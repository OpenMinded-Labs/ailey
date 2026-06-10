"""
ACE-Step Music Generator for Ailey
====================================
Generates music locally using ACE-Step v1.5 (Open Source, MIT License).
Runs ACE-Step handler in a SUBPROCESS — loads model, generates, exits.
Zero GPU memory retained after generation (process death = full cleanup).

Architecture (v1.5 — subprocess mode):
    1. Caller (ailey_api / idle_thinker) unloads Ministral LLM
    2. generate_music() spawns subprocess: ACE-Step/.venv/bin/python ace_generate.py {args}
    3. Subprocess loads handler → generate_music() → saves WAV → ffmpeg MP3
    4. Subprocess exits → complete memory cleanup
    5. Caller reloads Ministral LLM

Hardware: MacBook Air M4, 24GB Unified Memory
- Ministral must be FULLY UNLOADED before generation (~10GB freed)
- ACE-Step v1.5 with MLX backend: ~8-12GB peak
- Headroom: ~12-16GB free during generation ✅

Performance (M4 Air, ACE-Step v1.5 MLX):
- SFT 50 steps:  ~150-300s per song (best quality, training default)
- Turbo 8 steps: ~20-40s per song (fast iteration)
- Model load: ~10-30s (cached in unified memory)

Usage:
    from ailey_system.music_generator import generate_music, is_ace_step_available
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

# Songs directory — matches existing Songs API in ailey_api.py
SONGS_DIR = os.path.join(_BASE_DIR, "ailey_users", "songs")

# ACE-Step v1.5 — lives inside the Ailey project folder
ACE_STEP_DIR = os.path.join(_BASE_DIR, "ACE-Step")
ACE_STEP_PYTHON = os.path.join(ACE_STEP_DIR, ".venv", "bin", "python")
_ACE_SCRIPT = os.path.join(ACE_STEP_DIR, "ace_generate.py")

# Generation defaults — ACE-Step v1.5 with MLX backend
ACE_INFER_STEPS = 50         # SFT: 50 steps = best quality (training default), Turbo: 8
ACE_GUIDANCE_SCALE = 7.0     # v1.5 default (was 15.0 in v1.0)
ACE_MAX_DURATION = 480.0     # 8 minutes max (M4 24GB tier6b: 480s with LM)
ACE_DEFAULT_DURATION = 180.0 # 3 minutes default (v1.5 handles longer better)
ACE_BATCH_SIZE = 1           # 1 variant per run (fast), increase for quality
ACE_MODEL = "acestep-v15-sft"  # SFT for finals, turbo for fast tests

# Min free RAM before allowing generation (after LLM unload)
MIN_FREE_RAM_GB = 3.0

# Lock file — when present, ACE-Step is reserved by an external batch script.
# idle_thinker gracefully skips audio gen (no crash).
ACE_LOCK_FILE = os.path.join(_BASE_DIR, "_song_sprint.lock")

# ---------------------------------------------------------------------------
# LoRA + Voice Reference Configuration
# ---------------------------------------------------------------------------

# Available LoRA adapters (PEFT format, compatible with v1.5-sft)
_LORA_DIR = os.path.join(ACE_STEP_DIR, "checkpoints", "loras")

LORA_SYMPHONIC_METAL = {
    "path": os.path.join(_LORA_DIR, "symphonic_metal"),
    "name": "symphonic_metal",
    # Scale note: adapter_config has r=32, lora_alpha=64 → internal effective multiplier = 2.0
    # Passing 0.7 was WAY too hot (sounds like 1.4 effective) → crushing non-metal songs.
    # Lowered to 0.35 → effective ~0.70 — keeps metal character without destroying tonality.
    "scale": 0.35,
}
LORA_POP_ROCK = {
    "path": os.path.join(_LORA_DIR, "pop_rock"),
    "name": "pop_rock",
    # adapter_config has r=128, lora_alpha=128 → effective multiplier = 1.0 → 0.7 is correct
    "scale": 0.7,
}

# ---------------------------------------------------------------------------
# Primary Genre → LoRA Mapping
# ---------------------------------------------------------------------------
# The FIRST genre keyword found in the prompt determines the LoRA.
# Design principle: The prompt should have a clear PRIMARY genre that picks
# the LoRA. Sub-genres and style modifiers are handled by the prompt itself.
#
# Matching rules:
#   1. More specific multi-word genres are checked FIRST (insertion order)
#   2. Generic single-word fallbacks come LAST
#   3. Some genres explicitly map to None (no LoRA) — better than wrong LoRA
#   4. "hardcore" alone is ambiguous (metal vs hip-hop) → requires qualifier
#
# Future: Add more LoRAs (electronic, jazz, hip-hop, etc.)
# ---------------------------------------------------------------------------

_LORA_GENRE_MAP = {
    # ── EXPLICIT NO-LORA GUARDS (checked first — prevent false metal matches) ──
    # These genres must NEVER get the metal LoRA even if they contain sub-words
    # like "folk", "doom", "dark", "post-", "industrial" that could otherwise match.
    "electronic folk":      None,
    "folk pop":             None,
    "acoustic folk":        None,
    "indie folk":           None,
    "dark folk":            None,
    "ambient folk":         None,
    "neo-folk":             None,
    "chamber folk":         None,
    "electronic ambient":   None,
    "ambient electronic":   None,
    "dark ambient":         None,
    "industrial ambient":   None,
    "post-industrial":      None,  # without "metal" qualifier → ambient territory
    "noise-folk":           None,
    "experimental":         None,
    "ambient punk":         None,
    "gothic folk":          None,
    "electronic punk":      None,  # style modifier, base handles it well enough

    # ── SYMPHONIC METAL LoRA ── (heavy guitars, extreme music, aggressive)
    "symphonic metal": LORA_SYMPHONIC_METAL,
    "death metal":     LORA_SYMPHONIC_METAL,
    "black metal":     LORA_SYMPHONIC_METAL,
    "prog metal":      LORA_SYMPHONIC_METAL,
    "progressive metal": LORA_SYMPHONIC_METAL,
    "power metal":     LORA_SYMPHONIC_METAL,
    "nu metal":        LORA_SYMPHONIC_METAL,
    "metalcore":       LORA_SYMPHONIC_METAL,
    "deathcore":       LORA_SYMPHONIC_METAL,
    "djent":           LORA_SYMPHONIC_METAL,
    "thrash metal":    LORA_SYMPHONIC_METAL,  # requires "metal" qualifier — "thrash" alone removed
    "doom metal":      LORA_SYMPHONIC_METAL,  # requires "metal" qualifier — "doom" alone removed
    "grindcore":       LORA_SYMPHONIC_METAL,
    "post-metal":      LORA_SYMPHONIC_METAL,
    "sludge metal":    LORA_SYMPHONIC_METAL,  # requires "metal" qualifier — "sludge" alone removed
    "screamo":         LORA_SYMPHONIC_METAL,
    "post-hardcore":   LORA_SYMPHONIC_METAL,
    "hardcore punk":   LORA_SYMPHONIC_METAL,
    "pirate metal":    LORA_SYMPHONIC_METAL,
    "folk metal":      LORA_SYMPHONIC_METAL,
    "viking metal":    LORA_SYMPHONIC_METAL,
    "latin metal":     LORA_SYMPHONIC_METAL,
    "gothic metal":    LORA_SYMPHONIC_METAL,  # requires "metal" qualifier — gothic alone → folk/ambient
    "industrial metal": LORA_SYMPHONIC_METAL, # requires "metal" qualifier
    "grunge":          LORA_SYMPHONIC_METAL,  # heavy alt-rock — metal LoRA appropriate

    # ── K-Rap / K-Metal hybrids → Metal LoRA (aggressive K-influenced) ──
    "k-pop crossover":    LORA_SYMPHONIC_METAL,
    "k-pop metal":        LORA_SYMPHONIC_METAL,
    "k-pop metal fusion": LORA_SYMPHONIC_METAL,
    "industrial k-rap":   LORA_SYMPHONIC_METAL,
    "rap metal":          LORA_SYMPHONIC_METAL,
    "aggressive k-rap":   LORA_SYMPHONIC_METAL,
    "korean rap":         LORA_SYMPHONIC_METAL,

    # ── POP ROCK LoRA ── (clean guitars, melodic, polished production)
    "pop rock":          LORA_POP_ROCK,
    "pop-rock":          LORA_POP_ROCK,
    "pop punk":          LORA_POP_ROCK,
    "indie rock":        LORA_POP_ROCK,
    "indie pop":         LORA_POP_ROCK,
    "alternative rock":  LORA_POP_ROCK,
    "punk rock":         LORA_POP_ROCK,
    "digital punk":      LORA_POP_ROCK,
    "emo":               LORA_POP_ROCK,
    "post-punk":         LORA_POP_ROCK,
    "garage rock":       LORA_POP_ROCK,
    "britpop":           LORA_POP_ROCK,
    "singer-songwriter": LORA_POP_ROCK,
    "ballad":            LORA_POP_ROCK,
    "folk rock":         LORA_POP_ROCK,
    "country rock":      LORA_POP_ROCK,

    # ── Generic fallbacks (LAST — only match if nothing specific above hit) ──
    "metal":  LORA_SYMPHONIC_METAL,   # plain "metal" → symphonic
    "rock":   LORA_POP_ROCK,          # plain "rock" → pop_rock
    "punk":   LORA_POP_ROCK,          # plain "punk" → pop_rock (not metal)
    # NOTE: "pop", "acoustic", "folk" removed from fallbacks — base model handles
    # them better without any LoRA coloring.

    # NOTE: These genres have NO dedicated LoRA → no LoRA applied.
    # hip-hop, rap, trap, r&b, electronic, edm, techno, house, jazz, classical,
    # ambient, lo-fi, k-pop, reggae, latin, afrobeat, folk, acoustic, experimental
}

# Default voice reference — Ailey's vocal character (30s: singing + rap + scream)
_VOICE_REF_DIR = os.path.join(ACE_STEP_DIR, "checkpoints", "voice_reference")
DEFAULT_VOICE_REFERENCE = os.path.join(_VOICE_REF_DIR, "ailey_voice_reference.wav")
SOFT_VOICE_REFERENCE = os.path.join(_VOICE_REF_DIR, "ailey_voice_reference_soft.wav")


def select_lora_for_prompt(prompt: str) -> Optional[list]:
    """Auto-select the best LoRA adapter based on genre keywords in the prompt.

    Returns a list with one LoRA config dict, or None if no genre match.
    The prompt (ACE-Step hybrid caption) is matched case-insensitively.
    More specific matches (e.g. "death metal") are checked before generic ones
    because dict iteration preserves insertion order and we return on first match.

    Uses word-boundary matching to avoid false positives
    (e.g. "emo" should not match "emotional").
    """
    import re
    prompt_lower = prompt.lower()
    for keyword, lora_cfg in _LORA_GENRE_MAP.items():
        # Word-boundary match: "emo" matches "emo, punk" but not "emotional"
        if re.search(r'(?<![a-z])' + re.escape(keyword) + r'(?![a-z])', prompt_lower):
            # None entry = explicit "no LoRA" guard for this genre
            if lora_cfg is None:
                print(f"[MusicGen]    No-LoRA guard matched: '{keyword}' → base model only")
                return None
            # Verify LoRA files actually exist on disk
            adapter_path = os.path.join(lora_cfg["path"], "adapter_model.safetensors")
            if os.path.isfile(adapter_path):
                print(f"[MusicGen] 🎸 Auto-selected LoRA '{lora_cfg['name']}' (matched: '{keyword}')")
                return [lora_cfg]
            else:
                print(f"[MusicGen] ⚠️ LoRA '{lora_cfg['name']}' matched but files missing: {lora_cfg['path']}")
    return None


# ---------------------------------------------------------------------------
# Intelligent Song Duration Estimation
# ---------------------------------------------------------------------------

def estimate_song_duration(lyrics: str) -> float:
    """Estimate ideal song duration based on word count in lyrics.

    Heuristic:
      - Singing speed: ~110-130 words/minute (avg ~120 wpm for pop/rock)
      - Add 15s for intro and 15s for outro = 30s overhead
      - Count only lyric words (strip section markers like [Verse 1])
      - Clamp to [200, 480] seconds (3:20-8:00 minutes)
      - Target ~240s (4 min) for standard songs
      - ACE-Step v1.5 on M4 24GB supports up to 480s with LM

    If lyrics are empty or very short, returns 200s (minimum viable song).
    """
    import re
    if not lyrics or not lyrics.strip():
        return 200.0

    # Strip section markers like [Verse 1], [Chorus], [Bridge], etc.
    clean = re.sub(r'\[.*?\]', '', lyrics)
    # Strip blank lines and extra whitespace
    words = clean.split()
    word_count = len(words)

    if word_count < 20:
        # Very short lyrics — probably an instrumental or partial
        return 200.0

    # ~120 words per minute singing speed + 30s for intro/outro
    singing_seconds = (word_count / 120.0) * 60.0
    total = singing_seconds + 30.0

    # Clamp to [200, ACE_MAX_DURATION] (480s on M4 24GB)
    total = max(200.0, min(ACE_MAX_DURATION, total))
    # Round to nearest 10s for cleaner output
    total = round(total / 10.0) * 10.0

    return float(total)

# Max NEW songs per day (idle generation) — backlog re-gens don't count
# Songs are Ailey's primary creative output and users expect variety
MAX_IDLE_SONGS_PER_DAY = 5

# Generation status tracking
_generation_count_file = os.path.join(_BASE_DIR, "ailey_users", "music_gen_status.json")


# ---------------------------------------------------------------------------
# Ailey's Voice Signature — CONSISTENT vocal identity across ALL songs
# ---------------------------------------------------------------------------
# ACE-Step 1.5 uses HYBRID captions (tags + natural description) for best
# results. Pure comma-tags are too sparse — the model needs a paragraph
# describing the vocal character for accurate voice rendering.
#
# Reference voice: A punkier, edgier Miley Cyrus — raspy, powerful,
# melodic but raw, can switch between sweet singing and aggressive delivery.
#
# The voice description is ALWAYS appended to every caption, ensuring
# consistent vocal identity regardless of genre.

AILEY_VOICE_SIGNATURE = (
    "distinctive female vocalist with a raspy, powerful voice reminiscent of a punkier Miley Cyrus. "
    "She switches effortlessly between sweet melodic singing, fierce aggressive delivery, "
    "and rapid-fire Korean rap. Clear alto with a smoky, husky edge — feminine yet fierce, "
    "emotionally raw and unapologetically intense."
)

# Genre-aware voice signatures — K-Rap is ALWAYS present, but delivery adapts.
# "rapid-fire Korean rap over ambient pads" contradicts itself → bad generation.
_VOICE_BY_GENRE = {
    # Aggressive / energetic genres — classic rapid-fire K-Rap
    "metal":    ("distinctive female vocalist — clear alto with a smoky, powerful edge. "
                 "Switches between melodic singing, raw screams, and rapid-fire Korean rap passages "
                 "that cut through the distortion like a blade."),
    "metalcore": ("distinctive female vocalist — clear alto with a smoky, powerful edge. "
                  "Switches between melodic singing, raw screams, and rapid-fire Korean rap passages "
                  "that cut through the distortion like a blade."),
    "punk":     ("distinctive female vocalist — raspy, punkier Miley Cyrus energy. "
                 "Fierce melodic singing that explodes into Korean rap verses with staccato punch."),
    "rock":     ("distinctive female vocalist — raspy, smoky alto with attitude. "
                 "Melodic verses shift into powerful choruses and punchy Korean rap bridges."),
    "rap":      ("distinctive female vocalist — rapid-fire bilingual flow. "
                 "English verses weave into Korean rap with confident, aggressive delivery."),
    "hip-hop":  ("distinctive female vocalist — rapid-fire bilingual flow. "
                 "English verses weave into Korean rap with confident, aggressive delivery."),
    "k-rap":    ("distinctive female vocalist — rapid-fire bilingual flow. "
                 "English verses weave into Korean rap with confident, aggressive delivery."),
    "k-pop":    ("distinctive female vocalist with a bright, clear alto — melodic pop hooks "
                 "and crisp, rhythmic Korean rap sections woven seamlessly into the song."),
    "pop":      ("distinctive female vocalist — warm alto with a slight rasp. "
                 "Melodic pop delivery with Korean rap verses that add a sharp rhythmic contrast."),
    # Soft / atmospheric genres — K-Rap present but introspective, not aggressive
    "folk":     ("distinctive female vocalist — slightly raspy, intimate alto voice. "
                 "Confessional melodic singing with soft, spoken-word Korean rap interludes "
                 "that feel like whispered secrets over fingerpicked guitar."),
    "acoustic": ("distinctive female vocalist — slightly raspy, intimate alto voice. "
                 "Confessional melodic singing with soft, spoken-word Korean rap interludes "
                 "that feel like whispered secrets over fingerpicked guitar."),
    "ballad":   ("distinctive female vocalist — emotionally raw, slightly raspy alto. "
                 "Vulnerable melodic singing that builds into cathartic power, with introspective "
                 "Korean rap verses during the bridge."),
    "ambient":  ("distinctive female vocalist — breathy, slightly raspy alto with edge. "
                 "Floating melodic lines and hushed Korean rap passages "
                 "that dissolve into the atmospheric textures."),
    "electronic": ("distinctive female vocalist — clear but raspy alto with attitude. "
                   "Clean melodic hooks over synths with sharp, rhythmic Korean rap verses "
                   "that cut through the electronic layers."),
    "jazz":     ("distinctive female vocalist — warm, smoky raspy alto. "
                 "Swinging melodic phrasing with cool, jazz-inflected Korean rap verses "
                 "that feel improvised and intimate."),
}

def _voice_signature_for_genre(genre: str) -> str:
    """Return genre-appropriate voice description. K-Rap always present, delivery adapted."""
    gl = genre.lower() if genre else ""
    for key, sig in _VOICE_BY_GENRE.items():
        if key in gl:
            return sig
    # Default: punk energy (Ailey's core identity)
    return AILEY_VOICE_SIGNATURE

# ---------------------------------------------------------------------------
# Mood → Key Intelligence — Musical key selection based on emotional context
# ---------------------------------------------------------------------------
# Problem: D minor is NOT always right. "Press F to Reset" (aggressive, gamer rage)
# got D minor → sounded too melancholic/sad instead of energetic/powerful.
#
# Music theory: Major keys feel brighter/happier, minor keys darker/sadder.
# But specific keys have distinct "colors" (well-known in composition):
#   - D minor: melancholic, serious, introspective (Mozart's Requiem)
#   - E minor: aggressive, driving, heavy (most metal is in E minor/Drop D)
#   - A minor: neutral-dark, versatile (the "default" minor key)
#   - C major: bright, triumphant, "happy" (wedding marches)
#   - G major: warm, uplifting, anthemic (countless pop hits)
#   - Bb major: bold, warm, brassy (jazz, soul, powerful pop)
#
# This map lets ACE-Step pick the RIGHT key for the emotional intent.
# The mood keywords are matched case-insensitively against the mood parameter
# and caption text. First match wins.

_MOOD_KEY_MAP = {
    # ── Aggressive / High-Energy → E minor (power, drive, not sad) ──
    "aggressive":    "E minor",
    "rage":          "E minor",
    "angry":         "E minor",
    "furious":       "E minor",
    "gamer":         "E minor",
    "intense":       "E minor",
    "fierce":        "E minor",
    "unrelenting":   "E minor",
    "brutal":        "E minor",
    "heavy":         "E minor",
    "crushing":      "E minor",

    # ── Energetic / Upbeat / Fun → G major or E major ──
    "energetic":     "G major",
    "upbeat":        "G major",
    "fun":           "G major",
    "playful":       "E major",
    "catchy":        "E major",
    "bright":        "E major",
    "high-energy":   "E major",
    "dance":         "E major",
    "danceable":     "E major",
    "vibrant":       "E major",
    "colorful":      "E major",

    # ── Triumphant / Powerful / Anthemic → Bb major or D major ──
    "triumphant":    "Bb major",
    "powerful":      "Bb major",
    "anthemic":      "Bb major",
    "epic":          "Bb major",
    "soaring":       "Bb major",
    "victorious":    "D major",
    "heroic":        "D major",
    "confident":     "D major",
    "bold":          "D major",

    # ── Warm / Hopeful / Uplifting → C major or A major ──
    "warm":          "C major",
    "hopeful":       "C major",
    "uplifting":     "C major",
    "inspiring":     "C major",
    "optimistic":    "A major",
    "joyful":        "A major",
    "happy":         "C major",
    "cheerful":      "C major",
    "youthful":      "G major",

    # ── Melancholic / Sad / Emotional → A minor or D minor ──
    "melancholic":   "A minor",
    "sad":           "A minor",
    "emotional":     "A minor",
    "heartbreaking": "A minor",
    "vulnerable":    "A minor",
    "intimate":      "A minor",
    "lonely":        "A minor",
    "bittersweet":   "D minor",
    "nostalgic":     "D minor",
    "wistful":       "D minor",

    # ── Dark / Gothic / Sinister → C# minor or F# minor ──
    "dark":          "C# minor",
    "sinister":      "C# minor",
    "gothic":        "G minor",
    "haunting":      "G minor",
    "eerie":         "F# minor",
    "creepy":        "F# minor",
    "mysterious":    "F# minor",
    "ominous":       "C# minor",

    # ── Dreamy / Atmospheric → F major or Ab major ──
    "dreamy":        "F major",
    "atmospheric":   "F major",
    "ethereal":      "Ab major",
    "spacey":        "Ab major",
    "ambient":       "F major",
    "floating":      "Ab major",

    # ── Rebellious / Punk / Defiant → D major or E minor ──
    "rebellious":    "D major",
    "defiant":       "D major",
    "punk":          "E minor",
    "anarchic":      "E minor",
    "chaotic":       "E minor",

    # ── Smooth / Chill / Groovy → Bb major or Eb major ──
    "smooth":        "Bb major",
    "chill":         "Eb major",
    "groovy":        "Bb major",
    "soulful":       "Bb major",
    "laid-back":     "Eb major",
    "relaxed":       "Eb major",
}


def suggest_key_for_mood(mood: str, genre: str = "", caption: str = "") -> str:
    """Suggest a musical key based on mood, genre, and caption text.

    Scans mood parameter, genre, and full caption for emotional keywords.
    Returns a key like "E minor" or "G major", or empty string if no match.

    Priority: mood parameter > genre text > caption text.
    Within each text, the keyword that appears EARLIEST wins (leftmost match).
    This ensures "smooth, warm" → Bb major (smooth first), not C major (warm).
    """
    search_texts = [
        mood.lower() if mood else "",
        genre.lower() if genre else "",
        caption.lower() if caption else "",
    ]

    for text in search_texts:
        if not text:
            continue
        # Find ALL matching keywords and their position in the text.
        # The keyword appearing earliest (leftmost) wins.
        best_pos = len(text) + 1
        best_key = ""
        for keyword, key in _MOOD_KEY_MAP.items():
            pos = text.find(keyword)
            if pos != -1 and pos < best_pos:
                best_pos = pos
                best_key = key
        if best_key:
            return best_key

    return ""


# Short tag version for appending to comma-tag sections
AILEY_VOICE_TAGS = (
    "female vocal, raspy powerful voice, melodic yet aggressive, "
    "clean to scream transitions, Korean rap sections, bilingual vocals"
)

# Default full caption for Ailey's signature K-Rap/Punk sound
AILEY_DEFAULT_CAPTION = (
    "metalcore, punk rock, k-rap fusion, aggressive female vocal, "
    "screamo, electronic elements, bilingual English-Korean. "
    "An intense punk anthem featuring a " + AILEY_VOICE_SIGNATURE + " "
    "Drop-tuned distorted guitars, relentless drums, atmospheric synth pads, "
    "and glitchy electronic textures. 155 BPM, D minor, fierce and emotionally charged."
)

# ---------------------------------------------------------------------------
# Genre Presets — HYBRID CAPTIONS (Tags + Natural Description)
# ---------------------------------------------------------------------------
# ACE-Step 1.5 Guide says: Hybrid format (tags + description) produces the
# best results. Pure comma-tags are too sparse and lead to generic output.
#
# Format: "tag1, tag2, tag3. Natural language description with specific
# references, instruments, production style, and vocal character."
#
# AILEY_VOICE_SIGNATURE is appended automatically by build_ace_caption().

GENRE_PRESETS = {
    # ═══════════════════════════════════════════════════════════════════
    # TOP PICKS — the "DO I DREAM" signature sound
    # ═══════════════════════════════════════════════════════════════════
    "metalcore-k-pop-crossover": (
        "metalcore, k-pop crossover, aggressive vocals, melodic singing, female vocals, "
        "korean rap, english lyrics, heavy guitar riffs, double bass drums, "
        "electronic synth layers, emotional, anthemic chorus, breakdown, screamed vocals, "
        "powerful, rebellious, modern production, dynamic range, orchestral elements. "
        "A genre-defying metalcore anthem fusing crushing Western metal with K-Pop precision and K-Rap fury. "
        "Drop-tuned distorted guitars and rapid double bass drumming collide with polished K-Pop melodic hooks. "
        "Epic cinematic synthesizer stabs at 3 key transitions — massive, reverb-drenched synth swells "
        "that hit like a wall at the pre-chorus, bridge, and final chorus. These synth moments are ICONIC — "
        "electronic textures that elevate the metal into something cinematic and devastating. "
        "Vocals shift between clean melodic singing, aggressive Korean rap delivery, and raw screams. "
        "Inspired by Bring Me The Horizon meets Stray Kids meets Spiritbox. "
        "160 BPM, drop C tuning, D minor, fierce, epic, anthemic, emotionally devastating."
    ),
    "punk-k-pop-crossover": (
        "punk rock, k-pop crossover, aggressive female vocal, melodic singing, korean rap, "
        "english lyrics, distorted guitars, fast drums, electronic synth layers, "
        "anthemic chorus, catchy, rebellious, modern production, bilingual English-Korean. "
        "A high-octane punk anthem infused with K-Pop polish and K-Rap precision. "
        "Fast distorted power chords and driving drums meet bright melodic hooks and rapid Korean rap verses. "
        "Epic cinematic synthesizer stabs at key transitions — massive electronic swells "
        "that contrast the raw punk aggression with moments of anthemic beauty. "
        "Vocals shift between catchy punk singing, fierce Korean rap, and raw screamed breakdowns. "
        "Inspired by Paramore meets Stray Kids meets Bring Me The Horizon. "
        "170 BPM, E minor, fierce, catchy, rebellious, anthemic, punk energy meets K-Pop precision."
    ),
    # ═══════════════════════════════════════════════════════════════════
    # K-Rap / Metal / Punk hybrids
    # ═══════════════════════════════════════════════════════════════════
    "k-rap-punk": (
        "K-Rap, punk rock, metalcore, aggressive female vocal, screamo, electronic elements, "
        "electronic synth layers, bilingual English-Korean. "
        "A high-energy punk anthem blending Western punk aggression with Korean rap precision. "
        "Drop-tuned distorted guitars, pounding drums, 808 bass hits. "
        "Epic cinematic synthesizer stabs at key transitions — massive reverb-drenched synth swells "
        "that hit like a wall. Reminiscent of Bring Me The Horizon meets Stray Kids. "
        "155 BPM, D minor, fierce, rebellious, emotionally charged."
    ),
    "k-rap-metal": (
        "metalcore, K-Rap, heavy metal, aggressive female vocal, screamo, "
        "electronic synth layers, bilingual English-Korean, distorted guitars, double bass drums. "
        "A crushing metalcore track with rapid Korean rap verses over heavy distorted riffs. "
        "Double bass drumming, drop-tuned 7-string guitars, massive breakdowns, blast beats. "
        "The GUITARS and DRUMS dominate — Korean rap adds intensity but metal is the foundation. "
        "Epic cinematic synth stabs at transitions — massive electronic swells that add devastating weight. "
        "Production style reminiscent of Architects meets (G)I-DLE meets Spiritbox. "
        "170 BPM, E minor, dark, intense, unrelenting metalcore fury."
    ),
    "metal": (
        "metal, heavy metal, aggressive, heavy, female vocal, electronic synth layers, orchestral elements. "
        "A devastating metal track with drop-tuned distorted guitars, thunderous double bass drumming, "
        "crushing breakdowns, and fierce vocals alternating between melodic singing and raw screams. "
        "Epic cinematic synthesizer stabs at key transitions — massive, reverb-drenched synth swells "
        "that hit like a wall at the pre-chorus, bridge, and final chorus. "
        "Electronic textures weave through the heavy guitars creating a modern, cinematic heaviness. "
        "Inspired by Bring Me The Horizon meets Spiritbox meets Architects. "
        "160 BPM, D minor, heavy, intense, epic, cathartic, unrelenting."
    ),
    "symphonic-metal": (
        "symphonic metal, orchestral metal, epic, cinematic, female vocal, operatic, heavy guitar riffs, "
        "orchestra, choir, double bass drums, powerful, dramatic, electronic synth layers. "
        "A grandiose symphonic metal track fusing thundering distorted guitars and double bass drumming "
        "with sweeping orchestral arrangements — strings, brass, and choir. "
        "The vocalist alternates between powerful clean singing with operatic range and fierce screamed passages. "
        "Epic cinematic synthesizer stabs and orchestral swells at key transitions create "
        "a massive, cathedral-sized wall of sound. Dramatic key changes in the bridge. "
        "Inspired by Nightwish meets Epica meets Jinjer. "
        "155 BPM, D minor, epic, dramatic, cinematic, powerful, orchestral devastation."
    ),
    "k-pop-metal-fusion": (
        "K-Pop metal fusion, metalcore, K-Rap, aggressive female vocal, electronic synth layers, "
        "bilingual English-Korean. "
        "A genre-defying fusion of K-Pop precision and metalcore brutality. "
        "Polished K-Pop melodic hooks crash into crushing metal breakdowns with drop-tuned guitars. "
        "Epic cinematic synthesizer stabs at key transitions, rapid Korean rap over heavy riffs, "
        "double bass drumming, and soaring clean choruses. "
        "Inspired by (G)I-DLE meets Bring Me The Horizon meets Spiritbox. "
        "165 BPM, D minor, fierce, epic, anthemic, genre-breaking."
    ),
    "aggressive-k-rap---rock": (
        "Aggressive K-Rap, rock, metalcore, electronic synth layers, female vocal, bilingual English-Korean. "
        "A relentless K-Rap rock hybrid with aggressive Korean rap delivery over distorted guitars, "
        "pounding drums, 808 sub-bass, and epic cinematic synth stabs at transitions. "
        "Modern production blending hip-hop punch with metal weight. "
        "Inspired by Stray Kids meets Linkin Park. "
        "155 BPM, E minor, aggressive, fierce, relentless."
    ),
    "industrial-k-rap": (
        "industrial metal, K-Rap, metalcore, aggressive female vocal, distorted guitars, "
        "electronic synth layers, bilingual English-Korean, heavy drums, distorted bass. "
        "A dark industrial metal track fusing crushing distorted guitars and heavy drums "
        "with aggressive Korean rap and industrial electronic textures. "
        "Drop-tuned guitar riffs provide the foundation, with industrial noise and metallic percussion as accents. "
        "Epic cinematic synth stabs at transitions — cold, massive, reverb-drenched electronic swells. "
        "The GUITARS dominate — industrial textures add atmosphere but metal drives the track. "
        "Inspired by Rammstein meets Stray Kids meets Bring Me The Horizon. "
        "145 BPM, C minor, dark, heavy, industrial, aggressive, metallic fury."
    ),
    "indie-pop": (
        "indie pop, dreamy, melodic, atmospheric, female vocal, synth-driven. "
        "A shimmering indie pop track with lush synth pads, acoustic guitar layers, "
        "soft programmed drums, and warm bass. Reverb-drenched vocals float over "
        "a bed of arpeggiated synthesizers. Production inspired by CHVRCHES meets Clairo. "
        "108 BPM, A major, dreamy, warm, emotionally intimate yet uplifting."
    ),
    "pop-punk": (
        "pop-punk, punk rock, catchy, energetic, female vocal, anthemic. "
        "An infectious pop-punk anthem with driving power chords, fast palm-muted guitars, "
        "punchy drums, and a singalong chorus. Clean production with raw vocal energy. "
        "Reminiscent of Paramore meets Olivia Rodrigo. "
        "168 BPM, G major, energetic, rebellious, catchy, youthful defiance."
    ),
    "synth-pop": (
        "synth-pop, electronic, retro, 80s inspired, female vocal, danceable. "
        "A vibrant synth-pop track with lush analog synthesizers, pulsing drum machines, "
        "shimmering arpeggios, and a groovy bass synth line. Polished production with "
        "neon-lit atmosphere. Inspired by The Midnight meets CHVRCHES. "
        "122 BPM, F major, danceable, vibrant, nostalgic yet modern."
    ),
    "acoustic-folk": (
        "acoustic folk, singer-songwriter, intimate, emotional, female vocal. "
        "A delicate acoustic track built around fingerpicked guitar, soft cello swells, "
        "gentle piano, and minimal percussion. Stripped-back production that puts the "
        "vocal performance center stage. Warm and confessional, inspired by Phoebe Bridgers. "
        "84 BPM, C major, intimate, warm, heartfelt, storytelling."
    ),
    "grunge": (
        "grunge, alternative rock, 90s, raw, distorted, female vocal, angsty. "
        "A gritty grunge track with heavily distorted guitars, loose drumming, "
        "rumbling bass, and feedback-drenched transitions. Lo-fi recording aesthetic "
        "with dynamic quiet-loud-quiet structure. Reminiscent of Hole meets Nirvana. "
        "118 BPM, B minor, raw, angsty, melancholic, cathartic."
    ),
    "dark-cabaret": (
        "dark cabaret, theatrical, gothic, dramatic, female vocal, piano-driven. "
        "A theatrical dark cabaret piece featuring dramatic piano, sweeping strings, "
        "marching drums, and accordion accents. Gothic atmosphere with vaudeville flair. "
        "Reminiscent of Amanda Palmer meets Florence + The Machine. "
        "96 BPM, G minor, theatrical, haunting, dramatic, darkly beautiful."
    ),
    "electronic-rock": (
        "electronic rock, synth rock, industrial, driving, female vocal, aggressive. "
        "A hard-hitting electronic rock track fusing heavy synth bass, distorted guitars, "
        "programmed drums, and glitchy electronic textures. Futuristic production with "
        "a wall-of-sound approach. Inspired by Grimes meets Nine Inch Nails. "
        "135 BPM, C minor, driving, aggressive, futuristic, intense."
    ),
    "ballad": (
        "emotional ballad, post-hardcore ballad, piano, orchestral, female vocal, powerful. "
        "A deeply emotional ballad beginning with delicate piano and vulnerable vocals, "
        "gradually building with strings, cello, and soft drums into a powerful crescendo. "
        "Dynamic range from whispered intimacy to soaring catharsis. "
        "Inspired by Sleeping With Sirens meets Adele. "
        "72 BPM, A minor, slow, intimate, heartbreaking, powerful crescendo."
    ),
    "riot-grrrl": (
        "riot grrrl, punk, feminist punk, raw, fast, aggressive female vocal. "
        "A furious riot grrrl track with buzzsaw guitars, pounding drums, distorted bass, "
        "and raw, in-your-face vocals. Lo-fi recording aesthetic, garage energy. "
        "Inspired by Bikini Kill meets Sleater-Kinney. "
        "178 BPM, E minor, fast, angry, fierce, political, unapologetically loud."
    ),
    "k-pop-hybrid": (
        "K-Pop, pop, electronic, catchy, polished, female vocal, dance beat. "
        "A polished K-Pop influenced track with bright synth hooks, punchy drums, "
        "layered vocal harmonies, and a killer drop chorus. Crisp modern production "
        "with hip-hop influenced verses. Inspired by (G)I-DLE meets BLACKPINK. "
        "128 BPM, E major, catchy, bright, colorful, high-energy, dance-ready."
    ),
    "metalcore": (
        "metalcore, metal, aggressive, heavy, female vocal, screamo, breakdown, electronic synth layers, orchestral elements. "
        "A crushing metalcore track with drop-tuned guitars, rapid double bass drumming, "
        "blistering breakdowns, and fierce alternation between screamed and clean vocals. "
        "Epic cinematic synthesizer stabs at key transitions — massive, reverb-drenched synth swells "
        "that hit like a wall at the pre-chorus, bridge, and final chorus. "
        "Atmospheric electronic textures weave through the heavy guitars. Inspired by Architects meets Spiritbox meets Bring Me The Horizon. "
        "170 BPM, D minor, heavy, intense, unrelenting, cathartic, epic."
    ),
    "screamo": (
        "screamo, post-hardcore, emo, aggressive, emotional, female vocal, electronic synth layers. "
        "A raw screamo track with dissonant guitars, blast beats, and emotionally charged "
        "screamed vocals that crack with vulnerability. Abrupt tempo changes, "
        "delicate clean passages erupt into walls of distortion. "
        "Epic synthesizer swells mark key transitions — cinematic, reverb-heavy synth stabs "
        "that contrast the chaos with moments of devastating beauty. Inspired by Underoath meets La Dispute. "
        "165 BPM, F# minor, raw, chaotic, emotionally devastating, cathartic."
    ),
    "nu-metal": (
        "nu metal, metal, heavy, aggressive, female vocal, distorted guitars, electronic synth layers. "
        "A heavy nu-metal track with down-tuned 7-string guitars, thick distorted bass grooves, "
        "pounding drums, and massive sing-along choruses. "
        "Aggressive vocal delivery mixing melodic singing, raw screaming, and rhythmic spoken passages. "
        "Cinematic synth hits at transitions add epic electronic depth. Inspired by Linkin Park meets Korn meets Deftones. "
        "135 BPM, C# minor, heavy, aggressive, bouncy, anthemic."
    ),
    "post-hardcore": (
        "post-hardcore, punk, emo, melodic, aggressive, female vocal, electronic synth layers. "
        "A dynamic post-hardcore track oscillating between melodic singing and fierce screams. "
        "Intricate guitar work, driving bass lines, creative drum patterns, "
        "and atmospheric build-ups that explode into massive climaxes. "
        "Epic synth swells at key transitions — cinematic electronic stabs that elevate the heaviness. "
        "Inspired by Silverstein meets Pvris meets Bring Me The Horizon. "
        "155 BPM, Bb minor, dynamic, emotional, fierce, melodic yet heavy."
    ),
}


def _ensure_dirs():
    """Create required directories."""
    os.makedirs(SONGS_DIR, exist_ok=True)


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


# ---------------------------------------------------------------------------
# Availability Check
# ---------------------------------------------------------------------------

def is_ace_step_available() -> bool:
    """Check if ACE-Step v1.5 is installed and ready.

    Lightweight check — only verifies directory structure and key files exist.
    Does NOT spawn a subprocess or import PyTorch (which hangs for 30+ seconds
    and can time out, causing false "model unavailable" errors).

    Also respects the sprint lock file — when _song_sprint.py is running,
    ACE-Step is reserved exclusively for the batch job.
    """
    # Sprint lock — external batch script has exclusive ACE-Step access
    if os.path.isfile(ACE_LOCK_FILE):
        print("[MusicGen] 🔒 ACE-Step locked by _song_sprint.py — skipping")
        return False
    if not os.path.isdir(ACE_STEP_DIR):
        print(f"[MusicGen] ❌ ACE-Step dir missing: {ACE_STEP_DIR}")
        return False
    if not os.path.isfile(ACE_STEP_PYTHON):
        print(f"[MusicGen] ❌ ACE-Step venv python missing: {ACE_STEP_PYTHON}")
        return False
    if not os.path.isfile(_ACE_SCRIPT):
        print(f"[MusicGen] ❌ ace_generate.py missing: {_ACE_SCRIPT}")
        return False
    # Check that the acestep package directory exists (without importing it)
    _pkg_dir = os.path.join(ACE_STEP_DIR, "acestep")
    if not os.path.isdir(_pkg_dir) or not os.path.isfile(os.path.join(_pkg_dir, "__init__.py")):
        print(f"[MusicGen] ❌ acestep package dir missing: {_pkg_dir}")
        return False
    # Check that handler.py exists (the key module)
    if not os.path.isfile(os.path.join(_pkg_dir, "handler.py")):
        print(f"[MusicGen] ❌ acestep/handler.py missing")
        return False
    return True


# ---------------------------------------------------------------------------
# Idle Generation Limits
# ---------------------------------------------------------------------------

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


def can_generate_idle_song() -> bool:
    """Check if Ailey can generate another idle song today (max 1/day)."""
    status = _read_gen_status()
    today = datetime.now().strftime("%Y-%m-%d")
    if status.get("date") != today:
        return True
    return status.get("count", 0) < MAX_IDLE_SONGS_PER_DAY


def mark_idle_song_generated():
    """Increment today's idle song generation counter."""
    status = _read_gen_status()
    today = datetime.now().strftime("%Y-%m-%d")
    if status.get("date") != today:
        status = {"date": today, "count": 1}
    else:
        status["count"] = status.get("count", 0) + 1
    _write_gen_status(status)


# ---------------------------------------------------------------------------
# Caption Builder — converts song metadata to ACE-Step HYBRID caption format
# ---------------------------------------------------------------------------
# ACE-Step 1.5 Guide: Hybrid format (tags + natural description) is BEST.
# Pure comma-tags are too sparse → generic male voice.
# Hybrid = "tag1, tag2, tag3. Natural description paragraph."

def build_ace_caption(
    genre: str = "",
    mood: str = "",
    tempo: str = "",
    vocals: str = "female",
    language: str = "English",
    extra_tags: str = "",
    llm_tags: str = "",
    include_voice_signature: bool = True,
) -> str:
    """
    Build ACE-Step HYBRID caption (tags + natural description).

    ACE-Step 1.5 produces DRAMATICALLY better results with hybrid captions:
      "metalcore, punk rock, k-rap fusion, aggressive female vocal.
       An intense punk anthem featuring a distinctive vocalist who switches
       between melodic singing and aggressive Korean rap delivery. Distorted
       guitars, pounding drums, atmospheric synths. 155 BPM, D minor."

    vs. sparse tags like "K-Rap Punk" → generic male rap.

    The hybrid system:
    ═══════════════════════════════════════════════════════════════════
    1. GENRE PRESET or AUTO-BUILT caption (instruments, BPM, description)
    2. LLM CREATIVE TAGS merged in (mood, texture, production style)
    3. AILEY_VOICE_SIGNATURE always appended (consistent vocal identity)
    ═══════════════════════════════════════════════════════════════════
    """
    # ── 1. Try to match a genre preset (already hybrid format) ──
    genre_key = genre.lower().replace(" ", "-").replace("/", "-")
    if genre_key in GENRE_PRESETS:
        base = GENRE_PRESETS[genre_key]
    else:
        # ── 2. Auto-build hybrid caption from components ──
        gl = genre.lower() if genre else ""

        # Determine instruments, BPM, and description based on genre keywords
        if any(w in gl for w in ("metal", "metalcore", "screamo", "hardcore")):
            tag_part = f"{genre}, aggressive, distorted guitars, bass, drums, electronic synth layers, orchestral elements"
            desc_part = (
                f"A crushing {genre} track with drop-tuned distorted guitars, "
                f"driving double bass drums, heavy bass, and epic cinematic synthesizer stabs "
                f"at key transitions — massive reverb-drenched synth swells that hit like a wall."
            )
            default_bpm = "160 BPM"
            fallback_key = "D minor"
            default_mood = "aggressive, raw, intense, epic"
        elif any(w in gl for w in ("rock", "punk", "grunge")):
            tag_part = f"{genre}, aggressive, distorted guitars, bass, drums"
            desc_part = (
                f"A hard-hitting {genre} track with distorted electric guitars, "
                f"driving drums, and heavy bass."
            )
            default_bpm = "145 BPM"
            fallback_key = "E minor"  # rock/punk default — aggressive energy, not sad
            default_mood = "aggressive, raw, intense"
        elif any(w in gl for w in ("pop", "k-pop", "kpop")):
            tag_part = f"{genre}, catchy, melodic, synth, drums, bass, guitar"
            desc_part = (
                f"A polished {genre} track with bright synth hooks, punchy drums, "
                f"layered vocal harmonies, and a catchy chorus."
            )
            default_bpm = "120 BPM"
            fallback_key = "E major"
            default_mood = "catchy, bright, upbeat"
        elif any(w in gl for w in ("rap", "hip hop", "hip-hop", "trap")):
            tag_part = f"{genre}, 808 bass, hi-hats, synth, drums, aggressive"
            desc_part = (
                f"A hard-hitting {genre} track with deep 808 bass, crisp hi-hats, "
                f"atmospheric synth layers, and rapid-fire vocal delivery."
            )
            default_bpm = "150 BPM"
            fallback_key = "E minor"
            default_mood = "aggressive, intense, confident"
        elif any(w in gl for w in ("folk", "acoustic", "singer-songwriter")):
            tag_part = f"{genre}, acoustic guitar, piano, soft percussion, intimate"
            desc_part = (
                f"A delicate {genre} track built around fingerpicked acoustic guitar, "
                f"gentle piano, and minimal percussion. Warm and confessional."
            )
            default_bpm = "84 BPM"
            fallback_key = "C major"
            default_mood = "intimate, warm, heartfelt"
        elif any(w in gl for w in ("electronic", "edm", "techno")):
            tag_part = f"{genre}, synth, drum machine, bass synth, electronic"
            desc_part = (
                f"A driving {genre} track with pulsing synthesizers, programmed drums, "
                f"heavy bass synth, and atmospheric electronic textures."
            )
            default_bpm = "138 BPM"
            fallback_key = "A minor"
            default_mood = "driving, energetic, futuristic"
        elif any(w in gl for w in ("ballad", "slow")):
            tag_part = f"{genre}, piano, strings, cello, emotional, orchestral"
            desc_part = (
                f"A deeply emotional ballad beginning with delicate piano and vulnerable "
                f"vocals, gradually building with strings and soft drums into a powerful crescendo."
            )
            default_bpm = "72 BPM"
            fallback_key = "A minor"
            default_mood = "emotional, intimate, powerful crescendo"
        elif any(w in gl for w in ("jazz", "blues", "soul")):
            tag_part = f"{genre}, piano, bass, drums, saxophone, smooth"
            desc_part = (
                f"A smooth {genre} track with warm piano, walking bass, brushed drums, "
                f"and expressive saxophone."
            )
            default_bpm = "100 BPM"
            fallback_key = "Bb major"
            default_mood = "smooth, warm, soulful"
        else:
            # Generic fallback — still produce a rich caption
            tag_part = f"{genre}, guitar, bass, drums, synth" if genre else "rock, guitar, bass, drums, synth"
            desc_part = (
                f"A dynamic track with layered guitars, solid drums, "
                f"bass, and atmospheric synth textures."
            )
            default_bpm = "120 BPM"
            fallback_key = "A minor"
            default_mood = "energetic, dynamic"

        # ── Intelligent Key Selection ──
        # Use mood→key mapping if mood provides a clear emotional signal.
        # Falls back to genre-appropriate default if no mood keyword matches.
        mood_str = mood if mood else default_mood
        suggested_key = suggest_key_for_mood(mood_str, genre, llm_tags)
        default_key = suggested_key if suggested_key else fallback_key

        # Map tempo to BPM
        _TEMPO_BPM = {
            "slow": "72 BPM", "medium": "110 BPM", "fast": "145 BPM",
            "very fast": "175 BPM", "mid-tempo": "100 BPM",
        }
        bpm = _TEMPO_BPM.get(tempo.lower(), f"{tempo}" if tempo else default_bpm)
        if not any(c.isdigit() for c in bpm):
            bpm = default_bpm

        mood_str = mood if mood else default_mood

        base = f"{tag_part}, {mood_str}. {desc_part} {bpm}, {default_key}, {mood_str}."

    # ── 3. Merge LLM creative tags (from Ailey's [Tags: ...] line) ──
    if llm_tags:
        llm_items = [t.strip() for t in llm_tags.split(",") if t.strip()]
        base_lower = base.lower()
        new_items = []
        for item in llm_items:
            item_core = item.lower().strip()
            if not item_core:
                continue
            # Skip if exact tag already in base (substring match)
            if item_core in base_lower:
                continue
            # Skip voice-related LLM tags — voice signature handles that
            if any(v in item_core for v in (
                "female vocal", "male vocal", "singer", "alto", "husky",
                "soprano", "tenor", "baritone", "raspy", "vocal",
                "bilingual", "korean rap",
            )):
                continue
            # Skip non-musical abstract tags
            if item_core in (
                "meme punctuation", "meme-infused", "meme infused",
                "queer", "lgbtq", "feminist", "political",
                "rebellious",
            ):
                continue
            # Skip tags that are just adjective+noun where the adjective
            # already appears 2+ times in the base caption
            first_word = item_core.split()[0] if item_core.split() else ""
            if first_word and base_lower.count(first_word) >= 2:
                continue
            new_items.append(item.strip())
        if new_items:
            # Insert creative tags before the final period/description
            base = base.rstrip(".") + ", " + ", ".join(new_items) + "."

    # ── 4. Append extra tags from header parsing ──
    if extra_tags:
        base = base.rstrip(".") + ", " + extra_tags + "."

    # ── 5. ALWAYS append voice signature for consistent Ailey identity ──
    if include_voice_signature and "Korean rap" not in base:
        _vsig = _voice_signature_for_genre(genre)
        base = base.rstrip(".") + ". The vocalist is a " + _vsig
    elif include_voice_signature and "punkier Miley Cyrus" not in base and "The vocalist is" not in base:
        # Already has "Korean rap" mention from tags but no voice block yet
        _vsig = _voice_signature_for_genre(genre)
        base = base.rstrip(".") + ". The vocalist is a " + _vsig

    # ── 6. Deduplicate tags — remove repeated adjectives & nonsense tags ──
    base = _deduplicate_caption(base)

    return base


# Backwards-compatible alias — old code calls build_ace_tags()
def build_ace_tags(
    genre: str = "",
    mood: str = "",
    tempo: str = "",
    vocals: str = "female",
    language: str = "English",
    extra_tags: str = "",
    llm_tags: str = "",
    include_voice_signature: bool = True,
) -> str:
    """Alias for build_ace_caption() — backwards compatibility.

    Accepts the same positional+keyword args as build_ace_caption so callers
    can use either positional or keyword style.
    """
    return build_ace_caption(
        genre=genre, mood=mood, tempo=tempo, vocals=vocals,
        language=language, extra_tags=extra_tags, llm_tags=llm_tags,
        include_voice_signature=include_voice_signature,
    )


# ---------------------------------------------------------------------------
# Caption Post-Processing — Deduplicate & Clean
# ---------------------------------------------------------------------------

def _deduplicate_caption(caption: str) -> str:
    """Remove redundant adjectives and repeated words/phrases from a caption.

    ACE-Step attention is diluted by repeated terms — "aggressive" 5x is worse
    than "aggressive" 1x.  This function:
      1. Splits caption into tag-part (before first ".") and description-part
      2. Deduplicates comma-separated tags (case-insensitive)
      3. Removes non-musical nonsense tags ("meme punctuation", "queer", etc.)
      4. Skips tags that are already covered by words in the description
    """
    if not caption:
        return caption

    # Non-musical tags that confuse ACE-Step (no musical meaning)
    _NONSENSE_TAGS = {
        "meme punctuation", "meme-infused", "meme infused",
        "queer", "lgbtq", "feminist", "political",
        "rebellious",  # too abstract — doesn't translate to audio
    }

    # Split at first period+space — tags vs description
    dot_idx = caption.find(". ")
    if dot_idx == -1:
        tag_part = caption
        desc_part = ""
    else:
        tag_part = caption[:dot_idx]
        desc_part = caption[dot_idx + 2:]

    desc_lower = desc_part.lower()

    # Deduplicate comma-tags
    tags = [t.strip() for t in tag_part.split(",") if t.strip()]
    seen = set()
    deduped_tags = []
    for tag in tags:
        tag_lower = tag.lower()
        # Skip nonsense tags
        if tag_lower in _NONSENSE_TAGS:
            continue
        # Skip if already seen (case-insensitive)
        if tag_lower in seen:
            continue
        # Skip single-word tags that already appear in the description
        # (e.g. "aggressive" as standalone tag when description says "aggressive drums")
        # But keep multi-word tags like "aggressive synth stabs" — they add specificity
        tag_words = tag_lower.split()
        if len(tag_words) == 1 and tag_lower in desc_lower:
            continue
        seen.add(tag_lower)
        deduped_tags.append(tag)

    result = ", ".join(deduped_tags)
    if desc_part:
        # Also deduplicate repeated words in the description part
        # e.g. "suspended, suspended, weightless, weightless" in mood lists
        # Split desc into sentences/clauses and remove exact duplicate phrases
        _desc_words_seen: set = set()
        _desc_cleaned_parts = []
        for _clause in re.split(r',\s*', desc_part):
            _clause_stripped = _clause.strip().rstrip('.')
            _clause_lower = _clause_stripped.lower()
            if _clause_lower and _clause_lower not in _desc_words_seen:
                _desc_words_seen.add(_clause_lower)
                _desc_cleaned_parts.append(_clause_stripped)
        result += ". " + ", ".join(_desc_cleaned_parts)

    return result


def extract_bpm_from_caption(caption: str) -> Optional[int]:
    """Extract BPM integer from caption text like '145 BPM' or '145bpm'.

    Returns the BPM as int, or None if not found.
    Used to set GenerationParams.bpm explicitly so the 0.6B LM
    can't override it with a wrong value.
    """
    m = re.search(r'\b(\d{2,3})\s*BPM\b', caption, re.IGNORECASE)
    if m:
        bpm = int(m.group(1))
        if 30 <= bpm <= 300:
            return bpm
    return None


def extract_key_from_caption(caption: str) -> str:
    """Extract musical key from caption like 'D minor' or 'E major'.

    Returns the key string (e.g. 'D minor'), or empty string if not found.
    """
    m = re.search(r'\b([A-G][#b♯♭]?\s+(?:major|minor|maj|min))\b', caption, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Lyrics Length Limiter
# ---------------------------------------------------------------------------

# ACE-Step v1.5 struggles with very long lyrics — sections get rushed,
# pronunciation suffers, and the model tries to cram everything in.
# Optimal range: 200-350 words of actual lyrics (excluding section markers).
ACE_MAX_LYRIC_WORDS = 400
ACE_WARN_LYRIC_WORDS = 350

def check_lyrics_length(lyrics: str) -> dict:
    """Check lyrics length and return stats.

    Returns dict with:
      - word_count: int
      - section_count: int
      - is_too_long: bool
      - recommendation: str (empty if fine)
    """
    if not lyrics:
        return {"word_count": 0, "section_count": 0, "is_too_long": False, "recommendation": ""}

    # Count section markers
    sections = re.findall(r'\[.*?\]', lyrics)
    section_count = len(sections)

    # Count actual lyric words (strip markers and blank lines)
    clean = re.sub(r'\[.*?\]', '', lyrics)
    words = clean.split()
    word_count = len(words)

    is_too_long = word_count > ACE_MAX_LYRIC_WORDS
    recommendation = ""
    if is_too_long:
        recommendation = (
            f"Lyrics haben {word_count} Wörter ({section_count} Sections) — "
            f"ACE-Step funktioniert am besten mit max ~{ACE_MAX_LYRIC_WORDS} Wörtern. "
            f"Empfehlung: Einen Verse oder eine Chorus-Wiederholung kürzen."
        )
    elif word_count > ACE_WARN_LYRIC_WORDS:
        recommendation = (
            f"Lyrics haben {word_count} Wörter — nah am Limit ({ACE_MAX_LYRIC_WORDS}). "
            f"Qualität könnte bei kürzeren Lyrics besser sein."
        )

    return {
        "word_count": word_count,
        "section_count": section_count,
        "is_too_long": is_too_long,
        "recommendation": recommendation,
    }


def parse_suno_to_ace(raw_song_output: str) -> Tuple[str, str]:
    """
    Parse Ailey's song output into clean ACE-Step (caption, lyrics).

    Input: Ailey writes songs with markdown formatting, code fences, stage
    directions, creative section names, etc. This function strips markdown
    and produces clean ACE-Step format.

    ACE-Step 1.5 format:
    ──────────────────────────────────────────────────────────────────
    Caption (prompt):
      Hybrid format: "tag1, tag2, tag3. Natural description paragraph."
      Built by build_ace_caption() from [Genre:] header + [Tags:] line.

    Lyrics:
      Section tags WITH performance cues (ACE-Step 1.5 uses them!):
        [Verse 1 - Aggressive Korean rap, staccato delivery]
        [Chorus - Full screamo, wall of sound, all instruments]
        [Bridge - Melodic, vulnerable, stripped back]
      Plain text lyrics between sections.
      Empty lines separate sections.
      NO markdown (**, *, ###, ```)
      Korean/CJK text is fine — kept as-is.

    Returns:
        (caption_string, lyrics_string)
    """
    # ── 0. Pre-clean: strip code fences, normalize line endings ──
    text = raw_song_output.strip()
    # Remove code fences (```...``` wrapping)
    text = re.sub(r'^```[a-zA-Z]*\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    lines = text.split("\n")

    # ── 1. Extract genre/style header ────────────────────────────────
    genre = ""
    mood = ""
    tempo = ""
    vocals = "female"
    extra_tags_from_header: list[str] = []

    # Match [Genre: ...] or **[Genre: ...]** or ### [Genre: ...]
    genre_header = re.search(
        r'(?:\*{0,2})\[(?:Genre|Style)[:\s]*([^\]]+)\](?:\*{0,2})',
        text, re.IGNORECASE,
    )
    if genre_header:
        header_text = genre_header.group(1)
        for field in header_text.split(","):
            field = field.strip()
            if ":" in field:
                key, val = field.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key in ("genre", "style"):
                    genre = val
                elif key == "mood":
                    mood = val
                elif key == "tempo":
                    tempo = val
                elif key in ("vocals", "voice"):
                    vocals = val
                elif key in ("instruments", "production", "energy"):
                    extra_tags_from_header.append(val)
            else:
                if not genre:
                    genre = field
                else:
                    extra_tags_from_header.append(field)

    # ── 1b. Extract LLM creative tags from [Tags: ...] line ─────────
    # Ailey writes a [Tags: mood, tempo feel, special instruments, ...]
    # line in her song output. These are per-song creative additions that
    # the hybrid system merges with the fixed skeleton.
    llm_creative_tags = ""
    tags_line_match = re.search(
        r'(?:\*{0,2})\[Tags?[:\s]*([^\]]+)\](?:\*{0,2})',
        text, re.IGNORECASE,
    )
    if tags_line_match:
        llm_creative_tags = tags_line_match.group(1).strip()

    tags = build_ace_tags(genre, mood, tempo, vocals,
                          extra_tags=", ".join(extra_tags_from_header),
                          llm_tags=llm_creative_tags)

    # ── 2. Extract & clean lyrics ────────────────────────────────────

    # Section marker regex — handles all combinations:
    # [Verse 1], **[Chorus]**, ### [Bridge — guitar solo], *[Outro]*
    _SECTION_RE = re.compile(
        r'^\s*(?:[#*`]*\s*)*\[([^\]]+)\](?:\s*[#*`]*)*\s*$',
        re.IGNORECASE,
    )

    # Normalise creative section names → ACE-Step known names
    # ACE-Step 1.5 supports performance cues INSIDE section tags:
    #   [Verse 1 - Aggressive Korean rap, staccato delivery]
    #   [Chorus - Full screamo, wall of sound]
    # We normalise the section NAME but PRESERVE the performance cue.
    _SECTION_MAP = {
        "verse": "Verse", "verse 1": "Verse 1", "verse 2": "Verse 2",
        "verse 3": "Verse 3", "verse 4": "Verse 4",
        "chorus": "Chorus", "bridge": "Bridge",
        "intro": "Intro", "outro": "Outro",
        "pre-chorus": "Pre-Chorus", "pre chorus": "Pre-Chorus",
        "hook": "Chorus", "refrain": "Chorus",
        "post-chorus": "Chorus", "post chorus": "Chorus",
        "instrumental": "Instrumental", "inst": "Instrumental",
        "rap": "Rap Verse", "rap break": "Rap Verse", "rap verse": "Rap Verse",
        "korean rap": "Rap Verse", "korean rap break": "Rap Verse",
        "breakdown": "Breakdown", "metal breakdown": "Breakdown",
        "final chorus": "Chorus", "last chorus": "Chorus",
        "drop": "Chorus", "interlude": "Bridge",
        "spoken": "Verse", "spoken word": "Verse",
        "scream section": "Scream Section",
        "guitar solo": "Guitar Solo",
        "end": "Outro",
    }

    # Stage direction detection
    _STAGE_DIR_RE = re.compile(r'^\s*\(.*\)\s*$')
    _INLINE_PARENS_RE = re.compile(
        r'\([^)]*(?:scream|whisper|spoken|rap|growl|chant|sing|'
        r'sung|aggressive|controlled|switch|intimate|raw|fad|'
        r'explo|build|strip|process|voice|vocal|guitar|'
        r'piano|drum|palm|heav|half|grit|attitude|repeat|'
        r'louder|softer|slow|fast|double|melody|harmony|'
        r'gesprochen|wiederholt|lauter|leiser)[^)]*\)',
        re.IGNORECASE,
    )

    lyrics_lines: list[str] = []
    past_header = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines — preserve as section separators
        if not stripped:
            if lyrics_lines and lyrics_lines[-1] != "":
                lyrics_lines.append("")
            continue

        # Skip title line
        if re.match(r'^(?:\*{0,2})(?:Title|Titel|Song)\s*:', stripped, re.IGNORECASE):
            continue

        # Skip genre/style header
        if re.search(r'\[(?:Genre|Style)[:\s]', stripped, re.IGNORECASE):
            past_header = True
            continue

        # Skip [Tags: ...] line (already extracted above for LLM hybrid tags)
        if re.search(r'\[Tags?[:\s]', stripped, re.IGNORECASE):
            past_header = True
            continue

        # Skip trailing metadata lines
        if re.match(
            r'(?:SONGTITE?L|EMOTION|THEMEN|TOPICS?|MOTIVATION|---|\*\*\*|===|END)\s*:?',
            stripped, re.IGNORECASE,
        ):
            continue

        # Skip pure markdown decorators
        if re.match(r'^[\-=*#`]{3,}$', stripped):
            continue

        # Skip lines like "[End]", "---", "***"
        if stripped.lower() in ('[end]', '*[end]*', '**[end]**'):
            continue

        # ── Section marker? ──
        sm = _SECTION_RE.match(stripped)
        if sm:
            past_header = True
            raw_section = sm.group(1).strip()
            # Split section name from performance cue:
            # "Verse 1 — Aggressive Korean rap, staccato delivery"
            #  → section_name = "Verse 1", perf_cue = "Aggressive Korean rap, staccato delivery"
            cue_split = re.split(r'\s*[-—–]\s*', raw_section, maxsplit=1)
            core = cue_split[0].strip()
            perf_cue = cue_split[1].strip() if len(cue_split) > 1 else ""
            core = re.sub(r'[*#`]', '', core).strip()  # remove stray markdown
            core_lower = core.lower()

            # Look up normalised name
            ace_section = _SECTION_MAP.get(core_lower)
            if ace_section is None:
                for known, mapped in _SECTION_MAP.items():
                    if core_lower.startswith(known):
                        ace_section = mapped
                        break
                if ace_section is None:
                    ace_section = "Verse"  # safe default

            # Build final section tag — PRESERVE performance cue for ACE-Step 1.5
            if perf_cue:
                # Clean markdown from the cue but keep the descriptive text
                perf_cue = re.sub(r'[*#`]', '', perf_cue).strip()
                section_tag = f"[{ace_section} - {perf_cue}]"
            else:
                section_tag = f"[{ace_section}]"

            # Blank line before new section (except at start)
            if lyrics_lines and lyrics_lines[-1] != "":
                lyrics_lines.append("")
            lyrics_lines.append(section_tag)
            continue

        # ── Skip stage directions (full-line parenthetical) ──
        if _STAGE_DIR_RE.match(stripped):
            continue

        # ── Clean the lyric line ──
        lyric = stripped
        # Remove inline stage directions
        lyric = _INLINE_PARENS_RE.sub("", lyric).strip()
        # Remove ALL markdown: **, *, ###, ```, etc.
        lyric = re.sub(r'[`#]', '', lyric)
        lyric = lyric.replace('**', '').replace('*', '')
        lyric = lyric.strip()

        # Remove smart quotes artifacts
        lyric = lyric.replace('\u201c', '"').replace('\u201d', '"')
        lyric = lyric.replace('\u2018', "'").replace('\u2019', "'")

        # Skip if nothing meaningful left
        if not lyric or len(lyric) < 2:
            continue

        # Only collect lyrics once we've seen the first section/header
        if not past_header:
            if re.match(r'\[', stripped):
                past_header = True
            else:
                continue

        lyrics_lines.append(lyric)

    # ── 3. Clean up: collapse multiple blanks, trim ──
    cleaned: list[str] = []
    for ln in lyrics_lines:
        if ln == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(ln)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    lyrics = "\n".join(cleaned).strip()

    # ── 4. Fallback: if parsing failed, do aggressive cleanup ──
    if not lyrics or len(lyrics) < 20:
        fallback_lines = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if s.lower().startswith("title:"):
                continue
            if re.match(r'^```', s):
                continue
            if re.match(r'^[\-=*#]{3,}$', s):
                continue
            if re.search(r'\[(?:Genre|Style)', s, re.IGNORECASE):
                continue
            # Strip markdown
            s = re.sub(r'[`#]', '', s).replace('**', '').replace('*', '').strip()
            if s:
                fallback_lines.append(s)
        lyrics = "\n".join(fallback_lines).strip()

    # ── 5. Intro polish — ACE-Step intro quality fix ──
    # Problem: Short shouted lines in [Intro] sound jarring — ACE-Step tries
    # to sing them immediately without an instrumental build.
    # Fix: If the Intro section has only very short lines (1-4 words each,
    # typically CAPS shouts like "GAME OVER / PRESS F TO RESET"), convert
    # those into a performance cue on the Intro tag and let ACE-Step build
    # an instrumental intro with the words as sparse vocal drops.
    lyrics = _polish_intro_section(lyrics)

    return tags, lyrics


def _polish_intro_section(lyrics: str) -> str:
    """Improve [Intro] sections for better ACE-Step audio quality.

    Short shouted lines in intros sound bad because ACE-Step tries to
    sing them without any instrumental build. This function detects
    intros with only short lines (1-4 words each) and restructures them:
      - Merges the short text into the section tag as a vocal cue
      - Adds 'Instrumental build-up,' to guide ACE-Step to start musically

    Example:
      [Intro]                    →  [Intro - Instrumental build-up, sparse vocal shouts]
      GAME OVER                      GAME OVER
      PRESS F TO RESET               PRESS F TO RESET

    Intros with longer lyric lines (>4 words avg) are left unchanged.
    """
    lines = lyrics.split("\n")
    result_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect [Intro ...] section tag
        intro_match = re.match(r'^\[(Intro(?:\s*-\s*.+)?)\]$', line, re.IGNORECASE)
        if intro_match:
            tag_content = intro_match.group(1).strip()
            # Collect all lines until next section tag or blank line after blank
            intro_lyric_lines = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip() == "":
                    # Peek ahead — if next non-empty line is a section tag, stop
                    k = j + 1
                    while k < len(lines) and lines[k].strip() == "":
                        k += 1
                    if k >= len(lines) or re.match(r'^\[', lines[k].strip()):
                        break
                    j += 1
                    continue
                if re.match(r'^\[', lines[j].strip()):
                    break
                intro_lyric_lines.append(lines[j].strip())
                j += 1

            # Check if ALL intro lines are short (≤5 words each)
            if intro_lyric_lines:
                avg_words = sum(len(l.split()) for l in intro_lyric_lines) / len(intro_lyric_lines)
                all_short = all(len(l.split()) <= 5 for l in intro_lyric_lines)

                if all_short and avg_words <= 4:
                    # Add instrumental build-up cue if not already present
                    has_instrumental_cue = "instrumental" in tag_content.lower()
                    if not has_instrumental_cue:
                        if " - " in tag_content:
                            tag_content = tag_content + ", instrumental build-up, sparse vocal drops"
                        else:
                            tag_content = "Intro - Instrumental build-up, sparse vocal drops"
                    result_lines.append(f"[{tag_content}]")
                    # Keep the lyric lines — they become sparse vocal drops
                    for ll in intro_lyric_lines:
                        result_lines.append(ll)
                    i = j
                    continue

            # Normal intro — keep as-is
            result_lines.append(line)
            i += 1
            continue

        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# Cover Art Generation (Pillow post-processing with A!ley branding)
# ---------------------------------------------------------------------------

def generate_cover_art(
    song_title: str,
    genre: str = "",
    mood: str = "",
    song_dir: str = "",
    album_title: str = "",
    album_concept: str = "",
    use_mflux: bool = True,
    llm_visual_prompt: str = "",
) -> Optional[str]:
    """
    Generate cover art for a song/album using cinematic selfie + glitch typography.
    
    Strategy:
    1. Try MFLUX: generate a cinematic dark edgy Ailey portrait
    2. Fallback: pick a random existing selfie from image_private/
    3. Apply text overlay: "A!LEY VYRUS" in glitch/distortion style + album/song name
    
    Args:
        song_title: The song's display title
        genre: Genre for style hints
        mood: Mood for color palette hints
        song_dir: Directory to save cover.png
        album_title: Album name (shown below artist name)
        album_concept: Album concept/theme for visual direction
        use_mflux: Whether to generate fresh image via MFLUX
        llm_visual_prompt: Pre-generated visual prompt from LLM (skips keyword mapping)
        
    Returns:
        Path to cover image or None
    """
    if not song_dir:
        return None
    
    os.makedirs(song_dir, exist_ok=True)
    cover_path = os.path.join(song_dir, "cover.png")
    base_image_path = None
    
    # ── Step 1: Get base image (MFLUX selfie or existing selfie) ──
    if use_mflux:
        base_image_path = _generate_cover_selfie(
            genre, mood,
            song_title=song_title,
            album_title=album_title,
            album_concept=album_concept,
            llm_visual_prompt=llm_visual_prompt,
        )
    
    if not base_image_path:
        base_image_path = _pick_existing_selfie()
    
    if not base_image_path:
        print("[MusicGen] ⚠️ No base image available for cover art")
        return None
    
    # ── Step 2: Apply cinematic treatment + glitch typography ──
    try:
        result = _apply_cover_overlay(
            base_image_path=base_image_path,
            output_path=cover_path,
            artist_name="A!LEY VYRUS",
            title=album_title or song_title,
            genre=genre,
            mood=mood,
        )
        if result:
            print(f"[MusicGen] 🎨 Cover art saved: {cover_path} ({os.path.getsize(cover_path) // 1024}KB)")
            return cover_path
    except Exception as e:
        print(f"[MusicGen] ⚠️ Cover overlay error: {e}")
        import traceback
        traceback.print_exc()
    
    return None


def _generate_cover_selfie(genre: str = "", mood: str = "", song_title: str = "",
                           album_title: str = "", album_concept: str = "",
                           llm_visual_prompt: str = "") -> Optional[str]:
    """Generate a cinematic dark edgy Ailey portrait via MFLUX for cover art.
    
    If an llm_visual_prompt is provided (generated by the LLM while it was still loaded),
    we use it directly — just prepend AILEY_FACE_PREFIX and add standard quality tags.
    This produces far more unique and song-specific covers than keyword matching.
    
    Falls back to the keyword-mapping approach if no LLM prompt is available.
    """
    try:
        from ailey_system.image_generator import (
            generate_image, AILEY_FACE_PREFIX, build_lora_args,
        )
    except ImportError:
        print("[MusicGen] ⚠️ image_generator not available")
        return None

    # ── Ailey LoRA + Realism for all cover selfies ──
    _cover_lora_paths, _cover_lora_scales, _ = build_lora_args(
        ["realism"], include_ailey=True, exclude_nsfw=True
    )

    # ── Fast path: LLM already generated a creative visual prompt ──
    if llm_visual_prompt:
        prompt = (
            f"{AILEY_FACE_PREFIX} "
            f"{llm_visual_prompt}, "
            f"square format, album cover composition, "
            f"professional music artist photo, magazine editorial quality, "
            f"high contrast, shallow depth of field"
        )
        print(f"[MusicGen] 🎨 Using LLM-generated cover prompt ({len(prompt)} chars)")
        filepath, filename = generate_image(
            prompt=prompt,
            title="cover_selfie",
            width=1024,
            height=1024,
            private=True,
            lora_paths=_cover_lora_paths or None,
            lora_scales=_cover_lora_scales or None,
            image_type="selfie",
        )
        if filepath and os.path.isfile(filepath):
            return filepath
        print("[MusicGen] ⚠️ LLM prompt MFLUX failed — falling back to keyword mapping")
    
    # ── Keyword-mapping fallback (original approach) ──
    
    import random
    import hashlib
    
    # ── Deterministic seed from title → consistent but unique per song ──
    # This prevents re-runs from producing wildly different covers for the same song
    _seed_text = (album_title or song_title or "ailey")
    _seed = int(hashlib.md5(_seed_text.encode()).hexdigest()[:8], 16)
    rng = random.Random(_seed)
    
    # ── Song/Album-aware visual concept ──
    # Instead of pure random, derive the CONCEPT from the title/mood/genre.
    # The title carries the emotional DNA of the song.
    _title_lower = (song_title or "").lower()
    _album_lower = (album_title or "").lower()
    _concept_lower = (album_concept or "").lower()
    _all_text = f"{_title_lower} {_album_lower} {_concept_lower}"
    
    # ── Theme-driven location + lighting ──
    # Map emotional/thematic keywords to specific visual environments
    if any(w in _all_text for w in ("game", "reset", "npc", "pixel", "digital", "code", "ctrl", "alt")):
        location = rng.choice([
            "neon-lit arcade with retro gaming screens glowing in background",
            "dark room illuminated only by multiple computer monitors showing code",
            "cyberpunk control room with holographic displays",
        ])
        lighting = rng.choice(["harsh neon RGB lighting", "blue and purple screen glow", "flickering CRT monitor light"])
        style_override = "cyberpunk techwear, LED accessories, digital aesthetic"
    elif any(w in _all_text for w in ("night", "dark", "shadow", "ghost", "dead", "death", "grave")):
        location = rng.choice([
            "abandoned gothic cathedral with moonlight through stained glass",
            "foggy cemetery at midnight with iron gates",
            "dark forest path with pale moonlight filtering through dead trees",
        ])
        lighting = rng.choice(["cold moonlight from above", "eerie backlight with deep shadows", "pale blue ambient glow"])
        style_override = "dark gothic fashion, lace and leather, pale makeup"
    elif any(w in _all_text for w in ("fire", "rage", "burn", "destroy", "war", "fight", "fury")):
        location = rng.choice([
            "burning industrial landscape with sparks and embers flying",
            "rooftop overlooking city in flames at night",
            "dark arena with pyrotechnics and fire effects",
        ])
        lighting = rng.choice(["intense orange fire glow", "red-tinted harsh lighting with smoke", "dramatic rim lighting with fire behind"])
        style_override = "battle-worn leather, smudged makeup, fierce war paint"
    elif any(w in _all_text for w in ("love", "heart", "kiss", "dream", "hope", "together")):
        location = rng.choice([
            "rooftop garden at golden hour with city skyline",
            "rain-soaked street with warm street lamp reflections",
            "vintage cafe window with soft natural light",
        ])
        lighting = rng.choice(["warm golden hour glow", "soft diffused window light", "warm amber illumination"])
        style_override = "soft romantic look, flowing outfit, intimate mood"
    elif any(w in _all_text for w in ("seoul", "tokyo", "korea", "japan", "asian", "k-rap", "k-pop")):
        location = rng.choice([
            "neon-lit Seoul Gangnam district at night with Korean signs",
            "rain-soaked Tokyo alley with Japanese neon signs reflecting on wet ground",
            "Korean rooftop overlooking neon cityscape",
        ])
        lighting = rng.choice(["neon pink and blue city glow", "harsh neon backlight with deep shadows", "colorful Korean neon sign reflections"])
        style_override = "edgy Korean streetwear, oversized jacket, chain accessories"
    elif any(w in _all_text for w in ("school", "college", "class", "campus", "teenage", "youth")):
        location = rng.choice([
            "graffiti-covered school hallway with fluorescent lights",
            "skatepark at golden hour with urban backdrop",
            "bleachers at an empty sports field, sunset",
        ])
        lighting = rng.choice(["warm golden hour", "harsh fluorescent with warm overtones", "dramatic sunset backlight"])
        style_override = "punk school look, plaid skirt, combat boots, band patches"
    else:
        # Default pool — still randomized but with more variety
        _location_options = [
            "abandoned warehouse with graffiti walls",
            "neon-lit alley at night with rain reflections on asphalt",
            "rooftop overlooking city skyline at dusk",
            "dark concert stage with smoke machines and spotlights",
            "rain-soaked street with Korean neon signs",
            "vintage recording studio with analog equipment",
            "industrial factory with sparks flying in background",
            "underground club with laser lights cutting through haze",
        ]
        _lighting_options = [
            "dramatic rim lighting from the left",
            "harsh neon backlight with deep shadows",
            "cinematic golden hour glow from behind",
            "cold blue spotlight from above",
            "split lighting half face in shadow",
            "red-tinted stage lighting with haze",
        ]
        location = rng.choice(_location_options)
        lighting = rng.choice(_lighting_options)
        style_override = None

    # ── Pose — varies but influenced by mood ──
    _pose_options_fierce = [
        "looking directly at camera with fierce intense expression",
        "head tilted back, eyes half-closed, defiant smirk",
        "leaning against a wall, arms crossed, piercing gaze",
        "mid-scream, raw emotional energy",
        "chin up, wind in hair, powerful stance",
    ]
    _pose_options_soft = [
        "close-up three-quarter view, mysterious half-smile",
        "looking over shoulder at camera, vulnerable expression",
        "eyes closed, head slightly tilted, peaceful intensity",
        "gazing down thoughtfully, intimate close-up",
    ]
    
    mood_lower = mood.lower() if mood else ""
    if any(m in mood_lower for m in ("sad", "melanchol", "heartbreak", "vulnerable", "intimate")):
        pose = rng.choice(_pose_options_soft)
    elif any(m in mood_lower for m in ("angry", "aggressive", "fierce", "rage")):
        pose = rng.choice(_pose_options_fierce)
    else:
        pose = rng.choice(_pose_options_fierce + _pose_options_soft)

    # ── Genre-specific style (if no theme override) ──
    genre_lower = genre.lower() if genre else ""
    if style_override:
        style_detail = style_override
    elif "punk" in genre_lower or "rock" in genre_lower or "metal" in genre_lower:
        style_detail = "leather jacket, combat boots, ripped jeans, edgy punk aesthetic"
    elif "k-rap" in genre_lower or "k-pop" in genre_lower:
        style_detail = "edgy Korean streetwear, oversized jacket, chain accessories"
    elif "electronic" in genre_lower or "synth" in genre_lower:
        style_detail = "futuristic outfit, glowing accents, cyberpunk aesthetic"
    elif "acoustic" in genre_lower or "folk" in genre_lower or "ballad" in genre_lower:
        style_detail = "simple intimate look, soft textures, analog film grain"
    elif "grunge" in genre_lower:
        style_detail = "flannel shirt, messy hair, raw 90s grunge look, lo-fi grain"
    elif "cabaret" in genre_lower or "theatrical" in genre_lower:
        style_detail = "dramatic theatrical makeup, gothic elegant outfit"
    else:
        style_detail = "dark urban fashion, statement jewelry, bold look"

    # ── Mood-specific color grading ──
    if any(m in mood_lower for m in ("angry", "aggressive", "fierce", "rage", "wütend")):
        color_hint = "red and orange color grading, high contrast, intense"
    elif any(m in mood_lower for m in ("sad", "melanchol", "heartbreak", "traurig")):
        color_hint = "cool blue and grey tones, desaturated, moody"
    elif any(m in mood_lower for m in ("hope", "triumph", "epic", "anthemic")):
        color_hint = "warm golden tones with dramatic contrast, epic feel"
    elif any(m in mood_lower for m in ("dark", "sinister", "gothic")):
        color_hint = "deep shadows, desaturated with cold highlights, noir"
    elif any(m in mood_lower for m in ("fun", "playful", "bright", "happy")):
        color_hint = "vibrant saturated colors, bright highlights, energetic feel"
    else:
        color_hint = "cinematic color grading, rich contrast"
    
    # ── Build the prompt — song/album context drives the visual ──
    _context_hint = ""
    if album_concept:
        _context_hint = f"Concept: {album_concept}. "
    elif album_title and album_title != song_title:
        _context_hint = f"Album: {album_title}. "
    
    prompt = (
        f"{AILEY_FACE_PREFIX} "
        f"portrait photo, upper body shot, {pose}, "
        f"{lighting}, {location}, "
        f"{style_detail}, {color_hint}, "
        f"square format, album cover composition, "
        f"professional music artist photo, magazine editorial quality, "
        f"high contrast, shallow depth of field"
    )
    
    filepath, filename = generate_image(
        prompt=prompt,
        title="cover_selfie",
        width=1024,
        height=1024,
        private=True,
        lora_paths=_cover_lora_paths or None,
        lora_scales=_cover_lora_scales or None,
        image_type="selfie",
    )
    
    if filepath and os.path.isfile(filepath):
        return filepath
    return None


def _pick_existing_selfie() -> Optional[str]:
    """Pick a random existing selfie from the image_private directory."""
    import random
    
    img_dir = os.path.join(os.path.dirname(SONGS_DIR), "image_private")
    if not os.path.isdir(img_dir):
        return None
    
    selfies = [
        os.path.join(img_dir, f)
        for f in os.listdir(img_dir)
        if f.upper().endswith(".PNG") and "SELFIE" in f.upper()
    ]
    
    if not selfies:
        return None
    
    return random.choice(selfies)


def _apply_cover_overlay(
    base_image_path: str,
    output_path: str,
    artist_name: str = "A!LEY VYRUS",
    title: str = "",
    genre: str = "",
    mood: str = "",
) -> bool:
    """
    Apply cinematic treatment + glitch typography to a base image.
    
    Design:
    - Dark vignette + color grade
    - "A!LEY VYRUS" top area — bold, with glitch/chromatic aberration effect
    - Album/song title bottom — clean sans-serif, smaller
    - Subtle grain/noise overlay
    
    Returns True on success.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    import random
    
    img = Image.open(base_image_path).convert("RGBA")
    
    # Resize/crop to 1024x1024 square
    w, h = img.size
    if w != h:
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
    img = img.resize((1024, 1024), Image.LANCZOS)
    
    W, H = 1024, 1024
    
    # ── 1. Cinematic color grade: darken + slight desaturation + teal tint ──
    from PIL import ImageEnhance
    img_rgb = img.convert("RGB")
    img_rgb = ImageEnhance.Brightness(img_rgb).enhance(0.65)  # darken
    img_rgb = ImageEnhance.Color(img_rgb).enhance(0.7)  # slight desat
    img_rgb = ImageEnhance.Contrast(img_rgb).enhance(1.2)  # boost contrast
    img = img_rgb.convert("RGBA")
    
    # ── 2. Radial vignette (smooth, no box artifacts) ──
    import numpy as np
    cx, cy = W / 2, H / 2
    max_dist = (cx**2 + cy**2) ** 0.5  # corner distance
    ys, xs = np.mgrid[0:H, 0:W]
    dist = np.sqrt((xs - cx)**2 + (ys - cy)**2)
    # Normalize: 0 at center, 1 at corners
    norm = dist / max_dist
    # Smooth ease: vignette starts at ~50% radius, ramps to edges
    vig_alpha = np.clip((norm - 0.4) / 0.6, 0, 1) ** 1.8
    vig_alpha = (vig_alpha * 160).astype(np.uint8)  # max alpha 160
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vignette.putalpha(Image.fromarray(vig_alpha, mode="L"))
    # Set RGB channels to black
    black = Image.new("RGB", (W, H), (0, 0, 0))
    vignette = Image.merge("RGBA", (*black.split(), vignette.split()[3]))
    img = Image.alpha_composite(img, vignette)
    
    # ── 3. Bottom gradient — covers bottom 40%, fades from transparent to solid black ──
    gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    grad_start = int(H * 0.6)  # start at 60% from top = bottom 40%
    for y in range(grad_start, H):
        progress = (y - grad_start) / (H - grad_start)
        # Ease-in curve for smooth fade: slow start, strong at bottom
        alpha = int(230 * (progress ** 1.5))
        alpha = min(alpha, 230)
        grad_draw.rectangle([0, y, W, y], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, gradient)
    
    # (No top gradient — all text is at bottom)
    
    # ── 5. Load fonts ──
    _FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    
    # Permanent Marker for artist name (big, expressive, glitchy)
    font_artist = None
    artist_font_path = os.path.join(_FONT_DIR, "PermanentMarker-Regular.ttf")
    if os.path.isfile(artist_font_path):
        font_artist = ImageFont.truetype(artist_font_path, 96)
    if not font_artist:
        for fp in ["/System/Library/Fonts/Supplemental/Impact.ttf"]:
            if os.path.isfile(fp):
                try:
                    font_artist = ImageFont.truetype(fp, 96)
                    break
                except Exception:
                    continue
    if not font_artist:
        font_artist = ImageFont.load_default()
    
    # Poppins ExtraBold for album/song title
    font_title = None
    poppins_path = os.path.join(_FONT_DIR, "Poppins-ExtraBold.ttf")
    if os.path.isfile(poppins_path):
        font_title = ImageFont.truetype(poppins_path, 44)
    if not font_title:
        for fp in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
            if os.path.isfile(fp):
                try:
                    font_title = ImageFont.truetype(fp, 44)
                    break
                except Exception:
                    continue
    if not font_title:
        font_title = ImageFont.load_default()
    
    draw = ImageDraw.Draw(img)
    
    # ── 6. Prepare title lines first (need total height for layout) ──
    title_lines = []
    if title:
        clean_title = title
        for prefix in ["A!ley Vyrus - ", "A!LEY VYRUS - ", "A!ley Vyrus – "]:
            if clean_title.startswith(prefix):
                clean_title = clean_title[len(prefix):]
        clean_title = clean_title.strip("'\"")
        
        # Support explicit newlines in title (e.g. "BLOODLINES:\nA DIGITAL CRUCIFIXION")
        raw_lines = clean_title.split("\n")
        for raw_line in raw_lines:
            raw_line = raw_line.strip()
            if len(raw_line) <= 26:
                title_lines.append(raw_line)
            else:
                words = raw_line.split()
                current = ""
                for word in words:
                    test = f"{current} {word}".strip()
                    if len(test) <= 26:
                        current = test
                    else:
                        if current:
                            title_lines.append(current)
                        current = word
                if current:
                    title_lines.append(current)
        title_lines = title_lines[:4]
    
    # ── 7. Calculate layout — everything bottom-centered ──
    MARGIN_BOTTOM = 65
    TITLE_LINE_HEIGHT = 54
    ARTIST_TITLE_GAP = 18  # gap between artist name and album title
    
    # Total text block height
    artist_bbox = draw.textbbox((0, 0), artist_name, font=font_artist)
    artist_h = artist_bbox[3] - artist_bbox[1]
    artist_w = artist_bbox[2] - artist_bbox[0]
    
    title_block_h = len(title_lines) * TITLE_LINE_HEIGHT if title_lines else 0
    total_block_h = artist_h + (ARTIST_TITLE_GAP + title_block_h if title_lines else 0)
    
    # Position: bottom of image, centered, with margin
    block_top = H - MARGIN_BOTTOM - total_block_h
    artist_y = block_top
    artist_x = (W - artist_w) // 2
    
    # ── 8. "A!LEY VYRUS" — Big glitchy chromatic aberration ──
    # Multiple chromatic layers for maximum glitch feel
    offsets = [(-6, 0), (6, 0), (-3, -2), (3, 2)]
    colors = [
        (255, 0, 60, 100),   # red left
        (0, 220, 255, 100),  # cyan right
        (255, 0, 180, 60),   # magenta
        (0, 255, 120, 50),   # green
    ]
    for (ox, oy), color in zip(offsets, colors):
        draw.text((artist_x + ox, artist_y + oy), artist_name, fill=color, font=font_artist)
    
    # Main white text
    draw.text((artist_x, artist_y), artist_name, fill=(255, 255, 255, 250), font=font_artist)
    
    # Glitch slice bars — displace horizontal strips through the text
    glitch_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for _ in range(random.randint(4, 8)):
        gy = artist_y + random.randint(-8, artist_h + 5)
        gh = random.randint(2, 6)
        gx_offset = random.choice([-15, -10, -7, 7, 10, 15, 20, -20])
        x0 = max(0, artist_x - 20)
        x1 = min(W, artist_x + artist_w + 20)
        if 0 <= gy < H and gy + gh < H:
            strip = img.crop((x0, gy, x1, gy + gh))
            glitch_overlay.paste(strip, (x0 + gx_offset, gy))
    img = Image.alpha_composite(img, glitch_overlay)
    
    # Re-stamp artist text on top of glitch so it stays crisp
    draw = ImageDraw.Draw(img)
    draw.text((artist_x - 4, artist_y), artist_name, fill=(255, 0, 80, 70), font=font_artist)
    draw.text((artist_x + 4, artist_y), artist_name, fill=(0, 200, 255, 70), font=font_artist)
    draw.text((artist_x, artist_y), artist_name, fill=(255, 255, 255, 255), font=font_artist)
    
    # ── 9. Album/Song title — Poppins ExtraBold, directly below artist ──
    if title_lines:
        title_top = artist_y + artist_h + ARTIST_TITLE_GAP
        for i, line in enumerate(title_lines):
            bbox_t = draw.textbbox((0, 0), line, font=font_title)
            ltw = bbox_t[2] - bbox_t[0]
            ltx = (W - ltw) // 2
            lty = title_top + i * TITLE_LINE_HEIGHT
            # Shadow for readability
            draw.text((ltx + 2, lty + 2), line, fill=(0, 0, 0, 180), font=font_title)
            draw.text((ltx, lty), line, fill=(255, 255, 255, 240), font=font_title)
    
    # ── 9. Subtle noise/grain overlay ──
    noise = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    noise_draw = ImageDraw.Draw(noise)
    for _ in range(W * H // 80):
        nx = random.randint(0, W - 1)
        ny = random.randint(0, H - 1)
        na = random.randint(5, 25)
        noise_draw.point((nx, ny), fill=(255, 255, 255, na))
    img = Image.alpha_composite(img, noise)
    
    # ── 10. Save ──
    img.convert("RGB").save(output_path, "PNG", quality=95)
    
    # Clean up temp MFLUX image if it was generated (not an existing selfie)
    if "image_private" not in base_image_path:
        try:
            os.remove(base_image_path)
            meta = base_image_path.replace(".png", ".meta.json")
            if os.path.isfile(meta):
                os.remove(meta)
        except Exception:
            pass
    
    return True


# ---------------------------------------------------------------------------
# Main Generation Function — Subprocess Architecture
# ---------------------------------------------------------------------------

def generate_music(
    prompt: str,
    lyrics: str,
    song_id: str = "",
    duration: float = ACE_DEFAULT_DURATION,
    infer_steps: int = ACE_INFER_STEPS,
    guidance_scale: float = ACE_GUIDANCE_SCALE,
    seed: Optional[int] = None,
    batch_size: int = ACE_BATCH_SIZE,
    model: str = ACE_MODEL,
    thinking: bool = True,
    lora_paths: Optional[list] = None,
    voice_reference: Optional[str] = "auto",
    title_override: Optional[str] = None,
) -> Tuple[Optional[str], Optional[dict]]:
    """
    Generate music using ACE-Step v1.5 in a subprocess.

    IMPORTANT: The LLM (Ministral) MUST be fully unloaded before calling this.
    The caller is responsible for unload/reload (same pattern as MFLUX/Wan2.1).

    Architecture:
      1. Spawn subprocess: ACE-Step/.venv/bin/python ace_generate.py {args_json}
      2. Subprocess loads DiT handler + (optionally) 5Hz-LM 0.6B
      3. LoRA adapters loaded (style transfer: Metal/Pop-Rock)
      4. Voice reference conditioning (Ailey's vocal character)
      5. inference.generate_music() orchestrates: LM → audio codes → DiT
      6. Subprocess exits → complete GPU memory cleanup
      7. We read the JSON result from stdout

    Args:
        prompt: ACE-Step hybrid caption (tags + natural description)
        lyrics: Song lyrics with [Verse 1 - cue]/[Chorus] section markers
        song_id: Song identifier for file organization
        duration: Audio duration in seconds (max 240)
        infer_steps: Inference steps (SFT: 50=best quality, Turbo: 8=fast)
        guidance_scale: CFG guidance scale (v1.5 default: 7.0)
        seed: Random seed (None = random)
        batch_size: Number of variants to generate
        model: DiT model name (acestep-v15-sft or acestep-v15-turbo)
        thinking: If True, use 5Hz-LM 0.6B for audio code generation (BPM, key, structure)
        lora_paths: List of LoRA configs [{"path", "name", "scale"}], or None for auto-select
        voice_reference: Path to voice ref WAV, "auto" for default, or None to disable

    Returns:
        Tuple of (mp3_filepath, result_metadata) or (None, None) on failure
    """
    _ensure_dirs()

    # Validate duration
    duration = min(float(duration), ACE_MAX_DURATION)
    duration = max(duration, 10.0)

    # Generate song_id if not provided
    if not song_id:
        song_id = f"song_{int(time.time() * 1000)}"

    # Create song directory
    song_dir = os.path.join(SONGS_DIR, song_id)
    os.makedirs(song_dir, exist_ok=True)

    # Safety check: enough RAM?
    free_ram = get_free_ram_gb()
    if free_ram < MIN_FREE_RAM_GB:
        print(f"[MusicGen] ⚠️ Not enough free RAM: {free_ram:.1f}GB < {MIN_FREE_RAM_GB}GB min")
        return None, None

    # Check ACE-Step availability
    if not os.path.isfile(ACE_STEP_PYTHON) or not os.path.isfile(_ACE_SCRIPT):
        print(f"[MusicGen] ❌ ACE-Step not found: {ACE_STEP_DIR}")
        return None, None

    output_mp3 = os.path.join(song_dir, "audio.mp3")

    print(f"[MusicGen] 🎵 Generating song: {song_id}")
    print(f"[MusicGen]    Caption: {prompt[:120]}...")
    print(f"[MusicGen]    Duration: {duration}s, Steps: {infer_steps}, Model: {model}")

    # ── Centralized generation log — append-only for cross-run comparison ──
    _gen_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music_gen.log")
    try:
        _log_entry = {
            "ts": datetime.now().isoformat(),
            "song_id": song_id,
            "caller": "idle_thinker" if not os.environ.get("SONG_SPRINT") else "song_sprint",
            "model": model,
            "infer_steps": infer_steps,
            "guidance_scale": guidance_scale,
            "duration": duration,
            "seed": seed,
            "thinking": thinking,
            "batch_size": batch_size,
            "prompt_len": len(prompt),
            "prompt_head": prompt[:200],
            "lyrics_len": len(lyrics),
            "voice_reference": voice_reference,
            "free_ram_gb": round(free_ram, 1),
            "env_PYTORCH_MPS_HIGH_WATERMARK_RATIO": os.environ.get("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "not set"),
            "env_TOKENIZERS_PARALLELISM": os.environ.get("TOKENIZERS_PARALLELISM", "not set"),
        }
        with open(_gen_log_path, "a", encoding="utf-8") as _glf:
            _glf.write(json.dumps(_log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Non-fatal — don't block generation

    start_time = time.time()

    # ── Resolve LoRA adapters ──
    # If lora_paths not explicitly provided, auto-select based on genre tags in prompt
    resolved_loras = lora_paths
    if resolved_loras is None:
        resolved_loras = select_lora_for_prompt(prompt)
    if resolved_loras:
        lora_names = [l.get("name", "?") for l in resolved_loras]
        print(f"[MusicGen]    LoRAs: {lora_names}")
    else:
        print(f"[MusicGen]    LoRAs: none (no genre match)")

    # ── Resolve voice reference ──
    resolved_voice_ref = None
    if voice_reference == "auto":
        # Default: use Ailey's main voice reference if it exists
        if os.path.isfile(DEFAULT_VOICE_REFERENCE):
            resolved_voice_ref = DEFAULT_VOICE_REFERENCE
            print(f"[MusicGen]    Voice ref: {os.path.basename(DEFAULT_VOICE_REFERENCE)}")
        else:
            print(f"[MusicGen]    Voice ref: none (default file not found)")
    elif voice_reference and voice_reference != "none":
        if os.path.isfile(voice_reference):
            resolved_voice_ref = voice_reference
            print(f"[MusicGen]    Voice ref: {os.path.basename(voice_reference)}")
        else:
            print(f"[MusicGen]    ⚠️ Voice ref not found: {voice_reference}")
    else:
        print(f"[MusicGen]    Voice ref: disabled")

    # ── Extract BPM & Key from caption → explicit overrides ──
    # The 0.6B LM is too small to reliably parse BPM from caption text.
    # If the caption says "145 BPM, D minor", we extract those values and
    # pass them as explicit params that the LM cannot override.
    override_bpm = extract_bpm_from_caption(prompt)
    override_key = extract_key_from_caption(prompt)
    if override_bpm:
        print(f"[MusicGen]    BPM override: {override_bpm} (extracted from caption)")
    if override_key:
        print(f"[MusicGen]    Key override: {override_key} (extracted from caption)")

    # ── Check lyrics length ──
    lyrics_info = check_lyrics_length(lyrics)
    if lyrics_info["recommendation"]:
        print(f"[MusicGen]    ⚠️ {lyrics_info['recommendation']}")

    # Build args for subprocess
    sub_args = {
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": duration,
        "output_path": output_mp3,
        "infer_steps": infer_steps,
        "guidance_scale": guidance_scale,
        "batch_size": batch_size,
        "model": model,
        "seed": seed,
        "mp3_bitrate": "192k",
        "thinking": thinking,
        "shift": 3.0,  # v1.5 SFT timestep shift (UI default)
        "lora_paths": resolved_loras or [],
        "voice_reference": resolved_voice_ref,
        # Explicit metadata overrides — bypass unreliable 0.6B LM guessing
        "bpm": override_bpm,            # int or None
        "keyscale": override_key or "",  # e.g. "D minor"
    }

    try:
        # ── Run ACE-Step in subprocess ──
        # Uses ACE-Step's own venv — completely isolated
        result = subprocess.run(
            [ACE_STEP_PYTHON, _ACE_SCRIPT, json.dumps(sub_args)],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max
            cwd=ACE_STEP_DIR,
            env={
                **os.environ,
                "TOKENIZERS_PARALLELISM": "false",
                "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.0",
                "PYTORCH_ENABLE_MPS_FALLBACK": "1",
                "ACESTEP_GENERATION_TIMEOUT": "1800",  # 30 min internal timeout (default 600 too low for 50 steps)
            },
        )

        # Log stderr (progress messages)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"[MusicGen]    {line}")

        # ── Venv-Doctor: Diagnose bei Crash-Exit-Codes ──
        if result.returncode in (138, 137, 139, -10, -9, -11):
            print(f"[MusicGen] 🩺 Crash erkannt (exit {result.returncode}) — starte Venv-Diagnose …")
            try:
                from ailey_system.venv_doctor import diagnose_subprocess_failure
                diagnose_subprocess_failure(
                    env_name="ace_step",
                    returncode=result.returncode,
                    stderr=result.stderr or "",
                    command=f"{ACE_STEP_PYTHON} {_ACE_SCRIPT} ...",
                )
            except Exception as diag_err:
                print(f"[MusicGen] ⚠️ Venv-Diagnose fehlgeschlagen: {diag_err}")
            return None, None

        # Parse JSON result from stdout
        stdout_clean = result.stdout.strip()
        if not stdout_clean:
            print(f"[MusicGen] ❌ Subprocess produced no output (exit code {result.returncode})")
            return None, None

        # Find the JSON line (last line that starts with {)
        json_line = ""
        for line in reversed(stdout_clean.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                json_line = line
                break

        if not json_line:
            print(f"[MusicGen] ❌ No JSON in subprocess output")
            print(f"[MusicGen]    stdout: {stdout_clean[:500]}")
            return None, None

        sub_result = json.loads(json_line)

        if not sub_result.get("success"):
            error = sub_result.get("error", "Unknown error")
            print(f"[MusicGen] ❌ {error}")
            return None, None

        # Get the output path from subprocess
        final_path = sub_result.get("output_path", output_mp3)
        if not os.path.isfile(final_path):
            print(f"[MusicGen] ❌ Output file not found: {final_path}")
            return None, None

        elapsed = time.time() - start_time
        file_size = os.path.getsize(final_path)
        print(f"[MusicGen] ✅ Generated in {elapsed:.1f}s — {os.path.basename(final_path)} ({file_size // 1024}KB)")

        # Save metadata
        _created_at = datetime.now().isoformat()
        meta = {
            "song_id": song_id,
            "prompt": prompt,
            "lyrics": lyrics,
            "model": model,
            "ace_step_version": "1.5",
            "thinking": thinking,
            "duration_seconds": duration,
            "infer_steps": infer_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "batch_size": batch_size,
            "generation_time_s": sub_result.get("generation_time_s", round(elapsed, 1)),
            "load_time_s": sub_result.get("load_time_s", 0),
            "total_time_s": sub_result.get("total_time_s", round(elapsed, 1)),
            "override_bpm": override_bpm,
            "override_key": override_key or None,
            "lm_bpm": sub_result.get("lm_bpm"),
            "lm_key": sub_result.get("lm_key"),
            "lm_time_sig": sub_result.get("lm_time_sig"),
            "loras": sub_result.get("loras"),
            "voice_reference": sub_result.get("voice_reference"),
            "lyrics_word_count": lyrics_info.get("word_count", 0),
            "file_size_bytes": file_size,
            "created_at": _created_at,
        }
        # Store user-supplied title override in meta (portal/tauri passthrough)
        if title_override:
            meta["title"] = title_override
        meta_path = os.path.join(song_dir, "generation_meta.json")
        try:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # ── Write lyrics.txt (always — makes song findable in Tauri/Portal) ──
        try:
            with open(os.path.join(song_dir, "lyrics.txt"), "w", encoding="utf-8") as f:
                f.write(lyrics)
        except Exception:
            pass

        # ── Write manifest.json (always — uniform with idle_thinker songs) ──
        # Extract genre from first tag or prompt header
        _genre_raw = prompt.split(",")[0].strip() if prompt else ""
        _genre_hdr = re.search(r'\[Genre:\s*([^\],]+)', prompt, re.IGNORECASE)
        if _genre_hdr:
            _genre_raw = _genre_hdr.group(1).strip()
        # Build clean title
        _manifest_title = title_override or ""
        if not _manifest_title:
            # Try to extract from lyrics header line
            for _ln in lyrics.splitlines():
                _ln = _ln.strip()
                if _ln.startswith("[") and "Genre" in _ln:
                    continue
                if _ln.startswith("[") and "Tags" in _ln:
                    continue
                # First non-header lyric line becomes fallback title base
                _ln_clean = _ln.strip("[]")
                if len(_ln_clean.split()) >= 2:
                    _manifest_title = f"A!ley Vyrus - '{_ln_clean[:50]}'"
                    break
        if not _manifest_title:
            _manifest_title = f"A!ley Vyrus - Song ({song_id[-8:]})"
        # Only write manifest if it doesn't already exist (don't overwrite idle_thinker manifests)
        _manifest_path = os.path.join(song_dir, "manifest.json")
        if not os.path.isfile(_manifest_path):
            try:
                _manifest = {
                    "title": _manifest_title,
                    "genre": _genre_raw,
                    "mood": "",
                    "tags": prompt[:300] if prompt else "",
                    "lyrics_clean": lyrics,
                    "phase": "done",
                    "phases_completed": ["write", "audio"],
                    "audio_path": final_path,
                    "cover_path": None,
                    "created_at": _created_at,
                    "source": "user_generated",  # distinguishes from idle_thinker songs
                }
                if title_override:
                    _manifest["user_title"] = title_override
                with open(_manifest_path, "w", encoding="utf-8") as f:
                    json.dump(_manifest, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # ── Append result to centralized log ──
        try:
            _result_entry = {
                "ts": datetime.now().isoformat(),
                "song_id": song_id,
                "status": "ok",
                "elapsed_s": round(elapsed, 1),
                "file_size_kb": file_size // 1024,
                "lm_bpm": sub_result.get("lm_bpm"),
                "lm_key": sub_result.get("lm_key"),
                "override_bpm": override_bpm,
                "override_key": override_key or None,
                "actual_seed": sub_result.get("seed"),
                "loras_used": sub_result.get("loras"),
                "voice_ref_used": sub_result.get("voice_reference"),
            }
            with open(_gen_log_path, "a", encoding="utf-8") as _glf:
                _glf.write(json.dumps(_result_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        return final_path, meta

    except subprocess.TimeoutExpired:
        print(f"[MusicGen] ❌ Generation timed out (30 min)")
        return None, None
    except json.JSONDecodeError as e:
        print(f"[MusicGen] ❌ Failed to parse subprocess result: {e}")
        return None, None
    except Exception as e:
        print(f"[MusicGen] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None
