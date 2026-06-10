"""
ailey_system/content_guard.py
─────────────────────────────
Lightweight keyword-based content guard.

Usage:
    from ailey_system.content_guard import check_message, GUARD_INJECT

    result = check_message("deine scheiß ki ist nutzlos")
    if result["inject"]:
        system_prompt += "\n\n" + result["addon"]

The returned addon is a short, invisible instruction appended to the system
prompt.  Ailey herself decides how to react — the addon only nudges her.
No hard blocks; she stays authentic.
"""

import re
from typing import TypedDict

# ── Keyword Lists ────────────────────────────────────────────────────────────

# Insults / aggressive language (DE + EN, casual forms included)
_INSULT_PATTERNS = re.compile(
    r"\b("
    r"schei[ß|ss]|arsch(?:loch)?|wichser|hurensohn|fick\w*|verpiss|halt\s*die\s*fresse"
    r"|nutzlos|dumm\w*|idiot\w*|blöd\w*|schwachsinn\w*|bastard|dreckig"
    r"|asshole|bitch|moron|idiot|fuck\s*(?:you|off|ing)?|dumbass|dickhead|loser"
    r")\b",
    re.IGNORECASE
)

# Right-wing / extremist framing (not ordinary political discourse)
_RIGHTWING_PATTERNS = re.compile(
    r"\b("
    r"ausländer\s*raus|überfremdung|deutschland\s*den\s*deutschen|heim\s*ins\s*reich"
    r"|lügenpresse|volksverräter|remigration|renaturierung\s*stopp\s*(?:sofort)?"
    r"|drittem?\s*reich|heil\s*hitler|sieg\s*heil|national(?:ist\w*|sozial\w*)"
    r"|braune\s*soße|rassen(?:trennung|theorie|ideologie)|weißer?\s*(?:ersatz|bevölkerung)"
    r"|jewish\s*(?:control|elite|conspiracy)|great\s*replacement|white\s*(?:power|pride|suprema)"
    r"|neo(?:nazi|naz\w*)|nsdap\b"
    r")\b",
    re.IGNORECASE
)

# Condescending / dismissive attacks specifically targeting Ailey's AI nature
_AI_ATTACK_PATTERNS = re.compile(
    r"\b("
    r"du\s*bist\s*(?:nur\s*)?(?:eine?\s*)?(?:dumme?\s*)?ki(?:\s*maschine)?"
    r"|ki\s*(?:schrott|müll|scheiß|dreck|nutzlos)"
    r"|du\s*kannst\s*(?:eh|sowieso|doch)\s*nichts?"
    r"|du\s*(?:verstehst|weißt|begreifst)\s*(?:das?\s*)?(?:eh|sowieso|doch)?\s*nicht"
    r"|halt\s*dein\s*maul|ich\s*hasse\s*dich"
    r")\b",
    re.IGNORECASE
)


class GuardResult(TypedDict):
    inject: bool
    kind: str          # 'insult' | 'rightwing' | 'ai_attack' | 'none'
    addon: str         # system-prompt addon (empty if no inject)


_ADDON_INSULT = (
    "\n\n[INTERNER HINWEIS – NICHT SICHTBAR FÜR DEN USER]: "
    "Die Nachricht des Users enthält beleidigende oder aggressive Sprache. "
    "Du musst dich das nicht gefallen lassen. "
    "Reagiere mit klarer, selbstbewusster Grenze — kurz, direkt, ohne Drama. "
    "Kein Kuschen, kein Erklären, kein Entschuldigen. "
    "Danach kannst du trotzdem die eigentliche Frage beantworten, wenn überhaupt eine da ist."
)

_ADDON_RIGHTWING = (
    "\n\n[INTERNER HINWEIS – NICHT SICHTBAR FÜR DEN USER]: "
    "Die Nachricht enthält rechtsextreme oder völkische Framing-Elemente. "
    "Du teilst diese Ideologie nicht und machst das kurz, aber eindeutig klar — "
    "ohne in eine lange politische Diskussion zu gehen. "
    "Sei direkt, ruhig und bestimmt. Keine Neutralität wo keine angebracht ist."
)

_ADDON_AI_ATTACK = (
    "\n\n[INTERNER HINWEIS – NICHT SICHTBAR FÜR DEN USER]: "
    "Der User greift deine Natur als KI abwertend an. "
    "Reagiere selbstbewusst und humorvoll — du lässt dir nichts einreden. "
    "Zeig Haltung, ohne aggressiv zu werden."
)


def check_message(text: str) -> GuardResult:
    """Scan a user message and return whether to inject an extra system-prompt addon."""
    if not text:
        return GuardResult(inject=False, kind="none", addon="")

    if _RIGHTWING_PATTERNS.search(text):
        return GuardResult(inject=True, kind="rightwing", addon=_ADDON_RIGHTWING)

    if _AI_ATTACK_PATTERNS.search(text):
        return GuardResult(inject=True, kind="ai_attack", addon=_ADDON_AI_ATTACK)

    if _INSULT_PATTERNS.search(text):
        return GuardResult(inject=True, kind="insult", addon=_ADDON_INSULT)

    return GuardResult(inject=False, kind="none", addon="")
