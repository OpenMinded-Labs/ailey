"""
Wan2.1 Video Generator for Ailey — GGUF Q4_K_M Edition
========================================================
Generates short video clips locally using Wan2.1 T2V-1.3B via diffusers.
Runs as a subprocess so the MLX LLM stays unloaded during generation.

Hardware: MacBook Air M4, 24GB Unified Memory
- Ministral must be FULLY UNLOADED before generation (~10GB freed)
- Wan2.1 T2V-1.3B GGUF Q4_K_M: DiT ~983MB + T5 on CPU + VAE tiled ~1.3GB
- Peak GPU: ~4GB → 20GB headroom, NO SWAPPING
- Generates 480P (832×480) 5-second clips at 16fps (81 frames)

Quantization: GGUF Q4_K_M (via diffusers GGUFQuantizationConfig)
- Pure PyTorch dequantize on MPS via forward_native() — no CUDA needed
- VAE: enable_vae_tiling() + enable_vae_slicing() → 1.3GB peak (not 4.5GB)

Architecture:
    The generate_video() function calls a subprocess (`_wan_generate.py`)
    that loads the model, generates, and exits — same pattern as MFLUX
    for images.  The caller (ailey_api.py / idle_thinker.py) is responsible
    for unloading/reloading the LLM before/after calling generate_video().

Usage:
    from ailey_system.video_generator import generate_video, is_wan_available
"""

import os
import re
import sys
import time
import json
import subprocess
from typing import Optional, Tuple
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_GALLERY_DIR = os.path.join(_BASE_DIR, "ailey_users", "video_gallery")
VIDEO_PRIVATE_DIR = os.path.join(_BASE_DIR, "ailey_users", "video_private")

# Wan2.1 T2V-1.3B — GGUF Q4_K_M quantized DiT (MPS-compatible!)
# DiT: ~983MB (Q4_K_M GGUF) instead of ~5.68GB (bf16). T5 stays on CPU (~11GB).
# VAE: float32 with tiled decode → 1.3GB peak instead of 4.5GB
# Peak GPU usage: ~4GB → 20GB headroom on 24GB M4, NO SWAPPING
WAN_MODEL_ID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
WAN_GGUF_REPO_ID = "samuelchristlie/Wan2.1-T2V-1.3B-GGUF"
WAN_GGUF_FILENAME = "Wan2.1-T2V-1.3B-Q4_K_M.gguf"
WAN_NUM_FRAMES = 33        # 33 frames @ 16fps ≈ 2s clip — loops well (must be 4k+1)
WAN_FPS = 16
WAN_WIDTH = 480             # 480×272 = minimal pixel budget for M4, ~15 min generation
WAN_HEIGHT = 272
WAN_STEPS = 20             # 20 steps = good quality, faster than 25
WAN_GUIDANCE_SCALE = 6.0
WAN_FLOW_SHIFT = 8.0       # Recommended for 1.3B model

# Min free RAM before allowing generation
MIN_FREE_RAM_GB = 4.0

# Max videos per day (idle generation)
MAX_IDLE_VIDEOS_PER_DAY = 1

# Generation status tracking
_generation_count_file = os.path.join(_BASE_DIR, "ailey_users", "video_gen_status.json")

# The helper script that runs in a subprocess
_WAN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_wan_generate.py")


def _ensure_dirs():
    """Create required directories."""
    os.makedirs(VIDEO_GALLERY_DIR, exist_ok=True)
    os.makedirs(VIDEO_PRIVATE_DIR, exist_ok=True)


def _get_python_path() -> str:
    """Get the Python executable from the project venv."""
    venv_python = os.path.join(_BASE_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        return venv_python
    return sys.executable


def is_wan_available() -> bool:
    """Check if Wan2.1 dependencies are installed (diffusers, torch, etc.)."""
    python = _get_python_path()
    try:
        result = subprocess.run(
            [python, "-c", "import diffusers; import torch; print('ok')"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        return False


def get_free_ram_gb() -> float:
    """Get available RAM in GB (macOS)."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.available / (1024 ** 3)
    except ImportError:
        try:
            out = subprocess.check_output(["vm_stat"], text=True)
            lines = out.splitlines()
            page_size = 16384  # Apple Silicon default
            if lines and "page size of" in lines[0]:
                m = re.search(r'page size of (\d+)', lines[0])
                if m:
                    page_size = int(m.group(1))
            pages = {}
            for line in lines:
                for key in ("Pages free", "Pages speculative", "Pages inactive", "Pages purgeable"):
                    if key in line:
                        val = line.split(":")[-1].strip().rstrip(".")
                        try:
                            pages[key] = int(val)
                        except ValueError:
                            pass
            available_pages = sum(pages.values())
            return (available_pages * page_size) / (1024 ** 3)
        except Exception:
            return 99.0


def _read_gen_status() -> dict:
    try:
        with open(_generation_count_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": "", "count": 0}


def _write_gen_status(status: dict):
    os.makedirs(os.path.dirname(_generation_count_file), exist_ok=True)
    with open(_generation_count_file, "w") as f:
        json.dump(status, f)


def can_generate_idle_video() -> bool:
    """Check if Ailey can generate an idle video now.
    Rules: ONLY on Sundays, max 1 per day."""
    # Sunday-only check (weekday 6 = Sunday)
    now = datetime.now()
    if now.weekday() != 6:
        return False
    status = _read_gen_status()
    today = now.strftime("%Y-%m-%d")
    if status.get("date") != today:
        return True
    return status.get("count", 0) < MAX_IDLE_VIDEOS_PER_DAY


def can_generate_idle_video_weekly() -> bool:
    """Check if Ailey already generated a video this week (Mon-Sun).
    Used as secondary guard: max 1 video per calendar week."""
    status = _read_gen_status()
    last_date = status.get("date", "")
    if not last_date:
        return True
    try:
        last = datetime.strptime(last_date, "%Y-%m-%d")
        now = datetime.now()
        # Same ISO week?
        if last.isocalendar()[1] == now.isocalendar()[1] and last.year == now.year:
            return status.get("count", 0) < 1
        return True
    except ValueError:
        return True


def mark_idle_video_generated():
    """Increment today's idle video generation counter."""
    status = _read_gen_status()
    today = datetime.now().strftime("%Y-%m-%d")
    if status.get("date") != today:
        status = {"date": today, "count": 1}
    else:
        status["count"] = status.get("count", 0) + 1
    _write_gen_status(status)


def generate_video(
    prompt: str,
    title: str = "Untitled",
    width: int = WAN_WIDTH,
    height: int = WAN_HEIGHT,
    num_frames: int = WAN_NUM_FRAMES,
    steps: int = WAN_STEPS,
    guidance_scale: float = WAN_GUIDANCE_SCALE,
    seed: Optional[int] = None,
    private: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Generate a video using Wan2.1 T2V-1.3B.

    IMPORTANT: The LLM (Ministral) MUST be fully unloaded before calling this.
    The caller is responsible for unload/reload (same pattern as MFLUX image gen).

    Args:
        prompt: English video prompt (descriptive, cinematic language works best)
        title: Title for the video file
        width: Video width (default 832)
        height: Video height (default 480)
        num_frames: Number of frames (default 81 = ~5s at 16fps)
        steps: Inference steps (default 25)
        guidance_scale: CFG scale (default 6.0, recommended for 1.3B)
        seed: Random seed (None = random)
        private: If True, save to video_private/ (not uploaded to portal)

    Returns:
        Tuple of (filepath, filename) or (None, None) on failure
    """
    _ensure_dirs()

    target_dir = VIDEO_PRIVATE_DIR if private else VIDEO_GALLERY_DIR

    # Safety check: enough RAM?
    free_ram = get_free_ram_gb()
    if free_ram < MIN_FREE_RAM_GB:
        print(f"[VideoGen] ⚠️ Not enough free RAM: {free_ram:.1f}GB < {MIN_FREE_RAM_GB}GB minimum")
        return None, None

    # Build output filename
    title_slug = re.sub(r'[^a-z0-9]+', '_', (title or "untitled").lower())[:30]
    timestamp = int(time.time())
    filename = f"vid_{timestamp}_{title_slug}.mp4"
    filepath = os.path.join(target_dir, filename)

    # Negative prompt (Wan2.1 recommended)
    negative_prompt = (
        "Bright tones, overexposed, static, blurred details, subtitles, "
        "style, works, paintings, images, static, overall gray, worst quality, "
        "low quality, JPEG compression residue, ugly, incomplete, extra fingers, "
        "poorly drawn hands, poorly drawn faces, deformed, disfigured, "
        "misshapen limbs, fused fingers, still picture, messy background, "
        "three legs, many people in the background, walking backwards"
    )

    print(f"[VideoGen] 🎬 Generating: {prompt[:80]}...")
    print(f"[VideoGen] 📐 Size: {width}x{height}, Frames: {num_frames}, Steps: {steps}")
    print(f"[VideoGen] 📁 Output: {filepath}")

    # Build the subprocess command
    python = _get_python_path()
    cmd_args = json.dumps({
        "model_id": WAN_MODEL_ID,
        "gguf_repo_id": WAN_GGUF_REPO_ID,
        "gguf_filename": WAN_GGUF_FILENAME,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "flow_shift": WAN_FLOW_SHIFT,
        "fps": WAN_FPS,
        "seed": seed,
        "output_path": filepath,
    })

    try:
        start_time = time.time()
        result = subprocess.run(
            [python, _WAN_SCRIPT, cmd_args],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout (video gen is slow)
            cwd=_BASE_DIR,
            env={
                **os.environ,
                "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.0",
                "PYTORCH_ENABLE_MPS_FALLBACK": "1",
                "PYTORCH_MPS_FALLBACK_WARNINGS": "1",
            },
        )

        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"[VideoGen] ❌ Wan2.1 failed (exit {result.returncode})")
            if result.stderr:
                # Print last 1000 chars of stderr
                print(f"[VideoGen] stderr: {result.stderr[-1000:]}")
            if result.stdout:
                print(f"[VideoGen] stdout: {result.stdout[-500:]}")
            return None, None

        # Log MPS fallback warnings from stderr (critical for diagnostics)
        if result.stderr:
            fallback_warnings = [line for line in result.stderr.splitlines() if 'MPS' in line or 'fallback' in line.lower()]
            if fallback_warnings:
                print(f"[VideoGen] ⚠️ MPS Fallback warnings detected ({len(fallback_warnings)}):")
                # Print unique warnings (they repeat per step)
                seen = set()
                for w in fallback_warnings:
                    w_clean = w.strip()
                    if w_clean not in seen:
                        seen.add(w_clean)
                        print(f"[VideoGen]   → {w_clean}")
                print(f"[VideoGen] 📊 Total fallback occurrences: {len(fallback_warnings)}")

        # Log step timing from stdout
        if result.stdout:
            step_lines = [l for l in result.stdout.splitlines() if '⏱️' in l or '📊' in l]
            for sl in step_lines:
                print(f"[VideoGen] {sl.strip()}")

        # Verify file was created
        if not os.path.isfile(filepath):
            print(f"[VideoGen] ❌ Output file not found: {filepath}")
            return None, None

        file_size = os.path.getsize(filepath)
        print(f"[VideoGen] ✅ Generated in {elapsed:.1f}s — {filename} ({file_size // 1024}KB)")

        # Save metadata
        meta_path = filepath.replace(".mp4", ".meta.json")
        meta = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "title": title,
            "model": WAN_MODEL_ID,
            "gguf_model": f"{WAN_GGUF_REPO_ID}/{WAN_GGUF_FILENAME}",
            "quantization": "GGUF_Q4_K_M",
            "steps": steps,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "fps": WAN_FPS,
            "guidance_scale": guidance_scale,
            "flow_shift": WAN_FLOW_SHIFT,
            "seed": seed,
            "private": private,
            "generation_time_s": round(elapsed, 1),
            "file_size_bytes": file_size,
            "created_at": datetime.now().isoformat(),
        }
        try:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return filepath, filename

    except subprocess.TimeoutExpired:
        print("[VideoGen] ❌ Generation timed out (30min)")
        return None, None
    except Exception as e:
        print(f"[VideoGen] ❌ Error: {e}")
        return None, None
