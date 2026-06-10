#!/usr/bin/env python3
"""
merge_nitro_checkpoint.py
─────────────────────────
Lädt einen DoRA-Checkpoint, merged ihn in das Basismodell und speichert
das Ergebnis in-place als neues AileyNitro-2B.

Usage:
    .venv/bin/python3 lora_training/merge_nitro_checkpoint.py \
        --ckpt lora_training/checkpoints_nitro_v1/nitro_v1_epoch2_step5600_best.npz

    Optional:
        --hf-upload   # Push zu HuggingFace nach dem Merge
        --hf-repo     # z.B. CaptainShagggy/AileyNitro-2B (default)
        --hf-tag      # z.B. v1.1 (default: auto aus Checkpoint-Name)
"""

import os, sys, shutil, time, argparse
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
CKPT_DIR     = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints_nitro_v1")

RANK    = 16
ALPHA   = 32
SCALE   = float(ALPHA) / float(RANK)
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


def apply_dora(model, rank: int, scale: float) -> int:
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name):
                orig = getattr(attn, name)
                setattr(attn, name, DoRALinear.from_base(orig, r=rank, dropout=0.0, scale=scale))
                n += 1
    return n


def load_checkpoint(model, ckpt_path: str) -> int:
    import mlx.core as mx
    from mlx.utils import tree_unflatten
    weights = dict(mx.load(ckpt_path))
    nested  = tree_unflatten(list(weights.items()))
    model.language_model.update(nested)
    mx.eval(model.language_model.parameters())
    return len(weights)


def fuse_dora(model) -> int:
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n  = 0
    for layer in lm.model.layers:
        attn = layer.self_attn
        for name in TARGETS:
            if hasattr(attn, name) and isinstance(getattr(attn, name), DoRALinear):
                setattr(attn, name, getattr(attn, name).fuse(dequantize=False))
                n += 1
    return n


def main():
    parser = argparse.ArgumentParser(description="DoRA Checkpoint → Merged AileyNitro-2B")
    parser.add_argument("--ckpt",      required=True, help="Pfad zum .npz Checkpoint")
    parser.add_argument("--hf-upload", action="store_true", help="Nach HuggingFace pushen")
    parser.add_argument("--hf-repo",   default="CaptainShagggy/AileyNitro-2B", help="HF Repo ID")
    parser.add_argument("--hf-tag",    default=None, help="Version-Tag (z.B. v1.1)")
    args = parser.parse_args()

    ckpt_path = args.ckpt if os.path.isabs(args.ckpt) else os.path.join(PROJECT_ROOT, args.ckpt)
    if not os.path.isfile(ckpt_path):
        # Kurzer Name → im CKPT_DIR suchen
        ckpt_path = os.path.join(CKPT_DIR, os.path.basename(args.ckpt))
    if not os.path.isfile(ckpt_path):
        print(f"❌ Checkpoint nicht gefunden: {args.ckpt}")
        sys.exit(1)

    ckpt_name = Path(ckpt_path).stem
    hf_tag    = args.hf_tag or ("v1." + ckpt_name.split("step")[-1].split("_")[0] if "step" in ckpt_name else "v1.0")

    print("=" * 60)
    print("  AileyNitro-2B — DoRA Merge")
    print("=" * 60)
    print(f"  Checkpoint: {ckpt_name}")
    print(f"  Modell:     {MODEL_PATH}")
    print(f"  HF-Tag:     {hf_tag}")
    print()

    # ── 1. Modell laden ───────────────────────────────────────────────────────
    print("  [1/5] Lade Basismodell...")
    import mlx_vlm
    t0 = time.time()
    model, processor = mlx_vlm.load(MODEL_PATH)
    print(f"        Geladen in {time.time()-t0:.1f}s")

    # ── 2. DoRA anwenden ──────────────────────────────────────────────────────
    print(f"  [2/5] Wende DoRA an (Rank={RANK}, Scale={SCALE})...")
    n_layers = apply_dora(model, RANK, SCALE)
    print(f"        {n_layers} Layer gewrappt")

    # ── 3. Checkpoint laden ───────────────────────────────────────────────────
    print(f"  [3/5] Lade Checkpoint-Gewichte...")
    n_weights = load_checkpoint(model, ckpt_path)
    print(f"        {n_weights} Parameter geladen")

    # ── 4+5. Fuse + Speichern ─────────────────────────────────────────────────
    print(f"  [4/5] Fuse DoRA → Basisgewichte...")
    n_fused = fuse_dora(model)
    print(f"        {n_fused} Layer gefused")

    # Backup
    backup_path = MODEL_PATH + f"_backup_{int(time.time())}"
    print(f"\n  Backup: {backup_path}")
    shutil.copytree(MODEL_PATH, backup_path, dirs_exist_ok=False)

    # Speichern
    print(f"  Speichere → {MODEL_PATH}")
    os.makedirs(MODEL_PATH, exist_ok=True)
    for cfg_file in [
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "preprocessor_config.json",
        "generation_config.json", "processor_config.json",
        "chat_template.jinja", "chat_template.json",
    ]:
        src = os.path.join(backup_path, cfg_file)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(MODEL_PATH, cfg_file))

    for f in Path(backup_path).iterdir():
        if f.suffix in (".model", ".tiktoken", ".jinja") and not (Path(MODEL_PATH) / f.name).exists():
            shutil.copy2(f, MODEL_PATH)

    from mlx_lm.utils import save_model
    save_model(MODEL_PATH, model, donate_model=True)

    total_size = sum(f.stat().st_size for f in Path(MODEL_PATH).iterdir() if f.is_file())
    print(f"  Modellgröße: {total_size / 1024**3:.2f} GB")
    print(f"\n  ✅ Merge abgeschlossen → {MODEL_PATH}")

    # ── HuggingFace Upload ────────────────────────────────────────────────────
    if args.hf_upload:
        print(f"\n  HuggingFace Upload → {args.hf_repo} (tag: {hf_tag})...")
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            api.create_tag(repo_id=args.hf_repo, tag=hf_tag, exist_ok=True)
            api.upload_folder(
                folder_path=MODEL_PATH,
                repo_id=args.hf_repo,
                repo_type="model",
                commit_message=f"AileyNitro-2B {hf_tag} — DoRA step5600 merged",
            )
            print(f"  ✅ Upload abgeschlossen: https://huggingface.co/{args.hf_repo}")
        except Exception as e:
            print(f"  ❌ HF Upload fehlgeschlagen: {e}")
            print(f"     Manuell: huggingface-cli upload {args.hf_repo} {MODEL_PATH} .")

    print()


if __name__ == "__main__":
    main()
