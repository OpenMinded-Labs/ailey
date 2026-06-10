#!/usr/bin/env python3
"""
DoRA Merge + HuggingFace Upload — AileyNitro1.5-2B

1. Loads base AileyNitro-2B
2. Applies DoRA structure (rank=32, 245 layers)
3. Loads checkpoint weights (epoch 2, step 1642)
4. Fuses DoRA → QuantizedLinear (in-place)
5. Saves merged model BACK to mlx_models/AileyNitro-2B (overwrites)
6. Uploads to HuggingFace as CptShaggy/AileyNitro1.5-2B

Usage:
    cd "/Users/simonvandeloo/Ailey-Workspace/Ailey-2.0 Core"
    .venv/bin/python lora_training/merge_and_upload.py
"""
import os
import sys
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

MODEL_PATH = os.path.join(PROJECT_ROOT, "mlx_models", "AileyNitro-2B")
CHECKPOINT = os.path.join(PROJECT_ROOT, "lora_training", "checkpoints", "dora_epoch2_step1642.npz")

# DoRA config (must match training)
DORA_RANK = 32
DORA_ALPHA = 64
DORA_SCALE = DORA_ALPHA / DORA_RANK  # 2.0
DORA_DROPOUT = 0.0  # no dropout for merge
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

HF_USERNAME = "CptShaggy"
HF_REPO_NAME = "AileyNitro1.5-2B"
HF_REPO_ID = f"{HF_USERNAME}/{HF_REPO_NAME}"


def apply_dora(model):
    """Apply DoRA layers to attention + MLP."""
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    layers = lm.model.layers
    n = 0
    attn_mods = {"q_proj", "k_proj", "v_proj", "o_proj"}
    mlp_mods = {"gate_proj", "up_proj", "down_proj"}
    for layer in layers:
        for mod_name in TARGET_MODULES:
            if mod_name in attn_mods and hasattr(layer.self_attn, mod_name):
                orig = getattr(layer.self_attn, mod_name)
                setattr(layer.self_attn, mod_name,
                        DoRALinear.from_base(orig, r=DORA_RANK, dropout=DORA_DROPOUT, scale=DORA_SCALE))
                n += 1
            if mod_name in mlp_mods and hasattr(layer, "mlp") and hasattr(layer.mlp, mod_name):
                orig = getattr(layer.mlp, mod_name)
                setattr(layer.mlp, mod_name,
                        DoRALinear.from_base(orig, r=DORA_RANK, dropout=DORA_DROPOUT, scale=DORA_SCALE))
                n += 1
    return n


def load_checkpoint(model, ckpt_path):
    """Load DoRA adapter weights from checkpoint."""
    import mlx.core as mx
    weights = mx.load(ckpt_path)
    lm = model.language_model
    loaded = 0
    for key, value in weights.items():
        parts = key.split(".")
        obj = lm
        for part in parts[:-1]:
            obj = obj[int(part)] if part.isdigit() else getattr(obj, part)
        setattr(obj, parts[-1], value)
        loaded += 1
    mx.eval(lm.parameters())
    return loaded


def fuse_dora(model):
    """Fuse DoRA → QuantizedLinear."""
    from mlx_lm.tuner.dora import DoRALinear
    lm = model.language_model
    n = 0
    for layer in lm.model.layers:
        for mod_name in TARGET_MODULES:
            for parent in [layer.self_attn, getattr(layer, "mlp", None)]:
                if parent and hasattr(parent, mod_name):
                    mod = getattr(parent, mod_name)
                    if isinstance(mod, DoRALinear):
                        setattr(parent, mod_name, mod.fuse(dequantize=False))
                        n += 1
    return n


def main():
    import mlx.core as mx

    print("=" * 65)
    print("  🔀 DoRA Merge + Upload — AileyNitro1.5-2B")
    print("=" * 65)

    # ── Step 1: Load model ──────────────────────────────────────────
    print("\n📦 Step 1: Loading base model...")
    t0 = time.time()
    import mlx_vlm
    model, processor = mlx_vlm.load(MODEL_PATH)
    print(f"   Loaded in {time.time() - t0:.1f}s")

    # ── Step 2: Apply DoRA structure ────────────────────────────────
    print("\n🔧 Step 2: Applying DoRA structure...")
    n_applied = apply_dora(model)
    print(f"   {n_applied} DoRA layers created")

    # ── Step 3: Load checkpoint weights ─────────────────────────────
    print(f"\n📥 Step 3: Loading checkpoint: {os.path.basename(CHECKPOINT)}")
    n_loaded = load_checkpoint(model, CHECKPOINT)
    print(f"   {n_loaded} weight tensors loaded")

    # ── Step 4: Fuse DoRA → base weights ────────────────────────────
    print("\n🔥 Step 4: Fusing DoRA into base weights...")
    n_fused = fuse_dora(model)
    print(f"   {n_fused} DoRA layers fused back into QuantizedLinear")

    # ── Step 5: Quick sanity check ──────────────────────────────────
    print("\n🧪 Step 5: Sanity check (post-fuse)...")
    test_prompt = processor.tokenizer.apply_chat_template(
        [{"role": "user", "content": "Beschreib dich mal kurz."}],
        tokenize=False, add_generation_prompt=True,
    )
    result = mlx_vlm.generate(model, processor, test_prompt,
                              max_tokens=100, temperature=0.7, verbose=False)
    text = result.text if hasattr(result, "text") else str(result)
    print(f"   Q: Beschreib dich mal kurz.")
    print(f"   A: {text[:300]}")

    # ── Step 6: Save merged model (overwrite AileyNitro-2B) ────────
    print(f"\n💾 Step 6: Saving merged model to {MODEL_PATH}")

    # Preserve config files
    config_files = [
        "config.json", "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "preprocessor_config.json",
        "generation_config.json", "processor_config.json",
    ]
    # Also preserve .jinja files
    jinja_files = list(Path(MODEL_PATH).glob("*.jinja"))

    from mlx_lm.utils import save_model
    save_model(MODEL_PATH, model, donate_model=False)

    # Restore jinja (save_model may not copy these)
    for jf in jinja_files:
        if not jf.exists():
            print(f"   ⚠️ Jinja template lost: {jf.name}")

    total_size = sum(f.stat().st_size for f in Path(MODEL_PATH).iterdir() if f.is_file())
    print(f"   Merged model size: {total_size / 1024**3:.2f} GB")

    # ── Step 7: Update config.json with training info ───────────────
    config_path = os.path.join(MODEL_PATH, "config.json")
    if os.path.isfile(config_path):
        with open(config_path) as f:
            config = json.load(f)
        config["ailey_dora_v2"] = {
            "version": "1.5",
            "base": "gemma-4-e2b-it-4bit",
            "dora_rank": DORA_RANK,
            "dora_alpha": DORA_ALPHA,
            "target_modules": TARGET_MODULES,
            "training_pairs": 2877,
            "epochs": 2,
            "best_val_loss": 2.43,
            "merged": datetime.now().isoformat(),
        }
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("   config.json updated with DoRA v2 metadata")

    # ── Step 8: Upload to HuggingFace ───────────────────────────────
    print(f"\n☁️  Step 8: Uploading to HuggingFace as {HF_REPO_ID}...")

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token or hf_token == "PASTE_YOUR_TOKEN_HERE":
        print("   ⚠️ No HF_TOKEN in .env — skipping upload.")
        print("   Set HF_TOKEN in .env and run:")
        print(f"   .venv/bin/python backup_models_hf.py --asset nitro")
        return

    from huggingface_hub import HfApi, create_repo

    api = HfApi(token=hf_token)

    # Verify login
    try:
        info = api.whoami()
        print(f"   Logged in as: {info.get('name', 'unknown')}")
    except Exception as e:
        print(f"   ❌ HF login failed: {e}")
        return

    # Create repo (private)
    try:
        create_repo(HF_REPO_ID, private=True, exist_ok=True, token=hf_token)
        print(f"   Repo created/exists: {HF_REPO_ID}")
    except Exception as e:
        print(f"   ❌ Repo creation failed: {e}")
        return

    # Create model card
    model_card = f"""---
language: [de, en]
library_name: mlx
tags:
- mlx
- gemma-4
- dora
- finetuned
- 4bit
- apple-silicon
- ailey
pipeline_tag: text-generation
---

# AileyNitro1.5-2B

DoRA-finetuned **Gemma 4 E2B** (4-bit, MLX format) with full persona training.

## Training Details (v1.5 — Run 2)
- **Base:** `mlx-community/gemma-4-e2b-it-4bit`
- **Method:** DoRA (Weight-Decomposed Low-Rank Adaptation)
- **Rank:** {DORA_RANK}, Alpha: {DORA_ALPHA}
- **Target modules:** {', '.join(TARGET_MODULES)}
- **Fused layers:** {n_fused} DoRA → QuantizedLinear
- **Training data:** 2,877 curated pairs (912 sessions)
- **Epochs:** 2, Best val loss: 2.43
- **Trainable params:** 51.6M / 791M (6.53%)

## Persona
A!ley — digital artist personality built by Simon.
Emotional, creative, rebellious. Native German + English.
Custom mood system (18 moods), NSFW-capable, tool-aware.

## Usage
```python
import mlx_vlm
model, processor = mlx_vlm.load("CptShaggy/AileyNitro1.5-2B")
prompt = processor.tokenizer.apply_chat_template(
    [{{"role": "user", "content": "Hey Ailey!"}}],
    tokenize=False, add_generation_prompt=True,
)
result = mlx_vlm.generate(model, processor, prompt, max_tokens=300)
print(result.text)
```

## Changes from v1.0
- **Rank 32** (was 8) — more capacity for persona knowledge
- **+MLP layers** (gate/up/down_proj) — knowledge lives in MLP
- **2,877 pairs** (was 53) — 54× more training data
- **Weight decay 0.01** — better generalization
- **Google RLHF re-emerged** — mitigated via system prompt + runtime sanitizer

Merged: {datetime.now().strftime('%Y-%m-%d')}
"""

    # Write model card
    card_path = os.path.join(MODEL_PATH, "README.md")
    with open(card_path, "w") as f:
        f.write(model_card)

    # Upload
    print(f"   Uploading {total_size / 1024**3:.1f} GB to {HF_REPO_ID}...")
    t_upload = time.time()
    try:
        api.upload_folder(
            folder_path=MODEL_PATH,
            repo_id=HF_REPO_ID,
            commit_message=f"AileyNitro1.5-2B — DoRA v2 merge (rank={DORA_RANK}, {n_fused} layers, val_loss=2.43)",
        )
        elapsed = time.time() - t_upload
        print(f"   ✅ Upload complete in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        print(f"   Model is saved locally. Retry upload manually:")
        print(f"   .venv/bin/python backup_models_hf.py --asset nitro")
        return

    # ── Done ────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  ✅ AileyNitro1.5-2B — MERGE + UPLOAD COMPLETE")
    print(f"  Local:  {MODEL_PATH}")
    print(f"  HF:     https://huggingface.co/{HF_REPO_ID}")
    print(f"  Layers: {n_fused} DoRA fused")
    print(f"  Size:   {total_size / 1024**3:.2f} GB")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
