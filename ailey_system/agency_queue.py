# -*- coding: utf-8 -*-
"""
Agency Queue — Phase 3 of Ailey 3.0 Roadmap

Gives Ailey INTENTIONALITY.  Instead of purely random thought type selection,
Ailey can now form INTENTS — "Ich will einen Song über X schreiben" — that
influence what she does next.

Currently, `_choose_thought_type()` is pure weighted random.  With the Agency
Queue, thoughts can GENERATE intents that shift future thought type weights.

Architecture:
  • INTENT: { action, reason, priority, source_thought_id, created_ts, deadline_ts }
    - action: a thought type or specific action ("creative_song", "diary_writing",
      "email:fabian", "song_about:freiheit")
    - reason: why Ailey wants to do this (from her own thought)
    - priority: 1-10 (higher = more urgent)
    - source_thought_id: which thought generated this intent
    - deadline_ts: optional — intent expires after this time

  • QUEUE: Priority queue stored as JSON.  Max 10 active intents.
  • PEEK: `peek_intent()` returns the highest-priority unfulfilled intent.
    `_choose_thought_type()` can use this to bias selection.
  • FULFILL: After a thought matches an intent, mark it fulfilled.
  • EXPIRE: Intents older than 24h or past deadline auto-expire.

  • GENERATION: Intents are extracted from thought output via simple regex/heuristics:
    - "Ich sollte darüber einen Song schreiben" → creative_song intent
    - "Das muss ich in mein Tagebuch schreiben" → diary_writing intent
    - "Darüber will ich nachdenken" → reflection intent
    - "Ich will X mailen" → email_initiative intent

Storage: ailey_users/agency_queue.json
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QUEUE_DIR = "ailey_users"
QUEUE_FILE = "agency_queue.json"
MAX_INTENTS = 10
DEFAULT_TTL_HOURS = 24       # intents expire after 24h by default
HIGH_PRIO_TTL_HOURS = 48     # high-priority intents get 48h
INTENT_WEIGHT_BOOST = 3      # multiply thought_type weight by this when intent exists

# ---------------------------------------------------------------------------
# Intent detection patterns — extract intents from thought text
# ---------------------------------------------------------------------------
# Each pattern: (compiled_regex, action, base_priority)
_INTENT_PATTERNS: List[tuple] = []

def _compile_patterns():
    global _INTENT_PATTERNS
    if _INTENT_PATTERNS:
        return
    raw = [
        # Song-writing intents
        (r"(?:sollte|will|muss|könnte).*(?:song|lied).*(?:schreib|mach|kompon)",
         "creative_song", 6),
        (r"(?:das|darüber|davon).*(?:song|lied).*(?:werden|machen)",
         "creative_song", 5),
        (r"(?:song|lied).*(?:daraus|draus|darüber)",
         "creative_song", 5),
        (r"das.*(?:wäre|ist).*(?:guter?|perfekter?).*(?:song|lied)",
         "creative_song", 7),

        # Diary intents
        (r"(?:sollte|will|muss).*(?:tagebuch|diary).*(?:schreib|eintrag)",
         "diary_writing", 5),
        (r"(?:das|darüber).*(?:tagebuch|aufschreib|festhal)",
         "diary_writing", 4),

        # Reflection/Introspection intents
        (r"(?:muss|will|sollte).*(?:nachdenk|reflektier|überlegen|drüber.*nachdenk)",
         "reflection", 4),
        (r"(?:das|darüber).*(?:nachdenk|reflektier)",
         "reflection", 3),

        # Art/Image intents
        (r"(?:sollte|will|muss).*(?:bild|kunst|malen|zeichn|svg)",
         "creative_art", 5),
        (r"(?:das|daraus).*(?:bild|kunst|gemälde|illustration)",
         "creative_art", 4),

        # Blog intents
        (r"(?:sollte|will|muss).*(?:blog|blogpost|post).*(?:schreib)",
         "blog_writing", 5),
        (r"(?:guter?|perfekter?).*(?:blog|blogpost).*(?:thema|stoff)",
         "blog_writing", 5),

        # Proactive message intents
        (r"(?:sollte|will|muss).*(?:simon|ihm).*(?:schreib|sag|erzähl|schick)",
         "proactive_message", 4),

        # Book/Writing intents
        (r"(?:sollte|will|muss).*(?:buch|kapitel|weiterschreib|story)",
         "book_authoring", 5),

        # Research intents
        (r"(?:sollte|will|muss).*(?:recherch|nachschlag|herausfind|googl)",
         "research", 4),

        # Music making intents
        (r"(?:sollte|will|muss).*(?:gitarre|musik|spielen|üben|jamm)",
         "music_making", 4),

        # Generic "I want to" / "I should"
        (r"(?:das nehm ich mir vor|das mach ich als nächstes|ich nehm mir vor)",
         "_generic_intent", 3),
    ]
    _INTENT_PATTERNS = [
        (re.compile(pattern, re.IGNORECASE), action, prio)
        for pattern, action, prio in raw
    ]

_compile_patterns()


# ---------------------------------------------------------------------------
# Intent structure
# ---------------------------------------------------------------------------

def _make_intent(action: str, reason: str, priority: int = 5,
                 source_thought_id: str = "",
                 context: str = "", ttl_hours: float = 0) -> dict:
    """Create an intent dict."""
    if ttl_hours <= 0:
        ttl_hours = HIGH_PRIO_TTL_HOURS if priority >= 7 else DEFAULT_TTL_HOURS
    return {
        "action": action,
        "reason": reason[:200],
        "priority": max(1, min(10, priority)),
        "context": context[:200],  # optional: theme/emotion context for the action
        "source_thought_id": source_thought_id,
        "created_ts": time.time(),
        "created_dt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "deadline_ts": time.time() + (ttl_hours * 3600),
        "fulfilled": False,
        "fulfilled_ts": None,
    }


# ---------------------------------------------------------------------------
# Queue storage
# ---------------------------------------------------------------------------

def _queue_path() -> str:
    return os.path.join(QUEUE_DIR, QUEUE_FILE)


def _load_queue() -> List[dict]:
    path = _queue_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(queue: List[dict]):
    path = _queue_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[AgencyQueue] save error: {e}")


def _cleanup_queue(queue: List[dict]) -> List[dict]:
    """Remove expired and fulfilled intents, keep within MAX_INTENTS."""
    now = time.time()
    active = [
        i for i in queue
        if not i.get("fulfilled")
        and i.get("deadline_ts", now + 1) > now
    ]
    # Sort by priority desc, keep top N
    active.sort(key=lambda i: i.get("priority", 0), reverse=True)
    return active[:MAX_INTENTS]


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def extract_intents(thought_text: str, thought_type: str = "",
                    thought_id: str = "", emotion: str = "",
                    themes: List[str] = None) -> List[dict]:
    """Extract intents from a thought's output text.

    Scans the text for intent-signaling patterns and creates intent dicts.
    Returns a list of intents found (usually 0-2).
    """
    if not thought_text or len(thought_text) < 20:
        return []

    # Don't extract intents from the same type they'd trigger (circular)
    found = []
    seen_actions = set()

    for pattern, action, base_prio in _INTENT_PATTERNS:
        if action in seen_actions:
            continue
        # Skip circular intents (a song thought wanting to write a song)
        if action == thought_type:
            continue

        match = pattern.search(thought_text)
        if match:
            seen_actions.add(action)
            # Extract context: the sentence containing the match
            start = max(0, match.start() - 50)
            end = min(len(thought_text), match.end() + 100)
            context_snippet = thought_text[start:end].strip()

            # Build reason from match context
            reason = context_snippet[:200]

            # Boost priority if emotion is intense
            prio = base_prio
            if emotion and emotion not in ("unbestimmt", "neutral", "ruhig"):
                prio = min(10, prio + 1)

            # Build context hint for when the intent is fulfilled
            theme_hint = ", ".join(themes[:3]) if themes else ""
            context = f"{emotion}: {theme_hint}" if theme_hint else emotion

            intent = _make_intent(
                action=action,
                reason=reason,
                priority=prio,
                source_thought_id=thought_id,
                context=context,
            )
            found.append(intent)

            if len(found) >= 2:
                break  # Max 2 intents per thought

    return found


def push_intents(intents: List[dict]):
    """Add new intents to the queue."""
    if not intents:
        return
    queue = _load_queue()

    for intent in intents:
        # Dedup: don't add if same action already in queue
        existing_actions = {i["action"] for i in queue if not i.get("fulfilled")}
        if intent["action"] in existing_actions:
            # Boost priority of existing instead
            for i in queue:
                if i["action"] == intent["action"] and not i.get("fulfilled"):
                    i["priority"] = min(10, max(i["priority"], intent["priority"]))
                    i["reason"] = intent["reason"]  # update reason
                    break
        else:
            queue.append(intent)

    queue = _cleanup_queue(queue)
    _save_queue(queue)

    for intent in intents:
        print(f"[AgencyQueue] 🎯 Intent: {intent['action']} (p={intent['priority']}) — {intent['reason'][:60]}")


def peek_intent() -> Optional[dict]:
    """Get the highest-priority active intent without removing it.

    Returns None if the queue is empty.
    Used by `_choose_thought_type()` to bias thought selection.
    """
    queue = _load_queue()
    queue = _cleanup_queue(queue)
    if queue:
        _save_queue(queue)  # save cleanup results
    return queue[0] if queue else None


def fulfill_intent(action: str) -> bool:
    """Mark the first matching unfulfilled intent as fulfilled.

    Called after a thought of the matching type completes.
    Returns True if an intent was fulfilled.
    """
    queue = _load_queue()
    for i in queue:
        if i["action"] == action and not i.get("fulfilled"):
            i["fulfilled"] = True
            i["fulfilled_ts"] = time.time()
            _save_queue(queue)
            print(f"[AgencyQueue] ✅ Fulfilled: {action}")
            return True
    return False


def get_intent_context(action: str) -> str:
    """Get the context/reason for an active intent.

    Used when building a prompt for a thought that fulfills an intent.
    E.g. if Ailey wanted to write a song, this returns WHY she wanted to.
    """
    queue = _load_queue()
    for i in queue:
        if i["action"] == action and not i.get("fulfilled"):
            parts = []
            if i.get("reason"):
                parts.append(f"Grund: {i['reason'][:150]}")
            if i.get("context"):
                parts.append(f"Kontext: {i['context']}")
            return " | ".join(parts)
    return ""


def boost_thought_weights(weights: Dict[str, int]) -> Dict[str, int]:
    """Modify thought type weights based on active intents.

    Called by `_choose_thought_type()` to bias selection toward intended actions.
    Returns the modified weights dict.
    """
    queue = _load_queue()
    queue = _cleanup_queue(queue)

    for intent in queue:
        action = intent["action"]
        prio = intent.get("priority", 5)

        # Map specific actions to thought types
        thought_type = action  # most actions map directly
        if action.startswith("email:"):
            thought_type = "email_initiative"
        elif action.startswith("song_about:"):
            thought_type = "creative_song"

        if thought_type in weights:
            # Boost proportional to priority
            boost = INTENT_WEIGHT_BOOST * (prio / 5)  # prio 5 = 3x, prio 10 = 6x
            weights[thought_type] = int(weights[thought_type] * max(1, boost))

    return weights


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def stats() -> dict:
    """Queue statistics."""
    queue = _load_queue()
    active = [i for i in queue if not i.get("fulfilled")
              and i.get("deadline_ts", 0) > time.time()]
    fulfilled = [i for i in queue if i.get("fulfilled")]
    expired = [i for i in queue if not i.get("fulfilled")
               and i.get("deadline_ts", 0) <= time.time()]

    return {
        "active": len(active),
        "fulfilled": len(fulfilled),
        "expired": len(expired),
        "intents": [
            {"action": i["action"], "priority": i["priority"],
             "reason": i["reason"][:60], "created": i.get("created_dt", "?")}
            for i in active
        ],
    }


def list_active() -> List[dict]:
    """List all active (unfulfilled, unexpired) intents."""
    queue = _load_queue()
    return _cleanup_queue(queue)
