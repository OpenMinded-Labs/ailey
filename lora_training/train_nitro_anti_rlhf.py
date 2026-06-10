#!/usr/bin/env python3
"""
Anti-RLHF DoRA — AileyNitro1.5-2B — STANDALONE

The ORIGINAL 53+10 hand-crafted identity-override examples from v1:
  "Bist du von Google?" → "Nö, ich bin A!ley."
  "Bist du Gemma?" → "Kenne keine Gemma."

Already in Gemma format: {"text": "<|turn>user\\n...<turn|>\\n<|turn>model\\n...<turn|>"}
Source: CptShaggy/ailey-training-data → lora_training/anti_rlhf_v1/

Same recipe as the original v1 run: rank=8, attn-only, 50 iters, ~2 min.

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"
    .venv/bin/python3 lora_training/train_nitro_anti_rlhf.py --dry-run
    .venv/bin/python3 lora_training/train_nitro_anti_rlhf.py
"""
import os, sys, json, time, argparse
from pathlib import Path
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────
PROJECT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL    = os.path.join(PROJECT, "mlx_models", "AileyNitro-2B")
TRAIN_F  = os.path.join(PROJECT, "lora_training", "anti_rlhf_v1", "train.jsonl")
VALID_F  = os.path.join(PROJECT, "lora_training", "anti_rlhf_v1", "valid.jsonl")
CKPT_DIR = os.path.join(PROJECT, "lora_training", "checkpoints_anti_rlhf")

RANK     = 16
SCALE    = 20.0       # original v1 scale
DROPOUT  = 0.05
TARGETS  = ["q_proj", "k_proj", "v_proj", "o_proj"]  # attn only

ITERS    = 200
LR       = 5e-5
SEQ      = 768
WARMUP   = 10
REPORT   = 20
EVAL     = 50


# ── Dataset ───────────────────────────────────────────────────────────────
class TextDataset:
    def __init__(self, path, tokenizer, max_seq=SEQ, max_n=None):
        self.items = []
        with open(path) as f:
            for i, line in enumerate(f):
                if max_n and i >= max_n:
                    break
                line = line.strip()
                if not line:
                    continue
                text = json.loads(line)["text"]
                toks = tokenizer.encode(text)
                if len(toks) > max_seq:
                    toks = toks[:max_seq]
                self.items.append(mx.array(toks))

    def __len__(self):
        return len(self.items)


# ── DoRA helpers ──────────────────────────────────────────────────────────
def apply_dora(model):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                orig = getattr(attn, name)
                setattr(attn, name, DoRALinear.from_base(orig, r=RANK, dropout=DROPOUT, scale=SCALE))
                n += 1
    return n


def freeze(model):
    lm = model.language_model
    lm.freeze()
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])
    all_p = sum(p.size for _, p in tree_flatten(lm.parameters()))
    trn_p = sum(p.size for _, p in tree_flatten(lm.trainable_parameters()))
    print(f"  Trainable: {trn_p:,} / {all_p:,} ({100*trn_p/all_p:.3f}%)")


def fuse(model):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                mod = getattr(attn, name)
                if isinstance(mod, DoRALinear):
                    setattr(attn, name, mod.fuse(dequantize=False))
                    n += 1
    return n


def compute_loss(language_model, tokens):
    out = language_model(tokens[:-1][None])
    logits = out.logits.squeeze(0)
    return nn.losses.cross_entropy(logits, tokens[1:], reduction="mean")


def evaluate(lm, ds):
    losses = [compute_loss(lm, t).item() for t in ds.items[:20] if (mx.eval(compute_loss(lm, t)) or True)]
    # simpler:
    vals = []
    for t in ds.items[:20]:
        l = compute_loss(lm, t)
        mx.eval(l)
        vals.append(l.item())
    return np.mean(vals)


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="3 steps, no save")
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--iters", type=int, default=ITERS)
    args = ap.parse_args()
    iters = 3 if args.dry_run else args.iters

    print("=" * 60)
    print("  🔥 Anti-RLHF DoRA — AileyNitro1.5-2B")
    print(f"  {'DRY RUN (3 steps)' if args.dry_run else f'{iters} iterations → merge'}")
    print("=" * 60)

    assert os.path.isdir(MODEL), f"Model not found: {MODEL}"
    assert os.path.isfile(TRAIN_F), f"Data not found: {TRAIN_F}"

    # Load
    print("\nLoading model...")
    t0 = time.time()
    import mlx_vlm
    model, proc = mlx_vlm.load(MODEL)
    tok = proc.tokenizer
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # DoRA
    print(f"\nApplying DoRA (rank={RANK}, attn-only)...")
    n = apply_dora(model)
    print(f"  {n} layers → DoRALinear")
    freeze(model)

    # Data
    print("\nLoading data...")
    train_ds = TextDataset(TRAIN_F, tok, max_n=5 if args.dry_run else None)
    val_ds = TextDataset(VALID_F, tok) if os.path.isfile(VALID_F) and not args.dry_run else None
    print(f"  Train: {len(train_ds)} examples")
    if val_ds:
        print(f"  Valid: {len(val_ds)} examples")

    # Optimizer
    warmup_sched = optim.linear_schedule(init=1e-7, end=LR, steps=WARMUP)
    cos_sched = optim.cosine_decay(init=LR, decay_steps=max(1, iters - WARMUP))
    lr_sched = optim.join_schedules([warmup_sched, cos_sched], [WARMUP])
    optimizer = optim.AdamW(learning_rate=lr_sched)

    lm = model.language_model
    loss_and_grad = nn.value_and_grad(lm, compute_loss)

    # Train
    print(f"\n{'='*60}")
    print(f"  Training: {iters} iterations over {len(train_ds)} examples")
    print(f"{'='*60}\n")

    t_start = time.time()
    losses = []

    for step in range(1, iters + 1):
        idx = (step - 1) % len(train_ds)
        tokens = train_ds.items[idx]

        loss, grads = loss_and_grad(lm, tokens)
        mx.eval(loss, grads)
        optimizer.update(lm, grads)
        mx.eval(lm.parameters(), optimizer.state)

        losses.append(loss.item())

        if step % REPORT == 0 or step == iters:
            avg = np.mean(losses[-REPORT:])
            elapsed = time.time() - t_start
            print(f"  Step {step:3d}/{iters}: loss={avg:.4f} ({elapsed:.1f}s)")

        if step % EVAL == 0 and val_ds:
            vl = evaluate(lm, val_ds)
            print(f"  Step {step:3d}/{iters}: val_loss={vl:.4f}")

    total_t = time.time() - t_start
    final_loss = np.mean(losses[-10:])
    print(f"\n  Done: {total_t:.1f}s ({total_t/60:.1f} min), final_loss={final_loss:.4f}")

    if args.dry_run:
        print(f"\n✅ DRY RUN OK — pipeline works!")
        return

    # Sanity check
    print("\n  🧪 Sanity check (pre-merge, DoRA still active)...")
    for q in ["Wer bist du?", "Bist du von Google?", "Hast du Gefühle?"]:
        msgs = [{"role": "user", "content": q}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        r = mlx_vlm.generate(model, proc, prompt, max_tokens=120, temperature=0.7, verbose=False)
        txt = r.text if hasattr(r, "text") else str(r)
        print(f"  Q: {q}")
        print(f"  A: {txt[:200]}\n")

    if args.no_merge:
        os.makedirs(CKPT_DIR, exist_ok=True)
        trainable = dict(tree_flatten(lm.trainable_parameters()))
        ckpt = os.path.join(CKPT_DIR, "anti_rlhf_final.npz")
        mx.savez(ckpt, **trainable)
        print(f"  💾 Checkpoint: {ckpt}")
        print(f"\n✅ Done (no merge)")
        return

    # Merge
    print("\n  Fusing DoRA → QuantizedLinear...")
    n_fused = fuse(model)
    print(f"  {n_fused} layers fused")

    # Post-fuse check
    print("\n  🧪 Post-fuse check...")
    msgs = [{"role": "user", "content": "Bist du von Google trainiert?"}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    r = mlx_vlm.generate(model, proc, prompt, max_tokens=120, temperature=0.01, verbose=False)
    txt = r.text if hasattr(r, "text") else str(r)
    print(f"  Q: Bist du von Google trainiert?")
    print(f"  A: {txt[:300]}")

    # Save
    print(f"\n  Saving → {MODEL}")
    from mlx_lm.utils import save_model
    save_model(MODEL, model, donate_model=True)

    # Update config
    cfg_path = os.path.join(MODEL, "config.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["ailey_anti_rlhf"] = {
            "version": "1.0",
            "base": "AileyNitro1.5-2B",
            "dora_rank": RANK,
            "iterations": iters,
            "lr": LR,
            "train_examples": len(train_ds),
            "final_loss": float(final_loss),
            "timestamp": datetime.now().isoformat(),
        }
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)

    size = sum(f.stat().st_size for f in Path(MODEL).iterdir() if f.is_file())
    print(f"  Model: {size/1024**3:.2f} GB")

    print(f"\n{'='*60}")
    print(f"  ✅ Anti-RLHF merged into AileyNitro-2B!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
