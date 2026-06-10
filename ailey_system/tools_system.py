# -*- coding: utf-8 -*-
"""
Ailey System Tools — macOS integration tools.

App control, clipboard, system info, screenshots, notifications, URL opening.
"""
from __future__ import annotations
import os
import subprocess
import json
import platform
import logging
from datetime import datetime

from .tools import register_tool
from .agent_config import run_subprocess

_log = logging.getLogger("ailey.tools_system")


# ─── Tool: Open App ─────────────────────────────────────────────────────────

@register_tool(
    name="open_app",
    description="Öffnet eine macOS-Anwendung (z.B. 'Safari', 'Finder', 'Terminal').",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name der App (z.B. 'Safari', 'Visual Studio Code', 'Finder')"
            }
        },
        "required": ["app_name"]
    }
)
def open_app(app_name: str) -> dict:
    """Open a macOS application."""
    try:
        result = run_subprocess(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return {"message": f"App geöffnet: {app_name}"}
        else:
            return {"error": f"App nicht gefunden: {app_name}. {result.stderr.strip()}"}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Open URL ─────────────────────────────────────────────────────────

@register_tool(
    name="open_url",
    description="Öffnet eine URL im Standard-Browser.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL zum Öffnen (z.B. 'https://google.com')"
            }
        },
        "required": ["url"]
    }
)
def open_url(url: str) -> dict:
    """Open a URL in the default browser."""
    try:
        run_subprocess(["open", url], capture_output=True, timeout=5)
        return {"message": f"URL geöffnet: {url}"}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Clipboard Read ───────────────────────────────────────────────────

@register_tool(
    name="clipboard_read",
    description="Liest den aktuellen Inhalt der Zwischenablage.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def clipboard_read() -> dict:
    """Read clipboard contents using pbpaste."""
    try:
        result = run_subprocess(["pbpaste"], capture_output=True, text=True, timeout=5)
        content = result.stdout
        if not content:
            return {"message": "Zwischenablage ist leer", "content": ""}
        
        # Truncate very long content
        if len(content) > 5000:
            content = content[:5000] + f"\n... ({len(content)} Zeichen gesamt)"
        
        return {
            "message": f"Zwischenablage ({len(result.stdout)} Zeichen)",
            "content": content,
        }
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Clipboard Write ──────────────────────────────────────────────────

@register_tool(
    name="clipboard_write",
    description="Schreibt Text in die Zwischenablage.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text der in die Zwischenablage geschrieben werden soll"
            }
        },
        "required": ["text"]
    }
)
def clipboard_write(text: str) -> dict:
    """Write text to clipboard using pbcopy."""
    try:
        # subprocess.Popen doesn't support our wrapper, keep using Popen but with fallback timeout
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        try:
            process.communicate(input=text.encode("utf-8"), timeout=5)
        except TypeError:
            # Python older implementations may not support timeout here; ignore
            process.communicate(input=text.encode("utf-8"))
        return {"message": f"In Zwischenablage kopiert ({len(text)} Zeichen)"}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: System Info ──────────────────────────────────────────────────────

@register_tool(
    name="system_info",
    description="Gibt System-Informationen zurück: OS, CPU, RAM, Speicherplatz, Batterie.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def system_info() -> dict:
    """Get system information."""
    try:
        info = {
            "os": platform.system(),
            "os_version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
            "arch": platform.machine(),
            "hostname": platform.node(),
            "python": platform.python_version(),
        }
        
        # CPU info
        try:
            result = run_subprocess(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5)
            info["cpu"] = result.stdout.strip()
        except:
            pass
        
        # RAM
        try:
            result = run_subprocess(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            ram_bytes = int(result.stdout.strip())
            info["ram_gb"] = round(ram_bytes / (1024**3), 1)
        except:
            pass
        
        # Disk space
        try:
            import shutil
            usage = shutil.disk_usage("/")
            info["disk_total_gb"] = round(usage.total / (1024**3), 1)
            info["disk_free_gb"] = round(usage.free / (1024**3), 1)
            info["disk_used_pct"] = round(usage.used / usage.total * 100, 1)
        except:
            pass
        
        # Battery
        try:
            result = run_subprocess(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
            import re
            batt = re.search(r"(\d+)%", result.stdout)
            if batt:
                info["battery_pct"] = int(batt.group(1))
                info["charging"] = "charging" in result.stdout.lower() or "ac power" in result.stdout.lower()
        except:
            pass
        
        # Format message
        parts = [f"💻 {info.get('hostname', '?')} — macOS {info.get('os_version', '?')} ({info.get('arch', '?')})"]
        if "cpu" in info:
            parts.append(f"CPU: {info['cpu']}")
        if "ram_gb" in info:
            parts.append(f"RAM: {info['ram_gb']} GB")
        if "disk_free_gb" in info:
            parts.append(f"Disk: {info['disk_free_gb']} GB frei ({info.get('disk_used_pct', '?')}% belegt)")
        if "battery_pct" in info:
            status = "⚡ laden" if info.get("charging") else "🔋"
            parts.append(f"Batterie: {info['battery_pct']}% {status}")
        
        return {"message": "\n".join(parts), **info}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Screenshot ───────────────────────────────────────────────────────

@register_tool(
    name="screenshot",
    description="Macht einen Screenshot des gesamten Bildschirms und speichert ihn.",
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Dateiname (optional, default: screenshot_<timestamp>.png)"
            }
        },
        "required": []
    }
)
def screenshot(filename: str = "") -> dict:
    """Take a screenshot."""
    try:
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        filepath = os.path.join(os.path.expanduser("~/Desktop"), filename)
        
        result = run_subprocess(["screencapture", "-x", filepath], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and os.path.isfile(filepath):
            size = os.path.getsize(filepath)
            return {
                "message": f"📸 Screenshot gespeichert: {filename} ({size // 1024} KB)",
                "path": filepath,
            }
        else:
            return {"error": f"Screenshot fehlgeschlagen: {result.stderr}"}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Notification ─────────────────────────────────────────────────────

@register_tool(
    name="notification",
    description="Sendet eine macOS-Benachrichtigung.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titel der Benachrichtigung"
            },
            "text": {
                "type": "string",
                "description": "Text der Benachrichtigung"
            },
            "sound": {
                "type": "string",
                "description": "Sound-Name (optional, z.B. 'Glass', 'Ping', 'Pop')"
            }
        },
        "required": ["title", "text"]
    }
)
def notification(title: str, text: str, sound: str = "Glass") -> dict:
    """Send a macOS notification."""
    try:
        script = f'display notification "{text}" with title "{title}" sound name "{sound}"'
        run_subprocess(["osascript", "-e", script], capture_output=True, timeout=5)
        return {"message": f"🔔 Benachrichtigung gesendet: {title}"}
    except Exception as e:
        return {"error": f"Fehler: {e}"}
