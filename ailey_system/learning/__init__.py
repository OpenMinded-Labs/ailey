# -*- coding: utf-8 -*-
"""
Ailey Learning — Interactive programming & exam preparation modules.

Supported tracks:
  - HTML, CSS, JavaScript, Python, Rust, PHP, SQL/Datenbanken
  - JSON & XML
  - IHK Mediengestalter Digital & Print (Prüfungsvorbereitung)
    → inkl. 8 echte Prüfungsthemen 2026 (160 Fragen mit offenen Antworten)

Each track has levels 0-5 (Anfänger → Experte).
Users can set their entry level so they don't repeat what they know.
Includes hardcoded quiz/test elements AND LLM-driven interactive teaching.

Features:
  - Offene Fragen mit LLM-Bewertung (Musterantworten + Key Points)
  - Spaced Repetition (SM-2) für falsche Antworten
  - User-generierte Units (Ailey erstellt auf Anfrage neue Lerneinheiten)
  - Multi-User (jeder User hat eigene Progress-Dateien)
"""

from .engine import LearningEngine
from .curricula import TRACKS, get_track, get_unit

__all__ = ["LearningEngine", "TRACKS", "get_track", "get_unit"]
