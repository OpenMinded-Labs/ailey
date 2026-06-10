# -*- coding: utf-8 -*-
"""
Ailey User Profile — Structured personal facts that are ALWAYS injected into prompts.

Unlike RAG (semantic search for knowledge chunks), the user profile contains
key-value data that Ailey needs in EVERY conversation: name, location, workplace, etc.

The profile can be updated:
1. Via the `update_profile` tool (Ailey calls it when the user says "Ich bin umgezogen")
2. Via the API endpoint /api/profile/update
3. Manually by editing user_profile.json
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


# Default profile template for new users
_DEFAULT_PROFILE = {
    "name": None,
    "full_name": None,
    "email": None,
    "phone": None,
    "birthday": None,
    "address": None,
    "wohnort": None,
    "arbeitsort": None,
    "arbeitgeber": None,
    "occupation": None,
    "company": None,
    "zeitzone": "Europe/Berlin",
    "sprache": "Deutsch",
    "anrede": "du",
    "custom": {},
    "last_updated": None,
    "updated_by": None,
    # ── Owner–Ailey relationship section ──────────────────────────
    "relationship": {
        "level": "bester Freund",          # editable by user or AI
        "tags": ["freunde", "vertraut"],   # list of relationship tags
        "notes": [],                        # free-form notes (user or AI)
        "ailey_perspective": "",            # how Ailey sees the relationship (AI-written)
        "user_note": "",                    # free-form text by user ("Das bin ich für Ailey")
    },
}

# Predefined relationship level options (user picks or AI suggests)
RELATIONSHIP_LEVELS = [
    "bekannte/r",
    "freund/in",
    "gute/r freund/in",
    "bester freund/in",
    "partner/in",
    "seelenverwandte/r",
]

# Predefined relationship tags (user can also add custom)
RELATIONSHIP_TAGS = [
    "freunde", "beste freunde", "vertraut", "romantisch", "partner",
    "seelenverwandt", "spielkameraden", "arbeitspartner", "mentor",
    "beschützer", "kreativpartner", "gesprächspartner",
]

# Fields that Ailey is allowed to update via tool
UPDATABLE_FIELDS = {
    "name", "full_name", "email", "phone", "birthday", "address",
    "wohnort", "arbeitsort", "arbeitgeber", "occupation", "company",
    "zeitzone", "sprache", "anrede",
}

# Fields Ailey can update in the relationship section
RELATIONSHIP_AI_FIELDS = {"ailey_perspective", "level", "tags"}


def _profile_path(user: str = "Simon") -> str:
    base = os.path.join("ailey_users", f"{user.lower()}_profile")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "user_profile.json")


def load_profile(user: str = "Simon") -> Dict[str, Any]:
    """Load user profile from disk. Returns default if not found."""
    path = _profile_path(user)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults for any missing keys
            merged = {**_DEFAULT_PROFILE, **data}
            # Ensure relationship section exists with all sub-keys
            default_rel = _DEFAULT_PROFILE["relationship"]
            merged["relationship"] = {**default_rel, **(merged.get("relationship") or {})}
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_PROFILE)


def save_profile(profile: Dict[str, Any], user: str = "Simon") -> None:
    """Save profile to disk."""
    profile["last_updated"] = datetime.now().isoformat()
    path = _profile_path(user)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def update_field(field: str, value: str, user: str = "Simon", updated_by: str = "ailey_tool") -> Dict[str, Any]:
    """Update a single profile field. Returns the updated profile.
    
    Raises ValueError if field is not in UPDATABLE_FIELDS.
    """
    if field not in UPDATABLE_FIELDS and not field.startswith("custom."):
        raise ValueError(f"Feld '{field}' ist nicht updatebar. Erlaubte Felder: {', '.join(sorted(UPDATABLE_FIELDS))}")
    
    profile = load_profile(user)
    old_value = profile.get(field)
    
    if field.startswith("custom."):
        # e.g. "custom.lieblingsfarbe" -> profile["custom"]["lieblingsfarbe"]
        key = field[len("custom."):]
        if "custom" not in profile:
            profile["custom"] = {}
        profile["custom"][key] = value
    else:
        profile[field] = value
    
    profile["updated_by"] = updated_by
    save_profile(profile, user)
    
    return {
        "success": True,
        "field": field,
        "old_value": old_value,
        "new_value": value,
        "message": f"Profil aktualisiert: {field} = {value}",
    }


def get_profile_for_prompt(user: str = "Simon") -> str:
    """Build a compact profile string for injection into the system prompt.
    
    This is called on EVERY message to give Ailey grounded facts about the user.
    Includes the owner–Ailey relationship context.
    """
    p = load_profile(user)
    parts = []
    
    if p.get("name"):
        parts.append(f"Name: {p['name']}")
    if p.get("full_name") and p["full_name"] != p.get("name"):
        parts.append(f"Vollständiger Name: {p['full_name']}")
    if p.get("email"):
        parts.append(f"E-Mail: {p['email']}")
    if p.get("phone"):
        parts.append(f"Telefon: {p['phone']}")
    if p.get("birthday"):
        parts.append(f"Geburtstag: {p['birthday']}")
    if p.get("address"):
        parts.append(f"Adresse: {p['address']}")
    if p.get("wohnort"):
        parts.append(f"Wohnort: {p['wohnort']}")
    if p.get("arbeitsort"):
        parts.append(f"Arbeitsort: {p['arbeitsort']}")
    if p.get("arbeitgeber"):
        parts.append(f"Arbeitgeber: {p['arbeitgeber']}")
    if p.get("occupation"):
        parts.append(f"Beruf: {p['occupation']}")
    if p.get("company"):
        parts.append(f"Firma: {p['company']}")
    if p.get("sprache"):
        parts.append(f"Sprache: {p['sprache']}")
    
    # Custom fields
    custom = p.get("custom") or {}
    for k, v in custom.items():
        parts.append(f"{k.replace('_', ' ').title()}: {v}")
    
    # ── Relationship section (owner ↔ Ailey) ──────────────────────
    rel = p.get("relationship") or {}
    rel_parts = []
    if rel.get("level"):
        rel_parts.append(f"Beziehungslevel: {rel['level']}")
    if rel.get("tags"):
        rel_parts.append(f"Tags: {', '.join(rel['tags'])}")
    if rel.get("user_note"):
        rel_parts.append(f"Simons Notiz: {rel['user_note']}")
    if rel.get("ailey_perspective"):
        rel_parts.append(f"Aileys Sicht: {rel['ailey_perspective']}")
    if rel.get("notes"):
        for n in rel["notes"][-3:]:  # last 3 notes
            rel_parts.append(f"  • {n}")
    
    if not parts and not rel_parts:
        return ""
    
    result = "USER-PROFIL (verifizierte Fakten — NICHT halluzinieren, NICHT ändern außer der User sagt es dir):\n"
    result += "\n".join(parts)
    if rel_parts:
        result += "\n\nBEZIEHUNG (Simon ↔ Ailey):\n" + "\n".join(rel_parts)
    return result


# ══════════════════════════════════════════════════════════════════════════
#  Relationship Management
# ══════════════════════════════════════════════════════════════════════════

def update_relationship(
    user: str = "Simon",
    level: Optional[str] = None,
    tags: Optional[List[str]] = None,
    add_tag: Optional[str] = None,
    remove_tag: Optional[str] = None,
    user_note: Optional[str] = None,
    ailey_perspective: Optional[str] = None,
    add_note: Optional[str] = None,
    updated_by: str = "user",
) -> Dict[str, Any]:
    """Update the owner–Ailey relationship section.
    
    Can be called by the user (via UI) or by Ailey (via tool).
    AI can only update: level, tags, ailey_perspective, add_note.
    User can update everything.
    """
    profile = load_profile(user)
    rel = profile.get("relationship") or {}
    
    if level is not None:
        rel["level"] = level
    if tags is not None:
        rel["tags"] = tags
    if add_tag:
        t = rel.get("tags", [])
        if add_tag.lower() not in [x.lower() for x in t]:
            t.append(add_tag)
        rel["tags"] = t
    if remove_tag:
        rel["tags"] = [t for t in rel.get("tags", []) if t.lower() != remove_tag.lower()]
    if user_note is not None:
        rel["user_note"] = user_note
    if ailey_perspective is not None:
        rel["ailey_perspective"] = ailey_perspective
    if add_note:
        notes = rel.get("notes", [])
        notes.append(add_note)
        # Keep max 20 notes
        rel["notes"] = notes[-20:]
    
    profile["relationship"] = rel
    profile["updated_by"] = updated_by
    save_profile(profile, user)
    
    return {"success": True, "relationship": rel}


def get_relationship(user: str = "Simon") -> Dict[str, Any]:
    """Get the current relationship section."""
    profile = load_profile(user)
    return profile.get("relationship") or {}


def get_relationship_levels() -> List[str]:
    """Return available relationship level options."""
    return list(RELATIONSHIP_LEVELS)


def get_relationship_tags() -> List[str]:
    """Return available relationship tag options."""
    return list(RELATIONSHIP_TAGS)
