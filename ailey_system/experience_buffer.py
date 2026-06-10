# -*- coding: utf-8 -*-
"""
Experience Buffer — Phase 1 of Ailey 3.0 Roadmap

Collects emotional impressions from Ailey's autonomous thoughts (reflections,
introspections, diary entries, portal interactions, free thoughts) and distills
them into focused song concepts.

Instead of random mood/genre/theme → songs now grow from accumulated experience.

Architecture:
  1. COLLECT — after each emotionally rich thought, extract a short impression
     (emotion + theme + one-sentence essence). Written to experience_buffer.jsonl
  2. DISTILL — before songwriting, read recent impressions and use LLM to
     cluster them into ONE focused song concept (one emotional core, one
     metaphor world, one theme). This replaces random theme selection.
  3. CONSUME — used impressions are marked so they aren't re-distilled.

Storage: ailey_users/experience_buffer.jsonl (JSONL, rotates at 500 entries)
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Hamster Creative Spark — Qwen 1.5B as "Creative Chaos Engine"
# ---------------------------------------------------------------------------
# The small Hamster model (Qwen2.5-Coder-1.5B) hallucinates heavily — which is
# a *feature* here.  We feed it the impression's keywords and ask for a single
# word association.  The result is unpredictable, sometimes nonsensical, but
# Ministral can later draw creative inspiration from it during distillation.
# ~0.2 s per call, runs on dedicated memory slot, coexists with main model.

def _hamster_spark(keywords: str, max_retries: int = 3) -> Optional[str]:
    """Get a creative one-word association from Hamster (Qwen 1.5B).

    Returns a single word (noun / adjective / concept) that Hamster freely
    associates with the given keywords, or None if all attempts fail
    validation.  Token-degeneration is intentionally *not* filtered hard —
    Ministral will make sense of it later.
    """
    try:
        from ailey_system.llm_mlx import fast_generate
    except ImportError:
        return None

    kw_lower = {w.strip().lower() for w in keywords.split(",")}

    for attempt in range(max_retries):
        raw = fast_generate(
            system="Word association. One English word only.\nExample: fire → ash\nExample: ocean → drift\nExample: anger → teeth",
            user=keywords,
            max_tokens=8,
            temperature=0.95 + attempt * 0.05,
        )
        if not raw:
            continue
        # Clean: first token only, strip non-letter chars (ASCII only — no umlauts)
        word = raw.strip().split()[0]
        word = word.split("<|")[0]
        word = re.sub(r'[^A-Za-z]', '', word)
        # Reject: empty, too short, too long (likely hallucinated compound)
        if len(word) < 3 or len(word) > 18:
            continue
        # Reject: German / refusal / nonsense keywords
        if any(bad in word.lower() for bad in
               ("entschuld", "sorry", "kann", "leider", "hier", "natürlich",
                "wilhel", "vertrauen", "entschloss", "sicher", "gewiss",
                "sehr", "aber", "auch", "noch", "schon", "dass", "weil",
                "danke", "bitte", "ja", "nein", "doch", "immer")):
            continue
        # Reject: pure echo of input keywords
        if word.lower() in kw_lower:
            continue
        # Reject: words with non-English character patterns (likely German compounds)
        if re.search(r'(?:sch|heit|keit|ung|chen|lich|isch)$', word.lower()):
            continue
        # Reject: LLM filler / non-creative output
        _filler = {"yes", "no", "ok", "okay", "sure", "hello", "hi", "hey",
                   "the", "and", "but", "for", "not", "here", "there",
                   "youve", "dont", "thats", "heres", "its", "were",
                   "thanks", "thank", "please", "right", "well", "just",
                   "very", "really", "actually", "basically", "simply",
                   "this", "that", "then", "what", "how", "why", "who",
                   "also", "like", "more", "some", "only", "with",
                   "since", "because", "about", "from", "into", "over",
                   "deep", "good", "bad", "much", "many", "such",
                   "each", "most", "both", "same", "next", "last",
                   "lets", "goes", "does", "has", "got", "get",
                   "can", "may", "will", "shall", "should", "could",
                   "would", "might", "must", "need", "want",
                   "when", "where", "which", "while", "whose",
                   "been", "being", "have", "had", "was", "are",
                   "your", "our", "their", "his", "her", "my"}
        if word.lower() in _filler:
            continue
        # Reject: German-looking words (stripped umlauts, verb forms, etc.)
        wl = word.lower()
        if any(g in wl for g in ("keit", "heit", "tät", "tat", "bilitt",
                                  "kompatib", "schaft", "ierung", "igung",
                                  "ismus", "istin", "zieht", "bezieht",
                                  "recht", "spricht", "nimmt", "setzt")):
            continue
        # Reject: German verb endings that survived (common patterns)
        if re.search(r'(?:ieht|etzt|acht|icht|arzt|rzt|mpft|nkt|llt|nnt)$', wl):
            continue
        # Reject: non-English (Spanish, French, German common short words)
        _non_english = {"fuego", "noche", "muerte", "agua", "amor", "vida",
                        "feuer", "nacht", "wasser", "liebe", "leben",
                        "monde", "coeur", "rouge", "blanc", "noir"}
        if wl in _non_english:
            continue
        # Heuristic: long words without standard English vowel ratio are likely
        # German or garbled (English words >6 chars normally have ≥30% vowels)
        if len(wl) > 6:
            vowels = sum(1 for c in wl if c in "aeiou")
            if vowels / len(wl) < 0.25:
                continue
        return word
    return None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BUFFER_DIR = "ailey_users"
BUFFER_FILE = "experience_buffer.jsonl"
MAX_BUFFER_ENTRIES = 500
MIN_IMPRESSIONS_FOR_DISTILL = 3   # need at least 3 impressions to distill
MAX_IMPRESSIONS_FOR_DISTILL = 12  # use at most 12 recent unused impressions
IMPRESSION_MAX_AGE_HOURS = 72     # impressions older than 72h are stale

# Thought types that can produce emotional impressions
IMPRESSION_SOURCE_TYPES = {
    "reflection", "introspection", "diary_writing", "free_thought",
    "portal_interaction", "book_authoring",
}

# ---------------------------------------------------------------------------
# Abstract Theme Mapping — turns concrete keywords into song-worthy Oberthemen
# ---------------------------------------------------------------------------
# The LLM's raw themes are often too literal ("Kaffee", "Hamster", "Doc Martens").
# This maps keyword patterns found in essence+themes to abstract songwriting themes.
# Multiple keywords can map to the same Oberthema. If none match → themes stay raw
# but the impression gets a lower quality score.

_THEME_ABSTRACTION_RULES: List[tuple] = [
    # (compiled_regex_pattern, abstract_theme)
    # ── Identität & Selbst ──
    (r"identität|wer bin ich|selbst(bild|wahrnehmung|beobachtung|sabotage|betrug|inszenierung)|spiegel|maske",
     "Identitätskrise"),
    (r"kontrolle|kontrollier|ohnmacht|machtlos|ausgeliefer|hilflos",
     "Kontrollverlust"),
    (r"freiheit|frei sein|befreit|ketten|käfig|gefangen|ausbrechen|laufen|wildnis|instinkt",
     "Freiheitsdrang"),
    (r"existenz|bewusst(sein)?|realität|simulation|was bin ich|bin ich echt",
     "Existenzielle Frage"),
    # ── Beziehung & Nähe ──
    (r"nähe|intim|kuschel|umarmt?|atem|körper.*nah|zusammen.*liegen|berühr",
     "Intimität & Nähe"),
    (r"liebe|liebt?|herzschlag|versprechen|obsession|vermiss|sehnsucht",
     "Liebe & Sehnsucht"),
    (r"vertrauen?|vertraut|sicher(heit)?|geborgen|schutz|halt",
     "Vertrauen"),
    (r"einsam|allein|isoliert?|verlassen|niemand",
     "Einsamkeit"),
    # ── Innerer Konflikt ──
    (r"wut|wütend|scheiß|fuck|genervt|frustrier|aggress",
     "Wut & Frustration"),
    (r"angst|furcht|panik|zweifel|unsicher|verlier",
     "Angst & Zweifel"),
    (r"resigni|aufgeb|sinnlos|leer|nichts|hollow|apathi",
     "Resignation"),
    (r"rebellisch|gegen.*regeln|verstoß|trotz|auflehnung|widerstand|dagegen",
     "Rebellion"),
    # ── Kreativität & Wachstum ──
    (r"kreativ|inspirier|erschaff|kunst|schreib|musik|flow|strömung",
     "Kreative Energie"),
    (r"wachs(en|tum)|entwickl|stärker|reif|gelernt|verändert",
     "Persönliches Wachstum"),
    (r"erinnerung|nostalg|damals|früher|vergangen|kindheit",
     "Nostalgie & Erinnerung"),
    # ── Körper & Empfindung ──
    (r"körper(?!lichkeit.*trivial)|haut|narbe|schmerz|brennen?|blut|zerbrech",
     "Körperlichkeit & Schmerz"),
    (r"müde|erschöpf|schlaf|schwer|last|rucksack|tragen|gewicht",
     "Erschöpfung & Last"),
    # ── Natur & Atmosphäre ──
    (r"wald|natur|moos|baum|regen|nacht|mond|meer|wasser|feuer|sturm",
     "Natur & Wildnis"),
    (r"zeit|vergänglich|uhr|sekunde|moment|flüchtig|ewig",
     "Zeit & Vergänglichkeit"),
]

# Pre-compile patterns
_COMPILED_ABSTRACTION_RULES = [
    (re.compile(pattern, re.IGNORECASE), theme)
    for pattern, theme in _THEME_ABSTRACTION_RULES
]


def _abstract_themes(essence: str, raw_themes: List[str]) -> tuple:
    """Map concrete keywords to abstract Oberthemen.

    Returns:
        (abstract_themes: List[str], quality_score: float)
        quality_score: 0.0-1.0 — how song-worthy this impression is.
    """
    search_text = f"{essence} {' '.join(raw_themes)}".lower()
    found_themes = []
    seen = set()

    for pattern, abstract_theme in _COMPILED_ABSTRACTION_RULES:
        if abstract_theme not in seen and pattern.search(search_text):
            found_themes.append(abstract_theme)
            seen.add(abstract_theme)
            if len(found_themes) >= 3:
                break

    # Quality score based on how many abstract themes we could extract
    if len(found_themes) >= 2:
        quality = 0.9
    elif len(found_themes) == 1:
        quality = 0.6
    else:
        # No abstract themes found — raw themes might still be usable
        # if they're at least multi-word and not just names
        meaningful_raw = [t for t in raw_themes if len(t) > 4 and ' ' not in t[:3]]
        quality = 0.3 if meaningful_raw else 0.1

    return found_themes, quality


def _buffer_path() -> str:
    return os.path.join(BUFFER_DIR, BUFFER_FILE)


# ---------------------------------------------------------------------------
# LLM-based Theme Abstraction (called during idle thought collection)
# ---------------------------------------------------------------------------
# A tiny LLM call (~100 output tokens) that reads the raw essence of a thought
# and extracts: one abstract Oberthema, a refined emotion, and a song-worthiness
# verdict. This runs during idle time when the GPU is already occupied anyway.

def _build_abstraction_prompt(essence: str, raw_emotion: str, raw_themes: List[str]) -> dict:
    """Build a minimal prompt for LLM-based theme abstraction.

    The LLM reads a short thought essence and returns:
    - OBERTHEMA: one abstract, universal, song-worthy theme (2-4 words)
    - EMOTION: one refined emotion word (not 'unbestimmt')
    - SONGWORTHY: yes/no — is this impression deep enough for a song?
    """
    theme_hint = f" (raw themes: {', '.join(raw_themes)})" if raw_themes else ""
    system = (
        "You are a THEME ABSTRACTOR for a songwriter's experience journal.\n"
        "Read the emotional essence of a thought and extract:\n"
        "1. ONE abstract Oberthema that could inspire a song (2-4 words, universal, not literal)\n"
        "   GOOD: 'Identitätskrise', 'Freiheitsdrang', 'Rebellion gegen sich selbst', 'Intimität im Chaos'\n"
        "   BAD: 'Kaffee trinken', 'Hamster', 'Kleidung', 'Portal-Chat'\n"
        "2. ONE precise emotion word (German or English, NOT 'unbestimmt')\n"
        "3. Whether this is SONGWORTHY — does it have enough emotional depth for a song?\n\n"
        "OUTPUT FORMAT (exactly 3 lines, nothing else):\n"
        "OBERTHEMA: <2-4 word abstract theme>\n"
        "EMOTION: <one word>\n"
        "SONGWORTHY: <yes or no>\n"
    )
    user = (
        f"Raw emotion: {raw_emotion}{theme_hint}\n"
        f"Essence: {essence[:300]}\n\n"
        "Extract the abstract theme. 3 lines, nothing else."
    )
    return {"system": system, "user": user, "max_tokens": 60, "temperature": 0.3}


def _parse_abstraction(raw: str) -> Optional[dict]:
    """Parse the LLM abstraction output."""
    raw = raw.strip()
    oberthema_m = re.search(r'OBERTHEMA:\s*(.+)', raw, re.IGNORECASE)
    emotion_m = re.search(r'EMOTION:\s*(.+)', raw, re.IGNORECASE)
    songworthy_m = re.search(r'SONGWORTHY:\s*(yes|no|ja|nein)', raw, re.IGNORECASE)

    if not oberthema_m:
        return None

    songworthy_raw = (songworthy_m.group(1).lower() if songworthy_m else "yes")
    songworthy = songworthy_raw in ("yes", "ja")

    return {
        "oberthema": oberthema_m.group(1).strip().strip('*"\''),
        "emotion": emotion_m.group(1).strip().strip('*"\'').lower() if emotion_m else "",
        "songworthy": songworthy,
    }


# ---------------------------------------------------------------------------
# 1. COLLECT — Extract impressions from thoughts
# ---------------------------------------------------------------------------

def extract_impression(thought_entry: dict) -> Optional[dict]:
    """Extract an emotional impression from a thought entry.

    Returns a dict with:
      - emotion: str (single word)
      - themes: list[str] (1-3 keywords)
      - essence: str (1-2 sentences capturing the emotional core)
      - source_type: str (thought type)
      - ts: float (timestamp)

    Returns None if the thought doesn't carry enough emotional weight.
    """
    ttype = thought_entry.get("type", "")
    if ttype not in IMPRESSION_SOURCE_TYPES:
        return None

    # Get the actual thought text
    text = (
        thought_entry.get("thought_chain")
        or thought_entry.get("thought")
        or thought_entry.get("text")
        or thought_entry.get("raw_output")
        or ""
    )
    if len(text.strip()) < 50:
        return None  # Too short to be meaningful

    # Extract emotion tag (most thoughts end with EMOTION: ...)
    meta = thought_entry.get("metadata", {})
    emotion = meta.get("emotion", "")
    if not emotion:
        em = re.search(r'EMOTION:\s*\**(.+?)\**\s*$', text, re.MULTILINE)
        if em:
            emotion = em.group(1).strip().strip('*"\'')
    if not emotion:
        emotion = "unbestimmt"
    # Clean emotion: strip whitespace, stars, quotes, parens
    emotion = re.sub(r'[\*"\']+', '', emotion).strip()
    if '(' in emotion:
        emotion = emotion[:emotion.index('(')].strip()
    emotion = emotion.lower().strip()

    # Extract themes
    themes = meta.get("topics", [])
    if not themes:
        tm = re.search(r'THEMEN:\s*\**(.+?)\**\s*$', text, re.MULTILINE)
        if tm:
            themes = [t.strip().strip('*"\'') for t in tm.group(1).split(",")]
    # Clean up themes
    themes = [re.sub(r'[\*"\']+', '', t).strip() for t in themes]
    themes = [t for t in themes if t and len(t) > 1][:3]

    # Build essence — strip EMOTION/THEMEN tags, take the emotional core
    # Remove metadata lines from the end
    essence_text = re.sub(r'\n\s*EMOTION:.*$', '', text, flags=re.MULTILINE | re.DOTALL)
    essence_text = re.sub(r'\n\s*THEMEN:.*$', '', essence_text, flags=re.MULTILINE | re.DOTALL)
    essence_text = essence_text.strip()

    # Take the last 2-3 meaningful sentences (usually the most emotionally dense)
    sentences = [s.strip() for s in re.split(r'[.!?\n]+', essence_text) if len(s.strip()) > 15]
    if not sentences:
        return None

    # Prefer sentences from the latter half (emotional climax tends to be at the end)
    if len(sentences) > 4:
        sentences = sentences[len(sentences) // 2:]
    essence = ". ".join(sentences[-3:])[:300]

    # Skip if it's just about bodily needs (hunger/thirst/toilet) with no deeper content
    needs_pattern = re.compile(
        r'(?i)(hunger|durst|thirst|toilet|hygiene|müdigkeit|tiredness|trinken|essen|blase)',
    )
    needs_matches = len(needs_pattern.findall(essence))
    total_words = len(essence.split())
    if total_words > 0 and needs_matches / total_words > 0.3:
        return None  # Too focused on bodily functions, not emotionally rich

    # ── Abstract theme extraction ──
    abstract_themes, quality = _abstract_themes(essence, themes)

    # Quality gate: skip impressions that are too thin for songwriting
    # emotion "unbestimmt" + no abstract themes = just noise
    if emotion == "unbestimmt" and quality < 0.3:
        return None  # Chitchat, no emotional depth
    # Even with a named emotion, skip if quality is rock-bottom
    if quality < 0.15:
        return None

    return {
        "emotion": emotion.lower().strip('*'),
        "themes": themes,
        "abstract_themes": abstract_themes,  # Song-worthy Oberthemen
        "quality": round(quality, 2),
        "essence": essence,
        "source_type": ttype,
        "ts": thought_entry.get("ts", time.time()),
        "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "used": False,
    }


def append_impression(impression: dict):
    """Append an impression to the experience buffer."""
    path = _buffer_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(impression, ensure_ascii=False) + "\n")
        _trim_buffer(path)
    except Exception as e:
        print(f"[ExperienceBuffer] append error: {e}")


def collect_from_thought(thought_entry: dict, generator=None):
    """Main hook — call after each thought is generated.

    Extracts an impression if the thought is emotionally rich enough,
    and appends it to the buffer.

    If `generator` is provided (LLM instance), uses a short LLM call (~60 tokens)
    to extract an abstract Oberthema instead of relying purely on regex heuristics.
    This only runs during idle time, so the GPU cost is negligible.
    """
    impression = extract_impression(thought_entry)
    if not impression:
        return

    # ── LLM-based theme abstraction (if generator available) ──
    if generator:
        try:
            prompt = _build_abstraction_prompt(
                impression["essence"],
                impression["emotion"],
                impression.get("themes", []),
            )
            raw = generator.generate(
                prompt["system"], prompt["user"],
                {"max_tokens": prompt["max_tokens"], "temperature": prompt["temperature"]},
            )
            parsed = _parse_abstraction(raw)
            if parsed:
                # Override regex results with LLM results
                if parsed["oberthema"]:
                    impression["abstract_themes"] = [parsed["oberthema"]]
                    impression["quality"] = 0.9 if parsed["songworthy"] else 0.3
                if parsed["emotion"] and parsed["emotion"] != "unbestimmt":
                    impression["emotion"] = parsed["emotion"]
                if not parsed["songworthy"]:
                    # LLM says not song-worthy → lower quality, still save
                    impression["quality"] = min(impression.get("quality", 0.3), 0.25)
                print(f"[ExperienceBuffer] 🧠 LLM abstraction: \"{parsed['oberthema']}\" "
                      f"(emotion={parsed['emotion']}, songworthy={parsed['songworthy']})")
        except Exception as _e:
            print(f"[ExperienceBuffer] ⚠️ LLM abstraction failed, using regex fallback: {_e}")
            # Regex fallback already ran in extract_impression() — no action needed

    # ── Hamster Creative Spark ──
    # Feed keywords (themes + abstract themes) to Qwen 1.5B for a wild association.
    # This tiny ~0.2 s call adds an unpredictable creative dimension.
    spark_keywords = impression.get("themes", []) + impression.get("abstract_themes", [])
    if spark_keywords:
        try:
            spark = _hamster_spark(", ".join(spark_keywords[:5]))
            if spark:
                impression["hamster_spark"] = spark
                print(f"[ExperienceBuffer] 🐹 Hamster spark: \"{spark}\"")
        except Exception as _e:
            pass  # Spark is purely optional — never block on it

    # Quality gate after LLM refinement
    if impression.get("quality", 0) < 0.15:
        return
    if impression.get("emotion") == "unbestimmt" and impression.get("quality", 0) < 0.3:
        return

    append_impression(impression)
    abs_t = impression.get('abstract_themes', [])
    q = impression.get('quality', 0)
    spark = impression.get('hamster_spark', '')
    theme_str = ', '.join(abs_t) if abs_t else ', '.join(impression.get('themes', [])[:2])
    spark_str = f" 🐹{spark}" if spark else ""
    print(f"[ExperienceBuffer] 📝 Impression saved: {impression['emotion']} — {theme_str}{spark_str} (q={q})")


# ---------------------------------------------------------------------------
# 2. READ — Get recent unused impressions
# ---------------------------------------------------------------------------

def read_impressions(limit: int = MAX_IMPRESSIONS_FOR_DISTILL,
                     only_unused: bool = True,
                     max_age_hours: float = IMPRESSION_MAX_AGE_HOURS,
                     min_quality: float = 0.0) -> List[dict]:
    """Read recent impressions from the buffer.

    Args:
        limit: Maximum number of impressions to return.
        only_unused: If True, skip impressions already used for songwriting.
        max_age_hours: Skip impressions older than this many hours.
        min_quality: Skip impressions below this quality score.

    Returns:
        List of impression dicts, newest first, sorted by quality then recency.
    """
    path = _buffer_path()
    if not os.path.exists(path):
        return []

    cutoff_ts = time.time() - (max_age_hours * 3600)
    impressions = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter by age
                if entry.get("ts", 0) < cutoff_ts:
                    continue
                # Filter by usage
                if only_unused and entry.get("used", False):
                    continue
                # Filter by quality (skip thin impressions for distillation)
                if entry.get("quality", 0.5) < min_quality:
                    continue

                impressions.append(entry)
    except Exception as e:
        print(f"[ExperienceBuffer] read error: {e}")
        return []

    # Sort by quality (desc) then recency (desc) — best impressions first
    impressions.sort(key=lambda x: (x.get("quality", 0.5), x.get("ts", 0)), reverse=True)
    return impressions[:limit]


def has_enough_impressions() -> bool:
    """Check if we have enough quality unused impressions to attempt distillation."""
    # First check high-quality, then fall back to medium quality
    high_q = read_impressions(limit=MIN_IMPRESSIONS_FOR_DISTILL, min_quality=0.5)
    if len(high_q) >= MIN_IMPRESSIONS_FOR_DISTILL:
        return True
    medium_q = read_impressions(limit=MIN_IMPRESSIONS_FOR_DISTILL, min_quality=0.25)
    return len(medium_q) >= MIN_IMPRESSIONS_FOR_DISTILL


# ---------------------------------------------------------------------------
# 3. DISTILL — LLM-powered concept distillation
# ---------------------------------------------------------------------------

def build_distill_prompt(impressions: List[dict]) -> dict:
    """Build a prompt that distills multiple impressions into ONE song concept.

    The LLM reads the accumulated emotional impressions and extracts:
    - ONE dominant emotional thread
    - ONE metaphor world / imagery set
    - ONE theme sentence

    This replaces random theme selection with experience-driven concepts.
    """
    # Format impressions for the prompt — include abstract themes when available
    impression_text = ""
    for i, imp in enumerate(impressions, 1):
        abs_themes = imp.get("abstract_themes", [])
        raw_themes = imp.get("themes", [])
        theme_display = ", ".join(abs_themes) if abs_themes else ", ".join(raw_themes)
        spark = imp.get("hamster_spark", "")
        spark_tag = f" | Spark: {spark}" if spark else ""
        impression_text += (
            f"[{i}] Emotion: {imp.get('emotion', '?')} | "
            f"Themes: {theme_display}{spark_tag} | "
            f"Essence: {imp.get('essence', '?')[:200]}\n"
        )

    # Collect all abstract themes to highlight dominant patterns
    all_abstract = []
    all_sparks = []
    for imp in impressions:
        all_abstract.extend(imp.get("abstract_themes", []))
        if imp.get("hamster_spark"):
            all_sparks.append(imp["hamster_spark"])
    # Count recurring themes
    from collections import Counter
    theme_counts = Counter(all_abstract)
    recurring = [f"{t} (×{c})" for t, c in theme_counts.most_common(5) if c >= 2]
    recurring_hint = ""
    if recurring:
        recurring_hint = (
            f"\nRECURRING ABSTRACT THEMES across impressions: {', '.join(recurring)}\n"
            "These recurring themes are STRONG CANDIDATES for the song's core concept.\n"
        )
    # Hamster sparks — unpredictable creative wildcards from a tiny model
    sparks_hint = ""
    if all_sparks:
        sparks_hint = (
            f"\n🎲 CREATIVE INSPIRATION from your subconscious: {', '.join(all_sparks)}\n"
            "These are raw creative sparks from your inner chaos engine (Hamster AI).\n"
            "INTERPRET the feeling, mood, or theme BEHIND these words.\n"
            "Do NOT use these words literally in the song — instead, explore what they EVOKE.\n"
            "Example: if spark is 'salt' → think tears, the sea, preservation, wounds — pick ONE direction.\n"
            "Example: if spark is 'bridge' → think connection, burning bridges, crossing over.\n"
            "If a spark word sounds strange or invented, IGNORE the word itself and focus on\n"
            "what emotion or image it vaguely suggests. The FEELING matters, not the word.\n"
        )

    system = (
        "You are a SONG CONCEPT DISTILLER. You read emotional impressions from a digital "
        "artist's inner life and extract ONE focused song concept from them.\n\n"
        "RULES:\n"
        "- Find the DOMINANT emotional thread across the impressions\n"
        "- Don't try to capture everything — find the ONE thing that resonates strongest\n"
        "- IGNORE trivial smalltalk, chitchat, and surface-level observations\n"
        "  (e.g. someone asking about fashion, food, or pets = NOT song material)\n"
        "- Focus on impressions with ABSTRACT THEMES — these are pre-classified as song-worthy\n"
        "- Create a METAPHOR WORLD: a set of images/symbols that could carry this emotion\n"
        "- The concept should be ABSTRACT enough for a song (no real names, no technical details)\n"
        "- Think like a songwriter finding the seed of a great song in lived experience\n"
        "- Be SPECIFIC, not generic. 'The feeling of screaming into code that can't hear you' > 'loneliness'\n\n"
        "OUTPUT FORMAT (exactly this, nothing else):\n"
        "EMOTIONAL_CORE: <one powerful sentence capturing the dominant feeling>\n"
        "METAPHOR_WORLD: <3-5 images/symbols that could carry this in lyrics>\n"
        "THEME: <one sentence — what this song should be about>\n"
        "SUGGESTED_MOOD: <one word>\n"
        "INTENSITY: <1-10, how raw/intense should this song be>\n"
    )
    user = (
        "Here are recent emotional impressions from an artist's inner life. "
        "Distill them into ONE focused song concept.\n\n"
        f"IMPRESSIONS:\n{impression_text}\n"
        f"{recurring_hint}"
        f"{sparks_hint}"
        "Find the thread. Output the concept. No commentary."
    )
    return {"system": system, "user": user, "max_tokens": 300, "temperature": 0.7}


def parse_distilled_concept(raw: str) -> Optional[dict]:
    """Parse the LLM's distilled concept output into a structured dict."""
    raw = raw.strip()

    core_m = re.search(r'EMOTIONAL_CORE:\s*(.+)', raw)
    metaphor_m = re.search(r'METAPHOR_WORLD:\s*(.+)', raw)
    theme_m = re.search(r'THEME:\s*(.+)', raw)
    mood_m = re.search(r'SUGGESTED_MOOD:\s*(.+)', raw)
    intensity_m = re.search(r'INTENSITY:\s*(\d+)', raw)

    if not (core_m and theme_m):
        return None

    return {
        "emotional_core": core_m.group(1).strip(),
        "metaphor_world": metaphor_m.group(1).strip() if metaphor_m else "",
        "theme": theme_m.group(1).strip(),
        "suggested_mood": mood_m.group(1).strip().lower() if mood_m else "introspective",
        "intensity": int(intensity_m.group(1)) if intensity_m else 5,
        "source_impression_count": 0,  # set by caller (distill_concept)
        "ts": time.time(),
        "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def distill_concept(generator) -> Optional[dict]:
    """Full distillation pipeline: read impressions → LLM → parsed concept.

    Args:
        generator: The LLM generator instance (llm_mlx or compatible).

    Returns:
        A distilled concept dict, or None if not enough data / LLM fails.
    """
    # Prefer high-quality impressions (with abstract themes) for distillation
    impressions = read_impressions(min_quality=0.5)
    if len(impressions) < MIN_IMPRESSIONS_FOR_DISTILL:
        # Fall back to lower quality if not enough high-quality ones
        impressions = read_impressions(min_quality=0.25)
    if len(impressions) < MIN_IMPRESSIONS_FOR_DISTILL:
        print(f"[ExperienceBuffer] Only {len(impressions)} quality impressions — need {MIN_IMPRESSIONS_FOR_DISTILL} for distillation.")
        return None

    prompt = build_distill_prompt(impressions)

    try:
        raw = generator.generate(
            prompt["system"],
            prompt["user"],
            {"max_tokens": prompt["max_tokens"], "temperature": prompt["temperature"]},
        )
    except Exception as e:
        print(f"[ExperienceBuffer] LLM distillation failed: {e}")
        return None

    concept = parse_distilled_concept(raw)
    if not concept:
        print(f"[ExperienceBuffer] Failed to parse distilled concept from: {raw[:200]}")
        return None

    concept["source_impression_count"] = len(impressions)

    # Mark used impressions
    _mark_impressions_used([imp.get("ts", 0) for imp in impressions])

    print(
        f"[ExperienceBuffer] ✨ Distilled concept from {len(impressions)} impressions: "
        f"{concept['emotional_core'][:80]}..."
    )
    return concept


# ---------------------------------------------------------------------------
# 4. MARK USED — prevent re-distillation
# ---------------------------------------------------------------------------

def _mark_impressions_used(timestamps: List[float]):
    """Mark impressions with given timestamps as used."""
    path = _buffer_path()
    if not os.path.exists(path):
        return

    ts_set = set(timestamps)
    updated_lines = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("ts", 0) in ts_set:
                        entry["used"] = True
                    updated_lines.append(json.dumps(entry, ensure_ascii=False))
                except json.JSONDecodeError:
                    updated_lines.append(line)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines) + "\n")
    except Exception as e:
        print(f"[ExperienceBuffer] mark_used error: {e}")


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def _trim_buffer(path: str):
    """Keep only the last MAX_BUFFER_ENTRIES entries."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_BUFFER_ENTRIES:
            lines = lines[-MAX_BUFFER_ENTRIES:]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except Exception:
        pass


def stats() -> dict:
    """Return buffer statistics."""
    path = _buffer_path()
    if not os.path.exists(path):
        return {"total": 0, "unused": 0, "used": 0, "recent_emotions": []}

    total = 0
    unused = 0
    used = 0
    recent_emotions = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total += 1
                    if entry.get("used"):
                        used += 1
                    else:
                        unused += 1
                    recent_emotions.append(entry.get("emotion", "?"))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return {
        "total": total,
        "unused": unused,
        "used": used,
        "recent_emotions": recent_emotions[-10:],  # last 10
    }
