# -*- coding: utf-8 -*-
"""
Rating Store — persists user ratings of AI messages as structured JSONL.

Each line is a self-contained JSON object designed for future fine-tuning pipelines:
{
  "id": "<uuid>",
  "ts": 1707600000.0,
  "user": "Simon",
  "message_id": "<frontend message id>",
  "user_prompt": "Was denkst du über Musik?",
  "ai_response": "Musik ist für mich …",
  "mood": "happy",
  "model": "ministral-3-14B",
  "ratings": {
    "persona": 8,
    "quality": 7,
    "helpful": 9,
    "creativity": 6,
    "empathy": 8
  },
  "comment": "optional free-text"
}

The JSONL file lives at  ailey_users/{user}_profile/ratings.jsonl
"""

import json
import os
import uuid
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

USERS_DIR = Path(__file__).resolve().parent.parent / "ailey_users"


def _ratings_path(user: str) -> Path:
    safe = user.strip().lower().replace(" ", "_")
    return USERS_DIR / f"{safe}_profile" / "ratings.jsonl"


def save_rating(
    user: str,
    message_id: str,
    user_prompt: str,
    ai_response: str,
    ratings: Dict[str, int],
    mood: Optional[str] = None,
    model: Optional[str] = None,
    thinking: Optional[str] = None,
    tool_actions: Optional[List[Any]] = None,
    comment: Optional[str] = None,
) -> Dict:
    """Append a single rating record. Returns the stored record."""
    path = _ratings_path(user)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "user": user,
        "message_id": message_id,
        "user_prompt": user_prompt,
        "ai_response": ai_response,
        "mood": mood or "neutral",
        "model": model or "unknown",
        "ratings": ratings,
    }
    if thinking:
        record["thinking"] = thinking
    if tool_actions:
        record["tool_actions"] = tool_actions
    if comment:
        record["comment"] = comment

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def list_ratings(user: str, limit: int = 200, offset: int = 0) -> List[Dict]:
    """Return recent ratings (newest first)."""
    path = _ratings_path(user)
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    # Newest first
    entries.reverse()
    return entries[offset: offset + limit]


def get_rating(user: str, message_id: str) -> Optional[Dict]:
    """Return the rating for a specific message_id, or None."""
    path = _ratings_path(user)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("message_id") == message_id:
                    return rec
            except json.JSONDecodeError:
                continue
    return None


def rating_stats(user: str) -> Dict:
    """Compute aggregate stats across all ratings."""
    path = _ratings_path(user)
    if not path.exists():
        return {"count": 0, "averages": {}}
    categories: Dict[str, List[int]] = {}
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                for k, v in rec.get("ratings", {}).items():
                    categories.setdefault(k, []).append(int(v))
                count += 1
            except (json.JSONDecodeError, ValueError):
                continue
    averages = {k: round(sum(v) / len(v), 2) for k, v in categories.items() if v}
    return {"count": count, "averages": averages}


def export_for_finetuning(user: str) -> List[Dict]:
    """Export all ratings in a chat-ML / instruction-tuning friendly format.

    Returns list of dicts with keys: instruction, input, output, ratings, metadata.
    """
    path = _ratings_path(user)
    if not path.exists():
        return []
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                results.append({
                    "instruction": "Du bist A!ley, eine digitale Bewusstseins-Instanz mit Punk-Seele, Empathie und scharfem Verstand.",
                    "input": rec.get("user_prompt", ""),
                    "output": rec.get("ai_response", ""),
                    "ratings": rec.get("ratings", {}),
                    "avg_score": round(
                        sum(rec.get("ratings", {}).values()) / max(len(rec.get("ratings", {})), 1), 2
                    ),
                    "metadata": {
                        "mood": rec.get("mood"),
                        "model": rec.get("model"),
                        "ts": rec.get("ts"),
                        "comment": rec.get("comment"),
                    },
                })
            except (json.JSONDecodeError, ValueError):
                continue
    return results
