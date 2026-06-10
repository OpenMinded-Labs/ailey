"""
Ailey Cloud Backup -- 3-Tier Strategy
======================================

Tier 1 - NIGHTLY (DB only, fast):
  Every night 02:00-04:00 via IdleThinker.
  Items: ailey_system/lancedb, ailey_system/chromadb
  Target: iCloud + Google Drive
  Rotation: keep last 7

Tier 2 - BI-MONTHLY FULL (everything):
  Twice per month: day 1-3 AND day 15-18, between 23:00-04:00.
  Items: ailey_users, ailey_system/lancedb, ailey_system/chromadb,
         ailey_config.json, portal
  Target: Google Drive (gdrive:Ailey-Backups/full/)
  Rotation: keep last 4

Both tiers are called from IdleThinker via execute_nightly_backup().
On failure: email notification to Simon with logs.
"""
import os
import subprocess
import time
import json
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

# -- Paths ----------------------------------------------------------------
_AILEY_ROOT = Path(__file__).resolve().parent.parent
_ICLOUD_ROOT = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
_ICLOUD_BACKUP_DIR = _ICLOUD_ROOT / "Ailey-Backups" / "nightly"
_GDRIVE_NIGHTLY = "gdrive:Ailey-Backups/nightly"
_GDRIVE_FULL = "gdrive:Ailey-Backups/full"
_LOCAL_TMP = _AILEY_ROOT / ".backup_tmp"

# -- Tier 1: DB only (nightly) -------------------------------------------
_DB_ITEMS = [
    "ailey_system/lancedb",
    "ailey_system/chromadb",
]

# -- Tier 2: Full (bi-monthly) -------------------------------------------
_FULL_ITEMS = [
    "ailey_users",
    "ailey_system/lancedb",
    "ailey_system/chromadb",
    "ailey_config.json",
    "portal",
]

_EXCLUDE_PATTERNS = [
    "__pycache__", ".DS_Store", "*.pyc", "*.tmp", "*.lock",
    ".AppleDouble", "._*",
]

_MAX_NIGHTLY = 7
_MAX_FULL = 4
_STATE_FILE = _AILEY_ROOT / "ailey_users" / ".backup_state.json"
_SIMON_EMAIL = "simonvandeloo36@gmail.com"


# -- State ----------------------------------------------------------------
def _load_state():
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state):
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


# -- Schedule checks ------------------------------------------------------
def _is_nightly_window():
    """02:00 - 04:00"""
    h = datetime.now().hour
    return 2 <= h <= 4


def _is_full_backup_window():
    """Day 1-3 or 15-18, between 23:00-04:00"""
    now = datetime.now()
    d = now.day
    h = now.hour
    in_day_range = (1 <= d <= 3) or (15 <= d <= 18)
    in_hour_range = (h >= 23) or (h <= 4)
    return in_day_range and in_hour_range


def _already_done_today(key="last_nightly_date"):
    state = _load_state()
    return state.get(key) == str(date.today())


def _full_done_this_window():
    """Check if full backup already ran in the current window (1-3 or 15-18)."""
    state = _load_state()
    last = state.get("last_full_date", "")
    if not last:
        return False
    try:
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        today = date.today()
        d = today.day
        # Same window? Check if last_date is in the same day-range
        if 1 <= d <= 3:
            return last_date.month == today.month and 1 <= last_date.day <= 3
        elif 15 <= d <= 18:
            return last_date.month == today.month and 15 <= last_date.day <= 18
    except Exception:
        pass
    return False


def should_run_nightly():
    if not _is_nightly_window():
        return False
    if _already_done_today("last_nightly_date"):
        return False
    return True


def should_run_full():
    if not _is_full_backup_window():
        return False
    if _full_done_this_window():
        return False
    return True


# -- Archive creation (native tar, fast) ----------------------------------
def _create_archive(items, prefix="ailey_backup"):
    """Pack items with native tar. GZIP=-1 for speed."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{prefix}_{timestamp}.tar.gz"
    _LOCAL_TMP.mkdir(parents=True, exist_ok=True)
    archive_path = _LOCAL_TMP / archive_name
    missing = []

    existing = []
    for item in items:
        src = _AILEY_ROOT / item
        if src.exists():
            existing.append(item)
        else:
            missing.append(item)

    if not existing:
        return None, "No backup items found"

    try:
        exclude_args = []
        for pat in _EXCLUDE_PATTERNS:
            exclude_args.extend(["--exclude", pat])

        env = os.environ.copy()
        env["GZIP"] = "-1"

        cmd = ["tar", "czf", str(archive_path)] + exclude_args + existing
        label = ", ".join(existing)
        print(f"[Backup] Packing [{label}] ...")
        t0 = time.time()

        result = subprocess.run(
            cmd, cwd=str(_AILEY_ROOT),
            capture_output=True, text=True,
            timeout=1800, env=env,
        )
        pack_s = time.time() - t0

        # tar rc=1 means "file changed during read" -- acceptable
        if result.returncode > 1:
            if archive_path.exists():
                archive_path.unlink()
            return None, f"tar failed (rc={result.returncode}): {result.stderr[:300]}"

        if not archive_path.exists():
            return None, "Archive missing after tar"

        size_mb = archive_path.stat().st_size / (1024 * 1024)
        msg = f"{archive_name} ({size_mb:.0f} MB, {pack_s:.0f}s)"
        if missing:
            msg += f" [missing: {', '.join(missing)}]"
        print(f"[Backup] {msg}")
        return archive_path, msg

    except subprocess.TimeoutExpired:
        if archive_path.exists():
            archive_path.unlink()
        return None, "tar timeout (>30 min)"
    except Exception as e:
        if archive_path.exists():
            archive_path.unlink()
        return None, f"tar error: {e}"


# -- Upload targets -------------------------------------------------------
def _upload_to_icloud(archive_path):
    try:
        if not _ICLOUD_ROOT.exists():
            return False, "iCloud folder not found"
        _ICLOUD_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dst = _ICLOUD_BACKUP_DIR / archive_path.name
        shutil.copy2(str(archive_path), str(dst))
        if not dst.exists() or dst.stat().st_size != archive_path.stat().st_size:
            return False, "iCloud copy verification failed"
        subprocess.run(["brctl", "evict", str(dst)],
                       capture_output=True, timeout=30)
        size_mb = archive_path.stat().st_size / (1024 * 1024)
        return True, f"iCloud OK ({size_mb:.0f} MB)"
    except Exception as e:
        return False, f"iCloud: {e}"


_RCLONE = "/opt/homebrew/bin/rclone"


def _is_rclone_available():
    try:
        r = subprocess.run([_RCLONE, "listremotes"],
                           capture_output=True, text=True, timeout=10)
        return "gdrive:" in r.stdout
    except Exception:
        return False


def _upload_to_gdrive(archive_path, remote_dir):
    if not _is_rclone_available():
        return False, "rclone/gdrive not available"
    try:
        dst = f"{remote_dir}/{archive_path.name}"
        r = subprocess.run(
            [_RCLONE, "copyto", str(archive_path), dst, "-q"],
            capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            return False, f"GDrive: {r.stderr.strip()[:200]}"
        size_mb = archive_path.stat().st_size / (1024 * 1024)
        return True, f"GDrive OK ({size_mb:.0f} MB)"
    except subprocess.TimeoutExpired:
        return False, "GDrive upload timeout (>60 min)"
    except Exception as e:
        return False, f"GDrive: {e}"


# -- Rotation -------------------------------------------------------------
def _rotate_icloud(max_keep):
    try:
        if not _ICLOUD_BACKUP_DIR.exists():
            return
        backups = sorted(
            [f for f in _ICLOUD_BACKUP_DIR.iterdir()
             if f.name.endswith(".tar.gz")],
            key=lambda f: f.name, reverse=True)
        for old in backups[max_keep:]:
            old.unlink()
            print(f"[Backup] iCloud rotated: {old.name}")
    except Exception as e:
        print(f"[Backup] iCloud rotation error: {e}")


def _rotate_gdrive(remote_dir, max_keep):
    if not _is_rclone_available():
        return
    try:
        r = subprocess.run(
            [_RCLONE, "lsf", remote_dir, "--include", "*.tar.gz"],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return
        backups = sorted(r.stdout.strip().splitlines(), reverse=True)
        for old in backups[max_keep:]:
            subprocess.run([_RCLONE, "deletefile", f"{remote_dir}/{old}"],
                           capture_output=True, timeout=30)
            print(f"[Backup] GDrive rotated: {old}")
    except Exception as e:
        print(f"[Backup] GDrive rotation error: {e}")


# -- Cleanup temp ---------------------------------------------------------
def _cleanup_tmp(archive_path):
    try:
        if archive_path and archive_path.exists():
            archive_path.unlink()
        if _LOCAL_TMP.exists() and not list(_LOCAL_TMP.iterdir()):
            _LOCAL_TMP.rmdir()
    except Exception:
        pass


# -- Email notification ---------------------------------------------------
def _notify_failure(subject_tag, error_message):
    try:
        from .email_monitor import send_email_as_ailey
        body = (
            f"Hey Simon,\n\n"
            f"Backup failed: {subject_tag}\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Details:\n{error_message}\n\n"
            f"Source: {_AILEY_ROOT}\n\n"
            f"-- Ailey"
        )
        send_email_as_ailey(_SIMON_EMAIL,
                            f"Ailey Backup FAILED: {subject_tag}", body)
        print(f"[Backup] Failure email sent to {_SIMON_EMAIL}")
    except Exception as e:
        print(f"[Backup] Could not send failure email: {e}")


# -- Tier 1: Nightly DB backup -------------------------------------------
def run_nightly_db():
    start = time.time()
    log = []

    archive, msg = _create_archive(_DB_ITEMS, prefix="ailey_db")
    log.append(msg)
    if archive is None:
        return False, " | ".join(log)

    ic_ok, ic_msg = _upload_to_icloud(archive)
    log.append(ic_msg)

    gd_ok, gd_msg = _upload_to_gdrive(archive, _GDRIVE_NIGHTLY)
    log.append(gd_msg)

    _cleanup_tmp(archive)

    if ic_ok:
        _rotate_icloud(_MAX_NIGHTLY)
    if gd_ok:
        _rotate_gdrive(_GDRIVE_NIGHTLY, _MAX_NIGHTLY)

    dur = time.time() - start
    ok = ic_ok or gd_ok

    state = _load_state()
    if ok:
        dests = []
        if ic_ok: dests.append("iCloud")
        if gd_ok: dests.append("GDrive")
        state["last_nightly_date"] = str(date.today())
        state["last_nightly_ts"] = time.time()
        state["last_nightly_dur"] = round(dur, 1)
        _save_state(state)
        summary = f"DB Backup OK ({' + '.join(dests)}, {dur:.0f}s) -- " + " | ".join(log)
    else:
        summary = f"DB Backup FAILED ({dur:.0f}s): " + " | ".join(log)

    return ok, summary


# -- Tier 2: Bi-monthly full backup --------------------------------------
def run_full_backup():
    start = time.time()
    log = []

    archive, msg = _create_archive(_FULL_ITEMS, prefix="ailey_full")
    log.append(msg)
    if archive is None:
        return False, " | ".join(log)

    # Full backup goes ONLY to GDrive (too big for iCloud nightly dir)
    gd_ok, gd_msg = _upload_to_gdrive(archive, _GDRIVE_FULL)
    log.append(gd_msg)

    _cleanup_tmp(archive)

    if gd_ok:
        _rotate_gdrive(_GDRIVE_FULL, _MAX_FULL)

    dur = time.time() - start

    state = _load_state()
    if gd_ok:
        state["last_full_date"] = str(date.today())
        state["last_full_ts"] = time.time()
        state["last_full_dur"] = round(dur, 1)
        _save_state(state)
        summary = f"Full Backup OK (GDrive, {dur:.0f}s) -- " + " | ".join(log)
    else:
        summary = f"Full Backup FAILED ({dur:.0f}s): " + " | ".join(log)

    return gd_ok, summary


# -- Main entry point (called by IdleThinker) ----------------------------
def execute_nightly_backup():
    """Called by IdleThinker. Returns thought string or None if skipped."""
    results = []

    # Tier 2 first (if in window) -- runs rarely
    if should_run_full():
        print("[Backup] Starting bi-monthly FULL backup...")
        ok, msg = run_full_backup()
        print(f"[Backup] {msg}")
        results.append(msg)
        if not ok:
            _notify_failure("Full Backup (bi-monthly)", msg)

    # Tier 1 -- nightly DB
    if should_run_nightly():
        print("[Backup] Starting nightly DB backup...")
        ok, msg = run_nightly_db()
        print(f"[Backup] {msg}")
        results.append(msg)
        if not ok:
            _notify_failure("Nightly DB Backup", msg)

    if results:
        return " // ".join(results)
    return None
