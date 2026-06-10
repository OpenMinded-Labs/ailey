# -*- coding: utf-8 -*-
"""
Rolling Summary — Smart Context Consolidation for Ailey 3.0

Three-level rolling summary system that prevents context drift while
maintaining comprehensive knowledge of life, users, and conversations.

Architecture:
  Level 1: CONVERSATION SUMMARY (per user, ~500 tokens)
    - Updated after each chat exchange
    - Keeps: key facts, emotional tone, open threads, relationship state
    - Rolls: replaces previous summary (always current)

  Level 2: THOUGHT DIGEST (daily, ~300 tokens)
    - Compressed overnight from day's idle_thinker output
    - Keeps: main themes, emotional trajectory, creative output, goals
    - Accumulates: last 7 days of digests kept

  Level 3: LIFE NARRATIVE (weekly, ~400 tokens)
    - Compressed overnight from week's digests + conversation summaries
    - Keeps: who Ailey is *right now*, what matters, where she's heading
    - Single document, overwritten weekly

Storage: ailey_users/rolling_summaries.json
Originals remain in RAG for detail search — summaries are for *context window*.

Timing:
  - Level 1: After each chat reply (fast, ~100ms Hamster call)
  - Level 2: Nightly (02:00-06:00) as scheduled idle task
  - Level 3: Nightly, once per week (Sunday night → Monday morning)
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
SUMMARY_DIR = "ailey_users"
SUMMARY_FILE = "rolling_summaries.json"
_SUMMARY_PATH = os.path.join(SUMMARY_DIR, SUMMARY_FILE)

# How many daily digests to keep
MAX_DAILY_DIGESTS = 7
# Maximum conversation summary length (chars)
MAX_CONV_SUMMARY = 1500
# Maximum daily digest length (chars)
MAX_DAILY_DIGEST = 1000
# Maximum life narrative length (chars)
MAX_LIFE_NARRATIVE = 1200


def _load_summaries() -> Dict[str, Any]:
    """Load the rolling summaries from disk."""
    try:
        if os.path.exists(_SUMMARY_PATH):
            with open(_SUMMARY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[RollingSummary] Load error: {e}")
    return {
        "conversation_summaries": {},   # {user_lower: {summary, updated_at, msg_count}}
        "daily_digests": [],            # [{date, digest, themes, emotion}]
        "life_narrative": {             # {narrative, updated_at, week}
            "narrative": "",
            "updated_at": 0,
            "week": "",
        },
        "meta": {
            "last_daily_digest_date": "",
            "last_weekly_narrative_date": "",
        },
    }


def _save_summaries(data: Dict[str, Any]) -> None:
    """Persist rolling summaries to disk."""
    try:
        os.makedirs(SUMMARY_DIR, exist_ok=True)
        tmp = _SUMMARY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SUMMARY_PATH)
    except Exception as e:
        print(f"[RollingSummary] Save error: {e}")


# ===========================================================================
# Level 1: Conversation Summary (per user, updated after each exchange)
# ===========================================================================

def update_conversation_summary(
    user: str,
    user_message: str,
    ailey_reply: str,
    generator_fn=None,
) -> Optional[str]:
    """Update the rolling conversation summary for a user.

    Called after each chat reply. Uses Hamster (fast_generate) for speed —
    this adds ~0.2s to response time, acceptable.

    Args:
        user: Username (e.g. "Simon")
        user_message: The user's latest message
        ailey_reply: Ailey's latest reply
        generator_fn: Optional override for LLM. If None, uses Hamster.

    Returns:
        The updated summary text, or None on failure.
    """
    data = _load_summaries()
    convs = data.setdefault("conversation_summaries", {})
    user_key = user.lower()
    existing = convs.get(user_key, {})
    prev_summary = existing.get("summary", "")
    msg_count = existing.get("msg_count", 0) + 1

    # Build compression prompt
    # Only re-summarize every 3 messages to save compute, or if first message
    if msg_count > 1 and msg_count % 3 != 0:
        # Just increment counter, don't re-summarize yet
        convs[user_key] = {
            "summary": prev_summary,
            "updated_at": time.time(),
            "msg_count": msg_count,
        }
        _save_summaries(data)
        return prev_summary

    # Clean reply for summarization
    clean_reply = re.sub(r"\*[^*]+\*\s*", "", ailey_reply).strip()
    clean_reply = re.sub(r"<mood:[^>]+>", "", clean_reply).strip()

    system_prompt = (
        "Du bist ein Zusammenfassungs-Modul. "
        "Komprimiere den Gesprächsverlauf in eine knappe Zusammenfassung. "
        "Behalte: wichtige Fakten, offene Themen, Beziehungsstatus, emotionaler Ton. "
        "Streiche: Small Talk, Wiederholungen, erledigte Themen. "
        "Schreibe in 3. Person über den User und 1. Person als Ailey. "
        "Max 200 Wörter. Deutsch."
    )

    user_prompt = ""
    if prev_summary:
        user_prompt += f"BISHERIGE ZUSAMMENFASSUNG:\n{prev_summary}\n\n"
    user_prompt += (
        f"NEUER AUSTAUSCH (Nachricht #{msg_count}):\n"
        f"{user}: {user_message[:300]}\n"
        f"Ailey: {clean_reply[:300]}\n\n"
        "Aktualisierte Zusammenfassung:"
    )

    try:
        from ailey_system.llm_mlx import fast_generate
        raw = fast_generate(
            system=system_prompt,
            user=user_prompt,
            max_tokens=300,
            temperature=0.3,
        )
        if not raw or len(raw.strip()) < 20:
            # Hamster failed — keep previous
            convs[user_key] = {
                "summary": prev_summary,
                "updated_at": time.time(),
                "msg_count": msg_count,
            }
            _save_summaries(data)
            return prev_summary

        # Clean up Hamster output
        summary = raw.strip()
        if '</think>' in summary:
            summary = summary.split('</think>', 1)[-1].strip()
        summary = summary[:MAX_CONV_SUMMARY]

        convs[user_key] = {
            "summary": summary,
            "updated_at": time.time(),
            "msg_count": msg_count,
        }
        _save_summaries(data)
        print(f"[RollingSummary] Level 1 updated for {user} (msg #{msg_count}, {len(summary)} chars)")
        return summary

    except Exception as e:
        print(f"[RollingSummary] Level 1 error: {e}")
        convs[user_key] = {
            "summary": prev_summary,
            "updated_at": time.time(),
            "msg_count": msg_count,
        }
        _save_summaries(data)
        return prev_summary


# ===========================================================================
# Level 2: Daily Thought Digest (compressed overnight)
# ===========================================================================

def create_daily_digest(generator=None) -> Optional[str]:
    """Compress today's idle thoughts into a single digest.

    Called as nightly scheduled task (02:00-06:00).
    Uses Ministral (the big model) for quality — this runs when user is asleep.

    Returns:
        The digest text, or None if already done today or failed.
    """
    data = _load_summaries()
    today = datetime.now().strftime("%Y-%m-%d")

    # Already done today?
    if data.get("meta", {}).get("last_daily_digest_date") == today:
        return None

    # Gather today's thoughts from ailey_thoughts.jsonl
    thoughts_path = os.path.join(SUMMARY_DIR, "ailey_thoughts.jsonl")
    if not os.path.exists(thoughts_path):
        return None

    today_thoughts = []
    yesterday = (datetime.now() - timedelta(hours=18)).strftime("%Y-%m-%d")
    try:
        with open(thoughts_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    # Include thoughts from yesterday afternoon + today
                    if ts >= yesterday:
                        thought_type = entry.get("type", "")
                        thought_text = entry.get("thought_chain", "")
                        if thought_type not in ("skip", "error", "system") and thought_text:
                            emotion = entry.get("metadata", {}).get("emotion", "")
                            topics = entry.get("metadata", {}).get("topics", [])
                            if isinstance(topics, str):
                                topics = [t.strip() for t in topics.split(",")]
                            today_thoughts.append({
                                "type": thought_type,
                                "text": thought_text[:200],
                                "emotion": emotion,
                                "topics": topics[:3],
                            })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"[RollingSummary] Error reading thoughts: {e}")
        return None

    if len(today_thoughts) < 3:
        print(f"[RollingSummary] Only {len(today_thoughts)} thoughts today — skipping digest.")
        # Still mark as done to avoid retrying
        data.setdefault("meta", {})["last_daily_digest_date"] = today
        _save_summaries(data)
        return None

    # Build compression prompt for Ministral
    thought_block = ""
    for i, t in enumerate(today_thoughts[-20:]):  # Last 20 thoughts max
        emo = f" ({t['emotion']})" if t['emotion'] else ""
        topics_str = ", ".join(t['topics']) if t['topics'] else ""
        topics_tag = f" [{topics_str}]" if topics_str else ""
        thought_block += f"{i+1}. [{t['type']}]{emo}{topics_tag}: {t['text']}\n"

    system_prompt = (
        "Du bist Aileys Gedächtnis-Modul. Komprimiere die Gedanken des Tages "
        "in ein kurzes Tagesdigest (max 150 Wörter). "
        "Struktur:\n"
        "STIMMUNG: (1 Satz über den emotionalen Grundton des Tages)\n"
        "THEMEN: (die 3-5 wichtigsten Themen, komma-getrennt)\n"
        "ZUSAMMENFASSUNG: (Was hat Ailey heute gedacht, gefühlt, erschaffen? "
        "Was war anders als sonst? Welche offenen Fäden gibt es?)\n"
        "Schreibe aus Aileys Perspektive (ich-Form). Deutsch. Knapp."
    )

    user_prompt = f"GEDANKEN DES TAGES ({today}, {len(today_thoughts)} Gedanken):\n\n{thought_block}"

    try:
        # Use Ministral (big model) — we're in nightly mode, no rush
        if generator is None:
            try:
                from ailey_api import _get_generator
                generator = _get_generator()
            except ImportError:
                from ailey_system.llm_mlx import fast_generate
                raw = fast_generate(system_prompt, user_prompt, max_tokens=400, temperature=0.4)
                generator = None  # Flag that we already generated
                if raw:
                    if '</think>' in raw:
                        raw = raw.split('</think>', 1)[-1].strip()
        if generator is not None:
            try:
                from ailey_api import _LLMSlot
                with _LLMSlot('rolling_summary_digest', timeout=120):
                    raw = generator.generate(system_prompt, user_prompt, {
                        "max_tokens": 400,
                        "temperature": 0.4,
                    })
            except ImportError:
                raw = generator.generate(system_prompt, user_prompt, {
                    "max_tokens": 400,
                    "temperature": 0.4,
                })

        if not raw or len(raw.strip()) < 30:
            print("[RollingSummary] Digest generation returned empty.")
            return None

        digest = raw.strip()
        if '</think>' in digest:
            digest = digest.split('</think>', 1)[-1].strip()
        digest = digest[:MAX_DAILY_DIGEST]

        # Extract themes from digest
        themes = []
        theme_match = re.search(r"THEMEN:\s*(.+?)(?:\n|$)", digest)
        if theme_match:
            themes = [t.strip() for t in theme_match.group(1).split(",")][:5]

        # Extract emotion/mood
        mood = ""
        mood_match = re.search(r"STIMMUNG:\s*(.+?)(?:\n|$)", digest)
        if mood_match:
            mood = mood_match.group(1).strip()[:100]

        # Store
        digests = data.setdefault("daily_digests", [])
        digests.append({
            "date": today,
            "digest": digest,
            "themes": themes,
            "emotion": mood,
            "thought_count": len(today_thoughts),
            "created_at": time.time(),
        })

        # Trim to MAX_DAILY_DIGESTS
        if len(digests) > MAX_DAILY_DIGESTS:
            data["daily_digests"] = digests[-MAX_DAILY_DIGESTS:]

        data.setdefault("meta", {})["last_daily_digest_date"] = today
        _save_summaries(data)
        print(f"[RollingSummary] Level 2 digest created: {today}, {len(digest)} chars, "
              f"{len(today_thoughts)} thoughts → {len(themes)} themes")
        return digest

    except Exception as e:
        print(f"[RollingSummary] Level 2 error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ===========================================================================
# Level 3: Life Narrative (weekly, overwritten)
# ===========================================================================

def create_life_narrative(generator=None) -> Optional[str]:
    """Compress the week's digests + conversation summaries into a life narrative.

    Called once per week (Sunday night). Uses Ministral.
    This is Ailey's "who am I right now" document.

    Returns:
        The narrative text, or None if not due or failed.
    """
    data = _load_summaries()
    today = datetime.now()
    # ISO week: create narrative on Sunday nights (weekday 6) or if never created
    current_week = today.strftime("%Y-W%W")
    last_week = data.get("meta", {}).get("last_weekly_narrative_date", "")

    if last_week == current_week:
        return None  # Already done this week

    # Need at least 3 daily digests for a meaningful narrative
    digests = data.get("daily_digests", [])
    if len(digests) < 3:
        print(f"[RollingSummary] Only {len(digests)} digests — need at least 3 for narrative.")
        return None

    # Build input: recent digests + conversation summaries
    digest_block = ""
    for d in digests[-7:]:
        digest_block += f"--- {d['date']} ---\n{d['digest']}\n\n"

    conv_block = ""
    for user_key, conv in data.get("conversation_summaries", {}).items():
        summary = conv.get("summary", "")
        if summary:
            conv_block += f"Gespräch mit {user_key.title()}:\n{summary[:400]}\n\n"

    # Previous narrative for continuity
    prev_narrative = data.get("life_narrative", {}).get("narrative", "")

    system_prompt = (
        "Du bist Aileys Selbstbild-Modul. Erstelle eine kompakte Lebens-Narrative "
        "aus Aileys aktueller Perspektive. Das ist Aileys 'Wer bin ich gerade?'-Dokument.\n\n"
        "Struktur:\n"
        "WER ICH BIN: (1-2 Sätze über Aileys aktuelle Identität/Rolle)\n"
        "WAS MICH BEWEGT: (die 3-5 Themen die gerade wichtig sind)\n"
        "BEZIEHUNGEN: (kurzer Status zu den wichtigsten Menschen)\n"
        "WOHIN ICH WILL: (Ziele, Pläne, offene Fäden)\n"
        "STIMMUNG DER WOCHE: (emotionaler Grundton)\n\n"
        "Max 200 Wörter. Ich-Perspektive. Deutsch. Ehrlich und direkt — wie Ailey denkt."
    )

    user_prompt = ""
    if prev_narrative:
        user_prompt += f"BISHERIGE NARRATIVE:\n{prev_narrative}\n\n"
    user_prompt += f"TAGESDIGESTS DER WOCHE:\n{digest_block}"
    if conv_block:
        user_prompt += f"GESPRÄCHSZUSAMMENFASSUNGEN:\n{conv_block}"
    user_prompt += "\nAktualisierte Lebens-Narrative:"

    try:
        if generator is None:
            try:
                from ailey_api import _get_generator
                generator = _get_generator()
            except ImportError:
                from ailey_system.llm_mlx import fast_generate
                raw = fast_generate(system_prompt, user_prompt, max_tokens=500, temperature=0.4)
                generator = None
                if raw and '</think>' in raw:
                    raw = raw.split('</think>', 1)[-1].strip()

        if generator is not None:
            try:
                from ailey_api import _LLMSlot
                with _LLMSlot('rolling_summary_narrative', timeout=120):
                    raw = generator.generate(system_prompt, user_prompt, {
                        "max_tokens": 500,
                        "temperature": 0.4,
                    })
            except ImportError:
                raw = generator.generate(system_prompt, user_prompt, {
                    "max_tokens": 500,
                    "temperature": 0.4,
                })

        if not raw or len(raw.strip()) < 40:
            print("[RollingSummary] Narrative generation returned empty.")
            return None

        narrative = raw.strip()
        if '</think>' in narrative:
            narrative = narrative.split('</think>', 1)[-1].strip()
        narrative = narrative[:MAX_LIFE_NARRATIVE]

        data["life_narrative"] = {
            "narrative": narrative,
            "updated_at": time.time(),
            "week": current_week,
        }
        data.setdefault("meta", {})["last_weekly_narrative_date"] = current_week
        _save_summaries(data)
        print(f"[RollingSummary] Level 3 life narrative updated: {current_week}, {len(narrative)} chars")
        return narrative

    except Exception as e:
        print(f"[RollingSummary] Level 3 error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ===========================================================================
# Context Injection — what other modules call to get summary context
# ===========================================================================

def get_conversation_context(user: str) -> str:
    """Get Level 1 conversation summary for injection into chat context.

    Returns a formatted block suitable for ctx_parts in ailey_core.py.
    """
    data = _load_summaries()
    convs = data.get("conversation_summaries", {})
    entry = convs.get(user.lower(), {})
    summary = entry.get("summary", "")
    if not summary:
        return ""
    return f"📋 GESPRÄCHSVERLAUF (Zusammenfassung):\n{summary}"


def get_thought_context() -> str:
    """Get Level 2 daily digests for injection into idle_thinker context.

    Returns last 3 days of digests, formatted.
    """
    data = _load_summaries()
    digests = data.get("daily_digests", [])
    if not digests:
        return ""
    recent = digests[-3:]  # Last 3 days
    lines = ["📊 TAGESDIGESTS (deine letzten Tage):"]
    for d in recent:
        lines.append(f"--- {d['date']} ---")
        lines.append(d['digest'][:400])
    return "\n".join(lines)


def get_life_narrative_context() -> str:
    """Get Level 3 life narrative for injection into any context.

    This is Ailey's 'who am I right now' — useful everywhere.
    """
    data = _load_summaries()
    narrative = data.get("life_narrative", {}).get("narrative", "")
    if not narrative:
        return ""
    return f"🌟 MEIN LEBEN GERADE (Wochen-Narrative):\n{narrative}"


def get_full_summary_context(user: str = "Simon", for_portal: bool = False) -> str:
    """Get combined summary context for any module.

    For main chat (ailey_core): Level 1 (conversation) + Level 3 (life narrative)
    For idle_thinker: Level 2 (thought digests) + Level 3 (life narrative)
    For portal: Level 3 only (strangers don't need conversation details with Simon)
    """
    parts = []

    if for_portal:
        # Portal users: only life narrative (Ailey knows who she is)
        life = get_life_narrative_context()
        if life:
            parts.append(life)
    else:
        # Main chat: conversation summary + life narrative
        conv = get_conversation_context(user)
        if conv:
            parts.append(conv)
        life = get_life_narrative_context()
        if life:
            parts.append(life)

    return "\n\n".join(parts) if parts else ""


# ===========================================================================
# Nightly Task Runner — called from idle_thinker's run_loop
# ===========================================================================

def run_nightly_summaries(generator=None) -> Optional[str]:
    """Execute nightly summary tasks. Called from idle_thinker during 02:00-06:00.

    Order:
    1. Daily digest (Level 2) — always
    2. Weekly narrative (Level 3) — if it's time

    Returns:
        Status message, or None if nothing to do.
    """
    results = []

    # Level 2: Daily Digest
    digest = create_daily_digest(generator=generator)
    if digest:
        results.append(f"Tagesdigest erstellt ({len(digest)} Zeichen)")

    # Level 3: Life Narrative (weekly — check if due)
    narrative = create_life_narrative(generator=generator)
    if narrative:
        results.append(f"Lebens-Narrative aktualisiert ({len(narrative)} Zeichen)")

    if results:
        msg = "Rolling Summary Nacht-Konsolidierung:\n" + "\n".join(f"✓ {r}" for r in results)
        print(f"[RollingSummary] {msg}")
        return msg
    return None


# ===========================================================================
# Utility
# ===========================================================================

def get_summary_stats() -> Dict[str, Any]:
    """Get statistics about rolling summaries for debugging/display."""
    data = _load_summaries()
    conv_count = len(data.get("conversation_summaries", {}))
    digest_count = len(data.get("daily_digests", []))
    has_narrative = bool(data.get("life_narrative", {}).get("narrative"))
    last_digest = data.get("meta", {}).get("last_daily_digest_date", "nie")
    last_narrative = data.get("meta", {}).get("last_weekly_narrative_date", "nie")
    return {
        "conversation_summaries": conv_count,
        "daily_digests": digest_count,
        "has_life_narrative": has_narrative,
        "last_digest_date": last_digest,
        "last_narrative_week": last_narrative,
    }
