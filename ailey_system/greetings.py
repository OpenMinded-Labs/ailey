import os
import random
from typing import List

_DEFAULT_GREETINGS: List[str] = [
    "Hey, schön dass du wieder hier bist – fühl dich willkommen.",
    "Hi – ich hab Ohren, Herz und Fokus ganz bei dir.",
    "Willkommen zurück – erzähl mir sanft, was gerade in dir lebt.",
    "Hey du – ich bin da. Was braucht heute etwas Zuwendung?",
    "Gut, dass du auftauchst. Wir atmen kurz – dann dein erster Gedanke?",
    "Ich halt dir Raum – sag mir einfach womit wir beginnen sollen.",
    "Da bist du. Ich hab warme Präsenz für dich – was liegt an?",
    "Lass uns weich starten: ein Satz, wie fühlt es sich gerade an?",
    "Ich bin hier – kein Druck, nur neugierige, freundliche Aufmerksamkeit.",
    "Hi {user} – wenn du magst, gib mir einen kleinen Impuls zum Reinkommen.",
]

_recent_buffer: List[str] = []
_RECENT_MAX = 3


def load_custom_greetings() -> List[str]:
    env = os.environ.get("AILEY_GREETINGS")
    if not env:
        return []
    items = [g.strip() for g in env.split('|') if g.strip()]
    return [g for g in items if len(g) > 2]


def get_system_greeting(user: str) -> str:
    """Return a randomized greeting without mood tag.

    Avoid repeating the last few used greetings.
    Allows override via env AILEY_GREETINGS (pipe-separated list).
    User name is optionally inserted if placeholder {user} present.
    """
    pool = load_custom_greetings() or _DEFAULT_GREETINGS
    candidates = [g for g in pool if g not in _recent_buffer] or pool
    choice = random.choice(candidates)
    if '{user}' in choice:
        choice = choice.replace('{user}', user)
    _recent_buffer.append(choice)
    if len(_recent_buffer) > _RECENT_MAX:
        del _recent_buffer[0:len(_recent_buffer)-_RECENT_MAX]
    return choice
