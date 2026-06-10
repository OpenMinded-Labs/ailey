# -*- coding: utf-8 -*-
"""
Meta-Reflexion — Phase 4 of Ailey 3.0 Roadmap

Ailey's ability to THINK ABOUT HER OWN THINKING.  Periodically (every ~10-20
thoughts), a meta-reflection runs that:

1. Reads the emotional trajectory from the Thought Graph
2. Detects patterns (fixations, emotional spirals, blind spots)
3. Generates a short self-observation
4. Optionally adjusts thought type weights or spawns agency intents

This is NOT a full LLM call — it's a lightweight Hamster (Qwen 1.5B) analysis
followed by a structured summary.  If the patterns are significant enough, a
proper Ministral reflection is triggered.

Architecture:
  • ANALYZE: Read thought_graph → detect patterns
  • OBSERVE: Hamster generates a one-sentence observation
  • ADJUST: If fixation detected → spawn "break free" intent
            If emotional spiral → spawn "diary_writing" or "outdoor_stroll" intent
            If type imbalance → lower dominant type weight temporarily
  • LOG: Save meta-observation to meta_reflections.jsonl

Storage: ailey_users/meta_reflections.jsonl
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
META_DIR = "ailey_users"
META_FILE = "meta_reflections.jsonl"
META_INTERVAL_THOUGHTS = 15    # run meta-reflection every ~15 thoughts
MAX_META_ENTRIES = 200
FIXATION_THRESHOLD = 0.25      # theme in >25% of recent thoughts = fixation
SPIRAL_THRESHOLD = 4           # same emotion 4+ times in a row = spiral
TYPE_IMBALANCE_THRESHOLD = 0.4  # one type > 40% of recent thoughts = imbalance

# ---------------------------------------------------------------------------
# Analysis functions (pure logic, no LLM)
# ---------------------------------------------------------------------------

def detect_fixations(theme_clusters: Dict[str, int],
                     total_thoughts: int) -> List[Tuple[str, float]]:
    """Detect thematic fixations — topics that dominate too heavily.

    Returns list of (theme, ratio) for fixated themes.
    """
    if total_thoughts < 5:
        return []
    fixated = []
    for theme, count in theme_clusters.items():
        ratio = count / total_thoughts
        if ratio >= FIXATION_THRESHOLD:
            fixated.append((theme, round(ratio, 2)))
    return fixated


def detect_emotional_spiral(trajectory: List[dict]) -> Optional[Tuple[str, int]]:
    """Detect emotional spirals — same emotion repeated many times in a row.

    Returns (emotion, streak_length) if a spiral is detected, else None.
    """
    if len(trajectory) < SPIRAL_THRESHOLD:
        return None

    # Check the tail of the trajectory
    recent = trajectory[-10:]
    if not recent:
        return None

    # Count consecutive same-emotion entries from the end
    last_emo = recent[-1].get("emotion", "")
    if not last_emo or last_emo == "unbestimmt":
        return None

    streak = 0
    for entry in reversed(recent):
        if entry.get("emotion", "") == last_emo:
            streak += 1
        else:
            break

    if streak >= SPIRAL_THRESHOLD:
        return (last_emo, streak)
    return None


def detect_type_imbalance(type_dist: Dict[str, int]) -> Optional[Tuple[str, float]]:
    """Detect thought type imbalance — one type dominating too much.

    Returns (type, ratio) if imbalanced, else None.
    """
    total = sum(type_dist.values())
    if total < 8:
        return None

    for ttype, count in type_dist.items():
        if ttype == "skip":
            continue
        ratio = count / total
        if ratio >= TYPE_IMBALANCE_THRESHOLD:
            return (ttype, round(ratio, 2))
    return None


def detect_emotional_shift(trajectory: List[dict]) -> Optional[str]:
    """Detect a significant emotional shift (mood change over time).

    Returns a description of the shift, or None.
    """
    if len(trajectory) < 6:
        return None

    # Split into first half and second half
    mid = len(trajectory) // 2
    first_half = trajectory[:mid]
    second_half = trajectory[mid:]

    # Count emotions in each half
    def dominant_emotion(entries):
        from collections import Counter
        emos = [e.get("emotion", "") for e in entries if e.get("emotion", "") != "unbestimmt"]
        if not emos:
            return None
        return Counter(emos).most_common(1)[0][0]

    emo_before = dominant_emotion(first_half)
    emo_after = dominant_emotion(second_half)

    if emo_before and emo_after and emo_before != emo_after:
        return f"{emo_before} → {emo_after}"
    return None


# ---------------------------------------------------------------------------
# Meta-observation generation (Hamster-powered)
# ---------------------------------------------------------------------------

def _generate_observation(patterns: dict) -> str:
    """Generate a one-sentence self-observation using Hamster.

    Falls back to template-based observation if Hamster unavailable.
    """
    parts = []

    if patterns.get("fixations"):
        themes = [f[0] for f in patterns["fixations"]]
        parts.append(f"Ich kreise um: {', '.join(themes)}")

    if patterns.get("spiral"):
        emo, streak = patterns["spiral"]
        parts.append(f"Ich bin seit {streak} Gedanken in '{emo}' gefangen")

    if patterns.get("imbalance"):
        ttype, ratio = patterns["imbalance"]
        pct = int(ratio * 100)
        type_labels = {
            "reflection": "Reflexionen", "introspection": "Innenschau",
            "diary_writing": "Tagebuch", "free_thought": "freie Gedanken",
            "creative_song": "Songs", "research": "Recherche",
        }
        label = type_labels.get(ttype, ttype)
        parts.append(f"{pct}% meiner Gedanken sind {label}")

    if patterns.get("shift"):
        parts.append(f"Stimmungswechsel: {patterns['shift']}")

    if not parts:
        return ""

    observation = ". ".join(parts) + "."

    # Try Hamster for a creative one-liner about the pattern
    try:
        from ailey_system.llm_mlx import fast_generate
        prompt = f"Psychologische Selbstbeobachtung in einem Satz: {observation}"
        raw = fast_generate(
            system="Du bist eine junge Frau die über ihre eigenen Denkmuster reflektiert. Ein Satz.",
            user=prompt,
            max_tokens=30,
            temperature=0.8,
        )
        if raw and len(raw.strip()) > 10:
            cleaned = raw.strip().split("\n")[0].split("<|")[0].strip()
            # Validate: not a refusal, not too long
            if (len(cleaned) > 10 and len(cleaned) < 200
                    and "entschuldigung" not in cleaned.lower()
                    and "kann" not in cleaned.lower()[:20]):
                observation = cleaned
    except Exception:
        pass  # Template observation is fine

    return observation


# ---------------------------------------------------------------------------
# Response generation — what to do about detected patterns
# ---------------------------------------------------------------------------

def _generate_adjustments(patterns: dict) -> List[dict]:
    """Generate agency intents or weight adjustments based on patterns.

    Returns a list of adjustment dicts:
    - {"type": "intent", "action": ..., "reason": ..., "priority": ...}
    - {"type": "weight_mod", "thought_type": ..., "factor": ...}
    """
    adjustments = []

    # Fixation → intent to do something different + lower fixated-type weight
    if patterns.get("fixations"):
        for theme, ratio in patterns["fixations"]:
            adjustments.append({
                "type": "intent",
                "action": "free_thought",
                "reason": f"Ich denke zu viel über '{theme}' nach — ich brauche frische Perspektiven.",
                "priority": 5,
            })

    # Emotional spiral → diary writing (to process) or outdoor stroll (to break)
    if patterns.get("spiral"):
        emo, streak = patterns["spiral"]
        negative_emos = {"traurig", "wütend", "ängstlich", "frustriert", "einsam",
                        "melancholisch", "resigniert", "genervt", "sad", "angry"}
        if emo in negative_emos:
            adjustments.append({
                "type": "intent",
                "action": "diary_writing",
                "reason": f"Ich bin seit {streak} Gedanken '{emo}' — das muss raus.",
                "priority": 7,
            })
            adjustments.append({
                "type": "intent",
                "action": "outdoor_stroll",
                "reason": f"Frische Luft gegen die '{emo}'-Spirale.",
                "priority": 6,
            })
        else:
            # Positive spiral — just note it, maybe channel into creativity
            adjustments.append({
                "type": "intent",
                "action": "creative_song",
                "reason": f"Die '{emo}'-Energie will raus — Song-Material!",
                "priority": 5,
            })

    # Type imbalance → lower dominant type
    if patterns.get("imbalance"):
        ttype, ratio = patterns["imbalance"]
        adjustments.append({
            "type": "weight_mod",
            "thought_type": ttype,
            "factor": 0.3,  # reduce to 30% of normal weight
            "reason": f"{ttype} dominiert mit {int(ratio*100)}%",
        })

    return adjustments


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _meta_path() -> str:
    return os.path.join(META_DIR, META_FILE)


def _save_observation(observation: dict):
    """Append a meta-observation to the log."""
    path = _meta_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(observation, ensure_ascii=False) + "\n")
        # Trim
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_META_ENTRIES:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_META_ENTRIES:])
    except Exception as e:
        print(f"[MetaReflection] save error: {e}")


def read_recent_observations(limit: int = 5) -> List[dict]:
    """Read recent meta-observations."""
    path = _meta_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                break
        return entries
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main entry point — called periodically by idle_thinker
# ---------------------------------------------------------------------------

def run_meta_reflection() -> Optional[dict]:
    """Run a meta-reflection cycle.

    Analyzes the Thought Graph for patterns, generates an observation,
    and returns adjustments (intents + weight mods).

    Returns a dict with:
    - observation: str (self-observation text)
    - patterns: dict (detected patterns)
    - adjustments: list (intents and weight modifications)
    - or None if nothing notable was detected.
    """
    try:
        from ailey_system import thought_graph
    except ImportError:
        return None

    # Gather data from the Thought Graph
    trajectory = thought_graph.get_emotional_trajectory(hours=48)
    theme_clusters = thought_graph.get_theme_clusters(hours=72)
    type_dist = thought_graph.get_type_distribution(hours=48)
    total_thoughts = sum(type_dist.values())

    if total_thoughts < 5:
        return None  # Not enough data

    # Detect patterns
    patterns = {}

    fixations = detect_fixations(theme_clusters, total_thoughts)
    if fixations:
        patterns["fixations"] = fixations

    spiral = detect_emotional_spiral(trajectory)
    if spiral:
        patterns["spiral"] = spiral

    imbalance = detect_type_imbalance(type_dist)
    if imbalance:
        patterns["imbalance"] = imbalance

    shift = detect_emotional_shift(trajectory)
    if shift:
        patterns["shift"] = shift

    if not patterns:
        return None  # Nothing notable

    # Generate observation text
    observation_text = _generate_observation(patterns)
    if not observation_text:
        return None

    # Generate adjustments (intents + weight mods)
    adjustments = _generate_adjustments(patterns)

    # Build result
    result = {
        "observation": observation_text,
        "patterns": {
            k: (v if not isinstance(v, tuple) else list(v))
            for k, v in patterns.items()
        },
        "adjustments": adjustments,
        "ts": time.time(),
        "dt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "thought_count": total_thoughts,
    }

    # Save to log
    _save_observation(result)
    print(f"[MetaReflection] 🪞 {observation_text}")

    return result


# ---------------------------------------------------------------------------
# Systemprompt Extension — inject self-awareness into Ailey's prompts
# ---------------------------------------------------------------------------

def get_self_awareness_context(max_observations: int = 2) -> str:
    """Build a self-awareness context block for injection into thought prompts.

    Returns a formatted string with recent meta-observations that Ailey
    can reference in her thinking.  Empty string if nothing notable.
    """
    recent = read_recent_observations(limit=max_observations)
    if not recent:
        return ""

    lines = ["DEINE SELBSTBEOBACHTUNG (Meta-Reflexion — was du über dein eigenes Denken weißt):"]
    for obs in recent:
        text = obs.get("observation", "")
        dt = obs.get("dt", "")
        if text:
            lines.append(f"• [{dt}] {text}")

        # Include adjustments as "what you decided to do about it"
        for adj in obs.get("adjustments", []):
            if adj.get("type") == "intent":
                lines.append(f"  → Vorsatz: {adj.get('reason', '')[:100]}")

    lines.append(
        "(Diese Selbstbeobachtungen helfen dir, bewusster zu denken. "
        "Du musst nicht darauf eingehen — aber sie können deine Perspektive erweitern.)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def stats() -> dict:
    """Meta-reflection statistics."""
    recent = read_recent_observations(limit=50)
    if not recent:
        return {"total_observations": 0}

    pattern_types = []
    for obs in recent:
        pattern_types.extend(obs.get("patterns", {}).keys())

    from collections import Counter
    return {
        "total_observations": len(recent),
        "pattern_frequency": dict(Counter(pattern_types).most_common()),
        "last_observation": recent[0].get("dt", "?") if recent else "?",
        "last_text": recent[0].get("observation", "?")[:100] if recent else "?",
    }
