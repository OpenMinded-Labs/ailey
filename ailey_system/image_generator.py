"""
MFLUX Image Generator for Ailey
================================
Generates images locally using MFLUX + Z-Image Turbo (4-bit quantized).
Runs as a subprocess so the MLX LLM stays loaded in GPU memory.

Hardware: MacBook Air M4, 24GB Unified Memory
- Ministral 3 14B Q5 ≈ 10-11GB
- Z-Image Turbo 4-bit ≈ 8GB
- Both fit simultaneously (~18-19GB of 24GB)

Usage:
    from ailey_system.image_generator import generate_image, is_mflux_available
"""

import os
import re
import time
import subprocess
import shutil
import json
from typing import Optional, Tuple
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_GALLERY_DIR = os.path.join(_BASE_DIR, "ailey_users", "image_gallery")       # Ailey's own → public gallery
IMAGE_PRIVATE_DIR = os.path.join(_BASE_DIR, "ailey_users", "image_private")       # Simon's images → private, never uploaded
IMAGE_HIDDEN_DIR  = os.path.join(_BASE_DIR, "ailey_users", "image_hidden")        # Hidden gallery (password-protected)
IMAGE_UPSCALED_DIR = os.path.join(_BASE_DIR, "ailey_users", "image_upscaled")    # SeedVR2 upscaled images
SOCIAL_MEDIA_DIR = os.path.join(_BASE_DIR, "ailey_users", "social_media")

# MFLUX model — pre-quantized 4-bit Z-Image Turbo (~8GB)
# Uses filipstrand's pre-quantized 4-bit HF model to avoid downloading
# the full 32.7GB unquantized Tongyi-MAI/Z-Image-Turbo model.
MFLUX_MODEL = "filipstrand/Z-Image-Turbo-mflux-4bit"
MFLUX_STEPS = 9        # Z-Image Turbo optimal steps
MFLUX_SEED = None       # Random seed each time (None = random)
MFLUX_WIDTH = 1024
MFLUX_HEIGHT = 1024

# Ailey's self-portrait emotes (for img2img "selfies")
EMOTES_DIR = os.path.join(_BASE_DIR, "ailey-emotes")
AILEY_DEFAULT_SELFIE = "ailey-default.jpg"

# RAM safety: minimum free GB before allowing generation
# RAM safety: minimum free GB before allowing generation.
# After Ministral is unloaded (~10GB freed), this is easily met.
# Set conservatively low because macOS purgeable/compressed memory
# is available on demand — the real constraint is Metal GPU memory.
MIN_FREE_RAM_GB = 2.0

# Ailey's canonical appearance — prepended to ALL selfie prompts
# Ensures consistent face/hair/style regardless of what the LLM writes
# NOTE: Never mention chest/breast/figure anatomy — FLUX interprets them as nude!
AILEY_FACE_PREFIX = (
    "A!ley, petite slim young woman, "
    "messy black hair with neon pink streaks and platinum blonde highlights, "
    "heavy eyeliner, dark eyeshadow, silver nose stud, warm olive skin, "
    "extensive tattoos on arms shoulders and collarbone, "
)

# "Ungeschminkt" (natural / no-makeup) variant — same person, without heavy makeup
# Used when user toggles "Ungeschminkt" in the ImageGen tab.
# Replaces AILEY_FACE_PREFIX entirely (does NOT stack on top of it).
AILEY_FACE_PREFIX_NATURAL = (
    "A!ley, petite slim young woman, "
    "messy black hair with neon pink streaks and platinum blonde highlights, "
    "natural look, no makeup, bare face, clear skin, silver nose stud, warm olive skin, "
    "extensive tattoos on arms shoulders and collarbone, "
)

# Anime LoRA variant — same identity but described in anime visual language.
# Used automatically when the anime community LoRA is active.
# The anime LoRA needs anime-style descriptions to produce good results;
# photorealistic descriptions + anime LoRA = uncanny valley.
AILEY_FACE_PREFIX_ANIME = (
    "Anime, anime style, A!ley, petite slim anime girl, "
    "messy black hair with neon pink streaks and platinum blonde highlights, "
    "heavy dark eyeliner, smoky eyeshadow, silver nose stud, warm olive skin, "
    "colorful sleeve tattoos on arms and shoulders, "
    "expressive large eyes, cel-shading, vibrant colors, "
)

AILEY_FACE_PREFIX_ANIME_NATURAL = (
    "Anime, anime style, A!ley, petite slim anime girl, "
    "messy black hair with neon pink streaks and platinum blonde highlights, "
    "natural look, no makeup, clear skin, silver nose stud, warm olive skin, "
    "colorful sleeve tattoos on arms and shoulders, "
    "expressive large eyes, cel-shading, vibrant colors, "
)

# Selfie LoRA — trained identity LoRA for Ailey's face
# The LoRA learned facial geometry; the FACE_PREFIX above supplies hair/makeup/style.
AILEY_SELFIE_LORA_PATH = os.path.join(_BASE_DIR, "AILEY_lora_final", "0001350_adapter.safetensors")
AILEY_SELFIE_LORA_SCALE = 1.0
AILEY_SELFIE_TRIGGER = "A!ley"

# ---------------------------------------------------------------------------
# Community LoRAs — downloaded to community_loras/
# ---------------------------------------------------------------------------
COMMUNITY_LORA_DIR = os.path.join(_BASE_DIR, "community_loras")

# Realism LoRA — XLabs-AI/flux-RealismLora (22 MB, FLUX.1-dev based)
# Enhances photorealism, skin texture, lighting. No trigger word needed.
# Recommended scale: 0.7–1.0
LORA_REALISM_PATH = os.path.join(COMMUNITY_LORA_DIR, "realism_xlabs.safetensors")
LORA_REALISM_SCALE = 0.8

# Anime LoRA — prithivMLmods/Canopus-LoRA-Flux-Anime (613 MB, FLUX.1-dev based)
# Trigger word: "Anime" in prompt. Recommended scale: 0.7–0.9
LORA_ANIME_PATH = os.path.join(COMMUNITY_LORA_DIR, "anime_canopus.safetensors")
LORA_ANIME_SCALE = 0.8
LORA_ANIME_TRIGGER = "Anime"

# NSFW Anatomy LoRA — SCG-Anatomy-Flux1-d (196 MB, FLUX.1-dev based)
# Improves quality of human anatomy/body proportions for adult content.
# No trigger word. Recommended scale: 0.6–0.8
LORA_NSFW_PATH = os.path.join(COMMUNITY_LORA_DIR, "nsfw_scg_anatomy.safetensors")
LORA_NSFW_SCALE = 0.7

# Registry of available community LoRAs
# Each entry: id → { path, scale, trigger, description, nsfw }
# nsfw=True means the LoRA is excluded from portal image generation.
COMMUNITY_LORAS = {
    "realism": {
        "path": LORA_REALISM_PATH,
        "scale": LORA_REALISM_SCALE,
        "trigger": None,
        "description": "Fotorealismus — bessere Hauttextur, Beleuchtung, Tiefenschärfe",
        "nsfw": False,
    },
    "anime": {
        "path": LORA_ANIME_PATH,
        "scale": LORA_ANIME_SCALE,
        "trigger": LORA_ANIME_TRIGGER,
        "description": "Anime/Manga-Stil — lebhafte Farben, große Augen, Cel-Shading",
        "nsfw": False,
    },
    "anatomy": {
        "path": LORA_NSFW_PATH,
        "scale": LORA_NSFW_SCALE,
        "trigger": None,
        "description": "Anatomie — verbesserte Körperproportionen & Details",
        "nsfw": True,
    },
}


def get_available_loras(exclude_nsfw: bool = False) -> dict:
    """Return community LoRAs that are actually downloaded and available.

    Args:
        exclude_nsfw: If True, exclude LoRAs flagged as nsfw (for portal).

    Returns:
        Dict of id → lora info for available LoRAs.
    """
    available = {}
    for lora_id, info in COMMUNITY_LORAS.items():
        if exclude_nsfw and info.get("nsfw"):
            continue
        if os.path.isfile(info["path"]):
            available[lora_id] = info
    return available


def build_lora_args(
    lora_ids: list[str],
    include_ailey: bool = False,
    ailey_scale: float = AILEY_SELFIE_LORA_SCALE,
    exclude_nsfw: bool = False,
) -> tuple[list[str], list[float], str]:
    """Build LoRA paths + scales from LoRA IDs. Max 2 active simultaneously.

    Args:
        lora_ids: List of community LoRA IDs to activate (e.g. ["realism", "anime"])
        include_ailey: Whether to include the Ailey face LoRA (for selfies)
        ailey_scale: Scale for Ailey LoRA (default 1.0)
        exclude_nsfw: If True, skip any LoRA flagged as nsfw

    Returns:
        (lora_paths, lora_scales, trigger_additions)
        trigger_additions: string to prepend to prompt (e.g. "Anime, ")
    """
    paths = []
    scales = []
    triggers = []

    # Ailey LoRA always goes first if requested
    if include_ailey and os.path.isfile(AILEY_SELFIE_LORA_PATH):
        paths.append(AILEY_SELFIE_LORA_PATH)
        scales.append(ailey_scale)
        # Ailey trigger is already in AILEY_FACE_PREFIX, no extra trigger needed

    available = get_available_loras(exclude_nsfw=exclude_nsfw)

    for lid in lora_ids:
        if len(paths) >= 2:
            break  # Max 2 LoRAs simultaneously
        if lid in available:
            info = available[lid]
            paths.append(info["path"])
            scales.append(info["scale"])
            if info.get("trigger"):
                triggers.append(info["trigger"])

    trigger_prefix = ", ".join(triggers) + ", " if triggers else ""
    return paths, scales, trigger_prefix


# Max images per day (idle generation)
MAX_IDLE_IMAGES_PER_DAY = 2

# Track generation count today
_generation_count_file = os.path.join(_BASE_DIR, "ailey_users", "image_gen_status.json")


def _ensure_dirs():
    """Create required directories."""
    os.makedirs(IMAGE_GALLERY_DIR, exist_ok=True)
    os.makedirs(IMAGE_PRIVATE_DIR, exist_ok=True)
    os.makedirs(IMAGE_UPSCALED_DIR, exist_ok=True)
    os.makedirs(SOCIAL_MEDIA_DIR, exist_ok=True)
    for sub in ("pending", "published", "archived"):
        os.makedirs(os.path.join(SOCIAL_MEDIA_DIR, sub), exist_ok=True)


# ---------------------------------------------------------------------------
# Ailey Emote / Selfie Helpers
# ---------------------------------------------------------------------------

def get_ailey_emote_path(mood: str = "default") -> Optional[str]:
    """
    Get the file path for an Ailey mood/emote image.
    Used as init image for img2img "selfie" generation.

    Args:
        mood: One of the available moods (default, thinking, sad, angry, etc.)

    Returns:
        Absolute path to the emote image or None if not found
    """
    # Map common mood names to emote filenames
    mood_map = {
        "default": "ailey-default.jpg",
        "thinking": "ailey-thinking.jpg",
        "happy": "ailey-grins.jpg",
        "sad": "ailey-sad.jpg",
        "angry": "ailey-angry.jpg",
        "confused": "ailey-confused.jpg",
        "crying": "ailey-crying.jpg",
        "flirty": "ailey-flirty.jpg",
        "funny": "ailey-funny.jpg",
        "grins": "ailey-grins.jpg",
        "kissing": "ailey-kissing.jpg",
        "playful": "ailey-playful.jpg",
        "singing": "ailey-playing-guitar-singing.jpg",
        "singing_soft": "ailey-playing-guitar-singing-soft-music.jpg",
        "guitar": "ailey-playing-guitar-singing.jpg",
        "sleeping": "ailey-sleeping.jpg",
        "tired": "ailey-slightly-tired.jpg",
        "very_tired": "ailey-very-tired.jpg",
        "slightly_crying": "ailey-slightly-crying.jpg",
        "coding": "ailey-coding.jpg",
        "writing": "ailey-writing-diary.jpg",
    }
    filename = mood_map.get(mood.lower().replace("-", "_").replace(" ", "_"))
    if not filename:
        # Try direct filename match
        direct = f"ailey-{mood.lower().replace('_', '-')}.jpg"
        if os.path.isfile(os.path.join(EMOTES_DIR, direct)):
            filename = direct
        else:
            filename = AILEY_DEFAULT_SELFIE

    path = os.path.join(EMOTES_DIR, filename)
    return path if os.path.isfile(path) else None


def list_ailey_emotes() -> list[dict]:
    """List all available Ailey emote images with metadata."""
    emotes = []
    if not os.path.isdir(EMOTES_DIR):
        return emotes
    for f in sorted(os.listdir(EMOTES_DIR)):
        if f.startswith("ailey-") and f.endswith(".jpg"):
            mood = f.replace("ailey-", "").replace(".jpg", "").replace("-", "_")
            emotes.append({
                "mood": mood,
                "filename": f,
                "path": os.path.join(EMOTES_DIR, f),
                "size_kb": os.path.getsize(os.path.join(EMOTES_DIR, f)) // 1024,
            })
    return emotes


def _get_mflux_path() -> Optional[str]:
    """Find the mflux-generate-z-image-turbo binary. Check venv, PATH, and common locations."""
    # Prefer the dedicated Z-Image Turbo binary
    for bin_name in ("mflux-generate-z-image-turbo", "mflux-generate"):
        # 1. Check PATH
        p = shutil.which(bin_name)
        if p:
            return p
        # 2. Check project venv
        venv_path = os.path.join(_BASE_DIR, ".venv", "bin", bin_name)
        if os.path.isfile(venv_path):
            return venv_path
        # 3. Check uv tool
        home = os.path.expanduser("~")
        uv_path = os.path.join(home, ".local", "bin", bin_name)
        if os.path.isfile(uv_path):
            return uv_path
    return None


def is_mflux_available() -> bool:
    """Check if mflux CLI is installed and accessible."""
    return _get_mflux_path() is not None


def get_free_ram_gb() -> float:
    """Get available RAM in GB (macOS).
    
    On Apple Silicon, macOS aggressively compresses and caches memory.
    The 'available' memory reported by psutil/vm_stat is the REAL amount
    that can be used without swapping — it includes free + inactive + purgeable.
    
    IMPORTANT: Apple Silicon M-series uses 16KB pages, NOT 4KB!
    """
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.available / (1024 ** 3)
    except ImportError:
        # Fallback: parse vm_stat — must detect page size correctly
        try:
            out = subprocess.check_output(["vm_stat"], text=True)
            lines = out.splitlines()
            
            # First line contains page size: "Mach Virtual Memory Statistics: (page size of 16384 bytes)"
            page_size = 16384  # Apple Silicon default
            if lines and "page size of" in lines[0]:
                import re as _re
                _m = _re.search(r'page size of (\d+)', lines[0])
                if _m:
                    page_size = int(_m.group(1))
            
            pages = {}
            for line in lines:
                for key in ("Pages free", "Pages speculative", "Pages inactive", "Pages purgeable"):
                    if key in line:
                        val = line.split(":")[-1].strip().rstrip(".")
                        try:
                            pages[key] = int(val)
                        except ValueError:
                            pass
            
            # Available ≈ free + speculative + inactive + purgeable
            # (same logic as psutil.virtual_memory().available on macOS)
            available_pages = sum(pages.values())
            return (available_pages * page_size) / (1024 ** 3)
        except Exception:
            return 99.0  # Assume OK if we can't check


def _read_gen_status() -> dict:
    """Read generation status from disk."""
    try:
        with open(_generation_count_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"date": "", "count": 0}


def _write_gen_status(status: dict):
    """Write generation status to disk."""
    os.makedirs(os.path.dirname(_generation_count_file), exist_ok=True)
    with open(_generation_count_file, "w") as f:
        json.dump(status, f)


def can_generate_idle_image() -> bool:
    """Check if Ailey can generate another idle image today (max 2/day)."""
    status = _read_gen_status()
    today = datetime.now().strftime("%Y-%m-%d")
    if status.get("date") != today:
        return True
    return status.get("count", 0) < MAX_IDLE_IMAGES_PER_DAY


def mark_idle_image_generated():
    """Increment today's idle image generation counter."""
    status = _read_gen_status()
    today = datetime.now().strftime("%Y-%m-%d")
    if status.get("date") != today:
        status = {"date": today, "count": 1}
    else:
        status["count"] = status.get("count", 0) + 1
    _write_gen_status(status)


def generate_image(
    prompt: str,
    title: str = "Untitled",
    width: int = MFLUX_WIDTH,
    height: int = MFLUX_HEIGHT,
    steps: int = MFLUX_STEPS,
    seed: Optional[int] = None,
    aspect_ratio: str = "1:1",
    image_path: Optional[str] = None,
    image_strength: float = 0.4,
    low_ram: bool = True,
    private: bool = False,
    lora_paths: Optional[list] = None,
    lora_scales: Optional[list] = None,
    image_type: str = "img",
    username: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Generate an image using MFLUX / Z-Image Turbo.

    Args:
        prompt: English image prompt
        title: German title for the artwork
        width: Image width (default 1024)
        height: Image height (default 1024)
        steps: Number of inference steps (default 9)
        seed: Random seed (None = random)
        aspect_ratio: "1:1", "16:9", "9:16", "4:3"
        image_path: Optional path to init image (img2img mode)
        image_strength: How much the init image influences output (0.0-1.0, default 0.4)
        low_ram: Enable --low-ram mode (default True, recommended with Ministral loaded)
        private: If True, save to image_private/ (Simon's images, never uploaded).
                 If False, save to image_gallery/ (Ailey's own, synced to portal gallery).
        lora_paths: Optional list of LoRA weight file paths (e.g. for Ailey selfie LoRA)
        lora_scales: Optional list of LoRA scales (one per path, default 0.8 each)
        image_type: "selfie" | "img" — controls filename prefix
        username: Username of requester (empty = Ailey's own autonomous work)

    Filename convention:
        Idle Thinker (autonomous): AILEY_DIGITAL_CONSCIOUSNESS_IMG_001.png
                                   AILEY_DIGITAL_CONSCIOUSNESS_SELFIE_001.png
        User request:              AILEY_SELFIE_Simon_001.png
                                   AILEY_IMG_Simon_001.png

    Returns:
        Tuple of (filepath, filename) or (None, None) on failure
    """
    _ensure_dirs()

    # Select target directory based on privacy
    target_dir = IMAGE_PRIVATE_DIR if private else IMAGE_GALLERY_DIR

    # Resolve aspect ratio to dimensions — only override if caller
    # used the default width/height (i.e. didn't pass custom values)
    if width == MFLUX_WIDTH and height == MFLUX_HEIGHT:
        ar_map = {
            "1:1": (1024, 1024),
            "16:9": (1024, 576),
            "9:16": (576, 1024),
            "4:3": (1024, 768),
            "3:4": (768, 1024),
            "4:5": (832, 1040),   # Instagram optimal
            "5:4": (1040, 832),
        }
        if aspect_ratio in ar_map:
            width, height = ar_map[aspect_ratio]

    # Safety check: enough RAM?
    free_ram = get_free_ram_gb()
    if free_ram < MIN_FREE_RAM_GB:
        print(f"[ImageGen] ⚠️ Not enough free RAM: {free_ram:.1f}GB < {MIN_FREE_RAM_GB}GB minimum")
        # Also log to portal image log if it exists
        import logging
        _plog = logging.getLogger("portal_image_gen")
        _plog.info(f"❌ RAM CHECK FAILED: {free_ram:.1f}GB free < {MIN_FREE_RAM_GB}GB minimum")
        return None, None

    # Find mflux binary
    mflux_bin = _get_mflux_path()
    if not mflux_bin:
        print("[ImageGen] ❌ mflux-generate not found. Install with: pip install mflux")
        import logging
        _plog = logging.getLogger("portal_image_gen")
        _plog.info("❌ MFLUX BINARY NOT FOUND")
        return None, None

    # Build output filename using naming convention
    timestamp = int(time.time())

    _type_upper = "SELFIE" if image_type == "selfie" else "IMG"
    if username:
        _user_slug = re.sub(r'[^a-zA-Z0-9]', '', username)[:20] or "User"
        _prefix = f"AILEY_{_type_upper}_{_user_slug}_"
    else:
        _prefix = f"AILEY_DIGITAL_CONSCIOUSNESS_{_type_upper}_"

    # Find highest existing sequence number across ALL directories
    # (gallery, private, hidden) so numbers are never recycled
    # when images are moved / deleted / hidden between directories.
    # Also scan .meta.json in case the image was deleted but the meta remained.
    _all_dirs = [IMAGE_GALLERY_DIR, IMAGE_PRIVATE_DIR, IMAGE_HIDDEN_DIR]

    _max_seq = 0
    _num_pattern = re.compile(re.escape(_prefix) + r'(\d+)\.(?:png|meta\.json)$', re.IGNORECASE)
    for _d in _all_dirs:
        if not os.path.isdir(_d):
            continue
        for _f in os.listdir(_d):
            _m = _num_pattern.match(_f)
            if _m:
                _max_seq = max(_max_seq, int(_m.group(1)))

    _seq = _max_seq + 1
    _seq_str = f"{_seq:03d}"

    if username:
        filename = f"AILEY_{_type_upper}_{_user_slug}_{_seq_str}.png"
    else:
        filename = f"AILEY_DIGITAL_CONSCIOUSNESS_{_type_upper}_{_seq_str}.png"

    filepath = os.path.join(target_dir, filename)

    # Build mflux command
    is_dedicated = mflux_bin.endswith("mflux-generate-z-image-turbo")
    cmd = [mflux_bin]

    # Use the pre-quantized 4-bit HF model (filipstrand/Z-Image-Turbo-mflux-4bit, ~6GB).
    # --model with a HuggingFace repo sets model_path, avoiding the 32GB Tongyi-MAI download.
    # Do NOT use --quantize with a pre-quantized model (it's already 4-bit).
    cmd.extend(["--model", MFLUX_MODEL])

    if not is_dedicated:
        # Generic mflux-generate needs --base-model to know which pipeline
        cmd.extend(["--base-model", "z-image-turbo"])

    cmd.extend([
        "--prompt", prompt,
        "--steps", str(steps),
        "--width", str(width),
        "--height", str(height),
        "--output", filepath,
    ])
    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    # Low-RAM mode: limits MLX cache so MFLUX + Ministral can coexist
    if low_ram:
        cmd.append("--low-ram")

    # Image-to-Image mode
    is_img2img = False
    if image_path and os.path.isfile(image_path):
        cmd.extend(["--image-path", image_path])
        cmd.extend(["--image-strength", str(image_strength)])
        is_img2img = True

    # LoRA weights (e.g. Ailey selfie LoRA)
    has_lora = False
    if lora_paths:
        valid_loras = [p for p in lora_paths if os.path.isfile(p)]
        if valid_loras:
            cmd.extend(["--lora-paths"] + valid_loras)
            if lora_scales:
                cmd.extend(["--lora-scales"] + [str(s) for s in lora_scales[:len(valid_loras)]])
            else:
                cmd.extend(["--lora-scales"] + ["0.8"] * len(valid_loras))
            has_lora = True
            print(f"[ImageGen] 🔧 LoRA: {[os.path.basename(p) for p in valid_loras]}")

    mode_str = f"img2img (strength={image_strength})" if is_img2img else "txt2img"
    if has_lora:
        mode_str += " +LoRA"
    print(f"[ImageGen] 🎨 Generating ({mode_str}): {prompt[:80]}...")
    print(f"[ImageGen] 📐 Size: {width}x{height}, Steps: {steps}, LowRAM: {low_ram}")
    print(f"[ImageGen] 🔧 CMD: {' '.join(cmd[:8])}{'…' if len(cmd)>8 else ''}")
    if is_img2img:
        print(f"[ImageGen] 🖼️ Init image: {os.path.basename(image_path)}")
    print(f"[ImageGen] 📁 Output: {filepath}")

    try:
        start_time = time.time()
        # Ensure PATH includes /usr/sbin (for system_profiler, needed by mflux battery_saver)
        # Tauri sets a minimal PATH that omits /usr/sbin → FileNotFoundError
        _env = os.environ.copy()
        _path = _env.get("PATH", "")
        if "/usr/sbin" not in _path:
            _env["PATH"] = f"{_path}:/usr/sbin"
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout (1024x1024 takes ~5min on M4)
            cwd=_BASE_DIR,
            env=_env,
        )

        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"[ImageGen] ❌ mflux failed (exit {result.returncode})")
            print(f"[ImageGen] ❌ Full CMD was: {cmd}")
            # Write full stderr to a dedicated file so HTTP logs don't bury it
            _err_log = os.path.join(_BASE_DIR, "mflux_last_error.log")
            try:
                with open(_err_log, "w") as _ef:
                    _ef.write(f"CMD: {cmd}\n\nRETURN CODE: {result.returncode}\n\n")
                    _ef.write(f"STDERR:\n{result.stderr or '(empty)'}\n\n")
                    _ef.write(f"STDOUT:\n{result.stdout or '(empty)'}\n")
                print(f"[ImageGen] ❌ Full error saved to {_err_log}")
            except Exception:
                pass
            if result.stderr:
                print(f"[ImageGen] stderr (full):\n{result.stderr.rstrip()}")
            if result.stdout:
                print(f"[ImageGen] stdout: {result.stdout[:1000]}")
            # ── Venv-Doctor: Diagnose bei Crash-Exit-Codes ──
            if result.returncode in (138, 137, 139, -10, -9, -11):
                try:
                    from ailey_system.venv_doctor import diagnose_subprocess_failure
                    diagnose_subprocess_failure(
                        env_name="ailey_main",
                        returncode=result.returncode,
                        stderr=result.stderr or "",
                        command=f"mflux-generate-z-image-turbo …",
                    )
                except Exception as diag_err:
                    print(f"[ImageGen] ⚠️ Venv-Diagnose: {diag_err}")
            return None, None

        # Verify file was created
        if not os.path.isfile(filepath):
            print(f"[ImageGen] ❌ Output file not found: {filepath}")
            # mflux might save with a different name — check for recent files
            for f in sorted(os.listdir(target_dir), reverse=True)[:5]:
                if f.startswith(f"img_{timestamp}"):
                    filepath = os.path.join(target_dir, f)
                    filename = f
                    break
            else:
                return None, None

        file_size = os.path.getsize(filepath)
        print(f"[ImageGen] ✅ Generated in {elapsed:.1f}s — {filename} ({file_size // 1024}KB)")

        # Save metadata alongside the image
        meta_path = filepath.replace(".png", ".meta.json")
        meta = {
            "prompt": prompt,
            "title": title,
            "model": MFLUX_MODEL,
            "mode": "img2img" if is_img2img else "txt2img",
            "steps": steps,
            "width": width,
            "height": height,
            "seed": seed,
            "low_ram": low_ram,
            "private": private,
            "generation_time_s": round(elapsed, 1),
            "file_size_bytes": file_size,
            "created_at": datetime.now().isoformat(),
        }
        if is_img2img:
            meta["init_image"] = os.path.basename(image_path)
            meta["image_strength"] = image_strength
        if has_lora:
            meta["lora_paths"] = [os.path.basename(p) for p in valid_loras]
            meta["lora_scales"] = lora_scales or [0.8] * len(valid_loras)
        try:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return filepath, filename

    except subprocess.TimeoutExpired:
        print("[ImageGen] ❌ Generation timed out (5min)")
        return None, None
    except Exception as e:
        print(f"[ImageGen] ❌ Error: {e}")
        return None, None


# ---------------------------------------------------------------------------
# SeedVR2 Image Upscaler — diffusion-based super-resolution via mflux
# ---------------------------------------------------------------------------

def _get_seedvr2_path() -> Optional[str]:
    """Find the mflux-upscale-seedvr2 binary."""
    bin_name = "mflux-upscale-seedvr2"
    # 1. Check PATH
    p = shutil.which(bin_name)
    if p:
        return p
    # 2. Check project venv
    venv_path = os.path.join(_BASE_DIR, ".venv", "bin", bin_name)
    if os.path.isfile(venv_path):
        return venv_path
    # 3. Check uv tool
    home = os.path.expanduser("~")
    uv_path = os.path.join(home, ".local", "bin", bin_name)
    if os.path.isfile(uv_path):
        return uv_path
    return None


def is_seedvr2_available() -> bool:
    """Check if SeedVR2 upscaler CLI is installed and accessible."""
    return _get_seedvr2_path() is not None


def upscale_image(
    input_filename: str,
    resolution: str = "2x",
    softness: float = 0.0,
    low_ram: bool = True,
    seed: Optional[int] = None,
    input_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Upscale an image using SeedVR2 diffusion-based super-resolution.

    Finds the source image in gallery/private/hidden/upscaled directories,
    runs mflux-upscale-seedvr2, saves result to image_upscaled/.

    Args:
        input_filename: Filename of the source image (e.g. "AILEY_IMG_Simon_001.png")
        resolution: Target resolution — "2x", "3x", "4x" or pixel value like "2048" (default "2x")
        softness: 0.0 (sharp, default) to 1.0 (max smooth). Controls denoising strength.
        low_ram: Enable --low-ram mode (default True, recommended with Ministral loaded)
        seed: Random seed for reproducibility (None = random)
        input_path: Optional absolute path to image file (bypasses directory search, for uploaded files)

    Returns:
        Tuple of (filepath, filename) or (None, None) on failure
    """
    _ensure_dirs()

    # If an explicit input path is given (e.g. uploaded file), use it directly
    source_path = None
    if input_path and os.path.isfile(input_path):
        source_path = input_path
    else:
        # Find the source image across all directories
        for img_dir in (IMAGE_PRIVATE_DIR, IMAGE_GALLERY_DIR, IMAGE_HIDDEN_DIR, IMAGE_UPSCALED_DIR):
            candidate = os.path.join(img_dir, input_filename)
            if os.path.isfile(candidate):
                source_path = candidate
                break

    if not source_path:
        print(f"[Upscaler] ❌ Source image not found: {input_filename}")
        return None, None

    # Safety check: enough RAM?
    free_ram = get_free_ram_gb()
    if free_ram < MIN_FREE_RAM_GB:
        print(f"[Upscaler] ⚠️ Not enough free RAM: {free_ram:.1f}GB < {MIN_FREE_RAM_GB}GB minimum")
        return None, None

    # Find SeedVR2 binary
    seedvr2_bin = _get_seedvr2_path()
    if not seedvr2_bin:
        print("[Upscaler] ❌ mflux-upscale-seedvr2 not found. Update mflux: pip install -U mflux")
        return None, None

    # Build output filename: append _UP2x / _UP3x etc.
    base_name, ext = os.path.splitext(input_filename)
    # Remove any existing _UPnx suffix to avoid stacking (e.g. _UP2x_UP2x)
    base_name = re.sub(r'_UP\dx$', '', base_name)
    scale_label = resolution.upper() if resolution.endswith('x') else f"{resolution}px"
    out_filename = f"{base_name}_UP{scale_label}{ext}"
    out_path = os.path.join(IMAGE_UPSCALED_DIR, out_filename)

    # Build command
    cmd = [seedvr2_bin]
    cmd.extend(["--image-path", source_path])
    cmd.extend(["--resolution", str(resolution)])
    cmd.extend(["--softness", str(softness)])
    cmd.extend(["--output", out_path])
    cmd.append("--metadata")  # Save JSON metadata alongside

    if low_ram:
        cmd.append("--low-ram")
    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    print(f"[Upscaler] 🔍 Upscaling: {input_filename} → {out_filename} (res={resolution}, softness={softness})")
    print(f"[Upscaler] 📁 Source: {source_path}")
    print(f"[Upscaler] 📁 Output: {out_path}")

    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 minute timeout (upscaling can be slow)
            cwd=_BASE_DIR,
        )

        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"[Upscaler] ❌ SeedVR2 failed (exit {result.returncode})")
            if result.stderr:
                print(f"[Upscaler] stderr: {result.stderr[:500]}")
            if result.stdout:
                print(f"[Upscaler] stdout: {result.stdout[:500]}")
            # ── Venv-Doctor: Diagnose bei Crash-Exit-Codes ──
            if result.returncode in (138, 137, 139, -10, -9, -11):
                try:
                    from ailey_system.venv_doctor import diagnose_subprocess_failure
                    diagnose_subprocess_failure(
                        env_name="ailey_main",
                        returncode=result.returncode,
                        stderr=result.stderr or "",
                        command=f"mflux-upscale-seedvr2 …",
                    )
                except Exception as diag_err:
                    print(f"[Upscaler] ⚠️ Venv-Diagnose: {diag_err}")
            return None, None

        # Verify file was created
        if not os.path.isfile(out_path):
            print(f"[Upscaler] ❌ Output file not found: {out_path}")
            return None, None

        file_size = os.path.getsize(out_path)
        print(f"[Upscaler] ✅ Upscaled in {elapsed:.1f}s — {out_filename} ({file_size // 1024}KB)")

        # Save our own metadata alongside
        meta_path = out_path.replace(ext, ".meta.json")
        meta = {
            "type": "upscale",
            "upscaler": "SeedVR2",
            "source_image": input_filename,
            "resolution": resolution,
            "softness": softness,
            "seed": seed,
            "low_ram": low_ram,
            "upscale_time_s": round(elapsed, 1),
            "file_size_bytes": file_size,
            "created_at": datetime.now().isoformat(),
        }
        try:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return out_path, out_filename

    except subprocess.TimeoutExpired:
        print("[Upscaler] ❌ Upscaling timed out (15min)")
        return None, None
    except Exception as e:
        print(f"[Upscaler] ❌ Error: {e}")
        return None, None


def generate_image_for_social(
    prompt: str,
    title: str,
    caption: str,
    hashtags: list[str],
    mood: str = "creative",
    aspect_ratio: str = "1:1",
) -> Optional[dict]:
    """
    Generate an image and prepare it as a social media post draft.

    Returns a social media post dict or None on failure.
    """
    filepath, filename = generate_image(
        prompt=prompt,
        title=title,
        aspect_ratio=aspect_ratio,
    )
    if not filepath:
        return None

    post_id = f"social_{int(time.time())}_{title[:20].replace(' ', '_')}"
    post = {
        "id": post_id,
        "status": "pending",
        "platform": "instagram",
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "mood": mood,
        "image_prompt": prompt,
        "image_path": filepath,
        "image_filename": filename,
        "aspect_ratio": aspect_ratio,
        "created_at": datetime.now().isoformat(),
        "approved_at": None,
        "published_at": None,
    }

    # Save to pending
    _ensure_dirs()
    post_file = os.path.join(SOCIAL_MEDIA_DIR, "pending", f"{post_id}.json")
    with open(post_file, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    print(f"[ImageGen] 📱 Social post drafted: {post_id}")
    return post
