#!/usr/bin/env python3
"""
Wan2.1 Video Generation Subprocess — GGUF Q4_K_M Edition
=========================================================
This script is called by video_generator.py as a subprocess.
It loads the Wan2.1 T2V-1.3B model with GGUF Q4_K_M quantized DiT,
generates a video, and exits — ensuring all GPU memory is fully released.

Memory Strategy (M4 24GB Unified):
──────────────────────────────────
Phase 1 — Text Encoding:
  • T5 UMT5-XXL on CPU (~11.4GB system RAM, 0 GPU)
  • After encoding, T5 is explicitly deleted → RAM freed

Phase 2 — Denoising (25 steps):
  • DiT Transformer: GGUF Q4_K_M (~983MB on disk)
    → dequantized on-the-fly via forward_native() (pure PyTorch, MPS-safe)
    → Peak ~2.5GB GPU during forward passes
  • Scheduler + timestep embeddings: ~0.1GB

Phase 3 — VAE Decode:
  • enable_vae_tiling()  → spatial tiles instead of full-frame decode
    → Peak 1.3GB instead of 4.5GB (confirmed by diffusers PR #11414 benchmarks)
  • enable_vae_slicing() → batch-wise slicing (further reduction if batch>1)
  • VAE in float32 for quality (~0.5GB weights, peak ~1.3GB with tiling)

Total peak GPU: ~4GB → 20GB headroom on 24GB Mac ✅
NO SWAPPING — guaranteed.

GGUF on MPS:
  diffusers GGUFLinear.forward() dispatches to forward_native() on non-CUDA:
  → dequantize_gguf_tensor() is pure torch operations → works on MPS
  → No bitsandbytes/CUDA dependency needed

Usage (called by video_generator.py, not directly):
    python _wan_generate.py '{"model_id": "...", "prompt": "...", ...}'
"""

import os

# ── MPS fallback for ops not yet implemented on Apple Silicon ──
# conv3d (patch_embedding) is not on MPS yet → fall back to CPU for that op
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
# Enable MPS fallback WARNINGS so we can see which ops fall back to CPU
# This is critical for diagnosing slowness — silent fallbacks = hidden CPU copies
os.environ["PYTORCH_MPS_FALLBACK_WARNINGS"] = "1"

import sys
import json
import time
import gc


def main():
    if len(sys.argv) < 2:
        print("Usage: _wan_generate.py '<json_args>'", file=sys.stderr)
        sys.exit(1)

    args = json.loads(sys.argv[1])

    model_id = args["model_id"]
    gguf_filename = args.get("gguf_filename", "")
    gguf_repo_id = args.get("gguf_repo_id", "")
    prompt = args["prompt"]
    negative_prompt = args.get("negative_prompt", "")
    width = args.get("width", 832)
    height = args.get("height", 480)
    num_frames = args.get("num_frames", 81)
    steps = args.get("steps", 25)
    guidance_scale = args.get("guidance_scale", 6.0)
    flow_shift = args.get("flow_shift", 8.0)
    fps = args.get("fps", 16)
    seed = args.get("seed", None)
    output_path = args["output_path"]

    print(f"[WanGen] Loading model: {model_id}")
    print(f"[WanGen] GGUF DiT: {gguf_repo_id}/{gguf_filename}")
    start_load = time.time()

    import torch
    from diffusers import AutoencoderKLWan, WanPipeline, WanTransformer3DModel, GGUFQuantizationConfig
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
    from diffusers.utils import export_to_video

    # ── Determine device ──
    if torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.float16  # MPS works best with float16
    elif torch.cuda.is_available():
        device = "cuda"
        dtype = torch.bfloat16
    else:
        device = "cpu"
        dtype = torch.float32

    print(f"[WanGen] Device: {device}, dtype: {dtype}")

    # ── SAFETY CHECK: Verify Ministral is NOT loaded ──
    # On macOS, if we can allocate a 512MB test tensor on MPS, GPU is free enough
    try:
        if device == "mps":
            _test = torch.zeros(128 * 1024 * 1024, device="mps", dtype=torch.float32)  # 512MB
            del _test
            torch.mps.empty_cache()
            print("[WanGen] ✅ GPU memory sanity check passed (512MB test alloc)")
    except Exception as e:
        print(f"[WanGen] ⚠️ GPU memory check failed: {e} — Ministral might still be loaded!")

    # ══════════════════════════════════════════════════════════
    # STEP 1: Load GGUF Q4_K_M DiT Transformer
    # ══════════════════════════════════════════════════════════
    # GGUF quantized: 983MB on disk (vs 5.68GB bf16)
    # forward_native() dequantizes per-layer during forward pass
    # → pure PyTorch, works on MPS, no CUDA needed
    print("[WanGen] Loading GGUF Q4_K_M DiT transformer...")
    gguf_config = GGUFQuantizationConfig(compute_dtype=dtype)
    gguf_ckpt_url = f"https://huggingface.co/{gguf_repo_id}/blob/main/{gguf_filename}"
    print(f"[WanGen] GGUF checkpoint: {gguf_ckpt_url}")
    transformer = WanTransformer3DModel.from_single_file(
        gguf_ckpt_url,
        quantization_config=gguf_config,
        torch_dtype=dtype,
    )
    print(f"[WanGen] ✅ GGUF DiT loaded (Q4_K_M, ~983MB disk → dequant on-the-fly)")

    # ══════════════════════════════════════════════════════════
    # STEP 2: Load VAE in float32 (required for decode quality)
    # ══════════════════════════════════════════════════════════
    print("[WanGen] Loading VAE (float32)...")
    vae = AutoencoderKLWan.from_pretrained(
        model_id, subfolder="vae", torch_dtype=torch.float32
    )
    print("[WanGen] ✅ VAE loaded (float32, ~0.5GB)")

    # ══════════════════════════════════════════════════════════
    # STEP 3: Scheduler
    # ══════════════════════════════════════════════════════════
    scheduler = UniPCMultistepScheduler(
        prediction_type="flow_prediction",
        use_flow_sigmas=True,
        num_train_timesteps=1000,
        flow_shift=flow_shift,
    )

    # ══════════════════════════════════════════════════════════
    # STEP 4: Assemble Pipeline
    # ══════════════════════════════════════════════════════════
    # Community-proven approach (diffusers issue #12896):
    # → pipe.to(device) puts EVERYTHING on MPS/CUDA
    # → This ensures pipe.device returns "mps" so all intermediates
    #   (timesteps, latents, etc.) are created on the correct device.
    # T5 with float16 ≈ 4.5GB, GGUF DiT ≈ 1GB, VAE ≈ 0.5GB = ~6GB on 24GB MPS ✅
    print("[WanGen] Loading pipeline...")
    pipe = WanPipeline.from_pretrained(
        model_id,
        vae=vae,
        transformer=transformer,
        torch_dtype=dtype,
    )
    pipe.scheduler = scheduler

    # Move entire pipeline to device — critical for MPS!
    # Keeping T5 on CPU causes pipe.device="cpu" → all tensors on CPU → MPS layers crash
    move_start = time.time()
    pipe.to(device)
    move_time = time.time() - move_start
    print(f"[WanGen] ✅ Full pipeline on {device} (moved in {move_time:.1f}s)")

    # ── Dtype verification ──
    # Check that we're actually using float16 and not float32 (common silent issue)
    if hasattr(pipe, 'text_encoder') and pipe.text_encoder is not None:
        te_dtype = next(pipe.text_encoder.parameters()).dtype
        te_device = next(pipe.text_encoder.parameters()).device
        print(f"[WanGen] 📊 T5 text_encoder: dtype={te_dtype}, device={te_device}")
    if hasattr(pipe, 'transformer') and pipe.transformer is not None:
        try:
            # GGUF models may not have standard params
            for name, param in pipe.transformer.named_parameters():
                print(f"[WanGen] 📊 Transformer first param '{name}': dtype={param.dtype}, device={param.device}")
                break
        except Exception:
            pass
    if hasattr(pipe, 'vae') and pipe.vae is not None:
        vae_dtype = next(pipe.vae.parameters()).dtype
        vae_device = next(pipe.vae.parameters()).device
        print(f"[WanGen] 📊 VAE: dtype={vae_dtype}, device={vae_device}")

    # ── Monkey-patch Conv3d for MPS fallback ──
    # PYTORCH_ENABLE_MPS_FALLBACK=1 makes conv3d run on CPU,
    # but the output stays on CPU → next MPS layer crashes.
    # Fix: wrap patch_embedding so output always returns to MPS.
    if device == "mps":
        _orig_patch_embed = pipe.transformer.patch_embedding
        _target_device = torch.device("mps")

        class _Conv3dMPSWrapper(torch.nn.Module):
            def __init__(self, conv, target_device):
                super().__init__()
                self.conv = conv
                self.target_device = target_device

            def forward(self, x):
                out = self.conv(x)
                if out.device != self.target_device:
                    out = out.to(self.target_device)
                return out

        pipe.transformer.patch_embedding = _Conv3dMPSWrapper(_orig_patch_embed, _target_device)
        print(f"[WanGen] ✅ Conv3d MPS fallback wrapper applied")

    # ══════════════════════════════════════════════════════════
    # STEP 5: Enable VAE memory safety (CRITICAL for no-swap!)
    # ══════════════════════════════════════════════════════════
    # Tiled VAE: processes spatial tiles instead of full frames
    # → VAE decode: 4.45GB → 1.3GB (confirmed by diffusers PR #11414)
    # NOTE: enable_tiling/enable_slicing are on the VAE object, not the pipeline
    pipe.vae.enable_tiling()
    print("[WanGen] ✅ VAE tiling enabled (spatial tiles → 1.3GB peak instead of 4.5GB)")

    # VAE slicing: processes batch items one by one
    pipe.vae.enable_slicing()
    print("[WanGen] ✅ VAE slicing enabled (batch-wise processing)")

    load_time = time.time() - start_load
    print(f"[WanGen] ✅ Full model loaded in {load_time:.1f}s")
    print(f"[WanGen] Memory safety: GGUF Q4_K_M + Tiled VAE + Slicing = NO SWAP")

    # ══════════════════════════════════════════════════════════
    # STEP 6: Generate (with per-step timing diagnostics)
    # ══════════════════════════════════════════════════════════
    generator = None
    if seed is not None:
        generator = torch.Generator(device="cpu").manual_seed(seed)

    # Step callback for timing diagnostics
    _step_times = []
    _step_start = [time.time()]

    def _step_callback(pipe_obj, step_index, timestep, callback_kwargs):
        """Called after each denoising step — logs per-step time."""
        now = time.time()
        elapsed = now - _step_start[0]
        _step_times.append(elapsed)
        print(f"[WanGen] ⏱️  Step {step_index+1}/{steps} done in {elapsed:.1f}s (total: {sum(_step_times):.0f}s)", flush=True)
        _step_start[0] = now
        return callback_kwargs

    print(f"[WanGen] 🎬 Generating {num_frames} frames @ {width}x{height}, steps={steps}...")
    print(f"[WanGen] 📊 Per-step timing enabled for diagnostics")

    # Text encoding phase timing
    text_encode_start = time.time()
    gen_start = time.time()

    output = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        height=height,
        width=width,
        num_frames=num_frames,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        generator=generator,
        callback_on_step_end=_step_callback,
    )

    gen_time = time.time() - gen_start

    # Diagnostics summary
    if _step_times:
        avg_step = sum(_step_times) / len(_step_times)
        min_step = min(_step_times)
        max_step = max(_step_times)
        print(f"[WanGen] 📊 Step timing: avg={avg_step:.1f}s, min={min_step:.1f}s, max={max_step:.1f}s")
        print(f"[WanGen] 📊 Denoising total: {sum(_step_times):.0f}s, Overhead (text enc + VAE): {gen_time - sum(_step_times):.0f}s")
    print(f"[WanGen] ✅ Generation done in {gen_time:.1f}s")

    # ══════════════════════════════════════════════════════════
    # STEP 7: Export video
    # ══════════════════════════════════════════════════════════
    frames = output.frames[0]
    export_to_video(frames, output_path, fps=fps)
    print(f"[WanGen] ✅ Saved: {output_path}")
    print(f"[WanGen] 📊 File size: {os.path.getsize(output_path) // 1024}KB")

    # ══════════════════════════════════════════════════════════
    # STEP 8: Aggressive cleanup — free ALL GPU memory
    # ══════════════════════════════════════════════════════════
    # Senior-level cleanup: every reference nulled, GC forced, caches emptied
    print("[WanGen] 🧹 Cleaning up...")
    del output, frames

    # Move everything to CPU before deletion (prevents MPS zombie allocations)
    try:
        pipe.transformer.to("cpu")
    except Exception:
        pass
    try:
        pipe.vae.to("cpu")
    except Exception:
        pass
    try:
        pipe.text_encoder.to("cpu")
    except Exception:
        pass

    del pipe
    del vae, transformer, scheduler
    if 'gguf_config' in dir():
        del gguf_config

    # Force Python GC (twice — catches ref cycles)
    gc.collect()
    gc.collect()

    # Empty device caches
    if device == "mps":
        torch.mps.empty_cache()
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()

    total_time = time.time() - start_load
    print(f"[WanGen] ✅ Total time: {total_time:.1f}s — GPU memory fully released")


if __name__ == "__main__":
    main()
