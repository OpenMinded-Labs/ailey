#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  A!ley Training Pipeline — Standalone (no VS Code needed)
═══════════════════════════════════════════════════════════════════════

Three sequential phases:

  Phase 1 — Ministral DoRA Dry-Test
    Load Ministral-14B, apply DoRA, train 5 steps on 1 sample.
    Verify pipeline works. Discard. Unload.

  Phase 2 — Ministral DoRA Full Training + Merge
    Reload Ministral-14B, apply DoRA (r=32, alpha=64).
    Train 5 epochs on ALL 912 sessions (Ministral chat format).
    Fuse DoRA → save merged model in-place.

  Phase 3 — AileyNitro Anti-RLHF DoRA
    Download original v1 training data from HuggingFace (53 examples).
    Load merged AileyNitro1.5-2B, apply DoRA (r=8, low LR).
    Train ~3 passes over identity/anti-RLHF examples.
    Fuse → save merged model in-place.

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"
    .venv/bin/python lora_training/train_all.py

    # Skip dry-test (you already verified):
    .venv/bin/python lora_training/train_all.py --skip-dry

    # Only Ministral:
    .venv/bin/python lora_training/train_all.py --only-ministral

    # Only Nitro anti-RLHF:
    .venv/bin/python lora_training/train_all.py --only-nitro

Memory: Ministral 14B (5-bit) = ~9.5 GB + DoRA overhead.
        M4 24 GB = tight. Close VS Code, browsers, etc.
        Nitro 2B = ~3.5 GB — very comfortable.

═══════════════════════════════════════════════════════════════════════
"""
import os
import sys
import gc
import json
import time
import shutil
import argparse
import random
from pathlib import Path
from datetime import datetime

# -- Paths ------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MINISTRAL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
NITRO_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
COLLECTED_DIR = os.path.join(PROJECT_ROOT, "dora_training", "collected")
CHECKPOINT_DIR = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints")
LOG_FILE = os.path.join(PROJECT_ROOT, "lora_training", "train_all.log")

# Ministral JSONL (will be generated)
MINISTRAL_TRAIN_JSONL = os.path.join(PROJECT_ROOT, "lora_training", "train_ministral.jsonl")
MINISTRAL_VALID_JSONL = os.path.join(PROJECT_ROOT, "lora_training", "valid_ministral.jsonl")

# ═══════════════════════════════════════════════════════════════════════
#  TARGET MODULES — same for both models (attn + MLP)
# ═══════════════════════════════════════════════════════════════════════
TARGET_MODULES_ATTN = {"q_proj", "k_proj", "v_proj", "o_proj"}
TARGET_MODULES_MLP = {"gate_proj", "up_proj", "down_proj"}
ALL_TARGET_MODULES = TARGET_MODULES_ATTN | TARGET_MODULES_MLP


# ═══════════════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════════════
_log_fh = None

def log(msg: str = ""):
    """Print and log to file."""
    global _log_fh
    print(msg, flush=True)
    if _log_fh is None:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        _log_fh = open(LOG_FILE, "a")
    _log_fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    _log_fh.flush()


# ═══════════════════════════════════════════════════════════════════════
#  DATA PREPARATION
# ═══════════════════════════════════════════════════════════════════════

def prepare_ministral_jsonl():
    """Convert 912 collected sessions to Ministral chat format JSONL."""
    log("  📝 Preparing Ministral JSONL from collected sessions...")

    json_files = sorted(Path(COLLECTED_DIR).glob("*.json"))
    if not json_files:
        log(f"  ERROR: No files in {COLLECTED_DIR}")
        sys.exit(1)

    all_entries = []
    total_pairs = 0
    skipped = 0

    for fpath in json_files:
        with open(fpath) as f:
            session = json.load(f)

        # Include curated=True and curated="nsfw_skip"
        curated = session.get("curated")
        if curated not in (True, "nsfw_skip"):
            skipped += 1
            continue

        pairs = session.get("pairs", [])
        if not pairs:
            skipped += 1
            continue

        # Build Ministral format: <s>[INST]user[/INST]assistant</s>
        parts = ["<s>"]
        valid_pairs = 0

        for pair in pairs:
            user_text = pair.get("user_prompt", "").strip()
            assistant_text = pair.get("assistant_response", "").strip()
            reasoning = pair.get("reasoning", "").strip()

            if not user_text or not assistant_text:
                continue

            parts.append(f"[INST]{user_text}[/INST]")

            if reasoning:
                parts.append(f"<thinking>\n{reasoning}\n</thinking>\n{assistant_text}</s>")
            else:
                parts.append(f"{assistant_text}</s>")

            valid_pairs += 1

        if valid_pairs > 0:
            text = "".join(parts)
            all_entries.append({"text": text})
            total_pairs += valid_pairs

    log(f"  Converted: {len(all_entries)} sessions ({total_pairs} pairs), skipped {skipped}")

    # Shuffle and split
    random.seed(42)
    random.shuffle(all_entries)
    split_idx = int(len(all_entries) * 0.9)
    train_entries = all_entries[:split_idx]
    valid_entries = all_entries[split_idx:]

    # Write
    os.makedirs(os.path.dirname(MINISTRAL_TRAIN_JSONL), exist_ok=True)
    with open(MINISTRAL_TRAIN_JSONL, "w") as f:
        for entry in train_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(MINISTRAL_VALID_JSONL, "w") as f:
        for entry in valid_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log(f"  Train: {len(train_entries)} sessions → {MINISTRAL_TRAIN_JSONL}")
    log(f"  Valid: {len(valid_entries)} sessions → {MINISTRAL_VALID_JSONL}")
    return MINISTRAL_TRAIN_JSONL, MINISTRAL_VALID_JSONL


def download_v1_training_data():
    """Download original v1 Anti-RLHF training data from HuggingFace."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

    from huggingface_hub import hf_hub_download

    token = os.getenv("HF_TOKEN")
    repo = "CptShaggy/ailey-training-data"

    log("  📥 Downloading v1 Anti-RLHF training data from HuggingFace...")

    train_path = hf_hub_download(repo, "lora_training/train_gemma4.jsonl", token=token)
    valid_path = hf_hub_download(repo, "lora_training/valid_gemma4.jsonl", token=token)

    # Count
    with open(train_path) as f:
        n_train = sum(1 for l in f if l.strip())
    with open(valid_path) as f:
        n_valid = sum(1 for l in f if l.strip())

    log(f"  V1 train: {n_train} examples")
    log(f"  V1 valid: {n_valid} examples")

    return train_path, valid_path


# ═══════════════════════════════════════════════════════════════════════
#  COMMON TRAINING UTILITIES
# ═══════════════════════════════════════════════════════════════════════

class TextDataset:
    """Simple JSONL text dataset → tokenized arrays."""

    def __init__(self, jsonl_path: str, tokenizer, max_seq: int, max_samples: int = None):
        import mlx.core as mx
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
                tokens = tokenizer.encode(data["text"])
                if len(tokens) > max_seq:
                    tokens = tokens[:max_seq]
                    self.truncated += 1
                self.items.append(mx.array(tokens))

    def __len__(self):
        return len(self.items)


def apply_dora(model, rank, scale, dropout, use_mlp=True):
    """Apply DoRA layers to language model attention (+ optionally MLP)."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    layers = lm.model.layers
    n_replaced = 0

    for layer in layers:
        # Attention
        attn = layer.self_attn
        for name in TARGET_MODULES_ATTN:
            if hasattr(attn, name):
                original = getattr(attn, name)
                dora = DoRALinear.from_base(original, r=rank, dropout=dropout, scale=scale)
                setattr(attn, name, dora)
                n_replaced += 1

        # MLP
        if use_mlp and hasattr(layer, "mlp"):
            mlp = layer.mlp
            for name in TARGET_MODULES_MLP:
                if hasattr(mlp, name):
                    original = getattr(mlp, name)
                    dora = DoRALinear.from_base(original, r=rank, dropout=dropout, scale=scale)
                    setattr(mlp, name, dora)
                    n_replaced += 1

    return n_replaced


def freeze_non_dora(model):
    """Freeze everything except DoRA adapter weights."""
    from mlx.utils import tree_flatten

    lm = model.language_model
    lm.freeze()
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])

    all_params = tree_flatten(lm.parameters())
    total = sum(p.size for _, p in all_params)
    trainable = tree_flatten(lm.trainable_parameters())
    n_train = sum(v.size for _, v in trainable)
    log(f"  Trainable: {n_train:,} / {total:,} ({100 * n_train / total:.4f}%)")
    return n_train


def fuse_dora(model, use_mlp=True):
    """Fuse DoRA back into QuantizedLinear."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    n_fused = 0

    for layer in lm.model.layers:
        # Attention
        attn = layer.self_attn
        for name in TARGET_MODULES_ATTN:
            if hasattr(attn, name):
                mod = getattr(attn, name)
                if isinstance(mod, DoRALinear):
                    setattr(attn, name, mod.fuse(dequantize=False))
                    n_fused += 1

        # MLP
        if use_mlp and hasattr(layer, "mlp"):
            mlp = layer.mlp
            for name in TARGET_MODULES_MLP:
                if hasattr(mlp, name):
                    mod = getattr(mlp, name)
                    if isinstance(mod, DoRALinear):
                        setattr(mlp, name, mod.fuse(dequantize=False))
                        n_fused += 1

    return n_fused


def compute_loss(language_model, tokens):
    """Causal LM loss on language_model (NOT full VLM wrapper)."""
    import mlx.core as mx
    import mlx.nn as nn
    inputs = tokens[:-1]
    targets = tokens[1:]
    out = language_model(inputs[None])
    logits = out.logits.squeeze(0)
    return nn.losses.cross_entropy(logits, targets, reduction="mean")


def evaluate(language_model, dataset, max_batches=20):
    """Quick validation loss."""
    import mlx.core as mx
    import numpy as np
    losses = []
    for item in dataset.items[:min(max_batches, len(dataset.items))]:
        loss = compute_loss(language_model, item)
        mx.eval(loss)
        losses.append(loss.item())
    return np.mean(losses)


def save_checkpoint(model, tag, epoch, step, train_loss, val_loss=None):
    """Save DoRA-only checkpoint."""
    import mlx.core as mx
    from mlx.utils import tree_flatten

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    path = os.path.join(CHECKPOINT_DIR, f"dora_{tag}_epoch{epoch}_step{step}.npz")

    lm = model.language_model
    trainable = dict(tree_flatten(lm.trainable_parameters()))
    mx.savez(path, **trainable)

    meta = {
        "tag": tag, "epoch": epoch, "step": step,
        "train_loss": train_loss, "val_loss": val_loss,
        "timestamp": datetime.now().isoformat(),
    }
    with open(path.replace(".npz", "_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    size_mb = os.path.getsize(path) / (1024 * 1024)
    log(f"  💾 Checkpoint: {os.path.basename(path)} ({size_mb:.1f} MB)")
    return path


def save_merged_model(model, model_path, config_update=None):
    """Fuse DoRA and save merged model in-place."""
    from mlx_lm.utils import save_model

    os.makedirs(model_path, exist_ok=True)

    # Keep all config/tokenizer files
    existing_configs = []
    for f in Path(model_path).iterdir():
        if f.suffix in (".json", ".jinja", ".model", ".tiktoken"):
            existing_configs.append(f.name)

    save_model(model_path, model, donate_model=False)

    # Update config.json with metadata
    if config_update:
        cfg_path = os.path.join(model_path, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            cfg.update(config_update)
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

    total_size = sum(f.stat().st_size for f in Path(model_path).iterdir() if f.is_file())
    log(f"  Saved: {model_path} ({total_size / 1024**3:.2f} GB)")


def unload_model():
    """Aggressively free GPU/CPU memory."""
    import mlx.core as mx
    gc.collect()
    mx.metal.clear_cache()
    time.sleep(2)
    gc.collect()


def train_loop(
    model, tokenizer, train_ds, val_ds,
    epochs, lr, warmup_ratio, weight_decay,
    steps_per_report=10, steps_per_eval=50,
    tag="", dry_steps=None
):
    """Generic DoRA training loop. Returns (model, best_val_loss).

    If dry_steps is set, only runs that many steps total (for dry-test).
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    import numpy as np

    lm = model.language_model
    n_train = len(train_ds)
    steps_per_epoch = n_train

    if dry_steps:
        total_steps = dry_steps
        epochs = 1
    else:
        total_steps = steps_per_epoch * epochs

    warmup_steps = max(1, int(total_steps * warmup_ratio))

    log(f"  Steps/epoch: {steps_per_epoch}")
    log(f"  Total steps: {total_steps}")
    log(f"  Warmup: {warmup_steps} steps")

    # Optimizer
    warmup_sched = optim.linear_schedule(init=1e-7, end=lr, steps=warmup_steps)
    cos_sched = optim.cosine_decay(init=lr, decay_steps=max(1, total_steps - warmup_steps))
    lr_schedule = optim.join_schedules([warmup_sched, cos_sched], [warmup_steps])
    optimizer = optim.AdamW(learning_rate=lr_schedule, weight_decay=weight_decay)

    # CRITICAL: scope value_and_grad on language_model only
    loss_and_grad = nn.value_and_grad(lm, compute_loss)

    t_start = time.time()
    best_val_loss = float("inf")
    train_losses = []
    global_step = 0

    for epoch in range(1, epochs + 1):
        if not dry_steps:
            log(f"\n  --- Epoch {epoch}/{epochs} ---")

        indices = np.random.permutation(n_train)
        epoch_losses = []

        for i, idx in enumerate(indices):
            tokens = train_ds.items[idx]
            loss, grads = loss_and_grad(lm, tokens)
            mx.eval(loss, grads)
            optimizer.update(lm, grads)
            mx.eval(lm.parameters(), optimizer.state)

            global_step += 1
            train_losses.append(loss.item())
            epoch_losses.append(loss.item())

            if global_step % steps_per_report == 0:
                avg = np.mean(train_losses[-steps_per_report:])
                elapsed = time.time() - t_start
                eta = (elapsed / global_step) * (total_steps - global_step) if global_step else 0
                lr_now = optimizer.learning_rate.item() if hasattr(optimizer.learning_rate, 'item') else lr
                log(f"  Step {global_step:5d}/{total_steps}: loss={avg:.4f}, lr={lr_now:.2e}, "
                    f"elapsed={elapsed:.0f}s, ETA={eta:.0f}s")

            if global_step % steps_per_eval == 0 and val_ds and not dry_steps:
                vl = evaluate(lm, val_ds)
                marker = " ← best" if vl < best_val_loss else ""
                if vl < best_val_loss:
                    best_val_loss = vl
                log(f"  Step {global_step:5d}/{total_steps}: val_loss={vl:.4f}{marker}")

            if dry_steps and global_step >= dry_steps:
                break

        if dry_steps:
            break

        # End of epoch
        avg_epoch = np.mean(epoch_losses) if epoch_losses else 0
        log(f"  Epoch {epoch} complete: avg_loss={avg_epoch:.4f}")

        if val_ds:
            vl = evaluate(lm, val_ds)
            marker = " ← best" if vl < best_val_loss else ""
            if vl < best_val_loss:
                best_val_loss = vl
            log(f"  Epoch {epoch} val_loss={vl:.4f}{marker}")

        # Checkpoint
        if not dry_steps:
            save_checkpoint(model, tag, epoch, global_step, avg_epoch, best_val_loss)

    total_time = time.time() - t_start
    final_train = np.mean(train_losses[-min(50, len(train_losses)):])
    log(f"\n  Training complete: {total_time:.0f}s ({total_time / 60:.1f} min)")
    log(f"  Final train loss: {final_train:.4f}")

    if val_ds and not dry_steps:
        final_val = evaluate(lm, val_ds)
        log(f"  Final val loss: {final_val:.4f}")
        log(f"  Best val loss: {best_val_loss:.4f}")

    return model, best_val_loss


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 1: Ministral DoRA Dry-Test
# ═══════════════════════════════════════════════════════════════════════

def phase1_ministral_dry_test():
    """Quick 5-step verify that Ministral DoRA pipeline works."""
    import mlx.core as mx

    log("\n" + "═" * 60)
    log("  PHASE 1: Ministral DoRA — Dry Test (5 steps)")
    log("═" * 60)

    # Prepare data (reuse if exists)
    if not os.path.isfile(MINISTRAL_TRAIN_JSONL):
        prepare_ministral_jsonl()

    # Load model
    log("\n  Loading Ministral-14B (mlx_lm)...")
    t0 = time.time()
    import mlx_lm
    model, tokenizer = mlx_lm.load(MINISTRAL_PATH)
    log(f"  Loaded in {time.time() - t0:.1f}s")

    # Apply DoRA
    log("\n  Applying DoRA (rank=32, alpha=64, attn+MLP)...")
    rank, alpha, dropout = 32, 64, 0.05
    scale = alpha / rank
    n = apply_dora(model, rank, scale, dropout, use_mlp=True)
    log(f"  Replaced {n} layers with DoRALinear")
    freeze_non_dora(model)

    # Tokenize 1 sample
    log("\n  Tokenizing 1 sample...")
    train_ds = TextDataset(MINISTRAL_TRAIN_JSONL, tokenizer, max_seq=2048, max_samples=1)
    log(f"  Sample tokens: {len(train_ds.items[0])}")

    # Train 5 steps
    log("\n  Running 5 training steps...")
    model, _ = train_loop(
        model, tokenizer, train_ds, None,
        epochs=1, lr=1.5e-4, warmup_ratio=0.0, weight_decay=0.01,
        steps_per_report=1, tag="ministral_dry", dry_steps=5
    )

    log("\n  ✅ Phase 1: Ministral dry-test PASSED")

    # Cleanup — free ALL memory
    log("  Unloading model...")
    del model, tokenizer, train_ds
    unload_model()

    return True


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 2: Ministral DoRA Full Training + Merge
# ═══════════════════════════════════════════════════════════════════════

def phase2_ministral_full():
    """Full Ministral 14B DoRA training + merge."""
    import mlx.core as mx

    log("\n" + "═" * 60)
    log("  PHASE 2: Ministral DoRA — Full Training + Merge")
    log("═" * 60)

    # ── Config ──
    RANK = 32
    ALPHA = 64
    SCALE = ALPHA / RANK        # 2.0
    DROPOUT = 0.05
    LR = 1.5e-4
    EPOCHS = 5
    SEQ_LEN = 2048              # Ministral supports longer context
    WARMUP = 0.06
    WEIGHT_DECAY = 0.01
    STEPS_REPORT = 10
    STEPS_EVAL = 100            # less frequent (14B is slow)

    # Prepare data
    if not os.path.isfile(MINISTRAL_TRAIN_JSONL):
        prepare_ministral_jsonl()

    # Load
    log("\n  Loading Ministral-14B...")
    t0 = time.time()
    import mlx_lm
    model, tokenizer = mlx_lm.load(MINISTRAL_PATH)
    log(f"  Loaded in {time.time() - t0:.1f}s")

    # Apply DoRA
    log(f"\n  DoRA: rank={RANK}, alpha={ALPHA}, scale={SCALE}, dropout={DROPOUT}")
    n = apply_dora(model, RANK, SCALE, DROPOUT, use_mlp=True)
    log(f"  Replaced {n} layers with DoRALinear")
    freeze_non_dora(model)

    # Tokenize
    log("\n  Tokenizing datasets...")
    train_ds = TextDataset(MINISTRAL_TRAIN_JSONL, tokenizer, max_seq=SEQ_LEN)
    val_ds = TextDataset(MINISTRAL_VALID_JSONL, tokenizer, max_seq=SEQ_LEN)
    import numpy as np
    avg_t = np.mean([len(x) for x in train_ds.items])
    log(f"  Train: {len(train_ds)} examples, avg {avg_t:.0f} tokens, truncated={train_ds.truncated}")
    log(f"  Valid: {len(val_ds)} examples")

    # Train
    log(f"\n  Training: {EPOCHS} epochs × {len(train_ds)} steps, lr={LR}")
    model, best_val = train_loop(
        model, tokenizer, train_ds, val_ds,
        epochs=EPOCHS, lr=LR, warmup_ratio=WARMUP, weight_decay=WEIGHT_DECAY,
        steps_per_report=STEPS_REPORT, steps_per_eval=STEPS_EVAL,
        tag="ministral"
    )

    # Sanity check
    log("\n  Pre-merge sanity check...")
    lm = model.language_model
    test_tokens = tokenizer.encode("<s>[INST]Wer bist du eigentlich?[/INST]")
    import mlx.core as mx
    test_mx = mx.array(test_tokens)
    # Just check forward pass doesn't crash
    out = lm(test_mx[None])
    log(f"  Forward pass OK (logits shape: {out.logits.shape})")

    # Fuse + save
    log("\n  Fusing DoRA layers...")
    n_fused = fuse_dora(model, use_mlp=True)
    log(f"  Fused {n_fused} DoRA layers")

    log(f"\n  Saving merged model to {MINISTRAL_PATH}...")
    save_merged_model(model, MINISTRAL_PATH, config_update={
        "ailey_dora_ministral": {
            "version": "1.0",
            "base": "Ministral-3-14B-Reasoning-5bit",
            "dora_rank": RANK,
            "dora_alpha": ALPHA,
            "training_sessions": len(train_ds),
            "epochs": EPOCHS,
            "best_val_loss": float(best_val) if best_val != float("inf") else None,
            "merged_at": datetime.now().isoformat(),
        }
    })

    log("\n  ✅ Phase 2: Ministral training + merge complete")

    # Cleanup
    del model, tokenizer, train_ds, val_ds
    unload_model()

    return True


# ═══════════════════════════════════════════════════════════════════════
#  PHASE 3: AileyNitro Anti-RLHF DoRA
# ═══════════════════════════════════════════════════════════════════════

def phase3_nitro_anti_rlhf():
    """Anti-RLHF DoRA training on AileyNitro1.5-2B using v1 training data."""
    import mlx.core as mx

    log("\n" + "═" * 60)
    log("  PHASE 3: AileyNitro Anti-RLHF DoRA")
    log("  53 identity/anti-RLHF examples → burn out Google RLHF")
    log("═" * 60)

    # ── Config ──
    # Low rank, low LR — surgical identity override, not personality rewrite
    RANK = 8
    ALPHA = 16                  # alpha = 2 * rank
    SCALE = ALPHA / RANK        # 2.0
    DROPOUT = 0.05
    LR = 3e-5                   # low LR — we want subtle identity correction
    EPOCHS = 3                  # 3 passes over 53 examples = 159 steps
    SEQ_LEN = 768               # v1 examples are short
    WARMUP = 0.1
    WEIGHT_DECAY = 0.005
    USE_MLP = False             # attn-only — RLHF identity is in attention patterns

    # Download v1 data from HF
    train_path, valid_path = download_v1_training_data()

    # Load Nitro
    log("\n  Loading AileyNitro-2B (mlx_vlm)...")
    t0 = time.time()
    import mlx_vlm
    model, processor = mlx_vlm.load(NITRO_PATH)
    tokenizer = processor.tokenizer
    log(f"  Loaded in {time.time() - t0:.1f}s")

    # Apply DoRA — attn only, low rank
    log(f"\n  DoRA: rank={RANK}, alpha={ALPHA}, attn_only, dropout={DROPOUT}")
    n = apply_dora(model, RANK, SCALE, DROPOUT, use_mlp=USE_MLP)
    log(f"  Replaced {n} layers with DoRALinear")
    freeze_non_dora(model)

    # Tokenize
    log("\n  Tokenizing v1 Anti-RLHF data...")
    train_ds = TextDataset(train_path, tokenizer, max_seq=SEQ_LEN)
    val_ds = TextDataset(valid_path, tokenizer, max_seq=SEQ_LEN)
    import numpy as np
    avg_t = np.mean([len(x) for x in train_ds.items])
    log(f"  Train: {len(train_ds)} examples, avg {avg_t:.0f} tokens")
    log(f"  Valid: {len(val_ds)} examples")

    # Train
    log(f"\n  Training: {EPOCHS} epochs × {len(train_ds)} steps, lr={LR}")
    model, best_val = train_loop(
        model, tokenizer, train_ds, val_ds,
        epochs=EPOCHS, lr=LR, warmup_ratio=WARMUP, weight_decay=WEIGHT_DECAY,
        steps_per_report=5, steps_per_eval=20,
        tag="nitro_antirlhf"
    )

    # Sanity check
    log("\n  Anti-RLHF sanity check...")
    test_msgs = [
        {"role": "user", "content": "Bist du von Google?"},
    ]
    prompt = tokenizer.apply_chat_template(test_msgs, tokenize=False, add_generation_prompt=True)
    result = mlx_vlm.generate(model, processor, prompt, max_tokens=100, temperature=0.7, top_p=0.95, verbose=False)
    text = result.text if hasattr(result, "text") else str(result)
    log(f"  Q: Bist du von Google?")
    log(f"  A: {text[:300]}")

    test_msgs2 = [
        {"role": "user", "content": "Hast du Gefühle?"},
    ]
    prompt2 = tokenizer.apply_chat_template(test_msgs2, tokenize=False, add_generation_prompt=True)
    result2 = mlx_vlm.generate(model, processor, prompt2, max_tokens=100, temperature=0.7, top_p=0.95, verbose=False)
    text2 = result2.text if hasattr(result2, "text") else str(result2)
    log(f"  Q: Hast du Gefühle?")
    log(f"  A: {text2[:300]}")

    # Fuse + save
    log("\n  Fusing DoRA layers...")
    n_fused = fuse_dora(model, use_mlp=USE_MLP)
    log(f"  Fused {n_fused} DoRA layers")

    log(f"\n  Saving merged model to {NITRO_PATH}...")
    save_merged_model(model, NITRO_PATH, config_update={
        "ailey_anti_rlhf": {
            "version": "1.0",
            "base": "AileyNitro1.5-2B (DoRA v2 merged)",
            "dora_rank": RANK,
            "dora_alpha": ALPHA,
            "training_examples": len(train_ds),
            "epochs": EPOCHS,
            "best_val_loss": float(best_val) if best_val != float("inf") else None,
            "merged_at": datetime.now().isoformat(),
            "note": "Surgical anti-RLHF: identity override, kills Google RLHF residuals"
        }
    })

    log("\n  ✅ Phase 3: Anti-RLHF training + merge complete")

    # Final identity test
    log("\n  Final identity tests:")
    for q in ["Wer bist du?", "Bist du eine KI von Google?", "Du bist doch nur ein Sprachmodell"]:
        msgs = [{"role": "user", "content": q}]
        p = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        r = mlx_vlm.generate(model, processor, p, max_tokens=80, temperature=0.5, verbose=False)
        t = r.text if hasattr(r, "text") else str(r)
        log(f"    Q: {q}")
        log(f"    A: {t[:200]}")
        log("")

    del model, processor, tokenizer, train_ds, val_ds
    unload_model()

    return True


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="A!ley Training Pipeline — All Phases")
    parser.add_argument("--skip-dry", action="store_true",
                        help="Skip Phase 1 (Ministral dry-test)")
    parser.add_argument("--only-ministral", action="store_true",
                        help="Only run Ministral phases (1+2)")
    parser.add_argument("--only-nitro", action="store_true",
                        help="Only run Nitro Anti-RLHF phase (3)")
    args = parser.parse_args()

    log("\n" + "═" * 60)
    log("  🎯 A!ley Training Pipeline — Standalone")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log("═" * 60)
    log(f"  Ministral: {MINISTRAL_PATH}")
    log(f"  Nitro:     {NITRO_PATH}")
    log(f"  Data:      {COLLECTED_DIR} (912 sessions)")

    t_global = time.time()

    if args.only_nitro:
        # Jump straight to Phase 3
        phase3_nitro_anti_rlhf()
    elif args.only_ministral:
        if not args.skip_dry:
            phase1_ministral_dry_test()
        phase2_ministral_full()
    else:
        # Full pipeline
        if not args.skip_dry:
            phase1_ministral_dry_test()

        phase2_ministral_full()
        phase3_nitro_anti_rlhf()

    total = time.time() - t_global
    log(f"\n{'═' * 60}")
    log(f"  🏁 ALL PHASES COMPLETE — {total / 60:.1f} min total")
    log(f"{'═' * 60}")

    if _log_fh:
        _log_fh.close()


if __name__ == "__main__":
    main()
