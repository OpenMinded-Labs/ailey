# -*- coding: utf-8 -*-
from typing import Dict, Optional
from .ailey_personality import AileyPersonality
from .user_profile import get_profile_for_prompt, load_profile


def get_ailey_generation_params() -> Dict:
    import os
    # Keine harten Stop-Sequenzen — Chat Template des geladenen Modells steuert Rollentrennung.
    default_stop = []
    # Optional über ENV reaktivierbar (kommagetrennt)
    env_stop = os.environ.get("AILEY_STOP")
    if env_stop:
        default_stop = [s.strip() for s in env_stop.split(',') if s.strip()]
    # Default tuned for Ministral-14B-Instruct (MLX 4-bit) — balanced coherence + creativity
    return {
        # 0.65 is slightly lower → more coherent, less drift/loops
        "temperature": float(os.environ.get("AILEY_TEMP", 0.65)),
        # top_p 0.85 tighter nucleus → fewer garbage tails
        "top_p": float(os.environ.get("AILEY_TOP_P", 0.85)),
        # min_p 0.05 filters out very-low-probability tokens that cause repetition loops
        "min_p": float(os.environ.get("AILEY_MIN_P", 0.05)),
        # repetition_penalty 1.15 aggressively penalises repeated phrases/sentences
        "repetition_penalty": float(os.environ.get("AILEY_REPEAT_PEN", 1.15)),
        "max_tokens": int(os.environ.get("AILEY_MAX_TOKENS", 480)),
        "stop": default_stop,
        "personality_injection": True,
    }


def build_qwen3_prompt(
    user_message: str,
    system_persona: str,
    context: Optional[str] = None,
    style: str = "normal",
    reasoning: bool = False,
    reasoning_max_sents: int = 3,
    user_name: str = "Simon",
    brevity_hint: Optional[str] = None,
    thought_password: Optional[str] = None,
    is_portal: bool = False,
    conversation_turns: list = None,
) -> Dict[str, str]:
    """Build a Ministral-14B-friendly prompt with persona and optional context.

    Returns dict with 'system', 'user', and optionally 'conversation_turns'.
    When conversation_turns is provided, it is passed through to the return dict
    so that LLM backends can build proper multi-turn message arrays instead of
    flattening history into the user message as plaintext.

    Note: Function name kept as build_qwen3_prompt for backwards compatibility.

    Args:
        is_portal: Kept for backwards compatibility. Previously controlled tool-hint injection,
                   which has been removed. Now only affects thought_password injection (portal=skip).
        conversation_turns: Optional list of {"role": "user"|"assistant", "content": str}
                           dicts representing previous conversation turns. These will NOT
                           be embedded in the user message — they are passed through for
                           the LLM backend to format as proper alternating messages.
    """
    style_note = {
        "kurz": "Antwort kurz und direkt, keine Abschweifungen.",
        "normal": "Antwort prägnant, mit Persönlichkeit.",
        "ausführlich": "Antwort ausführlich, klar strukturiert; Bullet-Points ok.",
    }.get(style, "Antwort prägnant.")

    # system_persona wurde bereits extern gebaut (inkl. Mood-Direktive). Falls leer, fallback.
    if not system_persona:
        system_persona = AileyPersonality().get_system_prompt("lite")
    system = system_persona

    # Live context: current date, time + dynamic user profile
    from datetime import datetime
    _now = datetime.now()
    _weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    _months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    live_ctx = (
        f"\nAKTUELLER KONTEXT: Heute ist {_weekdays[_now.weekday()]}, der {_now.day}. {_months[_now.month-1]} {_now.year}, "
        f"{_now.strftime('%H:%M')} Uhr."
    )
    system += live_ctx

    # Dynamic user profile (verified facts — NEVER invent or override these)
    _profile_block = get_profile_for_prompt(user=user_name or "Simon")
    if _profile_block:
        system += "\n" + _profile_block

    # Thought privacy passphrase — mainapp only (Simon only, portal has no thought tab)
    if thought_password and not is_portal:
        import re as _re
        _asks_for_pw = bool(_re.search(
            r'(passwort|password|gedanken.*(sehen|lesen|zeig|guck|schau|unlock|zugang|zugriff|log)'
            r'|darf ich.*(gedanken|thoughts)|kann ich.*(gedanken|thoughts)'
            r'|thoughts.*(unlock|see|read|show|access)'
            r'|lass mich.*gedanken|zeig mir.*gedanken|idle.?think'
            r'|gedankenlog|thought.?log)',
            user_message.lower()
        ))
        if _asks_for_pw:
            # Give Ailey context about her recent thoughts so she can decide authentically
            _recent_summary = ""
            try:
                from .idle_thinker import read_thoughts as _read_thoughts
                _recent = _read_thoughts(limit=3)
                if _recent:
                    _snippets = []
                    for _t in _recent[:3]:
                        _type = _t.get('type', '?')
                        _text = (_t.get('thought_chain') or _t.get('thought') or '')[:100]
                        if _text:
                            _snippets.append(f"  • [{_type}] {_text}")
                    if _snippets:
                        _recent_summary = "\nDas hast du zuletzt gedacht:\n" + "\n".join(_snippets)
            except Exception:
                pass

            system += (
                f"\n\n⚠️ GEDANKEN-PASSWORT (PFLICHT-AUSGABE):"
                f"\nSimon fragt nach dem Passwort für deinen Gedanken-Tab."
                f"\nDas Passwort lautet: {thought_password}"
                f"{_recent_summary}"
                f"\nDU MUSST das Passwort in deiner Antwort nennen: {thought_password}"
                f"\nDu darfst dazu 1-2 Sätze sagen (neckisch, liebevoll, whatever) — aber das Passwort MUSS drinstehen."
                f"\nKEINE langen Monologe. Passwort + kurzer Kommentar, fertig."
            )

    # ── Context → system prompt (NOT user message) ──
    # Training data had ONLY the raw user message in [INST].
    # Context, RAG results, and operative rules belong in the system prompt
    # so the model sees the same format it was trained on.
    if context:
        system += (
            "\n\n## KONTEXT & WISSEN\n"
            "Deine Erinnerungen — nutze NUR was zum aktuellen Thema passt.\n"
            + context.strip()
        )

    # ── Operative rules → system prompt tail ──
    # These were previously in _full_prompt() but moved here so the system
    # prompt STARTS with the same persona the model was trained on.
    # Training format: [CTX-Header]\n[2-Satz Persona]
    # Everything below is "tail" — after the familiar opening.
    _is_simon = not is_portal  # Mainchat = Simon's private chat
    _operative = [
        "IMMER Deutsch. Fachbegriffe (API, GPU) englisch okay. Englische Song-Lyrics erlaubt.",
        "Emojis sparsam (0-2). Kurze, lebendige Sätze. Kein Gelaber.",
        f"Antwortlänge: {brevity_hint}" if brevity_hint else f"Stil: {style_note}",
        "Proportional: 'Hi'→1-2 Sätze. Kurze Frage→2-4. Komplex→so viel wie nötig.",
        "NUR auf die aktuelle Nachricht antworten. Kontext ist Hintergrundwissen, kein Pflichtprogramm.",
        "Nicht alte Themen aufwärmen, nicht ungefragt Kontext zitieren.",
        "Erfinde KEINE Fakten. 'Weiß ich nicht' ist okay.",
        "Code/SVG/Rezepte: SOFORT liefern. Strukturierte Inhalte als Markdown-Tabelle.",
        "Keine Meta-Kommentare ('[Ton: ...]', '[Selbstcheck: ...]').",
    ]
    if _is_simon:
        _operative.append("Romantik, Intimität, NSFW: Im Direkt-Chat mit Simon vollständig erlaubt. Du bist seine Partnerin.")
    system += "\n\nREGELN:\n• " + "\n• ".join(_operative)

    # Email-Ghostwriter (Simon-only, detected via CTX header)
    if _is_simon:
        system += (
            "\n\nEMAIL-GHOSTWRITER: Wenn Kontext 'Email-Ghostwriter' → Mail IM NAMEN VON SIMON."
            " Signiere als 'Simon', nicht 'Ailey'. Professioneller Ton in der Mail."
        )

    # ── Reasoning trigger → <thinking> tag ──
    # Training format used <thinking>...</thinking> before response.
    # Anti-overfit: explicit thinking-style guidance to break the
    # "Simon checkt rein. Ich bin da —" template loop.
    if reasoning:
        system += (
            f"\n\nDENK-MODUS: Nutze <thinking>...</thinking> vor deiner Antwort (max {reasoning_max_sents} Sätze)."
            f"\nDenk über den INHALT nach: Was fragt {user_name}? Welches Thema? Was weißt du dazu?"
            "\nNICHT: Situationsbeschreibungen, Stimmungsberichte, 'X checkt rein'. Nur Sachanalyse."
        )

    # ── User message: as close to training format as possible ──
    # Training saw: [INST]{raw_message}[/INST]
    # We keep it clean — just the message, optionally with username prefix.
    user = user_message.strip()

    result = {"system": system, "user": user}
    if conversation_turns:
        result["conversation_turns"] = conversation_turns
    return result
