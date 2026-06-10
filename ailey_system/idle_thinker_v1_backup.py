# -*- coding: utf-8 -*-
"""
Ailey Idle Thinker — Autonomous Background Reflection

When no user prompt has arrived for a configurable idle period, Ailey reviews
the recent conversation history and *decides for herself* whether anything is
worth researching.  She may also choose to say "Nein, nichts Relevantes" — that
decision itself gets logged.

All thought chains are persisted to a JSON-Lines file so the developer can
inspect them later via the "A!leys Gedanken" tab.

The thinker is lower priority than user prompts:
- It acquires the MLX lock only if nobody else is generating.
- If a user prompt arrives mid-thought, the thinker yields gracefully.
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IDLE_SECONDS = 120          # seconds of no user activity before thinking
THINK_INTERVAL_MIN = 300    # minimum seconds between two idle-think cycles
MAX_THOUGHT_LOG = 500       # max entries kept in the JSON-Lines log
THOUGHTS_DIR = "ailey_users"
THOUGHTS_FILE = "ailey_thoughts.jsonl"

# ---------------------------------------------------------------------------
# Thought log helpers
# ---------------------------------------------------------------------------

def _thoughts_path() -> str:
    os.makedirs(THOUGHTS_DIR, exist_ok=True)
    return os.path.join(THOUGHTS_DIR, THOUGHTS_FILE)


def append_thought(entry: dict):
    """Append a single thought entry to the JSONL log."""
    entry.setdefault("ts", time.time())
    entry.setdefault("dt", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    path = _thoughts_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Trim if too long
        _trim_log(path)
    except Exception as e:
        print(f"[IdleThinker] append_thought error: {e}")


def read_thoughts(limit: int = 50, offset: int = 0) -> List[dict]:
    """Read the most recent thoughts (newest first)."""
    path = _thoughts_path()
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
        return entries[offset:offset + limit]
    except Exception:
        return []


def _trim_log(path: str):
    """Keep only the last MAX_THOUGHT_LOG entries."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_THOUGHT_LOG:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_THOUGHT_LOG:])
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The Idle Thinker Thread
# ---------------------------------------------------------------------------

class IdleThinker:
    """Background daemon thread that monitors idle time and triggers reflection."""

    def __init__(self, core, get_generator):
        """
        Args:
            core: AileyCore instance (for conversation logs, RAG, etc.)
            get_generator: callable that returns the MLXGenerator singleton (or None)
        """
        self.core = core
        self.get_generator = get_generator
        self._last_user_activity = time.time()
        self._last_think_ts = 0.0
        self._stop_event = threading.Event()
        self._busy = False  # True while a thought cycle is in progress
        self._thread: Optional[threading.Thread] = None

    def record_user_activity(self):
        """Call this whenever a user sends a message."""
        self._last_user_activity = time.time()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AileyIdleThinker")
        self._thread.start()
        append_thought({"type": "system", "text": "IdleThinker gestartet."})

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        """Main loop: sleep, check idle, maybe think."""
        while not self._stop_event.is_set():
            # Sleep in small increments so we can stop quickly
            for _ in range(30):  # 30 × 1s = 30s check interval
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            now = time.time()
            idle_secs = now - self._last_user_activity
            since_last_think = now - self._last_think_ts

            # Not idle enough yet
            if idle_secs < IDLE_SECONDS:
                continue
            # Too soon since last think cycle
            if since_last_think < THINK_INTERVAL_MIN:
                continue

            # OK, let's think
            try:
                self._think_cycle()
            except Exception as e:
                append_thought({"type": "error", "text": f"Think-cycle error: {e}"})

    def _think_cycle(self):
        """One idle reflection cycle."""
        self._busy = True
        self._last_think_ts = time.time()
        try:
            self._do_reflect()
        finally:
            self._busy = False

    def _do_reflect(self):
        """The actual reflection: review conversation, decide, maybe research."""
        generator = self.get_generator()
        if generator is None:
            append_thought({"type": "skip", "text": "Kein LLM verfügbar — übersprungen."})
            return

        # Gather recent conversation context (last ~10 exchanges)
        context_lines = self._get_recent_context(user="Simon", max_exchanges=10)
        if not context_lines:
            append_thought({"type": "skip", "text": "Kein Gesprächsverlauf vorhanden — übersprungen."})
            return

        conversation_summary = "\n".join(context_lines[-20:])  # last 20 lines max

        # Phase 1: Ask Ailey whether she finds anything research-worthy
        from .prompt_builder import build_qwen3_prompt, get_ailey_generation_params

        decision_prompt = build_qwen3_prompt(
            user_message=(
                "Du bist gerade allein und es ist ruhig. Simon hat dir seit einer Weile nicht geschrieben. "
                "Schau dir den letzten Gesprächsverlauf an und entscheide:\n"
                "1) Gibt es ein KONKRETES Sachthema, über das du gern mehr wissen würdest? Etwas worüber du "
                "recherchieren könntest um beim nächsten Gespräch besser informiert zu sein?\n"
                "2) Oder ist alles gut abgedeckt und du brauchst gerade nichts nachzuschauen?\n\n"
                "WICHTIG:\n"
                "- Recherchiere NUR nach echten Sachthemen (z.B. Events, Technologie, Orte, Fakten)\n"
                "- Ignoriere Testdaten, Platzhalter oder offensichtliche Scherze/Tests von Simon\n"
                "- Wenn du ein Thema schon mehrfach recherchiert hast und nichts gefunden wurde, lass es\n"
                "- Schreibe KEINE Roleplay-Aktionen (*grinst*, *zwinkert* etc.) in die RECHERCHE-Zeilen\n"
                "- Halte den GEDANKE sachlich und kurz (1-3 Sätze)\n\n"
                "LETZTER VERLAUF:\n" + conversation_summary + "\n\n"
                "Antworte in diesem Format:\n"
                "ENTSCHEIDUNG: JA oder NEIN\n"
                "GEDANKE: (deine Überlegung in 1-3 Sätzen, sachlich)\n"
                "RECHERCHE: (falls JA: 1-3 konkrete Suchbegriffe, einer pro Zeile, NUR Sachbegriffe)"
            ),
            system_persona=(
                "Du bist Ailey und reflektierst still für dich selbst. "
                "Das ist dein innerer Monolog — sachlich, fokussiert, nicht performativ. "
                "KEIN Roleplay, KEINE Emotes, KEINE Fragen an Simon. "
                "Antworte knapp und auf Deutsch."
            ),
            context=None,
            style="kurz",
            reasoning=False,
        )

        params = get_ailey_generation_params()
        params["max_tokens"] = 250
        params["temperature"] = 0.6  # slightly more focused for decisions

        # Try to generate — but yield if user activity happens
        try:
            raw = generator.generate(decision_prompt["system"], decision_prompt["user"], params)
        except Exception as e:
            append_thought({"type": "error", "text": f"LLM generate fehlgeschlagen: {e}"})
            return

        if not raw or not raw.strip():
            append_thought({"type": "skip", "text": "LLM gab leere Antwort."})
            return

        # Parse decision
        raw_clean = raw.strip()
        decision_yes = "ENTSCHEIDUNG: JA" in raw_clean.upper() or "ENTSCHEIDUNG:JA" in raw_clean.upper()

        # Extract thought
        thought_text = raw_clean
        import re
        thought_match = re.search(r"GEDANKE:\s*(.+?)(?:\nRECHERCHE:|\Z)", raw_clean, re.DOTALL)
        if thought_match:
            thought_text = thought_match.group(1).strip()

        # Log the thought
        thought_entry = {
            "type": "reflection",
            "decision": "research" if decision_yes else "pass",
            "thought": thought_text,
            "raw": raw_clean,
            "conversation_context_lines": len(context_lines),
            "idle_seconds": int(time.time() - self._last_user_activity),
        }

        if not decision_yes:
            thought_entry["text"] = f"Entscheidung: Nichts zu recherchieren. Gedanke: {thought_text}"
            append_thought(thought_entry)
            return

        # Phase 2: Extract search queries
        queries = []
        research_match = re.search(r"RECHERCHE:\s*(.+)", raw_clean, re.DOTALL)
        if research_match:
            for line in research_match.group(1).splitlines():
                q = line.strip().strip("-•1234567890.").strip()
                if 3 <= len(q) <= 120:
                    # Skip RP/emote lines (start with * or contain emoji descriptions)
                    if q.startswith("*") or q.startswith("...") or q.startswith("("):
                        continue
                    # Skip lines that are clearly not search queries
                    if re.match(r"^[\*\.\!\?\…]+$", q):
                        continue
                    # Skip conversational filler directed at user
                    if any(w in q.lower() for w in ["schatz", "zwinkert", "grinst", "soll ich", "oder ich", "sag mir", "sag mal"]):
                        continue
                    queries.append(q)

        if not queries:
            thought_entry["text"] = f"Wollte recherchieren, aber keine konkreten Queries. Gedanke: {thought_text}"
            thought_entry["decision"] = "pass_no_queries"
            append_thought(thought_entry)
            return

        thought_entry["queries"] = queries
        thought_entry["text"] = f"Recherche gestartet: {', '.join(queries)}. Gedanke: {thought_text}"

        # Phase 3: Execute research (reuse core's method)
        try:
            stored = self.core.execute_research_queries("Simon", queries)
            thought_entry["research_results"] = stored
            thought_entry["stored_count"] = len(stored)
        except Exception as e:
            thought_entry["research_error"] = str(e)

        append_thought(thought_entry)

    def _get_recent_context(self, user: str = "Simon", max_exchanges: int = 10) -> List[str]:
        """Load recent conversation log entries."""
        try:
            base = os.path.join("ailey_users", f"{user.lower()}_profile", "conversation_logs")
            if not os.path.isdir(base):
                return []
            files = sorted([f for f in os.listdir(base) if f.endswith(".json")])
            recent_files = files[-(max_exchanges):]
            lines = []
            for fname in recent_files:
                try:
                    with open(os.path.join(base, fname), "r", encoding="utf-8") as fh:
                        entry = json.load(fh)
                    user_msg = entry.get("message", "")
                    ai_reply = entry.get("ailey_reply_visible", entry.get("ailey_reply", ""))
                    if user_msg:
                        lines.append(f"Simon: {user_msg[:300]}")
                    if ai_reply:
                        lines.append(f"Ailey: {ai_reply[:300]}")
                except Exception:
                    continue
            return lines
        except Exception:
            return []
