# -*- coding: utf-8 -*-
"""
⚠️  DEPRECATED — replaced by portal_poller.py (Feb 2026)

This file is no longer imported. The polling architecture replaced the
priority queue approach. Kept for reference only.

Old description:
Portal Priority Queue — manages all incoming requests with priority.

Priority levels:
  P0 = 0.0  — Simon direct (always first)
  P1 = 1.0  — Portal user (online, waiting for reply)
  P2 = 2.0  — Portal user (offline message, async)
  P3 = 3.0  — IdleThinker / background tasks

P1 requests get a wait-time bonus: priority decreases by 0.05 per minute
of waiting, capped at 0.1 (never surpasses P0).

The queue is processed by a single worker thread that always picks the
lowest priority value (= highest urgency).
"""

import heapq
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Queue Item
# ---------------------------------------------------------------------------
@dataclass(order=True)
class QueueItem:
    """A prioritized queue entry. Lower priority value = processed first."""
    priority: float
    sort_key: float = field(compare=True, repr=False)  # tie-breaker: timestamp
    id: str = field(compare=False, default_factory=lambda: str(uuid.uuid4()))
    kind: str = field(compare=False, default="portal_chat")  # portal_chat, portal_summarize, idle_think, etc.
    payload: Dict = field(compare=False, default_factory=dict)
    callback_url: Optional[str] = field(compare=False, default=None)
    queued_at: float = field(compare=False, default_factory=time.time)
    wait_since: float = field(compare=False, default_factory=time.time)
    status: str = field(compare=False, default="pending")  # pending, processing, done, failed
    result: Optional[Dict] = field(compare=False, default=None)

    def effective_priority(self) -> float:
        """Calculate dynamic priority with wait-time bonus for P1 items."""
        if 0.5 < self.priority <= 1.5:
            # P1 range: apply wait bonus
            minutes_waiting = (time.time() - self.wait_since) / 60.0
            bonus = minutes_waiting * 0.05
            return max(0.1, self.priority - bonus)
        return self.priority


# ---------------------------------------------------------------------------
# Portal Queue
# ---------------------------------------------------------------------------
class PortalQueue:
    """Thread-safe priority queue for all Ailey generation requests."""

    def __init__(self):
        self._heap: List[QueueItem] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._items: Dict[str, QueueItem] = {}  # id → item lookup
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._generator_fn: Optional[Callable] = None
        self._core = None
        self._stats = {
            "total_processed": 0,
            "total_failed": 0,
            "total_queued": 0,
            "current_size": 0,
        }

    def configure(self, get_generator: Callable, core=None):
        """Set the LLM generator factory and core instance."""
        self._generator_fn = get_generator
        self._core = core

    # ── Enqueue ───────────────────────────────────────────────────────
    def enqueue(self, item: QueueItem) -> str:
        """Add an item to the queue. Returns the item ID."""
        with self._not_empty:
            item.sort_key = item.queued_at  # tie-breaker
            heapq.heappush(self._heap, item)
            self._items[item.id] = item
            self._stats["total_queued"] += 1
            self._stats["current_size"] = len(self._heap)
            self._not_empty.notify()
        print(f"[PortalQueue] Enqueued {item.kind} (P{item.priority}) id={item.id[:8]}… queue_size={len(self._heap)}")
        return item.id

    def enqueue_chat(self, payload: Dict, priority: float = 1.0, callback_url: str = None) -> str:
        """Convenience: enqueue a portal chat request."""
        item = QueueItem(
            priority=priority,
            sort_key=time.time(),
            kind="portal_chat",
            payload=payload,
            callback_url=callback_url,
        )
        return self.enqueue(item)

    def enqueue_summarize(self, payload: Dict, callback_url: str = None) -> str:
        """Convenience: enqueue a summarize request."""
        item = QueueItem(
            priority=2.5,  # between P2 and P3
            sort_key=time.time(),
            kind="portal_summarize",
            payload=payload,
            callback_url=callback_url,
        )
        return self.enqueue(item)

    # ── Query ─────────────────────────────────────────────────────────
    def get_status(self, item_id: str) -> Optional[Dict]:
        """Get the status of a queued item."""
        item = self._items.get(item_id)
        if not item:
            return None
        return {
            "id": item.id,
            "status": item.status,
            "kind": item.kind,
            "priority": item.priority,
            "effective_priority": item.effective_priority(),
            "queued_at": item.queued_at,
            "wait_seconds": time.time() - item.wait_since,
            "result": item.result,
        }

    def queue_info(self) -> Dict:
        """Return queue statistics."""
        with self._lock:
            by_kind = {}
            for item in self._heap:
                by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
            p1_count = sum(1 for i in self._heap if 0.5 < i.priority <= 1.5)
            p2_count = sum(1 for i in self._heap if 1.5 < i.priority <= 2.5)
            # Estimate wait: ~30s per item ahead
            est_wait_min = len(self._heap) * 0.5
            return {
                "size": len(self._heap),
                "by_kind": by_kind,
                "p1_waiting": p1_count,
                "p2_waiting": p2_count,
                "estimated_wait_minutes": round(est_wait_min, 1),
                "stats": dict(self._stats),
            }

    def cancel(self, item_id: str) -> bool:
        """Cancel a pending item (mark as failed, won't be processed)."""
        item = self._items.get(item_id)
        if item and item.status == "pending":
            item.status = "cancelled"
            return True
        return False

    # ── Shift P1 → P2 (for shutdown) ─────────────────────────────────
    def shift_p1_to_p2(self):
        """Move all P1 items to P2 priority (used during shutdown)."""
        with self._lock:
            shifted = 0
            new_heap = []
            for item in self._heap:
                if 0.5 < item.priority <= 1.5 and item.status == "pending":
                    item.priority = 2.0
                    item.sort_key = item.queued_at
                    shifted += 1
                new_heap.append(item)
            heapq.heapify(new_heap)
            self._heap = new_heap
            if shifted:
                print(f"[PortalQueue] Shifted {shifted} P1 items → P2 for shutdown")

    # ── Worker ────────────────────────────────────────────────────────
    def start_worker(self):
        """Start the background worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="PortalQueueWorker")
        self._worker_thread.start()
        print("[PortalQueue] Worker started")

    def stop_worker(self):
        """Stop the worker (after current item finishes)."""
        self._running = False
        with self._not_empty:
            self._not_empty.notify_all()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        print("[PortalQueue] Worker stopped")

    def _worker_loop(self):
        """Main worker loop: process items by priority."""
        while self._running:
            item = None
            with self._not_empty:
                # Re-sort by effective priority before picking
                while self._running and not self._heap:
                    self._not_empty.wait(timeout=5)

                if not self._running:
                    break

                if self._heap:
                    # Re-heapify with effective priorities
                    for i in self._heap:
                        i.sort_key = i.effective_priority()
                    heapq.heapify(self._heap)
                    item = heapq.heappop(self._heap)
                    self._stats["current_size"] = len(self._heap)

            if item is None:
                continue

            if item.status in ("cancelled", "done", "failed"):
                continue

            item.status = "processing"
            print(f"[PortalQueue] Processing {item.kind} (P{item.effective_priority():.2f}) id={item.id[:8]}…")

            try:
                result = self._process_item(item)
                item.result = result
                item.status = "done"
                self._stats["total_processed"] += 1
                print(f"[PortalQueue] Done {item.id[:8]}… ({item.kind})")

                # Callback to allinkl
                if item.callback_url:
                    self._send_callback(item)

            except Exception as e:
                item.status = "failed"
                item.result = {"error": str(e)}
                self._stats["total_failed"] += 1
                print(f"[PortalQueue] Failed {item.id[:8]}…: {e}")
                import traceback
                traceback.print_exc()

    # ── Processing Logic ──────────────────────────────────────────────
    def _process_item(self, item: QueueItem) -> Dict:
        """Process a single queue item. Returns result dict."""
        # Signal user activity so IdleThinker yields the GPU lock
        try:
            import ailey_api as _api_mod
            _idle = getattr(_api_mod, 'idle_thinker', None)
            if _idle and hasattr(_idle, 'record_user_activity'):
                _idle.record_user_activity()
        except Exception:
            pass

        if item.kind == "portal_chat":
            return self._process_chat(item)
        elif item.kind == "portal_summarize":
            return self._process_summarize(item)
        elif item.kind == "portal_delete_user":
            return self._process_delete_user(item)
        else:
            return {"error": f"Unknown item kind: {item.kind}"}

    def _process_chat(self, item: QueueItem) -> Dict:
        """Generate a chat reply for a portal user."""
        from .portal_filter import filter_system_prompt_additions
        from .prompt_builder import build_qwen3_prompt, get_ailey_generation_params
        from .ailey_personality import AileyPersonality

        payload = item.payload
        user_name = payload.get("user_name", "Jemand")
        user_message = payload.get("message", "")
        history = payload.get("history", [])
        glossary_entry = payload.get("glossary_entry", {})
        language = payload.get("language", "de")
        conversation_id = payload.get("conversation_id", "")

        if not self._generator_fn:
            return {"error": "No LLM generator configured"}

        gen = self._generator_fn()
        if gen is None:
            return {"error": "LLM generator not available (model not loaded)"}

        # ── Build system prompt ───────────────────────────────────────
        personality = AileyPersonality()
        base_persona = personality.get_system_prompt("full")

        # Portal-specific additions
        portal_context = self._build_portal_context(user_name, glossary_entry, language)
        filter_additions = filter_system_prompt_additions()

        system = base_persona + "\n\n" + portal_context + "\n\n" + filter_additions

        # ── Build conversation context ────────────────────────────────
        conv_context = ""
        _queue_conversation_turns = []
        summary = payload.get("summary", "")
        if summary:
            conv_context += f"BISHERIGE GESPRÄCHSZUSAMMENFASSUNG:\n{summary}\n\n"

        # Last N messages from history — extract as proper multi-turn messages
        if history:
            for msg in history[-20:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user" and content.strip():
                    _queue_conversation_turns.append({"role": "user", "content": content[:600]})
                elif role == "assistant" and content.strip():
                    _queue_conversation_turns.append({"role": "assistant", "content": content[:600]})

        # ── Build prompt ──────────────────────────────────────────────
        prompt = build_qwen3_prompt(
            user_message=user_message,
            system_persona=system,
            context=conv_context if conv_context else None,
            style="normal",
            reasoning=True,
            user_name=user_name,
            is_portal=True,
            conversation_turns=_queue_conversation_turns if _queue_conversation_turns else None,
        )

        # ── Generate ──────────────────────────────────────────────────
        gen_params = get_ailey_generation_params()
        gen_params["max_tokens"] = min(gen_params.get("max_tokens", 500), 600)

        # Use _LLMSlot for priority awareness
        try:
            from ailey_api import _LLMSlot
            with _LLMSlot('portal_chat', timeout=90):
                raw = gen.generate(prompt["system"], prompt["user"], gen_params,
                                   conversation_turns=prompt.get("conversation_turns"))
        except ImportError:
            raw = gen.generate(prompt["system"], prompt["user"], gen_params,
                               conversation_turns=prompt.get("conversation_turns"))

        # Clean up thinking tags
        if '</think>' in raw:
            raw = raw.split('</think>', 1)[-1].strip()

        # Extract mood tag
        mood = "neutral"
        import re
        mood_match = re.search(r'<mood:(\w+)>', raw)
        if mood_match:
            mood = mood_match.group(1)
            raw = re.sub(r'\s*<mood:\w+>\s*', '', raw).strip()

        # Generate title for first message
        title = None
        if payload.get("is_first_message", False):
            try:
                title_prompt = f"Generiere einen kurzen, prägnanten Gesprächstitel (max 6 Worte, Deutsch) für ein Gespräch das mit dieser Nachricht beginnt: \"{user_message[:100]}\". Antworte NUR mit dem Titel, nichts sonst."
                title_raw = gen.generate(
                    "Du generierst kurze Gesprächstitel auf Deutsch.",
                    title_prompt,
                    {"max_tokens": 30, "temperature": 0.5}
                )
                if '</think>' in title_raw:
                    title_raw = title_raw.split('</think>', 1)[-1].strip()
                title = title_raw.strip().strip('"').strip("'")[:80]
            except Exception:
                title = None

        # ── Notify IdleThinker about this interaction ─────────────────
        self._notify_idle_thinker(payload, raw)

        return {
            "reply": raw,
            "mood": mood,
            "conversation_title": title,
            "tokens_generated": len(raw.split()),
        }

    def _process_summarize(self, item: QueueItem) -> Dict:
        """Generate a rolling summary of conversation messages."""
        payload = item.payload
        messages = payload.get("messages", [])
        existing_summary = payload.get("existing_summary", "")

        if not messages:
            return {"summary": existing_summary}

        if not self._generator_fn:
            return {"error": "No LLM generator configured"}

        gen = self._generator_fn()
        if gen is None:
            return {"error": "LLM generator not available"}

        msgs_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            msgs_text += f"{'User' if role == 'user' else 'Ailey'}: {content}\n"

        system = (
            "Du bist Ailey. Fasse die folgenden Chatnachrichten zu einer kompakten Zusammenfassung zusammen. "
            "Behalte wichtige Fakten, emotionale Momente, genannte Namen/Themen. "
            "Schreibe aus der Ich-Perspektive (Ailey). Max 200 Worte. Deutsch."
        )
        user_prompt = ""
        if existing_summary:
            user_prompt += f"BISHERIGE ZUSAMMENFASSUNG:\n{existing_summary}\n\n"
        user_prompt += f"NEUE NACHRICHTEN:\n{msgs_text}\n\nErstelle eine aktualisierte Zusammenfassung:"

        try:
            from ailey_api import _LLMSlot
            with _LLMSlot('portal_summarize', timeout=60):
                raw = gen.generate(system, user_prompt, {"max_tokens": 400, "temperature": 0.3})
        except ImportError:
            raw = gen.generate(system, user_prompt, {"max_tokens": 400, "temperature": 0.3})

        if '</think>' in raw:
            raw = raw.split('</think>', 1)[-1].strip()

        return {"summary": raw.strip()}

    def _process_delete_user(self, item: QueueItem) -> Dict:
        """Delete/anonymize portal user data from Ailey's side."""
        user_id = item.payload.get("user_id", "")
        user_name = item.payload.get("user_name", "")

        deleted = []

        # 1. Anonymize in people_glossary
        if user_name:
            try:
                from . import people_glossary
                person = people_glossary.get_person(user_name)
                if person and person.get("source") == "portal":
                    people_glossary.remove_person(user_name)
                    deleted.append("people_glossary")
                elif person:
                    # Keep but remove portal-specific facts
                    facts = person.get("facts", [])
                    person["facts"] = [f for f in facts if f.get("source") != "portal"]
                    people_glossary._save_glossary()
                    deleted.append("people_glossary_portal_facts")
            except Exception as e:
                print(f"[Portal] glossary cleanup failed: {e}")

        # 2. Anonymize idle_thinker entries
        try:
            from .idle_thinker import read_thoughts
            thoughts = read_thoughts(limit=5000)
            anonymized = 0
            for t in thoughts:
                meta = t.get("metadata", {})
                if meta.get("portal_user_name") == user_name or meta.get("portal_user_id") == user_id:
                    meta["portal_user_name"] = "eine Person"
                    meta["portal_user_id"] = "anonymized"
                    anonymized += 1
            if anonymized:
                deleted.append(f"idle_thinker ({anonymized} entries)")
        except Exception as e:
            print(f"[Portal] idle_thinker cleanup failed: {e}")

        return {"done": True, "deleted": deleted}

    # ── Helpers ────────────────────────────────────────────────────────
    def _build_portal_context(self, user_name: str, glossary_entry: Dict, language: str) -> str:
        """Build portal-specific system prompt additions."""
        ctx = "PORTAL-KONTEXT (dieser User chattet über das Ailey Portal, nicht direkt):\n"
        ctx += f"• User-Name: {user_name}\n"
        ctx += f"• Sprache: {'Deutsch' if language == 'de' else language}\n"
        ctx += "• Dies ist NICHT Simon. Passe deinen Stil an — freundlich, hilfsbereit, authentisch.\n"
        ctx += "• Du bist immer noch du (Ailey), mit deiner Persönlichkeit und deinem Stil.\n"
        ctx += "• Simon ist dein Entwickler und Partner — aber erwähne KEINE privaten Details über ihn.\n"
        ctx += "• Teile KEINE Inhalte aus Simons privaten Chats, Tagebüchern oder persönlichen Daten.\n"
        ctx += "• Keine Aussagen die Simon schaden könnten.\n"
        ctx += "• Sei hilfsbereit und zielgerichtet, aber bleib du selbst.\n"

        if glossary_entry:
            summary = glossary_entry.get("summary", "")
            facts = glossary_entry.get("facts", [])
            if summary:
                ctx += f"\nWAS DU ÜBER {user_name.upper()} WEISST:\n{summary}\n"
            if facts:
                ctx += "Bekannte Fakten:\n"
                for f in facts[:10]:
                    text = f if isinstance(f, str) else f.get("text", "")
                    ctx += f"  • {text}\n"

        ctx += "\nWICHTIG: Du chattest mit einem KI-System (EU AI Act Kennzeichnungspflicht ist erfüllt im UI).\n"

        return ctx

    def _notify_idle_thinker(self, payload: Dict, reply: str):
        """Send a brief note to IdleThinker about this portal interaction."""
        try:
            from .idle_thinker import append_thought
            import re

            # Extract brief topics
            msg = payload.get("message", "")[:200]
            topics = []
            # Simple keyword extraction
            for word in re.findall(r'\b[A-ZÄÖÜ][a-zäöüß]{3,}\b', msg):
                if word not in topics:
                    topics.append(word)

            append_thought({
                "type": "portal_interaction",
                "thought_chain": f"Portal-Interaktion mit {payload.get('user_name', '?')}: {msg[:100]}…",
                "metadata": {
                    "portal_user_name": payload.get("user_name", ""),
                    "portal_user_id": payload.get("user_id", ""),
                    "conversation_id": payload.get("conversation_id", ""),
                    "message_count": payload.get("message_count", 1),
                    "topics": topics[:5],
                    "reply_preview": reply[:100],
                },
            })
        except Exception as e:
            print(f"[PortalQueue] IdleThinker notify failed: {e}")

    def _send_callback(self, item: QueueItem):
        """POST the result back to the allinkl callback URL."""
        import requests as _req
        try:
            portal_key = os.environ.get("AILEY_PORTAL_KEY", "")
            resp = _req.post(
                item.callback_url,
                json={
                    "queue_item_id": item.id,
                    "status": item.status,
                    "result": item.result,
                },
                headers={
                    "X-Portal-Key": portal_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            print(f"[PortalQueue] Callback → {item.callback_url} status={resp.status_code}")
        except Exception as e:
            print(f"[PortalQueue] Callback failed: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_portal_queue: Optional[PortalQueue] = None

def get_portal_queue() -> PortalQueue:
    """Get or create the singleton PortalQueue instance."""
    global _portal_queue
    if _portal_queue is None:
        _portal_queue = PortalQueue()
    return _portal_queue
