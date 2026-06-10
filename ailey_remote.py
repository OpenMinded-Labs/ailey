#!/usr/bin/env python3
"""
Ailey Remote Controller — always-on lightweight watchdog service.

Runs on port 5580 as a standalone HTTP server (no Flask dependency).
Designed to be started via macOS LaunchAgent so it survives reboots
and keeps running even when Ailey is completely off.

Access from iPhone: http://<macbook-ip>:5580
"""

# ── CRITICAL: Set fork-safety env BEFORE any imports ─────────────
# When launched by LaunchAgent, macOS ObjC runtime is already active.
# Any subprocess we spawn (ailey_api.py) inherits this state.
# Without OBJC_DISABLE_INITIALIZE_FORK_SAFETY, the child Python process
# will get Errno 11 (EDEADLK) when loky/joblib tries to fork().
import os
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("JOBLIB_MULTIPROCESSING", "0")
os.environ.setdefault("no_proxy", "*")

import http.server
import json
import signal
import socket
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ─── Configuration ───────────────────────────────────────────────
AILEY_BASE = Path(__file__).parent.resolve()
AILEY_PYTHON = AILEY_BASE / ".venv" / "bin" / "python"
AILEY_API_SCRIPT = AILEY_BASE / "ailey_api.py"
AILEY_API_PORT = 5502
REMOTE_PORT = int(os.environ.get("AILEY_REMOTE_PORT", 5580))
LOG_FILE = AILEY_BASE / "remote_controller.log"
PID_FILE = AILEY_BASE / "ailey_api.pid"

# Auto-start Ailey on boot?  Set via env or toggle in UI
AUTO_START = os.environ.get("AILEY_AUTO_START", "0") in ("1", "true", "yes")

# ─── Logging ─────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ─── Helpers ─────────────────────────────────────────────────────
def get_local_ip() -> str:
    """Get the LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_ailey_running() -> dict:
    """Check if the Ailey API is responding."""
    import urllib.request

    # Strategy 1: HTTP health check (most reliable — API is fully up)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{AILEY_API_PORT}/api/profile",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"running": True, "status": {"api_responding": True}}
    except Exception:
        pass

    # Strategy 2: TCP port check (API is starting but not yet serving routes)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", AILEY_API_PORT))
        s.close()
        return {"running": True, "status": {"api_responding": False, "port_open": True}}
    except Exception:
        pass

    # Strategy 3: Check if process is alive via PID file
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)  # signal 0 = check existence
            return {"running": True, "status": {"pid": pid, "api_responding": False}}
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink(missing_ok=True)

    return {"running": False, "status": None}


def _cleanup_stale_resources():
    """Clean up stale POSIX semaphores and locks from a crashed API process.

    After a hard crash (SIGKILL, Bus Error, deadlock), the process may leave
    behind POSIX named semaphores (from joblib/loky used by sentence-transformers)
    and file locks. These cause 'OSError: [Errno 11] Resource deadlock avoided'
    on the next startup if not cleaned up.
    """
    cleaned = []

    # 1. Clean stale loky/joblib semaphores (macOS stores them in /dev/shm or kernel)
    #    We can't directly delete kernel semaphores, but we can ensure the
    #    resource_tracker from the old process is dead.
    try:
        result = subprocess.run(
            ["pgrep", "-f", "resource_tracker"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().split():
            try:
                pid = int(pid_str)
                os.kill(pid, signal.SIGKILL)
                cleaned.append(f"resource_tracker PID {pid}")
            except Exception:
                pass
    except Exception:
        pass

    # 2. Kill any orphaned mflux/acestep/seedvr2 subprocesses
    for pattern in ["mflux-generate", "mflux-upscale", "acestep", "seedvr2"]:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGKILL)
                    cleaned.append(f"{pattern} PID {pid}")
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Clean stale .lock files in project directory
    for lock_file in AILEY_BASE.glob("*.lock"):
        try:
            lock_file.unlink()
            cleaned.append(f"lock file {lock_file.name}")
        except Exception:
            pass

    if cleaned:
        log(f"Cleaned stale resources: {', '.join(cleaned)}")
    return cleaned


def _wait_for_port_free(port: int, timeout: float = 10.0) -> bool:
    """Wait until a TCP port is free (not LISTEN)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            # Port still in use — wait
            time.sleep(0.5)
        except (ConnectionRefusedError, OSError):
            return True  # Port is free
    return False


def start_ailey() -> dict:
    """Start the Ailey API backend."""
    check = is_ailey_running()
    if check["running"]:
        return {"success": True, "message": "Ailey läuft bereits", "status": check}

    if not AILEY_PYTHON.exists():
        return {"success": False, "error": f"Python nicht gefunden: {AILEY_PYTHON}"}
    if not AILEY_API_SCRIPT.exists():
        return {"success": False, "error": f"API-Script nicht gefunden: {AILEY_API_SCRIPT}"}

    # ── Pre-start cleanup: kill orphans + stale semaphores ──
    _cleanup_stale_resources()

    # ── Wait for port to be actually free (after stop/crash) ──
    if not _wait_for_port_free(AILEY_API_PORT, timeout=8):
        log(f"WARNING: Port {AILEY_API_PORT} still occupied after 8s wait")

    log("Starting Ailey API...")

    # Ensure PATH includes Homebrew + venv
    env = os.environ.copy()
    current_path = env.get("PATH", "")
    venv_bin = str(AILEY_BASE / ".venv" / "bin")
    if venv_bin not in current_path:
        env["PATH"] = f"{venv_bin}:/opt/homebrew/bin:/usr/local/bin:{current_path}"
    elif "/opt/homebrew/bin" not in current_path:
        env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{current_path}"

    # Portal Poller env vars (required for allinkl polling)
    env.setdefault("AILEY_PORTAL_URL", "https://ask-ailey.sexngears.de")
    env.setdefault("AILEY_PORTAL_KEY", "3leTu7Mhn69uTalXCwsxxjG9raB-SgXyTfbn0albP1Y")

    # ── CRITICAL: Prevent Errno 11 (EDEADLK) ──
    # macOS ObjC Fork Safety + loky/joblib semaphore prevention
    env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
    env["LOKY_MAX_CPU_COUNT"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["JOBLIB_MULTIPROCESSING"] = "0"
    env["no_proxy"] = "*"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        log_fh = open(AILEY_BASE / "api_run.log", "a")
        proc = subprocess.Popen(
            [str(AILEY_PYTHON), str(AILEY_API_SCRIPT)],
            cwd=str(AILEY_BASE),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach from this process
        )
        PID_FILE.write_text(str(proc.pid))
        log(f"Ailey API started (PID {proc.pid})")

        # Also start caffeinate to prevent sleep
        _start_caffeinate()

        return {"success": True, "message": f"Ailey gestartet (PID {proc.pid})", "pid": proc.pid}
    except Exception as e:
        log(f"Failed to start Ailey: {e}")
        return {"success": False, "error": str(e)}


def stop_ailey() -> dict:
    """Stop the Ailey API backend (hard kill if needed)."""
    killed = []

    # Kill via PID file
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
            log(f"Sent SIGTERM to PID {pid}")
        except Exception as e:
            log(f"PID file kill failed: {e}")
        PID_FILE.unlink(missing_ok=True)

    # Kill anything on port 5502/5503
    for port in [5502, 5503]:
        try:
            result = subprocess.run(
                ["lsof", "-nP", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGTERM)
                    killed.append(pid)
                    log(f"Killed PID {pid} on port {port}")
                except Exception:
                    pass
        except Exception:
            pass

    # Kill any remaining python ailey_api processes (catch zombies)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*ailey_api"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().split():
            try:
                pid = int(pid_str)
                if pid not in killed:
                    os.kill(pid, signal.SIGTERM)
                    killed.append(pid)
                    log(f"Killed zombie ailey_api PID {pid}")
            except Exception:
                pass
    except Exception:
        pass

    _stop_caffeinate()

    # Give processes time to die gracefully
    if killed:
        time.sleep(1.5)
        # SIGKILL anything still alive
        for pid in killed:
            try:
                os.kill(pid, 0)  # check if still alive
                os.kill(pid, signal.SIGKILL)
                log(f"Force-killed PID {pid}")
            except ProcessLookupError:
                pass
            except Exception:
                pass

    # Always clean up stale resources after stop
    _cleanup_stale_resources()

    if killed:
        return {"success": True, "message": f"Ailey gestoppt (PIDs: {killed})"}
    else:
        return {"success": True, "message": "Ailey war nicht aktiv"}


def restart_ailey() -> dict:
    """Stop, cleanup, then start Ailey."""
    log("Restart requested — stopping...")
    stop_result = stop_ailey()
    log(f"Stop result: {stop_result['message']}")

    # Wait for port to be free + processes to fully die
    _wait_for_port_free(AILEY_API_PORT, timeout=10)
    time.sleep(2)

    log("Restart — starting...")
    return start_ailey()


def force_recover() -> dict:
    """Emergency recovery: SIGKILL everything, clean all locks, restart.

    Designed for remote use when the API is completely stuck.
    """
    log("🚨 FORCE RECOVERY initiated")
    killed = []

    # SIGKILL everything python ailey related
    for pattern in ["python.*ailey_api", "mflux-generate", "mflux-upscale",
                     "acestep", "seedvr2", "resource_tracker"]:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                    log(f"SIGKILL {pattern} PID {pid}")
                except Exception:
                    pass
        except Exception:
            pass

    # Kill anything on our ports
    for port in [5502, 5503]:
        try:
            result = subprocess.run(
                ["lsof", "-nP", "-i", f":{port}", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                except Exception:
                    pass
        except Exception:
            pass

    PID_FILE.unlink(missing_ok=True)
    _stop_caffeinate()
    _cleanup_stale_resources()

    # Wait for everything to fully die
    time.sleep(3)

    log(f"Force recovery killed {len(killed)} processes — starting fresh...")
    start_result = start_ailey()
    return {
        "success": start_result.get("success", False),
        "message": f"Force Recovery: {len(killed)} killed, {start_result.get('message', '?')}",
        "killed": killed,
        "start": start_result,
    }


def get_api_tail() -> str:
    """Return last 80 lines of api_run.log for remote diagnostics."""
    log_path = AILEY_BASE / "api_run.log"
    if not log_path.exists():
        return "(kein Log vorhanden)"
    try:
        result = subprocess.run(
            ["tail", "-80", str(log_path)],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout or "(leer)"
    except Exception as e:
        return f"(Fehler: {e})"


def clear_all_pending() -> dict:
    """Clear ALL pending items: portal queue + internal API jobs.

    Works even when API is dead (portal is cleared via direct HTTP to portal).
    When API is alive, also clears in-process jobs via /api/system/clear-pending.
    """
    import urllib.request
    results = {"portal": [], "api": None}

    # 1. Clear portal queue (direct HTTP — works even when API is down)
    portal_url = os.environ.get("AILEY_PORTAL_URL", "https://ask-ailey.sexngears.de")
    portal_key = os.environ.get("AILEY_PORTAL_KEY", "3leTu7Mhn69uTalXCwsxxjG9raB-SgXyTfbn0albP1Y")
    try:
        # Poll all pending items
        req = urllib.request.Request(
            f"{portal_url}/api/poll_pending.php?key={portal_key}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data if isinstance(data, list) else data.get("items", [])
            for item in items:
                item_id = item.get("id", "?")
                # Reply with a "cleared by remote" message
                try:
                    reply_data = json.dumps({
                        "key": portal_key,
                        "request_id": item_id,
                        "reply": "⚠️ Anfrage gelöscht (Remote Recovery). Bitte erneut senden.",
                    }).encode("utf-8")
                    push_req = urllib.request.Request(
                        f"{portal_url}/api/push_reply.php",
                        data=reply_data,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(push_req, timeout=10)
                    results["portal"].append(f"cleared #{item_id}")
                except Exception as e:
                    results["portal"].append(f"failed #{item_id}: {e}")
    except Exception as e:
        results["portal"].append(f"poll error: {e}")

    # 2. Clear internal API jobs (only works when API is alive)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{AILEY_API_PORT}/api/system/clear-pending",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            results["api"] = json.loads(resp.read())
    except Exception as e:
        results["api"] = {"error": str(e), "note": "API vermutlich nicht erreichbar"}

    log(f"Clear-All-Pending: portal={results['portal']}, api={results['api']}")
    return results


# ─── Caffeinate (Sleep Prevention) ───────────────────────────────
_caffeinate_pid = None

def _start_caffeinate():
    global _caffeinate_pid
    _stop_caffeinate()
    try:
        proc = subprocess.Popen(["caffeinate", "-ims"], start_new_session=True)
        _caffeinate_pid = proc.pid
        log(f"caffeinate started (PID {proc.pid})")
    except Exception as e:
        log(f"caffeinate failed: {e}")

def _stop_caffeinate():
    global _caffeinate_pid
    if _caffeinate_pid:
        try:
            os.kill(_caffeinate_pid, signal.SIGTERM)
            log(f"caffeinate stopped (PID {_caffeinate_pid})")
        except Exception:
            pass
        _caffeinate_pid = None


# ─── VS Code Tunnel (Remote Copilot Access) ─────────────────────
_tunnel_proc = None
_VSCODE_CLI = None

def _find_vscode_cli() -> str | None:
    """Find the VS Code CLI binary."""
    import shutil
    # 1. PATH
    p = shutil.which("code")
    if p:
        return p
    # 2. Common macOS locations
    candidates = [
        "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
        os.path.expanduser("~/Downloads/Visual Studio Code.app/Contents/Resources/app/bin/code"),
        "/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code-insiders",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def start_code_tunnel() -> dict:
    """Start a VS Code tunnel for remote access via vscode.dev."""
    global _tunnel_proc, _VSCODE_CLI
    if _tunnel_proc and _tunnel_proc.poll() is None:
        return {"ok": True, "message": "Tunnel läuft bereits", "pid": _tunnel_proc.pid}

    if not _VSCODE_CLI:
        _VSCODE_CLI = _find_vscode_cli()
    if not _VSCODE_CLI:
        return {"ok": False, "message": "VS Code CLI nicht gefunden"}

    try:
        _tunnel_proc = subprocess.Popen(
            [_VSCODE_CLI, "tunnel", "--accept-server-license-terms",
             "--name", "ailey-macbook"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(AILEY_BASE), start_new_session=True,
        )
        log(f"🖥️ VS Code Tunnel gestartet (PID {_tunnel_proc.pid})")
        log(f"🖥️ Öffne https://vscode.dev/tunnel/ailey-macbook auf deinem Gerät")
        return {
            "ok": True,
            "message": "Tunnel gestartet! Öffne vscode.dev/tunnel/ailey-macbook",
            "url": "https://vscode.dev/tunnel/ailey-macbook",
            "pid": _tunnel_proc.pid,
        }
    except Exception as e:
        log(f"🖥️ Tunnel-Start fehlgeschlagen: {e}")
        return {"ok": False, "message": str(e)}

def stop_code_tunnel() -> dict:
    """Stop the VS Code tunnel."""
    global _tunnel_proc
    if _tunnel_proc and _tunnel_proc.poll() is None:
        _tunnel_proc.terminate()
        try:
            _tunnel_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _tunnel_proc.kill()
        log("🖥️ VS Code Tunnel gestoppt")
        _tunnel_proc = None
        return {"ok": True, "message": "Tunnel gestoppt"}
    _tunnel_proc = None
    return {"ok": True, "message": "Kein Tunnel aktiv"}

def is_tunnel_running() -> bool:
    """Check if tunnel process is alive."""
    return _tunnel_proc is not None and _tunnel_proc.poll() is None


# ─── Public IP & Cloudflare Quick Tunnel ─────────────────────────
_cf_tunnel_proc = None
_cf_tunnel_url = None

def get_public_ip() -> str | None:
    """Fetch public IP via api.ipify.org (fast, free, no auth)."""
    import urllib.request
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            return r.read().decode().strip()
    except Exception:
        return None

def get_tailscale_ip() -> str | None:
    """Get Tailscale IP if available."""
    import shutil
    if not shutil.which("tailscale"):
        return None
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        )
        ip = result.stdout.strip()
        return ip if ip and result.returncode == 0 else None
    except Exception:
        return None

def _has_cloudflared() -> bool:
    import shutil
    return shutil.which("cloudflared") is not None

def start_cloudflare_tunnel() -> dict:
    """Start a cloudflared quick tunnel exposing the Remote UI (port 5580)."""
    global _cf_tunnel_proc, _cf_tunnel_url
    if _cf_tunnel_proc and _cf_tunnel_proc.poll() is None:
        return {"ok": True, "message": "Cloudflare Tunnel läuft bereits",
                "url": _cf_tunnel_url or "?"}

    if not _has_cloudflared():
        return {"ok": False,
                "message": "cloudflared nicht installiert. Run: brew install cloudflared"}
    try:
        _cf_tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{REMOTE_PORT}",
             "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(AILEY_BASE), start_new_session=True, text=True,
        )
        # Read the output lines until we find the tunnel URL (max 30s)
        _cf_tunnel_url = None
        import re
        deadline = time.time() + 30
        while time.time() < deadline:
            line = _cf_tunnel_proc.stdout.readline()
            if not line:
                if _cf_tunnel_proc.poll() is not None:
                    break
                continue
            m = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
            if m:
                _cf_tunnel_url = m.group(1)
                break
        if _cf_tunnel_url:
            log(f"☁️ Cloudflare Quick Tunnel: {_cf_tunnel_url}")
            return {"ok": True, "message": f"Tunnel aktiv!",
                    "url": _cf_tunnel_url, "pid": _cf_tunnel_proc.pid}
        else:
            # Couldn't find URL, might still be starting or failed
            if _cf_tunnel_proc.poll() is not None:
                _cf_tunnel_proc = None
                return {"ok": False, "message": "cloudflared hat sich beendet"}
            log("☁️ Cloudflare Tunnel gestartet, URL noch nicht gefunden")
            return {"ok": True, "message": "Tunnel gestartet, URL wird ermittelt...",
                    "pid": _cf_tunnel_proc.pid}
    except Exception as e:
        log(f"☁️ Cloudflare Tunnel Fehler: {e}")
        return {"ok": False, "message": str(e)}

def stop_cloudflare_tunnel() -> dict:
    """Stop the cloudflared quick tunnel."""
    global _cf_tunnel_proc, _cf_tunnel_url
    if _cf_tunnel_proc and _cf_tunnel_proc.poll() is None:
        _cf_tunnel_proc.terminate()
        try:
            _cf_tunnel_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _cf_tunnel_proc.kill()
        log("☁️ Cloudflare Tunnel gestoppt")
    _cf_tunnel_proc = None
    _cf_tunnel_url = None
    return {"ok": True, "message": "Cloudflare Tunnel gestoppt"}

def is_cf_tunnel_running() -> bool:
    return _cf_tunnel_proc is not None and _cf_tunnel_proc.poll() is None


def quit_vscode() -> dict:
    """Quit VS Code completely to free RAM (~1-2 GB)."""
    # Also stop tunnel if running (VS Code tunnel only, keep cloudflared)
    stop_code_tunnel()
    try:
        # Graceful quit via AppleScript (saves open files)
        result = subprocess.run(
            ["osascript", "-e", 'tell application "Visual Studio Code" to quit'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            log("🗑️ VS Code beendet (AppleScript quit)")
            return {"ok": True, "message": "VS Code beendet"}
        # Fallback: killall
        subprocess.run(["killall", "Electron"], capture_output=True, timeout=5)
        subprocess.run(["killall", "Code Helper"], capture_output=True, timeout=5)
        log("🗑️ VS Code beendet (killall fallback)")
        return {"ok": True, "message": "VS Code beendet (killall)"}
    except Exception as e:
        log(f"🗑️ VS Code quit fehlgeschlagen: {e}")
        return {"ok": False, "message": str(e)}


# ─── Watchdog: Auto-restart crashed API ─────────────────────────
_watchdog_enabled = True   # can be toggled via /watchdog/on and /watchdog/off
_watchdog_last_restart = 0.0
_WATCHDOG_COOLDOWN = 120   # minimum seconds between auto-restarts

def _watchdog_loop():
    """Background thread: checks every 60s if API should be running but isn't."""
    global _watchdog_last_restart
    time.sleep(30)  # initial delay after remote start
    while True:
        try:
            if _watchdog_enabled and PID_FILE.exists():
                # PID file exists = we expect Ailey to be running
                check = is_ailey_running()
                if not check["running"]:
                    now = time.time()
                    if now - _watchdog_last_restart > _WATCHDOG_COOLDOWN:
                        log("🐕 Watchdog: API down but PID file exists — auto-restarting...")
                        _watchdog_last_restart = now
                        _cleanup_stale_resources()
                        _wait_for_port_free(AILEY_API_PORT, timeout=8)
                        time.sleep(2)
                        result = start_ailey()
                        log(f"🐕 Watchdog restart result: {result.get('message', '?')}")
                    else:
                        remaining = int(_WATCHDOG_COOLDOWN - (now - _watchdog_last_restart))
                        log(f"🐕 Watchdog: API down, cooldown {remaining}s remaining")
        except Exception as e:
            log(f"🐕 Watchdog error: {e}")
        time.sleep(60)


# ─── Venv Health Guard: Protect & repair Python environments ─────
# macOS aggressively compresses files (APFS transparent compression),
# Spotlight indexes site-packages (thrashes I/O, corrupts .pyc),
# Time Machine backs up gigabytes of venv data on every snapshot.
# This guard runs every 10 minutes: re-applies protection flags and
# does a lightweight import smoke-test to detect corruption early.

_VENV_DIRS = [
    AILEY_BASE / ".venv",
    AILEY_BASE / "ACE-Step" / ".venv",
]
_VENV_LAST_REPAIR: dict = {}  # path → timestamp of last repair attempt
_VENV_REPAIR_COOLDOWN = 3600  # don't repair same venv more than once per hour

def _apply_venv_protection(venv_path: Path):
    """Apply all macOS protection flags to a venv directory."""
    if not venv_path.is_dir():
        return
    venv_str = str(venv_path)
    try:
        # 1. Spotlight: don't index site-packages
        metadata_file = venv_path / ".metadata_never_index"
        if not metadata_file.exists():
            metadata_file.touch()
        # 2. iCloud: don't sync
        nosync_file = venv_path / ".nosync"
        if not nosync_file.exists():
            nosync_file.touch()
        # 3. Time Machine: exclude from backups
        subprocess.run(
            ["tmutil", "addexclusion", venv_str],
            capture_output=True, timeout=10
        )
        # 4. Backup exclude xattr
        subprocess.run(
            ["xattr", "-w", "com.apple.metadata:com_apple_backup_excludeItem",
             "com.apple.backupd", venv_str],
            capture_output=True, timeout=10
        )
    except Exception as e:
        log(f"🛡️ Venv protection error for {venv_path.name}: {e}")


def _smoke_test_venv(venv_path: Path) -> tuple[bool, str]:
    """Quick smoke test: can the venv's python import its core packages?"""
    python_bin = venv_path / "bin" / "python"
    if not python_bin.is_file():
        return False, "python binary missing"

    # Choose test based on which venv this is
    if "ACE-Step" in str(venv_path):
        test_code = "import torch; import transformers; print('ok')"
    else:
        # Main Ailey venv — test flask + mflux availability
        test_code = "import flask; import mflux; print('ok')"

    try:
        result = subprocess.run(
            [str(python_bin), "-c", test_code],
            capture_output=True, text=True, timeout=30,
            cwd=str(AILEY_BASE),
        )
        if result.returncode == 0 and "ok" in result.stdout:
            return True, "ok"
        err = (result.stderr or result.stdout or "unknown error")[:200]
        return False, err
    except subprocess.TimeoutExpired:
        return False, "import timed out (30s)"
    except Exception as e:
        return False, str(e)


def _repair_venv(venv_path: Path) -> bool:
    """Attempt to repair a corrupted venv by reinstalling key packages."""
    python_bin = venv_path / "bin" / "python"
    pip_cmd = [str(python_bin), "-m", "pip"]

    log(f"🔧 Attempting venv repair: {venv_path.name}")

    try:
        # Step 0: Ensure pip itself works — bootstrap if needed
        pip_test = subprocess.run(
            pip_cmd + ["--version"],
            capture_output=True, text=True, timeout=15
        )
        if pip_test.returncode != 0:
            log(f"🔧 pip broken in {venv_path.name}, bootstrapping...")
            subprocess.run(
                [str(python_bin), "-m", "ensurepip", "--upgrade"],
                capture_output=True, timeout=60
            )

        if "ACE-Step" in str(venv_path):
            # ACE-Step venv: torch is huge (2+ GB), never force-reinstall it.
            # Only reinstall lightweight packages. If torch is broken,
            # log a warning — manual intervention needed.
            torch_test = subprocess.run(
                [str(python_bin), "-c", "import torch; print(torch.__version__)"],
                capture_output=True, text=True, timeout=30
            )
            if torch_test.returncode != 0:
                log(f"🔧 ⚠️ torch broken in ACE-Step but too large to auto-reinstall. Manual fix needed.")
                log(f"🔧 Run: {python_bin} -m pip install torch torchaudio")
                return False
            # Only reinstall lightweight deps
            packages = ["transformers>=4.51.0,<4.58.0",
                         "safetensors", "scipy", "soundfile", "einops", "accelerate",
                         "numba", "diffusers", "loguru", "vector-quantize-pytorch", "toml"]
        else:
            # Main Ailey venv: fix the packages that keep breaking
            packages = ["sympy", "mflux"]

        for pkg in packages:
            log(f"🔧 Installing {pkg} in {venv_path.name}...")
            subprocess.run(
                pip_cmd + ["install", "--force-reinstall", "--no-deps", pkg],
                capture_output=True, text=True, timeout=120
            )

        # Verify repair worked
        ok, msg = _smoke_test_venv(venv_path)
        if ok:
            log(f"🔧 ✅ Repair successful for {venv_path.name}")
            return True
        else:
            log(f"🔧 ❌ Repair failed for {venv_path.name}: {msg}")
            return False
    except Exception as e:
        log(f"🔧 ❌ Repair exception for {venv_path.name}: {e}")
        return False


def _venv_health_loop():
    """Background thread: protects venvs and detects corruption every 10 min."""
    time.sleep(60)  # initial delay
    while True:
        for venv_path in _VENV_DIRS:
            if not venv_path.is_dir():
                continue
            try:
                # Always re-apply protection (flags can be lost after OS updates)
                _apply_venv_protection(venv_path)

                # Smoke test
                ok, msg = _smoke_test_venv(venv_path)
                if ok:
                    continue  # healthy, move on

                # Corruption detected!
                log(f"🛡️ ⚠️ Venv corrupted: {venv_path.name} — {msg}")

                # Check cooldown
                last = _VENV_LAST_REPAIR.get(str(venv_path), 0)
                if time.time() - last < _VENV_REPAIR_COOLDOWN:
                    remaining = int(_VENV_REPAIR_COOLDOWN - (time.time() - last))
                    log(f"🛡️ Repair cooldown for {venv_path.name}: {remaining}s remaining")
                    continue

                _VENV_LAST_REPAIR[str(venv_path)] = time.time()
                repaired = _repair_venv(venv_path)

                if repaired and venv_path == AILEY_BASE / ".venv":
                    # Main venv repaired — restart API if it was running
                    if PID_FILE.exists():
                        log("🛡️ Main venv repaired — restarting API...")
                        restart_ailey()

            except Exception as e:
                log(f"🛡️ Venv health check error for {venv_path.name}: {e}")

        time.sleep(600)  # check every 10 minutes


# ─── iPhone-friendly Web UI ──────────────────────────────────────
def render_html(status_info: dict) -> str:
    running = status_info.get("running", False)
    status_text = "🟢 Ailey läuft" if running else "🔴 Ailey ist aus"
    status_color = "#22c55e" if running else "#ef4444"
    local_ip = get_local_ip()
    ailey_url = f"http://{local_ip}:{AILEY_API_PORT}/app"

    # External access info (non-blocking, cached)
    public_ip = get_public_ip()
    tailscale_ip = get_tailscale_ip()
    cf_running = is_cf_tunnel_running()
    cf_url = _cf_tunnel_url if cf_running else None
    has_cf = _has_cloudflared()

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Ailey Remote">
    <title>Ailey Remote</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: #0a0a0a;
            color: #e5e5e5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            -webkit-tap-highlight-color: transparent;
        }}
        .card {{
            background: #1a1a2e;
            border-radius: 24px;
            padding: 40px 30px;
            max-width: 400px;
            width: 100%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }}
        h1 {{
            font-size: 1.8em;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #ff6b9d, #c44569);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .status {{
            font-size: 1.3em;
            margin: 20px 0;
            padding: 12px 20px;
            border-radius: 12px;
            background: rgba(255,255,255,0.05);
            border: 1px solid {status_color}40;
            color: {status_color};
            font-weight: 600;
        }}
        .buttons {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 24px;
        }}
        .btn {{
            display: block;
            padding: 16px 24px;
            border: none;
            border-radius: 14px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: transform 0.1s, opacity 0.2s;
            -webkit-tap-highlight-color: transparent;
        }}
        .btn:active {{ transform: scale(0.97); opacity: 0.8; }}
        .btn-start {{
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
        }}
        .btn-stop {{
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
        }}
        .btn-restart {{
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white;
        }}
        .btn-open {{
            background: linear-gradient(135deg, #8b5cf6, #7c3aed);
            color: white;
        }}
        .btn-refresh {{
            background: rgba(255,255,255,0.1);
            color: #a5a5a5;
        }}
        .btn-recover {{
            background: linear-gradient(135deg, #ef4444, #b91c1c);
            color: white;
            border: 2px solid #fca5a5;
        }}
        .btn-log {{
            background: rgba(255,255,255,0.08);
            color: #8b8b8b;
            font-size: 0.95em;
        }}
        .section-label {{
            font-size: 0.75em;
            color: #555;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 16px;
            margin-bottom: -4px;
            text-align: left;
            padding-left: 4px;
        }}
        .info {{
            margin-top: 20px;
            font-size: 0.85em;
            color: #666;
            line-height: 1.6;
        }}
        .loading {{
            display: none;
            margin: 16px auto;
            width: 30px; height: 30px;
            border: 3px solid #333;
            border-top-color: #ff6b9d;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .detail {{ font-size: 0.8em; color: #555; margin-top: 6px; }}
        .watchdog-info {{
            margin-top: 12px;
            padding: 8px 12px;
            border-radius: 8px;
            background: rgba(34,197,94,0.1);
            border: 1px solid rgba(34,197,94,0.2);
            font-size: 0.8em;
            color: #4ade80;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>💜 Ailey Remote</h1>
        <p style="color:#888; font-size:0.9em;">Fernsteuerung für dein MacBook</p>

        <div class="status">{status_text}</div>

        <div class="loading" id="loader"></div>

        <div class="buttons">
            <div class="section-label">⚡ Ailey Steuerung</div>
            {"" if running else '<a class="btn btn-start" href="/start" onclick="showLoader()">▶️ Ailey starten</a>'}
            {'<a class="btn btn-open" href="' + ailey_url + '" target="_blank">💬 Ailey öffnen</a>' if running else ""}
            {'<a class="btn btn-restart" href="/restart" onclick="showLoader()">🔄 Neustart</a>' if running else ""}
            {'<a class="btn btn-stop" href="/stop" onclick="showLoader()">⏹ Ailey stoppen</a>' if running else ""}

            <div class="section-label">🛠️ Wartung</div>
            <a class="btn btn-recover" href="/force-recover" onclick="return confirm('🚨 Force Recovery?\\nKillt ALLE Prozesse und startet komplett neu.') && showLoader()">🚨 Force Recovery</a>
            <a class="btn btn-log" href="/clear-pending" onclick="return confirm('🧹 Alle wartenden Anfragen löschen?') && showLoader()" style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3);">🧹 Pending Items leeren</a>
            <a class="btn btn-log" href="/repair-venvs" onclick="return confirm('🔧 Venvs reparieren?\\nDauert 1-3 Min.') && showLoader()" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3);">🔧 Venvs reparieren</a>

            <div class="section-label">🖥️ Entwickler-Zugang</div>
            {'<a class="btn btn-log" href="/tunnel/stop" style="background:rgba(139,92,246,0.25); color:#a78bfa; border:1px solid rgba(139,92,246,0.4);">🖥️ VS Code Tunnel stoppen (läuft)</a>' if is_tunnel_running() else '<a class="btn btn-log" href="/tunnel/start" onclick="showLoader()" style="background:rgba(139,92,246,0.15); color:#a78bfa; border:1px solid rgba(139,92,246,0.3);">🖥️ VS Code Tunnel starten</a>'}
            {'<a class="btn btn-log" href="/cf-tunnel/stop" style="background:rgba(249,115,22,0.25); color:#fb923c; border:1px solid rgba(249,115,22,0.4);">☁️ Cloudflare Tunnel stoppen' + (' — <code style="font-size:0.8em">' + cf_url + '</code>' if cf_url else '') + '</a>' if cf_running else ('<a class="btn btn-log" href="/cf-tunnel/start" onclick="showLoader()" style="background:rgba(249,115,22,0.15); color:#fb923c; border:1px solid rgba(249,115,22,0.3);">☁️ Cloudflare Quick Tunnel</a>' if has_cf else '<span class="btn btn-log" style="background:rgba(249,115,22,0.08); color:#777; border:1px solid rgba(249,115,22,0.15); font-size:0.85em;">☁️ cloudflared nicht installiert<br><code style="font-size:0.8em">brew install cloudflared</code></span>')}
            <a class="btn btn-log" href="/quit-vscode" onclick="return confirm('VS Code beenden?\\nSchließt alle VS Code Fenster (spart ~1-2 GB RAM).') && showLoader()" style="background:rgba(239,68,68,0.12); color:#f87171; border:1px solid rgba(239,68,68,0.25);">🗑️ VS Code beenden (RAM)</a>

            <div class="section-label">📊 Info</div>
            <a class="btn btn-log" href="/log">📋 Log (letzte 80 Zeilen)</a>
            <a class="btn btn-refresh" href="/">🔄 Status aktualisieren</a>
        </div>

        <div class="watchdog-info">
            🐕 Watchdog: {'aktiv' if _watchdog_enabled else 'aus'} · Prüft alle 60s<br>
            🛡️ Venv Guard: aktiv · Prüft alle 10min
        </div>

        <div class="info">
            <p>📱 Speichere diese Seite als Home-Bildschirm-Icon!</p>
            <p class="detail">🏠 LAN: {local_ip}:{REMOTE_PORT}</p>
            {'<p class="detail">🌐 Public IP: <strong>' + public_ip + '</strong> (Router Port-Forwarding nötig)</p>' if public_ip else '<p class="detail">🌐 Public IP: nicht verfügbar</p>'}
            {'<p class="detail">🔗 Tailscale: ' + tailscale_ip + ':' + str(REMOTE_PORT) + '</p>' if tailscale_ip else ''}
            {'<p class="detail" style="color:#fb923c;">☁️ Cloudflare: <a href="' + cf_url + '" target="_blank" style="color:#fb923c;">' + cf_url + '</a></p>' if cf_url else ''}
            {'<p class="detail" style="color:#a78bfa;">🖥️ VS Code: <a href="https://vscode.dev/tunnel/ailey-macbook" target="_blank" style="color:#a78bfa;">vscode.dev/tunnel/ailey-macbook</a></p>' if is_tunnel_running() else ''}
            <p class="detail" style="color:#555;">Ailey API: Port {AILEY_API_PORT} · {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
        </div>
    </div>

    <script>
        function showLoader() {{
            document.getElementById('loader').style.display = 'block';
            return true;
        }}
        // Auto-refresh every 15 seconds
        setTimeout(() => location.reload(), 15000);
    </script>
</body>
</html>"""


# ─── HTTP Server ─────────────────────────────────────────────────
class RemoteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log(f"HTTP {args[0]}" if args else "HTTP request")

    def _send_html(self, html: str, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data: dict, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _redirect(self, url="/"):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        want_json = "application/json" in self.headers.get("Accept", "")

        if path == "/" or path == "":
            status = is_ailey_running()
            if want_json:
                self._send_json(status)
            else:
                self._send_html(render_html(status))

        elif path == "/status" or path == "/api/status":
            self._send_json(is_ailey_running())

        elif path == "/start":
            result = start_ailey()
            if want_json:
                self._send_json(result)
            else:
                # Wait a moment for startup, then redirect
                time.sleep(3)
                self._redirect("/")

        elif path == "/stop":
            result = stop_ailey()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(1)
                self._redirect("/")

        elif path == "/restart":
            result = restart_ailey()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(4)
                self._redirect("/")

        elif path == "/force-recover":
            result = force_recover()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(5)
                self._redirect("/")

        elif path == "/clear-pending":
            result = clear_all_pending()
            if want_json:
                self._send_json(result)
            else:
                # Show result briefly then redirect
                portal_count = len([x for x in result.get("portal", []) if x.startswith("cleared")])
                api_cleared = result.get("api", {})
                api_count = len(api_cleared.get("cleared", [])) if isinstance(api_cleared, dict) else 0
                msg = f"Portal: {portal_count} gelöscht, API: {api_count} zurückgesetzt"
                html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="3;url=/">
<title>Pending gelöscht</title>
<style>body {{ background:#0a0a0a; color:#e5e5e5; font-family:-apple-system,system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; }}</style>
</head><body><div style="text-align:center;"><h2>🧹 {msg}</h2><p style="color:#888;">Weiterleitung in 3s...</p></div></body></html>"""
                self._send_html(html)

        elif path == "/log":
            log_text = get_api_tail()
            html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ailey Log</title>
<style>
body {{ background: #0a0a0a; color: #d4d4d4; font-family: monospace; padding: 16px; font-size: 11px; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; line-height: 1.5; }}
a {{ color: #ff6b9d; }}
h2 {{ color: #ff6b9d; margin-bottom: 12px; }}
</style>
</head><body>
<h2>📋 api_run.log (letzte 80 Zeilen)</h2>
<p><a href="/">← Zurück</a> · <a href="/log">🔄 Aktualisieren</a></p>
<pre>{log_text}</pre>
<p><a href="/">← Zurück</a></p>
</body></html>"""
            self._send_html(html)

        elif path == "/repair-venvs":
            log("🔧 Manual venv repair triggered via Remote UI")
            results = {}
            for vp in _VENV_DIRS:
                vname = vp.name if vp.name != ".venv" else f"{vp.parent.name}/.venv"
                if not vp.is_dir():
                    results[vname] = "⚠️ nicht vorhanden"
                    continue
                _apply_venv_protection(vp)
                ok, msg = _smoke_test_venv(vp)
                if ok:
                    results[vname] = "✅ gesund"
                else:
                    log(f"🔧 Repairing {vname}: {msg}")
                    repaired = _repair_venv(vp)
                    results[vname] = "✅ repariert" if repaired else f"❌ Reparatur fehlgeschlagen: {msg[:80]}"
            if want_json:
                self._send_json({"repaired": results})
            else:
                lines = "<br>".join(f"<b>{k}</b>: {v}" for k, v in results.items())
                html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="5;url=/">
<title>Venv Repair</title>
<style>body {{ background:#0a0a0a; color:#e5e5e5; font-family:-apple-system,system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; }}</style>
</head><body><div style="text-align:center;"><h2>🔧 Venv Repair</h2><p style="line-height:2;">{lines}</p><p style="color:#888; margin-top:16px;">Weiterleitung in 5s...</p></div></body></html>"""
                self._send_html(html)

        elif path == "/tunnel/start":
            result = start_code_tunnel()
            if want_json:
                self._send_json(result)
            else:
                url = result.get("url", "https://vscode.dev")
                ok = result.get("ok", False)
                msg = result.get("message", "?")
                icon = "✅" if ok else "❌"
                html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{"" if not ok else ""}
<title>VS Code Tunnel</title>
<style>body {{ background:#0a0a0a; color:#e5e5e5; font-family:-apple-system,system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; text-align:center; padding:20px; }} a {{ color:#a78bfa; }} .btn {{ display:inline-block; padding:16px 32px; background:linear-gradient(135deg,#8b5cf6,#7c3aed); color:white; border-radius:14px; text-decoration:none; font-size:1.1em; font-weight:600; margin:16px 8px; }} .btn-back {{ background:rgba(255,255,255,0.1); color:#aaa; }}</style>
</head><body><div>
<h2>{icon} {msg}</h2>
{'<p style="margin:20px 0;"><a class="btn" href="' + url + '" target="_blank">🖥️ VS Code öffnen</a><a class="btn btn-back" href="/">← Zurück</a></p><p style="color:#888; font-size:0.85em;">Tunnel-Name: ailey-macbook<br>Funktioniert auch vom iPhone!</p>' if ok else '<p><a class="btn btn-back" href="/">← Zurück</a></p>'}
</div></body></html>"""
                self._send_html(html)

        elif path == "/tunnel/stop":
            result = stop_code_tunnel()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(1)
                self._redirect("/")

        elif path == "/quit-vscode":
            result = quit_vscode()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(1)
                self._redirect("/")

        elif path == "/cf-tunnel/start":
            result = start_cloudflare_tunnel()
            if want_json:
                self._send_json(result)
            else:
                ok = result.get("ok", False)
                url = result.get("url", "")
                msg = result.get("message", "?")
                icon = "✅" if ok else "❌"
                html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cloudflare Tunnel</title>
<style>body {{ background:#0a0a0a; color:#e5e5e5; font-family:-apple-system,system-ui,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; text-align:center; padding:20px; }} a {{ color:#fb923c; }} code {{ background:rgba(255,255,255,0.1); padding:4px 8px; border-radius:6px; font-size:0.9em; word-break:break-all; }} .btn {{ display:inline-block; padding:16px 32px; background:linear-gradient(135deg,#f97316,#ea580c); color:white; border-radius:14px; text-decoration:none; font-size:1.1em; font-weight:600; margin:16px 8px; }} .btn-back {{ background:rgba(255,255,255,0.1); color:#aaa; }}</style>
</head><body><div>
<h2>{icon} {msg}</h2>
{'<p style="margin:20px 0;"><code>' + url + '</code></p><p><a class="btn" href="' + url + '" target="_blank">☁️ Remote öffnen</a><a class="btn btn-back" href="/">← Zurück</a></p><p style="color:#888; font-size:0.85em; margin-top:12px;">Temporäre URL — gültig bis Tunnel gestoppt wird.<br>Funktioniert von überall (Arbeit, iPhone, etc.)</p>' if ok and url else '<p><a class="btn btn-back" href="/">← Zurück</a></p>'}
</div></body></html>"""
                self._send_html(html)

        elif path == "/cf-tunnel/stop":
            result = stop_cloudflare_tunnel()
            if want_json:
                self._send_json(result)
            else:
                time.sleep(1)
                self._redirect("/")

        elif path == "/watchdog/on":
            global _watchdog_enabled
            _watchdog_enabled = True
            log("🐕 Watchdog enabled via remote")
            self._redirect("/")

        elif path == "/watchdog/off":
            _watchdog_enabled = False
            log("🐕 Watchdog disabled via remote")
            self._redirect("/")

        elif path == "/health":
            self._send_json({"ok": True, "service": "ailey-remote", "ts": time.time()})

        else:
            self._send_html("<h1>404</h1>", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


def run_server():
    server = http.server.HTTPServer(("0.0.0.0", REMOTE_PORT), RemoteHandler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    local_ip = get_local_ip()
    log(f"Ailey Remote Controller running on http://{local_ip}:{REMOTE_PORT}")
    log(f"Open this URL on your iPhone to control Ailey!")

    if AUTO_START:
        log("AUTO_START enabled — starting Ailey now...")
        start_ailey()

    # Start watchdog thread
    _wd_thread = threading.Thread(target=_watchdog_loop, daemon=True)
    _wd_thread.start()
    log("🐕 Watchdog thread started (auto-restart on crash)")

    # Start venv health guard thread
    _vh_thread = threading.Thread(target=_venv_health_loop, daemon=True)
    _vh_thread.start()
    log("🛡️ Venv Health Guard started (protection + smoke-test every 10min)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Remote Controller shutting down...")
        server.shutdown()


if __name__ == "__main__":
    log("=" * 60)
    log("Ailey Remote Controller starting...")
    log(f"Base: {AILEY_BASE}")
    log(f"Port: {REMOTE_PORT}")
    log(f"Auto-Start: {AUTO_START}")
    log("=" * 60)

    # Apply venv protection immediately on startup
    for _vp in _VENV_DIRS:
        if _vp.is_dir():
            _apply_venv_protection(_vp)
            log(f"🛡️ Protected: {_vp.name}")

    run_server()
