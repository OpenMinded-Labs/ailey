# -*- coding: utf-8 -*-
"""
Ailey Git Tools — Git operations as registered tools.

Full git workflow: status, diff, add, commit, push, pull, log, branch, stash.
"""
from __future__ import annotations
import os
import subprocess
import logging
from typing import Any, Dict

from .tools import register_tool
from .agent_config import AGENT_MODE, AGENT_TIMEOUT

_log = logging.getLogger("ailey.tools_git")


def _git_cmd(args: list, cwd: str, timeout: int | None = None) -> dict:
    """Run a git command and return stdout/stderr/returncode."""
    # If caller didn't provide a timeout, use an agent-mode friendly value
    if timeout is None:
        timeout = AGENT_TIMEOUT if AGENT_MODE else 15
    try:
        result = subprocess.run([
            "git"] + args,
            capture_output=True, text=True,
            timeout=timeout, cwd=cwd
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def _ensure_git_repo(path: str) -> str:
    """Verify path is a git repo, return realpath or raise."""
    real = os.path.realpath(path)
    home = os.path.expanduser("~")
    if not real.startswith(home):
        raise PermissionError(f"Zugriff verweigert: {real}")
    if not os.path.isdir(os.path.join(real, ".git")):
        raise ValueError(f"Kein Git-Repository: {real}")
    return real


# ─── Tool: Git Status ───────────────────────────────────────────────────────

@register_tool(
    name="git_status",
    description="Zeigt den Git-Status: Branch, geänderte Dateien, staged/unstaged.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            }
        },
        "required": ["project_root"]
    }
)
def git_status(project_root: str) -> dict:
    """Get git status."""
    try:
        cwd = _ensure_git_repo(project_root)
        
        branch = _git_cmd(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        status = _git_cmd(["status", "--porcelain"], cwd)
        
        changes = []
        if status["stdout"]:
            for line in status["stdout"].split("\n"):
                if len(line) >= 3:
                    changes.append({"status": line[:2].strip(), "file": line[3:]})
        
        # Last commit
        log = _git_cmd(["log", "-1", "--pretty=format:%h|%s|%ar"], cwd)
        last_commit = None
        if log["returncode"] == 0 and log["stdout"]:
            parts = log["stdout"].split("|", 2)
            if len(parts) >= 3:
                last_commit = {"hash": parts[0], "message": parts[1], "ago": parts[2]}
        
        return {
            "message": f"Branch: {branch['stdout']}, {len(changes)} Änderungen" + 
                       (f", letzter Commit: {last_commit['message']}" if last_commit else ""),
            "branch": branch["stdout"],
            "changes": changes[:50],
            "change_count": len(changes),
            "dirty": len(changes) > 0,
            "last_commit": last_commit,
        }
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Git-Fehler: {e}"}


# ─── Tool: Git Diff ─────────────────────────────────────────────────────────

@register_tool(
    name="git_diff",
    description="Zeigt Git-Diff: Änderungen an Dateien (staged oder unstaged).",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "staged": {
                "type": "boolean",
                "description": "Staged changes anzeigen (default: false = unstaged)"
            },
            "file": {
                "type": "string",
                "description": "Bestimmte Datei (optional)"
            }
        },
        "required": ["project_root"]
    }
)
def git_diff(project_root: str, staged: bool = False, file: str = "") -> dict:
    """Show git diff."""
    try:
        cwd = _ensure_git_repo(project_root)
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file:
            args.append("--")
            args.append(file)
        
        result = _git_cmd(args, cwd, timeout=10)
        diff = result["stdout"][:8000] if result["stdout"] else "(keine Änderungen)"
        
        return {
            "message": f"Git Diff ({'staged' if staged else 'unstaged'})" + (f" — {file}" if file else ""),
            "diff": diff,
        }
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Git-Fehler: {e}"}


# ─── Tool: Git Add ──────────────────────────────────────────────────────────

@register_tool(
    name="git_add",
    description="Stagt Dateien für den nächsten Commit.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "files": {
                "type": "string",
                "description": "Dateien zum Stagen (Leerzeichen-getrennt). '.' für alle."
            }
        },
        "required": ["project_root", "files"]
    }
)
def git_add(project_root: str, files: str = ".") -> dict:
    """Stage files for commit."""
    try:
        cwd = _ensure_git_repo(project_root)
        file_list = files.split()
        result = _git_cmd(["add"] + file_list, cwd)
        
        if result["returncode"] == 0:
            return {"message": f"✅ Gestagt: {files}"}
        else:
            return {"error": f"Git add fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Commit ───────────────────────────────────────────────────────

@register_tool(
    name="git_commit",
    description="Erstellt einen Git-Commit mit den gestagten Änderungen.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "message": {
                "type": "string",
                "description": "Commit-Message"
            }
        },
        "required": ["project_root", "message"]
    }
)
def git_commit(project_root: str, message: str) -> dict:
    """Create a git commit."""
    try:
        cwd = _ensure_git_repo(project_root)
        result = _git_cmd(["commit", "-m", message], cwd)
        
        if result["returncode"] == 0:
            _log.info(f"git_commit: {message[:50]} in {cwd}")
            return {"message": f"✅ Commit erstellt: {message}", "output": result["stdout"]}
        else:
            return {"error": f"Commit fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Push ─────────────────────────────────────────────────────────

@register_tool(
    name="git_push",
    description="Pusht Commits zum Remote-Repository.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "remote": {
                "type": "string",
                "description": "Remote-Name (default: origin)"
            },
            "branch": {
                "type": "string",
                "description": "Branch-Name (optional, default: aktueller Branch)"
            }
        },
        "required": ["project_root"]
    }
)
def git_push(project_root: str, remote: str = "origin", branch: str = "") -> dict:
    """Push commits to remote."""
    try:
        cwd = _ensure_git_repo(project_root)
        args = ["push", remote]
        if branch:
            args.append(branch)
        
        result = _git_cmd(args, cwd, timeout=30)
        
        if result["returncode"] == 0:
            return {"message": f"✅ Push erfolgreich zu {remote}" + (f"/{branch}" if branch else ""),
                    "output": result["stdout"] or result["stderr"]}
        else:
            return {"error": f"Push fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Pull ─────────────────────────────────────────────────────────

@register_tool(
    name="git_pull",
    description="Zieht Änderungen vom Remote-Repository.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "remote": {
                "type": "string",
                "description": "Remote-Name (default: origin)"
            }
        },
        "required": ["project_root"]
    }
)
def git_pull(project_root: str, remote: str = "origin") -> dict:
    """Pull changes from remote."""
    try:
        cwd = _ensure_git_repo(project_root)
        result = _git_cmd(["pull", remote], cwd, timeout=30)
        
        if result["returncode"] == 0:
            return {"message": f"✅ Pull erfolgreich von {remote}", "output": result["stdout"]}
        else:
            return {"error": f"Pull fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Log ──────────────────────────────────────────────────────────

@register_tool(
    name="git_log",
    description="Zeigt die letzten Git-Commits.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "count": {
                "type": "integer",
                "description": "Anzahl Commits (default: 10)"
            },
            "oneline": {
                "type": "boolean",
                "description": "Kompakte Einzeiler-Ansicht (default: true)"
            }
        },
        "required": ["project_root"]
    }
)
def git_log(project_root: str, count: int = 10, oneline: bool = True) -> dict:
    """Show recent git commits."""
    try:
        cwd = _ensure_git_repo(project_root)
        count = min(max(count, 1), 50)
        
        if oneline:
            result = _git_cmd(["log", f"-{count}", "--oneline"], cwd)
        else:
            result = _git_cmd(["log", f"-{count}", "--pretty=format:%h | %an | %ar | %s"], cwd)
        
        if result["returncode"] == 0:
            return {"message": f"Letzte {count} Commits:\n{result['stdout']}", "log": result["stdout"]}
        else:
            return {"error": f"Git log fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Checkout ─────────────────────────────────────────────────────

@register_tool(
    name="git_checkout",
    description="Wechselt den Git-Branch oder erstellt einen neuen.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "branch": {
                "type": "string",
                "description": "Branch-Name"
            },
            "create": {
                "type": "boolean",
                "description": "Neuen Branch erstellen (default: false)"
            }
        },
        "required": ["project_root", "branch"]
    }
)
def git_checkout(project_root: str, branch: str, create: bool = False) -> dict:
    """Switch or create git branch."""
    try:
        cwd = _ensure_git_repo(project_root)
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)
        
        result = _git_cmd(args, cwd)
        
        if result["returncode"] == 0:
            action = "erstellt und gewechselt" if create else "gewechselt"
            return {"message": f"✅ Branch {action}: {branch}"}
        else:
            return {"error": f"Checkout fehlgeschlagen: {result['stderr']}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}


# ─── Tool: Git Stash ────────────────────────────────────────────────────────

@register_tool(
    name="git_stash",
    description="Speichert aktuelle Änderungen temporär (git stash) oder stellt sie wieder her.",
    parameters={
        "type": "object",
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Pfad zum Git-Repository"
            },
            "action": {
                "type": "string",
                "description": "Aktion: push (speichern), pop (wiederherstellen), list",
                "enum": ["push", "pop", "list"]
            },
            "message": {
                "type": "string",
                "description": "Stash-Nachricht (optional, nur bei push)"
            }
        },
        "required": ["project_root", "action"]
    }
)
def git_stash(project_root: str, action: str = "push", message: str = "") -> dict:
    """Git stash operations."""
    try:
        cwd = _ensure_git_repo(project_root)
        
        if action == "push":
            args = ["stash", "push"]
            if message:
                args.extend(["-m", message])
            result = _git_cmd(args, cwd)
            if result["returncode"] == 0:
                return {"message": f"✅ Stash gespeichert" + (f": {message}" if message else ""),
                        "output": result["stdout"]}
            else:
                return {"error": f"Stash fehlgeschlagen: {result['stderr']}"}
        
        elif action == "pop":
            result = _git_cmd(["stash", "pop"], cwd)
            if result["returncode"] == 0:
                return {"message": "✅ Stash wiederhergestellt", "output": result["stdout"]}
            else:
                return {"error": f"Stash pop fehlgeschlagen: {result['stderr']}"}
        
        elif action == "list":
            result = _git_cmd(["stash", "list"], cwd)
            return {"message": result["stdout"] or "Kein Stash vorhanden", "stashes": result["stdout"]}
        
        else:
            return {"error": f"Unbekannte Aktion: {action}"}
    except (PermissionError, ValueError) as e:
        return {"error": str(e)}
