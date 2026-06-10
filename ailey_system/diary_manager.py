# -*- coding: utf-8 -*-
"""
Hierarchical diary manager for Ailey.

Storage hierarchy (automatic consolidation):
  Day   → 1 entry per calendar day (max)
  Week  → Sundays: merge 7 day-entries into 1 weekly digest, delete originals
  Month → 1st of month: merge ~4 weekly digests into 1 monthly digest
  Year  → Jan 1: merge 12 monthly digests into 1 yearly entry
  5yr   → Every 5 years: merge yearly entries into a 5-year block

User diary entries are stored under `ailey_users/{user}_profile/diary/`.
Supports password protection (PBKDF2) and RAG ingestion via core.rag_add.
"""
import os
import json
import hashlib
import secrets
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DIARY_FOLDER = "diary"
PASSWORD_FILENAME = "_diary_pass.hash"
PBKDF2_ITER = 150_000
PBKDF2_SALT_BYTES = 16

# Entry level tags for hierarchical consolidation
LEVEL_DAY = "day"
LEVEL_WEEK = "week"
LEVEL_MONTH = "month"
LEVEL_YEAR = "year"
LEVEL_5YEAR = "5year"


def _user_dir(user: str) -> str:
    # Prefer exact-case match if it already exists (e.g. "Simon_profile")
    # Fall back to lowercase to avoid creating a duplicate shadow folder.
    base_lower = os.path.join("ailey_users", f"{user.lower()}_profile")
    base_exact = os.path.join("ailey_users", f"{user}_profile")
    if os.path.isdir(base_exact):
        return base_exact
    os.makedirs(base_lower, exist_ok=True)
    return base_lower


def _diary_dir(user: str) -> str:
    d = os.path.join(_user_dir(user), DIARY_FOLDER)
    os.makedirs(d, exist_ok=True)
    return d


def _hash_pw_sha256(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()


def _hash_pw_pbkdf2(pw: str, salt: bytes = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def set_password(user: str, password: str):
    """Set diary password — stores PBKDF2 hash with salt and iterations."""
    path = os.path.join(_user_dir(user), PASSWORD_FILENAME)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_hash_pw_pbkdf2(password))


def verify_password(user: str, password: str) -> bool:
    """Verify password. Supports legacy SHA256 hashes by migrating them to PBKDF2 on successful check."""
    path = os.path.join(_user_dir(user), PASSWORD_FILENAME)
    if not os.path.exists(path):
        return False
    with open(path, 'r', encoding='utf-8') as f:
        stored = f.read().strip()
    # Legacy SHA256 hex (64 chars)
    if stored and len(stored) == 64 and all(c in '0123456789abcdef' for c in stored.lower()):
        # verify legacy
        if stored == _hash_pw_sha256(password):
            # migrate to pbkdf2
            try:
                with open(path, 'w', encoding='utf-8') as fw:
                    fw.write(_hash_pw_pbkdf2(password))
            except Exception:
                pass
            return True
        return False
    # PBKDF2 format: pbkdf2_sha256$iter$salthex$dkhex
    if stored.startswith('pbkdf2_sha256$'):
        try:
            parts = stored.split('$')
            if len(parts) != 4:
                return False
            it = int(parts[1])
            salt = bytes.fromhex(parts[2])
            dk = bytes.fromhex(parts[3])
            check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, it)
            return secrets.compare_digest(check, dk)
        except Exception:
            return False
    return False


def save_entry(user: str, title: str, content: str, tags: Optional[List[str]] = None, private: bool = True) -> Dict:
    d = _diary_dir(user)
    ts = int(datetime.utcnow().timestamp())
    filename = f"entry_{ts}.json"
    data = {
        'title': title,
        'content': content,
        'tags': tags or [],
        'private': bool(private),
        'ts': ts,
        'dt': datetime.utcnow().isoformat() + 'Z',
        'level': LEVEL_DAY,
    }
    path = os.path.join(d, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {'success': True, 'path': path, 'entry': data}


def list_entries(user: str) -> List[Dict]:
    out = []
    seen = set()
    for d in _all_diary_dirs(user):
        files = sorted([f for f in os.listdir(d) if f.endswith('.json')])
        for fn in reversed(files):
            path = os.path.join(d, fn)
            if path in seen:
                continue
            seen.add(path)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    j = json.load(f)
                # Support both new format (ts/dt) and legacy format (timestamp/date_readable/text)
                ts = j.get('ts') or j.get('timestamp')
                if ts and ts > 1e10:
                    ts = ts / 1000  # ms → s
                dt = j.get('dt') or j.get('date_readable', '')
                title = j.get('title') or j.get('type', 'Tagebucheintrag')
                out.append({
                    'id': fn, 'title': title, 'ts': ts,
                    'dt': dt, 'tags': j.get('tags', []),
                    'private': j.get('private', True),
                    'level': j.get('level', LEVEL_DAY),
                })
            except Exception:
                continue
    # Sort newest first
    out.sort(key=lambda x: (x.get('ts') or 0), reverse=True)
    return out


def read_entry(user: str, entry_id: str) -> Optional[Dict]:
    for d in _all_diary_dirs(user):
        path = os.path.join(d, entry_id)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
    return None


# ---------------------------------------------------------------------------
# Hierarchical Diary — Guards & Consolidation
# ---------------------------------------------------------------------------

def _all_diary_dirs(user: str) -> list:
    """Return all dirs that may contain *user* diary entries.
    Only 'diary/' is included — 'diaries/' is reserved for Ailey's
    auto-generated reflections and must NOT bleed into the user's tab."""
    udir = _user_dir(user)
    dirs = []
    p = os.path.join(udir, DIARY_FOLDER)
    if os.path.isdir(p):
        dirs.append(p)
    if not dirs:
        # ensure at least the canonical one exists
        p = os.path.join(udir, DIARY_FOLDER)
        os.makedirs(p, exist_ok=True)
        dirs.append(p)
    return dirs


def diary_written_today(user: str = "Simon") -> bool:
    """Check if a day-level diary entry already exists for today (UTC)."""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    for d in _all_diary_dirs(user):
        for fn in os.listdir(d):
            if not fn.endswith('.json'):
                continue
            path = os.path.join(d, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    j = json.load(f)
                level = j.get('level', LEVEL_DAY)
                if level != LEVEL_DAY:
                    continue
                dt_str = j.get('dt', '')
                if dt_str[:10] == today_str:
                    return True
                # Fallback: check ts / legacy timestamp (may be ms or s)
                ts = j.get('ts') or j.get('timestamp', 0)
                if ts and ts > 1e10:
                    ts = ts / 1000
                if ts > 0:
                    entry_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    if entry_date == today_str:
                        return True
            except Exception:
                continue
    return False


def _entries_by_level(user: str, level: str) -> List[Dict]:
    """Return all entries at a given level, sorted by ts ascending (scans all diary dirs)."""
    out = []
    for d in _all_diary_dirs(user):
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.json'):
                continue
            path = os.path.join(d, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    j = json.load(f)
                if j.get('level', LEVEL_DAY) == level:
                    j['_file'] = fn
                    j['_path'] = path
                    out.append(j)
            except Exception:
                continue
    # Sort by ts, dedup by path
    seen = set()
    deduped = []
    for e in sorted(out, key=lambda x: x.get('ts', 0)):
        if e['_path'] not in seen:
            seen.add(e['_path'])
            deduped.append(e)
    return deduped


def _delete_entries(entries: List[Dict]):
    """Delete entry files from disk."""
    for e in entries:
        p = e.get('_path', '')
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass


def _iso_week(dt: datetime) -> str:
    """Return ISO week string like '2026-W14'."""
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


def _iso_month(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def consolidate_if_due(user: str = "Simon", generator=None) -> List[str]:
    """Check and run any overdue consolidation merges.

    Called on startup and periodically. Handles:
    - Weekly merge (due on Sundays or catch-up if missed)
    - Monthly merge (due on 1st or catch-up)
    - Yearly merge (due on Jan 1 or catch-up)
    - 5-year merge

    Returns list of actions taken (for logging).
    """
    actions = []
    now = datetime.utcnow()

    # ── Weekly: merge day-entries older than current week into weekly digests ──
    day_entries = _entries_by_level(user, LEVEL_DAY)
    current_week = _iso_week(now)
    # Group old day entries by their ISO week
    weeks_to_merge: Dict[str, List[Dict]] = {}
    for e in day_entries:
        ts = e.get('ts', 0)
        if ts <= 0:
            continue
        edt = datetime.utcfromtimestamp(ts)
        ew = _iso_week(edt)
        if ew != current_week:  # Not current week → eligible for merge
            weeks_to_merge.setdefault(ew, []).append(e)

    for week_key, entries in sorted(weeks_to_merge.items()):
        if len(entries) < 1:
            continue
        merged_text = _merge_entries_text(entries, generator,
                                          f"Wochen-Zusammenfassung ({week_key})")
        ts_min = min(e.get('ts', 0) for e in entries)
        ts_max = max(e.get('ts', 0) for e in entries)
        save_consolidated(user, merged_text, LEVEL_WEEK,
                          title=f"Woche {week_key}",
                          ts_range=(ts_min, ts_max),
                          tags=[f"week:{week_key}"])
        _delete_entries(entries)
        actions.append(f"weekly_merge:{week_key}({len(entries)} days)")

    # ── Monthly: merge week-entries older than current month ──
    week_entries = _entries_by_level(user, LEVEL_WEEK)
    current_month = _iso_month(now)
    months_to_merge: Dict[str, List[Dict]] = {}
    for e in week_entries:
        ts = e.get('ts', 0)
        if ts <= 0:
            continue
        edt = datetime.utcfromtimestamp(ts)
        em = _iso_month(edt)
        if em != current_month:
            months_to_merge.setdefault(em, []).append(e)

    for month_key, entries in sorted(months_to_merge.items()):
        if len(entries) < 1:
            continue
        merged_text = _merge_entries_text(entries, generator,
                                          f"Monats-Zusammenfassung ({month_key})")
        ts_min = min(e.get('ts', 0) for e in entries)
        ts_max = max(e.get('ts', 0) for e in entries)
        save_consolidated(user, merged_text, LEVEL_MONTH,
                          title=f"Monat {month_key}",
                          ts_range=(ts_min, ts_max),
                          tags=[f"month:{month_key}"])
        _delete_entries(entries)
        actions.append(f"monthly_merge:{month_key}({len(entries)} weeks)")

    # ── Yearly: merge month-entries from completed years ──
    month_entries = _entries_by_level(user, LEVEL_MONTH)
    current_year = str(now.year)
    years_to_merge: Dict[str, List[Dict]] = {}
    for e in month_entries:
        ts = e.get('ts', 0)
        if ts <= 0:
            continue
        edt = datetime.utcfromtimestamp(ts)
        ey = str(edt.year)
        if ey != current_year:
            years_to_merge.setdefault(ey, []).append(e)

    for year_key, entries in sorted(years_to_merge.items()):
        if len(entries) < 1:
            continue
        merged_text = _merge_entries_text(entries, generator,
                                          f"Jahres-Zusammenfassung ({year_key})")
        ts_min = min(e.get('ts', 0) for e in entries)
        ts_max = max(e.get('ts', 0) for e in entries)
        save_consolidated(user, merged_text, LEVEL_YEAR,
                          title=f"Jahr {year_key}",
                          ts_range=(ts_min, ts_max),
                          tags=[f"year:{year_key}"])
        _delete_entries(entries)
        actions.append(f"yearly_merge:{year_key}({len(entries)} months)")

    # ── 5-Year: merge year-entries into 5-year blocks (after 5 years exist) ──
    year_entries = _entries_by_level(user, LEVEL_YEAR)
    if len(year_entries) >= 5:
        # Sort by ts, take the oldest 5
        year_entries.sort(key=lambda e: e.get('ts', 0))
        batch = year_entries[:5]
        merged_text = _merge_entries_text(batch, generator,
                                          "5-Jahres-Zusammenfassung")
        ts_min = min(e.get('ts', 0) for e in batch)
        ts_max = max(e.get('ts', 0) for e in batch)
        save_consolidated(user, merged_text, LEVEL_5YEAR,
                          title=f"5 Jahre ({datetime.utcfromtimestamp(ts_min).year}–{datetime.utcfromtimestamp(ts_max).year})",
                          ts_range=(ts_min, ts_max),
                          tags=["5year_block"])
        _delete_entries(batch)
        actions.append(f"5year_merge({len(batch)} years)")

    if actions:
        print(f"[DiaryManager] 📔 Consolidation: {', '.join(actions)}")
    return actions


def save_consolidated(user: str, content: str, level: str,
                      title: str = "", ts_range: tuple = None,
                      tags: Optional[List[str]] = None) -> Dict:
    """Save a consolidated diary entry at the given hierarchy level."""
    d = _diary_dir(user)
    ts = int(ts_range[1] if ts_range else time.time())
    filename = f"{level}_{ts}.json"
    data = {
        'title': title,
        'content': content,
        'tags': tags or [],
        'private': True,
        'ts': ts,
        'ts_start': int(ts_range[0]) if ts_range else ts,
        'ts_end': int(ts_range[1]) if ts_range else ts,
        'dt': datetime.utcfromtimestamp(ts).isoformat() + 'Z',
        'level': level,
    }
    path = os.path.join(d, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {'success': True, 'path': path, 'entry': data}


def _merge_entries_text(entries: List[Dict], generator=None, header: str = "") -> str:
    """Merge multiple diary entries into one text.

    If generator (LLM) is available, use it for intelligent summarization.
    Otherwise, concatenate with date headers.
    """
    # Build dated source text
    parts = []
    for e in sorted(entries, key=lambda x: x.get('ts', 0)):
        ts = e.get('ts', 0)
        date_str = datetime.utcfromtimestamp(ts).strftime('%d.%m.%Y') if ts else '?'
        title = e.get('title', '')
        content = e.get('content', '')
        text = f"[{date_str}] {title}\n{content}" if content else f"[{date_str}] {title}"
        parts.append(text.strip())
    combined = "\n\n---\n\n".join(parts)

    if generator and len(combined) > 100:
        try:
            system = (
                "Du bist Ailey und fasst deine eigenen Tagebucheinträge zusammen. "
                "Behalte die wichtigsten Emotionen, Fakten, Personen und Erkenntnisse. "
                "Entferne Wiederholungen und Banalitäten. "
                "Schreibe in deinem Stil — punky, direkt, ehrlich. Fließtext. "
                "Beginne mit einer kurzen Zeitlinie der wichtigsten Ereignisse. "
                "Max 1500 Zeichen."
            )
            user_prompt = f"{header}\n\nFasse diese Einträge zusammen:\n\n{combined[:5000]}"
            raw = generator.generate(system, user_prompt,
                                     {"max_tokens": 600, "temperature": 0.7})
            if raw and len(raw.strip()) > 50:
                return raw.strip()
        except Exception as e:
            print(f"[DiaryManager] ⚠️ LLM merge failed: {e}")

    # Fallback: just concatenate
    return f"**{header}**\n\n{combined[:3000]}"
