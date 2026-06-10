# -*- coding: utf-8 -*-
"""
Ailey Code Tools — File operations, project context, terminal, search.

All tools use the shared @register_tool decorator from tools.py
so they're automatically available via get_tool_schemas().
"""
from __future__ import annotations
import os
import json
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict

from .tools import register_tool
from .agent_config import AGENT_MODE, AGENT_TIMEOUT

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log = logging.getLogger("ailey.tools_code")


# ─── Safety helpers ──────────────────────────────────────────────────────────

def _safe_path(path: str, project_root: str = "") -> str:
    """Resolve path, make absolute using project_root if relative."""
    if project_root and not os.path.isabs(path):
        path = os.path.join(project_root, path)
    real = os.path.realpath(path)
    home = os.path.expanduser("~")
    if not real.startswith(home):
        raise PermissionError(f"Zugriff verweigert: {real}")
    return real


_BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){", "fork bomb",
    "shutdown", "reboot", "halt", "poweroff",
    "> /dev/sda", "chmod -R 777 /", "chown -R",
    # Git safety: no force push, no history rewrite on main
    "git push --force", "git push -f", "git reset --hard origin",
    "git clean -fdx /",
    # System safety
    "launchctl unload", "sudo rm", "sudo kill",
    "curl | sh", "curl | bash", "wget | sh",
]


# ─── Tool: Read File ────────────────────────────────────────────────────────

@register_tool(
    name="read_file",
    description=(
        "Liest den Inhalt einer Datei. Kann optional nur bestimmte Zeilen lesen. "
        "Nutze dieses Tool um Code zu verstehen bevor du Änderungen machst."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur Datei (relativ zum Projekt oder absolut)"
            },
            "start_line": {
                "type": "integer",
                "description": "Erste Zeile (1-basiert, optional)"
            },
            "end_line": {
                "type": "integer",
                "description": "Letzte Zeile (1-basiert, optional)"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis (optional, für relative Pfade)"
            }
        },
        "required": ["path"]
    }
)
def read_file(path: str, start_line: int = 0, end_line: int = 0, project_root: str = "") -> dict:
    """Read file contents, optionally a specific line range."""
    try:
        real = _safe_path(path, project_root)
        if not os.path.isfile(real):
            return {"error": f"Datei nicht gefunden: {path}"}
        
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total = len(lines)
        if start_line > 0 or end_line > 0:
            s = max(0, (start_line or 1) - 1)
            e = min(total, end_line or total)
            selected = lines[s:e]
            content = "".join(selected)
            return {
                "message": f"Datei gelesen: {os.path.basename(real)} (Zeilen {s+1}-{e} von {total})",
                "content": content,
                "total_lines": total,
                "path": real,
            }
        else:
            content = "".join(lines)
            # Truncate very large files
            if len(content) > 30000:
                content = content[:30000] + f"\n\n... (abgeschnitten, {total} Zeilen gesamt)"
            return {
                "message": f"Datei gelesen: {os.path.basename(real)} ({total} Zeilen)",
                "content": content,
                "total_lines": total,
                "path": real,
            }
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Lesefehler: {e}"}


# ─── Tool: Write File ───────────────────────────────────────────────────────

@register_tool(
    name="write_file",
    description=(
        "Schreibt Inhalt in eine bestehende Datei (überschreibt den gesamten Inhalt). "
        "Für neue Dateien verwende create_file. Für gezielte Änderungen verwende patch_file."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur Datei"
            },
            "content": {
                "type": "string",
                "description": "Neuer Dateiinhalt"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path", "content"]
    }
)
def write_file(path: str, content: str, project_root: str = "") -> dict:
    """Write content to an existing file."""
    try:
        real = _safe_path(path, project_root)
        if not os.path.isfile(real):
            return {"error": f"Datei nicht gefunden: {path}. Nutze create_file für neue Dateien."}
        
        with open(real, "w", encoding="utf-8") as f:
            f.write(content)
        
        _log.info(f"write_file: {real} ({len(content)} bytes)")
        return {
            "message": f"Datei geschrieben: {os.path.basename(real)} ({len(content)} Zeichen)",
            "path": real,
            "size": len(content),
        }
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Schreibfehler: {e}"}


# ─── Tool: Create File ──────────────────────────────────────────────────────

@register_tool(
    name="create_file",
    description=(
        "Erstellt eine neue Datei mit dem angegebenen Inhalt. "
        "Erstellt automatisch übergeordnete Verzeichnisse."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad für die neue Datei"
            },
            "content": {
                "type": "string",
                "description": "Dateiinhalt"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path", "content"]
    }
)
def create_file(path: str, content: str, project_root: str = "") -> dict:
    """Create a new file with content."""
    try:
        real = _safe_path(path, project_root)
        os.makedirs(os.path.dirname(real), exist_ok=True)
        
        with open(real, "w", encoding="utf-8") as f:
            f.write(content)
        
        _log.info(f"create_file: {real} ({len(content)} bytes)")
        return {
            "message": f"Datei erstellt: {os.path.basename(real)} ({len(content)} Zeichen)",
            "path": real,
            "size": len(content),
        }
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Erstellungsfehler: {e}"}


# ─── Tool: Patch File (Search & Replace) ────────────────────────────────────

@register_tool(
    name="patch_file",
    description=(
        "Führt eine gezielte Search-&-Replace-Änderung in einer Datei durch. "
        "BEVORZUGT für bestehende Dateien — effizienter als die ganze Datei neu zu schreiben. "
        "Der search-Text muss EXAKT im bestehenden Code vorkommen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur Datei"
            },
            "search": {
                "type": "string",
                "description": "Exakter bestehender Code-Block der ersetzt werden soll"
            },
            "replace": {
                "type": "string",
                "description": "Neuer Code der den search-Block ersetzt"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path", "search", "replace"]
    }
)
def patch_file(path: str, search: str, replace: str, project_root: str = "") -> dict:
    """Apply a targeted search & replace in a file."""
    try:
        real = _safe_path(path, project_root)
        if not os.path.isfile(real):
            return {"error": f"Datei nicht gefunden: {path}"}
        
        with open(real, "r", encoding="utf-8") as f:
            content = f.read()
        
        if search in content:
            new_content = content.replace(search, replace, 1)
            with open(real, "w", encoding="utf-8") as f:
                f.write(new_content)
            _log.info(f"patch_file: {real} (exact match)")
            return {
                "message": f"Patch angewendet: {os.path.basename(real)}",
                "path": real,
                "match_type": "exact",
            }
        else:
            # Fuzzy matching: try stripped whitespace
            search_lines = [l.strip() for l in search.strip().split("\n")]
            content_lines = content.split("\n")
            
            for idx in range(len(content_lines)):
                if content_lines[idx].strip() == search_lines[0]:
                    match = True
                    for si, sl in enumerate(search_lines):
                        if idx + si >= len(content_lines) or content_lines[idx + si].strip() != sl:
                            match = False
                            break
                    if match:
                        # Preserve indentation from original
                        indent = content_lines[idx][:len(content_lines[idx]) - len(content_lines[idx].lstrip())]
                        replace_lines = replace.split("\n")
                        indented = []
                        for ri, rl in enumerate(replace_lines):
                            if ri == 0:
                                indented.append(indent + rl.lstrip())
                            else:
                                indented.append(rl)
                        content_lines[idx:idx + len(search_lines)] = indented
                        new_content = "\n".join(content_lines)
                        with open(real, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        _log.info(f"patch_file: {real} (fuzzy match at line {idx+1})")
                        return {
                            "message": f"Patch angewendet (fuzzy): {os.path.basename(real)} (Zeile {idx+1})",
                            "path": real,
                            "match_type": "fuzzy",
                            "line": idx + 1,
                        }
            
            return {"error": f"SEARCH-Block nicht gefunden in {os.path.basename(real)}. Prüfe den exakten Text."}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Patch-Fehler: {e}"}


# ─── Tool: Delete File ──────────────────────────────────────────────────────

@register_tool(
    name="delete_file",
    description="Löscht eine Datei oder ein leeres Verzeichnis. VORSICHT: Nicht rückgängig machbar!",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur Datei/Verzeichnis"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path"]
    }
)
def delete_file(path: str, project_root: str = "") -> dict:
    """Delete a file or empty directory."""
    try:
        real = _safe_path(path, project_root)
        if os.path.isfile(real):
            os.remove(real)
            _log.info(f"delete_file: {real}")
            return {"message": f"Datei gelöscht: {os.path.basename(real)}"}
        elif os.path.isdir(real):
            import shutil
            shutil.rmtree(real)
            _log.info(f"delete_dir: {real}")
            return {"message": f"Verzeichnis gelöscht: {os.path.basename(real)}"}
        else:
            return {"error": f"Nicht gefunden: {path}"}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Löschfehler: {e}"}


# ─── Tool: Create Directory ─────────────────────────────────────────────────

@register_tool(
    name="create_directory",
    description="Erstellt ein Verzeichnis (und alle übergeordneten Verzeichnisse).",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad des neuen Verzeichnisses"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path"]
    }
)
def create_directory(path: str, project_root: str = "") -> dict:
    """Create a directory (mkdir -p)."""
    try:
        real = _safe_path(path, project_root)
        os.makedirs(real, exist_ok=True)
        _log.info(f"create_directory: {real}")
        return {"message": f"Verzeichnis erstellt: {os.path.basename(real)}", "path": real}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: List Directory ───────────────────────────────────────────────────

@register_tool(
    name="list_directory",
    description=(
        "Listet den Inhalt eines Verzeichnisses auf. "
        "Zeigt Dateien und Unterordner mit Größe und Typ."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zum Verzeichnis"
            },
            "recursive": {
                "type": "boolean",
                "description": "Rekursiv auflisten (default: false)"
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximale Tiefe bei rekursiver Auflistung (default: 3)"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path"]
    }
)
def list_directory(path: str, recursive: bool = False, max_depth: int = 3, project_root: str = "") -> dict:
    """List directory contents."""
    try:
        real = _safe_path(path, project_root)
        if not os.path.isdir(real):
            return {"error": f"Verzeichnis nicht gefunden: {path}"}
        
        skip = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".next", "out",
                ".DS_Store", ".mypy_cache", ".pytest_cache", "dist", "build"}
        
        def _list(dir_path: str, depth: int = 0) -> list:
            entries = []
            try:
                items = sorted(os.listdir(dir_path))
            except PermissionError:
                return entries
            for item in items:
                if item in skip or (item.startswith(".") and item not in (".env", ".gitignore")):
                    continue
                full = os.path.join(dir_path, item)
                rel = os.path.relpath(full, real)
                is_dir = os.path.isdir(full)
                entry = {"name": rel, "type": "directory" if is_dir else "file"}
                if not is_dir:
                    try:
                        entry["size"] = os.path.getsize(full)
                    except:
                        pass
                entries.append(entry)
                if is_dir and recursive and depth < max_depth:
                    entries.extend(_list(full, depth + 1))
            return entries
        
        entries = _list(real)
        return {
            "message": f"Verzeichnis: {os.path.basename(real)} ({len(entries)} Einträge)",
            "entries": entries[:200],
            "path": real,
        }
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Run Command ──────────────────────────────────────────────────────

@register_tool(
    name="run_command",
    description=(
        "Führt einen Shell-Befehl aus (z.B. npm install, pip install, npx tsc, python test.py). "
        "Timeout: 60 Sekunden. Gefährliche Befehle werden blockiert."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell-Befehl der ausgeführt werden soll"
            },
            "cwd": {
                "type": "string",
                "description": "Arbeitsverzeichnis (optional, default: Projekt-Root)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in Sekunden (default: 60, max: 120)"
            }
        },
        "required": ["command"]
    }
)
def run_command(command: str, cwd: str = "", timeout: int = 60) -> dict:
    """Execute a shell command."""
    # Security check
    cmd_lower = command.lower()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return {"error": f"Befehl blockiert (Sicherheit): {blocked}"}
    
    # Allow longer timeouts in agent mode (e.g. long-running background tasks)
    if AGENT_MODE:
        timeout = min(max(timeout, 5), AGENT_TIMEOUT)
    else:
        timeout = min(max(timeout, 5), 120)
    work_dir = cwd or os.path.expanduser("~")
    
    try:
        # Build enriched PATH so npx, cargo, composer, etc. are always found
        _extra_paths = [
            "/usr/local/bin", "/usr/local/sbin",
            "/usr/bin", "/usr/sbin", "/bin", "/sbin",
            "/root/.cargo/bin",           # Rust / cargo
            "/usr/local/cargo/bin",
            "/root/.npm-global/bin",      # npm global installs
            "/usr/local/lib/node_modules/.bin",
            "/root/.local/bin",           # pip --user installs
            "/home/linuxbrew/.linuxbrew/bin",  # Homebrew on Linux (if installed)
            os.environ.get("PATH", ""),
        ]
        _enriched_path = ":".join(p for p in _extra_paths if p)
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=work_dir,
            env={**os.environ, "LANG": "de_DE.UTF-8", "PATH": _enriched_path}
        )
        
        stdout = result.stdout[-4000:] if result.stdout else ""
        stderr = result.stderr[-2000:] if result.stderr else ""
        
        _log.info(f"run_command: `{command}` in {work_dir} → exit {result.returncode}")
        
        status = "✅ Erfolgreich" if result.returncode == 0 else f"⚠️ Exit Code {result.returncode}"
        output_parts = []
        if stdout.strip():
            output_parts.append(f"stdout:\n{stdout.strip()}")
        if stderr.strip():
            output_parts.append(f"stderr:\n{stderr.strip()}")
        output = "\n".join(output_parts) if output_parts else "(keine Ausgabe)"
        
        return {
            "message": f"{status}: `{command}`",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "output": output,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout ({timeout}s): {command}"}
    except Exception as e:
        return {"error": f"Ausführungsfehler: {e}"}


# ─── Tool: Search Text ──────────────────────────────────────────────────────

@register_tool(
    name="search_text",
    description=(
        "Durchsucht Projektdateien nach einem Textmuster (wie grep). "
        "Findet alle Vorkommen in Quelldateien."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchbegriff oder Regex-Pattern"
            },
            "path": {
                "type": "string",
                "description": "Verzeichnis zum Durchsuchen"
            },
            "is_regex": {
                "type": "boolean",
                "description": "Ob der query ein Regex ist (default: false)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximale Treffer (default: 50)"
            }
        },
        "required": ["query", "path"]
    }
)
def search_text(query: str, path: str, is_regex: bool = False, max_results: int = 50) -> dict:
    """Search for text across project files."""
    import re as _re
    
    try:
        real = _safe_path(path)
        if not os.path.isdir(real):
            return {"error": f"Verzeichnis nicht gefunden: {path}"}
        
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "out", "dist", "build"}
        skip_exts = {".pyc", ".pyo", ".so", ".dylib", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2"}
        
        if is_regex:
            pattern = _re.compile(query, _re.IGNORECASE)
        else:
            query_lower = query.lower()
        
        results = []
        for dirpath, dirnames, filenames in os.walk(real):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
            for fname in filenames:
                if len(results) >= max_results:
                    break
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_exts:
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    if os.path.getsize(fpath) > 1024 * 1024:
                        continue
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if len(results) >= max_results:
                                break
                            matched = bool(pattern.search(line)) if is_regex else (query_lower in line.lower())
                            if matched:
                                results.append({
                                    "file": os.path.relpath(fpath, real),
                                    "line": line_num,
                                    "text": line.rstrip()[:200],
                                })
                except:
                    continue
            if len(results) >= max_results:
                break
        
        return {
            "message": f"Suche nach '{query}': {len(results)} Treffer",
            "results": results,
            "total": len(results),
        }
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Suchfehler: {e}"}


# ─── Tool: Project Info ─────────────────────────────────────────────────────

@register_tool(
    name="project_info",
    description=(
        "Gibt eine Übersicht über ein Projekt: Dateistruktur, Dependencies, "
        "Framework-Erkennung, README. Nutze dies am Anfang einer Aufgabe."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zum Projektverzeichnis (optional wenn project_root gesetzt)"
            },
            "project_root": {
                "type": "string",
                "description": "Wurzelverzeichnis des Projekts"
            }
        },
        "required": []
    }
)
def project_info(path: str = "", project_root: str = "") -> dict:
    """Get comprehensive project information."""
    try:
        # Use project_root as fallback if path is empty
        if not path and project_root:
            path = project_root
        real = _safe_path(path, project_root)
        if not os.path.isdir(real):
            return {"error": f"Verzeichnis nicht gefunden: {path}"}
        
        info = {"path": real, "name": os.path.basename(real)}
        
        # Detect project type
        frameworks = []
        if os.path.isfile(os.path.join(real, "package.json")):
            try:
                with open(os.path.join(real, "package.json"), "r") as f:
                    pkg = json.load(f)
                info["package_json"] = {
                    "name": pkg.get("name", ""),
                    "dependencies": list(pkg.get("dependencies", {}).keys()),
                    "devDependencies": list(pkg.get("devDependencies", {}).keys()),
                    "scripts": list(pkg.get("scripts", {}).keys()),
                }
                deps = pkg.get("dependencies", {})
                if "next" in deps: frameworks.append("Next.js")
                if "react" in deps: frameworks.append("React")
                if "vue" in deps: frameworks.append("Vue")
                if "express" in deps: frameworks.append("Express")
                if "svelte" in deps: frameworks.append("Svelte")
            except:
                pass
        
        if os.path.isfile(os.path.join(real, "requirements.txt")):
            try:
                with open(os.path.join(real, "requirements.txt"), "r") as f:
                    reqs = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                info["requirements"] = reqs[:30]
                for r in reqs:
                    rl = r.lower().split("==")[0].split(">=")[0].split("[")[0].strip()
                    if rl == "flask" and "Flask" not in frameworks: frameworks.append("Flask")
                    if rl == "django" and "Django" not in frameworks: frameworks.append("Django")
                    if rl == "fastapi" and "FastAPI" not in frameworks: frameworks.append("FastAPI")
            except:
                pass
        
        if os.path.isfile(os.path.join(real, "Cargo.toml")):
            frameworks.append("Rust/Cargo")
        if os.path.isfile(os.path.join(real, "go.mod")):
            frameworks.append("Go")
        if os.path.isfile(os.path.join(real, "tsconfig.json")):
            frameworks.append("TypeScript")
        
        info["frameworks"] = frameworks
        info["is_git"] = os.path.isdir(os.path.join(real, ".git"))
        
        # File tree (compact)
        skip = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".next", "out", "dist", "build"}
        tree = []
        for dirpath, dirnames, filenames in os.walk(real):
            dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
            depth = os.path.relpath(dirpath, real).count(os.sep)
            if depth > 3:
                dirnames.clear()
                continue
            for fn in sorted(filenames)[:30]:
                rel = os.path.relpath(os.path.join(dirpath, fn), real)
                tree.append(rel)
            if len(tree) > 100:
                break
        
        info["file_count"] = len(tree)
        info["files"] = tree[:100]
        
        # README
        for readme in ["README.md", "readme.md", "README.txt"]:
            rp = os.path.join(real, readme)
            if os.path.isfile(rp):
                try:
                    with open(rp, "r", encoding="utf-8") as f:
                        info["readme"] = f.read()[:2000]
                except:
                    pass
                break
        
        summary = f"Projekt: {info['name']}"
        if frameworks:
            summary += f" ({', '.join(frameworks)})"
        summary += f" — {info['file_count']} Dateien"
        if info["is_git"]:
            summary += " [git]"
        
        return {"message": summary, **info}
    except PermissionError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Install Dependencies ─────────────────────────────────────────────

@register_tool(
    name="install_deps",
    description=(
        "Installiert Projekt-Dependencies. Erkennt automatisch ob npm oder pip "
        "verwendet werden soll anhand der Projektstruktur."
    ),
    parameters={
        "type": "object",
        "properties": {
            "packages": {
                "type": "string",
                "description": "Pakete zum Installieren (Leerzeichen-getrennt). Leer = alle aus package.json/requirements.txt"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis"
            },
            "manager": {
                "type": "string",
                "description": "Paketmanager: npm, pip, yarn (auto-detect wenn leer)",
                "enum": ["npm", "pip", "yarn", ""]
            }
        },
        "required": ["project_root"]
    }
)
def install_deps(project_root: str, packages: str = "", manager: str = "") -> dict:
    """Install project dependencies."""
    try:
        real = _safe_path(project_root)
        
        # Auto-detect
        if not manager:
            if os.path.isfile(os.path.join(real, "package.json")):
                manager = "npm"
            elif os.path.isfile(os.path.join(real, "requirements.txt")):
                manager = "pip"
            elif os.path.isfile(os.path.join(real, "yarn.lock")):
                manager = "yarn"
            else:
                return {"error": "Konnte Paketmanager nicht erkennen. Bitte manager angeben."}
        
        if packages:
            if manager == "npm":
                cmd = f"npm install {packages}"
            elif manager == "yarn":
                cmd = f"yarn add {packages}"
            elif manager == "pip":
                cmd = f"pip install {packages}"
            else:
                return {"error": f"Unbekannter Manager: {manager}"}
        else:
            if manager == "npm":
                cmd = "npm install"
            elif manager == "yarn":
                cmd = "yarn install"
            elif manager == "pip":
                cmd = "pip install -r requirements.txt"
            else:
                return {"error": f"Unbekannter Manager: {manager}"}
        
        return run_command(cmd, cwd=real, timeout=120)
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Run Tests ────────────────────────────────────────────────────────

@register_tool(
    name="run_tests",
    description=(
        "Führt Tests aus. Erkennt automatisch das Test-Framework "
        "(pytest, npm test, cargo test)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis"
            },
            "test_file": {
                "type": "string",
                "description": "Bestimmte Test-Datei (optional)"
            },
            "framework": {
                "type": "string",
                "description": "Test-Framework: pytest, npm, cargo (auto-detect wenn leer)"
            }
        },
        "required": ["project_root"]
    }
)
def run_tests(project_root: str, test_file: str = "", framework: str = "") -> dict:
    """Run project tests."""
    try:
        real = _safe_path(project_root)
        
        if not framework:
            if os.path.isfile(os.path.join(real, "package.json")):
                framework = "npm"
            elif os.path.isfile(os.path.join(real, "Cargo.toml")):
                framework = "cargo"
            else:
                framework = "pytest"
        
        if framework == "pytest":
            cmd = f"python -m pytest {test_file}" if test_file else "python -m pytest"
        elif framework == "npm":
            cmd = "npm test"
        elif framework == "cargo":
            cmd = "cargo test"
        else:
            cmd = f"{framework} {test_file}"
        
        return run_command(cmd, cwd=real, timeout=120)
    except Exception as e:
        return {"error": f"Fehler: {e}"}


# ─── Tool: Lint File ────────────────────────────────────────────────────────

@register_tool(
    name="lint_file",
    description=(
        "Prüft eine Datei auf Syntax-Fehler. Nutzt je nach Sprache: "
        "python -m py_compile, npx tsc --noEmit, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur Datei"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root (optional)"
            }
        },
        "required": ["path"]
    }
)
def lint_file(path: str, project_root: str = "") -> dict:
    """Check a file for syntax errors."""
    try:
        real = _safe_path(path, project_root)
        if not os.path.isfile(real):
            return {"error": f"Datei nicht gefunden: {path}"}
        
        ext = os.path.splitext(real)[1].lower()
        cwd = project_root or os.path.dirname(real)
        
        if ext == ".py":
            cmd = f'python3 -m py_compile "{real}"'
        elif ext in (".ts", ".tsx"):
            cmd = f'npx tsc --noEmit "{real}" 2>&1 || true'
        elif ext in (".js", ".jsx"):
            cmd = f'node --check "{real}" 2>&1 || true'
        elif ext == ".rs":
            cmd = "cargo check 2>&1"
        else:
            return {"message": f"Kein Lint verfügbar für {ext}", "clean": True}
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd
        )
        
        if result.returncode == 0 and not result.stderr.strip():
            return {"message": f"✅ Keine Fehler in {os.path.basename(real)}", "clean": True}
        else:
            errors = (result.stderr or result.stdout or "").strip()
            return {
                "message": f"⚠️ Fehler in {os.path.basename(real)}",
                "errors": errors[:3000],
                "clean": False,
            }
    except subprocess.TimeoutExpired:
        return {"error": "Lint-Timeout (30s)"}
    except Exception as e:
        return {"error": f"Lint-Fehler: {e}"}


# ─── Tool: Export Project (ZIP) ──────────────────────────────────────────────

@register_tool(
    name="export_project",
    description=(
        "Exportiert ein Projekt als ZIP-Datei. Respektiert .gitignore und schließt "
        "node_modules, __pycache__, .git, venv etc. automatisch aus. "
        "Die ZIP-Datei wird im Projekt-Root abgelegt und kann heruntergeladen werden."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis"
            },
            "output_name": {
                "type": "string",
                "description": "Name der ZIP-Datei (ohne .zip). Standard: Projektname"
            },
            "include_deps": {
                "type": "boolean",
                "description": "Dependencies einschließen (node_modules etc.)? Standard: false"
            }
        },
        "required": ["project_root"]
    }
)
def export_project(project_root: str, output_name: str = "", include_deps: bool = False) -> dict:
    """Export a project as a ZIP archive."""
    import zipfile
    from pathlib import Path
    from datetime import datetime
    
    try:
        real = _safe_path(project_root)
        if not os.path.isdir(real):
            return {"error": f"Projekt nicht gefunden: {project_root}"}
        
        project_name = os.path.basename(real.rstrip("/"))
        if not output_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"{project_name}_{ts}"
        
        zip_path = os.path.join(real, f"{output_name}.zip")
        
        # Default excludes (always skip)
        always_exclude = {
            ".git", ".DS_Store", "__pycache__", ".pytest_cache",
            ".mypy_cache", ".ruff_cache", "*.pyc", ".env",
        }
        # Dependency dirs (skip unless include_deps)
        dep_dirs = {"node_modules", "venv", ".venv", "env", "target", "dist", "build",
                    "__pycache__", ".next", ".nuxt", ".svelte-kit"}
        
        # Parse .gitignore patterns (basic)
        gitignore_patterns = set()
        gitignore_file = os.path.join(real, ".gitignore")
        if os.path.isfile(gitignore_file):
            with open(gitignore_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        gitignore_patterns.add(line.strip("/"))
        
        file_count = 0
        total_size = 0
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(real):
                # Get relative path from project root
                rel_root = os.path.relpath(root, real)
                
                # Filter directories
                dirs[:] = [
                    d for d in dirs
                    if d not in always_exclude
                    and (include_deps or d not in dep_dirs)
                    and d not in gitignore_patterns
                    and not d.startswith(".")
                ]
                
                for fname in files:
                    # Skip the zip itself
                    full_path = os.path.join(root, fname)
                    if full_path == zip_path:
                        continue
                    
                    # Skip excluded files
                    if fname in always_exclude or fname in gitignore_patterns:
                        continue
                    if fname.endswith(".pyc"):
                        continue
                    
                    # Skip large files (>50MB)
                    try:
                        fsize = os.path.getsize(full_path)
                        if fsize > 50 * 1024 * 1024:
                            continue
                    except OSError:
                        continue
                    
                    arcname = os.path.join(project_name, rel_root, fname) if rel_root != "." else os.path.join(project_name, fname)
                    zf.write(full_path, arcname)
                    file_count += 1
                    total_size += fsize
        
        zip_size = os.path.getsize(zip_path)
        size_mb = round(zip_size / (1024 * 1024), 2)
        
        _log.info(f"export_project: {zip_path} ({file_count} files, {size_mb}MB)")
        return {
            "success": True,
            "message": f"Projekt exportiert: {output_name}.zip ({file_count} Dateien, {size_mb}MB)",
            "zip_path": zip_path,
            "file_count": file_count,
            "size_mb": size_mb,
            "download_url": f"/api/code/download?path={zip_path}",
        }
    except Exception as e:
        return {"error": f"Export-Fehler: {e}"}


# ─── Tool: Build Project ────────────────────────────────────────────────────

@register_tool(
    name="build_project",
    description=(
        "Kompiliert/baut ein Projekt. Erkennt automatisch das Build-System: "
        "cargo build (Rust), npm run build (Node/React), python setup.py (Python), "
        "make (C/C++). Zeigt Build-Output und Fehler."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis"
            },
            "mode": {
                "type": "string",
                "description": "Build-Modus: debug, release (Standard: debug)",
                "enum": ["debug", "release", ""]
            },
            "command": {
                "type": "string",
                "description": "Eigener Build-Befehl (überschreibt Auto-Detect)"
            }
        },
        "required": ["project_root"]
    }
)
def build_project(project_root: str, mode: str = "debug", command: str = "") -> dict:
    """Build/compile a project."""
    try:
        real = _safe_path(project_root)
        if not os.path.isdir(real):
            return {"error": f"Projekt nicht gefunden: {project_root}"}
        
        # Custom command overrides everything
        if command:
            return run_command(command, cwd=real, timeout=180)
        
        # Auto-detect build system
        if os.path.isfile(os.path.join(real, "Cargo.toml")):
            cmd = f"cargo build {'--release' if mode == 'release' else ''}"
        elif os.path.isfile(os.path.join(real, "package.json")):
            # Check for build script
            try:
                import json as _json
                with open(os.path.join(real, "package.json")) as f:
                    pkg = _json.load(f)
                scripts = pkg.get("scripts", {})
                if "build" in scripts:
                    cmd = "npm run build"
                elif "compile" in scripts:
                    cmd = "npm run compile"
                else:
                    return {"error": "Kein 'build' script in package.json gefunden"}
            except Exception:
                cmd = "npm run build"
        elif os.path.isfile(os.path.join(real, "Makefile")):
            cmd = "make"
        elif os.path.isfile(os.path.join(real, "setup.py")):
            cmd = "python setup.py build"
        elif os.path.isfile(os.path.join(real, "pyproject.toml")):
            cmd = "python -m build"
        elif os.path.isfile(os.path.join(real, "CMakeLists.txt")):
            cmd = "cmake --build build"
        else:
            return {"error": "Kein Build-System erkannt. Nutze 'command' Parameter."}
        
        _log.info(f"build_project: {cmd} in {real}")
        result = run_command(cmd, cwd=real, timeout=180)
        result["build_command"] = cmd
        return result
    except Exception as e:
        return {"error": f"Build-Fehler: {e}"}


# ─── Tool: Preview Web Project ──────────────────────────────────────────────

@register_tool(
    name="preview_web",
    description=(
        "Startet einen lokalen Dev-Server für Web-Projekte und gibt die URL zurück. "
        "Unterstützt: npm (next dev, vite, react-scripts), Python (http.server), "
        "PHP (php -S). Die URL kann im Frontend-Preview-Panel angezeigt werden."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Verzeichnis"
            },
            "port": {
                "type": "integer",
                "description": "Port (Standard: 8080)"
            },
            "command": {
                "type": "string",
                "description": "Eigener Server-Befehl (überschreibt Auto-Detect)"
            }
        },
        "required": ["project_root"]
    }
)
def preview_web(project_root: str, port: int = 8080, command: str = "") -> dict:
    """Start a local dev server for web preview."""
    try:
        real = _safe_path(project_root)
        if not os.path.isdir(real):
            return {"error": f"Projekt nicht gefunden: {project_root}"}
        
        # Custom command overrides
        if command:
            cmd = command
        elif os.path.isfile(os.path.join(real, "package.json")):
            try:
                import json as _json
                with open(os.path.join(real, "package.json")) as f:
                    pkg = _json.load(f)
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    cmd = f"npx next dev -p {port}" if "next" in scripts.get("dev", "") else f"npm run dev -- --port {port}"
                elif "start" in scripts:
                    cmd = f"PORT={port} npm start"
                else:
                    cmd = f"npx serve -p {port} ."
            except Exception:
                cmd = f"npx serve -p {port} ."
        elif any(os.path.isfile(os.path.join(real, f)) for f in ("index.html", "index.htm")):
            # Static HTML — use Python's built-in server
            cmd = f"python3 -m http.server {port}"
        elif any(os.path.isfile(os.path.join(real, f)) for f in ("index.php", "app.php")):
            cmd = f"php -S 0.0.0.0:{port} -t ."
        else:
            # Fallback: serve as static
            cmd = f"python3 -m http.server {port}"
        
        # Start in background
        import shlex
        proc = subprocess.Popen(
            cmd, shell=True, cwd=real,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,  # detach from parent
        )
        
        # Give it a moment to start
        import time as _time
        _time.sleep(1.5)
        
        # Check if it crashed immediately
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors="replace")[:500]
            return {"error": f"Server sofort beendet: {stderr}"}
        
        url = f"http://localhost:{port}"
        _log.info(f"preview_web: {cmd} → {url} (PID {proc.pid})")
        
        return {
            "success": True,
            "message": f"Dev-Server gestartet auf {url}",
            "url": url,
            "port": port,
            "pid": proc.pid,
            "command": cmd,
        }
    except Exception as e:
        return {"error": f"Preview-Fehler: {e}"}


# ─── Tool: Ask User ─────────────────────────────────────────────────────────

@register_tool(
    name="ask_user",
    description=(
        "Stellt dem User eine Frage und wartet auf Antwort. "
        "Nutze dies wenn du eine Entscheidung brauchst oder unsicher bist."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Die Frage an den User"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optionale Auswahlmöglichkeiten"
            }
        },
        "required": ["question"]
    }
)
def ask_user(question: str, options: list = None) -> dict:
    """Ask the user a question (returns the question for frontend to handle)."""
    result = {"message": question, "needs_response": True}
    if options:
        result["options"] = options
    return result


# ─── Code Chat Session Store ────────────────────────────────────────────────
# Stores conversation history per project for on-demand recall.
# Ailey can search her own conversation with `recall_conversation` tool
# instead of bloating every prompt with full chat history.

import threading
import re
from difflib import SequenceMatcher

_code_sessions = {}   # project_path -> [{role, content, ts, summary?}]
_sessions_lock = threading.Lock()
_MAX_SESSION_MSGS = 100  # max messages per session before pruning


def code_session_add(project: str, role: str, content: str, summary: str = ""):
    """Add a message to the code chat session for a project."""
    key = project or "__global__"
    with _sessions_lock:
        if key not in _code_sessions:
            _code_sessions[key] = []
        _code_sessions[key].append({
            "role": role,
            "content": content,
            "summary": summary,
            "ts": time.time(),
        })
        # Prune old messages (keep last N)
        if len(_code_sessions[key]) > _MAX_SESSION_MSGS:
            _code_sessions[key] = _code_sessions[key][-_MAX_SESSION_MSGS:]


def code_session_get(project: str) -> list:
    """Get the full session for a project."""
    key = project or "__global__"
    with _sessions_lock:
        return list(_code_sessions.get(key, []))


def code_session_clear(project: str):
    """Clear the session for a project."""
    key = project or "__global__"
    with _sessions_lock:
        _code_sessions.pop(key, None)


def _keyword_score(text: str, keywords: list) -> float:
    """Score how many keywords appear in text (0.0 - 1.0)."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return hits / len(keywords)


def _fuzzy_score(query: str, text: str) -> float:
    """Fuzzy substring similarity score (0.0 - 1.0)."""
    if not query or not text:
        return 0.0
    return SequenceMatcher(None, query.lower()[:200], text.lower()[:500]).ratio()


import time  # ensure time is imported at module level (already is via logging)


@register_tool(
    "recall_conversation",
    "Durchsucht den bisherigen Code-Chat-Verlauf nach relevanten Nachrichten. "
    "Nutze dieses Tool wenn du Kontext brauchst was vorher besprochen oder gemacht wurde — "
    "z.B. bei Rückfragen, Follow-ups oder wenn der User auf etwas Bezug nimmt.",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Suchbegriff(e) oder Frage — was suchst du im Verlauf?"
            },
            "project_root": {
                "type": "string",
                "description": "Projekt-Root-Pfad (wird automatisch gesetzt)"
            },
            "max_results": {
                "type": "integer",
                "description": "Max Anzahl Ergebnisse (default 5)"
            }
        },
        "required": ["query"]
    }
)
def recall_conversation(query: str, project_root: str = "", max_results: int = 5) -> dict:
    """Search the code chat session history for relevant messages.
    
    Uses keyword matching + fuzzy matching to find the most relevant
    past messages without loading full history into context.
    """
    session = code_session_get(project_root)
    if not session:
        return {"message": "Kein bisheriger Verlauf vorhanden.", "results": [], "count": 0}
    
    # Extract keywords from query (words > 2 chars, no stopwords)
    _stopwords = {'der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'ist', 'hat',
                  'was', 'wie', 'wer', 'mit', 'von', 'für', 'auf', 'aus', 'bei',
                  'nach', 'vor', 'über', 'unter', 'nicht', 'noch', 'auch', 'aber',
                  'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have',
                  'ich', 'du', 'wir', 'sie', 'mir', 'dir', 'mich', 'dich',
                  'dann', 'denn', 'weil', 'wenn', 'also', 'dort', 'hier',
                  'kann', 'will', 'soll', 'muss', 'hast', 'bist', 'sind'}
    words = re.findall(r'\w+', query.lower())
    keywords = [w for w in words if len(w) > 2 and w not in _stopwords]
    
    # Score each message
    scored = []
    for i, msg in enumerate(session):
        text = msg.get("content", "") + " " + msg.get("summary", "")
        
        kw_score = _keyword_score(text, keywords)
        fz_score = _fuzzy_score(query, text)
        
        # Combined score: keyword match weighted higher
        score = kw_score * 0.7 + fz_score * 0.3
        
        # Boost recent messages slightly
        recency = 1.0 + (i / max(len(session), 1)) * 0.2
        score *= recency
        
        if score > 0.05:  # minimum threshold
            scored.append((score, i, msg))
    
    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_results]
    
    if not top:
        return {
            "message": f"Nichts Relevantes gefunden für: '{query}'",
            "results": [],
            "count": 0,
            "total_messages": len(session),
        }
    
    results = []
    for score, idx, msg in top:
        role_label = "User" if msg["role"] == "user" else "Ailey"
        content = msg["content"]
        # Truncate long messages but keep enough context
        if len(content) > 600:
            content = content[:600] + "…"
        results.append({
            "role": role_label,
            "content": content,
            "score": round(score, 3),
            "index": idx,
        })
    
    # Format as readable text for the model
    formatted = []
    for r in results:
        formatted.append(f"[{r['role']}] (Relevanz: {r['score']}): {r['content']}")
    
    return {
        "message": f"{len(results)} relevante Nachrichten gefunden",
        "results": results,
        "formatted": "\n\n".join(formatted),
        "count": len(results),
        "total_messages": len(session),
    }


# ══════════════════════════════════════════════════════════════════════════════
# TOOL: delegate_to_coder — Dual-Model Code Generation
# ══════════════════════════════════════════════════════════════════════════════

@register_tool(
    "delegate_to_coder",
    "Delegiert die Code-Generierung an das spezialisierte Coder-Modell (Qwen2.5-Coder). "
    "Nutze dieses Tool wenn du eine NEUE Datei erstellen willst oder großen Code-Block (>30 Zeilen) "
    "schreiben musst. Du gibst eine Spezifikation und optionalen Kontext, das Coder-Modell "
    "generiert den Code. Du bekommst den Code zurück und kannst ihn dann mit create_file oder "
    "write_file speichern. Für kleine Änderungen (Patches, 1-5 Zeilen) nutze patch_file direkt.",
    {
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": (
                    "Detaillierte Spezifikation was der Code tun soll. "
                    "Sei präzise: Funktionsnamen, Klassen, Imports, API-Endpunkte, etc."
                )
            },
            "language": {
                "type": "string",
                "description": "Zielsprache: python, typescript, javascript, tsx, rust, php, html, css, etc."
            },
            "filename": {
                "type": "string",
                "description": "Ziel-Dateiname (z.B. 'App.tsx', 'main.py'). Hilft dem Coder-Modell beim Kontext."
            },
            "context": {
                "type": "string",
                "description": (
                    "Optionaler Kontext: bestehender Code, Interfaces, Imports, "
                    "verwandte Dateien. Max ~2000 Zeichen sinnvoll."
                )
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max Tokens für die Generierung (Standard: 2048)"
            }
        },
        "required": ["spec", "language", "filename"]
    }
)
def delegate_to_coder(
    spec: str,
    language: str,
    filename: str,
    context: str = "",
    max_tokens: int = 2048,
    **kwargs,
) -> dict:
    """Delegate code generation to the specialised Coder model.
    
    Ailey (Ministral 14B) handles planning, analysis, and orchestration.
    The Coder model (Qwen2.5-Coder-1.5B) handles raw code generation — 
    it's faster and specialised for syntax-correct code output.
    
    Returns the generated code as a string for Ailey to review and save.
    """
    try:
        from ailey_system.llm_coder import generate_code
        
        _log.info(f"delegate_to_coder: {filename} ({language}) — spec: {spec[:80]}...")
        
        code = generate_code(
            spec=spec,
            language=language,
            filename=filename,
            context=context,
            max_tokens=max_tokens,
        )
        
        if code is None:
            return {
                "success": False,
                "error": (
                    "Coder-Modell konnte keinen Code generieren. "
                    "Schreibe den Code selbst mit create_file oder write_file."
                ),
                "fallback": True,
            }
        
        return {
            "success": True,
            "message": f"Code generiert: {filename} ({len(code)} Zeichen, {language})",
            "code": code,
            "filename": filename,
            "language": language,
            "char_count": len(code),
            "line_count": code.count("\n") + 1,
        }
    except Exception as e:
        _log.error(f"delegate_to_coder error: {e}")
        return {
            "success": False,
            "error": f"Coder-Delegierung fehlgeschlagen: {e}",
            "fallback": True,
        }

