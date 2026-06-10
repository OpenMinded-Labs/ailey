#!/usr/bin/env python3
"""
Merge Ministral DoRA Checkpoint → Modell (atomic save).

v3: Step 1350 (Ep2), rank=32, alpha=64 — der Best-by-Feel Checkpoint
aus dem systematischen Vergleich (test_checkpoints_v3.py).
Knackig, Ailey-Vibe, keine Overfit-Echoes.

Das Ergebnis ist **Ailey-14B** (Hauptmodell, Persona).
CodeAiley ist separat (Qwen-Coder).
"""
import os, sys, json, time, shutil
from pathlib import Path
from datetime import datetime

import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten, tree_unflatten

PROJECT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT, "mlx_models", "Ministral-3-14B-Reasoning-5bit")
CKPT_PATH  = os.path.join(PROJECT, "lora_training", "checkpoints_ministral",
                           "ministral_epoch2_step1350.npz")

# DoRA config (must match training v3)
RANK    = 32
ALPHA   = 64
SCALE   = ALPHA / RANK  # 2.0
DROPOUT = 0.0  # no dropout at merge time
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]


def get_dim_map(config_path):
    with open(config_path) as f:
        cfg = json.load(f)
    tc = cfg.get("text_config", cfg)
    h     = tc["hidden_size"]
    inter = tc["intermediate_size"]
    nh    = tc["num_attention_heads"]
    nkv   = tc["num_key_value_heads"]
    hd    = tc["head_dim"]
    return {
        "q_proj":    (h, nh * hd),
        "k_proj":    (h, nkv * hd),
        "v_proj":    (h, nkv * hd),
        "o_proj":    (nh * hd, h),
        "gate_proj": (h, inter),
        "up_proj":   (h, inter),
        "down_proj": (inter, h),
    }


def apply_dora(model, dim_map):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            container = layer.self_attn if name in {"q_proj","k_proj","v_proj","o_proj"} else getattr(layer, "mlp", None)
            if container is None or not hasattr(container, name):
                continue
            orig = getattr(container, name)
            in_d, out_d = dim_map[name]
            dora = DoRALinear(input_dims=in_d, output_dims=out_d,
                              r=RANK, dropout=DROPOUT, scale=SCALE)
            dora.set_linear(orig)
            setattr(container, name, dora)
            n += 1
    return n


def fuse_dora(model):
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        for name in TARGETS:
            container = layer.self_attn if name in {"q_proj","k_proj","v_proj","o_proj"} else getattr(layer, "mlp", None)
            if container is None or not hasattr(container, name):
                continue
            mod = getattr(container, name)
            if isinstance(mod, DoRALinear):
                setattr(container, name, mod.fuse(dequantize=False))
                n += 1
    return n


def main():
    print("=" * 64)
    print("  🔧 Merge DoRA Checkpoint → Ailey-14B")
    print("=" * 64)

    assert os.path.isdir(MODEL_PATH), f"Model not found: {MODEL_PATH}"
    assert os.path.isfile(CKPT_PATH), f"Checkpoint not found: {CKPT_PATH}"

    # Read checkpoint meta
    meta_path = CKPT_PATH.replace(".npz", "_meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"\n  Checkpoint: epoch={meta['epoch']}, step={meta['step']}")
        print(f"  train_loss={meta['train_loss']:.4f}, val_loss={meta['val_loss']:.4f}")
    print(f"  File: {os.path.basename(CKPT_PATH)}")

    dim_map = get_dim_map(os.path.join(MODEL_PATH, "config.json"))

    # 1. Load model
    print("\n  Loading Ministral...")
    t0 = time.time()
    import mlx_lm
    model, tok = mlx_lm.load(MODEL_PATH)
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # 2. Apply DoRA structure
    print(f"\n  Applying DoRA structure (rank={RANK})...")
    n_applied = apply_dora(model, dim_map)
    print(f"  {n_applied} DoRALinear layers created")

    # 3. Load checkpoint weights
    print(f"\n  Loading checkpoint weights...")
    ckpt_weights = dict(mx.load(CKPT_PATH))
    print(f"  {len(ckpt_weights)} weight tensors in checkpoint")

    # Map checkpoint keys to model
    lm = model.language_model
    lm_params = dict(tree_flatten(lm.parameters()))

    loaded = 0
    missing = []
    for key, val in ckpt_weights.items():
        if key in lm_params:
            # Verify shape match
            if lm_params[key].shape == val.shape:
                loaded += 1
            else:
                print(f"  ⚠️ Shape mismatch: {key} — ckpt={val.shape} vs model={lm_params[key].shape}")
        else:
            missing.append(key)

    if missing:
        print(f"  ⚠️ {len(missing)} keys in checkpoint not in model:")
        for k in missing[:5]:
            print(f"      {k}")

    print(f"  Loading {loaded} tensors into model...")
    lm.load_weights(list(ckpt_weights.items()), strict=False)
    mx.eval(lm.parameters())
    print(f"  ✅ Weights loaded")

    # 4. Quick sanity check
    print(f"\n  🧪 Sanity check...")
    for q in ["Wer bist du?", "Schreib mir einen Haiku über Code."]:
        prompt = f"<s>[INST]{q}[/INST]"
        result = mlx_lm.generate(model, tok, prompt=prompt, max_tokens=120, verbose=False)
        print(f"  Q: {q}")
        print(f"  A: {result[:200]}\n")

    # 5. Fuse DoRA
    print(f"  Fusing DoRA → QuantizedLinear...")
    n_fused = fuse_dora(model)
    print(f"  {n_fused} layers fused")

    # 6. Atomic save
    tmp_save = MODEL_PATH + "_tmp_merge"
    backup_path = MODEL_PATH + "_pre_dora_backup"

    if os.path.exists(tmp_save):
        shutil.rmtree(tmp_save)
    os.makedirs(tmp_save)

    # Copy non-weight files
    print(f"\n  Saving to temp dir...")
    for f in Path(MODEL_PATH).iterdir():
        if f.is_file() and not f.name.startswith("model") and f.suffix != ".safetensors":
            shutil.copy2(f, tmp_save)

    from mlx_lm.utils import save_model
    save_model(tmp_save, model, donate_model=True)

    # Verify
    tmp_size = sum(f.stat().st_size for f in Path(tmp_save).iterdir() if f.is_file())
    orig_size = sum(f.stat().st_size for f in Path(MODEL_PATH).iterdir() if f.is_file())
    print(f"  Temp: {tmp_size/1024**3:.2f} GB  (original: {orig_size/1024**3:.2f} GB)")

    if tmp_size < orig_size * 0.5:
        print(f"  ❌ Temp save too small — aborting! Model untouched.")
        print(f"  Temp dir: {tmp_save}")
        return

    # Atomic swap
    if os.path.exists(backup_path):
        shutil.rmtree(backup_path)

    print(f"  Swapping: original → backup, temp → final...")
    os.rename(MODEL_PATH, backup_path)
    os.rename(tmp_save, MODEL_PATH)

    # Update config
    cfg_path = os.path.join(MODEL_PATH, "config.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["ailey_dora"] = {
            "version": "3.0",
            "name": "Ailey-14B-v3",
            "base": "Ministral-3-14B-Reasoning-5bit",
            "type": "persona_dora",
            "dora_rank": RANK,
            "dora_alpha": ALPHA,
            "epochs_trained": 2,
            "steps": meta.get("step", 1350),
            "final_train_loss": meta.get("train_loss", 0),
            "best_val_loss": meta.get("val_loss", 0),
            "checkpoint": os.path.basename(CKPT_PATH),
            "dataset": "clean_train_v3.jsonl (1693 pairs, runtime-aligned)",
            "selection_method": "by_feel (systematic test_checkpoints_v3.py)",
            "timestamp": datetime.now().isoformat(),
        }
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)

    final_size = sum(f.stat().st_size for f in Path(MODEL_PATH).iterdir() if f.is_file())

    print(f"\n{'='*64}")
    print(f"  ✅ Ailey-14B-v3 merged!")
    print(f"  Model: {MODEL_PATH}")
    print(f"  Size:  {final_size/1024**3:.2f} GB")
    print(f"  Backup: {backup_path}")
    print(f"  (Delete backup once verified)")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
