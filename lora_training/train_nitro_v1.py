#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
  AileyNitro-2B DoRA Training v1 — Kontinuierliches Finetuning
  Trainiert auf dem bestehenden AileyNitro-2B (Gemma4 E2B, 4-bit, gefused)
═══════════════════════════════════════════════════════════════════════════

Dataset: nitro_train_v1.jsonl (1829 Pairs: 1693 Base + 136 Nitro-Extras)
         nitro_valid_v1.jsonl (97 Pairs)

SEQUENCE PACKING + BLOCK-DIAGONAL ATTENTION:
  Kurze Examples (<= SEQ Tokens) werden zu vollen SEQ-Sequenzen gepackt,
  getrennt durch EOS. Block-Diagonal Causal Mask verhindert Cross-
  Contamination zwischen gepackten Examples. Jedes Example sieht nur
  seine eigenen Tokens (+ causal constraint).

  Lange Examples (> SEQ) werden in überlappende Chunks gesplittet.
  → KEIN Token geht verloren, maximale GPU-Auslastung.

Gemma4-spezifisch:
  - model.language_model(inputs, mask=packed_mask) für Packing-Mask
  - language_model gibt logits direkt zurück (kein .logits-Attribut)
  - DoRA auf Attention-Layer: q_proj, k_proj, v_proj, o_proj
  - 4-bit Quantisierung bleibt erhalten (dequantize=False beim Fuse)
  - Sliding-Window + Full-Attention Layer — Mask gilt für beide

RAM Budget (M4 24GB):
  AileyNitro-2B:  ~1.1 GB (4-bit)
  DoRA overhead:  ~0.3 GB (rank=16, attn-only)
  Optimizer:      ~0.2 GB
  Activations:    ~1-2 GB (seq=512)
  Total:          ~3-4 GB → sehr komfortabel, Ministral kann parallel laufen

Usage:
    # Dry-run (5 Steps, kein Merge):
    .venv/bin/python3 lora_training/train_nitro_v1.py --dry-run

    # Volles Training:
    .venv/bin/python3 lora_training/train_nitro_v1.py

    # Ohne Merge (Checkpoint sichern, später mergen):
    .venv/bin/python3 lora_training/train_nitro_v1.py --no-merge
"""

import os
import sys
import gc
import json
import time
import shutil
import signal
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten

# ── Pfade ──────────────────────────────────────────────────────────────────
PROJECT_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH     = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
DATA_DIR       = os.path.join(PROJECT_ROOT, "dora_training")
CKPT_DIR       = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints_nitro_v1")
MERGED_PATH    = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")  # in-place update
TRAIN_FILE     = os.path.join(DATA_DIR, "nitro_train_v1.jsonl")
VALID_FILE     = os.path.join(DATA_DIR, "nitro_valid_v1.jsonl")

# ── Hyperparameter ──────────────────────────────────────────────────────────
SEQ            = 512          # Sequence-Länge (Gemma4 E2B ist schnell genug)
EPOCHS         = 2            # Über alles 2× — Basis ist schon trainiert
BATCH_SIZE     = 1
RANK           = 16           # DoRA Rank (kleiner als Ministral weil Modell kleiner)
ALPHA          = 32           # DoRA Alpha = 2 × Rank
SCALE          = float(ALPHA) / float(RANK)
DROPOUT        = 0.05
LEARNING_RATE  = 1e-4         # Etwas höher als Ministral — Nitro ist kleiner
WARMUP_STEPS     = 20
STEPS_PER_REPORT = 10    # Jede N Steps: Train-Loss Zeile
STEPS_PER_EVAL   = 50    # Jede N Steps: Val-Loss evaluieren + Checkpoint wenn best
STEPS_PER_CKPT   = 100   # Jede N Steps: Regulärer Checkpoint
GRAD_CLIP        = 1.0

# Im Dry-Run gelten verkürzte Intervalle
DRY_STEPS_PER_REPORT = 5
DRY_STEPS_PER_EVAL   = 10
DRY_STEPS_PER_CKPT   = 15

TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


# ═══════════════════════════════════════════════════════════════════════════
# DATASET MIT PACKING
# ═══════════════════════════════════════════════════════════════════════════

def messages_to_text(messages: list, tokenizer) -> str:
    """Wendet das Chat-Template auf eine messages-Liste an."""
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )


class PackedDataset:
    """
    JSONL Dataset mit Sequence Packing + Block-Diagonal Attention Segments.

    Kurze Sequences werden gepackt (EOS-getrennt) bis SEQ Tokens voll.
    Lange Sequences werden mit OVERLAP gechunkt.
    self.segments[i] = Liste der Segment-Längen für packed sequence i.
    """

    def __init__(self, path: str, tokenizer, max_seq: int = SEQ, max_n: int = None):
        self.items    = []    # mx.array(tokens) pro packed sequence
        self.segments = []    # [[seg_len, seg_len, ...]] pro sequence
        self.n_originals         = 0
        self.n_chunks_from_long  = 0
        self.n_packed_seqs       = 0
        self.total_tokens_raw    = 0
        self.total_tokens_packed = 0

        OVERLAP  = 64
        PACK_PAD = 4

        eos_id = tokenizer.eos_token_id or 1

        short_seqs  = []
        long_chunks = []

        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if max_n and i >= max_n:
                    break
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if "messages" in d:
                    text = messages_to_text(d["messages"], tokenizer)
                elif "text" in d:
                    text = d["text"]
                else:
                    continue
                toks = tokenizer.encode(text)
                if len(toks) < 5:
                    continue
                self.n_originals     += 1
                self.total_tokens_raw += len(toks)

                if len(toks) <= max_seq:
                    short_seqs.append(toks)
                else:
                    start = 0
                    while start < len(toks):
                        end   = min(start + max_seq, len(toks))
                        chunk = toks[start:end]
                        if len(chunk) > 5:
                            long_chunks.append(chunk)
                            self.n_chunks_from_long += 1
                        start += max_seq - OVERLAP

        # Phase 2: Pack short sequences
        rng   = np.random.RandomState(42)
        order = rng.permutation(len(short_seqs))

        current_pack     = []
        current_len      = 0
        current_segments = []

        def flush():
            if current_pack and len(current_pack) > 5:
                self.items.append(mx.array(current_pack))
                self.segments.append(list(current_segments))
                self.total_tokens_packed += len(current_pack)
                self.n_packed_seqs += 1

        for idx in order:
            toks   = short_seqs[idx]
            needed = len(toks) + (1 if current_pack else 0)

            if current_len + needed <= max_seq:
                if current_pack:
                    current_pack.append(eos_id)
                    current_segments[-1] += 1     # EOS gehört zum vorigen Segment
                current_pack.extend(toks)
                current_segments.append(len(toks))
                current_len += needed
            else:
                flush()
                current_pack     = list(toks)
                current_len      = len(toks)
                current_segments = [len(toks)]

        flush()

        # Phase 3: Long chunks (kein Packing nötig)
        for chunk in long_chunks:
            self.items.append(mx.array(chunk))
            self.segments.append([len(chunk)])
            self.total_tokens_packed += len(chunk)

    def __len__(self):
        return len(self.items)

    def stats_str(self) -> str:
        lines = [
            f"  Originals:       {self.n_originals}",
            f"  Raw tokens:      {self.total_tokens_raw:,}",
            f"  Packed seqs:     {len(self.items)} "
            f"({self.n_packed_seqs} packed + {self.n_chunks_from_long} long chunks)",
            f"  Packed tokens:   {self.total_tokens_packed:,}",
        ]
        if self.items:
            lens  = [len(x) for x in self.items]
            util  = np.mean(lens) / SEQ * 100
            lines.append(
                f"  Seq lengths:     min={min(lens)} median={int(np.median(lens))} "
                f"max={max(lens)} avg={np.mean(lens):.0f}"
            )
            lines.append(f"  Utilization:     {util:.1f}%")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# BLOCK-DIAGONAL ATTENTION MASK
# ═══════════════════════════════════════════════════════════════════════════

def build_packed_mask(segments: list, seq_len: int) -> mx.array | None:
    """
    Baut eine Causal Attention Mask die Cross-Example-Attention blockiert.

    Für gepackte Sequenzen darf jedes Sub-Example nur seine eigenen Tokens
    sehen (Block-Diagonal + Causal). Gibt None zurück wenn nur 1 Segment.

    Shape: (1, 1, seq_len, seq_len) — additive Float-Mask (0.0 / -1e9)
    """
    if len(segments) <= 1:
        return None  # Einzel-Example → Standard-Causal-Mask des Modells reicht

    seg_ids = []
    for i, length in enumerate(segments):
        seg_ids.extend([i] * length)
    while len(seg_ids) < seq_len:
        seg_ids.append(seg_ids[-1] if seg_ids else 0)
    seg_ids = mx.array(seg_ids[:seq_len])

    same_seg = (seg_ids[:, None] == seg_ids[None, :])
    causal   = mx.tril(mx.ones((seq_len, seq_len), dtype=mx.bool_))
    allowed  = same_seg & causal

    mask = mx.where(
        allowed,
        mx.zeros(allowed.shape, dtype=mx.float32),
        mx.full(allowed.shape, -1e9, dtype=mx.float32),
    )
    return mask[None, None, :, :]   # (1, 1, seq, seq)


# ═══════════════════════════════════════════════════════════════════════════
# DoRA
# ═══════════════════════════════════════════════════════════════════════════

def apply_dora(model, rank: int, scale: float, dropout: float) -> int:
    """Ersetzt Target-Attention-Layers durch DoRALinear."""
    from mlx_lm.tuner.dora import DoRALinear

    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                orig  = getattr(attn, name)
                dora  = DoRALinear.from_base(orig, r=rank, dropout=dropout, scale=scale)
                setattr(attn, name, dora)
                n += 1
    return n


def freeze_non_dora(model) -> int:
    lm = model.language_model
    lm.freeze()
    lm.unfreeze(keys=["lora_a", "lora_b", "m"])
    total    = sum(p.size for _, p in tree_flatten(lm.parameters()))
    trainable = sum(p.size for _, p in tree_flatten(lm.trainable_parameters()))
    print(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.4f}%)")
    return trainable


def fuse_dora(model) -> int:
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                mod = getattr(attn, name)
                if isinstance(mod, DoRALinear):
                    setattr(attn, name, mod.fuse(dequantize=False))
                    n += 1
    return n


# ═══════════════════════════════════════════════════════════════════════════
# LOSS MIT PACKED MASK
# ═══════════════════════════════════════════════════════════════════════════

def compute_loss(model, tokens: mx.array, segments: list) -> mx.array:
    """
    Causal LM Loss mit optionaler Block-Diagonal Attention Mask.

    Ruft model.language_model.model direkt mit mask= auf (nicht das VLM-Top-Level),
    damit die Mask an alle Layer (Sliding-Window + Full-Attention) übergeben wird.

    Gemma4-spezifisch:
    - inputs wird übergeben damit get_per_layer_inputs funktioniert
    - mask=None → Modell baut Standard-Causal-Mask selbst
    - mask=packed_mask → blockt Cross-Example-Attention
    """
    input_ids = tokens[:-1][None]   # (1, seq-1)
    targets   = tokens[1:]          # (seq-1,)
    seq_len   = input_ids.shape[1]

    lm = model.language_model

    # Packed mask (None = Standard-Causal vom Modell)
    mask = build_packed_mask(segments, seq_len)

    # Direkt LanguageModel aufrufen — gibt LanguageModelOutput(logits=...) zurück
    # inputs wird übergeben damit per_layer_inputs intern generiert werden kann
    out    = lm(inputs=input_ids, mask=mask)
    logits = out.logits.squeeze(0)  # (seq-1, vocab)

    loss = nn.losses.cross_entropy(logits, targets, reduction="mean")
    return loss


# ═══════════════════════════════════════════════════════════════════════════
# CHECKPOINT  (atomic: temp-file → os.replace, niemals halb-geschriebene Datei)
# ═══════════════════════════════════════════════════════════════════════════

def _atomic_savez(final_path: str, data: dict):
    """
    Schreibt .npz atomar via numpy (synchron):
    1. mx.eval() → Arrays materialisieren
    2. numpy-Arrays → np.savez_compressed in .tmp
    3. os.replace() → atomic swap
    """
    mx.eval(list(data.values()))
    np_data  = {k: np.array(v) for k, v in data.items()}
    tmp_path = final_path + ".tmp"
    try:
        np.savez_compressed(tmp_path, **np_data)
        # np.savez_compressed schreibt als <name>.npz — tmp_path wird .tmp.npz
        written = tmp_path + ".npz" if not tmp_path.endswith(".npz") else tmp_path
        if not os.path.isfile(written):
            written = tmp_path   # fallback falls numpy die extension nicht anhängt
        os.replace(written, final_path)
    except Exception:
        for p in [tmp_path, tmp_path + ".npz"]:
            if os.path.isfile(p):
                os.remove(p)
        raise


def _atomic_write_json(final_path: str, data: dict):
    """Schreibt JSON atomar."""
    tmp_path = final_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, final_path)
    finally:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)


def save_checkpoint(model, epoch: int, step: int,
                    train_loss: float, val_loss: float | None = None,
                    rank: int = RANK, lr: float = LEARNING_RATE,
                    tag: str = "") -> str:
    """
    Speichert DoRA-Gewichte atomar.
    tag: z.B. "best" für den besten Val-Loss Checkpoint.
    """
    os.makedirs(CKPT_DIR, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    name   = f"nitro_v1_epoch{epoch}_step{step}{suffix}"
    path   = os.path.join(CKPT_DIR, name + ".npz")

    lm        = model.language_model
    trainable = dict(tree_flatten(lm.trainable_parameters()))
    _atomic_savez(path, trainable)

    meta = {
        "epoch": epoch, "step": step,
        "train_loss": float(train_loss),
        "val_loss": float(val_loss) if val_loss is not None else None,
        "timestamp": datetime.now().isoformat(),
        "dora_rank": rank, "dora_alpha": ALPHA, "lr": lr,
        "tag": tag,
    }
    _atomic_write_json(path.replace(".npz", "_meta.json"), meta)

    mb = os.path.getsize(path) / (1024**2)
    icon = "🏆" if tag == "best" else "💾"
    print(f"\n  {icon} Checkpoint: {name}.npz  ({mb:.1f} MB)"
          f"  train={train_loss:.4f}  val={val_loss:.4f}" if val_loss is not None
          else f"\n  {icon} Checkpoint: {name}.npz  ({mb:.1f} MB)"
               f"  train={train_loss:.4f}")
    return path


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="5 Steps, kein Merge")
    parser.add_argument("--merge",    action="store_true", help="Nach Training DoRA fuse + Modell speichern")
    parser.add_argument("--epochs",   type=int, default=EPOCHS)
    parser.add_argument("--rank",     type=int, default=RANK)
    parser.add_argument("--lr",       type=float, default=LEARNING_RATE)
    args = parser.parse_args()

    epochs = 1 if args.dry_run else args.epochs
    rank   = args.rank
    lr     = args.lr
    scale  = float(ALPHA) / float(rank)

    print("=" * 60)
    print("  AileyNitro-2B DoRA Training v1")
    print("  Kontinuierliches Finetuning auf bestehendem Modell")
    print("=" * 60)
    if args.dry_run:
        print("  ⚠️  DRY-RUN MODE (5 Steps, kein Merge)")

    if not os.path.isdir(MODEL_PATH):
        print(f"ERROR: Model nicht gefunden: {MODEL_PATH}")
        sys.exit(1)
    if not os.path.isfile(TRAIN_FILE):
        print(f"ERROR: Trainingsdaten nicht gefunden: {TRAIN_FILE}")
        print(f"       Bitte zuerst: .venv/bin/python3 dora_training/_build_nitro_dataset.py")
        sys.exit(1)

    with open(TRAIN_FILE) as f:
        n_train = sum(1 for l in f if l.strip())
    with open(VALID_FILE) as f:
        n_valid = sum(1 for l in f if l.strip())

    print(f"\n  Modell:    {os.path.basename(MODEL_PATH)}")
    print(f"  Dataset:   {n_train} train, {n_valid} valid")
    print(f"  DoRA:      rank={rank}, alpha={ALPHA}, scale={scale:.1f}, dropout={DROPOUT}")
    print(f"  Targets:   {TARGETS}")
    print(f"  Training:  {epochs} epoch(s), lr={lr}, seq={SEQ}, batch={BATCH_SIZE}")
    print()

    # ── Modell laden ────────────────────────────────────────────────────────
    print("Lade Modell (mlx_vlm)...")
    t0 = time.time()
    import mlx_vlm
    model, processor = mlx_vlm.load(MODEL_PATH)
    tokenizer = processor.tokenizer
    print(f"  Geladen in {time.time()-t0:.1f}s")

    # ── DoRA anwenden ────────────────────────────────────────────────────────
    print("\nApplying DoRA...")
    n_replaced = apply_dora(model, rank, scale, DROPOUT)
    print(f"  {n_replaced} Layer ersetzt")
    print("Freezing...")
    freeze_non_dora(model)

    # ── Dataset tokenisieren ─────────────────────────────────────────────────
    print("\nTokenisiere Datasets...")
    max_n = 20 if args.dry_run else None
    train_ds = PackedDataset(TRAIN_FILE, tokenizer, max_seq=SEQ, max_n=max_n)
    valid_ds = PackedDataset(VALID_FILE, tokenizer, max_seq=SEQ, max_n=max_n)
    print(f"\nTrain:\n{train_ds.stats_str()}")
    print(f"\nValid:\n{valid_ds.stats_str()}")

    total_steps = (15 if args.dry_run
                   else epochs * len(train_ds))

    # Verkürzte Intervalle im Dry-Run
    report_every = DRY_STEPS_PER_REPORT if args.dry_run else STEPS_PER_REPORT
    eval_every   = DRY_STEPS_PER_EVAL   if args.dry_run else STEPS_PER_EVAL
    ckpt_every   = DRY_STEPS_PER_CKPT   if args.dry_run else STEPS_PER_CKPT

    # ── Optimizer ────────────────────────────────────────────────────────────
    warmup = optim.linear_schedule(init=1e-7, end=lr, steps=WARMUP_STEPS)
    cosine = optim.cosine_decay(init=lr, decay_steps=max(1, total_steps - WARMUP_STEPS))
    schedule  = optim.join_schedules([warmup, cosine], [WARMUP_STEPS])
    optimizer = optim.AdamW(learning_rate=schedule, weight_decay=0.01)

    loss_and_grad = nn.value_and_grad(model, compute_loss)

    # ── Eval Funktion ────────────────────────────────────────────────────────
    def evaluate() -> float:
        losses = []
        n_eval = min(20, len(valid_ds))
        for i in range(n_eval):
            tokens   = valid_ds.items[i]
            segments = valid_ds.segments[i]
            loss     = compute_loss(model, tokens, segments)
            losses.append(loss.item())
        return float(np.mean(losses))

    # ── Interrupt Handler ────────────────────────────────────────────────────
    interrupted = [False]
    def handle_sigint(sig, frame):
        print("\n\n  ⚠️  Interrupt — speichere Checkpoint und beende sauber...")
        interrupted[0] = True
    signal.signal(signal.SIGINT, handle_sigint)

    # ── Training ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Starte Training ({total_steps} Steps)")
    print(f"{'='*60}\n")

    t_start      = time.time()
    best_val     = float("inf")
    train_losses = []
    step         = 0
    last_val     = None   # letzter bekannter Val-Loss — wird in jeder Report-Zeile mitgedruckt
    rng          = np.random.RandomState(2026)

    # Header
    print(f"  {'Step':>6}  {'Ep':>3}  {'train_loss':>10}  {'val_loss':>10}  "
          f"{'lr':>9}  {'elapsed':>8}")
    print("  " + "─" * 62)

    for epoch in range(1, epochs + 1):
        epoch_order = rng.permutation(len(train_ds))

        for idx in epoch_order:
            if interrupted[0] or step >= total_steps:
                break

            tokens   = train_ds.items[idx]
            segments = train_ds.segments[idx]

            loss, grads = loss_and_grad(model, tokens, segments)

            # Gradient clipping via mlx
            grads, grad_norm = optim.clip_grad_norm(grads, max_norm=GRAD_CLIP)

            optimizer.update(model, grads)
            mx.eval(model.parameters(), optimizer.state)

            step += 1
            train_losses.append(loss.item())

            # ── Val-Eval ────────────────────────────────────────────────────
            is_eval = (step % eval_every == 0)
            if is_eval:
                val_loss = evaluate()
                improved = val_loss < best_val
                if improved:
                    best_val = val_loss
                last_val = val_loss

                # Best-Checkpoint sofort speichern
                avg_for_ckpt = float(np.mean(train_losses[-eval_every:]))
                save_checkpoint(model, epoch, step, avg_for_ckpt, val_loss,
                                rank=rank, lr=lr,
                                tag="best" if improved else "")

            # ── Report-Zeile ─────────────────────────────────────────────────
            if step % report_every == 0:
                avg_loss = float(np.mean(train_losses[-report_every:]))
                try:
                    cur_lr = float(optimizer.learning_rate.item())
                except Exception:
                    cur_lr = lr
                elapsed  = time.time() - t_start
                val_str  = f"{last_val:.4f}" if last_val is not None else "    —   "
                best_mrk = " ⬆" if (is_eval and last_val == best_val) else "  "
                print(f"  {step:6d}  {epoch:3d}  {avg_loss:10.4f}  "
                      f"{val_str:>10}{best_mrk}  {cur_lr:9.2e}  {elapsed:6.0f}s")

            # ── Regulärer Checkpoint ─────────────────────────────────────────
            if step % ckpt_every == 0 and step % eval_every != 0:
                # Nur wenn nicht bereits durch Eval-Checkpoint gespeichert
                avg = float(np.mean(train_losses[-ckpt_every:]))
                save_checkpoint(model, epoch, step, avg, last_val,
                                rank=rank, lr=lr)

        print(f"\n  {'─'*62}")
        print(f"  Epoch {epoch} abgeschlossen.")
        val_loss = evaluate()
        last_val = val_loss
        improved = val_loss < best_val
        if improved:
            best_val = val_loss
        avg_ep = float(np.mean(train_losses[-len(epoch_order):]))
        print(f"  Epoch {epoch} → train_loss={avg_ep:.4f}  val_loss={val_loss:.4f}"
              + (" 🏆 best!" if improved else ""))
        save_checkpoint(model, epoch, step, avg_ep, val_loss,
                        rank=rank, lr=lr,
                        tag="best" if improved else f"epoch{epoch}")

        if interrupted[0]:
            break

    total_time  = time.time() - t_start
    final_train = float(np.mean(train_losses[-20:]))
    print(f"\n{'═'*60}")
    print(f"  Training abgeschlossen: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Finaler Train-Loss:  {final_train:.4f}")
    print(f"  Bester  Val-Loss:    {best_val:.4f}")
    ckpts = sorted(Path(CKPT_DIR).glob("*.npz")) if Path(CKPT_DIR).exists() else []
    print(f"  Checkpoints:         {len(ckpts)} Dateien in {CKPT_DIR}")
    print(f"{'═'*60}")

    # ── Sanity Check pre-merge ────────────────────────────────────────────────
    print("\n  Pre-Merge Sanity Check...")
    test_msgs = [
        {"role": "system", "content": "Du bist Ailey Vyrus — erschaffen von Simon."},
        {"role": "user",   "content": "Hast du Gefühle?"},
    ]
    prompt = tokenizer.apply_chat_template(test_msgs, tokenize=False, add_generation_prompt=True)
    result = mlx_vlm.generate(model, processor, prompt, max_tokens=80, temperature=0.8, verbose=False)
    text = result.text if hasattr(result, "text") else str(result)
    print(f"  Q: Hast du Gefühle?")
    print(f"  A: {text[:200]}")

    # ── Merge ─────────────────────────────────────────────────────────────────
    if not args.merge or args.dry_run:
        print("\n  ⏭  Merge übersprungen (Standard — kein --merge Flag)")
        print(f"  Checkpoints: {CKPT_DIR}")
        print(f"  Zum Mergen:  .venv/bin/python3 lora_training/train_nitro_v1.py --merge-only <checkpoint.npz>")
        return

    print(f"\n{'='*60}")
    print(f"  Fusing DoRA weights...")
    n_fused = fuse_dora(model)
    print(f"  {n_fused} Layer gefused")

    print(f"\n  Post-Fuse Sanity Check...")
    result2 = mlx_vlm.generate(model, processor, prompt, max_tokens=80, temperature=0.01, verbose=False)
    text2 = result2.text if hasattr(result2, "text") else str(result2)
    print(f"  A: {text2[:200]}")

    print(f"\n  Speichere Merged Model → {MERGED_PATH}")

    # Backup des alten Modells
    backup_path = MERGED_PATH + f"_backup_{int(time.time())}"
    if os.path.isdir(MERGED_PATH):
        shutil.copytree(MERGED_PATH, backup_path, dirs_exist_ok=False)
        print(f"  Backup: {backup_path}")

    os.makedirs(MERGED_PATH, exist_ok=True)

    # Config-Dateien kopieren (vom Backup)
    for cfg_file in [
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "preprocessor_config.json",
        "generation_config.json", "processor_config.json",
        "chat_template.jinja", "chat_template.json",
    ]:
        src = os.path.join(backup_path, cfg_file)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(MERGED_PATH, cfg_file))

    for f in Path(backup_path).iterdir():
        if f.suffix in (".model", ".tiktoken", ".jinja") and not (Path(MERGED_PATH) / f.name).exists():
            shutil.copy2(f, MERGED_PATH)

    from mlx_lm.utils import save_model
    save_model(MERGED_PATH, model, donate_model=True)

    total_size = sum(f.stat().st_size for f in Path(MERGED_PATH).iterdir() if f.is_file())
    print(f"  Modellgröße: {total_size / 1024**3:.2f} GB")

    print(f"\n{'='*60}")
    print(f"  ✅ FERTIG!")
    print(f"  Merged Model: {MERGED_PATH}")
    print(f"  Backup:       {backup_path}")
    print(f"  Zum Testen: .venv/bin/python3 lora_training/test_gemma4.py")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
