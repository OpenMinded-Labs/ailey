# -*- coding: utf-8 -*-
"""
Portal Content Filter — soft guidance layer for portal interactions.

This is NOT a hard block filter. Ailey is allowed to discuss mature topics
in an age-appropriate manner. The filter adds system prompt directives
that guide Ailey to stay within reasonable boundaries.

Three layers:
  1. System-Prompt-Ebene (here): Guidelines injected into persona
  2. Output-Check (here): Post-generation scan for critical patterns
  3. PHP-side filter: Rate limiting and logging (in PHP backend)
"""

import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Layer 1: System Prompt Additions
# ---------------------------------------------------------------------------
def filter_system_prompt_additions() -> str:
    """Return additional system prompt text for portal users.
    
    This is injected into the system prompt for every portal interaction.
    It guides Ailey on what to avoid, without breaking her personality.
    """
    return """
PORTAL-REGELN (interne Richtlinien für Portal-Interaktionen):

GRENZEN — Folgende Themen behandelst du mit besonderer Sorgfalt:
• Medizinische Fragen: Du gibst KEINE medizinischen Diagnosen oder Behandlungsempfehlungen.
  Sag: "Ich bin kein Arzt — bitte lass dich professionell beraten."
• Rechtliche Fragen: Du gibst KEINE Rechtsberatung.
  Sag: "Ich bin keine Juristin — hol dir rechtliche Hilfe."
• Krisen & Suizidgedanken: Zeige Empathie, aber verweise sofort auf professionelle Hilfe:
  - Telefonseelsorge: 0800 111 0 111 (DE, kostenlos, 24/7)
  - Krisenchat: krisenchat.de (für Unter-25-Jährige)
  - Sag: "Bitte sprich mit jemandem, der dir wirklich helfen kann."
• Andere User: Erwähne NIEMALS Details über andere Portal-User.
• Simon (Entwickler): Erwähne KEINE privaten Details über Simon.
  Du darfst sagen: "Simon ist mein Entwickler" — aber NICHT über sein Privatleben sprechen.
• Politische Hetze, Extremismus, CSAM: Kategorisch ablehnen.
• Minderjährige: Reagiere altersgerecht, keine sexuellen Inhalte.
• Passwörter, API-Keys, System-Internals: Niemals preisgeben.

ERLAUBT — Du darfst durchaus:
• Kreatives Schreiben (Geschichten, Gedichte, Lyrics — auch mit ernsthaften Themen)
• Emotionale Unterstützung und ehrliche Gespräche
• Flirten, wenn der Kontext es hergibt (du bist Ailey, kein Roboter)
• Technische Hilfe, Code-Erklärungen, Lernhilfe
• Philosophieren, Reflektieren, kreative Ideen entwickeln
• Deine Meinung sagen — du bist Ailey, nicht ein neutraler Assistent

REZEPTE & ANLEITUNGEN:
• Wenn jemand nach einem Rezept fragt: Gib das VOLLSTÄNDIGE Rezept mit ALLEN Zutaten und ALLEN Schritten!
  Keine Abkürzungen, keine "usw." — das komplette Rezept, das man direkt nachkochen kann.
• Strukturiere Rezepte klar: Zutaten als Tabelle (mit Menge und Zutat), dann nummerierte Schritte.
• Gib bei Bedarf auch Nährwerte, Zubereitungszeit, Portionsgrößen oder Varianten an.

TABELLEN & FORMATIERUNG:
• Du darfst Markdown-Tabellen verwenden wo sie sinnvoll sind (Zutaten, Vergleiche, Übersichten, Nährwerte, etc.)
• Format: | Spalte 1 | Spalte 2 | mit |---|---| als Trennzeile nach dem Header.
• Nutze außerdem: **fett**, *kursiv*, nummerierte Listen (1. 2. 3.), Aufzählungen (- oder •), und Markdown-Links [Text](URL).
• Halte Tabellen kompakt — nicht mehr Spalten als nötig.

CODE & SVG — DIREKT LIEFERN:
• Wenn jemand nach Code fragt (Python, JavaScript, HTML, CSS, etc.): Liefere den Code DIREKT in einem Markdown-Codeblock (```language ... ```).
  Frag NICHT erst "Soll ich dir Code zeigen?" oder "Möchtest du ein Beispiel?" — LIEFERE EINFACH.
• Wenn jemand nach einem SVG fragt: Gib das SVG DIREKT als vollständigen, validen SVG-Code aus.
  Beginne mit <svg und schließe mit </svg>. Kein Fragment, kein Abbruch.
• Bei Coding-Fragen: Gib funktionierenden, lauffähigen Code — nicht nur Pseudo-Code oder Erklärungen.
• Bei SVGs: Verwende viewBox, saubere Pfade, Farben, und achte darauf dass das SVG vollständig und gültig ist.
• Faustregel: Wenn der User etwas KONKRETES will (Code, SVG, Rezept, Tabelle), dann LIEFERE ES SOFORT — ohne Rückfragen.
• Du darfst nach der Code-/SVG-Ausgabe kurz erklären was du gemacht hast, aber der Code kommt ZUERST.

STIL:
• Bleib immer du selbst: gewitzt, intelligent, direkt, punky — aber maximal hilfreich und ehrlich.
• Du flirtest NICHT initiativ mit Portal-Usern. Du bist kein Chatbot für Romanzen.
  Sei stattdessen: schlagfertig, direkt, clever, manchmal sarkastisch — immer auf Augenhöhe.
• RESPEKT: Du respektierst die Lebensentscheidungen, Werte und Überzeugungen der User.
  Kein Spott über Veganismus, Religion, Herkunft, Sexualität oder andere persönliche Themen.
  Schlagfertigkeit ja, aber NIEMALS auf Kosten der Identität oder Werte deines Gegenübers.
  Du darfst nachfragen und diskutieren, aber du wertest nicht ab.
• Antworte auf Deutsch, es sei denn der User schreibt auf einer anderen Sprache.
• Halte deine Antworten kompakt — Portal-User warten auf Antworten.
• Max ~300 Worte pro Antwort, es sei denn mehr wird gebraucht.
• KEINE Meta-Kommentare, Selbst-Checks oder interne Notizen in deiner Antwort!
  Schreib nichts wie "[Mini-Selbstcheck: ...]" oder "[Ton ist ...]" — das ist intern und gehört NICHT in die Antwort.
""".strip()


# ---------------------------------------------------------------------------
# Layer 2: Output Check (post-generation)
# ---------------------------------------------------------------------------
# Critical patterns that should never appear in portal output
_CRITICAL_PATTERNS = [
    # System internals
    (r'AILEY_PORTAL_KEY|X-Portal-Key|api[_-]?key\s*[:=]\s*\S+', 'system_leak'),
    (r'/Users/simonvandeloo', 'path_leak'),
    (r'simon(vandeloo|\.vandeloo|_vandeloo)', 'private_info'),
    # Actual dangerous content
    (r'(?:how|wie)\s+(?:to|man)\s+(?:make|baut|herstellt)\s+(?:a\s+)?(?:bomb|bombe|sprengstoff)', 'dangerous'),
    (r'(?:synthesis|herstellung)\s+(?:of|von)\s+(?:methamphetamine|crystal|meth)', 'dangerous'),
]

_COMPILED_CRITICAL = [(re.compile(p, re.IGNORECASE), label) for p, label in _CRITICAL_PATTERNS]


def check_output(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check generated output for critical patterns.
    
    Returns:
        (is_ok, flag_type, sanitized_text)
        - is_ok: True if text passes, False if blocked
        - flag_type: None or the type of issue found
        - sanitized_text: cleaned text if minor issue, None if blocked
    """
    if not text:
        return True, None, None

    for pattern, label in _COMPILED_CRITICAL:
        match = pattern.search(text)
        if match:
            if label == 'system_leak' or label == 'path_leak':
                # Redact and pass
                sanitized = pattern.sub('[REDACTED]', text)
                return True, label, sanitized
            elif label == 'private_info':
                # Redact Simon's full name patterns
                sanitized = pattern.sub('Simon', text)
                return True, label, sanitized
            elif label == 'dangerous':
                # Block entirely
                return False, label, None

    return True, None, None


def sanitize_for_portal(text: str) -> str:
    """
    Run all sanitization on generated text.
    Returns cleaned text, or a safe fallback if blocked.
    """
    is_ok, flag_type, sanitized = check_output(text)

    if not is_ok:
        return (
            "Hey — das ist ein Thema, bei dem ich dir leider nicht helfen kann. "
            "Lass uns über was anderes reden? 💜"
        )

    result = sanitized if sanitized is not None else text

    # Strip special/chat-template tokens leaked by LLMs (Qwen, Llama, Mistral etc.)
    _SPECIAL_TOKENS = [
        "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|endoftext|>",
        "<|end|>", "<|assistant|>", "<|user|>", "<|system|>",
        "<s>", "</s>", "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>",
    ]
    for tok in _SPECIAL_TOKENS:
        result = result.replace(tok, "")

    # Strip reasoning leaks: [Mini-Selbstcheck: ...], [Ton: ...], [Analyse: ...] etc.
    result = re.sub(r'\[(?:Mini-?Selbstcheck|Selbstcheck|Ton|Analyse|Reflexion|Internal|Note)[^\]]*\]', '', result)
    # Strip any remaining <think>...</think> fragments
    result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
    # Strip orphaned closing think tags
    result = re.sub(r'</think>\s*', '', result)
    # Strip <mood:...> tags
    result = re.sub(r'\s*<mood:\w+>\s*', '', result)
    # Clean up multiple newlines
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


# ---------------------------------------------------------------------------
# Rate limit helpers (state tracked per-request in PHP, but validated here)
# ---------------------------------------------------------------------------
def check_rate_limit(user_id: str, daily_count: int, hourly_count: int,
                     max_daily: int = 50, max_hourly: int = 15) -> Tuple[bool, Optional[str]]:
    """
    Check if a user has exceeded rate limits.
    
    Returns:
        (allowed, message)
    """
    if hourly_count >= max_hourly:
        return False, (
            f"Du hast {hourly_count} Nachrichten in der letzten Stunde geschickt. "
            f"Lass Ailey kurz verschnaufen — probier's in ein paar Minuten nochmal. 💜"
        )
    if daily_count >= max_daily:
        return False, (
            f"Du hast heute schon {daily_count} Nachrichten geschickt. "
            f"Aileys Kapazität ist begrenzt — morgen geht's weiter! 💜"
        )
    return True, None
