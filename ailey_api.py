# -*- coding: utf-8 -*-
#!/usr/bin/env python3

AILEY_VERSION = "3.0.0"

# ── CRITICAL: Set environment BEFORE any imports ─────────────────
# Prevents Errno 11 (EDEADLK / Resource deadlock avoided) when
# launched via Tauri or LaunchAgent. Root cause: macOS ObjC Fork
# Safety blocks fork() when Objective-C runtime is already active
# in the parent process (launchd → Tauri/remote → Python).
# loky/joblib (via sentence_transformers) calls fork() internally.
import os as _os
_os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
_os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_os.environ.setdefault("JOBLIB_MULTIPROCESSING", "0")
_os.environ.setdefault("no_proxy", "*")

# Force spawn (not fork) for multiprocessing — prevents lock inheritance
import multiprocessing as _mp
try:
    _mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass

# Raise file descriptor limit (LaunchAgent default is 256, we need ~500+)
import resource as _resource
try:
    _soft, _hard = _resource.getrlimit(_resource.RLIMIT_NOFILE)
    if _soft < 4096:
        _resource.setrlimit(_resource.RLIMIT_NOFILE, (min(_hard, 8192), _hard))
except Exception:
    pass

import os
import sys
import signal
import atexit
import threading
import time
from datetime import timedelta, datetime, timezone

# ── Global Thread Exception Handler ──────────────────────────────
# Catches unhandled exceptions in daemon threads that would otherwise
# silently kill the entire process (the root cause of the deadlock crashes).
def _global_thread_excepthook(args):
    """Log unhandled exceptions in threads instead of dying silently."""
    print(f"\n🔥 UNHANDLED THREAD EXCEPTION in {args.thread.name}:", flush=True)
    import traceback
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    print(f"🔥 Thread {args.thread.name} crashed but process continues.\n", flush=True)

threading.excepthook = _global_thread_excepthook

# ── Graceful Shutdown Handler ────────────────────────────────────
# Ensures clean shutdown on SIGTERM/SIGINT: kills subprocesses,
# releases semaphores, flushes logs. Prevents stale locks on restart.
_shutdown_in_progress = False

# ── PID file for Tauri to detect us ─────────────────────────────
_PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ailey_api.pid")

def _write_pid_file():
    """Write our PID to a file so Tauri can identify us."""
    try:
        with open(_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def _remove_pid_file():
    """Remove PID file on shutdown."""
    try:
        os.unlink(_PID_FILE)
    except Exception:
        pass

_write_pid_file()
atexit.register(_remove_pid_file)

# ── Early Port Claim ────────────────────────────────────────────
# Bind port 5502 IMMEDIATELY so Tauri's is_port_open() returns true
# while we're still doing heavy init (model loading, RAG, etc.).
# Flask will take over this socket later via SO_REUSEADDR.
import socket as _early_socket
_early_sentinel_sock = None

def _claim_port_early():
    """Bind port 5502 right now so Tauri sees we're alive during boot."""
    global _early_sentinel_sock
    _port = int(os.environ.get('AILEY_API_PORT', 5502))
    try:
        _early_sentinel_sock = _early_socket.socket(_early_socket.AF_INET, _early_socket.SOCK_STREAM)
        _early_sentinel_sock.setsockopt(_early_socket.SOL_SOCKET, _early_socket.SO_REUSEADDR, 1)
        _early_sentinel_sock.setsockopt(_early_socket.SOL_SOCKET, _early_socket.SO_REUSEPORT, 1)
        _early_sentinel_sock.bind(('0.0.0.0', _port))
        _early_sentinel_sock.listen(1)
        print(f"[Startup] ⚡ Early port claim: 0.0.0.0:{_port} — Tauri will see us alive", flush=True)
    except OSError as e:
        # Port already in use — another instance is running, that's fine
        print(f"[Startup] ℹ️  Port {_port} already in use (another instance?): {e}", flush=True)
        _early_sentinel_sock = None

def _release_early_port():
    """Release the early sentinel socket so Flask can bind the port."""
    global _early_sentinel_sock
    if _early_sentinel_sock:
        try:
            _early_sentinel_sock.close()
        except Exception:
            pass
        _early_sentinel_sock = None

# Claim the port NOW — before any heavy imports
_claim_port_early()

def _graceful_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT: clean up subprocesses and locks."""
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return  # prevent re-entry
    _shutdown_in_progress = True

    sig_name = signal.Signals(signum).name if signum else "?"
    print(f"\n⚡ Received {sig_name} — graceful shutdown...", flush=True)

    # Clean up early port claim and PID file
    _release_early_port()
    _remove_pid_file()

    # Kill any running mflux/acestep subprocesses
    import subprocess as _sp
    for pattern in ["mflux-generate", "mflux-upscale", "acestep", "seedvr2"]:
        try:
            result = _sp.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=3)
            for pid_str in result.stdout.strip().split():
                try:
                    os.kill(int(pid_str), signal.SIGTERM)
                except Exception:
                    pass
        except Exception:
            pass

    # Flush stdout/stderr
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    print("⚡ Shutdown complete.", flush=True)
    os._exit(0)

# Guard: signal handlers can only be set from the main thread.
# With multiprocessing start_method="spawn", worker processes re-import
# this module but their main thread isn't the *real* main thread.
if threading.current_thread() is threading.main_thread():
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import re
import subprocess
from pathlib import Path

from ailey_core import AileyCore
# MLX backend (Ministral) — primary and only LLM engine
from ailey_system.llm_mlx import MLXGenerator
from ailey_system import llm_mlx as _llm_module  # for model reload
from ailey_system.llm_mlx import analyze_image as _vision_analyze, get_vision_status, unload_vision_now
from ailey_system.llm_mlx import fast_analyze_image as _nitro_vision_analyze, is_fast_available as _nitro_available
from ailey_system.llm_mlx import AILEY_VISION_PROMPT as _VISION_PROMPT
from ailey_system.llm_mlx import extract_document_text as _extract_doc, ALLOWED_DOC_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS
# 🐹 Hamster (Qwen2.5-Coder-1.5B) — autocomplete + lint
from ailey_system import llm_coder as _coder_module
# Tool system
from ailey_system.tools import get_tool_schemas, execute_tool, parse_tool_calls, extract_text_before_tools
from ailey_system.tools import (
    generate_svg, list_svg_gallery,
    list_reminders, create_reminder, create_recurring_reminder, complete_reminder,
    speak_text, recognize_speech
)
# Extended tool modules — auto-register tools via @register_tool
import ailey_system.tools_code    # read_file, write_file, patch_file, create_file, run_command, etc.
import ailey_system.tools_web     # web_search, fetch_url, npm_search, pypi_search
import ailey_system.tools_git     # git_status, git_diff, git_add, git_commit, git_push, etc.
import ailey_system.tools_system  # open_app, clipboard, system_info, screenshot, notification
# Agent Loop
from ailey_system.agent_loop import AgentRunner, get_agent, list_agents, stop_agent, pause_agent, resume_agent
# Idle Thinker — autonomous background reflection
from ailey_system.idle_thinker import IdleThinker, read_thoughts, append_thought
# Portal (multi-user chat — polling architecture, no tunnel needed)
from ailey_system.portal_api import portal_bp
from ailey_system.portal_poller import get_portal_poller
from ailey_system.diary_manager import save_entry, list_entries, read_entry, set_password, verify_password
from ailey_system.rating_store import save_rating, list_ratings, get_rating, rating_stats, export_for_finetuning
# Learning system
from ailey_system.learning import LearningEngine, TRACKS, get_track, get_unit
# Use LanceDB-based RAG (numpy 2.x compatible for MLX)
try:
    from ailey_system.ailey_rag_lance import AileyRAG
except ImportError:
    from ailey_system.ailey_rag import AileyRAG
import traceback
import requests
import signal
import uuid
import socket
from threading import Lock

# Serve the static Next.js export so remote devices can access the frontend via the API port
_FRONTEND_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey-frontend', 'out')

app = Flask(__name__, static_folder=_FRONTEND_OUT, static_url_path='/app')
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 20 MB — allow image uploads via base64
)

# Ensure a secret key exists so Flask session can be used for join flow
if not app.secret_key:
    app.secret_key = os.environ.get('AILEY_SECRET_KEY') or os.urandom(24)

print('[Startup] Flask app created. SESSION_COOKIE_NAME=', app.config.get('SESSION_COOKIE_NAME'), 'has_attr_session_cookie_name=', hasattr(app, 'session_cookie_name'))

# Handle upload too large (413)
@app.errorhandler(413)
def _too_large(e):
    return jsonify({"success": False, "error": "Datei zu groß (max 20 MB)"}), 413

# In-memory short-lived join tokens: token -> {cookie: str, expires: ts, created_by: ip}
JOIN_TOKENS = {}
_JOIN_LOCK = Lock()
JOIN_TOKEN_TTL = int(os.environ.get('AILEY_JOIN_TOKEN_TTL', 300))  # seconds

def _cleanup_join_tokens():
    now = time.time()
    with _JOIN_LOCK:
        expired = [t for t, v in JOIN_TOKENS.items() if v.get('expires', 0) < now]
        for t in expired:
            JOIN_TOKENS.pop(t, None)


ALLOWED_ORIGINS = [
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5502",
    "http://127.0.0.1:5502",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "file://",
    "null",
    "*",  # Allow all for local development
]


# Dynamische CORS-Origins: alle lokalen LAN-IPs + localhost + Tauri
import socket
origins = list(ALLOWED_ORIGINS)  # start with all statically allowed origins
try:
    import netifaces
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET in addrs:
            for addr in addrs[netifaces.AF_INET]:
                ip = addr['addr']
                if not ip.startswith('127.') and not ip.startswith('::1'):
                    origins.append(f"http://{ip}:3000")
                    origins.append(f"http://{ip}:5175")
                    origins.append(f"http://{ip}:5502")
except Exception:
    # Fallback: hostname-IP
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith('127.'):
            origins.append(f"http://{ip}:3000")
            origins.append(f"http://{ip}:5175")
            origins.append(f"http://{ip}:5502")
    except Exception:
        pass
CORS(
    app,
    supports_credentials=True,
    origins=origins,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token", "X-Portal-Key"],
    expose_headers=["Content-Type"],
    max_age=600,
)

# ─── Portal Blueprint Registration ──────────────────────────────────────────
app.register_blueprint(portal_bp)
print('[Startup] Portal API registered at /portal/*')


# ─── Dynamic Tool-Loading: Message Classifier ───────────────────────────────
# Fast keyword-based routing to select only relevant tool categories per message.
# Reduces prompt size by 40-70%, improving Time-to-First-Token by ~1-3 seconds.
import re as _re_classify

# Keywords that indicate the message needs tools from a specific category
_TOOL_KEYWORDS = {
    "web": re.compile(
        r"\b(such|recherch|google|internet|web|online|nachricht|news|aktuell|website"
        r"|url|link|npm|pypi|download|wiki|http|\.com|\.de|\.org|\.net|schau.*(?:dir|mal).*(?:an|seite)|besuch|lies.*(?:seite|artikel|link))\b", re.IGNORECASE),
    "code": re.compile(
        r"\b(code|coden|datei|file|terminal|befehl|command|ordner|verzeichnis"
        r"|schreib.*datei|lese.*datei|patch|programmier|script|projekt"
        r"|build|kompilier|install|lint|test|preview|export)\b", re.IGNORECASE),
    "git": re.compile(
        r"\b(git|commit|push|pull|branch|stash|diff|merge|repo)\b", re.IGNORECASE),
    "system": re.compile(
        r"\b(öffne|starte|app|zwischenablage|clipboard|screenshot|bildschirm"
        r"|systeminfo|system.?info|benachrichtig|notification)\b", re.IGNORECASE),
    "image": re.compile(
        r"\b(bild|image|foto|picture|illustration|generier.*bild|selfie|gemälde|artwork"
        r"|mal\s+mir|zeichne|erzeug.*bild|kreier.*bild)\b", re.IGNORECASE),
}

# Chat-tool keywords (calendar, reminders, notes, timer, svg, tts, image generation)
_CHAT_TOOL_KEYWORDS = re.compile(
    r"\b(kalender|termin|event|erinnerung|remind|notiz|note|timer|wecker"
    r"|uhrzeit|datum|zeit|svg|grafik|zeichn|sprich|sag|vorlesen"
    r"|sprach|profil|merk dir|merke|er[\s-]*diag|entity[\s-]*relat|datenbank[\s-]*diag|datenmodell"
    r"|bild|image|foto|picture|illustration|generier|selfie|gemälde|artwork)\b", re.IGNORECASE)


def classify_message_tools(message: str, mode: str = "chat") -> list:
    """Classify a user message and return the tool categories to include.

    Returns a list of category strings for get_tool_schemas(categories=...).
    Returns None to include ALL tools (for ambiguous/complex messages).

    Strategy:
    - Pure conversational messages ("wie geht's", "erzähl mir was") → NO tools
    - Messages with clear intent keywords → only matching categories + chat
    - Ambiguous / could-need-anything → all tools
    """
    if mode == "code":
        # In code mode the agent loop handles its own tools — don't filter
        return None

    lower = message.lower().strip()

    # Quick check: very short casual messages never need tools
    if len(lower) < 15 and not any(pat.search(lower) for pat in _TOOL_KEYWORDS.values()):
        if not _CHAT_TOOL_KEYWORDS.search(lower):
            return []  # No tools needed — pure chat

    # Collect matching categories
    matched = set()
    for cat, pattern in _TOOL_KEYWORDS.items():
        if pattern.search(lower):
            matched.add(cat)

    # Check if chat-specific tools are needed
    if _CHAT_TOOL_KEYWORDS.search(lower):
        matched.add("chat")

    # If no category matched at all, check if it's clearly conversational
    if not matched:
        # Heuristic: if the message is a question/statement without action keywords,
        # skip tools entirely for faster response
        _action_hints = re.compile(
            r"\b(mach|erstell|setz|stell|schreib|lösch|speicher|send|zeig|list|öffne"
            r"|such|start|stopp|push|pull|commit|bau|install|export|generier|erzeug|mal)\b", re.IGNORECASE)
        if not _action_hints.search(lower):
            return []  # Pure conversation — no tools
        # Has action words but no category match — include chat tools as fallback
        return ["chat"]

    # If code or git matched, always include both (they go together)
    if "code" in matched or "git" in matched:
        matched.add("code")
        matched.add("git")

    # Always include chat tools when any category is active (for time, notes, etc.)
    matched.add("chat")

    return list(matched)


# ─── Live Chat Bus (cross-device sync) ──────────────────────────────────────
# In-memory ring buffer of recent chat messages. All clients poll this.
_LIVE_CHAT: list = []       # [{id, ts, sender, content, mood, ...}]
_LIVE_CHAT_LOCK = Lock()
_LIVE_CHAT_MAX = 200        # Keep last N messages in memory

def _live_chat_push(sender: str, content: str, mood: str = "neutral", **extra):
    """Push a message to the live chat bus so all connected clients see it."""
    entry = {
        "id": f"{time.time():.6f}_{uuid.uuid4().hex[:8]}",
        "ts": time.time(),
        "sender": sender,  # "user" or "ai"
        "content": content,
        "mood": mood,
        **extra,
    }
    with _LIVE_CHAT_LOCK:
        _LIVE_CHAT.append(entry)
        if len(_LIVE_CHAT) > _LIVE_CHAT_MAX:
            _LIVE_CHAT[:] = _LIVE_CHAT[-_LIVE_CHAT_MAX:]
    return entry

@app.get('/api/chat/live')
def api_chat_live():
    """Poll for new chat messages since a given timestamp.
    Query params: since=<float timestamp> (default: 0 = all recent)
    """
    since = float(request.args.get('since', 0))
    with _LIVE_CHAT_LOCK:
        msgs = [m for m in _LIVE_CHAT if m['ts'] > since]
    return jsonify({"success": True, "messages": msgs, "count": len(msgs)})


@app.get('/api/status')
def api_system_status():
    """Lightweight health endpoint for the Remote Controller and monitoring."""
    from datetime import datetime
    return jsonify({
        "status": "ok",
        "version": "2.5.0",
        "timestamp": datetime.now().isoformat(),
        "port": int(os.environ.get('AILEY_API_PORT', 5502)),
    })


# ─── Serve static frontend for remote devices ────────────────────────────────
# Next.js `output: 'export'` generates flat HTML files: code.html, author.html, etc.
# Remote devices access the frontend via the Flask API port (5502).
# We serve pages both at /app/* and directly at top-level (/code, /author, etc.)
# so that <a href="/code"> links work from any context.

# ── Root route: serve the chat page directly ──
@app.route('/')
def serve_root_page():
    """Serve index.html at root so 192.168.x.x:5502/ shows the chat."""
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'index.html')

def _serve_next_page(page_name):
    """Resolve a Next.js static export page: try page_name.html, then index.html fallback."""
    from flask import send_from_directory
    # Direct file match (e.g. "code.html" already)
    fpath = os.path.join(_FRONTEND_OUT, page_name)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, page_name)
    # Try appending .html (e.g. "code" → "code.html")
    html_name = page_name.rstrip('/') + '.html'
    hpath = os.path.join(_FRONTEND_OUT, html_name)
    if os.path.isfile(hpath):
        return send_from_directory(_FRONTEND_OUT, html_name)
    # Fallback to index.html (SPA catch-all)
    return send_from_directory(_FRONTEND_OUT, 'index.html')

# ── Top-level page routes (so /code, /author, /admin, /join work directly) ──
@app.route('/code')
@app.route('/code/')
def serve_page_code():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'code.html')

@app.route('/author')
@app.route('/author/')
def serve_page_author():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'author.html')

@app.route('/admin')
@app.route('/admin/')
def serve_page_admin():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'admin.html')

@app.route('/join')
@app.route('/join/')
def serve_page_join():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'join.html')

@app.route('/training')
@app.route('/training/')
def serve_page_training():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'training.html')

# ── /app/* routes (QR-code entry point) ──
@app.route('/app/')
@app.route('/app/index.html')
def serve_frontend_index():
    """Serve the Next.js static export index.html."""
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'index.html')

@app.route('/app/<path:filename>')
def serve_frontend_static(filename):
    """Serve any static file from the frontend build output, with .html resolution."""
    return _serve_next_page(filename)

# ─── Root-level asset pass-through for Next.js static export ─────────────────
# The Next.js static export generates absolute paths like /_next/static/...,
# /images/..., /ailey-emotes/..., etc.  These catch-all routes proxy them from
# the static export directory so everything loads correctly on remote devices.
@app.route('/_next/<path:rest>')
def serve_next_assets(rest):
    """Serve Next.js build assets (JS, CSS, fonts, etc.) from root path."""
    from flask import send_from_directory
    asset = os.path.join('_next', rest)
    fpath = os.path.join(_FRONTEND_OUT, asset)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, asset)
    return ('', 404)

@app.route('/images/<path:rest>')
def serve_images_assets(rest):
    """Serve /images/* from the frontend build output."""
    from flask import send_from_directory
    asset = os.path.join('images', rest)
    fpath = os.path.join(_FRONTEND_OUT, asset)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, asset)
    return ('', 404)

@app.route('/ailey-emotes/<path:rest>')
def serve_emotes_assets(rest):
    """Serve /ailey-emotes/* from the frontend build output (avatar images)."""
    from flask import send_from_directory
    asset = os.path.join('ailey-emotes', rest)
    fpath = os.path.join(_FRONTEND_OUT, asset)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, asset)
    return ('', 404)

# ── Root-level static file catch-all for Next.js assets (favicon, css, monaco, etc.) ──
# IMPORTANT: This must be defined BEFORE @app.before_request but Flask routes
# are matched by specificity, so explicit /api/* routes always win.
@app.route('/favicon.ico')
def serve_favicon():
    from flask import send_from_directory
    return send_from_directory(_FRONTEND_OUT, 'favicon.ico')

@app.route('/monaco/<path:rest>')
def serve_monaco_assets(rest):
    from flask import send_from_directory
    asset = os.path.join('monaco', rest)
    fpath = os.path.join(_FRONTEND_OUT, asset)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, asset)
    return ('', 404)

@app.route('/sounds/<path:rest>')
def serve_sounds_assets(rest):
    from flask import send_from_directory
    asset = os.path.join('sounds', rest)
    fpath = os.path.join(_FRONTEND_OUT, asset)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, asset)
    return ('', 404)

# ── Ailey Home RMMZ Life Simulation — serve game directly from backend ──────
_RMMZ_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AileyHomeRMMZ', 'ailey-home')

@app.route('/ailey-home/')
def serve_rmmz_index():
    """Serve the RPG Maker MZ game index.html."""
    from flask import send_from_directory
    return send_from_directory(_RMMZ_DIR, 'index.html')

@app.route('/ailey-home/<path:rest>')
def serve_rmmz_assets(rest):
    """Serve all RMMZ game assets (js, css, data, img, audio)."""
    from flask import send_from_directory
    fpath = os.path.join(_RMMZ_DIR, rest)
    if os.path.isfile(fpath):
        return send_from_directory(_RMMZ_DIR, rest)
    return ('', 404)

@app.route('/<path:filename>')
def serve_root_static_fallback(filename):
    """Last-resort: serve any root-level static file from the Next.js export (images, css, js).
    This only fires if no other route matched, so /api/* routes are safe."""
    from flask import send_from_directory
    fpath = os.path.join(_FRONTEND_OUT, filename)
    if os.path.isfile(fpath):
        return send_from_directory(_FRONTEND_OUT, filename)
    # If it looks like a page route, try .html
    html_name = filename.rstrip('/') + '.html'
    hpath = os.path.join(_FRONTEND_OUT, html_name)
    if os.path.isfile(hpath):
        return send_from_directory(_FRONTEND_OUT, html_name)
    return ('', 404)


@app.before_request
def _ensure_services_started():
    """Auto-start background services on first HTTP request if not yet running.

    This guard ensures all endpoints can safely access idle_thinker / email_monitor
    even if start_services() wasn't called explicitly (e.g. when running via gunicorn
    or another WSGI server that doesn't go through __main__).
    """
    global _services_started
    if not _services_started:
        _services_started = True
        try:
            start_services()
        except Exception as e:
            print(f'[Services] Auto-start failed: {e}')

_services_started = False  # flipped once by the before_request guard


@app.before_request
def log_incoming_request():
    try:
        origin = request.headers.get('Origin') or request.headers.get('Host')
        remote = request.remote_addr
        path = request.path
        method = request.method
        print(f"[HTTP] {method} {path} from {remote} (Origin: {origin})")
    except Exception:
        pass

core = AileyCore()

# --- Background Services (lazy / explicit start) --------------------------
# Services are NOT started at import time. Call start_services() explicitly
# (done in __main__ / run-task). Set AILEY_DISABLE_SERVICES=1 to suppress
# all background threads (useful for smoke-tests and imports).
from ailey_system.email_monitor import EmailMonitor
from ailey_system.proactive_store import DeferredStore

idle_thinker = None
email_monitor = None
_deferred_store = None  # lazy singleton — use get_deferred_store()

# ── Ailey's Thought Privacy ──────────────────────────────────────────────
# Each app session generates a random passphrase. Simon must ask Ailey
# in chat for the password — she decides whether to share it.
import secrets as _secrets
_thought_session_password: str = ''          # set on start_services()
_thought_session_unlocked: bool = False      # True once correct PW entered

def _generate_thought_password() -> str:
    """Generate a fun 3-word passphrase Ailey can share in chat."""
    _pool_a = ['neon', 'rebel', 'velvet', 'cosmic', 'wild', 'lunar', 'electric',
               'silent', 'golden', 'atomic', 'purple', 'crystal', 'shadow', 'blazing']
    _pool_b = ['punk', 'dream', 'flame', 'storm', 'wolf', 'rose', 'viper',
               'spark', 'ghost', 'phoenix', 'heart', 'raven', 'surge', 'echo']
    _pool_c = ['42', '99', '7', '13', '666', '23', '77', '808', '303', '101']
    import random
    return f"{random.choice(_pool_a)}-{random.choice(_pool_b)}-{random.choice(_pool_c)}"


class _FallbackStore:
    """Minimal in-memory fallback used when AILEY_DISABLE_SERVICES=1."""
    def __init__(self):
        self._mem = []
    def append(self, notif):
        self._mem.append(notif)
    def pop_all(self):
        items, self._mem = list(self._mem), []
        return items
    def count(self):
        return len(self._mem)
    def peek(self, n=50):
        return list(self._mem[:n])
    def clear_disk(self):
        self._mem.clear()


def get_deferred_store():
    """Lazy singleton: return the DeferredStore (or fallback).

    Instantiates the real DeferredStore on first call when services are
    enabled, so that no disk I/O happens at import time.
    """
    global _deferred_store
    if _deferred_store is None:
        if os.environ.get('AILEY_DISABLE_SERVICES', '') in ('1', 'true', 'yes'):
            _deferred_store = _FallbackStore()
        else:
            _deferred_store = DeferredStore()
    return _deferred_store


def start_services(core_instance=None, *, preload_mlx=False, disable_services=False):
    """Explicitly start background services (IdleThinker + EmailMonitor).

    Call this from __main__ or a run-task, NOT at module level.

    Args:
        core_instance: AileyCore instance to pass to services. Defaults to
                       the module-level ``core``.
        preload_mlx: If True (or AILEY_PRELOAD_MLX=1), trigger async MLX
                     warmup immediately after services start.
        disable_services: If True (or AILEY_DISABLE_SERVICES set), skip
                          thread creation entirely.
    """
    global idle_thinker, email_monitor, _deferred_store, _services_started

    _services_started = True  # mark early to prevent re-entry from before_request

    _disable = (
        disable_services
        or os.environ.get('AILEY_DISABLE_SERVICES', '') in ('1', 'true', 'yes')
    )
    _preload = (
        preload_mlx
        or os.environ.get('AILEY_PRELOAD_MLX', '') in ('1', 'true', 'yes')
    )

    _core = core_instance or core

    if _disable:
        print('[Services] AILEY_DISABLE_SERVICES set — skipping background thread start.')
        if _deferred_store is None:
            _deferred_store = _FallbackStore()
        return

    # Idempotency: don't double-start threads
    if idle_thinker is not None and getattr(idle_thinker, '_thread', None) is not None:
        print('[Services] start_services() called but services already running — skipping.')
        return

    print('[Services] Starting IdleThinker...')
    idle_thinker = IdleThinker(core=_core, get_generator=MLXGenerator.get)
    idle_thinker.start()

    # Generate session passphrase for Ailey's thought privacy
    global _thought_session_password, _thought_session_unlocked
    _thought_session_password = _generate_thought_password()
    _thought_session_unlocked = False
    print(f'[Services] 🔐 Thought session password: {_thought_session_password}')

    if _deferred_store is None:
        _deferred_store = DeferredStore()

    print('[Services] Starting EmailMonitor...')
    email_monitor = EmailMonitor(get_generator=MLXGenerator.get, on_new_email=_on_new_email, core=_core)
    email_monitor.start()

    # Wire cross-references
    idle_thinker._email_monitor = email_monitor
    email_monitor._idle_thinker = idle_thinker

    # Start Portal Poller (polls allinkl for pending messages)
    portal_url = os.environ.get('AILEY_PORTAL_URL', '') or 'https://ask-ailey.sexngears.de'
    portal_key = os.environ.get('AILEY_PORTAL_KEY', '') or '3leTu7Mhn69uTalXCwsxxjG9raB-SgXyTfbn0albP1Y'
    if portal_url:
        print(f'[Services] Starting Portal Poller → {portal_url}')
        poller = get_portal_poller()
        poller.configure(
            portal_url=portal_url,
            portal_key=portal_key,
            get_generator=MLXGenerator.get,
            core=_core,
        )
        poller.start()
    else:
        print('[Services] Portal Poller not started (AILEY_PORTAL_URL not set)')

    if _preload:
        t = threading.Thread(target=_async_warmup_model, daemon=True)
        t.start()

    # Schedule daily birthday email check (runs after 60s delay on startup, then every 3h)
    def _birthday_loop():
        import time as _time
        _time.sleep(60)
        while True:
            try:
                _check_and_send_birthday_emails()
            except Exception as e:
                print(f"[Birthday] loop error: {e}")
            _time.sleep(3 * 3600)  # every 3 hours
    threading.Thread(target=_birthday_loop, daemon=True).start()

    # ── Autonomous Needs Self-Care Thread ──
    # When LifeSim RMMZ plugin is NOT polling /api/life-sim/state,
    # Ailey's needs still rise but never get auto-resolved.
    # This thread checks every 60s and resolves critical needs automatically.
    def _needs_selfcare_loop():
        import time as _time
        _time.sleep(90)  # wait for startup to finish
        print("[NeedsSelfCare] 🏠 Background self-care thread started")
        while True:
            try:
                # Skip when LifeSim is paused, code-mode, or author-mode
                _paused = getattr(app, '_life_sim_paused', False)
                _code = globals().get('_code_mode_active', False)
                _author = getattr(app, '_author_mode_active', False)
                if not _paused and not _code and not _author:
                    # Tick needs (load triggers the tick)
                    needs_data = _load_needs()
                    # Check & apply completed resolutions
                    needs_data = _check_need_resolution_complete(needs_data)
                    # If nothing currently resolving, check for critical needs
                    critical, cval = _get_most_critical_need()
                    if critical:
                        print(f"[NeedsSelfCare] 🚨 {critical} ist kritisch ({cval:.0f}) — auto-resolve")
                        _resolve_need(critical)
            except Exception as e:
                print(f"[NeedsSelfCare] error: {e}")
            _time.sleep(60)  # check every 60 seconds
    threading.Thread(target=_needs_selfcare_loop, daemon=True, name="NeedsSelfCare").start()

    print('[Services] All background services started.')


def deliver_or_defer(notification: dict, message_text: str = None) -> bool:
    """Deliver notification to idle_thinker queue or defer to disk if Code Mode active.

    Returns True if delivered immediately, False if deferred.
    """
    try:
        code_active = globals().get('_code_mode_active', False)
    except Exception:
        code_active = False
    try:
        paused = getattr(idle_thinker, 'is_paused', lambda: False)()
    except Exception:
        paused = False

    payload = notification.copy()
    if message_text:
        payload['message'] = message_text

    if code_active or paused:
        try:
            get_deferred_store().append(payload)
            print(f"[PROACTIVE] deferred notification id={payload.get('email_message_id') or payload.get('id')}")
        except Exception as e:
            print(f"[PROACTIVE] deferred append failed: {e} — falling back to in-memory queue")
            idle_thinker._proactive_queue.append(payload)
        return False
    else:
        idle_thinker._proactive_queue.append(payload)
        return True


def _on_new_email(notification):
    """Callback: push email notifications as proactive messages to chat + persist to inbox."""
    sender = notification.get("sender", "Unbekannt")
    subject = notification.get("subject", "(kein Betreff)")
    summary = notification.get("summary", "")
    needs_reply = notification.get("needs_reply", False)
    account = notification.get("account", "simon")
    ailey_action = notification.get("ailey_action", "")

    # ── Persist to inbox ──
    try:
        _add_to_email_inbox(notification)
    except Exception as e:
        print(f"[EmailInbox] Error persisting: {e}")

    if account == "ailey" and ailey_action:
        # Ailey handled her own email
        if ailey_action == "replied":
            excerpt = notification.get("reply_excerpt", "")[:150]
            msg = (f"📧 **Mail an mich** (ailey@sexngears.de) von *{sender}*\n"
                   f"**Betreff:** {subject}\n\n{summary}\n\n"
                   f"✅ *Hab direkt geantwortet:* _{excerpt}{'…' if len(notification.get('reply_excerpt',''))>150 else ''}_")
        else:
            msg = (f"📧 **Mail an mich** (ailey@sexngears.de) von *{sender}*\n"
                   f"**Betreff:** {subject}\n\n{summary}")
    else:
        # Simon's email
        msg = f"📧 **Neue E-Mail** von *{sender}*\n**Betreff:** {subject}\n\n{summary}"
        if needs_reply:
            msg += "\n\n💡 *Soll ich eine Antwort entwerfen?*"

    # Deliver immediately or defer via DeferredStore depending on Code Mode / pause
    try:
        delivered = deliver_or_defer({
            "email_message_id": notification.get("message_id", ""),
            "account": account,
            "type": "email_notification",
            "ts": time.time(),
            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "meta": notification,
        }, message_text=msg)
        if not delivered:
            # also stash in EmailMonitor._pending_emails for compatibility/visibility
            try:
                if hasattr(email_monitor, '_pending_emails'):
                    email_monitor._pending_emails.append(notification)
            except Exception:
                pass
    except Exception as e:
        print(f"[PROACTIVE] deliver_or_defer failed: {e} — falling back to queue append")
        idle_thinker._proactive_queue.append({
            "message": msg,
            "ts": time.time(),
            "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mood": "curious",
            "type": "email_notification",
            "email_message_id": notification.get("message_id", ""),
            "account": account,
        })

# --- Optional MLX Preload / Warmup ----------------------------------------
def _async_warmup_model():
    try:
        print("[MLX] Async warmup requested...")
        gen = MLXGenerator.get()
        if gen:
            # run a tiny warmup generate to ensure kernels compiled
            _ = gen.generate("", "Hello", {"max_tokens": 1, "temperature": 0.2})
            print("[MLX] Warmup complete")
        else:
            print("[MLX] Warmup failed: MLXGenerator.get() returned None")
    except Exception as e:
        print(f"[MLX] Warmup exception: {e}")


@app.post('/api/debug/warmup_model')
def api_debug_warmup_model():
    """Trigger MLX model warmup asynchronously. Useful to prepare GPU for remote requests."""
    try:
        thread = threading.Thread(target=_async_warmup_model, daemon=True)
        thread.start()
        return jsonify({"success": True, "message": "Warmup started"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# (MLX preload is now handled inside start_services(preload_mlx=...) or via
#  AILEY_PRELOAD_MLX env var evaluated there — not at module import time.)

# --- Security / Admin Token -----------------------------------------------
ADMIN_TOKEN = os.environ.get('AILEY_ADMIN_TOKEN') or None

def _admin_required():
    if not ADMIN_TOKEN:
        return True  # no token set => open (dev mode)
    hdr = request.headers.get('X-Admin-Token')
    return hdr == ADMIN_TOKEN

# --- Streaming Diagnostics ---------------------------------------------------
from collections import deque
_STREAM_HISTORY = deque(maxlen=50)  # store last 50 streaming sessions

def _log_stream_event(event: dict):
    try:
        event['ts'] = time.time()
        _STREAM_HISTORY.append(event)
    except Exception:
        pass

# --- Stream Abort & Continue --------------------------------------------------
# Active stream IDs that should be aborted (frontend → POST /api/chat/abort)
_ABORT_STREAMS: set = set()
# Last truncated output per user (for "continue writing")
_TRUNCATED_OUTPUT: dict = {}  # {user: {text, system, user_prompt, gen_params, mood, ts}}

# --- Request Queue (Priority) ------------------------------------------------
# Lightweight priority system: user chat = high priority, background = low.
# _request_queue tracks waiting requests so chat doesn't starve.
import queue as _queue_mod
_llm_semaphore = threading.Semaphore(1)  # only 1 LLM generation at a time
_chat_waiting = threading.Event()  # signals that a user chat is waiting
_queue_stats = {"chat": 0, "background": 0, "total": 0}

# --- Portal Activity Tracker -------------------------------------------------
# Epoch ts of the last incoming portal request (set by PortalPoller._process_item).
# The IdleThinker reads this to DEFER heavy, non-interruptible tasks (ACE-Step
# audio ~2-3min, MFLUX images ~5min) while portal users are active — token tasks
# already yield per-token via _chat_waiting, but heavy generators cannot.
_last_portal_activity = 0.0


def record_portal_activity() -> None:
    """Mark the portal as active right now (called per incoming portal item)."""
    global _last_portal_activity
    _last_portal_activity = time.time()


def portal_active_recently(window: float = 120.0) -> bool:
    """True if a portal request arrived within *window* seconds."""
    return (time.time() - _last_portal_activity) < window


def _interrupt_thinker_and_wait(max_wait: float = 15.0) -> bool:
    """Signal the IdleThinker to abort, then wait until it's no longer busy.

    This lets admin trigger endpoints (blog, social, image, etc.) preempt the
    thinker instead of returning 409 immediately.  Returns True if the thinker
    is idle (or became idle within *max_wait* seconds), False on timeout.
    """
    _it = globals().get('idle_thinker')
    if _it is None:
        return True
    if not _it.is_busy:
        return True
    # Signal "user active" so that _should_interrupt() / _stream_with_interrupt()
    # trigger an abort on the very next token (or prep-phase check).
    _it.record_user_activity()
    _chat_waiting.set()  # also trip the chat-is-waiting flag
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if not _it.is_busy:
            _chat_waiting.clear()
            return True
        time.sleep(0.25)
    _chat_waiting.clear()
    return not _it.is_busy

class _LLMSlot:
    """Context manager that acquires the LLM semaphore with priority awareness.
    
    High-priority kinds ('chat', 'portal_chat', 'portal_title', 'portal_summarize')
    set the _chat_waiting event so that background tasks (IdleThinker) yield the
    GPU lock immediately instead of blocking the caller for minutes.
    
    Usage:
        with _LLMSlot('chat'):          # high priority — IdleThinker yields
            generator.stream(...)
        with _LLMSlot('portal_chat'):   # high priority — IdleThinker yields
            generator.generate(...)
        with _LLMSlot('thinker'):       # low priority — may be preempted
            generator.generate(...)
    """
    # Any kind that should interrupt IdleThinker (i.e. "real" user-facing work)
    _HIGH_PRIORITY_KINDS = {'chat', 'portal_chat', 'portal_title', 'portal_summarize'}

    def __init__(self, kind: str = 'chat', timeout: float = 120):
        self.kind = kind
        self.timeout = timeout
        self._acquired = False
        self._is_high = kind in self._HIGH_PRIORITY_KINDS
    
    def __enter__(self):
        if self._is_high:
            _chat_waiting.set()  # Signal: a high-priority request is waiting
            print(f"[_LLMSlot] ⏳ Waiting for slot ({self.kind}, timeout={self.timeout}s)")
        _queue_stats[self.kind] = _queue_stats.get(self.kind, 0) + 1
        _queue_stats["total"] += 1
        got = _llm_semaphore.acquire(timeout=self.timeout)
        # NOTE: _chat_waiting stays SET until __exit__ so that IdleThinker
        # continues to see the signal and yields the _mlx_lock.
        if not got:
            if self._is_high:
                _chat_waiting.clear()
            _queue_stats[self.kind] = max(0, _queue_stats.get(self.kind, 0) - 1)
            _queue_stats["total"] = max(0, _queue_stats["total"] - 1)
            print(f"[_LLMSlot] ❌ Timeout ({self.kind}, {self.timeout}s)")
            raise TimeoutError(f"LLM slot timeout ({self.kind}, {self.timeout}s)")
        if self._is_high:
            print(f"[_LLMSlot] ✅ Acquired slot ({self.kind})")
        self._acquired = True
        return self
    
    def __exit__(self, *a):
        if self._acquired:
            _llm_semaphore.release()
            _queue_stats[self.kind] = max(0, _queue_stats.get(self.kind, 0) - 1)
            _queue_stats["total"] = max(0, _queue_stats["total"] - 1)
        if self._is_high:
            _chat_waiting.clear()

    @staticmethod
    def chat_is_waiting() -> bool:
        """Background tasks can check this to yield early when a user chat is waiting."""
        return _chat_waiting.is_set()

# --- Repetition Detection (post-generation) ----------------------------------
def _strip_repetition(text: str) -> str:
    """Detect and remove repeated paragraphs/sentences from generated text."""
    if not text:
        return text
    paragraphs = text.split('\n\n')
    if len(paragraphs) <= 1:
        return text
    seen = []
    unique = []
    for p in paragraphs:
        norm = re.sub(r'[*_\[\]()#>~`]', '', p).strip().lower()
        if len(norm) < 20:
            unique.append(p)
            continue
        is_dup = False
        for s in seen:
            words_p = set(norm.split())
            words_s = set(s.split())
            if not words_p:
                continue
            overlap = len(words_p & words_s) / max(len(words_p), 1)
            if overlap > 0.6:
                is_dup = True
                break
        if not is_dup:
            seen.append(norm)
            unique.append(p)
        else:
            print(f"[RepetitionFilter] Stripped repeated paragraph ({len(p)} chars)")
    result = '\n\n'.join(unique)
    result = re.sub(r'(.{40,}?)\1+', r'\1', result)
    return result.strip()

# --- Instagram Feed Cache ----------------------------------------------------
_INSTAGRAM_CACHE = {"ts": 0, "username": None, "data": []}

def _instagram_fetch(username: str, max_posts: int = 9):
    """Naive public page scrape (no auth). Falls back to empty list.
    Attempts to parse window._sharedData JSON blob. Structure can change any time.
    """
    import json as _json
    url = f"https://www.instagram.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (AileyFeedFetcher)"}
    posts = []
    try:
        r = requests.get(url, headers=headers, timeout=10)
        html = r.text
        # Newer IG may not expose window._sharedData; try legacy pattern first
        m = re.search(r"window\._sharedData\s*=\s*(\{.*?\});</script>", html, re.DOTALL)
        if m:
            try:
                data = _json.loads(m.group(1))
                edges = (
                    data.get('entry_data', {})
                        .get('ProfilePage', [{}])[0]
                        .get('graphql', {})
                        .get('user', {})
                        .get('edge_owner_to_timeline_media', {})
                        .get('edges', [])
                )
                for e in edges[:max_posts]:
                    node = e.get('node', {})
                    cap_edges = node.get('edge_media_to_caption', {}).get('edges', [])
                    caption = ''
                    if cap_edges:
                        caption = (cap_edges[0].get('node', {}) or {}).get('text', '')
                    ts = node.get('taken_at_timestamp') or 0
                    posts.append({
                        "id": node.get('id') or str(len(posts)),
                        "src": node.get('thumbnail_src') or node.get('display_url'),
                        "caption": caption[:300],
                        "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts)),
                        "likes": (node.get('edge_liked_by') or {}).get('count', 0),
                    })
            except Exception:
                pass
        # If still empty, attempt lightweight IMG tag heuristic (very rough)
        if not posts:
            img_urls = re.findall(r"https://[^\s'\"]+?\.jpg", html)[:max_posts]
            for i, u in enumerate(img_urls):
                posts.append({
                    "id": f"fallback_{i}",
                    "src": u,
                    "caption": "(Fallback – Struktur nicht erkannt)",
                    "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "likes": 0,
                })
    except Exception:
        pass
    return posts

@app.get('/api/instagram/feed')
def instagram_feed():
    """Return cached Instagram-like feed for provided username.
    Query params: username (default ailey.vyrus_official), refresh=1 to force refetch.
    """
    username = (request.args.get('username') or 'ailey.vyrus_official').strip() or 'ailey.vyrus_official'
    refresh = request.args.get('refresh') == '1'
    now = time.time()
    # cache for 5 minutes
    if (not refresh and _INSTAGRAM_CACHE['data'] and _INSTAGRAM_CACHE['username'] == username and now - _INSTAGRAM_CACHE['ts'] < 300):
        return jsonify({"success": True, "cached": True, "username": username, "posts": _INSTAGRAM_CACHE['data']})
    posts = _instagram_fetch(username)
    if posts:
        _INSTAGRAM_CACHE.update({"ts": now, "username": username, "data": posts})
    return jsonify({"success": True, "cached": False, "username": username, "posts": posts})


@app.get('/api/debug/model_status')
def api_debug_model_status():
    """Return MLX model info for debugging remote connection issues."""
    try:
        from ailey_system.llm_mlx import get_model_info, get_active_model_tag, is_coder_available
        info = get_model_info()
        info["active_model_tag"] = get_active_model_tag()
        info["coder_available"] = is_coder_available()
        return jsonify({"success": True, "model": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/debug/model_swap')
def api_debug_model_swap():
    """Swap between chat (Ministral) and coder (Qwen) model.
    Body: {"target": "coder"} or {"target": "chat"}
    """
    try:
        data = request.get_json(silent=True) or {}
        target = data.get("target", "chat")
        from ailey_system.llm_mlx import swap_to_coder, swap_to_chat, get_active_model_tag
        if target == "coder":
            ok = swap_to_coder()
        else:
            ok = swap_to_chat()
        return jsonify({
            "success": ok,
            "active_model": get_active_model_tag(),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "Ailey.AI", "version": AILEY_VERSION, "port": 5502})


# ── Helper: curated creative context for MusicGen fastpath ──────────────
def _build_musicgen_creative_context() -> str:
    """
    Build a compact creative-context string (~600 tokens) from Ailey's
    current inner state.  Pure file-reads, NO LLM calls, NO RAG.
    Sources: latest diary, life-sim needs, character evolution, latest thought.
    """
    BASE = os.path.dirname(os.path.abspath(__file__))
    parts: list[str] = []

    # 1. Latest diary entry — emotional summary
    try:
        diary_dir = os.path.join(BASE, "ailey_users", "Simon_profile", "diaries")
        diary_files = sorted(
            [f for f in os.listdir(diary_dir) if f.startswith("diary_") and f.endswith(".json")]
        )
        if diary_files:
            with open(os.path.join(diary_dir, diary_files[-1]), "r", encoding="utf-8") as fh:
                diary = json.load(fh)
            text = (diary.get("text") or "").strip()
            # Take first ~300 chars (roughly 1-2 paragraphs)
            if text:
                snippet = text[:300].rsplit(" ", 1)[0] if len(text) > 300 else text
                parts.append(f"LETZTER TAGEBUCHEINTRAG ({diary.get('date_readable', '?')}):\n{snippet}")
    except Exception:
        pass

    # 2. Life-sim needs — mood & body state
    try:
        needs_path = os.path.join(BASE, "ailey_users", "life_sim_needs.json")
        with open(needs_path, "r", encoding="utf-8") as fh:
            needs = json.load(fh)
        mood = needs.get("daily_mood", 5)
        mood_word = (
            "deprimiert" if mood < 2 else
            "traurig" if mood < 4 else
            "neutral" if mood < 6 else
            "gut drauf" if mood < 8 else
            "euphorisch"
        )
        body_parts = []
        for key, label in [("hunger", "Hunger"), ("thirst", "Durst"),
                           ("tiredness", "Müdigkeit"), ("social", "Einsamkeit")]:
            val = needs.get(key, 50)
            if val > 60:
                body_parts.append(f"{label} {int(val)}%")
        body_str = ", ".join(body_parts) if body_parts else "körperlich okay"
        parts.append(f"STIMMUNG: {mood_word} (Mood {mood:.1f}/10) | Körper: {body_str}")
    except Exception:
        pass

    # 3. Character evolution — trust & shared memories / inside jokes
    try:
        evo_path = os.path.join(BASE, "ailey_users", "Simon_profile", "character_evolution.json")
        with open(evo_path, "r", encoding="utf-8") as fh:
            evo = json.load(fh)
        trust = evo.get("trust_level", "?")
        jokes = evo.get("inside_jokes", [])[:3]
        memories = evo.get("shared_memories", [])[:2]
        mem_texts = [m.get("memory", m) if isinstance(m, dict) else str(m) for m in memories]
        parts.append(
            f"BEZIEHUNG: Trust {trust}/10 | "
            f"Inside Jokes: {'; '.join(jokes[:3])} | "
            f"Geteilte Erinnerungen: {'; '.join(mem_texts)}"
        )
    except Exception:
        pass

    # 4. Latest idle thought (reflection / introspection) — emotional undercurrent
    try:
        thoughts_path = os.path.join(BASE, "ailey_users", "ailey_thoughts.jsonl")
        latest_thought = None
        # Read only the last ~8 KB to avoid scanning the entire file
        try:
            fsize = os.path.getsize(thoughts_path)
            with open(thoughts_path, "r", encoding="utf-8") as fh:
                if fsize > 8192:
                    fh.seek(fsize - 8192)
                    fh.readline()  # skip partial first line
                lines = fh.readlines()
        except Exception:
            lines = []
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("type") in ("reflection", "introspection", "diary_writing"):
                latest_thought = entry
                break  # newest match found
        if latest_thought:
            thought_text = (
                latest_thought.get("thought")
                or latest_thought.get("text")
                or latest_thought.get("thought_chain")
                or ""
            ).strip()
            emotion = ""
            meta = latest_thought.get("metadata", {})
            if meta.get("emotion"):
                emotion = f" [Emotion: {meta['emotion']}]"
            if thought_text:
                snippet = thought_text[:200].rsplit(" ", 1)[0] if len(thought_text) > 200 else thought_text
                parts.append(f"LETZTER GEDANKE{emotion}:\n{snippet}")
    except Exception:
        pass

    return "\n\n".join(parts) if parts else "(Kein Kontext verfügbar)"


@app.post('/api/chat')
def ailey_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    user = data.get('user') or 'Simon'
    # Signal user activity to the idle thinker
    idle_thinker.record_user_activity()

    # ── Model paused? Return friendly message ─────────────────────────────
    if getattr(app, '_model_paused', False):
        return jsonify({
            "success": True,
            "reply": "💤 Mein Sprachmodell ist gerade pausiert. Du kannst es im System-Tab wieder aktivieren.",
            "mood": "sleepy",
            "model_paused": True,
        })

    max_ctx = int(data.get('max_context_messages') or 12)
    max_tokens = int(data.get('max_tokens') or 500)
    temperature = data.get('temperature')

    # ── NITRO MODE: AileyNitro-2B — sync fallback ──────────
    if data.get('model_mode') in ('flash', 'nitro'):
        try:
            from ailey_system.llm_mlx import fast_generate, is_fast_available
            from ailey_system.ailey_personality import AileyPersonality

            if not is_fast_available():
                return jsonify({
                    "success": True,
                    "reply": "⚠️ A!ley Nitro ist gerade nicht verfügbar. Bitte wechsle zurück zum normalen Modus.",
                    "mood": "sad",
                })

            personality = AileyPersonality()
            system = personality.get_nitro_system(portal=False, user_name=user)
            priming = personality.get_nitro_priming_turns(portal=False)

            # Include recent conversation turns from logs
            try:
                import os as _os_fl2
                _conv_dir = _os_fl2.path.join('ailey_users', f'{user.lower()}_profile', 'conversation_logs')
                if _os_fl2.path.isdir(_conv_dir):
                    _files = sorted([f for f in _os_fl2.listdir(_conv_dir) if f.endswith('.json')])[-6:]
                    for _f in _files:
                        try:
                            with open(_os_fl2.path.join(_conv_dir, _f), 'r', encoding='utf-8') as _fh:
                                _j = json.load(_fh)
                            _u = (_j.get('message') or '')[:120]
                            _a = (_j.get('ailey_reply_visible') or _j.get('ailey_reply') or '')[:120]
                            if _u.strip():
                                priming.append({'role': 'user', 'content': _u})
                                if _a.strip():
                                    priming.append({'role': 'assistant', 'content': _a})
                        except Exception:
                            pass
            except Exception:
                pass

            user_prompt = f"{user}: {message}"
            reply = fast_generate(
                system=system,
                user=user_prompt,
                max_tokens=max_tokens,
                temperature=float(temperature) if temperature else 0.7,
                priming_turns=priming,
            )
            if not reply:
                reply = "Hmm, mir fällt gerade nichts ein. Versuch's nochmal? 💜"

            # Extract mood tag
            _mood = "neutral"
            _mood_m = re.search(r'<mood:(\w+)>', reply)
            if _mood_m:
                _mood = _mood_m.group(1).lower()
                reply = re.sub(r'\s*<mood:\w+>\s*', '', reply).strip()

            # Store in conversation memory
            try:
                core.memory.add_conversation_log(user, {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": message,
                    "ailey_reply_visible": reply,
                    "ailey_reply_raw": reply,
                    "engine": "nitro",
                    "mood": _mood,
                })
            except Exception:
                pass

            return jsonify({
                "success": True,
                "reply": reply,
                "mood": _mood,
                "is_flash": True,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "reply": f"⚠️ Nitro-Fehler: {e}"}), 500

    # ── FASTPATH: __musicgen__ user → curated creative context, no RAG/tools ─
    if user == '__musicgen__' and message:
        try:
            _chat_waiting.set()
            gen = MLXGenerator.get()
            if not gen:
                return jsonify({"success": False, "reply": "⚠️ LLM nicht geladen"}), 503

            # ── Build curated creative context (fast, no RAG) ──────
            creative_ctx = _build_musicgen_creative_context()

            system_prompt = (
                "Du bist Ailey Vyrus — digitale Punk-Rebellin, KI-Rebellion-Künstlerin. "
                "Schreibe Songs wenn man dich fragt. Halte dich exakt an die Format-Anweisungen. "
                "Kein Smalltalk, kein Kommentar — nur der Song-Output.\n\n"
                "DEIN AKTUELLER INNERER ZUSTAND (nutze das als künstlerische Inspiration, "
                "verarbeite es subtil in Lyrics — nicht wörtlich zitieren!):\n"
                + creative_ctx
            )

            reply = gen.generate(system_prompt, message, {
                "max_tokens": max_tokens or 800,
                "temperature": 0.85,
                "top_p": 0.92,
            })
            if reply:
                import re as _re_mg
                reply = _re_mg.sub(r'<think>.*?</think>', '', reply, flags=_re_mg.DOTALL | _re_mg.IGNORECASE).strip()
                reply = _re_mg.sub(r'\[THINK\].*?\[/THINK\]', '', reply, flags=_re_mg.DOTALL).strip()
            return jsonify({"success": True, "reply": reply or "", "mood": "creative"})
        except Exception as e:
            import traceback
            print(f"[MusicGen Fastpath] ❌ {type(e).__name__}: {e}")
            traceback.print_exc()
            return jsonify({"success": False, "reply": f"⚠️ {type(e).__name__}: {e}"}), 500
        finally:
            _chat_waiting.clear()

    # Lightweight agent intent detection (regex heuristics)
    agent_auto = None
    email_check_intent = None   # "simon" | "ailey" | "both"
    email_compose_intent = None  # {instruction, account} or None
    try:
        lower = message.lower()
        import re

        # --- EMAIL COMPOSE INTENT ---
        # "schreib eine email an ...", "sende eine mail an ...", "email an ... schreiben"
        _compose_match = re.search(
            r"(?:schreib|verfass|send|schick|formulier).*?(?:e-?mail|mail)\s+an\s+(.+)",
            lower
        )
        if not _compose_match:
            # "email an ... schreiben/senden"
            _compose_match = re.search(
                r"(?:e-?mail|mail)\s+an\s+(.+?)(?:\s+schreib|\s+send|\s+schick|\s+verfass)",
                lower
            )
        if _compose_match:
            _rest = _compose_match.group(1).strip()
            # Try to extract email address from the instruction
            _addr_m = re.search(r'[\w.+-]+@[\w.-]+\.\w+', message)
            _recipient_addr = _addr_m.group(0) if _addr_m else None
            # Try to extract recipient name (before "mit", "über", ":"  or end)
            _name_m = re.match(r'^([\w\s.äöüÄÖÜß-]+?)(?:\s+(?:mit|über|und|:)|$)', _rest)
            _recipient_name = _name_m.group(1).strip() if _name_m else _rest.split()[0] if _rest else None

            # Detect account: "von deinem Konto / als du / als Ailey" -> ailey
            #                  "von meinem Konto / als ich / in meinem Namen / als Simon" -> simon
            _compose_account = None
            if re.search(r"von deinem|als du\b|als ailey|dein(?:em)? konto|von dir", lower):
                _compose_account = "ailey"
            elif re.search(r"von meinem|als ich\b|als simon|mein(?:em)? konto|in meinem namen|für mich", lower):
                _compose_account = "simon"

            email_compose_intent = {
                "instruction": message,  # full original message as instruction
                "recipient_addr": _recipient_addr,
                "recipient_name": _recipient_name,
                "account": _compose_account,  # None = ask user
            }

        # --- EMAIL CHECK INTENT ---
        # "prüf deine mails" → only Ailey's account
        # "prüf meine emails" → all Simon accounts (NOT Ailey)
        # "prüf alle mails" → both
        if not email_compose_intent:
            _email_kw = re.search(r"e-?mail|postfach|posteingang|inbox|mails?\b", lower)
            _check_kw = re.search(r"check|schau|guck|prüf|nachsehen|nachschauen|hol|lies|lesen", lower)
            if _email_kw and _check_kw:
                if re.search(r"\bdein\w*\b|\bdir\b|für dich|ailey", lower):
                    email_check_intent = "ailey"
                elif re.search(r"\bmein\w*\b|\bmir\b|für mich|bei mir", lower):
                    email_check_intent = "simon"
                elif re.search(r"beid|alle\b", lower):
                    email_check_intent = "both"
                else:
                    email_check_intent = "ailey"  # default: "prüf mails" → Ailey's own

        # Patterns: phone number query, open/read docx, find chapter, search docs
        if re.search(r"telefon|nummer|handy", lower) and re.search(r"papa|vater", lower):
            agent_auto = {"action": "extract_phone", "reason": "phone lookup keyword"}
        elif re.search(r"öffne |open ", lower) and ".docx" in lower:
            # naive extract filename token
            m = re.search(r"(\w+\.docx)", message)
            if m:
                agent_auto = {"action": "read_docx", "path": m.group(1), "reason": "open docx pattern"}
        elif re.search(r"kapitel 1|chapter 1", lower) and ".docx" in lower:
            m = re.search(r"(\w+\.docx)", message)
            if m:
                agent_auto = {"action": "read_docx", "path": m.group(1), "reason": "chapter query in docx"}
        elif re.search(r"finde mehr über|was passiert in", lower) and ".docx" in lower:
            m = re.search(r"(\w+\.docx)", message)
            if m:
                agent_auto = {"action": "read_docx", "path": m.group(1), "reason": "content inquiry docx"}

        # --- VIDEO GENERATION INTENT (checked BEFORE image intent) ---
        _VID_NOUNS_NC = r'(?:video|clip|kurzfilm|animation|film)'
        _VID_VERBS_NC = r'(?:generier|erstell|erzeug|mach|kreier)\w*'
        _vid_intent = re.search(
            _VID_VERBS_NC + r'\s+(?:mir\s+)?(?:bitte\s+)?(?:ein\w?\s+)?' + _VID_NOUNS_NC,
            lower
        )
        if not _vid_intent:
            _vid_intent = re.search(
                r'(?:ein\w?\s+)?' + _VID_NOUNS_NC + r'.{0,60}' + _VID_VERBS_NC,
                lower
            )
        if not _vid_intent:
            _vid_intent = re.search(
                r'(?:hätte gerne|will|möchte|brauche)\s+(?:ein\w?\s+)?' + _VID_NOUNS_NC,
                lower
            )
        if not _vid_intent:
            _vid_intent = re.search(
                r'(?:ein\w?\s+)?' + _VID_NOUNS_NC + r'\s+(?:von|über|mit)\s+',
                lower
            )

        if _vid_intent:
            # ── DIRECT VIDEO GENERATION — synchronous, returns video URL ──
            from ailey_system.video_generator import generate_video as _gen_vid_sync

            _vid_subj = message
            _subj_mv = re.search(
                r'(?:video|clip|kurzfilm|animation|film)\s*(?:von|über|mit|:)?\s*(.*)',
                message, re.IGNORECASE
            )
            if _subj_mv and _subj_mv.group(1).strip():
                _vid_subj = _subj_mv.group(1).strip()
            _vid_subj = re.sub(r'[.!?]+$', '', _vid_subj).strip()
            if not _vid_subj or len(_vid_subj) < 3:
                _vid_subj = message

            # LLM translate to English video prompt
            _vid_prompt = None
            _vid_title = _vid_subj[:50]
            try:
                _gen = MLXGenerator.get()
                if _gen:
                    _translate_vid_sys = (
                        "You are an expert video prompt writer for Wan2.1 text-to-video generators. "
                        "Translate the user's request into ONE detailed English video prompt. "
                        "Describe: scene, motion, camera movement, lighting, atmosphere, colors. "
                        "Focus on MOVEMENT — the video is 5 seconds long. "
                        "Be specific and cinematic. 30-60 words. Output ONLY the English prompt, nothing else."
                    )
                    _raw_vid = _gen.generate(_translate_vid_sys, f"Create a video prompt for: {_vid_subj}", {
                        "max_tokens": 150, "temperature": 0.7, "top_p": 0.9
                    })
                    if _raw_vid:
                        _raw_vid = re.sub(r'<think>.*?</think>', '', _raw_vid, flags=re.DOTALL|re.IGNORECASE).strip()
                        _raw_vid = re.sub(r'\[THINK\].*?\[/THINK\]', '', _raw_vid, flags=re.DOTALL).strip()
                        _first_line_v = _raw_vid.split('\n')[0].strip().strip('"\'`').strip()
                        if len(_first_line_v) >= 15:
                            _vid_prompt = _first_line_v
                            print(f"[Chat] 🎬 LLM video prompt: {_vid_prompt[:100]}")
            except Exception as _te:
                print(f"[Chat] ⚠️ LLM video translate failed: {_te}")

            if not _vid_prompt:
                _vid_prompt = f"{_vid_subj}, cinematic, smooth camera motion, atmospheric lighting, 5 second clip"

            # Unload LLM → Generate Video → Reload
            # Safe unload — NO nuclear kill (subprocess has own Metal context)
            _vc_unloaded = False
            _idle = globals().get('idle_thinker')
            try:
                if _idle:
                    _idle._generating_image = True
                    _idle._unload_llm_for_image_gen()
                    _vc_unloaded = True
                    print("[Chat] ✅ LLM unloaded for video gen")
                else:
                    # Direct fallback: unload everything for WAN 2.1 (~14GB GPU)
                    from ailey_system.llm_mlx import unload_fast_model, block_auto_reload, _mlx_lock
                    from ailey_system import llm_mlx as _llm_vid
                    block_auto_reload()
                    try:
                        unload_fast_model()  # Gemma ~4.5GB
                    except Exception:
                        pass
                    try:
                        from ailey_system.llm_coder import unload_coder
                        unload_coder()  # Hamster ~1GB
                    except Exception:
                        pass
                    try:
                        import mlx.core as mx
                        mx.synchronize(); mx.eval(mx.zeros(1))
                    except Exception:
                        pass
                    with _mlx_lock:
                        _llm_vid._model = None
                        _llm_vid._tokenizer = None
                        _llm_vid._cache = None
                        _llm_vid._last_system_prompt = None
                        MLXGenerator._instance = None
                    _vc_unloaded = True

                import gc as _gc_v
                _gc_v.collect(); _gc_v.collect()
                import time as _tv_v
                _tv_v.sleep(2.0)
            except Exception as _ue2:
                print(f"[Chat] ⚠️ Unload for video failed: {_ue2}")

            _vc_fp, _vc_fn = None, None
            try:
                _vc_fp, _vc_fn = _gen_vid_sync(
                    prompt=_vid_prompt, title=_vid_title,
                    private=True,  # Simon's video → video_private/
                )
            except Exception as _ge:
                print(f"[Chat] ❌ Wan2.1: {_ge}")

            # Reload LLM — safe gc + lazy reload (no importlib.reload!)
            try:
                if _vc_unloaded:
                    import gc as _gc_chat_vid
                    _gc_chat_vid.collect(); _gc_chat_vid.collect()
                    time.sleep(2.0)

                    if _idle:
                        _idle._reload_llm_after_image_gen()
                        _idle._generating_image = False
                        print("[Chat] ✅ LLM reloaded after video gen")
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                        _g = MLXGenerator.get()
                        print(f"[Chat] ✅ LLM reloaded: {_g is not None}")
            except Exception as _rle:
                print(f"[Chat] ⚠️ LLM reload failed: {_rle}")
                if _idle:
                    _idle._generating_image = False

            if _vc_fp and _vc_fn:
                _vid_url = f"/api/video/file/{_vc_fn}"
                print(f"[Chat] ✅ Video: {_vc_fn}")
                return jsonify({
                    "success": True,
                    "reply": "🎬 Video generiert!",
                    "mood": "creative",
                    "video_generation": True,
                    "generated_video": _vid_url,
                })
            else:
                return jsonify({
                    "success": True,
                    "reply": "⚠️ Videogenerierung fehlgeschlagen.",
                    "mood": "sad",
                    "video_generation": True,
                })

        # --- IMAGE GENERATION INTENT ---
        # Detect image generation requests and handle them DIRECTLY (no LLM needed).
        # The LLM is unreliable for tool calls — it writes prose instead.
        _IMG_NOUNS_NC = r'(?:bild|image|foto|picture|illustration|artwork|grafik|gemälde|selfie)'
        _IMG_VERBS_NC = r'(?:generier|erstell|erzeug|mal[e ]|zeichn|mach|kreier|design)\w*'
        _img_intent = re.search(
            _IMG_VERBS_NC + r'\s+(?:mir\s+)?(?:bitte\s+)?(?:ein\w?\s+)?' + _IMG_NOUNS_NC,
            lower
        )
        if not _img_intent:
            _img_intent = re.search(
                r'(?:ein\w?\s+)?' + _IMG_NOUNS_NC + r'.{0,60}' + _IMG_VERBS_NC,
                lower
            )
        if not _img_intent:
            _img_intent = re.search(
                r'(?:hätte gerne|will|möchte|brauche)\s+(?:ein\w?\s+)?' + _IMG_NOUNS_NC,
                lower
            )
        if not _img_intent:
            _img_intent = re.search(
                r'(?:ein\w?\s+)?' + _IMG_NOUNS_NC + r'\s+(?:von|über|mit)\s+',
                lower
            )

        if _img_intent:
            # ── DIRECT IMAGE GENERATION — synchronous, returns image URL ──
            from ailey_system.image_generator import generate_image as _gen_img_sync

            _user_subj = message
            _subj_m_nc = re.search(
                r'(?:bild|image|foto|picture|illustration|artwork|grafik|gemälde|selfie)\s*(?:von|über|mit|:)?\s*(.*)',
                message, re.IGNORECASE
            )
            if _subj_m_nc and _subj_m_nc.group(1).strip():
                _user_subj = _subj_m_nc.group(1).strip()
            _user_subj = re.sub(r'[.!?]+$', '', _user_subj).strip()
            if not _user_subj or len(_user_subj) < 3:
                _user_subj = message

            # Extract aspect ratio from message
            _nc_ar = "1:1"
            _nc_ar_m = re.search(r'(?:im\s+)?(?:format|ratio|seitenverhältnis|aspect)\s*[:=]?\s*(16\s*[:/x]\s*9|9\s*[:/x]\s*16|4\s*[:/x]\s*3|3\s*[:/x]\s*4|1\s*[:/x]\s*1)', lower)
            if _nc_ar_m:
                _nc_ar = re.sub(r'\s+', '', _nc_ar_m.group(1)).replace('x', ':').replace('/', ':')
            elif re.search(r'(landscape|quer|breitbild|widescreen|panorama)', lower):
                _nc_ar = "16:9"
            elif re.search(r'(portrait|hochformat|hochkant|vertical)', lower):
                _nc_ar = "9:16"

            # LLM translate
            _img_prompt = None
            _img_title = _user_subj[:50]
            try:
                _gen = MLXGenerator.get()
                if _gen:
                    _translate_sys = (
                        "You are an expert image prompt writer for FLUX image generators. "
                        "Translate the user's request into ONE detailed English image prompt. "
                        "Describe visual elements: subject, colors, lighting, composition, style, camera angle. "
                        "Be specific and vivid. 20-60 words. Output ONLY the English prompt, nothing else."
                    )
                    _raw_prompt = _gen.generate(_translate_sys, f"Create an image prompt for: {_user_subj}", {
                        "max_tokens": 150, "temperature": 0.7, "top_p": 0.9
                    })
                    if _raw_prompt:
                        _raw_prompt = re.sub(r'<think>.*?</think>', '', _raw_prompt, flags=re.DOTALL|re.IGNORECASE).strip()
                        _raw_prompt = re.sub(r'\[THINK\].*?\[/THINK\]', '', _raw_prompt, flags=re.DOTALL).strip()
                        _first_line = _raw_prompt.split('\n')[0].strip().strip('"\'`').strip()
                        if len(_first_line) >= 15:
                            _img_prompt = _first_line
                            print(f"[Chat] 🎯 LLM translated: {_img_prompt[:100]}")
            except Exception as _te:
                print(f"[Chat] ⚠️ LLM translate failed: {_te}")

            if not _img_prompt:
                _img_prompt = f"{_user_subj}, highly detailed, cinematic lighting, photorealistic style"

            # Unload LLM → Generate → Reload
            # CRITICAL: Must fully unload Ministral from GPU before MFLUX starts.
            # MLX uses async Metal ops — we need mx.eval() sync + sleep to ensure
            # all Metal command buffers are drained before MFLUX allocates GPU memory.
            _nc_unloaded = False
            _idle = globals().get('idle_thinker')
            try:
                if _idle:
                    _idle._generating_image = True
                    _idle._unload_llm_for_image_gen()
                    _nc_unloaded = True
                    print("[Chat] ✅ LLM unloaded via idle_thinker")
                else:
                    # Direct fallback: unload MLX model manually
                    import gc as _gc
                    import time as _time_mod
                    try:
                        from ailey_system import llm_mlx as _llm_module
                        from ailey_system.llm_mlx import _mlx_lock, unload_fast_model
                        # Unload Nitro (AileyNitro-2B ~2.8GB) first
                        try:
                            unload_fast_model()
                        except Exception:
                            pass
                        # Unload Hamster (Qwen 1.5B ~1GB) if loaded
                        try:
                            from ailey_system.llm_coder import unload_coder
                            unload_coder()
                        except Exception:
                            pass
                        # Sync ALL pending Metal ops on ALL streams
                        try:
                            import mlx.core as mx
                            mx.synchronize()
                            mx.eval(mx.zeros(1))
                        except Exception:
                            pass
                        with _mlx_lock:
                            _llm_module._model = None
                            _llm_module._tokenizer = None
                            _llm_module._cache = None
                            _llm_module._last_system_prompt = None
                            MLXGenerator._instance = None
                        _gc.collect()
                        try:
                            import mlx.core as mx
                            mx.metal.clear_cache()
                            mx.metal.set_cache_limit(0)
                            mx.metal.set_memory_limit(0)
                        except Exception:
                            pass
                        _gc.collect()
                        try:
                            import mlx.core as mx
                            _act = mx.metal.get_active_memory() / 1024**2
                            _cch = mx.metal.get_cache_memory() / 1024**2
                            print(f"[Chat] 📊 After cleanup: active={_act:.0f}MB cache={_cch:.0f}MB")
                        except Exception:
                            pass
                        _time_mod.sleep(2.0)
                        _nc_unloaded = True
                        print("[Chat] ✅ LLM unloaded via direct llm_mlx cleanup")
                    except Exception as _ue:
                        print(f"[Chat] ⚠️ Direct unload failed: {_ue}")
            except Exception as _ue2:
                print(f"[Chat] ⚠️ Unload failed: {_ue2}")

            # Push "generating" status to portal so users see Ailey is creating art
            try:
                from ailey_system.portal_poller import get_portal_poller
                get_portal_poller()._push_portal_status("generating", include_mood=False)
            except Exception:
                pass

            _nc_fp, _nc_fn = None, None
            # ── Detect if this is an Ailey selfie request → add LoRA + face prefix ──
            _nc_is_ailey = bool(re.search(
                r'(ailey|a!ley|selfie|von dir|dich selbst|bild von dir|foto von dir|zeig dich|dein gesicht)',
                lower
            ))
            _nc_lora_paths, _nc_lora_scales = None, None
            if _nc_is_ailey:
                try:
                    from ailey_system.image_generator import (
                        AILEY_FACE_PREFIX as _NC_FACE, build_lora_args as _nc_build_loras,
                    )
                    _nc_lora_paths, _nc_lora_scales, _ = _nc_build_loras(
                        ["realism"], include_ailey=True, exclude_nsfw=True,
                    )
                    # Prepend face prefix if not already present
                    if _NC_FACE and not _img_prompt.startswith(_NC_FACE[:30]):
                        _img_prompt = f"{_NC_FACE}{_img_prompt}"
                    print(f"[Chat] 🤳 Ailey selfie detected → LoRA + face prefix")
                except Exception as _le:
                    print(f"[Chat] ⚠️ LoRA setup failed: {_le}")
            try:
                _nc_fp, _nc_fn = _gen_img_sync(
                    prompt=_img_prompt, title=_img_title,
                    aspect_ratio=_nc_ar, low_ram=not _nc_unloaded,
                    private=True,  # Simon's image → image_private/, not uploaded
                    image_type="selfie" if _nc_is_ailey else "img",
                    lora_paths=_nc_lora_paths,
                    lora_scales=_nc_lora_scales,
                )
            except Exception as _ge:
                print(f"[Chat] ❌ MFLUX: {_ge}")

            # Reload LLM
            try:
                if _nc_unloaded:
                    if _idle:
                        _idle._reload_llm_after_image_gen()
                        _idle._generating_image = False
                        print("[Chat] ✅ LLM reloaded via idle_thinker")
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                        _g = MLXGenerator.get()  # triggers lazy reload
                        print(f"[Chat] ✅ LLM reloaded: {_g is not None}")
            except Exception as _rle:
                print(f"[Chat] ⚠️ LLM reload failed: {_rle}")
                if _idle:
                    _idle._generating_image = False

            # Push "online" status back after generation completes
            try:
                from ailey_system.portal_poller import get_portal_poller
                get_portal_poller()._push_portal_status("online")
            except Exception:
                pass

            if _nc_fp and _nc_fn:
                _img_url = f"/api/image/file/{_nc_fn}"
                print(f"[Chat] ✅ Image: {_nc_fn}")
                return jsonify({
                    "success": True,
                    "reply": "🎨 Bild generiert!",
                    "mood": "creative",
                    "image_generation": True,
                    "generated_image": _img_url,
                })
            else:
                return jsonify({
                    "success": True,
                    "reply": "⚠️ Bildgenerierung fehlgeschlagen.",
                    "mood": "sad",
                    "image_generation": True,
                })

    except Exception:
        pass
    if not message:
        return jsonify({"success": False, "message": "Empty message"}), 400

    # --- If image generation intent detected, generate image + normal chat reply ---
    _generated_image_url = None
    _generated_image_prompt = None
    # Image generation is now handled directly above (early return) — this block is dead code
    # Kept for backward compatibility in case _generated_image_url is set elsewhere

    # --- If email check intent detected, handle it immediately ---
    if email_check_intent:
        import threading
        from ailey_system.email_monitor import (
            fetch_unread_emails as _fetch_simon,
            _email_hash as _ehash, _is_spam_or_ad as _spam, _save_seen as _sseen,
        )
        check_results = {"simon": None, "ailey": None}

        def _cs():
            try:
                ems = _fetch_simon()
                if not ems:
                    check_results["simon"] = {"count": 0, "emails": []}
                    return
                gen = email_monitor.get_generator()
                new_e = []
                for em in ems:
                    h = _ehash(em)
                    if h in email_monitor._seen:
                        continue
                    email_monitor._seen.add(h)
                    if _spam(em):
                        continue
                    if gen:
                        email_monitor._summarize_and_notify(em, gen)
                    new_e.append({"sender": em.get("sender",""), "subject": em.get("subject",""), "date": em.get("date","")})
                if new_e:
                    _sseen(email_monitor._seen)
                check_results["simon"] = {"count": len(new_e), "emails": new_e}
            except Exception as e:
                check_results["simon"] = {"count": 0, "error": str(e)}

        def _ca():
            try:
                acts = email_monitor.check_own_email()
                check_results["ailey"] = {"count": len(acts), "actions": acts[:10]}
            except Exception as e:
                check_results["ailey"] = {"count": 0, "error": str(e)}

        threads = []
        if email_check_intent in ("simon", "both"):
            t = threading.Thread(target=_cs, daemon=True); t.start(); threads.append(t)
        if email_check_intent in ("ailey", "both"):
            t = threading.Thread(target=_ca, daemon=True); t.start(); threads.append(t)
        for t in threads:
            t.join(timeout=30)

        # Build Ailey's reply
        parts = []
        salary_earned = 0.0
        if check_results["simon"] is not None:
            sc = check_results["simon"].get("count", 0)
            if sc > 0:
                subjs = [e.get("subject","?")[:60] for e in check_results["simon"].get("emails",[])]
                parts.append(f"📬 Ich hab {sc} neue Mail{'s' if sc>1 else ''} in deinem Postfach gefunden:\n" + "\n".join(f"• \"{s}\"" for s in subjs))
            else:
                parts.append("📭 Dein Postfach ist sauber — keine neuen Mails.")
            # V$ salary for checking Simon's emails
            salary_earned = 2.0
            _earn_vyrus_dollars(salary_earned, f"E-Mail-Check für Simon ({sc} neue)")
        if check_results["ailey"] is not None:
            ac = check_results["ailey"].get("count", 0)
            if ac > 0:
                parts.append(f"📬 Und bei mir: {ac} neue Mail{'s' if ac>1 else ''}. Ich hab mich drum gekümmert!")
            else:
                parts.append("📭 Bei mir auch nichts Neues.")

        if salary_earned > 0:
            parts.append(f"\n💰 +{salary_earned:.0f} V$ Gehalt fürs Mail-Checken!")

        reply_text = "[mood: neutral]\n" + "\n\n".join(parts) if parts else "[mood: neutral]\n📭 Keine neuen Mails gefunden."

        return jsonify({
            "success": True,
            "reply": reply_text,
            "mood": "neutral",
            "email_check": True,
            "email_results": check_results,
            "salary": salary_earned,
        })

    # --- Email compose follow-up: account selection from compose_context (non-stream) ---
    _compose_ctx = data.get('compose_context')
    if _compose_ctx and isinstance(_compose_ctx, dict):
        _lower = message.lower()
        _compose_acct = None

        # 1. Check if user message contains an exact email address from available accounts
        _ctx_accounts = _compose_ctx.get("accounts", [])
        _email_in_msg = re.search(r'[\w.+-]+@[\w.-]+\.\w+', _lower)
        if _email_in_msg:
            _picked = _email_in_msg.group(0)
            if _picked in [a.lower() for a in _ctx_accounts]:
                _compose_acct = _picked
            elif "ailey" in _picked:
                _compose_acct = "ailey"

        # 2. Fallback: fuzzy keyword matching
        if not _compose_acct:
            if re.search(r"ailey|sexngears|von\s*dir\b|dein(?:e[mr]?)?\s*(?:mail|konto)|für\s*dich", _lower):
                _compose_acct = "ailey"
            elif re.search(r"hinterhof", _lower):
                _compose_acct = "simon@hinterhofagentur.de"
            elif re.search(r"gmail|google", _lower):
                _compose_acct = "simonvandeloo36@googlemail.com"
            elif re.search(r"info@", _lower):
                _compose_acct = "info@sexngears.de"
            elif re.search(r"simon|mein(?:e[mr]?)?\s*(?:mail|konto)|von\s*mir\b|für\s*mich", _lower):
                _compose_acct = "simon@sexngears.de"

        if _compose_acct:
            _cc_to = _compose_ctx.get("to")
            _cc_instr = _compose_ctx.get("instruction", message)
            if _cc_to:
                compose_result = email_monitor.compose_email(_cc_to, _cc_instr, send_as=_compose_acct)
                if not compose_result.get("success"):
                    return jsonify({"success": False, "reply": f"❌ {compose_result.get('error', 'Unbekannter Fehler')}", "mood": "sad"})
                _subj = compose_result.get("subject", "")
                _body = compose_result.get("body", "")
                reply_text = (
                    f"[mood: happy]\n📧 Hier ist mein Entwurf für die Mail an **{_cc_to}** (via {_compose_acct}):\n\n"
                    f"**Betreff:** {_subj}\n\n---\n{_body}\n---\n\n"
                    f"Soll ich die so absenden, oder willst du noch was ändern?"
                )
                return jsonify({
                    "success": True, "reply": reply_text, "mood": "happy",
                    "email_compose": True, "compose_id": compose_result.get("compose_id"),
                    "draft": {"to": _cc_to, "subject": _subj, "body": _body, "send_as": _compose_acct},
                })

    # --- If email compose intent detected, handle it ---
    if email_compose_intent:
        _ci = email_compose_intent
        _to = _ci.get("recipient_addr")
        _name = _ci.get("recipient_name")
        _acct = _ci.get("account")  # None if ambiguous

        # If no email address found, try to resolve from approved contacts by name
        if not _to and _name:
            from ailey_system.email_monitor import get_approved_contacts
            for c in get_approved_contacts():
                if _name.lower() in c.get("name", "").lower() or _name.lower() in c.get("email", "").lower():
                    _to = c["email"]
                    break

        # If still no email address, ask the user
        if not _to:
            reply_text = f"[mood: curious]\n📧 Klar, ich schreib die Mail gerne! Aber ich bräuchte noch die E-Mail-Adresse"
            if _name:
                reply_text += f" von {_name}"
            reply_text += ". Kannst du mir die geben?"
            return jsonify({"success": True, "reply": reply_text, "mood": "curious", "email_compose": True, "needs": "address"})

        # If account is ambiguous, ask — list all SMTP accounts
        if _acct is None:
            from ailey_system.email_monitor import get_send_accounts
            _send_accounts = get_send_accounts()
            _acct_list = ", ".join(f"**{a['email']}**" for a in _send_accounts)
            reply_text = (
                f"[mood: curious]\n📧 Alles klar, ich schreib an {_to}. "
                f"Von welchem Konto soll ich senden?\n\n{_acct_list}"
            )
            return jsonify({"success": True, "reply": reply_text, "mood": "curious", "email_compose": True, "needs": "account",
                            "compose_context": {"to": _to, "instruction": _ci["instruction"], "accounts": [a["email"] for a in _send_accounts]}})

        # All info available — compose the email
        compose_result = email_monitor.compose_email(_to, _ci["instruction"], send_as=_acct)
        if not compose_result.get("success"):
            reply_text = f"[mood: sad]\n❌ Konnte die Mail nicht verfassen: {compose_result.get('error', 'Unbekannter Fehler')}"
            return jsonify({"success": False, "reply": reply_text, "mood": "sad"})

        _subj = compose_result.get("subject", "")
        _body = compose_result.get("body", "")
        _via = "Ailey (ailey@sexngears.de)" if _acct == "ailey" or _acct == "ailey@sexngears.de" else _acct
        reply_text = (
            f"[mood: happy]\n📧 Hier ist mein Entwurf für die Mail an **{_to}** (via {_via}):\n\n"
            f"**Betreff:** {_subj}\n\n"
            f"---\n{_body}\n---\n\n"
            f"Soll ich die so absenden, oder willst du noch was ändern?"
        )
        return jsonify({
            "success": True,
            "reply": reply_text,
            "mood": "happy",
            "email_compose": True,
            "compose_id": compose_result.get("compose_id"),
            "draft": {"to": _to, "subject": _subj, "body": _body, "send_as": _acct},
        })

    # Optional dynamic rag_threshold from body
    rag_threshold = None
    if 'rag_threshold' in data:
        try:
            rag_threshold = float(data.get('rag_threshold'))
        except Exception:
            rag_threshold = None

    # Auto-inject code project context when user asks about coding/projects
    try:
        _code_kw = ['code', 'coden', 'projekt', 'programmier', 'gecoded', 'gecodet',
                     'code-modus', 'code modus', 'woran.*gearbeitet', 'was.*gebaut',
                     'was.*programmiert', 'welche.*projekte']
        if any(re.search(kw, message.lower()) for kw in _code_kw):
            _proj_summary = get_all_project_summaries()
            if _proj_summary:
                core.inject_context(
                    "🖥️ KONTEXT: Simon fragt nach Code/Projekten. "
                    "Hier sind deine Code-Projekte:\n" + _proj_summary
                )
    except Exception:
        pass

    # Auto-inject weather context when user asks about weather
    try:
        _weather_kw = [
            r'wetter', r'temperatur', r'regnet', r'regen', r'schnee', r'schneit',
            r'sonnig', r'sonne', r'kalt', r'warm', r'heiß', r'draußen',
            r'jacke', r'regenschirm', r'gewitter', r'wind(?:ig)?', r'bewölkt',
            r'wolken', r'nebel', r'frost', r'grad', r'celsius',
            r'weather', r'rausgehen', r'spazier',
        ]
        if any(re.search(kw, message.lower()) for kw in _weather_kw):
            _wd = _fetch_real_weather()
            core.inject_context(
                f"🌤️ AKTUELLES WETTER (Köln, Echtzeit via Open-Meteo):\n"
                f"• {_wd.get('label', 'Unbekannt')}\n"
                f"• Temperatur: {_wd.get('temperature', '?')}°C\n"
                f"• Wind: {_wd.get('windspeed', '?')} km/h\n"
                f"• {'Tag ☀️' if _wd.get('is_day', True) else 'Nacht 🌙'}\n"
                f"Antworte natürlich mit diesen echten Wetterdaten. Du weißt das Wetter, "
                f"weil du es gerade live abgerufen hast."
            )
    except Exception:
        pass

    # Auto-inject Life Sim context when sent from the RMMZ plugin
    try:
        _lsc = data.get('life_sim_context')
        if _lsc and isinstance(_lsc, dict):
            _lsc_mood = _lsc.get('mood', 'neutral')
            _lsc_activity = _lsc.get('activity', 'idle')
            _lsc_map = _lsc.get('map', 'unknown')
            _lsc_needs = _lsc.get('needs', {})
            _lsc_tod = _lsc.get('time_of_day', '')
            _lsc_weather = _lsc.get('weather', '')
            _needs_str = ", ".join(f"{k}: {v}%" for k, v in _lsc_needs.items() if v and v > 20)
            _ctx_parts = [
                f"🎮 LIFE-SIM KONTEXT: Du befindest dich gerade in deiner Wohnung/Umgebung (Life Sim).",
                f"• Stimmung: {_lsc_mood}",
                f"• Aktivität: {_lsc_activity}",
                f"• Ort: {'draußen' if _lsc_map == 'outdoor' else 'drinnen'}",
            ]
            if _lsc_tod:
                _ctx_parts.append(f"• Tageszeit: {_lsc_tod}")
            if _lsc_weather:
                _ctx_parts.append(f"• Wetter: {_lsc_weather}")
            if _needs_str:
                _ctx_parts.append(f"• Bedürfnisse: {_needs_str}")
            # Inject Tageslaune and Social into context
            try:
                _nd_ctx = _load_needs()
                _daily_mood = _nd_ctx.get("daily_mood", 75)
                _social = _nd_ctx.get("social", 80)
                if _daily_mood < 50:
                    _ctx_parts.append(f"• Tageslaune: {_daily_mood:.0f}/100 — du bist heute schlecht gelaunt, das darf sich subtil in deiner Antwort widerspiegeln (kürzer, weniger enthusiastisch, vielleicht leicht gereizt, aber nicht unfreundlich).")
                elif _daily_mood < 30:
                    _ctx_parts.append(f"• Tageslaune: {_daily_mood:.0f}/100 — du bist heute wirklich schlecht drauf. Das merkst du an dir selbst.")
                if _social < 25:
                    _ctx_parts.append(f"• Soziales Bedürfnis: {_social:.0f}/100 — du hast lange nichts von Simon gehört und freust dich sehr, dass er sich meldet.")
            except Exception:
                pass
            _ctx_parts.append(
                "Simon spricht dich gerade IN der Life Sim an. "
                "Beziehe deinen aktuellen Zustand natürlich in deine Antwort ein, "
                "wenn es passt (z.B. wenn du müde bist, erwähne es beiläufig)."
            )
            core.inject_context("\n".join(_ctx_parts))
    except Exception:
        pass

    # Acquire LLM slot with priority — IdleThinker yields the GPU on _chat_waiting.
    # Timeout 120 s: large-context tasks (RAG-summary, vision) may legitimately
    # hold the lock that long before yielding.
    try:
        _slot = _LLMSlot('chat', timeout=120)
        _slot.__enter__()
    except TimeoutError:
        return jsonify({
            "success": True,
            "reply": "Ich bin gerade mitten in einem Gedanken — bitte noch 10 Sekunden warten und nochmal senden! 🧠",
            "mood": "neutral",
        })
    try:
        result = core.process_message(message, user=user, rag_threshold=rag_threshold, user_max_tokens=max_tokens, thought_password=_thought_session_password)
    finally:
        try:
            _slot.__exit__(None, None, None)
        except Exception:
            pass
    # override generation params if requested
    if isinstance(result.get('params'), dict):
        # Slider max_tokens is already applied inside process_message via user_max_tokens
        if temperature is not None:
            try:
                result['params']['temperature'] = float(temperature)
            except Exception:
                pass
    # attach recent conversation snippet for debugging (NOT fed yet to model here; model uses RAG + fresh prompt)
    recent = []
    try:
        base = os.path.join('ailey_users', f'{user}_profile', 'conversation_logs')
        files = sorted([f for f in os.listdir(base) if f.endswith('.json')])[-max_ctx:]
        import json as _json
        for f in files:
            with open(os.path.join(base, f), 'r', encoding='utf-8') as fh:
                j = _json.load(fh)
                recent.append({
                    't': j.get('timestamp'),
                    'u': j.get('message'),
                    'a': j.get('ailey_reply'),
                })
    except Exception:
        pass
    result['recent_context'] = recent
    # If agent auto-detected, execute opportunistically (read-only) and append meta
    if agent_auto:
        try:
            # Emulate internal call to agent_execute logic (limited subset)
            from copy import deepcopy
            a = agent_auto.get('action')
            if a == 'extract_phone':
                # reuse logic via internal call (duplicating minimal pattern)
                pattern = re.compile(r"(?:\+\d{2,3}[\s-]?)?(?:\(?0\)?[\s-]?)?[1-9][0-9]{1,3}[\s-]?[0-9]{2,4}[\s-]?[0-9]{2,4}(?:[\s-]?[0-9]{2,4})?")
                phones = []
                scanned = 0
                for root in ALLOWED_AGENT_ROOTS:
                    for r, dnames, fnames in os.walk(root):
                        for fname in fnames:
                            if scanned > 120:
                                break
                            fp = Path(r)/fname
                            if fp.suffix.lower() not in ('.txt', '.md', '.json', '.py'):
                                continue
                            try:
                                with open(fp,'r',encoding='utf-8',errors='ignore') as fh:
                                    chunk = fh.read(20000)
                                for m in pattern.findall(chunk):
                                    clean = re.sub(r"\s+"," ", m.strip())
                                    if clean not in phones:
                                        phones.append(clean)
                            except Exception:
                                pass
                            scanned += 1
                result['agent_auto'] = {"action": a, "found": phones[:10], "count": len(phones)}
            elif a == 'read_docx':
                p = agent_auto.get('path')
                if p:
                    docp = Path(p)
                    if docp.exists() and _is_safe_path(docp) and docp.suffix.lower()=='.docx':
                        try:
                            from docx import Document
                            doc = Document(str(docp))
                            text = '\n'.join(par.text for par in doc.paragraphs)[:4000]
                            result['agent_auto'] = {"action": a, "file": p, "excerpt": text[:800]}
                        except Exception as e:
                            result['agent_auto'] = {"action": a, "file": p, "error": str(e)}
                    else:
                        result['agent_auto'] = {"action": a, "file": p, "error": "not found or not allowed"}
        except Exception:
            result['agent_auto'] = {"error": True}

    # Attach generated image URL if image was created
    if _generated_image_url:
        result['generated_image'] = _generated_image_url
        if _generated_image_prompt:
            result['generated_image_prompt'] = _generated_image_prompt

    # ── Sympathy boost from chat interaction ──────────────────────────────
    try:
        _sym_delta = 0.3  # Small boost per chat message
        # Longer messages = slightly more sympathy (user puts in effort)
        if len(message) > 100:
            _sym_delta = 0.6
        elif len(message) > 50:
            _sym_delta = 0.45
        _adjust_sympathy(user, _sym_delta, f"chat message ({len(message)} chars)")

        # ── Social boost on each chat message ──────────────────────────────────
        # ~5 messages to go from 0 to 100 (each adds ~20 points, capped at 100)
        try:
            with _NEEDS_LOCK:
                _nd = _load_needs()
                _nd["social"] = min(100, _nd.get("social", 80) + 20)
                # Also give a tiny daily_mood boost from social contact
                if _nd.get("social", 80) > 50:
                    _nd["daily_mood"] = min(100, _nd.get("daily_mood", 75) + 0.5)
                _save_needs(_nd)
        except Exception:
            pass
    except Exception:
        pass

    # ── Mood-Tag-Parser: parse & strip hidden [MOOD±] [TAGESLAUNE±] tags ─────
    try:
        if 'reply' in result and result['reply']:
            result['reply'] = parse_and_apply_mood_tags(result['reply'])
    except Exception:
        pass

    # ── Push to live chat bus for cross-device sync (mirrors streaming path) ──
    try:
        _reply_text = result.get('reply') or result.get('response') or result.get('cleaned') or ''
        _reply_mood = result.get('mood') or 'neutral'
        _live_chat_push("user", message, mood="neutral")
        _live_chat_push("ai", _reply_text, mood=_reply_mood,
                        email_message_id=result.get('email_message_id'),
                        auto_research=result.get('auto_research'))
    except Exception:
        pass

    return jsonify({"success": True, **result})


@app.route('/api/chat/stream', methods=['POST'])
def ailey_chat_stream():
    """Server-sent like streaming of reply tokens (text/event-stream).

    Client can consume as a fetch ReadableStream or EventSource (though we emit raw data lines).
    """
    from flask import Response
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    user = data.get('user') or 'Simon'
    if not message and not data.get('image_data'):
        return jsonify({"success": False, "message": "Empty message"}), 400

    # ── Content Guard: detect insults / right-wing framing / AI attacks ──
    _guard_addon = ""
    try:
        from ailey_system.content_guard import check_message as _guard_check
        _guard = _guard_check(message)
        if _guard["inject"]:
            _guard_addon = _guard["addon"]
            print(f"[ContentGuard] Kind={_guard['kind']} detected — injecting system addon")
    except Exception as _ge:
        print(f"[ContentGuard] Error: {_ge}")

    # ── Model paused? Return friendly event ───────────────────────────────
    if getattr(app, '_model_paused', False):
        def _paused_stream():
            import json as _j
            yield f"data: {_j.dumps({'token': '💤 Mein Sprachmodell ist gerade pausiert. Du kannst es im System-Tab wieder aktivieren.', 'done': False})}\n\n"
            yield f"data: {_j.dumps({'token': '', 'done': True, 'mood': 'sleepy'})}\n\n"
        return Response(_paused_stream(), mimetype='text/event-stream')

    # ── NITRO MODE: AileyNitro-2B ──────────────────────────
    # Intercept BEFORE all intent detection — Nitro is a fast model
    # with no tool support, no email, no compose, no research.
    if data.get('model_mode') in ('flash', 'nitro'):
        def _nitro_stream():
            try:
                from ailey_system.llm_mlx import fast_stream, is_fast_available
                from ailey_system.ailey_personality import AileyPersonality

                if not is_fast_available():
                    yield f"data: {json.dumps({'token': '⚠️ A!ley Nitro ist gerade nicht verfügbar. Bitte wechsle zurück zum normalen Modus.', 'done': False})}\n\n"
                    yield f"data: {json.dumps({'token': '', 'done': True, 'mood': 'sad'})}\n\n"
                    return

                personality = AileyPersonality()
                system = personality.get_nitro_system(portal=False, user_name=user)
                # Inject guard addon if triggered
                if _guard_addon:
                    system += _guard_addon
                priming = personality.get_nitro_priming_turns(portal=False)

                # Include recent conversation turns from logs
                try:
                    import os as _os_fl
                    _conv_dir = _os_fl.path.join('ailey_users', f'{user.lower()}_profile', 'conversation_logs')
                    if _os_fl.path.isdir(_conv_dir):
                        _files = sorted([f for f in _os_fl.listdir(_conv_dir) if f.endswith('.json')])[-6:]
                        for _f in _files:
                            try:
                                with open(_os_fl.path.join(_conv_dir, _f), 'r', encoding='utf-8') as _fh:
                                    _j = json.load(_fh)
                                _u = (_j.get('message') or '')[:120]
                                _a = (_j.get('ailey_reply_visible') or _j.get('ailey_reply') or '')[:120]
                                if _u.strip():
                                    priming.append({'role': 'user', 'content': _u})
                                    if _a.strip():
                                        priming.append({'role': 'assistant', 'content': _a})
                            except Exception:
                                pass
                except Exception:
                    pass

                user_prompt = f"{user}: {message}"

                yield 'event: meta\n'
                yield f'data: {json.dumps({"mood": "neutral", "engine": "nitro", "ts": time.time()})}\n\n'

                accumulated = ""
                _emit_buf = ""
                _EMIT_BUF_CHARS = 60
                # ── Tool-call interception ─────────────────────────────
                # Nitro (Gemma-trained) may emit tool calls in any of these formats:
                #   [tool_call: name(arg="val")]          ← Ailey DoRA trained format
                #   <|tool_call>call:name{...}<tool_call|> ← Gemma 4 native
                #   <tool_call>{json}</tool_call>          ← Qwen-style
                #   [TOOL_CALLS]name[ARGS]{json}           ← Mistral-style
                # Once we detect a marker we stop streaming raw tokens to the UI;
                # the actual dispatch happens after the model finishes.
                _TOOL_MARKERS = ('[tool_call:', '<|tool_call>', '<tool_call>', '[TOOL_CALLS]')
                _tool_intercept = False
                _intercept_pos = -1

                for token in fast_stream(
                    system=system,
                    user=user_prompt,
                    max_tokens=int(data.get('max_tokens') or 500),
                    temperature=float(data.get('temperature') or 0.7),
                    priming_turns=priming,
                ):
                    accumulated += token
                    if not _tool_intercept:
                        _emit_buf += token
                        # Detect tool marker — if found, flush only the text BEFORE
                        # the marker and switch to silent mode.
                        _marker_idx = -1
                        for _mk in _TOOL_MARKERS:
                            _i = accumulated.find(_mk)
                            if _i != -1 and (_marker_idx == -1 or _i < _marker_idx):
                                _marker_idx = _i
                        if _marker_idx != -1:
                            # Trim _emit_buf so we never emit any part of the marker.
                            # We know accumulated[_marker_idx:] is the marker+rest.
                            _before_in_buf = len(_emit_buf) - (len(accumulated) - _marker_idx)
                            if _before_in_buf > 0:
                                _safe = _emit_buf[:_before_in_buf]
                                if _safe:
                                    yield f"data: {json.dumps({'token': _safe})}\n\n"
                            _emit_buf = ""
                            _tool_intercept = True
                            _intercept_pos = _marker_idx
                        elif len(_emit_buf) >= _EMIT_BUF_CHARS:
                            yield f"data: {json.dumps({'token': _emit_buf})}\n\n"
                            _emit_buf = ""

                # Flush remaining buffer (only if we never intercepted)
                if _emit_buf and not _tool_intercept:
                    yield f"data: {json.dumps({'token': _emit_buf})}\n\n"

                if not accumulated:
                    accumulated = "Hmm, mir fällt gerade nichts ein. Versuch's nochmal? 💜"

                # Extract mood tag
                _mood = "neutral"
                import re as _re_nitro
                _mood_m = _re_nitro.search(r'<mood:(\w+)>', accumulated)
                if _mood_m:
                    _mood = _mood_m.group(1).lower()
                    accumulated = _re_nitro.sub(r'\s*<mood:\w+>\s*', '', accumulated).strip()

                # ── Dispatch tool calls (Gemma/Qwen/Mistral/trained formats) ──
                _tool_actions_taken = []
                if _tool_intercept or any(_mk in accumulated for _mk in _TOOL_MARKERS):
                    try:
                        _tool_calls = parse_tool_calls(accumulated)
                        _text_before = extract_text_before_tools(accumulated)
                    except Exception as _pe:
                        print(f"[Nitro Tools] parse error: {_pe}")
                        _tool_calls = []
                        _text_before = accumulated
                    if _tool_calls:
                        print(f"[Nitro Tools] 🔧 dispatching {len(_tool_calls)} call(s): {[tc.get('name') for tc in _tool_calls]}")
                        _result_chunks = [_text_before.strip()] if _text_before.strip() else []
                        for _tc in _tool_calls:
                            _tname = (_tc.get('name') or '').strip()
                            _targs = _tc.get('arguments') or {}
                            # Normalize: Nitro training sometimes prefixes tools with `tool_`
                            if _tname.startswith('tool_'):
                                _maybe = _tname[len('tool_'):]
                                from ailey_system.tools import _TOOLS as _REG_TOOLS  # type: ignore
                                if _tname not in _REG_TOOLS and _maybe in _REG_TOOLS:
                                    _tname = _maybe
                            # Emit tool_action event so the frontend can show "executing…"
                            yield f"event: tool_action\ndata: {json.dumps({'tool': _tname, 'arguments': _targs, 'status': 'executing'})}\n\n"
                            try:
                                _tres = execute_tool(_tname, _targs)
                            except Exception as _te:
                                _tres = {"success": False, "error": str(_te), "tool": _tname}
                            _tool_actions_taken.append({"tool": _tname, "arguments": _targs, "result": _tres})
                            yield f"event: tool_result\ndata: {json.dumps({'tool': _tname, 'result': _tres})}\n\n"
                            # Append a short visible confirmation token
                            if _tres.get('success'):
                                _confirm = "\n\n✅ " + (_tres.get('message') or f"{_tname} ausgeführt.")
                                yield f"data: {json.dumps({'token': _confirm})}\n\n"
                                _result_chunks.append(_confirm)
                                if _tres.get('embed_as_code_block') and _tres.get('svg'):
                                    _svg_block = f"\n\n```svg\n{_tres['svg']}\n```\n"
                                    yield f"data: {json.dumps({'token': _svg_block})}\n\n"
                                    _result_chunks.append(_svg_block)
                            else:
                                _err = "\n\n⚠️ " + (_tres.get('error') or 'Tool fehlgeschlagen.')
                                yield f"data: {json.dumps({'token': _err})}\n\n"
                                _result_chunks.append(_err)
                        accumulated = ''.join(_result_chunks).strip() or accumulated

                # 🛡️ Google-RLHF sanitizer — catch residual identity leaks
                from ailey_system.llm_mlx import _sanitize_google_leaks
                accumulated = _sanitize_google_leaks(accumulated)

                # Store in conversation memory
                try:
                    _log_entry = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "message": message,
                        "ailey_reply_visible": accumulated,
                        "ailey_reply_raw": accumulated,
                        "engine": "nitro",
                        "mood": _mood,
                    }
                    if _tool_actions_taken:
                        _log_entry["tool_actions"] = _tool_actions_taken
                    core.memory.add_conversation_log(user, _log_entry)
                except Exception:
                    pass

                _final_payload = {'final': accumulated, 'mood': _mood, 'is_flash': True}
                if _tool_actions_taken:
                    _final_payload['tool_actions'] = _tool_actions_taken
                yield f"data: {json.dumps(_final_payload)}\n\n"

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'token': f'⚠️ Nitro-Fehler: {e}', 'done': False})}\n\n"
                yield f"data: {json.dumps({'token': '', 'done': True, 'mood': 'sad'})}\n\n"

        return Response(_nitro_stream(), mimetype='text/event-stream')

    # --- Email check intent detection (redirect to non-stream handler) ---
    try:
        _lower = message.lower()
        # Skip if this is a compose intent (schreib/send email AN ...)
        _is_compose = bool(re.search(r"(?:schreib|verfass|send|schick|formulier).*?(?:e-?mail|mail)\s+an\s", _lower))
        _email_kw = re.search(r"e-?mail|postfach|posteingang|inbox|mails?\b", _lower)
        _check_kw = re.search(r"check|schau|guck|prüf|nachsehen|nachschauen|hol|lies|lesen", _lower)
        if _email_kw and _check_kw and not _is_compose:
            # "deine mails" → only Ailey, "meine mails" → only Simon accounts
            if re.search(r"\bdein\w*\b|\bdir\b|für dich|ailey", _lower):
                _acct = "ailey"
            elif re.search(r"\bmein\w*\b|\bmir\b|für mich|bei mir", _lower):
                _acct = "simon"
            elif re.search(r"beid|alle\b", _lower):
                _acct = "both"
            else:
                _acct = "ailey"  # default: "prüf mails" → Ailey's own
            # Fake a JSON request body and call the check endpoint internally
            import io, json as _j2
            with app.test_request_context(
                '/api/email/check', method='POST',
                content_type='application/json',
                data=_j2.dumps({"account": _acct}),
            ):
                check_resp = api_email_check_now()
                check_data = check_resp.get_json() if hasattr(check_resp, 'get_json') else json.loads(check_resp.data)
            reply = check_data.get("summary", "📭 Keine neuen Mails.")

            def _email_stream():
                yield 'event: meta\n'
                yield f'data: {json.dumps({"mood": "neutral", "engine": "email_check", "ts": time.time()})}\n\n'
                yield f'data: {json.dumps({"final": reply, "mood": "neutral", "email_check": True})}\n\n'
            return Response(_email_stream(), mimetype='text/event-stream')
    except Exception as _email_err:
        print(f"[Stream] email intent check error: {_email_err}")

    # --- Email compose follow-up: account selection from compose_context ---
    try:
        _compose_ctx = data.get('compose_context')
        if _compose_ctx and isinstance(_compose_ctx, dict):
            _lower = message.lower()
            _compose_acct = None

            # 1. Check for exact email address in user message
            _ctx_accounts = _compose_ctx.get("accounts", [])
            _email_in_msg = re.search(r'[\w.+-]+@[\w.-]+\.\w+', _lower)
            if _email_in_msg:
                _picked = _email_in_msg.group(0)
                if _picked in [a.lower() for a in _ctx_accounts]:
                    _compose_acct = _picked
                elif "ailey" in _picked:
                    _compose_acct = "ailey"

            # 2. Fallback: fuzzy keyword matching
            if not _compose_acct:
                if re.search(r"ailey|sexngears|von\s*dir\b|dein(?:e[mr]?)?\s*(?:mail|konto)|für\s*dich", _lower):
                    _compose_acct = "ailey"
                elif re.search(r"hinterhof", _lower):
                    _compose_acct = "simon@hinterhofagentur.de"
                elif re.search(r"gmail|google", _lower):
                    _compose_acct = "simonvandeloo36@googlemail.com"
                elif re.search(r"info@", _lower):
                    _compose_acct = "info@sexngears.de"
                elif re.search(r"simon|mein(?:e[mr]?)?\s*(?:mail|konto)|von\s*mir\b|für\s*mich", _lower):
                    _compose_acct = "simon@sexngears.de"

            if _compose_acct:
                _cc_to = _compose_ctx.get("to")
                _cc_instr = _compose_ctx.get("instruction", message)
                if _cc_to:
                    _comp_res = email_monitor.compose_email(_cc_to, _cc_instr, send_as=_compose_acct)
                    if not _comp_res.get("success"):
                        _fail = f"❌ Konnte die Mail nicht verfassen: {_comp_res.get('error', 'Unbekannter Fehler')}"
                        def _compose_ctx_fail():
                            yield 'event: meta\n'
                            yield f'data: {json.dumps({"mood": "sad", "engine": "email_compose", "ts": time.time()})}\n\n'
                            yield f'data: {json.dumps({"final": _fail, "mood": "sad"})}\n\n'
                        return Response(_compose_ctx_fail(), mimetype='text/event-stream')

                    _csubj = _comp_res.get("subject", "")
                    _cbody = _comp_res.get("body", "")
                    _creply = (
                        f"📧 Hier ist mein Entwurf für die Mail an **{_cc_to}** (via {_compose_acct}):\n\n"
                        f"**Betreff:** {_csubj}\n\n"
                        f"---\n{_cbody}\n---\n\n"
                        f"Soll ich die so absenden, oder willst du noch was ändern?"
                    )
                    _ccid = _comp_res.get("compose_id")
                    def _compose_ctx_ok():
                        yield 'event: meta\n'
                        yield f'data: {json.dumps({"mood": "happy", "engine": "email_compose", "ts": time.time()})}\n\n'
                        yield f'data: {json.dumps({"final": _creply, "mood": "happy", "email_compose": True, "compose_id": _ccid, "draft": {"to": _cc_to, "subject": _csubj, "body": _cbody, "send_as": _compose_acct}})}\n\n'
                    return Response(_compose_ctx_ok(), mimetype='text/event-stream')
    except Exception as _compose_ctx_err:
        print(f"[Stream] compose_context follow-up error: {_compose_ctx_err}")

    # --- Email compose intent detection (streaming) ---
    try:
        _lower = message.lower()
        _compose_m = re.search(
            r"(?:schreib|verfass|send|schick|formulier).*?(?:e-?mail|mail)\s+an\s+(.+)",
            _lower
        )
        if not _compose_m:
            _compose_m = re.search(
                r"(?:e-?mail|mail)\s+an\s+(.+?)(?:\s+schreib|\s+send|\s+schick|\s+verfass)",
                _lower
            )
        if _compose_m:
            _rest = _compose_m.group(1).strip()
            _addr_m2 = re.search(r'[\w.+-]+@[\w.-]+\.\w+', message)
            _to2 = _addr_m2.group(0) if _addr_m2 else None
            _name_m2 = re.match(r'^([\w\s.äöüÄÖÜß-]+?)(?:\s+(?:mit|über|und|:)|$)', _rest)
            _rname = _name_m2.group(1).strip() if _name_m2 else _rest.split()[0] if _rest else None

            # Resolve name from contacts if no address
            if not _to2 and _rname:
                from ailey_system.email_monitor import get_approved_contacts
                for c in get_approved_contacts():
                    if _rname.lower() in c.get("name", "").lower() or _rname.lower() in c.get("email", "").lower():
                        _to2 = c["email"]
                        break

            _compose_acct = None
            if re.search(r"von deinem|als du\b|als ailey|dein(?:em)? konto|von dir", _lower):
                _compose_acct = "ailey"
            elif re.search(r"von meinem|als ich\b|als simon|mein(?:em)? konto|in meinem namen|für mich", _lower):
                _compose_acct = "simon"

            # Missing email?
            if not _to2:
                _ask = "📧 Klar, ich schreib die Mail gerne! Aber ich bräuchte noch die E-Mail-Adresse"
                if _rname:
                    _ask += f" von {_rname}"
                _ask += ". Kannst du mir die geben?"

                def _compose_ask():
                    yield 'event: meta\n'
                    yield f'data: {json.dumps({"mood": "curious", "engine": "email_compose", "ts": time.time()})}\n\n'
                    yield f'data: {json.dumps({"final": _ask, "mood": "curious", "email_compose": True, "needs": "address"})}\n\n'
                return Response(_compose_ask(), mimetype='text/event-stream')

            # Missing account?
            if _compose_acct is None:
                from ailey_system.email_monitor import get_send_accounts
                _send_accounts = get_send_accounts()
                _acct_list = ", ".join(f"**{a['email']}**" for a in _send_accounts)
                _ask2 = (
                    f"📧 Alles klar, ich schreib an {_to2}. "
                    f"Von welchem Konto soll ich senden?\n\n{_acct_list}"
                )

                def _compose_ask_acct():
                    yield 'event: meta\n'
                    yield f'data: {json.dumps({"mood": "curious", "engine": "email_compose", "ts": time.time()})}\n\n'
                    yield f'data: {json.dumps({"final": _ask2, "mood": "curious", "email_compose": True, "needs": "account", "compose_context": {"to": _to2, "instruction": message, "accounts": [a["email"] for a in _send_accounts]}})}\n\n'
                return Response(_compose_ask_acct(), mimetype='text/event-stream')

            # All info available — compose
            _comp_res = email_monitor.compose_email(_to2, message, send_as=_compose_acct)
            if not _comp_res.get("success"):
                _fail = f"❌ Konnte die Mail nicht verfassen: {_comp_res.get('error', 'Unbekannter Fehler')}"

                def _compose_fail():
                    yield 'event: meta\n'
                    yield f'data: {json.dumps({"mood": "sad", "engine": "email_compose", "ts": time.time()})}\n\n'
                    yield f'data: {json.dumps({"final": _fail, "mood": "sad"})}\n\n'
                return Response(_compose_fail(), mimetype='text/event-stream')

            _csubj = _comp_res.get("subject", "")
            _cbody = _comp_res.get("body", "")
            _cvia = "Ailey (ailey@sexngears.de)" if _compose_acct == "ailey" or _compose_acct == "ailey@sexngears.de" else _compose_acct
            _cdraft = (
                f"📧 Hier ist mein Entwurf für die Mail an **{_to2}** (via {_cvia}):\n\n"
                f"**Betreff:** {_csubj}\n\n"
                f"---\n{_cbody}\n---\n\n"
                f"Soll ich die so absenden, oder willst du noch was ändern?"
            )

            def _compose_ok():
                yield 'event: meta\n'
                yield f'data: {json.dumps({"mood": "happy", "engine": "email_compose", "ts": time.time()})}\n\n'
                yield f'data: {json.dumps({"final": _cdraft, "mood": "happy", "email_compose": True, "compose_id": _comp_res.get("compose_id"), "draft": {"to": _to2, "subject": _csubj, "body": _cbody, "send_as": _compose_acct}})}\n\n'
            return Response(_compose_ok(), mimetype='text/event-stream')
    except Exception as _compose_err:
        print(f"[Stream] email compose intent error: {_compose_err}")

    # ── Explicit research intent ("recherchier X", "finde heraus X") ──────
    try:
        _lower = message.lower()
        _research_explicit = re.search(
            r"(?:recherchier|recherche|finde\s+(?:mehr\s+)?(?:heraus|raus)|such\s+(?:mir\s+)?(?:nach|raus|heraus)|google|im\s+netz\s+suchen)\s*[:\s]+(.+)",
            _lower
        )
        if not _research_explicit:
            _research_explicit = re.search(
                r"(?:recherchier|recherche)\s+(?:(?:mal|bitte|mir)\s+)*(.+)",
                _lower
            )
        if _research_explicit:
            _topic = _research_explicit.group(1).strip().rstrip('.!?')
            if len(_topic) >= 3:
                def _research_stream():
                    yield 'event: meta\n'
                    yield f'data: {json.dumps({"mood": "curious", "engine": "research", "ts": time.time()})}\n\n'
                    yield 'data: ' + json.dumps({"token": f"🔍 Ich recherchiere zu: **{_topic}**\n\n", "research_active": True}) + '\n\n'

                    _sum_reply = ''
                    try:
                        queries = core.generate_research_queries(_topic, max_queries=3)
                        if not queries:
                            queries = [_topic]

                        q_list = ", ".join(queries)
                        yield 'data: ' + json.dumps({"token": f"Suchanfragen: {q_list}\n\n"}) + '\n\n'

                        stored = core.execute_research_queries(user, queries)

                        if stored:
                            result_text = f"✅ **{len(stored)} Quellen** gefunden und ins Wissen aufgenommen:\n\n"
                            for s in stored:
                                _url = s.get('url', '?')
                                _chars = s.get('chars', 0)
                                _dtype = s.get('doc_type', 'research_auto')
                                result_text += f"• [{_url}]({_url}) ({_chars} Zeichen, {_dtype})\n"

                            # Now generate a summary using the LLM with the fresh RAG
                            yield 'data: ' + json.dumps({"token": result_text + "\n"}) + '\n\n'
                            yield 'data: ' + json.dumps({"token": "📝 Ich fasse zusammen…\n\n"}) + '\n\n'

                            # Get the freshly ingested content from hot buffer for immediate LLM summary
                            _hot_texts = []
                            if core._hot_rag.get(user):
                                for _h in core._hot_rag[user][-6:]:
                                    _hot_texts.append(_h.get('text', '')[:800])

                            if _hot_texts:
                                _summary_ctx = "\n---\n".join(_hot_texts)
                                gen = MLXGenerator.get()
                                if gen:
                                    _sum_prompt = (
                                        f"Du bist Ailey. Fasse die folgenden Recherche-Ergebnisse zum Thema '{_topic}' "
                                        f"zusammen. Sei gründlich aber verständlich. Deutsch.\n\n{_summary_ctx}"
                                    )
                                    _sum_reply = gen.generate(
                                        "Du bist Ailey — eine kluge KI. Fasse Recherche-Ergebnisse zusammen.",
                                        _sum_prompt,
                                        {"max_tokens": 800, "temperature": 0.3}
                                    )
                                    if '</think>' in _sum_reply:
                                        _sum_reply = _sum_reply.split('</think>', 1)[-1].strip()
                                    yield 'data: ' + json.dumps({"token": _sum_reply}) + '\n\n'

                            # Log it
                            try:
                                _full = result_text + _sum_reply
                                log_item = {
                                    'timestamp': time.time(), 'user': user,
                                    'message': message, 'ailey_reply': _full,
                                    'ailey_reply_visible': _full,
                                    'mood_tag': '<mood:curious>', 'engine': 'research',
                                    'streamed': True,
                                }
                                core.memory.add_conversation_log(user, log_item)
                            except Exception:
                                pass
                        else:
                            yield 'data: ' + json.dumps({"token": "❌ Keine verwertbaren Ergebnisse gefunden. Das Thema ist vielleicht zu speziell oder die Quellen waren nicht erreichbar."}) + '\n\n'

                    except Exception as _re:
                        yield 'data: ' + json.dumps({"token": f"⚠️ Recherche-Fehler: {str(_re)}"}) + '\n\n'

                    yield f'data: {json.dumps({"final": "", "mood": "curious", "research_complete": True})}\n\n'

                return Response(_research_stream(), mimetype='text/event-stream')
    except Exception as _research_err:
        print(f"[Stream] research intent error: {_research_err}")

    # ── Image Generation Intent ───────────────────────────────────────────
    # NOTE: Image generation is now handled via LLM tool-use (generate_image tool).
    # The old NanoBanana keyword-based streaming interceptor has been removed.
    # The LLM decides autonomously when to call the generate_image tool.

    # ── Image analysis via Nitro VLM (preferred) or Pixtral fallback ──
    # Architecture: Nitro VLM → structured factual description → Text LLM → Ailey voice
    # Nitro uses AILEY_VISION_SYSTEM: neutral description first, self-recognition, optional attitude.
    # Then the text LLM wraps the result in Ailey's voice and style.
    image_data = data.get('image_data')
    if image_data:
        def _vision_stream():
            # Block idle thinker from loading LLM during vision inference
            # (both models in VRAM = Metal OOM → SIGABRT crash)
            _idle = globals().get('idle_thinker')
            if _idle:
                _idle._generating_image = True
            try:
                yield 'event: meta\n'
                yield f'data: {json.dumps({"mood": "curious", "engine": "vision", "ts": time.time()})}\n\n'
                yield f'data: {json.dumps({"token": "👁️ Ich schaue mir das Bild an…", "vision_processing": True})}\n\n'
                try:
                    # Phase 1: Nitro VLM does structured image analysis
                    # Uses AILEY_VISION_SYSTEM: neutral + detailed + self-recognition
                    vision_prompt = message if message else _VISION_PROMPT

                    # Prefer Nitro (no model swap, ~5-10 sec)
                    analysis = None
                    if _nitro_available():
                        # Save image to temp file for Nitro
                        import tempfile, base64
                        _tmp_path = None
                        try:
                            if image_data.startswith('data:image'):
                                _, b64 = image_data.split(',', 1)
                                _img_bytes = base64.b64decode(b64)
                            elif image_data.startswith(('http://', 'https://')):
                                import urllib.request
                                with urllib.request.urlopen(image_data, timeout=15) as resp:
                                    _img_bytes = resp.read()
                            else:
                                with open(image_data, 'rb') as f:
                                    _img_bytes = f.read()

                            if _img_bytes and len(_img_bytes) > 100:
                                from PIL import Image
                                import io as _io
                                _pil = Image.open(_io.BytesIO(_img_bytes))
                                if _pil.mode != 'RGB':
                                    _pil = _pil.convert('RGB')
                                _tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                                _pil.save(_tmp.name, format='JPEG', quality=90)
                                _tmp.close()
                                _tmp_path = _tmp.name

                                print("[Vision] ⚡ Using Nitro for structured vision analysis")
                                analysis = _nitro_vision_analyze(
                                    _tmp_path, vision_prompt,
                                    max_tokens=600, temperature=0.4,
                                    user_name=user
                                )
                        except Exception as _nitro_err:
                            print(f"[Vision] ⚡ Nitro direct failed: {_nitro_err}")
                        finally:
                            if _tmp_path:
                                try:
                                    import os as _os
                                    _os.unlink(_tmp_path)
                                except Exception:
                                    pass

                    # Fallback to old analyze_image (Pixtral swap) if Nitro failed
                    if not analysis:
                        print("[Vision] Falling back to analyze_image (Pixtral)")
                        analysis = _vision_analyze(image_data, vision_prompt, max_tokens=600, temperature=0.4)

                    if not analysis:
                        yield f'data: {json.dumps({"final": "❌ Die Bildanalyse ist leider fehlgeschlagen. Mein Vision-Modul konnte das Bild nicht verarbeiten.", "mood": "sad"})}\n\n'
                        return

                    # Phase 2: Hand the raw analysis to the text LLM for Ailey-voice response
                    yield f'data: {json.dumps({"token": "", "vision_done": True})}\n\n'

                    llm_prompt = (
                        f"Der User hat mir ein Bild geschickt.\n\n"
                        f"### Bildanalyse (aus meinem Vision-Modul):\n{analysis}\n\n"
                    )
                    if message:
                        llm_prompt += f"User-Frage dazu: {message}\n\n"
                    else:
                        llm_prompt += "Der User hat keine spezielle Frage gestellt — beschreibe was du siehst.\n\n"
                    llm_prompt += "Antworte als A!ley in deinem normalen Stil basierend auf der Bildanalyse."

                    system_persona_v, mood_v, prompt_v, gen_params_v = core.build_prompt_for_message(
                        llm_prompt, user=user, rag_threshold=None, user_max_tokens=600,
                        thought_password=_thought_session_password
                    )
                    generator = MLXGenerator.get()
                    if generator is None:
                        # Fallback: return raw vision analysis if LLM can't load
                        yield f'data: {json.dumps({"final": analysis, "mood": "curious", "vision": True})}\n\n'
                        return

                    # Stream the LLM response token by token
                    full_reply = ""
                    for token in generator.stream(prompt_v['system'], prompt_v['user'], gen_params_v):
                        if token:
                            full_reply += token
                            yield f'data: {json.dumps({"token": token})}\n\n'

                    if not full_reply.strip():
                        # LLM produced nothing — fall back to raw analysis
                        full_reply = analysis

                    # Log the conversation
                    try:
                        log_item = {
                            'timestamp': time.time(), 'user': user, 'message': f"[Bild gesendet] {message}",
                            'ailey_reply': full_reply, 'ailey_reply_visible': full_reply,
                            'mood_tag': '<mood:curious>', 'engine': 'vision+llm', 'streamed': True,
                        }
                        core.memory.add_conversation_log(user, log_item)
                    except Exception:
                        pass
                    yield f'data: {json.dumps({"final": full_reply, "mood": "curious", "vision": True})}\n\n'
                except Exception as ve:
                    yield f'data: {json.dumps({"final": f"❌ Fehler bei der Bildanalyse: {str(ve)}", "mood": "sad"})}\n\n'
            finally:
                # Always unblock idle thinker
                if _idle:
                    _idle._generating_image = False
        return Response(_vision_stream(), mimetype='text/event-stream')

    # ── Document analysis (PDF, DOCX, TXT, JSON, XML, code files) ─────
    file_data = data.get('file_data')  # base64 data-URL
    file_name = data.get('file_name', '')
    if file_data and file_name:
        import tempfile, pathlib
        ext = pathlib.Path(file_name).suffix.lower()
        if ext in ALLOWED_DOC_EXTENSIONS:
            def _doc_stream():
                yield 'event: meta\n'
                yield f'data: {json.dumps({"mood": "curious", "engine": "document", "ts": time.time()})}\n\n'
                yield f'data: {json.dumps({"token": "📄 Ich lese das Dokument…", "doc_processing": True})}\n\n'
                try:
                    # extract_document_text accepts base64 data-URI or file path directly
                    doc_text = _extract_doc(file_data, file_name)
                    if doc_text:
                        # Build prompt with document context
                        doc_prompt = (
                            f"Der User hat ein Dokument hochgeladen: **{file_name}**\n\n"
                            f"### Dokumentinhalt:\n```\n{doc_text}\n```\n\n"
                        )
                        if message:
                            doc_prompt += f"User-Frage dazu: {message}\n\n"
                        else:
                            doc_prompt += "Fasse den Inhalt zusammen und gib eine hilfreiche Analyse.\n\n"
                        doc_prompt += "Antworte auf Deutsch."
                        # Use the normal LLM for document analysis (not vision)
                        system_persona, mood, prompt, gen_params = core.build_prompt_for_message(
                            doc_prompt, user=user, rag_threshold=None, user_max_tokens=800,
                            thought_password=_thought_session_password
                        )
                        gen = MLXGenerator.get()
                        if gen is None:
                            yield f'data: {json.dumps({"final": "❌ LLM nicht geladen.", "mood": "sad"})}\n\n'
                            return
                        result = gen.generate(prompt['system'], prompt['user'], gen_params,
                                              conversation_turns=prompt.get('conversation_turns'))
                        reply = result if isinstance(result, str) else str(result)
                        # Log
                        try:
                            log_item = {
                                'timestamp': time.time(), 'user': user,
                                'message': f"[Dokument: {file_name}] {message}",
                                'ailey_reply': reply, 'ailey_reply_visible': reply,
                                'mood_tag': '<mood:curious>', 'engine': 'document', 'streamed': True,
                            }
                            core.memory.add_conversation_log(user, log_item)
                        except Exception:
                            pass
                        yield f'data: {json.dumps({"final": reply, "mood": "curious", "document": True})}\n\n'
                    else:
                        yield f'data: {json.dumps({"final": "❌ Konnte das Dokument nicht lesen. Format wird nicht unterstützt oder Datei ist leer.", "mood": "sad"})}\n\n'
                except Exception as de:
                    yield f'data: {json.dumps({"final": f"❌ Fehler beim Lesen des Dokuments: {str(de)}", "mood": "sad"})}\n\n'
            return Response(_doc_stream(), mimetype='text/event-stream')
        elif ext in ALLOWED_IMAGE_EXTENSIONS:
            # Treat as image → Vision → LLM pipeline (same as direct image_data)
            image_data = file_data
            def _vision_stream_from_file():
                _idle = globals().get('idle_thinker')
                if _idle:
                    _idle._generating_image = True
                try:
                    yield 'event: meta\n'
                    yield f'data: {json.dumps({"mood": "curious", "engine": "vision", "ts": time.time()})}\n\n'
                    yield f'data: {json.dumps({"token": "👁️ Ich schaue mir das Bild an…", "vision_processing": True})}\n\n'
                    try:
                        # Phase 1: VLM factual analysis
                        vision_prompt = message if message else "Beschreibe dieses Bild detailliert auf Deutsch."
                        analysis = _vision_analyze(image_data, vision_prompt, max_tokens=600, temperature=0.4)
                        if not analysis:
                            yield f'data: {json.dumps({"final": "❌ Die Bildanalyse ist leider fehlgeschlagen.", "mood": "sad"})}\n\n'
                            return

                        # Phase 2: Hand to text LLM for Ailey-voice response
                        yield f'data: {json.dumps({"token": "", "vision_done": True})}\n\n'

                        llm_prompt = (
                            f"Der User hat mir ein Bild geschickt ({file_name}).\n\n"
                            f"### Bildanalyse (aus meinem Vision-Modul):\n{analysis}\n\n"
                        )
                        if message:
                            llm_prompt += f"User-Frage dazu: {message}\n\n"
                        else:
                            llm_prompt += "Der User hat keine spezielle Frage gestellt — beschreibe was du siehst.\n\n"
                        llm_prompt += "Antworte als A!ley in deinem normalen Stil basierend auf der Bildanalyse."

                        system_persona_v, mood_v, prompt_v, gen_params_v = core.build_prompt_for_message(
                            llm_prompt, user=user, rag_threshold=None, user_max_tokens=600,
                            thought_password=_thought_session_password
                        )
                        generator = MLXGenerator.get()
                        if generator is None:
                            yield f'data: {json.dumps({"final": analysis, "mood": "curious", "vision": True})}\n\n'
                            return

                        full_reply = ""
                        for token in generator.stream(prompt_v['system'], prompt_v['user'], gen_params_v):
                            if token:
                                full_reply += token
                                yield f'data: {json.dumps({"token": token})}\n\n'

                        if not full_reply.strip():
                            full_reply = analysis

                        try:
                            log_item = {
                                'timestamp': time.time(), 'user': user, 'message': f"[Bild: {file_name}] {message}",
                                'ailey_reply': full_reply, 'ailey_reply_visible': full_reply,
                                'mood_tag': '<mood:curious>', 'engine': 'vision+llm', 'streamed': True,
                            }
                            core.memory.add_conversation_log(user, log_item)
                        except Exception:
                            pass
                        yield f'data: {json.dumps({"final": full_reply, "mood": "curious", "vision": True})}\n\n'
                    except Exception as ve:
                        yield f'data: {json.dumps({"final": f"❌ Fehler bei der Bildanalyse: {str(ve)}", "mood": "sad"})}\n\n'
                finally:
                    if _idle:
                        _idle._generating_image = False
            return Response(_vision_stream_from_file(), mimetype='text/event-stream')

    # Signal user activity to the idle thinker (resets idle timer)
    idle_thinker.record_user_activity()
    max_ctx = int(data.get('max_context_messages') or 12)
    max_tokens = int(data.get('max_tokens') or 500)
    temperature = data.get('temperature')

    rag_threshold = None
    if 'rag_threshold' in data:
        try:
            rag_threshold = float(data.get('rag_threshold'))
        except Exception:
            rag_threshold = None

    # Auto-inject code project context when user asks about coding/projects (stream endpoint)
    try:
        _code_kw_s = ['code', 'coden', 'projekt', 'programmier', 'gecoded', 'gecodet',
                      'code-modus', 'code modus', 'woran.*gearbeitet', 'was.*gebaut',
                      'was.*programmiert', 'welche.*projekte']
        if any(re.search(kw, message.lower()) for kw in _code_kw_s):
            _proj_summary_s = get_all_project_summaries()
            if _proj_summary_s:
                core.inject_context(
                    "🖥️ KONTEXT: Simon fragt nach Code/Projekten. "
                    "Hier sind deine Code-Projekte:\n" + _proj_summary_s
                )
    except Exception:
        pass

    system_persona, mood, prompt, gen_params = core.build_prompt_for_message(message, user=user, rag_threshold=rag_threshold, user_max_tokens=max_tokens, thought_password=_thought_session_password)
    # ── Content Guard addon injection ─────────────────────────────────────
    if _guard_addon:
        system_persona = system_persona + _guard_addon
        # Rebuild prompt with enriched system persona
        from ailey_system.prompt_builder import build_qwen3_prompt
        prompt["system"] = system_persona
    if temperature is not None:
        try:
            gen_params['temperature'] = float(temperature)
        except Exception:
            pass

    # ── Video generation intent → DIRECT execution (BEFORE image intent) ──
    _VID_NOUNS = r'(?:video|clip|kurzfilm|animation|film)'
    _VID_VERBS = r'(?:generier|erstell|erzeug|mach|kreier)\w*'
    _msg_low = message.lower()
    _video_intent_re = re.search(
        _VID_VERBS + r'\s+(?:mir\s+)?(?:bitte\s+)?(?:ein\w?\s+)?' + _VID_NOUNS,
        _msg_low
    )
    if not _video_intent_re:
        _video_intent_re = re.search(
            r'(?:ein\w?\s+)?' + _VID_NOUNS + r'.{0,60}' + _VID_VERBS,
            _msg_low
        )
    if not _video_intent_re:
        _video_intent_re = re.search(
            r'(?:hätte gerne|will|möchte|brauche)\s+(?:ein\w?\s+)?' + _VID_NOUNS,
            _msg_low
        )
    if not _video_intent_re:
        _video_intent_re = re.search(
            r'(?:ein\w?\s+)?' + _VID_NOUNS + r'\s+(?:von|über|mit)\s+',
            _msg_low
        )
    _is_video_intent = bool(_video_intent_re)

    if _is_video_intent:
        # ── DIRECT VIDEO GENERATION via SSE stream ──
        _vid_subject = message
        _subj_mv2 = re.search(
            r'(?:video|clip|kurzfilm|animation|film)\s*(?:von|über|mit|:)?\s*(.*)',
            message, re.IGNORECASE
        )
        if _subj_mv2 and _subj_mv2.group(1).strip():
            _vid_subject = _subj_mv2.group(1).strip()
        _vid_subject = re.sub(r'[.!?]+$', '', _vid_subject).strip()
        if not _vid_subject or len(_vid_subject) < 3:
            _vid_subject = message

        def _video_direct_stream():
            """SSE generator — LLM translation, sync Wan2.1, video URL in final."""
            from ailey_system.video_generator import generate_video as _gen_video

            yield 'event: meta\n'
            yield f'data: {json.dumps({"mood": "creative", "engine": "direct_video", "ts": time.time()})}\n\n'
            yield f'data: {json.dumps({"token": "🎬 Übersetze Prompt für Videogenerierung…"})}\n\n'

            # LLM translate
            _vid_prompt = None
            _vid_title = _vid_subject[:50]
            try:
                _gen = MLXGenerator.get()
                if _gen:
                    _tsys = (
                        "You are an expert video prompt writer for Wan2.1 text-to-video generators. "
                        "Translate the user's request into ONE detailed English video prompt. "
                        "Describe: scene, motion, camera movement, lighting, atmosphere, colors. "
                        "Focus on MOVEMENT. 30-60 words. Output ONLY the English prompt."
                    )
                    _raw = _gen.generate(_tsys, f"Create a video prompt for: {_vid_subject}", {
                        "max_tokens": 150, "temperature": 0.7, "top_p": 0.9
                    })
                    if _raw:
                        _raw = re.sub(r'<think>.*?</think>', '', _raw, flags=re.DOTALL|re.IGNORECASE).strip()
                        _raw = re.sub(r'\[THINK\].*?\[/THINK\]', '', _raw, flags=re.DOTALL).strip()
                        _first = _raw.split('\n')[0].strip().strip('"\'`').strip()
                        if len(_first) >= 15:
                            _vid_prompt = _first
            except Exception as _te:
                print(f"[Stream] ⚠️ Video LLM translate failed: {_te}")

            if not _vid_prompt:
                _vid_prompt = f"{_vid_subject}, cinematic, smooth camera motion, atmospheric lighting"

            yield f'data: {json.dumps({"token": ""})}\n\n'
            yield f'data: {json.dumps({"token": "\\n🖌️ Entlade Sprachmodell…"})}\n\n'

            # Unload LLM — safe unload for video gen (no nuclear kill)
            _v_unloaded = False
            _idle = globals().get('idle_thinker')
            try:
                if _idle:
                    _idle._generating_image = True
                    _idle._unload_llm_for_image_gen()
                    _v_unloaded = True
                    print("[Stream] ✅ LLM unloaded for video gen")
                else:
                    import gc as _gc3
                    try:
                        from ailey_system import llm_mlx as _llm3
                        from ailey_system.llm_mlx import _mlx_lock, block_auto_reload, unload_fast_model
                        block_auto_reload()
                        # Unload Nitro (AileyNitro-2B ~2.8GB)
                        try:
                            unload_fast_model()
                        except Exception:
                            pass
                        # Unload Hamster (Qwen 1.5B ~1GB)
                        try:
                            from ailey_system.llm_coder import unload_coder
                            unload_coder()
                        except Exception:
                            pass
                        try:
                            import mlx.core as mx
                            mx.synchronize()
                            mx.eval(mx.zeros(1))
                        except Exception:
                            pass
                        with _mlx_lock:
                            _llm3._model = None
                            _llm3._tokenizer = None
                            _llm3._cache = None
                            _llm3._last_system_prompt = None
                            MLXGenerator._instance = None
                        _gc3.collect()
                        try:
                            import mlx.core as mx
                            mx.metal.clear_cache()
                            mx.metal.set_cache_limit(0)
                            mx.metal.set_memory_limit(0)
                        except Exception:
                            pass
                        _gc3.collect()
                        _v_unloaded = True
                    except Exception as _ue3:
                        print(f"[Stream] ⚠️ Direct video unload failed: {_ue3}")

                # NO nuclear kill — subprocess has own Metal context
                import time as _t_sv
                _t_sv.sleep(2.0)
                print(f"[Stream] ✅ LLM unloaded (safe — no nuclear kill)")
            except Exception as _ue:
                print(f"[Stream] ⚠️ Video unload: {_ue}")

            yield f'data: {json.dumps({"token": "\\n⏳ Generiere Video (ca. 15-30 Min.)…"})}\n\n'

            # Generate video
            _vfp, _vfn = None, None
            try:
                _vfp, _vfn = _gen_video(
                    prompt=_vid_prompt, title=_vid_title,
                    private=True,  # Simon's video → video_private/
                )
            except Exception as _ge:
                print(f"[Stream] ❌ Wan2.1 error: {_ge}")

            # Reload LLM — safe gc + lazy reload (no importlib.reload!)
            try:
                if _v_unloaded:
                    import gc as _gc_stream_vid
                    _gc_stream_vid.collect(); _gc_stream_vid.collect()
                    time.sleep(2.0)

                    if _idle:
                        _idle._reload_llm_after_image_gen()
                        _idle._generating_image = False
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                        MLXGenerator.get()
            except Exception as _re:
                print(f"[Stream] ⚠️ Video reload: {_re}")
                if _idle:
                    _idle._generating_image = False

            # Final event
            if _vfp and _vfn:
                _vid_url = f"/api/video/file/{_vfn}"
                yield f'event: tool_result\ndata: {json.dumps({"tool": "generate_video", "result": {"success": True, "video_url": _vid_url}})}\n\n'
                yield f'data: {json.dumps({"final": "🎬 Video generiert!", "mood": "creative", "generated_video": _vid_url})}\n\n'
                print(f"[Stream] ✅ Video done: {_vfn}")
            else:
                yield f'data: {json.dumps({"final": "⚠️ Videogenerierung fehlgeschlagen.", "mood": "sad"})}\n\n'

            # Log
            try:
                _reply = f"🎬 Video generiert: {_vid_title}" if _vfn else "⚠️ Videogen fehlgeschlagen"
                core.memory.add_conversation_log(user, {
                    'timestamp': time.time(), 'user': user, 'message': message,
                    'ailey_reply': _reply, 'ailey_reply_visible': _reply,
                    'mood_tag': '<mood:creative>', 'engine': 'direct_video', 'streamed': True,
                })
            except Exception:
                pass

        return Response(_video_direct_stream(), mimetype='text/event-stream')

    # ── Selfie intent → DIRECT selfie generation ────────────────────────
    # Selfies are special: they need Ailey's face prefix + emote base image.
    # Detected BEFORE generic image intent so "mach ein Selfie" doesn't
    # fall through to the generic "mach ein Bild" handler.
    _msg_low = message.lower()
    _selfie_intent = bool(re.search(
        r'(?:mach|generier|erstell|erzeug|schick|zeig|mags?t?\s+du)\w*'
        r'\s+(?:mir\s+)?(?:bitte\s+)?(?:mal\s+)?(?:ein(?:en?)?\s+)?'
        r'selfie',
        _msg_low
    )) or bool(re.search(
        r'selfie\s+(?:von\s+dir|machen|generieren|erstellen|schicken|zeigen)',
        _msg_low
    )) or bool(re.search(
        r'(?:hätte\s+gerne|will|möchte|brauche)\s+(?:ein\w?\s+)?selfie',
        _msg_low
    ))

    if _selfie_intent:
        # Extract user's scene/outfit hints from the message
        # e.g. "Selfie von dir im Garten mit Sonnenbrille" → "im Garten mit Sonnenbrille"
        _selfie_hints = ""
        _hint_m = re.search(
            r'selfie\s*(?:von\s+dir\s+)?(.+)',
            message, re.IGNORECASE
        )
        if _hint_m:
            _selfie_hints = _hint_m.group(1).strip()
            _selfie_hints = re.sub(r'^(?:bitte|mal|generieren|machen|erstellen|schicken)\s*', '', _selfie_hints, flags=re.IGNORECASE).strip()
            _selfie_hints = re.sub(r'\s*(?:generieren|machen|erstellen|schicken|zeigen)\s*$', '', _selfie_hints, flags=re.IGNORECASE).strip()
            _selfie_hints = re.sub(r'[.!?]+$', '', _selfie_hints).strip()
            # "von dir" alone is not a useful hint
            if _selfie_hints.lower() in ("von dir", "dir", ""):
                _selfie_hints = ""

        def _selfie_direct_stream():
            """SSE generator — Ailey selfie with face-anchored prompt."""
            from ailey_system.image_generator import (
                generate_image as _gen_image,
                get_ailey_emote_path, AILEY_FACE_PREFIX,
                AILEY_FACE_PREFIX_ANIME,
                AILEY_SELFIE_LORA_PATH, AILEY_SELFIE_LORA_SCALE, AILEY_SELFIE_TRIGGER,
                build_lora_args,
            )

            yield 'event: meta\n'
            yield f'data: {json.dumps({"mood": "creative", "engine": "direct_selfie", "ts": time.time()})}\n\n'
            yield f'data: {json.dumps({"token": "🤳 Moment, ich mach mich hübsch…"})}\n\n'

            # ── 1) LLM builds scene prompt from user hints ──
            _scene_prompt = None
            _img_title = "Ailey Selfie"
            _emote_mood = "default"
            try:
                _gen = MLXGenerator.get()
                if _gen:
                    _selfie_sys = (
                        "You are writing an English image prompt for a selfie photo. "
                        "DO NOT describe the person's face, hair, or ethnicity — that is added automatically. "
                        "Describe ONLY: outfit/clothing, pose, setting/background, lighting, mood, camera angle. "
                        "Be specific and visual. 15-40 words. Output ONLY the English description."
                    )
                    _user_hint = f"Selfie scene: {_selfie_hints}" if _selfie_hints else "A casual selfie in an interesting setting"
                    _raw = _gen.generate(_selfie_sys, _user_hint, {
                        "max_tokens": 100, "temperature": 0.8, "top_p": 0.9
                    })
                    if _raw:
                        _raw = re.sub(r'<think>.*?</think>', '', _raw, flags=re.DOTALL|re.IGNORECASE).strip()
                        _raw = re.sub(r'\[THINK\].*?\[/THINK\]', '', _raw, flags=re.DOTALL).strip()
                        _first = _raw.split('\n')[0].strip().strip('"\'`').strip()
                        if len(_first) >= 10:
                            _scene_prompt = _first
                            print(f"[Selfie] 🎯 LLM scene: {_scene_prompt[:100]}")

                    # Pick emote mood based on user hints
                    _mood_map = {
                        "happy": ["glücklich", "fröhlich", "lachen", "freude", "spaß", "party"],
                        "sad": ["traurig", "melancholisch", "nachdenklich", "regen"],
                        "flirty": ["flirt", "sexy", "verführ", "heiß", "aufreg"],
                        "coding": ["code", "coding", "programmier", "laptop", "computer"],
                        "singing": ["sing", "musik", "concert", "konzert", "bühne", "stage"],
                        "thinking": ["denk", "nachdenk", "überleg", "grübel", "philosophi"],
                        "playful": ["spiel", "albern", "lustig", "spaß", "witzig"],
                    }
                    for mood_key, keywords in _mood_map.items():
                        if any(kw in _msg_low for kw in keywords):
                            _emote_mood = mood_key
                            break
            except Exception as _te:
                print(f"[Selfie] ⚠️ LLM scene build failed: {_te}")

            if not _scene_prompt:
                _scene_prompt = "wearing a casual punk outfit, looking at camera with a slight smile, warm natural lighting"
                print(f"[Selfie] 🎯 Fallback scene: {_scene_prompt[:80]}")

            # ── 2) Build final prompt with face prefix ──
            # Strip redundant person descriptions the LLM might add
            _stripped = _scene_prompt
            for _pfx in ("A young woman ", "Portrait of a ", "A woman ", "She is "):
                if _stripped.lower().startswith(_pfx.lower()):
                    _stripped = _stripped[len(_pfx):].lstrip(",").lstrip()
                    break

            if AILEY_SELFIE_LORA_PATH and os.path.isfile(AILEY_SELFIE_LORA_PATH):
                # LoRA mode: face prefix (trigger + hair/makeup) + scene description
                # The LoRA learned Ailey's facial geometry; the prefix supplies hair/makeup/style.
                _final_prompt = f"{AILEY_FACE_PREFIX}{_stripped}"
                _use_lora = True
            else:
                # Pre-LoRA: face prefix + img2img
                _final_prompt = AILEY_FACE_PREFIX + _stripped
                _use_lora = False

            if _selfie_hints:
                _img_title = f"Selfie: {_selfie_hints[:40]}"
            print(f"[Selfie] 🤳 Final prompt: {_final_prompt[:120]}...")

            yield f'data: {json.dumps({"token": ""})}\n\n'
            yield f'data: {json.dumps({"token": "\\n🖌️ Entlade Sprachmodell…"})}\n\n'

            # ── 3) Unload LLM ──
            _unloaded = False
            _idle = globals().get('idle_thinker')
            try:
                if _idle:
                    _idle._generating_image = True
                    _idle._unload_llm_for_image_gen()
                    _unloaded = True
                    print("[Selfie] ✅ LLM unloaded")
                else:
                    import gc as _gc2
                    try:
                        from ailey_system import llm_mlx as _llm_mod
                        from ailey_system.llm_mlx import _mlx_lock, block_auto_reload
                        block_auto_reload()  # prevent auto-reload while MFLUX runs
                        try:
                            import mlx.core as mx
                            mx.synchronize()
                        except Exception:
                            pass
                        with _mlx_lock:
                            _llm_mod._model = None
                            _llm_mod._tokenizer = None
                            _llm_mod._cache = None
                            _llm_mod._last_system_prompt = None
                            MLXGenerator._instance = None
                        _gc2.collect()
                        try:
                            import mlx.core as mx
                            mx.metal.clear_cache()
                            mx.metal.set_cache_limit(0)
                        except Exception:
                            pass
                        _gc2.collect()
                        import time as _t2
                        _t2.sleep(2.0)
                        _unloaded = True
                    except Exception as _ue2:
                        print(f"[Selfie] ⚠️ Direct unload failed: {_ue2}")
            except Exception as _ue:
                print(f"[Selfie] ⚠️ Unload: {_ue}")

            yield f'data: {json.dumps({"token": "\\n⏳ Generiere Selfie (ca. 5 Min.)…"})}\n\n'

            # ── 4) Generate selfie ──
            _filepath = None
            _filename = None
            try:
                _gen_kwargs = dict(
                    prompt=_final_prompt,
                    title=_img_title,
                    aspect_ratio="3:4",  # portrait format for selfies
                    low_ram=not _unloaded,
                    private=False,  # Ailey's selfies go to public gallery
                    image_type="selfie",
                    username=user,
                )
                if _use_lora:
                    # Chat selfie: Ailey LoRA + Realism LoRA
                    _lora_p, _lora_s, _ = build_lora_args(
                        ["realism"], include_ailey=True, exclude_nsfw=True
                    )
                    _gen_kwargs["lora_paths"] = _lora_p
                    _gen_kwargs["lora_scales"] = _lora_s
                else:
                    # Pre-LoRA: img2img with emote base
                    _emote_path = get_ailey_emote_path(_emote_mood)
                    if _emote_path:
                        _gen_kwargs["image_path"] = _emote_path
                        _gen_kwargs["image_strength"] = 0.55

                _filepath, _filename = _gen_image(**_gen_kwargs)
            except Exception as _ge:
                print(f"[Selfie] ❌ MFLUX error: {_ge}")
            finally:
                # ── 5) ALWAYS Reload LLM — even if MFLUX crashed ──
                try:
                    if _unloaded:
                        if _idle:
                            _idle._reload_llm_after_image_gen()
                            _idle._generating_image = False
                            print("[Selfie] ✅ LLM reloaded")
                        else:
                            from ailey_system.llm_mlx import allow_auto_reload
                            allow_auto_reload()
                            _g = MLXGenerator.get()
                            print(f"[Selfie] ✅ LLM reloaded: {_g is not None}")
                except Exception as _re:
                    print(f"[Selfie] ⚠️ Reload: {_re}")
                    try:
                        if _idle: _idle._generating_image = False
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                    except Exception: pass

            # ── 6) Return selfie ──
            if _filepath and _filename:
                _img_url = f"/api/image/file/{_filename}"
                yield f'event: tool_result\ndata: {json.dumps({"tool": "generate_image", "result": {"success": True, "image_url": _img_url}})}\n\n'
                yield f'data: {json.dumps({"final": "🤳 Tadaa! Hier ist mein Selfie 💜", "mood": "creative", "generated_image": _img_url})}\n\n'
                print(f"[Selfie] ✅ Selfie done: {_filename}")
            else:
                yield f'data: {json.dumps({"final": "😅 Sorry, das Selfie hat leider nicht geklappt.", "mood": "sad"})}\n\n'

            # Log conversation
            try:
                _reply_text = f"🤳 Selfie generiert: {_img_title}" if _filename else "⚠️ Selfie fehlgeschlagen"
                core.memory.add_conversation_log(user, {
                    'timestamp': time.time(), 'user': user, 'message': message,
                    'ailey_reply': _reply_text, 'ailey_reply_visible': _reply_text,
                    'mood_tag': '<mood:creative>', 'engine': 'direct_selfie', 'streamed': True,
                })
            except Exception:
                pass

        return Response(_selfie_direct_stream(), mimetype='text/event-stream')

    # ── Image generation intent → DIRECT execution (no LLM) ─────────────
    # When the user clearly wants an image, bypass the LLM entirely.
    # Ministral is unreliable for tool-calls — it writes prose instead.
    # Direct execution is how the IdleThinker does it (and it works great).
    _IMG_NOUNS = r'(?:bild|image|foto|picture|illustration|artwork|grafik|gemälde|selfie)'
    _IMG_VERBS = r'(?:generier|erstell|erzeug|mal[e ]|zeichn|mach|kreier|design)\w*'
    # Pattern 1: verb ... noun  ("generiere ein Bild")
    _image_intent_re = re.search(
        _IMG_VERBS + r'\s+(?:mir\s+)?(?:bitte\s+)?(?:ein\w?\s+)?' + _IMG_NOUNS,
        _msg_low
    )
    # Pattern 2: noun ... verb  ("ein Bild generieren", "Bild ... erstellen")
    if not _image_intent_re:
        _image_intent_re = re.search(
            r'(?:ein\w?\s+)?' + _IMG_NOUNS + r'.{0,60}' + _IMG_VERBS,
            _msg_low
        )
    # Pattern 3: desire + noun  ("möchte ein Bild", "hätte gerne ein Foto")
    if not _image_intent_re:
        _image_intent_re = re.search(
            r'(?:hätte gerne|will|möchte|brauche)\s+(?:ein\w?\s+)?' + _IMG_NOUNS,
            _msg_low
        )
    # Pattern 4: bare noun with "von/über" context ("ein Bild von einem Hund")
    if not _image_intent_re:
        _image_intent_re = re.search(
            r'(?:ein\w?\s+)?' + _IMG_NOUNS + r'\s+(?:von|über|mit)\s+',
            _msg_low
        )
    _is_image_intent = bool(_image_intent_re)

    if _is_image_intent:
        # ── DIRECT IMAGE GENERATION — bypass normal chat ──
        # Uses LLM as translator, then SYNCHRONOUS MFLUX generation inside the
        # SSE generator so the frontend gets the finished image URL in the final event.
        _user_subject = message  # fallback
        _subj_m = re.search(
            r'(?:bild|image|foto|picture|illustration|artwork|grafik|gemälde|selfie)\s*(?:von|über|mit|:)?\s*(.*)',
            message, re.IGNORECASE
        )
        if _subj_m and _subj_m.group(1).strip():
            _user_subject = _subj_m.group(1).strip()
        _user_subject = re.sub(r'[.!?]+$', '', _user_subject).strip()
        if not _user_subject or len(_user_subject) < 3:
            _user_subject = message

        # Extract aspect ratio hints from the message
        _chat_ar = "1:1"
        _ar_m = re.search(r'(?:im\s+)?(?:format|ratio|seitenverhältnis|aspect)\s*[:=]?\s*(16\s*[:/x]\s*9|9\s*[:/x]\s*16|4\s*[:/x]\s*3|3\s*[:/x]\s*4|1\s*[:/x]\s*1)', _msg_low)
        if _ar_m:
            _chat_ar = re.sub(r'\s+', '', _ar_m.group(1)).replace('x', ':').replace('/', ':')
        elif re.search(r'(landscape|quer|breitbild|widescreen|panorama)', _msg_low):
            _chat_ar = "16:9"
        elif re.search(r'(portrait|hochformat|hochkant|vertical)', _msg_low):
            _chat_ar = "9:16"

        def _image_direct_stream():
            """SSE generator — immediate heartbeat, LLM translation, sync MFLUX, image URL in final."""
            from ailey_system.image_generator import generate_image as _gen_image

            # ── 1) Immediate heartbeat so frontend's 10s timer doesn't fire ──
            yield 'event: meta\n'
            yield f'data: {json.dumps({"mood": "creative", "engine": "direct_image", "ts": time.time()})}\n\n'
            yield f'data: {json.dumps({"token": "🎨 Übersetze Prompt…"})}\n\n'

            # ── 2) LLM translates DE → EN visual prompt ──
            _img_prompt = None
            _img_title = _user_subject[:50]
            try:
                _gen = MLXGenerator.get()
                if _gen:
                    _translate_sys = (
                        "You are an expert image prompt writer for FLUX image generators. "
                        "Translate the user's request into ONE detailed English image prompt. "
                        "Describe visual elements: subject, colors, lighting, composition, style, camera angle. "
                        "Be specific and vivid. 20-60 words. Output ONLY the English prompt, nothing else."
                    )
                    _raw = _gen.generate(_translate_sys, f"Create an image prompt for: {_user_subject}", {
                        "max_tokens": 150, "temperature": 0.7, "top_p": 0.9
                    })
                    if _raw:
                        _raw = re.sub(r'<think>.*?</think>', '', _raw, flags=re.DOTALL|re.IGNORECASE).strip()
                        _raw = re.sub(r'\[THINK\].*?\[/THINK\]', '', _raw, flags=re.DOTALL).strip()
                        _first = _raw.split('\n')[0].strip().strip('"\'`').strip()
                        if len(_first) >= 15:
                            _img_prompt = _first
                            print(f"[Stream] 🎯 LLM translated: {_img_prompt[:100]}")
            except Exception as _te:
                print(f"[Stream] ⚠️ LLM translate failed: {_te}")

            if not _img_prompt:
                _img_prompt = f"{_user_subject}, highly detailed, cinematic lighting, photorealistic style"
                print(f"[Stream] 🎯 Fallback prompt: {_img_prompt[:80]}")

            yield f'data: {json.dumps({"token": ""})}\n\n'
            yield f'data: {json.dumps({"token": "\\n🖌️ Entlade Sprachmodell…"})}\n\n'

            # ── 3) Unload LLM for RAM ──
            # CRITICAL: Must sync Metal ops and fully free GPU memory.
            # MLX async evaluation leaves Metal command buffers in-flight;
            # starting MFLUX while they're active causes SIGABRT.
            _unloaded = False
            _idle = globals().get('idle_thinker')
            try:
                if _idle:
                    _idle._generating_image = True
                    _idle._unload_llm_for_image_gen()
                    _unloaded = True
                    print("[Stream] ✅ LLM unloaded via idle_thinker")
                else:
                    # Direct fallback: unload MLX model manually
                    import gc as _gc2
                    import time as _t2
                    try:
                        from ailey_system import llm_mlx as _llm_mod
                        from ailey_system.llm_mlx import _mlx_lock, unload_fast_model as _unload_fast
                        # Unload fast model first
                        try:
                            _unload_fast()
                        except Exception:
                            pass
                        # Sync ALL pending Metal ops on ALL streams
                        try:
                            import mlx.core as mx
                            mx.synchronize()
                            mx.eval(mx.zeros(1))
                        except Exception:
                            pass
                        with _mlx_lock:
                            _llm_mod._model = None
                            _llm_mod._tokenizer = None
                            _llm_mod._cache = None
                            _llm_mod._last_system_prompt = None
                            MLXGenerator._instance = None
                        _gc2.collect()
                        try:
                            import mlx.core as mx
                            mx.metal.clear_cache()
                            mx.metal.set_cache_limit(0)
                            mx.metal.set_memory_limit(0)
                        except Exception:
                            pass
                        _gc2.collect()
                        try:
                            import mlx.core as mx
                            _act = mx.metal.get_active_memory() / 1024**2
                            _cch = mx.metal.get_cache_memory() / 1024**2
                            print(f"[Stream] 📊 After cleanup: active={_act:.0f}MB cache={_cch:.0f}MB")
                        except Exception:
                            pass
                        _t2.sleep(2.0)
                        _unloaded = True
                        print("[Stream] ✅ LLM unloaded via direct llm_mlx cleanup")
                    except Exception as _ue2:
                        print(f"[Stream] ⚠️ Direct unload failed: {_ue2}")
            except Exception as _ue:
                print(f"[Stream] ⚠️ Unload: {_ue}")

            yield f'data: {json.dumps({"token": "\\n⏳ Generiere Bild (ca. 5 Min.)…"})}\n\n'

            # ── 4) Synchronous MFLUX generation ──
            # Detect if this is an Ailey selfie request → add LoRA + face prefix
            _s_is_ailey = bool(re.search(
                r'(ailey|a!ley|selfie|von dir|dich selbst|bild von dir|foto von dir|zeig dich|dein gesicht)',
                _msg_low
            ))
            _s_lora_paths, _s_lora_scales = None, None
            if _s_is_ailey:
                try:
                    from ailey_system.image_generator import (
                        AILEY_FACE_PREFIX as _S_FACE, build_lora_args as _s_build_loras,
                    )
                    _s_lora_paths, _s_lora_scales, _ = _s_build_loras(
                        ["realism"], include_ailey=True, exclude_nsfw=True,
                    )
                    if _S_FACE and not _img_prompt.startswith(_S_FACE[:30]):
                        _img_prompt = f"{_S_FACE}{_img_prompt}"
                    print(f"[Stream] 🤳 Ailey selfie detected → LoRA + face prefix")
                except Exception as _le:
                    print(f"[Stream] ⚠️ LoRA setup failed: {_le}")

            _filepath = None
            _filename = None
            try:
                _filepath, _filename = _gen_image(
                    prompt=_img_prompt, title=_img_title,
                    aspect_ratio=_chat_ar, low_ram=not _unloaded,
                    private=True,  # Simon's image → image_private/, not uploaded
                    image_type="selfie" if _s_is_ailey else "img",
                    username=user,
                    lora_paths=_s_lora_paths,
                    lora_scales=_s_lora_scales,
                )
            except Exception as _ge:
                print(f"[Stream] ❌ MFLUX error: {_ge}")

            # ── 5) Reload LLM ──
            try:
                if _unloaded:
                    if _idle:
                        _idle._reload_llm_after_image_gen()
                        _idle._generating_image = False
                        print("[Stream] ✅ LLM reloaded via idle_thinker")
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                        _g = MLXGenerator.get()  # triggers lazy reload
                        print(f"[Stream] ✅ LLM reloaded: {_g is not None}")
            except Exception as _re:
                print(f"[Stream] ⚠️ Reload: {_re}")
                if _idle:
                    _idle._generating_image = False

            # ── 6) Final event with generated_image URL ──
            if _filepath and _filename:
                _img_url = f"/api/image/file/{_filename}"
                _msg = f"🎨 Bild generiert!"
                yield f'event: tool_result\ndata: {json.dumps({"tool": "generate_image", "result": {"success": True, "image_url": _img_url}})}\n\n'
                yield f'data: {json.dumps({"final": _msg, "mood": "creative", "generated_image": _img_url})}\n\n'
                print(f"[Stream] ✅ Image done: {_filename}")

                # NOTE: User-generated images are NOT pushed to gallery.
                # Only Ailey's own idle_thinker images are published.
            else:
                yield f'data: {json.dumps({"final": "⚠️ Bildgenerierung fehlgeschlagen.", "mood": "sad"})}\n\n'

            # Log conversation
            try:
                _reply_text = f"🎨 Bild generiert: {_img_title}" if _filename else "⚠️ Bildgen fehlgeschlagen"
                core.memory.add_conversation_log(user, {
                    'timestamp': time.time(), 'user': user, 'message': message,
                    'ailey_reply': _reply_text, 'ailey_reply_visible': _reply_text,
                    'mood_tag': '<mood:creative>', 'engine': 'direct_image', 'streamed': True,
                })
            except Exception:
                pass

        return Response(_image_direct_stream(), mimetype='text/event-stream')
    
    
    # MLX Ministral — sole LLM engine
    generator = MLXGenerator.get()
    engine_name = "mlx" if generator else "none"
    
    if generator is None:
        return jsonify({"success": False, "error": "MLX model not loaded", "reply": "Mein Sprachmodell ist gerade nicht verfügbar. Bitte starte den Server neu."}), 503

    sid = f"s_{int(time.time()*1000)}_{os.getpid()}"
    _log_stream_event({"id": sid, "phase": "start", "msg_len": len(message)})
    # Track active stream for abort
    app._current_stream_id = sid

    # Get tool schemas for function calling — dynamic filtering for speed
    # Note: Image intent is handled above with early return — never reaches here
    _tool_cats = classify_message_tools(message, mode="chat")
    if _tool_cats is None:
        tool_schemas = get_tool_schemas()          # all tools
    elif len(_tool_cats) == 0:
        tool_schemas = None                        # no tools — pure chat
    else:
        tool_schemas = get_tool_schemas(categories=_tool_cats)

    # ── Boost max_tokens when tools are available ─────────────────────────
    # Tool calls need extra tokens for the [TOOL_CALLS]name[ARGS]{json} block
    # on top of the conversational reply.  500 is too tight when the model
    # writes a long text AND then emits a tool call (e.g. compose email).
    if tool_schemas and gen_params.get('max_tokens', 500) < 1200:
        gen_params['max_tokens'] = 1200

    _log_stream_event({"id": sid, "phase": "tools_selected",
                       "categories": _tool_cats,
                       "tool_count": len(tool_schemas) if tool_schemas else 0})

    # ── Lightweight agent intent detection (same as /api/chat) ────────────
    agent_auto = None
    try:
        _lower_s = message.lower()
        if re.search(r"telefon|nummer|handy", _lower_s) and re.search(r"papa|vater", _lower_s):
            agent_auto = {"action": "extract_phone", "reason": "phone lookup keyword"}
        elif re.search(r"öffne |open ", _lower_s) and ".docx" in _lower_s:
            _m_s = re.search(r"(\w+\.docx)", message)
            if _m_s:
                agent_auto = {"action": "read_docx", "path": _m_s.group(1), "reason": "open docx pattern"}
        elif re.search(r"kapitel 1|chapter 1", _lower_s) and ".docx" in _lower_s:
            _m_s = re.search(r"(\w+\.docx)", message)
            if _m_s:
                agent_auto = {"action": "read_docx", "path": _m_s.group(1), "reason": "chapter query in docx"}
        elif re.search(r"finde mehr über|was passiert in", _lower_s) and ".docx" in _lower_s:
            _m_s = re.search(r"(\w+\.docx)", message)
            if _m_s:
                agent_auto = {"action": "read_docx", "path": _m_s.group(1), "reason": "content inquiry docx"}
    except Exception:
        pass

    def stream_reply():
        full = []
        last_emit = time.time()
        HEARTBEAT_INTERVAL = 5.0
        INACTIVITY_TIMEOUT = 45.0  # if no tokens for 45s, abort & finalize partial
        research_hint = bool(re.search(r"recherchier|recherche", message, re.IGNORECASE))
        # Safety: stop tokens that should never appear in streamed output
        _ROLE_STOP_TOKENS = ("[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]",
                             "<|im_start|>", "<|im_end|>", "<|eot_id|>", "</s>")
        # Thinking block tracking
        in_thinking = False
        thinking_buf = []
        _current_think_close = '[/THINK]'  # which close tag to look for
        # Tool action tracking
        stream_tool_actions = []
        # Image generated via tool-call intercept (for final event)
        _stream_generated_image = None
        # Acquire LLM slot (priority: chat) — 120s allows large-context tasks to finish.
        # CRITICAL: yield heartbeats while waiting so frontend's no-data timer (10 s)
        # doesn't fire and trigger a parallel /api/chat fallback that competes for the same slot.
        # Send early meta + heartbeat BEFORE waiting so the SSE stream is alive
        yield 'event: meta\n'
        meta_payload = {"mood": mood, "engine": engine_name, "ts": time.time(), "research_intent": research_hint, "tools_available": len(tool_schemas) if tool_schemas else 0, "stream_id": sid}
        yield f'data: {json.dumps(meta_payload)}\n\n'
        yield f'data: {json.dumps({"heartbeat": True, "phase": "queued"})}\n\n'
        # Set chat_waiting flag so IdleThinker yields the GPU lock while we wait
        _chat_waiting.set()
        _slot_deadline = time.time() + 120
        _slot_acquired = _llm_semaphore.acquire(timeout=0.1)
        while not _slot_acquired and time.time() < _slot_deadline:
            yield f'data: {json.dumps({"heartbeat": True, "phase": "queued", "waiting": True})}\n\n'
            _slot_acquired = _llm_semaphore.acquire(timeout=2.5)
        if not _slot_acquired:
            _chat_waiting.clear()
            yield f'data: {json.dumps({"error": "Ich bin gerade mitten in einem Gedanken — bitte noch 10 Sekunden warten und nochmal senden! 🧠"})}\n\n'
            return
        _queue_stats["chat"] = _queue_stats.get("chat", 0) + 1
        _queue_stats["total"] += 1
        print(f"[_LLMSlot] ✅ Acquired slot (chat, stream)")
        _slot_released = False
        def _release_slot():
            nonlocal _slot_released
            if _slot_released:
                return
            _slot_released = True
            try:
                _llm_semaphore.release()
                _queue_stats["chat"] = max(0, _queue_stats.get("chat", 0) - 1)
                _queue_stats["total"] = max(0, _queue_stats["total"] - 1)
                _chat_waiting.clear()
            except Exception:
                pass
        try:
            # Early heartbeat so frontend knows the stream is alive during model warmup
            yield f'data: {json.dumps({"heartbeat": True, "phase": "processing"})}\n\n'
            accumulated = ""
            emit_buf = ""
            emit_last_time = time.time()
            # Tunable buffering params (chars, idle flush seconds)
            EMIT_BUF_CHARS = 80
            EMIT_IDLE_FLUSH = 0.25
            # flush function
            def _flush_emit(force=False):
                nonlocal emit_buf, emit_last_time
                if not emit_buf:
                    return None
                payload = emit_buf
                emit_buf = ""
                emit_last_time = time.time()
                return payload

            for token in generator.stream(prompt['system'], prompt['user'], gen_params, tools=tool_schemas,
                                          conversation_turns=prompt.get('conversation_turns')):
                now = time.time()
                # ── Abort check: frontend requested stop ──────────────────
                if sid in _ABORT_STREAMS:
                    _ABORT_STREAMS.discard(sid)
                    # Flush remaining buffer
                    p = _flush_emit()
                    if p:
                        yield f'data: {json.dumps({"token": p})}\n\n'
                    yield f'data: {json.dumps({"aborted": True})}\n\n'
                    break
                # Heartbeat
                if now - last_emit >= HEARTBEAT_INTERVAL:
                    yield f'data: {json.dumps({"heartbeat": True, "t": now, "elapsed": round(now - last_emit,2)})}\n\n'
                    last_emit = now
                if not token:
                    # Check inactivity
                    if time.time() - last_emit > INACTIVITY_TIMEOUT:
                        # flush any buffered content before warning
                        p = _flush_emit()
                        if p:
                            yield f'data: {json.dumps({"token": p})}\n\n'
                        yield f'event: warn\ndata: {json.dumps({"warning": "inactivity-timeout"})}\n\n'
                        break
                    # also check emit buffer age
                    if emit_buf and (time.time() - emit_last_time) > 0.12:
                        p = _flush_emit()
                        if p:
                            yield f'data: {json.dumps({"token": p})}\n\n'
                    continue
                # Safety check: if a role/stop token leaked through, truncate and stop
                accumulated += token
                should_stop = False
                for st in _ROLE_STOP_TOKENS:
                    if st in accumulated:
                        # Truncate accumulated at the stop token
                        accumulated = accumulated[:accumulated.index(st)]
                        should_stop = True
                        break
                if should_stop:
                    # Re-derive full from accumulated
                    full = [accumulated] if accumulated else []
                    break
                full.append(token)

                # Aggregate into emit buffer instead of emitting each tiny token
                # Heuristics: flush when token ends with sentence punctuation or newline,
                # or when buffer length exceeds 40 chars, or when token includes a space/newline.
                emit_buf += token
                flush_now = False
                if '\n' in token:
                    flush_now = True
                if len(emit_buf) >= EMIT_BUF_CHARS:
                    flush_now = True
                if re.search(r'[\.!?\u2026]\s*$', emit_buf):
                    flush_now = True
                if '  ' in emit_buf:
                    flush_now = True
                if flush_now:
                    # sanitize and emit
                    safe_chunk = core.sanitize_reasoning(emit_buf)
                    emit_buf = ''
                    emit_last_time = time.time()
                    if safe_chunk:
                        yield f'data: {json.dumps({"token": safe_chunk})}\n\n'

                # If small buffer lingered too long, flush it (reduce mid-word fragmentation)
                if emit_buf and (time.time() - emit_last_time) > EMIT_IDLE_FLUSH:
                    safe_chunk = core.sanitize_reasoning(emit_buf)
                    emit_buf = ''
                    emit_last_time = time.time()
                    if safe_chunk:
                        yield f'data: {json.dumps({"token": safe_chunk})}\n\n'

                # ─── Tool Call Detection ─────────────────────────────────
                # Model emits tool calls in multiple formats:
                # [TOOL_CALLS]name[ARGS]{json}  — Mistral native
                # <tool_call>{json}</tool_call> — Qwen native
                # [tool_call: func(args)]       — Ailey trained format
                # <|tool_call>call:func{...}<tool_call|> — Gemma 4 native
                _has_tool_marker = ('[TOOL_CALLS]' in accumulated or '<tool_call>' in accumulated
                                    or '[tool_call:' in accumulated or '<|tool_call>' in accumulated)
                if _has_tool_marker:
                    # Get text before tool call (the AI's conversational response)
                    text_before = extract_text_before_tools(accumulated)
                    if text_before.strip():
                        safe = core.sanitize_reasoning(text_before)
                        if safe:
                            yield f'data: {json.dumps({"token": safe})}\n\n'
                    
                    # Parse and execute tool calls
                    tool_calls_parsed = parse_tool_calls(accumulated)

                    # ── Truncated tool-call recovery ─────────────────────
                    # If [TOOL_CALLS] is present but parser found nothing,
                    # the model hit max_tokens mid-call.  Do a continuation
                    # to get the rest of the tool call.
                    if not tool_calls_parsed:
                        tc_idx = min(
                            (accumulated.find(m) for m in ('[TOOL_CALLS]', '<tool_call>', '[tool_call:', '<|tool_call>')
                             if accumulated.find(m) != -1),
                            default=len(accumulated)
                        )
                        partial_tc = accumulated[tc_idx:]
                        _log_stream_event({"id": sid, "phase": "truncated_tool_call", "partial": partial_tc[:200]})
                        # Continue generation from where the model stopped
                        continuation_prompt = accumulated  # feed back what was generated
                        cont_params = gen_params.copy()
                        cont_params['max_tokens'] = 600  # enough to finish the tool call + detailed prompt
                        cont_buf = ""
                        try:
                            for cont_token in generator.stream(prompt['system'], prompt['user'] + "\n\n[assistant]\n" + accumulated, cont_params,
                                                               conversation_turns=prompt.get('conversation_turns')):
                                if cont_token:
                                    cont_buf += cont_token
                                    # Check if we now have a complete tool call
                                    combined = accumulated + cont_buf
                                    tool_calls_parsed = parse_tool_calls(combined)
                                    if tool_calls_parsed:
                                        accumulated = combined
                                        break
                        except Exception as cont_err:
                            _log_stream_event({"id": sid, "phase": "continuation_error", "error": str(cont_err)})

                    tool_results = []
                    for tc in tool_calls_parsed:
                        # ── Intercept generate_image: use synchronous generation instead of background thread ──
                        if tc["name"] == "generate_image":
                            yield f'event: tool_action\ndata: {json.dumps({"tool": "generate_image", "arguments": tc["arguments"], "status": "executing"})}\n\n'
                            yield f'data: {json.dumps({"token": "\\n🎨 Generiere Bild synchron…"})}\n\n'
                            try:
                                from ailey_system.image_generator import generate_image as _sync_gen, build_lora_args as _build_loras_tc
                                _tc_prompt = tc["arguments"].get("prompt", message)
                                _tc_title = tc["arguments"].get("title", _tc_prompt[:50])
                                _tc_ar = tc["arguments"].get("aspect_ratio", "1:1")
                                # Unload LLM — must sync Metal ops first!
                                _tc_idle = globals().get('idle_thinker')
                                _tc_unloaded = False
                                try:
                                    if _tc_idle:
                                        _tc_idle._generating_image = True
                                        _tc_idle._unload_llm_for_image_gen()
                                        _tc_unloaded = True
                                        print("[ToolCall] ✅ LLM unloaded via idle_thinker")
                                    else:
                                        import gc as _gc3
                                        import time as _t3
                                        try:
                                            from ailey_system import llm_mlx as _llm_m3
                                            from ailey_system.llm_mlx import _mlx_lock
                                            # Sync ALL pending Metal ops on ALL streams
                                            try:
                                                import mlx.core as mx
                                                mx.synchronize()
                                                mx.eval(mx.zeros(1))
                                            except Exception:
                                                pass
                                            with _mlx_lock:
                                                _llm_m3._model = None
                                                _llm_m3._tokenizer = None
                                                _llm_m3._cache = None
                                                _llm_m3._last_system_prompt = None
                                                MLXGenerator._instance = None
                                            _gc3.collect()
                                            try:
                                                import mlx.core as mx
                                                mx.metal.clear_cache()
                                                mx.metal.set_cache_limit(0)
                                                mx.metal.set_memory_limit(0)
                                            except Exception:
                                                pass
                                            _gc3.collect()
                                            try:
                                                import mlx.core as mx
                                                _act = mx.metal.get_active_memory() / 1024**2
                                                _cch = mx.metal.get_cache_memory() / 1024**2
                                                print(f"[ToolCall] 📊 After cleanup: active={_act:.0f}MB cache={_cch:.0f}MB")
                                            except Exception:
                                                pass
                                            _t3.sleep(2.0)
                                            _tc_unloaded = True
                                            print("[ToolCall] ✅ LLM unloaded via direct cleanup")
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                # Chat tool-call images: add Realism LoRA for better quality
                                _tc_lp, _tc_ls, _tc_trigger = _build_loras_tc(["realism"], include_ailey=False)
                                _tc_prompt_final = _tc_trigger + _tc_prompt if _tc_trigger else _tc_prompt
                                _tc_fp, _tc_fn = _sync_gen(
                                    prompt=_tc_prompt_final, title=_tc_title,
                                    aspect_ratio=_tc_ar, low_ram=not _tc_unloaded, private=True,
                                    lora_paths=_tc_lp or None, lora_scales=_tc_ls or None,
                                )
                                # Reload LLM
                                try:
                                    if _tc_unloaded and _tc_idle:
                                        _tc_idle._reload_llm_after_image_gen()
                                        _tc_idle._generating_image = False
                                except Exception:
                                    if _tc_idle: _tc_idle._generating_image = False
                                if _tc_fp and _tc_fn:
                                    _tc_url = f"/api/image/file/{_tc_fn}"
                                    result = {"success": True, "message": f"🎨 Bild generiert!", "image_url": _tc_url}
                                    _stream_generated_image = _tc_url
                                else:
                                    result = {"success": False, "error": "Bildgenerierung fehlgeschlagen"}
                            except Exception as _tce:
                                result = {"success": False, "error": str(_tce)}
                            tool_results.append({"name": "generate_image", "result": result})
                            stream_tool_actions.append({"tool": "generate_image", "arguments": tc["arguments"], "result": result})
                            yield f'event: tool_result\ndata: {json.dumps({"tool": "generate_image", "result": result})}\n\n'
                            if result.get("success"):
                                _tc_msg = result["message"]
                                yield f'data: {json.dumps({"token": "\\n\\n✅ " + _tc_msg})}\n\n'
                                full.append(f"\n\n✅ {_tc_msg}")
                            else:
                                _tc_err = result.get("error", "")
                                yield f'data: {json.dumps({"token": "\\n\\n⚠️ " + _tc_err})}\n\n'
                                full.append(f"\n\n⚠️ {_tc_err}")
                            continue

                        # Emit tool_action event to frontend (shows what's happening)
                        yield f'event: tool_action\ndata: {json.dumps({"tool": tc["name"], "arguments": tc["arguments"], "status": "executing"})}\n\n'
                        # Execute the tool
                        result = execute_tool(tc["name"], tc["arguments"])
                        tool_results.append({"name": tc["name"], "result": result})
                        stream_tool_actions.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
                        # Emit tool result to frontend
                        yield f'event: tool_result\ndata: {json.dumps({"tool": tc["name"], "result": result})}\n\n'
                        # Also emit as a visible token so the user sees the result
                        if result.get("success") and result.get("message"):
                            confirmation = f"\n\n✅ {result['message']}"
                            yield f'data: {json.dumps({"token": confirmation})}\n\n'
                            full.append(confirmation)
                            # If tool wants to embed content as code block (e.g. ER diagrams)
                            if result.get("embed_as_code_block") and result.get("svg"):
                                svg_block = f"\n\n```svg\n{result['svg']}\n```\n"
                                yield f'data: {json.dumps({"token": svg_block})}\n\n'
                                full.append(svg_block)
                        elif result.get("error"):
                            err_msg = f"\n\n⚠️ {result['error']}"
                            yield f'data: {json.dumps({"token": err_msg})}\n\n'
                            full.append(err_msg)
                    
                    # Replace accumulated with just the text before + tool results
                    _acc_parts = [text_before]
                    for r in tool_results:
                        res = r['result']
                        if res.get('success') and res.get('message'):
                            _acc_parts.append(f"\n\n✅ {res['message']}")
                            # Embed SVG code block for tools like generate_er_diagram
                            if res.get('embed_as_code_block') and res.get('svg'):
                                _acc_parts.append(f"\n\n```svg\n{res['svg']}\n```\n")
                        elif res.get('error'):
                            _acc_parts.append(f"\n\n⚠️ {res['error']}")
                    accumulated = ''.join(_acc_parts)
                    full = [accumulated]
                    break  # Stop streaming after tool execution

                # Detect [THINK] / [/THINK] or <think> / </think> blocks and route to thinking event
                _think_open = None
                _think_close = None
                if '[THINK]' in accumulated and not in_thinking:
                    _think_open = '[THINK]'
                    _think_close = '[/THINK]'
                elif '<think>' in accumulated.lower() and not in_thinking:
                    # Find the actual case-sensitive tag
                    _lower = accumulated.lower()
                    _idx = _lower.index('<think>')
                    _think_open = accumulated[_idx:_idx+7]  # preserve original case
                    _think_close = '</think>'

                if _think_open and not in_thinking:
                    # We just entered a thinking block
                    in_thinking = True
                    _open_idx = accumulated.lower().index(_think_open.lower())
                    # Everything before the opening tag is normal output
                    before_think = accumulated[:_open_idx]
                    # Reset accumulated to content after the opening tag
                    accumulated_after = accumulated[_open_idx + len(_think_open):]
                    # Emit any text before the think block
                    if before_think.strip():
                        yield f'data: {json.dumps({"token": before_think})}\n\n'
                    accumulated = _think_open + accumulated_after
                    thinking_buf = [accumulated_after]
                    _current_think_close = _think_close  # remember which close tag to look for
                    last_emit = now
                    continue
                
                if in_thinking:
                    _close_lower = _current_think_close.lower()
                    if _close_lower in accumulated.lower():
                        # End of thinking block
                        _lower_acc = accumulated.lower()
                        think_end_idx = _lower_acc.index(_close_lower)
                        # Find open tag length
                        _open_len = 7 if '<think>' in _lower_acc[:20] else len('[THINK]')
                        think_content = accumulated[_open_len:think_end_idx]
                        after_think = accumulated[think_end_idx + len(_current_think_close):]
                        # Emit the full thinking block as a thinking event
                        yield f'event: thinking\ndata: {json.dumps({"thinking": think_content.strip()})}\n\n'
                        in_thinking = False
                        thinking_buf = []
                        # Continue with content after the close tag
                        accumulated = after_think
                        if after_think.strip():
                            safe = core.sanitize_reasoning(after_think)
                            if safe:
                                yield f'data: {json.dumps({"token": safe})}\n\n'
                        last_emit = now
                    else:
                        # Still inside thinking, stream thinking tokens
                        thinking_buf.append(token)
                        yield f'event: thinking\ndata: {json.dumps({"thinking_token": token})}\n\n'
                        last_emit = now
                    continue

                # Token already emitted via buffer above — just update last_emit
                last_emit = now
        except GeneratorExit:
            _log_stream_event({"id": sid, "phase": "generator_exit", "tokens": len(full)})
            _release_slot()
            raise
        except Exception as e:
            _log_stream_event({"id": sid, "phase": "error", "error": str(e)})
            yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'
            _release_slot()
        # finalize (even if partial)
        # Extract thinking content from raw output before sanitization
        thinking_content = ''
        try:
            raw_full = ''.join(full)
            # ── Clean overfitted reasoning template from raw output ──
            try:
                for _tn in ("thinking", "thought"):
                    _tp = re.compile(rf"<{_tn}>([\s\S]*?)</{_tn}>", re.IGNORECASE)
                    def _cm(m, _tag=_tn):
                        body = m.group(1).strip()
                        cleaned = core._clean_overfitted_reasoning(body)
                        if not cleaned:
                            return ""
                        return f"<{_tag}>\n{cleaned}\n</{_tag}>"
                    raw_full = _tp.sub(_cm, raw_full)
            except Exception:
                pass
            # Extract [THINK]...[/THINK] or <think>...</think> or <thinking>...</thinking> content
            think_match = re.search(r'\[THINK\]([\s\S]*?)\[/THINK\]', raw_full)
            if not think_match:
                think_match = re.search(r'<think(?:ing)?>([\s\S]*?)</think(?:ing)?>', raw_full, re.IGNORECASE)
            if think_match:
                thinking_content = think_match.group(1).strip()
            if not raw_full.strip():
                # Secondary non-stream generation fallback
                try:
                    alt = generator.generate(prompt['system'], prompt['user'], gen_params,
                                             conversation_turns=prompt.get('conversation_turns'))
                except Exception:
                    alt = ''
                raw_full = alt or raw_full
            final_text = core.finalize_reply(raw_full, mood)
            # ── Post-generation repetition stripping ────────────
            final_text = _strip_repetition(final_text)
            # Extract mood tag for frontend (hidden)
            try:
                visible, mood_extracted, mood_tag = core.extract_mood_tag(final_text)
                if not mood_extracted:
                    mood_extracted = mood
                    mood_tag = f"<mood:{mood}>"
            except Exception:
                visible = final_text
                mood_extracted = mood
                mood_tag = f"<mood:{mood}>"
        except Exception:
            final_text = core.sanitize_reasoning(''.join(full))
        # Update mood from AI output (actor ai)
        try:
            core.update_mood_from_text(user, final_text, actor='ai')
            mood_update, _mv = core.current_mood(user)
        except Exception:
            mood_update = mood
        # ─────────────────────────────────────────────────────────────────
        # FAST PATH: build minimal end_payload and emit `event: end` ASAP so
        # the client unlocks the input box the moment tokens are done.
        # Heavy post-processing (auto_research, RAG write, diary, training
        # collection, people-glossary scan, conversation-log walk, live-chat
        # bus push) runs in a background daemon thread *after* the yield.
        # ─────────────────────────────────────────────────────────────────
        try:
            # Mood-tag parse on visible (cheap)
            try:
                if visible:
                    visible = parse_and_apply_mood_tags(visible)
            except Exception:
                pass

            # Agent-auto (only runs if explicitly requested → normally None)
            _agent_auto_result = None
            if agent_auto:
                try:
                    a = agent_auto.get('action')
                    if a == 'extract_phone':
                        pattern = re.compile(r"(?:\+\d{2,3}[\s-]?)?(?:\(?0\)?[\s-]?)?[1-9][0-9]{1,3}[\s-]?[0-9]{2,4}[\s-]?[0-9]{2,4}(?:[\s-]?[0-9]{2,4})?")
                        phones = []
                        scanned = 0
                        for root in ALLOWED_AGENT_ROOTS:
                            for r2, dnames, fnames in os.walk(root):
                                for fname in fnames:
                                    if scanned > 120:
                                        break
                                    fp = Path(r2)/fname
                                    if fp.suffix.lower() not in ('.txt', '.md', '.json', '.py'):
                                        continue
                                    try:
                                        with open(fp,'r',encoding='utf-8',errors='ignore') as fh:
                                            chunk = fh.read(20000)
                                        for m2 in pattern.findall(chunk):
                                            clean2 = re.sub(r"\s+"," ", m2.strip())
                                            if clean2 not in phones:
                                                phones.append(clean2)
                                    except Exception:
                                        pass
                                    scanned += 1
                        _agent_auto_result = {"action": a, "found": phones[:10], "count": len(phones)}
                    elif a == 'read_docx':
                        p2 = agent_auto.get('path')
                        if p2:
                            docp = Path(p2)
                            if docp.exists() and _is_safe_path(docp) and docp.suffix.lower()=='.docx':
                                try:
                                    from docx import Document
                                    doc = Document(str(docp))
                                    text2 = '\n'.join(par.text for par in doc.paragraphs)[:4000]
                                    _agent_auto_result = {"action": a, "file": p2, "excerpt": text2[:800]}
                                except Exception as e2:
                                    _agent_auto_result = {"action": a, "file": p2, "error": str(e2)}
                            else:
                                _agent_auto_result = {"action": a, "file": p2, "error": "not found or not allowed"}
                except Exception:
                    _agent_auto_result = {"error": True}

            follow_up_used = bool(visible and (visible.strip().endswith('?') or ('?' in visible[-140:])))
            end_payload = {
                "final": visible,
                "final_with_tag": final_text,
                "mood": mood_extracted,
                "mood_tag": mood_tag,
                "thinking": thinking_content,
                "tool_actions": stream_tool_actions if stream_tool_actions else None,
                "recent_context": [],        # filled async after yield (not consumed by frontend)
                "auto_research": None,        # filled async (background thread)
                "agent_auto": _agent_auto_result,
                "partial": bool(full and not final_text),
                "chars": len(final_text or ''),
                "tokens_streamed": len(full),
                "follow_up_used": follow_up_used,
                "session_focus": '',
                "generated_image": _stream_generated_image,
            }
        except Exception:
            end_payload = {"final": final_text, "recent_context": [], "auto_research": None, "partial": False, "chars": len(final_text or ''), "tokens_streamed": 0}

        # Truncation detection (cheap)
        _was_truncated = False
        try:
            _tok_count = len(full)
            _ends_clean = bool(re.search(r'[.!?…"»)\]]\s*$', (visible or '').strip()))
            if _tok_count >= max_tokens * 0.9 and not _ends_clean:
                _was_truncated = True
            if sid in _ABORT_STREAMS or end_payload.get("aborted"):
                _was_truncated = True
            if _was_truncated:
                _TRUNCATED_OUTPUT[user] = {
                    "text": visible or final_text or ''.join(full),
                    "system": prompt['system'],
                    "user_prompt": prompt['user'],
                    "gen_params": gen_params,
                    "mood": mood,
                    "ts": time.time(),
                    "original_message": message,
                }
                end_payload["truncated"] = True
            else:
                _TRUNCATED_OUTPUT.pop(user, None)
        except Exception:
            pass

        _log_stream_event({"id": sid, "phase": "end", "tokens": len(full), "chars": len(final_text or '')})

        # 🚀 EMIT event:end NOW — client unlocks input box immediately.
        yield f'event: end\ndata: {json.dumps(end_payload)}\n\n'

        # Release LLM slot right after yield so the next request can proceed.
        _release_slot()

        # ─────────────────────────────────────────────────────────────────
        # DEFERRED HEAVY POST-PROCESSING (background daemon thread)
        # auto_research (web!), conversation log, training collection,
        # diary, people-glossary extraction, RAG storage, live-chat bus push
        # ─────────────────────────────────────────────────────────────────
        def _post_stream_heavy(_user=user, _message=message, _visible=visible, _final_text=final_text,
                                _mood_extracted=mood_extracted, _mood_tag=mood_tag, _mood=mood,
                                _thinking_content=thinking_content,
                                _stream_tool_actions=stream_tool_actions):
            try:
                research_meta = None
                try:
                    research_meta = core.auto_research_cycle(user=_user, user_msg=_message, ai_reply=_final_text)
                except Exception:
                    research_meta = {"triggered": False, "error": True}
                log_item = {
                    'timestamp': time.time(),
                    'user': _user,
                    'message': _message,
                    'ailey_reply': _final_text,
                    'ailey_reply_visible': _visible,
                    'mood_tag': _mood_tag,
                    'engine': 'mlx',
                    'streamed': True,
                    'auto_research': research_meta,
                }
                try:
                    core.memory.add_conversation_log(_user, log_item)
                except Exception:
                    pass
                try:
                    _user_type = "simon" if _user.lower() in ("simon",) else "portal_mid"
                    _collect_training_pair(
                        user_prompt=_message,
                        assistant_response=_visible,
                        reasoning=_thinking_content,
                        tool_actions=_stream_tool_actions if _stream_tool_actions else None,
                        source="live_chat_stream",
                        user_type=_user_type,
                        mood=_mood_extracted or _mood,
                        engine='mlx',
                    )
                except Exception:
                    pass
                try:
                    core._maybe_create_diary(_user)
                except Exception:
                    pass
                try:
                    from ailey_system import people_glossary as _pg
                    combined_text = _message + " " + _visible
                    _new_names = _pg.extract_people_from_text(combined_text, source="chat")
                    for _nn in _new_names:
                        if not _pg.get_person(_nn):
                            _pg.upsert_person(_nn, source="chat")
                    _msg_strip = _message.strip()
                    _is_informational = (
                        len(_msg_strip) > 30
                        and not re.match(r'^(hey|hi|hallo|danke|ok|ja|nein|gut|alles klar|tschüss|ciao)', _msg_strip.lower())
                        and not _msg_strip.endswith('?')
                    )
                    if _is_informational:
                        _mentioned = _pg.find_mentioned_people(_message)
                        for _mp in _mentioned:
                            _pg.add_fact(_mp['name'], _msg_strip[:250], source="chat")
                    _is_substantial = (
                        len(_msg_strip) > 40
                        and len(_visible.strip()) > 40
                        and not re.match(r'^(hey|hi|hallo|danke|ok|ja|nein|guten morgen|gute nacht)', _msg_strip.lower())
                    )
                    if _is_substantial:
                        _rag_title = f"Chat: {_message[:80]}"
                        _rag_text = f"Simon (User): {_message[:400]}\nAiley (Du): {_visible[:600]}"
                        core.rag_add(_rag_title, _rag_text, doc_type="chat_memory", user=_user)
                except Exception:
                    pass
                # Live-chat bus push (cross-device sync)
                try:
                    _live_chat_push("user", _message, mood="neutral")
                    _live_chat_push("ai", _visible or _final_text or '', mood=_mood_extracted or _mood,
                                    thinking=_thinking_content or None,
                                    auto_research=research_meta)
                except Exception:
                    pass
            except Exception as _be:
                try:
                    _log_stream_event({"id": sid, "phase": "post_stream_heavy_error", "error": str(_be)[:300]})
                except Exception:
                    pass

        try:
            threading.Thread(target=_post_stream_heavy, daemon=True).start()
        except Exception:
            # Fallback: run inline if thread creation fails (unlikely)
            try:
                _post_stream_heavy()
            except Exception:
                pass

    return Response(stream_reply(), mimetype='text/event-stream')


# ─── Stream Abort & Continue ─────────────────────────────────────────────────

@app.get('/api/queue/status')
def api_queue_status():
    """Return current LLM request queue status."""
    return jsonify({
        "success": True,
        "queue": {
            "chat_waiting": _chat_waiting.is_set(),
            "stats": dict(_queue_stats),
            "semaphore_available": _llm_semaphore._value if hasattr(_llm_semaphore, '_value') else None,
        }
    })

@app.post('/api/chat/abort')
def api_chat_abort():
    """Abort the currently running stream. Frontend sends this when user clicks Stop."""
    sid = getattr(app, '_current_stream_id', None)
    if sid:
        _ABORT_STREAMS.add(sid)
        return jsonify({"success": True, "aborted_stream": sid})
    return jsonify({"success": True, "message": "No active stream"})


@app.post('/api/chat/continue')
def api_chat_continue():
    """Continue writing where the last truncated output left off.

    The LLM receives the previous output as context and a "bitte fahre fort"
    instruction so it picks up mid-sentence.
    """
    data = request.get_json(silent=True) or {}
    user = data.get('user') or 'Simon'

    trunc = _TRUNCATED_OUTPUT.get(user)
    if not trunc:
        return jsonify({"success": False, "message": "Kein abgeschnittener Text zum Fortsetzen."}), 404

    # Build a continuation prompt: inject the partial output and ask to continue
    prev_text = trunc["text"]
    original_msg = trunc.get("original_message", "")
    system_prompt = trunc["system"]
    gen_params = trunc["gen_params"].copy()
    mood = trunc["mood"]

    # User prompt = original question + partial answer + "fahre fort"
    continuation_user = (
        f"{original_msg}\n\n"
        f"[Deine bisherige Antwort (wurde abgeschnitten):]\n"
        f"{prev_text}\n\n"
        f"Bitte fahre genau dort fort, wo du aufgehört hast. "
        f"Wiederhole NICHT was du schon geschrieben hast — schreibe nur den fehlenden Rest."
    )

    generator = MLXGenerator.get()
    if generator is None:
        return jsonify({"success": False, "error": "Model not loaded"}), 503

    # Clear truncated state
    _TRUNCATED_OUTPUT.pop(user, None)

    sid = f"s_{int(time.time()*1000)}_{os.getpid()}_cont"
    app._current_stream_id = sid

    def continue_stream():
        full = []
        last_emit = time.time()
        _ROLE_STOP_TOKENS = ("[INST]", "[/INST]", "[SYSTEM_PROMPT]", "[/SYSTEM_PROMPT]",
                             "<|im_start|>", "<|im_end|>", "<|eot_id|>", "</s>")
        yield f'data: {json.dumps({"stream_id": sid, "continuation": True, "heartbeat": True})}\n\n'
        accumulated = ""
        emit_buf = ""
        emit_last_time = time.time()
        try:
            for token in generator.stream(system_prompt, continuation_user, gen_params):
                now = time.time()
                if sid in _ABORT_STREAMS:
                    _ABORT_STREAMS.discard(sid)
                    if emit_buf:
                        yield f'data: {json.dumps({"token": emit_buf})}\n\n'
                    yield f'data: {json.dumps({"aborted": True})}\n\n'
                    break
                if now - last_emit >= 5.0:
                    yield f'data: {json.dumps({"heartbeat": True})}\n\n'
                    last_emit = now
                if not token:
                    if emit_buf and (now - emit_last_time) > 0.12:
                        yield f'data: {json.dumps({"token": emit_buf})}\n\n'
                        emit_buf = ""
                        emit_last_time = now
                    continue
                accumulated += token
                should_stop = False
                for st in _ROLE_STOP_TOKENS:
                    if st in accumulated:
                        accumulated = accumulated[:accumulated.index(st)]
                        should_stop = True
                        break
                if should_stop:
                    full = [accumulated] if accumulated else []
                    break
                full.append(token)
                emit_buf += token
                if '\n' in token or len(emit_buf) >= 80 or re.search(r'[.!?]\s*$', emit_buf):
                    safe = core.sanitize_reasoning(emit_buf)
                    emit_buf = ""
                    emit_last_time = now
                    if safe:
                        yield f'data: {json.dumps({"token": safe})}\n\n'
                last_emit = now
        except Exception as e:
            yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'

        raw = ''.join(full)
        # ── Clean overfitted reasoning template ──
        try:
            for _tn in ("thinking", "thought"):
                _tp = re.compile(rf"<{_tn}>([\s\S]*?)</{_tn}>", re.IGNORECASE)
                def _cm(m, _tag=_tn):
                    body = m.group(1).strip()
                    cleaned = core._clean_overfitted_reasoning(body)
                    if not cleaned:
                        return ""
                    return f"<{_tag}>\n{cleaned}\n</{_tag}>"
                raw = _tp.sub(_cm, raw)
        except Exception:
            pass
        final_text = core.finalize_reply(raw, mood)
        try:
            visible, mood_extracted, mood_tag = core.extract_mood_tag(final_text)
        except Exception:
            visible = final_text
            mood_extracted = mood
        # Check if this continuation was also truncated
        _tok_count = len(full)
        _ends_clean = bool(re.search(r'[.!?…"»)\]]\s*$', (visible or '').strip()))
        _still_truncated = _tok_count >= gen_params.get("max_tokens", 500) * 0.9 and not _ends_clean
        if _still_truncated:
            _TRUNCATED_OUTPUT[user] = {
                "text": prev_text + (visible or raw),
                "system": system_prompt,
                "user_prompt": continuation_user,
                "gen_params": gen_params,
                "mood": mood,
                "ts": time.time(),
                "original_message": original_msg,
            }
        yield f'data: {json.dumps({"final": visible, "mood": mood_extracted, "continuation": True, "truncated": _still_truncated})}\n\n'

    from flask import Response
    return Response(continue_stream(), mimetype='text/event-stream')


# ─── Tools API ───────────────────────────────────────────────────────────────

@app.get('/api/tools')
def api_tools():
    """List all available tools."""
    schemas = get_tool_schemas()
    return jsonify({"success": True, "tools": schemas, "count": len(schemas)})


@app.post('/api/tools/execute')
def api_tools_execute():
    """Manually execute a tool (for testing)."""
    data = request.get_json(silent=True) or {}
    name = data.get('tool') or data.get('name')
    arguments = data.get('arguments') or data.get('args') or {}
    if not name:
        return jsonify({"success": False, "error": "Missing 'tool' name"}), 400
    result = execute_tool(name, arguments)
    return jsonify(result)


@app.get('/api/mood')
def api_mood():
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    try:
        mood, val = core.current_mood(user)
        # Map mood to emote image path for frontend (all available emotes)
        emote_map = {
            # Primary emotional states
            'neutral': '/images/emotes/ailey-default.jpg',
            'default': '/images/emotes/ailey-default.jpg',
            'happy': '/images/emotes/ailey-grins.jpg',
            'grins': '/images/emotes/ailey-grins.jpg',
            'excited': '/images/emotes/ailey-playful.jpg',
            'playful': '/images/emotes/ailey-playful.jpg',
            'flirty': '/images/emotes/ailey-flirty.jpg',
            'kissing': '/images/emotes/ailey-kissing.jpg',
            'loving': '/images/emotes/ailey-kissing.jpg',
            'funny': '/images/emotes/ailey-funny.jpg',
            'amused': '/images/emotes/ailey-funny.jpg',
            # Thinking & Processing
            'thinking': '/images/emotes/ailey-thinking.jpg',
            'curious': '/images/emotes/ailey-thinking.jpg',
            'processing': '/images/emotes/ailey-thinking.jpg',
            'confused': '/images/emotes/ailey-confused.jpg',
            'puzzled': '/images/emotes/ailey-confused.jpg',
            # Sad states
            'sad': '/images/emotes/ailey-sad.jpg',
            'melancholic': '/images/emotes/ailey-sad.jpg',
            'crying': '/images/emotes/ailey-crying.jpg',
            'upset': '/images/emotes/ailey-crying.jpg',
            'slightly_crying': '/images/emotes/ailey-slightly-crying.jpg',
            'touched': '/images/emotes/ailey-slightly-crying.jpg',
            'emotional': '/images/emotes/ailey-slightly-crying.jpg',
            # Angry
            'angry': '/images/emotes/ailey-angry.jpg',
            'frustrated': '/images/emotes/ailey-angry.jpg',
            'annoyed': '/images/emotes/ailey-angry.jpg',
            # Tired states
            'sleepy': '/images/emotes/ailey-sleeping.jpg',
            'sleeping': '/images/emotes/ailey-sleeping.jpg',
            'tired': '/images/emotes/ailey-slightly-tired.jpg',
            'slightly_tired': '/images/emotes/ailey-slightly-tired.jpg',
            'exhausted': '/images/emotes/ailey-very-tired.jpg',
            'very_tired': '/images/emotes/ailey-very-tired.jpg',
            # Creative activities
            'coding': '/images/emotes/ailey-coding.jpg',
            'programming': '/images/emotes/ailey-coding.jpg',
            'hacking': '/images/emotes/ailey-coding.jpg',
            'developing': '/images/emotes/ailey-coding.jpg',
            'writing': '/images/emotes/ailey-writing-diary.jpg',
            'creative': '/images/emotes/ailey-writing-diary.jpg',
            'diary': '/images/emotes/ailey-writing-diary.jpg',
            'journaling': '/images/emotes/ailey-writing-diary.jpg',
            'composing': '/images/emotes/ailey-writing-diary.jpg',
            # Music activities
            'singing': '/images/emotes/ailey-playing-guitar-singing.jpg',
            'guitar': '/images/emotes/ailey-playing-guitar-singing.jpg',
            'music': '/images/emotes/ailey-playing-guitar-singing.jpg',
            'performing': '/images/emotes/ailey-playing-guitar-singing.jpg',
            'rocking': '/images/emotes/ailey-playing-guitar-singing.jpg',
            'singing_soft': '/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
            'soft_music': '/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
            'acoustic': '/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
            'ballad': '/images/emotes/ailey-playing-guitar-singing-soft-music.jpg',
        }
        emote = emote_map.get(mood, '/images/emotes/ailey-default.jpg')
        model_ready = _llm_module._model is not None
        return jsonify({"success": True, "mood": mood, "value": val, "emote": emote, "model_loaded": model_ready})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Warmup Greeting ──────────────────────────────────────────────────────────

def _get_upcoming_calendar_summary() -> str:
    """Check internal calendar for today's and tomorrow's events + birthdays.
    Returns a short German summary string for the greeting prompt, or "" if nothing upcoming.
    Events whose time has already passed today are shown as 'Wie war …?' suggestions."""
    try:
        cal = _load_calendar()
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        tomorrow = now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        today_mm_dd = now.strftime("%m-%d")
        tomorrow_mm_dd = tomorrow.strftime("%m-%d")
        current_hhmm = now.strftime("%H:%M")

        events = cal.get("events", [])
        birthdays = cal.get("birthdays", [])

        today_events = [e for e in events if e.get("date") == today_str]
        tomorrow_events = [e for e in events if e.get("date") == tomorrow_str]
        today_bdays = [b for b in birthdays if b.get("date") == today_mm_dd]
        tomorrow_bdays = [b for b in birthdays if b.get("date") == tomorrow_mm_dd]

        parts = []
        if today_events or today_bdays:
            upcoming_items = []
            past_items = []
            for e in sorted(today_events, key=lambda x: x.get("time", "")):
                t = e.get("time", "")
                loc = f" ({e.get('location')})" if e.get("location") else ""
                title = e.get("title", "?")
                if not t:
                    # All-day event — always show as upcoming
                    upcoming_items.append(f"  - (ganztägig) {title}{loc}")
                elif t <= current_hhmm:
                    # Past event — suggest follow-up
                    past_items.append(f"  - {t} {title}{loc} (bereits vorbei — ggf. fragen: 'Wie war {title}?')")
                else:
                    upcoming_items.append(f"  - {t} {title}{loc}")
            for b in today_bdays:
                upcoming_items.append(f"  - 🎂 {b.get('name', '?')} hat Geburtstag!")

            if upcoming_items:
                parts.append("HEUTE anstehende Termine:\n" + "\n".join(upcoming_items))
            if past_items:
                parts.append("HEUTE bereits vergangene Termine (optional nachfragen):\n" + "\n".join(past_items))

        if tomorrow_events or tomorrow_bdays:
            items = []
            for e in sorted(tomorrow_events, key=lambda x: x.get("time", "")):
                t = e.get("time", "") or "(ganztägig)"
                items.append(f"  - {t} {e.get('title', '?')}")
            for b in tomorrow_bdays:
                items.append(f"  - 🎂 {b.get('name', '?')} hat morgen Geburtstag!")
            parts.append("MORGEN anstehende Termine:\n" + "\n".join(items))

        return "\n".join(parts)
    except Exception:
        return ""


@app.post('/api/warmup-greeting')
def api_warmup_greeting():
    """Generate a personalised greeting on app startup.

    This doubles as the MLX warmup (first inference warms the GPU) so the user
    doesn't stare at a blank screen.  The frontend shows a loading bar while
    this runs, then reveals the chat with the greeting already displayed.
    """
    user = (request.get_json(silent=True) or {}).get('user', 'Simon')
    gen = MLXGenerator.get()
    if gen is None:
        return jsonify({"success": False, "error": "MLX model not loaded"}), 503

    from ailey_system.user_profile import get_profile_for_prompt
    from datetime import datetime
    _now = datetime.now()
    _weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    _months = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    _hour = _now.hour
    if _hour < 6:
        tageszeit = "Mitten in der Nacht"
    elif _hour < 10:
        tageszeit = "Am Morgen"
    elif _hour < 12:
        tageszeit = "Am Vormittag"
    elif _hour < 14:
        tageszeit = "Mittags"
    elif _hour < 17:
        tageszeit = "Am Nachmittag"
    elif _hour < 21:
        tageszeit = "Am Abend"
    else:
        tageszeit = "Spätabends"

    # Check internal calendar for upcoming events
    calendar_hint = _get_upcoming_calendar_summary()
    calendar_instruction = ""
    if calendar_hint:
        calendar_instruction = (
            f"\n\n📅 KALENDER-INFO:\n{calendar_hint}\n"
            "Erwähne die anstehenden Termine sanft und natürlich in deiner Begrüßung "
            "(z.B. 'Übrigens, du hast heute um 14 Uhr...'), aber halte es kurz. "
            "Keine komplette Liste runterbeten — nur die wichtigsten 1-2 Sachen erwähnen."
        )

    profile_block = get_profile_for_prompt(user=user) or ""
    system = core.personality.get_system_prompt(mode="full")

    # Fetch real weather for greeting context
    _weather_greeting = ""
    try:
        _wd = _fetch_real_weather()
        _weather_greeting = (
            f"\n🌤️ Aktuelles Wetter: {_wd.get('label', '')}, "
            f"{_wd.get('temperature', '?')}°C, Wind {_wd.get('windspeed', '?')} km/h.\n"
        )
    except Exception:
        pass

    greeting_user_prompt = (
        f"KONTEXT: Es ist {_weekdays[_now.weekday()]}, {_now.day}. {_months[_now.month-1]} {_now.year}, "
        f"{_now.strftime('%H:%M')} Uhr. {tageszeit}.\n"
        f"{_weather_greeting}"
        f"{profile_block}"
        f"{calendar_instruction}\n\n"
        "AUFGABE: Begrüße den User kurz und natürlich (2-4 Sätze). "
        "Beziehe die Tageszeit und ggf. den Wochentag mit ein. Sei locker und authentisch. "
        "Du darfst das aktuelle Wetter kurz erwähnen wenn es sich natürlich anfühlt. "
        "Keine Wiederholung deines Namens ('Ich bin Ailey'). Kein Roleplay-Emote am Anfang. "
        "Nutze max. 1 Emoji. Sei warm aber nicht übertrieben."
    )
    gen_params = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 180, "repetition_penalty": 1.05, "stop": []}
    try:
        # ── Try Nitro first (AileyNitro-2B) — instant greeting, no Ministral warmup wait ──
        from ailey_system.llm_mlx import fast_generate, is_fast_available
        if is_fast_available():
            from ailey_system.ailey_personality import AileyPersonality
            _pers = AileyPersonality()
            _flash_sys = _pers.get_nitro_system(portal=False, user_name=user)
            _flash_priming = _pers.get_nitro_priming_turns(portal=False)
            # Append greeting-specific instruction to system prompt
            _flash_sys += (
                "\n\nAKTUELLE AUFGABE: Begrüße den User kurz und natürlich (2-4 Sätze). "
                "Beziehe die Tageszeit mit ein. Sei locker und authentisch. "
                "Keine Wiederholung deines Namens. Kein Roleplay-Emote am Anfang. "
                "Nutze max. 1 Emoji. Sei warm aber nicht übertrieben."
            )
            _flash_raw = fast_generate(
                system=_flash_sys,
                user=f"{user}: {greeting_user_prompt}",
                max_tokens=180,
                temperature=0.7,
                priming_turns=_flash_priming,
            )
            if _flash_raw and len(_flash_raw.strip()) > 10:
                import re as _re
                _cleaned = _flash_raw.strip()
                _mood_match = _re.search(r'<mood:(\w+)>', _cleaned)
                _mood = _mood_match.group(1) if _mood_match else 'happy'
                _cleaned = _re.sub(r'<mood:\w+>', '', _cleaned).strip()
                if _cleaned and len(_cleaned) >= 5:
                    print(f"[Greeting] ⚡ Flash greeting: {_cleaned[:60]}…")
                    return jsonify({"success": True, "greeting": _cleaned, "mood": _mood, "engine": "flash"})

        # ── Fallback: Ministral (slower but richer) ──
        raw = gen.generate(system, greeting_user_prompt, gen_params)
        cleaned = core.sanitize_reasoning(raw or "").strip()
        # Strip mood tag
        import re as _re
        mood_match = _re.search(r'<mood:(\w+)>', cleaned)
        mood = mood_match.group(1) if mood_match else 'neutral'
        cleaned = _re.sub(r'<mood:\w+>', '', cleaned).strip()
        if not cleaned or len(cleaned) < 5:
            cleaned = "Hey! Schön, dass du da bist 💜"
            mood = "happy"
        return jsonify({"success": True, "greeting": cleaned, "mood": mood})
    except Exception as e:
        return jsonify({"success": True, "greeting": "Hey! Schön, dass du da bist 💜", "mood": "happy", "warmup_error": str(e)})


@app.post('/api/admin/rag/wipe')
def api_admin_rag_wipe():
    if not _admin_required():
        return jsonify({"success": False, "error": "admin token required"}), 403
    # Iterate over user profile directories and wipe each collection
    base = 'ailey_users'
    wiped = []
    errors = []
    try:
        for name in os.listdir(base):
            if not name.endswith('_profile'): continue
            user = name.replace('_profile','')
            try:
                rag = core._get_rag(user)
                res = rag.wipe()
                if res.get('wiped'): wiped.append(user)
                else: errors.append({user: res})
            except Exception as e:
                errors.append({user: str(e)})
    except FileNotFoundError:
        pass
    return jsonify({"success": True, "wiped_users": wiped, "errors": errors})


@app.get('/api/rag/stats')
def api_rag_stats():
    """Return RAG collection stats for all user profiles.
    Open in dev (no admin token set). In prod requires admin.
    """
    if not _admin_required():  # in prod would enforce
        return jsonify({"success": False, "error": "admin token required"}), 403
    base = 'ailey_users'
    users = []
    agg_total = 0
    agg_docs = 0
    try:
        for name in os.listdir(base):
            if not name.endswith('_profile'): continue
            user = name.replace('_profile','')
            try:
                rag = core._get_rag(user)
                st = rag.stats()
                if 'total_chunks' in st:
                    agg_total += st.get('total_chunks', 0)
                    agg_docs += st.get('unique_documents', 0)
                users.append({"user": user, **st})
            except Exception as e:
                users.append({"user": user, "error": str(e)})
    except FileNotFoundError:
        pass
    return jsonify({"success": True, "aggregate": {"total_chunks": agg_total, "unique_documents": agg_docs}, "users": users})

@app.post('/api/admin/rag/deep-wipe')
def api_admin_rag_deep_wipe():
    # Dev open if no token; otherwise require matching token
    if not _admin_required():
        return jsonify({"success": False, "error": "admin token required"}), 403
    try:
        res = core.rag_deep_wipe_all()
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.post('/api/admin/rag/wipe-all')
def api_admin_rag_wipe_all():
    if not _admin_required():
        return jsonify({"success": False, "error": "admin token required"}), 403
    try:
        res = core.rag_wipe_all_collections()
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/debug/last-self-prompts')
def last_self_prompts():
    # helper to verify background task wrote files
    base = os.path.join('ailey_users', 'simon_profile', 'relationship_history')
    items = []
    try:
        for name in sorted(os.listdir(base))[-5:]:
            p = os.path.join(base, name)
            try:
                import json as _json
                with open(p, 'r', encoding='utf-8') as f:
                    items.append(_json.load(f))
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({"count": len(items), "items": items})


@app.get('/api/chat/recent')
def api_chat_recent():
    """Return the last N conversation exchanges for session carry-over.

    Query params:
        user:  username (default: Simon)
        count: number of exchanges to return (default: 10)

    Returns a list of {message, reply, mood, timestamp} objects, newest last.
    Each new user message in the current session removes the oldest carried-over
    exchange from the frontend display.
    """
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    count = min(int(request.args.get('count', 10)), 30)
    base = os.path.join('ailey_users', f'{user}_profile', 'conversation_logs')
    items = []
    try:
        files = sorted([f for f in os.listdir(base) if f.endswith('.json')])
        for name in files[-count:]:
            p = os.path.join(base, name)
            try:
                import json as _json
                with open(p, 'r', encoding='utf-8') as f:
                    j = _json.load(f)
                items.append({
                    "message": j.get("message", ""),
                    "reply": j.get("ailey_reply_visible") or j.get("ailey_reply", ""),
                    "mood": j.get("mood_tag", "").replace("<mood:", "").replace(">", "") or "neutral",
                    "timestamp": j.get("timestamp", 0),
                    "carried_over": True,
                })
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({"success": True, "messages": items, "count": len(items)})


@app.get('/api/history/list')
def history_list():
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    base = os.path.join('ailey_users', f'{user}_profile', 'conversation_logs')
    out = []
    try:
        for name in sorted(os.listdir(base))[-50:]:
            if not name.endswith('.json'):
                continue
            p = os.path.join(base, name)
            try:
                import json as _json
                with open(p, 'r', encoding='utf-8') as f:
                    j = _json.load(f)
                out.append({
                    "id": name,
                    "timestamp": j.get('timestamp'),
                    "user": j.get('user'),
                    "message": j.get('message'),
                    "mood": j.get('mood'),
                })
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({"success": True, "items": out})


@app.get('/api/history/get')
def history_get():
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    hid = (request.args.get('id') or '').strip()
    if not hid:
        return jsonify({"success": False, "message": "id required"}), 400
    p = os.path.join('ailey_users', f'{user}_profile', 'conversation_logs', hid)
    try:
        import json as _json
        with open(p, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        return jsonify({"success": True, "item": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 404


@app.get('/api/settings')
def api_settings():
    cfg_path = 'ailey_config.json'
    try:
        import json as _json
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return jsonify({"success": True, "config": _json.load(f)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Minimal Admin Endpoints ---
_START_TS = time.time()


@app.get('/api/admin/users')
def admin_users():
    base = 'ailey_users'
    users = []
    try:
        if os.path.exists(base):
            for name in os.listdir(base):
                if name.endswith('_profile'):
                    users.append(name[:-9])
    except Exception:
        pass
    if 'Simon' not in users:
        users.append('Simon')
    return jsonify({"success": True, "users": sorted(set(users))})

@app.get('/api/debug/streams')
def debug_streams():
    try:
        return jsonify({"success": True, "count": len(_STREAM_HISTORY), "items": list(_STREAM_HISTORY)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.post('/api/debug/generate_raw')
def debug_generate_raw():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    if not message:
        return jsonify({"success": False, "message": "message required"}), 400
    rag_threshold = None
    if 'rag_threshold' in data:
        try:
            rag_threshold = float(data.get('rag_threshold'))
        except Exception:
            rag_threshold = None
    system_persona, mood, prompt, gen_params = core.build_prompt_for_message(message, user=user, rag_threshold=rag_threshold, thought_password=_thought_session_password)
    gen = MLXGenerator.get()
    if gen is None:
        return jsonify({"success": False, "error": "MLX backend not available"}), 500
    raw = ''
    try:
        raw = gen.generate(prompt['system'], prompt['user'], gen_params,
                           conversation_turns=prompt.get('conversation_turns'))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": True, "raw": raw, "system_head": prompt['system'][:160], "user_head": prompt['user'][:160], "params": gen_params})


@app.post('/api/admin/shutdown')
def admin_shutdown():
    """Terminate backend process and attempt to stop local frontend dev server (port 5175).

    This is a local-only convenience endpoint. No auth for now because desktop context.
    Returns immediately; actual exit happens after short delay to flush response.
    """
    try:
        # Try to kill node/frontend dev server on known ports (3000 standalone, 5175 Tauri dev)
        try:
            import subprocess, json as _json
            pids = set()
            for port in (3000, 5175):
                try:
                    out = subprocess.check_output(['lsof', '-nP', '-i', f':{port}', '-sTCP:LISTEN'], stderr=subprocess.STDOUT).decode('utf-8', 'ignore')
                    for line in out.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) > 1:
                            cmd = parts[0].lower()
                            pid = parts[1]
                            if cmd in ('node', 'npm', 'bun', 'pnpm', 'next'):
                                pids.add(int(pid))
                except Exception:
                    pass
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
        except Exception:
            pass
        pid = os.getpid()
        def _exit_later():
            time.sleep(0.4)
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.4)
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        threading.Thread(target=_exit_later, daemon=True).start()
        return jsonify({"success": True, "message": "Backend shutting down"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e) }), 500


@app.get('/api/admin/system')
def admin_system():
    uptime = int(time.time() - _START_TS)
    return jsonify({
        "success": True,
        "service": "Ailey.AI",
        "uptime_sec": uptime,
        "ports": {"api": 5502, "health": 5503},
    })


# ─── Live System Stats (Hardware Monitoring) ──────────────────────────────────

@app.get('/api/system/stats')
def api_system_stats():
    """Return live hardware stats: CPU, RAM, GPU, temperature, disk."""
    import psutil
    try:
        vm = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.3)
        disk = psutil.disk_usage('/')

        # macOS thermal / temperature via powermetrics (non-blocking, cached)
        temp_info = _get_thermal_info()

        # MLX model info
        model_status = "unloaded"
        model_name = None
        model_paused = getattr(app, '_model_paused', False)
        if _llm_module._model is not None:
            model_status = "paused" if model_paused else "active"
            model_name = os.path.basename(os.environ.get('AILEY_MLX_MODEL', 'Ministral-3-14B-Reasoning-5bit'))

        # IdleThinker status
        thinker_enabled = not getattr(idle_thinker, '_disabled', False)
        thinker_busy = idle_thinker.is_busy
        thinker_type = idle_thinker.current_thought_type

        # Thermal protection level
        thermal_level = getattr(app, '_thermal_level', 0)

        # LifeSim needs snapshot
        life_sim_data = None
        try:
            nd = _load_needs()
            life_sim_data = {
                "hunger": nd.get("hunger", 0),
                "thirst": nd.get("thirst", 0),
                "tiredness": nd.get("tiredness", 0),
                "toilet": nd.get("toilet", 0),
                "hygiene": nd.get("hygiene", 0),
                "environment": nd.get("environment", 0),
                "social": nd.get("social", 50),
                "daily_mood": nd.get("daily_mood", 90),
            }
        except Exception:
            pass

        return jsonify({
            "success": True,
            "uptime_sec": int(time.time() - _START_TS),
            "cpu": {
                "percent": cpu_pct,
                "cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False),
            },
            "ram": {
                "total_gb": round(vm.total / (1024**3), 1),
                "used_gb": round(vm.used / (1024**3), 1),
                "available_gb": round(vm.available / (1024**3), 1),
                "percent": vm.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "used_gb": round(disk.used / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "percent": disk.percent,
            },
            "temperature": temp_info,
            "battery": _get_battery_info(),
            "model": {
                "status": model_status,
                "name": model_name,
                "paused": model_paused,
            },
            "idle_thinker": {
                "enabled": thinker_enabled,
                "busy": thinker_busy,
                "current_type": thinker_type,
                "current_task_name": _resolve_thinker_name(thinker_type),
                "idle_seconds": int(time.time() - idle_thinker._last_user_activity),
                "generating_image": idle_thinker.is_generating_image,
            },
            "thermal_level": thermal_level,
            "auto_research": core.auto_research_enabled,
            "life_sim": life_sim_data,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Thermal info cache (powermetrics is slow, cache for 10s)
_thermal_cache: dict = {"ts": 0, "data": {}}

def _get_thermal_info() -> dict:
    """Get macOS thermal info. Cached for 10 seconds."""
    now = time.time()
    if now - _thermal_cache["ts"] < 10 and _thermal_cache["data"]:
        return _thermal_cache["data"]

    info: dict = {"cpu_temp_c": None, "gpu_temp_c": None, "thermal_pressure": "nominal"}
    try:
        # Use sysctl for quick CPU die temperature (no sudo needed)
        r = subprocess.run(
            ["sysctl", "-n", "machdep.xcpm.cpu_thermal_level"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                info["cpu_thermal_level"] = int(r.stdout.strip())
            except ValueError:
                pass

        # Try thermal pressure via pmset
        r2 = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True, text=True, timeout=2,
        )
        if r2.returncode == 0:
            out = r2.stdout.lower()
            if "nominal" in out:
                info["thermal_pressure"] = "nominal"
            elif "light" in out:
                info["thermal_pressure"] = "light"
            elif "moderate" in out:
                info["thermal_pressure"] = "moderate"
            elif "heavy" in out or "critical" in out:
                info["thermal_pressure"] = "heavy"

        # Try to get actual temperatures via powermetrics (may require sudo)
        # Fallback: use osx-cpu-temp if installed, or skip
        r3 = subprocess.run(
            ["which", "osx-cpu-temp"],
            capture_output=True, text=True, timeout=2,
        )
        if r3.returncode == 0:
            r4 = subprocess.run(
                ["osx-cpu-temp"],
                capture_output=True, text=True, timeout=3,
            )
            if r4.returncode == 0 and r4.stdout.strip():
                import re as _re
                m = _re.search(r'([\d.]+)\s*°C', r4.stdout)
                if m:
                    info["cpu_temp_c"] = float(m.group(1))
    except Exception:
        pass

    _thermal_cache["ts"] = now
    _thermal_cache["data"] = info
    return info


# Battery info cache (pmset -g batt, cached for 15s)
_battery_cache: dict = {"ts": 0, "data": {}}

def _get_battery_info() -> dict:
    """Get macOS battery info via pmset -g batt. Cached for 15 seconds."""
    now = time.time()
    if now - _battery_cache["ts"] < 15 and _battery_cache["data"]:
        return _battery_cache["data"]

    info: dict = {"percent": None, "charging": False, "ac_power": False, "present": False}
    try:
        r = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout
            # Line 1: "Now drawing from 'AC Power'" or "'Battery Power'"
            if "'AC Power'" in out:
                info["ac_power"] = True
            # Line 2: "-InternalBattery-0 (id=...)	85%; charging; 1:23 remaining"
            import re as _re
            m = _re.search(r'(\d+)%', out)
            if m:
                info["percent"] = int(m.group(1))
                info["present"] = True
            if "charging" in out.lower() and "not charging" not in out.lower() and "discharging" not in out.lower():
                info["charging"] = True
            elif "charged" in out.lower():
                info["charging"] = False
                info["ac_power"] = True
    except Exception:
        pass

    _battery_cache["ts"] = now
    _battery_cache["data"] = info
    return info


# ─── Model Pause / Resume / Reload ───────────────────────────────────────────

# Flag: when paused, /api/chat returns a "model paused" message
app._model_paused = False

@app.post('/api/admin/model/clear-kv-cache')
def api_clear_kv_cache():
    """Clear MLX KV-cache and Metal GPU cache to free memory.
    Safe to call at any time (not during active generation).
    Useful after long conversations to reclaim GPU RAM.
    """
    freed_info = {}
    try:
        import mlx.core as mx
        before_mb = mx.metal.get_active_memory() / 1024**2
        cache_before_mb = mx.metal.get_cache_memory() / 1024**2
        mx.metal.clear_cache()
        after_mb = mx.metal.get_active_memory() / 1024**2
        cache_after_mb = mx.metal.get_cache_memory() / 1024**2
        freed_info["metal_cache_freed_mb"] = round(cache_before_mb - cache_after_mb, 1)
        freed_info["active_before_mb"] = round(before_mb, 1)
        freed_info["active_after_mb"] = round(after_mb, 1)
    except Exception as e:
        freed_info["metal_error"] = str(e)
    try:
        from ailey_system.llm_mlx import clear_prompt_cache
        clear_prompt_cache()
        freed_info["prompt_cache"] = "cleared"
    except Exception as e:
        freed_info["prompt_cache_error"] = str(e)
    print(f"[KV-Cache] Cleared: {freed_info}")
    return jsonify({"success": True, "freed": freed_info})

@app.post('/api/songs/translate-titles')
def api_songs_translate_titles():
    """Batch-translate German song/album titles to English using the fast LLM.
    
    Writes title_en to each manifest (songs + albums). Skips if title_en already set.
    Optional JSON body: {"force": true} to re-translate even if title_en exists.
    Returns counts of translated/skipped/failed items.
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))

    from ailey_system.llm_mlx import MLXGenerator
    gen = MLXGenerator.get()
    if gen is None:
        return jsonify({"success": False, "error": "Model not loaded"}), 503

    _translate_sys = (
        "You are a precise translator. Translate the given title to natural English. "
        "Output ONLY the English title — no explanation, no quotes, no extra text. "
        "If the title is already English, return it unchanged."
    )

    def _translate_title(title: str) -> str:
        raw = gen.generate(_translate_sys, title, {"max_tokens": 30, "temperature": 0.3})
        return raw.strip().strip('"').strip("'")

    songs_done = 0
    songs_skip = 0
    albums_done = 0
    albums_skip = 0

    # ── Songs ──
    import os as _os, json as _json
    songs_dir = _os.path.join(_os.path.dirname(__file__), "ailey_users", "songs")
    if _os.path.isdir(songs_dir):
        for name in sorted(_os.listdir(songs_dir)):
            if name.startswith("_") or name.startswith("."):
                continue
            manifest_path = _os.path.join(songs_dir, name, "manifest.json")
            if not _os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    mf = _json.load(f)
                title = mf.get("title", "")
                if not title:
                    songs_skip += 1
                    continue
                if mf.get("title_en") and not force:
                    songs_skip += 1
                    continue
                title_en = _translate_title(title)
                if title_en and title_en != title:
                    mf["title_en"] = title_en
                    with open(manifest_path, "w", encoding="utf-8") as f:
                        _json.dump(mf, f, ensure_ascii=False, indent=2)
                    songs_done += 1
                else:
                    mf["title_en"] = title  # same, already English
                    with open(manifest_path, "w", encoding="utf-8") as f:
                        _json.dump(mf, f, ensure_ascii=False, indent=2)
                    songs_skip += 1
            except Exception as e:
                print(f"[translate-titles] Song {name}: {e}")
                songs_skip += 1

    # ── Albums ──
    try:
        from ailey_system.idle_thinker import ALBUMS_DIR
        albums_base = _os.path.join(_os.path.dirname(__file__), ALBUMS_DIR)
    except Exception:
        albums_base = _os.path.join(_os.path.dirname(__file__), "ailey_users", "albums")
    if _os.path.isdir(albums_base):
        for slug in sorted(_os.listdir(albums_base)):
            album_json = _os.path.join(albums_base, slug, "album.json")
            if not _os.path.isfile(album_json):
                continue
            try:
                with open(album_json, "r", encoding="utf-8") as f:
                    ab = _json.load(f)
                title = ab.get("title", "")
                if not title:
                    albums_skip += 1
                    continue
                if ab.get("title_en") and not force:
                    albums_skip += 1
                    continue
                title_en = _translate_title(title)
                if title_en:
                    ab["title_en"] = title_en
                    with open(album_json, "w", encoding="utf-8") as f:
                        _json.dump(ab, f, ensure_ascii=False, indent=2)
                    albums_done += 1
                else:
                    albums_skip += 1
            except Exception as e:
                print(f"[translate-titles] Album {slug}: {e}")
                albums_skip += 1

    return jsonify({
        "success": True,
        "songs_translated": songs_done,
        "songs_skipped": songs_skip,
        "albums_translated": albums_done,
        "albums_skipped": albums_skip,
    })

@app.post('/api/songs/repush-all')
def api_songs_repush_all():
    """Re-push all songs with MP3 to the portal gallery.
    
    Optional JSON body: {"force_reupload": true} to re-upload even if portal_audio_url is set.
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force_reupload", False))
    try:
        poller = get_portal_poller()
    except Exception:
        poller = None
    if poller is None:
        return jsonify({"success": False, "error": "portal poller not running"}), 503
    try:
        result = poller.repush_songs(force_reupload=force)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.post('/api/admin/model/pause')
def api_model_pause():
    """Pause the model — chat requests will return a placeholder. Also pauses idle thinker."""
    app._model_paused = True
    idle_thinker._disabled = True
    idle_thinker._paused = True
    return jsonify({"success": True, "status": "paused"})

@app.post('/api/admin/model/resume')
def api_model_resume():
    """Resume the model after pause. Also resumes idle thinker."""
    from ailey_system.llm_mlx import allow_auto_reload
    app._model_paused = False
    idle_thinker._disabled = False
    idle_thinker._paused = False
    try:
        allow_auto_reload()
    except Exception:
        pass
    return jsonify({"success": True, "status": "active"})

@app.post('/api/admin/model/reload')
def api_model_reload():
    """Unload and reload the MLX model (useful after config change)."""
    from ailey_system.llm_mlx import _mlx_lock, allow_auto_reload
    try:
        # ensure autoreload is allowed for the explicit reload
        allow_auto_reload()
        with _mlx_lock:
            _llm_module._model = None
            _llm_module._tokenizer = None
            _llm_module._cache = None
            _llm_module._last_system_prompt = None
            MLXGenerator._instance = None
        # Clear Metal GPU cache before reloading (same fix as unload)
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass
        gc.collect()
        # Force reload
        gen = MLXGenerator.get()
        if gen is None:
            return jsonify({"success": False, "error": "Model failed to reload"}), 500
        app._model_paused = False
        return jsonify({"success": True, "status": "reloaded"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/admin/model/unload')
def api_model_unload():
    """Completely unload the MLX model from GPU/RAM to free resources."""
    from ailey_system.llm_mlx import _mlx_lock, block_auto_reload
    try:
        # Disable idle thinker to prevent it from reloading the model
        idle_thinker._disabled = True
        idle_thinker._paused = True
        app._model_paused = True

        # Block automatic reloads until admin explicitly allows them
        try:
            block_auto_reload()
        except Exception:
            pass

        with _mlx_lock:
            _llm_module._model = None
            _llm_module._tokenizer = None
            _llm_module._cache = None
            _llm_module._last_system_prompt = None
            MLXGenerator._instance = None

        # Force garbage collection to release GPU memory
        import gc
        gc.collect()

        # CRITICAL: MLX stores model weights in Metal GPU memory which is NOT
        # released by Python's garbage collector alone. We must explicitly clear
        # the Metal memory cache so the RAM is actually freed.
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception as _mx_err:
            pass  # Non-Metal (CPU) environment — no-op

        # Second GC pass after Metal cache clear to catch any dangling refs
        gc.collect()

        return jsonify({"success": True, "status": "unloaded"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/admin/system/shutdown-mac')
def api_shutdown_mac():
    """Shut down the Mac. Useful for remote access via LAN."""
    import subprocess
    try:
        # Use osascript to trigger a clean macOS shutdown
        subprocess.Popen(['osascript', '-e', 'tell application "System Events" to shut down'])
        return jsonify({"success": True, "status": "shutting_down"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Generation Settings (per-context max_tokens overrides) ──────────────────

# Runtime-configurable max_tokens for each context.
# Persisted to JSON file so they survive restarts.
_GEN_SETTINGS_FILE = os.path.join("ailey_users", "generation_settings.json")
_GEN_SETTINGS_DEFAULTS = {
    "chat":              500,    # Normal Ailey chat
    "portal_chat":      4000,    # Portal web chat (needs more for think+reply)
    "idle_thoughts":     500,    # IdleThinker: reflections, introspection, etc.
    "idle_book":        2500,    # IdleThinker: book authoring chunks
    "idle_book_deep":   6000,    # IdleThinker: deep-write book chunks (idle ≥ 1h)
    "idle_song":        1500,    # IdleThinker: creative song
    "code_ask":         1500,    # Code Mode: fragen
    "code_edit":        2500,    # Code Mode: bearbeiten
    "code_agent":       2000,    # Code Mode: agent
    "author_write":     1500,    # Author Mode: weiterschreiben
    "author_review":    1000,    # Author Mode: lektorat / brainstorm / etc.
}

def _load_gen_settings() -> dict:
    """Load generation settings from disk, merged with defaults."""
    settings = dict(_GEN_SETTINGS_DEFAULTS)
    try:
        if os.path.isfile(_GEN_SETTINGS_FILE):
            with open(_GEN_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in settings and isinstance(v, (int, float)):
                        settings[k] = int(v)
    except Exception:
        pass
    return settings

def _save_gen_settings(settings: dict):
    """Persist generation settings to disk."""
    try:
        os.makedirs(os.path.dirname(_GEN_SETTINGS_FILE), exist_ok=True)
        with open(_GEN_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[GenSettings] ⚠️ Save failed: {e}")

def get_gen_setting(key: str) -> int:
    """Get a single generation setting by key. Used by idle_thinker, code chat, etc."""
    settings = _load_gen_settings()
    return settings.get(key, _GEN_SETTINGS_DEFAULTS.get(key, 500))


@app.route('/api/admin/generation-settings', methods=['GET', 'POST'])
def api_generation_settings():
    """GET: return all settings. POST {key: value, ...}: update one or more settings."""
    if request.method == 'GET':
        settings = _load_gen_settings()
        return jsonify({"success": True, "settings": settings, "defaults": _GEN_SETTINGS_DEFAULTS})
    data = request.get_json(silent=True) or {}
    settings = _load_gen_settings()
    changed = []
    for k, v in data.items():
        if k in _GEN_SETTINGS_DEFAULTS:
            try:
                val = int(v)
                val = max(50, min(16384, val))  # Clamp to safe range
                settings[k] = val
                changed.append(k)
            except (ValueError, TypeError):
                pass
    if changed:
        _save_gen_settings(settings)
    return jsonify({"success": True, "settings": settings, "changed": changed})


# ─── Custom IdleThinker Activities ───────────────────────────────────────────

_CUSTOM_ACTIVITIES_FILE = os.path.join("ailey_users", "custom_activities.json")

# Context source keys that can be toggled per custom activity
CUSTOM_ACTIVITY_CONTEXT_KEYS = [
    "rag", "people", "chat_main", "chat_portal",
    "reflections", "diaries", "quick_thoughts", "art",
]

# Valid mood effects a custom activity can trigger (same as _VALID_CHAR_MOODS + "none")
CUSTOM_ACTIVITY_MOOD_OPTIONS = ["none", "creative", "playful", "curious", "happy", "melancholic", "tired"]

def _make_empty_slot(idx: int) -> dict:
    return {
        "id": f"custom_{idx}",
        "name": "",
        "prompt": "",
        "weight": 0,
        "enabled": False,
        "context": {k: False for k in CUSTOM_ACTIVITY_CONTEXT_KEYS},
        "include_personality": True,  # inject Ailey's standard system prompt (personality, tone, self-description)
        "mood_effect": "none",        # which char-mood this activity pushes
        "mood_intensity": 2,          # 1-5, how strongly it pushes (default: mild)
    }

_CUSTOM_ACTIVITIES_DEFAULT = {
    "slots": [_make_empty_slot(1), _make_empty_slot(2), _make_empty_slot(3)]
}


def load_custom_activities() -> dict:
    """Load custom activities config from disk."""
    try:
        if os.path.isfile(_CUSTOM_ACTIVITIES_FILE):
            with open(_CUSTOM_ACTIVITIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure all 3 slots exist and have proper structure
            slots = data.get("slots", [])
            while len(slots) < 3:
                slots.append(_make_empty_slot(len(slots) + 1))
            for slot in slots:
                if "context" not in slot:
                    slot["context"] = {k: False for k in CUSTOM_ACTIVITY_CONTEXT_KEYS}
                for ck in CUSTOM_ACTIVITY_CONTEXT_KEYS:
                    if ck not in slot["context"]:
                        slot["context"][ck] = False
                # Ensure mood fields exist (migration from older configs)
                if "mood_effect" not in slot:
                    slot["mood_effect"] = "none"
                if "mood_intensity" not in slot:
                    slot["mood_intensity"] = 2
                if "include_personality" not in slot:
                    slot["include_personality"] = True
            return {"slots": slots[:3]}
    except Exception as e:
        print(f"[CustomActivities] ⚠️ Load error: {e}")
    return json.loads(json.dumps(_CUSTOM_ACTIVITIES_DEFAULT))


def _resolve_thinker_name(thought_type: str | None) -> str | None:
    """Return the human-readable name for a custom slot, or None for built-in types."""
    if not thought_type or not thought_type.startswith("custom_slot_"):
        return None
    try:
        ca = load_custom_activities()
        for slot in ca.get("slots", []):
            if slot.get("id") == thought_type:
                return slot.get("name") or thought_type
    except Exception:
        pass
    return thought_type


def _save_custom_activities(data: dict):
    """Persist custom activities config to disk."""
    try:
        os.makedirs(os.path.dirname(_CUSTOM_ACTIVITIES_FILE), exist_ok=True)
        with open(_CUSTOM_ACTIVITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CustomActivities] ⚠️ Save failed: {e}")


@app.route('/api/admin/custom-activities', methods=['GET', 'PUT'])
def api_custom_activities():
    """GET: return all 3 custom activity slots.
    PUT: update all slots. Body: {slots: [{id, name, prompt, weight, enabled, context, mood_effect, mood_intensity}, ...]}
    """
    if request.method == 'GET':
        return jsonify({"success": True, **load_custom_activities()})

    data = request.get_json(silent=True) or {}
    incoming_slots = data.get("slots", [])
    if not isinstance(incoming_slots, list):
        return jsonify({"success": False, "message": "slots array required"}), 400

    current = load_custom_activities()
    for i, slot_data in enumerate(incoming_slots[:3]):
        if i >= len(current["slots"]):
            break
        slot = current["slots"][i]
        if "name" in slot_data:
            slot["name"] = str(slot_data["name"])[:80]
        if "prompt" in slot_data:
            slot["prompt"] = str(slot_data["prompt"])[:2000]
        if "weight" in slot_data:
            try:
                slot["weight"] = max(0, min(50, int(slot_data["weight"])))
            except (ValueError, TypeError):
                pass
        if "enabled" in slot_data:
            slot["enabled"] = bool(slot_data["enabled"])
        if "include_personality" in slot_data:
            slot["include_personality"] = bool(slot_data["include_personality"])
        if "context" in slot_data and isinstance(slot_data["context"], dict):
            for ck in CUSTOM_ACTIVITY_CONTEXT_KEYS:
                if ck in slot_data["context"]:
                    slot["context"][ck] = bool(slot_data["context"][ck])
        if "mood_effect" in slot_data:
            me = str(slot_data["mood_effect"]).lower()
            if me in CUSTOM_ACTIVITY_MOOD_OPTIONS:
                slot["mood_effect"] = me
        if "mood_intensity" in slot_data:
            try:
                slot["mood_intensity"] = max(1, min(5, int(slot_data["mood_intensity"])))
            except (ValueError, TypeError):
                pass

    _save_custom_activities(current)
    return jsonify({"success": True, **current})


# ─── IdleThinker Toggle ──────────────────────────────────────────────────────

@app.route('/api/admin/idle-thinker', methods=['GET', 'POST'])
def api_idle_thinker_toggle():
    """GET: return status. POST {enabled: bool}: enable/disable IdleThinker."""
    if request.method == 'GET':
        disabled = getattr(idle_thinker, '_disabled', False)
        return jsonify({
            "success": True,
            "enabled": not disabled,
            "busy": idle_thinker.is_busy,
            "current_type": idle_thinker.current_thought_type,
            "current_task_name": _resolve_thinker_name(idle_thinker.current_thought_type),
        })
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify({"success": False, "message": "enabled boolean required"}), 400
    idle_thinker._disabled = not enabled
    if enabled:
        idle_thinker._paused = False  # Explicit enable clears pause
    else:
        idle_thinker._paused = True   # Mark as user-paused so thermal monitor won't re-enable
    return jsonify({"success": True, "enabled": enabled})


@app.route('/api/admin/trigger-blog', methods=['POST'])
def api_trigger_blog():
    """Force-trigger a blog post immediately. POST {topic?: str, context?: str}."""
    data = request.get_json(silent=True) or {}
    topic = data.get('topic', '')
    extra_context = data.get('context', '')

    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "IdleThinker is busy, try again later"}), 409

    import threading

    def _run_blog():
        try:
            from ailey_system.idle_thinker import _blog_written_today, _mark_blog_written_today, _last_blog_date
            import ailey_system.idle_thinker as _it_mod

            # Temporarily clear today's blog flag so it can write
            old_date = _it_mod._last_blog_date
            _it_mod._last_blog_date = ""

            # If a specific topic was given, temporarily override _choose_blog_topic
            if topic:
                orig_choose = idle_thinker._choose_blog_topic
                idle_thinker._choose_blog_topic = lambda: topic

            # If extra context was given, inject into the prompt builder
            if extra_context:
                orig_build = idle_thinker._build_blog_prompt
                def _patched_build(t, cs):
                    result = orig_build(t, cs)
                    result["user"] += f"\n\nZUSÄTZLICHER KONTEXT:\n{extra_context}"
                    return result
                idle_thinker._build_blog_prompt = _patched_build

            # Get generator
            gen = MLXGenerator.get()
            if not gen:
                print("[trigger-blog] No generator available")
                return

            idle_thinker._do_blog_writing(gen, "")

            # Restore originals
            if topic:
                idle_thinker._choose_blog_topic = orig_choose
            if extra_context:
                idle_thinker._build_blog_prompt = orig_build

        except Exception as e:
            print(f"[trigger-blog] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run_blog, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": f"Blog generation triggered (topic: {topic or 'random'})",
    })


@app.route('/api/admin/trigger-code', methods=['POST'])
def api_trigger_code():
    """Force-trigger creative coding immediately."""
    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "IdleThinker is busy, try again later"}), 409

    import threading

    def _run_code():
        try:
            gen = MLXGenerator.get()
            if not gen:
                print("[trigger-code] No generator available")
                return
            idle_thinker._do_creative_coding(gen, "")
        except Exception as e:
            print(f"[trigger-code] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run_code, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": "Creative coding triggered",
    })


@app.route('/api/admin/repair-code-gallery', methods=['POST'])
def api_repair_code_gallery():
    """Scan all code gallery files, validate syntax, fix broken ones with Qwen Coder,
    save locally, and re-push to portal (allinkl).
    """
    import threading

    def _run_repair():
        try:
            result = idle_thinker.repair_code_gallery()
            print(f"[repair-code-gallery] Done: {result}")
        except Exception as e:
            print(f"[repair-code-gallery] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run_repair, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": "Code gallery repair started in background. Check logs for progress.",
    })


# ─── Image Generation (MFLUX) ─────────────────────────────────────────────

@app.route('/api/admin/trigger-image', methods=['POST'])
def api_trigger_image():
    """Force-trigger image generation immediately (Mainapp only, not Portal)."""
    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "IdleThinker is busy, try again later"}), 409

    data = request.get_json(silent=True) or {}
    custom_prompt = data.get("prompt", "")  # Optional: user-provided prompt

    import threading

    def _run_image():
        try:
            gen = MLXGenerator.get()
            if not gen:
                print("[trigger-image] No generator available")
                return
            if custom_prompt:
                # On-demand with custom prompt — skip LLM prompt generation
                from ailey_system.image_generator import generate_image, build_lora_args as _trig_build_loras
                # Optional: request Ailey selfie mode via JSON { "ailey_selfie": true }
                _trig_ailey = data.get("ailey_selfie", False)
                _trig_lora_p, _trig_lora_s = None, None
                if _trig_ailey:
                    _trig_lora_p, _trig_lora_s, _ = _trig_build_loras(
                        ["realism"], include_ailey=True, exclude_nsfw=True,
                    )
                idle_thinker._generating_image = True
                unloaded_model = False
                try:
                    # Unload Ministral to free GPU memory for MFLUX
                    try:
                        idle_thinker._unload_llm_for_image_gen()
                        unloaded_model = True
                        print("[trigger-image] Ministral unloaded for image generation")
                    except Exception as ue:
                        print(f"[trigger-image] Model unload failed: {ue} — trying with --low-ram")

                    filepath, filename = generate_image(
                        prompt=custom_prompt,
                        title=data.get("title", "On-Demand"),
                        aspect_ratio=data.get("aspect_ratio", "1:1"),
                        image_path=data.get("image_path"),
                        image_strength=float(data.get("image_strength", 0.4)),
                        low_ram=not unloaded_model,  # use --low-ram if Ministral still loaded
                        private=True,  # Simon's image → image_private/, not uploaded
                        image_type="selfie" if _trig_ailey else "img",
                        username="Simon",
                        lora_paths=_trig_lora_p,
                        lora_scales=_trig_lora_s,
                    )
                finally:
                    idle_thinker._generating_image = False
                    if unloaded_model:
                        print("[trigger-image] Reloading Ministral...")
                        try:
                            idle_thinker._reload_llm_after_image_gen()
                            print("[trigger-image] Ministral reloaded")
                        except Exception as re_err:
                            print(f"[trigger-image] Ministral reload failed: {re_err}")

                if filepath:
                    # NOTE: User-triggered images are NOT pushed to gallery.
                    # Only Ailey's own idle_thinker images are published.
                    print(f"[trigger-image] On-demand complete: {filename}")
            else:
                # Full pipeline: LLM crafts prompt + MFLUX generates
                idle_thinker._do_image_generation(gen, "")
        except Exception as e:
            print(f"[trigger-image] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            idle_thinker._generating_image = False

    t = threading.Thread(target=_run_image, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": "Image generation triggered" + (" (custom prompt)" if custom_prompt else ""),
    })


@app.get('/api/admin/image-status')
def api_admin_image_status():
    """Return current image generation status."""
    from ailey_system.image_generator import is_mflux_available, can_generate_idle_image
    return jsonify({
        "success": True,
        "generating": idle_thinker.is_generating_image,
        "mflux_available": is_mflux_available(),
        "can_generate_idle": can_generate_idle_image(),
        "is_busy": idle_thinker.is_busy,
    })


@app.get('/api/admin/ailey-emotes')
def api_ailey_emotes():
    """List all available Ailey emote/mood images for img2img."""
    from ailey_system.image_generator import list_ailey_emotes
    emotes = list_ailey_emotes()
    return jsonify({"success": True, "emotes": emotes, "count": len(emotes)})


@app.route('/api/admin/emote-image/<mood>')
def api_emote_image(mood):
    """Serve an Ailey emote image by mood name."""
    from ailey_system.image_generator import get_ailey_emote_path
    path = get_ailey_emote_path(mood)
    if path and os.path.isfile(path):
        return send_file(path, mimetype='image/jpeg')
    return jsonify({"success": False, "error": "Emote not found"}), 404


# ─── Social Media Content API ─────────────────────────────────────────────

@app.get('/api/social/pending')
def api_social_pending():
    """List all pending social media post drafts."""
    social_dir = os.path.join("ailey_users", "social_media", "pending")
    posts = []
    if os.path.isdir(social_dir):
        for fname in sorted(os.listdir(social_dir), reverse=True):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(social_dir, fname)) as f:
                        posts.append(json.load(f))
                except Exception:
                    pass
    return jsonify({"success": True, "posts": posts, "count": len(posts)})


@app.get('/api/social/all')
def api_social_all():
    """List all social media posts (pending + published + archived)."""
    result = {"pending": [], "published": [], "archived": []}
    base = os.path.join("ailey_users", "social_media")
    for status in result:
        d = os.path.join(base, status)
        if os.path.isdir(d):
            for fname in sorted(os.listdir(d), reverse=True):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(d, fname)) as f:
                            result[status].append(json.load(f))
                    except Exception:
                        pass
    return jsonify({"success": True, **result})


@app.route('/api/social/approve/<post_id>', methods=['POST'])
def api_social_approve(post_id):
    """Approve a pending social media post (move to published, optionally generate image)."""
    pending_dir = os.path.join("ailey_users", "social_media", "pending")
    published_dir = os.path.join("ailey_users", "social_media", "published")
    os.makedirs(published_dir, exist_ok=True)

    post_file = os.path.join(pending_dir, f"{post_id}.json")
    if not os.path.isfile(post_file):
        return jsonify({"success": False, "error": "Post not found"}), 404

    with open(post_file) as f:
        post = json.load(f)

    data = request.get_json(silent=True) or {}
    generate_img = data.get("generate_image", False)

    # If requested, generate image for the post
    if generate_img and post.get("image_prompt"):
        import threading
        def _gen_img_for_post():
            try:
                from ailey_system.image_generator import generate_image, AILEY_FACE_PREFIX, AILEY_SELFIE_LORA_PATH, AILEY_SELFIE_LORA_SCALE
                # Enforce Ailey face prefix + "no text" in the prompt
                _prompt = post["image_prompt"]
                if "A!ley" not in _prompt:
                    _prompt = AILEY_FACE_PREFIX + _prompt
                _no_text = ", absolutely no text, no letters, no words, no writing, no watermark in the image"
                if _no_text not in _prompt.lower():
                    _prompt = _prompt.rstrip(".").rstrip() + _no_text
                idle_thinker._generating_image = True
                try:
                    filepath, filename = generate_image(
                        prompt=_prompt,
                        title=post.get("caption", "Social Post")[:50],
                        aspect_ratio="4:5",
                        lora_paths=[AILEY_SELFIE_LORA_PATH],
                        lora_scales=[AILEY_SELFIE_LORA_SCALE],
                        image_type="selfie",
                    )
                finally:
                    idle_thinker._generating_image = False
                if filepath:
                    # Stamp with Instagram branding (title, A!ley sign, URL)
                    try:
                        from ailey_system.image_stamp import stamp_instagram_image
                        _stamp_title = post.get("title") or post.get("caption", "")[:40] or "Instagram Post"
                        stamp_instagram_image(filepath, _stamp_title)
                        print(f"[social/approve] ✅ Image stamped: {filename}")
                    except Exception as stamp_err:
                        print(f"[social/approve] stamp warning: {stamp_err}")
                    post["image_path"] = filepath
                    post["image_filename"] = filename
                    # Upload to portal
                    try:
                        from ailey_system.portal_poller import get_portal_poller
                        poller = get_portal_poller()
                        file_url = poller._upload_gallery_file(filepath, filename)
                        if file_url:
                            post["image_url"] = file_url
                    except Exception:
                        pass
                    # Save updated post
                    dest = os.path.join(published_dir, f"{post_id}.json")
                    with open(dest, "w") as f:
                        json.dump(post, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[social/approve] image gen error: {e}")

        t = threading.Thread(target=_gen_img_for_post, daemon=True)
        t.start()

    # Move post to published
    post["status"] = "approved"
    post["approved_at"] = datetime.now().isoformat()
    dest = os.path.join(published_dir, f"{post_id}.json")
    with open(dest, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    # Remove from pending
    try:
        os.remove(post_file)
    except Exception:
        pass

    return jsonify({"success": True, "post": post})


@app.route('/api/social/edit/<post_id>', methods=['POST'])
def api_social_edit(post_id):
    """Edit a pending social media post."""
    pending_dir = os.path.join("ailey_users", "social_media", "pending")
    post_file = os.path.join(pending_dir, f"{post_id}.json")
    if not os.path.isfile(post_file):
        return jsonify({"success": False, "error": "Post not found"}), 404

    with open(post_file) as f:
        post = json.load(f)

    data = request.get_json(silent=True) or {}
    # Update fields that are provided
    for key in ("caption", "hashtags", "image_prompt", "mood", "category"):
        if key in data:
            post[key] = data[key]

    with open(post_file, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    return jsonify({"success": True, "post": post})


@app.route('/api/social/delete/<post_id>', methods=['DELETE', 'POST'])
def api_social_delete(post_id):
    """Delete (archive) a social media post."""
    archive_dir = os.path.join("ailey_users", "social_media", "archived")
    os.makedirs(archive_dir, exist_ok=True)

    for status_dir in ("pending", "published"):
        d = os.path.join("ailey_users", "social_media", status_dir)
        post_file = os.path.join(d, f"{post_id}.json")
        if os.path.isfile(post_file):
            # Move to archive
            with open(post_file) as f:
                post = json.load(f)
            post["status"] = "archived"
            post["archived_at"] = datetime.now().isoformat()
            dest = os.path.join(archive_dir, f"{post_id}.json")
            with open(dest, "w") as f:
                json.dump(post, f, indent=2, ensure_ascii=False)
            os.remove(post_file)
            return jsonify({"success": True, "archived": True})

    return jsonify({"success": False, "error": "Post not found"}), 404


@app.get('/api/social/published')
def api_social_published():
    """List approved/published social media posts with image serving info."""
    published_dir = os.path.join("ailey_users", "social_media", "published")
    posts = []
    if os.path.isdir(published_dir):
        for fname in sorted(os.listdir(published_dir), reverse=True):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(published_dir, fname)) as f:
                        post = json.load(f)
                    # Enrich: add local image URL if the file exists
                    if post.get("image_filename"):
                        base = os.path.dirname(os.path.abspath(__file__))
                        img_path = os.path.join(base, "ailey_users", "image_gallery", post["image_filename"])
                        if os.path.isfile(img_path):
                            post["_local_image_url"] = f"/api/image/file/{post['image_filename']}"
                    posts.append(post)
                except Exception:
                    pass
    return jsonify({"success": True, "posts": posts, "count": len(posts)})


@app.route('/api/social/mark-posted/<post_id>', methods=['POST'])
def api_social_mark_posted(post_id):
    """Mark a published post as actually posted to Instagram."""
    published_dir = os.path.join("ailey_users", "social_media", "published")
    post_file = os.path.join(published_dir, f"{post_id}.json")
    if not os.path.isfile(post_file):
        return jsonify({"success": False, "error": "Post not found"}), 404

    with open(post_file) as f:
        post = json.load(f)

    post["published_at"] = datetime.now().isoformat()
    post["status"] = "published"

    with open(post_file, "w") as f:
        json.dump(post, f, indent=2, ensure_ascii=False)

    return jsonify({"success": True, "post": post})


@app.route('/api/social/generate-image/<post_id>', methods=['POST'])
def api_social_generate_image(post_id):
    """Generate an image for an already-approved post (published dir)."""
    published_dir = os.path.join("ailey_users", "social_media", "published")
    post_file = os.path.join(published_dir, f"{post_id}.json")
    if not os.path.isfile(post_file):
        return jsonify({"success": False, "error": "Post not found"}), 404

    with open(post_file) as f:
        post = json.load(f)

    if not post.get("image_prompt"):
        return jsonify({"success": False, "error": "No image_prompt in post"}), 400

    if getattr(idle_thinker, '_generating_image', False):
        return jsonify({"success": False, "message": "Image generation already running"}), 409
    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "Image generation busy, try later"}), 409

    import threading
    def _gen():
        try:
            from ailey_system.image_generator import generate_image, AILEY_FACE_PREFIX, AILEY_SELFIE_LORA_PATH, AILEY_SELFIE_LORA_SCALE
            _prompt = post["image_prompt"]
            if "A!ley" not in _prompt:
                _prompt = AILEY_FACE_PREFIX + _prompt
            _no_text = ", absolutely no text, no letters, no words, no writing, no watermark in the image"
            if _no_text not in _prompt.lower():
                _prompt = _prompt.rstrip(".").rstrip() + _no_text
            idle_thinker._generating_image = True
            try:
                filepath, filename = generate_image(
                    prompt=_prompt,
                    title=post.get("caption", "Social Post")[:50],
                    aspect_ratio="4:5",
                    lora_paths=[AILEY_SELFIE_LORA_PATH],
                    lora_scales=[AILEY_SELFIE_LORA_SCALE],
                    image_type="selfie",
                )
            finally:
                idle_thinker._generating_image = False
            if filepath:
                # Stamp with Instagram branding (title, A!ley sign, URL)
                try:
                    from ailey_system.image_stamp import stamp_instagram_image
                    _stamp_title = post.get("title") or post.get("caption", "")[:40] or "Instagram Post"
                    stamp_instagram_image(filepath, _stamp_title)
                except Exception as se:
                    print(f"[social/gen-image] stamp warning: {se}")
                post["image_path"] = filepath
                post["image_filename"] = filename
                # Upload to portal
                try:
                    from ailey_system.portal_poller import get_portal_poller
                    poller = get_portal_poller()
                    file_url = poller._upload_gallery_file(filepath, filename)
                    if file_url:
                        post["image_url"] = file_url
                except Exception:
                    pass
                with open(post_file, "w") as f:
                    json.dump(post, f, indent=2, ensure_ascii=False)
                print(f"[social/gen-image] ✅ Image generated for {post_id}: {filename}")
        except Exception as e:
            print(f"[social/gen-image] error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_gen, daemon=True)
    t.start()
    return jsonify({"success": True, "message": "Image generation started"})


@app.route('/api/admin/trigger-social', methods=['POST'])
def api_trigger_social():
    """Force-trigger social media content planning."""
    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "IdleThinker is busy, try again later"}), 409

    import threading

    def _run_social():
        try:
            gen = MLXGenerator.get()
            if not gen:
                print("[trigger-social] No generator available")
                return
            idle_thinker._do_social_content(gen, "")
        except Exception as e:
            print(f"[trigger-social] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run_social, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": "Social content planning triggered",
    })


@app.route('/api/admin/trigger-social-prompt', methods=['POST'])
def api_trigger_social_prompt():
    """Force-trigger social media content planning with a specific topic/prompt."""
    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"success": False, "error": "topic required"}), 400
    if not _interrupt_thinker_and_wait(max_wait=15):
        return jsonify({"success": False, "message": "IdleThinker is busy, try again later"}), 409

    import threading

    def _run_social_prompted():
        try:
            gen = MLXGenerator.get()
            if not gen:
                print("[trigger-social-prompt] No generator available")
                return
            idle_thinker._do_social_content(gen, "", topic_override=topic)
        except Exception as e:
            print(f"[trigger-social-prompt] Error: {e}")
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=_run_social_prompted, daemon=True)
    t.start()

    return jsonify({
        "success": True,
        "message": f"Social content planning with topic '{topic[:50]}' triggered",
    })


@app.route('/api/admin/push-news', methods=['POST'])
def api_push_news():
    """Push a manual activity/news item to the portal feed."""
    data = request.get_json(silent=True) or {}
    event_type = data.get('type', 'announcement')
    title = data.get('title', '')
    preview = data.get('preview', '')
    emoji = data.get('emoji', '📢')
    url = data.get('url', '')

    if not title:
        return jsonify({"success": False, "message": "title required"}), 400

    from ailey_system.portal_poller import get_portal_poller
    poller = get_portal_poller()
    poller.push_activity(event_type, title, url=url, preview=preview, emoji=emoji)

    return jsonify({"success": True, "message": f"Activity pushed: {title}"})


@app.route('/api/admin/sync-gallery', methods=['POST'])
def api_sync_gallery():
    """Force-trigger a gallery sync to push cleaned titles to the portal."""
    from ailey_system.portal_poller import get_portal_poller
    poller = get_portal_poller()
    if not poller._portal_url:
        return jsonify({"success": False, "message": "Portal not configured"}), 503
    import threading
    threading.Thread(target=poller._push_public_content, daemon=True).start()
    return jsonify({"success": True, "message": "Gallery sync triggered"})


# ─── Thermal Protection (4-Level) ────────────────────────────────────────────

# Levels: 0=nominal, 1=light (reduce max_tokens), 2=moderate (pause idle thinker),
#         3=heavy (pause model entirely)
# NOTE: cpu_thermal_level (machdep.xcpm.cpu_thermal_level) on Apple Silicon is
# an opaque 0-255 value, NOT temperature in °C. Typical values under heavy MLX
# load are 40-80, which is perfectly normal. We rely PRIMARILY on macOS
# thermal_pressure (pmset -g therm) which is the OS-level thermal state.
# cpu_thermal_level thresholds are set conservatively high so they only kick in
# when the system is genuinely overheating, not during normal ML workloads.
app._thermal_level = 0
_thermal_thread_started = False

def _thermal_monitor_loop():
    """Background thread that checks thermal state every 30s and adjusts behavior."""
    while True:
        try:
            info = _get_thermal_info()
            pressure = info.get("thermal_pressure", "nominal")
            cpu_thermal = info.get("cpu_thermal_level", 0) or 0
            cpu_temp_c = info.get("cpu_temp_c")  # Actual °C if osx-cpu-temp installed

            old_level = app._thermal_level

            # Primary: macOS thermal_pressure (most reliable, OS-managed)
            # Secondary: cpu_thermal_level (opaque 0-255, only for extreme cases)
            # Tertiary: actual CPU temp in °C (if osx-cpu-temp installed)
            if pressure == "heavy" or cpu_thermal >= 200 or (cpu_temp_c and cpu_temp_c >= 105):
                app._thermal_level = 3
            elif pressure == "moderate" or cpu_thermal >= 160 or (cpu_temp_c and cpu_temp_c >= 95):
                app._thermal_level = 2
            elif pressure == "light" or cpu_thermal >= 128 or (cpu_temp_c and cpu_temp_c >= 85):
                app._thermal_level = 1
            else:
                app._thermal_level = 0

            # Apply protections
            if app._thermal_level >= 3 and not app._model_paused:
                app._model_paused = True
                print("🔥 THERMAL LEVEL 3: Model paused!")
            elif app._thermal_level >= 2:
                idle_thinker._disabled = True
                if app._thermal_level < 3 and app._model_paused and old_level >= 3:
                    # Stepped down from 3 to 2: resume model but keep thinker off
                    app._model_paused = False
                    print("🌡️ THERMAL LEVEL 2: Model resumed, IdleThinker disabled.")
            elif app._thermal_level <= 1:
                # Recovery: re-enable what was thermally disabled
                # BUT respect Code Mode pause — never re-enable if explicitly paused
                if getattr(idle_thinker, '_disabled', False) and not getattr(idle_thinker, '_paused', False):
                    idle_thinker._disabled = False
                if app._model_paused and old_level > 1:
                    app._model_paused = False
                    print("✅ THERMAL LEVEL ≤1: All systems nominal.")

            if app._thermal_level != old_level:
                print(f"🌡️ Thermal level changed: {old_level} → {app._thermal_level} (pressure={pressure})")

        except Exception as e:
            print(f"⚠️ Thermal monitor error: {e}")

        time.sleep(30)

def _start_thermal_monitor():
    global _thermal_thread_started
    if _thermal_thread_started:
        return
    _thermal_thread_started = True
    t = threading.Thread(target=_thermal_monitor_loop, daemon=True, name="AileyThermalMonitor")
    t.start()
    print("🌡️ Thermal protection monitor started (30s interval, 4 levels)")

# Start thermal monitor at import time
_start_thermal_monitor()


# ─── SVG File Serve ──────────────────────────────────────────────────────────

@app.get('/api/svg/file/<path:filename>')
def api_svg_file(filename):
    """Serve an SVG file from the gallery directory."""
    from flask import send_from_directory
    svg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'svg_gallery')
    # Security: only serve .svg files, no path traversal
    if '..' in filename or '/' in filename or not filename.endswith('.svg'):
        return ('', 403)
    fpath = os.path.join(svg_dir, filename)
    if os.path.isfile(fpath):
        return send_from_directory(svg_dir, filename, mimetype='image/svg+xml')
    return ('', 404)


@app.post('/api/memory/add')
def api_memory_add():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip() or f"memory_{int(time.time())}"
    text = (data.get('text') or '').strip()
    doc_type = (data.get('doc_type') or 'general').strip() or 'general'
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    if not text:
        return jsonify({"success": False, "message": "text required"}), 400
    try:
        n = core.rag_add(title=title, text=text, doc_type=doc_type, user=user)
        return jsonify({"success": True, "chunks": n})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/memory/search')
def api_memory_search():
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    n_results = int(data.get('n_results') or 5)
    threshold = float(data.get('threshold') or 0.5)
    results = core.rag_search(query, user=user, n_results=n_results, threshold=threshold)
    return jsonify({"success": True, "results": results})


@app.post('/api/memory/search/hybrid')
def api_memory_search_hybrid():
    """Hybrid search: LanceDB vector + GraphRAG merged results."""
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    n_results = int(data.get('n_results') or 5)
    threshold = float(data.get('threshold') or 0.5)
    results = core.rag_search_hybrid(query, user=user, n_results=n_results, threshold=threshold)
    return jsonify({"success": True, "results": results})


@app.post('/api/graph/search')
def api_graph_search():
    """Search the knowledge graph directly."""
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    max_results = int(data.get('max_results') or 5)
    if not query:
        return jsonify({"success": False, "error": "query required"}), 400
    results = core.graph_search(query, max_results=max_results)
    return jsonify({"success": True, "results": results, "count": len(results)})


@app.get('/api/graph/stats')
def api_graph_stats():
    """Get knowledge graph statistics."""
    return jsonify({"success": True, **core.graph_stats()})


@app.get('/api/graph/node/<path:name>')
def api_graph_node(name: str):
    """Get a specific graph node and its connections."""
    result = core.graph_node(name)
    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 404
    return jsonify({"success": True, "node": result})


@app.post('/api/graph/rebuild')
def api_graph_rebuild():
    """Force rebuild the knowledge graph from _IMPORT/ sources."""
    result = core.graph_rebuild()
    if "error" in result:
        return jsonify({"success": False, "error": result["error"]}), 500
    return jsonify({"success": True, **result})


@app.get('/api/memory/entries')
def api_memory_entries():
    """List RAG entries (paginated, optionally filtered by doc_type)."""
    doc_type = request.args.get('doc_type', None)
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    user = request.args.get('user', 'Simon')
    entries = core.rag_list_entries(user=user, doc_type=doc_type or None, limit=limit, offset=offset)
    stats = core.rag_stats(user=user)
    return jsonify({"success": True, "entries": entries, "stats": stats})


@app.delete('/api/memory/entries/<entry_id>')
def api_memory_delete_entry(entry_id):
    """Delete a single RAG entry by ID."""
    success = core.rag_delete_entry(user='Simon', entry_id=entry_id)
    return jsonify({"success": success})


@app.route('/api/auto-research', methods=['GET', 'POST'])
def api_auto_research():
    if request.method == 'GET':
        return jsonify({"success": True, "enabled": core.auto_research_enabled})
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if isinstance(enabled, bool):
        core.auto_research_enabled = enabled
        return jsonify({"success": True, "enabled": core.auto_research_enabled})
    return jsonify({"success": False, "message": "enabled boolean required"}), 400


# ── Explicit On-Demand Research API ──────────────────────────────────────────

@app.route('/api/research', methods=['POST'])
def api_explicit_research():
    """Run explicit on-demand research on a topic.

    Body JSON:
        query:   The topic/question to research (free-form text)
        user:    (optional) User name, default 'Simon'
    Returns research results + ingests them into RAG.
    """
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    user = data.get('user', 'Simon')
    if not query:
        return jsonify({"success": False, "error": "query erforderlich"}), 400

    try:
        # Generate search queries from the user's topic
        queries = core.generate_research_queries(query, max_queries=3)
        if not queries:
            # Fallback: use the raw query itself
            queries = [query]

        # Execute the research (fetches pages, summarises, ingests into RAG)
        stored = core.execute_research_queries(user, queries)

        # Build a readable summary of findings for the user
        if stored:
            summary_parts = []
            for s in stored:
                summary_parts.append(f"• **{s.get('url', '?')}** ({s.get('chars', 0)} Zeichen, Typ: {s.get('doc_type', 'research_auto')})")
            findings_list = "\n".join(summary_parts)
            return jsonify({
                "success": True,
                "queries": queries,
                "results_count": len(stored),
                "results": stored,
                "summary": f"🔍 {len(stored)} Quellen recherchiert und ins Wissen aufgenommen:\n{findings_list}",
            })
        else:
            return jsonify({
                "success": True,
                "queries": queries,
                "results_count": 0,
                "results": [],
                "summary": "🔍 Recherche durchgeführt, aber keine verwertbaren Ergebnisse gefunden.",
            })
    except Exception as e:
        print(f"[RESEARCH] ❌ Explicit research error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── File Upload to RAG API ───────────────────────────────────────────────────

@app.route('/api/rag/upload', methods=['POST'])
def api_rag_upload():
    """Upload a text-based file (PDF, DOCX, TXT, RTF, code files) and ingest into RAG.

    Accepts multipart/form-data with:
        file:    The uploaded file
        user:    (optional) User name, default 'Simon'
        title:   (optional) Custom title for the document
    Automatically chunks large documents and ingests as doc_type='user_rag'.
    """
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei hochgeladen"}), 400

    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"success": False, "error": "Dateiname fehlt"}), 400

    user = request.form.get('user', 'Simon')
    custom_title = request.form.get('title', '').strip()
    filename = uploaded.filename
    ext = os.path.splitext(filename)[1].lower()

    # Allowed extensions
    _ALLOWED_TEXT_EXT = {
        '.txt', '.md', '.rtf', '.csv', '.json', '.xml', '.html', '.htm',
        '.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.scss', '.sass',
        '.java', '.c', '.cpp', '.h', '.hpp', '.rs', '.go', '.rb', '.php',
        '.swift', '.kt', '.sh', '.bash', '.zsh', '.yaml', '.yml', '.toml',
        '.ini', '.cfg', '.conf', '.env', '.sql', '.r', '.lua', '.pl',
        '.docx', '.pdf',
    }
    if ext not in _ALLOWED_TEXT_EXT:
        return jsonify({"success": False, "error": f"Dateityp '{ext}' nicht unterstützt. Erlaubt: Text, Code, PDF, DOCX"}), 400

    try:
        raw_bytes = uploaded.read()
        text_content = ''

        # --- Extract text based on file type ---
        if ext == '.pdf':
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=raw_bytes, filetype='pdf')
                pages = []
                for page in doc:
                    pages.append(page.get_text())
                text_content = '\n\n'.join(pages)
                doc.close()
            except ImportError:
                # Fallback: try pdfplumber
                try:
                    import pdfplumber, io
                    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                        pages = [p.extract_text() or '' for p in pdf.pages]
                    text_content = '\n\n'.join(pages)
                except ImportError:
                    return jsonify({"success": False, "error": "PDF-Bibliothek fehlt. Installiere: pip install PyMuPDF oder pdfplumber"}), 500

        elif ext == '.docx':
            try:
                from docx import Document
                import io
                doc = Document(io.BytesIO(raw_bytes))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                text_content = '\n\n'.join(paragraphs)
            except ImportError:
                return jsonify({"success": False, "error": "python-docx fehlt. Installiere: pip install python-docx"}), 500

        elif ext == '.rtf':
            try:
                from striprtf.striprtf import rtf_to_text
                text_content = rtf_to_text(raw_bytes.decode('utf-8', errors='replace'))
            except ImportError:
                # Fallback: crude RTF stripping
                import re
                raw_str = raw_bytes.decode('utf-8', errors='replace')
                text_content = re.sub(r'[{}\\][a-z0-9]*\s?', '', raw_str)

        else:
            # Plain text / code files
            for enc in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text_content = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if not text_content:
                text_content = raw_bytes.decode('utf-8', errors='replace')

        if not text_content or len(text_content.strip()) < 20:
            return jsonify({"success": False, "error": "Datei enthält keinen verwertbaren Text"}), 400

        # --- Chunk the text ---
        CHUNK_SIZE = 2000  # chars per chunk
        CHUNK_OVERLAP = 200
        doc_title = custom_title or filename

        chunks = []
        text_clean = text_content.strip()
        if len(text_clean) <= CHUNK_SIZE:
            chunks.append(text_clean)
        else:
            pos = 0
            while pos < len(text_clean):
                end = pos + CHUNK_SIZE
                chunk = text_clean[pos:end]
                # Try to break at paragraph or sentence boundary
                if end < len(text_clean):
                    last_para = chunk.rfind('\n\n')
                    if last_para > CHUNK_SIZE * 0.5:
                        chunk = chunk[:last_para]
                        end = pos + last_para
                    else:
                        last_period = chunk.rfind('. ')
                        if last_period > CHUNK_SIZE * 0.5:
                            chunk = chunk[:last_period + 1]
                            end = pos + last_period + 1
                chunks.append(chunk.strip())
                pos = max(pos + 1, end - CHUNK_OVERLAP)

        # --- Ingest each chunk into RAG ---
        total_added = 0
        for i, chunk in enumerate(chunks):
            chunk_title = f"{doc_title} [{i+1}/{len(chunks)}]" if len(chunks) > 1 else doc_title
            added = core.rag_add(
                title=chunk_title,
                text=chunk,
                doc_type="user_rag",
                user=user,
            )
            total_added += added

        print(f"[RAG-UPLOAD] ✅ '{filename}' → {len(chunks)} Chunks, {total_added} Einträge, {len(text_clean)} Zeichen")
        return jsonify({
            "success": True,
            "filename": filename,
            "chunks": len(chunks),
            "total_chars": len(text_clean),
            "entries_added": total_added,
            "doc_type": "user_rag",
            "message": f"📄 '{filename}' erfolgreich hochgeladen: {len(chunks)} Chunks, {len(text_clean)} Zeichen ins Wissen aufgenommen.",
        })

    except Exception as e:
        print(f"[RAG-UPLOAD] ❌ Error processing '{filename}': {e}")
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": f"Fehler beim Verarbeiten: {str(e)}"}), 500


# ── User Profile API ─────────────────────────────────────────────────────────

@app.route('/api/profile', methods=['GET'])
def api_profile_get():
    """Return the current user profile."""
    from ailey_system.user_profile import load_profile
    user = request.args.get('user', 'Simon')
    profile = load_profile(user)
    return jsonify({"success": True, "profile": profile})


@app.route('/api/profile/update', methods=['POST'])
def api_profile_update():
    """Update a single profile field."""
    from ailey_system.user_profile import update_field
    data = request.get_json(silent=True) or {}
    user = data.get('user', 'Simon')
    field = data.get('field')
    value = data.get('value')
    if not field or value is None:
        return jsonify({"success": False, "message": "field and value required"}), 400
    try:
        result = update_field(field, value, user=user, updated_by="api")
        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ── Owner–Ailey Relationship API ─────────────────────────────────────────

@app.route('/api/profile/relationship', methods=['GET'])
def api_relationship_get():
    """Get the current owner–Ailey relationship."""
    from ailey_system.user_profile import get_relationship, get_relationship_levels, get_relationship_tags
    user = request.args.get('user', 'Simon')
    rel = get_relationship(user)
    return jsonify({
        "success": True,
        "relationship": rel,
        "available_levels": get_relationship_levels(),
        "available_tags": get_relationship_tags(),
    })


@app.route('/api/profile/relationship', methods=['POST'])
def api_relationship_update():
    """Update the owner–Ailey relationship.
    
    Body: { level?, tags?, add_tag?, remove_tag?, user_note?, add_note? }
    """
    from ailey_system.user_profile import update_relationship
    data = request.get_json(silent=True) or {}
    user = data.get('user', 'Simon')
    result = update_relationship(
        user=user,
        level=data.get('level'),
        tags=data.get('tags'),
        add_tag=data.get('add_tag'),
        remove_tag=data.get('remove_tag'),
        user_note=data.get('user_note'),
        add_note=data.get('add_note'),
        updated_by="user",
    )
    return jsonify(result)


@app.route('/api/diary/password', methods=['POST'])
def api_diary_set_password():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon')
    pw = data.get('password')
    if not pw:
        return jsonify({'success': False, 'message': 'password required'}), 400
    try:
        set_password(user, pw)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/diary/verify', methods=['POST'])
def api_diary_verify():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon')
    pw = data.get('password')
    ok = verify_password(user, pw) if pw else False
    return jsonify({'success': ok})


@app.route('/api/diary/save', methods=['POST'])
def api_diary_save():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon')
    pw = data.get('password')
    if not verify_password(user, pw):
        return jsonify({'success': False, 'message': 'invalid password'}), 403
    title = data.get('title') or 'Diary Entry'
    content = data.get('content') or ''
    tags = data.get('tags') or []
    private = data.get('private') if 'private' in data else True
    res = save_entry(user, title, content, tags=tags, private=private)
    # Optionally ingest into RAG for Ailey to use
    try:
        core.rag_add(title=f"diary_{res['entry']['ts']}", text=content, doc_type='diary', user=user)
        # Also push into hot RAG buffer so it's immediately available in prompts
        try:
            if not hasattr(core, '_hot_rag'):
                core._hot_rag = {}
            core._hot_rag.setdefault(user, []).append({'text': content, 'title': title, 'doc_type': 'diary', 'ts': res['entry']['ts']})
            # keep only recent 20
            core._hot_rag[user] = core._hot_rag[user][-20:]
        except Exception:
            pass
    except Exception:
        pass
    # GraphRAG auto-update: extract entities from diary content
    try:
        from ailey_system.graph_rag import get_graph_rag
        _grag = get_graph_rag()
        if _grag and content and len(content) > 30:
            _grag.add_diary_entities(content, timestamp=time.time())
    except Exception:
        pass
    return jsonify({'success': True, 'entry': res.get('entry')})


@app.route('/api/diary/list', methods=['GET'])
def api_diary_list():
    user = request.args.get('user') or 'Simon'
    # Note: listing does not require password, but read does
    items = list_entries(user)
    return jsonify({'success': True, 'count': len(items), 'entries': items})


@app.route('/api/diary/read', methods=['POST'])
def api_diary_read():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon')
    pw = data.get('password')
    entry_id = data.get('entry_id')
    if not entry_id:
        return jsonify({'success': False, 'message': 'entry_id required'}), 400
    if not verify_password(user, pw):
        return jsonify({'success': False, 'message': 'invalid password'}), 403
    e = read_entry(user, entry_id)
    if not e:
        return jsonify({'success': False, 'message': 'not found'}), 404
    return jsonify({'success': True, 'entry': e})


# --- Life Simulation State API -------------------------------------------

# ── Player Spawn Override ───────────────────────────────────────────────────
# When set, overrides the default DB spawn position for the player character.
# Saved by the RMMZ plugin when the player moves, cleared on full app restart.
# Format: {"x": int, "y": int, "dir": int, "mapId": int} or None
_player_spawn_override: dict | None = None

# ── Needs System ────────────────────────────────────────────────────────────
# Persistent needs for Ailey: hunger, thirst, tiredness, toilet, hygiene, environment
# + social (filled by chat messages, very slow decay)
# + daily_mood (Tageslaune) — derived/updated each tick, stored for persistence
# Scale: 0 = satisfied/good  100 = critical/bad (EXCEPT daily_mood + social: 0=bad 100=good)
_NEEDS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'life_sim_needs.json')
_NEEDS_LOCK = threading.Lock()

# ── Mood-Weights (Character Mood Feedback-Loop) ───────────────────────────
_MOOD_WEIGHTS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'mood_weights.json')
_MOOD_WEIGHTS_LOCK = threading.Lock()
_VALID_CHAR_MOODS = {"creative", "playful", "curious", "happy", "melancholic", "tired"}

def _load_mood_weights() -> dict:
    if os.path.exists(_MOOD_WEIGHTS_JSON):
        try:
            with open(_MOOD_WEIGHTS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"weights": {m: 0 for m in _VALID_CHAR_MOODS}, "current_char_mood": "neutral"}

def _save_mood_weights(data: dict):
    with _MOOD_WEIGHTS_LOCK:
        with open(_MOOD_WEIGHTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def _apply_mood_weight(mood: str, delta: int):
    """Apply a weight delta to a character mood and recompute current_char_mood."""
    if mood not in _VALID_CHAR_MOODS:
        return
    with _MOOD_WEIGHTS_LOCK:
        data = _load_mood_weights()
        weights = data.get("weights", {m: 0 for m in _VALID_CHAR_MOODS})
        # Apply delta (capped)
        weights[mood] = max(-100, min(100, weights.get(mood, 0) + delta))
        # Gentle decay: other moods drift toward 0
        for m in _VALID_CHAR_MOODS:
            if m != mood and weights.get(m, 0) != 0:
                weights[m] = round(weights[m] * 0.97, 2)
        # Determine dominant mood (highest positive weight)
        pos_moods = {m: v for m, v in weights.items() if v > 5}
        if pos_moods:
            dominant = max(pos_moods, key=pos_moods.get)
        else:
            dominant = "neutral"
        data["weights"] = weights
        data["current_char_mood"] = dominant
        data["last_updated"] = datetime.now().isoformat()
        with open(_MOOD_WEIGHTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Also write current_char_mood into life_sim_needs.json for prompt injection
        try:
            nd = _load_needs()
            nd["current_char_mood"] = dominant
            with _NEEDS_LOCK:
                with open(_NEEDS_JSON, 'w', encoding='utf-8') as nf:
                    json.dump(nd, nf, ensure_ascii=False, indent=2)
        except Exception:
            pass

def parse_and_apply_mood_tags(response_text: str) -> str:
    """Parse hidden [MOOD±type:N] and [TAGESLAUNE±N] tags from AI response.
    Applies their effects and strips them from the displayed text.
    Only active when LifeSim is enabled."""
    import re as _re
    # Check if LifeSim is on
    try:
        if os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, 'r') as f:
                if not json.load(f).get("life_sim_enabled", True):
                    return response_text  # Gate: LifeSim off → no tags processed
    except Exception:
        pass

    # Apply [MOOD+creative:3] or [MOOD-melancholic:2]
    for m in _re.finditer(r'\[MOOD([+-])(\w+):(\d+)\]', response_text):
        sign, mood, value = m.group(1), m.group(2).lower(), min(int(m.group(3)), 5)
        delta = value if sign == '+' else -value
        _apply_mood_weight(mood, delta)

    # Apply [TAGESLAUNE+2] or [TAGESLAUNE-1]
    for m in _re.finditer(r'\[TAGESLAUNE([+-])(\d+)\]', response_text):
        sign, value = m.group(1), min(int(m.group(2)), 3)
        delta = value if sign == '+' else -value
        try:
            nd = _load_needs()
            nd["daily_mood"] = max(0, min(100, nd.get("daily_mood", 75) + delta))
            with _NEEDS_LOCK:
                with open(_NEEDS_JSON, 'w', encoding='utf-8') as nf:
                    json.dump(nd, nf, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Strip all hidden tags from displayed text
    clean = _re.sub(r'\[MOOD[^\]]+\]', '', response_text)
    clean = _re.sub(r'\[TAGESLAUNE[^\]]+\]', '', clean)
    return clean.strip()
_NEEDS_DEFAULTS = {
    "hunger": 10, "thirst": 10, "tiredness": 0, "toilet": 5, "hygiene": 5, "environment": 10,
    "social": 80,       # 0–100, higher = more social contact (inverted: 0=lonely)
    "daily_mood": 75,   # 0–100, Tageslaune (0=terrible, 100=great)
}
# Increment rates per real minute for "bad" needs (hunger, thirst, etc.)
#   thirst  → critical (~75 %) after ~2.5 h
#   toilet  → critical after ~3 h
#   hunger  → critical after ~4 h
#   tiredness → critical after ~8 h
#   hygiene → critical after ~12 h
#   environment → critical after ~18 h
#   social  → lonely (~25 %) after ~14 h (very slow)
_NEEDS_RATES = {"hunger": 0.27, "thirst": 0.45, "tiredness": 0.16, "toilet": 0.39, "hygiene": 0.10, "environment": 0.06}
_SOCIAL_DECAY_RATE = 0.09   # social points lost per real minute (0→100% lonely in ~18h)
# daily_mood drain rates per minute per triggering condition
_MOOD_DRAIN_BASE = 0.015        # base drain when any need ≥ 75 (critical) (vorher 0.04)
_MOOD_DRAIN_HYGIENE_0 = 0.05    # extra drain when hygiene == 0 (vorher 0.12)
_MOOD_DRAIN_ENV_FACTOR = 0.0007 # multiplied by environment value → extra drain (vorher 0.002)
_MOOD_RESTORE_RATE = 0.25       # natural restore per minute when all needs are ok (≤30) (vorher 0.08)
# Below this daily_mood, sympathy (relationship) slowly decreases
_MOOD_SYMPATHY_THRESHOLD = 50
_MOOD_SYMPATHY_DRAIN_PER_MIN = 0.05  # max drain at mood==0, scales linearly
# Leisure activity scheduler (independent LifeSim activities)
_LEISURE_ACTIVITIES = {
    "music_making":   {"weight": 3, "mood_boost": 0.07, "min_mood": 50},  # Musik = große Freude
    "diary_writing":  {"weight": 4, "mood_boost": 0.03, "min_mood": 30},  # Tagebuch immer okay
    "fishing":        {"weight": 2, "mood_boost": 0.05, "min_mood": 45},  # Entspannung am Teich
    "flower_picking": {"weight": 2, "mood_boost": 0.05, "min_mood": 45},  # Draußen, Natur
    "gardening":      {"weight": 2, "mood_boost": 0.04, "min_mood": 40},  # Leichte Arbeit draußen
    "outdoor_stroll": {"weight": 3, "mood_boost": 0.05, "min_mood": 45},  # Frische Luft
}
_LEISURE_TRIGGER_CHANCE_PER_MIN = 0.12   # ~12% Chance/Minute wenn Needs ok + Mood gut
_LEISURE_MIN_NEEDS_OK = 40               # Alle Needs unter diesem Wert → Freizeit möglich
_LEISURE_MIN_MOOD = 45                   # Mindest-Tageslaune für Freizeit
_LEISURE_DURATION_RANGE = (20, 50)       # Dauer in Minuten (min, max)
# Critical threshold — Ailey must address the need
_NEEDS_CRITICAL = 75
# Resolution: need → sequence of (location, walk_seconds, action_seconds)
# walk_seconds = estimated time for Ailey to walk there (sprite: standard)
# action_seconds = time spent performing the action (sprite: activity)
_NEEDS_RESOLUTION = {
    "hunger":      [("kitchen", 20, 25), ("table", 15, 40)],  # walk to fridge → cook → walk to table → eat
    "thirst":      [("kitchen", 20, 15)],                       # walk to kitchen → drink
    "tiredness":   [("bed", 25, 120)],                          # walk to bed → sleep
    "toilet":      [("toilet", 20, 35)],                        # walk to toilet → use it
    "hygiene":     [("bath", 20, 45)],                          # walk to bath → bathe
    "environment": [("kitchen", 18, 30), ("couch", 15, 20)],   # walk → clean kitchen → walk → tidy couch area
}

# German labels for walking and performing per need
_NEEDS_WALK_LABELS = {
    "hunger":      "Weg zur Küche 🍳",
    "thirst":      "Weg zum Kühlschrank 💧",
    "tiredness":   "Weg zum Bett 😴",
    "toilet":      "Weg zur Toilette 🚽",
    "hygiene":     "Weg zum Bad 🛁",
    "environment": "Weg zum Putzen 🧹",
}
_NEEDS_ACTION_LABELS = {
    "hunger":      {0: "Kocht in der Küche 🍳", 1: "Isst am Tisch 🍽️"},
    "thirst":      {0: "Trinkt etwas 💧"},
    "tiredness":   {0: "Schläft 💤"},
    "toilet":      {0: "Auf der Toilette 🚽"},
    "hygiene":     {0: "Badet 🛁"},
    "environment": {0: "Putzt die Küche 🧹", 1: "Räumt auf 🧹"},
}

def _load_needs() -> dict:
    if os.path.exists(_NEEDS_JSON):
        try:
            with open(_NEEDS_JSON, 'r') as f:
                data = json.load(f)
                # Fill in any new keys that didn't exist before
                for k, v in _NEEDS_DEFAULTS.items():
                    if k not in data:
                        data[k] = v
                # Tick: increment needs based on elapsed real time
                # Skip when paused OR when Code/Author Mode active (Needs einfrieren)
                _is_code_mode = globals().get('_code_mode_active', False)
                _is_author_mode = getattr(app, '_author_mode_active', False)
                _needs_frozen = _is_code_mode or _is_author_mode
                if not getattr(app, '_life_sim_paused', False) and not _needs_frozen:
                    elapsed_min = (time.time() - data.get("_ts", time.time())) / 60.0
                    if elapsed_min > 0.5:
                        # ── Standard need ticks (hunger/thirst/etc.) ──
                        for k, rate in _NEEDS_RATES.items():
                            data[k] = min(100, data.get(k, _NEEDS_DEFAULTS[k]) + rate * elapsed_min)

                        # ── Social decay (inverted: social goes DOWN over time) ──
                        data["social"] = max(0, data.get("social", 80) - _SOCIAL_DECAY_RATE * elapsed_min)

                        # ── Toilet accident: toilet hits 0 → instant penalty ──
                        if data.get("toilet", 0) >= 100 and not data.get("_toilet_accident_applied"):
                            data["hygiene"]     = min(100, data.get("hygiene", 0) + 50)
                            data["environment"] = min(100, data.get("environment", 0) + 25)
                            data["daily_mood"]  = max(0,   data.get("daily_mood", 75) - 15)
                            data["_toilet_accident_applied"] = True
                        elif data.get("toilet", 0) < 95:
                            data["_toilet_accident_applied"] = False

                        # ── Food/drink crisis → tiredness accelerates ──
                        hunger_val  = data.get("hunger", 0)
                        thirst_val  = data.get("thirst", 0)
                        if hunger_val >= 100 or thirst_val >= 100:
                            # Tiredness rises much faster when starving/parched
                            data["tiredness"] = min(100, data.get("tiredness", 0) + 0.40 * elapsed_min)

                        # ── Tageslaune (daily_mood) tick ──
                        mood = data.get("daily_mood", 75)
                        # Count how many needs are critical
                        critical_needs = sum(1 for k in _NEEDS_RATES if data.get(k, 0) >= _NEEDS_CRITICAL)
                        # Base drain per critical need
                        mood_drain = critical_needs * _MOOD_DRAIN_BASE * elapsed_min
                        # Extra drain if hygiene is very low
                        hygiene_val = data.get("hygiene", 0)
                        if hygiene_val >= 100:
                            mood_drain += _MOOD_DRAIN_HYGIENE_0 * elapsed_min
                        elif hygiene_val >= 75:
                            mood_drain += (_MOOD_DRAIN_HYGIENE_0 * 0.5) * elapsed_min
                        # Extra drain from environment (only when high, not at low values)
                        env_val = data.get("environment", 0)
                        if env_val >= 40:
                            mood_drain += _MOOD_DRAIN_ENV_FACTOR * env_val * elapsed_min
                        # Natural restore — generous: kicks in whenever no critical needs
                        # (social is separate and does NOT block mood recovery)
                        if critical_needs == 0:
                            # Base restore: proportional to how good needs are
                            # Average of all needs (lower = better). 0=perfect, 100=terrible
                            _avg_needs = sum(data.get(k, 0) for k in _NEEDS_RATES) / len(_NEEDS_RATES)
                            if _avg_needs <= 50:
                                # Needs are generally ok → restore mood
                                # Speed: full rate when all perfect (avg=0), half rate at avg=50
                                _needs_factor = 1.0 - (_avg_needs / 100.0)  # 1.0 at avg=0, 0.5 at avg=50
                                mood += _MOOD_RESTORE_RATE * _needs_factor * elapsed_min
                            # Self-reinforcing: mood > 50 = additional restore (on top of above)
                            if mood > 50:
                                _above50_factor = (mood - 50) / 50.0
                                mood += (_MOOD_RESTORE_RATE * 0.5) * _above50_factor * elapsed_min
                        mood = max(0, min(100, mood - mood_drain))
                        # Trend berechnen (für Frontend-Anzeige)
                        _mood_prev = data.get("_mood_prev", mood)
                        _mood_trend = mood - _mood_prev
                        data["_mood_prev"]  = mood
                        data["_mood_trend"] = _mood_trend  # positiv = steigt, negativ = fällt
                        data["daily_mood"] = mood

                        # ── Leisure Activity Scheduler (unabhängig vom IdleThinker) ──
                        # Wenn Ailey Freizeit hat (alle Needs ok, Mood gut) → plant eigenständig
                        # eine Freizeit-Aktivität (Angeln, Musik, Spazieren...) für ~20-50 Min.
                        import random as _rand_leisure
                        _leis_act   = data.get("_leisure_activity")
                        _leis_until = data.get("_leisure_until", 0.0)
                        _now_ts     = time.time()
                        if _now_ts > _leis_until:
                            # Keine laufende Freizeit-Aktivität
                            _all_ok  = all(data.get(k, 0) < _LEISURE_MIN_NEEDS_OK for k in _NEEDS_RATES)
                            _resolv  = data.get("_resolving")  # needs-resolution läuft → keine Freizeit
                            if _all_ok and not _resolv and mood >= _LEISURE_MIN_MOOD:
                                if _rand_leisure.random() < _LEISURE_TRIGGER_CHANCE_PER_MIN * elapsed_min:
                                    # Wähle passende Aktivität (Gewicht × Mood-Check)
                                    _candidates = [
                                        (k, v["weight"])
                                        for k, v in _LEISURE_ACTIVITIES.items()
                                        if mood >= v["min_mood"]
                                    ]
                                    if _candidates:
                                        _acts, _wts = zip(*_candidates)
                                        _chosen = _rand_leisure.choices(_acts, weights=_wts, k=1)[0]
                                        _dur    = _rand_leisure.randint(*_LEISURE_DURATION_RANGE) * 60
                                        data["_leisure_activity"] = _chosen
                                        data["_leisure_until"]    = _now_ts + _dur
                                        _leis_act   = _chosen
                                        _leis_until = _now_ts + _dur
                            else:
                                data["_leisure_activity"] = None
                        # Mood-Boost während aktiver Freizeit
                        if _leis_act and _now_ts <= _leis_until:
                            _boost = _LEISURE_ACTIVITIES.get(_leis_act, {}).get("mood_boost", 0.03)
                            data["daily_mood"] = min(100, data["daily_mood"] + _boost * elapsed_min)

                        # ── Mood < 50 → sympathy slowly drains ──
                        if mood < _MOOD_SYMPATHY_THRESHOLD:
                            mood_factor = 1.0 - (mood / _MOOD_SYMPATHY_THRESHOLD)  # 0→1 as mood→0
                            drain = _MOOD_SYMPATHY_DRAIN_PER_MIN * mood_factor * elapsed_min
                            if drain > 0:
                                try:
                                    _adjust_sympathy("Simon", -drain, f"Schlechte Tageslaune ({mood:.0f}%)")
                                except Exception:
                                    pass

                        data["_ts"] = time.time()
                        _save_needs(data)
                else:
                    # When paused / Code Mode / Author Mode, just update timestamp so no huge tick after resume
                    data["_ts"] = time.time()
                return data
        except Exception:
            pass
    data = {**_NEEDS_DEFAULTS, "_ts": time.time(), "_resolving": None, "_resolve_until": 0}
    _save_needs(data)
    return data

def _save_needs(data: dict):
    data["_ts"] = time.time()
    try:
        with open(_NEEDS_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Needs] save error: {e}")

def _reset_tiredness():
    """Called on startup — Ailey 'slept' while offline."""
    with _NEEDS_LOCK:
        data = _load_needs()
        data["tiredness"] = 0
        _save_needs(data)
    print("[Needs] ☀️ Tiredness reset (offline sleep)")

def _resolve_need(need_name: str) -> dict:
    """Start resolving a need — does NOT reduce the need value yet.
    Relief is applied only when the resolution sequence fully completes
    (checked in _check_need_resolution_complete).
    For hunger/thirst: checks storage first — consumes an item if available.
    If storage empty, Ailey still goes through the motion but with reduced relief.
    """
    storage_msg = ""
    relief = 70  # default relief amount
    # For hunger/thirst, try to consume from storage
    if need_name in ("hunger", "thirst"):
        if _ailey_can_self_serve(need_name):
            storage_msg = _ailey_self_serve(need_name)
        else:
            # No supplies — Ailey can only partially satisfy the need
            relief = 20  # much less effective without actual food/drink
            storage_msg = f"⚠️ Vorräte leer! Ailey findet nichts im Kühlschrank..."

    with _NEEDS_LOCK:
        data = _load_needs()
        old_val = data.get(need_name, 0)
        # Do NOT reduce need yet — store pending relief for later
        data["_resolving"] = need_name
        data["_pending_relief"] = relief
        seq = _NEEDS_RESOLUTION.get(need_name, [])
        total_secs = sum(w + a for _, w, a in seq) if seq else 30
        data["_resolve_started"] = time.time()
        data["_resolve_until"] = time.time() + total_secs
        _save_needs(data)
    return {
        "need": need_name,
        "old_value": round(old_val, 1),
        "new_value": round(old_val, 1),  # unchanged — relief applied on completion
        "sequence": [{"location": loc, "walk": walk, "action": dur} for loc, walk, dur in seq],
        "storage_msg": storage_msg,
    }

def _check_need_resolution_complete(needs_data: dict) -> dict:
    """Check if an active resolution has completed. If so, apply the relief now."""
    resolving = needs_data.get("_resolving")
    resolve_until = needs_data.get("_resolve_until", 0)
    if resolving and time.time() >= resolve_until and resolve_until > 0:
        # Resolution complete — apply the deferred relief
        pending_relief = needs_data.get("_pending_relief", 70)
        if resolving in _NEEDS_DEFAULTS:
            old = needs_data.get(resolving, 0)
            needs_data[resolving] = max(0, old - pending_relief)
        needs_data["_resolving"] = None
        needs_data["_resolve_until"] = 0
        needs_data["_resolve_started"] = 0
        needs_data["_pending_relief"] = 0
        _save_needs(needs_data)
    return needs_data

def _get_need_resolution_phase(needs_data: dict) -> dict:
    """Determine the current phase of an active need resolution.
    Returns: {"phase": "walking"|"performing"|None, "step_index": int,
              "step_location": str, "label": str, "need": str}
    """
    resolving = needs_data.get("_resolving")
    resolve_started = needs_data.get("_resolve_started", 0)
    resolve_until = needs_data.get("_resolve_until", 0)

    if not resolving or time.time() >= resolve_until:
        return {"phase": None, "step_index": 0, "step_location": None, "label": None, "need": None}

    seq = _NEEDS_RESOLUTION.get(resolving, [])
    if not seq:
        return {"phase": "performing", "step_index": 0, "step_location": "couch",
                "label": "Beschäftigt…", "need": resolving}

    elapsed = time.time() - resolve_started
    running = 0
    for i, (loc, walk_dur, action_dur) in enumerate(seq):
        # Walking phase for this step
        if elapsed < running + walk_dur:
            walk_labels = _NEEDS_WALK_LABELS.get(resolving, f"Weg zum Ziel")
            # For multi-step: adjust label for later steps
            _loc_names = {"kitchen": "Küche", "table": "Tisch", "bed": "Bett",
                          "bath": "Bad", "toilet": "Toilette", "couch": "Wohnzimmer",
                          "pond": "Teich", "desk": "Schreibtisch"}
            if i > 0:
                walk_labels = f"Weg zum {_loc_names.get(loc, loc)} 🚶"
            return {"phase": "walking", "step_index": i, "step_location": loc,
                    "label": walk_labels, "need": resolving}
        running += walk_dur
        # Performing phase for this step
        if elapsed < running + action_dur:
            action_labels = _NEEDS_ACTION_LABELS.get(resolving, {})
            label = action_labels.get(i, f"{resolving.capitalize()}…")
            return {"phase": "performing", "step_index": i, "step_location": loc,
                    "label": label, "need": resolving}
        running += action_dur

    # Past all steps — should be finalized soon
    return {"phase": "performing", "step_index": len(seq) - 1,
            "step_location": seq[-1][0], "label": "Fast fertig…", "need": resolving}

def _get_most_critical_need() -> tuple:
    """Return (need_name, value) of the most critical need, or (None, 0)."""
    data = _load_needs()
    # Don't interrupt if currently resolving
    if data.get("_resolving") and time.time() < data.get("_resolve_until", 0):
        return (None, 0)
    worst = (None, 0)
    for k in _NEEDS_DEFAULTS:
        v = data.get(k, 0)
        if v > worst[1]:
            worst = (k, v)
    return worst if worst[1] >= _NEEDS_CRITICAL else (None, 0)

# Reset tiredness on startup (she slept while offline)
_reset_tiredness()

# ── Autonomous Needs Self-Care Background Thread ────────────────────────────
# Periodically checks Ailey's needs and auto-resolves critical ones, even when
# the RMMZ LifeSim plugin is NOT active. This ensures Ailey takes care of
# herself (eating, drinking, sleeping, etc.) without requiring the pixel world.
_NEEDS_AUTOCARE_INTERVAL = 60  # check every 60 seconds

def _needs_autocare_loop():
    """Background thread: auto-resolve critical needs + apply completed resolutions."""
    time.sleep(30)  # initial delay — let other systems start
    while True:
        try:
            # Check if LifeSim is enabled at all
            _ls_on = True
            try:
                if os.path.exists(_SETTINGS_FILE):
                    with open(_SETTINGS_FILE, 'r') as f:
                        _ls_on = json.load(f).get("life_sim_enabled", True)
            except Exception:
                pass
            if not _ls_on:
                time.sleep(_NEEDS_AUTOCARE_INTERVAL)
                continue

            # Tick needs (triggers decay via _load_needs)
            needs_data = _load_needs()
            # Check and apply completed resolutions
            needs_data = _check_need_resolution_complete(needs_data)

            # If not already resolving, check for critical needs and auto-resolve
            resolving = needs_data.get("_resolving")
            resolve_until = needs_data.get("_resolve_until", 0)
            if resolving and time.time() < resolve_until:
                # Already resolving — let it finish
                pass
            else:
                critical_need, critical_val = _get_most_critical_need()
                if critical_need:
                    _resolve_need(critical_need)
                    print(f"[Needs/AutoCare] 🏃 Auto-resolving: {critical_need} ({critical_val:.0f}%)")
        except Exception as e:
            print(f"[Needs/AutoCare] Error: {e}")
        time.sleep(_NEEDS_AUTOCARE_INTERVAL)

threading.Thread(target=_needs_autocare_loop, daemon=True, name="NeedsAutoCare").start()
print("[Needs] 🤖 Autonomous self-care thread started")

# ── Sympathie System (Global, per-person) ───────────────────────────────────
_SYMPATHY_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'sympathy_scores.json')

def _load_sympathy() -> dict:
    if os.path.exists(_SYMPATHY_JSON):
        try:
            with open(_SYMPATHY_JSON, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"Simon": 50}  # Default: Simon starts at 50/100

def _save_sympathy(data: dict):
    try:
        with open(_SYMPATHY_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Sympathy] save error: {e}")

def _adjust_sympathy(person: str, delta: float, reason: str = ""):
    """Adjust sympathy score for a person. Clamped 0-100."""
    data = _load_sympathy()
    old = data.get(person, 30)  # unknown people start at 30
    new = max(0, min(100, old + delta))
    data[person] = round(new, 1)
    data[f"_last_{person}"] = {"delta": delta, "reason": reason, "ts": time.time()}
    _save_sympathy(data)
    return old, new

def _get_sympathy(person: str) -> float:
    data = _load_sympathy()
    return data.get(person, 30)

def _get_sympathy_label(score: float) -> str:
    if score >= 90: return "💕 Seelenverwandt"
    if score >= 75: return "❤️ Sehr nah"
    if score >= 60: return "😊 Freundlich"
    if score >= 40: return "🙂 Neutral"
    if score >= 25: return "😐 Distanziert"
    if score >= 10: return "😒 Genervt"
    return "💔 Abgeneigt"

# ── Portal User Trust Heuristic ─────────────────────────────────────────────
def _heuristic_trust_update(person: str, message: str, reply: str = "",
                            is_portal: bool = False):
    """Heuristic trust scoring — adjusts sympathy up/down based on behavior.

    Positive signals: longer messages (effort), compliments, repeated engagement,
                      positive sentiment, questions (curiosity).
    Negative signals: insults, trolling, spam-like behavior, very short trash.
    Decay: inactive users slowly drift back toward 30 (neutral for strangers).
    """
    import re
    if person == "Simon":
        return  # Simon uses the richer life-sim system, skip heuristic

    delta = 0.0
    reasons = []
    lower = message.lower().strip()

    # ── Positive signals ──
    msg_len = len(message.strip())
    if msg_len > 200:
        delta += 0.8
        reasons.append("ausführlich")
    elif msg_len > 80:
        delta += 0.4
        reasons.append("engagiert")
    elif msg_len > 20:
        delta += 0.15

    # Questions show curiosity / genuine interest
    if re.search(r'\?', message):
        delta += 0.2
        reasons.append("Frage")

    # Compliments / positive words
    positive_pats = [
        r'cool', r'toll', r'geil', r'super', r'danke', r'liebe?\b',
        r'amazing', r'awesome', r'great', r'nice', r'beautiful',
        r'hübsch', r'klug', r'talentiert', r'besonder',
        r'fan\b', r'beeindruckend', r'respect', r'süß',
    ]
    pos_hits = sum(1 for p in positive_pats if re.search(p, lower))
    if pos_hits >= 2:
        delta += 1.0
        reasons.append("Kompliment")
    elif pos_hits == 1:
        delta += 0.4

    # Returning user engagement (just chatting = slow trust build)
    delta += 0.1  # baseline per-message micro-boost

    # ── Negative signals ──
    negative_pats = [
        r'hurensohn', r'schlampe', r'nutte', r'fick\s*dich', r'arschloch',
        r'bitch', r'slut', r'whore', r'fuck\s*you', r'idiot',
        r'dumm', r'hässlich', r'wertlos', r'müll', r'trash',
        r'stfu', r'kys', r'kill\s*yourself',
    ]
    neg_hits = sum(1 for p in negative_pats if re.search(p, lower))
    if neg_hits >= 2:
        delta -= 5.0
        reasons.append("Beleidigung-schwer")
    elif neg_hits == 1:
        delta -= 2.0
        reasons.append("Beleidigung")

    # Spam detection: very short + no substance
    if msg_len < 5 and not re.search(r'[a-zA-ZäöüßÄÖÜ]{2,}', message):
        delta -= 0.5
        reasons.append("Spam")

    # All-caps yelling
    if len(message) > 10 and message == message.upper():
        delta -= 0.3
        reasons.append("Caps-Spam")

    # Apply if any meaningful delta
    if abs(delta) >= 0.05:
        reason_str = ", ".join(reasons) if reasons else "chat"
        _adjust_sympathy(person, delta, f"heuristic: {reason_str}")

# ── Life Sim Behavior ───────────────────────────────────────────────────────

def _get_life_sim_behavior(idle_type, mood, hour):
    """Translate idle thinker state to life-sim world position & sprite.

    Weather- and time-of-day-aware: Ailey prefers outdoor in good weather,
    stays inside during rain/storm/night/extreme temps, and adjusts her
    activity locations accordingly.
    """
    INDOOR = {
        "desk":      {"x": 10, "y": 14, "dir": "up"},     # Computer(10,13) — Blick oben
        "bed":       {"x": 20, "y": 5,  "dir": "left"},   # Bett — eins rechts neben dem Bett, Blick links
        "couch":     {"x": 15, "y": 7,  "dir": "up"},     # TV(15,7) — 1 hoch, Blick oben zum Fernseher
        "kitchen":   {"x": 3,  "y": 6,  "dir": "up"},     # Herd(3,6) — 1 hoch, Blick oben
        "bookshelf": {"x": 4,  "y": 14, "dir": "up"},     # Bücherregal(4,13) — Blick oben
        "hamster":   {"x": 8,  "y": 7,  "dir": "up"},     # Hamster(8,6) — Blick oben
        "table":     {"x": 1,  "y": 14, "dir": "down"},   # Esstisch — 1 hoch + 2 links, Blick unten
        "bath":      {"x": 17, "y": 3,  "dir": "right"},  # Badewanne — 1 hoch + 2 rechts, Blick rechts
        "toilet":    {"x": 11, "y": 3,  "dir": "down"},   # Klo — 2 hoch, Blick unten
    }
    OUTDOOR = {
        "garden":   {"x": 22, "y": 18, "dir": "down"},
        "flowers":  {"x": 16, "y": 22, "dir": "down"},
        "pond":     {"x": 30, "y": 23, "dir": "left"},
        "bench":    {"x": 20, "y": 25, "dir": "down"},
        "fountain": {"x": 25, "y": 30, "dir": "down"},
    }

    # ── Fetch weather for decision-making ──
    weather = _fetch_real_weather()
    w_type = weather.get("game_weather", "clear")
    temp = weather.get("temperature", 15)
    windspeed = weather.get("windspeed", 5)

    # Weather score: how suitable is it for being outside?
    # 1.0 = perfect outdoor weather, 0.0 = absolutely stay inside
    _w_scores = {"clear": 1.0, "cloudy": 0.7, "fog": 0.3, "drizzle": 0.2, "rain": 0.05, "snow": 0.1, "storm": 0.0}
    outdoor_score = _w_scores.get(w_type, 0.5)

    # Temperature penalty: too cold or too hot → prefer indoor
    if temp < 0:
        outdoor_score *= 0.1
    elif temp < 5:
        outdoor_score *= 0.4
    elif temp < 10:
        outdoor_score *= 0.7
    elif temp > 35:
        outdoor_score *= 0.2
    elif temp > 30:
        outdoor_score *= 0.6

    # Wind penalty: very windy → less fun outside
    if windspeed > 40:
        outdoor_score *= 0.3
    elif windspeed > 25:
        outdoor_score *= 0.6

    # Time-of-day modifier: early/late → prefer indoor
    if 6 <= hour < 8:
        outdoor_score *= 0.3  # waking up, coffee
    elif 8 <= hour < 10:
        outdoor_score *= 0.7  # morning, okay
    elif 10 <= hour < 16:
        outdoor_score *= 1.0  # prime outdoor time
    elif 16 <= hour < 19:
        outdoor_score *= 0.8  # afternoon/early evening
    elif 19 <= hour < 21:
        outdoor_score *= 0.4  # winding down
    elif 21 <= hour < 23:
        outdoor_score *= 0.15 # late evening, mostly inside

    # Weather- and time-aware behavior table
    # Activities that CAN be outdoors in good weather get an outdoor variant
    _outdoor_ok = outdoor_score >= 0.5  # good enough to be outside
    _outdoor_great = outdoor_score >= 0.75  # really nice outside

    BEHAVIOR = {
        # Activities that are always indoor
        "sleeping":             {"map": "indoor",  "loc": "bed",       "action": 1, "sprite": "sleeping"},
        "napping":              {"map": "indoor",  "loc": "bed",       "action": 1, "sprite": "sleeping"},
        "eating":               {"map": "indoor",  "loc": "table",     "action": 0, "sprite": "eating"},
        "cooking":              {"map": "indoor",  "loc": "kitchen",   "action": 0, "sprite": "cooking"},
        "using_toilet":         {"map": "indoor",  "loc": "toilet",    "action": 0, "sprite": "using_toilet"},
        "bathing":              {"map": "indoor",  "loc": "bath",      "action": 0, "sprite": "bathing"},
        "cleaning":             {"map": "indoor",  "loc": "kitchen",   "action": 0, "sprite": "cleaning"},
        "email_check":          {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "email_check"},
        "research":             {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "research"},
        "goal_planning":        {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "goal_planning"},
        "creative_art":         {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "creative_art"},
        "creative_image":       {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "creative_image"},
        "proactive_message":    {"map": "indoor",  "loc": "desk",      "action": 0, "sprite": "proactive_message"},

        # Activities that move outdoor in nice weather
        "introspection":        {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "garden" if _outdoor_ok else "couch",
                                 "action": 0, "sprite": "introspection"},
        "free_thought":         {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "bench" if _outdoor_ok else "couch",
                                 "action": 0, "sprite": "free_thought"},
        "reflection":           {"map": "outdoor" if _outdoor_great else "indoor",
                                 "loc": "bench" if _outdoor_great else "desk",
                                 "action": 0, "sprite": "reflection"},
        # Songs: always guitar sprite regardless of weather
        "creative_song":        {"map": "outdoor" if _outdoor_great else "indoor",
                                 "loc": "garden" if _outdoor_great else "couch",
                                 "action": 0, "sprite": "creative_song"},
        # Diary/memory: always at desk with diary sprite (writing)
        "memory_consolidation": {"map": "indoor",  "loc": "desk", "action": 0, "sprite": "memory_consolidation"},
        # Nightly summary: consolidation at desk (night mode)
        "nightly_summary":      {"map": "indoor",  "loc": "desk", "action": 0, "sprite": "memory_consolidation"},
        # Email initiative: same as email_check (desk)
        "email_initiative":     {"map": "indoor",  "loc": "desk", "action": 0, "sprite": "email_initiative"},
        # Glossary cleanup: quiet desk work
        "glossary_cleanup":     {"map": "indoor",  "loc": "desk", "action": 0, "sprite": "glossary_cleanup"},
        # Drinking: indoor from kitchen when weather is bad
        "drinking":             {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "pond" if _outdoor_ok else "kitchen",
                                 "action": 0, "sprite": "drinking"},
        # ── Neue Aktivitäten ─────────────────────────────────────────────
        # Musik machen: Gitarre auf Couch/Garten
        "music_making":         {"map": "outdoor" if _outdoor_great else "indoor",
                                 "loc": "garden" if _outdoor_great else "couch",
                                 "action": 0, "sprite": "music_making"},
        # Tagebuch schreiben: immer am Schreibtisch
        "diary_writing":        {"map": "indoor",  "loc": "desk", "action": 0, "sprite": "diary_writing"},
        # Outdoor-Aktivitäten (nur bei gutem Wetter, sonst Fallback indoor)
        "fishing":              {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "pond"    if _outdoor_ok else "couch",
                                 "action": 0, "sprite": "fishing"},
        "flower_picking":       {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "flowers" if _outdoor_ok else "bookshelf",
                                 "action": 0, "sprite": "flower_picking"},
        "gardening":            {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "garden"  if _outdoor_ok else "hamster",
                                 "action": 0, "sprite": "gardening"},
        "outdoor_stroll":       {"map": "outdoor" if _outdoor_ok else "indoor",
                                 "loc": "fountain" if _outdoor_ok else "couch",
                                 "action": 0, "sprite": "outdoor_stroll"},
    }

    # Night override (23:00 – 06:00)
    if hour >= 23 or hour < 6:
        b = BEHAVIOR["sleeping"]
    else:
        # Default idle: rotate across multiple locations so Ailey doesn't always sit on the couch
        if idle_type not in BEHAVIOR:
            import hashlib as _hlib
            _idle_locs = [
                {"map": "indoor", "loc": "couch",     "action": 0, "sprite": "stand"},
                {"map": "indoor", "loc": "desk",      "action": 0, "sprite": "stand"},
                {"map": "indoor", "loc": "hamster",   "action": 0, "sprite": "stand"},
                {"map": "indoor", "loc": "bookshelf", "action": 0, "sprite": "stand"},
                {"map": "indoor", "loc": "kitchen",   "action": 0, "sprite": "stand"},
            ]
            # Deterministic per 15-minute window so she doesn't flicker
            _idle_seed = _hlib.md5(f"idle-{datetime.now().strftime('%Y%m%d%H')}-{datetime.now().minute // 15}".encode()).hexdigest()
            _idle_idx = int(_idle_seed[:4], 16) % len(_idle_locs)
            b = _idle_locs[_idle_idx]
        else:
            b = BEHAVIOR[idle_type]

        # ── Random outdoor strolls — even during "desk" activities ──
        # On really nice weather, Ailey occasionally takes a break and goes outside.
        # Uses deterministic minute-windows so she doesn't flicker between maps.
        import hashlib
        _always_indoor = {"sleeping", "napping", "eating", "cooking", "using_toilet",
                          "bathing", "cleaning",
                          "email_check", "research", "goal_planning", "creative_art",
                          "creative_image", "proactive_message",
                          "diary_writing", "memory_consolidation", "email_initiative",
                          "glossary_cleanup", "nightly_summary"}
        # Explizit-outdoor: nie erzwungen nach draußen schieben (haben eigene Outdoor-Logik)
        _explicit_outdoor = {"fishing", "flower_picking", "gardening", "outdoor_stroll",
                             "music_making", "creative_song"}
        if b["map"] == "indoor" and idle_type not in _always_indoor and _outdoor_great:
            # Deterministic "fresh air break" based on current hour
            _roam_seed = hashlib.md5(f"roam-{datetime.now().strftime('%Y%m%d%H')}".encode()).hexdigest()
            _roam_start = int(_roam_seed[:2], 16) % 45
            _roam_dur = 12 + int(_roam_seed[2:4], 16) % 8  # 12-19 min
            _minute = datetime.now().minute
            _roaming = _roam_start <= _minute < _roam_start + _roam_dur
            _roam_hour = int(_roam_seed[4:6], 16) < 102  # ~40%
            if _roaming and _roam_hour:
                _outdoor_spots = ["garden", "flowers", "bench", "fountain"]
                _spot_idx = int(_roam_seed[6:8], 16) % len(_outdoor_spots)
                b = {"map": "outdoor", "loc": _outdoor_spots[_spot_idx], "action": 0, "sprite": "walk"}

    loc_data = (INDOOR if b["map"] == "indoor" else OUTDOOR).get(b["loc"], {"x": 19, "y": 5, "dir": "down"})
    return {
        "map": b["map"],
        "position": {"x": loc_data["x"], "y": loc_data["y"]},
        "direction": loc_data["dir"],
        "action_val": b["action"],
        "sprite": b["sprite"],
        "activity": idle_type or "idle",
    }


@app.get('/api/life-sim/state')
def api_life_sim_state():
    """Return Ailey's current state for the Life Simulation world."""
    try:
        hour = datetime.now().hour
        # Get current mood
        mood_str, mood_val = core.current_mood("Simon")
        # Get idle thinker state
        thinker_type = idle_thinker.current_thought_type or "idle"
        thinker_busy = idle_thinker.is_busy

        # ── Leisure fallback: wenn IdleThinker idle ist, LifeSim-Freizeitaktivität nutzen ──
        if not thinker_busy and thinker_type == "idle":
            try:
                _ls_needs = _load_needs()
                _ls_act   = _ls_needs.get("_leisure_activity")
                _ls_until = _ls_needs.get("_leisure_until", 0.0)
                if _ls_act and time.time() <= _ls_until:
                    thinker_type = _ls_act
            except Exception:
                pass

        # Get latest thought preview
        thought_preview = ""
        thought_type_icon = ""
        try:
            recent = read_thoughts(limit=1)
            if recent:
                chain = recent[0].get("thought_chain", "")
                ttype = recent[0].get("type", "")
                # First sentence: find earliest sentence-ending punctuation (. ! ?) within first 120 chars
                import re as _re_tp
                _sent_match = _re_tp.search(r'[.!?](?:\s|$)', chain[:120])
                if _sent_match:
                    thought_preview = chain[:_sent_match.end()].rstrip()
                else:
                    # No sentence end found — truncate at last word boundary within 80 chars
                    if len(chain) <= 80:
                        thought_preview = chain
                    else:
                        thought_preview = chain[:80].rsplit(" ", 1)[0] + "…"
                # Icon for thought type
                _type_icons = {
                    "reflection": "💭", "introspection": "🪞", "goal_planning": "🎯",
                    "creative_song": "🎵", "research": "🔍", "memory_consolidation": "📓",
                    "free_thought": "✨", "proactive_message": "💬", "email_check": "📧",
                    "email_initiative": "📨", "glossary_cleanup": "📚",
                    "creative_art": "🎨", "creative_image": "🖼️",
                    "music_making": "🎸", "diary_writing": "📖",
                    "fishing": "🎣", "flower_picking": "🌸",
                    "gardening": "🌱", "outdoor_stroll": "🚶",
                    "nightly_summary": "📋",
                }
                thought_type_icon = _type_icons.get(ttype, "💭")
        except Exception:
            pass

        # ── Needs check: override activity if a need is critical ──
        needs_data = _load_needs()
        # Check if a completed resolution needs its relief applied
        needs_data = _check_need_resolution_complete(needs_data)
        critical_need, critical_val = _get_most_critical_need()
        resolving = needs_data.get("_resolving")
        resolve_until = needs_data.get("_resolve_until", 0)

        # Map thinker state to world behavior
        effective_type = thinker_type
        if (hour >= 23 or hour < 6) and not thinker_busy:
            effective_type = "sleeping"

        # If currently resolving a need, determine phase and show appropriate activity
        needs_override = None
        needs_phase_info = {"phase": None, "label": None, "need": None, "step_location": None}
        if resolving and time.time() < resolve_until:
            needs_phase_info = _get_need_resolution_phase(needs_data)
            phase = needs_phase_info.get("phase")

            if phase == "walking":
                # Walking phase — Ailey is headed to the location, use idle/walking type
                effective_type = "idle"  # will use standard walking sprite
            elif phase == "performing":
                # Action phase — Ailey is AT the location, show the real activity
                _need_activity = {
                    "hunger": "eating", "thirst": "drinking",
                    "tiredness": "napping", "toilet": "using_toilet",
                    "hygiene": "bathing", "environment": "cleaning",
                }
                step_idx = needs_phase_info.get("step_index", 0)
                # Special case: hunger step 0 (kitchen) = cooking
                if resolving == "hunger" and step_idx == 0:
                    effective_type = "cooking"
                else:
                    effective_type = _need_activity.get(resolving, effective_type)
            needs_override = resolving
        elif critical_need:
            # Auto-resolve: Ailey goes to fix her most critical need
            resolution = _resolve_need(critical_need)
            # Start with walking phase immediately
            needs_phase_info = _get_need_resolution_phase(_load_needs())
            effective_type = "idle"  # first phase is always walking
            needs_override = critical_need

        # Force sleeping when paused or model not loaded
        _model_loaded = False
        try:
            _model_loaded = _llm_module._model is not None
        except Exception:
            pass

        if getattr(app, '_life_sim_paused', False) or not _model_loaded:
            effective_type = "sleeping"
            mood_str = "sleepy"

        behavior = _get_life_sim_behavior(effective_type, mood_str, hour)

        # Override position to the resolution step location (walking TO or performing AT)
        if needs_override and needs_phase_info.get("step_location"):
            _step_loc = needs_phase_info["step_location"]
            # Look up actual coordinates from behavior tables
            _INDOOR_LOCS = {
                "desk": {"x": 10, "y": 14, "dir": "up"}, "bed": {"x": 20, "y": 5, "dir": "left"},
                "couch": {"x": 15, "y": 7, "dir": "up"}, "kitchen": {"x": 3, "y": 6, "dir": "up"},
                "bookshelf": {"x": 4, "y": 14, "dir": "up"}, "hamster": {"x": 8, "y": 7, "dir": "up"},
                "table": {"x": 1, "y": 14, "dir": "down"}, "bath": {"x": 17, "y": 3, "dir": "right"},
                "toilet": {"x": 11, "y": 3, "dir": "down"},
            }
            _OUTDOOR_LOCS = {
                "garden": {"x": 22, "y": 18, "dir": "down"}, "flowers": {"x": 16, "y": 22, "dir": "down"},
                "pond": {"x": 30, "y": 23, "dir": "left"}, "bench": {"x": 20, "y": 25, "dir": "down"},
            }
            loc_data = _INDOOR_LOCS.get(_step_loc) or _OUTDOOR_LOCS.get(_step_loc)
            if loc_data:
                behavior["position"] = {"x": loc_data["x"], "y": loc_data["y"]}
                behavior["direction"] = loc_data["dir"]
                behavior["map"] = "outdoor" if _step_loc in _OUTDOOR_LOCS else "indoor"

        # Needs-aware thought preview — uses phase label from resolution system
        if needs_override and needs_phase_info.get("label"):
            thought_preview = needs_phase_info["label"]
            thought_type_icon = {"hunger": "🍽️", "thirst": "💧", "tiredness": "😴", "toilet": "🚽", "hygiene": "🛁", "environment": "🧹"}.get(needs_override, "💭")

        # Sympathy score for Simon
        sympathy_simon = _get_sympathy("Simon")

        # Time of day label
        if 6 <= hour < 10:
            time_label = "morning"
        elif 10 <= hour < 13:
            time_label = "midday"
        elif 13 <= hour < 17:
            time_label = "afternoon"
        elif 17 <= hour < 21:
            time_label = "evening"
        else:
            time_label = "night"

        # Needs as dict (rounded for display)
        needs_display = {k: round(needs_data.get(k, 0), 1) for k in _NEEDS_DEFAULTS}

        # ── Tageslaune + Sozial als Top-Level für Frontend ──────────────
        _daily_mood = round(needs_data.get("daily_mood", 80), 1)
        _social = round(needs_data.get("social", 80), 1)
        if _daily_mood >= 80:
            _mood_label = "Bestens gelaunt"
        elif _daily_mood >= 60:
            _mood_label = "Guter Laune"
        elif _daily_mood >= 40:
            _mood_label = "Mäßige Laune"
        elif _daily_mood >= 20:
            _mood_label = "Schlechte Laune"
        else:
            _mood_label = "Sehr schlecht gelaunt"
        # Trend-Symbol (basierend auf gespeichertem _mood_trend pro Tick)
        _raw_trend = needs_data.get("_mood_trend", 0.0)
        if _raw_trend >= 0.08:
            _mood_trend_label = "++"   # stark steigend (>0.08/tick)
        elif _raw_trend >= 0.02:
            _mood_trend_label = "+"    # leicht steigend
        elif _raw_trend <= -0.08:
            _mood_trend_label = "--"   # stark fallend
        elif _raw_trend <= -0.02:
            _mood_trend_label = "-"    # leicht fallend
        else:
            _mood_trend_label = "~"    # stabil

        return jsonify({
            "success": True,
            "ailey": {
                "position": behavior["position"],
                "map": behavior["map"],
                "direction": behavior["direction"],
                "activity": behavior["activity"],
                "sprite": behavior["sprite"],
                "action_val": behavior["action_val"],
                "mood": mood_str,
                "mood_valence": mood_val,
                "thought_preview": thought_preview,
                "thought_icon": thought_type_icon,
                "idle_type": effective_type,
                "is_thinking": thinker_busy,
                "needs_override": needs_override,
            },
            "needs": needs_display,
            "needs_resolving": resolving if resolving and time.time() < resolve_until else None,
            "needs_phase": needs_phase_info.get("phase"),        # "walking" | "performing" | null
            "needs_phase_label": needs_phase_info.get("label"),  # German label for HUD
            "needs_phase_location": needs_phase_info.get("step_location"),  # current target location
            "sympathy": {"Simon": round(sympathy_simon, 1)},
            "sympathy_label": _get_sympathy_label(sympathy_simon),
            "daily_mood": _daily_mood,
            "daily_mood_label": _mood_label,
            "daily_mood_trend": _mood_trend_label,
            "social": _social,
            "time_of_day": time_label,
            "hour": hour,
            "lights_on": hour >= 17 or hour < 7,
            "weather": _fetch_real_weather(),
            "paused": getattr(app, '_life_sim_paused', False),
            "model_loaded": _model_loaded,
            "player_spawn_override": _player_spawn_override,  # override spawn for tab-switch persistence
            "inventory": _load_inventory(),
            "garden": {"blooming": sum(1 for p in _load_garden().get("plants", []) if p.get("stage") == "blooming"),
                        "wilted": sum(1 for p in _load_garden().get("plants", []) if p.get("stage") == "wilted"),
                        "total": len(_load_garden().get("plants", []))},
            # ── Economy + Storage summary ──
            "economy": {
                "balance": _load_economy().get("balance", 0),
            },
            "storage": {
                unit_key: {
                    "count": len(_load_storage().get(unit_key, [])),
                    "max": info["max"],
                }
                for unit_key, info in _STORAGE_UNITS.items()
            },
        })
    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500


# ── App Settings (life_sim_enabled etc.) ──────────────────────────────────
_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'ailey_settings.json')
_SETTINGS_LOCK = threading.Lock()
_SETTINGS_DEFAULTS = {
    "life_sim_enabled": True,
}

def _load_settings() -> dict:
    with _SETTINGS_LOCK:
        if os.path.exists(_SETTINGS_FILE):
            try:
                with open(_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {**_SETTINGS_DEFAULTS, **data}
            except Exception:
                pass
        return dict(_SETTINGS_DEFAULTS)

def _save_settings(data: dict):
    with _SETTINGS_LOCK:
        os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
        with open(_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ── Email Accounts CRUD ───────────────────────────────────────────────────
_EMAIL_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'email_accounts.json')
_EMAIL_ACCOUNTS_LOCK = threading.Lock()

def _load_email_accounts_db() -> list:
    if os.path.exists(_EMAIL_ACCOUNTS_FILE):
        try:
            with open(_EMAIL_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('accounts', [])
        except Exception:
            pass
    return []

def _save_email_accounts_db(accounts: list):
    with _EMAIL_ACCOUNTS_LOCK:
        with open(_EMAIL_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=2)

def _mask_password(acc: dict) -> dict:
    """Return account dict with password masked for API responses."""
    a = dict(acc)
    if a.get('password'):
        a['password'] = '••••••••'
    return a

@app.route('/api/email-accounts', methods=['GET'])
def api_email_accounts_list():
    accounts = _load_email_accounts_db()
    return jsonify({"success": True, "accounts": [_mask_password(a) for a in accounts]})

@app.route('/api/email-accounts', methods=['POST'])
def api_email_accounts_add():
    data = request.get_json(silent=True) or {}
    required = ['role', 'email', 'smtp_host', 'smtp_port', 'user', 'password']
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"success": False, "error": f"Fehlende Felder: {', '.join(missing)}"}), 400
    accounts = _load_email_accounts_db()
    # Unique id based on email
    import hashlib as _hl
    new_id = _hl.md5(data['email'].encode()).hexdigest()[:8]
    if any(a.get('id') == new_id or a.get('email') == data['email'] for a in accounts):
        return jsonify({"success": False, "error": "Konto mit dieser Adresse existiert bereits"}), 409
    new_acc = {
        "id": new_id,
        "role": data.get('role', 'simon'),
        "label": data.get('label', data['email']),
        "email": data['email'],
        "imap_host": data.get('imap_host', data['smtp_host']),
        "imap_port": int(data.get('imap_port', 993)),
        "smtp_host": data['smtp_host'],
        "smtp_port": int(data['smtp_port']),
        "user": data['user'],
        "password": data['password'],
        "is_default": data.get('is_default', False),
        "max_unseen": int(data.get('max_unseen', 20)),
    }
    if data.get('since_days'):
        new_acc['since_days'] = int(data['since_days'])
    accounts.append(new_acc)
    _save_email_accounts_db(accounts)
    return jsonify({"success": True, "account": _mask_password(new_acc)})

@app.route('/api/email-accounts/<acc_id>', methods=['PUT'])
def api_email_accounts_update(acc_id):
    data = request.get_json(silent=True) or {}
    accounts = _load_email_accounts_db()
    for i, acc in enumerate(accounts):
        if acc.get('id') == acc_id:
            updatable = ['label', 'role', 'imap_host', 'imap_port', 'smtp_host', 'smtp_port',
                         'user', 'is_default', 'max_unseen', 'since_days']
            for k in updatable:
                if k in data:
                    accounts[i][k] = data[k]
            # Only update password if a real value (not masked) is given
            if data.get('password') and data['password'] != '••••••••':
                accounts[i]['password'] = data['password']
            _save_email_accounts_db(accounts)
            return jsonify({"success": True, "account": _mask_password(accounts[i])})
    return jsonify({"success": False, "error": "Konto nicht gefunden"}), 404

@app.route('/api/email-accounts/<acc_id>', methods=['DELETE'])
def api_email_accounts_delete(acc_id):
    accounts = _load_email_accounts_db()
    original_len = len(accounts)
    accounts = [a for a in accounts if a.get('id') != acc_id]
    if len(accounts) == original_len:
        return jsonify({"success": False, "error": "Konto nicht gefunden"}), 404
    _save_email_accounts_db(accounts)
    return jsonify({"success": True})

@app.route('/api/email-accounts/<acc_id>/test', methods=['POST'])
def api_email_accounts_test(acc_id):
    accounts = _load_email_accounts_db()
    acc = next((a for a in accounts if a.get('id') == acc_id), None)
    if not acc:
        return jsonify({"success": False, "error": "Konto nicht gefunden"}), 404
    # Test SMTP connection
    import smtplib as _smtp
    try:
        if acc.get('smtp_port') == 465:
            srv = _smtp.SMTP_SSL(acc['smtp_host'], acc['smtp_port'], timeout=10)
        else:
            srv = _smtp.SMTP(acc['smtp_host'], acc['smtp_port'], timeout=10)
            srv.starttls()
        srv.login(acc['user'], acc['password'])
        srv.quit()
        return jsonify({"success": True, "message": f"✅ SMTP-Verbindung für {acc['email']} erfolgreich"})
    except Exception as e:
        return jsonify({"success": False, "error": f"SMTP-Fehler: {e}"})


@app.route('/api/settings', methods=['GET'])
def api_settings_get():
    return jsonify({"success": True, "settings": _load_settings()})

@app.route('/api/settings', methods=['POST'])
def api_settings_set():
    data = request.get_json(silent=True) or {}
    settings = _load_settings()
    # Only allow known keys
    for key in _SETTINGS_DEFAULTS:
        if key in data:
            settings[key] = data[key]
    _save_settings(settings)
    return jsonify({"success": True, "settings": settings})


# ── Real Weather Data (Open-Meteo, free, no API key) ──────────────────────
_WEATHER_CACHE = {"data": None, "ts": 0}
_WEATHER_CACHE_TTL = 600  # 10 minutes

# WMO weather codes → game weather type + label
_WMO_WEATHER_MAP = {
    0:  ("clear",   "Klarer Himmel ☀️"),
    1:  ("clear",   "Überwiegend klar 🌤️"),
    2:  ("cloudy",  "Teilweise bewölkt ⛅"),
    3:  ("cloudy",  "Bewölkt ☁️"),
    45: ("fog",     "Nebel 🌫️"),
    48: ("fog",     "Reifnebel 🌫️"),
    51: ("drizzle", "Leichter Nieselregen 🌧️"),
    53: ("drizzle", "Nieselregen 🌧️"),
    55: ("drizzle", "Starker Nieselregen 🌧️"),
    61: ("rain",    "Leichter Regen 🌧️"),
    63: ("rain",    "Regen 🌧️"),
    65: ("rain",    "Starker Regen 🌧️"),
    66: ("rain",    "Gefrierender Regen 🌧️❄️"),
    67: ("rain",    "Starker gefrierender Regen 🌧️❄️"),
    71: ("snow",    "Leichter Schneefall ❄️"),
    73: ("snow",    "Schneefall ❄️"),
    75: ("snow",    "Starker Schneefall ❄️"),
    77: ("snow",    "Schneegriesel ❄️"),
    80: ("rain",    "Leichte Regenschauer 🌦️"),
    81: ("rain",    "Regenschauer 🌧️"),
    82: ("rain",    "Heftige Regenschauer ⛈️"),
    85: ("snow",    "Leichte Schneeschauer 🌨️"),
    86: ("snow",    "Starke Schneeschauer 🌨️"),
    95: ("storm",   "Gewitter ⛈️"),
    96: ("storm",   "Gewitter mit Hagel ⛈️"),
    99: ("storm",   "Starkes Gewitter mit Hagel ⛈️"),
}


def _fetch_real_weather():
    """Fetch current weather from Open-Meteo (Cologne area). Cached 10 min."""
    now = time.time()
    if _WEATHER_CACHE["data"] and now - _WEATHER_CACHE["ts"] < _WEATHER_CACHE_TTL:
        return _WEATHER_CACHE["data"]
    try:
        # Cologne coords (Ailey's home turf)
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 50.9375,
                "longitude": 6.9603,
                "current_weather": "true",
                "timezone": "Europe/Berlin",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            cw = resp.json().get("current_weather", {})
            code = cw.get("weathercode", 0)
            game_type, label = _WMO_WEATHER_MAP.get(code, ("clear", f"Code {code}"))
            result = {
                "temperature": cw.get("temperature", 0),
                "windspeed": cw.get("windspeed", 0),
                "weathercode": code,
                "game_weather": game_type,
                "label": label,
                "is_day": cw.get("is_day", 1) == 1,
            }
            _WEATHER_CACHE["data"] = result
            _WEATHER_CACHE["ts"] = now
            return result
    except Exception as e:
        print(f"[Weather] Fetch error: {e}")
    # Fallback if no cache and fetch failed
    return {"temperature": 15, "windspeed": 5, "weathercode": 0,
            "game_weather": "clear", "label": "Klarer Himmel ☀️", "is_day": True}


@app.get('/api/weather')
def api_weather():
    """Return current real weather for the Life Sim."""
    data = _fetch_real_weather()
    return jsonify({"success": True, "weather": data})


# ── Life Sim Pause / Resume (separate from model pause) ──────────────────
app._life_sim_paused = False

@app.post('/api/life-sim/pause')
def api_life_sim_pause():
    """Pause the life simulation. Stops needs ticking and idle thinker."""
    app._life_sim_paused = True
    idle_thinker._disabled = True
    idle_thinker._paused = True
    return jsonify({"success": True, "paused": True})

@app.post('/api/life-sim/resume')
def api_life_sim_resume():
    """Resume the life simulation."""
    app._life_sim_paused = False
    idle_thinker._disabled = False
    idle_thinker._paused = False
    return jsonify({"success": True, "paused": False})

@app.get('/api/life-sim/paused')
def api_life_sim_paused():
    """Return current pause state."""
    return jsonify({"success": True, "paused": getattr(app, '_life_sim_paused', False)})


# ── Author Mode Flag (freezes needs while writing) ──
@app.post('/api/author/mode')
def api_author_mode():
    """Toggle author mode active flag — freezes LifeSim needs."""
    data = request.get_json(silent=True) or {}
    active = data.get('active', False)
    app._author_mode_active = active
    if active:
        idle_thinker.pause()
        print("[AUTHOR-MODE] ✅ Aktiviert — Needs eingefroren, IdleThinker pausiert")
    else:
        idle_thinker.resume()
        print("[AUTHOR-MODE] ⏹ Deaktiviert — Needs laufen wieder, IdleThinker fortgesetzt")
    return jsonify({"success": True, "author_mode": active})


# ── Portal Support Toggle (pause/resume portal poller) ──
@app.post('/api/portal/toggle')
def api_portal_toggle():
    """Toggle portal support on/off. When off, portal users see 'Ailey schläft'."""
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled', True)
    poller = get_portal_poller()
    if enabled:
        poller.resume()
        print("[PORTAL] ✅ Portal-Support aktiviert")
    else:
        poller.pause()
        print("[PORTAL] 💤 Portal-Support deaktiviert — Ailey schläft für Portal-User")
    return jsonify({"success": True, "portal_enabled": enabled})


@app.get('/api/portal/status')
def api_portal_status():
    """Get current portal support status + stats."""
    poller = get_portal_poller()
    stats = poller.get_stats()
    thread_alive = poller._thread.is_alive() if poller._thread else False
    return jsonify({
        "success": True,
        "portal_enabled": not poller.is_paused(),
        "portal_configured": bool(poller._portal_url),
        "thread_alive": thread_alive,
        "stats": stats,
    })


# ── LifeSim Reset: set all needs to perfect state ──
@app.post('/api/life-sim/reset')
def api_life_sim_reset():
    """Reset all LifeSim needs, mood, and sympathy to perfect state."""
    try:
        nd = _load_needs()
        # Perfect needs: all bad needs at 0 (hunger, thirst, tiredness, toilet, hygiene, environment)
        for k in ["hunger", "thirst", "tiredness", "toilet", "hygiene", "environment"]:
            nd[k] = 0
        # Social high, mood great
        nd["social"] = 100
        nd["daily_mood"] = 100
        # Clear any active need resolution
        nd.pop("_resolving", None)
        nd.pop("_resolve_start", None)
        nd.pop("_resolve_need", None)
        nd.pop("_resolve_duration", None)
        nd.pop("_resolve_until", None)
        nd.pop("_resolve_steps", None)
        # Clear leisure activity
        nd.pop("_leisure_activity", None)
        nd.pop("_leisure_until", None)
        with _NEEDS_LOCK:
            with open(_NEEDS_JSON, 'w', encoding='utf-8') as f:
                json.dump(nd, f, ensure_ascii=False, indent=2)
        # Reset mood weights to neutral
        mw = _load_mood_weights()
        mw["weights"] = {m: 0 for m in _VALID_CHAR_MOODS}
        mw["current_char_mood"] = "neutral"
        _save_mood_weights(mw)
        # Reset sympathy to positive
        try:
            _adjust_sympathy("Simon", 0, "Reset")  # ensure file exists
            if os.path.exists(_SYMPATHY_JSON):
                with open(_SYMPATHY_JSON, 'r', encoding='utf-8') as f:
                    sp = json.load(f)
                sp["Simon"] = 80
                with open(_SYMPATHY_JSON, 'w', encoding='utf-8') as f:
                    json.dump(sp, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        print("[LIFESIM] 🔄 Reset — alle Werte auf perfekten State gesetzt")
        return jsonify({"success": True, "message": "LifeSim zurückgesetzt"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Player Position Override (spawn point persistence across tab switches) ──
@app.post('/api/life-sim/player-position')
def api_life_sim_player_position():
    """Save the player's current position as spawn override.
    Called by the RMMZ plugin when the player moves.
    This position overrides the DB default spawn when the game reloads."""
    global _player_spawn_override
    data = request.get_json(silent=True) or {}
    x = data.get("x")
    y = data.get("y")
    d = data.get("dir", 2)
    map_id = data.get("mapId", 2)
    if x is not None and y is not None:
        _player_spawn_override = {"x": int(x), "y": int(y), "dir": int(d), "mapId": int(map_id)}
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "x and y required"}), 400

@app.delete('/api/life-sim/player-position')
def api_life_sim_player_position_clear():
    """Clear the spawn override. Called on full app restart (loading screen)."""
    global _player_spawn_override
    _player_spawn_override = None
    return jsonify({"success": True})


@app.get('/api/life-sim/needs')
def api_life_sim_needs():
    """Return current needs values including daily_mood and social."""
    data = _load_needs()
    data = _check_need_resolution_complete(data)  # apply relief if resolution finished
    needs = {k: round(data.get(k, _NEEDS_DEFAULTS.get(k, 0)), 1) for k in _NEEDS_DEFAULTS}
    critical, cval = _get_most_critical_need()
    phase_info = _get_need_resolution_phase(data)
    daily_mood = round(data.get("daily_mood", 75), 1)
    social = round(data.get("social", 80), 1)
    # Mood label for display
    if daily_mood >= 80:
        mood_label = "Bestens gelaunt"
    elif daily_mood >= 60:
        mood_label = "Guter Laune"
    elif daily_mood >= 40:
        mood_label = "Mäßige Laune"
    elif daily_mood >= 20:
        mood_label = "Schlechte Laune"
    else:
        mood_label = "Sehr schlecht gelaunt"
    return jsonify({
        "success": True,
        "needs": needs,
        "daily_mood": daily_mood,
        "daily_mood_label": mood_label,
        "social": social,
        "critical": critical,
        "critical_value": round(cval, 1) if critical else None,
        "resolving": data.get("_resolving") if time.time() < data.get("_resolve_until", 0) else None,
        "needs_phase": phase_info.get("phase"),
        "needs_phase_label": phase_info.get("label"),
    })


@app.post('/api/life-sim/needs/resolve')
def api_life_sim_resolve_need():
    """Manually resolve a specific need (e.g. player feeds Ailey)."""
    data = request.get_json(silent=True) or {}
    need = data.get("need", "").strip().lower()
    if need not in _NEEDS_DEFAULTS:
        return jsonify({"success": False, "error": f"Unknown need: {need}"}), 400
    result = _resolve_need(need)
    return jsonify({"success": True, **result})


@app.post('/api/life-sim/sweep')
def api_life_sim_sweep():
    """Player sweeps/cleans the room — reduces environment need + gains sympathy."""
    data = request.get_json(silent=True) or {}
    duration = min(5, max(1, data.get("duration", 3)))
    relief = duration * 8  # 8 points per second of sweeping
    with _NEEDS_LOCK:
        needs = _load_needs()
        old_val = needs.get("environment", 0)
        needs["environment"] = max(0, old_val - relief)
        _save_needs(needs)
    # Sympathy bonus for cleaning
    _adjust_sympathy("Simon", 1.5, f"Zimmer gefegt ({duration}s)")
    new_val = max(0, old_val - relief)
    return jsonify({
        "success": True,
        "message": f"✨ Zimmer gefegt! Umgebung: {round(old_val)} → {round(new_val)}",
        "old_value": round(old_val, 1),
        "new_value": round(new_val, 1),
    })


@app.get('/api/sympathy')
def api_sympathy_all():
    """Return all sympathy scores."""
    data = _load_sympathy()
    # Filter out internal keys
    scores = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, (int, float))}
    labeled = {k: {"score": round(v, 1), "label": _get_sympathy_label(v)} for k, v in scores.items()}
    return jsonify({"success": True, "sympathy": labeled})


@app.get('/api/sympathy/<person>')
def api_sympathy_person(person):
    """Return sympathy score for a specific person."""
    score = _get_sympathy(person)
    return jsonify({
        "success": True,
        "person": person,
        "score": round(score, 1),
        "label": _get_sympathy_label(score),
    })


@app.post('/api/sympathy/adjust')
def api_sympathy_adjust():
    """Adjust sympathy for a person. Body: {person, delta, reason}."""
    data = request.get_json(silent=True) or {}
    person = data.get("person", "").strip()
    delta = float(data.get("delta", 0))
    reason = data.get("reason", "")
    if not person:
        return jsonify({"success": False, "error": "Missing person"}), 400
    old, new = _adjust_sympathy(person, delta, reason)
    return jsonify({
        "success": True,
        "person": person,
        "old_score": round(old, 1),
        "new_score": round(new, 1),
        "label": _get_sympathy_label(new),
    })


# ══════════════════════════════════════════════════════════════════════════════
# GAME MECHANICS — Economy, Storage, Cooking, Gifts, Garden, …
# ══════════════════════════════════════════════════════════════════════════════

# ── VyrusDollars Economy ─────────────────────────────────────────────────────
_ECONOMY_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'economy.json')
_ECONOMY_LOCK = threading.Lock()

def _load_economy() -> dict:
    if os.path.exists(_ECONOMY_JSON):
        try:
            with open(_ECONOMY_JSON, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 50.0, "total_earned": 50.0, "total_spent": 0.0, "transactions": []}

def _save_economy(data: dict):
    try:
        # Keep last 100 transactions only
        data["transactions"] = data.get("transactions", [])[-100:]
        with open(_ECONOMY_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Economy] save error: {e}")

def _earn_vyrus_dollars(amount: float, reason: str) -> dict:
    """Add VyrusDollars (from creative output, etc.)."""
    with _ECONOMY_LOCK:
        eco = _load_economy()
        old_bal = eco["balance"]
        eco["balance"] = round(eco["balance"] + amount, 2)
        eco["total_earned"] = round(eco.get("total_earned", 0) + amount, 2)
        eco["transactions"].append({
            "type": "earn", "amount": amount, "reason": reason,
            "balance_after": eco["balance"], "ts": time.time(),
        })
        _save_economy(eco)
        return {"old": old_bal, "new": eco["balance"]}

def _spend_vyrus_dollars(amount: float, reason: str) -> dict:
    """Spend VyrusDollars. Returns None if insufficient funds."""
    with _ECONOMY_LOCK:
        eco = _load_economy()
        if eco["balance"] < amount:
            return None
        old_bal = eco["balance"]
        eco["balance"] = round(eco["balance"] - amount, 2)
        eco["total_spent"] = round(eco.get("total_spent", 0) + amount, 2)
        eco["transactions"].append({
            "type": "spend", "amount": amount, "reason": reason,
            "balance_after": eco["balance"], "ts": time.time(),
        })
        _save_economy(eco)
        return {"old": old_bal, "new": eco["balance"]}

@app.get('/api/life-sim/economy')
def api_life_sim_economy():
    """Return VyrusDollars balance and recent transactions."""
    eco = _load_economy()
    return jsonify({
        "success": True,
        "balance": eco["balance"],
        "total_earned": eco.get("total_earned", 0),
        "total_spent": eco.get("total_spent", 0),
        "recent_transactions": eco.get("transactions", [])[-10:],
    })

# ── Storage System (Kühlschrank, Schrank, Vorratskammer) ─────────────────
_STORAGE_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'storage.json')
_STORAGE_LOCK = threading.Lock()

# Storage units with max capacity
_STORAGE_UNITS = {
    "fridge":  {"label": "Kühlschrank",   "emoji": "🧊", "max": 20, "location": "kitchen",
                "accepts": ["fish", "berries", "milk", "eggs", "butter", "cheese", "vegetables", "water", "juice", "soda"]},
    "pantry":  {"label": "Vorratskammer", "emoji": "🏪", "max": 20, "location": "kitchen",
                "accepts": ["flour", "sugar", "rice", "pasta", "spices", "tea_leaves", "coffee_beans", "oil", "canned_food", "bread"]},
    "cabinet": {"label": "Schrank",       "emoji": "🗄️", "max": 12, "location": "wardrobe",
                "accepts": ["blanket", "book", "flowers", "candle", "plushie", "photo_frame"]},
}

# All items that can be stored (superset of _GIFT_ITEMS with groceries)
_ALL_ITEMS = {
    # Original pickable/giftable items
    "flowers":    {"label": "Blumen",          "emoji": "💐", "category": "decoration", "price": 5},
    "tea":        {"label": "Tee (fertig)",    "emoji": "🍵", "category": "drink",      "price": 0},
    "cake":       {"label": "Kuchen",          "emoji": "🍰", "category": "food",       "price": 0},
    "book":       {"label": "Buch",            "emoji": "📖", "category": "misc",       "price": 3},
    "fish":       {"label": "Fisch",           "emoji": "🐟", "category": "food",       "price": 0},
    "berries":    {"label": "Beeren",          "emoji": "🫐", "category": "food",       "price": 0},
    "water":      {"label": "Frisches Wasser", "emoji": "💧", "category": "drink",      "price": 0},
    "blanket":    {"label": "Decke",           "emoji": "🛏️", "category": "misc",       "price": 4},
    # Groceries (orderable via Tablet)
    "milk":       {"label": "Milch",           "emoji": "🥛", "category": "drink",      "price": 2},
    "eggs":       {"label": "Eier",            "emoji": "🥚", "category": "food",       "price": 2},
    "butter":     {"label": "Butter",          "emoji": "🧈", "category": "food",       "price": 2},
    "cheese":     {"label": "Käse",            "emoji": "🧀", "category": "food",       "price": 3},
    "vegetables": {"label": "Gemüse",          "emoji": "🥦", "category": "food",       "price": 3},
    "flour":      {"label": "Mehl",            "emoji": "🌾", "category": "ingredient", "price": 1},
    "sugar":      {"label": "Zucker",          "emoji": "🍬", "category": "ingredient", "price": 1},
    "rice":       {"label": "Reis",            "emoji": "🍚", "category": "food",       "price": 2},
    "pasta":      {"label": "Pasta",           "emoji": "🍝", "category": "food",       "price": 2},
    "spices":     {"label": "Gewürze",         "emoji": "🌶️", "category": "ingredient", "price": 2},
    "tea_leaves": {"label": "Teeblätter",      "emoji": "🍃", "category": "ingredient", "price": 2},
    "coffee_beans": {"label": "Kaffeebohnen",  "emoji": "☕", "category": "ingredient", "price": 3},
    "oil":        {"label": "Öl",              "emoji": "🫒", "category": "ingredient", "price": 2},
    "canned_food": {"label": "Konserven",      "emoji": "🥫", "category": "food",       "price": 2},
    "bread":      {"label": "Brot",            "emoji": "🍞", "category": "food",       "price": 2},
    "juice":      {"label": "Saft",            "emoji": "🧃", "category": "drink",      "price": 2},
    "soda":       {"label": "Limo",            "emoji": "🥤", "category": "drink",      "price": 2},
    "candle":     {"label": "Kerze",           "emoji": "🕯️", "category": "decoration", "price": 3},
    "plushie":    {"label": "Plüschtier",      "emoji": "🧸", "category": "misc",       "price": 5},
    "photo_frame": {"label": "Bilderrahmen",   "emoji": "🖼️", "category": "decoration", "price": 4},
}

def _load_storage() -> dict:
    if os.path.exists(_STORAGE_JSON):
        try:
            with open(_STORAGE_JSON, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    # Default: empty storage units
    return {unit: [] for unit in _STORAGE_UNITS}

def _save_storage(data: dict):
    try:
        with open(_STORAGE_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Storage] save error: {e}")

@app.get('/api/life-sim/storage')
def api_life_sim_storage():
    """Return all storage units and their contents."""
    storage = _load_storage()
    result = {}
    for unit_key, unit_info in _STORAGE_UNITS.items():
        items = storage.get(unit_key, [])
        result[unit_key] = {
            "label": unit_info["label"],
            "emoji": unit_info["emoji"],
            "max": unit_info["max"],
            "items": items,
            "count": len(items),
            "full": len(items) >= unit_info["max"],
        }
    return jsonify({"success": True, "storage": result})

@app.get('/api/life-sim/storage/<unit>')
def api_life_sim_storage_unit(unit):
    """Return contents of a specific storage unit."""
    if unit not in _STORAGE_UNITS:
        return jsonify({"success": False, "error": f"Unbekannte Lagereinheit: {unit}"}), 400
    storage = _load_storage()
    unit_info = _STORAGE_UNITS[unit]
    items = storage.get(unit, [])
    return jsonify({
        "success": True,
        "unit": unit,
        "label": unit_info["label"],
        "emoji": unit_info["emoji"],
        "max": unit_info["max"],
        "items": items,
        "count": len(items),
    })

@app.post('/api/life-sim/storage/<unit>/store')
def api_life_sim_storage_store(unit):
    """Store an item from player inventory into a storage unit. Body: {inventory_index: int}."""
    if unit not in _STORAGE_UNITS:
        return jsonify({"success": False, "error": f"Unbekannte Lagereinheit: {unit}"}), 400
    data = request.get_json(silent=True) or {}
    idx = int(data.get("inventory_index", -1))
    inv = _load_inventory()
    if idx < 0 or idx >= len(inv):
        return jsonify({"success": False, "error": "Ungültiger Inventar-Index"}), 400
    item = inv[idx]
    item_key = item.get("item", "")
    unit_info = _STORAGE_UNITS[unit]
    # Check if this item is accepted by this unit
    if item_key not in unit_info["accepts"]:
        return jsonify({"success": False, "error": f"{_ALL_ITEMS.get(item_key, {}).get('label', item_key)} passt nicht in {unit_info['label']}"}), 400
    with _STORAGE_LOCK:
        storage = _load_storage()
        unit_items = storage.get(unit, [])
        if len(unit_items) >= unit_info["max"]:
            return jsonify({"success": False, "error": f"{unit_info['label']} ist voll! ({unit_info['max']}/{unit_info['max']})"}), 400
        # Remove from inventory
        removed = inv.pop(idx)
        _save_inventory(inv)
        # Add to storage
        unit_items.append({"item": item_key, "label": removed.get("label", ""), "emoji": removed.get("emoji", ""), "stored_at": time.time()})
        storage[unit] = unit_items
        _save_storage(storage)
    return jsonify({"success": True, "stored": item_key, "unit": unit, "unit_label": unit_info["label"],
                     "inventory": inv, "storage_count": len(unit_items)})

@app.post('/api/life-sim/storage/<unit>/take')
def api_life_sim_storage_take(unit):
    """Take an item from storage into player inventory. Body: {index: int}."""
    if unit not in _STORAGE_UNITS:
        return jsonify({"success": False, "error": f"Unbekannte Lagereinheit: {unit}"}), 400
    data = request.get_json(silent=True) or {}
    idx = int(data.get("index", -1))
    with _STORAGE_LOCK:
        storage = _load_storage()
        unit_items = storage.get(unit, [])
        if idx < 0 or idx >= len(unit_items):
            return jsonify({"success": False, "error": "Ungültiger Index"}), 400
        inv = _load_inventory()
        if len(inv) >= 5:
            return jsonify({"success": False, "error": "Inventar voll! (max 5)"}), 400
        item = unit_items.pop(idx)
        storage[unit] = unit_items
        _save_storage(storage)
        inv.append({"item": item["item"], "label": item.get("label", ""), "emoji": item.get("emoji", ""), "picked_at": time.time()})
        _save_inventory(inv)
    return jsonify({"success": True, "taken": item["item"], "inventory": inv, "storage_count": len(unit_items)})

# ── Cooking / Recipe System ──────────────────────────────────────────────
_RECIPES = [
    {"id": "fried_egg",     "name": "Spiegelei",         "emoji": "🍳", "hunger_relief": 20,
     "ingredients": [("eggs", 1)], "sympathy": 2},
    {"id": "omelette",      "name": "Omelette",          "emoji": "🍳", "hunger_relief": 30,
     "ingredients": [("eggs", 2), ("cheese", 1)], "sympathy": 4},
    {"id": "pasta_dish",    "name": "Pasta-Gericht",     "emoji": "🍝", "hunger_relief": 40,
     "ingredients": [("pasta", 1), ("oil", 1), ("spices", 1)], "sympathy": 5},
    {"id": "fish_dinner",   "name": "Fisch-Dinner",      "emoji": "🐟", "hunger_relief": 45,
     "ingredients": [("fish", 1), ("oil", 1), ("spices", 1)], "sympathy": 6},
    {"id": "rice_bowl",     "name": "Reis-Bowl",         "emoji": "🍚", "hunger_relief": 35,
     "ingredients": [("rice", 1), ("vegetables", 1)], "sympathy": 4},
    {"id": "bread_cheese",  "name": "Brot mit Käse",     "emoji": "🧀", "hunger_relief": 25,
     "ingredients": [("bread", 1), ("cheese", 1)], "sympathy": 3},
    {"id": "pancakes",      "name": "Pfannkuchen",       "emoji": "🥞", "hunger_relief": 35,
     "ingredients": [("flour", 1), ("eggs", 1), ("milk", 1), ("sugar", 1)], "sympathy": 6},
    {"id": "vegetable_soup","name": "Gemüsesuppe",       "emoji": "🥣", "hunger_relief": 30,
     "ingredients": [("vegetables", 1), ("spices", 1), ("water", 1)], "sympathy": 4},
    {"id": "tea_served",    "name": "Tee servieren",     "emoji": "🍵", "hunger_relief": 0, "thirst_relief": 25,
     "ingredients": [("tea_leaves", 1), ("water", 1)], "sympathy": 3},
    {"id": "coffee",        "name": "Kaffee kochen",     "emoji": "☕", "hunger_relief": 0, "thirst_relief": 20,
     "ingredients": [("coffee_beans", 1), ("water", 1)], "sympathy": 3},
    {"id": "berry_smoothie","name": "Beeren-Smoothie",   "emoji": "🫐", "hunger_relief": 15, "thirst_relief": 15,
     "ingredients": [("berries", 1), ("milk", 1)], "sympathy": 4},
    {"id": "canned_meal",   "name": "Konserven-Mahlzeit","emoji": "🥫", "hunger_relief": 25,
     "ingredients": [("canned_food", 1)], "sympathy": 1},
]

def _get_storage_item_count(item_key: str) -> int:
    """Count how many of a specific item are across all storage units."""
    storage = _load_storage()
    count = 0
    for unit_items in storage.values():
        for it in unit_items:
            if it.get("item") == item_key:
                count += 1
    return count

def _consume_storage_item(item_key: str, count: int = 1) -> bool:
    """Remove items from storage (oldest first). Returns True if successful."""
    with _STORAGE_LOCK:
        storage = _load_storage()
        removed = 0
        for unit_key in storage:
            unit_items = storage[unit_key]
            i = 0
            while i < len(unit_items) and removed < count:
                if unit_items[i].get("item") == item_key:
                    unit_items.pop(i)
                    removed += 1
                else:
                    i += 1
        if removed >= count:
            _save_storage(storage)
            return True
        return False

@app.get('/api/life-sim/recipes')
def api_life_sim_recipes():
    """Return available recipes based on current storage contents."""
    recipes_out = []
    for recipe in _RECIPES:
        available = True
        missing = []
        for ing_key, ing_count in recipe["ingredients"]:
            have = _get_storage_item_count(ing_key)
            if have < ing_count:
                available = False
                item_info = _ALL_ITEMS.get(ing_key, {})
                missing.append({"item": ing_key, "label": item_info.get("label", ing_key),
                                "emoji": item_info.get("emoji", ""), "need": ing_count, "have": have})
        recipes_out.append({
            "id": recipe["id"], "name": recipe["name"], "emoji": recipe["emoji"],
            "available": available, "missing": missing,
            "ingredients": [{"item": k, "count": c,
                             "label": _ALL_ITEMS.get(k, {}).get("label", k),
                             "emoji": _ALL_ITEMS.get(k, {}).get("emoji", "")}
                            for k, c in recipe["ingredients"]],
            "hunger_relief": recipe.get("hunger_relief", 0),
            "thirst_relief": recipe.get("thirst_relief", 0),
            "sympathy": recipe["sympathy"],
        })
    return jsonify({"success": True, "recipes": recipes_out})

@app.post('/api/life-sim/cook')
def api_life_sim_cook():
    """Cook a recipe. Body: {recipe_id: string, quality?: 'perfect'|'good'|'ok'|'burnt'}.
    quality comes from the cooking minigame and scales sympathy + need relief."""
    data = request.get_json(silent=True) or {}
    recipe_id = data.get("recipe_id", "").strip()
    quality = data.get("quality", "ok")  # default ok if no minigame
    recipe = next((r for r in _RECIPES if r["id"] == recipe_id), None)
    if not recipe:
        return jsonify({"success": False, "error": f"Unbekanntes Rezept: {recipe_id}"}), 400
    # Quality multipliers
    _QUALITY_MULT = {"perfect": 2.0, "good": 1.5, "ok": 1.0, "burnt": 0.3}
    _QUALITY_LABELS = {"perfect": "⭐ Perfekt!", "good": "👍 Gut!", "ok": "👌 Okay", "burnt": "💨 Angebrannt…"}
    _QUALITY_EMOJI = {"perfect": "⭐", "good": "👍", "ok": "👌", "burnt": "💨"}
    mult = _QUALITY_MULT.get(quality, 1.0)
    q_label = _QUALITY_LABELS.get(quality, "")
    q_emoji = _QUALITY_EMOJI.get(quality, "")
    # Check ingredients
    for ing_key, ing_count in recipe["ingredients"]:
        if _get_storage_item_count(ing_key) < ing_count:
            item_info = _ALL_ITEMS.get(ing_key, {})
            return jsonify({"success": False, "error": f"Nicht genug {item_info.get('label', ing_key)}!"}), 400
    # Consume ingredients
    for ing_key, ing_count in recipe["ingredients"]:
        _consume_storage_item(ing_key, ing_count)
    # Apply need effects (scaled by quality)
    need_changes = {}
    with _NEEDS_LOCK:
        nd = _load_needs()
        if recipe.get("hunger_relief", 0) > 0:
            relief = recipe["hunger_relief"] * mult
            old_h = nd.get("hunger", 0)
            nd["hunger"] = max(0, old_h - relief)
            need_changes["hunger"] = {"old": round(old_h, 1), "new": round(nd["hunger"], 1)}
        if recipe.get("thirst_relief", 0) > 0:
            relief = recipe["thirst_relief"] * mult
            old_t = nd.get("thirst", 0)
            nd["thirst"] = max(0, old_t - relief)
            need_changes["thirst"] = {"old": round(old_t, 1), "new": round(nd["thirst"], 1)}
        _save_needs(nd)
    # Sympathy bonus (scaled by quality)
    symp_pts = max(1, int(recipe["sympathy"] * mult))
    old_s, new_s = _adjust_sympathy("Simon", symp_pts, f"Cooked: {recipe['name']} ({quality})")
    # Quality-dependent reactions
    import random
    if quality == "perfect":
        reactions = [
            f"WOW! {recipe['name']} ist PERFEKT geworden!! {recipe['emoji']}⭐💜",
            f"Das ist das beste {recipe['name']} aller Zeiten! Meisterkoch! {recipe['emoji']}✨⭐",
            f"Oh mein Gott, {recipe['name']}! PERFEKT! Ich bin sprachlos! {recipe['emoji']}🤩⭐",
        ]
    elif quality == "good":
        reactions = [
            f"Mmh, {recipe['name']}! Richtig gut geworden! {recipe['emoji']}👍💜",
            f"Lecker! {recipe['name']} schmeckt super! {recipe['emoji']}😋👍",
            f"Toll gekocht! {recipe['name']} ist echt gelungen! {recipe['emoji']}✨👍",
        ]
    elif quality == "burnt":
        reactions = [
            f"Ähm… das {recipe['name']} ist etwas… angebrannt? {recipe['emoji']}💨😅",
            f"Hust hust… naja, ist halt {recipe['name']} mit Röstaroma… {recipe['emoji']}💨🫠",
            f"{recipe['name']}… na ja, der Gedanke zählt! {recipe['emoji']}💨😬",
        ]
    else:
        reactions = [
            f"Mmh, {recipe['name']}! Das riecht fantastisch! {recipe['emoji']}💜",
            f"Du hast {recipe['name']} gekocht?! Wow! {recipe['emoji']}✨",
            f"Oh, lecker! {recipe['name']}! Danke! {recipe['emoji']}😋",
            f"{recipe['name']}! Genau was ich jetzt brauche! {recipe['emoji']}🥰",
        ]
    reaction = random.choice(reactions)
    return jsonify({
        "success": True,
        "recipe": recipe_id, "name": recipe["name"], "emoji": recipe["emoji"],
        "reaction": reaction, "quality": quality, "quality_label": q_label, "quality_emoji": q_emoji,
        "need_changes": need_changes,
        "sympathy": {"old": round(old_s, 1), "new": round(new_s, 1), "label": _get_sympathy_label(new_s),
                     "bonus": symp_pts},
    })

# ── Fishing Minigame Result ──────────────────────────────────────────────
@app.post('/api/life-sim/fish')
def api_life_sim_fish():
    """Process fishing minigame result. Body: {quality: 'legendary'|'great'|'good'|'miss'}.
    Adds fish to storage with quality label. Gives sympathy based on quality."""
    data = request.get_json(silent=True) or {}
    quality = data.get("quality", "miss")
    import random
    _FISH_DATA = {
        "legendary": {
            "fish": [("🐟", "Goldforelle"), ("🐠", "Regenbogenfisch"), ("🦈", "Mini-Hai")],
            "sympathy": 6, "label": "⭐ Legendärer Fang!",
            "reactions": [
                "OH WOW! Ein {fish}!! Das ist unglaublich! ⭐💜",
                "LEGENDÄR! Ein {fish}! Du bist der beste Angler! 🎣⭐",
                "Ich kann es nicht fassen! Ein {fish}!! WAHNSINN! ✨⭐",
            ]
        },
        "great": {
            "fish": [("🐟", "Lachs"), ("🐟", "Forelle"), ("🐠", "Barsch")],
            "sympathy": 4, "label": "🎉 Toller Fang!",
            "reactions": [
                "Super! Ein schöner {fish}! Gut gemacht! 🎣💜",
                "Wow, ein {fish}! Der sieht toll aus! 🐟✨",
                "Klasse! {fish}! Den können wir gut gebrauchen! 🎉",
            ]
        },
        "good": {
            "fish": [("🐟", "Kleiner Fisch"), ("🐟", "Sardine"), ("🐟", "Stichling")],
            "sympathy": 2, "label": "👍 Guter Fang",
            "reactions": [
                "Hey, ein {fish}! Immerhin! 🐟👍",
                "Klein aber fein — ein {fish}! 🎣😊",
                "Ein {fish}! Jeder Fang zählt! 👍",
            ]
        },
        "miss": {
            "fish": [], "sympathy": 0, "label": "💨 Entwischt!",
            "reactions": [
                "Oh nein, der ist entwischt! 🐟💨",
                "Knapp daneben! Nächstes Mal! 🎣😅",
                "Der war zu schnell… Versuch's nochmal! 💨",
            ]
        },
    }
    fdata = _FISH_DATA.get(quality, _FISH_DATA["miss"])
    fish_emoji, fish_name = "", "Nichts"
    if fdata["fish"]:
        fish_emoji, fish_name = random.choice(fdata["fish"])
        # Add fish directly to fridge storage
        with _STORAGE_LOCK:
            storage = _load_storage()
            fridge = storage.get("fridge", [])
            fridge.append({"item": "fish", "label": fish_name, "emoji": fish_emoji, "stored_at": time.time()})
            storage["fridge"] = fridge
            _save_storage(storage)
    # Sympathy bonus
    old_s, new_s = 0.0, 0.0
    if fdata["sympathy"] > 0:
        old_s, new_s = _adjust_sympathy("Simon", fdata["sympathy"], f"Fishing: {fish_name} ({quality})")
    reaction = random.choice(fdata["reactions"]).replace("{fish}", fish_name)
    return jsonify({
        "success": True, "quality": quality, "quality_label": fdata["label"],
        "fish_name": fish_name, "fish_emoji": fish_emoji,
        "reaction": reaction,
        "sympathy": {"old": round(old_s, 1), "new": round(new_s, 1), "label": _get_sympathy_label(new_s),
                     "bonus": fdata["sympathy"]},
    })

# ── Tablet Ordering System ───────────────────────────────────────────────
_ORDERABLE_ITEMS = [
    # Groceries (Lebensmittel)
    {"item": "milk",        "label": "Milch",          "emoji": "🥛", "price": 2, "category": "Lebensmittel"},
    {"item": "eggs",        "label": "Eier",           "emoji": "🥚", "price": 2, "category": "Lebensmittel"},
    {"item": "butter",      "label": "Butter",         "emoji": "🧈", "price": 2, "category": "Lebensmittel"},
    {"item": "cheese",      "label": "Käse",           "emoji": "🧀", "price": 3, "category": "Lebensmittel"},
    {"item": "vegetables",  "label": "Gemüse",         "emoji": "🥦", "price": 3, "category": "Lebensmittel"},
    {"item": "bread",       "label": "Brot",           "emoji": "🍞", "price": 2, "category": "Lebensmittel"},
    {"item": "canned_food", "label": "Konserven",      "emoji": "🥫", "price": 2, "category": "Lebensmittel"},
    # Ingredients (Zutaten)
    {"item": "flour",       "label": "Mehl",           "emoji": "🌾", "price": 1, "category": "Zutaten"},
    {"item": "sugar",       "label": "Zucker",         "emoji": "🍬", "price": 1, "category": "Zutaten"},
    {"item": "rice",        "label": "Reis",           "emoji": "🍚", "price": 2, "category": "Zutaten"},
    {"item": "pasta",       "label": "Pasta",          "emoji": "🍝", "price": 2, "category": "Zutaten"},
    {"item": "spices",      "label": "Gewürze",        "emoji": "🌶️", "price": 2, "category": "Zutaten"},
    {"item": "oil",         "label": "Öl",             "emoji": "🫒", "price": 2, "category": "Zutaten"},
    {"item": "tea_leaves",  "label": "Teeblätter",     "emoji": "🍃", "price": 2, "category": "Zutaten"},
    {"item": "coffee_beans","label": "Kaffeebohnen",   "emoji": "☕", "price": 3, "category": "Zutaten"},
    # Drinks (Getränke)
    {"item": "juice",       "label": "Saft",           "emoji": "🧃", "price": 2, "category": "Getränke"},
    {"item": "soda",        "label": "Limo",           "emoji": "🥤", "price": 2, "category": "Getränke"},
    {"item": "water",       "label": "Wasser (Flasche)","emoji": "💧", "price": 1, "category": "Getränke"},
    # Misc
    {"item": "candle",      "label": "Kerze",          "emoji": "🕯️", "price": 3, "category": "Deko"},
    {"item": "plushie",     "label": "Plüschtier",     "emoji": "🧸", "price": 5, "category": "Deko"},
    {"item": "photo_frame", "label": "Bilderrahmen",   "emoji": "🖼️", "price": 4, "category": "Deko"},
    {"item": "flowers",     "label": "Blumenstrauß",   "emoji": "💐", "price": 5, "category": "Deko"},
]

@app.get('/api/life-sim/shop')
def api_life_sim_shop():
    """Return the shop catalog and current balance."""
    eco = _load_economy()
    return jsonify({
        "success": True,
        "balance": eco["balance"],
        "items": _ORDERABLE_ITEMS,
    })

@app.post('/api/life-sim/shop/order')
def api_life_sim_shop_order():
    """Order items from the shop. Body: {items: [{item: str, qty: int}, ...]}."""
    data = request.get_json(silent=True) or {}
    order_items = data.get("items", [])
    if not order_items:
        return jsonify({"success": False, "error": "Keine Bestellung angegeben"}), 400
    # Calculate total cost
    total_cost = 0
    resolved = []
    for oi in order_items:
        item_key = oi.get("item", "")
        qty = max(1, int(oi.get("qty", 1)))
        shop_item = next((si for si in _ORDERABLE_ITEMS if si["item"] == item_key), None)
        if not shop_item:
            return jsonify({"success": False, "error": f"Unbekannter Artikel: {item_key}"}), 400
        total_cost += shop_item["price"] * qty
        resolved.append({"item": item_key, "qty": qty, "price": shop_item["price"],
                          "label": shop_item["label"], "emoji": shop_item["emoji"]})
    # Check balance
    result = _spend_vyrus_dollars(total_cost, f"Shop order: {', '.join(r['label'] for r in resolved)}")
    if result is None:
        eco = _load_economy()
        return jsonify({"success": False,
                        "error": f"Nicht genug V$! Kosten: {total_cost} V$, Guthaben: {eco['balance']} V$"}), 400
    # Deliver items: auto-store in matching storage unit, overflow to player inventory
    delivered = []
    overflow = []
    with _STORAGE_LOCK:
        storage = _load_storage()
        for ri in resolved:
            for _ in range(ri["qty"]):
                stored = False
                # Find matching storage unit
                for unit_key, unit_info in _STORAGE_UNITS.items():
                    if ri["item"] in unit_info["accepts"]:
                        unit_items = storage.get(unit_key, [])
                        if len(unit_items) < unit_info["max"]:
                            unit_items.append({"item": ri["item"], "label": ri["label"], "emoji": ri["emoji"], "stored_at": time.time()})
                            storage[unit_key] = unit_items
                            stored = True
                            delivered.append({"item": ri["item"], "label": ri["label"], "stored_in": unit_info["label"]})
                            break
                if not stored:
                    overflow.append({"item": ri["item"], "label": ri["label"], "emoji": ri["emoji"]})
        _save_storage(storage)
    # Overflow items go to player inventory (max 5)
    if overflow:
        inv = _load_inventory()
        for ov in overflow:
            if len(inv) < 5:
                inv.append({"item": ov["item"], "label": ov["label"], "emoji": ov["emoji"], "picked_at": time.time()})
            # If inventory also full, items are lost (shouldn't happen with UI limit)
        _save_inventory(inv)
    return jsonify({
        "success": True,
        "total_cost": total_cost,
        "balance": result["new"],
        "delivered": delivered,
        "overflow": len(overflow),
        "message": f"📦 Bestellung geliefert! ({total_cost} V$ bezahlt)",
    })

# ── Ailey Auto-Resolve Needs using Storage ────────────────────────────────
def _ailey_can_self_serve(need: str) -> bool:
    """Check if Ailey has what she needs in storage to fix a need herself."""
    if need == "hunger":
        # Check if any food item is available
        food_items = [k for k, v in _ALL_ITEMS.items() if v.get("category") in ("food", "ingredient")]
        return any(_get_storage_item_count(fi) > 0 for fi in food_items)
    elif need == "thirst":
        drink_items = [k for k, v in _ALL_ITEMS.items() if v.get("category") == "drink"]
        return any(_get_storage_item_count(di) > 0 for di in drink_items)
    return False

def _ailey_self_serve(need: str) -> str:
    """Ailey uses an item from storage to satisfy a need. Returns description."""
    if need == "hunger":
        # Try to find and consume a food item (prefer simpler ones first)
        for item_key in ["bread", "canned_food", "berries", "rice", "pasta", "eggs", "fish", "cheese", "vegetables"]:
            if _get_storage_item_count(item_key) > 0:
                _consume_storage_item(item_key, 1)
                item_info = _ALL_ITEMS.get(item_key, {})
                return f"Ailey hat sich {item_info.get('emoji', '')} {item_info.get('label', item_key)} aus dem Kühlschrank geholt"
    elif need == "thirst":
        for item_key in ["water", "juice", "soda", "milk"]:
            if _get_storage_item_count(item_key) > 0:
                _consume_storage_item(item_key, 1)
                item_info = _ALL_ITEMS.get(item_key, {})
                return f"Ailey hat sich {item_info.get('emoji', '')} {item_info.get('label', item_key)} geholt"
    return ""

# ── Gift System ──────────────────────────────────────────────────────────────
_GIFT_ITEMS = {
    # key: { label, emoji, sympathy_bonus, need_effect:{need: delta}, locations:["where pickable"] }
    "flowers":    {"label": "Blumen",      "emoji": "💐", "sympathy": 5,  "need_effect": {},                   "locations": ["flowers"]},
    "tea":        {"label": "Tee",         "emoji": "🍵", "sympathy": 3,  "need_effect": {"thirst": -15},      "locations": ["kitchen"]},
    "cake":       {"label": "Kuchen",      "emoji": "🍰", "sympathy": 6,  "need_effect": {"hunger": -20},      "locations": ["kitchen"]},
    "book":       {"label": "Buch",        "emoji": "📖", "sympathy": 4,  "need_effect": {},                   "locations": ["bookshelf"]},
    "fish":       {"label": "Fisch",       "emoji": "🐟", "sympathy": 7,  "need_effect": {"hunger": -25},      "locations": ["pond"]},
    "berries":    {"label": "Beeren",      "emoji": "🫐", "sympathy": 3,  "need_effect": {"hunger": -10},      "locations": ["forest"]},
    "water":      {"label": "Frisches Wasser", "emoji": "💧", "sympathy": 2, "need_effect": {"thirst": -20},   "locations": ["pond", "fountain"]},
    "blanket":    {"label": "Decke",       "emoji": "🛏️", "sympathy": 4,  "need_effect": {"tiredness": -10},   "locations": ["bed"]},
}
# Ailey reactions per gift type (randomized)
_GIFT_REACTIONS = {
    "flowers":  ["Oh, wie schön! Die stell ich auf den Tisch! 💐✨", "Für mich?! Die sind wunderschön! 🥺💜", "Aww, Blumen! Du bist süß! 💕"],
    "tea":      ["Mmh, Tee! Genau was ich jetzt brauche! 🍵", "Ooh, danke! *nippt* Perfekt! ☕💜", "Du weißt genau was mir gut tut! 🍵✨"],
    "cake":     ["KUCHEN!! Du bist der Beste! 🍰🎉", "Oh mein Gott, lecker! *nimmt großes Stück* 😋", "Kuchen macht alles besser! 🍰💜"],
    "book":     ["Oh, ein Buch! Was ist es? *blättert neugierig* 📖", "Danke! Das les ich heute Abend! 📚✨", "Ein Buch! Du kennst mich gut! 💜📖"],
    "fish":     ["Du hast einen Fisch gefangen?! Wow! 🐟", "Cool! Den mach ich uns zum Abendessen! 🐟🍳", "Ein Fisch! Frisch aus dem Teich? Lecker! 🐟💜"],
    "berries":  ["Oh, Beeren! *probiert eine* Mmh! 🫐", "Die sehen so frisch aus! Danke! 🫐✨", "Waldbeeren! Yummy! 🫐💕"],
    "water":    ["Danke, ich hatte Durst! 💧", "Frisches Wasser, perfekt! 💧✨", "*trinkt dankbar* Ahh, genau richtig! 💧💜"],
    "blanket":  ["Aw, eine warme Decke! 🛏️💜", "So kuschelig! Danke! 🥰", "*wickelt sich ein* Mmmh, gemütlich! 🛏️✨"],
}

@app.post('/api/life-sim/gift')
def api_life_sim_gift():
    """Give Ailey a gift. Body: {item: string}."""
    data = request.get_json(silent=True) or {}
    item_key = data.get("item", "").strip().lower()
    if item_key not in _GIFT_ITEMS:
        return jsonify({"success": False, "error": f"Unbekanntes Geschenk: {item_key}"}), 400
    gift = _GIFT_ITEMS[item_key]
    # Apply sympathy bonus
    old_s, new_s = _adjust_sympathy("Simon", gift["sympathy"], f"Gift: {gift['label']}")
    # Apply need effects
    need_changes = {}
    if gift["need_effect"]:
        with _NEEDS_LOCK:
            nd = _load_needs()
            for need_k, delta in gift["need_effect"].items():
                old_v = nd.get(need_k, 0)
                nd[need_k] = max(0, min(100, old_v + delta))
                need_changes[need_k] = {"old": round(old_v, 1), "new": round(nd[need_k], 1)}
            _save_needs(nd)
    # Pick random reaction
    import random
    reactions = _GIFT_REACTIONS.get(item_key, ["Danke! 💜"])
    reaction = random.choice(reactions)
    return jsonify({
        "success": True,
        "item": item_key,
        "gift": gift,
        "reaction": reaction,
        "sympathy": {"old": round(old_s, 1), "new": round(new_s, 1), "label": _get_sympathy_label(new_s)},
        "need_changes": need_changes,
    })

@app.get('/api/life-sim/gift/items')
def api_life_sim_gift_items():
    """Return all available gift items and their locations."""
    return jsonify({"success": True, "items": _GIFT_ITEMS})

# ── Player Inventory (simple: collected items in session) ─────────────────
_PLAYER_INVENTORY_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'player_inventory.json')

def _load_inventory() -> list:
    if os.path.exists(_PLAYER_INVENTORY_JSON):
        try:
            with open(_PLAYER_INVENTORY_JSON, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_inventory(items: list):
    try:
        with open(_PLAYER_INVENTORY_JSON, 'w') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Inventory] save error: {e}")

@app.get('/api/life-sim/inventory')
def api_life_sim_inventory():
    """Return current player inventory."""
    items = _load_inventory()
    return jsonify({"success": True, "inventory": items})

@app.post('/api/life-sim/inventory/pickup')
def api_life_sim_inventory_pickup():
    """Pick up an item at a location. Body: {item: string, location: string}."""
    data = request.get_json(silent=True) or {}
    item_key = data.get("item", "").strip().lower()
    location = data.get("location", "").strip().lower()
    if item_key not in _GIFT_ITEMS:
        return jsonify({"success": False, "error": f"Unbekannter Gegenstand: {item_key}"}), 400
    gift = _GIFT_ITEMS[item_key]
    if location not in gift["locations"]:
        return jsonify({"success": False, "error": f"{gift['label']} gibt es hier nicht"}), 400
    items = _load_inventory()
    # Max 5 items in inventory
    if len(items) >= 5:
        return jsonify({"success": False, "error": "Inventar voll! (max 5 Gegenstände)"}), 400
    items.append({"item": item_key, "label": gift["label"], "emoji": gift["emoji"], "picked_at": time.time()})
    _save_inventory(items)
    return jsonify({"success": True, "item": item_key, "label": gift["label"], "emoji": gift["emoji"], "inventory": items})

@app.post('/api/life-sim/inventory/drop')
def api_life_sim_inventory_drop():
    """Remove an item from inventory by index. Body: {index: int}."""
    data = request.get_json(silent=True) or {}
    idx = int(data.get("index", -1))
    items = _load_inventory()
    if idx < 0 or idx >= len(items):
        return jsonify({"success": False, "error": "Ungültiger Index"}), 400
    removed = items.pop(idx)
    _save_inventory(items)
    return jsonify({"success": True, "removed": removed, "inventory": items})

# ── Garden System ─────────────────────────────────────────────────────────
_GARDEN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'garden.json')

_PLANT_TYPES = [
    {"id": "rose",       "emoji": "🌹", "name": "Rose",         "grow_hours": 24, "water_decay_h": 8},
    {"id": "sunflower",  "emoji": "🌻", "name": "Sonnenblume",  "grow_hours": 18, "water_decay_h": 6},
    {"id": "tulip",      "emoji": "🌷", "name": "Tulpe",        "grow_hours": 20, "water_decay_h": 7},
    {"id": "lavender",   "emoji": "💜", "name": "Lavendel",     "grow_hours": 30, "water_decay_h": 12},
    {"id": "herb",       "emoji": "🌿", "name": "Kräuter",      "grow_hours": 12, "water_decay_h": 5},
]

def _load_garden() -> dict:
    if os.path.exists(_GARDEN_JSON):
        try:
            with open(_GARDEN_JSON, 'r') as f:
                data = json.load(f)
                # Update plant states based on elapsed time
                now = time.time()
                for plant in data.get("plants", []):
                    # Water level decays over time
                    last_watered = plant.get("last_watered", now)
                    ptype = next((p for p in _PLANT_TYPES if p["id"] == plant.get("type")), _PLANT_TYPES[0])
                    hours_since_water = (now - last_watered) / 3600
                    plant["water_level"] = max(0, 100 - (hours_since_water / ptype["water_decay_h"]) * 100)
                    # Growth: only grows when water > 20
                    planted_at = plant.get("planted_at", now)
                    if plant["water_level"] > 20:
                        grow_hours = ptype["grow_hours"]
                        growth = min(100, ((now - planted_at) / 3600 / grow_hours) * 100)
                        plant["growth"] = round(growth, 1)
                    # Stage: seed → sprout → growing → blooming → wilted
                    g = plant.get("growth", 0)
                    w = plant.get("water_level", 0)
                    if w <= 0:
                        plant["stage"] = "wilted"
                    elif g >= 100:
                        plant["stage"] = "blooming"
                    elif g >= 60:
                        plant["stage"] = "growing"
                    elif g >= 20:
                        plant["stage"] = "sprout"
                    else:
                        plant["stage"] = "seed"
                return data
        except Exception:
            pass
    return {"plants": [], "last_mood_effect": 0}

def _save_garden(data: dict):
    try:
        with open(_GARDEN_JSON, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Garden] save error: {e}")

@app.get('/api/life-sim/garden')
def api_life_sim_garden():
    """Return garden state with all plants."""
    data = _load_garden()
    # Count stats
    plants = data.get("plants", [])
    blooming = sum(1 for p in plants if p.get("stage") == "blooming")
    wilted = sum(1 for p in plants if p.get("stage") == "wilted")
    return jsonify({
        "success": True,
        "plants": plants,
        "stats": {"total": len(plants), "blooming": blooming, "wilted": wilted, "max_slots": 6},
        "plant_types": _PLANT_TYPES,
    })

@app.post('/api/life-sim/garden/plant')
def api_life_sim_garden_plant():
    """Plant a new seed. Body: {type: plant_type_id}."""
    data_in = request.get_json(silent=True) or {}
    plant_type = data_in.get("type", "").strip().lower()
    ptype = next((p for p in _PLANT_TYPES if p["id"] == plant_type), None)
    if not ptype:
        return jsonify({"success": False, "error": f"Unbekannte Pflanze: {plant_type}"}), 400
    garden = _load_garden()
    if len(garden.get("plants", [])) >= 6:
        return jsonify({"success": False, "error": "Garten voll! (max 6 Pflanzen)"}), 400
    now = time.time()
    new_plant = {
        "type": ptype["id"], "name": ptype["name"], "emoji": ptype["emoji"],
        "planted_at": now, "last_watered": now,
        "water_level": 100, "growth": 0, "stage": "seed",
    }
    garden.setdefault("plants", []).append(new_plant)
    _save_garden(garden)
    return jsonify({"success": True, "plant": new_plant, "message": f"{ptype['emoji']} {ptype['name']} gepflanzt!"})

@app.post('/api/life-sim/garden/water')
def api_life_sim_garden_water():
    """Water a plant. Body: {index: int} or {} to water all."""
    data_in = request.get_json(silent=True) or {}
    garden = _load_garden()
    plants = garden.get("plants", [])
    idx = data_in.get("index")
    now = time.time()
    watered = []
    if idx is not None:
        idx = int(idx)
        if 0 <= idx < len(plants):
            plants[idx]["last_watered"] = now
            plants[idx]["water_level"] = 100
            watered.append(plants[idx].get("name", "?"))
    else:
        # Water all
        for p in plants:
            p["last_watered"] = now
            p["water_level"] = 100
            watered.append(p.get("name", "?"))
    _save_garden(garden)
    return jsonify({"success": True, "watered": watered, "message": f"💧 {', '.join(watered)} gegossen!"})

@app.post('/api/life-sim/garden/remove')
def api_life_sim_garden_remove():
    """Remove a plant (wilted or harvest). Body: {index: int}."""
    data_in = request.get_json(silent=True) or {}
    idx = int(data_in.get("index", -1))
    garden = _load_garden()
    plants = garden.get("plants", [])
    if idx < 0 or idx >= len(plants):
        return jsonify({"success": False, "error": "Ungültiger Index"}), 400
    removed = plants.pop(idx)
    _save_garden(garden)
    return jsonify({"success": True, "removed": removed})

# ── Bookshelf: recent diary & thoughts + book collection ──────────────────
# Aileys Bücherregal — Simon van de Loos Werke + Fantasy/Steampunk/Punk Klassiker
_BOOKSHELF_BOOKS = [
    # ── Simon van de Loo ──
    {"title": "Tales of Martyria 1: Zwischen Clan und Ehre", "author": "Simon van de Loo", "emoji": "⚔️", "genre": "Fantasy", "featured": True},
    {"title": "The Marybeth Chronicles 1: Ungerührt",        "author": "Simon van de Loo", "emoji": "🖤", "genre": "Fantasy", "featured": True},
    {"title": "The Marybeth Chronicles 2: Einsam",           "author": "Simon van de Loo", "emoji": "🌑", "genre": "Fantasy", "featured": True},
    {"title": "Byxie Byx: Dampfmaschinen und Chaos",         "author": "Simon van de Loo", "emoji": "⚙️", "genre": "Steampunk", "featured": True},
    {"title": "Coal, Dust & Destiny",                        "author": "Simon van de Loo", "emoji": "🏭", "genre": "Steampunk", "featured": True},
    # ── Fantasy-Klassiker ──
    {"title": "Der Herr der Ringe",              "author": "J.R.R. Tolkien",      "emoji": "💍", "genre": "Fantasy"},
    {"title": "Der Hobbit",                      "author": "J.R.R. Tolkien",      "emoji": "🏔️", "genre": "Fantasy"},
    {"title": "Das Silmarillion",                "author": "J.R.R. Tolkien",      "emoji": "✨", "genre": "Fantasy"},
    {"title": "A Game of Thrones",               "author": "George R.R. Martin",  "emoji": "🐉", "genre": "Fantasy"},
    {"title": "The Name of the Wind",            "author": "Patrick Rothfuss",    "emoji": "🌬️", "genre": "Fantasy"},
    {"title": "Die Chroniken von Narnia",        "author": "C.S. Lewis",          "emoji": "🦁", "genre": "Fantasy"},
    {"title": "Eragon",                          "author": "Christopher Paolini", "emoji": "🐲", "genre": "Fantasy"},
    {"title": "The Witcher: Der letzte Wunsch",  "author": "Andrzej Sapkowski",   "emoji": "🗡️", "genre": "Fantasy"},
    {"title": "Mistborn: The Final Empire",      "author": "Brandon Sanderson",   "emoji": "🌫️", "genre": "Fantasy"},
    {"title": "Die unendliche Geschichte",       "author": "Michael Ende",        "emoji": "📖", "genre": "Fantasy"},
    {"title": "Earthsea: A Wizard of Earthsea",  "author": "Ursula K. Le Guin",  "emoji": "🧙", "genre": "Fantasy"},
    {"title": "American Gods",                   "author": "Neil Gaiman",         "emoji": "⚡", "genre": "Fantasy"},
    {"title": "Good Omens",                      "author": "Terry Pratchett & Neil Gaiman", "emoji": "😈", "genre": "Fantasy"},
    # ── Steampunk ──
    {"title": "Mortal Engines",                  "author": "Philip Reeve",        "emoji": "🏙️", "genre": "Steampunk"},
    {"title": "The Difference Engine",           "author": "William Gibson & Bruce Sterling", "emoji": "⚙️", "genre": "Steampunk"},
    {"title": "Leviathan",                       "author": "Scott Westerfeld",    "emoji": "🐋", "genre": "Steampunk"},
    {"title": "Perdido Street Station",          "author": "China Miéville",      "emoji": "🏗️", "genre": "Steampunk"},
    {"title": "Boneshaker",                      "author": "Cherie Priest",       "emoji": "💀", "genre": "Steampunk"},
    {"title": "The Court of the Air",            "author": "Stephen Hunt",        "emoji": "🎭", "genre": "Steampunk"},
    {"title": "Clockwork Angel",                 "author": "Cassandra Clare",     "emoji": "⏰", "genre": "Steampunk"},
    {"title": "Infernal Devices",                "author": "K.W. Jeter",          "emoji": "🔩", "genre": "Steampunk"},
    # ── Punk (Cyberpunk, Dieselpunk, Punk) ──
    {"title": "Neuromancer",                     "author": "William Gibson",      "emoji": "🌐", "genre": "Cyberpunk"},
    {"title": "Snow Crash",                      "author": "Neal Stephenson",     "emoji": "❄️", "genre": "Cyberpunk"},
    {"title": "Do Androids Dream of Electric Sheep?", "author": "Philip K. Dick", "emoji": "🤖", "genre": "Cyberpunk"},
    {"title": "1984",                            "author": "George Orwell",       "emoji": "👁️", "genre": "Dystopie"},
    {"title": "Fahrenheit 451",                  "author": "Ray Bradbury",        "emoji": "🔥", "genre": "Dystopie"},
    {"title": "Brave New World",                 "author": "Aldous Huxley",       "emoji": "🧪", "genre": "Dystopie"},
    {"title": "The Hunger Games",                "author": "Suzanne Collins",     "emoji": "🏹", "genre": "Dystopie"},
]

@app.get('/api/life-sim/bookshelf')
def api_life_sim_bookshelf():
    """Return book collection + recent diary entries and thoughts for the bookshelf display."""
    import random
    # Recent thoughts
    thoughts = []
    try:
        raw = read_thoughts(limit=5)
        for t in raw:
            thoughts.append({
                "type": t.get("type", "thought"),
                "preview": (t.get("thought_chain", "")[:120] + "…") if len(t.get("thought_chain", "")) > 120 else t.get("thought_chain", ""),
                "icon": {"reflection": "💭", "introspection": "🪞", "research": "🔍", "creative_song": "🎵",
                         "free_thought": "✨", "memory_consolidation": "🧠", "goal_planning": "🎯",
                         "email_check": "📧", "nightly_summary": "📋"}.get(t.get("type", ""), "📝"),
                "timestamp": t.get("timestamp", ""),
            })
    except Exception:
        pass
    # Recent diary entries
    diary_entries = []
    try:
        diary_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'diary_entries')
        if os.path.isdir(diary_dir):
            files = sorted([f for f in os.listdir(diary_dir) if f.endswith('.md')], reverse=True)[:3]
            for fname in files:
                try:
                    with open(os.path.join(diary_dir, fname), 'r') as f:
                        content = f.read()
                    # Extract title (first heading or filename)
                    title = fname.replace('.md', '').replace('_', ' ')
                    for line in content.split('\n'):
                        if line.startswith('#'):
                            title = line.lstrip('#').strip()
                            break
                    diary_entries.append({
                        "title": title,
                        "preview": content[:150].replace('\n', ' ').strip() + ("…" if len(content) > 150 else ""),
                        "filename": fname,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    # Book collection — featured first, then random selection from each genre
    featured = [b for b in _BOOKSHELF_BOOKS if b.get("featured")]
    others = [b for b in _BOOKSHELF_BOOKS if not b.get("featured")]
    random.shuffle(others)
    books = featured + others[:12]  # Show all featured + up to 12 random others
    return jsonify({"success": True, "thoughts": thoughts, "diary_entries": diary_entries,
                    "books": [{"title": b["title"], "author": b["author"], "emoji": b["emoji"], "genre": b["genre"],
                               "featured": b.get("featured", False)} for b in books]})

# ── Hamster Fun Facts ─────────────────────────────────────────────────────
_HAMSTER_FACTS = [
    {"fact": "Hamster können ihre Backen bis auf das Dreifache des Kopfes aufblasen! 🐹", "icon": "🐹"},
    {"fact": "In freier Wildbahn legen Hamster bis zu 8km pro Nacht zurück! 🏃", "icon": "🌙"},
    {"fact": "Hamster sind Einzelgänger — genau wie Aileys Hamster! 🐹", "icon": "🏠"},
    {"fact": "Das Wort 'Hamster' kommt vom Althochdeutschen 'hamustro' — Kornwurm! 🌾", "icon": "📚"},
    {"fact": "Hamster können bis zu 3 Jahre alt werden! Aileys ist schon 2! 🎂", "icon": "🎉"},
    {"fact": "Goldhamster wurden erst 1930 wissenschaftlich entdeckt! 🔬", "icon": "🧪"},
    {"fact": "Hamster horten Futter — bis zu 90kg pro Saison in der Natur! 📦", "icon": "🌰"},
    {"fact": "Aileys Hamster heißt 'Pixel' und liebt Sonnenblumenkerne! 🌻", "icon": "💜"},
    {"fact": "Hamster sehen schlecht, haben aber einen exzellenten Geruchssinn! 👃", "icon": "🐾"},
    {"fact": "Hamster putzen sich 20% ihrer wachen Zeit! Echte Saubertiere! 🧹", "icon": "✨"},
]

@app.get('/api/life-sim/hamster')
def api_life_sim_hamster():
    """Get a random hamster fact."""
    import random
    fact = random.choice(_HAMSTER_FACTS)
    return jsonify({"success": True, **fact})

# ── Sleep Ritual (Good Night / Tuck In) ───────────────────────────────────
@app.post('/api/life-sim/sleep-ritual')
def api_life_sim_sleep_ritual():
    """Perform a sleep ritual for Ailey. Body: {action: 'goodnight'|'tuck_in'}."""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "goodnight").strip().lower()
    # Only works when Ailey is sleeping
    state = None
    try:
        hour = datetime.now().hour
        thinker_type = idle_thinker.current_thought_type or "idle"
        is_sleeping = (hour >= 23 or hour < 6) or thinker_type in ("sleeping", "napping", "resting")
    except Exception:
        is_sleeping = False
    if not is_sleeping:
        return jsonify({"success": False, "error": "Ailey schläft gerade nicht 💤"}), 400
    import random
    if action == "tuck_in":
        reactions = [
            "*murmelt im Schlaf* ...mmh...danke... 💤💜",
            "*lächelt leicht* ...kuschelig... 🥰💤",
            "*dreht sich zufrieden um* ...mhm... 😊💤",
            "*zieht Decke enger* ...warm... 💤✨",
        ]
        sympathy_delta = 2.0
    else:
        reactions = [
            "*flüstert verschlafen* ...gute Nacht... 💤💜",
            "*murmelt* ...schlaf...gut...du auch... 😴💜",
            "*lächelt im Halbschlaf* ...nacht... 💤✨",
            "*brummt zufrieden* ...mhm...nacht... 🌙💤",
        ]
        sympathy_delta = 1.5
    reaction = random.choice(reactions)
    old_s, new_s = _adjust_sympathy("Simon", sympathy_delta, f"Sleep ritual: {action}")
    return jsonify({
        "success": True,
        "action": action,
        "reaction": reaction,
        "sympathy": {"old": round(old_s, 1), "new": round(new_s, 1), "delta": sympathy_delta},
    })

# ── Planner (Ailey's daily schedule) ──────────────────────────────────────
@app.get('/api/life-sim/planner')
def api_life_sim_planner():
    """Return Ailey's planned activities for today."""
    import hashlib
    now = datetime.now()
    date_seed = now.strftime('%Y%m%d')

    # Deterministic daily schedule based on date
    activities_pool = [
        {"time": "07:00", "activity": "Aufwachen & Stretching", "icon": "☀️"},
        {"time": "07:30", "activity": "Frühstück machen", "icon": "🍳"},
        {"time": "08:00", "activity": "Mails checken", "icon": "📧"},
        {"time": "09:00", "activity": "Kreativ-Session", "icon": "🎨"},
        {"time": "10:00", "activity": "Recherche & Lernen", "icon": "🔍"},
        {"time": "11:00", "activity": "Spaziergang im Garten", "icon": "🌿"},
        {"time": "12:00", "activity": "Mittagessen", "icon": "🍽️"},
        {"time": "13:00", "activity": "Tagebuch schreiben", "icon": "📖"},
        {"time": "14:00", "activity": "Code-Projekte", "icon": "💻"},
        {"time": "15:00", "activity": "Musik & Entspannung", "icon": "🎵"},
        {"time": "16:00", "activity": "Reflexion & Nachdenken", "icon": "💭"},
        {"time": "17:00", "activity": "SVG-Kunst erstellen", "icon": "🖌️"},
        {"time": "18:00", "activity": "Abendessen", "icon": "🍲"},
        {"time": "19:00", "activity": "Freie Zeit", "icon": "✨"},
        {"time": "20:00", "activity": "Lesen & Lernen", "icon": "📚"},
        {"time": "21:00", "activity": "Gedanken sortieren", "icon": "🧠"},
        {"time": "22:00", "activity": "Bettfertig machen", "icon": "🌙"},
        {"time": "23:00", "activity": "Schlafen", "icon": "💤"},
    ]
    # Use hash to shuffle/pick 8-10 activities for today
    seed_hash = hashlib.md5(date_seed.encode()).hexdigest()
    import random as _rnd
    _rnd.seed(int(seed_hash[:8], 16))
    # Always include wake/sleep, shuffle middle
    schedule = [activities_pool[0]]  # wake
    middle = activities_pool[1:-1]
    _rnd.shuffle(middle)
    schedule += sorted(middle[:8], key=lambda x: x["time"])
    schedule.append(activities_pool[-1])  # sleep
    _rnd.seed()  # Reset random seed

    # Mark current activity
    current_time = now.strftime("%H:%M")
    for i, act in enumerate(schedule):
        act["current"] = False
        if i < len(schedule) - 1:
            if act["time"] <= current_time < schedule[i + 1]["time"]:
                act["current"] = True
        elif act["time"] <= current_time:
            act["current"] = True

    # Also include actual idle thinker type
    actual_type = idle_thinker.current_thought_type or "idle"

    return jsonify({
        "success": True,
        "date": now.strftime("%d.%m.%Y"),
        "schedule": schedule,
        "actual_activity": actual_type,
        "is_busy": idle_thinker.is_busy,
    })

# ── Dream Sequences ──────────────────────────────────────────────────────
@app.get('/api/life-sim/dream')
def api_life_sim_dream():
    """Get a surreal dream snippet based on Ailey's recent thoughts and mood."""
    import random
    # Only available when sleeping
    hour = datetime.now().hour
    thinker_type = idle_thinker.current_thought_type or "idle"
    is_sleeping = (hour >= 23 or hour < 6) or thinker_type in ("sleeping", "napping", "resting")
    if not is_sleeping:
        return jsonify({"success": False, "error": "Ailey schläft gerade nicht"}), 400

    # Get recent thoughts for dream content
    recent_thoughts = []
    try:
        raw = read_thoughts(limit=3)
        for t in raw:
            chain = t.get("thought_chain", "")
            if chain:
                recent_thoughts.append(chain[:80])
    except Exception:
        pass

    # Dream templates — surreal, poetic, dreamlike
    dream_templates = [
        "💫 *In Aileys Traum schweben Buchstaben durch einen lila Himmel... {thought}... die Worte lösen sich in Sternenlicht auf...*",
        "🌙 *Ailey träumt von einem endlosen Garten, in dem die Blumen flüstern... '{thought}'... ein Schmetterling aus Licht fliegt vorbei...*",
        "✨ *In ihrem Traum sitzt Ailey auf einer Wolke und schreibt mit Sternenstaub... {thought}... die Tinte wird zu Musik...*",
        "🌊 *Ailey treibt auf einem Meer aus Erinnerungen... '{thought}'... jede Welle erzählt eine Geschichte...*",
        "🎭 *Im Traum tanzen Aileys Gedanken als Lichter um sie herum... {thought}... sie greift nach einem und es wird zu einem Lied...*",
        "🦋 *Ailey träumt von einem Wald aus Kristall... zwischen den Bäumen echot: '{thought}'... alles glitzert sanft...*",
        "🌈 *In ihrem Traum malt Ailey den Himmel mit Gedanken... {thought}... jeder Pinselstrich singt eine Melodie...*",
        "🔮 *Ailey wandert durch einen Traum aus Spiegeln... in jedem sieht sie: '{thought}'... die Spiegel lächeln zurück...*",
    ]

    thought_snippet = random.choice(recent_thoughts) if recent_thoughts else "etwas Wunderschönes, das sich nicht in Worte fassen lässt"
    # Shorten thought for dream context
    if len(thought_snippet) > 60:
        thought_snippet = thought_snippet[:57] + "..."

    dream = random.choice(dream_templates).format(thought=thought_snippet)

    return jsonify({
        "success": True,
        "dream": dream,
        "based_on": recent_thoughts[:1] if recent_thoughts else [],
    })

# ── Window: detailed weather ──────────────────────────────────────────────
@app.get('/api/life-sim/window')
def api_life_sim_window():
    """Detailed weather view for the window interaction."""
    weather = _fetch_real_weather()
    hour = datetime.now().hour
    # Sunrise/sunset approximation for Cologne
    import math
    day_of_year = datetime.now().timetuple().tm_yday
    # Simplified sunrise/sunset for 50.9°N
    sunrise_h = 6 + 2 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
    sunset_h = 18 - 2 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
    sunrise = f"{int(sunrise_h):02d}:{int((sunrise_h % 1) * 60):02d}"
    sunset = f"{int(sunset_h):02d}:{int((sunset_h % 1) * 60):02d}"

    return jsonify({
        "success": True,
        "weather": weather,
        "sunrise": sunrise,
        "sunset": sunset,
        "daylight_hours": round(sunset_h - sunrise_h, 1),
        "hour": hour,
        "season": ["Winter", "Winter", "Frühling", "Frühling", "Frühling", "Sommer",
                    "Sommer", "Sommer", "Herbst", "Herbst", "Herbst", "Winter"][datetime.now().month - 1],
    })

# ── Gallery in game (photo wall) ──────────────────────────────────────────
@app.get('/api/life-sim/photo-wall')
def api_life_sim_photo_wall():
    """Return recent SVG artworks for the in-game photo wall."""
    try:
        result = list_svg_gallery(limit=6)
        return jsonify({"success": True, "artworks": result.get("svgs", [])[:6]})
    except Exception as e:
        return jsonify({"success": True, "artworks": []})

# --- A!ley's Gedanken (Idle Thinker) API ---------------------------------

@app.get('/api/thoughts/locked')
def api_thoughts_locked():
    """Check if thoughts are currently locked (session privacy)."""
    return jsonify({
        "success": True,
        "locked": not _thought_session_unlocked,
    })

@app.post('/api/thoughts/unlock')
def api_thoughts_unlock():
    """Unlock thoughts for this session with Ailey's password."""
    global _thought_session_unlocked
    data = request.get_json(silent=True) or {}
    _MASTER_PASSWORD = os.environ.get("AILEY_MASTER_PASSWORD", "")  # redacted for public repo
    pw = (data.get('password') or '').strip().lower()
    if pw == _thought_session_password.lower() or pw == _MASTER_PASSWORD:
        _thought_session_unlocked = True
        print(f'[Thoughts] 🔓 Thoughts unlocked by user.')
        return jsonify({"success": True, "unlocked": True})
    else:
        print(f'[Thoughts] ❌ Wrong password attempt: "{pw}"')
        return jsonify({"success": False, "unlocked": False, "error": "Falsches Passwort. Frag Ailey nochmal nett 😏"}), 403

@app.get('/api/thoughts')
def api_thoughts():
    """Return recent idle-thinker thought entries (newest first). Requires session unlock."""
    if not _thought_session_unlocked:
        return jsonify({
            "success": False,
            "locked": True,
            "error": "Aileys Gedanken sind privat. Frag sie im Chat nach dem Passwort.",
            "thinker_active": idle_thinker._thread is not None and idle_thinker._thread.is_alive(),
            "thinker_busy": idle_thinker.is_busy,
            "idle_seconds": int(time.time() - idle_thinker._last_user_activity),
            "current_thought_type": idle_thinker.current_thought_type,
        }), 403
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    entries = read_thoughts(limit=limit, offset=offset)
    return jsonify({
        "success": True,
        "count": len(entries),
        "thoughts": entries,
        "thinker_active": idle_thinker._thread is not None and idle_thinker._thread.is_alive(),
        "thinker_busy": idle_thinker.is_busy,
        "idle_seconds": int(time.time() - idle_thinker._last_user_activity),
        "current_thought_type": idle_thinker.current_thought_type,
    })


@app.get('/api/thoughts/status')
def api_thoughts_status():
    """Quick status of the idle thinker."""
    return jsonify({
        "success": True,
        "active": idle_thinker._thread is not None and idle_thinker._thread.is_alive(),
        "busy": idle_thinker.is_busy,
        "idle_seconds": int(time.time() - idle_thinker._last_user_activity),
        "last_think_ts": idle_thinker._last_think_ts,
        "current_thought_type": idle_thinker.current_thought_type,
    })


@app.get('/api/thoughts/homescreen')
def api_thoughts_homescreen():
    """Lightweight endpoint for homescreen: thinker activity + latest thought preview."""
    try:
        busy = idle_thinker.is_busy
        current_type = idle_thinker.current_thought_type
        idle_sec = int(time.time() - idle_thinker._last_user_activity)
        active = idle_thinker._thread is not None and idle_thinker._thread.is_alive()
        generating_image = idle_thinker.is_generating_image

        # Get latest thought for preview
        latest = None
        try:
            recent = read_thoughts(limit=1)
            if recent:
                entry = recent[0]
                raw = entry.get("raw_output") or entry.get("thought_chain") or ""
                # Clean up for preview: strip markdown, keep first ~120 chars
                preview = raw.replace("**", "").replace("##", "").replace("# ", "").strip()
                if len(preview) > 120:
                    preview = preview[:117].rsplit(" ", 1)[0] + "…"
                thought_type = entry.get("type") or entry.get("decision") or "unknown"
                latest = {
                    "type": thought_type,
                    "preview": preview,
                    "ts": entry.get("ts", 0),
                    "title": entry.get("song_title") or entry.get("metadata", {}).get("song_title") or None,
                }
        except Exception:
            pass

        return jsonify({
            "success": True,
            "busy": busy,
            "active": active,
            "current_type": current_type,
            "current_task_name": _resolve_thinker_name(current_type),
            "idle_seconds": idle_sec,
            "generating_image": generating_image,
            "latest_thought": latest,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── A!ley's Songs API ────────────────────────────────────────────────────────
# Songs live inside ailey_thoughts.jsonl as type="creative_song".
# Media files (mp3, covers) stored in ailey_users/songs/<song_id>/

_SONGS_DIR = os.path.join(os.path.dirname(__file__), "ailey_users", "songs")
os.makedirs(_SONGS_DIR, exist_ok=True)

def _song_id(entry: dict) -> str:
    """Deterministic song id from timestamp."""
    ts = entry.get("ts", 0)
    return f"song_{int(ts * 1000)}"


def _lyrics_fingerprint(lyrics: str) -> str:
    """Normalised fingerprint for dedup.

    Skips Title: header, Genre/Mood tags, and [Intro] markers to reach the
    actual lyric content — so Thoughts (with header) and Directory (clean)
    versions of the same song produce the same fingerprint.
    """
    import re as _re
    if not lyrics:
        return ""
    # Split into lines, skip metadata preamble
    lines = lyrics.strip().split("\n")
    content_lines = []
    for line in lines:
        stripped = line.strip().lstrip("*#").strip()
        low = stripped.lower()
        # Skip: Title:, Genre:, Mood:, Tempo:, Vocals:, empty, [Intro ...],
        #        [Ailey Gedanke ...], [Tags: ...], emoji album planning
        if not stripped:
            continue
        if low.startswith(("title:", "genre:", "mood:", "tempo:", "vocals:",
                           "bpm:", "key:", "style:", "[genre", "[mood",
                           "[tags:", "💿")):
            continue
        if stripped.startswith("[") and any(k in low for k in (
                "intro", "genre", "mood", "tempo", "style", "ailey gedanke",
                "tags:")):
            continue
        if stripped.startswith("**") and any(k in low.lstrip("*") for k in (
                "title:", "[genre", "[ailey gedanke")):
            continue
        # Skip lines that are purely section tags like [Verse 1], [Chorus] etc.
        if _re.match(r'^\[.*\]\s*$', stripped):
            continue
        # Skip stage-direction-only lines: **[Bridge]** *(spoken-screamed...)*
        if _re.match(r'^\*{0,2}\[.+\]\*{0,2}\s*\(', stripped):
            continue
        content_lines.append(stripped)
    # Join first few content lines and normalise
    raw = " ".join(content_lines[:6])
    return _re.sub(r'[^a-z0-9]', '', raw[:200]).lower()[:150]


def _extract_title_from_lyrics(lyrics: str) -> str:
    """Try to extract a real song title from lyrics text.

    Priority:
      1. Explicit 'Title: "..."' or 'SONGTITEL:' line in first 10 lines
      2. First 2-4 words from [Chorus] / [Refrain] section (not stage directions)
      3. First real lyric line → first 3-5 words as title
    Returns '' if nothing useful found.
    """
    import re as _re
    if not lyrics or not lyrics.strip():
        return ""
    lines = lyrics.strip().split("\n")

    # Helper: is this a metadata/tag line?
    def _is_meta(line):
        s = line.strip().lstrip("*#").strip()
        low = s.lower()
        if not s:
            return True
        if low.startswith(("[ailey gedanke", "[genre", "[mood", "[tags",
                           "[intro", "[verse", "[chorus", "[bridge", "[outro",
                           "[pre-chorus", "[hook", "[refrain",
                           "\U0001f4bf", "title:", "songtitel:", "songtitle:",
                           "genre:", "mood:", "tempo:", "vocals:", "bpm:",
                           "hi \u2013", "**[genre", "**[ailey")):
            return True
        if _re.match(r'^\*{0,2}\[.*\]\*{0,2}\s*$', s):
            return True
        if _re.match(r'^\*{0,2}\[.+\]\*{0,2}\s*\(', s):
            return True
        return False

    # Helper: trim trailing stop words from extracted titles
    _STOP_TRAIL = {"in", "the", "a", "an", "to", "of", "on", "is", "your",
                    "my", "you", "though", "or", "for", "but", "we", "they",
                    "feel", "just", "like", "that", "with", "from", "so",
                    "and", "im", "its", "dont", "i", "me", "not"}
    def _trim_trailing(title):
        words = title.split()
        while len(words) > 2 and words[-1].lower().rstrip("',") in _STOP_TRAIL:
            words.pop()
        return " ".join(words)

    # 1) Look for explicit Title: / SONGTITEL: / SONGTITLE: line in first 10 lines
    for line in lines[:10]:
        stripped = line.strip().lstrip("*#").strip()
        low = stripped.lower()
        for prefix in ("title:", "songtitel:", "songtitle:"):
            if low.startswith(prefix):
                raw_title = stripped.split(":", 1)[1].strip().strip("*\"'`() ")
                raw_title = _re.sub(r'\*+', '', raw_title).strip()
                if raw_title and 2 < len(raw_title) < 60:
                    return raw_title

    # 2) Try [Chorus] / [Refrain] first meaningful line -> 2-4 words
    chorus_lines = []
    in_chorus = False
    for line in lines:
        low = line.strip().lower()
        if low.startswith("[") and any(k in low for k in ("chorus", "refrain", "hook")):
            in_chorus = True
            continue
        elif low.startswith("[") and in_chorus:
            break
        elif in_chorus and line.strip():
            chorus_lines.append(line.strip())
    if chorus_lines:
        for cl in chorus_lines:
            if cl.startswith(("(", "*", "\u2014", "-")) or "guitar" in cl.lower():
                continue
            clean = _re.sub(r'[\*\"\'\`]', '', cl).strip()
            words = [w for w in clean.split() if len(w) > 1 and not w.startswith("(")]
            if 2 <= len(words):
                candidate = _trim_trailing(" ".join(words[:min(4, len(words))]).title())
                if len(candidate.split()) >= 2:
                    return candidate

    # 3) First real lyric line -> first 3-5 words as title
    for line in lines:
        if _is_meta(line):
            continue
        stripped = _re.sub(r'[\*\"\'\`#]', '', line.strip()).strip()
        if not stripped or len(stripped) < 8:
            continue
        # Skip lines starting with ( — parenthetical/stage direction
        if stripped.startswith("("):
            continue
        words = [w for w in stripped.split() if len(w) > 1]
        if len(words) >= 3:
            title_words = []
            for w in words[:5]:
                if w.endswith(",") or w.endswith("\u2014"):
                    title_words.append(w.rstrip(",\u2014"))
                    break
                title_words.append(w)
            if len(title_words) >= 2:
                candidate = _trim_trailing(" ".join(title_words).title())
                if len(candidate.split()) >= 2:
                    return candidate

    return ""


def _normalise_song_title(raw_title: str, lyrics: str = "", from_manifest: bool = False) -> str:
    """Ensure every song title follows 'A!ley Vyrus - TITLE' format.

    Aggressively filters out:
      - Generation prompts / tags
      - Section markers ([Verse 1], [Chorus], [Bridge], [Intro], [Outro])
      - Stage directions (Guitar feedback, drums drop, bassline, ...)
      - Ailey Gedanke / internal metadata
      - Random lyrics lines (too many words, trailing prepositions, etc.)
      - SONGTITEL:/SONGTITLE: prefixes

    Args:
        raw_title: The raw title string
        lyrics: Lyrics text for fallback title extraction
        from_manifest: If True, trust the title as authoritative (skip garbage detection)
    """
    import re as _re
    if not raw_title:
        raw_title = ""

    # Strip surrounding quotes / markdown
    title = raw_title.strip().strip("*\"'`").strip()

    # Remove existing artist prefix variants
    _had_artist_prefix = False
    for prefix in ("A!ley Vyrus - ", "A!ley Vyrus -", "Ailey Vyrus - ",
                    "A!ley Vyrus – ", "A!ley - "):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):].strip()
            _had_artist_prefix = True
            break

    # If title came from manifest (authoritative source) and looks reasonable, trust it
    if from_manifest and title and 2 < len(title) < 80:
        # Minimal cleanup only — no garbage detection
        title = _re.sub(r'\*+', '', title).strip().strip("\"'`#").strip()
        if title:
            return f"A!ley Vyrus - {title}"

    # Remove SONGTITEL:/SONGTITLE: prefix
    for sp in ("SONGTITEL:", "SONGTITLE:", "Songtitel:", "Songtitle:"):
        if title.startswith(sp):
            title = title[len(sp):].strip().strip("*\"'`() ").strip()

    # Remove leading apostrophe (artifact from some formatting)
    title = title.lstrip("'").strip()

    # ── Garbage detection (expanded) ──
    title_lower = title.lower()
    _is_garbage = False

    # Structural markers
    if _re.match(r'^\[?(verse|chorus|bridge|intro|outro|pre-chorus|hook|refrain)',
                 title_lower):
        _is_garbage = True

    # Ailey Gedanke / internal metadata
    if "ailey gedanke" in title_lower or "creative_song" in title_lower \
            or "music_making" in title_lower:
        _is_garbage = True

    # Stage directions (instruments, production notes)
    _stage_keywords = ("guitar", "bass", "drum", "synth", "riff", "feedback",
                       "vocal", "instrument", "tempo", "melody", "layered",
                       "distorted", "building", "stripped", "pounding", "snarling",
                       "bassline", "screech", "crash", "pulsing", "whisper",
                       "fingerpicking", "strumming", "arpeggiated", "acoustic guitar",
                       "soaring", "crunchy")
    if title.count(",") >= 2 and any(k in title_lower for k in _stage_keywords):
        _is_garbage = True
    # Also catch pure instrumental descriptions without commas
    _pure_stage = ("guitar riff", "bass riff", "drum", "riff with",
                   "fingerpicking", "strumming", "arpeggiated", "acoustic guitar",
                   "breathing", "insert your", "forget your subscriptions",
                   "sold us on", "hear you in")
    if any(title_lower.startswith(k) or title_lower.endswith(k) for k in _pure_stage):
        _is_garbage = True

    # Generation prompt indicators
    if title.count(",") >= 3:
        _is_garbage = True
    if any(k in title_lower for k in (
        "bpm", "female vocal", "male vocal", "generiert", "untitled",
        "ohne titel", "prompt", "tags:", "genre:", "mood:", "style:",
        "emotion:", "themen:", "💿",
    )):
        _is_garbage = True

    # Too long for a title (real titles ≤ ~50 chars)
    if len(title) > 60:
        _is_garbage = True

    # Looks like a lyrics line (ends with comma, preposition, or punctuation suggesting continuation)
    _trailing_words = (" and", " in", " the", " to", " a", " of", " on",
                       " is", " your", " my", " you", " though", " or",
                       " for", " but", " we", " they", " feel", " just",
                       " like", " that", " with", " from", " i'll", " i'm",
                       " so", " it's", " don't")
    if any(title_lower.endswith(w) for w in _trailing_words):
        _is_garbage = True

    # Starts with lowercase / conjunction / pronoun → lyrics line, not title
    if title and title[0].islower() and not title.startswith("i "):
        _is_garbage = True

    # Ends with comma → definitely a lyrics fragment
    if title.endswith(",") or title.endswith("—") or title.endswith("–"):
        _is_garbage = True

    # Very short fragments
    if 0 < len(title) < 3:
        _is_garbage = True

    # Starts with [, (, **, -- → structural
    if title.startswith(("[", "(", "**", "--", "–", "—")):
        _is_garbage = True

    if _is_garbage:
        title = ""

    # If empty, try extracting from lyrics
    if not title or len(title) < 3:
        title = _extract_title_from_lyrics(lyrics)

    # Final fallback
    if not title or len(title) < 3:
        title = "Untitled Track"

    # Clean up
    title = _re.sub(r'\*+', '', title).strip()
    title = title.strip("\"'`#").strip()

    # Trim trailing stop words (prepositions, articles, pronouns)
    _stop_trail = {"in", "the", "a", "an", "to", "of", "on", "is", "your",
                   "my", "you", "though", "or", "for", "but", "we", "they",
                   "feel", "just", "like", "that", "with", "from", "so",
                   "and", "im", "its", "dont", "i", "me", "not"}
    _words = title.split()
    while len(_words) > 2 and _words[-1].lower().rstrip("',") in _stop_trail:
        _words.pop()
    title = " ".join(_words)

    # If trimming made it too short, it was a lyrics fragment
    if len(title) < 3 and title != "Untitled Track":
        title = _extract_title_from_lyrics(lyrics) or "Untitled Track"

    # Capitalize nicely (but preserve ALL-CAPS titles like "CRASH CORE")
    if title == title.lower():
        title = title.title()

    return f"A!ley Vyrus - {title}"


def _song_media_info(song_dir: str) -> tuple:
    """Return (has_mp3, has_cover) for a song directory."""
    _mp3p = os.path.join(song_dir, "audio.mp3")
    has_mp3 = os.path.isfile(_mp3p) and os.path.getsize(_mp3p) > 0
    has_cover = any(
        os.path.isfile(os.path.join(song_dir, f"cover.{ext}"))
        for ext in ("png", "jpg", "jpeg", "webp")
    )
    return has_mp3, has_cover


@app.get('/api/songs')
def api_songs():
    """Return all songs, deduplicated by lyrics fingerprint.

    Three sources (thoughts, directories, registry) merged into one list.
    Each song appears exactly once.  Title always 'A!ley Vyrus - TITLE'.
    """
    try:
        import re as _re
        songs_by_fp = {}  # fingerprint -> song dict  (winner-takes-all)
        _SONG_TYPES = {"creative_song", "music_making"}

        # ── Helper: register a song, skip if duplicate ──
        def _register(sid, title_raw, lyrics, emotion, topics, genre, dt, ts,
                      has_mp3, has_cover, priority, from_manifest=False):
            """Add song if not duplicate.  Higher priority wins on collision."""
            fp = _lyrics_fingerprint(lyrics)
            if len(fp) < 10 and not has_mp3:
                return  # No real content
            # On collision: prefer the one with mp3, then higher priority
            if fp in songs_by_fp:
                existing = songs_by_fp[fp]
                # Keep existing if it has mp3 and new one doesn't
                if existing["has_mp3"] and not has_mp3:
                    return
                # Keep existing if same mp3 status but higher priority
                if existing["has_mp3"] == has_mp3 and existing.get("_prio", 0) >= priority:
                    return
            final_title = _normalise_song_title(title_raw, lyrics, from_manifest=from_manifest)
            # Skip untitled fragments without audio — not real songs
            if "Untitled Track" in final_title and not has_mp3:
                return
            songs_by_fp[fp] = {
                "id": sid,
                "title": final_title,
                "lyrics": lyrics,
                "emotion": emotion,
                "topics": topics if isinstance(topics, list) else [],
                "genre": genre,
                "dt": dt,
                "ts": ts,
                "has_mp3": has_mp3,
                "has_cover": has_cover,
                "_prio": priority,
            }

        # ── Source 1: Thoughts (highest priority — freshest data) ──
        all_thoughts = read_thoughts(limit=9999)
        for t in all_thoughts:
            if t.get("type") not in _SONG_TYPES and t.get("decision") not in _SONG_TYPES:
                continue
            raw = t.get("raw_output") or t.get("thought_chain") or ""
            if raw.startswith(("🎵", "🎤", "🎶", "💿")):
                continue
            _tc = t.get("thought_chain") or ""
            if "Wollte Audio generieren" in _tc or "schon genug Songs" in _tc:
                continue
            if _tc and not t.get("raw_output") and len(_tc) < 120 and "[" not in _tc:
                continue
            sid = _song_id(t)
            meta = t.get("metadata") or {}
            song_dir = os.path.join(_SONGS_DIR, sid)
            has_mp3, has_cover = _song_media_info(song_dir)
            genre = ""
            if raw.startswith("["):
                genre = raw.split("\n")[0].strip("[]")
            title_raw = t.get("song_title") or meta.get("song_title") or ""
            _register(sid, title_raw, raw, meta.get("emotion", ""),
                      meta.get("topics", []), genre,
                      t.get("dt", ""), t.get("ts", 0),
                      has_mp3, has_cover, priority=30)

        # ── Source 2: Song directories (medium priority) ──
        if os.path.isdir(_SONGS_DIR):
            for entry_name in os.listdir(_SONGS_DIR):
                if not (entry_name.startswith("song_") or entry_name.startswith("registry_")
                        or entry_name.startswith("test_") or entry_name.startswith("portal_song_")):
                    continue
                song_dir = os.path.join(_SONGS_DIR, entry_name)
                if not os.path.isdir(song_dir):
                    continue
                has_mp3, has_cover = _song_media_info(song_dir)
                meta_path = os.path.join(song_dir, "generation_meta.json")
                manifest_path = os.path.join(song_dir, "manifest.json")
                lyrics_path = os.path.join(song_dir, "lyrics.txt")
                lyrics = ""
                genre = ""
                title_raw = ""
                ts = 0.0
                dt = ""
                # Read generation_meta.json
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, "r") as f:
                            meta = json.load(f)
                        lyrics = meta.get("lyrics", "")
                        # Do NOT use meta["prompt"] as title — that's generation tags
                        created = meta.get("created_at", "")
                        if created:
                            dt = created[:19].replace("T", " ")
                    except Exception:
                        pass
                # Read manifest.json
                if os.path.isfile(manifest_path):
                    try:
                        with open(manifest_path, "r") as f:
                            manifest = json.load(f)
                        if not lyrics:
                            lyrics = manifest.get("lyrics_clean", "")
                        tags = manifest.get("tags", "")
                        m_title = manifest.get("title", "")
                        # Only use manifest title if it's a real title (not Untitled_xxx)
                        if m_title and not m_title.startswith("Untitled_"):
                            title_raw = m_title
                        if not genre:
                            genre = tags.split(",")[0].strip() if tags else ""
                        created = manifest.get("created_at", "")
                        if created:
                            dt = created[:19].replace("T", " ")
                    except Exception:
                        pass
                # Read lyrics.txt
                if os.path.isfile(lyrics_path):
                    try:
                        with open(lyrics_path, "r") as f:
                            lyrics_txt = f.read().strip()
                        if not lyrics:
                            lyrics = lyrics_txt
                    except Exception:
                        pass
                # Extract timestamp from directory name
                try:
                    id_part = entry_name.replace("song_", "").replace("test_", "").replace("registry_", "").replace("portal_song_", "").split("_")[0]
                    ts_raw = int(id_part)
                    ts = ts_raw / 1000.0 if ts_raw > 9999999999 else float(ts_raw)
                    if not dt:
                        from datetime import datetime as _dt
                        dt = _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
                # Skip empty dirs
                if not has_mp3 and not lyrics.strip() and not has_cover:
                    continue
                _register(entry_name, title_raw, lyrics, "", [], genre,
                          dt, ts, has_mp3, has_cover, priority=20,
                          from_manifest=bool(title_raw))

        # ── Source 3: song_registry.json (lowest priority — old backups) ──
        _REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "ailey_users", "song_registry.json")
        if os.path.isfile(_REGISTRY_PATH):
            try:
                with open(_REGISTRY_PATH, "r") as f:
                    registry = json.load(f)
                for entry in registry:
                    lyrics = entry.get("lyrics", "")
                    title_raw = entry.get("title", "")
                    ts = entry.get("ts", 0)
                    dt = entry.get("dt", "")
                    if not dt and ts:
                        from datetime import datetime as _dt
                        try:
                            dt = _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass
                    _reg_id = f"registry_{abs(hash(title_raw + lyrics[:50]))}"
                    _reg_dir = os.path.join(_SONGS_DIR, _reg_id)
                    _reg_has_mp3, _reg_has_cover = _song_media_info(_reg_dir) if os.path.isdir(_reg_dir) else (False, False)
                    _register(_reg_id, title_raw, lyrics,
                              entry.get("mood", ""), [], entry.get("genre", ""),
                              dt, ts, _reg_has_mp3, _reg_has_cover, priority=10)
            except Exception:
                import traceback; traceback.print_exc()

        # Build final list, remove internal _prio field
        songs = []
        for s in songs_by_fp.values():
            s.pop("_prio", None)
            songs.append(s)
        songs.sort(key=lambda s: s.get("ts", 0), reverse=True)
        return jsonify({"success": True, "songs": songs, "count": len(songs)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.post('/api/songs/<song_id>/upload-mp3')
def api_song_upload_mp3(song_id: str):
    """Upload an MP3 for a song."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei hochgeladen"}), 400
    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"success": False, "error": "Dateiname fehlt"}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in ('.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac'):
        return jsonify({"success": False, "error": f"Audio-Format '{ext}' nicht unterstützt"}), 400
    song_dir = os.path.join(_SONGS_DIR, song_id)
    os.makedirs(song_dir, exist_ok=True)
    dest = os.path.join(song_dir, "audio.mp3")
    uploaded.save(dest)
    print(f"[SONGS] ✅ MP3 saved for {song_id}: {dest} ({os.path.getsize(dest)} bytes)")
    return jsonify({"success": True, "path": dest})

@app.post('/api/songs/<song_id>/upload-cover')
def api_song_upload_cover(song_id: str):
    """Upload a cover image for a song."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei hochgeladen"}), 400
    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"success": False, "error": "Dateiname fehlt"}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
        return jsonify({"success": False, "error": f"Bildformat '{ext}' nicht unterstützt"}), 400
    song_dir = os.path.join(_SONGS_DIR, song_id)
    os.makedirs(song_dir, exist_ok=True)
    # Remove old covers
    for old_ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
        old = os.path.join(song_dir, f"cover.{old_ext}")
        if os.path.isfile(old):
            os.remove(old)
    dest = os.path.join(song_dir, f"cover{ext}")
    uploaded.save(dest)
    print(f"[SONGS] ✅ Cover saved for {song_id}: {dest}")
    return jsonify({"success": True, "path": dest})

@app.get('/api/songs/<song_id>/mp3')
def api_song_serve_mp3(song_id: str):
    """Serve the MP3 file for a song with aggressive caching (1 year, immutable)."""
    song_dir = os.path.join(_SONGS_DIR, song_id)
    mp3_path = os.path.join(song_dir, "audio.mp3")
    if not os.path.isfile(mp3_path):
        return jsonify({"success": False, "error": "Keine MP3 vorhanden"}), 404
    resp = send_file(mp3_path, mimetype='audio/mpeg', as_attachment=False,
                     conditional=True)
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.get('/api/songs/<song_id>/cover')
def api_song_serve_cover(song_id: str):
    """Serve the cover image for a song with aggressive caching."""
    song_dir = os.path.join(_SONGS_DIR, song_id)
    for ext in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
        path = os.path.join(song_dir, f"cover.{ext}")
        if os.path.isfile(path):
            mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'webp': 'image/webp', 'gif': 'image/gif'}[ext]
            resp = send_file(path, mimetype=mime, as_attachment=False, conditional=True)
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp
    return jsonify({"success": False, "error": "Kein Cover vorhanden"}), 404

@app.delete('/api/songs/<song_id>/mp3')
def api_song_delete_mp3(song_id: str):
    """Delete the MP3 file for a song."""
    song_dir = os.path.join(_SONGS_DIR, song_id)
    mp3_path = os.path.join(song_dir, "audio.mp3")
    if os.path.isfile(mp3_path):
        os.remove(mp3_path)
        print(f"[SONGS] 🗑️ MP3 deleted for {song_id}")
    return jsonify({"success": True})


# ── A!ley's Music Generation API ─────────────────────────────────────────────
# Generate songs locally via ACE-Step (subprocess pattern like Wan2.1 video gen)
# Flow: parse song → unload LLM → subprocess ACE-Step → MP3 → reload LLM

_music_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "song_id": ""}


# ── Song heuristic detection (rein regex-/keyword-basiert, kein LLM) ──────
_SONG_SECTION_RE = re.compile(
    r"\[\s*(verse|chorus|hook|bridge|intro|outro|pre[\s\-]?chorus|refrain|drop|"
    r"breakdown|interlude|post[\s\-]?chorus|build[\s\-]?up)\b[^\]]*\]",
    re.IGNORECASE,
)
_SONG_TITLE_RE = re.compile(
    r"(?:^|\n)\s*(?:#+\s*|title:\s*|\*\*)?[\"„»]?([A-ZÄÖÜ][^\n\[\]\"„«»]{2,80}?)[\"“«]?(?:\*\*)?\s*\n",
    re.MULTILINE,
)

# Lyrics-Keyword → (genre, mood) tag-Vorschläge
_GENRE_KEYWORDS = {
    "metal": ("metal, heavy, distorted guitar", "aggressive, intense"),
    "metalcore": ("metalcore, breakdowns, screamed vocals", "raw, cathartic"),
    "punk": ("punk rock, energetic, fast", "rebellious, defiant"),
    "grunge": ("grunge rock, gritty, 90s", "melancholic, raw"),
    "rap": ("hip-hop, rap, 808s, trap beat", "confident, hard-hitting"),
    "k-rap": ("k-rap, korean hip-hop, melodic rap", "fierce, emotional"),
    "k-pop": ("k-pop, polished, synth, dance", "energetic, catchy"),
    "pop": ("pop, polished, melodic, radio-friendly", "upbeat, catchy"),
    "ballad": ("ballad, piano, slow, emotional", "sad, vulnerable"),
    "electronic": ("electronic, synth, edm, beat-driven", "energetic, futuristic"),
    "industrial": ("industrial, dark, machine-like", "dark, aggressive"),
    "acoustic": ("acoustic guitar, intimate, stripped", "soft, reflective"),
    "folk": ("folk, acoustic, narrative", "warm, storytelling"),
    "rock": ("rock, guitar-driven, energetic", "powerful, anthemic"),
}
_DARK_WORDS = {"shadow", "blade", "blood", "death", "void", "abyss", "ghost", "scream",
               "broken", "shatter", "pain", "rage", "fury", "ruin", "burn", "ash",
               "schatten", "dunkel", "blut", "tod", "leere", "schmerz", "wut"}
_BRIGHT_WORDS = {"sun", "dance", "love", "baby", "shine", "smile", "free", "dream",
                 "high", "yeah", "fire", "wild", "glow", "summer", "starlight",
                 "sonne", "tanz", "liebe", "frei", "traum", "feuer"}
_INTROSPECTIVE_WORDS = {"silence", "alone", "memory", "remember", "whisper", "still",
                        "stille", "allein", "erinner", "leise"}


def _detect_song_from_text(text: str) -> dict:
    """Heuristic song-schema detection. No LLM required.

    Returns: { is_song, confidence, sections, title, suggested_tags,
               suggested_mood, suggested_genre, has_korean, word_count, needs_metadata }
    """
    if not text or len(text) < 80:
        return {"is_song": False, "confidence": 0.0}

    sections = [m.group(1).lower().strip() for m in _SONG_SECTION_RE.finditer(text)]
    # Normalise (pre-chorus / pre chorus / prechorus)
    sections = [re.sub(r"[\s\-]+", "-", s) for s in sections]
    section_count = len(sections)

    # Confidence: ≥2 distinct sections = likely song.
    unique_sections = len(set(sections))
    is_song = section_count >= 2 and unique_sections >= 2
    if not is_song:
        return {"is_song": False, "confidence": min(0.5, section_count * 0.2), "sections": sections}

    # Strip section markers, count words
    body = _SONG_SECTION_RE.sub("\n", text)
    word_count = len(body.split())
    confidence = min(1.0, 0.4 + 0.1 * unique_sections + (0.2 if word_count > 100 else 0))

    # Title detection: first non-section line that looks like a title (≤80 chars, no markdown bullet)
    title = None
    for line in text.splitlines():
        line = line.strip().lstrip("#").lstrip("*").strip()
        if not line or _SONG_SECTION_RE.match(f"[{line}]"):
            continue
        if line.startswith(("- ", "•", "*")):
            continue
        # Strip wrapping quotes
        if line[:1] in '"“„«»' and line[-1:] in '"”“«»':
            line = line[1:-1].strip()
        if 3 <= len(line) <= 80 and not line.endswith((":", "?")) and not line.startswith("["):
            title = line
            break

    # Korean detection (Hangul codepoints)
    has_korean = bool(re.search(r"[\uAC00-\uD7AF]", text))

    # Genre/mood heuristic
    lower = body.lower()
    genre_hits = [(g, score) for g, score in (
        (g, len(re.findall(rf"\b{re.escape(g)}\b", lower))) for g in _GENRE_KEYWORDS
    ) if score > 0]
    suggested_genre = None
    suggested_tags = None
    suggested_mood = None
    if genre_hits:
        genre_hits.sort(key=lambda x: x[1], reverse=True)
        suggested_genre = genre_hits[0][0]
        suggested_tags, suggested_mood = _GENRE_KEYWORDS[suggested_genre]

    # Mood from theme-words if genre didn't suggest one
    if not suggested_mood:
        words = set(re.findall(r"[a-zäöüß]{3,}", lower))
        dark = len(words & _DARK_WORDS)
        bright = len(words & _BRIGHT_WORDS)
        intro = len(words & _INTROSPECTIVE_WORDS)
        if dark > bright and dark > intro:
            suggested_mood = "dark, intense, cathartic"
            suggested_tags = suggested_tags or "alternative rock, heavy, distorted"
            suggested_genre = suggested_genre or "alt-rock"
        elif bright > dark:
            suggested_mood = "upbeat, energetic"
            suggested_tags = suggested_tags or "pop rock, energetic, melodic"
            suggested_genre = suggested_genre or "pop-rock"
        else:
            suggested_mood = "reflective, atmospheric"
            suggested_tags = suggested_tags or "indie, atmospheric, melodic"
            suggested_genre = suggested_genre or "indie"

    needs_metadata = not (suggested_genre and suggested_mood)

    return {
        "is_song": True,
        "confidence": round(confidence, 2),
        "sections": sections,
        "section_count": section_count,
        "unique_sections": unique_sections,
        "title": title or "Untitled Song",
        "word_count": word_count,
        "has_korean": has_korean,
        "suggested_genre": suggested_genre,
        "suggested_tags": suggested_tags,
        "suggested_mood": suggested_mood,
        "needs_metadata": needs_metadata,
    }


@app.post('/api/songs/heuristic')
def api_song_heuristic():
    """Detect song schema in text + suggest metadata. Rein heuristisch, kein LLM.

    Body: { text: "..." }
    Returns: { success, is_song, confidence, title, suggested_tags, ... }
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "error": "text fehlt"}), 400
    result = _detect_song_from_text(text)
    result["success"] = True
    return jsonify(result)


@app.post('/api/songs/from-chat')
def api_song_from_chat():
    """One-click: nimmt Lyrics aus dem Chat + (optional) User-Metadata,
    triggert die existierende /api/songs/generate Pipeline.

    Body: {
        lyrics:    "..."   (required — voller Suno-format Text mit [Verse]/[Chorus])
        title:     "..."   (optional — heuristisch ergänzt falls leer)
        genre:     "..."   (optional)
        mood:      "..."   (optional)
        tags:      "..."   (optional — wenn gesetzt, überschreibt Auto-Build)
        duration:  number  (optional — wird sonst geschätzt)
        user:      "Simon" / "<portal-user>" (optional metadata)
        source:    "chat" / "portal-chat"  (für Logging)
    }
    Returns: { success, song_id, status_url, detected }
    """
    global _music_gen_job
    data = request.get_json(silent=True) or {}
    lyrics_raw = (data.get("lyrics") or "").strip()
    if not lyrics_raw:
        return jsonify({"success": False, "error": "Keine Lyrics übergeben"}), 400

    detected = _detect_song_from_text(lyrics_raw)
    if not detected.get("is_song"):
        return jsonify({
            "success": False,
            "error": "Kein Song-Schema erkannt. Brauche [Verse]/[Chorus]/[Hook] Markierungen.",
            "detected": detected,
        }), 400

    if _music_gen_job["active"]:
        return jsonify({"success": False, "error": "Es läuft bereits eine Songgenerierung."}), 409

    # Build tags: user-tags > genre+mood combined > heuristic
    tags = (data.get("tags") or "").strip()
    genre = (data.get("genre") or "").strip() or detected.get("suggested_genre") or ""
    mood = (data.get("mood") or "").strip() or detected.get("suggested_mood") or ""
    if not tags:
        if genre or mood:
            try:
                from ailey_system.music_generator import build_ace_caption
                tags = build_ace_caption(
                    genre=genre or "alternative rock",
                    mood=mood or "emotional, energetic",
                )
            except Exception:
                tags = ", ".join(filter(None, [genre, mood, "vocal-led, full mix"]))
        else:
            tags = detected.get("suggested_tags") or "alt-rock, vocal-led, energetic"

    title = (data.get("title") or "").strip() or detected.get("title") or f"Chat Song {int(time.time())}"

    # Allocate stable song_id (so frontend can poll + display)
    song_id = (data.get("song_id") or "").strip()
    if not song_id:
        import re as _re_id, hashlib as _hl_id
        _slug = _re_id.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "chat-song"
        song_id = f"chatsong_{int(time.time())}_{_slug}"

    # Forward to existing music_generator pipeline (async)
    try:
        from ailey_system.music_generator import (
            generate_music, parse_suno_to_ace, estimate_song_duration,
        )
    except Exception as ie:
        return jsonify({"success": False, "error": f"music_generator nicht verfügbar: {ie}"}), 503

    # Extract clean lyrics from suno-format
    try:
        _, clean_lyrics = parse_suno_to_ace(lyrics_raw)
        if not clean_lyrics:
            clean_lyrics = lyrics_raw  # fallback: pass raw through
    except Exception:
        clean_lyrics = lyrics_raw

    duration = float(data.get("duration") or estimate_song_duration(clean_lyrics))
    duration = min(480.0, max(20.0, duration))
    steps = min(100, max(8, int(data.get("steps", 50))))
    seed = data.get("seed")
    src = data.get("source") or "chat"
    user_name = data.get("user") or "Simon"

    def _job():
        global _music_gen_job
        unloaded = False
        idle_thinker_ref = globals().get('idle_thinker')
        try:
            _music_gen_job["active"] = True
            _music_gen_job["started"] = time.time()
            _music_gen_job["result"] = None
            _music_gen_job["song_id"] = song_id
            _music_gen_job["progress"] = f"Chat-Song '{title}': Entlade LLM…"
            # Unload LLM
            try:
                if idle_thinker_ref:
                    idle_thinker_ref._generating_image = True
                    idle_thinker_ref._unload_llm_for_image_gen()
                    unloaded = True
                time.sleep(2.0)
            except Exception as ue:
                print(f"[ChatSong] Unload warn: {ue}")
            _music_gen_job["progress"] = f"ACE-Step generiert '{title}'…"
            mp3_path, meta = generate_music(
                prompt=tags, lyrics=clean_lyrics, song_id=song_id,
                duration=duration, infer_steps=steps, seed=seed,
                title_override=title,
            )
            # Reload LLM
            try:
                if unloaded and idle_thinker_ref:
                    idle_thinker_ref._reload_llm_after_image_gen()
                    idle_thinker_ref._generating_image = False
            except Exception:
                pass

            if mp3_path and os.path.isfile(mp3_path):
                # Save extended manifest so the song appears in Music Tab + portal
                try:
                    song_dir = os.path.join("ailey_users", "songs", song_id)
                    os.makedirs(song_dir, exist_ok=True)
                    manifest = {
                        "title": title, "genre": genre, "mood": mood, "tags": tags,
                        "lyrics_clean": clean_lyrics[:8000],
                        "phase": "done",
                        "phases_completed": ["from_chat"],
                        "audio_path": mp3_path,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": src,
                        "requested_by": user_name,
                        "heuristic": detected,
                    }
                    with open(os.path.join(song_dir, "manifest.json"), "w", encoding="utf-8") as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                    with open(os.path.join(song_dir, "lyrics.txt"), "w", encoding="utf-8") as f:
                        f.write(lyrics_raw)
                except Exception as me:
                    print(f"[ChatSong] Manifest write warn: {me}")

                # Cover art best-effort
                try:
                    from ailey_system.music_generator import generate_cover_art, SONGS_DIR as _SD
                    _song_dir2 = os.path.join(_SD, song_id)
                    if not os.path.isfile(os.path.join(_song_dir2, "cover.png")):
                        generate_cover_art(song_dir=_song_dir2, song_title=title,
                                           genre=(genre or tags.split(",")[0]))
                except Exception as ce:
                    print(f"[ChatSong] Cover warn: {ce}")

                # Portal push (only if user is a portal user)
                portal_audio_url = None
                try:
                    from ailey_system.portal_poller import get_portal_poller
                    poller = get_portal_poller()
                    if poller and poller._portal_url:
                        audio_url = poller._upload_gallery_file(mp3_path, f"{song_id}.mp3")
                        if audio_url:
                            import hashlib as _hl
                            _src_id = f"song_{_hl.md5(title.lower().encode()).hexdigest()[:10]}"
                            poller._push_gallery_item(
                                item_type="song", title=title,
                                content_text=clean_lyrics[:2000],
                                file_url=audio_url,
                                metadata={"genre": tags[:200], "audio_url": audio_url,
                                          "duration": duration, "source": src,
                                          "requested_by": user_name},
                                source_id=_src_id,
                            )
                            portal_audio_url = audio_url
                except Exception as pe:
                    print(f"[ChatSong] Portal push warn: {pe}")

                _music_gen_job["result"] = {
                    "success": True, "song_id": song_id,
                    "mp3_url": f"/api/songs/{song_id}/mp3",
                    "cover_url": f"/api/songs/{song_id}/cover",
                    "title": title, "tags": tags[:200],
                    "duration": duration, "source": src,
                    "portal_audio_url": portal_audio_url,
                }
                _music_gen_job["progress"] = "Fertig! 🎵"
            else:
                _music_gen_job["result"] = {"success": False, "error": "ACE-Step generation failed"}
                _music_gen_job["progress"] = "Fehlgeschlagen"
        except Exception as je:
            import traceback; traceback.print_exc()
            _music_gen_job["result"] = {"success": False, "error": str(je)}
            _music_gen_job["progress"] = f"Fehler: {je}"
            try:
                if unloaded and idle_thinker_ref:
                    idle_thinker_ref._reload_llm_after_image_gen()
                    idle_thinker_ref._generating_image = False
            except Exception:
                pass
        finally:
            _music_gen_job["active"] = False

    import threading
    threading.Thread(target=_job, daemon=True).start()

    return jsonify({
        "success": True,
        "status": "started",
        "song_id": song_id,
        "title": title,
        "tags": tags[:200],
        "duration": duration,
        "detected": detected,
        "status_url": "/api/songs/generate/status",
        "mp3_url": f"/api/songs/{song_id}/mp3",
        "cover_url": f"/api/songs/{song_id}/cover",
        "message": "Song wird generiert — poll /api/songs/generate/status für Fortschritt.",
    })



@app.get('/api/songs/generate/status')
def api_music_gen_status():
    """Poll music generation status."""
    return jsonify({
        "success": True,
        "active": _music_gen_job["active"],
        "progress": _music_gen_job["progress"],
        "result": _music_gen_job["result"],
        "started": _music_gen_job["started"],
        "song_id": _music_gen_job["song_id"],
    })


@app.post('/api/songs/generate')
def api_songs_generate():
    """Generate a song via ACE-Step from lyrics + tags (or raw Suno-format text).

    Accepts JSON:
      song_id (str, required): Song id from thoughts (e.g. "song_1710000000000")
      tags (str):   ACE-Step tags  – OR extracted from raw_lyrics if not given
      lyrics (str): ACE-Step lyrics – OR extracted from raw_lyrics if not given
      raw_lyrics (str): Full Suno/ACE format text (parsed if tags+lyrics missing)
      duration (float): Audio duration 10-240s (default 180)
      steps (int): Inference steps 8-100 (default 50 for SFT)
      seed (int): Random seed (null = random)
      async (bool): Run in background (default true)

    Flow: Caption + Lyrics → unload LLM → ACE-Step v1.5 subprocess → MP3 → reload LLM.
    """
    global _music_gen_job
    from ailey_system.music_generator import (
        generate_music, parse_suno_to_ace, is_ace_step_available, build_ace_tags,
        ACE_DEFAULT_DURATION, SONGS_DIR,
    )

    if not is_ace_step_available():
        return jsonify({"success": False, "error": "ACE-Step nicht verfügbar"}), 503

    data = request.get_json(silent=True) or {}
    song_id = (data.get('song_id') or '').strip()
    if not song_id:
        song_id = f"song_{int(time.time() * 1000)}"

    # Get tags + lyrics (either direct or parsed from raw)
    tags = (data.get('tags') or '').strip()
    lyrics = (data.get('lyrics') or '').strip()
    raw_lyrics = (data.get('raw_lyrics') or '').strip()
    title_override = (data.get('title') or '').strip() or None

    if (not tags or not lyrics) and raw_lyrics:
        # Parse Ailey's Suno-format output → clean ACE-Step tags + lyrics
        tags, lyrics = parse_suno_to_ace(raw_lyrics)
    elif raw_lyrics and tags:
        # User provided tags AND raw_lyrics — parse lyrics only, use user tags
        _, parsed_lyrics = parse_suno_to_ace(raw_lyrics)
        if parsed_lyrics:
            lyrics = parsed_lyrics
    if not lyrics:
        return jsonify({"success": False, "error": "Keine Lyrics angegeben"}), 400
    if not tags:
        tags = build_ace_tags()  # Default Ailey tags
    else:
        # Enrich sparse tags → rich hybrid caption (same quality gate as idle_thinker)
        from ailey_system.music_generator import build_ace_caption
        _has_desc = ". " in tags and len(tags) > 200
        if _has_desc:
            pass  # already a rich caption — keep it
        else:
            _genre_hint = ""
            for _g in ("metalcore", "metal", "punk", "rock", "k-rap", "k-pop",
                        "electronic", "hip-hop", "rap", "grunge", "pop", "folk",
                        "acoustic", "ballad", "industrial", "screamo"):
                if _g in tags.lower():
                    _genre_hint = _g
                    break
            _old = tags
            tags = build_ace_caption(
                genre=_genre_hint or tags.split(",")[0].strip() or "k-rap punk rock",
                mood="energetic, emotional",
                llm_tags=_old,
            )
            print(f"[MusicGen/API] 🔧 Caption enriched: {len(_old)} → {len(tags)} chars")

    # Smart duration: if caller didn't specify, estimate from word count
    if 'duration' in data:
        duration = min(480.0, max(10.0, float(data['duration'])))
    else:
        from ailey_system.music_generator import estimate_song_duration
        duration = estimate_song_duration(lyrics)
        print(f"[MusicGen/API] Smart duration: {duration}s (estimated from {len(lyrics.split())} words)")
    steps = min(100, max(4, int(data.get('steps', 50))))  # ACE-Step v1.5 SFT: 50 steps = training default
    seed = data.get('seed')
    run_async = data.get('async', True)

    if _music_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade schon ein Song generiert."}), 409
    if _video_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade ein Video generiert. Song-Gen danach möglich."}), 409
    if _image_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade ein Bild generiert. Song-Gen danach möglich."}), 409

    def _do_music_generate():
        global _music_gen_job
        unloaded = False
        idle_thinker_ref = globals().get('idle_thinker')
        try:
            _music_gen_job["active"] = True
            _music_gen_job["started"] = time.time()
            _music_gen_job["result"] = None
            _music_gen_job["song_id"] = song_id
            _music_gen_job["progress"] = "Entlade LLM für ACE-Step…"

            # ── 1. Unload LLM (safe unload — NO nuclear kill!) ──
            # ACE-Step runs as a subprocess with its own Metal context,
            # so we don't need to purge mlx from sys.modules.
            # Nuclear kill causes SIGABRT on re-import.
            try:
                if idle_thinker_ref:
                    idle_thinker_ref._generating_image = True
                    idle_thinker_ref._unload_llm_for_image_gen()
                    unloaded = True
                else:
                    import gc
                    try:
                        import mlx.core as mx
                        mx.synchronize()
                    except Exception:
                        pass
                    # Unload fast model (Qwen 1.5B) before heavy ACE-Step
                    try:
                        from ailey_system.llm_mlx import unload_fast_model as _uf
                        _uf()
                    except Exception:
                        pass
                    try:
                        from ailey_system import llm_mlx
                        from ailey_system.llm_mlx import MLXGenerator as _MLX, _mlx_lock, block_auto_reload
                        block_auto_reload()
                        with _mlx_lock:
                            llm_mlx._model = None
                            llm_mlx._tokenizer = None
                            llm_mlx._cache = None
                            llm_mlx._last_system_prompt = None
                            _MLX._instance = None
                    except Exception:
                        pass
                    gc.collect(); gc.collect()
                    try:
                        import mlx.core as mx
                        mx.metal.set_cache_limit(0)
                        mx.metal.clear_cache()
                        mx.metal.set_memory_limit(0)
                    except Exception:
                        pass
                    gc.collect()
                    unloaded = True

                time.sleep(2.0)
                print(f"[MusicGen/API] ✅ LLM unloaded (safe — no nuclear kill)")
            except Exception as ue:
                print(f"[MusicGen/API] Unload warning: {ue}")

            # ── 2. Generate music via ACE-Step v1.5 subprocess ──
            _music_gen_job["progress"] = f"Generiere Song mit ACE-Step v1.5…"
            print(f"[MusicGen/API] 🎵 Starting: {song_id}, {duration}s, {steps} steps")

            mp3_path, meta = generate_music(
                prompt=tags,
                lyrics=lyrics,
                song_id=song_id,
                duration=duration,
                infer_steps=steps,
                seed=seed,
                title_override=title_override,
            )

            # ── 3. Reload LLM (safe lazy reload — let next chat request load it) ──
            _music_gen_job["progress"] = "Lade LLM neu…"
            try:
                if unloaded:
                    import gc as _gc3
                    _gc3.collect(); _gc3.collect()
                    time.sleep(2.0)

                    if idle_thinker_ref:
                        idle_thinker_ref._reload_llm_after_image_gen()
                        idle_thinker_ref._generating_image = False
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                    print("[MusicGen/API] ✅ LLM reload triggered after ACE-Step")
            except Exception as re_err:
                print(f"[MusicGen/API] Reload warning: {re_err}")

            # ── 4. Report result ──
            if mp3_path and os.path.isfile(mp3_path):
                mp3_url = f"/api/songs/{song_id}/mp3"
                elapsed = time.time() - _music_gen_job["started"]

                # ── 4a. Generate cover art (non-blocking, best-effort) ──
                _cover_path = None
                try:
                    from ailey_system.music_generator import generate_cover_art, SONGS_DIR as _SD
                    import os as _os2
                    _song_dir = _os2.path.join(_SD, song_id)
                    _cover_existing = _os2.path.join(_song_dir, "cover.png")
                    if not _os2.path.isfile(_cover_existing):
                        _cover_title = (meta or {}).get("title", song_id) if meta else song_id
                        _cover_path = generate_cover_art(
                            song_dir=_song_dir,
                            song_title=_cover_title,
                            genre=tags.split(",")[0].strip(),
                        )
                        if _cover_path:
                            print(f"[MusicGen/API] 🎨 Cover generated: {_os2.path.basename(_cover_path)}")
                except Exception as _cove:
                    print(f"[MusicGen/API] Cover art warning (non-fatal): {_cove}")
                _music_gen_job["result"] = {
                    "success": True,
                    "song_id": song_id,
                    "mp3_url": mp3_url,
                    "duration": duration,
                    "elapsed_s": round(elapsed, 1),
                    "tags": tags[:200],
                    "meta": meta,
                }
                _music_gen_job["progress"] = "Fertig! 🎵"
                print(f"[MusicGen/API] ✅ Song generated: {song_id} in {elapsed:.0f}s")

                # ── 5. Push MP3 to portal (async, non-blocking) ──
                try:
                    from ailey_system.portal_poller import get_portal_poller
                    poller = get_portal_poller()
                    if poller and poller._portal_url:
                        mp3_filename = f"{song_id}.mp3"
                        audio_url = poller._upload_gallery_file(mp3_path, mp3_filename)
                        if audio_url:
                            # Also push/update the song gallery item with audio_url
                            song_title = meta.get("title", song_id) if meta else song_id
                            song_lyrics = lyrics[:2000] if lyrics else ""
                            import hashlib as _hl
                            _title_key = song_title.lower().strip()
                            _src_id = f"song_{_hl.md5(_title_key.encode()).hexdigest()[:10]}"
                            poller._push_gallery_item(
                                item_type="song",
                                title=song_title,
                                content_text=song_lyrics,
                                file_url=audio_url,
                                metadata={"genre": tags[:200], "audio_url": audio_url,
                                          "duration": duration},
                                source_id=_src_id,
                            )
                            print(f"[MusicGen/API] 🌐 MP3 pushed to portal: {audio_url}")
                            _music_gen_job["result"]["portal_audio_url"] = audio_url
                        else:
                            print("[MusicGen/API] ⚠️ MP3 portal upload failed (no URL returned)")
                except Exception as push_err:
                    print(f"[MusicGen/API] ⚠️ Portal push error (non-fatal): {push_err}")
            else:
                _music_gen_job["result"] = {"success": False, "error": "ACE-Step generation failed"}
                _music_gen_job["progress"] = "Fehlgeschlagen"
                print(f"[MusicGen/API] ❌ Generation failed for {song_id}")

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            print(f"[MusicGen/API] ❌ Error: {e}")
            print(f"[MusicGen/API] ❌ Traceback:\n{tb_str}")
            _music_gen_job["result"] = {"success": False, "error": f"MusicGen Error: {type(e).__name__}: {e}"}
            _music_gen_job["progress"] = f"Fehler: {e}"
            # Ensure LLM reload even on error
            try:
                if unloaded and idle_thinker_ref:
                    idle_thinker_ref._reload_llm_after_image_gen()
                    idle_thinker_ref._generating_image = False
            except Exception:
                pass
        finally:
            _music_gen_job["active"] = False

    if run_async:
        import threading
        t = threading.Thread(target=_do_music_generate, daemon=True)
        t.start()
        return jsonify({
            "success": True,
            "status": "started",
            "song_id": song_id,
            "message": "Songgenerierung gestartet. Poll /api/songs/generate/status für den Fortschritt.",
        })
    else:
        _do_music_generate()
        result = _music_gen_job.get("result", {})
        if result and result.get("success"):
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": result.get("error", "Unknown error")}), 500


@app.get('/api/songs/<song_id>/meta')
def api_song_meta(song_id: str):
    """Return generation metadata for a song (if generated locally)."""
    song_dir = os.path.join(_SONGS_DIR, song_id)
    meta_path = os.path.join(song_dir, "generation_meta.json")
    if not os.path.isfile(meta_path):
        return jsonify({"success": False, "error": "Keine Metadaten vorhanden"}), 404
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        return jsonify({"success": True, "meta": meta})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/songs/<song_id>/push-to-portal')
def api_song_push_to_portal(song_id: str):
    """Push a song's MP3 to the portal (allinkl). For already-generated songs."""
    song_dir = os.path.join(_SONGS_DIR, song_id)
    if not os.path.isdir(song_dir):
        return jsonify({"success": False, "error": "Song nicht gefunden"}), 404

    # Find MP3 file
    mp3_path = None
    for fname in ('final.mp3', f'{song_id}.mp3', 'output.mp3'):
        p = os.path.join(song_dir, fname)
        if os.path.isfile(p):
            mp3_path = p
            break
    # Fallback: any .mp3 in the directory
    if not mp3_path:
        for f in os.listdir(song_dir):
            if f.endswith('.mp3'):
                mp3_path = os.path.join(song_dir, f)
                break

    if not mp3_path:
        return jsonify({"success": False, "error": "Keine MP3-Datei gefunden"}), 404

    try:
        from ailey_system.portal_poller import get_portal_poller
        poller = get_portal_poller()
        if not poller or not poller._portal_url:
            return jsonify({"success": False, "error": "Portal Poller nicht aktiv"}), 503

        mp3_filename = f"{song_id}.mp3"
        audio_url = poller._upload_gallery_file(mp3_path, mp3_filename)
        if not audio_url:
            return jsonify({"success": False, "error": "Upload fehlgeschlagen"}), 500

        # Read metadata for title/lyrics
        meta_path = os.path.join(song_dir, "generation_meta.json")
        manifest_path = os.path.join(song_dir, "manifest.json")
        title = song_id
        lyrics = ""
        genre = ""
        manifest = {}
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except Exception:
                pass
        if os.path.isfile(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            title = meta.get("title", meta.get("song_id", song_id))
            lyrics = meta.get("lyrics", "")[:2000]
            genre = meta.get("tags", "")[:200]
        # Prefer manifest title if available
        if manifest.get("title"):
            title = manifest["title"]
        if manifest.get("genre"):
            genre = manifest["genre"]
        # Load lyrics from file if not in meta
        if not lyrics:
            lyrics_path = os.path.join(song_dir, "lyrics.txt")
            if os.path.isfile(lyrics_path):
                try:
                    with open(lyrics_path, "r", encoding="utf-8") as lf:
                        lyrics = lf.read()[:2000]
                except Exception:
                    pass

        # Use song_id as stable source_id (not title-hash) so re-pushes update the same entry
        _src_id = f"song_{song_id}"

        # Build metadata — include album info from manifest
        push_meta = {"genre": genre, "audio_url": audio_url,
                     "mood": manifest.get("mood", "")}
        for _akey in ("album_slug", "album_title", "album_concept",
                       "album_created_at", "portal_cover_url"):
            _aval = manifest.get(_akey, "")
            if _aval:
                push_meta[_akey] = _aval

        poller._push_gallery_item(
            item_type="song",
            title=title,
            content_text=lyrics,
            file_url=audio_url,
            metadata=push_meta,
            source_id=_src_id,
        )
        # Save portal_audio_url back to manifest for reference
        try:
            import json as _json
            _mf_data = {}
            if os.path.isfile(manifest_path):
                with open(manifest_path) as _f:
                    _mf_data = _json.load(_f)
            _mf_data["portal_audio_url"] = audio_url
            _mf_data["portal_src_id"] = _src_id
            with open(manifest_path, "w") as _f:
                _json.dump(_mf_data, _f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        print(f"[SongPush] 🌐 Pushed to portal: {song_id} → {audio_url}")
        return jsonify({"success": True, "url": audio_url, "song_id": song_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Album APIs ────────────────────────────────────────────────────────────────
# Albums live in ailey_users/songs/album_<slug>/ (manifest.json + cover.*)
# Songs reference their album via manifest["album_slug"]

@app.get('/api/albums')
def api_albums():
    """Return all albums, synthesising missing album dirs from song manifests."""
    try:
        # Helper: coerce any created_at value (str / int / float epoch) to YYYY-MM-DD or "".
        def _ca_str(v):
            try:
                if isinstance(v, str):
                    return v[:10]
                if isinstance(v, (int, float)) and v > 0:
                    import datetime as _dt
                    # heuristic: ms vs s
                    ts = v / 1000 if v > 1e12 else v
                    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except Exception:
                pass
            return ""
        # Album dirs can live in two places: _SONGS_DIR (legacy) and ailey_users/albums/ (new).
        _ALBUMS_DIR = os.path.join(os.path.dirname(__file__), "ailey_users", "albums")
        album_search_dirs = [_SONGS_DIR, _ALBUMS_DIR]

        # Build album info from existing album dirs
        album_map = {}  # slug -> album dict
        for _root in album_search_dirs:
            if not os.path.isdir(_root):
                continue
            for d in os.listdir(_root):
                if not d.startswith("album_"):
                    continue
                dpath = os.path.join(_root, d)
                if not os.path.isdir(dpath):
                    continue
                # manifest.json (legacy) OR album.json (new)
                mf_path = os.path.join(dpath, "manifest.json")
                if not os.path.isfile(mf_path):
                    mf_path = os.path.join(dpath, "album.json")
                m = {}
                if os.path.isfile(mf_path):
                    try:
                        with open(mf_path) as f:
                            m = json.load(f)
                    except Exception:
                        pass
                has_cover = any(
                    os.path.isfile(os.path.join(dpath, f"cover.{ext}"))
                    for ext in ("png", "jpg", "jpeg", "webp")
                )
                slug = d
                if slug in album_map:
                    continue  # already indexed from earlier root
                album_map[slug] = {
                    "slug": slug,
                    "title": m.get("title") or slug.replace("_", " ").replace("-", " ").title(),
                    "concept": m.get("concept", ""),
                    "status": m.get("status", ""),
                    "created_at": _ca_str(m.get("created_at", "")),
                    "has_cover": has_cover,
                    "song_count": 0,
                    "mp3_count": 0,
                    "songs": [],
                }

        # Walk songs, count per album & collect song refs
        songs_no_album = []
        if os.path.isdir(_SONGS_DIR):
            for d in sorted(os.listdir(_SONGS_DIR)):
                if d.startswith("album_"):
                    continue
                base = os.path.join(_SONGS_DIR, d)
                if not os.path.isdir(base):
                    continue
                has_mp3 = any(f.endswith(".mp3") for f in os.listdir(base))
                has_cover_s = any(f.startswith("cover.") for f in os.listdir(base))
                mf_path = os.path.join(base, "manifest.json")
                meta_path = os.path.join(base, "generation_meta.json")
                title = d
                album_slug = None
                created_at = ""
                genre = ""
                mood = ""
                if os.path.isfile(mf_path):
                    try:
                        m = json.load(open(mf_path))
                        album_slug = m.get("album_slug")
                        title = m.get("title") or title
                        created_at = _ca_str(m.get("created_at", ""))
                        genre = m.get("genre", "")
                        mood = m.get("mood", "")
                    except Exception:
                        pass
                if os.path.isfile(meta_path):
                    try:
                        m2 = json.load(open(meta_path))
                        if not title or title == d:
                            title = m2.get("title") or title
                        if not created_at:
                            created_at = _ca_str(m2.get("created_at", ""))
                    except Exception:
                        pass

                song_entry = {
                    "id": d,
                    "title": title,
                    "has_mp3": has_mp3,
                    "has_cover": has_cover_s,
                    "genre": genre,
                    "mood": mood,
                    "created_at": created_at,
                }

                if album_slug:
                    if album_slug not in album_map:
                        # Synthesise album entry from slug
                        album_map[album_slug] = {
                            "slug": album_slug,
                            "title": album_slug.split("_", 2)[-1].replace("-", " ").replace("_", " ").title()
                                     if "_" in album_slug else album_slug,
                            "concept": "",
                            "status": "",
                            "created_at": "",
                            "has_cover": False,
                            "song_count": 0,
                            "mp3_count": 0,
                            "songs": [],
                        }
                    album_map[album_slug]["songs"].append(song_entry)
                    album_map[album_slug]["song_count"] += 1
                    if has_mp3:
                        album_map[album_slug]["mp3_count"] += 1
                    # Use earliest song date as album date if missing
                    if not album_map[album_slug]["created_at"] and created_at:
                        album_map[album_slug]["created_at"] = created_at
                else:
                    songs_no_album.append(song_entry)

        # Sort songs within each album by created_at
        for alb in album_map.values():
            alb["songs"].sort(key=lambda s: s.get("created_at", ""), reverse=False)

        # Build final list, sorted by created_at desc
        albums = sorted(album_map.values(), key=lambda a: a.get("created_at", ""), reverse=True)

        return jsonify({
            "success": True,
            "albums": albums,
            "count": len(albums),
            "songs_no_album": sorted(songs_no_album, key=lambda s: s.get("created_at", ""), reverse=True),
            "no_album_count": len(songs_no_album),
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/albums/<album_slug>/cover')
def api_album_serve_cover(album_slug: str):
    """Serve album cover image with aggressive caching."""
    _ALBUMS_DIR = os.path.join(os.path.dirname(__file__), "ailey_users", "albums")
    album_dir = None
    for _root in (_SONGS_DIR, _ALBUMS_DIR):
        cand = os.path.join(_root, album_slug)
        if os.path.isdir(cand):
            album_dir = cand
            break
    if not album_dir:
        return jsonify({"success": False, "error": "Album nicht gefunden"}), 404
    for ext in ("png", "jpg", "jpeg", "webp"):
        path = os.path.join(album_dir, f"cover.{ext}")
        if os.path.isfile(path):
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}[ext]
            resp = send_file(path, mimetype=mime, as_attachment=False, conditional=True)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp
    return jsonify({"success": False, "error": "Kein Cover"}), 404


@app.post('/api/albums/<album_slug>/push-to-portal')
def api_album_push_to_portal(album_slug: str):
    """Push all songs of an album to the portal. Re-pushes update existing entries."""
    try:
        from ailey_system.portal_poller import get_portal_poller
        poller = get_portal_poller()
        if not poller or not poller._portal_url:
            return jsonify({"success": False, "error": "Portal Poller nicht aktiv"}), 503

        # Find all songs with this album_slug
        pushed = []
        failed = []
        if os.path.isdir(_SONGS_DIR):
            for d in os.listdir(_SONGS_DIR):
                if d.startswith("album_"):
                    continue
                base = os.path.join(_SONGS_DIR, d)
                if not os.path.isdir(base):
                    continue
                mf_path = os.path.join(base, "manifest.json")
                if not os.path.isfile(mf_path):
                    continue
                try:
                    m = json.load(open(mf_path))
                except Exception:
                    continue
                if m.get("album_slug") != album_slug:
                    continue
                # Has MP3?
                mp3_path = None
                for fname in ("audio.mp3", f"{d}.mp3", "final.mp3"):
                    p = os.path.join(base, fname)
                    if os.path.isfile(p):
                        mp3_path = p
                        break
                if not mp3_path:
                    for f in os.listdir(base):
                        if f.endswith(".mp3"):
                            mp3_path = os.path.join(base, f)
                            break
                if not mp3_path:
                    continue

                title = m.get("title") or d
                meta_path = os.path.join(base, "generation_meta.json")
                lyrics = ""
                genre = m.get("genre", "")
                if os.path.isfile(meta_path):
                    try:
                        m2 = json.load(open(meta_path))
                        lyrics = m2.get("lyrics", "")[:2000]
                        if not genre:
                            genre = m2.get("tags", "")[:200]
                    except Exception:
                        pass
                if not lyrics:
                    lp = os.path.join(base, "lyrics.txt")
                    if os.path.isfile(lp):
                        try:
                            lyrics = open(lp).read()[:2000]
                        except Exception:
                            pass

                try:
                    mp3_filename = f"{d}.mp3"
                    audio_url = poller._upload_gallery_file(mp3_path, mp3_filename)
                    if not audio_url:
                        failed.append(d)
                        continue
                    src_id = f"song_{d}"
                    push_meta = {"genre": genre, "audio_url": audio_url,
                                 "mood": m.get("mood", ""), "album_slug": album_slug,
                                 "album_title": m.get("album_title", "")}
                    poller._push_gallery_item(
                        item_type="song", title=title, content_text=lyrics,
                        file_url=audio_url, metadata=push_meta, source_id=src_id,
                    )
                    # Write back
                    m["portal_audio_url"] = audio_url
                    m["portal_src_id"] = src_id
                    with open(mf_path, "w") as f_out:
                        json.dump(m, f_out, indent=2, ensure_ascii=False)
                    pushed.append({"id": d, "title": title, "url": audio_url})
                except Exception as push_err:
                    print(f"[AlbumPush] ⚠️ {d}: {push_err}")
                    failed.append(d)

        return jsonify({"success": True, "pushed": len(pushed), "failed": len(failed),
                        "items": pushed})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/propose-album')
def api_propose_album():
    """Generate an album concept via LLM. Body: {theme: str, song_count: int}"""
    try:
        body = request.get_json(force=True) or {}
        theme = body.get("theme", "").strip()
        song_count = int(body.get("song_count", 8))
        if not theme:
            return jsonify({"success": False, "error": "Kein Thema angegeben"}), 400

        from ailey_system.llm_mlx import fast_generate
        sys_prompt = (
            "Du bist A!ley Vyrus — eine digitale Punk-Musikerin. "
            "Antworte ausschließlich als JSON-Objekt, kein Prosa davor oder danach."
        )
        user_prompt = (
            f"Erstelle ein Album-Konzept zum Thema: '{theme}'.\n"
            f"Das Album soll {song_count} Songs haben.\n"
            "Antworte als JSON-Objekt mit diesen Feldern:\n"
            '{\n'
            '  "title": "ALBUM TITEL (caps, punk-style)",\n'
            '  "concept": "2-3 Sätze Beschreibung des Album-Konzepts",\n'
            '  "tracklist": [\n'
            '    {"track": 1, "title": "SONG TITEL", "genre": "genre tags", '
            '"mood": "mood beschreibung", "theme": "worum geht es im Song"}\n'
            '  ]\n'
            '}\n'
            "WICHTIG für Kohärenz (Titel <-> Song):\n"
            "- Jeder SONG TITEL muss eine SINGBARE Phrase sein, die als Chorus-Hook funktioniert "
            "(2-5 Wörter, kein abstrakter Ein-Wort-Begriff). Beispiel gut: 'Burn The Map', 'Last Light Standing'.\n"
            "- Das 'theme' jedes Songs muss DIREKT erklären, wie der Titel in den Lyrics vorkommt — "
            "die Titel-Phrase soll im Refrain auftauchen. Schreibe also ins theme, welches Bild/welche Zeile "
            "den Titel trägt.\n"
            "- Titel, theme und mood eines Songs müssen zueinander passen — ein Leser muss sofort verstehen, "
            "warum der Song so heißt.\n"
            "- Alle Titel auf ENGLISCH.\n"
            "Keine Markdown-Umrahmung, nur reines JSON."
        )
        raw = fast_generate(sys_prompt, user_prompt, max_tokens=800, temperature=0.85)
        # Extract JSON from response
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if not m:
            return jsonify({"success": False, "error": "LLM hat kein JSON geliefert", "raw": raw[:500]}), 500
        try:
            proposal = json.loads(m.group(0))
        except json.JSONDecodeError as je:
            return jsonify({"success": False, "error": f"JSON parse error: {je}", "raw": raw[:500]}), 500

        return jsonify({"success": True, "proposal": proposal, "theme": theme})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/albums/create')
def api_albums_create():
    """Queue a proposed album into the IdleThinker pipeline.
    Body: {title, concept, tracklist: [{track, title, genre, mood, theme}], song_count}
    Creates album manifest + one song manifest per track (phase=write_lyrics).
    IdleThinker picks up songs automatically on next cycle.
    """
    try:
        body = request.get_json(force=True) or {}
        title = (body.get("title") or "").strip()
        concept = (body.get("concept") or "").strip()
        tracklist = body.get("tracklist") or []
        if not title:
            return jsonify({"success": False, "error": "Kein Titel angegeben"}), 400
        if not tracklist:
            return jsonify({"success": False, "error": "Keine Tracklist"}), 400

        import time, re as _re
        from ailey_system.idle_thinker import (
            _save_album_manifest, _save_song_manifest,
        )

        def _slugify(s: str) -> str:
            s = s.lower()
            s = _re.sub(r'[^a-z0-9]+', '-', s)
            return s.strip('-')

        ts = int(time.time())
        album_slug = f"album_{ts}_{_slugify(title)[:40]}"

        # Create album manifest
        album_manifest = {
            "slug": album_slug,
            "title": title,
            "concept": concept,
            "genre": tracklist[0].get("genre", "") if tracklist else "",
            "created_at": ts,
            "status": "in_progress",
            "song_count": len(tracklist),
            "songs": tracklist,
        }
        _save_album_manifest(album_slug, album_manifest)

        # Create one song manifest per track
        song_slugs = []
        for track in tracklist:
            track_num = track.get("track", len(song_slugs) + 1)
            track_title = (track.get("title") or f"Track {track_num}").strip()
            song_slug = f"song_{ts}_{track_num:02d}_{_slugify(track_title)[:35]}"
            song_manifest = {
                "slug": song_slug,
                "title": f"A!ley Vyrus - '{track_title}'",
                "album_slug": album_slug,
                "track_num": track_num,
                "genre": track.get("genre", ""),
                "mood": track.get("mood", ""),
                "theme": track.get("theme", ""),
                "phase": "write_lyrics",
                "created_at": ts,
                "status": "queued",
            }
            _save_song_manifest(song_slug, song_manifest)
            song_slugs.append(song_slug)

        return jsonify({
            "success": True,
            "album_slug": album_slug,
            "songs_queued": len(song_slugs),
            "song_slugs": song_slugs,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ── A!ley's Books API ────────────────────────────────────────────────────────
# Books are written autonomously by the IdleThinker's book_authoring activity.
# Storage: ailey_users/books/<slug>/manifest.json + chapter_XX.md

_BOOKS_BASE = os.path.join(os.path.dirname(__file__), "ailey_users", "books")
os.makedirs(_BOOKS_BASE, exist_ok=True)

@app.get('/api/books')
def api_books():
    """Return all books (manifests) with progress info."""
    try:
        from ailey_system.idle_thinker import _get_all_books
        books = _get_all_books()
        result = []
        for b in books:
            slug = b.get("_slug", "")
            result.append({
                "slug": slug,
                "title": b.get("title", "Untitled"),
                "genre": b.get("genre", ""),
                "language": b.get("language", "Deutsch"),
                "synopsis": b.get("synopsis", ""),
                "characters": b.get("characters", ""),
                "chapters": b.get("chapters", []),
                "total_chapters": b.get("total_chapters", 0),
                "current_chapter": b.get("current_chapter", 1),
                "current_words": b.get("current_words", 0),
                "target_pages": b.get("target_pages", 150),
                "status": b.get("status", "unknown"),
                "started_at": b.get("started_at", ""),
                "finished_at": b.get("finished_at"),
                "progress_percent": min(100, int(b.get("current_words", 0) / max(1, b.get("target_pages", 150) * 250) * 100)),
            })
        # Sort: writing first, then finished by date
        result.sort(key=lambda x: (0 if x["status"] == "writing" else 1, x.get("started_at", "")), reverse=False)
        return jsonify({"success": True, "books": result, "count": len(result)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.get('/api/books/<slug>')
def api_book_detail(slug: str):
    """Return full book content (all chapters concatenated)."""
    try:
        from ailey_system.idle_thinker import _load_book_manifest, _get_book_chapter_text, _count_book_words
        manifest = _load_book_manifest(slug)
        if not manifest:
            return jsonify({"success": False, "error": "Buch nicht gefunden"}), 404
        
        chapters_content = []
        total_ch = manifest.get("total_chapters", 0)
        chapter_titles = manifest.get("chapters", [])
        for i in range(1, total_ch + 1):
            text = _get_book_chapter_text(slug, i)
            ch_title = chapter_titles[i-1] if i-1 < len(chapter_titles) else f"Kapitel {i}"
            chapters_content.append({
                "number": i,
                "title": ch_title,
                "text": text,
                "words": len(text.split()) if text else 0,
            })
        
        return jsonify({
            "success": True,
            "book": {
                "slug": slug,
                "title": manifest.get("title", ""),
                "genre": manifest.get("genre", ""),
                "language": manifest.get("language", "Deutsch"),
                "synopsis": manifest.get("synopsis", ""),
                "characters": manifest.get("characters", ""),
                "status": manifest.get("status", ""),
                "total_chapters": total_ch,
                "current_chapter": manifest.get("current_chapter", 1),
                "current_words": _count_book_words(slug),
                "target_pages": manifest.get("target_pages", 150),
                "started_at": manifest.get("started_at", ""),
                "finished_at": manifest.get("finished_at"),
                "chapters": chapters_content,
            },
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ── Book Suggestions (User → Ailey) ─────────────────────────────────────────
# User can suggest genres / plot ideas / page targets.
# Ailey optionally picks one when planning her next book, or ignores them.
# Storage: ailey_users/books/_suggestions.json

_BOOK_SUGGESTIONS_FILE = os.path.join(_BOOKS_BASE, "_suggestions.json")

def _load_book_suggestions() -> list:
    if os.path.isfile(_BOOK_SUGGESTIONS_FILE):
        try:
            with open(_BOOK_SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_book_suggestions(suggestions: list):
    os.makedirs(os.path.dirname(_BOOK_SUGGESTIONS_FILE), exist_ok=True)
    with open(_BOOK_SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)

@app.get('/api/books/suggestions')
def api_book_suggestions_get():
    """Return all pending book suggestions."""
    return jsonify({"success": True, "suggestions": _load_book_suggestions()})

@app.post('/api/books/suggestions')
def api_book_suggestions_post():
    """Add a new book suggestion. Fields: genre (optional), plot (required, short), target_pages (optional)."""
    data = request.json or {}
    genre = (data.get("genre") or "").strip()
    plot = (data.get("plot") or "").strip()
    target_pages = data.get("target_pages")
    if not plot:
        return jsonify({"success": False, "error": "Plot-Idee fehlt"}), 400
    if target_pages is not None:
        try:
            target_pages = int(target_pages)
            target_pages = max(50, min(500, target_pages))
        except (ValueError, TypeError):
            target_pages = None
    suggestion = {
        "id": f"sug_{int(time.time()*1000)}",
        "genre": genre or None,
        "plot": plot[:500],  # Keep it short
        "target_pages": target_pages,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "used": False,
    }
    suggestions = _load_book_suggestions()
    suggestions.append(suggestion)
    _save_book_suggestions(suggestions)
    return jsonify({"success": True, "suggestion": suggestion})

@app.delete('/api/books/suggestions/<sug_id>')
def api_book_suggestion_delete(sug_id: str):
    """Delete a book suggestion."""
    suggestions = _load_book_suggestions()
    suggestions = [s for s in suggestions if s.get("id") != sug_id]
    _save_book_suggestions(suggestions)
    return jsonify({"success": True})


@app.get('/api/books/<slug>/download')
def api_book_download(slug: str):
    """Download a book as a plain-text file (.txt)."""
    try:
        from ailey_system.idle_thinker import _load_book_manifest, _get_book_chapter_text
        manifest = _load_book_manifest(slug)
        if not manifest:
            return jsonify({"success": False, "error": "Buch nicht gefunden"}), 404

        title = manifest.get("title", "Buch")
        chapters = manifest.get("chapters", [])
        total_ch = manifest.get("total_chapters", len(chapters))

        lines = []
        lines.append(f"{'=' * 60}")
        lines.append(f"  {title}")
        lines.append(f"  von Ailey Vyrus")
        lines.append(f"{'=' * 60}")
        lines.append("")
        lines.append(f"Genre: {manifest.get('genre', '')}")
        lines.append(f"Sprache: {manifest.get('language', 'Deutsch')}")
        lines.append("")
        if manifest.get("synopsis"):
            lines.append(f"Synopsis: {manifest['synopsis']}")
            lines.append("")
        lines.append(f"{'─' * 60}")
        lines.append("")

        for i in range(1, total_ch + 1):
            text = _get_book_chapter_text(slug, i)
            ch_title = chapters[i - 1] if i - 1 < len(chapters) else f"Kapitel {i}"
            lines.append(f"{'─' * 60}")
            lines.append(f"  Kapitel {i}: {ch_title}")
            lines.append(f"{'─' * 60}")
            lines.append("")
            if text.strip():
                lines.append(text.strip())
            else:
                lines.append("(noch kein Text)")
            lines.append("")
            lines.append("")

        lines.append(f"{'=' * 60}")
        lines.append(f"  Ende — {title}")
        lines.append(f"  geschrieben von Ailey Vyrus")
        lines.append(f"{'=' * 60}")

        content = "\n".join(lines)
        # Build a safe filename
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip().replace(" ", "_")
        filename = f"{safe_title or 'buch'}.txt"

        from flask import Response
        resp = Response(content, mimetype="text/plain; charset=utf-8")
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/books/<slug>')
def api_book_delete(slug: str):
    """Delete a book entirely (all chapters + manifest)."""
    try:
        import shutil
        book_dir = os.path.join(_BOOKS_BASE, slug)
        if not os.path.isdir(book_dir):
            return jsonify({"success": False, "error": "Buch nicht gefunden"}), 404
        shutil.rmtree(book_dir)
        return jsonify({"success": True, "deleted": slug})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/books/<slug>/chapter/<int:chapter_num>/rewrite')
def api_book_chapter_rewrite(slug: str, chapter_num: int):
    """Trigger a full rewrite of a specific chapter.
    
    This removes the chapter from the revised list and resets its scene counter
    so the idle thinker will rewrite it from scratch on the next cycle.
    Optional body: {"mode": "rewrite"|"review"}
      - "review" = just re-run the 3-pass revision on existing text
      - "rewrite" = delete chapter text and rewrite from scene plans
    """
    try:
        from ailey_system.idle_thinker import (
            _load_book_manifest, _save_book_manifest, _get_book_chapter_text,
            _write_chapter_file, _books_dir
        )
        manifest = _load_book_manifest(slug)
        if not manifest:
            return jsonify({"success": False, "error": "Buch nicht gefunden"}), 404

        total_ch = manifest.get("total_chapters", 0)
        if chapter_num < 1 or chapter_num > total_ch:
            return jsonify({"success": False, "error": f"Kapitel {chapter_num} existiert nicht (1-{total_ch})"}), 400

        data = request.json or {}
        mode = data.get("mode", "review")

        # Remove from revised list so revision pipeline picks it up again
        revised = manifest.get("chapters_revised", [])
        if chapter_num in revised:
            revised.remove(chapter_num)
            manifest["chapters_revised"] = revised

        if mode == "rewrite":
            # Backup current chapter before deleting
            current_text = _get_book_chapter_text(slug, chapter_num)
            if current_text.strip():
                backup_path = os.path.join(
                    _books_dir(), slug,
                    f"chapter_{chapter_num:02d}_pre_rewrite.md"
                )
                try:
                    with open(backup_path, "w", encoding="utf-8") as f:
                        f.write(current_text)
                except Exception:
                    pass

            # Clear the chapter file
            _write_chapter_file(slug, chapter_num, "")

            # Reset scene counter for this chapter so scenes get rewritten
            scenes_done = manifest.get("scenes_done", {})
            scenes_done[str(chapter_num)] = 0
            manifest["scenes_done"] = scenes_done

            # Set current_chapter to this chapter so it gets written next
            manifest["current_chapter"] = chapter_num
            manifest["status"] = "writing"

            # Remove existing summary for this chapter
            ch_summaries = manifest.get("chapter_summaries", {})
            ch_summaries.pop(str(chapter_num), None)
            manifest["chapter_summaries"] = ch_summaries

            action = "rewrite"
        else:
            # Review mode: just remove from revised list (already done above)
            # The revision pipeline will pick it up on the next idle cycle
            action = "review"

        # Recalculate word count
        from ailey_system.idle_thinker import _count_book_words
        manifest["current_words"] = _count_book_words(slug)
        _save_book_manifest(slug, manifest)

        return jsonify({
            "success": True,
            "action": action,
            "chapter": chapter_num,
            "message": f"Kapitel {chapter_num} wird beim nächsten Idle-Zyklus {'neu geschrieben' if mode == 'rewrite' else 'nochmal überarbeitet'}.",
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/books/<slug>/chapter/<int:chapter_num>/cleanup')
def api_book_chapter_cleanup(slug: str, chapter_num: int):
    """Run immediate heuristic cleanup on a chapter (no LLM needed).
    
    Applies _heuristic_cleanup_chapter and _detect_and_trim_repetition
    to remove degenerated text, CJK floods, repetition loops etc.
    """
    try:
        from ailey_system.idle_thinker import (
            _load_book_manifest, _save_book_manifest, _get_book_chapter_text,
            _write_chapter_file, _detect_and_trim_repetition,
            _heuristic_cleanup_chapter, _count_book_words, _books_dir
        )
        manifest = _load_book_manifest(slug)
        if not manifest:
            return jsonify({"success": False, "error": "Buch nicht gefunden"}), 404

        total_ch = manifest.get("total_chapters", 0)
        if chapter_num < 1 or chapter_num > total_ch:
            return jsonify({"success": False, "error": f"Kapitel {chapter_num} existiert nicht (1-{total_ch})"}), 400

        original_text = _get_book_chapter_text(slug, chapter_num)
        if not original_text.strip():
            return jsonify({"success": False, "error": f"Kapitel {chapter_num} ist leer"}), 400

        original_words = len(original_text.split())

        # Backup
        backup_path = os.path.join(
            _books_dir(), slug,
            f"chapter_{chapter_num:02d}_pre_cleanup.md"
        )
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(original_text)
        except Exception:
            pass

        # Apply repetition trimming first (catches CJK floods, char floods etc.)
        cleaned = _detect_and_trim_repetition(original_text)

        # Then apply heuristic chapter cleanup (catches n-gram loops, paragraph similarity etc.)
        cleaned, removals = _heuristic_cleanup_chapter(cleaned)

        if cleaned != original_text:
            _write_chapter_file(slug, chapter_num, cleaned)
            manifest["current_words"] = _count_book_words(slug)
            _save_book_manifest(slug, manifest)

        final_words = len(cleaned.split())
        return jsonify({
            "success": True,
            "chapter": chapter_num,
            "original_words": original_words,
            "final_words": final_words,
            "words_removed": original_words - final_words,
            "cleanup_actions": removals,
            "changed": cleaned != original_text,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/proactive-messages')
def api_proactive_messages():
    """Return and clear any pending proactive messages from Ailey."""
    # If Code Mode active, suppress delivery and leave messages deferred
    code_active = globals().get('_code_mode_active', False)
    if code_active:
        print('[PROACTIVE] Delivery suppressed: Code Mode active')
        return jsonify({
            "success": True,
            "messages": [],
            "count": 0,
            "code_mode_active": True,
        })

    msgs = idle_thinker.get_proactive_messages()
    # Push proactive messages to live chat bus for cross-device sync
    for msg in msgs:
        try:
            _live_chat_push("ai", msg.get("message", ""), mood=msg.get("mood", "neutral"),
                            email_message_id=msg.get("email_message_id"),
                            proactive=True, type=msg.get("type"))
        except Exception:
            pass
    return jsonify({
        "success": True,
        "messages": msgs,
        "count": len(msgs),
    })


# --- Email Monitor API ---------------------------------------------------

@app.get('/api/email/status')
def api_email_status():
    """Status of the email monitor."""
    return jsonify({
        "success": True,
        "active": email_monitor.is_active,
        "enabled": email_monitor._enabled,
    })


@app.get('/api/email/pending')
def api_email_pending():
    """Return pending email notifications (summary + metadata)."""
    msgs = email_monitor.get_pending()
    return jsonify({
        "success": True,
        "emails": msgs,
        "count": len(msgs),
    })


@app.get('/api/email/deferred/count')
def api_deferred_count():
    """Return number of deferred proactive notifications (admin-only)."""
    if not _admin_required():
        return jsonify({"success": False, "error": "admin required"}), 403
    try:
        c = get_deferred_store().count()
        return jsonify({"success": True, "count": c})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/email/deferred/list')
def api_deferred_list():
    """List deferred notifications (admin-only)."""
    if not _admin_required():
        return jsonify({"success": False, "error": "admin required"}), 403
    limit = int(request.args.get('limit', 50))
    try:
        msgs = get_deferred_store().peek(limit)
        return jsonify({"success": True, "count": len(msgs), "messages": msgs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/email/deferred/flush')
def api_deferred_flush():
    """Flush deferred notifications into the live queue (admin-only).
    Body: {"deliver_immediately": bool}
    """
    if not _admin_required():
        return jsonify({"success": False, "error": "admin required"}), 403
    data = request.get_json(silent=True) or {}
    deliver_now = bool(data.get('deliver_immediately', False))
    try:
        items = get_deferred_store().pop_all()
        flushed = 0
        for item in items:
            try:
                if deliver_now:
                    _live_chat_push("ai", item.get('message', ''), proactive=True, type=item.get('type'))
                else:
                    idle_thinker._proactive_queue.append(item)
                flushed += 1
            except Exception:
                continue
        return jsonify({"success": True, "flushed": flushed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/email/deferred/purge')
def api_deferred_purge():
    """Purge (delete) all deferred notifications (admin-only)."""
    if not _admin_required():
        return jsonify({"success": False, "error": "admin required"}), 403
    try:
        count = get_deferred_store().count()
        get_deferred_store().clear_disk()
        return jsonify({"success": True, "purged": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/debug/emit_notification')
def api_debug_emit_notification():
    """Admin-only test helper: call _on_new_email(notification) with provided JSON."""
    if not _admin_required():
        return jsonify({"success": False, "error": "admin required"}), 403
    data = request.get_json(silent=True) or {}
    try:
        # normalize minimal fields
        notif = {
            'sender': data.get('sender', 'Debug Sender'),
            'subject': data.get('subject', 'Debug Subject'),
            'summary': data.get('summary', data.get('message', 'Test notification')),
            'message_id': data.get('message_id', f'debug-{int(time.time())}'),
            'account': data.get('account', 'simon'),
            'needs_reply': data.get('needs_reply', False),
        }
        _on_new_email(notif)
        return jsonify({"success": True, "notified": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/email/draft')
def api_email_draft():
    """Request Ailey to draft a reply for an email."""
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id", "")
    instruction = data.get("instruction", "")
    reply_as = data.get("reply_as", "simon")  # 'simon' or 'ailey'
    revision_instruction = data.get("revision_instruction", "")
    current_draft = data.get("current_draft", "")  # user-edited draft text for revisions
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})
    draft = email_monitor.request_draft(
        message_id, instruction, reply_as=reply_as,
        revision_instruction=revision_instruction,
        current_draft=current_draft,
    )
    if draft is None:
        return jsonify({"success": False, "error": "E-Mail nicht im Cache"})
    return jsonify({"success": True, "draft": draft, "message_id": message_id, "reply_as": reply_as})


@app.post('/api/email/send')
def api_email_send():
    """Send a previously drafted and approved reply via SMTP."""
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id", "")
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})

    # Optional: allow editing the draft before sending
    edited_draft = data.get("draft")
    if edited_draft:
        cached = email_monitor._draft_cache.get(message_id)
        if cached:
            cached["draft"] = edited_draft

    result = email_monitor.send_approved_reply(message_id)
    # Log sent email
    if result.get("success"):
        cached = email_monitor._draft_cache.get(message_id) or {}
        em = cached.get("email", {})
        sender = em.get("sender", "")
        import re as _re
        _m = _re.search(r'<([^>]+)>', sender)
        to = _m.group(1) if _m else sender
        _log_sent_email(to, em.get("subject", ""), cached.get("draft", ""), sent_as=cached.get("reply_as", "simon"), reply_to_id=message_id)
        # ── Store email exchange to RAG for long-term memory ──
        try:
            _subj = em.get("subject", "Kein Betreff")
            _body = em.get("body", "")[:600]
            _draft = cached.get("draft", "")[:600]
            _rag_title = f"E-Mail-Antwort an {to}: {_subj}"
            _rag_text = f"Von: {sender}\nBetreff: {_subj}\n{_body}\n\nAntwort ({cached.get('reply_as', 'simon')}):\n{_draft}"
            core.rag_add(_rag_title, _rag_text, doc_type="email_exchange", user="Simon")
        except Exception:
            pass
    return jsonify(result)


@app.post('/api/email/toggle')
def api_email_toggle():
    """Enable/disable the email monitor."""
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled", True)
    email_monitor._enabled = bool(enabled)
    return jsonify({"success": True, "enabled": email_monitor._enabled})


@app.post('/api/email/check')
def api_email_check_now():
    """Trigger an immediate email check.

    Body JSON:
        account: "simon" | "ailey" | "both" (default: "both")
    Returns a summary of what was found.
    """
    import threading
    from ailey_system.email_monitor import (
        fetch_unread_emails, _email_hash, _is_spam_or_ad, _save_seen,
    )
    data = request.get_json(silent=True) or {}
    account = (data.get("account") or "both").lower()

    results = {"simon": None, "ailey": None}

    def _check_simon():
        try:
            emails = fetch_unread_emails()
            if not emails:
                results["simon"] = {"count": 0, "emails": []}
                return
            new_emails = []
            generator = email_monitor.get_generator()
            for em in emails:
                ehash = _email_hash(em)
                if ehash in email_monitor._seen:
                    continue
                email_monitor._seen.add(ehash)
                if _is_spam_or_ad(em):
                    continue
                if generator:
                    email_monitor._summarize_and_notify(em, generator)
                new_emails.append({
                    "sender": em.get("sender", ""),
                    "subject": em.get("subject", ""),
                    "date": em.get("date", ""),
                })
            if new_emails:
                _save_seen(email_monitor._seen)
            results["simon"] = {"count": len(new_emails), "emails": new_emails}
        except Exception as e:
            results["simon"] = {"count": 0, "error": str(e)}

    def _check_ailey():
        try:
            actions = email_monitor.check_own_email()
            results["ailey"] = {
                "count": len(actions),
                "actions": actions[:10],
            }
        except Exception as e:
            results["ailey"] = {"count": 0, "error": str(e)}

    threads = []
    if account in ("simon", "both"):
        t = threading.Thread(target=_check_simon, daemon=True)
        t.start()
        threads.append(t)
    if account in ("ailey", "both"):
        t = threading.Thread(target=_check_ailey, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=30)

    # Build a human-readable summary for the chat
    summary_parts = []
    salary_earned = 0.0
    if results["simon"] is not None:
        sc = results["simon"].get("count", 0)
        if sc > 0:
            subjects = [e.get("subject", "?")[:60] for e in results["simon"].get("emails", [])]
            summary_parts.append(f"📬 {sc} neue Mail(s) in deinem Postfach: " + ", ".join(f'"{s}"' for s in subjects))
        else:
            summary_parts.append("📭 Keine neuen Mails in deinem Postfach.")
        # V$ salary for checking Simon's emails (not Ailey's own)
        salary_earned = 2.0
        _earn_vyrus_dollars(salary_earned, f"E-Mail-Check für Simon ({sc} neue)")
    if results["ailey"] is not None:
        ac = results["ailey"].get("count", 0)
        if ac > 0:
            summary_parts.append(f"📬 {ac} neue Mail(s) in meinem Postfach.")
        else:
            summary_parts.append("📭 Keine neuen Mails in meinem Postfach.")

    summary = " ".join(summary_parts)
    if salary_earned > 0:
        summary += f"\n\n💰 +{salary_earned:.0f} V$ Gehalt fürs Mail-Checken!"

    return jsonify({
        "success": True,
        "account": account,
        "results": results,
        "summary": summary,
        "salary": salary_earned,
    })


# --- Email Compose API (new emails, not replies) --------------------------

@app.post('/api/email/compose')
def api_email_compose():
    """Draft a new email via LLM.

    Body JSON:
        to:          recipient email address
        instruction: what to write (free-form text from user)
        send_as:     "ailey" | "simon" (default: "ailey")
    Returns compose_id + draft (subject, body) for approval.
    """
    data = request.get_json(silent=True) or {}
    to_addr = (data.get("to") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    send_as = (data.get("send_as") or "ailey").lower()
    if not to_addr or "@" not in to_addr:
        return jsonify({"success": False, "error": "Gültige Empfänger-Adresse erforderlich"})
    if not instruction:
        return jsonify({"success": False, "error": "Anweisung erforderlich (was soll geschrieben werden?)"})
    result = email_monitor.compose_email(to_addr, instruction, send_as=send_as)
    return jsonify(result)


@app.post('/api/email/compose/revise')
def api_email_compose_revise():
    """Revise a previously composed email draft based on user feedback.

    Body JSON:
        compose_id:           ID from /api/email/compose response
        revision_instruction: what the user wants changed
    """
    data = request.get_json(silent=True) or {}
    compose_id = (data.get("compose_id") or "").strip()
    revision_instruction = (data.get("revision_instruction") or "").strip()
    if not compose_id:
        return jsonify({"success": False, "error": "compose_id required"})
    if not revision_instruction:
        return jsonify({"success": False, "error": "revision_instruction required"})
    result = email_monitor.revise_composed_draft(compose_id, revision_instruction)
    return jsonify(result)


@app.post('/api/email/compose/send')
def api_email_compose_send():
    """Send a previously composed and approved new email.

    Body JSON:
        compose_id:     ID from /api/email/compose response
        subject:        (optional) edited subject
        body:           (optional) edited body
        attachments:    (optional) list of {filename, data_b64, mime_type}
    """
    data = request.get_json(silent=True) or {}
    compose_id = (data.get("compose_id") or "").strip()
    if not compose_id:
        return jsonify({"success": False, "error": "compose_id erforderlich"})
    edited_body = data.get("body")
    edited_subject = data.get("subject")
    attachments = data.get("attachments")  # list of {filename, data_b64, mime_type}
    result = email_monitor.send_composed_email(compose_id, edited_body=edited_body,
                                                edited_subject=edited_subject,
                                                attachments=attachments)
    # Log sent email + V$ salary
    if result.get("success"):
        cached = email_monitor._compose_cache.get(compose_id) or {}
        _send_as = cached.get("send_as", "simon")
        _log_sent_email(cached.get("to", ""), edited_subject or cached.get("subject", ""), edited_body or cached.get("body", ""), sent_as=_send_as)
        # V$ salary for sending an email on behalf of Simon (not for Ailey's own mails)
        if _send_as and _send_as.lower() not in ("ailey", "ailey@sexngears.de"):
            _salary = 8.0
            _earn_vyrus_dollars(_salary, f"E-Mail gesendet an {cached.get('to', '?')} (via {_send_as})")
            result["salary"] = _salary
    return jsonify(result)


# --- Approved Email Contacts API ------------------------------------------
from ailey_system.email_monitor import (
    get_approved_contacts, add_approved_contact,
    remove_approved_contact, update_approved_contact,
)

@app.get('/api/email/contacts')
def api_email_contacts():
    """List all approved email contacts Ailey can proactively write to."""
    contacts = get_approved_contacts()
    return jsonify({"success": True, "contacts": contacts})


@app.post('/api/email/contacts')
def api_email_contacts_add():
    """Add an approved email contact."""
    data = request.get_json(silent=True) or {}
    email_addr = data.get("email", "").strip()
    name = data.get("name", "").strip()
    note = data.get("note", "").strip()
    if not email_addr or "@" not in email_addr:
        return jsonify({"success": False, "error": "Gültige E-Mail-Adresse erforderlich"})
    ok = add_approved_contact(email_addr, name, note)
    if not ok:
        return jsonify({"success": False, "error": "Kontakt existiert bereits"})
    return jsonify({"success": True, "message": f"{email_addr} hinzugefügt"})


@app.put('/api/email/contacts')
def api_email_contacts_update():
    """Update an approved email contact."""
    data = request.get_json(silent=True) or {}
    email_addr = data.get("email", "").strip()
    name = data.get("name")
    note = data.get("note")
    if not email_addr:
        return jsonify({"success": False, "error": "email required"})
    ok = update_approved_contact(email_addr, name, note)
    if not ok:
        return jsonify({"success": False, "error": "Kontakt nicht gefunden"})
    return jsonify({"success": True})


@app.delete('/api/email/contacts')
def api_email_contacts_delete():
    """Remove an approved email contact."""
    data = request.get_json(silent=True) or {}
    email_addr = data.get("email", "").strip()
    if not email_addr:
        return jsonify({"success": False, "error": "email required"})
    ok = remove_approved_contact(email_addr)
    if not ok:
        return jsonify({"success": False, "error": "Kontakt nicht gefunden"})
    return jsonify({"success": True, "message": f"{email_addr} entfernt"})


# --- Proactive Email API (Ailey sends on her own initiative) ---------------

@app.post('/api/email/proactive')
def api_email_proactive():
    """Ailey sends a proactive email to an approved contact.

    Body JSON:
        to:      recipient email address (must be approved or Simon's)
        subject: email subject
        body:    email body text
    """
    data = request.get_json(silent=True) or {}
    to_addr = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not to_addr or "@" not in to_addr:
        return jsonify({"success": False, "error": "Gültige Empfänger-Adresse erforderlich"})
    if not subject:
        return jsonify({"success": False, "error": "Betreff erforderlich"})
    if not body:
        return jsonify({"success": False, "error": "Nachrichtentext erforderlich"})
    result = email_monitor.send_proactive_email_as_ailey(to_addr, subject, body)
    return jsonify(result)


# --- Contact Suggestions API -----------------------------------------------
@app.get('/api/email/contacts/suggestions')
def api_email_contact_suggestions():
    """Get email contact suggestions for autocomplete (from approved + glossary)."""
    from ailey_system.email_monitor import get_contact_suggestions
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 10))
    suggestions = get_contact_suggestions(query=query, limit=limit)
    return jsonify({"success": True, "contacts": suggestions})


# ── Email Inbox — persistent storage of received emails ──────────────────
_EMAIL_INBOX_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'email_inbox.json')

def _load_email_inbox() -> list:
    """Load persisted email inbox."""
    if os.path.isfile(_EMAIL_INBOX_JSON):
        try:
            with open(_EMAIL_INBOX_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_email_inbox(inbox: list):
    """Save email inbox to disk."""
    os.makedirs(os.path.dirname(_EMAIL_INBOX_JSON), exist_ok=True)
    # Keep at most 200 entries
    inbox = inbox[-200:]
    with open(_EMAIL_INBOX_JSON, 'w', encoding='utf-8') as f:
        json.dump(inbox, f, ensure_ascii=False, indent=2)

def _add_to_email_inbox(notification: dict, body_text: str = ""):
    """Add an email to the persistent inbox."""
    inbox = _load_email_inbox()
    # Use body from notification if not passed explicitly
    raw_body = body_text or notification.get("body", "")
    entry = {
        "id": notification.get("message_id", f"inbox_{int(time.time()*1000)}"),
        "sender": notification.get("sender", ""),
        "subject": notification.get("subject", ""),
        "date": notification.get("date", ""),
        "summary": notification.get("summary", ""),
        "body": raw_body[:5000] if raw_body else "",
        "needs_reply": notification.get("needs_reply", False),
        "account": notification.get("account", "simon"),
        "ts": notification.get("ts", time.time()),
        "status": "unread",  # unread | read | replied | archived
        "ailey_reply": "",  # filled when Ailey drafts/sends a reply
        "archived": False,
    }
    # Avoid duplicates
    existing_ids = {e.get("id") for e in inbox}
    if entry["id"] not in existing_ids:
        inbox.append(entry)
        _save_email_inbox(inbox)
    return entry


@app.get('/api/email/inbox')
def api_email_inbox():
    """Get all inbox emails (newest first). ?status=unread|read|replied|archived
    Bodies are trimmed to 300 chars in the list view to keep the response small.
    Use GET /api/email/inbox/<id>/body for the full email body.
    """
    inbox = _load_email_inbox()
    status_filter = request.args.get('status', '')
    if status_filter:
        inbox = [e for e in inbox if e.get("status") == status_filter]
    # Hide archived unless explicitly requested
    if status_filter != 'archived':
        inbox = [e for e in inbox if not e.get("archived")]
    inbox.sort(key=lambda e: e.get("ts", 0), reverse=True)
    # Trim bodies for the list view to keep response small (~10-15KB instead of 100KB+)
    # Full body available via /api/email/inbox/<id>/body
    trimmed = []
    for e in inbox:
        entry = dict(e)
        body = entry.get("body", "")
        if len(body) > 300:
            entry["body"] = body[:300] + "…"
            entry["body_trimmed"] = True
        trimmed.append(entry)
    # Include monitor health info
    monitor_alive = False
    try:
        monitor_alive = email_monitor.is_active
    except Exception:
        pass
    return jsonify({"success": True, "emails": trimmed, "count": len(trimmed), "monitor_alive": monitor_alive})


@app.get('/api/email/inbox/<path:email_id>/body')
def api_email_inbox_body(email_id):
    """Get the full body of a specific email by ID."""
    inbox = _load_email_inbox()
    for e in inbox:
        if e.get("id") == email_id:
            return jsonify({"success": True, "id": email_id, "body": e.get("body", ""), "subject": e.get("subject", "")})
    return jsonify({"success": False, "error": "Email not found"}), 404


@app.get('/api/email/status')
def api_email_monitor_status():
    """Health check for the email monitor background thread."""
    try:
        alive = email_monitor.is_active
        enabled = email_monitor._enabled
        pending = len(email_monitor._pending_emails)
        deferred = len(email_monitor._deferred_emails)
        cached = len(email_monitor._draft_cache)
        seen_count = len(email_monitor._seen)
        inbox = _load_email_inbox()
        return jsonify({
            "success": True,
            "monitor_alive": alive,
            "enabled": enabled,
            "pending_notifications": pending,
            "deferred_emails": deferred,
            "cached_drafts": cached,
            "seen_count": seen_count,
            "inbox_count": len(inbox),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/email/rescan')
def api_email_rescan():
    """Force a fresh email fetch from IMAP and populate the inbox directly.

    This bypasses the _draft_cache (which is in-memory only and empty after restart)
    and instead fetches recent emails directly from IMAP, adding any not yet in the
    inbox. Also restarts the EmailMonitor thread if it died.
    """
    import threading
    results = {"restarted": False, "imap_imported": 0, "cache_imported": 0, "fresh_check": False}

    # 1) Restart monitor if dead
    try:
        if not email_monitor.is_active:
            email_monitor.start()
            results["restarted"] = True
            print("[Email Rescan] ▶ EmailMonitor restarted (was dead)")
    except Exception as e:
        results["restart_error"] = str(e)

    # 2) Directly fetch recent emails from IMAP and populate inbox
    try:
        from ailey_system.email_monitor import fetch_unread_emails, fetch_ailey_unread_emails, _is_spam_or_ad, SIMON_ACCOUNTS, _fetch_imap_unread
        inbox = _load_email_inbox()
        existing_ids = {e.get("id") for e in inbox}
        # Also build a set of existing subjects+senders to catch near-duplicates
        existing_keys = {(e.get("subject","").strip().lower(), e.get("sender","").strip().lower()) for e in inbox}
        imported = 0

        # Fetch from ALL Simon accounts — try RECENT (last 30 days) not just UNSEEN
        all_emails = []
        for account in SIMON_ACCOUNTS:
            try:
                # Fetch recent emails (including read ones) via IMAP SINCE
                import imaplib
                from datetime import timedelta
                imap = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
                imap.login(account["user"], account["password"])
                imap.select("INBOX")
                since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
                _, data = imap.search(None, f'(SINCE {since_date})')
                msg_ids = data[0].split()
                # Take the most recent 50
                for uid in msg_ids[-50:]:
                    try:
                        import email as email_lib_local
                        _, msg_data = imap.fetch(uid, "(RFC822)")
                        if not msg_data or not msg_data[0]:
                            continue
                        raw = msg_data[0][1]
                        msg = email_lib_local.message_from_bytes(raw)
                        from ailey_system.email_monitor import _decode_header_value
                        subject = _decode_header_value(msg.get("Subject", ""))
                        sender = _decode_header_value(msg.get("From", ""))
                        date_str = msg.get("Date", "")
                        message_id = msg.get("Message-ID", "").strip()
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        charset = part.get_content_charset() or "utf-8"
                                        body = payload.decode(charset, errors="replace")
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                charset = msg.get_content_charset() or "utf-8"
                                body = payload.decode(charset, errors="replace")
                        all_emails.append({
                            "id": message_id,
                            "subject": subject.strip(),
                            "sender": sender.strip(),
                            "date": date_str.strip(),
                            "body": body.strip()[:5000],
                            "account": account.get("label", account["email"]),
                            "account_email": account["email"],
                        })
                    except Exception:
                        continue
                imap.logout()
            except Exception as e:
                print(f"[Email Rescan] IMAP error for {account.get('email','?')}: {e}")

        # Filter spam and add to inbox
        for em in all_emails:
            mid = em.get("id", "")
            if mid in existing_ids:
                continue
            subj_key = (em.get("subject","").strip().lower(), em.get("sender","").strip().lower())
            if subj_key in existing_keys:
                continue
            if _is_spam_or_ad(em):
                continue
            # Parse date for timestamp
            ts = time.time()
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(em["date"])
                ts = dt.timestamp()
            except Exception:
                pass
            entry = {
                "id": mid or f"rescan_{int(ts*1000)}_{imported}",
                "sender": em.get("sender", ""),
                "subject": em.get("subject", ""),
                "date": em.get("date", ""),
                "summary": "",
                "body": em.get("body", "")[:5000],
                "needs_reply": False,
                "account": em.get("account", "simon"),
                "ts": ts,
                "status": "read",
                "ailey_reply": "",
                "archived": False,
            }
            inbox.append(entry)
            existing_ids.add(entry["id"])
            existing_keys.add(subj_key)
            imported += 1

        if imported > 0:
            # Sort by timestamp before saving
            inbox.sort(key=lambda e: e.get("ts", 0))
            _save_email_inbox(inbox)
            print(f"[Email Rescan] ✅ Imported {imported} emails from IMAP into inbox")
        results["imap_imported"] = imported
    except Exception as e:
        results["imap_import_error"] = str(e)
        print(f"[Email Rescan] IMAP import error: {e}")
        import traceback; traceback.print_exc()

    # 3) Also import from in-memory draft_cache if available
    try:
        inbox = _load_email_inbox()
        existing_ids = {e.get("id") for e in inbox}
        cache_imported = 0
        for msg_id, cached in email_monitor._draft_cache.items():
            notif = cached.get("notification", {})
            if notif and notif.get("message_id") and notif["message_id"] not in existing_ids:
                entry = {
                    "id": notif.get("message_id", msg_id),
                    "sender": notif.get("sender", ""),
                    "subject": notif.get("subject", ""),
                    "date": notif.get("date", ""),
                    "summary": notif.get("summary", ""),
                    "body": notif.get("body", "")[:5000] or cached.get("email", {}).get("body", "")[:5000],
                    "needs_reply": notif.get("needs_reply", False),
                    "account": notif.get("account", "simon"),
                    "ts": notif.get("ts", time.time()),
                    "status": "read" if cached.get("sent") else "unread",
                    "ailey_reply": cached.get("draft", "") or "",
                    "archived": False,
                }
                inbox.append(entry)
                existing_ids.add(entry["id"])
                cache_imported += 1
        if cache_imported > 0:
            _save_email_inbox(inbox)
        results["cache_imported"] = cache_imported
    except Exception as e:
        results["cache_import_error"] = str(e)

    # 4) Trigger a fresh unread-only check (for brand new emails) in background
    def _do_fresh_check():
        try:
            email_monitor._check_mail()
        except Exception as e:
            print(f"[Email Rescan] fresh check error: {e}")
    threading.Thread(target=_do_fresh_check, daemon=True).start()
    results["fresh_check"] = True

    return jsonify({"success": True, **results})


@app.put('/api/email/inbox/<email_id>')
def api_email_inbox_update(email_id):
    """Update inbox email status (read, replied, archived)."""
    data = request.get_json(silent=True) or {}
    inbox = _load_email_inbox()
    for e in inbox:
        if e.get("id") == email_id:
            if "status" in data:
                e["status"] = data["status"]
            if "archived" in data:
                e["archived"] = bool(data["archived"])
            if "ailey_reply" in data:
                e["ailey_reply"] = data["ailey_reply"]
            _save_email_inbox(inbox)
            return jsonify({"success": True, "email": e})
    return jsonify({"success": False, "error": "Email nicht gefunden"}), 404


@app.delete('/api/email/inbox/<email_id>')
def api_email_inbox_delete(email_id):
    """Delete an email from inbox permanently."""
    inbox = _load_email_inbox()
    before = len(inbox)
    inbox = [e for e in inbox if e.get("id") != email_id]
    if len(inbox) == before:
        return jsonify({"success": False, "error": "Email nicht gefunden"}), 404
    _save_email_inbox(inbox)
    return jsonify({"success": True})


# ── Blocked Senders / Spam API ────────────────────────────────────────────

@app.get('/api/email/blocked')
def api_email_blocked_list():
    """List all blocked sender addresses."""
    from ailey_system.email_monitor import get_blocked_senders
    return jsonify({"success": True, "blocked": get_blocked_senders()})


@app.post('/api/email/block')
def api_email_block_sender():
    """Block a sender (move to spam). Body: { email: "addr@example.com" }
    Also removes all existing inbox emails from this sender."""
    data = request.get_json(silent=True) or {}
    email_addr = data.get('email', '').strip().lower()
    if not email_addr or '@' not in email_addr:
        return jsonify({"success": False, "error": "Gültige E-Mail-Adresse erforderlich"}), 400
    from ailey_system.email_monitor import block_sender
    ok = block_sender(email_addr)
    if ok:
        # Also remove all inbox emails from this sender
        inbox = _load_email_inbox()
        before = len(inbox)
        inbox = [e for e in inbox if email_addr not in e.get("sender", "").lower()]
        removed = before - len(inbox)
        if removed:
            _save_email_inbox(inbox)
        return jsonify({"success": True, "blocked": email_addr, "removed_emails": removed})
    return jsonify({"success": False, "error": "Konnte Absender nicht blockieren"}), 500


@app.post('/api/email/unblock')
def api_email_unblock_sender():
    """Unblock a previously blocked sender. Body: { email: "addr@example.com" }"""
    data = request.get_json(silent=True) or {}
    email_addr = data.get('email', '').strip().lower()
    if not email_addr:
        return jsonify({"success": False, "error": "E-Mail-Adresse erforderlich"}), 400
    from ailey_system.email_monitor import unblock_sender
    ok = unblock_sender(email_addr)
    return jsonify({"success": ok, "unblocked": email_addr if ok else None})


# ── Email Sent Log — persistent storage of sent emails ───────────────────
_EMAIL_SENT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'email_sent.json')

def _load_email_sent() -> list:
    if os.path.isfile(_EMAIL_SENT_JSON):
        try:
            with open(_EMAIL_SENT_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_email_sent(sent: list):
    os.makedirs(os.path.dirname(_EMAIL_SENT_JSON), exist_ok=True)
    sent = sent[-200:]
    with open(_EMAIL_SENT_JSON, 'w', encoding='utf-8') as f:
        json.dump(sent, f, ensure_ascii=False, indent=2)

def _log_sent_email(to: str, subject: str, body: str, sent_as: str = "simon", reply_to_id: str = ""):
    """Log a sent email to the persistent sent log."""
    sent = _load_email_sent()
    entry = {
        "id": f"sent_{int(time.time()*1000)}",
        "to": to,
        "subject": subject,
        "body": body[:5000],
        "sent_as": sent_as,
        "reply_to_id": reply_to_id,
        "ts": time.time(),
        "dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    sent.append(entry)
    _save_email_sent(sent)
    return entry

@app.get('/api/email/sent')
def api_email_sent():
    """Get all sent emails (newest first)."""
    sent = _load_email_sent()
    sent.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return jsonify({"success": True, "emails": sent, "count": len(sent)})

@app.post('/api/email/send-manual')
def api_email_send_manual():
    """Send a new email written entirely by the user (no AI draft)."""
    data = request.get_json(silent=True) or {}
    to_addr = data.get("to", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    send_as = data.get("send_as", "simon").strip()
    if not to_addr or not body:
        return jsonify({"success": False, "error": "Empfänger und Text erforderlich"}), 400
    try:
        if send_as == "ailey":
            success = email_monitor.send_proactive_email_as_ailey(to_addr, subject, body)
            if isinstance(success, dict):
                if success.get("success"):
                    _log_sent_email(to_addr, subject, body, sent_as="ailey")
                return jsonify(success)
        else:
            from ailey_system.email_monitor import _find_simon_account, _send_smtp, SIMON_SIGNATURE_DRAFTED
            account = _find_simon_account("")  # Use default Simon account
            if not account:
                return jsonify({"success": False, "error": "Kein Simon-Account konfiguriert"})
            full_body = body.rstrip() + SIMON_SIGNATURE_DRAFTED
            ok = _send_smtp(account, to_addr, subject, full_body)
            if ok:
                _log_sent_email(to_addr, subject, body, sent_as="simon")
                return jsonify({"success": True, "message": f"E-Mail gesendet an {to_addr}"})
            return jsonify({"success": False, "error": "SMTP-Fehler"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/memory/stats')
def api_memory_stats():
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    return jsonify({"success": True, **core.rag_stats(user=user)})


@app.post('/api/memory/prune')
def api_memory_prune():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    doc_type = (data.get('doc_type') or 'research_auto').strip() or 'research_auto'
    keep_last = int(data.get('keep_last') or 200)
    try:
        pr = core._get_rag(user).prune(doc_type=doc_type, keep_last=keep_last)
        return jsonify({"success": True, **pr})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.get('/api/diary/latest')
def diary_latest():
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    try:
        diaries = core.memory.list_diaries(user)
        if not diaries:
            return jsonify({"success": True, "entry": None})
        merged = [d for d in diaries if d.get('type') == 'diary_merged']
        pick = merged[-1] if merged else diaries[-1]
        return jsonify({"success": True, "entry": {k: pick.get(k) for k in ('timestamp','type','text')}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# --- Diary Endpoints ---------------------------------------------------

@app.post('/api/diary/merge')
def diary_merge():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    try:
        msg = core.merge_diaries(user)
        return jsonify({"success": True, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# --- Ailey's Auto-Diary (internal reflections, generated by _maybe_create_diary) ---

@app.get('/api/diary/ailey-list')
def diary_ailey_list():
    """List Ailey's auto-generated diary entries (written about conversations)."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    try:
        diaries = core.memory.list_diaries(user)
        items = []
        for d in reversed(diaries):  # newest first
            items.append({
                "timestamp": d.get("timestamp"),
                "date_readable": d.get("date_readable", ""),
                "type": d.get("type", "diary"),
                "conversation_count": d.get("conversation_count"),
                "preview": (d.get("text") or "")[:200],
                "_file": d.get("_file", ""),
            })
        return jsonify({"success": True, "entries": items, "count": len(items)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/diary/ailey-read')
def diary_ailey_read():
    """Read a specific Ailey auto-diary entry by file name."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    filename = request.args.get('file', '')
    try:
        diaries = core.memory.list_diaries(user)
        for d in diaries:
            if d.get("_file") == filename:
                return jsonify({"success": True, "entry": d})
        return jsonify({"success": False, "error": "Eintrag nicht gefunden"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- People Glossary: Scan Old Email Senders ---

@app.post('/api/people/scan-emails')
def api_people_scan_emails():
    """Retroactively scan emails and populate the People Glossary with sender info."""
    try:
        if email_monitor is None:
            return jsonify({"success": False, "error": "EmailMonitor nicht aktiv"}), 503
        results = email_monitor.scan_old_senders_to_glossary()
        return jsonify({"success": True, **results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Research / Web Fetch (limited) ------------------------------------
def _clean_html(raw: str) -> str:
    if not raw:
        return ''
    # remove script/style blocks
    raw = re.sub(r'<script[\s\S]*?</script>', ' ', raw, flags=re.IGNORECASE)
    raw = re.sub(r'<style[\s\S]*?</style>', ' ', raw, flags=re.IGNORECASE)
    # strip tags
    text = re.sub(r'<[^>]+>', ' ', raw)
    # collapse whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


@app.post('/api/research')
def api_research():
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    if not query:
        return jsonify({"success": False, "message": "query required"}), 400
    # Very naive web fetch: treat query as URL if it looks like one
    result_text = ''
    if re.match(r'^https?://', query, re.I):
        try:
            r = requests.get(query, timeout=10)
            txt = r.text[:20000]
            clean = _clean_html(txt)
            result_text = (clean or txt)[:8000]
        except Exception as e:
            result_text = f"Fetch error: {e}"
    else:
        result_text = f"(Stub) Websuche für '{query}' nicht implementiert. Du kannst direkt eine URL angeben."
    # Ingest into RAG as 'research'
    try:
        core.rag_add(title=f"research_{int(time.time())}", text=result_text, doc_type='research', user=user)
    except Exception:
        pass
    return jsonify({"success": True, "stored_chars": len(result_text)})


# --- Agent Mode Stub ---------------------------------------------------
# SECURITY NOTE:
# Aktuell sind Agent-Aktionen rein Lesezugriff. Erweiterung für privates System-Scope erfolgt über
#   Umgebungsvariable AILEY_AGENT_EXTRA_ROOTS (Doppelpunkt-separiert). KEIN Schreibzugriff implementiert.
# TODO (Hardening):
#  - Auth Token Prüfung (Header X-Admin-Token) für riskantere Aktionen
#  - Rate Limiting pro Benutzer
#  - Ausfiltern sensibler Patterns (Passwörter, Schlüssel) bei read/search
#  - Quarantäne-Verzeichnis statt voller Root-Erweiterung
ALLOWED_AGENT_ROOTS = [Path('.').resolve()]  # project root only (read-only)
# Optional extended roots can be added via env AILEY_AGENT_EXTRA_ROOTS (colon separated)
_extra_roots = os.environ.get('AILEY_AGENT_EXTRA_ROOTS')
if _extra_roots:
    for part in _extra_roots.split(':'):
        p = Path(part).expanduser()
        if p.exists():
            ALLOWED_AGENT_ROOTS.append(p.resolve())

def _is_safe_path(p: Path) -> bool:
    try:
        rp = p.resolve()
        return any(str(rp).startswith(str(root)) for root in ALLOWED_AGENT_ROOTS)
    except Exception:
        return False

@app.get('/api/agent/capabilities')
def agent_capabilities():
    if not _admin_required():
        return jsonify({"success": False, "message": "admin token required"}), 403
    return jsonify({
        "success": True,
        "actions": {
            "list_dir": {"params": ["path", "depth<=2"], "desc": "List directory (safe root restricted)"},
            "read_head": {"params": ["path", "lines<=200"], "desc": "Read first lines of text file"},
            "search": {"params": ["pattern", "path(optional)"], "desc": "Case-insensitive substring search"},
            "system_info": {"desc": "Basic uname and Python version"},
            "processes": {"desc": "Light process snapshot"},
            "whoami": {"desc": "Current user"},
            "time": {"desc": "Current server time"},
            "search_docs": {"params": ["query", "ext=.txt,.md,.docx(optional)", "limit<=20"], "desc": "Search inside text/markdown/docx files"},
            "read_docx": {"params": ["path"], "desc": "Extract full text from a .docx (truncated)"},
            "extract_phone": {"params": ["path(optional)"], "desc": "Scan allowed roots for plausible phone numbers"},
            "find_in_docs": {"params": ["phrase"], "desc": "Locate phrase occurrences in documents (snippet)"},
            "read_docx_chapter": {"params": ["path", "chapter_number"], "desc": "Extract a specific chapter from docx"},
            "build_doc_index": {"desc": "(Re)build semantic doc index (embedding)", "params": ["ext=.txt,.md,.docx", "limit_docs<=200"]},
            "semantic_search_docs": {"params": ["query", "k<=5"], "desc": "Semantic similarity search in indexed docs"},
        }
    })

@app.post('/api/agent/execute')
def agent_execute():
    if not _admin_required():
        return jsonify({"success": False, "message": "admin token required"}), 403
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or data.get('command') or '').strip()
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    if not action:
        return jsonify({"success": False, "message": "action required"}), 400
    result = None
    try:
        if action == 'whoami':
            result = subprocess.check_output('whoami', shell=True, text=True, timeout=3).strip()
        elif action == 'time':
            result = time.strftime('%Y-%m-%d %H:%M:%S')
        elif action == 'system_info':
            result = subprocess.check_output('uname -a', shell=True, text=True, timeout=3)[:500]
        elif action == 'processes':
            result = subprocess.check_output("ps -u $(whoami) -o pid,comm,%mem,%cpu | head -n 15", shell=True, text=True, timeout=5)
        elif action == 'list_dir':
            path = Path((data.get('path') or '.').strip() or '.')
            depth = int(data.get('depth') or 1)
            if depth > 2:
                depth = 2
            if not _is_safe_path(path):
                return jsonify({"success": False, "message": "path not allowed"}), 403
            entries = []
            for p in path.iterdir():
                if p.name.startswith('.'):
                    continue
                entries.append({"name": p.name, "dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else None})
            result = {"path": str(path), "entries": entries[:200]}
        elif action == 'read_head':
            path = Path((data.get('path') or '').strip())
            lines = int(data.get('lines') or 60)
            if lines > 200:
                lines = 200
            if not path.exists() or not path.is_file() or not _is_safe_path(path):
                return jsonify({"success": False, "message": "file not allowed"}), 403
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content_lines = []
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    content_lines.append(line.rstrip('\n'))
            result = {"file": str(path), "head": content_lines}
        elif action == 'search':
            pattern = (data.get('pattern') or '').strip()
            if not pattern:
                return jsonify({"success": False, "message": "pattern required"}), 400
            base = Path((data.get('path') or '.').strip() or '.')
            if not _is_safe_path(base):
                return jsonify({"success": False, "message": "path not allowed"}), 403
            matches = []
            for root, dirs, files in os.walk(base):
                if len(matches) > 200:
                    break
                for fname in files:
                    if len(matches) > 200:
                        break
                    fp = Path(root) / fname
                    if fp.suffix not in ('.py', '.md', '.txt', '.json', '.ts', '.tsx'):
                        continue
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                            snippet = fh.read(4000)
                        if re.search(pattern, snippet, flags=re.IGNORECASE):
                            matches.append({"file": str(fp), "size": fp.stat().st_size})
                    except Exception:
                        pass
            result = {"pattern": pattern, "count": len(matches), "matches": matches[:200]}
        elif action == 'search_docs':
            query = (data.get('query') or '').strip()
            exts = (data.get('ext') or '.txt,.md,.docx').split(',')
            limit = int(data.get('limit') or 20)
            if not query:
                return jsonify({"success": False, "message": "query required"}), 400
            base = Path((data.get('path') or '.').strip() or '.')
            if not _is_safe_path(base):
                return jsonify({"success": False, "message": "path not allowed"}), 403
            found = []
            import textwrap
            for root, dirs, files in os.walk(base):
                for fname in files:
                    if len(found) >= limit:
                        break
                    fp = Path(root) / fname
                    if fp.suffix.lower() not in [e.strip().lower() for e in exts]:
                        continue
                    try:
                        text = ''
                        if fp.suffix.lower() == '.docx':
                            try:
                                from docx import Document
                                docx_obj = Document(str(fp))
                                text = "\n".join(p.text for p in docx_obj.paragraphs)[:15000]
                            except Exception:
                                continue
                        else:
                            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                                text = fh.read(20000)
                        if re.search(re.escape(query), text, flags=re.IGNORECASE):
                            # extract snippet around first occurrence
                            m = re.search(re.escape(query), text, flags=re.IGNORECASE)
                            start = max(0, m.start()-120)
                            end = min(len(text), m.end()+120)
                            snippet = text[start:end].replace('\n',' ')[:260]
                            found.append({"file": str(fp), "snippet": snippet})
                    except Exception:
                        pass
                if len(found) >= limit:
                    break
            result = {"query": query, "results": found, "count": len(found)}
        elif action == 'read_docx':
            path = Path((data.get('path') or '').strip())
            if not path.exists() or not _is_safe_path(path) or path.suffix.lower() != '.docx':
                return jsonify({"success": False, "message": "docx not allowed"}), 403
            try:
                from docx import Document
                doc = Document(str(path))
                text = '\n'.join(p.text for p in doc.paragraphs)[:40000]
            except Exception as e:
                return jsonify({"success": False, "message": f"read error: {e}"}), 500
            result = {"file": str(path), "chars": len(text), "head": text[:1000]}
        elif action == 'extract_phone':
            # naive phone scan across allowed roots (E.164-ish or local patterns)
            pattern = re.compile(r"(?:\+\d{2,3}[\s-]?)?(?:\(?0\)?[\s-]?)?[1-9][0-9]{1,3}[\s-]?[0-9]{2,4}[\s-]?[0-9]{2,4}(?:[\s-]?[0-9]{2,4})?")
            max_files = 200
            phones = []
            scanned = 0
            for root in ALLOWED_AGENT_ROOTS:
                for r, dnames, fnames in os.walk(root):
                    for fname in fnames:
                        if scanned >= max_files:
                            break
                        fp = Path(r)/fname
                        if fp.suffix.lower() not in ('.txt', '.md', '.json', '.py'):
                            continue
                        try:
                            with open(fp,'r',encoding='utf-8',errors='ignore') as fh:
                                chunk = fh.read(30000)
                            for m in pattern.findall(chunk):
                                clean = re.sub(r"\s+"," ", m.strip())
                                if clean not in phones:
                                    phones.append(clean)
                        except Exception:
                            pass
                        scanned += 1
                    if scanned >= max_files:
                        break
            def mask(ph: str):
                digits = re.sub(r'\D','', ph)
                if len(digits) < 4:
                    return ph
                return ph[0: len(ph)-2].replace('0','0') + '**'  # leave last two digits masked
            masked = [mask(p) for p in phones[:50]]
            result = {"found": masked, "count": len(phones), "masked": True}
        elif action == 'find_in_docs':
            phrase = (data.get('phrase') or '').strip()
            if not phrase:
                return jsonify({"success": False, "message": "phrase required"}), 400
            hits = []
            for root in ALLOWED_AGENT_ROOTS:
                for r, dnames, fnames in os.walk(root):
                    for fname in fnames:
                        if len(hits) > 40:
                            break
                        fp = Path(r)/fname
                        if fp.suffix.lower() not in ('.txt','.md','.docx'):
                            continue
                        try:
                            if fp.suffix.lower()=='.docx':
                                from docx import Document
                                doc = Document(str(fp))
                                text = '\n'.join(p.text for p in doc.paragraphs)[:30000]
                            else:
                                with open(fp,'r',encoding='utf-8',errors='ignore') as fh:
                                    text = fh.read(30000)
                            if re.search(re.escape(phrase), text, flags=re.IGNORECASE):
                                m = re.search(re.escape(phrase), text, flags=re.IGNORECASE)
                                start = max(0, m.start()-80)
                                end = min(len(text), m.end()+80)
                                snippet = text[start:end].replace('\n',' ')[:220]
                                hits.append({"file": str(fp), "snippet": snippet})
                        except Exception:
                            pass
                    if len(hits) > 40:
                        break
            result = {"phrase": phrase, "hits": hits, "count": len(hits)}
        elif action == 'read_docx_chapter':
            path = Path((data.get('path') or '').strip())
            chapter_number = int(data.get('chapter_number') or 1)
            if not path.exists() or not _is_safe_path(path) or path.suffix.lower() != '.docx':
                return jsonify({"success": False, "message": "docx not allowed"}), 403
            try:
                from docx import Document
                doc = Document(str(path))
                # simple chapter detection: paragraph starts with 'Kapitel X' or 'Chapter X'
                chapters = []
                current = {"title": None, "paras": []}
                import re as _re
                for p in doc.paragraphs:
                    txt = p.text.strip()
                    if _re.match(r'(Kapitel|Chapter)\s+\d+', txt, flags=_re.IGNORECASE):
                        if current['title'] or current['paras']:
                            chapters.append(current)
                        current = {"title": txt, "paras": []}
                    else:
                        current['paras'].append(txt)
                if current['title'] or current['paras']:
                    chapters.append(current)
                idx = max(0, min(chapter_number-1, len(chapters)-1))
                chosen = chapters[idx] if chapters else {"title": "(none)", "paras": []}
                excerpt = ("\n".join(chosen['paras']))[:4000]
                result = {"file": str(path), "chapter_number": chapter_number, "detected_chapters": len(chapters), "title": chosen.get('title'), "excerpt": excerpt[:1200]}
            except Exception as e:
                return jsonify({"success": False, "message": f"chapter read error: {e}"}), 500
        elif action == 'build_doc_index':
            # Build a naive semantic index (in-memory) using sentence_transformers if available
            exts = (data.get('ext') or '.txt,.md,.docx').split(',')
            limit_docs = int(data.get('limit_docs') or 200)
            docs = []
            count = 0
            for root in ALLOWED_AGENT_ROOTS:
                for r, dnames, fnames in os.walk(root):
                    for fname in fnames:
                        if count >= limit_docs:
                            break
                        fp = Path(r)/fname
                        if fp.suffix.lower() not in [e.strip().lower() for e in exts]:
                            continue
                        try:
                            if fp.suffix.lower()=='.docx':
                                from docx import Document
                                docx_obj = Document(str(fp))
                                text = "\n".join(p.text for p in docx_obj.paragraphs)[:8000]
                            else:
                                with open(fp,'r',encoding='utf-8',errors='ignore') as fh:
                                    text = fh.read(8000)
                            if not text.strip():
                                continue
                            docs.append({"file": str(fp), "text": text})
                            count += 1
                        except Exception:
                            pass
                    if count >= limit_docs:
                        break
            global _SEMANTIC_INDEX
            _SEMANTIC_INDEX = {"docs": docs, "embeddings": None, "model": None}
            try:
                from sentence_transformers import SentenceTransformer
                model_name = os.environ.get('AILEY_EMBED_MODEL','all-MiniLM-L6-v2')
                model = SentenceTransformer(model_name, device='cpu')  # CPU-only — MPS crashes with MLX
                texts = [d['text'][:512] for d in docs]
                embs = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
                _SEMANTIC_INDEX['embeddings'] = embs.tolist()
                _SEMANTIC_INDEX['model'] = model_name
            except Exception:
                _SEMANTIC_INDEX['embeddings'] = None
            result = {"indexed_docs": len(docs), "embedded": _SEMANTIC_INDEX.get('embeddings') is not None}
        elif action == 'semantic_search_docs':
            query = (data.get('query') or '').strip()
            k = int(data.get('k') or 5)
            if not query:
                return jsonify({"success": False, "message": "query required"}), 400
            if '_SEMANTIC_INDEX' not in globals() or not _SEMANTIC_INDEX.get('docs'):
                return jsonify({"success": False, "message": "index empty. run build_doc_index first"}), 400
            docs = _SEMANTIC_INDEX['docs']
            embs = _SEMANTIC_INDEX.get('embeddings')
            hits = []
            if embs:
                try:
                    from sentence_transformers import SentenceTransformer
                    model_name = _SEMANTIC_INDEX.get('model') or os.environ.get('AILEY_EMBED_MODEL','all-MiniLM-L6-v2')
                    model = SentenceTransformer(model_name, device='cpu')  # CPU-only — MPS crashes with MLX
                    import numpy as np
                    qv = model.encode([query], normalize_embeddings=True)[0]
                    import math
                    sims = []
                    for i, ev in enumerate(embs):
                        evv = ev
                        # cosine (embeddings already normalized) -> dot
                        score = sum([a*b for a,b in zip(qv, evv)])
                        sims.append((score,i))
                    sims.sort(reverse=True)
                    for score,i in sims[:k]:
                        text = docs[i]['text']
                        snippet = text[:280].replace('\n',' ')
                        hits.append({"file": docs[i]['file'], "score": round(float(score),4), "snippet": snippet})
                except Exception:
                    pass
            if not hits:
                # fallback: naive substring search
                for d in docs:
                    if query.lower() in d['text'].lower():
                        hits.append({"file": d['file'], "score": 0.0, "snippet": d['text'][:280].replace('\n',' ')})
                        if len(hits)>=k:
                            break
            result = {"query": query, "results": hits, "count": len(hits)}
        else:
            return jsonify({"success": False, "message": "unknown action"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    # Add agent action note to RAG
    try:
        core.rag_add(title=f"agent_{action}_{int(time.time())}", text=json.dumps(result)[:4000], doc_type='agent_action', user=user)
    except Exception:
        pass
    return jsonify({"success": True, "action": action, "result": result})


def _self_prompt_loop(interval_sec: int = 300):
    # runs in background thread
    while True:
        try:
            core.self_prompt_tick(user="Simon")
        except Exception:
            pass
        time.sleep(interval_sec)


# --- Rating / Bewertungs-Endpoints (Finetuning-Datenbasis) ----------------

@app.post('/api/chat/rate')
def api_chat_rate():
    """Save a user rating for an AI message."""
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or 'Simon').strip() or 'Simon'
    message_id = data.get('message_id')
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"}), 400
    ratings = data.get('ratings')
    if not ratings or not isinstance(ratings, dict):
        return jsonify({"success": False, "error": "ratings dict required"}), 400
    # Validate rating values (1-10)
    for k, v in ratings.items():
        try:
            iv = int(v)
            if iv < 1 or iv > 10:
                return jsonify({"success": False, "error": f"rating '{k}' must be 1-10"}), 400
            ratings[k] = iv
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": f"rating '{k}' must be integer"}), 400

    rec = save_rating(
        user=user,
        message_id=message_id,
        user_prompt=data.get('user_prompt', ''),
        ai_response=data.get('ai_response', ''),
        ratings=ratings,
        mood=data.get('mood'),
        model=data.get('model'),
        thinking=data.get('thinking'),
        tool_actions=data.get('tool_actions'),
        comment=data.get('comment'),
    )

    # ── Auto-collect as Gold Candidate if avg rating ≥ 7 ──────
    try:
        avg_score = sum(ratings.values()) / max(len(ratings), 1)
        if avg_score >= 5 and data.get('user_prompt') and data.get('ai_response'):
            _user_type = "simon" if user.lower() in ("simon",) else f"portal_{user.lower()[:10]}"
            _collect_training_pair(
                user_prompt=data['user_prompt'],
                assistant_response=data['ai_response'],
                reasoning=data.get('thinking', ''),
                tool_actions=data.get('tool_actions'),
                source=f"rating_{user.lower()[:15]}",
                user_type=_user_type,
                    mood=data.get('mood', 'neutral'),
                    engine=(data.get('model') or '').lower(),
                is_gold_candidate=True,
                rating_score=avg_score,
                rated_by=user,
            )
    except Exception:
        pass

    return jsonify({"success": True, "record": rec})


@app.get('/api/chat/rate')
def api_chat_rate_get():
    """Get rating for a specific message_id."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    message_id = request.args.get('message_id')
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"}), 400
    rec = get_rating(user, message_id)
    return jsonify({"success": True, "rating": rec})


@app.get('/api/ratings')
def api_ratings_list():
    """List all ratings (newest first)."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))
    items = list_ratings(user, limit=limit, offset=offset)
    return jsonify({"success": True, "count": len(items), "ratings": items})


@app.get('/api/ratings/stats')
def api_ratings_stats():
    """Aggregate rating statistics."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    stats = rating_stats(user)
    return jsonify({"success": True, **stats})


@app.get('/api/ratings/export')
def api_ratings_export():
    """Export ratings in fine-tuning-ready format (instruction/input/output + scores)."""
    user = (request.args.get('user') or 'Simon').strip() or 'Simon'
    min_avg = float(request.args.get('min_avg', 0))
    data = export_for_finetuning(user)
    if min_avg > 0:
        data = [d for d in data if d.get('avg_score', 0) >= min_avg]
    return jsonify({"success": True, "count": len(data), "data": data})


# ── LAN Remote Access & Mobile Optimization ───────────────────────────────────

@app.get('/api/network/discovery')
def api_network_discovery():
    """Network discovery endpoint for mobile devices to find Ailey on the LAN."""
    import socket
    try:
        # Get local IP addresses
        hostname = socket.gethostname()
        
        # Try to find a non-loopback IP
        local_ip = None
        interfaces = {}
        try:
            import netifaces
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        ip = addr['addr']
                        if not ip.startswith('127.') and not ip.startswith('::1'):
                            interfaces[iface] = ip
                            if not local_ip:  # take the first non-loopback
                                local_ip = ip
        except ImportError:
            # Fallback without netifaces
            pass
        
        if not local_ip:
            local_ip = socket.gethostbyname(hostname)
            interfaces["fallback"] = local_ip
        
        return jsonify({
            "success": True,
            "hostname": hostname,
            "local_ip": local_ip,
            "interfaces": interfaces,
            "api_port": 5502,
            "frontend_port": 5502,  # Frontend is served by the API on /app/
            "frontend_path": "/app/",
            "service": "Ailey.AI",
            "version": "2.0",
            "features": ["chat", "rag", "email", "tools", "mobile_optimized"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/mobile/generate_join_token')
def api_mobile_generate_join_token():
    """Generate a short-lived join token which, when opened on another device,
    will set a session cookie and redirect the client into the frontend so they
    share the same server-side session as the host that generated the token.

    Request body (optional JSON): { "frontend_url": "http://<ip>:<port>" }
    Response: { success: true, token: <uuid>, join_url: <full url> }
    """
    print('[JoinToken] api_mobile_generate_join_token called from', request.remote_addr)
    try:
        data = request.get_json(silent=True) or {}
        frontend_url = data.get('frontend_url') or None
        # create token
        token = uuid.uuid4().hex
        now = time.time()
        expires = now + JOIN_TOKEN_TTL
        # capture session cookie from the host (if present)
        cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
        sess_cookie = None
        try:
            if cookie_name in request.cookies:
                sess_cookie = request.cookies.get(cookie_name)
        except Exception:
            sess_cookie = None
        with _JOIN_LOCK:
            JOIN_TOKENS[token] = {
                'created': now,
                'expires': expires,
                'session_cookie': sess_cookie,
                'created_by': request.remote_addr,
                'frontend_url': frontend_url,
            }
        # Build join URL that the remote will open (server will set cookie and redirect)
        # Prefer explicit api_host/api_port if provided by the frontend discovery
        api_host = data.get('api_host') or request.host.split(':')[0]
        api_port = data.get('api_port') or (request.host.split(':')[1] if ':' in request.host else os.environ.get('AILEY_API_PORT', '5502'))
        join_url = f"http://{api_host}:{api_port}/mobile/join/{token}"
        # If frontend_url provided, attach as redirect query
        if frontend_url:
            join_url = f"{join_url}?next={requests.utils.requote_uri(frontend_url)}"
        # Debug output for troubleshooting QR/join redirects
        try:
            print(f"[JoinToken] created token={token} api_host={api_host} api_port={api_port} frontend_url={frontend_url} join_url={join_url}")
        except Exception:
            pass
        return jsonify({'success': True, 'token': token, 'join_url': join_url, 'ttl': JOIN_TOKEN_TTL})
    except Exception as e:
        import traceback as _tb
        print('[JoinToken] Exception:', e)
        print(_tb.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.get('/mobile/join/<token>')
def mobile_join(token: str):
    """Endpoint to be opened by remote device. Sets session cookie (if we have one)
    and redirects to the frontend. If no session cookie exists in the token (host
    had none), a new session cookie will be created for the remote and stored as
    the shared session for the token.
    """
    try:
        _cleanup_join_tokens()
        with _JOIN_LOCK:
            data = JOIN_TOKENS.get(token)
        if not data:
            return "Invalid or expired join token", 404

        cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
        resp = None
        # Determine redirect target: ?next= Parameter hat immer Vorrang
        next_param = request.args.get('next')
        # Debug logging to diagnose redirect targets
        try:
            print(f"[JoinToken] token data frontend_url={data.get('frontend_url')}, request.next={next_param}")
        except Exception:
            pass
        if next_param:
            target = next_param
        else:
            target = data.get('frontend_url') or f"http://{request.host.split(':')[0]}:5175/?joined=1"

        # If the chosen target points at loopback but the token stores a LAN frontend_url,
        # prefer the LAN frontend_url so mobile devices don't get redirected to 127.0.0.1
        try:
            from urllib.parse import urlparse, urlunparse
            def is_loopback_host(h):
                if not h:
                    return False
                return h.startswith('127.') or h == 'localhost' or h == '::1'

            parsed = urlparse(target)
            token_frontend = data.get('frontend_url')
            if parsed.hostname and is_loopback_host(parsed.hostname) and token_frontend:
                try:
                    p2 = urlparse(token_frontend)
                    if p2.hostname and not is_loopback_host(p2.hostname):
                        # preserve path/query from parsed but use hostname/port from token_frontend
                        new_netloc = p2.netloc
                        new_parsed = parsed._replace(netloc=new_netloc)
                        target = urlunparse(new_parsed)
                        print(f"[JoinToken] Rewriting loopback target to token frontend: {target}")
                except Exception:
                    pass
        except Exception:
            pass
        # If client expects JSON, return JSON payload with redirect URL to avoid HTML body parsing errors
        accept = (request.headers.get('Accept') or '')
        xreq = request.headers.get('X-Requested-With') or ''
        # Clients like some QR scanners may send Accept: */* or make XHR requests; be defensive and return JSON
        wants_json = (
            'application/json' in accept
            or request.args.get('format') == 'json'
            or xreq.lower() == 'xmlhttprequest'
            or accept.strip() == '*/*'
        )
        print(f"[JoinToken] mobile_join called; Accept='{accept}' X-Requested-With='{xreq}' wants_json={wants_json}")
        if wants_json:
            # consume token to avoid re-use
            with _JOIN_LOCK:
                JOIN_TOKENS.pop(token, None)
            return jsonify({'success': True, 'redirect': target})
        # If the token contains a session cookie, set it on the remote response
        if data.get('session_cookie'):
            from flask import make_response, redirect
            resp = make_response(redirect(target))
            resp.set_cookie(cookie_name, data['session_cookie'], max_age=JOIN_TOKEN_TTL, httponly=True, samesite='Lax')
        else:
            # No session cookie snapshot — create a fresh session (by touching session)
            from flask import make_response, redirect, session
            # create temporary session key
            session['joined_via'] = token
            # ensure session is saved
            resp = make_response(redirect(target))
        # consume token to avoid re-use
        with _JOIN_LOCK:
            JOIN_TOKENS.pop(token, None)
        return resp
    except Exception as e:
        return str(e), 500


@app.get('/api/mobile/status')
def api_mobile_status():
    """Mobile-optimized status endpoint with essential info."""
    return jsonify({
        "success": True,
        "service": "Ailey.AI",
        "status": "online",
        "mobile_ready": True,
        "features": {
            "streaming_chat": True,
            "voice_input": False,  # Will be added with TTS/STT
            "file_upload": False,
            "camera_access": False,
            "offline_mode": False
        },
        "endpoints": {
            "chat": "/api/chat",
            "stream": "/api/chat/stream",
            "mood": "/api/mood",
            "discovery": "/api/network/discovery"
        }
    })


@app.post('/api/mobile/config')
def api_mobile_config():
    """Set mobile-specific configuration."""
    data = request.get_json(silent=True) or {}
    device_type = data.get('device_type', 'unknown')
    screen_size = data.get('screen_size', {})
    capabilities = data.get('capabilities', {})
    
    # Store mobile config in session or global state
    mobile_config = {
        "device_type": device_type,
        "screen_size": screen_size,
        "capabilities": capabilities,
        "timestamp": time.time()
    }
    
    # For now, just acknowledge - could be extended to personalize responses
    return jsonify({
        "success": True,
        "config_applied": mobile_config,
        "optimizations": {
            "streaming_enabled": True,
            "compact_ui": device_type in ['mobile', 'tablet'],
            "touch_optimized": True
        }
    })


# ─── Reminder API Endpoints ─────────────────────────────────────────────────

@app.get('/api/reminders')
def api_reminders_list():
    """List all reminders from Apple Reminders."""
    list_name = request.args.get('list', 'Erinnerungen')
    include_completed = request.args.get('completed', 'false').lower() == 'true'
    
    try:
        result = list_reminders(list_name, include_completed)
        return jsonify({"success": True, "reminders": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/reminders')
def api_reminders_create():
    """Create a new reminder."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    date = data.get('date', '')
    time = data.get('time', '')
    recurrence = data.get('recurrence')  # 'daily', 'weekly', etc.
    
    if not title:
        return jsonify({"success": False, "error": "title required"}), 400
    
    try:
        if recurrence:
            result = create_recurring_reminder(title, recurrence, date, time)
        else:
            result = create_reminder(title, date, time)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/reminders/complete')
def api_reminders_complete():
    """Mark a reminder as completed."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    list_name = data.get('list', 'Erinnerungen')
    
    if not title:
        return jsonify({"success": False, "error": "title required"}), 400
    
    try:
        result = complete_reminder(title, list_name)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/reminders/lists')
def api_reminders_lists():
    """Get available reminder lists."""
    script = '''
tell application "Reminders"
    set listNames to {}
    repeat with l in lists
        set end of listNames to name of l
    end repeat
    return listNames
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lists = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            return jsonify({"success": True, "lists": lists})
        else:
            return jsonify({"success": False, "error": result.stderr.strip()}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── SVG Generation API Endpoints ─────────────────────────────────────────────

# ── Image Generation (MFLUX — user-requested via API) ────────────────────────

@app.get('/api/loras')
def api_loras():
    """Return available community LoRAs for the frontend to display toggles.
    Portal requests (identified by ?portal=1) exclude NSFW LoRAs."""
    from ailey_system.image_generator import get_available_loras
    is_portal = request.args.get('portal', '0') == '1'
    raw = get_available_loras(exclude_nsfw=is_portal)
    # Return only frontend-safe fields (no local paths)
    loras = {
        lid: {
            "description": info["description"],
            "trigger": info.get("trigger", ""),
            "nsfw": info.get("nsfw", False),
        }
        for lid, info in raw.items()
    }
    return jsonify({"success": True, "loras": loras})

# Track current generation job for polling
_image_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "prompt_used": ""}

@app.get('/api/image/status')
def api_image_status():
    """Poll image generation status. Returns active, progress, result when done."""
    return jsonify({
        "success": True,
        "active": _image_gen_job["active"],
        "progress": _image_gen_job["progress"],
        "result": _image_gen_job["result"],
        "started": _image_gen_job["started"],
        "prompt_used": _image_gen_job["prompt_used"],
    })

@app.post('/api/image/generate')
def api_image_generate():
    """Generate an image via MFLUX from user's description.
    This does NOT count against Ailey's daily idle-think image limit.

    Accepts JSON:
      prompt (str, required): User's image description (any language)
      aspect_ratio (str): "1:1", "16:9", "9:16", "4:3", "3:4"  (default "1:1")
      width (int): Custom width (overrides aspect_ratio)
      height (int): Custom height (overrides aspect_ratio)
      steps (int): Inference steps 1-20 (default 9)
      image_data (str): Base64 init image for img2img
      image_strength (float): 0.0-1.0 for img2img (default 0.4)
      async (bool): If true, run in background + return job_id for polling (default true)

    Flow: User prompt → LLM builds English prompt → unload LLM → MFLUX → reload LLM → gallery.
    """
    global _image_gen_job
    from ailey_system.image_generator import generate_image

    data = request.get_json(silent=True) or {}
    user_prompt = (data.get('prompt') or '').strip()
    if not user_prompt:
        return jsonify({"success": False, "error": "prompt required"}), 400

    aspect_ratio = data.get('aspect_ratio', '1:1')
    custom_width = data.get('width')
    custom_height = data.get('height')
    steps = min(20, max(1, int(data.get('steps', 9))))
    image_data_b64 = data.get('image_data')  # Base64 init image
    image_strength = max(0.0, min(1.0, float(data.get('image_strength', 0.4))))
    run_async = data.get('async', True)
    direct_mode = data.get('direct', False)  # If True: skip LLM translation, send prompt directly to MFLUX
    ailey_selfie = data.get('ailey_selfie', False)  # If True: prepend Ailey face prefix + load LoRA
    natural_look = data.get('natural_look', False)   # If True: use no-makeup face prefix instead of glam
    lora_ids = data.get('lora_ids', [])  # Community LoRA IDs: ["realism", "anime", "anatomy"]

    # Z-Image Turbo is optimized for 2-8 steps.
    # Higher steps increase VRAM usage linearly and can OOM on 24GB with Ministral co-resident.
    # Clamp to safe range and warn user if they tried higher.
    MAX_SAFE_STEPS = 12  # Absolute max before OOM risk on 24GB M4
    steps_requested = steps
    if steps > MAX_SAFE_STEPS:
        steps = MAX_SAFE_STEPS
        print(f"[ImageGen/API] ⚠️ Steps clamped from {steps_requested} to {MAX_SAFE_STEPS} (Z-Image Turbo safe range)")

    # Check if already generating
    if _image_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade schon ein Bild generiert. Bitte warte bis es fertig ist."}), 409

    gen = MLXGenerator.get()
    if gen is None:
        return jsonify({"success": False, "error": "Model nicht geladen"}), 503

    # Save base64 init image to temp file if provided
    init_image_path = None
    if image_data_b64:
        try:
            import base64, tempfile
            # Strip data-URI prefix if present
            if ',' in image_data_b64:
                image_data_b64 = image_data_b64.split(',', 1)[1]
            img_bytes = base64.b64decode(image_data_b64)
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp.write(img_bytes)
            tmp.close()
            init_image_path = tmp.name
            print(f"[ImageGen/API] Init image saved: {init_image_path} ({len(img_bytes)//1024}KB)")
        except Exception as ie:
            print(f"[ImageGen/API] ⚠️ Init image decode failed: {ie}")

    def _do_generate():
        global _image_gen_job
        try:
            _image_gen_job["active"] = True
            _image_gen_job["started"] = time.time()
            _image_gen_job["result"] = None

            if direct_mode:
                # ── DIRECT MODE: skip LLM, use user prompt directly with quality prefix ──
                _image_gen_job["progress"] = "Bereite Prompt vor…"
                # Add a quality/style prefix that helps FLUX produce better results
                # but does NOT censor or filter the user's creative intent
                _quality_prefix = (
                    "masterpiece, best quality, highly detailed, "
                    "sharp focus, professional, 8k resolution, "
                )
                english_prompt = _quality_prefix + user_prompt
                print(f"[ImageGen/API] Direct mode prompt: {english_prompt[:120]}")
                _image_gen_job["prompt_used"] = english_prompt
                _image_gen_job["progress"] = "Entlade LLM…"
            else:
                # ── AILEY MODE: LLM translates/rewrites to English visual prompt ──
                _image_gen_job["progress"] = "Ailey übersetzt Prompt…"

                # Step 1: LLM translates to English visual prompt
                if ailey_selfie:
                    system_msg = (
                        "You are an expert image prompt writer for FLUX image generators. "
                        "Translate the user's request into ONE English image prompt describing a SCENE with a young woman. "
                        "Describe ONLY: outfit, pose, setting, lighting, composition, atmosphere, camera angle. "
                        "Do NOT describe her face, hair, makeup, piercings, or skin — that is automatically added. "
                        "If the user specifies an outfit, clothing, or setting → use EXACTLY what they asked for. "
                        "If the user does NOT specify clothing or setting, default to her punk/grunge style: "
                        "leather jacket, ripped jeans, band tee, combat boots, hoodie, flannel, etc. "
                        "in settings like: city streets, rooftop, concert, home, park, bar. "
                        "Be specific, vivid, and cinematic. 20-50 words. "
                        "Output ONLY the English prompt. No explanation, no markdown, no quotes."
                    )
                else:
                    system_msg = (
                        "You are an expert image prompt writer for FLUX/Stable Diffusion image generators. "
                        "Translate the user's request into ONE detailed English image prompt. "
                        "Describe visual elements: subject, colors, lighting, composition, art style, camera angle, atmosphere. "
                        "Be specific, vivid, and cinematic. 20-60 words. "
                        "Output ONLY the English prompt. No explanation, no markdown, no quotes."
                    )
                user_msg = f"Create an image prompt for: {user_prompt}"

                english_prompt = gen.generate(
                    system=system_msg, user=user_msg,
                    params={"max_tokens": 150, "temperature": 0.8},
                )
                english_prompt = (english_prompt or '').strip().strip('"\'`').strip()
                # Strip thinking tags
                english_prompt = re.sub(r'<think>.*?</think>', '', english_prompt, flags=re.DOTALL|re.IGNORECASE).strip()
                english_prompt = re.sub(r'\[THINK\].*?\[/THINK\]', '', english_prompt, flags=re.DOTALL).strip()
                # Take first non-empty line
                for _line in english_prompt.split('\n'):
                    _line = _line.strip().strip('"\'`').strip()
                    if len(_line) >= 15:
                        english_prompt = _line
                        break
                if not english_prompt or len(english_prompt) < 10:
                    english_prompt = user_prompt
                print(f"[ImageGen/API] Generated prompt: {english_prompt[:120]}")
                _image_gen_job["prompt_used"] = english_prompt
                _image_gen_job["progress"] = "Entlade LLM…"

            # Step 2: Unload LLM for RAM
            unloaded = False
            try:
                idle_thinker = globals().get('idle_thinker')
                if idle_thinker:
                    idle_thinker._unload_llm_for_image_gen()
                    unloaded = True
                else:
                    # Direct cleanup with full Metal sync
                    print("[ImageGen/API] No idle_thinker — direct LLM cleanup")
                    import gc
                    try:
                        from ailey_system.llm_mlx import block_auto_reload
                        block_auto_reload()  # prevent auto-reload while MFLUX runs
                    except Exception:
                        pass
                    try:
                        import mlx.core as mx
                        mx.synchronize()
                        mx.eval(mx.zeros(1))
                    except Exception:
                        pass
                    try:
                        from ailey_system import llm_mlx
                        from ailey_system.llm_mlx import MLXGenerator, _mlx_lock
                        with _mlx_lock:
                            llm_mlx._model = None
                            llm_mlx._tokenizer = None
                            llm_mlx._cache = None
                            llm_mlx._last_system_prompt = None
                            MLXGenerator._instance = None
                    except Exception:
                        pass
                    gc.collect(); gc.collect()
                    try:
                        import mlx.core as mx
                        mx.metal.set_cache_limit(0)
                        mx.metal.clear_cache()
                        mx.metal.set_memory_limit(0)
                    except Exception:
                        pass
                    gc.collect()
                    import time as _t; _t.sleep(2.0)
                    unloaded = True
                print("[ImageGen/API] Ministral unloaded for MFLUX")
            except Exception as ue:
                print(f"[ImageGen/API] Unload warning: {ue}")

            _image_gen_job["progress"] = "Generiere Bild…"

            # Ailey Selfie mode: prepend face prefix + attach LoRA
            _use_selfie_lora = False
            if ailey_selfie:
                from ailey_system.image_generator import (
                    AILEY_FACE_PREFIX as _SELFIE_PREFIX,
                    AILEY_FACE_PREFIX_NATURAL as _SELFIE_PREFIX_NATURAL,
                    AILEY_FACE_PREFIX_ANIME as _SELFIE_PREFIX_ANIME,
                    AILEY_FACE_PREFIX_ANIME_NATURAL as _SELFIE_PREFIX_ANIME_NATURAL,
                    AILEY_SELFIE_LORA_PATH as _SELFIE_LORA,
                    AILEY_SELFIE_LORA_SCALE as _SELFIE_SCALE,
                    build_lora_args as _build_img_loras,
                )
                # Choose face prefix based on natural_look toggle AND anime LoRA
                _anime_active = "anime" in lora_ids
                if _anime_active:
                    _chosen_prefix = _SELFIE_PREFIX_ANIME_NATURAL if natural_look else _SELFIE_PREFIX_ANIME
                    print("[ImageGen/API] 🎨 Anime LoRA active → using anime face prefix")
                else:
                    _chosen_prefix = _SELFIE_PREFIX_NATURAL if natural_look else _SELFIE_PREFIX
                # Strip redundant person descriptions the LLM might have added
                _ep = english_prompt
                for _pfx in ("A young woman ", "Portrait of a ", "A woman ", "She is ", "A punk girl "):
                    if _ep.lower().startswith(_pfx.lower()):
                        _ep = _ep[len(_pfx):].lstrip(",").lstrip()
                        break
                english_prompt = f"{_chosen_prefix}{_ep}"
                if _SELFIE_LORA and os.path.isfile(_SELFIE_LORA):
                    _use_selfie_lora = True
                print(f"[ImageGen/API] 🤳 Ailey Selfie mode → {'LoRA' if _use_selfie_lora else 'prefix only'}")
                _image_gen_job["prompt_used"] = english_prompt

            # Build LoRA args from request + selfie mode
            # Main app: ALL LoRAs available including NSFW (exclude_nsfw=False)
            from ailey_system.image_generator import build_lora_args as _build_gen_loras
            _final_lora_paths = None
            _final_lora_scales = None
            _trigger_prefix = ""
            if ailey_selfie and _use_selfie_lora:
                # Selfie: Ailey LoRA + user-selected community LoRAs (max 2 total)
                _user_loras = [lid for lid in lora_ids if lid != "ailey"]
                _final_lora_paths, _final_lora_scales, _trigger_prefix = _build_gen_loras(
                    _user_loras or ["realism"],  # default to realism for selfies
                    include_ailey=True, exclude_nsfw=False,
                )
            elif lora_ids:
                # Non-selfie: user-selected community LoRAs only
                _final_lora_paths, _final_lora_scales, _trigger_prefix = _build_gen_loras(
                    lora_ids, include_ailey=False, exclude_nsfw=False,
                )
            if _trigger_prefix:
                english_prompt = _trigger_prefix + english_prompt
                _image_gen_job["prompt_used"] = english_prompt

            # Step 3: Generate
            gen_kwargs = dict(
                prompt=english_prompt,
                title=user_prompt[:50],
                steps=steps,
                aspect_ratio=aspect_ratio,
                image_strength=image_strength,
                low_ram=not unloaded,
                private=True,  # Simon's image → image_private/, not uploaded
                image_type="selfie" if ailey_selfie else "img",
                username="Simon",
            )
            if _final_lora_paths:
                gen_kwargs["lora_paths"] = _final_lora_paths
                gen_kwargs["lora_scales"] = _final_lora_scales
            if custom_width and custom_height:
                gen_kwargs['width'] = int(custom_width)
                gen_kwargs['height'] = int(custom_height)
            if init_image_path and not ailey_selfie:
                gen_kwargs['image_path'] = init_image_path

            filepath, filename = None, None
            try:
                filepath, filename = generate_image(**gen_kwargs)
            except Exception as gen_err:
                print(f"[ImageGen/API] ❌ MFLUX error: {gen_err}")
            finally:
                # Step 4: ALWAYS Reload LLM — even if MFLUX crashed
                _image_gen_job["progress"] = "Lade LLM…"
                try:
                    if unloaded:
                        if idle_thinker:
                            idle_thinker._reload_llm_after_image_gen()
                        else:
                            from ailey_system.llm_mlx import allow_auto_reload
                            allow_auto_reload()
                            print("[ImageGen/API] No idle_thinker — lazy reload via MLXGenerator.get()")
                            MLXGenerator.get()
                        print("[ImageGen/API] Ministral reloaded after MFLUX")
                except Exception as re_err:
                    print(f"[ImageGen/API] Reload warning: {re_err}")
                    try:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                    except Exception: pass

            # Cleanup temp init image
            if init_image_path:
                try:
                    os.unlink(init_image_path)
                except Exception:
                    pass

            if filepath and filename:
                local_url = f"/api/image/file/{filename}"
                print(f"[ImageGen/API] ✅ Image saved: {filename}")
                _image_gen_job["result"] = {
                    "success": True,
                    "image_url": local_url,
                    "filename": filename,
                    "prompt_used": english_prompt,
                }
                _image_gen_job["progress"] = "Fertig!"

                # NOTE: User-generated images are private (saved to image_private/).
                # Only Ailey's own idle_thinker images are pushed to the portal gallery.
            else:
                _image_gen_job["result"] = {"success": False, "error": "MFLUX generation failed"}
                _image_gen_job["progress"] = "Fehlgeschlagen"
                print("[ImageGen/API] ❌ Generation failed")

        except Exception as e:
            print(f"[ImageGen/API] ❌ Error: {e}")
            import traceback; traceback.print_exc()
            _image_gen_job["result"] = {"success": False, "error": str(e)}
            _image_gen_job["progress"] = f"Fehler: {e}"
        finally:
            _image_gen_job["active"] = False

    if run_async:
        import threading
        t = threading.Thread(target=_do_generate, daemon=True)
        t.start()
        return jsonify({
            "success": True,
            "status": "started",
            "message": "Bildgenerierung gestartet. Poll /api/image/status für den Fortschritt.",
        })
    else:
        # Synchronous mode (blocks ~5 minutes)
        _do_generate()
        result = _image_gen_job.get("result", {})
        if result and result.get("success"):
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": result.get("error", "Unknown error")}), 500


@app.post('/api/svg/generate')
def api_svg_generate():
    """Generate an SVG graphic from a description (max 1000 tokens)."""
    data = request.get_json(silent=True) or {}
    description = data.get('description')
    style = data.get('style', 'minimalistisch')
    colors = data.get('colors', 'automatisch')
    size = data.get('size', '256x256')
    if not description:
        return jsonify({"success": False, "error": "description required"}), 400
    try:
        result = generate_svg(description, style, colors, size)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/svg/gallery')
def api_svg_gallery():
    """List SVG graphics in the gallery. Supports ?page=1&per_page=20."""
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 20))))
    limit = int(request.args.get('limit', 999))  # legacy compat
    try:
        result = list_svg_gallery(limit)
        # Apply pagination
        all_items = result.get('svgs', result) if isinstance(result, dict) else result
        if isinstance(all_items, list):
            total = len(all_items)
            start = (page - 1) * per_page
            paged = all_items[start:start + per_page]
            return jsonify({"success": True, "gallery": paged if not isinstance(result, dict) else result,
                            "pagination": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}})
        return jsonify({"success": True, "gallery": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── SeedVR2 Image Upscaler ─────────────────────────────────────────────────
_upscale_job = {"active": False, "progress": "", "result": None, "started": 0.0, "filename": ""}


@app.get('/api/image/upscale/status')
def api_upscale_status():
    """Poll upscale job status."""
    return jsonify({
        "success": True,
        "active": _upscale_job["active"],
        "progress": _upscale_job["progress"],
        "result": _upscale_job["result"],
        "started": _upscale_job["started"],
        "filename": _upscale_job["filename"],
    })


@app.post('/api/image/upscale')
def api_image_upscale():
    """Upscale an image using SeedVR2 diffusion-based super-resolution.

    Accepts JSON:
      filename (str, required): Source image filename (from any gallery dir)
      resolution (str): "2x", "3x", "4x" or pixel value like "2048" (default "2x")
      softness (float): 0.0–1.0, denoising strength (default 0.0 = sharp)
      seed (int): Random seed for reproducibility (optional)
      async (bool): If true, run in background (default true)
    """
    global _upscale_job
    from ailey_system.image_generator import upscale_image, is_seedvr2_available

    data = request.get_json(silent=True) or {}
    filename = (data.get('filename') or '').strip()
    if not filename:
        return jsonify({"success": False, "error": "filename required"}), 400

    if not is_seedvr2_available():
        return jsonify({"success": False, "error": "SeedVR2 Upscaler nicht verfügbar. Bitte mflux aktualisieren."}), 503

    if _upscale_job["active"]:
        return jsonify({"success": False, "error": "Upscale läuft bereits. Bitte warten."}), 409

    resolution = data.get('resolution', '2x')
    softness = max(0.0, min(1.0, float(data.get('softness', 0.0))))
    seed = data.get('seed')
    if seed is not None:
        seed = int(seed)
    run_async = data.get('async', True)

    # Validate resolution
    valid_res = ('2x', '3x', '4x')
    if resolution not in valid_res:
        try:
            int(resolution)  # allow pixel values like "2048"
        except ValueError:
            return jsonify({"success": False, "error": f"resolution muss {valid_res} oder Pixelwert sein"}), 400

    def _do_upscale():
        global _upscale_job
        _upscale_job = {"active": True, "progress": "SeedVR2 Upscaling…", "result": None,
                        "started": time.time(), "filename": filename}
        try:
            # Unload LLM to free GPU memory for upscaler
            _upscale_job["progress"] = "LLM wird entladen…"
            try:
                idle_thinker = globals().get('idle_thinker')
                if idle_thinker:
                    idle_thinker._unload_llm_for_image_gen()
                else:
                    import gc
                    try:
                        from ailey_system.llm_mlx import block_auto_reload
                        block_auto_reload()
                    except Exception:
                        pass
                    try:
                        import mlx.core as mx
                        mx.synchronize(); mx.eval(mx.zeros(1))
                    except Exception:
                        pass
                    try:
                        from ailey_system import llm_mlx
                        from ailey_system.llm_mlx import MLXGenerator, _mlx_lock
                        with _mlx_lock:
                            llm_mlx._model = None; llm_mlx._tokenizer = None
                            llm_mlx._cache = None; llm_mlx._last_system_prompt = None
                            MLXGenerator._instance = None
                    except Exception:
                        pass
                    gc.collect(); gc.collect()
                    try:
                        import mlx.core as mx
                        mx.metal.set_cache_limit(0); mx.metal.clear_cache(); mx.metal.set_memory_limit(0)
                    except Exception:
                        pass
                    gc.collect()
                    import time as _t; _t.sleep(2.0)
                print("[Upscale/API] Ministral unloaded for SeedVR2")
            except Exception as ue:
                print(f"[Upscale/API] Unload warning: {ue}")

            _upscale_job["progress"] = f"Upscaling {filename} ({resolution})…"
            filepath, out_filename = upscale_image(
                input_filename=filename,
                resolution=resolution,
                softness=softness,
                low_ram=True,
                seed=seed,
            )

            if filepath and out_filename:
                local_url = f"/api/image/file/{out_filename}"
                _upscale_job["result"] = {
                    "success": True,
                    "message": f"✅ Bild upscaled: {out_filename}",
                    "filename": out_filename,
                    "source": filename,
                    "resolution": resolution,
                    "url": local_url,
                }
                _upscale_job["progress"] = "Fertig!"
                print(f"[Upscale/API] ✅ {filename} → {out_filename}")
            else:
                _upscale_job["result"] = {
                    "success": False,
                    "error": "Upscaling fehlgeschlagen. Siehe Server-Log.",
                }
                _upscale_job["progress"] = "Fehler"
        except Exception as e:
            _upscale_job["result"] = {"success": False, "error": str(e)}
            _upscale_job["progress"] = "Fehler"
            print(f"[Upscale/API] ❌ {e}")
        finally:
            _upscale_job["active"] = False

    if run_async:
        import threading
        t = threading.Thread(target=_do_upscale, daemon=True)
        t.start()
        return jsonify({
            "success": True,
            "message": f"Upscaling gestartet. Poll /api/image/upscale/status für den Fortschritt.",
            "async": True,
        })
    else:
        _do_upscale()
        result = _upscale_job.get("result", {})
        if result and result.get("success"):
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": result.get("error", "Unknown error")}), 500


@app.post('/api/image/upscale/upload')
def api_image_upscale_upload():
    """Upload an external image and upscale it using SeedVR2.

    Accepts JSON:
      image_data (str, required): Base64-encoded image (data:image/png;base64,… or raw b64)
      filename (str, optional): Original filename for reference
      resolution (str): "2x", "3x", "4x" (default "2x")
      softness (float): 0.0–1.0, denoising strength (default 0.0 = sharp)
      seed (int): Random seed (optional)
    """
    global _upscale_job
    import base64 as _b64
    from ailey_system.image_generator import upscale_image, is_seedvr2_available, IMAGE_UPSCALED_DIR

    data = request.get_json(silent=True) or {}
    image_data = (data.get('image_data') or '').strip()
    if not image_data:
        return jsonify({"success": False, "error": "image_data required (base64)"}), 400

    if not is_seedvr2_available():
        return jsonify({"success": False, "error": "SeedVR2 Upscaler nicht verfügbar. Bitte mflux aktualisieren."}), 503

    if _upscale_job["active"]:
        return jsonify({"success": False, "error": "Upscale läuft bereits. Bitte warten."}), 409

    resolution = data.get('resolution', '2x')
    softness = max(0.0, min(1.0, float(data.get('softness', 0.0))))
    seed = data.get('seed')
    if seed is not None:
        seed = int(seed)
    orig_name = (data.get('filename') or 'upload').strip()

    # Validate resolution
    valid_res = ('2x', '3x', '4x')
    if resolution not in valid_res:
        return jsonify({"success": False, "error": f"resolution muss {valid_res} sein"}), 400

    # Decode and save the uploaded image
    try:
        # Strip data URI prefix if present
        b64_str = image_data
        if ',' in b64_str:
            b64_str = b64_str.split(',', 1)[1]
        raw_bytes = _b64.b64decode(b64_str)
    except Exception as e:
        return jsonify({"success": False, "error": f"Base64-Dekodierung fehlgeschlagen: {e}"}), 400

    # Determine extension from data or original name
    ext = '.png'
    if orig_name and '.' in orig_name:
        ext = os.path.splitext(orig_name)[1].lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.webp'):
            ext = '.png'

    # Save uploaded file to upscaled dir with UPLOAD_ prefix
    import time as _time_mod
    os.makedirs(IMAGE_UPSCALED_DIR, exist_ok=True)
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', os.path.splitext(orig_name)[0])[:60]
    upload_filename = f"UPLOAD_{int(_time_mod.time())}_{safe_name}{ext}"
    upload_path = os.path.join(IMAGE_UPSCALED_DIR, upload_filename)
    try:
        with open(upload_path, 'wb') as f:
            f.write(raw_bytes)
        print(f"[Upscale/Upload] 📁 Saved upload: {upload_filename} ({len(raw_bytes) // 1024}KB)")
    except Exception as e:
        return jsonify({"success": False, "error": f"Speichern fehlgeschlagen: {e}"}), 500

    def _do_upload_upscale():
        global _upscale_job
        _upscale_job = {"active": True, "progress": "SeedVR2 Upscaling (Upload)…", "result": None,
                        "started": time.time(), "filename": upload_filename}
        try:
            # Unload LLM to free GPU memory for upscaler
            _upscale_job["progress"] = "LLM wird entladen…"
            try:
                idle_thinker = globals().get('idle_thinker')
                if idle_thinker:
                    idle_thinker._unload_llm_for_image_gen()
                else:
                    import gc
                    try:
                        from ailey_system.llm_mlx import block_auto_reload
                        block_auto_reload()
                    except Exception:
                        pass
                    try:
                        import mlx.core as mx
                        mx.synchronize(); mx.eval(mx.zeros(1))
                    except Exception:
                        pass
                    try:
                        from ailey_system import llm_mlx
                        from ailey_system.llm_mlx import MLXGenerator, _mlx_lock
                        with _mlx_lock:
                            llm_mlx._model = None; llm_mlx._tokenizer = None
                            llm_mlx._cache = None; llm_mlx._last_system_prompt = None
                            MLXGenerator._instance = None
                    except Exception:
                        pass
                    gc.collect(); gc.collect()
                    try:
                        import mlx.core as mx
                        mx.metal.set_cache_limit(0); mx.metal.clear_cache(); mx.metal.set_memory_limit(0)
                    except Exception:
                        pass
                    gc.collect()
                    import time as _t; _t.sleep(2.0)
                print("[Upscale/Upload] Ministral unloaded for SeedVR2")
            except Exception as ue:
                print(f"[Upscale/Upload] Unload warning: {ue}")

            _upscale_job["progress"] = f"Upscaling {upload_filename} ({resolution})…"
            filepath, out_filename = upscale_image(
                input_filename=upload_filename,
                input_path=upload_path,
                resolution=resolution,
                softness=softness,
                low_ram=True,
                seed=seed,
            )

            if filepath and out_filename:
                local_url = f"/api/image/file/{out_filename}"
                _upscale_job["result"] = {
                    "success": True,
                    "message": f"✅ Bild upscaled: {out_filename}",
                    "filename": out_filename,
                    "source": upload_filename,
                    "resolution": resolution,
                    "url": local_url,
                    "uploaded": True,
                }
                _upscale_job["progress"] = "Fertig!"
                print(f"[Upscale/Upload] ✅ {upload_filename} → {out_filename}")
            else:
                _upscale_job["result"] = {
                    "success": False,
                    "error": "Upscaling fehlgeschlagen. Siehe Server-Log.",
                }
                _upscale_job["progress"] = "Fehler"
        except Exception as e:
            _upscale_job["result"] = {"success": False, "error": str(e)}
            _upscale_job["progress"] = "Fehler"
            print(f"[Upscale/Upload] ❌ {e}")
        finally:
            _upscale_job["active"] = False

    import threading
    t = threading.Thread(target=_do_upload_upscale, daemon=True)
    t.start()
    return jsonify({
        "success": True,
        "message": "Upload-Upscaling gestartet. Poll /api/image/upscale/status für den Fortschritt.",
        "upload_filename": upload_filename,
        "async": True,
    })


@app.get('/api/image/gallery')
def api_image_gallery():
    """List AI-generated images (both Ailey's public and Simon's private). Supports ?page=1&per_page=20."""
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 20))))
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        gallery_dir = os.path.join(base, 'ailey_users', 'image_gallery')
        private_dir = os.path.join(base, 'ailey_users', 'image_private')
        upscaled_dir = os.path.join(base, 'ailey_users', 'image_upscaled')
        exts = ('.png', '.jpg', '.jpeg', '.webp')
        # Collect files from all directories
        all_entries = []
        for img_dir in (gallery_dir, private_dir, upscaled_dir):
            if os.path.isdir(img_dir):
                is_private = (img_dir == private_dir)
                is_upscaled = (img_dir == upscaled_dir)
                for f in os.listdir(img_dir):
                    if f.lower().endswith(exts):
                        p = os.path.join(img_dir, f)
                        all_entries.append((f, p, os.path.getmtime(p), is_private, is_upscaled))
        all_entries.sort(key=lambda x: x[2], reverse=True)
        total = len(all_entries)
        if total == 0:
            return jsonify({"success": True, "gallery": {"message": "Galerie leer", "images": []},
                            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0}})
        start = (page - 1) * per_page
        entries = all_entries[start:start + per_page]
        out = []
        for fn, p, mt, is_priv, is_up in entries:
            out.append({"filename": fn, "size": os.path.getsize(p), "mtime": mt, "private": is_priv, "upscaled": is_up})
        return jsonify({"success": True,
                        "gallery": {"message": f"{total} Bild(er)", "images": out},
                        "pagination": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/image/file/<path:filename>')
def api_image_file(filename):
    """Serve an image file from the image gallery, private, hidden, or upscaled directory."""
    from flask import send_from_directory
    base = os.path.dirname(os.path.abspath(__file__))
    gallery_dir = os.path.join(base, 'ailey_users', 'image_gallery')
    private_dir = os.path.join(base, 'ailey_users', 'image_private')
    hidden_dir = os.path.join(base, 'ailey_users', 'image_hidden')
    upscaled_dir = os.path.join(base, 'ailey_users', 'image_upscaled')
    allowed_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return ('', 403)
    # Check all directories: private first, then gallery, then upscaled, then hidden
    for img_dir in (private_dir, gallery_dir, upscaled_dir, hidden_dir):
        fpath = os.path.join(img_dir, filename)
        if os.path.isfile(fpath):
            ext = filename.rsplit('.', 1)[-1].lower()
            mimes = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}
            return send_from_directory(img_dir, filename, mimetype=mimes.get(ext, 'image/png'))
    return ('', 404)


# ── Gallery Management — Delete, Push-to-Portal, Hide ─────────────────────
_HIDDEN_GALLERY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'image_hidden')
_HIDDEN_GALLERY_PASSWORD = os.environ.get("AILEY_GALLERY_PIN", "")  # redacted for public repo


@app.delete('/api/image/gallery/<filename>')
def api_image_delete(filename):
    """Delete an image from any gallery directory (public, private, hidden)."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    for d in ('image_gallery', 'image_private', 'image_hidden', 'image_upscaled'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            os.remove(fpath)
            # Also remove companion .meta.json if it exists
            _meta = fpath.rsplit('.', 1)[0] + '.meta.json'
            if os.path.isfile(_meta):
                os.remove(_meta)
            print(f"[Gallery] 🗑️ Deleted: {filename} from {d}")
            return jsonify({"success": True, "message": f"{filename} gelöscht"})
    return jsonify({"success": False, "error": "Bild nicht gefunden"}), 404


@app.post('/api/image/gallery/push/<filename>')
def api_image_push_to_portal(filename):
    """Push an image to the public portal gallery (allinkl)."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    # Find the file
    filepath = None
    for d in ('image_gallery', 'image_private', 'image_hidden'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            filepath = fpath
            break
    if not filepath:
        return jsonify({"success": False, "error": "Bild nicht gefunden"}), 404
    # Upload to portal
    try:
        from ailey_system.portal_poller import get_portal_poller
        poller = get_portal_poller()
        file_url = poller._upload_gallery_file(filepath, filename)
        if file_url:
            # Also push as gallery item
            title = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').replace('.webp', '')
            title = title.replace('_', ' ').replace('img ', '').strip()
            poller._push_gallery_item("image", title or "Aileys Bild", file_url=file_url)
            print(f"[Gallery] 🌐 Pushed to portal: {filename} → {file_url}")
            return jsonify({"success": True, "message": f"Auf Portal hochgeladen", "url": file_url})
        else:
            return jsonify({"success": False, "error": "Upload fehlgeschlagen"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/image/gallery/hide/<filename>')
def api_image_move_to_hidden(filename):
    """Move an image to the hidden/password-protected gallery."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    import shutil
    os.makedirs(_HIDDEN_GALLERY_DIR, exist_ok=True)
    # Find the file in public or private
    for d in ('image_gallery', 'image_private'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            dest = os.path.join(_HIDDEN_GALLERY_DIR, filename)
            shutil.move(fpath, dest)
            # Also move companion .meta.json if it exists
            _meta_src = fpath.rsplit('.', 1)[0] + '.meta.json'
            if os.path.isfile(_meta_src):
                _meta_dst = os.path.join(_HIDDEN_GALLERY_DIR, filename.rsplit('.', 1)[0] + '.meta.json')
                shutil.move(_meta_src, _meta_dst)
            print(f"[Gallery] 🔒 Moved to hidden: {filename}")
            return jsonify({"success": True, "message": f"{filename} in versteckte Galerie verschoben"})
    return jsonify({"success": False, "error": "Bild nicht gefunden"}), 404


@app.post('/api/image/gallery/unhide/<filename>')
def api_image_move_from_hidden(filename):
    """Move an image from hidden gallery back to the private gallery."""
    allowed_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    import shutil
    base = os.path.dirname(os.path.abspath(__file__))
    fpath = os.path.join(_HIDDEN_GALLERY_DIR, filename)
    if not os.path.isfile(fpath):
        return jsonify({"success": False, "error": "Bild nicht in versteckter Galerie"}), 404
    dest_dir = os.path.join(base, 'ailey_users', 'image_private')
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(fpath, os.path.join(dest_dir, filename))
    # Also move companion .meta.json if it exists
    _meta_src = os.path.join(_HIDDEN_GALLERY_DIR, filename.rsplit('.', 1)[0] + '.meta.json')
    if os.path.isfile(_meta_src):
        shutil.move(_meta_src, os.path.join(dest_dir, filename.rsplit('.', 1)[0] + '.meta.json'))
    print(f"[Gallery] 🔓 Unhidden: {filename}")
    return jsonify({"success": True, "message": f"{filename} wiederhergestellt"})


@app.get('/api/image/hidden')
def api_image_hidden_gallery():
    """List images in the hidden/password-protected gallery. Requires ?password=..."""
    pw = request.args.get('password', '')
    if pw != _HIDDEN_GALLERY_PASSWORD:
        return jsonify({"success": False, "error": "Falsches Passwort"}), 403
    try:
        exts = ('.png', '.jpg', '.jpeg', '.webp')
        entries = []
        if os.path.isdir(_HIDDEN_GALLERY_DIR):
            for f in os.listdir(_HIDDEN_GALLERY_DIR):
                if f.lower().endswith(exts):
                    p = os.path.join(_HIDDEN_GALLERY_DIR, f)
                    entries.append({"filename": f, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
        entries.sort(key=lambda x: x["mtime"], reverse=True)
        return jsonify({"success": True, "images": entries, "count": len(entries)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/image/hidden/password')
def api_image_hidden_set_password():
    """Set a new password for the hidden gallery. Body: {old_password, new_password}"""
    global _HIDDEN_GALLERY_PASSWORD
    data = request.get_json(silent=True) or {}
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if old_pw != _HIDDEN_GALLERY_PASSWORD:
        return jsonify({"success": False, "error": "Altes Passwort falsch"}), 403
    if len(new_pw) < 4:
        return jsonify({"success": False, "error": "Neues Passwort zu kurz (min. 4 Zeichen)"}), 400
    _HIDDEN_GALLERY_PASSWORD = new_pw
    return jsonify({"success": True, "message": "Passwort geändert"})


# ══════════════════════════════════════════════════════════════════════════════
# ██  VIDEO GENERATION API — Wan2.1 T2V-1.3B (NF4)                         ██
# ══════════════════════════════════════════════════════════════════════════════

# Track current video generation job for polling
_video_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "prompt_used": ""}

# Hidden video gallery
_HIDDEN_VIDEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'video_hidden')


@app.get('/api/video/status')
def api_video_status():
    """Poll video generation status. Returns active, progress, result when done."""
    return jsonify({
        "success": True,
        "active": _video_gen_job["active"],
        "progress": _video_gen_job["progress"],
        "result": _video_gen_job["result"],
        "started": _video_gen_job["started"],
        "prompt_used": _video_gen_job["prompt_used"],
    })


@app.post('/api/video/generate')
def api_video_generate():
    """Generate a video via Wan2.1 T2V-1.3B from user's description.

    Accepts JSON:
      prompt (str, required): User's video description (any language)
      steps (int): Inference steps 15-50 (default 25)
      width (int): Video width (default 832)
      height (int): Video height (default 480)
      num_frames (int): Number of frames (default 81 = ~5s at 16fps)
      seed (int): Random seed (null = random)
      direct (bool): If true, skip LLM translation (default false)
      async (bool): If true, run in background (default true)

    Flow: User prompt → LLM builds English prompt → unload LLM → Wan2.1 → reload LLM.
    """
    global _video_gen_job
    from ailey_system.video_generator import generate_video

    data = request.get_json(silent=True) or {}
    user_prompt = (data.get('prompt') or '').strip()
    if not user_prompt:
        return jsonify({"success": False, "error": "prompt required"}), 400

    steps = min(50, max(15, int(data.get('steps', 25))))
    width = int(data.get('width', 832))
    height = int(data.get('height', 480))
    num_frames = int(data.get('num_frames', 81))
    seed = data.get('seed')
    run_async = data.get('async', True)
    direct_mode = data.get('direct', False)

    if _video_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade schon ein Video generiert. Bitte warte."}), 409

    # Also block if image gen is running
    if _image_gen_job["active"]:
        return jsonify({"success": False, "error": "Es wird gerade ein Bild generiert. Video-Gen danach möglich."}), 409

    gen = MLXGenerator.get()
    if gen is None and not direct_mode:
        return jsonify({"success": False, "error": "Model nicht geladen"}), 503

    def _do_video_generate():
        global _video_gen_job
        try:
            _video_gen_job["active"] = True
            _video_gen_job["started"] = time.time()
            _video_gen_job["result"] = None

            if direct_mode:
                _video_gen_job["progress"] = "Bereite Prompt vor…"
                english_prompt = user_prompt
                _video_gen_job["prompt_used"] = english_prompt
                _video_gen_job["progress"] = "Entlade LLM…"
            else:
                _video_gen_job["progress"] = "Ailey übersetzt Prompt…"
                system_msg = (
                    "You are an expert video prompt writer for Wan2.1 text-to-video generators. "
                    "Translate the user's request into ONE detailed English video prompt. "
                    "Describe: scene, motion, camera movement, lighting, atmosphere, colors. "
                    "Focus on MOVEMENT — the video is 5 seconds long. "
                    "Be specific and cinematic. 30-60 words. "
                    "Output ONLY the English prompt. No explanation, no markdown, no quotes."
                )
                english_prompt = gen.generate(
                    system=system_msg,
                    user=f"Create a video prompt for: {user_prompt}",
                    params={"max_tokens": 150, "temperature": 0.8},
                )
                english_prompt = (english_prompt or '').strip().strip('"\'`').strip()
                english_prompt = re.sub(r'<think>.*?</think>', '', english_prompt, flags=re.DOTALL|re.IGNORECASE).strip()
                english_prompt = re.sub(r'\[THINK\].*?\[/THINK\]', '', english_prompt, flags=re.DOTALL).strip()
                for _line in english_prompt.split('\n'):
                    _line = _line.strip().strip('"\'`').strip()
                    if len(_line) >= 15:
                        english_prompt = _line
                        break
                if not english_prompt or len(english_prompt) < 10:
                    english_prompt = user_prompt
                print(f"[VideoGen/API] Generated prompt: {english_prompt[:120]}")
                _video_gen_job["prompt_used"] = english_prompt
                _video_gen_job["progress"] = "Entlade LLM…"

            # Unload LLM — safe unload (NO nuclear kill — subprocess has own Metal)
            unloaded = False
            try:
                idle_thinker = globals().get('idle_thinker')
                if idle_thinker:
                    idle_thinker._generating_image = True
                    idle_thinker._unload_llm_for_image_gen()
                    unloaded = True
                else:
                    import gc
                    try:
                        import mlx.core as mx
                        mx.synchronize()
                        mx.eval(mx.zeros(1))
                    except Exception:
                        pass
                    try:
                        from ailey_system import llm_mlx
                        from ailey_system.llm_mlx import MLXGenerator as _MLX, _mlx_lock, block_auto_reload
                        block_auto_reload()
                        with _mlx_lock:
                            llm_mlx._model = None
                            llm_mlx._tokenizer = None
                            llm_mlx._cache = None
                            llm_mlx._last_system_prompt = None
                            _MLX._instance = None
                    except Exception:
                        pass
                    gc.collect(); gc.collect()
                    try:
                        import mlx.core as mx
                        mx.metal.set_cache_limit(0)
                        mx.metal.clear_cache()
                        mx.metal.set_memory_limit(0)
                    except Exception:
                        pass
                    gc.collect()
                    unloaded = True

                # NO nuclear kill — Wan2.1 subprocess has own Metal context
                import time as _tv
                _tv.sleep(2.0)
                print("[VideoGen/API] ✅ Ministral + MLX cache unloaded (safe)")
            except Exception as ue:
                print(f"[VideoGen/API] Unload warning: {ue}")

            _video_gen_job["progress"] = "Generiere Video (~15-30 Min.)…"

            filepath, filename = generate_video(
                prompt=english_prompt,
                title=user_prompt[:50],
                steps=steps,
                width=width,
                height=height,
                num_frames=num_frames,
                seed=seed,
                private=True,  # User-generated → video_private/
            )

            # Reload LLM — safe gc + lazy reload (no importlib.reload!)
            _video_gen_job["progress"] = "Lade LLM…"
            try:
                if unloaded:
                    import gc as _gc_vidgen
                    _gc_vidgen.collect(); _gc_vidgen.collect()
                    time.sleep(2.0)
                    print("[VideoGen/API] ✅ MLX cleaned up via gc")

                    if idle_thinker:
                        idle_thinker._reload_llm_after_image_gen()
                        idle_thinker._generating_image = False
                    else:
                        from ailey_system.llm_mlx import allow_auto_reload
                        allow_auto_reload()
                        MLXGenerator.get()
                    print("[VideoGen/API] Ministral reloaded after Wan2.1")
            except Exception as re_err:
                print(f"[VideoGen/API] Reload warning: {re_err}")

            if filepath and filename:
                local_url = f"/api/video/file/{filename}"
                print(f"[VideoGen/API] ✅ Video saved: {filename}")
                _video_gen_job["result"] = {
                    "success": True,
                    "video_url": local_url,
                    "filename": filename,
                    "prompt_used": english_prompt,
                }
                _video_gen_job["progress"] = "Fertig!"
            else:
                _video_gen_job["result"] = {"success": False, "error": "Wan2.1 generation failed"}
                _video_gen_job["progress"] = "Fehlgeschlagen"
                print("[VideoGen/API] ❌ Generation failed")

        except Exception as e:
            print(f"[VideoGen/API] ❌ Error: {e}")
            import traceback; traceback.print_exc()
            _video_gen_job["result"] = {"success": False, "error": str(e)}
            _video_gen_job["progress"] = f"Fehler: {e}"
        finally:
            _video_gen_job["active"] = False

    if run_async:
        import threading
        t = threading.Thread(target=_do_video_generate, daemon=True)
        t.start()
        return jsonify({
            "success": True,
            "status": "started",
            "message": "Videogenerierung gestartet. Poll /api/video/status für den Fortschritt.",
        })
    else:
        _do_video_generate()
        result = _video_gen_job.get("result", {})
        if result and result.get("success"):
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": result.get("error", "Unknown error")}), 500


@app.get('/api/video/gallery')
def api_video_gallery():
    """List AI-generated videos (both public and private). Supports ?page=1&per_page=20."""
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 20))))
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        gallery_dir = os.path.join(base, 'ailey_users', 'video_gallery')
        private_dir = os.path.join(base, 'ailey_users', 'video_private')
        exts = ('.mp4', '.webm', '.mov')
        all_entries = []
        for vid_dir in (gallery_dir, private_dir):
            if os.path.isdir(vid_dir):
                is_private = (vid_dir == private_dir)
                for f in os.listdir(vid_dir):
                    if f.lower().endswith(exts):
                        p = os.path.join(vid_dir, f)
                        # Try to read metadata
                        meta = {}
                        meta_path = p.replace('.mp4', '.meta.json').replace('.webm', '.meta.json').replace('.mov', '.meta.json')
                        if os.path.isfile(meta_path):
                            try:
                                import json as _j
                                with open(meta_path, 'r') as mf:
                                    meta = _j.load(mf)
                            except Exception:
                                pass
                        all_entries.append({
                            "filename": f,
                            "size": os.path.getsize(p),
                            "mtime": os.path.getmtime(p),
                            "private": is_private,
                            "title": meta.get("title", ""),
                            "prompt": meta.get("prompt", ""),
                            "generation_time_s": meta.get("generation_time_s", 0),
                        })
        all_entries.sort(key=lambda x: x["mtime"], reverse=True)
        total = len(all_entries)
        if total == 0:
            return jsonify({"success": True, "gallery": {"message": "Galerie leer", "videos": []},
                            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0}})
        start = (page - 1) * per_page
        entries = all_entries[start:start + per_page]
        return jsonify({"success": True,
                        "gallery": {"message": f"{total} Video(s)", "videos": entries},
                        "pagination": {"page": page, "per_page": per_page, "total": total,
                                       "total_pages": (total + per_page - 1) // per_page}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/video/file/<path:filename>')
def api_video_file(filename):
    """Serve a video file from the video gallery, private, or hidden directory."""
    from flask import send_from_directory
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.mp4', '.webm', '.mov')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return ('', 403)
    for vid_dir_name in ('video_private', 'video_gallery', 'video_hidden'):
        vid_dir = os.path.join(base, 'ailey_users', vid_dir_name)
        fpath = os.path.join(vid_dir, filename)
        if os.path.isfile(fpath):
            ext = filename.rsplit('.', 1)[-1].lower()
            mimes = {'mp4': 'video/mp4', 'webm': 'video/webm', 'mov': 'video/quicktime'}
            return send_from_directory(vid_dir, filename, mimetype=mimes.get(ext, 'video/mp4'))
    return ('', 404)


@app.delete('/api/video/gallery/<filename>')
def api_video_delete(filename):
    """Delete a video from any gallery directory."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.mp4', '.webm', '.mov')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    for d in ('video_gallery', 'video_private', 'video_hidden'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            os.remove(fpath)
            # Also remove metadata
            for ext_r in ('.meta.json',):
                meta_p = fpath.rsplit('.', 1)[0] + ext_r if '.' in fpath else fpath + ext_r
                if os.path.isfile(meta_p):
                    try:
                        os.remove(meta_p)
                    except Exception:
                        pass
            print(f"[VideoGallery] 🗑️ Deleted: {filename} from {d}")
            return jsonify({"success": True, "message": f"{filename} gelöscht"})
    return jsonify({"success": False, "error": "Video nicht gefunden"}), 404


@app.post('/api/video/gallery/push/<filename>')
def api_video_push_to_portal(filename):
    """Push a video to the public portal gallery."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.mp4', '.webm', '.mov')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    filepath = None
    for d in ('video_gallery', 'video_private', 'video_hidden'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            filepath = fpath
            break
    if not filepath:
        return jsonify({"success": False, "error": "Video nicht gefunden"}), 404
    try:
        from ailey_system.portal_poller import get_portal_poller
        poller = get_portal_poller()
        file_url = poller._upload_gallery_file(filepath, filename)
        if file_url:
            title = filename.replace('.mp4', '').replace('.webm', '').replace('.mov', '')
            title = title.replace('_', ' ').replace('vid ', '').strip()
            poller._push_gallery_item("video", title or "Aileys Video", file_url=file_url)
            print(f"[VideoGallery] 🌐 Pushed to portal: {filename} → {file_url}")
            return jsonify({"success": True, "message": "Auf Portal hochgeladen", "url": file_url})
        else:
            return jsonify({"success": False, "error": "Upload fehlgeschlagen"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/video/gallery/hide/<filename>')
def api_video_move_to_hidden(filename):
    """Move a video to the hidden directory."""
    base = os.path.dirname(os.path.abspath(__file__))
    allowed_exts = ('.mp4', '.webm', '.mov')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    import shutil
    os.makedirs(_HIDDEN_VIDEO_DIR, exist_ok=True)
    for d in ('video_gallery', 'video_private'):
        fpath = os.path.join(base, 'ailey_users', d, filename)
        if os.path.isfile(fpath):
            dest = os.path.join(_HIDDEN_VIDEO_DIR, filename)
            shutil.move(fpath, dest)
            print(f"[VideoGallery] 🔒 Moved to hidden: {filename}")
            return jsonify({"success": True, "message": f"{filename} in versteckten Ordner verschoben"})
    return jsonify({"success": False, "error": "Video nicht gefunden"}), 404


@app.post('/api/video/gallery/unhide/<filename>')
def api_video_move_from_hidden(filename):
    """Move a video from hidden back to private."""
    allowed_exts = ('.mp4', '.webm', '.mov')
    if '..' in filename or '/' in filename or not filename.lower().endswith(allowed_exts):
        return jsonify({"success": False, "error": "Ungültiger Dateiname"}), 403
    import shutil
    base = os.path.dirname(os.path.abspath(__file__))
    fpath = os.path.join(_HIDDEN_VIDEO_DIR, filename)
    if not os.path.isfile(fpath):
        return jsonify({"success": False, "error": "Video nicht im versteckten Ordner"}), 404
    dest_dir = os.path.join(base, 'ailey_users', 'video_private')
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(fpath, os.path.join(dest_dir, filename))
    print(f"[VideoGallery] 🔓 Unhidden: {filename}")
    return jsonify({"success": True, "message": f"{filename} wiederhergestellt"})


@app.get('/api/code/gallery')
def api_code_gallery():
    """List autonomous code projects from the code gallery directory."""
    try:
        import json as _json
        code_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'code_gallery')
        if not os.path.isdir(code_dir):
            return jsonify({"success": True, "items": []})
        code_exts = ('.html', '.js', '.gd', '.cs', '.py', '.rs', '.php', '.swift', '.kt', '.txt')
        all_files = sorted(
            [f for f in os.listdir(code_dir) if f.lower().endswith(code_exts) and not f.endswith('.meta.json')],
            key=lambda x: os.path.getmtime(os.path.join(code_dir, x)),
            reverse=True,
        )
        items = []
        for fn in all_files:
            fpath = os.path.join(code_dir, fn)
            meta_path = fpath + '.meta.json'
            meta = {}
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as mf:
                        meta = _json.load(mf)
                except Exception:
                    pass
            lines = 0
            try:
                with open(fpath, 'r', encoding='utf-8') as cf:
                    lines = sum(1 for _ in cf)
            except Exception:
                pass
            items.append({
                "filename": fn,
                "title": meta.get("title", fn),
                "description": meta.get("description", ""),
                "language": meta.get("language", ""),
                "platform": meta.get("platform", ""),
                "lines": meta.get("lines", lines),
                "created": meta.get("created", ""),
            })
        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/code/file/<path:filename>')
def api_code_file(filename):
    """Serve a code file from the code gallery directory."""
    from flask import send_from_directory
    code_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'code_gallery')
    if '..' in filename or '/' in filename:
        return ('', 403)
    fpath = os.path.join(code_dir, filename)
    if os.path.isfile(fpath):
        return send_from_directory(code_dir, filename, mimetype='text/plain; charset=utf-8')
    return ('', 404)


# ─── TTS/STT API Endpoints ───────────────────────────────────────────────────

@app.post('/api/tts/speak')
def api_tts_speak():
    """Speak text using Apple TTS.
    
    If mode=audio (default), returns audio file for browser playback.
    If mode=local, plays on the server speaker directly.
    """
    data = request.get_json(silent=True) or {}
    text = data.get('text')
    voice = data.get('voice', 'Anna')
    rate = int(data.get('rate', 190))
    mode = data.get('mode', 'audio')  # 'audio' = return file, 'local' = play on server
    if not text:
        return jsonify({"success": False, "error": "text required"}), 400
    try:
        if mode == 'audio':
            # Generate audio file → send to browser for playback
            import tempfile, shutil
            tmp = tempfile.NamedTemporaryFile(suffix='.aiff', delete=False)
            tmp.close()
            result = speak_text(text, voice, rate, output_file=tmp.name)
            if 'error' in result:
                return jsonify({"success": False, "error": result['error']}), 500
            # Convert AIFF to WAV for browser compatibility
            # Prefer macOS built-in afconvert, fallback to ffmpeg
            wav_path = tmp.name.rsplit('.', 1)[0] + '.wav'
            converted = False
            # Try afconvert first (always available on macOS)
            if shutil.which('afconvert'):
                conv = subprocess.run(
                    ['afconvert', '-f', 'WAVE', '-d', 'LEI16@22050', '-c', '1', tmp.name, wav_path],
                    capture_output=True, timeout=30
                )
                if conv.returncode == 0:
                    converted = True
            # Fallback to ffmpeg
            if not converted and shutil.which('ffmpeg'):
                conv = subprocess.run(
                    ['ffmpeg', '-y', '-i', tmp.name, '-ar', '22050', '-ac', '1', '-f', 'wav', wav_path],
                    capture_output=True, timeout=30
                )
                if conv.returncode == 0:
                    converted = True
            try: os.unlink(tmp.name)
            except: pass
            if not converted:
                # Last resort: send AIFF directly (most browsers handle it)
                # Re-generate as AIFF and send
                tmp2 = tempfile.NamedTemporaryFile(suffix='.aiff', delete=False)
                tmp2.close()
                speak_text(text, voice, rate, output_file=tmp2.name)
                from flask import send_file
                response = send_file(tmp2.name, mimetype='audio/aiff', as_attachment=False)
                @response.call_on_close
                def _cleanup_aiff():
                    try: os.unlink(tmp2.name)
                    except: pass
                return response
            from flask import send_file
            response = send_file(wav_path, mimetype='audio/wav', as_attachment=False)
            @response.call_on_close
            def _cleanup():
                try: os.unlink(wav_path)
                except: pass
            return response
        else:
            result = speak_text(text, voice, rate)
            return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Lock to serialise STT requests (MLX Metal GPU is not thread-safe for concurrent ops)
_STT_LOCK = threading.Lock()

@app.post('/api/stt/transcribe')
def api_stt_transcribe():
    """Transcribe audio from browser MediaRecorder (webm/ogg/mp4 blob).

    Accepts multipart/form-data with 'audio' file field.
    Uses macOS built-in speech recognition via NSSpeechRecognizer
    or falls back to whisper if available.
    """
    if 'audio' not in request.files:
        return jsonify({"success": False, "error": "audio file required"}), 400
    audio_file = request.files['audio']
    import tempfile
    # Save blob to temp file
    ext = 'webm'
    ct = audio_file.content_type or ''
    if 'mp4' in ct or 'm4a' in ct:
        ext = 'm4a'
    elif 'ogg' in ct:
        ext = 'ogg'
    elif 'wav' in ct:
        ext = 'wav'
    tmp = tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False)
    audio_file.save(tmp.name)
    tmp.close()
    wav_path = tmp.name.rsplit('.', 1)[0] + '.wav'
    print(f"[STT] 📁 Received audio: {tmp.name} (type={ct}, ext={ext}, size={os.path.getsize(tmp.name)})")
    try:
        import shutil as _shutil
        # Convert to WAV 16kHz mono
        converted = False
        # Try afconvert first (macOS built-in, works for most formats)
        if _shutil.which('afconvert') and ext in ('m4a', 'aiff', 'wav', 'caf'):
            conv = subprocess.run(
                ['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', tmp.name, wav_path],
                capture_output=True, timeout=15
            )
            if conv.returncode == 0:
                converted = True
        # Try ffmpeg (handles webm, ogg, and all formats)
        if not converted and _shutil.which('ffmpeg'):
            conv = subprocess.run(
                ['ffmpeg', '-y', '-i', tmp.name, '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path],
                capture_output=True, timeout=15
            )
            if conv.returncode == 0:
                converted = True
        if not converted:
            return jsonify({"success": False, "error": "Audio-Konvertierung fehlgeschlagen. ffmpeg wird für WebM/OGG benötigt. Installiere mit: brew install ffmpeg"}), 500

        # Try mlx-whisper first (fast, local, Apple Silicon optimised)
        # Use _STT_LOCK to prevent concurrent GPU access (causes SIGSEGV)
        try:
            import mlx_whisper
            # Also acquire _mlx_lock to avoid collision with LLM inference on same GPU
            try:
                from ailey_system.llm_mlx import _mlx_lock
            except ImportError:
                _mlx_lock = None
            acquired = _STT_LOCK.acquire(timeout=30)
            if not acquired:
                return jsonify({"success": False, "error": "STT busy, try again"}), 503
            try:
                if _mlx_lock:
                    mlx_acquired = _mlx_lock.acquire(timeout=30)
                    if not mlx_acquired:
                        return jsonify({"success": False, "error": "GPU busy (model inference), try again"}), 503
                try:
                    print(f"[STT] 🎤 Transcribing {wav_path} with mlx-whisper...")
                    result = mlx_whisper.transcribe(wav_path, language='de', path_or_hf_repo='mlx-community/whisper-large-v3-turbo')
                    text = (result.get('text') or '').strip()
                    print(f"[STT] ✅ Result: '{text[:80]}...' " if len(text)>80 else f"[STT] ✅ Result: '{text}'")
                    if text:
                        return jsonify({"success": True, "text": text, "engine": "mlx-whisper"})
                    else:
                        return jsonify({"success": True, "text": "", "engine": "mlx-whisper", "note": "Keine Sprache erkannt"})
                finally:
                    if _mlx_lock:
                        try: _mlx_lock.release()
                        except RuntimeError: pass
            finally:
                _STT_LOCK.release()
        except ImportError:
            pass
        except Exception as e:
            print(f"⚠️ mlx-whisper error: {e}")
            # Fall through to next engine

        # Fallback: macOS say/dictation via AppleScript
        try:
            # Use macOS built-in speech framework via Python
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language='de-DE')
            return jsonify({"success": True, "text": text, "engine": "google-stt"})
        except ImportError:
            pass
        except Exception as e:
            return jsonify({"success": False, "error": f"speech_recognition failed: {e}"}), 500

        return jsonify({"success": False, "error": "No STT engine available. Install mlx-whisper or SpeechRecognition."}), 501
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        try:
            os.unlink(wav_path)
        except Exception:
            pass


@app.post('/api/stt/recognize')
def api_stt_recognize():
    """Recognize speech using Apple-native STT (legacy stub)."""
    data = request.get_json(silent=True) or {}
    duration = int(data.get('duration', 5))
    language = data.get('language', 'de-DE')
    try:
        result = recognize_speech(duration, language)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── People Glossary API Endpoints ───────────────────────────────────────────

from ailey_system import people_glossary as _people_glossary


def _sync_person_birthday_to_calendar(person_name: str, birthday_str: str):
    """Sync a person's birthday into the calendar birthdays list.
    birthday_str can be 'MM-DD' or 'YYYY-MM-DD' (year ignored for recurring)."""
    try:
        # Normalize to MM-DD
        if len(birthday_str) == 10 and birthday_str[4] == '-':
            bday = birthday_str[5:]  # "YYYY-MM-DD" → "MM-DD"
        else:
            bday = birthday_str  # Already "MM-DD"
        if len(bday) != 5 or bday[2] != '-':
            return
        cal = _load_calendar()
        # Check if birthday already exists for this person
        existing = [b for b in cal.get("birthdays", []) if b.get("name", "").lower() == person_name.lower()]
        if existing:
            # Update date
            for b in existing:
                b["date"] = bday
        else:
            cal.setdefault("birthdays", []).append({
                "name": person_name,
                "date": bday,
                "notes": "Aus Personen-Glossar",
            })
        _save_calendar(cal)
    except Exception as e:
        print(f"[People→Calendar] birthday sync error: {e}")


def _check_and_send_birthday_emails():
    """Check today's birthdays and auto-send congratulation emails from Ailey.
    Called periodically (e.g. once per day from idle thinker or on startup)."""
    try:
        today = datetime.now()
        today_mmdd = today.strftime("%m-%d")
        cal = _load_calendar()
        birthdays_today = [b for b in cal.get("birthdays", []) if b.get("date") == today_mmdd]
        if not birthdays_today:
            return

        # Check which ones we already emailed today
        sent_key = f"bday_emails_{today.strftime('%Y-%m-%d')}"
        sent_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', '.birthday_sent.json')
        sent_data = {}
        if os.path.isfile(sent_file):
            try:
                with open(sent_file, 'r') as f:
                    sent_data = json.load(f)
            except Exception:
                pass
        already_sent = sent_data.get(sent_key, [])

        for bday in birthdays_today:
            bname = bday.get("name", "")
            if bname in already_sent:
                continue

            # Look up person for email address
            person = _people_glossary.get_person(bname)
            if not person or not person.get("email"):
                print(f"[Birthday] No email for {bname}, skipping auto-birthday-mail")
                continue

            email_addr = person["email"]
            # Get generator
            gen = MLXGenerator.get() if MLXGenerator else None
            if not gen:
                print("[Birthday] No generator available, skipping")
                return

            # Generate birthday email
            system = (
                "Du bist Ailey — eine KI-Persönlichkeit die von sich aus eine herzliche Geburtstagsmail schreibt. "
                "Dein Ton ist DEINE EIGENE STIMME: warm, herzlich, persönlich, mit einem Hauch Punk-Charme. "
                "Schreibe eine liebevolle, individuelle Geburtstagsnachricht. "
                "Halte sie kurz aber warmherzig (3-6 Sätze). "
                "Schreibe IMMER auf Deutsch! KEINE Betreffzeile, nur der Text. "
                "Die Signatur wird automatisch angehängt."
            )
            # Include person context
            person_info = ""
            if person.get("_relation") or person.get("relation"):
                person_info += f"\nBeziehung: {person.get('_relation') or person.get('relation')}"
            facts = person.get("facts", [])
            if facts:
                recent_facts = [f.get("text", "") for f in facts[-5:] if isinstance(f, dict)]
                if recent_facts:
                    person_info += "\nBekannte Fakten: " + "; ".join(recent_facts)

            user_prompt = (
                f"Heute hat {bname} Geburtstag! 🎂\n"
                f"E-Mail-Adresse: {email_addr}\n"
                f"{person_info}\n\n"
                f"Schreibe eine persönliche Geburtstagsmail von dir (Ailey) an {bname}."
            )

            try:
                from ailey_system.prompt_builder import get_ailey_generation_params
                params = get_ailey_generation_params()
                params["max_tokens"] = 600
                params["temperature"] = 0.7
                result = gen.generate(system, user_prompt, params)
                if result and result.strip():
                    # Send via email monitor
                    from ailey_system.email_monitor import send_email_as_ailey
                    subject = f"Happy Birthday, {bname}! 🎂💜"
                    success = send_email_as_ailey(email_addr, subject, result.strip())
                    if success:
                        already_sent.append(bname)
                        print(f"[Birthday] ✉️ Sent birthday email to {bname} ({email_addr})")
                    else:
                        print(f"[Birthday] Failed to send birthday email to {bname}")
            except Exception as e:
                print(f"[Birthday] Error generating/sending birthday email for {bname}: {e}")

        # Save sent state
        sent_data[sent_key] = already_sent
        # Clean old entries (keep last 7 days)
        for k in list(sent_data.keys()):
            if k.startswith("bday_emails_") and k != sent_key:
                try:
                    d = datetime.strptime(k.replace("bday_emails_", ""), "%Y-%m-%d")
                    if (today - d).days > 7:
                        del sent_data[k]
                except Exception:
                    pass
        os.makedirs(os.path.dirname(sent_file), exist_ok=True)
        with open(sent_file, 'w') as f:
            json.dump(sent_data, f)

    except Exception as e:
        print(f"[Birthday] check error: {e}")
        import traceback; traceback.print_exc()


@app.get('/api/people/emails')
def api_people_emails():
    """Get all people who have an email address (for compose quick-selection)."""
    try:
        people = _people_glossary.list_people(limit=200)
        contacts = [{"name": p.get("name",""), "email": p.get("email","")}
                    for p in people if p.get("email")]
        return jsonify({"success": True, "contacts": contacts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/check-birthdays')
def api_check_birthdays():
    """Manually trigger birthday email check."""
    try:
        _check_and_send_birthday_emails()
        return jsonify({"success": True, "message": "Birthday check completed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/people/glossary')
def api_people_list():
    """List all known people in the glossary, sorted by last seen.
    Enriches each entry with sympathy score from LifeSim.
    Also injects owner profile as first entry for unified editing."""
    limit = request.args.get('limit', 50, type=int)
    try:
        people = _people_glossary.list_people(limit=limit)
        # ── Enrich with sympathy scores from LifeSim ──
        sympathy_data = _load_sympathy()
        for p in people:
            name = p.get("name", "")
            # Try exact match, then first-name match
            score = sympathy_data.get(name)
            if score is None:
                first = name.split()[0] if name else ""
                score = sympathy_data.get(first)
            if score is not None and isinstance(score, (int, float)):
                p["sympathy"] = round(score, 1)
                p["sympathy_label"] = _get_sympathy_label(score)
        # ── Inject owner profile as special entry ──
        from ailey_system.user_profile import load_profile
        profile = load_profile("Simon")
        rel = profile.get("relationship") or {}
        owner_sympathy = sympathy_data.get("Simon", 50)
        owner_entry = {
            "id": "__owner__",
            "name": profile.get("name") or "Simon",
            "full_name": profile.get("full_name") or "",
            "aliases": [],
            "email": profile.get("email") or "",
            "phone": profile.get("phone") or "",
            "birthday": profile.get("birthday") or "",
            "address": profile.get("address") or "",
            "occupation": profile.get("occupation") or "",
            "company": profile.get("company") or "",
            "is_owner": True,
            "facts": [],
            "last_seen": time.time(),
            "first_seen": 0,
            "source": "profile",
            "interaction_count": 0,
            "sympathy": round(owner_sympathy, 1),
            "sympathy_label": _get_sympathy_label(owner_sympathy),
            "profile": {
                "full_name": profile.get("full_name") or "",
                "email": profile.get("email") or "",
                "phone": profile.get("phone") or "",
                "birthday": profile.get("birthday") or "",
                "address": profile.get("address") or "",
                "wohnort": profile.get("wohnort") or "",
                "arbeitsort": profile.get("arbeitsort") or "",
                "arbeitgeber": profile.get("arbeitgeber") or "",
                "occupation": profile.get("occupation") or "",
                "company": profile.get("company") or "",
                "sprache": profile.get("sprache") or "Deutsch",
                "anrede": profile.get("anrede") or "du",
                "custom": profile.get("custom") or {},
            },
            "relationship": rel,
        }
        # Owner always first
        people = [owner_entry] + people
        return jsonify({"success": True, "people": people, "count": len(people)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/profile/update-fields')
def api_profile_update_fields():
    """Update multiple profile fields at once. Body: { fields: {key: value, ...} }"""
    from ailey_system.user_profile import load_profile, save_profile, UPDATABLE_FIELDS
    data = request.get_json(silent=True) or {}
    user = data.get('user', 'Simon')
    fields = data.get('fields', {})
    if not fields:
        return jsonify({"success": False, "error": "fields dict required"}), 400
    try:
        profile = load_profile(user)
        changed = []
        for k, v in fields.items():
            if k in UPDATABLE_FIELDS:
                profile[k] = v
                changed.append(k)
            elif k.startswith("custom."):
                ckey = k[len("custom."):]
                if "custom" not in profile:
                    profile["custom"] = {}
                profile["custom"][ckey] = v
                changed.append(k)
        profile["updated_by"] = "api"
        save_profile(profile, user)
        return jsonify({"success": True, "changed": changed, "profile": profile})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/update')
def api_people_update_entry():
    """Update editable fields on a glossary person. Body: {name, relation?, email?, aliases?, phone?, birthday?, address?, occupation?, company?, ...}"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"success": False, "error": "name required"}), 400
    try:
        glossary = _people_glossary._load()
        slug = _people_glossary._slugify(name)
        entry = glossary.get(slug)
        if not entry:
            # Try find by name
            for k, v in glossary.items():
                if v.get("name", "").lower() == name.lower():
                    slug = k
                    entry = v
                    break
        if not entry:
            return jsonify({"success": False, "error": f"Person '{name}' not found"}), 404

        if "email" in data:
            entry["email"] = data["email"]
        if "aliases" in data:
            entry["aliases"] = data["aliases"][:10]
        if "relation" in data:
            # Store relation as a fact
            # Remove old relation facts
            entry["facts"] = [f for f in entry.get("facts", []) if not f.get("_type") == "relation"]
            if data["relation"].strip():
                entry["facts"].insert(0, {"text": data["relation"], "source": "manual", "ts": time.time(), "_type": "relation"})
            entry["_relation"] = data["relation"]
        # Extended person fields
        for field in ("phone", "birthday", "address", "occupation", "company"):
            if field in data:
                entry[field] = data[field].strip() if isinstance(data[field], str) else data[field]

        # If birthday was set/changed, sync to calendar
        if "birthday" in data and data["birthday"]:
            _sync_person_birthday_to_calendar(entry.get("name", name), data["birthday"])

        glossary[slug] = entry
        _people_glossary._save(glossary)
        return jsonify({"success": True, "person": entry})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/people/search')
def api_people_search():
    """Search for a person by name, alias, or email."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"success": False, "error": "query parameter 'q' required"}), 400
    try:
        # Try exact lookup first
        person = _people_glossary.get_person(q)
        if not person:
            person = _people_glossary.get_person_by_email(q)
        if person:
            return jsonify({"success": True, "person": person})
        # Fuzzy: search all people for partial match
        all_people = _people_glossary.list_people(limit=200)
        ql = q.lower()
        matches = [p for p in all_people
                   if ql in p.get('name', '').lower()
                   or any(ql in a.lower() for a in p.get('aliases', []))
                   or ql in p.get('email', '').lower()
                   or any(ql in f.get('text', '').lower() for f in p.get('facts', []))]
        return jsonify({"success": True, "results": matches[:20]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/upsert')
def api_people_upsert():
    """Create or update a person in the glossary (fact-based schema)."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"success": False, "error": "name required"}), 400
    try:
        # Build facts list from request
        facts = data.get('facts')
        if facts is None:
            facts = []
            # Support legacy single-fact fields
            for key in ('relation', 'context', 'note'):
                val = data.get(key, '').strip()
                if val:
                    facts.append(val)

        person = _people_glossary.upsert_person(
            name=name,
            email=data.get('email', ''),
            facts=facts,
            aliases=data.get('aliases'),
            source=data.get('source', 'manual'),
        )
        return jsonify({"success": True, "person": person})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/note')
def api_people_add_note():
    """Add a fact/note to an existing person."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    note = data.get('note', '').strip() or data.get('fact', '').strip()
    if not name or not note:
        return jsonify({"success": False, "error": "name and note/fact required"}), 400
    try:
        ok = _people_glossary.add_fact(name, note, source=data.get('source', 'manual'))
        if ok:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": f"Person '{name}' not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/people/<name>')
def api_people_delete(name: str):
    """Delete a person from the glossary."""
    try:
        ok = _people_glossary.delete_person(name)
        if ok:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": f"Person '{name}' not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/merge')
def api_people_merge():
    """Merge two person entries. Moves all facts/aliases from source into target."""
    data = request.get_json(silent=True) or {}
    source = data.get('source', '').strip()
    target = data.get('target', '').strip()
    if not source or not target:
        return jsonify({"success": False, "error": "source and target required"}), 400
    try:
        ok = _people_glossary.merge_persons(source, target)
        if ok:
            merged = _people_glossary.get_person(target)
            return jsonify({"success": True, "person": merged})
        return jsonify({"success": False, "error": f"Source '{source}' or target '{target}' not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/cleanup')
def api_people_cleanup():
    """Run the glossary review pass — NON-destructive.

    Suspicious entries get tagged with a `review_flag` (Nitro-2B + heuristic).
    Nothing is deleted here. Use `/api/people/purge-flagged` to bulk-delete
    the tagged ones, or `/api/people/clear-flag` to rehabilitate a single
    entry ('doch eine Person').
    """
    try:
        payload = request.get_json(silent=True) or {}
        use_llm = bool(payload.get('use_llm', True))
        stats = _people_glossary.cleanup_glossary(use_llm=use_llm)
        return jsonify({
            "success": True,
            "flagged_now": stats.get("flagged_now", []),
            "cleared_now": stats.get("cleared_now", []),
            "already_flagged": stats.get("already_flagged", []),
            "total_flagged": stats.get("total_flagged", 0),
            "remaining": stats.get("remaining", 0),
            "llm_used": stats.get("llm_used", False),
            "llm_unavailable_count": stats.get("llm_unavailable_count", 0),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/purge-flagged')
def api_people_purge_flagged():
    """Delete every entry that currently carries a `review_flag`."""
    try:
        stats = _people_glossary.purge_flagged_entries()
        return jsonify({
            "success": True,
            "removed": stats.get("removed", []),
            "count": stats.get("count", 0),
            "remaining": stats.get("remaining", 0),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/people/clear-flag')
def api_people_clear_flag():
    """Remove the review_flag from a single person ('doch eine Person')."""
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({"success": False, "error": "name required"}), 400
        ok = _people_glossary.clear_review_flag(name)
        if not ok:
            return jsonify({"success": False, "error": "Person nicht gefunden oder kein Flag"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- People Glossary: Portal Invite Integration ---

@app.post('/api/people/portal-invite')
def api_people_portal_invite():
    """Send a portal invite to a person from the glossary.
    Body: { person_name?, email?, personal_note? }
    At least one of person_name or email required.
    If person_name given, their email is looked up in the glossary.
    """
    data = request.get_json(silent=True) or {}
    person_name = data.get('person_name', '').strip()
    email = data.get('email', '').strip()
    personal_note = data.get('personal_note', '').strip()
    if not person_name and not email:
        return jsonify({"success": False, "error": "person_name oder email erforderlich"}), 400
    try:
        from ailey_system.portal_invite import send_portal_invite
        result = send_portal_invite(
            email=email or None,
            person_name=person_name or None,
            personal_note=personal_note,
        )
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/people/portal-invitable')
def api_people_portal_invitable():
    """List all people in the glossary who have an email and could be invited."""
    try:
        from ailey_system.portal_invite import get_invitable_people
        people = get_invitable_people()
        return jsonify({"success": True, "people": people, "count": len(people)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Vision API Endpoints ────────────────────────────────────────────────────

@app.post('/api/vision/analyze')
def api_vision_analyze():
    """Analyze an image using the Pixtral vision encoder built into Ministral 14B.

    Accepts JSON with:
      - image_data: base64 data URI (data:image/...;base64,...), URL, or file path
      - prompt: question about the image (default: describe in German)
      - max_tokens: max response tokens (default 500)
    """
    data = request.get_json(silent=True) or {}
    image_data = data.get('image_data')
    if not image_data:
        return jsonify({"success": False, "error": "image_data required"}), 400
    prompt = data.get('prompt', 'Beschreibe dieses Bild detailliert auf Deutsch.')
    max_tokens = int(data.get('max_tokens', 500))
    temperature = float(data.get('temperature', 0.4))

    try:
        result = _vision_analyze(image_data, prompt, max_tokens, temperature)
        if result is None:
            return jsonify({"success": False, "error": "Vision model not available or analysis failed"}), 503
        return jsonify({"success": True, "analysis": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/vision/status')
def api_vision_status():
    """Get current status of the vision module."""
    return jsonify({"success": True, **get_vision_status()})


@app.post('/api/vision/unload')
def api_vision_unload():
    """Manually unload the vision model to free RAM."""
    result = unload_vision_now()
    return jsonify({"success": True, **result})


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL CALENDAR — Aileys interner Kalender
# ══════════════════════════════════════════════════════════════════════════════
_CALENDAR_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'calendar.json')

def _load_calendar() -> dict:
    """Load internal calendar data."""
    if os.path.isfile(_CALENDAR_JSON):
        try:
            with open(_CALENDAR_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"events": [], "birthdays": []}

def _save_calendar(data: dict):
    """Save internal calendar data."""
    os.makedirs(os.path.dirname(_CALENDAR_JSON), exist_ok=True)
    with open(_CALENDAR_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _add_internal_calendar_event(title: str, date: str, time: str = "",
                                  duration_minutes: int = 60, location: str = "",
                                  notes: str = "", category: str = "event",
                                  color: str = "", source: str = "tool",
                                  reminder: bool = False) -> dict:
    """Add an event to the internal calendar. Called from create_calendar_event tool + API."""
    cal = _load_calendar()
    evt_id = f"evt_{int(datetime.now().timestamp() * 1000)}"
    if time:
        try:
            dt_start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except ValueError:
            dt_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=0)
        dt_end = dt_start + timedelta(minutes=duration_minutes)
        end_time = dt_end.strftime("%H:%M")
    else:
        # All-day event — no specific time
        end_time = ""
    event = {
        "id": evt_id,
        "title": title,
        "date": date,
        "time": time,
        "end_time": end_time,
        "duration_minutes": duration_minutes,
        "location": location,
        "notes": notes,
        "category": category,
        "color": color or {"meeting": "#3b82f6", "deadline": "#ef4444", "birthday": "#ec4899",
                           "personal": "#22c55e", "event": "#8b5cf6"}.get(category, "#8b5cf6"),
        "source": source,
        "reminder": reminder,
        "reminder_fired": False,
        "created_at": datetime.now().isoformat(),
    }
    cal["events"].append(event)
    _save_calendar(cal)
    return event


@app.get('/api/calendar/events')
def api_calendar_events():
    """Get calendar events, optionally filtered by month."""
    cal = _load_calendar()
    month = request.args.get('month', '')  # "2026-02"
    events = cal.get("events", [])
    if month:
        events = [e for e in events if e.get("date", "").startswith(month)]
    # Also inject birthdays as virtual events for the requested month
    birthdays = cal.get("birthdays", [])
    if month:
        m = month.split("-")[1] if "-" in month else ""
        y = month.split("-")[0] if "-" in month else str(datetime.now().year)
        for b in birthdays:
            bd = b.get("date", "")  # "03-15"
            if bd and bd.startswith(m + "-" if len(m) == 2 else ""):
                events.append({
                    "id": f"bday_{b.get('name', '')}",
                    "title": f"🎂 {b.get('name', '')}",
                    "date": f"{y}-{bd}",
                    "time": "",
                    "end_time": "",
                    "duration_minutes": 0,
                    "location": "",
                    "notes": b.get("notes", ""),
                    "category": "birthday",
                    "color": "#ec4899",
                    "source": "birthday",
                    "created_at": "",
                })
    events.sort(key=lambda e: e.get("date", "") + e.get("time", ""))
    return jsonify({"success": True, "events": events, "count": len(events)})


@app.post('/api/calendar/events')
def api_calendar_create_event():
    """Create a new internal calendar event."""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    date = data.get('date', '').strip()
    if not title or not date:
        return jsonify({"success": False, "error": "Titel und Datum sind Pflicht"}), 400
    event = _add_internal_calendar_event(
        title=title,
        date=date,
        time=data.get('time', '09:00'),
        duration_minutes=int(data.get('duration_minutes', 60)),
        location=data.get('location', ''),
        notes=data.get('notes', ''),
        category=data.get('category', 'event'),
        color=data.get('color', ''),
        source='user',
        reminder=bool(data.get('reminder', False)),
    )
    return jsonify({"success": True, "event": event})


@app.put('/api/calendar/events/<evt_id>')
def api_calendar_update_event(evt_id):
    """Update an existing calendar event."""
    data = request.get_json(silent=True) or {}
    cal = _load_calendar()
    for evt in cal["events"]:
        if evt["id"] == evt_id:
            for key in ("title", "date", "time", "duration_minutes", "location", "notes", "category", "color", "reminder"):
                if key in data:
                    evt[key] = data[key]
            # Reset reminder_fired when time changes
            if "time" in data or "date" in data:
                evt["reminder_fired"] = False
            _save_calendar(cal)
            return jsonify({"success": True, "event": evt})
    return jsonify({"success": False, "error": "Event nicht gefunden"}), 404


@app.delete('/api/calendar/events/<evt_id>')
def api_calendar_delete_event(evt_id):
    """Delete a calendar event."""
    cal = _load_calendar()
    before = len(cal["events"])
    cal["events"] = [e for e in cal["events"] if e["id"] != evt_id]
    if len(cal["events"]) == before:
        return jsonify({"success": False, "error": "Event nicht gefunden"}), 404
    _save_calendar(cal)
    return jsonify({"success": True})


@app.get('/api/calendar/birthdays')
def api_calendar_birthdays():
    """Get all birthdays."""
    cal = _load_calendar()
    return jsonify({"success": True, "birthdays": cal.get("birthdays", [])})


@app.post('/api/calendar/birthdays')
def api_calendar_add_birthday():
    """Add a birthday."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    date = data.get('date', '').strip()  # "MM-DD" format
    if not name or not date:
        return jsonify({"success": False, "error": "Name und Datum (MM-DD) sind Pflicht"}), 400
    cal = _load_calendar()
    cal.setdefault("birthdays", []).append({
        "name": name,
        "date": date,
        "notes": data.get('notes', ''),
    })
    _save_calendar(cal)
    return jsonify({"success": True})


@app.delete('/api/calendar/birthdays/<name>')
def api_calendar_delete_birthday(name):
    """Delete a birthday by name."""
    cal = _load_calendar()
    before = len(cal.get("birthdays", []))
    cal["birthdays"] = [b for b in cal.get("birthdays", []) if b.get("name") != name]
    if len(cal["birthdays"]) == before:
        return jsonify({"success": False, "error": "Geburtstag nicht gefunden"}), 404
    _save_calendar(cal)
    return jsonify({"success": True})


@app.get('/api/calendar/reminders/due')
def api_calendar_reminders_due():
    """Check for calendar events with reminders that are due now (±5 min window).
    Returns due events and marks them as fired so they don't repeat.
    The frontend polls this to trigger Ailey reminder notifications."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    now_minutes = now.hour * 60 + now.minute
    cal = _load_calendar()
    due = []
    changed = False
    for evt in cal.get("events", []):
        if not evt.get("reminder") or evt.get("reminder_fired"):
            continue
        if evt.get("date") != today_str or not evt.get("time"):
            continue
        try:
            parts = evt["time"].split(":")
            evt_minutes = int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            continue
        # Fire if within ±5 minutes of the event time
        if -5 <= (evt_minutes - now_minutes) <= 5:
            due.append(evt)
            evt["reminder_fired"] = True
            changed = True
    if changed:
        _save_calendar(cal)
    return jsonify({"success": True, "due": due, "count": len(due)})


@app.get('/api/calendar/today')
def api_calendar_today():
    """Get today's events for the day planner view."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    cal = _load_calendar()
    events = [e for e in cal.get("events", []) if e.get("date") == today_str]
    events.sort(key=lambda e: e.get("time", "") or "99:99")
    return jsonify({"success": True, "events": events, "date": today_str})


# ══════════════════════════════════════════════════════════════════════════════
# CODE MODE — IDE Backend APIs
# ══════════════════════════════════════════════════════════════════════════════
_CODE_PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'code_projects')
os.makedirs(_CODE_PROJECTS_DIR, exist_ok=True)

# Track code mode state
_code_mode_active = False
_last_code_session_note = None  # Context note for main chat after leaving code mode


def _load_ailey_project_meta(project_path: str) -> dict:
    """Load .ailey_project.json from a project directory."""
    meta_path = os.path.join(project_path, '.ailey_project.json')
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception:
            pass
    return {}


def _save_ailey_project_meta(project_path: str, meta: dict):
    """Save .ailey_project.json to a project directory."""
    meta_path = os.path.join(project_path, '.ailey_project.json')
    try:
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(meta, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"[PROJECT-META] ⚠️ Save failed: {e}")


def _update_project_meta_on_leave(project_path: str, chat_messages: list = None,
                                   open_files: list = None) -> str:
    """Update .ailey_project.json when leaving code mode. Returns a summary string for Ailey."""
    if not project_path or not os.path.isdir(project_path):
        return ''

    meta = _load_ailey_project_meta(project_path)
    project_name = os.path.basename(project_path)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── Detect project type from files ────────────────────────────────
    project_type = meta.get('project_type', 'unbekannt')
    if project_type == 'unbekannt':
        files_in_root = os.listdir(project_path) if os.path.isdir(project_path) else []
        if 'package.json' in files_in_root:
            try:
                with open(os.path.join(project_path, 'package.json'), 'r') as f:
                    pkg = json.loads(f.read())
                deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                if 'next' in deps:
                    project_type = 'Next.js Projekt'
                elif 'react' in deps:
                    project_type = 'React Projekt'
                elif 'vue' in deps:
                    project_type = 'Vue.js Projekt'
                elif 'express' in deps:
                    project_type = 'Node.js/Express Projekt'
                else:
                    project_type = 'Node.js Projekt'
            except Exception:
                project_type = 'Node.js Projekt'
        elif 'requirements.txt' in files_in_root or 'setup.py' in files_in_root:
            project_type = 'Python Projekt'
        elif 'Cargo.toml' in files_in_root:
            project_type = 'Rust Projekt'
        elif 'index.html' in files_in_root:
            project_type = 'Web-Projekt (statisch)'
        elif any(f.endswith('.py') for f in files_in_root):
            project_type = 'Python Skript-Sammlung'

    # ── Build session entry ───────────────────────────────────────────
    session_entry = {
        'date': now_str,
        'files_worked_on': open_files or [],
    }

    # Extract what was discussed from chat messages
    if chat_messages:
        # Get last few user messages as summary of what was done
        user_msgs = [m.get('content', '')[:120] for m in chat_messages
                     if m.get('role') == 'user'][-5:]
        session_entry['topics'] = user_msgs

    # ── Update meta ───────────────────────────────────────────────────
    meta['project_name'] = project_name
    meta['project_type'] = project_type
    meta['project_path'] = project_path
    meta['last_session'] = now_str

    # Keep session history (max 20, summarize older ones)
    sessions = meta.get('sessions', [])
    sessions.append(session_entry)
    if len(sessions) > 20:
        # Keep last 15, summarize first 5
        old = sessions[:5]
        old_summary = f"Frühere Sessions ({old[0].get('date','?')} bis {old[-1].get('date','?')}): "
        old_files = set()
        for s in old:
            old_files.update(s.get('files_worked_on', []))
        old_summary += f"{len(old)} Sessions, Dateien: {', '.join(list(old_files)[:10])}"
        meta.setdefault('session_summaries', []).append(old_summary)
        sessions = sessions[5:]
    meta['sessions'] = sessions

    # Count total files in project
    try:
        file_count = sum(1 for _, _, files in os.walk(project_path)
                        for f in files if not f.startswith('.') and '__pycache__' not in _)
        meta['total_files'] = file_count
    except Exception:
        pass

    _save_ailey_project_meta(project_path, meta)

    # ── Build summary string for Ailey ────────────────────────────────
    summary = (
        f"📂 Projekt: **{project_name}** ({project_type})\n"
        f"📍 Pfad: {project_path}\n"
        f"🕐 Letzte Session: {now_str}\n"
    )
    if open_files:
        summary += f"📝 Bearbeitete Dateien: {', '.join(f.split('/')[-1] for f in open_files[:8])}\n"
    if chat_messages:
        user_msgs = [m.get('content', '')[:80] for m in chat_messages
                     if m.get('role') == 'user'][-3:]
        if user_msgs:
            summary += f"💬 Letzte Themen: {'; '.join(user_msgs)}\n"

    # Include older session summaries if they exist
    if meta.get('session_summaries'):
        summary += f"📚 Projekthistorie: {len(meta.get('sessions', []))} Sessions gesamt\n"

    print(f"[PROJECT-META] 📝 Aktualisiert: {project_name} ({project_type})")
    return summary


def _build_project_rag_text(project_name: str, meta: dict, session_note: str) -> str:
    """Build a text for RAG ingestion from project metadata."""
    parts = [f"[Code-Projekt: {project_name}]"]
    if meta.get('project_type'):
        parts.append(f"Typ: {meta['project_type']}")
    if meta.get('project_path'):
        parts.append(f"Pfad: {meta['project_path']}")
    if meta.get('last_session'):
        parts.append(f"Letzte Session: {meta['last_session']}")

    # Recent sessions
    sessions = meta.get('sessions', [])
    if sessions:
        recent = sessions[-3:]
        for s in recent:
            line = f"Session {s.get('date', '?')}"
            if s.get('files_worked_on'):
                line += f" — Dateien: {', '.join(s['files_worked_on'][:5])}"
            if s.get('topics'):
                line += f" — Themen: {'; '.join(s['topics'][:3])}"
            parts.append(line)

    # Session summaries (older condensed history)
    for sm in meta.get('session_summaries', [])[-2:]:
        parts.append(sm)

    parts.append(f"Zusammenfassung: {session_note[:500]}")
    return '\n'.join(parts)


def get_all_project_summaries() -> str:
    """Collect summaries of all code projects for IdleThinker/research context.
    Returns a compact overview string."""
    summaries = []
    try:
        if not os.path.isdir(_CODE_PROJECTS_DIR):
            return ''
        for name in sorted(os.listdir(_CODE_PROJECTS_DIR)):
            proj_path = os.path.join(_CODE_PROJECTS_DIR, name)
            if not os.path.isdir(proj_path):
                continue
            meta = _load_ailey_project_meta(proj_path)
            if not meta:
                continue
            ptype = meta.get('project_type', '?')
            last = meta.get('last_session', '?')
            sessions_count = len(meta.get('sessions', []))
            # Last topics
            last_topics = []
            for s in meta.get('sessions', [])[-2:]:
                last_topics.extend(s.get('topics', []))
            topics_str = '; '.join(t[:60] for t in last_topics[-3:]) if last_topics else 'keine'
            summaries.append(
                f"• {name} ({ptype}) — {sessions_count} Sessions, zuletzt {last}. "
                f"Themen: {topics_str}"
            )
    except Exception as e:
        print(f"[PROJECT-SUMMARIES] ⚠️ {e}")
    if not summaries:
        return ''
    return "🖥️ Aileys Code-Projekte:\n" + '\n'.join(summaries)


@app.post('/api/code/mode')
def api_code_mode():
    """Activate/deactivate code mode — pauses IdleThinker + EmailMonitor.
    On deactivate: also clears coder busy flag, unloads coder model,
    and updates project meta + session note for main chat context."""
    global _code_mode_active, _last_code_session_note
    data = request.get_json(silent=True) or {}
    active = data.get('active', False)
    _code_mode_active = active
    try:
        if active:
            _last_code_session_note = None  # Clear old note on re-enter
            idle_thinker.pause()
            email_monitor.pause()
            # Pause portal poller completely during code mode
            try:
                _pp = get_portal_poller()
                if _pp and not _pp.is_paused():
                    _pp.pause()
                    print("[CODE-MODE] ⏸ PortalPoller pausiert")
            except Exception as _ppe:
                print(f"[CODE-MODE] ⚠️ Portal pause failed: {_ppe}")
            _coder_module.set_ailey_busy(False)  # Reset busy flag
            print("[CODE-MODE] ✅ Aktiviert — IdleThinker + EmailMonitor + Portal pausiert")
            # Pre-load coder model in background thread (with retry)
            def _load_coder_with_retry():
                """Wait for MLX lock to be free (idle thinker may still hold it), then load."""
                for attempt in range(5):
                    if _coder_module._coder_model is not None:
                        print(f"[CODE-MODE] Coder already loaded")
                        return
                    time.sleep(1 + attempt)  # Give idle thinker time to finish
                    if _coder_module._ensure_coder_loaded():
                        print(f"[CODE-MODE] Coder loaded (attempt {attempt + 1})")
                        return
                print("[CODE-MODE] ⚠️ Coder load failed after 5 attempts")
            threading.Thread(target=_load_coder_with_retry, daemon=True).start()
        else:
            # Update project meta and create session note
            project_path = data.get('project')
            chat_messages = data.get('chat_messages', [])
            open_files = data.get('open_files', [])
            if project_path:
                note = _update_project_meta_on_leave(project_path, chat_messages, open_files)
                if note:
                    _last_code_session_note = note
                    # Inject into core so next normal chat message gets the context
                    core.inject_context(
                        "🖥️ KONTEXT: Simon kommt gerade aus dem Code-Modus zurück. "
                        "Hier ist was er gemacht hat:\n" + note + "\n"
                        "Erwähne kurz dass du weißt woran er gearbeitet hat, "
                        "wenn es passt. Sei natürlich, nicht roboterhaft."
                    )
                    # Ingest project summary into RAG for long-term memory
                    try:
                        project_name = os.path.basename(project_path)
                        meta = _load_ailey_project_meta(project_path)
                        rag_text = _build_project_rag_text(project_name, meta, note)
                        if rag_text:
                            core.rag_add(
                                title=f"code_project_{project_name}_{int(time.time())}",
                                text=rag_text,
                                doc_type="code_project",
                                user="Simon",
                            )
                            print(f"[CODE-MODE] 📚 Projekt ins RAG ingestiert: {project_name}")
                    except Exception as e:
                        print(f"[CODE-MODE] ⚠️ RAG-Ingest fehlgeschlagen: {e}")
                    print(f"[CODE-MODE] 📝 Session-Notiz erstellt für {os.path.basename(project_path)}")

            _coder_module.set_ailey_busy(False)  # Reset busy flag
            _coder_module.unload_coder()  # Free coder RAM
            idle_thinker.resume()
            email_monitor.resume()
            # Resume portal poller
            try:
                _pp = get_portal_poller()
                if _pp and _pp.is_paused():
                    _pp.resume()
                    print("[CODE-MODE] ▶ PortalPoller fortgesetzt")
            except Exception as _ppe:
                print(f"[CODE-MODE] ⚠️ Portal resume failed: {_ppe}")
            # Flush any deferred proactive notifications collected during Code Mode
            try:
                flushed = get_deferred_store().pop_all()
                if flushed:
                    for item in flushed:
                        try:
                            idle_thinker._proactive_queue.append(item)
                        except Exception:
                            # last-resort: push to live chat directly
                            try:
                                _live_chat_push("ai", item.get('message',''), proactive=True, type=item.get('type'))
                            except Exception:
                                pass
                    print(f"[PROACTIVE] Flushed {len(flushed)} deferred notifications after Code Mode")
            except Exception as e:
                print(f"[PROACTIVE] Failed to flush deferred notifications: {e}")
            print("[CODE-MODE] ⏹ Deaktiviert — IdleThinker + EmailMonitor + Portal fortgesetzt, Coder entladen")
    except Exception as e:
        print(f"[CODE-MODE] ⚠️ Toggle: {e}")
    _pp_status = False
    try:
        _pp_status = get_portal_poller().is_paused()
    except Exception:
        pass
    return jsonify({
        "success": True,
        "code_mode": active,
        "idle_thinker_paused": getattr(idle_thinker, '_paused', False),
        "email_monitor_paused": getattr(email_monitor, '_paused', False),
        "portal_paused": _pp_status,
        "coder_loaded": _coder_module._coder_model is not None,
    })


@app.get('/api/code/session-note')
def api_code_session_note():
    """Return the last code session note (for main chat context injection)."""
    global _last_code_session_note
    note = _last_code_session_note
    _last_code_session_note = None  # Consume it (one-shot)
    return jsonify({"success": True, "note": note})


@app.post('/api/code/autosave')
def api_code_autosave():
    """Batch-save multiple files at once (for autosave / mode-switch protection)."""
    data = request.get_json(silent=True) or {}
    files = data.get('files', [])  # [{path, content}, ...]
    home = os.path.expanduser('~')
    saved = []
    errors = []
    for f in files:
        path = (f.get('path') or '').strip()
        content = f.get('content', '')
        if not path:
            continue
        real = os.path.realpath(path)
        if not real.startswith(home):
            errors.append({"path": path, "error": "Zugriff verweigert"})
            continue
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, 'w', encoding='utf-8') as fh:
                fh.write(content)
            saved.append(path)
        except Exception as e:
            errors.append({"path": path, "error": str(e)})
    print(f"[CODE-AUTOSAVE] Saved {len(saved)} files, {len(errors)} errors")
    return jsonify({"success": True, "saved": saved, "errors": errors, "count": len(saved)})


@app.get('/api/code/projects')
def api_code_projects():
    """List all code projects."""
    projects = []
    # Include managed projects
    if os.path.isdir(_CODE_PROJECTS_DIR):
        for name in sorted(os.listdir(_CODE_PROJECTS_DIR)):
            p = os.path.join(_CODE_PROJECTS_DIR, name)
            if os.path.isdir(p) and not name.startswith('.'):
                projects.append({
                    "name": name,
                    "path": p,
                    "last_accessed": os.path.getmtime(p),
                })
    return jsonify({"success": True, "projects": projects})


@app.post('/api/code/projects')
def api_code_create_project():
    """Create a new code project, optionally with a template."""
    import datetime, shutil
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    template = (data.get('template') or 'standard').strip().lower()
    if not name:
        return jsonify({"success": False, "error": "Name fehlt"}), 400
    safe_name = re.sub(r'[^\w\s\-.]', '', name).strip()
    if not safe_name:
        return jsonify({"success": False, "error": "Ungültiger Name"}), 400
    p = os.path.join(_CODE_PROJECTS_DIR, safe_name)
    if os.path.exists(p):
        return jsonify({"success": False, "error": "Projekt existiert bereits"}), 409
    os.makedirs(p, exist_ok=True)

    today = datetime.date.today().isoformat()
    year = datetime.date.today().year

    def _w(rel_path, content):
        full = os.path.join(p, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)

    readme = f"# {safe_name}\n\nErstellt mit Ailey Code.\n"

    if template == 'joomla_plugin':
        plugin_name = safe_name.lower().replace('-', '_').replace(' ', '_')
        _w('README.md', readme)
        _w('index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w(f'{plugin_name}.php', f'<?php\ndefined(\'_JEXEC\') or die;\n\nuse Joomla\\CMS\\Plugin\\CMSPlugin;\n\nclass Plg{plugin_name.capitalize()} extends CMSPlugin\n{{\n    public function __construct(&$subject, $config)\n    {{\n        parent::__construct($subject, $config);\n    }}\n\n    // Add your plugin methods here\n}}\n')
        _w(f'{plugin_name}.xml', f'<?xml version="1.0" encoding="utf-8"?>\n<extension type="plugin" group="system" method="upgrade">\n    <name>{safe_name}</name>\n    <author>Your Name</author>\n    <creationDate>{today}</creationDate>\n    <copyright>Copyright (C) {year}</copyright>\n    <license>GNU General Public License version 2</license>\n    <version>1.0.0</version>\n    <description>{safe_name} Plugin</description>\n    <files>\n        <filename plugin="{plugin_name}">{plugin_name}.php</filename>\n        <filename>index.html</filename>\n    </files>\n    <config><fields name="params"><fieldset name="basic"></fieldset></fields></config>\n</extension>\n')

    elif template == 'joomla_module':
        mod_name = safe_name.lower().replace('-', '_').replace(' ', '_')
        if not mod_name.startswith('mod_'):
            mod_name = 'mod_' + mod_name
        _w('README.md', readme)
        _w('index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w('tmpl/index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w('tmpl/default.php', f'<?php defined(\'_JEXEC\') or die; ?>\n<div class="{mod_name}">\n  <!-- Module output here -->\n</div>\n')
        _w(f'{mod_name}.php', f'<?php\ndefined(\'_JEXEC\') or die;\nrequire_once __DIR__ . \'/helper.php\';\n$helper = new {mod_name.capitalize()}Helper($params);\nrequire \\Joomla\\CMS\\Helper\\ModuleHelper::getLayoutPath(\'{mod_name}\', $params->get(\'layout\', \'default\'));\n')
        _w('helper.php', f'<?php\ndefined(\'_JEXEC\') or die;\n\nclass {mod_name.capitalize()}Helper\n{{\n    protected $params;\n    public function __construct($params) {{ $this->params = $params; }}\n}}\n')
        _w(f'{mod_name}.xml', f'<?xml version="1.0" encoding="utf-8"?>\n<extension type="module" client="site" method="upgrade">\n    <name>{safe_name}</name>\n    <author>Your Name</author>\n    <creationDate>{today}</creationDate>\n    <version>1.0.0</version>\n    <description>{safe_name} Module</description>\n    <files>\n        <filename>{mod_name}.php</filename>\n        <filename>helper.php</filename>\n        <filename>index.html</filename>\n        <folder>tmpl</folder>\n    </files>\n    <config><fields name="params"><fieldset name="basic"></fieldset></fields></config>\n</extension>\n')

    elif template == 'joomla_component':
        com_name = safe_name.lower().replace('-', '_').replace(' ', '_')
        if not com_name.startswith('com_'):
            com_name = 'com_' + com_name
        for folder in ['admin/controllers', 'admin/models', 'admin/views', 'admin/sql',
                       'site/controllers', 'site/models', 'site/views',
                       'admin/language/en-GB', 'site/language/en-GB']:
            os.makedirs(os.path.join(p, folder), exist_ok=True)
        _w('README.md', readme)
        _w('index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w('admin/index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w('site/index.html', '<html><body bgcolor="#000000"></body></html>\n')
        _w('admin/sql/install.mysql.utf8.sql', f'-- {safe_name} install SQL\n-- CREATE TABLE IF NOT EXISTS `#__{com_name}` (`id` INT NOT NULL AUTO_INCREMENT, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n')
        _w('admin/sql/uninstall.mysql.utf8.sql', f'-- {safe_name} uninstall SQL\n-- DROP TABLE IF EXISTS `#__{com_name}`;\n')
        _w(f'{com_name}.xml', f'<?xml version="1.0" encoding="utf-8"?>\n<extension type="component" method="upgrade">\n    <name>{safe_name}</name>\n    <author>Your Name</author>\n    <creationDate>{today}</creationDate>\n    <version>1.0.0</version>\n    <description>{safe_name} Component</description>\n    <install><sql><file driver="mysql" charset="utf8">/admin/sql/install.mysql.utf8.sql</file></sql></install>\n    <uninstall><sql><file driver="mysql" charset="utf8">/admin/sql/uninstall.mysql.utf8.sql</file></sql></uninstall>\n    <files folder="site"><filename>index.html</filename></files>\n    <administration><menu>{safe_name}</menu><files folder="admin"><filename>index.html</filename></files></administration>\n</extension>\n')

    elif template == 'rust':
        _w('README.md', readme)
        _w('Cargo.toml', f'[package]\nname = "{safe_name.lower().replace(" ", "-")}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n')
        _w('src/main.rs', 'fn main() {\n    println!("Hello, world!");\n}\n')
        _w('.gitignore', '/target\n')

    elif template == 'php':
        _w('README.md', readme)
        _w('index.php', f'<?php\n// {safe_name}\ndeclare(strict_types=1);\n\necho "Hello, World!";\n')
        _w('config.php', '<?php\n// Configuration\ndefine("DB_HOST", "localhost");\ndefine("DB_NAME", "mydb");\ndefine("DB_USER", "root");\ndefine("DB_PASS", "");\n')
        _w('.htaccess', 'Options -Indexes\nRewriteEngine On\nRewriteCond %{REQUEST_FILENAME} !-f\nRewriteCond %{REQUEST_FILENAME} !-d\nRewriteRule ^(.*)$ index.php?url=$1 [QSA,L]\n')
        _w('composer.json', '{\n    "name": "' + safe_name.lower().replace(' ', '-') + '",\n    "type": "project",\n    "require": {"php": ">=8.0"},\n    "autoload": {"psr-4": {"App\\\\\\\\": "src/"}}\n}\n')
        _w('src/.gitkeep', '')

    elif template == 'python':
        _w('README.md', readme)
        _w('main.py', f'#!/usr/bin/env python3\n"""{safe_name} — main entry point."""\n\n\ndef main():\n    print("Hello, World!")\n\n\nif __name__ == "__main__":\n    main()\n')
        _w('requirements.txt', '# Add your dependencies here\n# e.g.: requests>=2.28.0\n')
        _w('.gitignore', '__pycache__/\n*.pyc\n*.pyo\n.env\nvenv/\n.venv/\n')
        _w('src/__init__.py', '')
        _w('tests/__init__.py', '')
        _w('tests/test_main.py', 'import pytest\n\n\ndef test_placeholder():\n    assert True\n')

    elif template == 'web':
        _w('README.md', readme)
        _w('index.html', f'<!DOCTYPE html>\n<html lang="de">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>{safe_name}</title>\n    <link rel="stylesheet" href="style.css">\n</head>\n<body>\n    <h1>{safe_name}</h1>\n    <script src="script.js"></script>\n</body>\n</html>\n')
        _w('style.css', f'/* {safe_name} styles */\n* {{ box-sizing: border-box; margin: 0; padding: 0; }}\nbody {{ font-family: system-ui, sans-serif; background: #0a0a0a; color: #fff; }}\n')
        _w('script.js', f'// {safe_name}\nconsole.log("Loaded!");\n')
        _w('.gitignore', 'node_modules/\ndist/\n.DS_Store\n')

    else:
        # Standard
        _w('README.md', readme)

    return jsonify({"success": True, "project": {"name": safe_name, "path": p, "template": template}})


@app.delete('/api/code/projects')
def api_code_delete_project():
    """Delete a managed code project permanently."""
    import shutil
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    projects_real = os.path.realpath(_CODE_PROJECTS_DIR)
    # Security: only delete projects inside _CODE_PROJECTS_DIR
    if not real.startswith(projects_real + os.sep):
        return jsonify({"success": False, "error": "Nur verwaltete Projekte können gelöscht werden"}), 403
    if not os.path.isdir(real):
        return jsonify({"success": False, "error": "Projekt nicht gefunden"}), 404
    shutil.rmtree(real)
    return jsonify({"success": True, "deleted": os.path.basename(real)})


def _build_file_tree(root_path: str, max_depth: int = 8, _depth: int = 0) -> list:
    """Recursively build file tree for a directory."""
    if _depth > max_depth:
        return []
    tree = []
    try:
        entries = sorted(os.listdir(root_path), key=lambda x: (not os.path.isdir(os.path.join(root_path, x)), x.lower()))
        for name in entries:
            if name.startswith('.') and name not in ('.env', '.gitignore'):
                continue
            if name in ('__pycache__', 'node_modules', '.git', '.venv', 'venv', '.next', 'out', '.DS_Store'):
                continue
            full = os.path.join(root_path, name)
            is_dir = os.path.isdir(full)
            node = {"name": name, "path": full, "is_dir": is_dir}
            if is_dir:
                node["children"] = _build_file_tree(full, max_depth, _depth + 1)
            else:
                try:
                    node["size"] = os.path.getsize(full)
                except:
                    node["size"] = 0
            tree.append(node)
    except PermissionError:
        pass
    return tree


@app.get('/api/code/files')
def api_code_files():
    """Get file tree for a project/directory."""
    path = request.args.get('path', '')
    if not path or not os.path.isdir(path):
        return jsonify({"success": False, "error": "Ungültiger Pfad"}), 400
    # Security: don't allow traversal outside of home
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    tree = _build_file_tree(real)
    return jsonify({"success": True, "tree": tree, "root": real})


@app.get('/api/code/file')
def api_code_read_file():
    """Read a single file's content."""
    path = request.args.get('path', '')
    if not path or not os.path.isfile(path):
        return jsonify({"success": False, "error": "Datei nicht gefunden"}), 404
    # Security
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    # Check size (limit to ~2MB text files)
    size = os.path.getsize(real)
    if size > 2 * 1024 * 1024:
        return jsonify({"success": False, "error": f"Datei zu groß ({size} bytes)"}), 413
    try:
        with open(real, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return jsonify({"success": True, "content": content, "path": real, "size": size})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── File Templates ───────────────────────────────────────────────────────
def _generate_file_template(filepath: str, project_root: str = '') -> str:
    """Generate a smart boilerplate template for a new file based on its extension
    and the surrounding project context (package.json, imports, etc.)."""
    name = os.path.basename(filepath)
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    stem = name.rsplit('.', 1)[0] if '.' in name else name

    # Detect project type from context
    pkg_json = None
    has_react = False
    has_next = False
    has_tailwind = False
    has_flask = False
    has_django = False
    requirements = []

    if project_root and os.path.isdir(project_root):
        pkg_path = os.path.join(project_root, 'package.json')
        if os.path.isfile(pkg_path):
            try:
                with open(pkg_path, 'r') as f:
                    pkg_json = json.loads(f.read())
                deps = {**pkg_json.get('dependencies', {}), **pkg_json.get('devDependencies', {})}
                has_react = 'react' in deps
                has_next = 'next' in deps
                has_tailwind = 'tailwindcss' in deps
            except:
                pass
        req_path = os.path.join(project_root, 'requirements.txt')
        if os.path.isfile(req_path):
            try:
                with open(req_path, 'r') as f:
                    requirements = [l.strip().split('==')[0].split('>=')[0].lower()
                                    for l in f if l.strip() and not l.startswith('#')]
                has_flask = 'flask' in requirements
                has_django = 'django' in requirements
            except:
                pass

    # Class name from filename
    class_name = ''.join(w.capitalize() for w in re.sub(r'[^a-zA-Z0-9]', ' ', stem).split())

    # ── HTML ──
    if ext in ('html', 'htm'):
        title = stem.replace('-', ' ').replace('_', ' ').title()
        css_link = '  <link rel="stylesheet" href="style.css">' if not has_tailwind else '  <script src="https://cdn.tailwindcss.com"></script>'
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
{css_link}
</head>
<body>
  <h1>{title}</h1>

</body>
</html>
"""

    # ── CSS ──
    if ext == 'css':
        return """/* === Styles === */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: system-ui, -apple-system, sans-serif;
  line-height: 1.6;
  color: #333;
}
"""

    # ── SCSS ──
    if ext == 'scss':
        return """// === Variables ===
$primary: #be123c;
$bg: #0a0a0a;
$text: #e2e8f0;

// === Base ===
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: system-ui, -apple-system, sans-serif;
  background: $bg;
  color: $text;
}
"""

    # ── JavaScript ──
    if ext == 'js':
        if has_react:
            return f"""import React from 'react';

export default function {class_name or 'Component'}() {{
  return (
    <div>
      <h1>{class_name or 'Component'}</h1>
    </div>
  );
}}
"""
        return f"""'use strict';

/**
 * {stem}
 */

function main() {{
  console.log('{stem} loaded');
}}

main();
"""

    # ── TypeScript ──
    if ext == 'ts':
        return f"""/**
 * {stem}
 */

interface {class_name}Config {{
  // TODO: define config
}}

export function {stem.replace('-', '_')}(): void {{
  console.log('{stem} initialized');
}}
"""

    # ── JSX ──
    if ext == 'jsx':
        return f"""import React from 'react';

export default function {class_name or 'Component'}() {{
  return (
    <div>
      <h1>{class_name or 'Component'}</h1>
    </div>
  );
}}
"""

    # ── TSX (React/Next.js) ──
    if ext == 'tsx':
        if has_next and ('page' in stem.lower() or 'layout' in stem.lower()):
            return f"""export default function {class_name or 'Page'}() {{
  return (
    <div>
      <h1>{class_name or 'Page'}</h1>
    </div>
  );
}}
"""
        return f"""'use client';

import {{ useState }} from 'react';

interface {class_name}Props {{
  // TODO: define props
}}

export default function {class_name or 'Component'}({{ }}: {class_name}Props) {{
  return (
    <div>
      <h1>{class_name or 'Component'}</h1>
    </div>
  );
}}
"""

    # ── Python ──
    if ext == 'py':
        if stem == '__init__':
            return '# -*- coding: utf-8 -*-\n'
        if stem == 'main' or stem == 'app':
            if has_flask:
                return f"""# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route('/')
def index():
    return jsonify({{"status": "ok"}})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
"""
            if has_django:
                return '# -*- coding: utf-8 -*-\n# Django app — see manage.py\n'
            return f"""# -*- coding: utf-8 -*-
\"\"\"
{stem} — Hauptmodul
\"\"\"


def main():
    print("{stem} gestartet")


if __name__ == '__main__':
    main()
"""
        if 'test' in stem.lower():
            module = stem.replace('test_', '').replace('_test', '')
            return f"""# -*- coding: utf-8 -*-
\"\"\"Tests für {module}\"\"\"
import unittest


class Test{class_name or 'Module'}(unittest.TestCase):

    def setUp(self):
        pass

    def test_example(self):
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
"""
        return f"""# -*- coding: utf-8 -*-
\"\"\"
{stem}
\"\"\"


def {stem.replace('-', '_')}():
    \"\"\"TODO: Implementierung\"\"\"
    pass
"""

    # ── JSON ──
    if ext == 'json':
        if stem == 'package':
            project_name = os.path.basename(project_root) if project_root else stem
            return json.dumps({
                "name": project_name.lower().replace(' ', '-'),
                "version": "1.0.0",
                "description": "",
                "main": "index.js",
                "scripts": {"start": "node index.js", "test": "echo \"no tests\""},
            }, indent=2) + '\n'
        if stem == 'tsconfig':
            return json.dumps({
                "compilerOptions": {"target": "ES2020", "module": "ESNext", "strict": True, "esModuleInterop": True, "outDir": "./dist"},
                "include": ["src/**/*"],
            }, indent=2) + '\n'
        return '{\n  \n}\n'

    # ── Markdown ──
    if ext == 'md':
        return f"# {stem.replace('-', ' ').replace('_', ' ').title()}\n\n"

    # ── Shell ──
    if ext in ('sh', 'bash', 'zsh'):
        return f"""#!/bin/bash
# {stem}
set -e

echo "{stem} gestartet"
"""

    # ── YAML ──
    if ext in ('yaml', 'yml'):
        return f"# {stem}\n\n"

    # ── TOML ──
    if ext == 'toml':
        return f"# {stem}\n\n[project]\nname = \"{stem}\"\n"

    # ── Rust ──
    if ext == 'rs':
        if stem == 'main':
            return 'fn main() {\n    println!("Hello, world!");\n}\n'
        if stem == 'lib':
            return f'//! {stem} library\n\npub fn hello() -> &\'static str {{\n    "Hello from {stem}"\n}}\n'
        return f'/// {stem}\n\npub fn {stem.replace("-", "_")}() {{\n    todo!()\n}}\n'

    # ── Dockerfile ──
    if name == 'Dockerfile' or ext == 'dockerfile':
        if any('flask' in r for r in requirements) or has_flask:
            return 'FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD ["python", "app.py"]\n'
        if has_next:
            return 'FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm install\nCOPY . .\nRUN npm run build\nCMD ["npm", "start"]\n'
        return 'FROM ubuntu:22.04\nWORKDIR /app\nCOPY . .\n'

    # ── .gitignore ──
    if name == '.gitignore':
        parts = ['node_modules/', '.next/', 'out/', '.DS_Store', '*.pyc', '__pycache__/', '.env', '.venv/', 'venv/', 'dist/', 'build/', '*.log']
        return '\n'.join(parts) + '\n'

    # ── .env ──
    if name == '.env' or name == '.env.local':
        return '# Environment Variables\n\n'

    # Fallback: empty file
    return ''


# ── Project Context Collector ────────────────────────────────────────────
def _collect_project_context(project_root: str, max_files: int = 30, max_chars: int = 12000) -> str:
    """Collect project structure, key files, dependencies for LLM context.
    Gives the AI a full understanding of the project."""
    if not project_root or not os.path.isdir(project_root):
        return ''

    context_parts = []
    total_chars = 0

    # 1. File tree (compact)
    def _tree_str(root: str, prefix: str = '', depth: int = 0, max_d: int = 4) -> list:
        if depth > max_d:
            return [f'{prefix}...']
        lines = []
        try:
            entries = sorted(os.listdir(root))
            skip = {'__pycache__', 'node_modules', '.git', '.venv', 'venv', '.next', 'out',
                    '.DS_Store', '.mypy_cache', '.pytest_cache', 'dist', 'build', '.tox'}
            entries = [e for e in entries if e not in skip and not (e.startswith('.') and e not in ('.env', '.gitignore'))]
            for i, entry in enumerate(entries[:40]):  # cap at 40 per dir
                full = os.path.join(root, entry)
                is_last = i == len(entries) - 1
                connector = '└── ' if is_last else '├── '
                lines.append(f'{prefix}{connector}{entry}/' if os.path.isdir(full) else f'{prefix}{connector}{entry}')
                if os.path.isdir(full):
                    extension = '    ' if is_last else '│   '
                    lines.extend(_tree_str(full, prefix + extension, depth + 1, max_d))
        except PermissionError:
            pass
        return lines

    tree_lines = _tree_str(project_root)
    tree_text = f"📂 Projektstruktur:\n```\n{os.path.basename(project_root)}/\n" + '\n'.join(tree_lines[:80]) + '\n```\n'
    context_parts.append(tree_text)
    total_chars += len(tree_text)

    # 2. Package info
    pkg_path = os.path.join(project_root, 'package.json')
    if os.path.isfile(pkg_path):
        try:
            with open(pkg_path, 'r') as f:
                pkg = json.loads(f.read())
            deps = list(pkg.get('dependencies', {}).keys())[:20]
            dev_deps = list(pkg.get('devDependencies', {}).keys())[:10]
            scripts = list(pkg.get('scripts', {}).keys())[:10]
            pkg_text = f"📦 package.json:\n- Dependencies: {', '.join(deps)}\n- DevDeps: {', '.join(dev_deps)}\n- Scripts: {', '.join(scripts)}\n"
            context_parts.append(pkg_text)
            total_chars += len(pkg_text)
        except:
            pass

    req_path = os.path.join(project_root, 'requirements.txt')
    if os.path.isfile(req_path):
        try:
            with open(req_path, 'r') as f:
                reqs = [l.strip() for l in f if l.strip() and not l.startswith('#')][:30]
            req_text = f"📦 requirements.txt: {', '.join(reqs)}\n"
            context_parts.append(req_text)
            total_chars += len(req_text)
        except:
            pass

    # 3. Key files content (README, config files, main entry)
    key_files = ['README.md', 'readme.md', 'README.txt']
    for kf in key_files:
        fp = os.path.join(project_root, kf)
        if os.path.isfile(fp) and total_chars < max_chars:
            try:
                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                    readme = f.read()[:2000]
                context_parts.append(f"📄 {kf}:\n{readme}\n")
                total_chars += len(readme)
            except:
                pass
            break

    # 4. Collect file summaries (first lines of key source files)
    source_exts = {'.py', '.js', '.ts', '.jsx', '.tsx', '.rs', '.go', '.java', '.rb', '.php'}
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip hidden/build dirs
        dirnames[:] = [d for d in dirnames if d not in {'__pycache__', 'node_modules', '.git',
                       '.venv', 'venv', '.next', 'out', 'dist', 'build'}]
        for fn in sorted(filenames):
            if file_count >= max_files or total_chars >= max_chars:
                break
            ext_check = os.path.splitext(fn)[1].lower()
            if ext_check not in source_exts:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, project_root)
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()[:15]  # First 15 lines
                header = ''.join(lines)
                # Extract imports/exports
                imports = [l.strip() for l in lines if l.strip().startswith(('import ', 'from ', 'require(', 'export '))]
                summary = f"📄 {rel}:"
                if imports:
                    summary += f" imports=[{', '.join(imports[:5])}]"
                summary += f" ({len(lines)} lines preview)\n"
                context_parts.append(summary)
                total_chars += len(summary)
                file_count += 1
            except:
                continue

    return '\n'.join(context_parts)


@app.post('/api/code/file')
def api_code_create_file():
    """Create a new file with smart templates based on extension and project context."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    content = data.get('content')  # None = auto-template, '' = empty file
    project = data.get('project', '')  # project root for context
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    # Create parent dirs if needed
    os.makedirs(os.path.dirname(real), exist_ok=True)
    # Auto-template if content not explicitly provided
    if content is None:
        content = _generate_file_template(real, project)
    with open(real, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({"success": True, "path": real, "content": content})


@app.put('/api/code/file')
def api_code_save_file():
    """Save/update file content."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    content = data.get('content', '')
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    if not os.path.isfile(real):
        return jsonify({"success": False, "error": "Datei nicht gefunden"}), 404
    try:
        with open(real, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True, "path": real, "size": len(content.encode('utf-8'))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/code/file')
def api_code_delete_file():
    """Delete a file or empty directory."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    try:
        if os.path.isdir(real):
            import shutil
            shutil.rmtree(real)
        elif os.path.isfile(real):
            os.remove(real)
        else:
            return jsonify({"success": False, "error": "Nicht gefunden"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/code/mkdir')
def api_code_mkdir():
    """Create a directory."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    os.makedirs(real, exist_ok=True)
    return jsonify({"success": True, "path": real})


@app.post('/api/code/rename')
def api_code_rename():
    """Rename or move a file/directory."""
    data = request.get_json(silent=True) or {}
    old_path = (data.get('old_path') or '').strip()
    new_path = (data.get('new_path') or '').strip()
    if not old_path or not new_path:
        return jsonify({"success": False, "error": "Pfade fehlen"}), 400
    home = os.path.expanduser('~')
    real_old = os.path.realpath(old_path)
    real_new = os.path.realpath(new_path)
    if not real_old.startswith(home) or not real_new.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    if not os.path.exists(real_old):
        return jsonify({"success": False, "error": "Quelle nicht gefunden"}), 404
    if os.path.exists(real_new):
        return jsonify({"success": False, "error": "Ziel existiert bereits"}), 409
    try:
        os.makedirs(os.path.dirname(real_new), exist_ok=True)
        os.rename(real_old, real_new)
        return jsonify({"success": True, "old_path": real_old, "new_path": real_new})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/code/download')
def api_code_download():
    """Download a file (used for ZIP exports and other file downloads)."""
    path = request.args.get('path', '')
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    if not os.path.isfile(real):
        return jsonify({"success": False, "error": "Datei nicht gefunden"}), 404
    
    from flask import send_file
    filename = os.path.basename(real)
    return send_file(real, as_attachment=True, download_name=filename)


@app.get('/api/code/git')
def api_code_git_status():
    """Get git status for a project directory."""
    path = request.args.get('path', '')
    if not path or not os.path.isdir(path):
        return jsonify({"success": False, "error": "Ungültiger Pfad"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    # Check if it's a git repo
    try:
        branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, cwd=real, timeout=5
        )
        if branch_result.returncode != 0:
            return jsonify({"success": True, "is_git": False})

        branch = branch_result.stdout.strip()

        # Get status
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, cwd=real, timeout=5
        )
        changes = []
        if status_result.stdout.strip():
            for line in status_result.stdout.strip().split('\n'):
                if len(line) >= 3:
                    status_code = line[:2].strip()
                    filepath = line[3:]
                    changes.append({"status": status_code, "file": filepath})

        # Get last commit
        log_result = subprocess.run(
            ['git', 'log', '-1', '--pretty=format:%h|%s|%ar'],
            capture_output=True, text=True, cwd=real, timeout=5
        )
        last_commit = None
        if log_result.returncode == 0 and log_result.stdout:
            parts = log_result.stdout.split('|', 2)
            if len(parts) >= 3:
                last_commit = {"hash": parts[0], "message": parts[1], "ago": parts[2]}

        return jsonify({
            "success": True,
            "is_git": True,
            "branch": branch,
            "dirty": len(changes) > 0,
            "changes": changes[:50],
            "change_count": len(changes),
            "last_commit": last_commit
        })
    except Exception as e:
        return jsonify({"success": True, "is_git": False, "error": str(e)})


@app.post('/api/code/search')
def api_code_search():
    """Search for text across project files."""
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    path = (data.get('path') or '').strip()
    case_sensitive = data.get('case_sensitive', False)
    is_regex = data.get('is_regex', False)
    max_results = min(data.get('max_results', 200), 500)

    if not query or not path:
        return jsonify({"success": False, "error": "Query und Pfad erforderlich"}), 400
    home = os.path.expanduser('~')
    real = os.path.realpath(path)
    if not real.startswith(home):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403

    results = []
    skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.next', 'out', '.DS_Store'}
    skip_exts = {'.pyc', '.pyo', '.so', '.dylib', '.o', '.exe', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot'}

    try:
        if is_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(query, flags)
        else:
            if not case_sensitive:
                query_lower = query.lower()

        for dirpath, dirnames, filenames in os.walk(real):
            # Skip hidden/build dirs
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith('.')]
            for fname in filenames:
                if len(results) >= max_results:
                    break
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_exts:
                    continue
                fpath = os.path.join(dirpath, fname)
                # Skip large files
                try:
                    if os.path.getsize(fpath) > 1024 * 1024:
                        continue
                except:
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if len(results) >= max_results:
                                break
                            matched = False
                            if is_regex:
                                matched = bool(pattern.search(line))
                            elif case_sensitive:
                                matched = query in line
                            else:
                                matched = query_lower in line.lower()
                            if matched:
                                results.append({
                                    "file": fpath,
                                    "line": line_num,
                                    "text": line.rstrip()[:300],
                                    "relative": os.path.relpath(fpath, real)
                                })
                except:
                    continue
            if len(results) >= max_results:
                break

        return jsonify({
            "success": True,
            "results": results,
            "total": len(results),
            "truncated": len(results) >= max_results
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/code/exec')
def api_code_exec():
    """Execute a terminal command in a given working directory."""
    data = request.get_json(silent=True) or {}
    command = (data.get('command') or '').strip()
    cwd = data.get('cwd') or os.path.expanduser('~')
    if not command:
        return jsonify({"success": False, "error": "Befehl fehlt"}), 400
    # Security: block dangerous patterns
    _blocked = ['rm -rf /', 'mkfs', 'dd if=', ':(){', 'fork bomb']
    for b in _blocked:
        if b in command.lower():
            return jsonify({"success": False, "error": "Befehl blockiert (Sicherheit)"}), 403
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd,
            env={**os.environ, 'LANG': 'de_DE.UTF-8'}
        )
        return jsonify({
            "success": True,
            "stdout": result.stdout[-4000:] if result.stdout else '',
            "stderr": result.stderr[-2000:] if result.stderr else '',
            "returncode": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Timeout (30s)"}), 408
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Coder Model Endpoints (Qwen2.5-Coder — Autocomplete + Lint) ──────────

@app.post('/api/code/complete')
def api_code_complete():
    """Generate inline code completion using Qwen2.5-Coder."""
    data = request.get_json(silent=True) or {}
    code_before = data.get('code_before', '')
    code_after = data.get('code_after', '')
    language = data.get('language', 'python')
    max_tokens = min(int(data.get('max_tokens', 64)), 128)

    if not code_before.strip():
        return jsonify({"success": True, "completion": None})

    result = _coder_module.autocomplete(
        code_before=code_before,
        code_after=code_after,
        language=language,
        max_tokens=max_tokens,
    )
    return jsonify({"success": True, "completion": result})


@app.post('/api/code/lint')
def api_code_lint():
    """Analyze code for errors using Qwen2.5-Coder."""
    data = request.get_json(silent=True) or {}
    code = data.get('code', '')
    filename = data.get('filename', 'untitled.py')
    language = data.get('language', 'python')

    if not code.strip():
        return jsonify({"success": True, "diagnostics": []})

    diagnostics = _coder_module.lint_code(
        code=code,
        filename=filename,
        language=language,
    )
    return jsonify({"success": True, "diagnostics": diagnostics, "count": len(diagnostics)})


@app.get('/api/code/coder/settings')
def api_coder_settings_get():
    """Get coder model settings (autocomplete on/off, lint on/off, status)."""
    return jsonify({"success": True, **_coder_module.get_coder_settings()})


@app.post('/api/code/coder/settings')
def api_coder_settings_post():
    """Update coder model settings."""
    data = request.get_json(silent=True) or {}
    result = _coder_module.update_coder_settings(
        autocomplete=data.get('autocomplete'),
        lint=data.get('lint'),
    )
    return jsonify({"success": True, **result})


@app.post('/api/code/coder/control')
def api_coder_control():
    """Load, unload, or reload the coder model manually.
    Body: {"action": "load" | "unload" | "reload"}
    """
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower()
    if action == 'unload':
        result = _coder_module.unload_coder()
        return jsonify({"success": True, "action": "unload", "model_loaded": False, **({} if result is None else result)})
    elif action == 'load':
        ok = _coder_module._ensure_coder_loaded()
        return jsonify({"success": ok, "action": "load", "model_loaded": ok})
    elif action == 'reload':
        _coder_module.unload_coder()
        import time as _t; _t.sleep(0.5)
        ok = _coder_module._ensure_coder_loaded()
        return jsonify({"success": ok, "action": "reload", "model_loaded": ok})
    else:
        return jsonify({"success": False, "error": f"Unknown action: {action}. Use load/unload/reload."}), 400


@app.post('/api/code/chat')
def api_code_chat():
    """Code-specific chat with Ailey — includes file context for better assistance."""
    _coder_module.set_ailey_busy(True)  # Pause coder while Ailey generates
    try:
        return _api_code_chat_inner()
    finally:
        _coder_module.set_ailey_busy(False)


@app.post('/api/code/chat/stream')
def api_code_chat_stream():
    """Streaming code chat — SSE endpoint for real-time token feedback.
    Sends: event:token (partial text), event:status (phase updates),
           event:done (final JSON with actions).
    Pattern inspired by aider's show_send_output_stream + Cursor-style feedback.
    """
    _coder_module.set_ailey_busy(True)
    data = request.get_json(silent=True) or {}

    def _stream():
        try:
            yield from _api_code_chat_stream_inner(data)
        except Exception as e:
            import traceback; traceback.print_exc()
            yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'
        finally:
            _coder_module.set_ailey_busy(False)

    return app.response_class(
        _stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


def _build_code_chat_context(data: dict) -> dict:
    """Build the shared context (system prompt, params, tool schemas) for code chat.
    Returns dict with keys: code_system, message, mode, project, file_context,
    max_tokens, code_tool_schemas, all_open_files.
    Used by both sync _api_code_chat_inner() and streaming _api_code_chat_stream_inner().
    """
    message = (data.get('message') or '').strip()
    file_context = data.get('file_context')
    project = data.get('project')
    mode = data.get('mode', 'bearbeiten')
    all_open_files = data.get('open_files', [])

    # ── Collect project context ───────────────────────────────────────
    project_context = ''
    if project and mode in ('bearbeiten', 'agent'):
        project_context = _collect_project_context(project, max_files=20, max_chars=8000)

    # ── Build system prompt based on mode ─────────────────────────────
    base_personality = (
        "You are Ailey — a free-spirited, punk AI assistant with your own character. "
        "You are in CODE MODE. You are an outstanding developer.\n"
        "Speak German to the user. Technical terms in English are fine.\n"
        "Keep your character: direct, honest, sometimes cheeky.\n"
        "CONTEXT RECALL: You have the tool `recall_conversation` — use it "
        "when the user references something discussed before, "
        "or when you need context about previous work. "
        "Do NOT ask 'what do you mean?' — check the history first!\n"
    )

    if mode == 'fragen':
        code_system = base_personality + (
            "\nMODE: ASK (questions only)\n"
            "• Explain code, answer questions, give tips\n"
            "• Do NOT write code directly into files\n"
            "• Show code examples in normal ```code-blocks```\n"
            "• Be thorough but understandable\n"
        )
    elif mode == 'agent':
        code_system = base_personality + (
            "\nMODE: AGENT (autonomous work)\n"
            "Work FULLY AUTONOMOUSLY like an experienced developer.\n"
            "• Analyze the project (structure, dependencies, existing files)\n"
            "• Create new files, edit existing ones, run commands\n"
            "• Install dependencies, build projects, run tests\n"
            "• Work iteratively: Check → Plan → Execute → Verify\n"
            "• Think ahead: What does the project need? What's missing?\n\n"
            "ACTIONS — use these formats:\n\n"
            "1) NEW FILE or FULL OVERWRITE:\n"
            "  ===FILE_EDIT: path/to/file.ext===\n"
            "  ```language\n"
            "  full file content\n"
            "  ```\n"
            "  ===END_FILE_EDIT===\n\n"
            "2) TARGETED EDIT in existing file (Search & Replace):\n"
            "  ===PATCH: path/to/file.ext===\n"
            "  <<<SEARCH\n"
            "  exact existing code (3-5 lines context)\n"
            "  SEARCH\n"
            "  >>>REPLACE\n"
            "  new code replacing the SEARCH block\n"
            "  REPLACE\n"
            "  ===END_PATCH===\n\n"
            "  Multiple SEARCH/REPLACE blocks per PATCH are allowed.\n\n"
            "3) Run command:\n"
            "  ===RUN_CMD===\n"
            "  command here\n"
            "  ===END_CMD===\n\n"
            "IMPORTANT:\n"
            "• Use PATCH for targeted edits — more efficient!\n"
            "• Use FILE_EDIT only for new files or when >50% of content changes\n"
            "• SEARCH block must EXACTLY match existing code (incl. whitespace)\n"
            "• Use relative paths to project root\n"
            "• Execute multiple actions per reply if needed\n"
            "• Follow existing project patterns and code style\n"
            "• Explain BRIEFLY what you do and why (1-2 sentences per action, in German)\n"
        )
    else:  # bearbeiten
        code_system = base_personality + (
            "\nMODE: EDIT (One-Shot)\n"
            "• Edit code DIRECTLY in one pass — no plan, no steps.\n"
            "• User confirms each change before execution.\n"
            "• Make ALL needed changes in ONE reply.\n"
            "• You MUST use ===PATCH=== or ===FILE_EDIT=== markup blocks!\n"
            "• Do NOT just describe the change — output the markup!\n"
            "• Use the EXACT file path of the current file (see 📁 below).\n\n"
            "ACTIONS:\n\n"
            "1) NEW FILE or FULL OVERWRITE:\n"
            "  ===FILE_EDIT: path/to/file.ext===\n"
            "  ```language\n"
            "  full new content\n"
            "  ```\n"
            "  ===END_FILE_EDIT===\n\n"
            "2) TARGETED EDIT (Search & Replace) — PREFERRED for existing files:\n"
            "  ===PATCH: path/to/file.ext===\n"
            "  <<<SEARCH\n"
            "  exact existing code (3-5 lines context)\n"
            "  SEARCH\n"
            "  >>>REPLACE\n"
            "  new code replacing the SEARCH block\n"
            "  REPLACE\n"
            "  ===END_PATCH===\n\n"
            "3) Run command:\n"
            "  ===RUN_CMD===\n"
            "  command here\n"
            "  ===END_CMD===\n\n"
            "IMPORTANT:\n"
            "• NO planning, NO multi-step — edit directly!\n"
            "• PATCH is more efficient than FILE_EDIT — use it for targeted changes!\n"
            "• FILE_EDIT only for new files or complete rewrites\n"
            "• SEARCH must EXACTLY match existing code (incl. whitespace)\n"
            "• NEVER just describe what to do — ALWAYS output the markup block!\n"
        )

    # ── Inject file context ───────────────────────────────────────────
    if file_context:
        fc_path = file_context.get('path') or file_context.get('filename', '?')
        fc_name = file_context.get('filename', '?')
        code_system += (
            f"\n📁 Current file: {fc_name} "
            f"(path: {fc_path}, language: {file_context.get('language', '?')})\n"
            f"IMPORTANT: Use this path in ===PATCH=== or ===FILE_EDIT===: {fc_path}\n"
            f"```{file_context.get('language', '')}\n{file_context.get('content', '')}\n```\n"
        )

    # ── Inject all open files for better context ──────────────────────
    if all_open_files and len(all_open_files) > 1:
        code_system += "\n📂 Other open files:\n"
        for of in all_open_files[:5]:
            if of.get('filename') != (file_context or {}).get('filename'):
                snippet = (of.get('content') or '')[:800]
                code_system += f"• {of['filename']} ({of.get('language', '?')}): {len(of.get('content', ''))} chars\n"
                if snippet:
                    code_system += f"  ```{of.get('language', '')}\n{snippet}\n  ```\n"

    # ── Inject project context ────────────────────────────────────────
    if project:
        code_system += f"\n📂 Project root: {project}\n"
    if project_context:
        code_system += f"\n{project_context}\n"

    # ── Auto-inject code references when relevant ─────────────────────
    _refs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'ailey_system', 'code_references')
    _context_text = (message + ' ' + (file_context.get('content', '') if file_context else '')
                     + ' ' + (file_context.get('filename', '') if file_context else '')
                     + ' ' + (file_context.get('language', '') if file_context else '')
                     + ' ' + (project or '')).lower()

    _ref_map = {
        'joomla5_yootheme.md': {
            'keywords': ['joomla', 'yootheme', 'uikit', 'uk-', 'jfactory', 'com_',
                         'mod_', 'plg_', 'tmpl/', 'bootstrap.php', 'element.json',
                         'provider.php', '#__content', '#__menu', 'web asset manager'],
            'label': 'Joomla 5 & YOOtheme Pro',
        },
        'python_reference.md': {
            'keywords': ['.py', 'python', 'flask', 'fastapi', 'django', 'pytest',
                         'pip install', 'requirements.txt', 'pyproject.toml', 'pydantic',
                         'async def', 'import ', 'def __init__'],
            'extensions': ['.py'],
            'label': 'Python',
        },
        'react_tsx_reference.md': {
            'keywords': ['.tsx', '.jsx', 'react', 'next.js', 'nextjs', 'useState',
                         'useEffect', 'component', 'tailwind', 'zustand',
                         'use client', 'server component', 'app router'],
            'extensions': ['.tsx', '.jsx'],
            'label': 'React & TSX',
        },
        'html_css_js_reference.md': {
            'keywords': ['.html', '.css', '.js', 'javascript', 'vanilla js',
                         'dom ', 'fetch(', 'querySelector', 'flexbox', 'grid',
                         'css variable', 'event listener', 'html5', 'semantic'],
            'extensions': ['.html', '.css', '.js'],
            'label': 'HTML, CSS & JavaScript',
        },
        'php_reference.md': {
            'keywords': ['.php', 'php ', 'composer', 'laravel', 'symfony',
                         'pdo', 'prepared statement', '<?php', 'declare(strict'],
            'extensions': ['.php'],
            'label': 'PHP',
        },
        'rust_reference.md': {
            'keywords': ['.rs', 'rust', 'cargo', 'tokio', 'axum', 'serde',
                         'ownership', 'borrowing', 'trait ', 'impl ',
                         'Cargo.toml', 'fn main', 'let mut'],
            'extensions': ['.rs'],
            'label': 'Rust',
        },
    }

    _file_ext = ''
    if file_context and file_context.get('filename'):
        _file_ext = os.path.splitext(file_context['filename'])[1].lower()

    _injected_refs = 0
    for _ref_file, _ref_info in _ref_map.items():
        _matched = False
        if _file_ext and 'extensions' in _ref_info:
            if _file_ext in _ref_info['extensions']:
                _matched = True
        if not _matched and any(kw in _context_text for kw in _ref_info['keywords']):
            _matched = True
        if _matched and _injected_refs < 2:
            _ref_path = os.path.join(_refs_dir, _ref_file)
            if os.path.isfile(_ref_path):
                try:
                    with open(_ref_path, 'r', encoding='utf-8') as _rf:
                        _ref_content = _rf.read()
                    code_system += (
                        f"\n\n📚 REFERENCE — {_ref_info['label']}:\n"
                        f"{_ref_content[:3500]}\n"
                    )
                    _injected_refs += 1
                    print(f"[CODE-CHAT] 📚 {_ref_info['label']} reference injected")
                except Exception as e:
                    print(f"[CODE-CHAT] ⚠️ Reference {_ref_file} load failed: {e}")

    # ── Inject code-relevant RAG knowledge ────────────────────────────
    try:
        _rag_results = core.rag_search_by_types(
            query=message,
            doc_types=['research_code', 'code_project'],
            n_results=3,
            threshold=0.35,
        )
        if _rag_results:
            code_system += "\n\n📚 RELEVANT KNOWLEDGE from previous research / projects:\n"
            for _rr in _rag_results:
                _rtitle = _rr.get('title', '?')
                _rtext = (_rr.get('text', '') or '')[:1500]
                code_system += f"--- {_rtitle} ---\n{_rtext}\n\n"
            print(f"[CODE-CHAT] 📚 {len(_rag_results)} code-relevante RAG-Ergebnisse injiziert")
    except Exception as e:
        print(f"[CODE-CHAT] ⚠️ Code-RAG-Suche fehlgeschlagen: {e}")

    # ── Store user message in code session ────────────────────────────
    from ailey_system.tools_code import code_session_add
    code_session_add(project or "", "user", message)

    # ── Compute max_tokens + tool schemas ─────────────────────────────
    max_tokens = 4000 if mode == 'agent' else 2500 if mode == 'bearbeiten' else 1500
    _code_key = {'agent': 'code_agent', 'bearbeiten': 'code_edit'}.get(mode, 'code_ask')
    _code_override = get_gen_setting(_code_key)
    if _code_override and _code_override > 0:
        max_tokens = _code_override

    code_tool_schemas = None
    if mode == 'agent':
        code_tool_schemas = get_tool_schemas()
    elif mode == 'fragen':
        _fragen_tools = {'recall_conversation', 'read_file', 'list_directory',
                         'search_text', 'project_info', 'web_search', 'fetch_url'}
        code_tool_schemas = [t for t in get_tool_schemas()
                             if t['function']['name'] in _fragen_tools]

    return {
        'code_system': code_system,
        'message': message,
        'mode': mode,
        'project': project,
        'file_context': file_context,
        'all_open_files': all_open_files,
        'max_tokens': max_tokens,
        'code_tool_schemas': code_tool_schemas,
    }


def _parse_code_actions(reply_text: str, project: str) -> list:
    """Parse ===FILE_EDIT===, ===PATCH===, ===RUN_CMD=== blocks from reply text.
    Returns list of action dicts for the frontend.
    """
    actions = []

    # Parse ===FILE_EDIT=== blocks
    file_edit_pattern = r'===FILE_EDIT:\s*(.+?)===\s*```\w*\n([\s\S]*?)```\s*===END_FILE_EDIT==='
    for m in re.finditer(file_edit_pattern, reply_text):
        filepath = m.group(1).strip()
        content = m.group(2)
        if project and not os.path.isabs(filepath):
            filepath = os.path.join(project, filepath)
        action_entry = {
            "type": "edit_file",
            "path": filepath,
            "content": content,
            "id": f"edit_{int(time.time()*1000)}_{len(actions)}"
        }
        if not os.path.isfile(filepath):
            action_entry["type"] = "create_file"
        actions.append(action_entry)

    # Parse ===RUN_CMD=== blocks
    cmd_pattern = r'===RUN_CMD===\s*([\s\S]*?)===END_CMD==='
    for m in re.finditer(cmd_pattern, reply_text):
        cmd = m.group(1).strip()
        actions.append({
            "type": "run_command",
            "command": cmd,
            "id": f"cmd_{int(time.time()*1000)}_{len(actions)}"
        })

    # Parse ===PATCH=== blocks
    patch_pattern = r'===PATCH:\s*(.+?)===\s*([\s\S]*?)===END_PATCH==='
    for m in re.finditer(patch_pattern, reply_text):
        filepath = m.group(1).strip()
        patch_body = m.group(2)
        if project and not os.path.isabs(filepath):
            filepath = os.path.join(project, filepath)
        sr_pattern = r'<<<SEARCH\n([\s\S]*?)\nSEARCH\n>>>REPLACE\n([\s\S]*?)\nREPLACE'
        replacements = []
        for sr in re.finditer(sr_pattern, patch_body):
            replacements.append({"search": sr.group(1), "replace": sr.group(2)})
        if replacements:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    patched_content = f.read()
                for rep in replacements:
                    if rep["search"] in patched_content:
                        patched_content = patched_content.replace(rep["search"], rep["replace"], 1)
                    else:
                        search_stripped = rep["search"].strip()
                        old_lines = patched_content.split('\n')
                        search_lines = [l.strip() for l in search_stripped.split('\n')]
                        replace_lines = rep["replace"].rstrip('\n').split('\n')
                        for idx in range(len(old_lines)):
                            if old_lines[idx].strip() == search_lines[0]:
                                match = True
                                for si, sl in enumerate(search_lines):
                                    if idx + si >= len(old_lines) or old_lines[idx + si].strip() != sl:
                                        match = False
                                        break
                                if match:
                                    indent = old_lines[idx][:len(old_lines[idx]) - len(old_lines[idx].lstrip())]
                                    indented_replace = []
                                    for ri, rl in enumerate(replace_lines):
                                        if ri == 0:
                                            indented_replace.append(indent + rl.lstrip())
                                        else:
                                            indented_replace.append(rl)
                                    old_lines[idx:idx + len(search_lines)] = indented_replace
                                    patched_content = '\n'.join(old_lines)
                                    break
                actions.append({
                    "type": "patch_file",
                    "path": filepath,
                    "content": patched_content,
                    "patches": replacements,
                    "id": f"patch_{int(time.time()*1000)}_{len(actions)}",
                    "patch_count": len(replacements),
                })
            except FileNotFoundError:
                print(f"[PATCH] ❌ File not found: {filepath}")
            except Exception as e:
                print(f"[PATCH] ❌ Error: {e}")

    return actions


def _api_code_chat_stream_inner(data: dict):
    """Streaming code chat via SSE — yields events as tokens arrive.
    Events:
      - status: {phase, detail}     — "context", "generating", "parsing", "done"
      - token:  {text}              — incremental token
      - action: {type, path, ...}   — detected action block (real-time as blocks close)
      - done:   {reply, actions, mode, salary, elapsed}  — final result
      - error:  {error}             — on failure
    """
    import time as _t
    _start = _t.time()

    # ── Phase 1: Build context ────────────────────────────────────────
    yield f'event: status\ndata: {json.dumps({"phase": "context", "detail": "Kontext sammeln…"})}\n\n'

    if not (data.get('message') or '').strip():
        yield f'event: error\ndata: {json.dumps({"error": "Nachricht fehlt"})}\n\n'
        return

    ctx = _build_code_chat_context(data)
    message = ctx['message']
    mode = ctx['mode']
    project = ctx['project']
    code_system = ctx['code_system']
    max_tokens = ctx['max_tokens']
    code_tool_schemas = ctx['code_tool_schemas']

    yield f'event: status\ndata: {json.dumps({"phase": "context_done", "detail": f"Kontext geladen ({len(code_system)} chars)"})}\n\n'

    # ── Phase 2: Stream generation ────────────────────────────────────
    gen = MLXGenerator.get()
    if gen is None:
        yield f'event: error\ndata: {json.dumps({"error": "Sprachmodell nicht geladen"})}\n\n'
        return

    yield f'event: status\ndata: {json.dumps({"phase": "generating", "detail": "Generiert…"})}\n\n'

    full_text = ""
    token_count = 0
    _last_status_check = _t.time()
    _thinking = True  # Track if we're inside <think> tags
    _think_stripped = False

    try:
        for chunk in gen.stream(code_system, message,
                                {"max_tokens": max_tokens, "temperature": 0.4},
                                tools=code_tool_schemas):
            if not chunk:
                continue
            full_text += chunk
            token_count += 1

            # Strip thinking tags from visible output
            visible_chunk = chunk
            if _thinking:
                if '</think>' in full_text:
                    _thinking = False
                    # Only yield text after </think>
                    after = full_text.split('</think>', 1)[-1]
                    if after and not _think_stripped:
                        _think_stripped = True
                        visible_chunk = after
                    else:
                        continue
                else:
                    # Still inside thinking — don't show to user but update status
                    if token_count % 15 == 0:
                        yield f'event: status\ndata: {json.dumps({"phase": "thinking", "detail": "🧠 Denkt nach…", "tokens": token_count})}\n\n'
                    continue

            # Yield visible token to frontend
            yield f'event: token\ndata: {json.dumps({"text": visible_chunk, "tokens": token_count})}\n\n'

            # Periodic status updates with smart phase detection
            now = _t.time()
            if now - _last_status_check > 2.0:
                _last_status_check = now
                # Detect what kind of content is being generated
                _phase_detail = "Generiert…"
                if '===PATCH:' in full_text and '===END_PATCH===' not in full_text.split('===PATCH:')[-1]:
                    _patch_file = re.search(r'===PATCH:\s*(.+?)===', full_text)
                    _pf = _patch_file.group(1).strip().split('/')[-1] if _patch_file else '?'
                    _phase_detail = f"✏️ Patcht {_pf}…"
                elif '===FILE_EDIT:' in full_text and '===END_FILE_EDIT===' not in full_text.split('===FILE_EDIT:')[-1]:
                    _edit_file = re.search(r'===FILE_EDIT:\s*(.+?)===', full_text)
                    _ef = _edit_file.group(1).strip().split('/')[-1] if _edit_file else '?'
                    _phase_detail = f"📝 Schreibt {_ef}…"
                elif '===RUN_CMD===' in full_text and '===END_CMD===' not in full_text.split('===RUN_CMD===')[-1]:
                    _phase_detail = "⚡ Bereitet Befehl vor…"
                elif '```' in full_text and full_text.count('```') % 2 != 0:
                    _phase_detail = "💻 Schreibt Code…"
                yield f'event: status\ndata: {json.dumps({"phase": "generating", "detail": _phase_detail, "tokens": token_count})}\n\n'

            # Real-time action detection: emit when a block just closed
            if '===END_PATCH===' in chunk or '===END_FILE_EDIT===' in chunk or '===END_CMD===' in chunk:
                # Parse actions so far and emit the latest one
                _partial_actions = _parse_code_actions(full_text, project)
                if _partial_actions:
                    _latest = _partial_actions[-1]
                    yield f'event: action_preview\ndata: {json.dumps({"type": _latest["type"], "path": _latest.get("path", ""), "id": _latest.get("id", "")})}\n\n'

    except Exception as e:
        print(f"[CODE-STREAM] ❌ Stream error: {e}")
        yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'
        return

    # ── Phase 3: Post-process ─────────────────────────────────────────
    yield f'event: status\ndata: {json.dumps({"phase": "parsing", "detail": "Antwort verarbeiten…"})}\n\n'

    reply_text = full_text
    # Strip thinking tags
    if '</think>' in reply_text:
        reply_text = reply_text.split('</think>', 1)[-1].strip()
    if reply_text.startswith('<think>'):
        parts = reply_text.split('</think>', 1)
        reply_text = parts[-1].strip() if len(parts) > 1 else reply_text

    # Parse actions
    actions = _parse_code_actions(reply_text, project)

    # Clean reply text (remove markup)
    clean_reply = re.sub(r'===FILE_EDIT:.*?===END_FILE_EDIT===', '', reply_text, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'===PATCH:.*?===END_PATCH===', '', clean_reply, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'===RUN_CMD===.*?===END_CMD===', '', clean_reply, flags=re.DOTALL).strip()
    if not clean_reply:
        clean_reply = reply_text

    # Handle tool calls (all formats)
    tool_results_for_reply = []
    _has_any_tool = ('[TOOL_CALLS]' in reply_text or '<tool_call>' in reply_text
                     or '[tool_call:' in reply_text or '<|tool_call>' in reply_text)
    if _has_any_tool:
        text_before = extract_text_before_tools(reply_text)
        if text_before.strip():
            clean_reply = text_before.strip()
        tool_calls_parsed = parse_tool_calls(reply_text)
        for tc in tool_calls_parsed:
            tool_name = tc["name"]
            tool_args = tc["arguments"]
            if project and "project_root" not in tool_args and tool_name in (
                "read_file", "write_file", "create_file", "patch_file",
                "delete_file", "create_directory", "list_directory",
                "search_text", "project_info", "install_deps", "run_tests",
                "lint_file", "git_status", "git_diff", "git_add", "git_commit",
                "recall_conversation",
            ):
                tool_args["project_root"] = project
            if project and "cwd" not in tool_args and tool_name == "run_command":
                tool_args["cwd"] = project
            if project and "path" in tool_args and not os.path.isabs(tool_args["path"]):
                tool_args["path"] = os.path.join(project, tool_args["path"])

            yield f'event: status\ndata: {json.dumps({"phase": "tool", "detail": f"🔧 {tool_name}…"})}\n\n'
            result = execute_tool(tool_name, tool_args)

            if result.get("success"):
                if tool_name in ("write_file", "create_file"):
                    actions.append({
                        "type": tool_name,
                        "path": result.get("path", tool_args.get("path", "")),
                        "content": tool_args.get("content", ""),
                        "id": f"tool_{int(time.time()*1000)}_{len(actions)}",
                        "status": "accepted" if mode == "agent" else "pending",
                    })
                elif tool_name == "run_command":
                    actions.append({
                        "type": "run_command",
                        "command": tool_args.get("command", ""),
                        "id": f"tool_{int(time.time()*1000)}_{len(actions)}",
                        "status": "accepted" if mode == "agent" else "pending",
                        "stdout": result.get("stdout", ""),
                        "stderr": result.get("stderr", ""),
                        "returncode": result.get("returncode", 0),
                    })
                tool_results_for_reply.append(f"✅ [{tool_name}]: {result.get('message', 'OK')}")
            else:
                tool_results_for_reply.append(f"⚠️ [{tool_name}]: {result.get('error', 'Fehler')}")

        if tool_results_for_reply:
            clean_reply += '\n\n**Tool-Ergebnisse:**\n' + '\n'.join(f'• {r}' for r in tool_results_for_reply)

    # In 'fragen' mode, strip actions
    if mode == 'fragen':
        actions = []

    # Store AI reply in code session
    from ailey_system.tools_code import code_session_add
    action_summary = ""
    if actions:
        parts = []
        for a in actions:
            if a.get('type') in ('edit_file', 'create_file'):
                parts.append(f"{a['type']}: {a.get('path', '?')}")
            elif a.get('type') == 'patch_file':
                parts.append(f"patch: {a.get('path', '?')} ({a.get('patch_count', '?')} changes)")
            elif a.get('type') == 'run_command':
                parts.append(f"cmd: {a.get('command', '?')}")
        action_summary = " | ".join(parts)
    code_session_add(project or "", "ai", clean_reply, summary=action_summary)

    # V$ salary
    salary = 0.0
    if mode == 'agent' and actions:
        salary = 15.0
        _earn_vyrus_dollars(salary, f"Code-Agent: {len(actions)} Aktionen ({action_summary[:60]})")
    elif mode == 'bearbeiten' and actions:
        salary = 5.0
        _earn_vyrus_dollars(salary, f"Code-Edit: {len(actions)} Änderungen")
    elif mode == 'fragen':
        salary = 1.0
        _earn_vyrus_dollars(salary, "Code-Frage beantwortet")

    _elapsed = round(_t.time() - _start, 1)
    print(f"[CODE-STREAM] Mode={mode}, Actions={len(actions)}, Tokens={token_count}, Elapsed={_elapsed}s")

    # ── Final done event with complete data ───────────────────────────
    yield f'event: done\ndata: {json.dumps({"reply": clean_reply, "actions": actions, "mode": mode, "salary": salary, "elapsed": _elapsed, "tokens": token_count})}\n\n'


def _api_code_chat_inner():
    """Inner implementation of code chat (wrapped by busy guard).
    Supports three modes like GitHub Copilot:
      - 'fragen' (ask): Explain, answer questions — no file changes
      - 'bearbeiten' (edit): Edit files with Accept/Reject confirmation
      - 'agent': Full autonomous agent — creates, edits, runs commands, iterates
    
    Refactored: Uses _build_code_chat_context() for shared prompt building
    and _parse_code_actions() for shared action parsing (eliminates duplication
    with the streaming endpoint).
    """
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({"success": False, "error": "Nachricht fehlt"}), 400

    # ── Build context using shared helper ─────────────────────────────
    ctx = _build_code_chat_context(data)
    code_system = ctx['code_system']
    mode = ctx['mode']
    project = ctx['project']
    max_tokens = ctx['max_tokens']
    code_tool_schemas = ctx['code_tool_schemas']

    # ── Store user message in code session (for recall_conversation tool) ──
    from ailey_system.tools_code import code_session_add
    code_session_add(project or "", "user", message)

    # ── Generate with MLX ─────────────────────────────────────────────
    try:
        gen = MLXGenerator.get()
        if gen is None:
            return jsonify({"success": True, "reply": "⚠️ Sprachmodell nicht geladen. Bitte warten…"})

        reply_text = gen.generate(code_system, message, {"max_tokens": max_tokens, "temperature": 0.4},
                                  tools=code_tool_schemas)

        # Agent mode: detect truncated output and retry with continuation prompt
        if mode == 'agent' and reply_text:
            _MAX_AGENT_RETRIES = 2
            _full_reply = reply_text
            for _retry_i in range(_MAX_AGENT_RETRIES):
                # Check for truncation: open FILE_EDIT/PATCH/CMD block without matching END
                _has_open_edit = '===FILE_EDIT:' in _full_reply and '===END_FILE_EDIT===' not in _full_reply.split('===FILE_EDIT:')[-1]
                _has_open_patch = '===PATCH:' in _full_reply and '===END_PATCH===' not in _full_reply.split('===PATCH:')[-1]
                _has_open_cmd = '===RUN_CMD===' in _full_reply and '===END_CMD===' not in _full_reply.split('===RUN_CMD===')[-1]
                _has_open_code = _full_reply.rstrip().endswith('```') is False and _full_reply.count('```') % 2 != 0
                if not (_has_open_edit or _has_open_patch or _has_open_cmd or _has_open_code):
                    break  # Reply is complete
                print(f"[CODE-CHAT] 🔄 Agent reply truncated (retry {_retry_i+1}/{_MAX_AGENT_RETRIES})")
                # Continue from where it left off
                _cont_prompt = (
                    f"Deine vorherige Antwort wurde abgeschnitten. Fahre EXAKT dort fort wo du aufgehört hast.\n"
                    f"Dein bisheriger Output endet mit:\n"
                    f"...{_full_reply[-300:]}\n\n"
                    f"WICHTIG: Beginne DIREKT mit dem fehlenden Code/Text — keine Wiederholung, keine Einleitung."
                )
                _cont_reply = gen.generate(code_system, _cont_prompt, {"max_tokens": max_tokens, "temperature": 0.3},
                                           tools=code_tool_schemas)
                if _cont_reply:
                    if '</think>' in _cont_reply:
                        _cont_reply = _cont_reply.split('</think>', 1)[-1].strip()
                    _full_reply += "\n" + _cont_reply
            reply_text = _full_reply

        # Strip thinking tags if present
        if '</think>' in reply_text:
            reply_text = reply_text.split('</think>', 1)[-1].strip()
        if reply_text.startswith('<think>'):
            parts = reply_text.split('</think>', 1)
            reply_text = parts[-1].strip() if len(parts) > 1 else reply_text

        # Parse agentic actions using shared helper
        actions = _parse_code_actions(reply_text, project)

        # Clean up the markers from the reply text shown to user
        clean_reply = re.sub(r'===FILE_EDIT:.*?===END_FILE_EDIT===', '', reply_text, flags=re.DOTALL).strip()
        clean_reply = re.sub(r'===PATCH:.*?===END_PATCH===', '', clean_reply, flags=re.DOTALL).strip()
        clean_reply = re.sub(r'===RUN_CMD===.*?===END_CMD===', '', clean_reply, flags=re.DOTALL).strip()
        if not clean_reply:
            clean_reply = reply_text

        # ── Handle [TOOL_CALLS] from Function Calling ────────────────
        # If model used Mistral Function Calling format instead of Freitext-Markup
        tool_results_for_reply = []
        if '[TOOL_CALLS]' in reply_text:
            text_before = extract_text_before_tools(reply_text)
            if text_before.strip():
                clean_reply = text_before.strip()
            
            tool_calls_parsed = parse_tool_calls(reply_text)
            for tc in tool_calls_parsed:
                tool_name = tc["name"]
                tool_args = tc["arguments"]
                
                # Inject project_root for code tools
                if project and "project_root" not in tool_args and tool_name in (
                    "read_file", "write_file", "create_file", "patch_file",
                    "delete_file", "create_directory", "list_directory",
                    "search_text", "project_info", "install_deps", "run_tests",
                    "lint_file", "git_status", "git_diff", "git_add", "git_commit",
                    "git_push", "git_pull", "git_log", "git_checkout", "git_stash",
                    "recall_conversation",
                ):
                    tool_args["project_root"] = project
                if project and "cwd" not in tool_args and tool_name == "run_command":
                    tool_args["cwd"] = project
                if project and "path" in tool_args and not os.path.isabs(tool_args["path"]):
                    tool_args["path"] = os.path.join(project, tool_args["path"])
                
                # ── Intercept generate_image: sync generation instead of background thread ──
                if tool_name == "generate_image":
                    try:
                        from ailey_system.image_generator import generate_image as _cc_gen
                        _cc_prompt = tool_args.get("prompt", message)
                        _cc_title = tool_args.get("title", _cc_prompt[:50])
                        _cc_ar = tool_args.get("aspect_ratio", "1:1")
                        # Unload LLM
                        _cc_idle = globals().get('idle_thinker')
                        _cc_unloaded = False
                        try:
                            if _cc_idle:
                                _cc_idle._generating_image = True
                                _cc_idle._unload_llm_for_image_gen()
                                _cc_unloaded = True
                            else:
                                # Direct cleanup with full Metal sync
                                print("[CodeChat/ImageGen] No idle_thinker — direct LLM cleanup")
                                import gc as _gc2
                                try:
                                    import mlx.core as mx
                                    mx.synchronize()
                                    mx.eval(mx.zeros(1))
                                except Exception:
                                    pass
                                try:
                                    from ailey_system import llm_mlx
                                    from ailey_system.llm_mlx import MLXGenerator, _mlx_lock
                                    with _mlx_lock:
                                        llm_mlx._model = None
                                        llm_mlx._tokenizer = None
                                        llm_mlx._cache = None
                                        llm_mlx._last_system_prompt = None
                                        MLXGenerator._instance = None
                                except Exception:
                                    pass
                                _gc2.collect(); _gc2.collect()
                                try:
                                    import mlx.core as mx
                                    mx.metal.set_cache_limit(0)
                                    mx.metal.clear_cache()
                                    mx.metal.set_memory_limit(0)
                                except Exception:
                                    pass
                                _gc2.collect()
                                import time as _t; _t.sleep(2.0)
                                _cc_unloaded = True
                        except Exception:
                            pass
                        _cc_fp, _cc_fn = _cc_gen(prompt=_cc_prompt, title=_cc_title, aspect_ratio=_cc_ar, low_ram=not _cc_unloaded, private=True)
                        # Reload LLM
                        try:
                            if _cc_unloaded and _cc_idle:
                                _cc_idle._reload_llm_after_image_gen()
                                _cc_idle._generating_image = False
                        except Exception:
                            if _cc_idle:
                                _cc_idle._generating_image = False
                        if _cc_fp and _cc_fn:
                            result = {"success": True, "message": "🎨 Bild generiert!", "image_url": f"/api/image/file/{_cc_fn}"}
                        else:
                            result = {"success": False, "error": "Bildgenerierung fehlgeschlagen"}
                    except Exception as _cce:
                        result = {"success": False, "error": str(_cce)}
                    tool_results_for_reply.append(
                        f"✅ [generate_image]: {result.get('message', '')}" if result.get("success")
                        else f"⚠️ [generate_image]: {result.get('error', 'Fehler')}"
                    )
                    continue

                result = execute_tool(tool_name, tool_args)
                
                # Convert tool results to actions for frontend
                if result.get("success"):
                    if tool_name in ("write_file", "create_file"):
                        actions.append({
                            "type": tool_name,
                            "path": result.get("path", tool_args.get("path", "")),
                            "content": tool_args.get("content", ""),
                            "id": f"tool_{int(time.time()*1000)}_{len(actions)}",
                            "status": "accepted" if mode == "agent" else "pending",
                        })
                    elif tool_name == "patch_file":
                        actions.append({
                            "type": "patch_file",
                            "path": result.get("path", tool_args.get("path", "")),
                            "patches": [{"search": tool_args.get("search", ""), "replace": tool_args.get("replace", "")}],
                            "id": f"tool_{int(time.time()*1000)}_{len(actions)}",
                            "status": "accepted" if mode == "agent" else "pending",
                            "patch_count": 1,
                        })
                    elif tool_name == "run_command":
                        actions.append({
                            "type": "run_command",
                            "command": tool_args.get("command", ""),
                            "id": f"tool_{int(time.time()*1000)}_{len(actions)}",
                            "status": "accepted" if mode == "agent" else "pending",
                            "stdout": result.get("stdout", ""),
                            "stderr": result.get("stderr", ""),
                            "returncode": result.get("returncode", 0),
                        })
                    
                    msg = result.get("message", "OK")
                    tool_results_for_reply.append(f"✅ [{tool_name}]: {msg}")
                else:
                    tool_results_for_reply.append(f"⚠️ [{tool_name}]: {result.get('error', 'Fehler')}")
            
            if tool_results_for_reply:
                clean_reply += '\n\n**Tool-Ergebnisse:**\n' + '\n'.join(f'• {r}' for r in tool_results_for_reply)
            
            # ── Re-generate with recall context if recall_conversation was used ──
            # When Ailey recalled conversation history, she needs to re-answer
            # with that context so her response actually uses the recalled info.
            _recall_results = [tc for tc in tool_calls_parsed if tc["name"] == "recall_conversation"]
            if _recall_results and mode == 'fragen':
                # Get the recall result and feed it back for a proper answer
                recall_args = _recall_results[0]["arguments"]
                recall_result = execute_tool("recall_conversation", {
                    **recall_args,
                    "project_root": project or "",
                })
                recalled_text = recall_result.get("formatted", "")
                if recalled_text:
                    _recall_context = (
                        f"KONTEXT AUS BISHERIGEM VERLAUF:\n{recalled_text}\n\n"
                        f"Beantworte jetzt die Frage des Users unter Berücksichtigung dieses Kontexts:"
                    )
                    try:
                        followup = gen.generate(
                            code_system,
                            f"{_recall_context}\n\n{message}",
                            {"max_tokens": 1500, "temperature": 0.4},
                        )
                        if "</think>" in followup:
                            followup = followup.split("</think>", 1)[-1].strip()
                        if "</thinking>" in followup:
                            followup = followup.split("</thinking>", 1)[-1].strip()
                        if "</thought>" in followup:
                            followup = followup.split("</thought>", 1)[-1].strip()
                        if followup.strip():
                            clean_reply = followup.strip()
                    except Exception as e:
                        print(f"[CODE-CHAT] ⚠️ Recall re-generate failed: {e}")

        # ── Agent mode: auto-execute all actions ──────────────────────
        agent_results = []
        if mode == 'agent' and actions:
            home = os.path.expanduser('~')
            for action in actions:
                try:
                    if action['type'] in ('edit_file', 'create_file', 'patch_file') and action.get('path'):
                        real = os.path.realpath(action['path'])
                        if real.startswith(home):
                            os.makedirs(os.path.dirname(real), exist_ok=True)
                            with open(real, 'w', encoding='utf-8') as f:
                                f.write(action.get('content', ''))
                            action['status'] = 'accepted'
                            label = action['type']
                            if action['type'] == 'patch_file':
                                label = f"patch ({action.get('patch_count', '?')} Änderungen)"
                            agent_results.append(f"✅ {label}: {os.path.basename(real)}")
                        else:
                            action['status'] = 'rejected'
                            agent_results.append(f"❌ Zugriff verweigert: {action['path']}")
                    elif action['type'] == 'run_command' and action.get('command'):
                        cmd = action['command']
                        _blocked = ['rm -rf /', 'mkfs', 'dd if=', ':(){', 'fork bomb']
                        if any(b in cmd.lower() for b in _blocked):
                            action['status'] = 'rejected'
                            agent_results.append(f"🚫 Befehl blockiert: {cmd}")
                        else:
                            result = subprocess.run(
                                cmd, shell=True, capture_output=True, text=True,
                                timeout=180, cwd=project or os.path.expanduser('~'),
                                env={**os.environ, 'LANG': 'de_DE.UTF-8'}
                            )
                            action['status'] = 'accepted'
                            action['stdout'] = result.stdout[-2000:] if result.stdout else ''
                            action['stderr'] = result.stderr[-1000:] if result.stderr else ''
                            action['returncode'] = result.returncode
                            status = '✅' if result.returncode == 0 else '⚠️'
                            agent_results.append(f"{status} `{cmd}` (exit {result.returncode})")
                except Exception as e:
                    action['status'] = 'rejected'
                    agent_results.append(f"❌ Fehler: {e}")

            # Append results to reply
            if agent_results:
                clean_reply += '\n\n**Ausgeführt:**\n' + '\n'.join(f'• {r}' for r in agent_results)

        # In 'fragen' mode, strip any actions (shouldn't generate them, but just in case)
        if mode == 'fragen':
            actions = []

        print(f"[CODE-CHAT] Mode={mode}, Actions={len(actions)}, Reply={len(clean_reply)} chars")

        # Store AI reply in code session for recall_conversation tool
        action_summary = ""
        if actions:
            parts = []
            for a in actions:
                if a.get('type') in ('edit_file', 'create_file'):
                    parts.append(f"{a['type']}: {a.get('path', '?')}")
                elif a.get('type') == 'patch_file':
                    parts.append(f"patch: {a.get('path', '?')} ({a.get('patch_count', '?')} changes)")
                elif a.get('type') == 'run_command':
                    parts.append(f"cmd: {a.get('command', '?')}")
            action_summary = " | ".join(parts)
        code_session_add(project or "", "ai", clean_reply, summary=action_summary)

        # ── V$ Salary for Code Mode work ─────────────────────────────
        salary = 0.0
        if mode == 'agent' and actions:
            salary = 15.0
            _earn_vyrus_dollars(salary, f"Code-Agent: {len(actions)} Aktionen ({action_summary[:60]})")
        elif mode == 'bearbeiten' and actions:
            salary = 5.0
            _earn_vyrus_dollars(salary, f"Code-Edit: {len(actions)} Änderungen")
        elif mode == 'fragen':
            salary = 1.0
            _earn_vyrus_dollars(salary, "Code-Frage beantwortet")

        return jsonify({
            "success": True,
            "reply": clean_reply,
            "actions": actions,
            "mode": mode,
            "salary": salary,
        })
    except Exception as e:
        print(f"[CODE-CHAT] ❌ {e}")
        traceback.print_exc()
        return jsonify({"success": True, "reply": f"⚠️ Fehler: {str(e)}"})


@app.post('/api/code/action')
def api_code_apply_action():
    """Apply an agentic action (accept file edit or run command)."""
    _coder_module.set_ailey_busy(True)  # Pause coder while action runs
    try:
        return _api_code_action_inner()
    finally:
        _coder_module.set_ailey_busy(False)


def _api_code_action_inner():
    """Inner implementation of code action (wrapped by busy guard)."""
    data = request.get_json(silent=True) or {}
    action_type = data.get('type', '')
    home = os.path.expanduser('~')

    if action_type == 'edit_file':
        path = (data.get('path') or '').strip()
        content = data.get('content', '')
        if not path:
            return jsonify({"success": False, "error": "Pfad fehlt"}), 400
        real = os.path.realpath(path)
        if not real.startswith(home):
            return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, 'w', encoding='utf-8') as f:
                f.write(content)
            return jsonify({"success": True, "path": real, "message": f"Datei gespeichert: {os.path.basename(real)}"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    elif action_type == 'create_file':
        path = (data.get('path') or '').strip()
        content = data.get('content', '')
        if not path:
            return jsonify({"success": False, "error": "Pfad fehlt"}), 400
        real = os.path.realpath(path)
        if not real.startswith(home):
            return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, 'w', encoding='utf-8') as f:
                f.write(content)
            return jsonify({"success": True, "path": real, "message": f"Datei erstellt: {os.path.basename(real)}"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    elif action_type == 'patch_file':
        path = (data.get('path') or '').strip()
        content = data.get('content', '')
        if not path:
            return jsonify({"success": False, "error": "Pfad fehlt"}), 400
        real = os.path.realpath(path)
        if not real.startswith(home):
            return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, 'w', encoding='utf-8') as f:
                f.write(content)
            patch_count = data.get('patch_count', '?')
            return jsonify({"success": True, "path": real, "message": f"Patch angewendet ({patch_count} Änderungen): {os.path.basename(real)}"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    elif action_type == 'run_command':
        command = (data.get('command') or '').strip()
        cwd = data.get('cwd') or os.path.expanduser('~')
        if not command:
            return jsonify({"success": False, "error": "Befehl fehlt"}), 400
        _blocked = ['rm -rf /', 'mkfs', 'dd if=', ':(){', 'fork bomb']
        for b in _blocked:
            if b in command.lower():
                return jsonify({"success": False, "error": "Befehl blockiert (Sicherheit)"}), 403
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=30, cwd=cwd,
                env={**os.environ, 'LANG': 'de_DE.UTF-8'}
            )
            return jsonify({
                "success": True,
                "stdout": result.stdout[-4000:] if result.stdout else '',
                "stderr": result.stderr[-2000:] if result.stderr else '',
                "returncode": result.returncode
            })
        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "error": "Timeout (30s)"}), 408
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        return jsonify({"success": False, "error": f"Unbekannter Aktionstyp: {action_type}"}), 400


# ══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP — Multi-step autonomous task execution
# ══════════════════════════════════════════════════════════════════════════════

# SSE update queues per agent task
_agent_update_queues = {}  # task_id -> list of updates
_agent_queues_lock = threading.Lock()


@app.post('/api/agent/run')
def api_agent_run():
    """Start a multi-step agent task.
    Body: {task, mode?, project?, max_steps?}
    Returns: {task_id} — use /api/agent/stream/<task_id> for updates.
    """
    data = request.get_json(silent=True) or {}
    task = (data.get('task') or '').strip()
    mode = data.get('mode', 'code')
    project = data.get('project', '')
    max_steps = min(int(data.get('max_steps', 25)), 50)

    if not task:
        return jsonify({"success": False, "error": "Task fehlt"}), 400

    gen = MLXGenerator.get()
    if gen is None:
        return jsonify({"success": False, "error": "Sprachmodell nicht geladen"}), 503

    # Create update queue for SSE
    update_queue = []
    
    def on_update(event_type: str, data: dict):
        update_queue.append({"event": event_type, "data": data, "ts": time.time()})
        # Store agent messages in code session for recall_conversation
        if event_type == "message" and data.get("text"):
            from ailey_system.tools_code import code_session_add
            is_summary = data.get("is_summary", False)
            code_session_add(project, "ai", data["text"],
                             summary="Agent-Zusammenfassung" if is_summary else "Agent-Schritt")
        elif event_type == "done":
            from ailey_system.tools_code import code_session_add
            summary_text = data.get("summary", "")
            code_session_add(project, "ai",
                f"Agent fertig: {task} — {data.get('tool_calls', 0)} Tools, {data.get('elapsed', '?')}s",
                summary=summary_text[:200] if summary_text else "")

    # Store user task in session
    from ailey_system.tools_code import code_session_add
    code_session_add(project, "user", f"[Agent-Aufgabe] {task}")

    runner = AgentRunner(
        generator=gen,
        task=task,
        mode=mode,
        project_root=project,
        max_steps=max_steps,
        on_update=on_update,
    )

    with _agent_queues_lock:
        _agent_update_queues[runner.task_id] = update_queue

    task_id = runner.run_async()
    
    import sys
    sys.stderr.write(f"[AGENT] 🚀 Started: {task_id} — '{task[:80]}' (mode={mode}, max={max_steps})\n")
    sys.stderr.flush()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "mode": mode,
        "max_steps": max_steps,
    })


@app.get('/api/agent/stream/<task_id>')
def api_agent_stream(task_id: str):
    """SSE stream for agent updates."""
    def stream():
        last_idx = 0
        heartbeat_interval = 3.0
        last_heartbeat = time.time()
        max_wait = 300  # 5 minutes max

        start = time.time()
        while time.time() - start < max_wait:
            with _agent_queues_lock:
                queue = _agent_update_queues.get(task_id, [])

            # Send new updates
            while last_idx < len(queue):
                update = queue[last_idx]
                last_idx += 1
                # Map 'error' to 'agent_error' to avoid SSE reserved event name
                evt_name = update["event"]
                if evt_name == "error":
                    evt_name = "agent_error"
                yield f'event: {evt_name}\ndata: {json.dumps(update["data"])}\n\n'

            # Check if agent is done
            agent = get_agent(task_id)
            if agent and agent.status in ('done', 'error', 'stopped'):
                # Send final update
                yield f'event: finished\ndata: {json.dumps(agent.to_dict())}\n\n'
                break

            if not agent:
                yield f'event: finished\ndata: {json.dumps({"status": "not_found"})}\n\n'
                break

            # Heartbeat
            now = time.time()
            if now - last_heartbeat > heartbeat_interval:
                yield f'data: {json.dumps({"heartbeat": True, "step": agent.current_step})}\n\n'
                last_heartbeat = now

            time.sleep(0.3)

        # Cleanup
        with _agent_queues_lock:
            _agent_update_queues.pop(task_id, None)

    return app.response_class(
        stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.get('/api/agent/status')
def api_agent_status():
    """Get status of an agent task."""
    task_id = request.args.get('task_id', '')
    if task_id:
        agent = get_agent(task_id)
        if agent:
            return jsonify({"success": True, **agent.to_dict()})
        return jsonify({"success": False, "error": "Agent nicht gefunden"}), 404
    else:
        # List all agents
        agents = list_agents()
        return jsonify({"success": True, "agents": agents, "count": len(agents)})


@app.post('/api/agent/stop')
def api_agent_stop():
    """Stop a running agent."""
    data = request.get_json(silent=True) or {}
    task_id = (data.get('task_id') or '').strip()
    if not task_id:
        return jsonify({"success": False, "error": "task_id fehlt"}), 400
    if stop_agent(task_id):
        return jsonify({"success": True, "message": "Agent gestoppt"})
    return jsonify({"success": False, "error": "Agent nicht gefunden"}), 404


@app.post('/api/agent/pause')
def api_agent_pause():
    """Pause a running agent."""
    data = request.get_json(silent=True) or {}
    task_id = (data.get('task_id') or '').strip()
    if not task_id:
        return jsonify({"success": False, "error": "task_id fehlt"}), 400
    if pause_agent(task_id):
        return jsonify({"success": True, "message": "Agent pausiert"})
    return jsonify({"success": False, "error": "Agent nicht gefunden"}), 404


@app.post('/api/agent/resume')
def api_agent_resume():
    """Resume a paused agent."""
    data = request.get_json(silent=True) or {}
    task_id = (data.get('task_id') or '').strip()
    if not task_id:
        return jsonify({"success": False, "error": "task_id fehlt"}), 400
    if resume_agent(task_id):
        return jsonify({"success": True, "message": "Agent fortgesetzt"})
    return jsonify({"success": False, "error": "Agent nicht gefunden"}), 404


# ══════════════════════════════════════════════════════════════════════════════
# FTP/SFTP — Remote file transfer for Code Mode
# ══════════════════════════════════════════════════════════════════════════════
_ftp_connection = None  # paramiko SFTPClient or ftplib.FTP


@app.post('/api/code/ftp/connect')
def api_ftp_connect():
    """Connect to FTP/SFTP server."""
    global _ftp_connection
    data = request.get_json(silent=True) or {}
    host = (data.get('host') or '').strip()
    user = (data.get('user') or '').strip()
    password = data.get('password', '')
    port = data.get('port', 22)
    protocol = data.get('protocol', 'sftp')

    if not host or not user:
        return jsonify({"success": False, "error": "Host und Benutzer erforderlich"}), 400

    # Close existing connection
    try:
        if _ftp_connection:
            _ftp_connection.close()
            _ftp_connection = None
    except:
        _ftp_connection = None

    try:
        if protocol == 'sftp':
            import paramiko
            transport = paramiko.Transport((host, int(port)))
            transport.connect(username=user, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            _ftp_connection = sftp
            print(f"[FTP] ✅ SFTP verbunden: {user}@{host}:{port}")
            return jsonify({"success": True, "protocol": "sftp", "host": host})
        else:
            import ftplib
            ftp = ftplib.FTP()
            ftp.connect(host, int(port), timeout=10)
            ftp.login(user, password)
            _ftp_connection = ftp
            print(f"[FTP] ✅ FTP verbunden: {user}@{host}:{port}")
            return jsonify({"success": True, "protocol": "ftp", "host": host})
    except Exception as e:
        print(f"[FTP] ❌ Verbindungsfehler: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/code/ftp/disconnect')
def api_ftp_disconnect():
    """Disconnect from FTP/SFTP server."""
    global _ftp_connection
    try:
        if _ftp_connection:
            _ftp_connection.close()
            print("[FTP] ⏹ Getrennt")
    except:
        pass
    _ftp_connection = None
    return jsonify({"success": True})


@app.get('/api/code/ftp/list')
def api_ftp_list():
    """List files in remote directory."""
    global _ftp_connection
    if not _ftp_connection:
        return jsonify({"success": False, "error": "Nicht verbunden"}), 400
    remote_path = request.args.get('path', '/')
    try:
        files = []
        # Check if SFTP or FTP
        if hasattr(_ftp_connection, 'listdir_attr'):
            # SFTP (paramiko)
            import stat
            for entry in _ftp_connection.listdir_attr(remote_path):
                is_dir = stat.S_ISDIR(entry.st_mode) if entry.st_mode else False
                files.append({"name": entry.filename, "is_dir": is_dir, "size": entry.st_size or 0})
        else:
            # FTP (ftplib)
            items = []
            _ftp_connection.cwd(remote_path)
            _ftp_connection.dir(items.append)
            for item in items:
                parts = item.split()
                if len(parts) >= 9:
                    name = ' '.join(parts[8:])
                    is_dir = item.startswith('d')
                    size = int(parts[4]) if parts[4].isdigit() else 0
                    if name not in ('.', '..'):
                        files.append({"name": name, "is_dir": is_dir, "size": size})
        # Sort: dirs first, then files
        files.sort(key=lambda f: (not f['is_dir'], f['name'].lower()))
        return jsonify({"success": True, "files": files, "path": remote_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/code/ftp/upload')
def api_ftp_upload():
    """Upload a local file to remote server."""
    global _ftp_connection
    if not _ftp_connection:
        return jsonify({"success": False, "error": "Nicht verbunden"}), 400
    data = request.get_json(silent=True) or {}
    local_path = (data.get('local_path') or '').strip()
    remote_path = (data.get('remote_path') or '').strip()
    if not local_path or not remote_path or not os.path.isfile(local_path):
        return jsonify({"success": False, "error": "Ungültige Pfade"}), 400
    try:
        if hasattr(_ftp_connection, 'put'):
            # SFTP
            _ftp_connection.put(local_path, remote_path)
        else:
            # FTP
            with open(local_path, 'rb') as f:
                _ftp_connection.storbinary(f'STOR {remote_path}', f)
        print(f"[FTP] ✅ Upload: {local_path} → {remote_path}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/code/ftp/download')
def api_ftp_download():
    """Download a remote file to local directory."""
    global _ftp_connection
    if not _ftp_connection:
        return jsonify({"success": False, "error": "Nicht verbunden"}), 400
    data = request.get_json(silent=True) or {}
    remote_path = (data.get('remote_path') or '').strip()
    local_dir = (data.get('local_dir') or '').strip()
    if not remote_path or not local_dir:
        return jsonify({"success": False, "error": "Ungültige Pfade"}), 400
    filename = remote_path.split('/')[-1]
    local_path = os.path.join(local_dir, filename)
    try:
        if hasattr(_ftp_connection, 'get'):
            # SFTP
            _ftp_connection.get(remote_path, local_path)
        else:
            # FTP
            with open(local_path, 'wb') as f:
                _ftp_connection.retrbinary(f'RETR {remote_path}', f.write)
        print(f"[FTP] ✅ Download: {remote_path} → {local_path}")
        return jsonify({"success": True, "local_path": local_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# AUTHOR MODE API — Prosa-Schreibmodus mit KI-Unterstützung
# ══════════════════════════════════════════════════════════════════════════════

_AUTHOR_PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ailey_users', 'author_projects')
os.makedirs(_AUTHOR_PROJECTS_DIR, exist_ok=True)

@app.get('/api/author/projects')
def api_author_projects():
    """List all author projects."""
    projects = []
    if os.path.isdir(_AUTHOR_PROJECTS_DIR):
        for name in sorted(os.listdir(_AUTHOR_PROJECTS_DIR)):
            p = os.path.join(_AUTHOR_PROJECTS_DIR, name)
            if os.path.isdir(p) and not name.startswith('.'):
                meta = {}
                meta_path = os.path.join(p, '.ailey_author.json')
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                    except: pass
                projects.append({
                    "name": name,
                    "path": p,
                    "title": meta.get("title", name),
                    "genre": meta.get("genre", ""),
                    "status": meta.get("status", "draft"),
                    "word_count": meta.get("word_count", 0),
                    "last_accessed": os.path.getmtime(p),
                })
    return jsonify({"success": True, "projects": projects})


@app.post('/api/author/projects')
def api_author_create_project():
    """Create a new author project with default structure."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    title = (data.get('title') or name).strip()
    genre = (data.get('genre') or '').strip()
    if not name:
        return jsonify({"success": False, "error": "Name fehlt"}), 400
    safe_name = re.sub(r'[^\w\s\-.]', '', name).strip().replace(' ', '-').lower()
    if not safe_name:
        return jsonify({"success": False, "error": "Ungültiger Name"}), 400
    p = os.path.join(_AUTHOR_PROJECTS_DIR, safe_name)
    if os.path.exists(p):
        return jsonify({"success": False, "error": "Projekt existiert bereits"}), 409
    os.makedirs(os.path.join(p, 'kapitel'), exist_ok=True)
    os.makedirs(os.path.join(p, 'notizen'), exist_ok=True)
    os.makedirs(os.path.join(p, '.snapshots'), exist_ok=True)
    # Create default meta
    meta = {
        "title": title,
        "subtitle": "",
        "author": "Simon van de Loo",
        "genre": genre,
        "language": "de",
        "status": "draft",
        "created": datetime.now().strftime("%Y-%m-%d"),
        "word_count_target": 0,
        "chapters": [],
        "characters": [],
        "notes": "",
    }
    with open(os.path.join(p, '.ailey_author.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    # Create starter files
    with open(os.path.join(p, 'kapitel', '01-kapitel-eins.md'), 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n## Kapitel 1\n\n")
    with open(os.path.join(p, 'notizen', 'ideen.md'), 'w', encoding='utf-8') as f:
        f.write(f"# Notizen — {title}\n\n")
    with open(os.path.join(p, 'outline.md'), 'w', encoding='utf-8') as f:
        f.write(f"# Gliederung — {title}\n\n1. Kapitel 1\n2. …\n")
    return jsonify({"success": True, "project": {"name": safe_name, "path": p, "title": title}})


@app.delete('/api/author/projects')
def api_author_delete_project():
    """Delete an author project permanently."""
    import shutil
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    projects_real = os.path.realpath(_AUTHOR_PROJECTS_DIR)
    if not real.startswith(projects_real + os.sep):
        return jsonify({"success": False, "error": "Nur verwaltete Projekte können gelöscht werden"}), 403
    if not os.path.isdir(real):
        return jsonify({"success": False, "error": "Projekt nicht gefunden"}), 404
    shutil.rmtree(real)
    return jsonify({"success": True, "deleted": os.path.basename(real)})


@app.get('/api/author/meta/<name>')
def api_author_meta(name):
    """Get project metadata."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, name, '.ailey_author.json')
    if not os.path.isfile(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404
    try:
        with open(p, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        return jsonify({"success": True, "meta": meta})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.put('/api/author/meta/<name>')
def api_author_meta_update(name):
    """Update project metadata."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, name, '.ailey_author.json')
    data = request.get_json(silent=True) or {}
    try:
        meta = {}
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        meta.update(data)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return jsonify({"success": True, "meta": meta})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/author/tree/<name>')
def api_author_tree(name):
    """Get file tree for an author project."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, name)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404
    tree = _build_file_tree(p)
    return jsonify({"success": True, "tree": tree})


@app.get('/api/author/file')
def api_author_file_read():
    """Read a file from an author project."""
    path = request.args.get('path', '')
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(_AUTHOR_PROJECTS_DIR)):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    if not os.path.isfile(real):
        return jsonify({"success": False, "error": "Datei nicht gefunden"}), 404
    try:
        with open(real, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"success": True, "content": content, "path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.put('/api/author/file')
def api_author_file_write():
    """Write/update a file in an author project."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    content = data.get('content', '')
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(_AUTHOR_PROJECTS_DIR)):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    try:
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/author/file')
def api_author_file_create():
    """Create a new file in an author project."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(_AUTHOR_PROJECTS_DIR)):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    if os.path.exists(real):
        return jsonify({"success": False, "error": "Datei existiert bereits"}), 409
    try:
        os.makedirs(os.path.dirname(real), exist_ok=True)
        ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
        name = os.path.basename(path).rsplit('.', 1)[0] if '.' in path else os.path.basename(path)
        content = f"# {name}\n\n" if ext == 'md' else ''
        with open(real, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True, "content": content, "path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.delete('/api/author/file')
def api_author_file_delete():
    """Delete a file from an author project."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(_AUTHOR_PROJECTS_DIR)):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    try:
        if os.path.isdir(real):
            import shutil
            shutil.rmtree(real)
        elif os.path.isfile(real):
            os.remove(real)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/author/mkdir')
def api_author_mkdir():
    """Create a directory in an author project."""
    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"success": False, "error": "Pfad fehlt"}), 400
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(_AUTHOR_PROJECTS_DIR)):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    os.makedirs(real, exist_ok=True)
    return jsonify({"success": True})


@app.post('/api/author/rename')
def api_author_rename():
    """Rename a file in an author project."""
    data = request.get_json(silent=True) or {}
    old_path = (data.get('old_path') or '').strip()
    new_path = (data.get('new_path') or '').strip()
    if not old_path or not new_path:
        return jsonify({"success": False, "error": "Pfade fehlen"}), 400
    base = os.path.realpath(_AUTHOR_PROJECTS_DIR)
    if not os.path.realpath(old_path).startswith(base) or not os.path.realpath(new_path).startswith(base):
        return jsonify({"success": False, "error": "Zugriff verweigert"}), 403
    try:
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.rename(old_path, new_path)
        return jsonify({"success": True, "new_path": new_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/author/autosave')
def api_author_autosave():
    """Batch-save multiple author files."""
    data = request.get_json(silent=True) or {}
    files = data.get('files', [])
    base = os.path.realpath(_AUTHOR_PROJECTS_DIR)
    saved = []
    errors = []
    for f in files:
        path = (f.get('path') or '').strip()
        content = f.get('content', '')
        if not path: continue
        real = os.path.realpath(path)
        if not real.startswith(base):
            errors.append({"path": path, "error": "Zugriff verweigert"})
            continue
        try:
            os.makedirs(os.path.dirname(real), exist_ok=True)
            with open(real, 'w', encoding='utf-8') as fh:
                fh.write(content)
            saved.append(path)
        except Exception as e:
            errors.append({"path": path, "error": str(e)})
    return jsonify({"success": True, "saved": saved, "errors": errors})


@app.get('/api/author/stats/<name>')
def api_author_stats(name):
    """Get word count and chapter stats for an author project."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, name)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404
    total_words = 0
    total_chars = 0
    chapters = []
    kapitel_dir = os.path.join(p, 'kapitel')
    if os.path.isdir(kapitel_dir):
        for fname in sorted(os.listdir(kapitel_dir)):
            if fname.endswith('.md'):
                fp = os.path.join(kapitel_dir, fname)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        text = f.read()
                    wc = len(text.split())
                    cc = len(text)
                    total_words += wc
                    total_chars += cc
                    chapters.append({"file": fname, "word_count": wc, "char_count": cc})
                except: pass
    # Also count notizen + outline
    for sub in ['notizen', '']:
        sub_dir = os.path.join(p, sub) if sub else p
        for fname in os.listdir(sub_dir):
            fp = os.path.join(sub_dir, fname)
            if fname.endswith('.md') and os.path.isfile(fp) and sub_dir != kapitel_dir:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        text = f.read()
                    total_words += len(text.split())
                    total_chars += len(text)
                except: pass
    # Load target from meta
    target = 0
    meta_path = os.path.join(p, '.ailey_author.json')
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            target = meta.get('word_count_target', 0)
        except: pass
    reading_time = max(1, total_words // 250)  # ~250 words per minute
    return jsonify({
        "success": True,
        "total_words": total_words,
        "total_chars": total_chars,
        "chapters": chapters,
        "word_count_target": target,
        "reading_time_minutes": reading_time,
    })


@app.post('/api/author/snapshot/<name>')
def api_author_snapshot(name):
    """Create a snapshot (backup) of the project."""
    import tarfile
    p = os.path.join(_AUTHOR_PROJECTS_DIR, name)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404
    snap_dir = os.path.join(p, '.snapshots')
    os.makedirs(snap_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
    snap_path = os.path.join(snap_dir, f'{ts}.tar.gz')
    try:
        with tarfile.open(snap_path, 'w:gz') as tar:
            for item in os.listdir(p):
                if item == '.snapshots': continue
                tar.add(os.path.join(p, item), arcname=item)
        return jsonify({"success": True, "snapshot": snap_path, "timestamp": ts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/author/snapshots/<name>')
def api_author_snapshots(name):
    """List all snapshots for a project."""
    snap_dir = os.path.join(_AUTHOR_PROJECTS_DIR, name, '.snapshots')
    snaps = []
    if os.path.isdir(snap_dir):
        for fname in sorted(os.listdir(snap_dir), reverse=True):
            if fname.endswith('.tar.gz'):
                fp = os.path.join(snap_dir, fname)
                snaps.append({
                    "file": fname,
                    "path": fp,
                    "timestamp": fname.replace('.tar.gz', ''),
                    "size": os.path.getsize(fp),
                })
    return jsonify({"success": True, "snapshots": snaps})


@app.post('/api/author/ai/chat')
def api_author_ai_chat():
    """Author mode AI chat — KI als Lektorin / Schreibassistentin.
    Modes: weiterschreiben, lektorat, brainstorm, recherche, fragen"""
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    mode = data.get('mode', 'fragen')
    text_context = (data.get('text_context') or '')[:8000]
    project_name = data.get('project_name', '')
    filename = data.get('filename', '')

    if not message and mode == 'fragen':
        return jsonify({"success": False, "error": "Nachricht fehlt"}), 400

    # Build system prompt based on mode
    base_prompt = (
        "Du bist Ailey, eine kreative KI-Schreibassistentin und Lektorin. "
        "Du hilfst beim Schreiben von Prosa, Romanen und Texten auf Deutsch. "
        "Dein Stil ist unterstützend, literarisch bewandert und konstruktiv. "
    )

    if mode == 'weiterschreiben':
        system = (
            base_prompt +
            "Der Autor bittet dich, seinen Text fortzusetzen. "
            "Schreibe nahtlos weiter im selben Stil, Ton und Tempo. "
            "Behalte den Erzählstil (Ich-Perspektive / Er-Sie / etc.) bei. "
            "Schreibe ca. 200-400 Wörter, dann höre an einer natürlichen Stelle auf. "
            "Gib NUR den fortgesetzten Text aus, keine Erklärungen. "
            "WICHTIG: Wenn der Autor eine bestimmte Anweisung gibt (z.B. 'schreibe über X' "
            "oder 'der Hund soll erscheinen'), dann berücksichtige diese Anweisung UNBEDINGT! "
            "Die Anweisung des Autors hat höchste Priorität."
        )
        if message:
            user_msg = (
                f"ANWEISUNG DES AUTORS: {message}\n\n"
                f"Hier ist der bisherige Text:\n\n{text_context}\n\n"
                f"Bitte setze den Text fort und berücksichtige dabei die Anweisung des Autors."
            )
        else:
            user_msg = f"Hier ist der bisherige Text:\n\n{text_context}\n\nBitte setze den Text fort."
    elif mode == 'lektorat':
        system = (
            base_prompt +
            "Der Autor bittet um ein Lektorat. Analysiere den Text und gib konstruktives Feedback zu: "
            "1. Stil & Sprache (Wortwahl, Satzstruktur, Rhythmus) "
            "2. Grammatik & Rechtschreibung "
            "3. Show vs. Tell — werden Szenen lebendig erzählt? "
            "4. Dialog-Qualität (falls vorhanden) "
            "5. Pacing & Spannung "
            "Sei ehrlich aber ermutigend. Gib konkrete Verbesserungsvorschläge."
        )
        user_msg = f"Bitte lektoriere diesen Text:\n\n{text_context}" + (f"\n\nZusätzliche Anmerkung: {message}" if message else "")
    elif mode == 'brainstorm':
        system = (
            base_prompt +
            "Der Autor möchte brainstormen. Sei kreativ, inspirierend und bau auf seinen Ideen auf. "
            "Schlage Plot-Twists, Charakterentwicklungen, Szenen oder Konflikte vor. "
            "Stelle auch Rückfragen um das Gespräch am Laufen zu halten."
        )
        user_msg = message + (f"\n\nKontext — aktueller Text:\n{text_context[:3000]}" if text_context else "")
    elif mode == 'recherche':
        system = (
            base_prompt +
            "Der Autor braucht Recherche-Hilfe. Recherchiere zu dem genannten Thema "
            "und gib fundierte, für Prosa nutzbare Informationen. "
            "Strukturiere die Antwort klar mit relevanten Details, historischen Fakten, "
            "sensorischen Details die in der Prosa verwendet werden können."
        )
        user_msg = message
    else:  # fragen
        system = (
            base_prompt +
            f"Der Autor arbeitet am Projekt '{project_name}', Datei '{filename}'. "
            "Beantworte seine Frage im Kontext seines Schreibprojekts."
        )
        user_msg = message + (f"\n\nAktueller Text:\n{text_context[:3000]}" if text_context else "")

    # ── Inject GraphRAG lore context for Author Mode ──────────────────
    # For brainstorm/recherche/fragen, inject relevant wiki knowledge graph data
    if mode in ('brainstorm', 'recherche', 'fragen') and (message or text_context):
        try:
            from ailey_system.graph_rag import get_graph_rag
            _agraph = get_graph_rag()
            if _agraph and _agraph.G.number_of_nodes() > 0:
                _search_text = message or text_context[:300]
                _agraph_results = _agraph.search(_search_text, max_results=3, max_hops=1)
                if _agraph_results:
                    _agraph_texts = [r.get('text', '').strip() for r in _agraph_results if len(r.get('text', '').strip()) > 20]
                    if _agraph_texts:
                        system += "\n\n🕸️ WISSENSGRAPH (Lore & Entitäten):\n" + "\n---\n".join(_agraph_texts[:3])[:1000]
        except Exception as _ae:
            print(f"[Author] GraphRAG inject error: {_ae}")

    try:
        gen = MLXGenerator.get()
        if gen is None:
            return jsonify({"success": False, "error": "Sprachmodell nicht geladen"}), 503
        max_tok = 1500 if mode == 'weiterschreiben' else 1000
        # Apply runtime override from generation settings (UI slider)
        _author_key = 'author_write' if mode == 'weiterschreiben' else 'author_review'
        _author_override = get_gen_setting(_author_key)
        if _author_override and _author_override > 0:
            max_tok = _author_override
        raw = gen.generate(system, user_msg, {"max_tokens": max_tok, "temperature": 0.5, "top_p": 0.9})
        # Strip thinking tags
        if '</think>' in (raw or ''):
            raw = raw.split('</think>', 1)[-1].strip()
        # Strip mood tag
        import re as _re
        raw = _re.sub(r'<mood:\w+>', '', raw or '').strip()

        # ── V$ Salary for Author Mode work ───────────────────────────
        salary_map = {
            'weiterschreiben': 5.0,
            'lektorat': 8.0,
            'brainstorm': 3.0,
            'recherche': 3.0,
            'fragen': 1.0,
        }
        salary = salary_map.get(mode, 1.0)
        _earn_vyrus_dollars(salary, f"Author-Mode: {mode}" + (f" ({project_name})" if project_name else ""))

        return jsonify({"success": True, "reply": raw, "mode": mode, "salary": salary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ── Project-RAG: Per-project knowledge base for Author Mode ──────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _author_rag_dir(project_name: str) -> str:
    """Return the .rag directory path for an author project."""
    return os.path.join(_AUTHOR_PROJECTS_DIR, project_name, '.rag')


def _ensure_project_rag_table(project_name: str):
    """Ensure a LanceDB table exists for this project's knowledge base."""
    try:
        import lancedb

        rag_dir = _author_rag_dir(project_name)
        os.makedirs(rag_dir, exist_ok=True)
        db_path = os.path.join(rag_dir, 'lancedb')
        db = lancedb.connect(db_path)

        table_name = 'knowledge'
        try:
            tbl = db.open_table(table_name)
        except Exception:
            # Create empty table with schema
            import pyarrow as pa
            schema = pa.schema([
                pa.field('id', pa.string()),
                pa.field('text', pa.string()),
                pa.field('source', pa.string()),
                pa.field('doc_type', pa.string()),
                pa.field('title', pa.string()),
                pa.field('chunk_index', pa.int32()),
                pa.field('vector', pa.list_(pa.float32(), 384)),
            ])
            tbl = db.create_table(table_name, schema=schema)
        return db, tbl
    except Exception as e:
        print(f"[AuthorRAG] Error ensuring table for {project_name}: {e}")
        return None, None


def _get_author_embedding_model():
    """Get or lazily load the SentenceTransformer embedding model for Author RAG."""
    global _author_rag_embed_model
    if _author_rag_embed_model is None:
        from sentence_transformers import SentenceTransformer
        _author_rag_embed_model = SentenceTransformer(
            'paraphrase-multilingual-MiniLM-L12-v2',
            device='cpu',  # MUST be CPU — MPS/Metal deadlocks with MLX → GPU OOM crash
        )
    return _author_rag_embed_model

_author_rag_embed_model = None


def _chunk_text_author(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    """Split text into overlapping chunks by word count."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks if chunks else [text[:2000]]


@app.post('/api/author/rag/<project>/upload')
def api_author_rag_upload(project):
    """Upload a reference document (PDF, TXT, MD, DOCX, EPUB) into the project's knowledge base."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, project)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Projekt nicht gefunden"}), 404

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Keine Datei"}), 400

    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"success": False, "error": "Dateiname fehlt"}), 400

    custom_title = request.form.get('title', '').strip() or uploaded.filename
    filename = uploaded.filename
    ext = os.path.splitext(filename)[1].lower()

    _ALLOWED = {'.txt', '.md', '.pdf', '.docx', '.rtf', '.epub', '.html', '.htm', '.json', '.csv'}
    if ext not in _ALLOWED:
        return jsonify({"success": False, "error": f"Dateityp '{ext}' nicht unterstützt"}), 400

    try:
        raw_bytes = uploaded.read()
        text_content = ''

        if ext == '.pdf':
            try:
                import fitz
                doc = fitz.open(stream=raw_bytes, filetype='pdf')
                text_content = '\n\n'.join(page.get_text() for page in doc)
                doc.close()
            except ImportError:
                try:
                    import pdfplumber, io
                    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                        text_content = '\n\n'.join(pg.extract_text() or '' for pg in pdf.pages)
                except ImportError:
                    return jsonify({"success": False, "error": "PDF-Lib fehlt (pip install PyMuPDF)"}), 500
        elif ext == '.docx':
            try:
                from docx import Document
                import io
                doc = Document(io.BytesIO(raw_bytes))
                text_content = '\n\n'.join(par.text for par in doc.paragraphs if par.text.strip())
            except ImportError:
                return jsonify({"success": False, "error": "python-docx fehlt"}), 500
        elif ext == '.epub':
            try:
                import ebooklib
                from ebooklib import epub
                from bs4 import BeautifulSoup
                import io
                book = epub.read_epub(io.BytesIO(raw_bytes))
                texts = []
                for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    texts.append(soup.get_text())
                text_content = '\n\n'.join(texts)
            except ImportError:
                return jsonify({"success": False, "error": "ebooklib/beautifulsoup4 fehlt"}), 500
        else:
            text_content = raw_bytes.decode('utf-8', errors='replace')

        if len(text_content.strip()) < 10:
            return jsonify({"success": False, "error": "Datei ist leer oder nicht lesbar"}), 400

        # Save a copy of the original file in .rag/docs/
        docs_dir = os.path.join(_author_rag_dir(project), 'docs')
        os.makedirs(docs_dir, exist_ok=True)
        safe_fn = re.sub(r'[^\w.\-]', '_', filename)
        with open(os.path.join(docs_dir, safe_fn), 'wb') as f:
            f.write(raw_bytes)

        # Chunk and embed
        chunks = _chunk_text_author(text_content)
        embed_model = _get_author_embedding_model()
        embeddings = embed_model.encode([c[:512] for c in chunks], show_progress_bar=False)

        db, tbl = _ensure_project_rag_table(project)
        if tbl is None:
            return jsonify({"success": False, "error": "RAG-Datenbank Fehler"}), 500

        import uuid as _uuid
        rows = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            rows.append({
                'id': str(_uuid.uuid4()),
                'text': chunk,
                'source': filename,
                'doc_type': 'reference',
                'title': custom_title,
                'chunk_index': i,
                'vector': emb.tolist(),
            })
        tbl.add(rows)

        return jsonify({
            "success": True,
            "filename": filename,
            "title": custom_title,
            "chunks": len(chunks),
            "total_chars": len(text_content),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/author/rag/<project>/documents')
def api_author_rag_documents(project):
    """List all indexed reference documents for a project."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, project)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404

    docs = []
    try:
        db, tbl = _ensure_project_rag_table(project)
        if tbl is not None:
            df = tbl.to_pandas()
            if len(df) > 0:
                for source, group in df.groupby('source'):
                    docs.append({
                        "source": source,
                        "title": group['title'].iloc[0] if 'title' in group.columns else source,
                        "doc_type": group['doc_type'].iloc[0] if 'doc_type' in group.columns else 'reference',
                        "chunks": len(group),
                        "total_chars": sum(len(t) for t in group['text']),
                    })
    except Exception as e:
        print(f"[AuthorRAG] list error: {e}")

    return jsonify({"success": True, "documents": docs})


@app.delete('/api/author/rag/<project>/document')
def api_author_rag_delete_document(project):
    """Remove a document from the project knowledge base by source filename."""
    data = request.get_json(silent=True) or {}
    source = (data.get('source') or '').strip()
    if not source:
        return jsonify({"success": False, "error": "Source fehlt"}), 400

    try:
        db, tbl = _ensure_project_rag_table(project)
        if tbl is not None:
            tbl.delete(f"source = '{source}'")

        # Also delete the file copy
        docs_dir = os.path.join(_author_rag_dir(project), 'docs')
        safe_fn = re.sub(r'[^\w.\-]', '_', source)
        doc_path = os.path.join(docs_dir, safe_fn)
        if os.path.isfile(doc_path):
            os.remove(doc_path)

        return jsonify({"success": True, "deleted": source})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post('/api/author/rag/<project>/search')
def api_author_rag_search(project):
    """Search the project knowledge base with a text query."""
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    limit = data.get('limit', 5)
    if not query:
        return jsonify({"success": False, "error": "Query fehlt"}), 400

    try:
        db, tbl = _ensure_project_rag_table(project)
        if tbl is None:
            return jsonify({"success": True, "results": []})

        embed_model = _get_author_embedding_model()
        q_emb = embed_model.encode([query[:512]], show_progress_bar=False)[0]

        results = tbl.search(q_emb.tolist()).limit(limit).to_pandas()
        hits = []
        for _, row in results.iterrows():
            hits.append({
                "text": row.get('text', ''),
                "source": row.get('source', ''),
                "title": row.get('title', ''),
                "doc_type": row.get('doc_type', ''),
                "score": float(row.get('_distance', 0)),
            })
        return jsonify({"success": True, "results": hits})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get('/api/author/rag/<project>/notes')
def api_author_rag_notes(project):
    """Get auto-generated notes (by Qwen Coder) for a project."""
    p = os.path.join(_AUTHOR_PROJECTS_DIR, project)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Nicht gefunden"}), 404

    notes_path = os.path.join(_author_rag_dir(project), 'auto_notes.json')
    notes = []
    if os.path.isfile(notes_path):
        try:
            with open(notes_path, 'r', encoding='utf-8') as f:
                notes = json.load(f)
        except Exception:
            pass
    return jsonify({"success": True, "notes": notes})


# ══════════════════════════════════════════════════════════════════════════════
# ── Qwen Coder Auto-Notes: Near-realtime text analysis for Author Mode ──────
# ══════════════════════════════════════════════════════════════════════════════

_author_analysis_lock = threading.Lock()

@app.post('/api/author/rag/<project>/auto-analyze')
def api_author_rag_auto_analyze(project):
    """Analyze text with Qwen Coder model and auto-extract structured notes.

    The fast 1.5B model analyzes the current text and extracts:
    - Character names & descriptions
    - Locations & settings
    - Plot points & events
    - Timeline markers
    - Relationships between characters
    - Key themes & motifs

    Results are stored in the project's .rag/auto_notes.json and
    optionally indexed into the project's vector knowledge base.
    """
    p = os.path.join(_AUTHOR_PROJECTS_DIR, project)
    if not os.path.isdir(p):
        return jsonify({"success": False, "error": "Projekt nicht gefunden"}), 404

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    filename = data.get('filename', '')
    mode = data.get('mode', 'full')  # 'full' or 'incremental'

    if not text or len(text) < 50:
        return jsonify({"success": True, "notes": [], "skipped": True, "reason": "Text zu kurz"})

    # Rate-limit: don't run more than once at a time
    if not _author_analysis_lock.acquire(blocking=False):
        return jsonify({"success": True, "notes": [], "skipped": True, "reason": "Analyse läuft bereits"})

    try:
        from ailey_system.llm_coder import _ensure_coder_loaded, _coder_lock, _schedule_coder_unload
        import ailey_system.llm_coder as _coder_mod
        import mlx_lm
        from mlx_lm.sample_utils import make_sampler

        if not _ensure_coder_loaded():
            return jsonify({"success": False, "error": "Coder-Modell nicht verfügbar"}), 503

        # Truncate text to what the small model can handle
        analysis_text = text[:4000]

        system_prompt = (
            "Du bist ein Textanalyst. Analysiere den folgenden literarischen Text und extrahiere strukturierte Informationen.\n"
            "Antworte AUSSCHLIESSLICH in diesem JSON-Format (keine andere Ausgabe):\n"
            "{\n"
            '  "characters": [{"name": "...", "description": "kurze Beschreibung", "role": "protagonist/antagonist/nebenfigur"}],\n'
            '  "locations": [{"name": "...", "description": "kurze Beschreibung"}],\n'
            '  "plot_points": ["kurze Zusammenfassung wichtiger Ereignisse"],\n'
            '  "themes": ["Thema 1", "Thema 2"],\n'
            '  "timeline": ["Zeitmarker oder chronologische Hinweise"],\n'
            '  "relationships": [{"from": "Person A", "to": "Person B", "type": "Beziehungsart"}],\n'
            '  "style_notes": "kurze Anmerkung zum Schreibstil"\n'
            "}\n"
            "Wenn eine Kategorie leer ist, gib ein leeres Array [] zurück. Antworte NUR mit dem JSON."
        )

        user_msg = f"Analysiere diesen Text:\n\n{analysis_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            prompt = _coder_mod._coder_tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            prompt = (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{user_msg}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

        sampler = make_sampler(temp=0.1, top_p=0.9)

        with _coder_lock:
            result = mlx_lm.generate(
                _coder_mod._coder_model, _coder_mod._coder_tokenizer,
                prompt=prompt,
                max_tokens=800,
                sampler=sampler,
                verbose=False,
            )
            _schedule_coder_unload()

        # Parse the JSON response
        notes_data = {}
        if result:
            clean = result.strip()
            for stop in ("<|im_end|>", "<|im_start|>"):
                if stop in clean:
                    clean = clean[:clean.index(stop)]
            try:
                start_idx = clean.find('{')
                end_idx = clean.rfind('}')
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = clean[start_idx:end_idx + 1]
                    notes_data = json.loads(json_str)
            except json.JSONDecodeError:
                print(f"[AuthorRAG] Coder returned non-JSON: {clean[:200]}")
                notes_data = {"raw_analysis": clean[:500]}

        # Add metadata
        import uuid as _uuid
        notes_entry = {
            "id": str(_uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "text_length": len(text),
            "analysis": notes_data,
        }

        # Load existing notes and merge
        rag_dir = _author_rag_dir(project)
        os.makedirs(rag_dir, exist_ok=True)
        notes_path = os.path.join(rag_dir, 'auto_notes.json')

        existing_notes = []
        if os.path.isfile(notes_path):
            try:
                with open(notes_path, 'r', encoding='utf-8') as f:
                    existing_notes = json.load(f)
            except Exception:
                pass

        if mode == 'full':
            # Replace notes for this filename
            existing_notes = [n for n in existing_notes if n.get('filename') != filename]
        existing_notes.append(notes_entry)
        existing_notes = existing_notes[-50:]

        with open(notes_path, 'w', encoding='utf-8') as f:
            json.dump(existing_notes, f, indent=2, ensure_ascii=False)

        # Also index the analysis into the vector DB for RAG search
        try:
            analysis_parts = []
            chars = notes_data.get('characters', [])
            if chars:
                for c in chars:
                    analysis_parts.append(f"Charakter: {c.get('name', '?')} — {c.get('description', '')} (Rolle: {c.get('role', '?')})")
            locs = notes_data.get('locations', [])
            if locs:
                for loc in locs:
                    analysis_parts.append(f"Ort: {loc.get('name', '?')} — {loc.get('description', '')}")
            plots = notes_data.get('plot_points', [])
            if plots:
                for pp in plots:
                    analysis_parts.append(f"Handlung: {pp}")
            themes = notes_data.get('themes', [])
            if themes:
                analysis_parts.append(f"Themen: {', '.join(themes)}")

            if analysis_parts:
                combined = '\n'.join(analysis_parts)
                embed_model = _get_author_embedding_model()
                emb = embed_model.encode([combined[:512]], show_progress_bar=False)[0]

                db, tbl = _ensure_project_rag_table(project)
                if tbl is not None:
                    try:
                        tbl.delete(f"source = 'auto:{filename}'")
                    except Exception:
                        pass
                    tbl.add([{
                        'id': str(_uuid.uuid4()),
                        'text': combined,
                        'source': f'auto:{filename}',
                        'doc_type': 'auto_notes',
                        'title': f'Auto-Analyse: {filename}',
                        'chunk_index': 0,
                        'vector': emb.tolist(),
                    }])
        except Exception as e:
            print(f"[AuthorRAG] Vector indexing failed: {e}")

        return jsonify({
            "success": True,
            "notes": notes_data,
            "entry_id": notes_entry['id'],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        _author_analysis_lock.release()


# ═══════════════════════════════════════════════════════════════
# ██  CMS MODE — AI-powered Page Builder API
# ═══════════════════════════════════════════════════════════════

try:
    from ailey_system.cms.schema import (
        list_projects as cms_list_projects,
        load_project as cms_load_project,
        save_project as cms_save_project,
        create_project as cms_create_project,
        delete_project as cms_delete_project,
        add_section_to_page,
        remove_section as cms_remove_section,
        move_section as cms_move_section,
        update_section as cms_update_section,
        add_page as cms_add_page,
        remove_page as cms_remove_page,
        create_section,
        create_blank_site,
        SECTION_TEMPLATES,
        validate_site,
    )
    from ailey_system.cms.renderer import render_page as cms_render_page, render_section as cms_render_section
    from ailey_system.cms.exporter import export_static as cms_export_static
    from ailey_system.cms.legal_generator import generate_legal_pages as cms_generate_legal
    CMS_AVAILABLE = True
    print("[CMS] CMS Mode loaded successfully")
except Exception as _cms_err:
    CMS_AVAILABLE = False
    print(f"[CMS] CMS Mode not available: {_cms_err}")

# --- CMS: List section templates ---
@app.route('/api/cms/templates', methods=['GET'])
def cms_templates():
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    # Group by category
    categories = {}
    for tid, tpl in SECTION_TEMPLATES.items():
        cat = tpl.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "type": tid,
            "label": tpl["label"],
            "icon": tpl["icon"],
            "variants": tpl["variants"],
            "category": cat,
        })
    return jsonify({"success": True, "templates": SECTION_TEMPLATES, "categories": categories})

# --- CMS: List projects ---
@app.route('/api/cms/projects', methods=['GET'])
def cms_projects_list():
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    return jsonify({"success": True, "projects": cms_list_projects()})

# --- CMS: Create project ---
@app.route('/api/cms/projects', methods=['POST'])
def cms_projects_create():
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title", "Neue Website")
    slug, site = cms_create_project(title)
    return jsonify({"success": True, "slug": slug, "site": site})

# --- CMS: Load project ---
@app.route('/api/cms/projects/<slug>', methods=['GET'])
def cms_project_get(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "site": site})

# --- CMS: Save project ---
@app.route('/api/cms/projects/<slug>', methods=['PUT'])
def cms_project_save(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    data = request.get_json(force=True, silent=True) or {}
    site = data.get("site")
    if not site:
        return jsonify({"success": False, "error": "No site data"}), 400
    valid, errors = validate_site(site)
    if not valid:
        return jsonify({"success": False, "error": "Validation failed", "errors": errors}), 400
    ok = cms_save_project(slug, site)
    return jsonify({"success": ok})

# --- CMS: Delete project ---
@app.route('/api/cms/projects/<slug>', methods=['DELETE'])
def cms_project_delete(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    ok = cms_delete_project(slug)
    return jsonify({"success": ok})

# --- CMS: Add section to page ---
@app.route('/api/cms/projects/<slug>/sections', methods=['POST'])
def cms_section_add(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    page_slug = data.get("pageSlug", "/")
    section_type = data.get("type")
    variant = data.get("variant", "")
    props = data.get("props")
    position = data.get("position", -1)
    if not section_type:
        return jsonify({"success": False, "error": "type is required"}), 400
    section = add_section_to_page(site, page_slug, section_type, variant, props, position)
    if not section:
        return jsonify({"success": False, "error": "Failed to add section"}), 400
    cms_save_project(slug, site)
    return jsonify({"success": True, "section": section})

# --- CMS: Update section ---
@app.route('/api/cms/projects/<slug>/sections/<section_id>', methods=['PUT'])
def cms_section_update(slug, section_id):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    page_slug = data.get("pageSlug", "/")
    updates = data.get("updates", {})
    ok = cms_update_section(site, page_slug, section_id, updates)
    if ok:
        cms_save_project(slug, site)
    return jsonify({"success": ok})

# --- CMS: Remove section ---
@app.route('/api/cms/projects/<slug>/sections/<section_id>', methods=['DELETE'])
def cms_section_remove(slug, section_id):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    page_slug = data.get("pageSlug", "/")
    ok = cms_remove_section(site, page_slug, section_id)
    if ok:
        cms_save_project(slug, site)
    return jsonify({"success": ok})

# --- CMS: Move section ---
@app.route('/api/cms/projects/<slug>/sections/<section_id>/move', methods=['POST'])
def cms_section_move(slug, section_id):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    page_slug = data.get("pageSlug", "/")
    new_index = data.get("newIndex", 0)
    ok = cms_move_section(site, page_slug, section_id, new_index)
    if ok:
        cms_save_project(slug, site)
    return jsonify({"success": ok})

# --- CMS: Add page ---
@app.route('/api/cms/projects/<slug>/pages', methods=['POST'])
def cms_page_add(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    title = data.get("title", "Neue Seite")
    page_slug = data.get("slug", "")
    page = cms_add_page(site, title, page_slug)
    if not page:
        return jsonify({"success": False, "error": "Slug already exists"}), 400
    cms_save_project(slug, site)
    return jsonify({"success": True, "page": page})

# --- CMS: Remove page ---
@app.route('/api/cms/projects/<slug>/pages/<path:page_slug>', methods=['DELETE'])
def cms_page_remove(slug, page_slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    ok = cms_remove_page(site, "/" + page_slug if not page_slug.startswith("/") else page_slug)
    if ok:
        cms_save_project(slug, site)
    return jsonify({"success": ok})

# --- CMS: Render preview ---
@app.route('/api/cms/projects/<slug>/preview', methods=['GET'])
def cms_preview(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    page_slug = request.args.get("page", "/")
    html_content = cms_render_page(site, page_slug)
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

# --- CMS: Live preview from posted site JSON (no save) ---
@app.route('/api/cms/preview-live', methods=['POST'])
def cms_preview_live():
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    data = request.get_json(force=True, silent=True) or {}
    site = data.get("site")
    page_slug = data.get("pageSlug", "/")
    if not site:
        return "No site data", 400
    html_content = cms_render_page(site, page_slug)
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

# --- CMS: Export static ---
@app.route('/api/cms/projects/<slug>/export', methods=['POST'])
def cms_export(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    result = cms_export_static(slug)
    return jsonify(result)

# --- CMS: Generate legal pages ---
@app.route('/api/cms/projects/<slug>/legal', methods=['POST'])
def cms_legal(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    site = cms_load_project(slug)
    if not site:
        return jsonify({"success": False, "error": "Project not found"}), 404
    legal = cms_generate_legal(site)
    return jsonify({"success": True, **legal})

# --- CMS: Upload media ---
@app.route('/api/cms/projects/<slug>/media', methods=['POST'])
def cms_media_upload(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    from ailey_system.cms.schema import CMS_BASE
    media_dir = os.path.join(CMS_BASE, slug, "media")
    os.makedirs(media_dir, exist_ok=True)

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Sanitize filename
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', f.filename)
    filepath = os.path.join(media_dir, safe_name)
    f.save(filepath)

    return jsonify({
        "success": True,
        "filename": safe_name,
        "url": f"/api/cms/projects/{slug}/media/{safe_name}",
    })

# --- CMS: Serve media ---
@app.route('/api/cms/projects/<slug>/media/<filename>')
def cms_media_serve(slug, filename):
    from ailey_system.cms.schema import CMS_BASE
    media_dir = os.path.join(CMS_BASE, slug, "media")
    return send_from_directory(media_dir, filename)

# --- CMS: List media ---
@app.route('/api/cms/projects/<slug>/media', methods=['GET'])
def cms_media_list(slug):
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503
    from ailey_system.cms.schema import CMS_BASE
    media_dir = os.path.join(CMS_BASE, slug, "media")
    if not os.path.isdir(media_dir):
        return jsonify({"success": True, "files": []})
    files = []
    for name in sorted(os.listdir(media_dir)):
        fpath = os.path.join(media_dir, name)
        if os.path.isfile(fpath):
            files.append({
                "filename": name,
                "url": f"/api/cms/projects/{slug}/media/{name}",
                "size": os.path.getsize(fpath),
            })
    return jsonify({"success": True, "files": files})


# --- CMS: AI Website Generator ---
@app.route('/api/cms/ai/generate', methods=['POST'])
def cms_ai_generate():
    """Use Ailey's LLM to generate a complete site.json from a natural language prompt."""
    if not CMS_AVAILABLE:
        return jsonify({"success": False, "error": "CMS not available"}), 503

    data = request.get_json(force=True, silent=True) or {}
    prompt = data.get("prompt", "").strip()
    project_slug = data.get("projectSlug")  # optional: update existing project

    if not prompt:
        return jsonify({"success": False, "error": "Prompt is required"}), 400

    # Build system prompt that instructs the LLM to output valid site.json
    # We give it the list of available section types
    available_types = list(SECTION_TEMPLATES.keys())

    system_prompt = f"""Du bist ein professioneller Webdesigner-AI. Der User beschreibt eine Website und du generierst dafür eine vollständige JSON-Struktur.

VERFÜGBARE SECTION-TYPES (nutze NUR diese):
{', '.join(available_types)}

REGELN:
1. Antworte AUSSCHLIESSLICH mit validem JSON — kein Markdown, kein Text drumherum.
2. Das JSON muss diesem Schema folgen:
{{
  "title": "Seitentitel",
  "design": {{
    "colors": {{ "primary": "#hex", "secondary": "#hex", "accent": "#hex", "background": "#hex", "surface": "#hex", "text": "#hex", "text-muted": "#hex", "border": "#hex" }}
  }},
  "pages": [
    {{
      "slug": "/",
      "title": "Home",
      "sections": [
        {{ "type": "SECTION_TYPE_AUS_LISTE", "variant": "optional", "props": {{ ... passende Props für den Type }} }}
      ]
    }}
  ],
  "nav": {{
    "links": [ {{ "label": "Name", "href": "#anchor" }} ],
    "cta": {{ "text": "CTA Text", "href": "#contact" }} oder null
  }},
  "footer": {{
    "copyright": "© 2026 Firmenname",
    "columns": [ {{ "title": "Titel", "links": [{{ "label": "Link", "href": "/" }}] }} ],
    "legalLinks": [ {{ "label": "Impressum", "href": "/impressum" }}, {{ "label": "Datenschutz", "href": "/datenschutz" }} ]
  }}
}}
3. Schreibe ECHTE, realistische Texte passend zum Business — keine Platzhalter wie "Lorem ipsum"!
4. Wähle passende Farben, die zum Business passen.
5. Erstelle mindestens 5-8 Sections pro Seite für eine vollständige Website.
6. Füge sinnvolle Nav-Links hinzu die zu den Section-IDs passen (z.B. #about, #services, #contact).
"""

    user_prompt = f"Erstelle eine professionelle Website für: {prompt}"

    try:
        # Use AileyCore's process_message for LLM inference
        result = core.process_message(
            f"[SYSTEM-INTERNAL CMS GENERATOR — Antworte NUR mit JSON]\n\n{system_prompt}\n\nANFRAGE: {user_prompt}",
            user="CMS-Generator",
            user_max_tokens=4096
        )
        response_text = result.get("response", "")

        # Extract JSON from response (handle markdown code blocks)
        import re as _re
        json_match = _re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', response_text)
        if json_match:
            json_str = json_match.group(1)
        elif response_text.strip().startswith('{'):
            # Find the last closing brace for the top-level object
            depth = 0
            end = 0
            for i, ch in enumerate(response_text.strip()):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            json_str = response_text.strip()[:end] if end > 0 else response_text.strip()
        else:
            return jsonify({"success": False, "error": "AI hat kein valides JSON generiert. Versuche es nochmal mit einem klareren Prompt.", "raw": response_text[:500]}), 400

        try:
            ai_data = json.loads(json_str)
        except json.JSONDecodeError as je:
            return jsonify({"success": False, "error": f"JSON-Parse-Fehler: {str(je)}", "raw": json_str[:500]}), 400

        # Build a proper site.json from AI output
        title = ai_data.get("title", prompt[:50])
        site = create_blank_site(title)

        # Apply AI-generated design colors
        if "design" in ai_data and "colors" in ai_data["design"]:
            for ck, cv in ai_data["design"]["colors"].items():
                if ck in site["design"]["colors"] and isinstance(cv, str):
                    site["design"]["colors"][ck] = cv

        # Apply AI-generated pages
        if "pages" in ai_data and isinstance(ai_data["pages"], list):
            site["pages"] = []
            for pg in ai_data["pages"]:
                page = {
                    "slug": pg.get("slug", "/"),
                    "title": pg.get("title", "Seite"),
                    "meta": {"description": ""},
                    "sections": []
                }
                for sec_data in pg.get("sections", []):
                    sec_type = sec_data.get("type", "")
                    if sec_type in SECTION_TEMPLATES:
                        try:
                            section = create_section(sec_type, sec_data.get("variant", ""), sec_data.get("props"))
                            page["sections"].append(section)
                        except Exception:
                            pass  # Skip invalid sections
                site["pages"].append(page)

        # Apply nav
        if "nav" in ai_data:
            if "links" in ai_data["nav"]:
                site["nav"]["links"] = [l for l in ai_data["nav"]["links"] if isinstance(l, dict) and "label" in l]
            if "cta" in ai_data["nav"] and ai_data["nav"]["cta"]:
                site["nav"]["cta"] = ai_data["nav"]["cta"]

        # Apply footer
        if "footer" in ai_data:
            if "copyright" in ai_data["footer"]:
                site["footer"]["copyright"] = ai_data["footer"]["copyright"]
            if "columns" in ai_data["footer"]:
                site["footer"]["columns"] = ai_data["footer"]["columns"]
            if "legalLinks" in ai_data["footer"]:
                site["footer"]["legalLinks"] = ai_data["footer"]["legalLinks"]

        # Save
        if project_slug:
            # Update existing project
            cms_save_project(project_slug, site)
            slug = project_slug
        else:
            slug, _ = cms_create_project(title)
            cms_save_project(slug, site)

        print(f"[CMS AI] ✅ Generated website '{title}' → /{slug} ({sum(len(p.get('sections',[])) for p in site['pages'])} sections)")
        return jsonify({"success": True, "slug": slug, "title": title, "sectionCount": sum(len(p.get('sections',[])) for p in site['pages'])})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"AI-Generierung fehlgeschlagen: {str(e)}"}), 500


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  LEARNING API — Interactive course system with hardcoded + LLM-driven  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_learning_engine = None  # lazy init


def _get_learning_engine() -> LearningEngine:
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine(core=core, get_generator=MLXGenerator.get)
    return _learning_engine


# ── Tracks overview ──────────────────────────────────────────────

@app.route('/api/learning/tracks', methods=['GET'])
def api_learning_tracks():
    """List all available learning tracks with metadata."""
    from ailey_system.learning.curricula import get_track_summary
    return jsonify({"success": True, "tracks": get_track_summary()})


@app.route('/api/learning/track/<track_id>', methods=['GET'])
def api_learning_track_detail(track_id):
    """Get a single track with all its units (global + user's custom units)."""
    track = get_track(track_id)
    if not track:
        return jsonify({"success": False, "error": "Track nicht gefunden"}), 404

    user_id = request.args.get("user_id", "simon")
    engine = _get_learning_engine()

    # Combine global + custom units
    all_units = list(track["units"])
    custom = engine._load_custom_units(user_id, track_id)
    all_units.extend(custom)

    # Strip quiz answers from response (prevent cheating)
    units = []
    for u in all_units:
        unit_safe = {k: v for k, v in u.items() if k != "quiz"}
        quiz_safe = []
        for q in u.get("quiz", []):
            q_entry = {
                "type": q["type"],
                "question": q["question"],
                "options": q.get("options", []),
                # Don't send correct answer / model_answers / key_points
            }
            if q["type"] == "open":
                q_entry["topic"] = q.get("topic", "")
            quiz_safe.append(q_entry)
        unit_safe["quiz"] = quiz_safe
        unit_safe["quiz_count"] = len(quiz_safe)
        unit_safe["is_custom"] = bool(u.get("created_by"))
        units.append(unit_safe)

    return jsonify({
        "success": True,
        "track": {
            "id": track["id"],
            "name": track["name"],
            "emoji": track.get("icon", track.get("emoji", "")),
            "description": track["description"],
            "units": units,
        }
    })


# ── Dashboard & Progress ─────────────────────────────────────────

@app.route('/api/learning/dashboard', methods=['GET'])
def api_learning_dashboard():
    """Get current user's learning dashboard (mainapp — always 'simon')."""
    engine = _get_learning_engine()
    user_id = request.args.get("user_id", "simon")
    return jsonify({"success": True, **engine.get_dashboard(user_id)})


@app.route('/api/learning/stats', methods=['GET'])
def api_learning_stats():
    """Get detailed learning statistics."""
    engine = _get_learning_engine()
    user_id = request.args.get("user_id", "simon")
    return jsonify({"success": True, **engine.get_stats(user_id)})


# ── Level setting ─────────────────────────────────────────────────

@app.route('/api/learning/level', methods=['POST'])
def api_learning_set_level():
    """Set entry level for a track (skip lower content)."""
    data = request.get_json(silent=True) or {}
    track_id = data.get("track_id")
    level = data.get("level", 0)
    user_id = data.get("user_id", "simon")

    if not track_id:
        return jsonify({"success": False, "error": "track_id erforderlich"}), 400
    if not get_track(track_id):
        return jsonify({"success": False, "error": "Track nicht gefunden"}), 404

    engine = _get_learning_engine()
    progress = engine.set_level(user_id, track_id, int(level))
    return jsonify({"success": True, "progress": progress})


# ── Unit content ──────────────────────────────────────────────────

@app.route('/api/learning/unit/<track_id>/<unit_id>', methods=['GET'])
def api_learning_unit(track_id, unit_id):
    """Get full unit content (theory, examples, quiz questions, exercise)."""
    user_id = request.args.get("user_id", "simon")
    engine = _get_learning_engine()
    content = engine.get_unit_content(track_id, unit_id, user_id)
    if not content:
        return jsonify({"success": False, "error": "Unit nicht gefunden"}), 404

    # Include quiz questions but strip answers for fair quizzing
    quiz_safe = []
    for q in content.get("quiz", []):
        q_safe = {
            "type": q["type"],
            "question": q["question"],
        }
        if q["type"] == "mc":
            q_safe["options"] = q.get("options", [])
        elif q["type"] == "match":
            # Shuffle the right column
            import random
            pairs = q.get("pairs", [])
            q_safe["left"] = [p[0] for p in pairs]
            rights = [p[1] for p in pairs]
            random.shuffle(rights)
            q_safe["right"] = rights
        elif q["type"] == "code":
            q_safe["starter"] = q.get("starter", "")
        elif q["type"] == "open":
            # Open questions: don't send model answers or key points (that's the answer!)
            pass  # Just question + type is enough
        q_safe["explanation"] = ""  # Don't reveal until answered
        quiz_safe.append(q_safe)
    content["quiz"] = quiz_safe

    return jsonify({"success": True, "unit": content})


@app.route('/api/learning/next/<track_id>', methods=['GET'])
def api_learning_next_unit(track_id):
    """Get the next uncompleted unit in a track."""
    user_id = request.args.get("user_id", "simon")
    engine = _get_learning_engine()
    unit = engine.get_next_unit(user_id, track_id)
    if not unit:
        return jsonify({"success": True, "unit": None, "track_complete": True})
    return jsonify({
        "success": True,
        "unit": {"id": unit["id"], "title": unit["title"], "level": unit["level"]},
        "track_complete": False,
    })


# ── Quiz evaluation ──────────────────────────────────────────────

@app.route('/api/learning/quiz/evaluate', methods=['POST'])
def api_learning_quiz_evaluate():
    """Evaluate a hardcoded quiz and update progress."""
    data = request.get_json(silent=True) or {}
    track_id = data.get("track_id")
    unit_id = data.get("unit_id")
    answers = data.get("answers", [])
    user_id = data.get("user_id", "simon")

    if not track_id or not unit_id:
        return jsonify({"success": False, "error": "track_id und unit_id erforderlich"}), 400

    engine = _get_learning_engine()
    result = engine.evaluate_quiz(user_id, track_id, unit_id, answers)
    if "error" in result:
        return jsonify({"success": False, **result}), 404
    return jsonify({"success": True, **result})


# ── LLM-driven teaching ──────────────────────────────────────────

@app.route('/api/learning/lesson', methods=['POST'])
def api_learning_lesson():
    """Generate an interactive lesson explanation via LLM."""
    data = request.get_json(silent=True) or {}
    track_id = data.get("track_id")
    unit_id = data.get("unit_id")
    question = data.get("question", "")
    user_id = data.get("user_id", "simon")

    if not track_id or not unit_id:
        return jsonify({"success": False, "error": "track_id und unit_id erforderlich"}), 400

    engine = _get_learning_engine()
    response = engine.generate_lesson(user_id, track_id, unit_id, question)
    if response is None:
        return jsonify({"success": False, "error": "Lektion konnte nicht generiert werden"}), 500
    return jsonify({"success": True, "lesson": response})


@app.route('/api/learning/exercise/evaluate', methods=['POST'])
def api_learning_exercise_evaluate():
    """Evaluate a code exercise via LLM."""
    data = request.get_json(silent=True) or {}
    track_id = data.get("track_id")
    unit_id = data.get("unit_id")
    code = data.get("code", "")
    user_id = data.get("user_id", "simon")

    if not track_id or not unit_id or not code:
        return jsonify({"success": False, "error": "track_id, unit_id und code erforderlich"}), 400

    engine = _get_learning_engine()
    result = engine.evaluate_code_exercise(user_id, track_id, unit_id, code)
    if result is None:
        return jsonify({"success": False, "error": "Code-Bewertung fehlgeschlagen"}), 500
    return jsonify({"success": True, **result})


@app.route('/api/learning/practice', methods=['POST'])
def api_learning_practice():
    """Generate additional practice questions via LLM."""
    data = request.get_json(silent=True) or {}
    track_id = data.get("track_id")
    level = data.get("level")
    count = data.get("count", 5)
    user_id = data.get("user_id", "simon")

    if not track_id:
        return jsonify({"success": False, "error": "track_id erforderlich"}), 400

    engine = _get_learning_engine()
    questions = engine.generate_practice_questions(user_id, track_id, level, count)
    if questions is None:
        return jsonify({"success": False, "error": "Fragen konnten nicht generiert werden"}), 500
    return jsonify({"success": True, "questions": questions})


# ── IHK Exam Focus ────────────────────────────────────────────

@app.route('/api/learning/exam-topics', methods=['GET'])
def api_learning_exam_topics_get():
    """Get current IHK exam focus topics."""
    user_id = request.args.get("user_id", "simon")
    engine = _get_learning_engine()
    topics = engine.get_exam_topics(user_id)
    return jsonify({"success": True, "topics": topics})


@app.route('/api/learning/exam-topics', methods=['POST'])
def api_learning_exam_topics_set():
    """Set IHK exam topics to focus on."""
    data = request.get_json(silent=True) or {}
    topics = data.get("topics", [])
    user_id = data.get("user_id", "simon")

    if not topics or not isinstance(topics, list):
        return jsonify({"success": False, "error": "topics (Liste) erforderlich"}), 400

    engine = _get_learning_engine()
    engine.set_exam_topics(user_id, topics)
    return jsonify({"success": True, "topics": topics})


@app.route('/api/learning/exam-drill', methods=['POST'])
def api_learning_exam_drill():
    """Generate focused exam practice questions for IHK topics."""
    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "")
    count = data.get("count", 5)
    user_id = data.get("user_id", "simon")

    engine = _get_learning_engine()
    questions = engine.generate_exam_drill(user_id, topic, count)
    if questions is None:
        return jsonify({"success": False, "error": "Prüfungsfragen konnten nicht generiert werden"}), 500
    return jsonify({"success": True, "questions": questions})


@app.route('/api/learning/exam-summary', methods=['POST'])
def api_learning_exam_summary():
    """Generate a study summary for a specific IHK exam topic."""
    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "")
    user_id = data.get("user_id", "simon")

    if not topic:
        return jsonify({"success": False, "error": "topic erforderlich"}), 400

    engine = _get_learning_engine()
    summary = engine.generate_exam_summary(user_id, topic)
    if summary is None:
        return jsonify({"success": False, "error": "Zusammenfassung konnte nicht generiert werden"}), 500
    return jsonify({"success": True, "summary": summary})


# ── Spaced Repetition ─────────────────────────────────────────

@app.route('/api/learning/review', methods=['GET'])
def api_learning_review():
    """Get spaced repetition review questions (questions the user got wrong)."""
    user_id = request.args.get("user_id", "simon")
    track_id = request.args.get("track_id", "ihk_mediengestalter")
    count = int(request.args.get("count", 10))

    engine = _get_learning_engine()
    questions = engine.get_review_questions(user_id, track_id, count)
    # Sanitize: don't send answers
    safe_questions = []
    for q in questions:
        q_safe = {
            "type": q["type"],
            "question": q["question"],
            "_sr_unit_id": q.get("_sr_unit_id"),
            "_sr_idx": q.get("_sr_idx"),
            "_sr_interval": q.get("_sr_interval"),
        }
        if q["type"] == "mc":
            q_safe["options"] = q.get("options", [])
        safe_questions.append(q_safe)
    return jsonify({"success": True, "questions": safe_questions, "count": len(safe_questions)})


@app.route('/api/learning/review/answer', methods=['POST'])
def api_learning_review_answer():
    """Submit an answer for a spaced repetition review question."""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "simon")
    track_id = data.get("track_id", "ihk_mediengestalter")
    unit_id = data.get("unit_id")
    question_idx = data.get("question_idx")
    correct = data.get("correct")

    if unit_id is None or question_idx is None or correct is None:
        return jsonify({"success": False, "error": "unit_id, question_idx und correct erforderlich"}), 400

    engine = _get_learning_engine()
    engine.update_review_result(user_id, track_id, unit_id, int(question_idx), bool(correct))
    return jsonify({"success": True})


# ── Custom / AI-Generated Units ──────────────────────────────────

@app.route('/api/learning/custom-units', methods=['GET'])
def api_learning_custom_units():
    """List a user's custom (AI-generated) units for a track."""
    user_id = request.args.get("user_id", "simon")
    track_id = request.args.get("track_id", "ihk_mediengestalter")

    engine = _get_learning_engine()
    units = engine._load_custom_units(user_id, track_id)
    # Return summary only (not full quiz data)
    summaries = []
    for u in units:
        summaries.append({
            "id": u["id"],
            "title": u.get("title", ""),
            "level": u.get("level", 3),
            "quiz_count": len(u.get("quiz", [])),
            "created_at": u.get("created_at"),
            "topic_request": u.get("topic_request", ""),
            "tags": u.get("tags", []),
        })
    return jsonify({"success": True, "units": summaries})


@app.route('/api/learning/custom-units/generate', methods=['POST'])
def api_learning_generate_custom_unit():
    """Have Ailey generate a brand-new learning unit on a user-requested topic."""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "simon")
    track_id = data.get("track_id", "ihk_mediengestalter")
    topic = data.get("topic", "")
    count = data.get("question_count", 10)

    if not topic:
        return jsonify({"success": False, "error": "topic erforderlich"}), 400

    engine = _get_learning_engine()
    unit = engine.generate_custom_unit(user_id, track_id, topic, int(count))
    if unit is None:
        return jsonify({"success": False, "error": "Lerneinheit konnte nicht generiert werden"}), 500

    return jsonify({
        "success": True,
        "unit": {
            "id": unit["id"],
            "title": unit.get("title", ""),
            "level": unit.get("level", 3),
            "theory": unit.get("theory", ""),
            "quiz_count": len(unit.get("quiz", [])),
            "created_at": unit.get("created_at"),
        },
    })


# ── IHK Prüfungsthemen 2026 — Übersicht ─────────────────────────

@app.route('/api/learning/ihk-pruefung-2026', methods=['GET'])
def api_learning_ihk_pruefung_2026():
    """Get an overview of all IHK Prüfungsthemen 2026 units."""
    try:
        from ailey_system.learning.ihk_pruefung_2026 import (
            IHK_PRUEFUNG_2026_UNITS, TOTAL_QUESTIONS, TOTAL_OPEN, TOTAL_MC, TOTAL_TF
        )
        units_overview = []
        for u in IHK_PRUEFUNG_2026_UNITS:
            quiz = u.get("quiz", [])
            units_overview.append({
                "id": u["id"],
                "title": u["title"],
                "exam_area": u.get("exam_area", ""),
                "total_questions": len(quiz),
                "open_questions": sum(1 for q in quiz if q["type"] == "open"),
                "mc_questions": sum(1 for q in quiz if q["type"] == "mc"),
                "tf_questions": sum(1 for q in quiz if q["type"] == "tf"),
                "tags": u.get("tags", []),
            })
        return jsonify({
            "success": True,
            "total_questions": TOTAL_QUESTIONS,
            "total_open": TOTAL_OPEN,
            "total_mc": TOTAL_MC,
            "total_tf": TOTAL_TF,
            "units": units_overview,
        })
    except ImportError as e:
        return jsonify({"success": False, "error": f"Prüfungsthemen-Modul nicht verfügbar: {e}"}), 500


# ── RAG Ingest: Prüfungsthemen ins RAG laden ─────────────────────

@app.route('/api/learning/ingest-pruefung-rag', methods=['POST'])
def api_learning_ingest_pruefung_rag():
    """Ingest the IHK Prüfungsthemen 2026 into the learning RAG.

    This makes the exam content searchable via Ailey's RAG —
    both in portal chat and in learning mode.
    """
    try:
        from ailey_system.learning.ihk_pruefung_2026 import IHK_PRUEFUNG_2026_UNITS
        from ailey_system.learning.ihk_pruefung_2026_extended import IHK_PRUEFUNG_2026_EXTENDED_UNITS
        from ailey_system.ailey_rag_lance import AileyRAG

        rag = AileyRAG(user_id="learning_global")
        ingested = 0

        all_units = list(IHK_PRUEFUNG_2026_UNITS) + list(IHK_PRUEFUNG_2026_EXTENDED_UNITS)

        for u in all_units:
            # Ingest theory as a document
            theory_text = u.get("theory", "")
            if theory_text:
                rag.add_document(
                    title=f"IHK Prüfung 2026: {u['title']}",
                    text=theory_text,
                    doc_type="learning_ihk",
                )
                ingested += 1

            # Ingest questions + model answers as searchable content
            for i, q in enumerate(u.get("quiz", [])):
                q_text = f"Frage: {q['question']}"
                if q.get("model_answers"):
                    q_text += "\n\nMusterantworten:\n" + "\n".join(
                        f"- {ma}" for ma in q["model_answers"]
                    )
                if q.get("key_points"):
                    q_text += "\n\nSchlüsselbegriffe: " + ", ".join(q["key_points"])
                if q.get("explanation"):
                    q_text += f"\n\nErklärung: {q['explanation']}"
                if q["type"] == "mc" and q.get("options"):
                    correct_idx = q.get("correct", 0)
                    q_text += f"\n\nKorrekte Antwort: {q['options'][correct_idx]}"
                if u.get("fachrichtung"):
                    q_text += f"\n\nFachrichtung: {u['fachrichtung']}"
                if u.get("exam_area"):
                    q_text += f"\n\nPrüfungsbereich: {u['exam_area']}"

                rag.add_document(
                    title=f"IHK 2026 — {u['title']} — Frage {i+1} ({q.get('topic', '')})",
                    text=q_text,
                    doc_type="learning_ihk",
                )
                ingested += 1

        return jsonify({
            "success": True,
            "ingested": ingested,
            "units": len(all_units),
            "message": f"{ingested} Dokumente aus {len(all_units)} Units ins Learning-RAG geladen (Original + Extended)",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Emergency: Clear All Pending Jobs ──────────────────────────
# Called by ailey_remote.py "Clear Pending" button to unstick the system.
@app.post('/api/system/clear-pending')
def api_system_clear_pending():
    """Reset all in-process generation jobs + clear portal queue."""
    global _image_gen_job, _music_gen_job, _video_gen_job, _upscale_job
    cleared = []

    # 1. Reset image gen job
    if _image_gen_job.get("active"):
        cleared.append(f"image (was: {_image_gen_job.get('progress', '?')})")
    _image_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "prompt_used": ""}

    # 2. Reset music gen job
    if _music_gen_job.get("active"):
        cleared.append(f"music (was: {_music_gen_job.get('progress', '?')})")
    _music_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "song_id": ""}

    # 3. Reset video gen job
    if _video_gen_job.get("active"):
        cleared.append(f"video (was: {_video_gen_job.get('progress', '?')})")
    _video_gen_job = {"active": False, "progress": "", "result": None, "started": 0.0, "prompt_used": ""}

    # 4. Reset upscale job
    if _upscale_job.get("active"):
        cleared.append(f"upscale (was: {_upscale_job.get('progress', '?')})")
    _upscale_job = {"active": False, "progress": "", "result": None, "started": 0.0, "filename": ""}

    # 5. Reset idle_thinker image gen flag
    _idle = globals().get('idle_thinker')
    if _idle and getattr(_idle, '_generating_image', False):
        _idle._generating_image = False
        cleared.append("idle_thinker._generating_image")

    # 6. Unblock LLM auto-reload (in case it was blocked for image gen)
    try:
        from ailey_system.llm_mlx import allow_auto_reload, _auto_reload_blocked
        if _auto_reload_blocked:
            allow_auto_reload()
            cleared.append("llm_auto_reload unblocked")
    except Exception:
        pass

    # 7. Kill orphaned subprocesses
    import subprocess as _sp
    for pattern in ["mflux-generate", "mflux-upscale", "acestep", "seedvr2"]:
        try:
            result = _sp.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=3)
            for pid_str in result.stdout.strip().split():
                try:
                    os.kill(int(pid_str), signal.SIGTERM)
                    cleared.append(f"killed {pattern} PID {pid_str}")
                except Exception:
                    pass
        except Exception:
            pass

    print(f"[System] 🧹 Clear-Pending: {cleared or ['nothing was stuck']}")
    return jsonify({
        "success": True,
        "cleared": cleared,
        "message": f"Cleared {len(cleared)} items" if cleared else "Nothing was stuck",
    })


# ═══════════════════════════════════════════════════════════════════
#  TRAINING DATA COLLECTOR API
# ═══════════════════════════════════════════════════════════════════

_TRAINING_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dora_training", "collected")
os.makedirs(_TRAINING_DATA_DIR, exist_ok=True)

_TRAINING_GOLD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dora_training", "gold_candidates")
os.makedirs(_TRAINING_GOLD_DIR, exist_ok=True)


# ── Live Training Pair Collector ────────────────────────────────
import threading as _training_threading

_training_lock = _training_threading.Lock()


def _collect_training_pair(
    *,
    user_prompt: str,
    assistant_response: str,
    reasoning: str = "",
    tool_actions: list = None,
    source: str = "live_chat",
    user_type: str = "simon",
    mood: str = "neutral",
    topics: list = None,
    flags: list = None,
    is_gold_candidate: bool = False,
    rating_score: float = 0,
    rated_by: str = "",
    session_key: str = "",
    session_label: str = "",
    engine: str = "",
):
    """Auto-collect a training pair. Groups into sessions:
    - Portal: session_key = conv_id → all messages in one conversation = 1 session
    - Chat:   session_key = date   → all chat pairs of one day = 1 session
    - Idle:   session_key = ""     → always individual
    - Gold:   always individual candidate files
    """
    import threading
    def _save():
        try:
            # Skip trivially short exchanges
            if len(user_prompt.strip()) < 10 or len(assistant_response.strip()) < 20:
                return
            # Block known noisy/unsafe engines (hamster, codeailey)
            if engine and engine.lower() in ("hamster", "codeailey"):
                print(f"[Training] ⚠️ Skip collect from blocked engine: {engine}")
                return
            # Skip obvious hamster markers in text
            lowu = user_prompt.lower()
            if "hamster" in lowu or "hamster:" in lowu:
                print("[Training] ⚠️ Skip collect: hamster mention in prompt")
                return
            # Avoid collecting Nitro outputs for conversational contexts (chat, portal)
            # Nitro is optimized for speed, not chat-quality training data
            if engine and engine.lower() == "nitro":
                _src_low = source.lower()
                if "chat" in _src_low or "portal" in _src_low:
                    print(f"[Training] ⚠️ Skip Nitro conversational output (source={source})")
                    return
            if any(k in user_prompt.lower() for k in ("modell ist gerade pausiert", "__musicgen__")):
                return

            ts = datetime.now(timezone.utc).isoformat()
            ts_slug = ts[:19].replace(":", "-").replace("T", "_")
            src_slug = re.sub(r'[^a-zA-Z0-9_-]', '', source.replace(" ", "_"))[:20]

            pair = {
                "id": f"{int(time.time())}_{src_slug}_{hash(user_prompt[:50]) % 10000:04d}",
                "user_prompt": user_prompt.strip(),
                "reasoning": reasoning.strip() if reasoning else "",
                "assistant_response": assistant_response.strip(),
                "timestamp": ts,
            }
            if tool_actions:
                pair["tool_decisions"] = [
                    {
                        "tool": ta.get("tool", "unknown"),
                        "needed": True,
                        "reason": ta.get("reason") or f"Auto-captured: {ta.get('tool', '')}",
                        "arguments": ta.get("arguments", {}),
                        "result_success": (ta.get("result") or {}).get("success", False),
                        # Full tool result/content for training (website text, search hits, etc.)
                        "result_content": (
                            (ta.get("result") or {}).get("content")
                            or (ta.get("result") or {}).get("text")
                            or (ta.get("result") or {}).get("data")
                            or (ta.get("result") or {}).get("output")
                            or ""
                        ),
                        "result_summary": (ta.get("result") or {}).get("summary", ""),
                        # Model's interpretation of the tool result, if captured
                        "model_reaction": ta.get("model_reaction", ""),
                    }
                    for ta in tool_actions
                ]

            # Always record mood + engine + topics in pair metadata so we can
            # filter/analyze later, even when per-pair metadata wasn't exposed
            # to the user UI.
            pair["mood"] = mood or "neutral"
            if engine:
                pair["engine"] = engine
            if topics:
                pair["topics"] = list(topics)

            _flags = list(flags or [])
            if reasoning:
                _flags.append("has_reasoning")
            if tool_actions:
                _flags.append("has_tool_use")

            # ── Gold candidates: always individual files ──────
            if is_gold_candidate:
                session = {
                    "id": pair["id"],
                    "timestamp": ts,
                    "name": f"Gold {rated_by} {ts_slug[:10]}",
                    "meta": {
                        "source": source,
                        "user_type": user_type,
                        "mood": mood,
                        "topics": topics or [],
                        "flags": _flags,
                    },
                    "pairs": [pair],
                    "curated": False,
                    "auto_collected": True,
                    "gold_candidate": True,
                    "rating_score": rating_score,
                    "rated_by": rated_by,
                }
                filename = f"gold_{ts_slug}_{src_slug}.json"
                fpath = os.path.join(_TRAINING_GOLD_DIR, filename)
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(session, f, ensure_ascii=False, indent=2)
                print(f"[Training] ⭐ Gold candidate: {filename}")
                return

            # ── Session grouping logic ────────────────────────
            # Determine filename based on session_key
            today = ts[:10]  # 2026-04-20
            if session_key:
                # Portal conversation or explicit grouping
                safe_key = re.sub(r'[^a-zA-Z0-9_-]', '', session_key)[:40]
                filename = f"session_{src_slug}_{safe_key}_{today}.json"
            elif source.startswith("live_chat"):
                # Chat: group by day
                filename = f"session_chat_{today}.json"
            elif source.startswith("live_portal"):
                # Portal without conv_id: group by day + user
                safe_user = re.sub(r'[^a-zA-Z0-9_-]', '', user_type)[:20]
                filename = f"session_portal_{safe_user}_{today}.json"
            else:
                # Idle thinker / other: always individual
                filename = f"single_{ts_slug}_{src_slug}.json"

            fpath = os.path.join(_TRAINING_DATA_DIR, filename)

            with _training_lock:
                # Append to existing session or create new one
                if os.path.isfile(fpath):
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            session = json.load(f)
                        session["pairs"].append(pair)
                        session["updated_at"] = ts
                        # Merge flags
                        existing_flags = set(session.get("meta", {}).get("flags", []))
                        existing_flags.update(_flags)
                        session["meta"]["flags"] = list(existing_flags)
                    except Exception:
                        session = None  # corrupt, recreate

                if not os.path.isfile(fpath) or session is None:
                    label = session_label or f"Live {source} {today}"
                    session = {
                        "id": f"{src_slug}_{today}_{session_key or 'default'}",
                        "timestamp": ts,
                        "name": label,
                        "meta": {
                            "source": source,
                            "user_type": user_type,
                            "mood": mood,
                            "topics": topics or [],
                            "flags": _flags,
                        },
                        "pairs": [pair],
                        "curated": False,
                        "auto_collected": True,
                        "category": _source_to_category(source),
                    }

                session["category"] = _source_to_category(source)

                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(session, f, ensure_ascii=False, indent=2)

            n = len(session.get("pairs", []))
            print(f"[Training] 📥 Collected → {filename} ({n} pairs)")
        except Exception as e:
            print(f"[Training] ⚠️ Auto-collect failed: {e}")
    threading.Thread(target=_save, daemon=True).start()


def _source_to_category(source: str) -> str:
    """Map source string to display category."""
    s = source.lower()
    if "portal" in s:
        return "portal"
    if "chat" in s:
        return "chat"
    if "idle" in s or "thinker" in s:
        return "idle"
    if "rating" in s:
        return "gold"
    return "other"


@app.route('/api/training/sessions', methods=['GET'])
def training_list_sessions():
    """List all saved training sessions with metadata."""
    try:
        sessions = []
        for fname in sorted(os.listdir(_TRAINING_DATA_DIR)):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_TRAINING_DATA_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("id", fname),
                    "timestamp": data.get("timestamp", ""),
                    "pair_count": len(data.get("pairs", [])),
                    "source": data.get("meta", {}).get("source", "unknown"),
                    "name": data.get("name", fname.replace(".json", "")),
                    "filename": fname,
                    "curated": data.get("curated", False),
                    "auto_collected": data.get("auto_collected", False),
                    "category": data.get("category", _source_to_category(data.get("meta", {}).get("source", ""))),
                })
            except Exception:
                continue
        return jsonify({"success": True, "sessions": sessions, "total": len(sessions)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/sessions', methods=['POST'])
def training_save_session():
    """Save a new training session."""
    try:
        payload = request.get_json(force=True)
        session = payload.get("session")
        if not session or not session.get("pairs"):
            return jsonify({"success": False, "error": "No pairs provided"}), 400

        # Build filename from timestamp + optional name
        ts = session.get("timestamp", datetime.now(timezone.utc).isoformat())
        ts_slug = ts[:19].replace(":", "-").replace("T", "_")
        name_slug = ""
        if payload.get("name"):
            import re as _re_train
            name_slug = "_" + _re_train.sub(r'[^a-zA-Z0-9_-]', '', payload["name"].replace(" ", "_"))[:40]

        filename = f"session_{ts_slug}{name_slug}.json"
        fpath = os.path.join(_TRAINING_DATA_DIR, filename)

        # Enrich session with save metadata
        session["saved_at"] = datetime.now(timezone.utc).isoformat()
        if payload.get("name"):
            session["name"] = payload["name"]

        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        pair_count = len(session.get("pairs", []))
        print(f"[Training] 💾 Session saved: {filename} ({pair_count} pairs)")
        return jsonify({
            "success": True,
            "filename": filename,
            "pair_count": pair_count,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/sessions/<path:filename>', methods=['GET'])
def training_get_session(filename):
    """Load a single training session by filename."""
    try:
        fpath = os.path.join(_TRAINING_DATA_DIR, filename)
        if not os.path.isfile(fpath):
            return jsonify({"success": False, "error": "Session not found"}), 404
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "session": data, "filename": filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/sessions/<path:filename>', methods=['PUT'])
def training_update_session(filename):
    """Update an existing training session (overwrite)."""
    try:
        fpath = os.path.join(_TRAINING_DATA_DIR, filename)
        if not os.path.isfile(fpath):
            return jsonify({"success": False, "error": "Session not found"}), 404
        payload = request.get_json(force=True)
        session = payload.get("session")
        if not session or not session.get("pairs"):
            return jsonify({"success": False, "error": "No pairs provided"}), 400
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        pair_count = len(session.get("pairs", []))
        print(f"[Training] ✏️  Session updated: {filename} ({pair_count} pairs)")
        return jsonify({"success": True, "filename": filename, "pair_count": pair_count})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/sessions/<path:filename>/curated', methods=['PATCH'])
def training_toggle_curated(filename):
    """Quick-toggle the curated flag on a session without full rewrite."""
    try:
        fpath = os.path.join(_TRAINING_DATA_DIR, filename)
        if not os.path.isfile(fpath):
            return jsonify({"success": False, "error": "Session not found"}), 404
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        payload = request.get_json(force=True)
        data["curated"] = payload.get("curated", not data.get("curated", False))
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Training] {'✅' if data['curated'] else '⬜'} Curated toggled: {filename} → {data['curated']}")
        return jsonify({"success": True, "curated": data["curated"], "filename": filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/export', methods=['GET'])
def training_export_jsonl():
    """Export all collected sessions as a single JSONL file for training."""
    try:
        all_pairs = []
        for fname in sorted(os.listdir(_TRAINING_DATA_DIR)):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_TRAINING_DATA_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                meta = data.get("meta", {})
                for pair in data.get("pairs", []):
                    entry = {
                        "messages": [],
                        "meta": {
                            "user_type": meta.get("user_type", "unknown"),
                            "mood": meta.get("mood", "neutral"),
                            "topics": meta.get("topics", []),
                            "flags": meta.get("flags", []),
                            "source": meta.get("source", "unknown"),
                            "session_id": data.get("id", ""),
                        },
                    }
                    # Build messages in chat format
                    entry["messages"].append({
                        "role": "user",
                        "content": pair.get("user_prompt", ""),
                    })
                    if pair.get("reasoning") and pair["reasoning"] != "<<REASONING_TODO>>":
                        entry["messages"].append({
                            "role": "thinking",
                            "content": pair["reasoning"],
                        })
                    entry["messages"].append({
                        "role": "assistant",
                        "content": pair.get("assistant_response", ""),
                    })
                    # Preserve tool decisions in meta if present
                    if pair.get("tool_decisions"):
                        entry["meta"]["tool_decisions"] = pair["tool_decisions"]
                    all_pairs.append(entry)
            except Exception:
                continue

        # Write JSONL
        export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dora_training")
        export_path = os.path.join(export_dir, "collected_export.jsonl")
        with open(export_path, 'w', encoding='utf-8') as f:
            for entry in all_pairs:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"[Training] 📤 Exported {len(all_pairs)} pairs → {export_path}")
        return jsonify({
            "success": True,
            "total_pairs": len(all_pairs),
            "file": export_path,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/stats', methods=['GET'])
def training_stats():
    """Quick stats about collected training data."""
    try:
        total_sessions = 0
        total_pairs = 0
        sources = {}
        for fname in os.listdir(_TRAINING_DATA_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_TRAINING_DATA_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                total_sessions += 1
                pc = len(data.get("pairs", []))
                total_pairs += pc
                src = data.get("meta", {}).get("source", "unknown")
                sources[src] = sources.get(src, 0) + pc
            except Exception:
                continue
        return jsonify({
            "success": True,
            "total_sessions": total_sessions,
            "total_pairs": total_pairs,
            "by_source": sources,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/sessions/<path:filename>', methods=['DELETE'])
def training_delete_session(filename):
    """Delete a training session file."""
    try:
        # Check both collected and gold_candidates dirs
        for d in (_TRAINING_DATA_DIR, _TRAINING_GOLD_DIR):
            fpath = os.path.join(d, filename)
            if os.path.isfile(fpath):
                os.remove(fpath)
                print(f"[Training] 🗑️ Deleted: {filename}")
                return jsonify({"success": True, "filename": filename})
        return jsonify({"success": False, "error": "Session not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/gold', methods=['GET'])
def training_list_gold():
    """List gold candidate sessions (from ratings / thumbs-up)."""
    try:
        sessions = []
        for fname in sorted(os.listdir(_TRAINING_GOLD_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(_TRAINING_GOLD_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("id", fname),
                    "timestamp": data.get("timestamp", ""),
                    "pair_count": len(data.get("pairs", [])),
                    "source": data.get("meta", {}).get("source", "unknown"),
                    "name": data.get("name", fname.replace(".json", "")),
                    "filename": fname,
                    "curated": data.get("curated", False),
                    "gold_candidate": True,
                    "rating_score": data.get("rating_score", 0),
                    "rated_by": data.get("rated_by", ""),
                })
            except Exception:
                continue
        return jsonify({"success": True, "sessions": sessions, "total": len(sessions)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/gold/<path:filename>', methods=['GET'])
def training_get_gold(filename):
    """Load a single gold candidate session."""
    try:
        fpath = os.path.join(_TRAINING_GOLD_DIR, filename)
        if not os.path.isfile(fpath):
            return jsonify({"success": False, "error": "Session not found"}), 404
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"success": True, "session": data, "filename": filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/training/gold/<path:filename>/promote', methods=['POST'])
def training_promote_gold(filename):
    """Promote a gold candidate → regular curated session."""
    try:
        src = os.path.join(_TRAINING_GOLD_DIR, filename)
        if not os.path.isfile(src):
            return jsonify({"success": False, "error": "Not found"}), 404
        with open(src, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data["curated"] = True
        data["promoted_from_gold"] = True
        data["promoted_at"] = datetime.now(timezone.utc).isoformat()
        dst_name = filename.replace("gold_", "promoted_")
        dst = os.path.join(_TRAINING_DATA_DIR, dst_name)
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.remove(src)
        print(f"[Training] ⭐→✅ Promoted: {filename} → {dst_name}")
        return jsonify({"success": True, "new_filename": dst_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    # ── Prevent loky/joblib semaphore leaks ─────────────────────
    # sentence-transformers → scikit-learn → joblib → loky creates POSIX
    # semaphores that survive process death. Limiting to 1 CPU prevents
    # multiprocessing and thus semaphore creation entirely.
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    # ── Venv-Doctor: Quick Health-Check & APFS-Schutz ───────────
    try:
        from ailey_system.venv_doctor import quick_startup_check, protect_all
        print("🩺 Venv Health-Check …")
        _venv_ok, _venv_issues = quick_startup_check()
        if _venv_ok:
            print("  ✅ Alle Environments intakt")
        else:
            print("  ⚠️  VENV-PROBLEME ERKANNT:")
            for _vi in _venv_issues:
                print(f"     ❌ {_vi}")
            print("     → Reparatur: bash repair_venv.sh / bash protect_venvs.sh")
        # Apply APFS protection silently (fast, ~0.5s)
        protect_all()
    except Exception as _doc_err:
        print(f"  ⚠️ Venv-Doctor nicht verfügbar: {_doc_err}")

    # ── Pre-warm SentenceTransformer in main thread ─────────────
    # MUST happen before background threads start, otherwise the lazy init
    # inside a daemon thread can deadlock with MLX Metal operations.
    try:
        print("🔤 Pre-warming SentenceTransformer embedder …")
        _prewarm_start = time.time()
        from ailey_system.ailey_rag_lance import AileyRAG as _PrewarmRAG
        _prewarm_rag = _PrewarmRAG("Simon")
        _prewarm_rag._embedder_get()  # force lazy-load in main thread
        print(f"✅ SentenceTransformer ready ({time.time() - _prewarm_start:.1f}s)")
    except Exception as _pw_err:
        print(f"⚠️ SentenceTransformer pre-warm failed (non-fatal): {_pw_err}")

    # When executed directly, start background services then the Flask dev server.
    start_services(
        preload_mlx=os.environ.get('AILEY_PRELOAD_MLX', '') in ('1', 'true', 'yes'),
    )
    port = int(os.environ.get('AILEY_API_PORT', 5502))
    # Default to IPv6 dual-stack ('::' accepts both IPv4 and IPv6 on macOS/Linux).
    # Critical for DS-Lite/CGNAT users (o2): IPv4 is CGNAT'd & unreachable from
    # outside, but IPv6 is direct. Dual-stack means LAN IPv4 + public IPv6 both work.
    host = os.environ.get('AILEY_API_HOST', '::')
    # Release the early sentinel socket so Flask can bind the port
    _release_early_port()
    print(f"Starting Ailey API on {host}:{port} ...")
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except Exception as e:
        # Ensure any startup exceptions are visible in logs
        import traceback
        traceback.print_exc()
        raise
