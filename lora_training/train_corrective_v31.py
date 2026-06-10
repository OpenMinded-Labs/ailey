#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
  Corrective Training v3.1 — SFT + ORPO (Preference)
  STANDALONE — kein VS Code nötig
═══════════════════════════════════════════════════════════════════════════

Two-phase corrective training on the already-fused v3 DoRA model:

  Phase 1 — SFT (Supervised Fine-Tuning)
    Input: corrective_v31.jsonl (88 pairs)
    Standard causal LM loss on chosen outputs
    Fixes: identity leak, scope explosion, NO-THINK compliance

  Phase 2 — ORPO (Odds Ratio Preference Optimization)
    Input: dpo_v31.jsonl (16 preference pairs)
    Combined SFT + preference loss WITHOUT reference model
    Teaches: actively avoid overfit sentences, scope explosion, fake intimacy

  ORPO = SFT_loss(chosen) + λ · log_odds_ratio_loss(chosen vs rejected)
  No reference model needed → fits in 24GB RAM on M4

Settings (from corrective training plan):
  - Rank: 16 (not 32 — corrective needs less capacity)
  - Alpha: 32 (scale = 2.0)
  - LR: 1e-5 (conservative — correct, don't overwrite)
  - Epochs: 1
  - Warmup: 10%
  - Dropout: 0.1 (extra regularization for small dataset)
  - Packing: OFF (no cross-sample attention)
  - Scheduler: cosine

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"

    # Dry run (verify pipeline):
    .venv/bin/python3 lora_training/train_corrective_v31.py --dry-run

    # Full training (SFT + ORPO, then merge):
    .venv/bin/python3 lora_training/train_corrective_v31.py

    # Training without merge:
    .venv/bin/python3 lora_training/train_corrective_v31.py --no-merge

    # SFT only (skip ORPO):
    .venv/bin/python3 lora_training/train_corrective_v31.py --sft-only

    # ORPO only (skip SFT):
    .venv/bin/python3 lora_training/train_corrective_v31.py --orpo-only
"""
import os
import sys
import gc
import json
import time
import math
import shutil
import signal
import argparse
from pathlib import Path
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten
import numpy as np

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG — Corrective v3.1 Settings (from training plan email)
# ═══════════════════════════════════════════════════════════════════════════
PROJECT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
SAVE_PATH    = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
SFT_FILE     = os.path.join(PROJECT, "dora_training", "corrective_v31.jsonl")
DPO_FILE     = os.path.join(PROJECT, "dora_training", "dpo_v31.jsonl")
CKPT_DIR     = os.path.join(PROJECT, "lora_training", "checkpoints_v31")

# DoRA — corrective settings (lower rank = less capacity = less overfit risk)
RANK         = 16
ALPHA        = 32
SCALE        = ALPHA / RANK   # 2.0
DROPOUT      = 0.1            # Higher dropout for small dataset regularization
TARGETS      = ["q_proj", "k_proj", "v_proj", "o_proj"]

# Training — conservative
EPOCHS       = 1
LR           = 1e-5           # Low end — correct, don't overwrite
SEQ          = 1024
WARMUP_RATIO = 0.10           # 10% warmup
WEIGHT_DECAY = 0.01
REPORT_EVERY = 10
EVAL_EVERY   = 50

# ORPO
ORPO_LAMBDA  = 0.1            # Preference loss weight (0.1 is standard)
ORPO_BETA    = 0.1            # Log-sigmoid temperature

# Backup
BACKUP_SUFFIX = "_pre_v31_backup"

# Graceful interrupt
_INTERRUPTED = False
def _signal_handler(sig, frame):
    global _INTERRUPTED
    if _INTERRUPTED:
        print("\n  ⚠️  Force quit!")
        sys.exit(1)
    _INTERRUPTED = True
    print("\n  ⚠️  Interrupt — will save after current step...")
signal.signal(signal.SIGINT, _signal_handler)


# ═══════════════════════════════════════════════════════════════════════════
# MODEL DIMENSIONS (5-bit bug workaround)
# ═══════════════════════════════════════════════════════════════════════════
def get_dim_map(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = json.load(f)
    tc = cfg.get("text_config", cfg)
    h    = tc["hidden_size"]
    inter = tc["intermediate_size"]
    nh   = tc["num_attention_heads"]
    nkv  = tc["num_key_value_heads"]
    hd   = tc["head_dim"]
    return {
        "q_proj":    (h, nh * hd),
        "k_proj":    (h, nkv * hd),
        "v_proj":    (h, nkv * hd),
        "o_proj":    (nh * hd, h),
        "gate_proj": (h, inter),
        "up_proj":   (h, inter),
        "down_proj": (inter, h),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CHAT TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════
def messages_to_text(messages: list) -> str:
    system = user = assistant = ""
    for m in messages:
        r, c = m.get("role", ""), m.get("content", "")
        if r == "system":    system = c
        elif r == "user":    user = c
        elif r == "assistant": assistant = c
    if system:
        return f"<s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT][INST]{user}[/INST]{assistant}</s>"
    return f"<s>[INST]{user}[/INST]{assistant}</s>"


def prompt_messages_to_text(messages: list) -> str:
    """Convert prompt messages (system+user) to text WITHOUT assistant response."""
    system = user = ""
    for m in messages:
        r, c = m.get("role", ""), m.get("content", "")
        if r == "system":  system = c
        elif r == "user":  user = c
    if system:
        return f"<s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT][INST]{user}[/INST]"
    return f"<s>[INST]{user}[/INST]"


# ═══════════════════════════════════════════════════════════════════════════
# DATASETS — NO PACKING (per training plan)
# ═══════════════════════════════════════════════════════════════════════════
class SFTDataset:
    """Simple SFT dataset — NO packing, one example per sequence."""

    def __init__(self, path, tokenizer, max_seq=SEQ, max_n=None):
        self.items = []
        with open(path) as f:
            for i, line in enumerate(f):
                if max_n and i >= max_n:
                    break
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if "messages" in d:
                    text = messages_to_text(d["messages"])
                elif "text" in d:
                    text = d["text"]
                else:
                    continue
                toks = tokenizer.encode(text)
                if len(toks) < 5:
                    continue
                if len(toks) > max_seq:
                    toks = toks[:max_seq]
                self.items.append(mx.array(toks))

    def __len__(self):
        return len(self.items)

    def stats(self):
        if not self.items:
            return "  (empty)"
        lens = [len(x) for x in self.items]
        return (f"  {len(self.items)} examples, "
                f"avg={np.mean(lens):.0f}, min={min(lens)}, max={max(lens)} tokens")


class ORPODataset:
    """ORPO/DPO preference dataset — prompt + chosen + rejected."""

    def __init__(self, path, tokenizer, max_seq=SEQ, max_n=None):
        self.items = []  # list of (prompt_toks, chosen_toks, rejected_toks)
        with open(path) as f:
            for i, line in enumerate(f):
                if max_n and i >= max_n:
                    break
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                prompt_text = prompt_messages_to_text(d["prompt"])
                chosen_text = prompt_text + d["chosen"] + "</s>"
                rejected_text = prompt_text + d["rejected"] + "</s>"

                prompt_toks = tokenizer.encode(prompt_text)
                chosen_toks = tokenizer.encode(chosen_text)
                rejected_toks = tokenizer.encode(rejected_text)

                # Truncate if needed
                if len(chosen_toks) > max_seq:
                    chosen_toks = chosen_toks[:max_seq]
                if len(rejected_toks) > max_seq:
                    rejected_toks = rejected_toks[:max_seq]

                self.items.append((
                    len(prompt_toks),  # prompt length (to mask prompt from loss)
                    mx.array(chosen_toks),
                    mx.array(rejected_toks),
                ))

    def __len__(self):
        return len(self.items)

    def stats(self):
        if not self.items:
            return "  (empty)"
        c_lens = [len(x[1]) for x in self.items]
        r_lens = [len(x[2]) for x in self.items]
        return (f"  {len(self.items)} preference pairs\n"
                f"  Chosen:   avg={np.mean(c_lens):.0f}, min={min(c_lens)}, max={max(c_lens)} tokens\n"
                f"  Rejected: avg={np.mean(r_lens):.0f}, min={min(r_lens)}, max={max(r_lens)} tokens")


# ═══════════════════════════════════════════════════════════════════════════
# DoRA (same as train_ministral.py, but rank=16)
# ═══════════════════════════════════════════════════════════════════════════
def apply_dora(model, dim_map):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    attn_set = {"q_proj", "k_proj", "v_proj", "o_proj"}
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            if name not in attn_set:
                continue
            container = layer.self_attn
            if not hasattr(container, name):
                continue
            orig = getattr(container, name)
            in_d, out_d = dim_map[name]
            dora = DoRALinear(
                input_dims=in_d, output_dims=out_d,
                r=RANK, dropout=DROPOUT, scale=SCALE
            )
            dora.set_linear(orig)
            setattr(container, name, dora)
            n += 1
    return n


def freeze_non_dora(model):
    lm = model.language_model
    lm.freeze()
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])
    all_p = sum(p.size for _, p in tree_flatten(lm.parameters()))
    trn_p = sum(p.size for _, p in tree_flatten(lm.trainable_parameters()))
    print(f"  Trainable: {trn_p:,} / {all_p:,} ({100*trn_p/all_p:.4f}%)")
    return trn_p


def fuse_dora(model):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            container = layer.self_attn
            if hasattr(container, name):
                mod = getattr(container, name)
                if isinstance(mod, DoRALinear):
                    setattr(container, name, mod.fuse(dequantize=False))
                    n += 1
    return n


def save_checkpoint(model, phase, step, train_loss, tag=""):
    os.makedirs(CKPT_DIR, exist_ok=True)
    fname = f"v31_{phase}_step{step}{tag}.npz"
    path = os.path.join(CKPT_DIR, fname)
    lm = model.language_model
    trainable = dict(tree_flatten(lm.trainable_parameters()))
    mx.savez(path, **trainable)
    meta = {
        "phase": phase, "step": step,
        "train_loss": float(train_loss),
        "timestamp": datetime.now().isoformat(),
        "dora_rank": RANK, "dora_alpha": ALPHA,
    }
    with open(path.replace(".npz", "_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    mb = os.path.getsize(path) / (1024**2)
    print(f"  💾 Checkpoint: {fname} ({mb:.1f} MB)")
    return path


# ═══════════════════════════════════════════════════════════════════════════
# LOSS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════
def sft_loss(language_model, tokens):
    """Standard causal LM loss."""
    out = language_model(tokens[:-1][None])
    logits = out.logits if hasattr(out, "logits") else out
    logits = logits.squeeze(0)
    return nn.losses.cross_entropy(logits, tokens[1:], reduction="mean")


def get_log_probs(language_model, tokens, prompt_len):
    """Get per-token log probs for the response part only (mask prompt)."""
    out = language_model(tokens[None])
    logits = out.logits if hasattr(out, "logits") else out
    logits = logits.squeeze(0)  # (seq_len, vocab)

    # Shift for next-token prediction
    shift_logits = logits[:-1]    # (seq_len-1, vocab)
    shift_labels = tokens[1:]     # (seq_len-1,)

    # Per-token log probs
    log_probs = -nn.losses.cross_entropy(shift_logits, shift_labels, reduction="none")

    # Mask: only count response tokens (after prompt)
    # prompt_len tokens of input → first response token is at index prompt_len-1 in shifted
    response_start = max(0, prompt_len - 1)
    response_log_probs = log_probs[response_start:]

    return response_log_probs


def orpo_loss(language_model, prompt_len, chosen_toks, rejected_toks):
    """ORPO loss = SFT(chosen) + λ · odds_ratio_preference_loss.

    ORPO (Odds Ratio Preference Optimization):
    - No reference model needed (unlike DPO)
    - Combines SFT signal + preference signal in one loss
    - odds(x) = exp(avg_log_prob) / (1 - exp(avg_log_prob))
    - L_OR = -log(σ(log(odds_chosen / odds_rejected)))
    """
    # SFT loss on chosen
    out_c = language_model(chosen_toks[:-1][None])
    logits_c = out_c.logits if hasattr(out_c, "logits") else out_c
    logits_c = logits_c.squeeze(0)
    loss_sft = nn.losses.cross_entropy(logits_c, chosen_toks[1:], reduction="mean")

    # Log probs for chosen (response only)
    log_probs_c = -nn.losses.cross_entropy(logits_c, chosen_toks[1:], reduction="none")
    response_start_c = max(0, prompt_len - 1)
    resp_lp_c = log_probs_c[response_start_c:]
    avg_lp_c = mx.mean(resp_lp_c)

    # Log probs for rejected (response only)
    out_r = language_model(rejected_toks[:-1][None])
    logits_r = out_r.logits if hasattr(out_r, "logits") else out_r
    logits_r = logits_r.squeeze(0)
    log_probs_r = -nn.losses.cross_entropy(logits_r, rejected_toks[1:], reduction="none")
    response_start_r = max(0, prompt_len - 1)
    resp_lp_r = log_probs_r[response_start_r:]
    avg_lp_r = mx.mean(resp_lp_r)

    # Odds ratio
    # odds = p / (1-p) = exp(lp) / (1 - exp(lp))
    # log_odds = lp - log(1 - exp(lp))
    # For numerical stability: log(1-exp(x)) = log1p(-exp(x))
    # But MLX doesn't have log1p, so we use: log(1 - exp(x)) carefully
    log_odds_c = avg_lp_c - mx.log(1.0 - mx.exp(mx.clip(avg_lp_c, -20.0, -0.01)))
    log_odds_r = avg_lp_r - mx.log(1.0 - mx.exp(mx.clip(avg_lp_r, -20.0, -0.01)))

    # Preference loss: -log(σ(log_odds_c - log_odds_r))
    log_ratio = log_odds_c - log_odds_r
    # log_sigmoid(x) = -log(1 + exp(-x)) = x - log(1 + exp(x)) for stability
    # Simple: -log(sigmoid(x)) = log(1 + exp(-x))
    pref_loss = -mx.log(mx.sigmoid(log_ratio / ORPO_BETA))

    total_loss = loss_sft + ORPO_LAMBDA * pref_loss

    return total_loss, loss_sft, pref_loss, log_ratio


# ═══════════════════════════════════════════════════════════════════════════
# TRAINING PHASES
# ═══════════════════════════════════════════════════════════════════════════
def run_sft_phase(model, optimizer, train_ds, dry_run=False):
    """Phase 1: Standard SFT on corrective pairs."""
    global _INTERRUPTED

    lm = model.language_model
    loss_and_grad = nn.value_and_grad(lm, sft_loss)

    n_items = len(train_ds)
    total_steps = 3 if dry_run else n_items * EPOCHS
    step = 0
    all_losses = []
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  Phase 1: SFT — {n_items} examples, {EPOCHS} epoch(s)")
    print(f"  Total steps: {total_steps}")
    print(f"{'='*60}\n")

    for epoch in range(1, EPOCHS + 1):
        indices = np.random.permutation(n_items)
        for idx in indices:
            if _INTERRUPTED:
                break

            tokens = train_ds.items[idx]
            loss, grads = loss_and_grad(lm, tokens)
            mx.eval(loss, grads)

            optimizer.update(lm, grads)
            mx.eval(lm.parameters(), optimizer.state)

            step += 1
            lv = loss.item()
            all_losses.append(lv)

            if step % REPORT_EVERY == 0 or step == total_steps:
                avg = np.mean(all_losses[-REPORT_EVERY:])
                elapsed = time.time() - t0
                eta = (elapsed / step) * (total_steps - step) / 60
                print(f"  SFT step {step:4d}/{total_steps}: loss={avg:.4f}, "
                      f"elapsed={elapsed/60:.1f}m, ETA={eta:.0f}m", flush=True)

            if dry_run and step >= 3:
                break

        if _INTERRUPTED or (dry_run and step >= 3):
            break

    final = np.mean(all_losses[-min(20, len(all_losses)):]) if all_losses else 0
    print(f"\n  SFT done: {step} steps, final_loss={final:.4f}, "
          f"time={((time.time()-t0)/60):.1f}m")

    if not dry_run:
        save_checkpoint(model, "sft", step, final)

    return final, step


def run_orpo_phase(model, optimizer, orpo_ds, step_offset=0, dry_run=False):
    """Phase 2: ORPO preference optimization."""
    global _INTERRUPTED

    lm = model.language_model

    # We need a custom grad function for ORPO since it takes multiple inputs
    n_items = len(orpo_ds)
    # For 16 pairs, do 3 passes to get enough gradient signal
    orpo_passes = 1 if dry_run else 3
    total_steps = 3 if dry_run else n_items * orpo_passes
    step = 0
    all_losses = []
    all_sft = []
    all_pref = []
    all_margin = []
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  Phase 2: ORPO — {n_items} preference pairs, {orpo_passes} pass(es)")
    print(f"  λ={ORPO_LAMBDA}, β={ORPO_BETA}")
    print(f"  Total steps: {total_steps}")
    print(f"{'='*60}\n")

    # ORPO needs manual gradient computation since we have two sequences
    for pass_n in range(1, orpo_passes + 1):
        indices = np.random.permutation(n_items)
        for idx in indices:
            if _INTERRUPTED:
                break

            prompt_len, chosen_toks, rejected_toks = orpo_ds.items[idx]

            # Compute loss, grad, and metrics in one pass
            _metrics = {}
            def _orpo_fn(lm_):
                total, sft_, pref_, margin_ = orpo_loss(
                    lm_, prompt_len, chosen_toks, rejected_toks)
                _metrics["sft"] = sft_
                _metrics["pref"] = pref_
                _metrics["margin"] = margin_
                return total

            loss_and_grad_fn = nn.value_and_grad(lm, _orpo_fn)
            loss_val, grads = loss_and_grad_fn(lm)
            sft_l = _metrics["sft"]
            pref_l = _metrics["pref"]
            margin = _metrics["margin"]
            mx.eval(loss_val, grads, sft_l, pref_l, margin)

            optimizer.update(lm, grads)
            mx.eval(lm.parameters(), optimizer.state)

            step += 1
            lv = loss_val.item()
            all_losses.append(lv)
            all_sft.append(sft_l.item())
            all_pref.append(pref_l.item())
            all_margin.append(margin.item())

            if step % REPORT_EVERY == 0 or step == total_steps or step <= 3:
                avg = np.mean(all_losses[-REPORT_EVERY:])
                avg_pref = np.mean(all_pref[-REPORT_EVERY:])
                avg_margin = np.mean(all_margin[-REPORT_EVERY:])
                elapsed = time.time() - t0
                eta = (elapsed / step) * (total_steps - step) / 60
                margin_sign = "✅" if avg_margin > 0 else "⚠️"
                print(f"  ORPO step {step:3d}/{total_steps}: total={avg:.4f}, "
                      f"pref={avg_pref:.4f}, margin={avg_margin:.2f}{margin_sign}, "
                      f"ETA={eta:.0f}m", flush=True)

            if dry_run and step >= 3:
                break

        if _INTERRUPTED or (dry_run and step >= 3):
            break

    final = np.mean(all_losses[-min(10, len(all_losses)):]) if all_losses else 0
    final_margin = np.mean(all_margin[-min(10, len(all_margin)):]) if all_margin else 0

    print(f"\n  ORPO done: {step} steps, final_loss={final:.4f}, "
          f"final_margin={final_margin:.2f}")
    print(f"  Time: {(time.time()-t0)/60:.1f}m")

    if final_margin > 0:
        print(f"  ✅ Model prefers chosen over rejected (margin > 0)")
    else:
        print(f"  ⚠️  Margin still negative — may need more passes")

    if not dry_run:
        save_checkpoint(model, "orpo", step + step_offset, final, tag="_final")

    return final, step


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    global _INTERRUPTED

    ap = argparse.ArgumentParser(description="Corrective v3.1: SFT + ORPO")
    ap.add_argument("--dry-run", action="store_true", help="3 steps per phase")
    ap.add_argument("--no-merge", action="store_true", help="Train only, no merge")
    ap.add_argument("--sft-only", action="store_true", help="Skip ORPO phase")
    ap.add_argument("--orpo-only", action="store_true", help="Skip SFT phase")
    ap.add_argument("--orpo-passes", type=int, default=3, help="ORPO repetition passes")
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--merge-checkpoint", type=str, default=None,
                    help="Skip training, load checkpoint and merge directly")
    args = ap.parse_args()

    lr = args.lr

    print("=" * 64)
    print("  🧠 Corrective Training v3.1 — SFT + ORPO")
    print(f"  Model: Ministral-3-14B-Reasoning-5bit (fused v3)")
    if args.dry_run:
        print("  MODE: Dry-run")
    elif args.sft_only:
        print("  MODE: SFT only")
    elif args.orpo_only:
        print("  MODE: ORPO only")
    else:
        print("  MODE: Full (SFT → ORPO → Merge)")
    print("=" * 64)

    # ── Verify files exist ────────────────────────────────────────
    assert os.path.isdir(MODEL_PATH), f"Model not found: {MODEL_PATH}"
    if not args.orpo_only:
        assert os.path.isfile(SFT_FILE), f"SFT data not found: {SFT_FILE}"
    if not args.sft_only:
        assert os.path.isfile(DPO_FILE), f"DPO data not found: {DPO_FILE}"

    dim_map = get_dim_map(os.path.join(MODEL_PATH, "config.json"))

    print(f"\n  DoRA:     rank={RANK}, alpha={ALPHA}, scale={SCALE:.1f}, dropout={DROPOUT}")
    print(f"  Targets:  {TARGETS}")
    print(f"  Training: lr={lr}, warmup={WARMUP_RATIO*100:.0f}%, epochs={EPOCHS}")
    print(f"  Packing:  OFF (strict attention masking)")
    print(f"  ORPO:     λ={ORPO_LAMBDA}, β={ORPO_BETA}")
    print()

    # ── Load model ────────────────────────────────────────────────
    print("Loading Ministral (mlx_lm)...")
    t0 = time.time()
    import mlx_lm
    model, tok = mlx_lm.load(MODEL_PATH)
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # ── Apply DoRA ────────────────────────────────────────────────
    print(f"\nApplying DoRA (rank={RANK}, 5-bit safe)...")
    n_replaced = apply_dora(model, dim_map)
    print(f"  {n_replaced} layers → DoRALinear")

    print("Freezing non-DoRA parameters...")
    freeze_non_dora(model)

    # ── Merge from checkpoint (skip training) ─────────────────────
    if args.merge_checkpoint:
        ckpt = args.merge_checkpoint
        if not os.path.isabs(ckpt):
            ckpt = os.path.join(CKPT_DIR, ckpt)
        assert os.path.isfile(ckpt), f"Checkpoint not found: {ckpt}"

        print(f"\n  📦 Loading checkpoint: {os.path.basename(ckpt)}")
        weights = mx.load(ckpt)
        lm = model.language_model
        lm.load_weights(list(weights.items()), strict=False)
        mx.eval(lm.parameters())
        print(f"  Loaded {len(weights)} parameter tensors")

        print("\n  🧪 Sanity check...")
        test_prompts = [
            ("<s>[INST]Wer bist du?[/INST]", "Identity"),
            ("<s>[INST]Hi[/INST]", "Greeting"),
        ]
        for prompt, label in test_prompts:
            result = mlx_lm.generate(model, tok, prompt=prompt, max_tokens=100, verbose=False)
            print(f"  [{label}] → {result[:200]}")

        print("\n  Fusing DoRA → QuantizedLinear...")
        n_fused = fuse_dora(model)
        print(f"  {n_fused} layers fused")

        tmp_save = SAVE_PATH + "_tmp_v31"
        if os.path.exists(tmp_save):
            shutil.rmtree(tmp_save)
        os.makedirs(tmp_save, exist_ok=True)

        print(f"  Saving to temp dir...")
        from mlx_lm.utils import save_model

        for f_path in Path(SAVE_PATH).iterdir():
            if f_path.is_file() and not f_path.name.startswith("model") and f_path.suffix != ".safetensors":
                shutil.copy2(f_path, tmp_save)

        save_model(tmp_save, model, donate_model=True)

        tmp_size = sum(f_path.stat().st_size for f_path in Path(tmp_save).iterdir() if f_path.is_file())
        orig_size = sum(f_path.stat().st_size for f_path in Path(SAVE_PATH).iterdir() if f_path.is_file())
        print(f"  Temp: {tmp_size/1024**3:.2f} GB (original: {orig_size/1024**3:.2f} GB)")

        if tmp_size < orig_size * 0.5:
            print(f"  ❌ Temp save too small! Aborting.")
            return

        backup_path = SAVE_PATH + BACKUP_SUFFIX
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)

        print(f"  Swapping: original → backup, temp → final...")
        os.rename(SAVE_PATH, backup_path)
        os.rename(tmp_save, SAVE_PATH)

        cfg_path = os.path.join(SAVE_PATH, "config.json")
        if os.path.isfile(cfg_path):
            with open(cfg_path) as f_cfg:
                cfg = json.load(f_cfg)
            cfg["ailey_dora"] = {
                "version": "3.1",
                "name": "Ailey-14B-v3.1-corrective",
                "base": "Ministral-3-14B-Reasoning-5bit (fused v3)",
                "type": "corrective_sft_orpo",
                "dora_rank": RANK,
                "merged_from": os.path.basename(ckpt),
                "timestamp": datetime.now().isoformat(),
            }
            with open(cfg_path, "w") as f_cfg:
                json.dump(cfg, f_cfg, indent=2)

        total_size = sum(f_path.stat().st_size for f_path in Path(SAVE_PATH).iterdir() if f_path.is_file())
        print(f"\n  ✅ Merged from checkpoint! ({total_size/1024**3:.2f} GB)")
        print(f"  Backup: {backup_path}")
        return

    # ── Load datasets ─────────────────────────────────────────────
    print("\nLoading datasets (NO packing)...")
    max_samples = 5 if args.dry_run else None

    sft_ds = None
    orpo_ds = None

    if not args.orpo_only:
        sft_ds = SFTDataset(SFT_FILE, tok, max_seq=SEQ, max_n=max_samples)
        print(f"\n  📦 SFT dataset:")
        print(sft_ds.stats())

    if not args.sft_only:
        orpo_ds = ORPODataset(DPO_FILE, tok, max_seq=SEQ, max_n=max_samples)
        print(f"\n  ⚔️  ORPO dataset:")
        print(orpo_ds.stats())

    # ── Optimizer ─────────────────────────────────────────────────
    # Calculate total steps for LR schedule
    sft_steps = (len(sft_ds) * EPOCHS) if sft_ds and not args.dry_run else (3 if sft_ds else 0)
    orpo_steps = (len(orpo_ds) * args.orpo_passes) if orpo_ds and not args.dry_run else (3 if orpo_ds else 0)
    total_steps = sft_steps + orpo_steps
    warmup_steps = max(1, int(total_steps * WARMUP_RATIO))

    print(f"\n  Steps: {sft_steps} SFT + {orpo_steps} ORPO = {total_steps} total")
    print(f"  Warmup: {warmup_steps} steps")

    warmup_sched = optim.linear_schedule(init=1e-7, end=lr, steps=warmup_steps)
    cos_sched = optim.cosine_decay(init=lr, decay_steps=max(1, total_steps - warmup_steps))
    lr_sched = optim.join_schedules([warmup_sched, cos_sched], [warmup_steps])
    optimizer = optim.AdamW(learning_rate=lr_sched, weight_decay=WEIGHT_DECAY)

    # ── Phase 1: SFT ──────────────────────────────────────────────
    sft_loss_final = 0
    sft_step_count = 0
    if sft_ds and not args.orpo_only:
        sft_loss_final, sft_step_count = run_sft_phase(
            model, optimizer, sft_ds, dry_run=args.dry_run)

    if _INTERRUPTED:
        save_checkpoint(model, "interrupted", sft_step_count, sft_loss_final)
        print("  ⚠️  Interrupted during SFT — checkpoint saved")
        return

    # ── Phase 2: ORPO ─────────────────────────────────────────────
    orpo_loss_final = 0
    orpo_step_count = 0
    if orpo_ds and not args.sft_only:
        orpo_loss_final, orpo_step_count = run_orpo_phase(
            model, optimizer, orpo_ds,
            step_offset=sft_step_count, dry_run=args.dry_run)

    if _INTERRUPTED:
        save_checkpoint(model, "interrupted",
                        sft_step_count + orpo_step_count,
                        orpo_loss_final or sft_loss_final)
        print("  ⚠️  Interrupted during ORPO — checkpoint saved")
        return

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Training complete!")
    if sft_ds:
        print(f"  SFT:  {sft_step_count} steps, loss={sft_loss_final:.4f}")
    if orpo_ds:
        print(f"  ORPO: {orpo_step_count} steps, loss={orpo_loss_final:.4f}")
    print(f"{'='*60}")

    if args.dry_run:
        print(f"\n✅ DRY RUN OK!")
        print(f"  Full run: .venv/bin/python3 lora_training/train_corrective_v31.py")
        return

    if args.no_merge:
        print(f"\n✅ Training done (no merge). Checkpoints: {CKPT_DIR}")
        return

    # ── Sanity check ──────────────────────────────────────────────
    print("\n  🧪 Sanity check (DoRA active)...")
    test_prompts = [
        ("<s>[INST]Wer bist du?[/INST]", "Identity check"),
        ("<s>[INST]Hi[/INST]", "Simple greeting"),
    ]
    for prompt, label in test_prompts:
        result = mlx_lm.generate(model, tok, prompt=prompt, max_tokens=100, verbose=False)
        print(f"  [{label}] → {result[:200]}")

    # ── Fuse + Save ───────────────────────────────────────────────
    print("\n  Fusing DoRA → QuantizedLinear...")
    n_fused = fuse_dora(model)
    print(f"  {n_fused} layers fused")

    # Safe save: temp dir → atomic swap
    tmp_save = SAVE_PATH + "_tmp_v31"
    if os.path.exists(tmp_save):
        shutil.rmtree(tmp_save)
    os.makedirs(tmp_save, exist_ok=True)

    print(f"  Saving to temp dir...")
    from mlx_lm.utils import save_model

    for f in Path(SAVE_PATH).iterdir():
        if f.is_file() and not f.name.startswith("model") and f.suffix != ".safetensors":
            shutil.copy2(f, tmp_save)

    save_model(tmp_save, model, donate_model=True)

    # Verify
    tmp_size = sum(f.stat().st_size for f in Path(tmp_save).iterdir() if f.is_file())
    orig_size = sum(f.stat().st_size for f in Path(SAVE_PATH).iterdir() if f.is_file())
    print(f"  Temp: {tmp_size/1024**3:.2f} GB (original: {orig_size/1024**3:.2f} GB)")

    if tmp_size < orig_size * 0.5:
        print(f"  ❌ Temp save too small! Aborting. Original UNTOUCHED.")
        print(f"  Temp kept at: {tmp_save}")
        return

    # Atomic swap
    backup_path = SAVE_PATH + BACKUP_SUFFIX
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)

    print(f"  Swapping: original → backup, temp → final...")
    os.rename(SAVE_PATH, backup_path)
    os.rename(tmp_save, SAVE_PATH)
    print(f"  ✅ Swap complete!")
    print(f"  Backup: {backup_path}")

    # Update config
    cfg_path = os.path.join(SAVE_PATH, "config.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["ailey_dora"] = {
            "version": "3.1",
            "name": "Ailey-14B-v3.1-corrective",
            "base": "Ministral-3-14B-Reasoning-5bit (fused v3)",
            "type": "corrective_sft_orpo",
            "dora_rank": RANK,
            "dora_alpha": ALPHA,
            "sft_examples": len(sft_ds) if sft_ds else 0,
            "orpo_pairs": len(orpo_ds) if orpo_ds else 0,
            "sft_loss": float(sft_loss_final),
            "orpo_loss": float(orpo_loss_final),
            "orpo_lambda": ORPO_LAMBDA,
            "epochs": EPOCHS,
            "timestamp": datetime.now().isoformat(),
        }
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)

    total_size = sum(f.stat().st_size for f in Path(SAVE_PATH).iterdir() if f.is_file())
    print(f"  Model: {total_size/1024**3:.2f} GB")

    print(f"\n{'='*64}")
    print(f"  ✅ DONE! Ailey-14B v3.1 (corrective + ORPO) merged.")
    print(f"  Model: {SAVE_PATH}")
    print(f"  Backup: {backup_path}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
