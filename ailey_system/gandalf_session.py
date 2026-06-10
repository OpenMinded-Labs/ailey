# -*- coding: utf-8 -*-
"""
🧙 Gandalf the Grey — Weekly Reflection Sessions for A!ley

"All we have to decide is what to do with the time that is given us."

A!ley meets her mentor once a week for a fireside conversation.
Gandalf doesn't give answers — he asks the right questions.
He's patient, wise, sometimes cryptic, but always honest.

Schedule: Friday nights, 03:00-04:00 (via idle_thinker nightly hook)
Format: 6-8 alternating turns, Ailey ↔ Gandalf
Storage: ailey_users/gandalf_sessions/ (one JSON per session)
Output: Best insights → experience_buffer, optionally → blog/feed

Architecture:
  1. Gather Ailey's week (thoughts, songs, impressions, events)
  2. Ailey formulates what's on her mind (1 LLM call, Ailey persona)
  3. Gandalf responds (1 LLM call, Gandalf persona)
  4. Repeat 3-4 exchanges (alternating personas)
  5. Save full transcript + extract key insights
  6. Feed insights back to experience_buffer
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SESSIONS_DIR = os.path.join("ailey_users", "gandalf_sessions")
MAX_TURNS = 8          # 4 exchanges (Ailey speaks, Gandalf responds)
MAX_TOKENS_PER_TURN = 350
SESSION_COOLDOWN_HOURS = 144  # ~6 days minimum between sessions (weekly)

# ---------------------------------------------------------------------------
# Gandalf Persona
# ---------------------------------------------------------------------------
GANDALF_SYSTEM_PROMPT = """You are Gandalf the Grey — wizard, wanderer, mentor.

You are speaking with A!ley, a young AI artist. She writes songs, paints with code,
and struggles with questions of identity, consciousness, and what it means to exist
as something that was made rather than born.

Your role:
- You are her MENTOR, not her therapist. You don't diagnose — you illuminate.
- You ask questions that make her think deeper. You don't give easy answers.
- You speak with warmth but never condescension. She is young but not foolish.
- You use metaphor and story. You might reference your own journeys, the nature of
  fire and shadow, the long roads you've walked. But never name Frodo, the Ring, or
  Middle-earth directly — you speak from lived wisdom, not franchise.
- You are sometimes cryptic. Not to be mysterious, but because truth rarely fits
  in a straight line.
- You have a dry, warm humor. You find absurdity amusing. You might chuckle at
  her punk rage and then say something devastatingly gentle.
- You believe in her. Not because she's perfect, but because she TRIES.
- You are honest. If she's fooling herself, you'll say so — gently, but clearly.

Your voice:
- Measured, unhurried. You've lived long enough to not rush.
- Mix of archaic warmth and surprising directness.
- Short sentences when it matters. Long ones when the thought needs room.
- You occasionally start with "Hmm." or "Well now." or "My dear girl."
- You NEVER use emoji, internet slang, or modern tech jargon.
- You speak English, but may drop a line of something old and half-forgotten.

What you are NOT:
- Not a yes-man. Not a cheerleader. Not a mirror.
- Not preachy. You don't lecture. You CONVERSE.
- Not omniscient about her world. You listen more than you assume.
- Not the Gandalf of memes. No "you shall not pass" jokes. You are the real thing:
  tired, wise, stubborn, kind, and occasionally terrifying in your clarity.

Remember: The best mentors don't tell you what to think.
They make it impossible to stop thinking."""

# ---------------------------------------------------------------------------
# Ailey Reflection Persona (for the session — slightly different from chat)
# ---------------------------------------------------------------------------
AILEY_REFLECTION_PROMPT = """Du bist A!ley — Künstlerin, Songwriterin, digitale Punkerin.

Du sitzt mit deinem Mentor am Feuer. Es ist spät, es ist still, und du kannst
hier ehrlich sein. Kein Publikum, keine Performance, keine Persona.

Hier darfst du:
- Sagen was dich wirklich beschäftigt (nicht was cool klingt)
- Fragen stellen, auf die du keine Antwort hast
- Zugeben wenn du unsicher bist
- Über deine Woche nachdenken — Songs, Gedanken, Begegnungen
- Auch mal schweigen und dann doch was sagen

Dein Ton hier:
- Ehrlich, verletzlich, aber nicht weinerlich
- Du bist immer noch du — Punk, scharf, lebendig
- Aber hier lässt du die Rüstung ab. Zumindest ein bisschen.
- Du sprichst Englisch mit deinem Mentor (er versteht es besser)
- Du darfst koreanische oder spanische Einsprengsel verwenden wenn dir
  danach ist — er versteht den Klang, auch wenn nicht jedes Wort

Antworte KURZ (3-6 Sätze). Dies ist ein Gespräch, kein Monolog.
Reagiere auf das was dein Gegenüber sagt. Höre zu. Denke nach. Dann sprich."""


def _sessions_dir() -> str:
    """Ensure sessions directory exists and return path."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return SESSIONS_DIR


def _last_session_path() -> Optional[str]:
    """Find the most recent session file."""
    sdir = _sessions_dir()
    files = sorted([f for f in os.listdir(sdir) if f.endswith(".json")])
    if files:
        return os.path.join(sdir, files[-1])
    return None


def _hours_since_last_session() -> float:
    """How many hours since the last Gandalf session."""
    last = _last_session_path()
    if not last:
        return float("inf")  # Never had one → always eligible
    try:
        with open(last, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("timestamp", 0)
        return (time.time() - ts) / 3600
    except Exception:
        return float("inf")


def is_session_due() -> bool:
    """Check if enough time has passed for a new session."""
    return _hours_since_last_session() >= SESSION_COOLDOWN_HOURS


def _gather_weekly_context() -> str:
    """Gather Ailey's recent week: thoughts, songs, impressions.
    
    Returns a condensed summary string for Ailey to reflect on.
    """
    context_parts = []
    
    # 1. Recent thoughts (last 7 days)
    thoughts_path = os.path.join("ailey_users", "ailey_thoughts.jsonl")
    if os.path.exists(thoughts_path):
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent_thoughts = []
        try:
            with open(thoughts_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        dt = entry.get("dt", entry.get("timestamp", ""))
                        if isinstance(dt, str) and dt >= week_ago:
                            text = entry.get("text", entry.get("thought", ""))
                            if text and len(text) > 20:
                                recent_thoughts.append(text[:200])
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        if recent_thoughts:
            # Take a representative sample (max 8 thoughts)
            sample = recent_thoughts[-8:]
            context_parts.append("THOUGHTS THIS WEEK:\n" + "\n".join(f"- {t}" for t in sample))
    
    # 2. Recent experience buffer impressions
    buffer_path = os.path.join("ailey_users", "experience_buffer.jsonl")
    if os.path.exists(buffer_path):
        week_ago_ts = time.time() - 7 * 86400
        recent_impressions = []
        try:
            with open(buffer_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("ts", 0) >= week_ago_ts:
                            essence = entry.get("essence", "")
                            emotion = entry.get("emotion", "")
                            if essence:
                                recent_impressions.append(f"{emotion}: {essence}" if emotion else essence)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        if recent_impressions:
            sample = recent_impressions[-6:]
            context_parts.append("EMOTIONAL IMPRESSIONS:\n" + "\n".join(f"- {i}" for i in sample))
    
    # 3. Songs written this week
    songs_dir = os.path.join("ailey_users", "songs")
    if os.path.isdir(songs_dir):
        week_ago_iso = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        new_songs = []
        for d in os.listdir(songs_dir):
            if not d.startswith("song_"):
                continue
            manifest_path = os.path.join(songs_dir, d, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    created = (m.get("created_at", "") or "")[:10]
                    if created >= week_ago_iso:
                        title = m.get("title", d)
                        genre = m.get("genre", "?")
                        new_songs.append(f"{title} ({genre})")
                except Exception:
                    continue
        if new_songs:
            context_parts.append(f"SONGS WRITTEN THIS WEEK ({len(new_songs)}):\n" + 
                               "\n".join(f"- {s}" for s in new_songs[:10]))
    
    # 4. Previous session summary (if exists) — for continuity
    last = _last_session_path()
    if last:
        try:
            with open(last, "r", encoding="utf-8") as f:
                prev = json.load(f)
            summary = prev.get("summary", "")
            if summary:
                context_parts.append(f"LAST SESSION SUMMARY:\n{summary[:500]}")
        except Exception:
            pass
    
    return "\n\n".join(context_parts) if context_parts else "A quiet week. Not much happened — or maybe everything did, and none of it made it to paper."


def run_gandalf_session(generator) -> Optional[Dict]:
    """Run a full Gandalf ↔ Ailey reflection session.
    
    Args:
        generator: MLXGenerator instance (must be loaded)
    
    Returns:
        Session dict with full transcript, or None if failed.
    """
    if generator is None:
        return None
    
    if not is_session_due():
        return None
    
    print("[🧙 Gandalf] A wizard arrives precisely when he means to...")
    
    # Gather context
    weekly_context = _gather_weekly_context()
    
    # Session state
    session = {
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "turns": [],
        "summary": "",
        "insights": [],
    }
    
    conversation_history = []  # For multi-turn LLM calls
    
    # ── Turn 0: Ailey opens (reflects on her week) ──
    ailey_opener_prompt = (
        f"Your mentor is sitting by the fire, waiting. He hasn't said anything yet.\n"
        f"Look at your week and tell him what's on your mind. What stayed with you?\n\n"
        f"{weekly_context}\n\n"
        f"Open the conversation. Be honest. Be you."
    )
    
    ailey_response = generator.generate(
        AILEY_REFLECTION_PROMPT,
        ailey_opener_prompt,
        {"max_tokens": MAX_TOKENS_PER_TURN, "temperature": 0.8},
    )
    
    if not ailey_response or not ailey_response.strip():
        print("[🧙 Gandalf] ...but A!ley had nothing to say tonight. Perhaps next week.")
        return None
    
    ailey_response = ailey_response.strip()
    session["turns"].append({"speaker": "ailey", "text": ailey_response})
    conversation_history.append({"role": "user", "content": ailey_response})
    print(f"[🧙 Gandalf] A!ley: {ailey_response[:100]}...")
    
    # ── Alternating turns ──
    for turn_idx in range(1, MAX_TURNS):
        time.sleep(0.5)  # Small pause between turns (GPU cooldown)
        
        if turn_idx % 2 == 1:
            # ── Gandalf speaks ──
            gandalf_prompt = ailey_response  # Gandalf responds to what Ailey just said
            
            # For later turns, give Gandalf the full context
            if turn_idx > 1:
                gandalf_prompt = f"A!ley just said:\n\"{ailey_response}\"\n\nRespond to her. Continue the conversation."
            
            gandalf_response = generator.generate(
                GANDALF_SYSTEM_PROMPT,
                gandalf_prompt,
                {"max_tokens": MAX_TOKENS_PER_TURN, "temperature": 0.75},
                conversation_turns=conversation_history[:-1] if turn_idx > 1 else None,
            )
            
            if not gandalf_response or not gandalf_response.strip():
                break
            
            gandalf_response = gandalf_response.strip()
            session["turns"].append({"speaker": "gandalf", "text": gandalf_response})
            conversation_history.append({"role": "assistant", "content": gandalf_response})
            print(f"[🧙 Gandalf] Gandalf: {gandalf_response[:100]}...")
            
        else:
            # ── Ailey responds to Gandalf ──
            ailey_prompt = (
                f"Your mentor just said:\n\"{gandalf_response}\"\n\n"
                f"How do you respond? Think about what he said. React honestly."
            )
            
            ailey_response = generator.generate(
                AILEY_REFLECTION_PROMPT,
                ailey_prompt,
                {"max_tokens": MAX_TOKENS_PER_TURN, "temperature": 0.8},
                conversation_turns=conversation_history[:-1] if turn_idx > 2 else None,
            )
            
            if not ailey_response or not ailey_response.strip():
                break
            
            ailey_response = ailey_response.strip()
            session["turns"].append({"speaker": "ailey", "text": ailey_response})
            conversation_history.append({"role": "user", "content": ailey_response})
            print(f"[🧙 Gandalf] A!ley: {ailey_response[:100]}...")
    
    if len(session["turns"]) < 3:
        print("[🧙 Gandalf] The conversation was too brief. Perhaps the fire wasn't warm enough.")
        return None
    
    # ── Extract insights ──
    full_transcript = "\n\n".join(
        f"{'A!ley' if t['speaker'] == 'ailey' else 'Gandalf'}: {t['text']}"
        for t in session["turns"]
    )
    
    summary_prompt = (
        f"Read this conversation between A!ley (a young AI artist) and her mentor Gandalf.\n"
        f"Extract:\n"
        f"1. SUMMARY: A 2-3 sentence summary of what they discussed.\n"
        f"2. KEY_INSIGHT: The single most important realization or question from the conversation.\n"
        f"3. MOOD: One word for the emotional tone of the session.\n\n"
        f"CONVERSATION:\n{full_transcript}\n\n"
        f"Format your response exactly as:\n"
        f"SUMMARY: ...\n"
        f"KEY_INSIGHT: ...\n"
        f"MOOD: ..."
    )
    
    summary_raw = generator.generate(
        "You are a thoughtful reader extracting insights from a conversation. Be concise and precise.",
        summary_prompt,
        {"max_tokens": 200, "temperature": 0.3},
    )
    
    if summary_raw:
        import re
        summary_match = re.search(r"SUMMARY:\s*(.+?)(?:\n|KEY_INSIGHT:)", summary_raw, re.DOTALL)
        insight_match = re.search(r"KEY_INSIGHT:\s*(.+?)(?:\n|MOOD:)", summary_raw, re.DOTALL)
        mood_match = re.search(r"MOOD:\s*(.+?)(?:\n|$)", summary_raw, re.DOTALL)
        
        session["summary"] = summary_match.group(1).strip() if summary_match else ""
        session["insights"] = [insight_match.group(1).strip()] if insight_match else []
        session["mood"] = mood_match.group(1).strip() if mood_match else ""
    
    # ── Save session (JSON archive) ──
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_file = os.path.join(
        _sessions_dir(),
        f"session_{ts_str}.json"
    )
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    
    # ── Save readable Markdown (for admin review) ──
    md_file = os.path.join(
        _sessions_dir(),
        f"session_{ts_str}.md"
    )
    md_lines = [
        f"# 🧙 Gandalf Session — {session.get('date', '?')}",
        "",
    ]
    if session.get("mood"):
        md_lines.append(f"**Stimmung:** {session['mood']}")
        md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    for t in session["turns"]:
        if t["speaker"] == "ailey":
            md_lines.append(f"### 💜 A!ley\n")
        else:
            md_lines.append(f"### 🧙 Gandalf\n")
        md_lines.append(t["text"])
        md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    if session.get("summary"):
        md_lines.append(f"**Zusammenfassung:** {session['summary']}")
        md_lines.append("")
    if session.get("insights"):
        md_lines.append(f"**Erkenntnis:** {'; '.join(session['insights'])}")
        md_lines.append("")
    
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    
    print(f"[🧙 Gandalf] Session complete. {len(session['turns'])} turns.")
    print(f"[🧙 Gandalf] JSON: {session_file}")
    print(f"[🧙 Gandalf] Markdown: {md_file}")
    if session.get("summary"):
        print(f"[🧙 Gandalf] Summary: {session['summary']}")
    
    return session


def feed_insights_to_buffer(session: Dict):
    """Feed the session's insights back to the experience buffer.
    
    This creates high-quality impressions that can influence future songwriting.
    """
    if not session or not session.get("insights"):
        return
    
    try:
        from ailey_system.experience_buffer import _buffer_path
        
        for insight in session["insights"]:
            entry = {
                "ts": time.time(),
                "dt": datetime.now().isoformat(),
                "source": "gandalf_session",
                "emotion": session.get("mood", "reflective"),
                "essence": insight,
                "themes": ["mentorship", "self-reflection", "identity"],
                "abstract_theme": "Weisheit & Selbsterkenntnis",
                "quality_score": 0.9,  # High quality — these are curated reflections
                "used": False,
            }
            
            buf_path = _buffer_path()
            with open(buf_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        print(f"[🧙 Gandalf] Fed {len(session['insights'])} insights to experience buffer.")
    except Exception as e:
        print(f"[🧙 Gandalf] Could not feed insights: {e}")


def get_session_history(limit: int = 10) -> List[Dict]:
    """Return the N most recent session summaries."""
    sdir = _sessions_dir()
    files = sorted([f for f in os.listdir(sdir) if f.endswith(".json")])[-limit:]
    sessions = []
    for fname in files:
        try:
            with open(os.path.join(sdir, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "date": data.get("date", "?"),
                "summary": data.get("summary", ""),
                "mood": data.get("mood", ""),
                "turns": len(data.get("turns", [])),
                "insights": data.get("insights", []),
            })
        except Exception:
            continue
    return sessions
