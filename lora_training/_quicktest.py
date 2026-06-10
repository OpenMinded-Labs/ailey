#!/usr/bin/env python3
"""Quick smoke test: can we load model + generate?"""
import sys, time
sys.path.insert(0, ".")

print("Loading mlx_lm...")
import mlx_lm
from mlx_lm.sample_utils import make_sampler

MODEL = "mlx_models/Ministral-3-14B-Reasoning-5bit"
print(f"Loading {MODEL}...")
t0 = time.time()
model, tok = mlx_lm.load(MODEL)
print(f"  Loaded in {time.time()-t0:.1f}s")

prompt = "<s>[SYSTEM_PROMPT]Du bist Ailey.[/SYSTEM_PROMPT][INST]Hi![/INST]"
sampler = make_sampler(temp=0.7, top_p=0.9)
print("Generating...")
t0 = time.time()
result = mlx_lm.generate(model, tok, prompt=prompt, max_tokens=80, sampler=sampler, verbose=False)
print(f"  Done in {time.time()-t0:.1f}s")
print(f"  Result: {result}")
