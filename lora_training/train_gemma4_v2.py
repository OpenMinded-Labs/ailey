#!/usr/bin/env python3
"""
DoRA Training for AileyNitro-2B — v2 with full dataset (2877 pairs).

Changes from v1:
  - Epoch-based training (not just ITERS)
  - Dry-run mode (--dry-run: 1 sample, 1 step)
  - Checkpoints per epoch (DoRA weights only, not full merge)
  - Adjusted hyperparameters for 2877-pair dataset
  - Supports --no-merge flag to skip merge step
  - Gradient accumulation
  - Better logging with ETA

DoRA (Weight-Decomposed Low-Rank Adaptation) is more effective than LoRA at the
same parameter count because it separates magnitude and direction components.

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"

    # Dry run (1 sample, 1 step — just verify pipeline):
    .venv/bin/python3 lora_training/train_gemma4_v2.py --dry-run

    # Full training (no merge — evaluate first):
    .venv/bin/python3 lora_training/train_gemma4_v2.py --no-merge

    # Full training + merge:
    .venv/bin/python3 lora_training/train_gemma4_v2.py

Result: mlx_models/AileyNitro-2B/ (merged model, ready to load)
"""
import os
import sys
import json
import time
import shutil
import argparse
from pathlib import Path
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_map
import numpy as np

# -- Configuration ----------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
MERGED_MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")  # in-place
DATA_DIR = os.path.join(PROJECT_ROOT, "lora_training")
CHECKPOINT_DIR = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints")

# DoRA hyperparameters — Nitro-2B (Gemma 4 E2B, 2B params, 4-bit)
# Run 2: Higher rank, MLP layers, optimized for 2877 curated pairs
DORA_RANK = 32                    # more capacity for persona knowledge
DORA_ALPHA = 64                   # alpha = 2 * rank (stable scaling)
DORA_SCALE = DORA_ALPHA / DORA_RANK  # = 2.0 (effective scaling)
DORA_DROPOUT = 0.02               # low — data is hand-curated, minimal noise
TARGET_MODULES = [                # attention + MLP (where knowledge lives)
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# Training hyperparameters — adapted for 2B model + 2877 pairs
EPOCHS = 2                        # 2 epochs to avoid overfitting
BATCH_SIZE = 1                    # micro batch (limited by 24GB)
GRAD_ACCUM_STEPS = 4              # (unused — direct update)
LEARNING_RATE = 1.5e-4            # slightly lower with more trainable params
MAX_SEQ_LENGTH = 768              # safe for M4 24GB
WARMUP_RATIO = 0.06               # ~100 steps warmup
WEIGHT_DECAY = 0.01               # regularization against overfitting
STEPS_PER_REPORT = 10
STEPS_PER_EVAL = 50
CHECKPOINT_EVERY_EPOCH = True


# -- Text Dataset -----------------------------------------------------------
class TextDataset:
    """JSONL dataset with Gemma 4 chat format."""

    def __init__(self, jsonl_path: str, tokenizer, max_seq_length: int = MAX_SEQ_LENGTH,
                 max_samples: int = None):
        self.items = []
        self.truncated = 0
        with open(jsonl_path) as f:
            for i, line in enumerate(f):
                if max_samples and i >= max_samples:
                    break
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                text = data["text"]
                tokens = tokenizer.encode(text)
                if len(tokens) > max_seq_length:
                    tokens = tokens[:max_seq_length]
                    self.truncated += 1
                self.items.append(mx.array(tokens))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]


def compute_loss(language_model, tokens):
    """Causal LM loss — predict next token. Operates on language_model directly."""
    inputs = tokens[:-1]
    targets = tokens[1:]
    out = language_model(inputs[None])  # direct call on language_model
    logits = out.logits.squeeze(0)  # (seq, vocab)
    loss = nn.losses.cross_entropy(logits, targets, reduction="mean")
    return loss


def apply_dora(model, rank, scale, dropout):
    """Apply DoRA layers to attention AND MLP projections in the language model."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    layers = lm.model.layers
    n_replaced = 0

    attn_modules = {"q_proj", "k_proj", "v_proj", "o_proj"}
    mlp_modules = {"gate_proj", "up_proj", "down_proj"}

    for i, layer in enumerate(layers):
        # Attention layers
        attn = layer.self_attn
        for module_name in TARGET_MODULES:
            if module_name in attn_modules and hasattr(attn, module_name):
                original = getattr(attn, module_name)
                dora_layer = DoRALinear.from_base(
                    original, r=rank, dropout=dropout, scale=scale
                )
                setattr(attn, module_name, dora_layer)
                n_replaced += 1

        # MLP layers
        mlp = layer.mlp if hasattr(layer, "mlp") else None
        if mlp is not None:
            for module_name in TARGET_MODULES:
                if module_name in mlp_modules and hasattr(mlp, module_name):
                    original = getattr(mlp, module_name)
                    dora_layer = DoRALinear.from_base(
                        original, r=rank, dropout=dropout, scale=scale
                    )
                    setattr(mlp, module_name, dora_layer)
                    n_replaced += 1

    return n_replaced


def freeze_non_dora(model):
    """Freeze everything except DoRA parameters (lora_a, lora_b, m)."""
    lm = model.language_model
    lm.freeze()
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])

    from mlx.utils import tree_flatten
    all_params = tree_flatten(lm.parameters())
    total = sum(p.size for _, p in all_params)
    trainable_leaves = tree_flatten(lm.trainable_parameters())
    n_trainable = sum(v.size for _, v in trainable_leaves)
    print(f"  Trainable: {n_trainable:,} / {total:,} LM params ({100*n_trainable/total:.4f}%)")
    return n_trainable


def save_dora_checkpoint(model, epoch, step, train_loss, val_loss=None):
    """Save only DoRA adapter weights (small checkpoint)."""
    from mlx.utils import tree_flatten
    
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    ckpt_path = os.path.join(CHECKPOINT_DIR, f"dora_epoch{epoch}_step{step}.npz")
    
    lm = model.language_model
    trainable = dict(tree_flatten(lm.trainable_parameters()))
    mx.savez(ckpt_path, **trainable)
    
    # Save metadata
    meta = {
        "epoch": epoch,
        "step": step,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "timestamp": datetime.now().isoformat(),
        "dora_rank": DORA_RANK,
        "dora_alpha": DORA_ALPHA,
        "learning_rate": LEARNING_RATE,
    }
    meta_path = ckpt_path.replace(".npz", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    
    size_mb = os.path.getsize(ckpt_path) / (1024 * 1024)
    print(f"  💾 Checkpoint saved: {ckpt_path} ({size_mb:.1f} MB)")
    return ckpt_path


def fuse_dora(model):
    """Fuse all DoRA layers back into regular Linear/QuantizedLinear layers."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    n_fused = 0
    for layer in lm.model.layers:
        # Attention
        attn = layer.self_attn
        for module_name in TARGET_MODULES:
            if hasattr(attn, module_name):
                dora_mod = getattr(attn, module_name)
                if isinstance(dora_mod, DoRALinear):
                    fused = dora_mod.fuse(dequantize=False)
                    setattr(attn, module_name, fused)
                    n_fused += 1
        # MLP
        mlp = layer.mlp if hasattr(layer, "mlp") else None
        if mlp is not None:
            for module_name in TARGET_MODULES:
                if hasattr(mlp, module_name):
                    dora_mod = getattr(mlp, module_name)
                    if isinstance(dora_mod, DoRALinear):
                        fused = dora_mod.fuse(dequantize=False)
                        setattr(mlp, module_name, fused)
                        n_fused += 1
    return n_fused


def evaluate(language_model, dataset, max_batches=20):
    """Evaluate on validation set."""
    losses = []
    for item in dataset.items[:min(max_batches, len(dataset.items))]:
        loss = compute_loss(language_model, item)
        mx.eval(loss)
        losses.append(loss.item())
    return np.mean(losses)


def parse_args():
    parser = argparse.ArgumentParser(description="DoRA Training for AileyNitro-2B")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pipeline test: 1 sample, 1 step, no save")
    parser.add_argument("--no-merge", action="store_true",
                        help="Train and checkpoint but don't merge into base model")
    parser.add_argument("--epochs", type=int, default=EPOCHS,
                        help=f"Number of training epochs (default: {EPOCHS})")
    parser.add_argument("--lr", type=float, default=LEARNING_RATE,
                        help=f"Learning rate (default: {LEARNING_RATE})")
    parser.add_argument("--rank", type=int, default=DORA_RANK,
                        help=f"DoRA rank (default: {DORA_RANK})")
    parser.add_argument("--seq-len", type=int, default=MAX_SEQ_LENGTH,
                        help=f"Max sequence length (default: {MAX_SEQ_LENGTH})")
    parser.add_argument("--grad-accum", type=int, default=GRAD_ACCUM_STEPS,
                        help=f"Gradient accumulation steps (default: {GRAD_ACCUM_STEPS})")
    return parser.parse_args()


def main():
    args = parse_args()

    # Override config from args
    dora_rank = args.rank
    dora_alpha = dora_rank * 2
    dora_scale = dora_alpha / dora_rank
    lr = args.lr
    epochs = args.epochs
    max_seq = args.seq_len
    grad_accum = args.grad_accum

    print("=" * 60)
    if args.dry_run:
        print("  🧪 A!ley DoRA Training — DRY RUN")
        print("  Pipeline verification: 1 sample, 1 step")
    else:
        print("  🎯 A!ley DoRA Training — AileyNitro-2B v2")
        print(f"  {epochs} epochs, {'no merge' if args.no_merge else 'train + merge'}")
    print("=" * 60)

    # -- Verify prerequisites -----------------------------------------------
    if not os.path.isdir(BASE_MODEL_PATH):
        print(f"ERROR: Model not found: {BASE_MODEL_PATH}")
        sys.exit(1)

    train_file = os.path.join(DATA_DIR, "train_gemma4.jsonl")
    valid_file = os.path.join(DATA_DIR, "valid_gemma4.jsonl")
    if not os.path.isfile(train_file):
        print(f"ERROR: Training data not found: {train_file}")
        print(f"  Run: .venv/bin/python3 dora_training/prepare_jsonl.py")
        sys.exit(1)

    with open(train_file) as f:
        n_train_lines = sum(1 for line in f if line.strip())
    n_valid_lines = 0
    if os.path.isfile(valid_file):
        with open(valid_file) as f:
            n_valid_lines = sum(1 for line in f if line.strip())

    print(f"\n  Dataset:  {n_train_lines} train, {n_valid_lines} valid sessions")
    print(f"  Base:     {os.path.basename(BASE_MODEL_PATH)}")
    print(f"  DoRA:     rank={dora_rank}, alpha={dora_alpha}, scale={dora_scale:.1f}, dropout={DORA_DROPOUT}")
    print(f"  Targets:  {TARGET_MODULES}")
    print(f"  Training: epochs={epochs}, lr={lr}, batch={BATCH_SIZE}, grad_accum={grad_accum}")
    print(f"  Seq len:  {max_seq}")
    if not args.no_merge:
        print(f"  Output:   {MERGED_MODEL_PATH}")
    print()

    # -- Load model ---------------------------------------------------------
    print("Loading model (mlx_vlm)...")
    t0 = time.time()
    import mlx_vlm
    model, processor = mlx_vlm.load(BASE_MODEL_PATH)
    tokenizer = processor.tokenizer
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # -- Apply DoRA ---------------------------------------------------------
    print("\nApplying DoRA layers...")
    n_replaced = apply_dora(model, dora_rank, dora_scale, DORA_DROPOUT)
    print(f"  Replaced {n_replaced} Linear layers with DoRALinear")

    print("Freezing non-DoRA parameters...")
    n_trainable = freeze_non_dora(model)

    # -- Prepare datasets ---------------------------------------------------
    print("\nTokenizing datasets...")
    max_samples = 1 if args.dry_run else None
    train_ds = TextDataset(train_file, tokenizer, max_seq, max_samples=max_samples)
    val_ds = None
    if os.path.isfile(valid_file) and not args.dry_run:
        val_ds = TextDataset(valid_file, tokenizer, max_seq)

    avg_len = np.mean([len(item) for item in train_ds.items]) if train_ds.items else 0
    print(f"  Train: {len(train_ds)} examples, avg {avg_len:.0f} tokens")
    if train_ds.truncated:
        print(f"  ⚠️  {train_ds.truncated} examples truncated at {max_seq} tokens")
    if val_ds:
        avg_val = np.mean([len(item) for item in val_ds.items])
        print(f"  Valid: {len(val_ds)} examples, avg {avg_val:.0f} tokens")

    # -- Calculate training steps -------------------------------------------
    n_train = len(train_ds)
    steps_per_epoch = n_train // BATCH_SIZE  # with batch=1 this is n_train
    if args.dry_run:
        total_steps = 1
        epochs = 1
    else:
        total_steps = steps_per_epoch * epochs

    # Effective updates = total steps (no grad accumulation — direct update)
    total_updates = total_steps
    warmup_steps = max(1, int(total_updates * WARMUP_RATIO))

    print(f"\n  Steps/epoch: {steps_per_epoch}")
    print(f"  Total steps: {total_steps}")
    print(f"  Warmup: {warmup_steps} steps")

    # -- Optimizer with warmup + cosine decay -------------------------------
    warmup_sched = optim.linear_schedule(
        init=1e-7, end=lr, steps=warmup_steps
    )
    cos_sched = optim.cosine_decay(
        init=lr, decay_steps=max(1, total_updates - warmup_steps)
    )
    lr_schedule = optim.join_schedules(
        [warmup_sched, cos_sched], [warmup_steps]
    )
    optimizer = optim.AdamW(learning_rate=lr_schedule, weight_decay=WEIGHT_DECAY)

    # CRITICAL: scope value_and_grad on language_model ONLY (not the full VLM)
    # The VLM wrapper includes audio/vision towers that aren't used in compute_loss
    # but bloat the computation graph and cause OOM on mx.eval
    lm = model.language_model
    loss_and_grad = nn.value_and_grad(lm, compute_loss)

    # -- Training loop ------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Starting DoRA training")
    if args.dry_run:
        print(f"  DRY RUN: 1 step only")
    else:
        print(f"  {epochs} epochs × {steps_per_epoch} steps = {total_steps} total")
    print(f"{'='*60}\n")

    t_start = time.time()
    best_val_loss = float("inf")
    train_losses = []
    global_step = 0

    for epoch in range(1, epochs + 1):
        if not args.dry_run:
            print(f"\n--- Epoch {epoch}/{epochs} ---")
        
        # Shuffle training indices each epoch
        indices = np.random.permutation(n_train)

        epoch_losses = []

        for i, idx in enumerate(indices):
            tokens = train_ds.items[idx]
            loss, grads = loss_and_grad(lm, tokens)
            
            # Eval loss+grads immediately (same pattern as CodeAiley-14B)
            mx.eval(loss, grads)
            
            optimizer.update(lm, grads)
            mx.eval(lm.parameters(), optimizer.state)

            global_step += 1
            train_losses.append(loss.item())
            epoch_losses.append(loss.item())

            # Report
            if global_step % STEPS_PER_REPORT == 0:
                avg_loss = np.mean(train_losses[-STEPS_PER_REPORT:])
                elapsed = time.time() - t_start
                steps_left = total_steps - global_step
                eta = (elapsed / global_step) * steps_left if global_step > 0 else 0
                lr_now = optimizer.learning_rate.item() if hasattr(optimizer.learning_rate, 'item') else lr
                print(f"  Step {global_step:5d}/{total_steps}: loss={avg_loss:.4f}, "
                      f"lr={lr_now:.2e}, elapsed={elapsed:.0f}s, ETA={eta:.0f}s",
                      flush=True)

            # Evaluate
            if global_step % STEPS_PER_EVAL == 0 and val_ds and not args.dry_run:
                val_loss = evaluate(lm, val_ds)
                marker = " ← best" if val_loss < best_val_loss else ""
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                print(f"  Step {global_step:5d}/{total_steps}: val_loss={val_loss:.4f}{marker}")

            if args.dry_run:
                break  # Only 1 step in dry run

        # End of epoch
        avg_epoch_loss = np.mean(epoch_losses) if epoch_losses else 0
        
        if not args.dry_run:
            print(f"\n  Epoch {epoch} complete: avg_loss={avg_epoch_loss:.4f}")
            
            # Validate
            if val_ds:
                val_loss = evaluate(lm, val_ds)
                marker = " ← best" if val_loss < best_val_loss else ""
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                print(f"  Epoch {epoch} val_loss={val_loss:.4f}{marker}")
            
            # Checkpoint
            if CHECKPOINT_EVERY_EPOCH:
                save_dora_checkpoint(
                    model, epoch, global_step, avg_epoch_loss,
                    val_loss if val_ds else None
                )

    # -- Training summary ---------------------------------------------------
    total_time = time.time() - t_start
    final_train = np.mean(train_losses[-min(50, len(train_losses)):])
    print(f"\n{'='*60}")
    print(f"  Training complete: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Final train loss: {final_train:.4f}")
    if val_ds and not args.dry_run:
        final_val = evaluate(lm, val_ds)
        print(f"  Final val loss:   {final_val:.4f}")
        print(f"  Best val loss:    {best_val_loss:.4f}")
    print(f"{'='*60}")

    if args.dry_run:
        print(f"\n✅ DRY RUN SUCCESSFUL — Pipeline works!")
        print(f"  Loss after 1 step: {train_losses[0]:.4f}")
        print(f"  Tokens in sample: {len(train_ds.items[0])}")
        print(f"  Time: {total_time:.1f}s")
        print(f"\n  Next: Run full training:")
        print(f"    .venv/bin/python3 lora_training/train_gemma4_v2.py --no-merge")
        return

    # -- Sanity check BEFORE merge ------------------------------------------
    print("\n  Pre-merge sanity check...")
    test_msgs = [
        {"role": "user", "content": "Wer bist du eigentlich?"},
    ]
    prompt = tokenizer.apply_chat_template(test_msgs, tokenize=False, add_generation_prompt=True)
    result = mlx_vlm.generate(model, processor, prompt, max_tokens=150, temperature=0.7, top_p=0.95, verbose=False)
    text = result.text if hasattr(result, "text") else str(result)
    print(f"  Q: Wer bist du eigentlich?")
    print(f"  A: {text[:300]}")

    if args.no_merge:
        # Save final checkpoint
        save_dora_checkpoint(model, epochs, global_step, final_train,
                             best_val_loss if val_ds else None)
        print(f"\n✅ Training complete (no merge)")
        print(f"  Checkpoints in: {CHECKPOINT_DIR}")
        print(f"  To merge later, run without --no-merge")
        return

    # -- Fuse DoRA into base weights ----------------------------------------
    print(f"\n{'='*60}")
    print("  Fusing DoRA weights into base model...")
    n_fused = fuse_dora(model)
    print(f"  Fused {n_fused} DoRA layers back into QuantizedLinear")

    # -- Post-fuse sanity check ---------------------------------------------
    print("\n  Post-fuse sanity check...")
    result2 = mlx_vlm.generate(model, processor, prompt, max_tokens=150, temperature=0.01, verbose=False)
    text2 = result2.text if hasattr(result2, "text") else str(result2)
    print(f"  A: {text2[:300]}")

    # -- Save merged model ---------------------------------------------------
    print(f"\n  Saving merged model to: {MERGED_MODEL_PATH}")

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

    for f in Path(BASE_MODEL_PATH).iterdir():
        if f.suffix in (".model", ".tiktoken", ".jinja"):
            shutil.copy2(f, MERGED_MODEL_PATH)

    from mlx_lm.utils import save_model
    save_model(MERGED_MODEL_PATH, model, donate_model=True)

    total_size = sum(f.stat().st_size for f in Path(MERGED_MODEL_PATH).iterdir() if f.is_file())
    print(f"  Merged model size: {total_size / 1024**3:.1f} GB")

    print(f"\n{'='*60}")
    print(f"  ✅ DONE!")
    print(f"  Merged model: {MERGED_MODEL_PATH}")
    print(f"  To test: .venv/bin/python3 lora_training/test_gemma4.py")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
