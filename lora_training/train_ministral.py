#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
  DoRA Training v3 — Ailey auf bereits trainiertem CodeAiley-14B
  STANDALONE — kein VS Code nötig, kein Import von anderen Scripts
═══════════════════════════════════════════════════════════════════════════

v3-Training: Feintuning über das bereits DoRA-trainierte Modell.
  - Source: Ministral-3-14B-Reasoning-5bit (bereits trainiertes Modell)
  - Dataset: clean_train_v3.jsonl (1639 Pairs mit CTX-Headers + Songs)
  - Rank: 32 (höher als v1/v2 für mehr Kapazität)
  - LR: 2e-5 (konservativ — wir trainieren über vorhandenem Training)
  - Epochs: 2

SEQUENCE PACKING + ATTENTION MAPPING:
  Kurze Examples werden zu vollen 1024-Token-Sequenzen gepackt, getrennt
  durch EOS. Lange Examples (> 1024 Tokens) werden in überlappende Chunks
  gesplittet. → KEIN Token geht verloren, maximale GPU-Auslastung.

  NEU: Block-diagonal causal attention mask verhindert Cross-Contamination
  zwischen gepackten Examples. Jedes Example sieht nur seine eigenen Tokens.

WICHTIG: 5-bit Quantisierung Bug-Fix
  DoRALinear.from_base() berechnet input_dims falsch bei 5-bit:
  `32 // 5 = 6` statt `6.4` → alle Dimensionen sind falsch.
  Wir umgehen das mit manueller DoRALinear-Erstellung + set_linear().

Ministral-Architektur:
  - model.language_model.model.layers[0..39]
  - self_attn: q_proj(5120→4096), k_proj(5120→1024), v_proj(5120→1024), o_proj(4096→5120)
  - mlp: gate_proj(5120→16384), up_proj(5120→16384), down_proj(16384→5120)
  - language_model() returns raw tensor (no .logits attribute!)
  - Chat: <s>[SYSTEM_PROMPT]...[/SYSTEM_PROMPT][INST]...[/INST]response</s>

RAM Budget (M4 24GB, VS Code CLOSED):
  Model: ~9.5 GB (5-bit)
  DoRA overhead: ~1.0 GB (attn-only, rank=32)
  Optimizer state: ~1.0 GB
  Activations (seq=1024): ~2-3 GB
  Total: ~14-15 GB → safe with ~9 GB headroom

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"

    # Dry run (3 steps, verify pipeline):
    .venv/bin/python3 lora_training/train_ministral.py --dry-run

    # Full training (1 epoch, attn-only, then merge):
    .venv/bin/python3 lora_training/train_ministral.py

    # Training ohne merge (checkpoint only):
    .venv/bin/python3 lora_training/train_ministral.py --no-merge
"""
import os
import sys
import gc
import json
import time
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
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════
PROJECT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
SAVE_PATH    = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")  # in-place
TRAIN_F      = os.path.join(PROJECT, "dora_training", "clean_train_v3.jsonl")
VALID_F      = os.path.join(PROJECT, "dora_training", "clean_valid_v3.jsonl")
CKPT_DIR     = os.path.join(PROJECT, "lora_training", "checkpoints_ministral")

# DoRA — attn-only, rank=32 für v3-Feintuning (überschreibt altes Training)
RANK         = 32
ALPHA        = 64           # = 2×RANK → Scale bleibt 2.0
SCALE        = ALPHA / RANK  # 2.0
DROPOUT      = 0.05
TARGETS      = ["q_proj", "k_proj", "v_proj", "o_proj"]

# Training — 2 Epochen, konservative LR (from scratch auf Instruct-Weights)
EPOCHS       = 2
LR           = 2e-5
SEQ          = 1024         # Volle Seq-Länge — VS Code MUSS geschlossen sein
WARMUP_RATIO = 0.06
WEIGHT_DECAY = 0.01
REPORT_EVERY = 25
EVAL_EVERY   = 50
CKPT_EVERY   = 50           # Checkpoint alle 50 Steps (Sweetspot: Ende Ep1 → Mitte Ep2)

# Backup-Suffix für atomaren Save
BACKUP_SUFFIX = "_pre_v3_backup"

# Graceful interrupt handling
_INTERRUPTED = False
def _signal_handler(sig, frame):
    global _INTERRUPTED
    if _INTERRUPTED:
        print("\n  ⚠️  Force quit!")
        sys.exit(1)
    _INTERRUPTED = True
    print("\n  ⚠️  Interrupt received — will save checkpoint after current step...")
signal.signal(signal.SIGINT, _signal_handler)


# ═══════════════════════════════════════════════════════════════════════════
# MODEL DIMENSIONS (from config, NOT from buggy packed-weight calculation)
# ═══════════════════════════════════════════════════════════════════════════
def get_dim_map(config_path: str) -> dict:
    """Read true dimensions from config.json to work around 5-bit DoRA bug."""
    with open(config_path) as f:
        cfg = json.load(f)
    tc = cfg.get("text_config", cfg)
    h    = tc["hidden_size"]           # 5120
    inter = tc["intermediate_size"]    # 16384
    nh   = tc["num_attention_heads"]   # 32
    nkv  = tc["num_key_value_heads"]   # 8
    hd   = tc["head_dim"]             # 128
    return {
        "q_proj":    (h, nh * hd),      # 5120 → 4096
        "k_proj":    (h, nkv * hd),     # 5120 → 1024
        "v_proj":    (h, nkv * hd),     # 5120 → 1024
        "o_proj":    (nh * hd, h),      # 4096 → 5120
        "gate_proj": (h, inter),        # 5120 → 16384
        "up_proj":   (h, inter),        # 5120 → 16384
        "down_proj": (inter, h),        # 16384 → 5120
    }


# ═══════════════════════════════════════════════════════════════════════════
# DATASET FORMAT
# ═══════════════════════════════════════════════════════════════════════════
def messages_to_text(messages: list) -> str:
    """Konvertiert messages-Format → Ministral Chat-Template.
    Format: <s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT][INST]{user}[/INST]{assistant}</s>
    """
    system = ""
    user = ""
    assistant = ""
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            system = content
        elif role == "user":
            user = content
        elif role == "assistant":
            assistant = content

    if system:
        return f"<s>[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT][INST]{user}[/INST]{assistant}</s>"
    else:
        return f"<s>[INST]{user}[/INST]{assistant}</s>"


# ═══════════════════════════════════════════════════════════════════════════
# DATASET — with SEQUENCE PACKING
# ═══════════════════════════════════════════════════════════════════════════
class TextDataset:
    """JSONL dataset with SEQUENCE PACKING + chunking.

    Strategy:
      1. Long examples (> max_seq) are CHUNKED with overlap → no data lost
      2. Short examples are PACKED together into full sequences → no wasted tokens
      3. EOS token separates packed examples within a sequence
      4. Packing dramatically improves training efficiency:
         - Without packing: median 192 tokens → 80% wasted per sequence
         - With packing: ~5 short examples per sequence → ~95%+ utilization

    This follows the T5/LLaMA/Mistral packing approach where multiple training
    examples share a single forward pass. The model learns to handle EOS boundaries
    naturally since it sees them during pre-training too.
    """

    def __init__(self, path, tokenizer, max_seq=SEQ, max_n=None, do_pack=True):
        self.items = []
        self.segments = []  # segment lengths per packed sequence (for attention mask)
        self.n_originals = 0
        self.n_chunks_from_long = 0
        self.n_packed_seqs = 0
        self.total_tokens_raw = 0
        self.total_tokens_packed = 0

        OVERLAP = 64   # token overlap between chunks of long examples
        PACK_PAD = 4   # minimum leftover space to consider "full enough"

        eos_id = tokenizer.eos_token_id or 1  # Mistral EOS = 2 usually

        # Phase 1: Tokenize everything, separate into short and long
        short_seqs = []   # will be packed together
        long_chunks = []  # already chunked, go directly into items

        with open(path) as f:
            for i, line in enumerate(f):
                if max_n and i >= max_n:
                    break
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if "text" in d:
                    text = d["text"]
                elif "messages" in d:
                    text = messages_to_text(d["messages"])
                else:
                    continue
                toks = tokenizer.encode(text)
                if len(toks) < 5:
                    continue
                self.n_originals += 1
                self.total_tokens_raw += len(toks)

                if len(toks) <= max_seq:
                    short_seqs.append(toks)
                else:
                    # Chunk long sequences with overlap
                    start = 0
                    while start < len(toks):
                        end = min(start + max_seq, len(toks))
                        chunk = toks[start:end]
                        if len(chunk) > 5:
                            long_chunks.append(chunk)
                            self.n_chunks_from_long += 1
                        start += max_seq - OVERLAP

        # Phase 2: Pack short sequences into full-length sequences
        if do_pack and short_seqs:
            # Shuffle short seqs so packing isn't biased by file order
            rng = np.random.RandomState(42)
            order = rng.permutation(len(short_seqs))

            current_pack = []
            current_len = 0
            current_segments = []  # lengths of each example in this pack

            for idx in order:
                toks = short_seqs[idx]
                # +1 for EOS separator between packed examples
                needed = len(toks) + (1 if current_pack else 0)

                if current_len + needed <= max_seq:
                    # Fits — add to current pack
                    if current_pack:
                        current_pack.append(eos_id)  # separator
                        # EOS belongs to previous segment
                        current_segments[-1] += 1
                    current_pack.extend(toks)
                    current_segments.append(len(toks))
                    current_len += needed
                else:
                    # Doesn't fit — flush current pack and start new one
                    if current_pack and len(current_pack) > 5:
                        self.items.append(mx.array(current_pack))
                        self.segments.append(current_segments)
                        self.total_tokens_packed += len(current_pack)
                        self.n_packed_seqs += 1
                    current_pack = list(toks)
                    current_len = len(toks)
                    current_segments = [len(toks)]

            # Flush last pack
            if current_pack and len(current_pack) > 5:
                self.items.append(mx.array(current_pack))
                self.segments.append(current_segments)
                self.total_tokens_packed += len(current_pack)
                self.n_packed_seqs += 1
        else:
            # No packing — just add short seqs as-is
            for toks in short_seqs:
                self.items.append(mx.array(toks))
                self.segments.append([len(toks)])  # single segment
                self.total_tokens_packed += len(toks)

        # Phase 3: Add long chunks (already full-length, no packing needed)
        for chunk in long_chunks:
            self.items.append(mx.array(chunk))
            self.segments.append([len(chunk)])  # single segment
            self.total_tokens_packed += len(chunk)

    def __len__(self):
        return len(self.items)

    def stats_str(self):
        """Human-readable statistics about packing efficiency."""
        lines = []
        lines.append(f"  Originals: {self.n_originals} examples")
        lines.append(f"  Raw tokens: {self.total_tokens_raw:,}")
        lines.append(f"  After packing: {len(self.items)} sequences "
                     f"({self.n_packed_seqs} packed + {self.n_chunks_from_long} chunks from long)")
        lines.append(f"  Packed tokens: {self.total_tokens_packed:,}")
        if self.items:
            lens = [len(x) for x in self.items]
            lines.append(f"  Seq lengths: min={min(lens)}, median={int(np.median(lens))}, "
                         f"max={max(lens)}, avg={np.mean(lens):.0f}")
            utilization = np.mean(lens) / SEQ * 100
            lines.append(f"  Sequence utilization: {utilization:.1f}%")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# DoRA — with 5-bit bug workaround
# ═══════════════════════════════════════════════════════════════════════════
def apply_dora(model, dim_map):
    """Apply DoRA with CORRECT dimensions (bypasses 5-bit bug)."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    attn_set = {"q_proj", "k_proj", "v_proj", "o_proj"}
    mlp_set  = {"gate_proj", "up_proj", "down_proj"}
    n = 0

    for layer in lm.model.layers:
        for name in TARGETS:
            if name in attn_set:
                container = layer.self_attn
            elif name in mlp_set:
                container = getattr(layer, "mlp", None)
                if container is None:
                    continue
            else:
                continue

            if not hasattr(container, name):
                continue

            orig = getattr(container, name)
            in_d, out_d = dim_map[name]

            # Create DoRALinear with CORRECT dims (not from_base which is buggy)
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
    attn_set = {"q_proj", "k_proj", "v_proj", "o_proj"}
    mlp_set  = {"gate_proj", "up_proj", "down_proj"}
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            if name in attn_set:
                container = layer.self_attn
            elif name in mlp_set:
                container = getattr(layer, "mlp", None)
                if not container:
                    continue
            else:
                continue
            if hasattr(container, name):
                mod = getattr(container, name)
                if isinstance(mod, DoRALinear):
                    setattr(container, name, mod.fuse(dequantize=False))
                    n += 1
    return n


def save_checkpoint(model, epoch, step, train_loss, val_loss=None):
    os.makedirs(CKPT_DIR, exist_ok=True)
    path = os.path.join(CKPT_DIR, f"ministral_epoch{epoch}_step{step}.npz")
    lm = model.language_model
    trainable = dict(tree_flatten(lm.trainable_parameters()))
    mx.savez(path, **trainable)
    meta = {
        "epoch": epoch, "step": step,
        "train_loss": float(train_loss),
        "val_loss": float(val_loss) if val_loss else None,
        "timestamp": datetime.now().isoformat(),
        "dora_rank": RANK, "dora_alpha": ALPHA,
    }
    with open(path.replace(".npz", "_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    mb = os.path.getsize(path) / (1024**2)
    print(f"  💾 Checkpoint: {os.path.basename(path)} ({mb:.1f} MB)")
    return path


# ═══════════════════════════════════════════════════════════════════════════
# ATTENTION MASK FOR PACKED SEQUENCES
# ═══════════════════════════════════════════════════════════════════════════
def build_packed_mask(segments, seq_len):
    """Build causal attention mask that blocks cross-example attention.

    For packed sequences with multiple examples, each example can only
    attend to tokens within itself (+ causal constraint). This prevents
    cross-contamination between packed training examples.

    Returns shape (1, 1, seq_len, seq_len) with 0.0 for allowed and
    -1e9 for blocked positions.
    """
    if len(segments) <= 1:
        return None  # Single example — standard causal mask from model is fine

    # Build segment IDs: [0,0,0, 1,1,1,1, 2,2, ...]
    seg_ids = []
    for i, length in enumerate(segments):
        seg_ids.extend([i] * length)
    # Pad if segments don't fill seq_len (shouldn't happen, but safety)
    while len(seg_ids) < seq_len:
        seg_ids.append(seg_ids[-1] if seg_ids else 0)
    seg_ids = mx.array(seg_ids[:seq_len])

    # Same-segment mask: True where seg_ids[i] == seg_ids[j]
    same_seg = seg_ids[:, None] == seg_ids[None, :]  # (seq, seq)

    # Causal mask: True where j <= i (lower triangular)
    causal = mx.tril(mx.ones((seq_len, seq_len), dtype=mx.bool_))

    # Combined: allowed only if same segment AND causal
    allowed = same_seg & causal

    # Convert to additive mask: 0.0 for allowed, -1e9 for blocked
    mask = mx.where(allowed, mx.zeros(allowed.shape, dtype=mx.float32),
                    mx.full(allowed.shape, -1e9, dtype=mx.float32))

    return mask[None, None, :, :]  # (1, 1, seq, seq) for broadcast over heads


# ═══════════════════════════════════════════════════════════════════════════
# LOSS + EVAL
# ═══════════════════════════════════════════════════════════════════════════
# PACKED-MASK MONKEY-PATCH for Mistral3
# ═══════════════════════════════════════════════════════════════════════════
import mlx_lm.models.ministral3 as _ministral3_mod

_ORIG_CREATE_ATTN_MASK = _ministral3_mod.create_attention_mask
_OVERRIDE_MASK = None  # thread-local-ish: set before forward, cleared after


def _patched_create_attention_mask(h, cache=None, window_size=None, return_array=False):
    """If we have an override mask (from packing), use it. Otherwise default."""
    global _OVERRIDE_MASK
    if _OVERRIDE_MASK is not None:
        # _OVERRIDE_MASK is an additive mask with floats (0.0 / -1e9).
        # Ensure it has the same dtype as model hidden (h.dtype) so
        # scaled_dot_product_attention accepts it (e.g., bfloat16).
        try:
            if isinstance(_OVERRIDE_MASK, mx.array):
                return _OVERRIDE_MASK.astype(h.dtype)
            else:
                return mx.array(_OVERRIDE_MASK, dtype=h.dtype)
        except Exception:
            # fallback: return as-is
            return _OVERRIDE_MASK
    return _ORIG_CREATE_ATTN_MASK(h, cache=cache, window_size=window_size,
                                   return_array=return_array)

_ministral3_mod.create_attention_mask = _patched_create_attention_mask


# ═══════════════════════════════════════════════════════════════════════════
# LOSS + EVAL
# ═══════════════════════════════════════════════════════════════════════════
def compute_loss(language_model, tokens, segments=None):
    """Causal LM loss with optional packed-sequence attention mask.

    When segments is provided (multiple examples packed in one sequence),
    builds a block-diagonal causal mask so examples can't attend to each other.
    Uses monkey-patch on create_attention_mask so Mistral3's internal SWA/FA
    layers pick up our packed mask.
    """
    global _OVERRIDE_MASK
    input_ids = tokens[:-1][None]  # (1, seq-1)
    seq_len = input_ids.shape[1]

    if segments is not None and len(segments) > 1:
        full_mask = build_packed_mask(segments, len(tokens))
        if full_mask is not None:
            _OVERRIDE_MASK = full_mask[:, :, :seq_len, :seq_len]

    try:
        out = language_model(input_ids)
    finally:
        _OVERRIDE_MASK = None  # always clear

    logits = out.logits if hasattr(out, "logits") else out
    logits = logits.squeeze(0)
    return nn.losses.cross_entropy(logits, tokens[1:], reduction="mean")


def evaluate(lm, dataset, max_n=30):
    vals = []
    for item in dataset.items[:min(max_n, len(dataset))]:
        l = compute_loss(lm, item)
        mx.eval(l)
        vals.append(l.item())
    return np.mean(vals)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    global _INTERRUPTED

    ap = argparse.ArgumentParser(description="DoRA Training for CodeAiley-14B (Ministral)")
    ap.add_argument("--dry-run", action="store_true", help="3 steps, no save")
    ap.add_argument("--no-merge", action="store_true", help="Train + checkpoint, no merge")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--seq", type=int, default=SEQ)
    args = ap.parse_args()

    epochs = args.epochs
    lr = args.lr
    seq = args.seq

    # ── Memory: allow spikes up to 28 GB, generous cache (backward-compatible)
    import mlx.core as _mx
    MEM_LIMIT = 28 * 1024**3
    CACHE_LIMIT = 4 * 1024**3
    # prefer new API mlx.set_memory_limit / mlx.set_cache_limit, fallback to mlx.metal
    try:
        if hasattr(_mx, 'set_memory_limit'):
            _mx.set_memory_limit(MEM_LIMIT)
            _mx.set_cache_limit(CACHE_LIMIT)
            print(f"  mlx.set_memory_limit applied: {MEM_LIMIT // 1024**3} GB, cache: {CACHE_LIMIT // 1024**3} GB")
        else:
            raise AttributeError
    except Exception:
        try:
            # older API
            _mx.metal.set_memory_limit(MEM_LIMIT)
            _mx.metal.set_cache_limit(CACHE_LIMIT)
            print(f"  mlx.metal.set_memory_limit applied: {MEM_LIMIT // 1024**3} GB, cache: {CACHE_LIMIT // 1024**3} GB")
        except Exception:
            print("  Warning: could not set mlx memory limits (running with defaults)")

    print("=" * 64)
    print("  🧠 DoRA Training — Ailey-14B (Ministral)")
    if args.dry_run:
        print("  MODE: Dry-run (3 steps)")
    else:
        print(f"  MODE: {epochs} epochs → {'checkpoint' if args.no_merge else 'merge in-place'}")
    print("=" * 64)

    # ── Verify ────────────────────────────────────────────────────
    assert os.path.isdir(MODEL_PATH), f"Model not found: {MODEL_PATH}"
    assert os.path.isfile(TRAIN_F), f"Train data not found: {TRAIN_F}"

    with open(TRAIN_F) as f:
        n_train_total = sum(1 for l in f if l.strip())
    n_valid_total = 0
    if os.path.isfile(VALID_F):
        with open(VALID_F) as f:
            n_valid_total = sum(1 for l in f if l.strip())

    dim_map = get_dim_map(os.path.join(MODEL_PATH, "config.json"))

    print(f"\n  Model:    {os.path.basename(MODEL_PATH)}")
    print(f"  Data:     {n_train_total} train, {n_valid_total} valid")
    print(f"  DoRA:     rank={RANK}, alpha={ALPHA}, scale={SCALE:.1f}, dropout={DROPOUT}")
    print(f"  Targets:  {TARGETS}")
    print(f"  Training: epochs={epochs}, lr={lr}, seq={seq}")
    print(f"  5-bit fix: using manual dim_map (bypasses DoRALinear.from_base bug)")
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
    n_train = freeze_non_dora(model)

    # ── Load data (with sequence packing) ──────────────────────────
    print("\nTokenizing + packing data...")
    max_samples = 20 if args.dry_run else None
    # Mistral3 packing: monkey-patched create_attention_mask handles packed masks
    train_ds = TextDataset(TRAIN_F, tok, max_seq=seq, max_n=max_samples,
                           do_pack=True)
    val_ds = None
    if os.path.isfile(VALID_F) and not args.dry_run:
        # Don't pack validation — we want per-example loss
        val_ds = TextDataset(VALID_F, tok, max_seq=seq, do_pack=False)

    print(f"\n  📦 Train dataset (packed):")
    print(train_ds.stats_str())
    if val_ds:
        print(f"\n  📋 Valid dataset (unpacked):")
        print(val_ds.stats_str())

    # ── Training setup ────────────────────────────────────────────
    n_train_items = len(train_ds)
    steps_per_epoch = n_train_items
    dry_steps = 3

    if args.dry_run:
        total_steps = dry_steps
        epochs = 1
    else:
        total_steps = steps_per_epoch * epochs

    warmup_steps = max(1, int(total_steps * WARMUP_RATIO))

    print(f"\n  Steps/epoch: {steps_per_epoch}")
    print(f"  Total steps: {total_steps}")
    print(f"  Warmup: {warmup_steps}")

    # Optimizer
    warmup_sched = optim.linear_schedule(init=1e-7, end=lr, steps=warmup_steps)
    cos_sched = optim.cosine_decay(init=lr, decay_steps=max(1, total_steps - warmup_steps))
    lr_sched = optim.join_schedules([warmup_sched, cos_sched], [warmup_steps])
    optimizer = optim.AdamW(learning_rate=lr_sched, weight_decay=WEIGHT_DECAY)

    # CRITICAL: scope on language_model
    lm = model.language_model
    loss_and_grad = nn.value_and_grad(lm, compute_loss)

    # ── Training loop ─────────────────────────────────────────────
    print(f"\n{'='*64}")
    print(f"  🚀 Starting DoRA training — Ailey-14B")
    if args.dry_run:
        print(f"  DRY RUN: {dry_steps} steps")
    else:
        print(f"  {epochs} epochs × {steps_per_epoch} steps = {total_steps}")
    print(f"{'='*64}\n")

    t_start = time.time()
    best_val = float("inf")
    all_losses = []
    global_step = 0

    for epoch in range(1, epochs + 1):
        if not args.dry_run:
            print(f"\n── Epoch {epoch}/{epochs} ──")

        indices = np.random.permutation(n_train_items)
        epoch_losses = []

        for i, idx in enumerate(indices):
            if _INTERRUPTED:
                print(f"\n  ⚠️  Interrupted at step {global_step}")
                break

            tokens = train_ds.items[idx]
            segments = train_ds.segments[idx]
            loss, grads = loss_and_grad(lm, tokens, segments)
            mx.eval(loss, grads)

            optimizer.update(lm, grads)
            mx.eval(lm.parameters(), optimizer.state)

            global_step += 1
            lv = loss.item()
            all_losses.append(lv)
            epoch_losses.append(lv)

            if global_step % REPORT_EVERY == 0 or global_step == total_steps:
                avg = np.mean(all_losses[-REPORT_EVERY:])
                elapsed = time.time() - t_start
                eta = (elapsed / global_step) * (total_steps - global_step)
                eta_m = eta / 60
                print(f"  Step {global_step:5d}/{total_steps}: loss={avg:.4f}, "
                      f"elapsed={elapsed/60:.1f}m, ETA={eta_m:.0f}m", flush=True)

            if global_step % EVAL_EVERY == 0 and val_ds and not args.dry_run:
                vl = evaluate(lm, val_ds)
                tag = " ← best" if vl < best_val else ""
                if vl < best_val:
                    best_val = vl
                print(f"  Step {global_step:5d}: val_loss={vl:.4f}{tag}")

            # Mid-epoch checkpoints
            if global_step % CKPT_EVERY == 0 and not args.dry_run:
                avg_recent = np.mean(all_losses[-CKPT_EVERY:])
                save_checkpoint(model, epoch, global_step, avg_recent,
                                best_val if best_val < float("inf") else None)

            if args.dry_run and global_step >= dry_steps:
                break

        if _INTERRUPTED or (args.dry_run and global_step >= dry_steps):
            break

        # End of epoch
        avg_epoch = np.mean(epoch_losses) if epoch_losses else 0
        print(f"\n  Epoch {epoch} done: avg_loss={avg_epoch:.4f}")

        if val_ds:
            vl = evaluate(lm, val_ds)
            tag = " ← best" if vl < best_val else ""
            if vl < best_val:
                best_val = vl
            print(f"  Epoch {epoch} val_loss={vl:.4f}{tag}")

        # Save checkpoint every epoch
        save_checkpoint(model, epoch, global_step, avg_epoch,
                        best_val if val_ds and best_val < float("inf") else None)

    # ── Summary ───────────────────────────────────────────────────
    total_time = time.time() - t_start
    final_loss = np.mean(all_losses[-min(50, len(all_losses)):]) if all_losses else 0

    print(f"\n{'='*64}")
    print(f"  Training done: {total_time/60:.1f} min")
    print(f"  Final train loss: {final_loss:.4f}")
    if val_ds and not args.dry_run:
        final_val = evaluate(lm, val_ds)
        print(f"  Final val loss:   {final_val:.4f}")
        print(f"  Best val loss:    {best_val:.4f}")
    print(f"{'='*64}")

    if _INTERRUPTED:
        # Save emergency checkpoint
        save_checkpoint(model, epoch, global_step, final_loss,
                        best_val if val_ds and best_val < float("inf") else None)
        print(f"\n  ⚠️  Training interrupted — checkpoint saved")
        print(f"  To resume: reload checkpoint and continue training")
        return

    if args.dry_run:
        print(f"\n✅ DRY RUN OK!")
        print(f"  Loss after {dry_steps} steps: {all_losses[-1]:.4f}")
        print(f"  Dataset: {len(train_ds)} examples loaded")
        print(f"  Time: {total_time:.1f}s")
        print(f"\n  Full run:")
        print(f"    .venv/bin/python3 lora_training/train_ministral.py")
        return

    if args.no_merge:
        save_checkpoint(model, epochs, global_step, final_loss,
                        best_val if val_ds and best_val < float("inf") else None)
        print(f"\n✅ Training done (no merge)")
        print(f"  Checkpoints: {CKPT_DIR}")
        return

    # ── Sanity check ──────────────────────────────────────────────
    print("\n  🧪 Sanity check (DoRA active)...")
    for q in ["Wer bist du?", "Schreib mir einen kurzen Song über Regen."]:
        prompt = f"<s>[INST]{q}[/INST]"
        result = mlx_lm.generate(model, tok, prompt=prompt, max_tokens=150, verbose=False)
        print(f"  Q: {q}")
        print(f"  A: {result[:250]}\n")

    # ── Fuse + Save (SAFE: write to temp dir, then atomic swap) ────
    print("  Fusing DoRA → QuantizedLinear...")
    n_fused = fuse_dora(model)
    print(f"  {n_fused} layers fused")

    # SAFE SAVE: write to temp dir first, then swap
    # This prevents the Qwen disaster (crash during save = corrupted model)
    tmp_save = SAVE_PATH + "_tmp_merge"
    if os.path.exists(tmp_save):
        shutil.rmtree(tmp_save)
    os.makedirs(tmp_save, exist_ok=True)

    print(f"\n  Saving to temp dir first (safe merge)...")
    from mlx_lm.utils import save_model

    # Copy all non-weight files (config, tokenizer, etc.)
    for f in Path(SAVE_PATH).iterdir():
        if f.is_file() and not f.name.startswith("model") and f.suffix != ".safetensors":
            shutil.copy2(f, tmp_save)

    save_model(tmp_save, model, donate_model=True)

    # Verify the temp save is valid
    tmp_size = sum(f.stat().st_size for f in Path(tmp_save).iterdir() if f.is_file())
    orig_size = sum(f.stat().st_size for f in Path(SAVE_PATH).iterdir() if f.is_file())
    print(f"  Temp save: {tmp_size/1024**3:.2f} GB (original: {orig_size/1024**3:.2f} GB)")

    if tmp_size < orig_size * 0.5:
        print(f"  ❌ ERROR: Temp save is suspiciously small! Aborting swap.")
        print(f"  Temp dir kept at: {tmp_save}")
        print(f"  Original model UNTOUCHED at: {SAVE_PATH}")
        return

    # Atomic swap: rename original → backup, temp → original
    backup_path = SAVE_PATH + BACKUP_SUFFIX
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)

    print(f"  Swapping: original → backup, temp → final...")
    os.rename(SAVE_PATH, backup_path)
    os.rename(tmp_save, SAVE_PATH)
    print(f"  ✅ Swap complete!")
    print(f"  Backup at: {backup_path}")
    print(f"  (Delete backup manually once you've verified the model works)")

    # Update config with training metadata
    cfg_path = os.path.join(SAVE_PATH, "config.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["ailey_dora"] = {
            "version": "4.0",
            "name": "Ailey-14B",
            "base": "Ministral-3-14B-Reasoning-5bit",
            "type": "persona_dora_v3",
            "dora_rank": RANK,
            "dora_alpha": ALPHA,
            "training_examples": n_train_total,
            "epochs": epochs,
            "seq_len": seq,
            "final_train_loss": float(final_loss),
            "best_val_loss": float(best_val) if best_val < float("inf") else None,
            "timestamp": datetime.now().isoformat(),
        }
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
        print("  config.json updated")

    total_size = sum(f.stat().st_size for f in Path(SAVE_PATH).iterdir() if f.is_file())
    print(f"  Model: {total_size/1024**3:.2f} GB")

    print(f"\n{'='*64}")
    print(f"  ✅ DONE! CodeAiley-14B trained and merged.")
    print(f"  Model: {SAVE_PATH}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
