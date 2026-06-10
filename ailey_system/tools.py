# -*- coding: utf-8 -*-
"""
Ailey Tool System — executable tools that Ailey can invoke during conversation.

Tools are defined as JSON schemas (Mistral/OpenAI function calling format)
and executed locally. Results are returned to the model as [TOOL_RESULTS].

Currently available tools:
  - create_calendar_event: Creates an .ics file and opens it in Apple Calendar
  - create_reminder: Creates a reminder via AppleScript
  - create_note: Saves a text note to Ailey's notes directory
  - get_current_time: Returns current date/time info
  - set_timer: Sets a macOS timer with notification
  - update_user_profile: Updates a personal fact in the user profile
"""
from __future__ import annotations
import os
import json
import time
import subprocess
import tempfile
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path
from .agent_config import run_subprocess

# Setup audit logging
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(
    filename=os.path.join(_PROJECT_ROOT, "audit_tools.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ─── Tool Registry ───────────────────────────────────────────────────────────

# Each tool has: name, description, parameters (JSON Schema), execute function
_TOOLS: Dict[str, Dict[str, Any]] = {}

# ── Tool Category Mapping ────────────────────────────────────────────────────
# Categories: "chat" (always available in chat), "code", "git", "web", "system"
# Tools not listed here default to "chat".
_TOOL_CATEGORIES: Dict[str, str] = {
    # --- Chat tools (tools.py) — always available in chat mode ---
    "list_calendar_events": "chat",
    "create_calendar_event": "chat",
    "create_reminder": "chat",
    "list_reminders": "chat",
    "complete_reminder": "chat",
    "create_recurring_reminder": "chat",
    "create_note": "chat",
    "get_current_time": "chat",
    "set_timer": "chat",
    "update_user_profile": "chat",
    "update_relationship": "chat",
    "generate_svg": "chat",
    "generate_er_diagram": "chat",
    "list_svg_gallery": "chat",
    "speak_text": "chat",
    "recognize_speech": "chat",
    "send_proactive_email": "chat",
    "get_weather": "chat",
    "generate_image": "image",
    # --- Web tools (tools_web.py) ---
    "web_search": "web",
    "fetch_url": "web",
    "npm_search": "web",
    "pypi_search": "web",
    # --- Code tools (tools_code.py) ---
    "read_file": "code",
    "write_file": "code",
    "patch_file": "code",
    "delete_file": "code",
    "create_file": "code",
    "create_directory": "code",
    "list_directory": "code",
    "search_text": "code",
    "run_command": "code",
    "run_tests": "code",
    "lint_file": "code",
    "install_deps": "code",
    "project_info": "code",
    "build_project": "code",
    "export_project": "code",
    "preview_web": "code",
    "ask_user": "code",
    "delegate_to_coder": "code",
    # --- Git tools (tools_git.py) ---
    "git_status": "git",
    "git_diff": "git",
    "git_add": "git",
    "git_commit": "git",
    "git_push": "git",
    "git_pull": "git",
    "git_log": "git",
    "git_checkout": "git",
    "git_stash": "git",
    # --- System tools (tools_system.py) ---
    "open_app": "system",
    "open_url": "system",
    "clipboard_read": "system",
    "clipboard_write": "system",
    "system_info": "system",
    "screenshot": "system",
    "notification": "system",
    # --- RAG knowledge search (portal + chat) ---
    "rag_search": "chat",
}


def register_tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool function."""
    def decorator(func):
        _TOOLS[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "function": func,
        }
        return func
    return decorator


def get_tool_schemas(categories: Optional[List[str]] = None) -> List[dict]:
    """Return tool definitions in Mistral function calling format.

    Args:
        categories: If given, only return tools from these categories.
                    E.g. ["chat", "web"] returns chat + web tools.
                    None = return ALL tools (backward compatible).
    """
    schemas = []
    for name, tool in _TOOLS.items():
        if categories is not None:
            cat = _TOOL_CATEGORIES.get(name, "chat")
            if cat not in categories:
                continue
        schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            }
        })
    return schemas


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a registered tool and return the result."""
    if name not in _TOOLS:
        return {"success": False, "error": f"Unknown tool: {name}"}

    # Handle parse errors from broken JSON
    if arguments.get("_parse_error"):
        return {
            "success": False, "tool": name,
            "error": f"Konnte die Argumente nicht parsen. Bitte versuche es nochmal mit gültigem JSON."
        }

    try:
        # Filter arguments to only those the function actually accepts
        import inspect
        func = _TOOLS[name]["function"]
        sig = inspect.signature(func)
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if not accepts_kwargs:
            valid_params = set(sig.parameters.keys())
            filtered_args = {k: v for k, v in arguments.items() if k in valid_params}
            if len(filtered_args) != len(arguments):
                dropped = set(arguments.keys()) - valid_params
                print(f"[Tools] ⚠️ Dropped unknown args for {name}: {dropped}")
        else:
            filtered_args = arguments

        # ── Check required parameters before calling ──────────────────
        # Prevents TypeError: func() missing required positional argument
        required_params = [
            p_name for p_name, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty
            and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]
        missing = [p for p in required_params if p not in filtered_args]
        if missing:
            print(f"[Tools] ❌ Missing required args for {name}: {missing} (got: {list(filtered_args.keys())})")
            return {
                "success": False, "tool": name,
                "error": f"Fehlende Parameter: {', '.join(missing)}. Bitte versuche den Tool-Call nochmal mit allen Pflichtfeldern."
            }

        result = func(**filtered_args)
        return {"success": True, "tool": name, **result}
    except Exception as e:
        return {"success": False, "tool": name, "error": str(e)}


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Parse tool calls from model output.
    
    Supports FOUR formats:
      1. Mistral:  [TOOL_CALLS]name[ARGS]{json}
      2. Qwen:     <tool_call>{"name": "...", "arguments": {...}}</tool_call>
      3. Trained:  [tool_call: func_name(key="val", ...)]
      4. Gemma 4:  <|tool_call>call:func_name{key:<|"|>val<|"|>}<tool_call|>
    
    Returns list of {name, arguments} dicts.
    """
    import re
    calls = []

    # ── Format 1: Mistral — [TOOL_CALLS]function_name[ARGS]{...json...} ──
    pattern = re.compile(r'\[TOOL_CALLS\]\s*(\w+)\[ARGS\](.*?)(?=\[TOOL_CALLS\]|$)', re.DOTALL)
    for match in pattern.finditer(text):
        name = match.group(1).strip()
        args_str = match.group(2).strip()
        arguments = _robust_json_parse(args_str, name)
        calls.append({"name": name, "arguments": arguments})

    # ── Format 2: Qwen — <tool_call>{"name": "...", "arguments": {...}}</tool_call> ──
    qwen_pattern = re.compile(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL)
    for match in qwen_pattern.finditer(text):
        try:
            obj = json.loads(match.group(1))
            name = obj.get("name", "")
            args = obj.get("arguments", {})
            if isinstance(args, str):
                args = _robust_json_parse(args, name)
            if name:
                calls.append({"name": name, "arguments": args})
        except json.JSONDecodeError:
            # Try robust parse on the whole content
            inner = match.group(1).strip()
            parsed = _robust_json_parse(inner, "tool_call")
            name = parsed.pop("name", "")
            args = parsed.pop("arguments", parsed)
            if name:
                calls.append({"name": name, "arguments": args})

    # ── Format 3: Trained — [tool_call: func_name(key="val", key2="val2")] ──
    # This is the format Ailey was trained on via DoRA.
    trained_pattern = re.compile(r'\[tool_call:\s*(\w+)\(([^)]*)\)\]')
    for match in trained_pattern.finditer(text):
        name = match.group(1).strip()
        args_raw = match.group(2).strip()
        arguments = {}
        if args_raw:
            # Parse key="value" pairs (also handles key='value' and key=value)
            kv_pattern = re.compile(r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^,\s]+))')
            for kv in kv_pattern.finditer(args_raw):
                key = kv.group(1)
                val = kv.group(2) if kv.group(2) is not None else (kv.group(3) if kv.group(3) is not None else kv.group(4))
                arguments[key] = val
        calls.append({"name": name, "arguments": arguments})

    # ── Format 4: Gemma 4 — <|tool_call>call:func{key:<|"|>val<|"|>}<tool_call|> ──
    # Native Gemma 4 E2B tool-call format with special tokens.
    # The <|"|> tokens may be decoded as literal strings or as unicode markers.
    gemma_pattern = re.compile(
        r'<\|tool_call>call:(\w+)\{(.*?)\}<tool_call\|>', re.DOTALL
    )
    for match in gemma_pattern.finditer(text):
        name = match.group(1).strip()
        args_raw = match.group(2).strip()
        arguments = {}
        if args_raw:
            # Parse key:<|"|>value<|"|> or key:plain_value pairs
            # <|"|> is Gemma's special quote token
            kv_gemma = re.compile(r'(\w+):\s*(?:<\|"\|>(.*?)<\|"\|>|([^,}]*))')
            for kv in kv_gemma.finditer(args_raw):
                key = kv.group(1)
                val = kv.group(2) if kv.group(2) is not None else kv.group(3).strip()
                # Try to cast numeric/bool values
                if val.isdigit():
                    val = int(val)
                elif val.lower() in ('true', 'false'):
                    val = val.lower() == 'true'
                else:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                arguments[key] = val
        calls.append({"name": name, "arguments": arguments})

    return calls


def _robust_json_parse(args_str: str, tool_name: str) -> dict:
    """Robustly parse JSON arguments from LLM output.

    LLMs often produce broken JSON (unescaped quotes, trailing commas,
    truncated output). This function tries increasingly aggressive
    strategies to recover a valid dict.
    """
    import re

    # 1. Direct parse
    try:
        return json.loads(args_str)
    except json.JSONDecodeError:
        pass

    # 2. Extract outermost { ... } and try again
    brace_match = re.search(r'\{.*\}', args_str, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

        # 3. Fix common LLM JSON errors: trailing commas, single quotes
        fixed = brace_match.group()
        # Remove trailing commas before } or ]
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        # Replace single quotes with double quotes (careful with apostrophes)
        if '"' not in fixed:
            fixed = fixed.replace("'", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 4. Extract key-value pairs with regex
        extracted = _extract_kv_pairs(brace_match.group())
        if extracted:
            print(f"[Tools] ⚠️ Recovered args via regex extraction for {tool_name}: {list(extracted.keys())}")
            return extracted

    # 5. Last resort: try to find a "prompt" field in the raw text
    # (most common failure mode: LLM writes prose and forgets JSON)
    prompt_match = re.search(r'"prompt"\s*:\s*"((?:[^"\\]|\\.)*)"', args_str)
    title_match = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', args_str)
    if prompt_match:
        result = {"prompt": prompt_match.group(1)}
        if title_match:
            result["title"] = title_match.group(1)
        print(f"[Tools] ⚠️ Recovered prompt/title from broken JSON for {tool_name}")
        return result

    print(f"[Tools] ❌ Could not parse args for {tool_name}, raw: {args_str[:200]}")
    return {"_parse_error": True, "_raw": args_str[:500]}


def _extract_kv_pairs(json_str: str) -> dict:
    """Extract key-value pairs from semi-valid JSON using regex."""
    import re
    result = {}
    # Match "key": "value" (string values)
    for m in re.finditer(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', json_str):
        result[m.group(1)] = m.group(2)
    # Match "key": number
    for m in re.finditer(r'"(\w+)"\s*:\s*(\d+\.?\d*)\b', json_str):
        key = m.group(1)
        if key not in result:
            val = m.group(2)
            result[key] = float(val) if '.' in val else int(val)
    # Match "key": true/false
    for m in re.finditer(r'"(\w+)"\s*:\s*(true|false)\b', json_str):
        key = m.group(1)
        if key not in result:
            result[key] = m.group(2) == 'true'
    return result


def extract_text_before_tools(text: str) -> str:
    """Extract the text content before any tool call marker.
    
    Supports [TOOL_CALLS] (Mistral), <tool_call> (Qwen), [tool_call: (trained),
    and <|tool_call> (Gemma 4).
    """
    import re
    # Find earliest marker
    markers = []
    idx_m = text.find('[TOOL_CALLS]')
    if idx_m != -1:
        markers.append(idx_m)
    idx_q = text.find('<tool_call>')
    if idx_q != -1:
        markers.append(idx_q)
    # Trained format: [tool_call: func(...)]
    idx_t = text.find('[tool_call:')
    if idx_t != -1:
        markers.append(idx_t)
    # Gemma 4 format: <|tool_call>call:func{...}<tool_call|>
    idx_g = text.find('<|tool_call>')
    if idx_g != -1:
        markers.append(idx_g)
    if not markers:
        return text
    return text[:min(markers)].strip()


# ─── Project paths ───────────────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NOTES_DIR = os.path.join(_PROJECT_ROOT, "ailey_users", "notes")
_CALENDAR_DIR = os.path.join(_PROJECT_ROOT, "ailey_users", "calendar")


# ─── Tool: List Calendar Events ──────────────────────────────────────────────

@register_tool(
    name="list_calendar_events",
    description="Zeigt Kalendereinträge aus Apple Calendar an. Nutze dieses Tool wenn der User nach seinen Terminen fragt.",
    parameters={
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Anzahl der Tage in die Zukunft (Standard: 7)"
            },
            "calendar_name": {
                "type": "string",
                "description": "Name des Kalenders (optional, leer = alle Kalender)"
            }
        }
    }
)
def list_calendar_events(days_ahead: int = 7, calendar_name: str = "") -> dict:
    """List calendar events from Apple Calendar via AppleScript."""
    
    if calendar_name:
        calendar_filter = f'set allCalendars to {{calendar "{calendar_name}"}}'
    else:
        calendar_filter = 'set allCalendars to every calendar'
    
    script = f'''
tell application "Calendar"
    with timeout of 45 seconds
        set todayDate to current date
        set endDate to todayDate + ({days_ahead} * days)
        set output to ""
        
        {calendar_filter}
        repeat with cal in allCalendars
            set calName to name of cal
            try
                set calEvents to (every event of cal whose start date ≥ todayDate and start date ≤ endDate)
                repeat with ev in calEvents
                    set evSummary to summary of ev
                    set evStart to start date of ev
                    set evEnd to end date of ev
                    set evLoc to ""
                    try
                        set evLoc to location of ev
                    end try
                    
                    set output to output & "• " & evSummary & "\\n"
                    set output to output & "  📅 " & (evStart as string) & " - " & (evEnd as string) & "\\n"
                    if evLoc is not "" and evLoc is not missing value then
                        set output to output & "  📍 " & evLoc & "\\n"
                    end if
                    set output to output & "  Kalender: " & calName & "\\n\\n"
                end repeat
            on error errMsg
                -- Skip calendars that fail (e.g. subscriptions timing out)
                set output to output & "⚠️ Kalender '" & calName & "' konnte nicht gelesen werden\\n\\n"
            end try
        end repeat
        
        if output is "" then
            return "Keine Termine in den nächsten " & {days_ahead} & " Tagen gefunden."
        end if
        return output
    end timeout
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            events = result.stdout.strip()
            if not events or events.startswith("Keine Termine"):
                return {"message": f"Keine Termine in den nächsten {days_ahead} Tagen gefunden."}
            return {"message": f"Termine der nächsten {days_ahead} Tage:\n\n{events}"}
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout beim Abrufen der Kalendereinträge"}
    except Exception as e:
        return {"error": str(e)}


# ─── Tool: Calendar Event ────────────────────────────────────────────────────

@register_tool(
    name="create_calendar_event",
    description="Erstellt einen Kalendereintrag im Apple Calendar. Nutze dieses Tool wenn der User dich bittet, einen Termin, ein Event oder eine Verabredung einzutragen.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titel des Termins (z.B. 'Meeting mit Max', 'Zahnarzt')"
            },
            "date": {
                "type": "string",
                "description": "Datum im Format YYYY-MM-DD (z.B. '2026-02-15')"
            },
            "time": {
                "type": "string",
                "description": "Uhrzeit im Format HH:MM (z.B. '14:30'). Optional, Standard: 09:00"
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Dauer in Minuten. Standard: 60"
            },
            "location": {
                "type": "string",
                "description": "Ort des Termins (optional)"
            },
            "notes": {
                "type": "string",
                "description": "Zusätzliche Notizen (optional)"
            },
            "calendar_name": {
                "type": "string",
                "description": "Name des Kalenders (optional, Standard: erster verfügbarer Kalender)"
            }
        },
        "required": ["title", "date"]
    }
)
def create_calendar_event(
    title: str,
    date: str,
    time: str = "09:00",
    duration_minutes: int = 60,
    location: str = "",
    notes: str = "",
    calendar_name: str = ""
) -> dict:
    """Create a calendar event directly in Apple Calendar using AppleScript."""
    # Parse date and time
    try:
        dt_start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            dt_start = datetime.strptime(date, "%Y-%m-%d")
            dt_start = dt_start.replace(hour=9, minute=0)
        except ValueError:
            return {"error": f"Ungültiges Datum: {date}"}
    
    dt_end = dt_start + timedelta(minutes=duration_minutes)
    
    # Build AppleScript to create event
    # If no calendar specified, use first writable calendar
    if calendar_name:
        calendar_target = f'calendar "{calendar_name}"'
    else:
        calendar_target = 'first calendar whose writable is true'
    
    script = '''
tell application "Calendar"
    set targetCal to {calendar_target}
    tell targetCal
        set startDate to current date
        set year of startDate to {year_start}
        set month of startDate to {month_start}
        set day of startDate to {day_start}
        set hours of startDate to {hour_start}
        set minutes of startDate to {minute_start}
        set seconds of startDate to {second_start}
        
        set endDate to current date
        set year of endDate to {year_end}
        set month of endDate to {month_end}
        set day of endDate to {day_end}
        set hours of endDate to {hour_end}
        set minutes of endDate to {minute_end}
        set seconds of endDate to {second_end}
        
        set newEvent to make new event with properties {{summary:"{title}", start date:startDate, end date:endDate, location:"{location}", description:"{description}"}}
    end tell
end tell
'''.format(
        calendar_target=calendar_target,
        year_start=dt_start.year,
        month_start=dt_start.month,
        day_start=dt_start.day,
        hour_start=dt_start.hour,
        minute_start=dt_start.minute,
        second_start=dt_start.second,
        year_end=dt_end.year,
        month_end=dt_end.month,
        day_end=dt_end.day,
        hour_end=dt_end.hour,
        minute_end=dt_end.minute,
        second_end=dt_end.second,
        title=title.replace('"', '\\"'),
        location=location.replace('"', '\\"'),
        description=(notes or 'Erstellt von Ailey').replace('"', '\\"')
    )
    
    try:
        # Write AppleScript to a temporary file to avoid quoting issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as temp_file:
            temp_file.write(script)
            temp_file_path = temp_file.name
        
        result = subprocess.run(
            ["osascript", temp_file_path],
            capture_output=True, text=True, timeout=20
        )
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        if result.returncode == 0:
            # ── Also save to internal calendar ──
            try:
                import importlib
                api = importlib.import_module('ailey_api')
                api._add_internal_calendar_event(
                    title=title, date=date, time=time,
                    duration_minutes=duration_minutes,
                    location=location, notes=notes,
                    category="event", source="tool",
                )
            except Exception:
                pass  # Don't fail if internal calendar save fails

            return {
                "message": f"Kalendereintrag '{title}' erstellt für {dt_start.strftime('%d.%m.%Y um %H:%M')}",
                "event": {
                    "title": title,
                    "start": dt_start.isoformat(),
                    "end": dt_end.isoformat(),
                    "location": location,
                    "duration_minutes": duration_minutes,
                }
            }
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout beim Erstellen des Termins"}
    except Exception as e:
        return {"error": str(e)}


# ─── Tool: Reminder ──────────────────────────────────────────────────────────

@register_tool(
    name="create_reminder",
    description="Erstellt eine Erinnerung in Apple Reminders. Nutze dieses Tool wenn der User dich bittet, ihn an etwas zu erinnern.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Text der Erinnerung (z.B. 'Milch kaufen', 'Simon anrufen')"
            },
            "date": {
                "type": "string",
                "description": "Datum im Format YYYY-MM-DD (optional, für zeitbasierte Erinnerung)"
            },
            "time": {
                "type": "string",
                "description": "Uhrzeit im Format HH:MM (optional, z.B. '15:00')"
            }
        },
        "required": ["title"]
    }
)
def create_reminder(title: str, date: str = "", time: str = "") -> dict:
    """Create a reminder via AppleScript in Apple Reminders."""
    # Sanitize title for AppleScript
    safe_title = title.replace('"', '\\"').replace("\\", "\\\\")
    
    # Build AppleScript
    reminder_date = ""
    if date:
        try:
            dt = datetime.strptime(f"{date} {time or '09:00'}", "%Y-%m-%d %H:%M")
            # AppleScript date format
            reminder_date = dt.strftime("%B %d, %Y at %I:%M:%S %p")
        except ValueError:
            pass
    
    if reminder_date:
        # Use numeric date components to avoid locale parsing issues in AppleScript
        year = dt.year
        month = dt.month
        day = dt.day
        hour = dt.hour
        minute = dt.minute
        second = dt.second

        # AppleScript expects month identifiers like January, February (not integers)
        _month_names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
        month_name = _month_names[month-1]

        script = f'''
tell application "Reminders"
    set startDate to current date
    set year of startDate to {year}
    set month of startDate to {month_name}
    set day of startDate to {day}
    set hours of startDate to {hour}
    set minutes of startDate to {minute}
    set seconds of startDate to {second}

    set newReminder to make new reminder in list "Erinnerungen" with properties {{name:"{safe_title}", due date:startDate}}
end tell
'''
    else:
        script = f'''
tell application "Reminders"
    set newReminder to make new reminder in list "Erinnerungen" with properties {{name:"{safe_title}"}}
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            msg = f"Erinnerung '{title}' erstellt"
            if reminder_date:
                msg += f" für {reminder_date}"
            return {"message": msg}
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout beim Erstellen der Erinnerung"}
    except Exception as e:
        return {"error": str(e)}


# ─── Tool: Note ───────────────────────────────────────────────────────────────

@register_tool(
    name="create_note",
    description="Speichert eine Notiz für den User. Nutze dieses Tool wenn der User dich bittet, sich etwas zu merken oder eine Notiz zu machen.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titel der Notiz"
            },
            "content": {
                "type": "string",
                "description": "Inhalt der Notiz"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optionale Tags (z.B. ['idee', 'projekt'])"
            }
        },
        "required": ["title", "content"]
    }
)
def create_note(title: str, content: str, tags: list = None) -> dict:
    """Save a note as a markdown file."""
    os.makedirs(_NOTES_DIR, exist_ok=True)
    
    timestamp = datetime.now()
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:60]
    filename = f"{timestamp.strftime('%Y%m%d_%H%M')}_{safe_title}.md"
    filepath = os.path.join(_NOTES_DIR, filename)
    
    tag_line = ""
    if tags:
        tag_line = f"\ntags: {', '.join(tags)}\n"
    
    md_content = f"""# {title}

*Erstellt: {timestamp.strftime('%d.%m.%Y %H:%M')} — von Ailey*
{tag_line}
---

{content}
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    return {
        "message": f"Notiz '{title}' gespeichert",
        "file": filepath,
        "chars": len(content),
    }


# ─── Tool: Current Time ──────────────────────────────────────────────────────

@register_tool(
    name="get_current_time",
    description="Gibt das aktuelle Datum und die Uhrzeit zurück. Nutze dieses Tool wenn der User nach dem aktuellen Datum oder der Uhrzeit fragt.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_current_time() -> dict:
    """Return current date/time information."""
    now = datetime.now()
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return {
        "message": f"Es ist {weekdays[now.weekday()]}, der {now.strftime('%d.%m.%Y')}, {now.strftime('%H:%M')} Uhr.",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekdays[now.weekday()],
        "timestamp": now.isoformat(),
    }


# ─── Tool: SVG Generation (simple fallback generator) ───────────────────────

@register_tool(
    name="generate_svg",
    description="Erstellt eine simple SVG-Grafik basierend auf einer textuellen Beschreibung (Fallback, lokal).",
    parameters={
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "style": {"type": "string"},
            "colors": {"type": "string"},
            "size": {"type": "string"}
        },
        "required": ["description"]
    }
)
def generate_svg(description: str, style: str = "minimalistisch", colors: str = "automatisch", size: str = "256x256") -> dict:
    """Generate a simple SVG and save it to the svg_gallery directory.

    This is a deterministic, local fallback generator that does not call an LLM.
    It ensures the backend feature is available without additional runtime deps.
    """
    try:
        try:
            w, h = map(int, (size or "256x256").lower().split('x'))
        except Exception:
            w, h = 256, 256

        # sanitize description for small text
        safe_desc = ''.join(c for c in description if c.isalnum() or c.isspace() or c in '.,-_:')[:200]

        # choose colors
        if colors and colors != 'automatisch':
            fill = colors.split()[0]
        else:
            fill = '#6b21a8' if 'violet' in style or 'minimal' in style else '#0ea5a4'

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white" />
  <g transform="translate({w//2},{h//2})">
    <circle r="{min(w,h)//4}" fill="{fill}" opacity="0.12" />
    <text x="0" y="0" font-size="14" text-anchor="middle" dominant-baseline="middle" fill="#111">{safe_desc}</text>
  </g>
</svg>'''

        svg_dir = os.path.join(_PROJECT_ROOT, 'ailey_users', 'svg_gallery')
        os.makedirs(svg_dir, exist_ok=True)
        filename = f"svg_{int(time.time())}_{abs(hash(description))%10000}.svg"
        filepath = os.path.join(svg_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(svg)

        return {"message": f"SVG erstellt: {filename}", "filename": filename, "filepath": filepath, "svg": svg}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="list_svg_gallery",
    description="Listet erstellte SVG-Dateien in der Galerie auf.",
    parameters={"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}
)
def list_svg_gallery(limit: int = 20) -> dict:
    svg_dir = os.path.join(_PROJECT_ROOT, 'ailey_users', 'svg_gallery')
    if not os.path.exists(svg_dir):
        return {"message": "Galerie leer", "svgs": []}
    files = sorted([f for f in os.listdir(svg_dir) if f.endswith('.svg')], key=lambda x: os.path.getmtime(os.path.join(svg_dir, x)), reverse=True)[:limit]
    out = []
    for fn in files:
        p = os.path.join(svg_dir, fn)
        out.append({"filename": fn, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
    return {"message": f"{len(out)} SVG(s)", "svgs": out}


# ─── Tool: ER-Diagramm Generator ────────────────────────────────────────────

@register_tool(
    name="generate_er_diagram",
    description=(
        "Erstellt ein professionelles ER-Diagramm (Entity-Relationship) als SVG. "
        "Du lieferst die Entitäten mit Attributen und die Beziehungen als JSON, "
        "das Tool baut daraus ein korrektes, speicherbares SVG mit Chen-Notation "
        "(Rechtecke=Entitäten, Ellipsen=Attribute, Diamanten=Beziehungen, "
        "unterstrichene PKs, Crow's-Foot-Kardinalitäten). "
        "Das SVG wird NICHT in der Galerie gespeichert, sondern direkt als "
        "```svg Code-Block in deiner Antwort ausgegeben — der User kann es "
        "dann runterladen. Nutze dieses Tool IMMER wenn jemand nach einem "
        "ER-Diagramm fragt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titel des Diagramms (z.B. 'Online-Shop Datenbank')"
            },
            "entities": {
                "type": "array",
                "description": (
                    "Liste der Entitäten. Jede Entität hat 'name' und 'attributes'. "
                    "Attribute haben 'name' und optional 'pk':true für Primary Key, "
                    "'fk':true für Foreign Key."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "attributes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "pk": {"type": "boolean"},
                                    "fk": {"type": "boolean"}
                                },
                                "required": ["name"]
                            }
                        }
                    },
                    "required": ["name", "attributes"]
                }
            },
            "relationships": {
                "type": "array",
                "description": (
                    "Liste der Beziehungen. Jede hat 'from', 'to', 'label' (Verb), "
                    "'cardinality' ('1:1', '1:n', 'n:m')."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "description": "Name der Start-Entität"},
                        "to": {"type": "string", "description": "Name der Ziel-Entität"},
                        "label": {"type": "string", "description": "Beziehungs-Verb (z.B. 'hat', 'gehört zu')"},
                        "cardinality": {
                            "type": "string",
                            "description": "Kardinalität: '1:1', '1:n', 'n:m'",
                            "enum": ["1:1", "1:n", "n:m"]
                        }
                    },
                    "required": ["from", "to", "label", "cardinality"]
                }
            }
        },
        "required": ["title", "entities", "relationships"]
    }
)
def generate_er_diagram(title: str, entities: list, relationships: list) -> dict:
    """Build a professional ER diagram as SVG from structured JSON data.

    Returns the SVG string directly (NOT saved to gallery).
    The caller (Ailey) embeds it as ```svg code block in her reply.
    """
    import math
    import html as html_mod

    try:
        # ── Layout constants ────────────────────────────────────
        ENTITY_W = 180          # entity box width
        ENTITY_HEADER_H = 32    # header row height
        ATTR_ROW_H = 22         # per-attribute row height
        ENTITY_PAD_BOTTOM = 6   # padding below last attr
        COL_GAP = 280           # horizontal gap between entities
        ROW_GAP = 100           # extra vertical gap between entity rows
        DIAMOND_W = 140         # relationship diamond width
        DIAMOND_H = 50          # relationship diamond height
        MARGIN_X = 60
        MARGIN_Y = 80
        COLS = max(1, min(4, int(math.ceil(math.sqrt(len(entities))))))

        # ── Colors (professional, dark-on-white) ────────────────
        C_BG = "#ffffff"
        C_ENTITY_FILL = "#e8f0fe"       # light blue
        C_ENTITY_STROKE = "#1a73e8"     # Google blue
        C_ENTITY_HEADER = "#1a73e8"     # header bg
        C_ENTITY_HEADER_TEXT = "#ffffff"
        C_ATTR_TEXT = "#1f1f1f"
        C_PK_TEXT = "#1a73e8"           # primary key color
        C_FK_TEXT = "#e65100"           # foreign key color
        C_DIAMOND_FILL = "#fff3e0"      # light orange
        C_DIAMOND_STROKE = "#e65100"
        C_DIAMOND_TEXT = "#bf360c"
        C_LINE = "#5f6368"
        C_CARD_TEXT = "#1a73e8"
        C_TITLE = "#1f1f1f"

        esc = html_mod.escape

        # ── Calculate entity positions (grid layout) ────────────
        entity_map = {}  # name → {x, y, w, h, cx, cy}
        for i, ent in enumerate(entities):
            col = i % COLS
            row = i // COLS
            attrs = ent.get("attributes", [])
            h = ENTITY_HEADER_H + len(attrs) * ATTR_ROW_H + ENTITY_PAD_BOTTOM
            x = MARGIN_X + col * COL_GAP
            y = MARGIN_Y + row * (200 + ROW_GAP)  # rough row height
            entity_map[ent["name"]] = {
                "x": x, "y": y, "w": ENTITY_W, "h": h,
                "cx": x + ENTITY_W // 2,
                "cy": y + h // 2,
                "attrs": attrs,
            }

        # ── Recalculate row heights (use actual max per row) ────
        row_heights = {}
        for i, ent in enumerate(entities):
            row = i // COLS
            h = entity_map[ent["name"]]["h"]
            row_heights[row] = max(row_heights.get(row, 0), h)

        # Re-position with real row heights
        cum_y = MARGIN_Y
        for i, ent in enumerate(entities):
            col = i % COLS
            row = i // COLS
            if col == 0 and row > 0:
                cum_y += row_heights.get(row - 1, 200) + ROW_GAP
            elif col == 0 and row == 0:
                pass
            x = MARGIN_X + col * COL_GAP
            y = cum_y
            em = entity_map[ent["name"]]
            em["x"] = x
            em["y"] = y
            em["cx"] = x + ENTITY_W // 2
            em["cy"] = y + em["h"] // 2

        # ── Calculate total canvas size ─────────────────────────
        max_x = max(em["x"] + em["w"] for em in entity_map.values()) + MARGIN_X
        num_rows = (len(entities) + COLS - 1) // COLS
        last_row = num_rows - 1
        max_y = cum_y + row_heights.get(last_row, 200) + MARGIN_Y + 40
        canvas_w = max(max_x, 600)
        canvas_h = max(max_y, 400)

        # ── Start SVG ───────────────────────────────────────────
        svg_parts = []
        svg_parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{canvas_w}" height="{canvas_h}" '
            f'viewBox="0 0 {canvas_w} {canvas_h}" '
            f'style="font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        )

        # Background
        svg_parts.append(f'<rect width="100%" height="100%" fill="{C_BG}"/>')

        # Title
        svg_parts.append(
            f'<text x="{canvas_w//2}" y="35" font-size="18" font-weight="bold" '
            f'text-anchor="middle" fill="{C_TITLE}">{esc(title)}</text>'
        )
        # Subtle subtitle
        svg_parts.append(
            f'<text x="{canvas_w//2}" y="55" font-size="11" '
            f'text-anchor="middle" fill="#9e9e9e">ER-Diagramm • Chen-Notation</text>'
        )

        # ── Draw relationship lines + diamonds ──────────────────
        for rel in relationships:
            fr = rel.get("from", "")
            to = rel.get("to", "")
            label = rel.get("label", "")
            card = rel.get("cardinality", "1:n")

            if fr not in entity_map or to not in entity_map:
                continue

            e1 = entity_map[fr]
            e2 = entity_map[to]

            # Connection points: nearest edges
            x1, y1 = _er_edge_point(e1, e2)
            x2, y2 = _er_edge_point(e2, e1)

            # Diamond midpoint
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2

            # Line from entity1 → diamond
            svg_parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{mx}" y2="{my}" '
                f'stroke="{C_LINE}" stroke-width="1.5"/>'
            )
            # Line from diamond → entity2
            svg_parts.append(
                f'<line x1="{mx}" y1="{my}" x2="{x2}" y2="{y2}" '
                f'stroke="{C_LINE}" stroke-width="1.5"/>'
            )

            # Diamond shape
            dw = DIAMOND_W // 2
            dh = DIAMOND_H // 2
            svg_parts.append(
                f'<polygon points="{mx},{my-dh} {mx+dw},{my} {mx},{my+dh} {mx-dw},{my}" '
                f'fill="{C_DIAMOND_FILL}" stroke="{C_DIAMOND_STROKE}" stroke-width="1.5"/>'
            )
            # Diamond label
            svg_parts.append(
                f'<text x="{mx}" y="{my+4}" font-size="11" font-weight="600" '
                f'text-anchor="middle" fill="{C_DIAMOND_TEXT}">{esc(label)}</text>'
            )

            # Cardinality labels near entities
            card_from, card_to = card.split(":")
            # Near entity 1
            cx1 = x1 + (mx - x1) * 0.15
            cy1 = y1 + (my - y1) * 0.15 - 8
            svg_parts.append(
                f'<text x="{cx1}" y="{cy1}" font-size="12" font-weight="bold" '
                f'text-anchor="middle" fill="{C_CARD_TEXT}">{esc(card_from)}</text>'
            )
            # Near entity 2
            cx2 = x2 + (mx - x2) * 0.15
            cy2 = y2 + (my - y2) * 0.15 - 8
            svg_parts.append(
                f'<text x="{cx2}" y="{cy2}" font-size="12" font-weight="bold" '
                f'text-anchor="middle" fill="{C_CARD_TEXT}">{esc(card_to)}</text>'
            )

            # Crow's foot for 'n' side
            if card_to in ("n", "m"):
                _er_crows_foot(svg_parts, x2, y2, mx, my, C_LINE)
            if card_from in ("n", "m"):
                _er_crows_foot(svg_parts, x1, y1, mx, my, C_LINE)

        # ── Draw entities ───────────────────────────────────────
        for ent_name, em in entity_map.items():
            x, y, w, h = em["x"], em["y"], em["w"], em["h"]
            attrs = em["attrs"]

            # Shadow
            svg_parts.append(
                f'<rect x="{x+2}" y="{y+2}" width="{w}" height="{h}" '
                f'rx="6" fill="#00000010"/>'
            )
            # Entity box
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'rx="6" fill="{C_ENTITY_FILL}" stroke="{C_ENTITY_STROKE}" stroke-width="1.5"/>'
            )
            # Header
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{ENTITY_HEADER_H}" '
                f'rx="6" fill="{C_ENTITY_HEADER}"/>'
            )
            # Header bottom corners (square, covered by body)
            svg_parts.append(
                f'<rect x="{x}" y="{y+ENTITY_HEADER_H-6}" width="{w}" height="6" '
                f'fill="{C_ENTITY_HEADER}"/>'
            )
            # Entity name
            svg_parts.append(
                f'<text x="{x+w//2}" y="{y+21}" font-size="13" font-weight="bold" '
                f'text-anchor="middle" fill="{C_ENTITY_HEADER_TEXT}">{esc(ent_name)}</text>'
            )

            # Attributes
            for j, attr in enumerate(attrs):
                ay = y + ENTITY_HEADER_H + j * ATTR_ROW_H + 16
                a_name = attr.get("name", "")
                is_pk = attr.get("pk", False)
                is_fk = attr.get("fk", False)

                # PK icon + underline
                prefix = ""
                color = C_ATTR_TEXT
                decoration = ""
                if is_pk:
                    prefix = "PK "
                    color = C_PK_TEXT
                    decoration = ' text-decoration="underline" font-weight="600"'
                elif is_fk:
                    prefix = "FK "
                    color = C_FK_TEXT

                svg_parts.append(
                    f'<text x="{x+12}" y="{ay}" font-size="11" '
                    f'fill="{color}"{decoration}>{esc(prefix + a_name)}</text>'
                )

            # Separator line below header
            svg_parts.append(
                f'<line x1="{x}" y1="{y+ENTITY_HEADER_H}" x2="{x+w}" y2="{y+ENTITY_HEADER_H}" '
                f'stroke="{C_ENTITY_STROKE}" stroke-width="0.5"/>'
            )

        # ── Legend ──────────────────────────────────────────────
        ly = canvas_h - 30
        svg_parts.append(
            f'<text x="{MARGIN_X}" y="{ly}" font-size="9" fill="#9e9e9e">'
            f'PK = Primary Key  •  FK = Foreign Key  •  ◇ = Beziehung  •  '
            f'Crow\'s Foot = n/m-Seite</text>'
        )

        svg_parts.append('</svg>')
        svg_str = "\n".join(svg_parts)

        return {
            "message": f"ER-Diagramm '{title}' erstellt ({len(entities)} Entitäten, {len(relationships)} Beziehungen). Bette das SVG als ```svg Code-Block in deine Antwort ein!",
            "svg": svg_str,
            "embed_as_code_block": True,
        }

    except Exception as e:
        return {"error": f"ER-Diagramm Fehler: {str(e)}"}


def _er_edge_point(source: dict, target: dict) -> tuple:
    """Calculate the nearest edge point on source entity box facing target."""
    import math
    sx, sy = source["cx"], source["cy"]
    tx, ty = target["cx"], target["cy"]
    dx = tx - sx
    dy = ty - sy
    if dx == 0 and dy == 0:
        return (sx, sy)

    # Check which edge to use
    hw = source["w"] / 2
    hh = source["h"] / 2

    if abs(dx) * hh > abs(dy) * hw:
        # Hit left or right edge
        if dx > 0:
            return (source["x"] + source["w"], sy + dy * hw / abs(dx))
        else:
            return (source["x"], sy - dy * hw / abs(dx))
    else:
        # Hit top or bottom edge
        if dy > 0:
            return (sx + dx * hh / abs(dy), source["y"] + source["h"])
        else:
            return (sx - dx * hh / abs(dy), source["y"])


def _er_crows_foot(parts: list, ex: float, ey: float, mx: float, my: float, color: str):
    """Draw a crow's foot (three-pronged fork) near entity edge point."""
    import math
    dx = ex - mx
    dy = ey - my
    length = math.sqrt(dx*dx + dy*dy) or 1
    # Normalize
    nx = dx / length
    ny = dy / length
    # Perpendicular
    px = -ny
    py = nx
    # Fork base (15px from entity edge toward diamond)
    bx = ex - nx * 18
    by = ey - ny * 18
    spread = 10
    # Three prongs from fork base to entity edge
    parts.append(
        f'<line x1="{bx + px*spread}" y1="{by + py*spread}" '
        f'x2="{ex}" y2="{ey}" stroke="{color}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{bx}" y1="{by}" '
        f'x2="{ex}" y2="{ey}" stroke="{color}" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{bx - px*spread}" y1="{by - py*spread}" '
        f'x2="{ex}" y2="{ey}" stroke="{color}" stroke-width="1.5"/>'
    )


# ─── Tool: Timer ─────────────────────────────────────────────────────────────

@register_tool(
    name="set_timer",
    description="Setzt einen Timer/Wecker über macOS. Nutze dieses Tool wenn der User einen Timer oder Wecker stellen möchte.",
    parameters={
        "type": "object",
        "properties": {
            "minutes": {
                "type": "integer",
                "description": "Timer-Dauer in Minuten"
            },
            "label": {
                "type": "string",
                "description": "Beschriftung des Timers (optional)"
            }
        },
        "required": ["minutes"]
    }
)
def set_timer(minutes: int, label: str = "Ailey Timer") -> dict:
    """Set a timer using macOS notification."""
    seconds = minutes * 60
    # Use osascript to schedule a delayed notification
    script = f'''
do shell script "sleep {seconds} && osascript -e 'display notification \\"{label} – {minutes} Minuten sind um!\\" with title \\"⏰ Ailey Timer\\" sound name \\"Glass\\"' &"
'''
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {
            "message": f"Timer auf {minutes} Minuten gestellt: {label}",
            "minutes": minutes,
            "label": label,
            "fires_at": (datetime.now() + timedelta(minutes=minutes)).strftime("%H:%M"),
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Tool: Update User Profile ───────────────────────────────────────────────

@register_tool(
    name="update_user_profile",
    description=(
        "Aktualisiert ein persönliches Faktum über den User (z.B. Wohnort, Arbeitsort, Arbeitgeber). "
        "Nutze dieses Tool NUR wenn der User dir EXPLIZIT eine neue persönliche Info mitteilt, "
        "z.B. 'Ich bin umgezogen nach Hamburg' oder 'Ich arbeite jetzt bei XY'. "
        "Erlaubte Felder: wohnort, arbeitsort, arbeitgeber, zeitzone, sprache, anrede, name, full_name. "
        "Für beliebige andere Fakten nutze das Präfix 'custom.' (z.B. 'custom.lieblingsfarbe')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "description": (
                    "Das zu aktualisierende Feld. Eines von: "
                    "wohnort, arbeitsort, arbeitgeber, zeitzone, sprache, anrede, name, full_name, "
                    "oder custom.<key> für beliebige Fakten."
                ),
            },
            "value": {
                "type": "string",
                "description": "Der neue Wert für das Feld.",
            },
        },
        "required": ["field", "value"],
    },
)
def update_user_profile(field: str, value: str) -> dict:
    """Update a field in the active user profile."""
    from .user_profile import update_field

    # Default user for now (single-user mode)
    user = "Simon"
    try:
        result = update_field(field, value, user=user)
        return {
            "message": f"Profil aktualisiert: {field} → {value}",
            "field": field,
            "value": value,
            "old_value": result.get("old_value"),
        }
    except ValueError as e:
        return {
            "error": str(e),
        }


# ─── Tool: Update Relationship ───────────────────────────────────────────────

@register_tool(
    name="update_relationship",
    description=(
        "Aktualisiert die Beziehung zwischen Simon und Ailey. "
        "Nutze dieses Tool wenn sich die Beziehung verändert oder du deine Perspektive festhalten willst. "
        "Du kannst: das Beziehungslevel ändern, Tags hinzufügen/entfernen, "
        "oder deine eigene Sicht auf die Beziehung festhalten (ailey_perspective). "
        "Level-Optionen: bekannte/r, freund/in, gute/r freund/in, bester freund/in, partner/in, seelenverwandte/r. "
        "Tag-Beispiele: freunde, vertraut, romantisch, spielkameraden, kreativpartner."
    ),
    parameters={
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "description": "Neues Beziehungslevel (optional).",
            },
            "add_tag": {
                "type": "string",
                "description": "Ein Tag hinzufügen (z.B. 'vertraut', 'kreativpartner').",
            },
            "remove_tag": {
                "type": "string",
                "description": "Ein Tag entfernen.",
            },
            "ailey_perspective": {
                "type": "string",
                "description": "Aileys eigene Sicht auf die Beziehung (max 200 Zeichen).",
            },
            "add_note": {
                "type": "string",
                "description": "Eine Notiz zur Beziehungsentwicklung hinzufügen.",
            },
        },
        "required": [],
    },
)
def update_relationship(
    level: str = None, add_tag: str = None, remove_tag: str = None,
    ailey_perspective: str = None, add_note: str = None,
) -> dict:
    """Update the owner–Ailey relationship from Ailey's side."""
    from .user_profile import update_relationship as _update_rel
    try:
        result = _update_rel(
            user="Simon",
            level=level,
            add_tag=add_tag,
            remove_tag=remove_tag,
            ailey_perspective=ailey_perspective[:200] if ailey_perspective else None,
            add_note=add_note[:300] if add_note else None,
            updated_by="ailey",
        )
        return {"message": "Beziehung aktualisiert", **result}
    except Exception as e:
        return {"error": str(e)}


# ─── Extended Reminder Tools ─────────────────────────────────────────────────

@register_tool(
    name="list_reminders",
    description="Listet alle aktiven Erinnerungen aus Apple Reminders auf.",
    parameters={
        "type": "object",
        "properties": {
            "list_name": {
                "type": "string",
                "description": "Name der Liste (optional, default: 'Erinnerungen')",
                "default": "Erinnerungen"
            },
            "include_completed": {
                "type": "boolean",
                "description": "Auch abgeschlossene Erinnerungen einbeziehen",
                "default": False
            }
        }
    }
)
def list_reminders(list_name: str = "Erinnerungen", include_completed: bool = False) -> dict:
    """List reminders from Apple Reminders via AppleScript."""
    completed_filter = "" if include_completed else "whose completed is false"
    
    script = f'''
tell application "Reminders"
    set reminderList to list "{list_name}"
    set allReminders to reminders in reminderList {completed_filter}
    set output to ""
    repeat with r in allReminders
        set reminderName to name of r
        set isCompleted to completed of r
        set bodyText to body of r
        
        set output to output & "• " & reminderName
        try
            set dueDate to due date of r
            if dueDate is not missing value then
                set output to output & " (Fällig: " & (dueDate as string) & ")"
            end if
        end try
        if isCompleted then
            set output to output & " ✓"
        end if
        if bodyText is not missing value and bodyText is not "" then
            set output to output & "\\n  " & bodyText
        end if
        set output to output & "\\n"
    end repeat
    return output
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            reminders = result.stdout.strip()
            if not reminders:
                return {"message": f"Keine Erinnerungen in Liste '{list_name}' gefunden."}
            return {"message": f"Erinnerungen in '{list_name}':\\n{reminders}"}
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="complete_reminder",
    description="Markiert eine Erinnerung als erledigt in Apple Reminders.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titel der Erinnerung die abgeschlossen werden soll"
            },
            "list_name": {
                "type": "string",
                "description": "Name der Liste (optional, default: 'Erinnerungen')",
                "default": "Erinnerungen"
            }
        },
        "required": ["title"]
    }
)
def complete_reminder(title: str, list_name: str = "Erinnerungen") -> dict:
    """Mark a reminder as completed in Apple Reminders."""
    script = f'''
tell application "Reminders"
    set reminderList to list "{list_name}"
    set targetReminders to reminders in reminderList whose name contains "{title}"
    if (count of targetReminders) > 0 then
        set targetReminder to first item of targetReminders
        set completed of targetReminder to true
        return "Erinnerung '" & name of targetReminder & "' als erledigt markiert."
    else
        return "Erinnerung '" & "{title}" & "' nicht gefunden."
    end if
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {"message": result.stdout.strip() or f"Erinnerung '{title}' abgeschlossen."}
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="create_recurring_reminder",
    description="Erstellt eine wiederkehrende Erinnerung in Apple Reminders.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Text der Erinnerung"
            },
            "recurrence": {
                "type": "string",
                "description": "Wiederholung: 'daily', 'weekly', 'monthly', 'yearly'",
                "enum": ["daily", "weekly", "monthly", "yearly"]
            },
            "start_date": {
                "type": "string",
                "description": "Startdatum im Format YYYY-MM-DD (optional)"
            },
            "start_time": {
                "type": "string",
                "description": "Startzeit im Format HH:MM (optional)"
            }
        },
        "required": ["title", "recurrence"]
    }
)
def create_recurring_reminder(title: str, recurrence: str, start_date: str = "", start_time: str = "") -> dict:
    """Create a recurring reminder in Apple Reminders.
    
    Note: Apple Reminders does not support setting recurrence via AppleScript directly.
    We create the reminder and inform the user to set recurrence manually, or use a workaround.
    """
    if recurrence not in ["daily", "weekly", "monthly", "yearly"]:
        return {"error": f"Ungültige Wiederholung: {recurrence}"}
    
    # Build the base reminder with due date
    reminder_date_script = ""
    date_msg = ""
    if start_date:
        try:
            dt = datetime.strptime(f"{start_date} {start_time or '09:00'}", "%Y-%m-%d %H:%M")
            year = dt.year
            month = dt.month
            day = dt.day
            hour = dt.hour
            minute = dt.minute
            
            _month_names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
            month_name = _month_names[month-1]
            
            reminder_date_script = f'''
        set reminderDate to current date
        set year of reminderDate to {year}
        set month of reminderDate to {month_name}
        set day of reminderDate to {day}
        set hours of reminderDate to {hour}
        set minutes of reminderDate to {minute}
        set seconds of reminderDate to 0
        set due date of newReminder to reminderDate
'''
            date_msg = f" ab {dt.strftime('%d.%m.%Y %H:%M')}"
        except ValueError:
            return {"error": "Ungültiges Datum/Zeit Format"}
    
    # Recurrence German translation for user message
    recurrence_de = {"daily": "täglich", "weekly": "wöchentlich", "monthly": "monatlich", "yearly": "jährlich"}
    
    # AppleScript to create the reminder (without recurrence - not supported via AppleScript)
    script = f'''
tell application "Reminders"
    set newReminder to make new reminder in list "Erinnerungen" with properties {{name:"{title} ({recurrence_de[recurrence]})"}}
    {reminder_date_script}
    return "OK"
end tell
'''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            msg = f"Erinnerung '{title}' erstellt ({recurrence_de[recurrence]}){date_msg}. Hinweis: Bitte Wiederholung manuell in der Reminders-App einstellen, da AppleScript dies nicht unterstützt."
            return {"message": msg}
        else:
            return {"error": f"AppleScript Fehler: {result.stderr.strip()}"}
    except Exception as e:
        return {"error": str(e)}


# ─── TTS/STT Tools (Apple-native) ───────────────────────────────────────────

@register_tool(
    name="speak_text",
    description="Spricht einen Text mit Apple Sprachausgabe (TTS).",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text, der gesprochen werden soll"
            },
            "voice": {
                "type": "string",
                "description": "Stimme (optional, z.B. 'Anna', 'Yannick', 'Ailey')",
                "default": "Anna"
            },
            "rate": {
                "type": "number",
                "description": "Sprechgeschwindigkeit (optional, default: 200)",
                "default": 200
            }
        },
        "required": ["text"]
    }
)
def speak_text(text: str, voice: str = "Anna", rate: int = 200, output_file: str = "") -> dict:
    """Speak text using Apple TTS (say command).
    
    If output_file is given, writes AIFF audio to that path instead of playing.
    Splits long texts into sentences to avoid truncation.
    """
    try:
        import re as _re
        # Clean markdown artifacts
        clean = text.replace("**", "").replace("*", "").replace("#", "").replace("`", "").replace("_", " ").strip()
        # Remove mood tags
        clean = _re.sub(r'\[mood:[^\]]+\]', '', clean).strip()
        if not clean:
            return {"message": "Nichts zu sprechen"}
        
        if output_file:
            # Generate audio file (AIFF) — no timeout needed
            cmd = ["say", "-v", voice, "-r", str(rate), "-o", output_file, clean]
            run_subprocess(cmd, timeout=120)
            return {"message": "Audio generiert", "file": output_file}
        else:
            # Split into sentences for reliable playback (no timeout issues)
            sentences = _re.split(r'(?<=[.!?;:])\s+', clean)
            for sentence in sentences:
                s = sentence.strip()
                if not s:
                    continue
                cmd = ["say", "-v", voice, "-r", str(rate), s]
                # Allow up to 30s per sentence (generous for long sentences)
                run_subprocess(cmd, timeout=30)
            return {"message": f"Text gesprochen mit Stimme '{voice}' ({len(sentences)} Sätze)"}
    except Exception as e:
        return {"error": f"TTS fehlgeschlagen: {str(e)}"}


@register_tool(
    name="recognize_speech",
    description="Spracherkennung (STT) via Apple-native APIs. Nimmt Audio auf und transkribiert.",
    parameters={
        "type": "object",
        "properties": {
            "duration": {
                "type": "integer",
                "description": "Aufnahmedauer in Sekunden (default: 5)",
                "default": 5
            },
            "language": {
                "type": "string",
                "description": "Sprache (z.B. 'de-DE', 'en-US')",
                "default": "de-DE"
            }
        }
    }
)
def recognize_speech(duration: int = 5, language: str = "de-DE") -> dict:
    """Recognize speech using Apple-native APIs (stub, demo only)."""
    try:
        # Demo: Use AppleScript to record audio and transcribe (stub)
        # Real implementation would use macOS Speech framework
        script = f'''
tell application "QuickTime Player"
    set newRecording to (new audio recording)
    start newRecording
    delay {duration}
    stop newRecording
    set audioFile to (newRecording as alias)
end tell
'''
        subprocess.run(["osascript", "-e", script], timeout=duration+5)
        # Stub: Return demo transcript
        transcript = "(Demo) Spracherkennung nicht implementiert."
        return {"transcript": transcript, "language": language}
    except Exception as e:
        return {"error": f"STT fehlgeschlagen: {str(e)}"}


# ─── Tool: Send Proactive Email ──────────────────────────────────────────────

@register_tool(
    name="send_proactive_email",
    description=(
        "Sendet eine E-Mail von Aileys eigenem E-Mail-Konto (proaktiv). "
        "Nutze dieses Tool wenn du selbstständig eine E-Mail an jemanden schicken willst, "
        "z.B. als Nachricht an Simon oder an einen freigegebenen Kontakt. "
        "WICHTIG: Nur an freigegebene Kontakte oder Simons Adressen erlaubt. "
        "Tageslimit: 1 autonome Mail pro Kontakt pro Tag (an Simon unbegrenzt)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Empfänger-E-Mail-Adresse"
            },
            "subject": {
                "type": "string",
                "description": "Betreff der E-Mail"
            },
            "body": {
                "type": "string",
                "description": "Text der E-Mail (wird mit Aileys Signatur versehen)"
            },
        },
        "required": ["to", "subject", "body"],
    },
)
def send_proactive_email(to: str, subject: str, body: str) -> dict:
    """Send a proactive email from Ailey's own account via the API."""
    try:
        import importlib
        api_mod = importlib.import_module('ailey_api')
        em = api_mod.email_monitor
        if em is None:
            return {"error": "EmailMonitor nicht gestartet (start_services() noch nicht aufgerufen)"}
        result = em.send_proactive_email_as_ailey(to, subject, body)
        if result.get("success"):
            return {"message": result.get("message", f"E-Mail an {to} gesendet")}
        else:
            return {"error": result.get("error", "Senden fehlgeschlagen")}
    except Exception as e:
        return {"error": f"Proaktive E-Mail fehlgeschlagen: {str(e)}"}


# ─── Tool: Get Weather ───────────────────────────────────────────────────────

@register_tool(
    name="get_weather",
    description=(
        "Ruft aktuelle Echtzeit-Wetterdaten ab (Open-Meteo API, Standort Köln). "
        "Liefert Temperatur, Windgeschwindigkeit, Wetterbeschreibung auf Deutsch. "
        "Nutze dieses Tool wenn der User nach dem Wetter fragt, oder wenn du das Wetter "
        "für eine Antwort brauchst (z.B. Kleidungsempfehlung, Ausgehplan, Small Talk)."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def get_weather() -> dict:
    """Fetch current real weather data via the backend's _fetch_real_weather()."""
    try:
        import importlib
        api_mod = importlib.import_module('ailey_api')
        data = api_mod._fetch_real_weather()
        # Build a human-readable summary in German
        temp = data.get("temperature", "?")
        wind = data.get("windspeed", "?")
        label = data.get("label", "Unbekannt")
        game_w = data.get("game_weather", "clear")
        is_day = data.get("is_day", True)

        summary = (
            f"Aktuelles Wetter in Köln: {label}\n"
            f"🌡️ Temperatur: {temp}°C\n"
            f"💨 Wind: {wind} km/h\n"
            f"{'☀️ Tag' if is_day else '🌙 Nacht'}"
        )
        return {
            "message": summary,
            "temperature": temp,
            "windspeed": wind,
            "label": label,
            "game_weather": game_w,
            "is_day": is_day,
        }
    except Exception as e:
        return {"error": f"Wetter konnte nicht abgerufen werden: {str(e)}"}


# ─── Image Generation Tool ──────────────────────────────────────────────────

@register_tool(
    name="generate_image",
    description=(
        "Generate an AI image using MFLUX/Z-Image Turbo locally on this Mac. "
        "IMPORTANT RULES FOR THE PROMPT:\n"
        "- Write a SHORT, FOCUSED English image prompt (1-3 sentences max!)\n"
        "- Describe ONLY visual elements: subject, composition, lighting, colors, style\n"
        "- Do NOT write prose, poetry, or storytelling in the prompt\n"
        "- Example: 'Abandoned rusty car in a misty valley, cracked windshield, blue hour lighting, "
        "industrial ruins in background, cinematic photography style'\n"
        "- Generation takes ~3-5 minutes for 1024x1024. Tell the user it will take a moment.\n"
        "- The finished image appears in Ailey's gallery."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "SHORT English image prompt (1-3 sentences). Only visual descriptions: subject, colors, lighting, style, composition. NO prose or storytelling!"
            },
            "title": {
                "type": "string",
                "description": "Short German title for the artwork (max 5 words)."
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "description": "Image aspect ratio. Default: 1:1"
            },
            "use_ailey_selfie": {
                "type": "boolean",
                "description": "If true, use one of Ailey's emote portraits as init image (img2img mode)."
            },
            "emote_mood": {
                "type": "string",
                "enum": ["default", "thinking", "happy", "sad", "angry", "confused", "flirty",
                         "playful", "coding", "singing", "writing", "sleeping", "tired"],
                "description": "Which Ailey emote to use as base image. Only used if use_ailey_selfie=true."
            },
            "image_strength": {
                "type": "number",
                "description": "How much the init image influences the result (0.0-1.0). Default: 0.4. Lower = more creative freedom."
            },
        },
        "required": ["prompt", "title"],
    },
)
def tool_generate_image(
    prompt: str,
    title: str = "Untitled",
    aspect_ratio: str = "1:1",
    use_ailey_selfie: bool = False,
    emote_mood: str = "default",
    image_strength: float = 0.4,
) -> dict:
    """Generate an image via MFLUX. Runs in background thread, returns immediately."""
    try:
        from ailey_system.image_generator import is_mflux_available, get_ailey_emote_path

        if not is_mflux_available():
            return {"error": "MFLUX ist nicht installiert. Bildgenerierung nicht verfügbar."}

        # Check if already generating
        try:
            import importlib
            api_mod = importlib.import_module('ailey_api')
            idle_thinker = getattr(api_mod, 'idle_thinker', None)
            if idle_thinker and idle_thinker.is_generating_image:
                return {"error": "Es wird gerade schon ein Bild generiert. Bitte warte bis es fertig ist."}
        except Exception:
            pass

        # Resolve selfie image path
        init_image = None
        if use_ailey_selfie:
            init_image = get_ailey_emote_path(emote_mood)
            if not init_image:
                return {"error": f"Emote '{emote_mood}' nicht gefunden."}

        # Start generation in background thread
        import threading

        def _bg_generate():
            try:
                from ailey_system.image_generator import generate_image
                import importlib
                api_mod = importlib.import_module('ailey_api')
                idle_thinker = getattr(api_mod, 'idle_thinker', None)

                if idle_thinker:
                    idle_thinker._generating_image = True

                # Unload Ministral for RAM
                unloaded = False
                if idle_thinker:
                    try:
                        idle_thinker._unload_llm_for_image_gen()
                        unloaded = True
                    except Exception:
                        pass

                try:
                    filepath, filename = generate_image(
                        prompt=prompt,
                        title=title,
                        aspect_ratio=aspect_ratio,
                        image_path=init_image,
                        image_strength=image_strength,
                        low_ram=not unloaded,
                    )
                finally:
                    if idle_thinker:
                        idle_thinker._generating_image = False
                    if unloaded and idle_thinker:
                        try:
                            idle_thinker._reload_llm_after_image_gen()
                        except Exception:
                            pass

                if filepath:
                    # Push to portal gallery
                    try:
                        from ailey_system.portal_poller import get_portal_poller
                        poller = get_portal_poller()
                        file_url = poller._upload_gallery_file(filepath, filename)
                        if file_url:
                            poller._push_gallery_item(
                                item_type="image", title=title[:200],
                                file_url=file_url,
                                metadata={"filename": filename, "prompt": prompt[:200]},
                                source_id=f"image_{filename}",
                            )
                            poller.push_activity("new_image", f"Neues Bild: {title}", emoji="🖼️")
                    except Exception:
                        pass
                    print(f"[Tool:generate_image] ✅ Complete: {filename}")
                else:
                    print("[Tool:generate_image] ❌ Generation failed")
            except Exception as e:
                print(f"[Tool:generate_image] ❌ Error: {e}")
                if idle_thinker:
                    idle_thinker._generating_image = False

        t = threading.Thread(target=_bg_generate, daemon=True)
        t.start()

        mode = "img2img Selfie" if use_ailey_selfie else "txt2img"
        return {
            "message": (
                f"🎨 Bildgenerierung gestartet! ({mode})\n"
                f"Titel: {title}\n"
                f"Format: {aspect_ratio}\n"
                f"⏱️ Dauert ca. 5 Minuten — das Bild erscheint dann in der Galerie."
            ),
            "status": "generating",
            "mode": mode,
            "title": title,
        }
    except Exception as e:
        return {"error": f"Fehler bei Bildgenerierung: {str(e)}"}


# ─── RAG Knowledge Search Tool ──────────────────────────────────────────────

@register_tool(
    name="rag_search",
    description=(
        "Durchsucht Aileys Wissensdatenbank (RAG) nach relevantem Wissen. "
        "Nutze dieses Tool wenn der User nach Fakten, Büchern, Personen, "
        "Projekten, Technik, Lore oder Hintergrundwissen fragt. "
        "NICHT nötig für: Smalltalk, Grüße, Meinungsfragen, ER-Diagramme, "
        "Bildgenerierung, Kalender, Timer oder andere Tool-Aktionen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Die Suchanfrage — sollte die Kernfrage oder das Thema enthalten.",
            },
        },
        "required": ["query"],
    },
)
def _tool_rag_search(query: str) -> dict:
    """Execute RAG search as a tool call."""
    try:
        from ailey_api import app
        core = getattr(app, 'ailey_core', None)
        if not core:
            return {"results": "", "message": "RAG nicht verfügbar (kein Core)."}

        results = core.rag_search(
            query=query,
            user="Simon",
            n_results=5,
            threshold=0.25,
        )
        if not results:
            return {"results": "", "message": "Keine relevanten Ergebnisse gefunden."}

        # Filter: only public knowledge (same logic as portal_rag_search)
        BLOCKED_TYPES = {
            "diary", "private", "personal", "journal", "email",
            "chat_log", "memory", "relationship",
            "thought_introspection", "thought_reflection", "thought_free_thought",
            "thought_diary_writing", "thought_goal_planning", "thought_daydream",
            "thought_creative", "thought_music", "thought_existential",
            "self_prompt",
        }
        filtered = []
        for r in results:
            doc_type = r.get("metadata", {}).get("doc_type", "general")
            if doc_type in BLOCKED_TYPES or doc_type.startswith("thought_"):
                continue
            text = r.get("text", "")
            lower_text = text.lower()
            if any(w in lower_text for w in ["tagebuch", "diary", "simon privat", "mein leben"]):
                continue
            filtered.append(r)

        if not filtered:
            return {"results": "", "message": "Keine öffentlich relevanten Ergebnisse."}

        # Build compact text
        rag_text = ""
        for r in filtered[:4]:
            title = r.get("metadata", {}).get("title", "Quelle")
            text = r.get("text", "")[:500]
            rag_text += f"• [{title}]: {text}\n"

        return {"results": rag_text.strip(), "count": len(filtered)}

    except Exception as e:
        return {"results": "", "error": str(e)}

