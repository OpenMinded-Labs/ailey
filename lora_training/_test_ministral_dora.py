#!/usr/bin/env python3
"""Quick test: DoRA + value_and_grad on Ministral 5-bit with correct dims."""
import mlx.core as mx
import mlx.nn as nn
import mlx_lm
from mlx_lm.tuner.dora import DoRALinear
import json, time

print("Loading Ministral...")
t0 = time.time()
model, tok = mlx_lm.load("mlx_models/Ministral-3-14B-Reasoning-5bit")
print(f"Loaded in {time.time()-t0:.1f}s")

with open("mlx_models/Ministral-3-14B-Reasoning-5bit/config.json") as f:
    cfg = json.load(f)
tc = cfg.get("text_config", cfg)
hidden = tc["hidden_size"]
inter = tc["intermediate_size"]
n_heads = tc["num_attention_heads"]
n_kv = tc["num_key_value_heads"]
head_dim = tc["head_dim"]

DIM_MAP = {
    "q_proj": (hidden, n_heads * head_dim),
    "k_proj": (hidden, n_kv * head_dim),
    "v_proj": (hidden, n_kv * head_dim),
    "o_proj": (n_heads * head_dim, hidden),
    "gate_proj": (hidden, inter),
    "up_proj": (hidden, inter),
    "down_proj": (inter, hidden),
}

RANK = 16
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
ATTN_SET = set(TARGETS)

lm = model.language_model
# Apply to first 2 layers only (test)
n = 0
for layer in lm.model.layers:
    for name in TARGETS:
        if hasattr(layer.self_attn, name):
            orig = getattr(layer.self_attn, name)
            in_d, out_d = DIM_MAP[name]
            dora = DoRALinear(input_dims=in_d, output_dims=out_d, r=RANK, dropout=0.05, scale=2.0)
            dora.set_linear(orig)
            setattr(layer.self_attn, name, dora)
            n += 1
print(f"Applied DoRA to {n} layers (ALL 40 layers, attn-only)")

lm.freeze()
lm.unfreeze(keys=["lora_a", "lora_b", "m"])

from mlx.utils import tree_flatten
trn = sum(p.size for _, p in tree_flatten(lm.trainable_parameters()))
print(f"Trainable: {trn:,}")


def compute_loss(language_model, tokens):
    out = language_model(tokens[:-1][None])
    # Ministral's language_model returns raw tensor or object with .logits
    logits = out.logits if hasattr(out, "logits") else out
    logits = logits.squeeze(0)
    return nn.losses.cross_entropy(logits, tokens[1:], reduction="mean")


loss_and_grad = nn.value_and_grad(lm, compute_loss)

test_text = "<s>[INST]Wer bist du?[/INST]Ich bin Ailey, gebaut von Simon.</s>"
tokens = mx.array(tok.encode(test_text))
print(f"Test tokens: {tokens.shape}")

print("Computing loss + grad...")
t1 = time.time()
loss, grads = loss_and_grad(lm, tokens)
mx.eval(loss, grads)
print(f"Loss: {loss.item():.4f}, time: {time.time()-t1:.1f}s")
print("OK - value_and_grad works on Ministral")

# Test fuse
print("\nTesting fuse...")
n_fused = 0
for layer in lm.model.layers:
    for name in TARGETS:
        if hasattr(layer.self_attn, name):
            mod = getattr(layer.self_attn, name)
            if isinstance(mod, DoRALinear):
                fused = mod.fuse(dequantize=False)
                setattr(layer.self_attn, name, fused)
                n_fused += 1
print(f"Fused {n_fused} layers")

# Test save
print("\nTesting save (to /tmp)...")
import tempfile, shutil
tmp_dir = tempfile.mkdtemp(prefix="ministral_test_")
from mlx_lm.utils import save_model
save_model(tmp_dir, model, donate_model=False)
import os
total = sum(os.path.getsize(os.path.join(tmp_dir, f)) for f in os.listdir(tmp_dir) if os.path.isfile(os.path.join(tmp_dir, f)))
print(f"Saved to {tmp_dir}: {total/1024**3:.2f} GB")
shutil.rmtree(tmp_dir)
print("Cleaned up tmp dir")

print("\nALL TESTS PASSED")
