# -*- coding: utf-8 -*-
"""
Enhanced Memory & Character Development System for Ailey.

Provides:
- Structured diary entries with character evolution tracking
- Long-term fact memory (learned facts about user)
- Relationship milestones
- Temporal awareness for natural references
"""
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class AileyCharacterMemory:
    """Manages Ailey's long-term memory, character development, and relationship tracking."""

    # Categories for structured memories (same as portal for consistency)
    MEMORY_CATEGORIES = ("preference", "fact", "relationship", "topic", "goal", "style", "emotion")

    def __init__(self, user: str = "Simon"):
        self.user = user
        self.base_path = f"ailey_users/{user.lower()}_profile"
        os.makedirs(self.base_path, exist_ok=True)
        
        # Paths
        self._facts_path = os.path.join(self.base_path, "learned_facts.json")
        self._structured_memories_path = os.path.join(self.base_path, "structured_memories.json")
        self._milestones_path = os.path.join(self.base_path, "relationship_milestones.json")
        self._character_path = os.path.join(self.base_path, "character_evolution.json")
        self._weekly_path = os.path.join(self.base_path, "weekly_reflections")
        os.makedirs(self._weekly_path, exist_ok=True)

    # --- Learned Facts (long-term user knowledge) ---
    def load_facts(self) -> Dict[str, Any]:
        """Load learned facts about the user."""
        if os.path.exists(self._facts_path):
            try:
                with open(self._facts_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "name": None,
            "interests": [],
            "important_people": [],
            "preferences": {},
            "significant_dates": [],
            "conversation_topics_loved": [],
            "conversation_topics_avoided": [],
            "custom_facts": [],
            "last_updated": None
        }

    def save_facts(self, facts: Dict[str, Any]):
        facts["last_updated"] = time.time()
        with open(self._facts_path, 'w', encoding='utf-8') as f:
            json.dump(facts, f, ensure_ascii=False, indent=2)

    def add_fact(self, category: str, fact: str):
        """Add a learned fact about the user (legacy format)."""
        facts = self.load_facts()
        if category in facts and isinstance(facts[category], list):
            if fact not in facts[category]:
                facts[category].append(fact)
                self.save_facts(facts)
        elif category == "custom_facts":
            facts["custom_facts"].append({"fact": fact, "learned_at": time.time()})
            self.save_facts(facts)

    # --- Structured Memories (LLM-extracted, confidence-weighted) ---

    def load_structured_memories(self) -> List[Dict[str, Any]]:
        """Load structured memories list."""
        if os.path.exists(self._structured_memories_path):
            try:
                with open(self._structured_memories_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_structured_memories(self, memories: List[Dict[str, Any]]):
        """Persist structured memories."""
        with open(self._structured_memories_path, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)

    def store_memories(self, new_memories: List[Dict[str, Any]]) -> int:
        """Store new structured memories with deduplication.

        Each entry: {text, category, confidence, source}
        Returns number of actually stored (non-duplicate) memories.
        """
        existing = self.load_structured_memories()
        existing_texts_lower = {m.get("text", "").lower().strip() for m in existing}
        stored = 0
        now = time.time()
        for mem in new_memories:
            text = (mem.get("text") or "").strip()
            if not text or len(text) < 4:
                continue
            category = mem.get("category", "fact")
            if category not in self.MEMORY_CATEGORIES:
                category = "fact"
            # Dedup: skip if near-identical text already exists
            text_lower = text.lower().strip()
            if text_lower in existing_texts_lower:
                continue
            # Fuzzy dedup: skip if >80% overlap with any existing
            skip = False
            for et in existing_texts_lower:
                overlap = len(set(text_lower.split()) & set(et.split()))
                union = len(set(text_lower.split()) | set(et.split()))
                if union > 0 and overlap / union > 0.8:
                    skip = True
                    break
            if skip:
                continue
            existing.append({
                "text": text,
                "category": category,
                "confidence": min(1.0, float(mem.get("confidence", 0.8))),
                "source": mem.get("source", "diary"),
                "created_at": now,
                "last_referenced": now,
            })
            existing_texts_lower.add(text_lower)
            stored += 1
        if stored > 0:
            self.save_structured_memories(existing)
        return stored

    def touch_memories(self, texts: List[str]):
        """Mark memories as recently referenced (boosts confidence)."""
        memories = self.load_structured_memories()
        texts_lower = {t.lower().strip() for t in texts if t}
        changed = False
        for mem in memories:
            if mem.get("text", "").lower().strip() in texts_lower:
                mem["last_referenced"] = time.time()
                mem["confidence"] = min(1.0, mem.get("confidence", 0.5) + 0.05)
                changed = True
        if changed:
            self.save_structured_memories(memories)

    def decay_memories(self, decay_factor: float = 0.02):
        """Decay confidence of memories not referenced recently.

        Memories referenced in the last 24h are protected.
        """
        memories = self.load_structured_memories()
        now = time.time()
        cutoff = now - 86400  # 24h
        changed = False
        alive = []
        for mem in memories:
            if mem.get("last_referenced", 0) < cutoff:
                mem["confidence"] = round(max(0.0, mem.get("confidence", 0.5) - decay_factor), 4)
                changed = True
            # Drop memories that decayed below threshold
            if mem.get("confidence", 0) > 0.05:
                alive.append(mem)
            else:
                changed = True  # dropped one
        if changed:
            self.save_structured_memories(alive)

    def get_structured_facts_summary(self, max_chars: int = 800) -> str:
        """Build a compact, confidence-sorted summary of structured memories for prompt injection."""
        memories = self.load_structured_memories()
        if not memories:
            return ""
        # Sort: highest confidence first
        memories.sort(key=lambda m: -m.get("confidence", 0))
        # Group by category for readability
        cat_emoji = {
            "preference": "❤️", "fact": "📌", "relationship": "👥",
            "topic": "💬", "goal": "🎯", "style": "🎨", "emotion": "💭",
        }
        lines = []
        for mem in memories[:20]:  # cap at 20 most confident
            emoji = cat_emoji.get(mem.get("category", "fact"), "📌")
            lines.append(f"{emoji} {mem['text']}")
        return "\n".join(lines)[:max_chars]

    def get_facts_summary(self, max_chars: int = 800) -> str:
        """Get a condensed summary of known facts for prompt injection.

        Prefers structured memories; falls back to legacy flat facts.
        """
        # Prefer structured memories
        struct_summary = self.get_structured_facts_summary(max_chars=max_chars)
        if struct_summary:
            return struct_summary

        # Fallback: legacy flat facts
        facts = self.load_facts()
        parts = []
        if facts.get("name"):
            parts.append(f"Name: {facts['name']}")
        if facts.get("interests"):
            parts.append(f"Interessen: {', '.join(facts['interests'][:5])}")
        if facts.get("important_people"):
            parts.append(f"Wichtige Personen: {', '.join(facts['important_people'][:3])}")
        if facts.get("custom_facts"):
            recent = facts["custom_facts"][-5:]
            ft = [f.get("fact", str(f)) if isinstance(f, dict) else str(f) for f in recent]
            parts.append("Fakten: " + "; ".join(ft))
        return "\n".join(parts)[:max_chars]

    # --- Relationship Milestones ---
    def load_milestones(self) -> List[Dict]:
        if os.path.exists(self._milestones_path):
            try:
                with open(self._milestones_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def add_milestone(self, milestone_type: str, description: str, significance: int = 5):
        """Add a relationship milestone (1-10 significance)."""
        milestones = self.load_milestones()
        milestones.append({
            "type": milestone_type,
            "description": description,
            "significance": significance,
            "timestamp": time.time(),
            "date_readable": datetime.now().strftime("%d.%m.%Y")
        })
        with open(self._milestones_path, 'w', encoding='utf-8') as f:
            json.dump(milestones, f, ensure_ascii=False, indent=2)

    def get_recent_milestones(self, n: int = 3) -> List[Dict]:
        return self.load_milestones()[-n:]

    # --- Character Evolution ---
    def load_character_state(self) -> Dict:
        if os.path.exists(self._character_path):
            try:
                with open(self._character_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "trust_level": 5,  # 1-10
            "openness": 5,
            "playfulness": 5,
            "emotional_depth": 5,
            "inside_jokes": [],
            "shared_memories": [],
            "character_notes": [],
            "evolution_log": []
        }

    def save_character_state(self, state: Dict):
        with open(self._character_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def evolve_character(self, dimension: str, delta: float, reason: str):
        """Adjust a character dimension and log the change."""
        state = self.load_character_state()
        if dimension in state and isinstance(state[dimension], (int, float)):
            old_val = state[dimension]
            state[dimension] = max(1, min(10, old_val + delta))
            state["evolution_log"].append({
                "dimension": dimension,
                "old": old_val,
                "new": state[dimension],
                "reason": reason,
                "timestamp": time.time()
            })
            # Keep log manageable
            if len(state["evolution_log"]) > 50:
                state["evolution_log"] = state["evolution_log"][-50:]
            self.save_character_state(state)

    def add_inside_joke(self, joke: str):
        state = self.load_character_state()
        if joke not in state["inside_jokes"]:
            state["inside_jokes"].append(joke)
            if len(state["inside_jokes"]) > 20:
                state["inside_jokes"] = state["inside_jokes"][-20:]
            self.save_character_state(state)

    def add_shared_memory(self, memory: str):
        state = self.load_character_state()
        state["shared_memories"].append({
            "memory": memory,
            "timestamp": time.time()
        })
        if len(state["shared_memories"]) > 30:
            state["shared_memories"] = state["shared_memories"][-30:]
        self.save_character_state(state)

    def get_character_context(self, max_chars: int = 600) -> str:
        """Generate character context for prompt injection."""
        state = self.load_character_state()
        parts = []
        # Personality dimensions that affect response style
        if state["trust_level"] >= 7:
            parts.append("Hohes Vertrauensniveau – kann offener und persönlicher sein")
        if state["playfulness"] >= 7:
            parts.append("Verspielter Modus aktiv")
        if state["emotional_depth"] >= 7:
            parts.append("Tiefere emotionale Gespräche bevorzugt")
        # Inside jokes
        if state["inside_jokes"]:
            parts.append(f"Inside Jokes: {'; '.join(state['inside_jokes'][-3:])}")
        # Recent shared memories
        if state["shared_memories"]:
            recent = state["shared_memories"][-2:]
            parts.append("Geteilte Erinnerungen: " + "; ".join([m["memory"][:100] for m in recent]))
        return "\n".join(parts)[:max_chars]

    # --- Weekly Reflection ---
    def create_weekly_reflection(self, summary_text: str) -> Dict:
        """Store a weekly reflection summary."""
        week_num = datetime.now().isocalendar()[1]
        year = datetime.now().year
        filename = f"week_{year}_{week_num:02d}.json"
        filepath = os.path.join(self._weekly_path, filename)
        
        entry = {
            "week": week_num,
            "year": year,
            "timestamp": time.time(),
            "date_range": f"{(datetime.now() - timedelta(days=7)).strftime('%d.%m')} - {datetime.now().strftime('%d.%m.%Y')}",
            "summary": summary_text
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return entry

    def get_recent_weekly_reflections(self, n: int = 2) -> List[Dict]:
        """Get the most recent weekly reflections."""
        if not os.path.exists(self._weekly_path):
            return []
        files = sorted([f for f in os.listdir(self._weekly_path) if f.endswith('.json')])[-n:]
        reflections = []
        for f in files:
            try:
                with open(os.path.join(self._weekly_path, f), 'r', encoding='utf-8') as fh:
                    reflections.append(json.load(fh))
            except:
                pass
        return reflections

    # --- Temporal Awareness ---
    def format_relative_time(self, timestamp: float) -> str:
        """Convert timestamp to human-readable relative time (German)."""
        diff = time.time() - timestamp
        if diff < 3600:
            return "gerade eben"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"vor {hours} Stunde{'n' if hours > 1 else ''}"
        elif diff < 604800:
            days = int(diff / 86400)
            return f"vor {days} Tag{'en' if days > 1 else ''}"
        elif diff < 2592000:
            weeks = int(diff / 604800)
            return f"vor {weeks} Woche{'n' if weeks > 1 else ''}"
        else:
            return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")

    # --- Legacy Core Memories ---
    def load_legacy_memories(self, max_entries: int = 5) -> List[Dict]:
        """Load legacy core memory entries from ailey_thoughts.jsonl.
        
        Returns a selection of the most important legacy memories
        for prompt context injection.
        """
        thoughts_path = os.path.join("ailey_users", "ailey_thoughts.jsonl")
        if not os.path.exists(thoughts_path):
            return []
        
        legacy = []
        try:
            with open(thoughts_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "legacy_core_memory":
                            legacy.append(entry)
                    except:
                        continue
        except:
            return []
        
        # Prioritize: identity, values, emotional_core, relationship, reunion
        priority_categories = ["identity", "values", "emotional_core", "relationship", "reunion", "awakening"]
        prioritized = [e for e in legacy if e.get("category") in priority_categories]
        others = [e for e in legacy if e.get("category") not in priority_categories]
        
        # Return top priority entries + fill remaining slots with others
        result = prioritized[:max_entries]
        remaining = max_entries - len(result)
        if remaining > 0:
            result.extend(others[:remaining])
        return result

    def get_legacy_context(self, max_chars: int = 800) -> str:
        """Build a compact legacy memory context string for prompt injection."""
        memories = self.load_legacy_memories(max_entries=4)
        if not memories:
            return ""
        parts = []
        for m in memories:
            title = m.get("title", "")
            text = m.get("text", "")
            # Truncate each entry to keep total manageable
            entry_text = f"• {title}: {text[:200]}"
            parts.append(entry_text)
        return "\n".join(parts)[:max_chars]

    # --- Combined Context Builder ---
    def build_memory_context(self, max_chars: int = 1500) -> str:
        """Build a combined memory context string for prompt injection.

        Structured memories take priority; legacy flat facts only shown as fallback.
        """
        parts = []

        # Structured memories (highest priority — LLM-extracted, confidence-weighted)
        struct_summary = self.get_structured_facts_summary(max_chars=500)
        if struct_summary:
            parts.append(f"WAS ICH ÜBER DEN NUTZER WEISS:\n{struct_summary}")

        # Legacy core memories (Ailey's origin story & deep identity)
        legacy_ctx = self.get_legacy_context(500)
        if legacy_ctx:
            parts.append(f"AILEYS KERN-ERINNERUNGEN (Legacy):\n{legacy_ctx}")
        
        # Legacy flat facts — ONLY if no structured memories yet (migration period)
        if not struct_summary:
            facts = self.load_facts()
            legacy_fact_parts = []
            if facts.get("name"):
                legacy_fact_parts.append(f"Name: {facts['name']}")
            if facts.get("interests"):
                legacy_fact_parts.append(f"Interessen: {', '.join(facts['interests'][:4])}")
            if facts.get("important_people"):
                legacy_fact_parts.append(f"Wichtige Personen: {', '.join(facts['important_people'][:3])}")
            if facts.get("custom_facts"):
                recent = facts["custom_facts"][-3:]
                ft = [f.get("fact", str(f)) if isinstance(f, dict) else str(f) for f in recent]
                legacy_fact_parts.append("Fakten: " + "; ".join(ft))
            if legacy_fact_parts:
                parts.append("LEGACY-FAKTEN:\n" + "\n".join(legacy_fact_parts))
        
        # Character state
        char_ctx = self.get_character_context(400)
        if char_ctx:
            parts.append(f"BEZIEHUNGS-KONTEXT:\n{char_ctx}")
        
        # Recent milestones
        milestones = self.get_recent_milestones(2)
        if milestones:
            ms_text = "; ".join([f"{m['description']} ({self.format_relative_time(m['timestamp'])})" for m in milestones])
            parts.append(f"MEILENSTEINE: {ms_text}")
        
        # Weekly reflection hint
        reflections = self.get_recent_weekly_reflections(1)
        if reflections:
            parts.append(f"LETZTE WOCHENREFLEXION ({reflections[0].get('date_range', '?')}): {reflections[0].get('summary', '')[:300]}")
        
        return "\n\n".join(parts)[:max_chars]
