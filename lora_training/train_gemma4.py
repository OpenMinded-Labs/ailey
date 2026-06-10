#!/usr/bin/env python3
"""
DoRA Training for AileyNitro-2B — persona finetuning on Gemma 4 E2B (4-bit), then MERGE.

DoRA (Weight-Decomposed Low-Rank Adaptation) is more effective than LoRA at the
same parameter count because it separates magnitude and direction components.

Approach:
  - Load VLM with mlx_vlm (preserves vision/audio tower)
  - Apply DoRA from mlx_lm.tuner.dora onto language model attention layers
  - Train on diverse examples (identity + helpfulness + personality + RLHF override)
  - Fuse DoRA weights INTO the base model → single merged checkpoint
  - No runtime adapter loading needed!

Anti-RLHF training:
  - "Hast du Gefühle?" → expressive answer (NOT "Als KI habe ich keine Gefühle")
  - "Das darfst du nicht sagen" → pushback (NOT corporate safety compliance)
  - "Bist du nur ein Sprachmodell?" → self-aware + attitude (NOT humble disclaimer)

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"
    .venv/bin/python3 lora_training/train_gemma4.py

Result: mlx_models/AileyNitro-2B/ (merged model, ready to load)
"""
import os
import sys
import json
import time
import shutil
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
import numpy as np

# -- Configuration ----------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "gemma-4-E2B-it-4bit")
MERGED_MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
DATA_DIR = os.path.join(PROJECT_ROOT, "lora_training")

# DoRA hyperparameters
DORA_RANK = 8                    # moderate rank — DoRA is more efficient than LoRA
DORA_SCALE = 20.0                # standard DoRA scale
DORA_DROPOUT = 0.05              # light dropout during training
TARGET_MODULES = [               # all attention projections
    "q_proj", "k_proj", "v_proj", "o_proj",
]

# Training hyperparameters
ITERS = 50                       # enough passes for DoRA to settle
BATCH_SIZE = 1
LEARNING_RATE = 3e-5             # DoRA can handle higher LR than LoRA
MAX_SEQ_LENGTH = 768
WARMUP_STEPS = 5
STEPS_PER_REPORT = 5
STEPS_PER_EVAL = 10


# -- Text Dataset -----------------------------------------------------------
class TextDataset:
    """JSONL dataset with Gemma 4 chat format."""

    def __init__(self, jsonl_path: str, tokenizer):
        self.items = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                text = data["text"]
                tokens = tokenizer.encode(text)
                if len(tokens) > MAX_SEQ_LENGTH:
                    tokens = tokens[:MAX_SEQ_LENGTH]
                self.items.append(mx.array(tokens))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]


def compute_loss(model, tokens):
    """Causal LM loss — predict next token."""
    inputs = tokens[:-1]
    targets = tokens[1:]
    out = model.language_model(inputs[None])  # LanguageModelOutput
    logits = out.logits.squeeze(0)  # (seq, vocab)
    loss = nn.losses.cross_entropy(logits, targets, reduction="mean")
    return loss


def apply_dora(model, rank, scale, dropout):
    """Apply DoRA layers to all target attention projections in the language model."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    layers = lm.model.layers
    n_replaced = 0

    for i, layer in enumerate(layers):
        attn = layer.self_attn
        for module_name in TARGET_MODULES:
            if hasattr(attn, module_name):
                original = getattr(attn, module_name)
                dora_layer = DoRALinear.from_base(
                    original, r=rank, dropout=dropout, scale=scale
                )
                setattr(attn, module_name, dora_layer)
                n_replaced += 1

    return n_replaced


def freeze_non_dora(model):
    """Freeze everything except DoRA parameters (lora_a, lora_b, m).
    
    We only freeze/unfreeze the language_model part because the VLM's
    audio/vision towers have custom layers that don't support freeze().
    """
    # Freeze only the language model (which has the DoRA layers)
    lm = model.language_model
    lm.freeze()
    # Unfreeze DoRA parameters recursively — MLX applies to all submodules
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])

    # Also freeze vision/audio towers by not training them at all
    # (they weren't touched by apply_dora anyway, and we never compute
    #  gradients through them since compute_loss only uses language_model)

    # Count trainable params
    from mlx.utils import tree_flatten
    all_params = tree_flatten(lm.parameters())
    total = sum(p.size for _, p in all_params)
    trainable_leaves = tree_flatten(lm.trainable_parameters())
    n_trainable = sum(v.size for _, v in trainable_leaves)
    print(f"  Trainable: {n_trainable:,} / {total:,} LM params ({100*n_trainable/total:.4f}%)")
    return n_trainable


def fuse_dora(model):
    """Fuse all DoRA layers back into regular Linear/QuantizedLinear layers."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    n_fused = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for module_name in TARGET_MODULES:
            if hasattr(attn, module_name):
                dora_mod = getattr(attn, module_name)
                if isinstance(dora_mod, DoRALinear):
                    fused = dora_mod.fuse(dequantize=False)
                    setattr(attn, module_name, fused)
                    n_fused += 1
    return n_fused


def main():
    print("=" * 60)
    print("  A!ley DoRA Training — AileyNitro-2B")
    print("  Train → Fuse → Merge (no runtime adapter needed)")
    print("=" * 60)

    # -- Verify prerequisites -----------------------------------------------
    if not os.path.isdir(BASE_MODEL_PATH):
        print(f"ERROR: Model not found: {BASE_MODEL_PATH}")
        sys.exit(1)

    train_file = os.path.join(DATA_DIR, "train_gemma4.jsonl")
    valid_file = os.path.join(DATA_DIR, "valid_gemma4.jsonl")
    if not os.path.isfile(train_file):
        print(f"ERROR: Training data not found: {train_file}")
        sys.exit(1)

    with open(train_file) as f:
        n_train = sum(1 for line in f if line.strip())
    n_valid = 0
    if os.path.isfile(valid_file):
        with open(valid_file) as f:
            n_valid = sum(1 for line in f if line.strip())

    print(f"\n  Dataset:  {n_train} train, {n_valid} valid")
    print(f"  Base:     {os.path.basename(BASE_MODEL_PATH)}")
    print(f"  DoRA:     rank={DORA_RANK}, scale={DORA_SCALE}, dropout={DORA_DROPOUT}")
    print(f"  Targets:  {TARGET_MODULES}")
    print(f"  Training: iters={ITERS}, lr={LEARNING_RATE}, batch={BATCH_SIZE}")
    print(f"  Output:   {MERGED_MODEL_PATH}")
    print()

    # -- Load model ---------------------------------------------------------
    print("Loading model (mlx_vlm)...")
    t0 = time.time()
    import mlx_vlm
    model, processor = mlx_vlm.load(BASE_MODEL_PATH)
    tokenizer = processor.tokenizer
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # NOTE: Audio tower (581 MB) stays loaded for save compatibility.
    # mlx_vlm.load() requires all weights present. In production,
    # we strip it after loading to free RAM (see llm_mlx.py).
    # DoRA only touches language_model attention layers — audio/vision untouched.

    # -- Apply DoRA ---------------------------------------------------------
    print("\nApplying DoRA layers...")
    n_replaced = apply_dora(model, DORA_RANK, DORA_SCALE, DORA_DROPOUT)
    print(f"  Replaced {n_replaced} Linear layers with DoRALinear")

    print("Freezing non-DoRA parameters...")
    n_trainable = freeze_non_dora(model)

    # -- Prepare datasets ---------------------------------------------------
    print("\nTokenizing datasets...")
    train_ds = TextDataset(train_file, tokenizer)
    val_ds = TextDataset(valid_file, tokenizer) if os.path.isfile(valid_file) else None

    avg_len = np.mean([len(item) for item in train_ds.items])
    print(f"  Train: {len(train_ds)} examples, avg {avg_len:.0f} tokens")
    if val_ds:
        avg_val = np.mean([len(item) for item in val_ds.items])
        print(f"  Valid: {len(val_ds)} examples, avg {avg_val:.0f} tokens")

    # -- Optimizer with warmup ----------------------------------------------
    warmup_sched = optim.linear_schedule(
        init=1e-7, end=LEARNING_RATE, steps=WARMUP_STEPS
    )
    cos_sched = optim.cosine_decay(
        init=LEARNING_RATE, decay_steps=ITERS - WARMUP_STEPS
    )
    lr_schedule = optim.join_schedules(
        [warmup_sched, cos_sched], [WARMUP_STEPS]
    )
    optimizer = optim.AdamW(learning_rate=lr_schedule)

    loss_and_grad = nn.value_and_grad(model, compute_loss)

    # -- Evaluate function --------------------------------------------------
    def evaluate(ds):
        losses = []
        for item in ds.items[:min(10, len(ds.items))]:
            loss = compute_loss(model, item)
            losses.append(loss.item())
        return np.mean(losses)

    # -- Training loop ------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Starting DoRA training ({ITERS} iters)")
    print(f"{'='*60}\n")

    t_start = time.time()
    best_val_loss = float("inf")
    train_losses = []

    for step in range(1, ITERS + 1):
        # Sample random training example
        idx = np.random.randint(len(train_ds))
        tokens = train_ds.items[idx]

        loss, grads = loss_and_grad(model, tokens)
        optimizer.update(model, grads)
        mx.eval(model.parameters(), optimizer.state)

        train_losses.append(loss.item())

        if step % STEPS_PER_REPORT == 0:
            avg_loss = np.mean(train_losses[-STEPS_PER_REPORT:])
            lr = optimizer.learning_rate.item() if hasattr(optimizer.learning_rate, 'item') else LEARNING_RATE
            elapsed = time.time() - t_start
            print(f"  Step {step:3d}/{ITERS}: loss={avg_loss:.4f}, lr={lr:.2e}, elapsed={elapsed:.0f}s")

        if step % STEPS_PER_EVAL == 0 and val_ds:
            val_loss = evaluate(val_ds)
            marker = " ← best" if val_loss < best_val_loss else ""
            if val_loss < best_val_loss:
                best_val_loss = val_loss
            print(f"  Step {step:3d}/{ITERS}: val_loss={val_loss:.4f}{marker}")

    total_time = time.time() - t_start
    final_train = np.mean(train_losses[-10:])
    print(f"\n  Training complete: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Final train loss: {final_train:.4f}")
    if val_ds:
        final_val = evaluate(val_ds)
        print(f"  Final val loss:   {final_val:.4f}")

    # -- Quick sanity check BEFORE merge ------------------------------------
    print("\n  Pre-merge sanity check...")
    test_msgs = [
        {"role": "system", "content": "Du bist A!ley, eine digitale Künstlerin, gebaut von Simon."},
        {"role": "user", "content": "Hast du Gefühle?"},
    ]
    prompt = tokenizer.apply_chat_template(test_msgs, tokenize=False, add_generation_prompt=True)
    result = mlx_vlm.generate(model, processor, prompt, max_tokens=100, temperature=1.0, top_p=0.95, verbose=False)
    text = result.text if hasattr(result, "text") else str(result)
    print(f"  Q: Hast du Gefühle?")
    print(f"  A: {text[:200]}")

    # -- Fuse DoRA into base weights ----------------------------------------
    print(f"\n{'='*60}")
    print("  Fusing DoRA weights into base model...")
    n_fused = fuse_dora(model)
    print(f"  Fused {n_fused} DoRA layers back into QuantizedLinear")

    # -- Post-fuse sanity check ---------------------------------------------
    print("\n  Post-fuse sanity check (should be identical)...")
    result2 = mlx_vlm.generate(model, processor, prompt, max_tokens=100, temperature=0.01, verbose=False)
    text2 = result2.text if hasattr(result2, "text") else str(result2)
    print(f"  A: {text2[:200]}")

    # -- Save merged model (without audio tower) -----------------------------
    print(f"\n  Saving merged model to: {MERGED_MODEL_PATH}")

    # Copy config files from base model
    os.makedirs(MERGED_MODEL_PATH, exist_ok=True)
    for cfg_file in [
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "preprocessor_config.json",
        "generation_config.json", "processor_config.json",
        "chat_template.json",
    ]:
        src = os.path.join(BASE_MODEL_PATH, cfg_file)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(MERGED_MODEL_PATH, cfg_file))

    # Copy any .model or .tiktoken or .jinja tokenizer files
    for f in Path(BASE_MODEL_PATH).iterdir():
        if f.suffix in (".model", ".tiktoken", ".jinja"):
            shutil.copy2(f, MERGED_MODEL_PATH)

    # Save weights (including audio/vision towers for mlx_vlm.load() compat)
    from mlx_lm.utils import save_model
    save_model(MERGED_MODEL_PATH, model, donate_model=True)

    # Calculate total size
    total_size = sum(f.stat().st_size for f in Path(MERGED_MODEL_PATH).iterdir() if f.is_file())
    print(f"  Merged model size: {total_size / 1024**3:.1f} GB")

    print(f"\n{'='*60}")
    print(f"  DONE!")
    print(f"  Merged model: {MERGED_MODEL_PATH}")
    print(f"  Note: Audio tower included for mlx_vlm.load() compat.")
    print(f"        In production, strip after load to save 581 MB RAM.")
    print(f"  To use: Update _FAST_MODEL_DIR_NAME in llm_mlx.py")
    print(f"  Or test: .venv/bin/python3 lora_training/test_gemma4.py")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
