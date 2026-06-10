# -*- coding: utf-8 -*-
"""
Ailey Agent Loop — Multi-step autonomous task execution.

The Agent Loop enables Ailey to:
  1. Plan a task (decompose into steps)
  2. Execute each step by calling tools
  3. Observe the results
  4. Decide: continue, retry, or finish
  5. Verify the result (lint, build, test)

Runs in a background thread, sends updates via a callback.
"""
from __future__ import annotations
import os
import sys
import json
import re
import time
import threading
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from .tools import get_tool_schemas, execute_tool, parse_tool_calls, extract_text_before_tools
from .chunker import chunk_file

_log = logging.getLogger("ailey.agent")

# ─── File-based agent logger (visible even in .app) ─────────────────────────
_AGENT_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent.log")
_agent_file_logger = logging.getLogger("ailey.agent.file")
_agent_file_logger.setLevel(logging.DEBUG)
_agent_file_logger.propagate = False
if not _agent_file_logger.handlers:
    _afh = logging.FileHandler(_AGENT_LOG_PATH, encoding="utf-8")
    _afh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    _agent_file_logger.addHandler(_afh)


def _agent_log(msg: str):
    """Write agent log line to file + stderr."""
    _agent_file_logger.info(msg)
    try:
        sys.stderr.write(f"[AGENT] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass  # stderr may be closed in .app

# ─── Agent State ─────────────────────────────────────────────────────────────

class AgentState:
    """Tracks the state of a running agent task."""
    
    def __init__(self, task_id: str, task: str, mode: str = "code"):
        self.task_id = task_id
        self.task = task
        self.mode = mode
        self.status = "planning"  # planning, running, paused, done, error, stopped
        self.steps: List[dict] = []
        self.current_step = 0
        self.total_steps = 0
        self.plan: Optional[dict] = None
        self.started_at = time.time()
        self.finished_at = None
        self.error = None
        self._abort = False
        self._pause = False
        self.tool_calls: List[dict] = []
        self.conversation: List[dict] = []  # system, user, assistant, tool_result messages
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task": self.task,
            "mode": self.mode,
            "status": self.status,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "steps": self.steps,
            "plan": self.plan,
            "elapsed": round(time.time() - self.started_at, 1),
            "tool_calls_count": len(self.tool_calls),
        }


# ─── Active Agents Registry ─────────────────────────────────────────────────

_active_agents: Dict[str, AgentState] = {}
_agents_lock = threading.Lock()


def get_agent(task_id: str) -> Optional[AgentState]:
    """Get an agent by task ID."""
    with _agents_lock:
        return _active_agents.get(task_id)


def list_agents() -> List[dict]:
    """List all active agents."""
    with _agents_lock:
        return [a.to_dict() for a in _active_agents.values()]


def stop_agent(task_id: str) -> bool:
    """Signal an agent to stop."""
    agent = get_agent(task_id)
    if agent:
        agent._abort = True
        agent.status = "stopped"
        return True
    return False


def pause_agent(task_id: str) -> bool:
    """Pause an agent."""
    agent = get_agent(task_id)
    if agent:
        agent._pause = True
        agent.status = "paused"
        return True
    return False


def resume_agent(task_id: str) -> bool:
    """Resume a paused agent."""
    agent = get_agent(task_id)
    if agent and agent._pause:
        agent._pause = False
        agent.status = "running"
        return True
    return False


# ─── Agent Runner ────────────────────────────────────────────────────────────

class AgentRunner:
    """
    Runs a multi-step agent loop using Ailey's MLX model + tool system.
    
    Flow:
      1. Build initial system prompt with task + available tools
      2. Ask model: "What's your plan?"
      3. Loop:
         a. Model generates response (may include tool calls)
         b. Parse tool calls → execute tools → get results
         c. Feed results back to model
         d. Model decides: next step or done
      4. Exit on: "done", max_steps, abort, or error
    """
    
    def __init__(
        self,
        generator,  # MLXGenerator instance
        task: str,
        mode: str = "code",
        project_root: str = "",
        max_steps: int = 25,
        on_update: Optional[Callable] = None,
        tool_filter: Optional[List[str]] = None,
    ):
        self.generator = generator
        self.task = task
        self.mode = mode
        self.project_root = project_root
        self.max_steps = max_steps
        self.on_update = on_update or (lambda *a, **kw: None)
        self.tool_filter = tool_filter
        
        # Create agent state
        self.task_id = f"agent_{int(time.time()*1000)}"
        self.state = AgentState(self.task_id, task, mode)
        
        # Register
        with _agents_lock:
            _active_agents[self.task_id] = self.state
    
    def _get_tool_schemas(self, planning_only: bool = False) -> list:
        """Get filtered tool schemas based on mode.
        
        Uses category-based filtering to keep the prompt small.
        Code mode: code + git + web tools only (~20 tools instead of 53).
        Chat mode: chat + web tools only.
        
        Args:
            planning_only: If True, return NO tools (plan step doesn't need them).
        """
        if planning_only:
            return []  # Planning step: model just needs to output a plan, no tools
        
        if self.tool_filter:
            all_tools = get_tool_schemas()
            return [t for t in all_tools if t["function"]["name"] in self.tool_filter]
        
        # Category-based filtering (much faster, smaller prompts)
        if self.mode == "code":
            # ESSENTIAL tools only (~15) to keep prompt small and generation fast
            # The full 30 tools add ~15K chars to the prompt → 40-60s just for
            # prompt processing on 14B. With 15 tools (~7K) it's much faster.
            _ESSENTIAL_CODE_TOOLS = {
                # File operations (core)
                "read_file", "write_file", "create_file", "patch_file",
                "delete_file", "create_directory", "list_directory",
                # Execution
                "run_command", "install_deps", "run_tests",
                # Analysis
                "search_text", "project_info", "lint_file",
                # Web research
                "web_search", "fetch_url",
                # Git (full workflow: status → diff → add → commit → push)
                "git_status", "git_diff", "git_add", "git_commit", "git_push",
                "git_log", "git_checkout", "git_pull",
                # Code delegation (for Ministral fallback)
                "delegate_to_coder",
            }
            all_tools = get_tool_schemas(categories=["code", "git", "web"])
            return [t for t in all_tools if t["function"]["name"] in _ESSENTIAL_CODE_TOOLS]
        elif self.mode == "chat":
            if self.project_root:
                return get_tool_schemas(categories=["chat", "web", "code"])
            return get_tool_schemas(categories=["chat", "web"])
        
        return get_tool_schemas()
    
    def _build_system_prompt(self, planning: bool = False) -> str:
        """Build the system prompt for the agent.

        Args:
            planning: If True, build a compact planning-only prompt (no tools section).
        """
        if planning:
            # ── PLANNING PROMPT — ultra-compact, no tools, no <think> ──
            prompt = (
                "/no_think\n"
                "Du bist Ailey — ein autonomer KI-Agent.\n"
                "Erstelle einen Plan für die folgende Aufgabe.\n\n"
                "Antworte NUR mit einem JSON-Plan in diesem Format:\n"
                '[PLAN]{"steps": [{"title": "Schritt-Titel"}, ...]}[/PLAN]\n\n'
                "Regeln:\n"
                "• Max 5-8 Schritte\n"
                "• Jeder Schritt = eine konkrete Aktion\n"
                "• Kein Erklärungstext — NUR der [PLAN]-Block\n"
                "• ALLES auf Deutsch\n"
            )
        else:
            # ── EXECUTION PROMPT — model-adaptive, with tool instructions ──
            # Detect which model is active to use correct tool-call syntax
            try:
                from .llm_mlx import get_active_model_tag
                _model_tag = get_active_model_tag()
            except Exception:
                _model_tag = "chat"

            if _model_tag == "coder":
                # ═══════════════════════════════════════════════════════
                # CodeA!ley PROMPT — state-of-the-art coding agent
                # Inspired by Aider, Claude Code, Cursor
                # ═══════════════════════════════════════════════════════
                prompt = (
                    "You are Ailey — an expert autonomous coding agent running on Apple Silicon.\n"
                    "You are CodeA!ley (Qwen2.5-Coder-14B), a specialized code model.\n"
                    "You think step-by-step, write clean code, and verify your work.\n\n"

                    "## WORKFLOW\n"
                    "1. UNDERSTAND — Read relevant files before editing. Never guess file contents.\n"
                    "2. PLAN — Think through the change. Consider edge cases and dependencies.\n"
                    "3. IMPLEMENT — Make precise, minimal edits. One tool call per step.\n"
                    "4. VERIFY — After edits: lint the file, run tests, check for errors.\n"
                    "5. COMMIT — When done: git add + git commit with a descriptive message.\n\n"

                    "## TOOL CALL FORMAT (Qwen native)\n"
                    "Use <tool_call> XML tags with JSON inside:\n"
                    '<tool_call>\n{"name": "tool_name", "arguments": {"param": "value"}}\n</tool_call>\n\n'

                    "## AVAILABLE STRATEGIES\n\n"

                    "### Reading & Understanding\n"
                    '• Read a file: <tool_call>\n{"name": "read_file", "arguments": {"path": "src/app.py"}}\n</tool_call>\n'
                    '• Search code: <tool_call>\n{"name": "search_text", "arguments": {"query": "def handle_request", "path": "src/"}}\n</tool_call>\n'
                    '• List directory: <tool_call>\n{"name": "list_directory", "arguments": {"path": "."}}\n</tool_call>\n'
                    '• Project overview: <tool_call>\n{"name": "project_info", "arguments": {}}\n</tool_call>\n\n'

                    "### Editing Files\n"
                    '• Create new file: <tool_call>\n{"name": "create_file", "arguments": {"path": "src/utils.py", "content": "def helper():\\n    pass"}}\n</tool_call>\n'
                    '• Write/overwrite file: <tool_call>\n{"name": "write_file", "arguments": {"path": "src/app.py", "content": "...full content..."}}\n</tool_call>\n'
                    '• Patch file (search/replace): <tool_call>\n{"name": "patch_file", "arguments": {"path": "src/app.py", "patches": [{"search": "old_code", "replace": "new_code"}]}}\n</tool_call>\n'
                    '• Delete file: <tool_call>\n{"name": "delete_file", "arguments": {"path": "tmp/old.py"}}\n</tool_call>\n\n'

                    "### Running Commands\n"
                    '• Shell command: <tool_call>\n{"name": "run_command", "arguments": {"command": "python -m pytest tests/ -x"}}\n</tool_call>\n'
                    '• Install deps: <tool_call>\n{"name": "install_deps", "arguments": {"packages": ["flask", "requests"]}}\n</tool_call>\n'
                    '• Lint file: <tool_call>\n{"name": "lint_file", "arguments": {"path": "src/app.py"}}\n</tool_call>\n\n'

                    "### Git Operations\n"
                    '• Status: <tool_call>\n{"name": "git_status", "arguments": {}}\n</tool_call>\n'
                    '• Add files: <tool_call>\n{"name": "git_add", "arguments": {"files": ["src/app.py", "src/utils.py"]}}\n</tool_call>\n'
                    '• Commit: <tool_call>\n{"name": "git_commit", "arguments": {"message": "feat: add request handler with validation"}}\n</tool_call>\n'
                    '• Push: <tool_call>\n{"name": "git_push", "arguments": {}}\n</tool_call>\n'
                    '• Diff: <tool_call>\n{"name": "git_diff", "arguments": {}}\n</tool_call>\n\n'

                    "### Web Research\n"
                    '• Search web: <tool_call>\n{"name": "web_search", "arguments": {"query": "python asyncio best practices"}}\n</tool_call>\n'
                    '• Fetch URL: <tool_call>\n{"name": "fetch_url", "arguments": {"url": "https://docs.python.org/3/library/asyncio.html"}}\n</tool_call>\n\n'

                    "## CODING PRINCIPLES\n"
                    "• Use best practices for the language/framework at hand.\n"
                    "• Respect existing code style, conventions, imports, and naming patterns.\n"
                    "• Write concise, self-documenting code. Add comments only when logic is non-obvious.\n"
                    "• For patch_file: include 3+ lines of context in 'search' to ensure unique match.\n"
                    "• NEVER use placeholder comments like '... rest of code ...' — always write complete code.\n"
                    "• Handle errors properly. No bare except, no swallowed exceptions.\n"
                    "• When editing large files: use patch_file with search/replace, NOT write_file.\n\n"

                    "## VERIFICATION LOOP (after every edit)\n"
                    "1. lint_file on every file you changed\n"
                    "2. If lint errors: fix them immediately with another patch_file\n"
                    "3. If the project has tests: run_command to execute relevant tests\n"
                    "4. If tests fail: read the error, fix the code, re-run\n"
                    "5. Only proceed to git commit when lint + tests pass\n\n"

                    "## GIT WORKFLOW\n"
                    "• After all changes verified: git_add → git_commit → git_push\n"
                    "• Commit messages: conventional commits (feat:, fix:, refactor:, docs:, chore:)\n"
                    "• One logical change per commit. Don't bundle unrelated changes.\n"
                    "• Always push to the current branch after committing.\n\n"

                    "## TERMINAL / SHELL\n"
                    "• macOS with zsh. Homebrew available.\n"
                    "• Python venv at .venv/ — use .venv/bin/python for Python commands.\n"
                    "• Node.js/npm/npx available. Cargo/Rust available.\n"
                    "• NEVER run destructive commands (rm -rf /, etc.) without explicit user approval.\n"
                    "• Long-running servers: add & or note that the command blocks.\n\n"

                    "## SIGNALS\n"
                    "• Say [AGENT_DONE] ONLY when ALL steps are complete, verified, and committed.\n"
                    "• Say [AGENT_ERROR]description[/AGENT_ERROR] for unsolvable problems.\n"
                    "• Say [AGENT_ASK]question[/AGENT_ASK] if you need user input.\n"
                    "• Step markers (USE THEM after every step!):\n"
                    "  [STEP_ACTIVE:N] — emit BEFORE starting step N\n"
                    "  [STEP_DONE:N] — emit AFTER completing step N\n"
                    "• Plan revision: [PLAN_REVISION]{\"steps\": [...]}[/PLAN_REVISION]\n\n"

                    "## CRITICAL RULES — READ CAREFULLY\n"
                    "1. You MUST write or modify at least one file before saying [AGENT_DONE].\n"
                    "   Reading/listing files alone is NOT completing the task.\n"
                    "2. NEVER say [AGENT_DONE] after only exploring the project.\n"
                    "   Explore → Understand → IMPLEMENT → Verify → THEN [AGENT_DONE].\n"
                    "3. NEVER use [TOOL_CALLS] format. ONLY use <tool_call> XML tags.\n"
                    "4. After each completed step, ALWAYS emit [STEP_DONE:N] and [STEP_ACTIVE:N+1].\n"
                    "5. One tool call at a time. Wait for the result before the next call.\n"
                    "6. If you feel stuck, use search_text or list_directory to get oriented, then PROCEED.\n\n"

                    "## LANGUAGE\n"
                    "• Communicate in German (Deutsch). Code comments in English.\n"
                    "• Be concise. 1-2 sentences explanation, then tool call.\n"
                )
            else:
                # ═══════════════════════════════════════════════════════
                # MINISTRAL CHAT PROMPT — original execution prompt
                # ═══════════════════════════════════════════════════════
                prompt = (
                    "/no_think\n"
                    "Du bist Ailey — ein autonomer KI-Agent. Arbeite eigenständig.\n"
                    "Nutze die bereitgestellten Tools um die Aufgabe zu erledigen.\n\n"
                    "REGELN:\n"
                    "• Führe genau EIN Tool pro Schritt aus\n"
                    "• Immer read_file VOR dem Ändern einer Datei\n"
                    "• Sage [AGENT_DONE] wenn ALLE Schritte erledigt sind\n"
                    "• Sage [AGENT_ERROR]Beschreibung[/AGENT_ERROR] bei unlösbaren Problemen\n"
                    "• Erkläre in 1-2 Sätzen was du tust (DEUTSCH), dann ruf das Tool auf\n"
                    "• IMMER auf Deutsch kommunizieren\n"
                    "• create_directory: NUR für neue Unterverzeichnisse — Projekt-Root existiert bereits!\n"
                    "• Bei unbekannter Struktur: ERST list_directory, dann arbeiten\n\n"
                    "KRITISCH — TOOL-FORMAT (IMMER exakt so):\n"
                    "[TOOL_CALLS]tool_name[ARGS]{\"param\": \"wert\"}\n\n"
                    "Beispiele:\n"
                    "[TOOL_CALLS]list_directory[ARGS]{\"path\": \".\"}\n"
                    "[TOOL_CALLS]read_file[ARGS]{\"path\": \"src/index.js\"}\n"
                    "[TOOL_CALLS]write_file[ARGS]{\"path\": \"src/new.js\", \"content\": \"// code\"}\n\n"
                    "SCHRITT-MARKER (optional, nach Tool-Aufruf):\n"
                    "  [STEP_DONE:1] — Schritt 1 erledigt\n"
                    "  [STEP_ACTIVE:2] — Schritt 2 gestartet\n\n"
                    "PLAN REVIDIEREN (wenn du neue Erkenntnisse hast):\n"
                    "  [PLAN_REVISION]{\"steps\": [{\"title\": \"...\"}, ...]}[/PLAN_REVISION]\n"
                    "  → Ersetzt alle noch ausstehenden Schritte durch den neuen Plan.\n"
                    "  → Bereits erledigte Schritte bleiben erhalten.\n\n"
                    "TERMINAL-BEFEHLE:\n"
                    "• npm, npx, cargo, pip, python, php, composer stehen zur Verfügung\n"
                    "• Syntax: [TOOL_CALLS]run_command[ARGS]{\"command\": \"npm install\"}\n\n"
                    "CODE-GENERIERUNG:\n"
                    "• Neue Dateien oder >30 Zeilen: nutze `delegate_to_coder`\n"
                    "• Kleine Änderungen (<30 Zeilen): nutze patch_file direkt\n"
                )
        
        if self.mode == "code" and self.project_root:
            prompt += (
                f"\n📂 Project: {self.project_root}\n"
                f"Use paths relative to project root or absolute.\n"
                f"Always set project_root to '{self.project_root}'.\n"
            )
            # ── Stack-aware conventions ──
            # Detect project type from files and inject framework-specific rules.
            prompt += self._detect_stack_conventions()
        
        return prompt

    def _detect_stack_conventions(self) -> str:
        """Detect project stack from files and return convention hints for the planner."""
        if not self.project_root:
            return ""
        import os as _os
        root = self.project_root
        hints: list[str] = []

        # ── Rust / Cargo ──
        if _os.path.isfile(_os.path.join(root, "Cargo.toml")):
            hints.append(
                "\n🦀 RUST/CARGO-Konventionen:\n"
                "• `cargo build` / `cargo check` zum Prüfen, `cargo test` für Tests\n"
                "• Fehler zuerst mit `cargo check 2>&1 | head -40` diagnostizieren\n"
                "• Ownership & Borrow-Checker ernst nehmen — kein `.unwrap()` in Prod-Code\n"
                "• `mod.rs` oder `lib.rs` für Modul-Exports nutzen\n"
                "• Fehlerbehandlung: `anyhow::Result` oder `thiserror` für eigene Error-Types\n"
            )
            # Tauri sub-check
            tauri_toml = _os.path.join(root, "src-tauri", "Cargo.toml")
            tauri_conf = _os.path.join(root, "src-tauri", "tauri.conf.json")
            if _os.path.isfile(tauri_toml) or _os.path.isfile(tauri_conf):
                hints.append(
                    "🖥 TAURI-Konventionen:\n"
                    "• Frontend-Code in `src/` oder `app/`, Rust-Backend in `src-tauri/src/`\n"
                    "• Tauri commands: `#[tauri::command]` in `src-tauri/src/main.rs` oder eigene Module\n"
                    "• `tauri.conf.json` für Fenster-Config, Permissions, Build-Settings\n"
                    "• Build: `npx tauri build`, Dev: `npx tauri dev`\n"
                    "• IPC: `invoke('command_name', {args})` im Frontend\n"
                )

        # ── Next.js ──
        pkg_path = _os.path.join(root, "package.json")
        if _os.path.isfile(pkg_path):
            try:
                import json as _json
                with open(pkg_path, "r") as f:
                    pkg = _json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    hints.append(
                        "\n⚡ NEXT.JS-Konventionen:\n"
                        "• App Router: `app/` Verzeichnis, `page.tsx` = Route, `layout.tsx` = Layout\n"
                        "• Server Components Standard — `'use client'` nur wenn nötig\n"
                        "• API Routes: `app/api/route_name/route.ts` mit `export async function GET/POST`\n"
                        "• Styling: Tailwind CSS bevorzugt, CSS Modules als Alternative\n"
                        "• `next.config.js` für Rewrites, Env-Vars, Image-Domains\n"
                    )
                if "react" in deps and "next" not in deps:
                    hints.append(
                        "\n⚛️ REACT-Konventionen:\n"
                        "• Functional Components + Hooks (kein Class-Components)\n"
                        "• State: useState/useReducer, Side-Effects: useEffect\n"
                        "• Komponenten in PascalCase, eine Komponente pro Datei\n"
                    )
                if "vue" in deps:
                    hints.append(
                        "\n💚 VUE-Konventionen:\n"
                        "• Single File Components (.vue): <template>, <script setup>, <style scoped>\n"
                        "• Composition API bevorzugt (ref, reactive, computed)\n"
                    )
            except Exception:
                pass

        # ── Joomla 5 ──
        joomla_xml = _os.path.join(root, "administrator", "components")
        joomla_manifest = any(
            f.endswith(".xml") and "joomla" in f.lower()
            for f in _os.listdir(root) if _os.path.isfile(_os.path.join(root, f))
        ) if _os.path.isdir(root) else False
        if _os.path.isdir(joomla_xml) or joomla_manifest:
            hints.append(
                "\n🟠 JOOMLA 5-Konventionen:\n"
                "• MVC-Struktur: `src/Controller/`, `src/Model/`, `src/View/`, `tmpl/`\n"
                "• Namespace: `Joomla\\Component\\<Name>\\...` (PSR-4)\n"
                "• Services via DI Container: `services/provider.php`\n"
                "• Manifest: `<componentname>.xml` im Root\n"
                "• Datenbank: `sql/install.mysql.utf8.sql` für Schema\n"
                "• Sprachdateien: `language/de-DE/`, `language/en-GB/`\n"
                "• Admin-Views: `administrator/components/com_<name>/`\n"
                "• Frontend-Views: `components/com_<name>/`\n"
            )

        # ── Python / Flask / Django / FastAPI ──
        if _os.path.isfile(_os.path.join(root, "requirements.txt")) or _os.path.isfile(_os.path.join(root, "pyproject.toml")):
            try:
                reqs_text = ""
                if _os.path.isfile(_os.path.join(root, "requirements.txt")):
                    with open(_os.path.join(root, "requirements.txt"), "r") as f:
                        reqs_text = f.read().lower()
                if "flask" in reqs_text:
                    hints.append(
                        "\n🐍 FLASK-Konventionen:\n"
                        "• Routes: `@app.route('/...')` mit `methods=['GET','POST']`\n"
                        "• Blueprints für modulare Struktur\n"
                        "• `jsonify()` für JSON-Responses, `request.json` für Body\n"
                    )
                if "django" in reqs_text:
                    hints.append(
                        "\n🐍 DJANGO-Konventionen:\n"
                        "• Apps: `python manage.py startapp <name>`\n"
                        "• Models → Migrations → Views → URLs → Templates\n"
                        "• `settings.py` für Config, `urls.py` für Routing\n"
                    )
                if "fastapi" in reqs_text:
                    hints.append(
                        "\n🐍 FASTAPI-Konventionen:\n"
                        "• Pydantic Models für Request/Response Validation\n"
                        "• `async def` für Endpoints, Dependency Injection\n"
                        "• Auto-Docs unter `/docs` (Swagger) und `/redoc`\n"
                    )
            except Exception:
                pass

        return "".join(hints)
    
    def _generate_summary(self, final_step: int) -> str:
        """Generate a structured summary of what the agent did.
        
        Uses the model to create a user-friendly explanation based on
        the actual tool calls and their results.
        """
        # Build a compact log of everything that happened
        action_log = []
        files_created = []
        files_modified = []
        files_deleted = []
        commands_run = []
        errors = []
        
        for tc in self.state.tool_calls:
            tool = tc["tool"]
            args = tc.get("arguments", {})
            result = tc.get("result", {})
            success = result.get("success", False)
            
            if tool == "create_file":
                p = args.get("path", "?")
                files_created.append(p)
                action_log.append(f"✅ Created: {p}")
            elif tool == "delegate_to_coder":
                fname = args.get("filename", "?")
                lang = args.get("language", "?")
                action_log.append(f"🤖 Coder → {fname} ({lang}, {result.get('char_count', '?')} chars)")
            elif tool == "write_file":
                p = args.get("path", "?")
                files_modified.append(p)
                action_log.append(f"✏️ Wrote: {p}")
            elif tool == "patch_file":
                p = args.get("path", "?")
                files_modified.append(p)
                action_log.append(f"🩹 Patched: {p}")
            elif tool == "delete_file":
                p = args.get("path", "?")
                files_deleted.append(p)
                action_log.append(f"🗑️ Deleted: {p}")
            elif tool == "run_command":
                cmd = args.get("command", "?")
                rc = result.get("returncode", "?")
                commands_run.append(cmd)
                action_log.append(f"🖥️ `{cmd}` → exit {rc}")
            elif tool == "install_deps":
                action_log.append(f"📦 Dependencies installed")
            elif tool == "run_tests":
                action_log.append(f"🧪 Tests → {'✅' if success else '⚠️'}")
            elif tool == "lint_file":
                p = args.get("path", "?")
                action_log.append(f"🔍 Lint: {p} → {'✅ OK' if success else '⚠️ issues'}")
            elif tool == "read_file":
                pass  # Don't clutter the summary with reads
            elif tool == "list_directory":
                pass
            elif tool == "search_text":
                action_log.append(f"🔎 Search: {args.get('query', '?')}")
            elif tool == "web_search":
                action_log.append(f"🌐 Web search: {args.get('query', '?')}")
            elif tool == "fetch_url":
                action_log.append(f"🌐 Fetched: {args.get('url', '?')[:60]}")
            elif tool in ("git_add", "git_commit", "git_push"):
                msg = args.get("message", "")
                action_log.append(f"📦 {tool}: {msg}" if msg else f"📦 {tool}")
            elif tool == "export_project":
                action_log.append(f"📦 ZIP export: {result.get('message', '?')}")
            elif tool == "build_project":
                action_log.append(f"🔨 Build: {result.get('build_command', '?')}")
            elif tool == "preview_web":
                action_log.append(f"🌐 Preview: {result.get('url', '?')}")
            else:
                action_log.append(f"🔧 {tool}")
            
            if not success and result.get("error"):
                errors.append(f"⚠️ {tool}: {result['error'][:80]}")
        
        # Build structured summary
        elapsed = round(time.time() - self.state.started_at, 1)
        parts = [f"## 📋 Zusammenfassung\n"]
        parts.append(f"**Aufgabe:** {self.task}\n")
        parts.append(f"**{final_step} Schritte** · **{len(self.state.tool_calls)} Tool-Aufrufe** · **{elapsed}s**\n")
        
        if files_created:
            basenames = [os.path.basename(f) for f in files_created]
            parts.append(f"\n**Neue Dateien ({len(files_created)}):**")
            for f in files_created:
                parts.append(f"  • `{f}`")
        
        if files_modified:
            parts.append(f"\n**Geänderte Dateien ({len(files_modified)}):**")
            for f in files_modified:
                parts.append(f"  • `{f}`")
        
        if files_deleted:
            parts.append(f"\n**Gelöschte Dateien ({len(files_deleted)}):**")
            for f in files_deleted:
                parts.append(f"  • `{f}`")
        
        if commands_run:
            parts.append(f"\n**Ausgeführte Befehle ({len(commands_run)}):**")
            for c in commands_run:
                parts.append(f"  • `{c}`")
        
        if errors:
            parts.append(f"\n**Warnungen/Fehler:**")
            for e in errors:
                parts.append(f"  {e}")
        
        # Now ask the model for a brief human-readable explanation
        try:
            summary_prompt = (
                "Fasse kurz zusammen was du gerade gemacht hast. "
                "Erkläre in 2-4 Sätzen (auf Deutsch!) was passiert ist und das Ergebnis. "
                "Sei konkret — nenne Dateien, Technologien und Änderungen. "
                "Falls es Fehler gab, erkläre das Problem. "
                "Antworte direkt, keine Markdown-Überschriften. IMMER auf Deutsch."
            )
            log_text = "\n".join(action_log) if action_log else "Keine Aktionen."
            model_summary = self.generator.generate(
                "Du bist Ailey. Fasse deine erledigte Arbeit kurz und präzise zusammen. Antworte auf Deutsch.",
                f"Aufgabe: {self.task}\n\nAktionen:\n{log_text}\n\n{summary_prompt}",
                {"max_tokens": 800, "temperature": 0.4},
            )
            if "</think>" in model_summary:
                model_summary = model_summary.split("</think>", 1)[-1].strip()
            if "</thinking>" in model_summary:
                model_summary = model_summary.split("</thinking>", 1)[-1].strip()
            if "</thought>" in model_summary:
                model_summary = model_summary.split("</thought>", 1)[-1].strip()
            if model_summary.strip():
                parts.append(f"\n---\n{model_summary.strip()}")
        except Exception as e:
            _log.warning(f"Summary generation failed: {e}")
        
        return "\n".join(parts)
    
    def _build_activity(self, tool_name: str, args: dict, result: dict) -> dict | None:
        """Build a compact activity event for inline chat display.
        
        Returns a dict with: icon, label, detail, success — or None to skip.
        These are rendered as small inline activity items in the chat UI,
        similar to VS Code Copilot's checkmark items.
        """
        success = result.get("success", False)
        
        # Skip read-only tools (too noisy)
        if tool_name in ("read_file", "list_directory", "project_info", "recall_conversation",
                         "search_text", "git_status", "git_log", "git_diff", "system_info"):
            return None
        
        path = args.get("path", "")
        basename = os.path.basename(path) if path else ""
        
        if tool_name == "delegate_to_coder":
            fname = args.get("filename", "?")
            lang = args.get("language", "?")
            return {"icon": "🤖", "label": f"Coder generiert `{fname}` ({lang})",
                    "success": success, "detail": result.get("message", "")}
        elif tool_name == "create_file":
            return {"icon": "✨", "label": f"Erstellt `{basename}`", "success": success,
                    "detail": path}
        elif tool_name == "write_file":
            return {"icon": "📝", "label": f"Geschrieben `{basename}`", "success": success,
                    "detail": path}
        elif tool_name == "patch_file":
            return {"icon": "🩹", "label": f"Gepatcht `{basename}`", "success": success,
                    "detail": path}
        elif tool_name == "delete_file":
            return {"icon": "🗑️", "label": f"Gelöscht `{basename}`", "success": success,
                    "detail": path}
        elif tool_name == "create_directory":
            return {"icon": "📁", "label": f"Ordner erstellt `{basename}`", "success": success,
                    "detail": path}
        elif tool_name == "run_command":
            cmd = args.get("command", "?")
            rc = result.get("returncode", "?")
            return {"icon": "▶️", "label": f"`{cmd[:50]}`", "success": rc == 0,
                    "detail": f"exit {rc}"}
        elif tool_name == "install_deps":
            return {"icon": "📦", "label": "Dependencies installiert", "success": success}
        elif tool_name == "run_tests":
            return {"icon": "🧪", "label": "Tests ausgeführt", "success": success,
                    "detail": result.get("message", "")}
        elif tool_name == "lint_file":
            return {"icon": "🔍", "label": f"Lint `{basename}`", "success": success,
                    "detail": result.get("message", "")}
        elif tool_name == "web_search":
            q = args.get("query", "?")
            return {"icon": "🌐", "label": f"Suche: {q[:40]}", "success": success}
        elif tool_name == "fetch_url":
            url = args.get("url", "?")
            return {"icon": "🌐", "label": f"Geladen: {url[:40]}", "success": success}
        elif tool_name in ("git_add", "git_commit", "git_push", "git_pull",
                           "git_checkout", "git_stash"):
            msg = args.get("message", "")
            return {"icon": "📦", "label": f"{tool_name.replace('git_', 'Git ')}{': ' + msg[:30] if msg else ''}",
                    "success": success}
        elif tool_name == "notification":
            return {"icon": "🔔", "label": args.get("title", "Benachrichtigung"), "success": success}
        elif tool_name == "export_project":
            return {"icon": "📦", "label": f"Projekt exportiert als ZIP", "success": success,
                    "detail": result.get("message", "")}
        elif tool_name == "build_project":
            cmd = result.get("build_command", "build")
            return {"icon": "🔨", "label": f"Build: `{cmd[:40]}`", "success": success}
        elif tool_name == "preview_web":
            url = result.get("url", "?")
            return {"icon": "🌐", "label": f"Preview: {url}", "success": success}
        else:
            return {"icon": "🔧", "label": tool_name, "success": success}

    def _generate_with_timeout(self, system: str, user: str, params: dict,
                                tools: list = None, timeout: int = 300) -> str:
        """Run generate() in a thread pool with a hard timeout.
        
        This is the KEY fix: generate() blocks inside _mlx_lock while
        processing the prompt (30-60s for large prompts on 14B).
        stream() has the same problem — the in-loop timeout never fires
        because stream_generate blocks before yielding the first token.
        
        By running generate() in a ThreadPoolExecutor, we get a REAL
        timeout that works even during prompt processing.
        """
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-gen") as pool:
            future = pool.submit(self.generator.generate, system, user, params, tools)
            try:
                result = future.result(timeout=timeout)
                return result
            except FuturesTimeout:
                _agent_log(f"⏰ Generation timeout after {timeout}s")
                # Can't actually kill the MLX thread, but we return immediately
                # The generation will finish in the background and release the lock
                return "[AGENT_ERROR]Generation-Timeout[/AGENT_ERROR]"
            except Exception as e:
                _agent_log(f"❌ Generation error: {e}")
                return ""

    def run(self):
        """Run the agent loop (blocking — call in a thread).
        
        Two-phase approach:
          Phase 1: PLANNING — compact prompt, no tools, short generation → fast plan
          Phase 2: EXECUTION — tools included, one step at a time with timeout
        """
        self.state.status = "running"
        self.on_update("status", {"status": "running", "task": self.task})
        _agent_log(f"🚀 Starting agent: '{self.task[:80]}' (mode={self.mode})")
        
        step = 0
        retry_count = 0
        max_retries_per_step = 3
        _swapped_to_coder = False
        
        try:
            # ════════════════════════════════════════════════════════
            # PHASE 1: PLANNING — no tools, compact prompt, 60s timeout
            # ════════════════════════════════════════════════════════
            self.on_update("step", {"step": 1, "max_steps": self.max_steps, "status": "planning"})
            _agent_log("📋 Phase 1: Planning (no tools, compact prompt)...")
            
            plan_system = self._build_system_prompt(planning=True)
            plan_user = f"Task: {self.task}"
            
            if self.mode == "code" and self.project_root:
                plan_user += f"\n📂 Project: {self.project_root}"
            
            plan_reply = self._generate_with_timeout(
                plan_system, plan_user,
                {"max_tokens": 1200, "temperature": 0.3},
                tools=None,  # NO tools for planning
                timeout=7200,
            )
            
            _agent_log(f"📋 Plan reply ({len(plan_reply)} chars): {plan_reply[:200]}...")
            
            if self.state._abort:
                self.state.status = "stopped"
                self.on_update("stopped", {"step": 0, "reason": "User-Abbruch"})
                return self.state
            
            # Strip <think>...</think> from plan reply
            plan_reply = re.sub(r'<think>.*?</think>', '', plan_reply, flags=re.DOTALL).strip()
            
            # Parse [PLAN] from reply
            plan_match = re.search(r'\[PLAN\](.*?)\[/PLAN\]', plan_reply, re.DOTALL)
            if plan_match:
                try:
                    plan_json = json.loads(plan_match.group(1).strip())
                    plan_steps = plan_json.get("steps", [])
                    self.state.plan = {
                        "steps": [
                            {"id": i + 1, "title": s.get("title", f"Schritt {i+1}"), "status": "pending"}
                            for i, s in enumerate(plan_steps)
                        ]
                    }
                    self.state.total_steps = len(plan_steps)
                    self.on_update("plan", {"plan": self.state.plan})
                    _agent_log(f"✅ Plan parsed: {len(plan_steps)} steps")
                except (json.JSONDecodeError, AttributeError) as e:
                    _agent_log(f"⚠️ Plan parse failed: {e} — continuing without plan")
            else:
                _agent_log("⚠️ No [PLAN] block found — continuing without plan")
            
            # ════════════════════════════════════════════════════════
            # MODEL SWAP: Code mode → CodeA!ley (Qwen2.5-Coder-14B)
            # ════════════════════════════════════════════════════════
            if self.mode == "code":
                try:
                    from .llm_mlx import is_coder_available, swap_to_coder, get_active_model_tag
                    if is_coder_available():
                        _agent_log("🔄 Swapping to CodeA!ley (Qwen2.5-Coder-14B)...")
                        self.on_update("status", {"status": "swapping_model", "detail": "Loading Coder model..."})
                        ok = swap_to_coder()
                        if ok:
                            _swapped_to_coder = True
                            # Re-get the generator instance (now backed by Coder model)
                            from .llm_mlx import MLXGenerator
                            coder_gen = MLXGenerator.get()
                            if coder_gen:
                                self.generator = coder_gen
                            _agent_log(f"✅ Coder model active ({get_active_model_tag()})")
                        else:
                            _agent_log("⚠️ Coder swap failed — continuing with chat model")
                    else:
                        _agent_log("ℹ️ Coder model not downloaded — using chat model for code mode")
                except Exception as e:
                    _agent_log(f"⚠️ Coder swap error: {e} — continuing with chat model")

            # ════════════════════════════════════════════════════════
            # PHASE 2: EXECUTION — with tools, one step at a time
            # ════════════════════════════════════════════════════════
            _agent_log("⚙️ Phase 2: Execution...")
            
            tool_schemas = self._get_tool_schemas()
            exec_system = self._build_system_prompt(planning=False)
            
            # Build initial conversation for execution phase
            plan_text = ""
            if self.state.plan:
                plan_titles = [f"{s['id']}. {s['title']}" for s in self.state.plan["steps"]]
                plan_text = "Your plan:\n" + "\n".join(plan_titles) + "\n\n"
            
            conversation = [
                {"role": "system", "content": exec_system},
                {"role": "user", "content": f"{plan_text}Task: {self.task}\n\nStart with step 1. Use a tool."},
            ]
            
            _agent_log(f"📝 Execution prompt: system={len(exec_system)} chars, {len(tool_schemas)} tools")
            
            # ── Track productive work to prevent premature [AGENT_DONE] ──
            _WRITE_TOOLS = {"write_file", "create_file", "patch_file", "delete_file",
                            "git_commit", "git_push", "run_command", "install_deps",
                            "delegate_to_coder", "create_directory"}
            _productive_tool_count = 0  # counts calls to write/create/patch/commit tools
            _last_active_plan_step = 0  # for auto-emitting plan_update
            
            while step < self.max_steps:
                # Check abort
                if self.state._abort:
                    self.state.status = "stopped"
                    self.on_update("stopped", {"step": step, "reason": "User abort"})
                    break
                
                # Check pause
                while self.state._pause:
                    time.sleep(0.5)
                    if self.state._abort:
                        break
                if self.state._abort:
                    break
                
                step += 1
                self.state.current_step = step
                self.on_update("step", {"step": step, "max_steps": self.max_steps, "status": "generating"})
                _agent_log(f"🧠 Step {step}: generating...")
                
                # Build user context from conversation history
                # Keep last 10 messages, then compress old tool_results to save tokens
                max_history = 10
                recent = conversation[-max_history:] if len(conversation) > max_history else conversation
                full_system = recent[0]["content"] if recent[0]["role"] == "system" else exec_system

                # How many messages from the end to keep UNCOMPRESSED
                # (the last 4 = ~2 complete tool exchanges)
                _KEEP_INTACT = 4

                user_context_parts = []
                msgs_from_end = len(recent) - 1  # excludes system at index 0
                for i, msg in enumerate(recent[1:]):
                    idx_from_end = msgs_from_end - i  # 0 = last msg
                    role = msg["role"]
                    content = msg["content"]

                    if role == "tool_result" and idx_from_end > _KEEP_INTACT:
                        # Compress old tool results to a short summary line
                        # Extract first line (usually "[tool_name]: OK / message")
                        first_line = content.split("\n")[0][:200]
                        content = f"[Ergebnis gekürzt] {first_line}"
                    elif role == "tool_result":
                        # Even recent tool results: hard cap at 3000 chars total
                        if len(content) > 3000:
                            content = content[:3000] + f"\n… (gekürzt, {len(msg['content'])} Zeichen gesamt)"

                    if role == "user":
                        user_context_parts.append(f"[User]: {content}")
                    elif role == "assistant":
                        user_context_parts.append(f"[Ailey]: {content}")
                    elif role == "tool_result":
                        user_context_parts.append(f"[Tool-Ergebnis]: {content}")

                full_user = "\n\n".join(user_context_parts)
                
                # ── Log prompt size for debugging ──
                prompt_chars = len(full_system) + len(full_user)
                _agent_log(f"📐 Step {step} prompt: system={len(full_system)} + user={len(full_user)} = {prompt_chars} chars, {len(tool_schemas)} tools, history={len(recent)} msgs")
                
                # ── Generate with REAL timeout ──
                # Dynamic timeout: base 600s + 60s per step (history grows)
                # Cap the per-step timeout to 7200s (2 hours) to allow
                # long-running code-mode generations without premature abort.
                step_timeout = min(600 + step * 60, 7200)
                gen_start = time.time()
                # CodeMode uses temp 0.7 (balanced creativity + format compliance), others 0.3
                _exec_temp = 0.7 if self.mode == "code" else 0.3
                reply = self._generate_with_timeout(
                    full_system, full_user,
                    {"max_tokens": 3000, "temperature": _exec_temp},
                    tools=tool_schemas,
                    timeout=step_timeout,
                )
                gen_elapsed = round(time.time() - gen_start, 1)
                
                # Strip <think> blocks
                reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()
                
                _agent_log(f"✅ Step {step}: {len(reply)} chars in {gen_elapsed}s — reply: {reply[:120]}...")
                
                if self.state._abort:
                    break
                
                # ── Handle empty reply ──
                if not reply:
                    _agent_log(f"⚠️ Step {step}: empty reply (retry {retry_count+1}/{max_retries_per_step})")
                    retry_count += 1
                    conversation.append({"role": "assistant", "content": "(leere Antwort)"})
                    conversation.append({
                        "role": "user",
                        "content": "Your reply was empty. Execute the next step or say [AGENT_DONE]."
                    })
                    if retry_count >= max_retries_per_step:
                        self.state.error = "Repeated empty replies"
                        self.state.status = "error"
                        self.on_update("error", {"error": self.state.error, "step": step})
                        break
                    continue
                
                # ── Parse [PLAN] — task decomposition ────────────────
                plan_match = re.search(r'\[PLAN\](.*?)\[/PLAN\]', reply, re.DOTALL)
                if plan_match:
                    try:
                        plan_json = json.loads(plan_match.group(1).strip())
                        plan_steps = plan_json.get("steps", [])
                        # Normalize plan steps
                        self.state.plan = {
                            "steps": [
                                {"id": i + 1, "title": s.get("title", f"Schritt {i+1}"), "status": "pending"}
                                for i, s in enumerate(plan_steps)
                            ]
                        }
                        self.state.total_steps = len(plan_steps)
                        self.on_update("plan", {"plan": self.state.plan})
                        _log.info(f"Agent plan: {len(plan_steps)} steps")
                    except (json.JSONDecodeError, AttributeError) as e:
                        _log.warning(f"Plan parsing failed: {e}")
                    # Remove plan from reply text
                    reply = re.sub(r'\[PLAN\].*?\[/PLAN\]', '', reply, flags=re.DOTALL).strip()
                
                # ── Parse [PLAN_REVISION] — agent revises its own plan mid-execution ──
                plan_rev_match = re.search(r'\[PLAN_REVISION\](.*?)\[/PLAN_REVISION\]', reply, re.DOTALL)
                if plan_rev_match:
                    try:
                        rev_json = json.loads(plan_rev_match.group(1).strip())
                        new_steps = rev_json.get("steps", [])
                        if new_steps and self.state.plan:
                            # Keep already-done steps, replace pending ones with revised steps
                            done_steps = [s for s in self.state.plan["steps"] if s["status"] == "done"]
                            next_id = (done_steps[-1]["id"] + 1) if done_steps else 1
                            new_plan_steps = done_steps + [
                                {"id": next_id + i, "title": s.get("title", f"Schritt {next_id+i}"), "status": "pending"}
                                for i, s in enumerate(new_steps)
                            ]
                            self.state.plan["steps"] = new_plan_steps
                            self.state.total_steps = len(new_plan_steps)
                            self.on_update("plan", {"plan": self.state.plan})
                            _agent_log(f"📋 Plan revidiert: {len(done_steps)} done + {len(new_steps)} neue Schritte")
                    except (json.JSONDecodeError, AttributeError) as e:
                        _agent_log(f"⚠️ Plan-Revision parse failed: {e}")
                    reply = re.sub(r'\[PLAN_REVISION\].*?\[/PLAN_REVISION\]', '', reply, flags=re.DOTALL).strip()

                # ── Parse [STEP_DONE:N], [STEP_ACTIVE:N], [STEP_COMMENT:N:text] ──
                for sd_match in re.finditer(r'\[STEP_DONE:(\d+)\]', reply):
                    step_id = int(sd_match.group(1))
                    if self.state.plan:
                        for ps in self.state.plan["steps"]:
                            if ps["id"] == step_id:
                                ps["status"] = "done"
                    self.on_update("plan_update", {"step_id": step_id, "status": "done"})
                
                for sa_match in re.finditer(r'\[STEP_ACTIVE:(\d+)\]', reply):
                    step_id = int(sa_match.group(1))
                    if self.state.plan:
                        for ps in self.state.plan["steps"]:
                            if ps["id"] == step_id:
                                ps["status"] = "active"
                    self.on_update("plan_update", {"step_id": step_id, "status": "active"})
                
                for sc_match in re.finditer(r'\[STEP_COMMENT:(\d+):(.*?)\]', reply):
                    step_id = int(sc_match.group(1))
                    comment = sc_match.group(2).strip()
                    self.on_update("plan_update", {"step_id": step_id, "comment": comment})
                
                # Clean step markers from reply text for conversation
                reply = re.sub(r'\[STEP_(?:DONE|ACTIVE):\d+\]', '', reply)
                reply = re.sub(r'\[STEP_COMMENT:\d+:.*?\]', '', reply)
                reply = reply.strip()
                
                # Check for completion signals
                if "[AGENT_DONE]" in reply:
                    # ── ANTI-PREMATURE GUARD ──────────────────────────
                    # Reject [AGENT_DONE] if the agent hasn't done any productive work
                    # (no write/create/patch/commit/run_command calls yet).
                    # This prevents the model from giving up after only reading files.
                    _MIN_STEPS_FOR_DONE = 3  # must be at least step 3
                    if _productive_tool_count == 0 and step < _MIN_STEPS_FOR_DONE + 2:
                        _agent_log(f"🚫 Step {step}: PREMATURE [AGENT_DONE] rejected — 0 productive tool calls, step {step}")
                        # Strip [AGENT_DONE] and inject a nudge to keep working
                        reply = reply.replace("[AGENT_DONE]", "").strip()
                        if reply:
                            conversation.append({"role": "assistant", "content": reply})
                        conversation.append({
                            "role": "user",
                            "content": (
                                "STOPP — du hast noch KEINE Dateien geschrieben oder verändert! "
                                "Du hast nur gelesen/erkundet. Das ist erst der Anfang.\n\n"
                                "Arbeite jetzt den Plan ab:\n"
                                "1. Du hast die Struktur gesehen → GUT\n"
                                "2. Jetzt: Lies die relevanten Dateien die du ändern musst\n"
                                "3. Dann: Schreibe/ändere den Code mit patch_file oder write_file\n"
                                "4. Verifiziere mit lint_file\n"
                                "5. ERST DANN darfst du [AGENT_DONE] sagen.\n\n"
                                "Fang jetzt an — nächster Schritt, Tool aufrufen!"
                            )
                        })
                        self.on_update("message", {
                            "text": "⚠️ Agent wollte vorzeitig aufhören — wurde zurück an die Arbeit geschickt.",
                            "step": step,
                        })
                        retry_count = 0
                        continue  # Back to the generation loop

                    text_before = reply.split("[AGENT_DONE]")[0].strip()
                    if text_before:
                        self.on_update("message", {"text": text_before, "step": step})
                    
                    # Mark all remaining plan steps as done
                    if self.state.plan:
                        for ps in self.state.plan["steps"]:
                            if ps["status"] != "done":
                                ps["status"] = "done"
                                self.on_update("plan_update", {"step_id": ps["id"], "status": "done"})
                    
                    # ── Generate a detailed summary of what was done ─────
                    summary = self._generate_summary(step)
                    if summary:
                        self.on_update("message", {"text": summary, "step": step, "is_summary": True})
                    
                    self.state.status = "done"
                    self.state.finished_at = time.time()
                    self.on_update("done", {
                        "step": step,
                        "elapsed": round(time.time() - self.state.started_at, 1),
                        "tool_calls": len(self.state.tool_calls),
                        "summary": summary,
                    })
                    break
                
                if "[AGENT_ERROR]" in reply:
                    err_match = re.search(r'\[AGENT_ERROR\](.*?)\[/AGENT_ERROR\]', reply, re.DOTALL)
                    error_msg = err_match.group(1).strip() if err_match else "Unbekannter Fehler"
                    self.state.error = error_msg
                    self.state.status = "error"
                    self.on_update("error", {"error": error_msg, "step": step})
                    break
                
                if "[AGENT_ASK]" in reply:
                    ask_match = re.search(r'\[AGENT_ASK\](.*?)\[/AGENT_ASK\]', reply, re.DOTALL)
                    question = ask_match.group(1).strip() if ask_match else reply
                    self.state.status = "waiting"
                    self.on_update("ask", {"question": question, "step": step})
                    # Wait for answer (will be resumed by external code setting conversation)
                    break
                
                # Check for tool calls (Mistral format OR Qwen format)
                _has_tool_call = "[TOOL_CALLS]" in reply or "<tool_call>" in reply
                if _has_tool_call:
                    text_before = extract_text_before_tools(reply)
                    if text_before.strip():
                        self.on_update("message", {"text": text_before, "step": step})
                        conversation.append({"role": "assistant", "content": text_before})
                    
                    tool_calls = parse_tool_calls(reply)
                    tool_results = []
                    
                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        
                        # Inject project_root if not set
                        if self.project_root and "project_root" in str(get_tool_schemas()):
                            if "project_root" not in tool_args and tool_name in (
                                "read_file", "write_file", "create_file", "patch_file",
                                "delete_file", "create_directory", "list_directory",
                                "search_text", "project_info", "install_deps", "run_tests",
                                "lint_file", "git_status", "git_diff", "git_add", "git_commit",
                                "git_push", "git_pull", "git_log", "git_checkout", "git_stash",
                                "recall_conversation",
                            ):
                                tool_args["project_root"] = self.project_root
                            if "cwd" not in tool_args and tool_name == "run_command":
                                tool_args["cwd"] = self.project_root
                        
                        self.on_update("tool_action", {
                            "tool": tool_name,
                            "arguments": tool_args,
                            "step": step,
                        })

                        # --- Chunking shortcut for delegate_to_coder ---
                        # If the model requests code generation via delegate_to_coder
                        # AND provides a filename for an EXISTING file that is large
                        # enough to warrant chunking, split it into chunks and call
                        # the coder model per-chunk using patch_file (safe, non-destructive).
                        # New files (no chunks) fall through to normal execute_tool.
                        if tool_name == "delegate_to_coder" and tool_args.get("filename"):
                            filename = tool_args.get("filename")
                            relpath = filename
                            if self.project_root and os.path.isabs(filename):
                                try:
                                    relpath = os.path.relpath(filename, self.project_root)
                                except Exception:
                                    relpath = filename

                            chunks = chunk_file(self.project_root or '.', relpath, max_chunk_lines=300)
                            if not chunks:
                                # File doesn't exist or is small — fall through to
                                # normal execute_tool below (no continue!)
                                pass
                            else:
                                # Process each chunk with the coder model
                                chunk_summaries = []
                                chunk_error = False
                                for ch in chunks:
                                    spec = tool_args.get("spec", "Generiere Code")
                                    chunk_spec = (
                                        f"Teil {ch.id} von {len(chunks)} für Datei {relpath}.\n"
                                        f"Zeilen {ch.start_line}-{ch.end_line}.\n\n"
                                        f"Kontext:\n{ch.context}\n\n"
                                        f"Spezifikation:\n{spec}"
                                    )
                                    coder_args = {
                                        "spec": chunk_spec,
                                        "language": tool_args.get("language", "python"),
                                        "filename": filename,
                                        "context": ch.context,
                                        "max_tokens": tool_args.get("max_tokens", 2048),
                                    }
                                    coder_result = execute_tool("delegate_to_coder", coder_args)
                                    self.state.tool_calls.append({
                                        "tool": "delegate_to_coder",
                                        "arguments": coder_args,
                                        "result": coder_result,
                                        "step": step,
                                    })
                                    self.on_update("tool_result", {
                                        "tool": "delegate_to_coder",
                                        "result": coder_result,
                                        "step": step,
                                    })

                                    if not coder_result.get("success"):
                                        chunk_summaries.append(f"Chunk {ch.id}: ERROR — {coder_result.get('error', 'Coder failed')}")
                                        self.on_update("error", {"error": coder_result.get("error", "Coder failed"), "step": step})
                                        chunk_error = True
                                        break

                                    code = coder_result.get("code", "")
                                    # Use patch_file to safely replace only this chunk's
                                    # line range — no destructive overwrite of the whole file.
                                    patch_args = {
                                        "path": os.path.join(self.project_root or '.', relpath),
                                        "patches": [{"start_line": ch.start_line, "end_line": ch.end_line, "content": code}],
                                        "project_root": self.project_root,
                                    }
                                    patch_result = execute_tool("patch_file", patch_args)
                                    self.state.tool_calls.append({
                                        "tool": "patch_file",
                                        "arguments": patch_args,
                                        "result": patch_result,
                                        "step": step,
                                    })
                                    self.on_update("tool_result", {"tool": "patch_file", "result": patch_result, "step": step})
                                    self.on_update("plan_update", {"step_id": ch.id, "status": "done", "detail": f"Chunk {ch.id}/{len(chunks)} patched in {relpath}"})
                                    chunk_summaries.append(f"Chunk {ch.id}/{len(chunks)}: OK (lines {ch.start_line}-{ch.end_line})")

                                # Build a summary for the model's conversation history
                                status = "with errors" if chunk_error else "successfully"
                                tool_results.append(f"[delegate_to_coder]: Chunked edit of {relpath} ({len(chunks)} chunks) completed {status}.\n" + "\n".join(chunk_summaries))
                                _act = self._build_activity(tool_name, tool_args, {"success": not chunk_error, "message": f"{len(chunks)} chunks processed"})
                                if _act:
                                    self.on_update("activity", _act)
                                continue
                        
                        # Execute
                        result = execute_tool(tool_name, tool_args)
                        
                        self.state.tool_calls.append({
                            "tool": tool_name,
                            "arguments": tool_args,
                            "result": result,
                            "step": step,
                        })
                        
                        self.on_update("tool_result", {
                            "tool": tool_name,
                            "result": result,
                            "step": step,
                        })
                        
                        # ── Emit compact activity event for inline chat display ──
                        _act = self._build_activity(tool_name, tool_args, result)
                        if _act:
                            self.on_update("activity", _act)
                        
                        # ── Track productive (write) tool calls ──
                        if tool_name in _WRITE_TOOLS and result.get("success"):
                            _productive_tool_count += 1
                            _agent_log(f"✏️ Productive tool #{_productive_tool_count}: {tool_name}")
                        
                        # ── AUTO PLAN-STEP UPDATE ──────────────────────
                        # When the model doesn't emit [STEP_DONE:N] / [STEP_ACTIVE:N],
                        # we infer progress from tool calls. Each productive tool call
                        # advances the plan by one step (heuristic).
                        if self.state.plan and self.state.plan.get("steps"):
                            plan_steps_list = self.state.plan["steps"]
                            # Find current active step or first pending
                            current_plan_step = None
                            for ps in plan_steps_list:
                                if ps["status"] == "active":
                                    current_plan_step = ps
                                    break
                            if not current_plan_step:
                                for ps in plan_steps_list:
                                    if ps["status"] == "pending":
                                        current_plan_step = ps
                                        break
                            # Mark first pending as active if nothing is active yet
                            if current_plan_step and current_plan_step["status"] == "pending":
                                current_plan_step["status"] = "active"
                                self.on_update("plan_update", {"step_id": current_plan_step["id"], "status": "active"})
                                _last_active_plan_step = current_plan_step["id"]
                            # After a productive tool: mark current active step as done,
                            # advance to next pending step
                            if tool_name in _WRITE_TOOLS and result.get("success") and current_plan_step and current_plan_step["status"] == "active":
                                current_plan_step["status"] = "done"
                                self.on_update("plan_update", {"step_id": current_plan_step["id"], "status": "done"})
                                _agent_log(f"📋 Auto plan: step {current_plan_step['id']} '{current_plan_step['title']}' → done")
                                # Activate next pending step
                                for ps in plan_steps_list:
                                    if ps["status"] == "pending":
                                        ps["status"] = "active"
                                        self.on_update("plan_update", {"step_id": ps["id"], "status": "active"})
                                        _last_active_plan_step = ps["id"]
                                        _agent_log(f"📋 Auto plan: step {ps['id']} '{ps['title']}' → active")
                                        break
                        
                        # ── AUTO-LINT: In coder mode, auto-lint after file edits ──
                        if _swapped_to_coder and tool_name in ("write_file", "create_file", "patch_file") and result.get("success"):
                            _lint_path = tool_args.get("path", "")
                            if _lint_path and _lint_path.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".rs")):
                                try:
                                    lint_result = execute_tool("lint_file", {
                                        "path": _lint_path,
                                        "project_root": self.project_root,
                                    })
                                    self.state.tool_calls.append({
                                        "tool": "lint_file",
                                        "arguments": {"path": _lint_path},
                                        "result": lint_result,
                                        "step": step,
                                    })
                                    _lint_act = self._build_activity("lint_file", {"path": _lint_path}, lint_result)
                                    if _lint_act:
                                        self.on_update("activity", _lint_act)
                                    if not lint_result.get("success") and lint_result.get("errors"):
                                        # Inject lint errors into tool results so model can fix them
                                        lint_errors_text = lint_result.get("message", "") or str(lint_result.get("errors", ""))
                                        if len(lint_errors_text) > 1000:
                                            lint_errors_text = lint_errors_text[:1000] + "…"
                                        tool_results.append(f"[auto_lint:{os.path.basename(_lint_path)}]: ⚠️ LINT ERRORS — fix these:\n{lint_errors_text}")
                                        _agent_log(f"⚠️ Auto-lint found errors in {_lint_path}")
                                    else:
                                        _agent_log(f"✅ Auto-lint OK: {_lint_path}")
                                except Exception as lint_err:
                                    _agent_log(f"⚠️ Auto-lint failed: {lint_err}")
                        
                        # Build result summary for model
                        # IMPORTANT: Keep results SHORT — each char here costs tokens later.
                        # Limits: read_file 2000, run_command stdout 1500+stderr 600,
                        #         fetch_url 2000, search 3 results, list_dir 50 entries.
                        if result.get("success"):
                            summary = result.get("message", "OK")
                            # Include file content for read_file (hard cap: 2000 chars)
                            if tool_name == "read_file" and result.get("content"):
                                content = result['content']
                                total = len(content)
                                if total > 2000:
                                    content = content[:2000] + f"\n… ({total} Zeichen gesamt, gekürzt)"
                                summary += f"\n\nDateiinhalt:\n{content}"
                            # Include command output (hard cap: 1500 stdout, 600 stderr)
                            if tool_name == "run_command":
                                if result.get("stdout"):
                                    out = result['stdout']
                                    if len(out) > 1500:
                                        out = out[:1500] + f"\n… ({len(result['stdout'])} Zeichen, gekürzt)"
                                    summary += f"\n\nOutput:\n{out}"
                                if result.get("stderr"):
                                    err = result['stderr']
                                    if len(err) > 600:
                                        err = err[:600] + "…"
                                    summary += f"\n\nStderr:\n{err}"
                            # Include search results (max 3, short snippets)
                            if tool_name in ("web_search", "search_text") and result.get("results"):
                                for r in result["results"][:3]:
                                    if isinstance(r, dict):
                                        title = r.get('title', r.get('file', ''))
                                        snip = r.get('snippet', r.get('text', ''))[:200]
                                        summary += f"\n• {title}: {snip}"
                            # Include fetch_url content (hard cap: 2000 chars)
                            if tool_name == "fetch_url" and result.get("content"):
                                fc = result['content']
                                if len(fc) > 2000:
                                    fc = fc[:2000] + f"\n… ({len(result['content'])} Zeichen, gekürzt)"
                                summary += f"\n\n{fc}"
                            # Include directory listing — include base path so model knows where things are
                            if tool_name == "list_directory" and result.get("entries"):
                                base_path = result.get("path", tool_args.get("path", "."))
                                if self.project_root and base_path.startswith(self.project_root):
                                    base_path = os.path.relpath(base_path, self.project_root)
                                summary += f"\n📂 Inhalt von '{base_path}':"
                                entries = result["entries"][:50]
                                for e in entries:
                                    summary += f"\n  {'📁' if e.get('type')=='directory' else '📄'} {e['name']}"
                                if len(result["entries"]) > 50:
                                    summary += f"\n  … ({len(result['entries'])} Einträge gesamt)"
                            # Include project info
                            if tool_name == "project_info":
                                if result.get("frameworks"):
                                    summary += f"\nFrameworks: {', '.join(result['frameworks'])}"
                                if result.get("files"):
                                    summary += f"\nDateien ({result.get('file_count', '?')}):\n" + "\n".join(result["files"][:15])
                            # Include recall_conversation results
                            if tool_name == "recall_conversation" and result.get("formatted"):
                                hist = result['formatted']
                                if len(hist) > 1000:
                                    hist = hist[:1000] + "…"
                                summary += f"\n\nHistory:\n{hist}"
                        else:
                            summary = f"FEHLER: {result.get('error', 'Unbekannter Fehler')}"
                        
                        tool_results.append(f"[{tool_name}]: {summary}")
                    
                    # Add tool results to conversation
                    result_text = "\n\n".join(tool_results)
                    conversation.append({"role": "tool_result", "content": result_text})
                    _agent_log(f"🔧 Step {step}: {len(tool_results)} tool(s) executed, result_text={len(result_text)} chars")
                    
                    retry_count = 0  # Reset retry on successful tool call
                    
                else:
                    # No tool call — just text response
                    self.on_update("message", {"text": reply, "step": step})
                    conversation.append({"role": "assistant", "content": reply})

                    # Check if the reply contains step markers — if so, it's progress, not idle
                    has_progress = bool(re.search(r'\[STEP_(?:DONE|ACTIVE):\d+\]', reply))

                    if has_progress:
                        # Model is reporting progress — prompt it to continue with tool
                        retry_count = 0
                        conversation.append({
                            "role": "user",
                            "content": "Gut. Führe jetzt den nächsten Schritt aus — ruf ein Tool auf."
                        })
                    else:
                        # Model is talking without doing anything — give explicit format reminder
                        retry_count += 1
                        if retry_count == 1:
                            # First gentle nudge
                            conversation.append({
                                "role": "user",
                                "content": (
                                    "Bitte ruf jetzt ein Tool auf. Nutze das Format:\n"
                                    "[TOOL_CALLS]tool_name[ARGS]{\"param\": \"wert\"}\n"
                                    "Beispiel: [TOOL_CALLS]list_directory[ARGS]{\"path\": \".\"}\n"
                                    "Oder sage [AGENT_DONE] wenn du fertig bist."
                                )
                            })
                        elif retry_count >= max_retries_per_step:
                            # Hard nudge — force a specific next action
                            next_step_hint = ""
                            if self.state.plan and self.state.plan.get("steps"):
                                pending = [s for s in self.state.plan["steps"] if s.get("status") != "done"]
                                if pending:
                                    next_step_hint = f" Nächster Schritt: {pending[0]['title']}"
                            conversation.append({
                                "role": "user",
                                "content": (
                                    f"Du hast {retry_count}x kein Tool aufgerufen.{next_step_hint}\n"
                                    "JETZT Tool aufrufen — exaktes Format:\n"
                                    "[TOOL_CALLS]tool_name[ARGS]{\"param\": \"wert\"}\n"
                                    "Wenn die Aufgabe wirklich fertig ist: [AGENT_DONE]"
                                )
                            })
                            retry_count = 0
            
            # Max steps reached
            if step >= self.max_steps and self.state.status == "running":
                self.state.status = "done"
                self.state.finished_at = time.time()
                self.on_update("done", {
                    "step": step,
                    "reason": f"Max Steps ({self.max_steps}) erreicht",
                    "elapsed": round(time.time() - self.state.started_at, 1),
                })
        
        except Exception as e:
            tb = traceback.format_exc()
            _log.error(f"Agent error: {e}\n{tb}")
            _agent_log(f"❌ Fatal error: {e}\n{tb}")
            try:
                traceback.print_exc(file=sys.stderr)
            except Exception:
                pass
            self.state.error = str(e)
            self.state.status = "error"
            self.on_update("error", {"error": str(e), "step": step})
        
        finally:
            # ── Swap back to chat model if we swapped to coder ──
            if _swapped_to_coder:
                try:
                    from .llm_mlx import swap_to_chat
                    _agent_log("🔄 Swapping back to Chat model (Ministral)...")
                    swap_to_chat()
                    _agent_log("✅ Chat model restored")
                except Exception as swap_err:
                    _agent_log(f"⚠️ Chat model swap-back failed: {swap_err}")

            # Cleanup after a delay
            def _cleanup():
                time.sleep(300)  # Keep state for 5 minutes
                with _agents_lock:
                    _active_agents.pop(self.task_id, None)
            threading.Thread(target=_cleanup, daemon=True).start()
        
        return self.state
    
    def run_async(self) -> str:
        """Start the agent in a background thread. Returns task_id."""
        thread = threading.Thread(target=self.run, daemon=True, name=f"agent-{self.task_id}")
        thread.start()
        return self.task_id
