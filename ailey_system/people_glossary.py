# -*- coding: utf-8 -*-
"""
People Glossary — Ailey's knowledge about REAL people she encounters.

Maintains structured profiles for every real person Ailey learns about:
- People Simon mentions in conversation
- Email senders / recipients
- Names appearing in diary entries

Each profile collects atomic facts as individual entries, which can be
merged/consolidated periodically to keep profiles clean.

IMPORTANT: Only REAL PEOPLE get entries. No roles, concepts, body parts,
emotions, or random nouns.

Storage: ailey_users/people_glossary.json  (global, not per-user)
"""

import json
import os
import re
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

# ── Schema for a single person entry ──────────────────────────────────────
# {
#   "id": "ben_thoma",                           # slug key
#   "name": "Ben Thoma",                          # display name (full name preferred)
#   "aliases": ["Ben", "Benjamin"],               # alternative names / references
#   "email": "ben@example.de",                    # known email (if any)
#   "facts": [                                    # atomic facts — one piece of info each
#     {"text": "Chef der Hinterhofagentur", "source": "email", "ts": 170000000},
#     {"text": "Hat Ailey nach dem Wetter gefragt", "source": "email", "ts": 170000001},
#   ],
#   "last_seen": 1700000000.0,
#   "first_seen": 1699000000.0,
#   "source": "chat",                             # original source
#   "interaction_count": 5,
# }

_GLOSSARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ailey_users", "people_glossary.json"
)

_MAX_FACTS = 30
_MAX_ALIASES = 10


# ══════════════════════════════════════════════════════════════════════════
#  STOP WORDS & NAME VALIDATION
# ══════════════════════════════════════════════════════════════════════════

_STOP_WORDS = {
    'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'man', 'das', 'die',
    'der', 'ein', 'eine', 'einem', 'einen', 'auch', 'und', 'oder', 'aber',
    'dann', 'wenn', 'weil', 'dass', 'was', 'wie', 'nicht', 'noch', 'schon',
    'mal', 'jetzt', 'hier', 'dort', 'heute', 'gestern', 'morgen', 'immer',
    'nie', 'alles', 'nichts', 'bitte', 'danke', 'vielleicht', 'warum',
    'simon', 'ailey',  # known entities, not "new" people
    # Titles / honorifics (strip these, don't create "Herr Müller")
    'herr', 'frau', 'fräulein', 'doktor', 'professor',
    'mr', 'mrs', 'ms', 'miss', 'dr', 'prof',
}

# Broader list: common nouns, concepts, roles, section headers, tech terms.
# These are case-insensitive. Anything in here is rejected as a person name.
# In German ALL nouns are capitalized, so we must be very aggressive here.
_NON_PERSON_WORDS = _STOP_WORDS | {
    # Family roles (the ROLE, not a name)
    'papa', 'mama', 'oma', 'opa', 'kind', 'baby', 'kleinkind',
    'freund', 'freundin', 'partner', 'partnerin',
    'chef', 'chefin', 'kollege', 'kollegin',
    'bruder', 'schwester', 'mutter', 'vater', 'tochter', 'sohn',
    'onkel', 'tante', 'nachbar', 'nachbarin', 'cousin', 'cousine',
    'lehrer', 'lehrerin', 'arzt', 'ärztin', 'anwalt', 'anwältin',
    'mitbewohner', 'mitbewohnerin', 'nutzer', 'user', 'spieler',
    # Body parts / physical
    'augen', 'haare', 'gesicht', 'stimme', 'herz', 'kopf', 'hand',
    'hände', 'finger', 'lippen', 'mund', 'nase', 'ohr', 'ohren',
    'brust', 'schulter', 'schultern', 'arm', 'arme', 'bein', 'beine',
    'haut', 'rücken', 'bauch', 'fuß', 'füße', 'zehen', 'knie',
    'nacken', 'hals', 'stirn', 'wange', 'wangen', 'kinn', 'bart',
    'haar', 'auge', 'zähne', 'zunge', 'nagel', 'nägel', 'nagelspitzen',
    'rippen', 'hüfte', 'knöchel', 'ellbogen', 'handgelenk',
    # Possessive body/self references (common in diaries)
    'meine', 'meiner', 'meinem', 'meinen', 'mein',
    'deine', 'deiner', 'deinem', 'deinen', 'dein',
    'seine', 'seiner', 'seinem', 'seinen', 'sein',
    'ihre', 'ihrer', 'ihrem', 'ihren', 'ihr',
    # Concepts / abstract nouns (ALL German nouns are capitalized!)
    'liebe', 'leben', 'arbeit', 'musik', 'kunst', 'zeit', 'geld', 'haus',
    'welt', 'nacht', 'tag', 'traum', 'angst', 'glück', 'zukunft',
    'idee', 'plan', 'projekt', 'system', 'fehler', 'problem', 'lösung',
    'antwort', 'frage', 'gedanke', 'gefühl', 'gedanken', 'gefühle',
    'rolle', 'neues', 'assoziation', 'reflexion', 'analyse', 'fazit',
    'ergebnis', 'einleitung', 'zusammenfassung', 'stimmung',
    'kreativität', 'emotions', 'thema', 'themen', 'dynamik',
    'meine assoziation', 'erwähnte personen', 'gelernte fakten',
    'seele', 'geist', 'verstand', 'bewusstsein', 'unterbewusstsein',
    'wahrheit', 'lüge', 'hoffnung', 'verzweiflung', 'einsamkeit',
    'freiheit', 'schmerz', 'freude', 'trauer', 'wut', 'ekel',
    'neugier', 'langeweile', 'scham', 'schuld', 'stolz', 'neid',
    'eifersucht', 'sehnsucht', 'nostalgie', 'melancholie',
    'energie', 'kraft', 'schwäche', 'stärke', 'mut', 'furcht',
    'vertrauen', 'misstrauen', 'respekt', 'bewunderung',
    'beziehung', 'verbindung', 'distanz', 'nähe', 'intimität',
    'erinnerung', 'erinnerungen', 'vergangenheit', 'gegenwart',
    'moment', 'augenblick', 'ewigkeit', 'unendlichkeit',
    'chaos', 'ordnung', 'harmonie', 'dissonanz', 'kontrast',
    'licht', 'schatten', 'dunkelheit', 'helligkeit', 'dämmerung',
    'stille', 'lärm', 'geräusch', 'klang', 'melodie', 'rhythmus',
    'wärme', 'kälte', 'hitze', 'frost', 'regen', 'schnee', 'wind',
    'sonne', 'mond', 'sterne', 'himmel', 'erde', 'meer', 'ozean',
    'berg', 'wald', 'fluss', 'see', 'wiese', 'garten',
    'raum', 'platz', 'ort', 'stelle', 'ecke', 'winkel',
    'tür', 'fenster', 'wand', 'decke', 'boden', 'treppe',
    'straße', 'weg', 'pfad', 'brücke', 'tor', 'mauer',
    'stadt', 'dorf', 'land', 'heimat', 'zuhause', 'wohnung',
    'bett', 'stuhl', 'tisch', 'sofa', 'lampe', 'spiegel',
    'kleid', 'hemd', 'hose', 'schuh', 'schuhe', 'jacke',
    'kaffee', 'tee', 'wasser', 'bier', 'wein', 'essen',
    'morgen', 'abend', 'mittag', 'vormittag', 'nachmittag',
    'anfang', 'ende', 'mitte', 'beginn', 'schluss', 'abschluss',
    'grund', 'ursache', 'wirkung', 'folge', 'konsequenz',
    'ziel', 'zweck', 'sinn', 'bedeutung', 'wert', 'preis',
    'grenze', 'horizont', 'perspektive', 'blick', 'sicht',
    'sprache', 'wort', 'worte', 'satz', 'text', 'buch', 'brief',
    'geschichte', 'erzählung', 'märchen', 'legende', 'mythos',
    'bild', 'foto', 'gemälde', 'zeichnung', 'skizze',
    'farbe', 'form', 'gestalt', 'figur', 'muster', 'struktur',
    'spiel', 'tanz', 'gesang', 'lied', 'song', 'album',
    'film', 'serie', 'show', 'szene', 'akt', 'drama', 'komödie',
    'maschine', 'motor', 'gerät', 'werkzeug', 'instrument',
    'netz', 'netzwerk', 'internet', 'daten', 'information',
    'algorithmus', 'programm', 'software', 'hardware',
    'nachricht', 'botschaft', 'mitteilung', 'hinweis', 'warnung',
    'fakt', 'fakten', 'meinung', 'ansicht', 'standpunkt',
    'versuch', 'experiment', 'test', 'probe', 'übung',
    'erfolg', 'misserfolg', 'niederlage', 'sieg', 'triumph',
    'kampf', 'krieg', 'frieden', 'konflikt', 'streit',
    'regeln', 'gesetz', 'recht', 'pflicht', 'verantwortung',
    'macht', 'kontrolle', 'einfluss', 'autorität', 'dominanz',
    'simulation', 'illusion', 'realität', 'fantasie', 'fiktion',
    'identität', 'persönlichkeit', 'charakter', 'wesen', 'natur',
    'rebellion', 'revolution', 'veränderung', 'wandel', 'entwicklung',
    'fortschritt', 'rückschritt', 'stillstand', 'bewegung',
    'atem', 'puls', 'herzschlag', 'blut', 'schweiß', 'träne', 'tränen',
    'kuss', 'küsse', 'umarmung', 'berührung', 'blicke',
    'ekstase', 'orgasmus', 'lust', 'verlangen', 'begierde',
    # German diary section headers (often matched as "names")
    'zusammenfassung', 'gelernte', 'emotionen', 'emotionale',
    'notiz', 'beziehungsentwicklung', 'offene', 'ziele',
    'erwähnte', 'personen', 'neue', 'pläne', 'reflexion',
    'analyse', 'beobachtung', 'erkenntnis', 'bewertung',
    # Common adjectives that may appear capitalized at line start
    'neue', 'alte', 'kleine', 'große', 'gute', 'schlechte',
    'erste', 'letzte', 'nächste', 'andere', 'eigene',
    # Tech terms
    'code', 'server', 'api', 'app', 'browser', 'python', 'react',
    'details', 'updates', 'changelog', 'readme', 'todo', 'feature',
    'status', 'fortschritt', 'hinweis', 'warnung', 'tipp',
    'frontend', 'backend', 'plugin', 'modul', 'funktion',
    'prompt', 'token', 'modell', 'training', 'output', 'input',
    # Places
    'berlin', 'deutschland', 'europa', 'münchen', 'hamburg', 'köln',
    'düsseldorf', 'frankfurt', 'wien', 'zürich',
    'bad neuenahr-ahrweiler', 'vyrus valley', 'ahrweiler',
    # Holidays / dates
    'valentinstag', 'weihnachten', 'ostern', 'silvester',
    # English common words that slip in
    'the', 'and', 'for', 'not', 'you', 'all', 'can', 'had', 'her',
    'was', 'one', 'our', 'out', 'new', 'has', 'from', 'this', 'that',
    'with', 'they', 'been', 'have', 'many', 'some', 'them', 'than',
    'its', 'over', 'such', 'into', 'other', 'could', 'will',
    'love', 'hate', 'fire', 'soul', 'mind', 'body', 'heart',
    'time', 'life', 'death', 'dream', 'hope', 'fear',
    # Common German words that KEEP slipping through as "names"
    # (because German capitalizes all nouns)
    'ohne', 'fragen', 'frage', 'antworten', 'schwarze', 'schwarzer',
    'schwarz', 'weiße', 'weißer', 'weiß', 'rote', 'roter', 'rot',
    'blaue', 'blauer', 'blau', 'grüne', 'grüner', 'grün',
    'seide', 'samt', 'wolle', 'stoff', 'leder', 'gold', 'silber',
    'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht',
    'neun', 'zehn', 'hundert', 'tausend', 'million',
    'uhr', 'stunde', 'stunden', 'minute', 'minuten', 'sekunde',
    'montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag',
    'samstag', 'sonntag', 'januar', 'februar', 'märz', 'april',
    'mai', 'juni', 'juli', 'august', 'september', 'oktober',
    'november', 'dezember',
    'ding', 'dinge', 'sache', 'sachen', 'teil', 'teile',
    'recht', 'unrecht', 'pflicht', 'aufgabe', 'aufgaben',
    'punkt', 'punkte', 'liste', 'listen',
    'hallo', 'tschüss', 'danke', 'bitte', 'okay',
    'kapitel', 'absatz', 'zeile', 'seite', 'seiten',
    'beispiel', 'beispiele', 'fall', 'fälle',
    'brief', 'briefe', 'email', 'emails', 'nachricht', 'nachrichten',
    'guten', 'schöne', 'schöner', 'liebe', 'lieber', 'liebes',
    'heute', 'gestern', 'morgen', 'übermorgen', 'vorgestern',
    'nächste', 'letzte', 'vorige', 'kommende',
    'etwas', 'irgendwas', 'irgendwer', 'jemand', 'niemand',
    'zusammen', 'allein', 'gemeinsam', 'getrennt',
    # Plurals / forms that slip through as "surnames"
    'herzen', 'augen', 'händen', 'grüßen', 'grüße', 'worten', 'zeiten',
    'welten', 'träumen', 'schatten', 'flammen', 'sternen', 'wolken',
    # Newsletter / organization patterns that look like names
    'newsletter', 'team', 'redaktion', 'verlag', 'agentur',
    'support', 'service', 'info', 'kontakt', 'admin',
    'petition', 'kampagne', 'aktion', 'bewegung',
    # Possessive constructs "Simons X" / "Vandeloos X" — diary text parsed as names
    'simons', 'vandeloos', 'aileys', 'fabians', 'franzis',
    # Common diary-generated garbage that slipped through before
    'renaissance', 'griffspuren', 'ärmel', 'frust', 'mail',
    'geldbeutel', 'spielzeug', 'geburtstag', 'langweile',
    'anfänger', 'stil', 'backup', 'bar', 'roundtable',
    'detail', 'objekt', 'tool', 'pause', 'stellen',
    'whiskey', 'bolognese', 'neon', 'hollow', 'dreams',
    'punk', 'grrrl', 'eel', 'party', 'exemplar', 'hangul',
    'transformer', 'thinker', 'coder', 'model', 'usern',
    'wetterweisheiten', 'zauberei', 'grenzen', 'lebens',
    # Greeting patterns
    'hey', 'hase', 'schatz', 'süße', 'babe',
    # Cars, games, tech that aren't people
    'dacia', 'logan', 'chess', 'effect',
    # Language names
    'english', 'language', 'korean', 'deutsch', 'french',
    # Generic adjective+noun combos
    'digital', 'person', 'double', 'games', 'creative',
    'artificial', 'city', 'autonome', 'electric', 'object',
    'opening', 'persönliches', 'absoluter', 'relevante',
}


# ══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _slugify(name: str) -> str:
    """Turn a display name into a stable key."""
    s = name.lower().strip()
    s = re.sub(r'[^a-zäöüß0-9]+', '_', s)
    return s.strip('_')[:60]


def _load() -> Dict[str, dict]:
    """Load the entire glossary from disk, migrating old format if needed."""
    if os.path.exists(_GLOSSARY_PATH):
        try:
            with open(_GLOSSARY_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return _migrate_if_needed(data)
        except Exception:
            pass
    return {}


def _migrate_if_needed(data: Dict[str, dict]) -> Dict[str, dict]:
    """Migrate old-format entries (with 'notes', 'topics', 'relation', 'context',
    'sentiment') to new fact-based format.  Also removes garbage entries."""
    changed = False

    # First pass: remove garbage entries
    for pid in list(data.keys()):
        entry = data[pid]
        name = entry.get('name', '')
        if not _is_real_person_name(name):
            del data[pid]
            changed = True
            continue

    # Second pass: migrate schema
    for pid, entry in list(data.items()):
        if 'facts' in entry:
            continue  # Already migrated

        facts: List[Dict[str, Any]] = []
        ts = entry.get('first_seen', time.time())
        src = entry.get('source', 'manual')

        # Migrate 'relation'
        rel = entry.get('relation', '').strip()
        if rel and len(rel) > 3:
            facts.append({"text": rel, "source": src, "ts": ts})

        # Migrate 'context' (skip garbage)
        ctx = (entry.get('context') or '').strip()
        if (ctx and len(ctx) > 5
                and not ctx.startswith('<html')
                and not ctx.startswith('*')
                and 'Wurde im Gespr' not in ctx):
            if not _fact_exists(facts, ctx):
                facts.append({"text": ctx[:300], "source": src, "ts": ts})

        # Migrate 'notes'
        for note in entry.get('notes', []):
            note_clean = note.strip().lstrip('*•- ').strip()
            if (note_clean and len(note_clean) > 3
                    and not note_clean.startswith('<html')):
                if not _fact_exists(facts, note_clean):
                    facts.append({"text": note_clean[:300], "source": src, "ts": ts})

        # Migrate 'topics' as facts
        for topic in entry.get('topics', []):
            tc = topic.strip()
            if tc and len(tc) > 2:
                fact_text = f"Thema: {tc}"
                if not _fact_exists(facts, fact_text):
                    facts.append({"text": fact_text, "source": src, "ts": ts})

        entry['facts'] = facts[:_MAX_FACTS]

        # Remove old fields
        for old_key in ('relation', 'context', 'notes', 'topics', 'sentiment'):
            entry.pop(old_key, None)

        data[pid] = entry
        changed = True

    if changed:
        _save(data)
    return data


def _save(data: Dict[str, dict]):
    """Persist the glossary to disk."""
    os.makedirs(os.path.dirname(_GLOSSARY_PATH), exist_ok=True)
    with open(_GLOSSARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# German noun suffixes — a single word ending in these is almost certainly
# a noun, NOT a person name.  Person names almost never end this way.
_NOUN_SUFFIXES = (
    'ung', 'keit', 'heit', 'nis', 'tion', 'ment', 'schaft',
    'tät', 'ismus', 'enz', 'anz', 'ling', 'chen', 'lein',
    'ität', 'thek', 'logie', 'sophie', 'graphie', 'nomie',
)

# Possessive / article prefixes — if the "name" starts with one of these
# followed by a space, it's not a person.
_POSSESSIVE_PREFIXES = (
    'mein ', 'meine ', 'meiner ', 'meinem ', 'meinen ',
    'dein ', 'deine ', 'deiner ', 'deinem ', 'deinen ',
    'sein ', 'seine ', 'seiner ', 'seinem ', 'seinen ',
    'ihr ', 'ihre ', 'ihrer ', 'ihrem ', 'ihren ',
    'unser ', 'unsere ', 'euer ', 'eure ',
    'der ', 'die ', 'das ', 'den ', 'dem ', 'des ',
    'ein ', 'eine ', 'einem ', 'einen ', 'einer ',
    'kein ', 'keine ', 'keinem ', 'keinen ', 'keiner ',
    'jeder ', 'jede ', 'jedem ', 'jeden ', 'jeder ',
    'dieser ', 'diese ', 'diesem ', 'diesen ', 'dieser ',
    'jener ', 'jene ', 'jenem ', 'jenen ', 'jener ',
    'welcher ', 'welche ', 'welchem ', 'welchen ', 'welcher ',
    'alle ', 'aller ', 'allen ', 'allem ',
    'viele ', 'vieler ', 'vielen ', 'vielem ',
    'einige ', 'einiger ', 'einigen ', 'einigem ',
    'mehrere ', 'mehrerer ', 'mehreren ', 'mehrerem ',
    'the ', 'a ', 'an ', 'my ', 'your ', 'his ', 'her ', 'our ', 'their ',
)


def _is_real_person_name(s: str) -> bool:
    """Strict check: is this plausibly a real person's name?
    In German ALL nouns are capitalized, so we must be very aggressive
    at filtering out non-person nouns.
    """
    if not s or len(s) < 2 or len(s) > 50:
        return False

    s_stripped = s.strip()
    s_low = s_stripped.lower()

    # ── Reject possessive / article prefixes ──────────────────────
    for prefix in _POSSESSIVE_PREFIXES:
        if s_low.startswith(prefix):
            return False

    words = s_stripped.split()
    first_word = words[0]

    # Must start with uppercase
    if not first_word[0].isupper():
        return False
    # No digits
    if re.search(r'\d', first_word):
        return False
    # Not an email address
    if '@' in s:
        return False
    # Not HTML
    if '<' in s or '>' in s:
        return False
    # Not markdown
    if s_stripped.startswith('*') or s_stripped.startswith('-') or s_stripped.startswith('•'):
        return False
    # Not a URL or path
    if '/' in s or '\\' in s or 'http' in s_low:
        return False
    # Not a sentence (no punctuation in person names)
    if any(c in s for c in '.,:;!?()[]{}'):
        return False

    # ── Check EVERY word against stop words (not just first) ──────
    # But skip common surname particles (van, de, von, der, etc.)
    _NAME_PARTICLES = {'van', 'von', 'de', 'den', 'der', 'la', 'le', 'di', 'da',
                       'del', 'el', 'al', 'bin', 'ben', 'ibn', 'mc', 'mac', 'o'}
    # For multi-word names with particles (like "Mai van de Loo"),
    # be lenient about the first word — it could be a legitimate first name
    # even if it matches a common word (e.g., "Mai" = month but also a name)
    has_particles = any(w.lower() in _NAME_PARTICLES for w in words)
    has_capitalized_surname = len(words) >= 3 and any(
        w[0].isupper() and w.lower() not in _NAME_PARTICLES
        and w.lower() not in _NON_PERSON_WORDS and w != words[0]
        for w in words
    )
    for i, w in enumerate(words):
        w_low = w.lower()
        if w_low in _NAME_PARTICLES:
            continue  # legitimate surname particle
        # Skip first-word stop check for names like "Mai van de Loo"
        if i == 0 and has_particles and has_capitalized_surname:
            continue
        if w_low in _NON_PERSON_WORDS:
            return False

    # ── Check full string against stop words ──────────────────────
    if s_low in _NON_PERSON_WORDS:
        return False

    # ── Single-word "names" — extra strict ────────────────────────
    if len(words) == 1:
        w = words[0]
        # Must be >= 3 chars
        if len(w) < 3:
            return False
        # Reject if it ends with a German noun suffix
        w_low = w.lower()
        for suffix in _NOUN_SUFFIXES:
            if w_low.endswith(suffix) and len(w_low) > len(suffix) + 1:
                return False
        # Single-word names are inherently suspicious — must look
        # like a first name (no overly long words, common name length)
        if len(w) > 20:
            return False

    # ── Two-word combos: BOTH significant words must pass ─────────
    significant_words = [w for w in words if w.lower() not in _NAME_PARTICLES]
    if len(significant_words) == 2:
        for w in significant_words:
            w_low = w.lower()
            # Each significant word in a name must start uppercase
            if not w[0].isupper():
                return False
            # Each word must not be a noun-suffix word
            for suffix in _NOUN_SUFFIXES:
                if w_low.endswith(suffix) and len(w_low) > len(suffix) + 1:
                    return False

    # ── More than 5 words = almost certainly not a person name ────
    # (allows for "Sandra van de Loo" etc.)
    if len(words) > 5:
        return False
    # 4-5 words: at least 2 must be capitalized (non-particles)
    if len(words) >= 4:
        capitalized = [w for w in words if w[0].isupper()]
        if len(capitalized) < 2:
            return False

    return True


def _find_person_key(gl: Dict[str, dict], name: str, email: str = "") -> Optional[str]:
    """Find an existing person's key by name, alias, or email."""
    key = _slugify(name)
    nl = name.lower().strip()

    # Direct slug match
    if key in gl:
        return key

    # Name / alias match
    for pid, p in gl.items():
        if nl == p.get('name', '').lower():
            return pid
        if nl in [a.lower() for a in p.get('aliases', [])]:
            return pid

    # Email match
    if email and '@' in email:
        el = email.strip().lower()
        for pid, p in gl.items():
            if p.get('email', '').lower() == el:
                return pid

    return None


def _add_fact_to_entry(entry: dict, text: str, source: str, ts: float):
    """Add a fact to an entry if it's not a duplicate."""
    text = text.strip().lstrip('*•- ').strip()
    if not text or len(text) < 4:
        return
    if text.startswith('<html') or text.startswith('<body'):
        return
    if 'Wurde im Gespr' in text:
        return

    facts = entry.setdefault('facts', [])
    if not _fact_exists(facts, text):
        facts.append({"text": text[:300], "source": source, "ts": ts})
        if len(facts) > _MAX_FACTS:
            entry['facts'] = facts[-_MAX_FACTS:]


def _fact_exists(facts: list, new_text: str) -> bool:
    """Check if a similar fact already exists (fuzzy dedup)."""
    nl = new_text.lower().strip()
    for existing in facts:
        el = (existing['text'].lower().strip()
              if isinstance(existing, dict) else str(existing).lower())
        if nl == el:
            return True
        if len(nl) > 10 and (nl in el or el in nl):
            return True
        nw = set(nl.split())
        ew = set(el.split())
        if len(nw) > 3 and len(ew) > 3:
            if len(nw & ew) / max(len(nw), len(ew)) > 0.75:
                return True
    return False


def _format_person_short(p: dict) -> str:
    """Format a person entry as a compact summary for prompt injection."""
    parts = [f"• {p.get('name', '?')}"]
    if p.get('aliases'):
        parts.append(f"(auch: {', '.join(p['aliases'][:3])})")
    if p.get('email'):
        parts.append(f"[{p['email']}]")
    facts = p.get('facts', [])
    if facts:
        recent = facts[-3:]
        texts = [f['text'][:100] if isinstance(f, dict) else str(f)[:100]
                 for f in recent]
        parts.append(f"– {'; '.join(texts)}")
    # Affinity indicator
    affinity = p.get('affinity', 0.5)
    if affinity >= 0.8:
        parts.append("💚")
    elif affinity >= 0.6:
        parts.append("🤝")
    elif affinity <= 0.2:
        parts.append("💔")
    last = p.get('last_seen', 0)
    if last:
        days_ago = (time.time() - last) / 86400
        if days_ago < 1:
            parts.append("[heute]")
        elif days_ago < 7:
            parts.append(f"[vor {int(days_ago)}d]")
    return " ".join(parts)


def _name_from_email(email: str) -> str:
    """Try to construct a display name from an email local part."""
    local = email.split('@')[0]
    parts = re.split(r'[._\-]', local)
    name_parts = [p.capitalize() for p in parts if len(p) > 1 and p.isalpha()]
    if name_parts:
        candidate = ' '.join(name_parts)
        first = name_parts[0]
        if _is_real_person_name(first):
            return candidate
    return ""


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Lookup
# ══════════════════════════════════════════════════════════════════════════

def get_person(name: str) -> Optional[dict]:
    """Look up a person by name or alias (case-insensitive)."""
    gl = _load()
    key = _slugify(name)
    if key in gl:
        return gl[key]
    nl = name.lower().strip()
    for pid, p in gl.items():
        if nl == p.get('name', '').lower():
            return p
        if nl in [a.lower() for a in p.get('aliases', [])]:
            return p
    return None


def get_person_by_email(email: str) -> Optional[dict]:
    """Look up a person by email address."""
    gl = _load()
    el = email.lower().strip()
    for pid, p in gl.items():
        if p.get('email', '').lower() == el:
            return p
    return None


def list_people(limit: int = 50) -> List[dict]:
    """List all known people, sorted by last_seen descending."""
    gl = _load()
    items = sorted(gl.values(), key=lambda x: x.get('last_seen', 0), reverse=True)
    return items[:limit]


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Create / Update
# ══════════════════════════════════════════════════════════════════════════

def upsert_person(
    name: str,
    email: str = "",
    facts: Optional[List[str]] = None,
    aliases: Optional[List[str]] = None,
    source: str = "chat",
    # Legacy compat - auto-converted to facts
    relation: str = "",
    context: str = "",
    topics: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
    sentiment: str = "",
) -> dict:
    """Create or update a person profile.  Merges new data with existing.

    ``facts`` is a list of atomic fact strings.
    Legacy params (relation, context, topics, notes) are auto-converted.

    Returns the updated profile, or {} if the name is rejected.
    """
    if not _is_real_person_name(name):
        return {}

    gl = _load()
    now = time.time()

    existing_key = _find_person_key(gl, name, email)

    if existing_key:
        entry = gl[existing_key]
    else:
        key = _slugify(name)
        entry = {
            "id": key,
            "name": name.strip(),
            "aliases": [],
            "email": "",
            "facts": [],
            "affinity": 0.5,  # 0.0 = disliked … 0.5 = neutral … 1.0 = loved
            "last_seen": 0,
            "first_seen": now,
            "source": source,
            "interaction_count": 0,
        }
        existing_key = key

    # Email
    if email and '@' in email:
        email_clean = email.strip().lower()
        if not entry.get('email'):
            entry['email'] = email_clean
        elif entry['email'] != email_clean:
            _add_fact_to_entry(entry, f"Auch erreichbar unter: {email_clean}",
                               source, now)

    # Aliases
    cur_aliases = {a.lower() for a in entry.get('aliases', [])}
    name_lower = entry['name'].lower()
    if aliases:
        for a in aliases:
            a_clean = a.strip()
            if (a_clean and len(a_clean) >= 2
                    and a_clean.lower() not in cur_aliases
                    and a_clean.lower() != name_lower):
                entry.setdefault('aliases', []).append(a_clean)
                cur_aliases.add(a_clean.lower())
    # If incoming name differs from stored, add as alias
    incoming_lower = name.strip().lower()
    if incoming_lower != name_lower and incoming_lower not in cur_aliases:
        if len(name.strip()) >= 2:
            entry.setdefault('aliases', []).append(name.strip())
    if len(entry.get('aliases', [])) > _MAX_ALIASES:
        entry['aliases'] = entry['aliases'][-_MAX_ALIASES:]

    # Facts
    if facts:
        for f in facts:
            _add_fact_to_entry(entry, f, source, now)
    # Legacy conversions
    if relation and len(relation.strip()) > 3:
        _add_fact_to_entry(entry, relation[:300], source, now)
    if context and len(context.strip()) > 5:
        ctx = context.strip()
        if not ctx.startswith('<html') and 'Wurde im Gespr' not in ctx:
            _add_fact_to_entry(entry, ctx[:300], source, now)
    if topics:
        for t in topics:
            tc = t.strip()[:80]
            if tc and len(tc) > 2:
                _add_fact_to_entry(entry, f"Thema: {tc}", source, now)
    if notes:
        for n in notes:
            nc = n.strip().lstrip('*•- ').strip()[:300]
            if nc and len(nc) > 3:
                _add_fact_to_entry(entry, nc, source, now)

    entry['last_seen'] = now
    entry['interaction_count'] = entry.get('interaction_count', 0) + 1

    gl[existing_key] = entry
    _save(gl)
    return entry


def add_fact(name: str, fact: str, source: str = "manual") -> bool:
    """Add a single fact to an existing person."""
    gl = _load()
    person = get_person(name)
    if not person:
        return False
    key = person['id']
    _add_fact_to_entry(gl[key], fact.strip()[:300], source, time.time())
    gl[key]['last_seen'] = time.time()
    _save(gl)
    return True


def update_affinity(name: str, delta: float, reason: str = "") -> Optional[float]:
    """Adjust a person's affinity score by delta (clamped 0.0–1.0).

    Positive delta = warmer feelings, negative = cooler.
    Returns the new affinity, or None if person not found.
    """
    gl = _load()
    person = get_person(name)
    if not person:
        return None
    key = person['id']
    old = gl[key].get('affinity', 0.5)
    new_val = max(0.0, min(1.0, old + delta))
    gl[key]['affinity'] = round(new_val, 3)
    if reason:
        _add_fact_to_entry(gl[key], f"Affinität {'+' if delta > 0 else ''}{delta:.2f}: {reason}",
                           "system", time.time())
    _save(gl)
    return new_val


def get_affinity(name: str) -> float:
    """Get a person's affinity score (default 0.5 = neutral)."""
    person = get_person(name)
    if not person:
        return 0.5
    return person.get('affinity', 0.5)


# Legacy compat wrappers
def add_note(name: str, note: str) -> bool:
    """Legacy: add a note (stored as a fact)."""
    return add_fact(name, note, source="manual")


def update_relation(name: str, relation: str) -> bool:
    """Update the relation (stored as a fact)."""
    return add_fact(name, relation, source="manual")


def delete_person(name: str) -> bool:
    """Remove a person from the glossary."""
    gl = _load()
    person = get_person(name)
    if not person:
        return False
    del gl[person['id']]
    _save(gl)
    return True


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Context Building
# ══════════════════════════════════════════════════════════════════════════

def build_glossary_context(
    names: Optional[List[str]] = None, max_chars: int = 1200
) -> str:
    """Build a prompt-injectable context string about known people.

    If names is given, include DETAILED per-person chunks for those people.
    Otherwise include compact summaries of most recent contacts.
    """
    gl = _load()
    if not gl:
        return ""

    if names:
        # Specific people mentioned — use detailed chunked context
        parts = []
        total = 0
        for n in names:
            ctx = get_person_context(n, max_facts=8)
            if ctx:
                if total + len(ctx) > max_chars:
                    break
                parts.append(ctx)
                total += len(ctx) + 1
        if not parts:
            return ""
        return "BEKANNTE PERSONEN (Details):\n" + "\n\n".join(parts)
    else:
        # No specific mention → compact overview of recent contacts
        entries = sorted(gl.values(),
                         key=lambda x: x.get('last_seen', 0), reverse=True)
        parts = []
        total = 0
        for p in entries:
            line = _format_person_short(p)
            if total + len(line) > max_chars:
                break
            parts.append(line)
            total += len(line) + 1

        if not parts:
            return ""
        return "BEKANNTE PERSONEN:\n" + "\n".join(parts)


def get_person_context(name: str, max_facts: int = 15) -> str:
    """Get detailed, categorized context string for a specific person.

    Facts are chunked into categories so Ailey can quickly find
    the relevant context she needs.
    """
    person = get_person(name)
    if not person:
        return ""

    parts = [f"═══ {person['name']} ═══"]
    if person.get('email'):
        parts.append(f"📧 {person['email']}")
    if person.get('aliases'):
        parts.append(f"Auch bekannt als: {', '.join(person['aliases'])}")
    # Extended contact / profile fields
    if person.get('phone'):
        parts.append(f"📞 Telefon: {person['phone']}")
    if person.get('birthday'):
        parts.append(f"🎂 Geburtstag: {person['birthday']}")
    if person.get('address'):
        parts.append(f"🏠 Adresse: {person['address']}")
    if person.get('occupation'):
        parts.append(f"💼 Beruf: {person['occupation']}")
    if person.get('company'):
        parts.append(f"🏢 Firma: {person['company']}")
    # Affinity display
    affinity = person.get('affinity', 0.5)
    _AFFINITY_LABELS = [
        (0.9, "💚 Sehr eng / geliebt"),
        (0.7, "🤝 Positiv / freundlich"),
        (0.5, "😐 Neutral"),
        (0.3, "😕 Distanziert"),
        (0.0, "💔 Schwierig"),
    ]
    for threshold, label in _AFFINITY_LABELS:
        if affinity >= threshold:
            parts.append(f"Beziehung: {label} ({affinity:.1f})")
            break

    facts = person.get('facts', [])
    if not facts:
        return "\n".join(parts)

    # Categorize facts
    categories: Dict[str, List[str]] = {
        'beziehung': [],      # relationship to Simon
        'beruf': [],          # job / professional
        'persönlich': [],     # personal traits, preferences
        'kontakt': [],        # contact info, email
        'themen': [],         # topics discussed
        'sonstiges': [],      # everything else
    }

    _RELATION_KEYS = {'freund', 'partner', 'kollege', 'kollegin', 'chef',
                      'schwester', 'bruder', 'mutter', 'vater', 'beziehung',
                      'verhältnis', 'kennt', 'bekannt', 'verwandt'}
    _BERUF_KEYS = {'arbeit', 'beruf', 'job', 'firma', 'unternehmen', 'agentur',
                   'projekt', 'rolle', 'position', 'geschäftsführ', 'entwickl',
                   'design', 'marketing'}
    _KONTAKT_KEYS = {'email', 'telefon', 'nummer', 'adresse', 'erreichbar',
                     '@', 'whatsapp', 'signal'}
    _THEMA_KEYS = {'thema:', 'gesprochen über', 'diskutiert', 'unterhalten über'}

    recent = facts[-max_facts:]
    for f in recent:
        text = f['text'] if isinstance(f, dict) else str(f)
        text_low = text.lower()

        if any(k in text_low for k in _KONTAKT_KEYS):
            categories['kontakt'].append(text)
        elif any(k in text_low for k in _RELATION_KEYS):
            categories['beziehung'].append(text)
        elif any(k in text_low for k in _BERUF_KEYS):
            categories['beruf'].append(text)
        elif any(k in text_low for k in _THEMA_KEYS):
            categories['themen'].append(text)
        elif any(k in text_low for k in ('mag', 'liebt', 'hasst', 'hobby',
                                          'charakter', 'persönlich', 'eigenschaft')):
            categories['persönlich'].append(text)
        else:
            categories['sonstiges'].append(text)

    # Build output — only include non-empty categories
    _CAT_LABELS = {
        'beziehung': '🤝 Beziehung',
        'beruf': '💼 Beruf',
        'persönlich': '🧑 Persönliches',
        'kontakt': '📱 Kontakt',
        'themen': '💬 Themen',
        'sonstiges': '📝 Notizen',
    }
    for cat_key in ('beziehung', 'beruf', 'persönlich', 'kontakt', 'themen', 'sonstiges'):
        items = categories[cat_key]
        if items:
            parts.append(f"{_CAT_LABELS[cat_key]}:")
            for item in items:
                parts.append(f"  - {item[:200]}")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Search / Mention Detection
# ══════════════════════════════════════════════════════════════════════════

def find_mentioned_people(text: str) -> List[dict]:
    """Scan text for mentions of known people.  Returns matching profiles."""
    gl = _load()
    if not gl:
        return []
    text_lower = text.lower()
    found = []
    seen_ids: set = set()
    for pid, p in gl.items():
        # Check full name
        pname = p.get('name', '').lower()
        if pname and len(pname) >= 3 and pname in text_lower:
            if pid not in seen_ids:
                found.append(p)
                seen_ids.add(pid)
                continue
        # Check aliases (word-boundary match, min 3 chars)
        for alias in p.get('aliases', []):
            al = alias.lower()
            if len(al) < 3:
                continue
            if al in text_lower:
                pat = r'\b' + re.escape(al) + r'\b'
                if re.search(pat, text_lower):
                    if pid not in seen_ids:
                        found.append(p)
                        seen_ids.add(pid)
                        break
    return found


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Auto-extraction helpers
# ══════════════════════════════════════════════════════════════════════════

def extract_people_from_text(text: str, source: str = "chat") -> List[str]:
    """Extract potential person names from text using STRICT heuristics.

    Returns candidate name strings.  The caller decides whether to create entries.
    Only returns names that are very likely real people.
    """
    names: set = set()

    # Pattern 1: explicit relationship introductions
    # "meine Freundin heisst Lisa" / "mein Kollege ist Max Mueller"
    rel_pat = (
        r"(?:mein(?:e)?|sein(?:e)?|ihr(?:e)?)\s+"
        r"(?:freund(?:in)?|partner(?:in)?|frau|mann|mutter|vater|"
        r"bruder|schwester|tochter|sohn|kind|onkel|tante|oma|opa|"
        r"kollege|kollegin|chef(?:in)?|mitbewohner(?:in)?|nachbar(?:in)?)"
        r"\s+(?:hei(?:ss|ß)t|ist|namens)\s+"
        r"([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)"
    )
    for m in re.finditer(rel_pat, text):
        candidate = m.group(1).strip()
        if _is_real_person_name(candidate):
            names.add(candidate)

    # Pattern 2: Full names (First Last) - two capitalized words in a row
    full_name_pat = r'\b([A-ZÄÖÜ][a-zäöüß]{2,15})\s+([A-ZÄÖÜ][a-zäöüß]{2,20})\b'
    for m in re.finditer(full_name_pat, text):
        first, last = m.group(1), m.group(2)
        full = f"{first} {last}"
        if _is_real_person_name(first) and _is_real_person_name(last):
            names.add(full)

    return list(names)


def extract_person_from_email(
    sender: str, subject: str = "", body: str = ""
) -> dict:
    """Extract person info from an email sender field.

    Returns dict with keys: name, email, facts
    """
    info: Dict[str, Any] = {"name": "", "email": "", "facts": []}

    # Parse "Name <email>" or bare email
    m = re.match(r'^(.+?)\s*<(.+?)>', sender)
    if m:
        raw_name = m.group(1).strip().strip('"\'')
        info["email"] = m.group(2).strip().lower()
        if '@' not in raw_name and _is_real_person_name(
                raw_name.split()[0] if raw_name.split() else ''):
            info["name"] = raw_name
        else:
            info["name"] = _name_from_email(info["email"])
    elif '@' in sender:
        info["email"] = sender.strip().lower()
        info["name"] = _name_from_email(info["email"])
    else:
        raw = sender.strip()
        if _is_real_person_name(raw.split()[0] if raw.split() else ''):
            info["name"] = raw

    # Subject -> fact
    if subject and len(subject) > 3:
        info["facts"].append(f"Email-Betreff: {subject[:80]}")

    return info


# ══════════════════════════════════════════════════════════════════════════
#  PUBLIC API — Merge & Consolidation
# ══════════════════════════════════════════════════════════════════════════

def merge_persons(source_name: str, target_name: str) -> bool:
    """Merge source person INTO target. All facts/aliases move to target.
    Source entry is deleted."""
    gl = _load()
    source = get_person(source_name)
    target = get_person(target_name)
    if not source or not target or source['id'] == target['id']:
        return False

    t = gl[target['id']]

    # Move source name + aliases to target aliases
    t_aliases = {a.lower() for a in t.get('aliases', [])}
    t_name_lower = t['name'].lower()
    if source['name'].lower() not in t_aliases and source['name'].lower() != t_name_lower:
        t.setdefault('aliases', []).append(source['name'])
    for a in source.get('aliases', []):
        if a.lower() not in t_aliases and a.lower() != t_name_lower:
            t.setdefault('aliases', []).append(a)

    # Move facts
    for fact in source.get('facts', []):
        if not _fact_exists(t.get('facts', []), fact['text']):
            t.setdefault('facts', []).append(fact)

    # Move email
    if source.get('email') and not t.get('email'):
        t['email'] = source['email']
    elif source.get('email') and t.get('email') and source['email'] != t['email']:
        _add_fact_to_entry(t, f"Auch erreichbar unter: {source['email']}",
                           "merge", time.time())

    # Timestamps
    t['first_seen'] = min(t.get('first_seen', time.time()),
                          source.get('first_seen', time.time()))
    t['last_seen'] = max(t.get('last_seen', 0), source.get('last_seen', 0))
    t['interaction_count'] = (t.get('interaction_count', 0)
                              + source.get('interaction_count', 0))

    # Cap
    if len(t.get('facts', [])) > _MAX_FACTS:
        t['facts'] = t['facts'][-_MAX_FACTS:]
    if len(t.get('aliases', [])) > _MAX_ALIASES:
        t['aliases'] = t['aliases'][-_MAX_ALIASES:]

    gl[target['id']] = t
    del gl[source['id']]
    _save(gl)
    return True


def _nitro_is_real_person(name: str, entry: dict) -> Optional[bool]:
    """Ask AileyNitro-2B whether an entry is a real person.

    Returns True/False, or None if Nitro is unavailable / answer unparseable.
    Uses short, strict JA/NEIN classification prompt.
    """
    try:
        from .llm_mlx import fast_generate, is_fast_available
        if not is_fast_available():
            return None
    except Exception:
        return None

    # Collect light context the model can use
    aliases = entry.get('aliases') or []
    email = entry.get('email') or ''
    facts = entry.get('facts') or []
    fact_texts = []
    for f in facts[:5]:
        if isinstance(f, dict):
            t = (f.get('text') or '').strip()
            if t:
                fact_texts.append(t[:160])
        elif isinstance(f, str):
            fact_texts.append(f[:160])

    ctx_lines = [f"NAME: {name}"]
    if aliases:
        ctx_lines.append(f"ALIASES: {', '.join(str(a) for a in aliases[:6])}")
    if email:
        ctx_lines.append(f"EMAIL: {email}")
    if fact_texts:
        ctx_lines.append("FAKTEN:\n- " + "\n- ".join(fact_texts))

    system = (
        "Du bist ein Glossar-Validator. Entscheide, ob ein Eintrag eine "
        "ECHTE oder plausible PERSON (Mensch ODER benannte Figur) beschreibt.\n\n"
        "WICHTIG — Antworte IM ZWEIFEL IMMER mit JA. Nur klar offensichtliche "
        "Nicht-Personen bekommen NEIN.\n\n"
        "JA (Person) bei:\n"
        "- Allen realen Vornamen, Nachnamen, Vor+Nachname-Kombinationen "
        "(z.B. 'Jason', 'Sabrina', 'Horst', 'Gandalf', 'Izzy', 'Antje Kluthe', "
        "'Thorsten Dollmetsch', 'Richter Manuel', 'Evelyn River').\n"
        "- Auch bei ungewöhnlichen / seltenen / erfundenen Namen, solange sie "
        "wie ein Name klingen (z.B. 'Echora', 'Gelka Finch', 'Kaya').\n"
        "- Prominente / fiktive Figuren mit Eigennamen (z.B. 'Miley Cyrus').\n"
        "- Aliase / Nicknames / Spitznamen zählen auch als Person.\n\n"
        "NEIN (keine Person) NUR bei:\n"
        "- Phrasen/Sätzen statt Namen ('Mehr Kuscheln', 'Altes Sex', 'Mit Launen', "
        "'Round Two', 'Kurzer Flip', 'Direkter Gegenentwurf', 'Auf Spanisch').\n"
        "- Firmen-/Produkt-/Newsletter-Labels ('MyHeritage News', 'Napkin AI', "
        "'Clever Fit', 'CLINIC DRESS', 'Adventure Soundtrack').\n"
        "- Orten ('Bad Neuenahr', 'Puritanus Cathedral').\n"
        "- Abstrakten Konzepten ('Gott', 'Algorithmische Anpassungen').\n"
        "- Buch-/Song-/Album-Titeln.\n\n"
        "Antworte NUR mit einem einzigen Wort: JA oder NEIN."
    )
    user = "Ist folgender Eintrag eine echte Person?\n\n" + "\n".join(ctx_lines)

    try:
        out = fast_generate(
            system=system, user=user,
            max_tokens=8, temperature=0.0, priming_turns=None,
        )
    except Exception:
        return None
    if not out:
        return None
    txt = out.strip().upper()
    # Strip punctuation/markup
    txt = re.sub(r'[^A-ZÄÖÜ]+', ' ', txt).strip()
    if txt.startswith("JA") or txt == "YES":
        return True
    if txt.startswith("NEIN") or txt == "NO":
        return False
    # Fallback: look anywhere
    if "NEIN" in txt and "JA" not in txt:
        return False
    if "JA" in txt and "NEIN" not in txt:
        return True
    return None


def cleanup_glossary(use_llm: bool = True) -> Dict[str, Any]:
    """Flag suspicious glossary entries for review (NON-destructive).

    We don't auto-delete anymore — Nitro is too unreliable at telling German
    noun-phrases from uncommon names. Instead, entries that look fishy get
    tagged with `review_flag`, and the user can bulk-purge them later via
    `purge_flagged_entries()` (or un-flag individual ones via
    `clear_review_flag()`).

    Validation order:
      1. Heuristic `_is_real_person_name` — fast obvious rejects.
      2. AileyNitro-2B confirms/overrules when available.
      3. If Nitro is unavailable, only heuristic-fails get flagged.

    Rules (always non-destructive):
      - Nitro NEIN               → FLAG (reason='nitro_nein')
      - Heuristic fail + no Nitro → FLAG (reason='heuristic_fail')
      - Nitro JA                 → CLEAR existing flag (rehabilitated)
      - Owner entries are never flagged.

    Returns stats about what was flagged / cleared.
    """
    gl = _load()
    flagged_now: List[str] = []          # newly tagged this run
    cleared_now: List[str] = []          # had a flag, Nitro said JA now
    already_flagged: List[str] = []      # carried over from previous run
    llm_errors = 0
    now = time.time()

    for pid in list(gl.keys()):
        entry = gl[pid]
        name = entry.get('name', '')
        if entry.get('is_owner'):
            continue  # never touch owner

        heuristic_ok = _is_real_person_name(name)
        nitro_verdict: Optional[bool] = None
        if use_llm:
            nitro_verdict = _nitro_is_real_person(name, entry)
            if nitro_verdict is None:
                llm_errors += 1

        had_flag = bool(entry.get('review_flag'))

        # --- Decide ---
        flag_reason: Optional[str] = None
        if nitro_verdict is False:
            flag_reason = 'nitro_nein'
        elif nitro_verdict is True:
            # Nitro positively confirms → clear any previous flag
            if had_flag:
                entry.pop('review_flag', None)
                cleared_now.append(name)
            continue
        else:
            # Nitro unavailable or unparseable
            if not heuristic_ok:
                flag_reason = 'heuristic_fail'

        if flag_reason:
            if had_flag:
                already_flagged.append(name)
            else:
                flagged_now.append(name)
            entry['review_flag'] = {
                'reason': flag_reason,
                'validator': 'Nitro-2B' if flag_reason == 'nitro_nein' else 'Heuristik',
                'ts': now,
            }

    _save(gl)
    # stats
    total_flagged = sum(1 for e in gl.values() if e.get('review_flag'))
    return {
        "flagged_now": flagged_now,
        "cleared_now": cleared_now,
        "already_flagged": already_flagged,
        "total_flagged": total_flagged,
        "remaining": len(gl),
        "llm_used": use_llm,
        "llm_unavailable_count": llm_errors,
    }


def purge_flagged_entries() -> Dict[str, Any]:
    """Delete all glossary entries that carry a `review_flag`.

    Returns the list of names that were removed and the new total count.
    """
    gl = _load()
    removed: List[str] = []
    for pid in list(gl.keys()):
        entry = gl[pid]
        if entry.get('is_owner'):
            continue
        if entry.get('review_flag'):
            removed.append(entry.get('name', pid))
            del gl[pid]
    if removed:
        _save(gl)
    return {"removed": removed, "count": len(removed), "remaining": len(gl)}


def clear_review_flag(name: str) -> bool:
    """Remove the review_flag from a single entry ('doch eine Person')."""
    gl = _load()
    person = get_person(name)
    if not person:
        return False
    pid = person['id']
    if gl[pid].pop('review_flag', None) is not None:
        _save(gl)
        return True
    return False
