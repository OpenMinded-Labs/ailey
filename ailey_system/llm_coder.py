# -*- coding: utf-8 -*-
"""
🐹 Hamster — Qwen2.5-Coder-1.5B-Instruct (Small code model for Ailey Code Mode)

Internal model names:
  • A!ley     — Ministral-3-14B-Reasoning (Main LLM, personality & planning)
  • CodeA!ley — Qwen2.5-Coder-14B-Instruct (Large coder, Korean rap & code agent)
  • Hamster   — Qwen2.5-Coder-1.5B-Instruct (This file! Fast autocomplete & lint)

Two functions:
  1. Autocomplete: Fast inline completions while typing
  2. Lint/Error detection: Background analysis of files for errors

Runs alongside the main Ministral 14B model (A!ley).
Auto-loads on first use, auto-unloads after idle timeout.
Uses a separate MLX lock to avoid conflicts with main model.

Model: mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit (~1GB)
"""
from __future__ import annotations
import os
import time
import threading
from typing import Optional, Dict, List

# Module-level state
_coder_model = None
_coder_tokenizer = None

# CRITICAL: Share the same GPU lock with llm_mlx to prevent concurrent Metal calls!
# Two separate locks caused SIGABRT crashes when both models ran on GPU simultaneously.
try:
    from ailey_system.llm_mlx import _mlx_lock as _coder_lock
except ImportError:
    # Fallback if llm_mlx not available (shouldn't happen in normal operation)
    _coder_lock = threading.RLock()
_coder_last_used: float = 0.0
_coder_loading = False
_CODER_IDLE_TIMEOUT = 300  # Auto-unload after 5 min idle
_coder_unload_timer: Optional[threading.Timer] = None

# Settings
_coder_autocomplete_enabled = True
_coder_lint_enabled = True

# Coordination: Hamster yields when A!ley (Ministral) is generating
_ailey_busy = False  # Set by API when code-chat or action is running

# Model ID — Use DoRA-fused LintingHamster (Mr. Fluffbytes) if available,
# otherwise fall back to base Qwen model.
CODER_MODEL_ID = "mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit"  # HF fallback
CODER_LOCAL_NAME_FUSED = "LintingHamster-1.5B"      # DoRA-fused Mr. Fluffbytes
CODER_LOCAL_NAME_BASE = "Qwen2.5-Coder-1.5B-Instruct-4bit"  # Base model fallback


def _coder_model_path() -> str:
    """Return the local path for the coder model.
    Prefers DoRA-fused LintingHamster-1.5B (Mr. Fluffbytes) over base Qwen."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Prefer fused Mr. Fluffbytes model
    fused_path = os.path.join(project_root, "mlx_models", CODER_LOCAL_NAME_FUSED)
    if os.path.isdir(fused_path) and os.path.isfile(os.path.join(fused_path, "config.json")):
        return fused_path
    # Fallback to base Qwen
    return os.path.join(project_root, "mlx_models", CODER_LOCAL_NAME_BASE)


def _ensure_coder_loaded() -> bool:
    """Lazy-load the coder model on first use. Thread-safe."""
    global _coder_model, _coder_tokenizer, _coder_last_used, _coder_loading
    if _coder_model is not None:
        _coder_last_used = time.time()
        return True

    with _coder_lock:
        if _coder_model is not None:
            _coder_last_used = time.time()
            return True
        if _coder_loading:
            return False  # Another thread is loading

        _coder_loading = True
        try:
            import mlx_lm
            model_path = _coder_model_path()

            # Auto-download if not present
            if not os.path.isdir(model_path) or not os.path.isfile(os.path.join(model_path, "config.json")):
                print(f"[Hamster 🐹] ⬇️  Downloading {CODER_MODEL_ID} (~1 GB)...")
                # Set cache dir
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                local_model_dir = os.path.join(project_root, "mlx_models")
                os.makedirs(local_model_dir, exist_ok=True)
                os.environ["HF_HOME"] = local_model_dir
                os.environ["HUGGINGFACE_HUB_CACHE"] = local_model_dir
                use_id = CODER_MODEL_ID
            else:
                use_id = model_path

            start = time.time()
            _is_fused = CODER_LOCAL_NAME_FUSED in str(use_id)
            _label = "Mr. Fluffbytes (LintingHamster-1.5B)" if _is_fused else CODER_LOCAL_NAME_BASE
            print(f"[Hamster 🐹] 🧠 Loading coder model: {_label}...")
            _coder_model, _coder_tokenizer = mlx_lm.load(use_id)

            # Warmup
            _ = mlx_lm.generate(_coder_model, _coder_tokenizer, prompt="# Hello", max_tokens=1, verbose=False)

            # Create symlink if downloaded from HF
            if use_id == CODER_MODEL_ID and not os.path.isdir(model_path):
                try:
                    import glob
                    snap = glob.glob(os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "mlx_models", "models--*Qwen*Coder*1.5B*4bit", "snapshots", "*", "config.json"
                    ))
                    if snap:
                        snap_dir = os.path.dirname(snap[0])
                        os.symlink(snap_dir, model_path)
                        print(f"[Hamster 🐹] 🔗 Symlink: {CODER_LOCAL_NAME_BASE} -> {snap_dir}")
                except Exception as e:
                    print(f"[Hamster 🐹] ⚠️  Symlink failed: {e}")

            elapsed = time.time() - start
            _coder_last_used = time.time()
            print(f"[Hamster 🐹] ✅ Coder model loaded in {elapsed:.1f}s")
            _schedule_coder_unload()
            return True
        except Exception as e:
            print(f"[Hamster 🐹] ❌ Load failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            _coder_loading = False


def _schedule_coder_unload():
    """Schedule auto-unload after idle timeout."""
    global _coder_unload_timer
    if _coder_unload_timer is not None:
        _coder_unload_timer.cancel()
    _coder_unload_timer = threading.Timer(_CODER_IDLE_TIMEOUT + 5, _check_coder_unload)
    _coder_unload_timer.daemon = True
    _coder_unload_timer.start()


def _check_coder_unload():
    """Check if coder model should be unloaded due to idle timeout."""
    global _coder_model, _coder_tokenizer, _coder_unload_timer
    with _coder_lock:
        if _coder_model is None:
            return
        idle = time.time() - _coder_last_used
        if idle < _CODER_IDLE_TIMEOUT:
            _schedule_coder_unload()
            return
        print(f"[Hamster 🐹] Auto-unloading (idle {idle:.0f}s)")
        # Sync ALL pending Metal ops before freeing references
        try:
            import mlx.core as mx
            mx.synchronize()
        except Exception:
            pass
        _coder_model = None
        _coder_tokenizer = None
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except:
            pass
        gc.collect()
        print("[Hamster 🐹] ✅ Coder model unloaded, RAM freed")


def unload_coder():
    """Manually unload the coder model immediately."""
    global _coder_model, _coder_tokenizer, _coder_last_used, _coder_unload_timer
    with _coder_lock:
        if _coder_unload_timer:
            _coder_unload_timer.cancel()
            _coder_unload_timer = None
        if _coder_model is None:
            return {"unloaded": False, "reason": "not loaded"}
        # Sync ALL pending Metal ops before freeing references
        try:
            import mlx.core as mx
            mx.synchronize()
        except Exception:
            pass
        _coder_model = None
        _coder_tokenizer = None
        _coder_last_used = 0.0
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except:
            pass
        gc.collect()
        print("[Hamster 🐹] Manually unloaded")
        return {"unloaded": True}


def is_hamster_available() -> bool:
    """Check if the Hamster (Qwen 1.5B) model files exist locally."""
    path = _coder_model_path()
    return os.path.isdir(path) and os.path.isfile(os.path.join(path, "config.json"))


def hamster_generate(system: str, user: str, max_tokens: int = 400,
                     temperature: float = 0.6) -> Optional[str]:
    """Generate a chat reply using Mr. Fluffbytes (LintingHamster-1.5B).

    Used for the Portal "Hamster Mode" — Mr. Fluffbytes is a hamster who
    works as a linting assistant. Excellent at code-linting, cheerfully
    hallucinates about everything else. DoRA-fused from Qwen2.5-Coder-1.5B.

    Auto-loads on first use, auto-unloads after 5 min idle.
    Uses shared _mlx_lock (same Metal GPU).

    Returns:
        Generated text or None on failure.
    """
    global _coder_last_used
    if not _ensure_coder_loaded():
        return None

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.9)

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            result = mlx_lm.generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            _schedule_coder_unload()

            result = result.strip() if result else ""
            for stop in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
                if stop in result:
                    result = result[:result.index(stop)]
            return result.strip() or None
        except Exception as e:
            print(f"[Hamster 🐹] ❌ hamster_generate error: {e}")
            return None


def hamster_stream(system: str, user: str, max_tokens: int = 400,
                   temperature: float = 0.6):
    """Stream a chat reply token-by-token from Hamster (Qwen2.5-Coder-1.5B).

    Yields text chunks. Used for Portal Hamster mode with partial pushes.
    Auto-loads on first use, auto-unloads after 5 min idle.

    Yields:
        str: Text chunks as they are generated.
    """
    global _coder_last_used
    if not _ensure_coder_loaded():
        yield "[Hamster konnte nicht geladen werden 🐹💀]"
        return

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.9)
    _stop_seqs = {"<|im_end|>", "<|im_start|>", "<|endoftext|>"}

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            for chunk in mlx_lm.stream_generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
            ):
                text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                if not text:
                    continue
                # Stop on EOS tokens
                hit_stop = False
                for stop in _stop_seqs:
                    if stop in text:
                        text = text[:text.index(stop)]
                        if text:
                            yield text
                        hit_stop = True
                        break
                if hit_stop:
                    break
                yield text
            _schedule_coder_unload()
        except Exception as e:
            print(f"[Hamster 🐹] ❌ hamster_stream error: {e}")
            yield f"[Hamster-Fehler: {e} 🐹💀]"


# ══════════════════════════════════════════════════════════════════════════════
# AUTOCOMPLETE
# ══════════════════════════════════════════════════════════════════════════════

def autocomplete(
    code_before: str,
    code_after: str = "",
    language: str = "python",
    max_tokens: int = 64,
    temperature: float = 0.2,
) -> Optional[str]:
    """Generate inline code completion.

    Uses fill-in-the-middle (FIM) style prompting for context-aware completions.

    Args:
        code_before: Code text before the cursor
        code_after: Code text after the cursor (for FIM context)
        language: Programming language
        max_tokens: Max tokens to generate (keep small for speed)
        temperature: Low = more deterministic

    Returns:
        Completion string or None
    """
    global _coder_last_used
    if not _coder_autocomplete_enabled:
        return None
    # Yield to Ailey when she's generating (agentic chat/action)
    if _ailey_busy:
        return None
    if not _ensure_coder_loaded():
        return None

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    # Build prompt: Qwen2.5-Coder supports fill-in-middle via chat
    # Use a focused prompt that generates only the completion
    system = (
        f"You are a code completion engine. "
        f"Language: {language}. "
        f"Complete the code at the cursor position. "
        f"Output ONLY the completion text, nothing else. "
        f"No explanations, no markdown, no code fences. "
        f"Keep it short (1-3 lines max)."
    )

    user_msg = f"Complete the code at [CURSOR]:\n\n{code_before[-1500:]}[CURSOR]{code_after[:500]}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except:
        # Fallback: Qwen ChatML format
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.8)

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            result = mlx_lm.generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            _schedule_coder_unload()

            # Clean up result
            result = result.strip() if result else ""
            # Remove common artifacts
            for stop in ("<|im_end|>", "<|im_start|>", "```", "[CURSOR]"):
                if stop in result:
                    result = result[:result.index(stop)]
            # Don't return empty or too-short completions
            if len(result.strip()) < 2:
                return None
            return result.strip()
        except Exception as e:
            print(f"[Hamster 🐹] Autocomplete error: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
# CODE GENERATION — Delegated by Ailey during Agent runs
# ══════════════════════════════════════════════════════════════════════════════

def generate_code(
    spec: str,
    language: str = "python",
    filename: str = "",
    context: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Optional[str]:
    """Generate a complete code file from a specification.

    Used by A!ley's Agent Loop to delegate code writing to the specialised
    Hamster (Qwen2.5-Coder-1.5B) while she handles planning and
    orchestration on the larger Ministral 14B.

    Args:
        spec: Natural language description of what the code should do.
              Should be detailed — class names, functions, dependencies.
        language: Target language (python, typescript, javascript, tsx, rust, php, …)
        filename: Target filename hint (e.g. "App.tsx") for context.
        context: Optional existing code/context the new code relates to
                 (imports, interfaces, related files). Max ~2000 chars sent.
        max_tokens: Max tokens for the generated code (default 2048).
        temperature: Lower = more deterministic (default 0.3).

    Returns:
        Generated code as a string, or None on failure.
    """
    global _coder_last_used
    if not _ensure_coder_loaded():
        return None

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    system = (
        f"You are an expert code generator. Language: {language}.\n"
        f"Generate ONLY the code — no explanations, no markdown fences, no comments about what it does.\n"
        f"Output production-ready, clean, idiomatic {language} code.\n"
        f"Include necessary imports and type annotations where appropriate.\n"
        f"Follow best practices and conventions for {language}."
    )

    user_parts = []
    if filename:
        user_parts.append(f"Filename: {filename}")
    user_parts.append(f"Specification:\n{spec}")
    if context:
        # Trim context to avoid overflowing the small model
        user_parts.append(f"\nRelated existing code (for reference):\n{context[:2000]}")
    user_parts.append(f"\nGenerate the complete {language} code now:")

    user_msg = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.8)

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            start = time.time()
            result = mlx_lm.generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            elapsed = time.time() - start
            _schedule_coder_unload()

            # Clean up
            result = result.strip() if result else ""
            # Strip markdown fences if the model wraps them
            if result.startswith("```"):
                lines = result.split("\n")
                # Remove first line (```lang) and last line (```)
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                result = "\n".join(lines)
            # Strip stop tokens
            for stop in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
                if stop in result:
                    result = result[:result.index(stop)]

            result = result.strip()
            if len(result) < 5:
                print(f"[Hamster 🐹] generate_code: result too short ({len(result)} chars)")
                return None

            print(f"[Hamster 🐹] ✅ generate_code: {filename or language} — {len(result)} chars in {elapsed:.1f}s")
            return result
        except Exception as e:
            print(f"[Hamster 🐹] ❌ generate_code error: {e}")
            import traceback
            traceback.print_exc()
            return None


# ══════════════════════════════════════════════════════════════════════════════
# LINT / ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _static_lint_python(code: str) -> List[Dict]:
    """Deterministic Python lint using ast.parse + heuristics.
    Always catches syntax errors reliably, unlike the tiny LLM."""
    import ast
    import re
    diagnostics: List[Dict] = []

    # 1. Syntax errors via ast.parse
    ast_error_lines: set = set()
    try:
        ast.parse(code)
    except SyntaxError as e:
        line_no = e.lineno or 1
        ast_error_lines.add(line_no)
        diagnostics.append({
            "line": line_no,
            "severity": "error",
            "message": f"SyntaxError: {e.msg}",
        })

    # 2. Heuristic checks per line
    lines = code.split('\n')
    indent_stack: List[int] = [0]
    in_multiline_string = False
    string_delim = None

    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        lstripped = line.lstrip()

        # Track multiline strings
        for delim in ('"""', "'''"):
            count = stripped.count(delim)
            if in_multiline_string and string_delim == delim:
                if count % 2 == 1:
                    in_multiline_string = False
                    string_delim = None
                continue
            elif not in_multiline_string and count % 2 == 1:
                in_multiline_string = True
                string_delim = delim

        if in_multiline_string:
            continue

        # Skip comments and empty lines
        if not stripped or lstripped.startswith('#'):
            continue

        # Check for common Python mistakes

        # Missing colon after def/class/if/elif/else/for/while/try/except/finally/with
        colon_keywords = r'^(def|class|if|elif|for|while|try|except|finally|with|async\s+def|async\s+for|async\s+with)\b'
        m = re.match(colon_keywords, lstripped)
        if m and i not in ast_error_lines:
            # Check if line ends with colon (ignoring comments)
            code_part = stripped.split('#')[0].rstrip()
            if not code_part.endswith(':') and not code_part.endswith('\\'):
                # Could be a multiline statement — check for open parens
                if code_part.count('(') <= code_part.count(')') and \
                   code_part.count('[') <= code_part.count(']'):
                    diagnostics.append({
                        "line": i,
                        "severity": "error",
                        "message": f"SyntaxError: Fehlender Doppelpunkt ':' nach '{m.group(1)}'",
                    })

        # else/elif without colon
        if re.match(r'^(else|elif)\b', lstripped) and i not in ast_error_lines:
            code_part = stripped.split('#')[0].rstrip()
            if not code_part.endswith(':'):
                diagnostics.append({
                    "line": i,
                    "severity": "error",
                    "message": "SyntaxError: Fehlender Doppelpunkt ':' nach else/elif",
                })

        # Mismatched brackets on single line
        for open_b, close_b, name in [('(', ')', 'Klammern'), ('[', ']', 'eckige Klammern'), ('{', '}', 'geschweifte Klammern')]:
            diff = stripped.count(open_b) - stripped.count(close_b)
            # Only flag if clearly unbalanced and not continued
            if diff < 0 and not stripped.endswith('\\'):
                diagnostics.append({
                    "line": i,
                    "severity": "error",
                    "message": f"Unbalancierte {name}: zu viele '{close_b}'",
                })

        # Assignment in condition (common mistake)
        if re.match(r'^(if|elif|while)\s+.*[^=!<>]=[^=]', lstripped) and '==' not in lstripped:
            # Avoid false positives with walrus operator
            if ':=' not in lstripped:
                diagnostics.append({
                    "line": i,
                    "severity": "warning",
                    "message": "Möglicher Fehler: '=' statt '==' in Bedingung?",
                })

        # Print statement (Python 2 style)
        if re.match(r'^print\s+[^(]', lstripped):
            diagnostics.append({
                "line": i,
                "severity": "error",
                "message": "SyntaxError: 'print' ist eine Funktion in Python 3 — print(...) verwenden",
            })

    # 3. Try to detect undefined names using AST (only if code parses)
    try:
        tree = ast.parse(code)
        defined_names: set = set()
        imported_names: set = set()
        used_names: set = set()
        import_lines: Dict[str, int] = {}

        for node in ast.walk(tree):
            # Collect defined names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name)
                for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                    defined_names.add(arg.arg)
                if node.args.vararg:
                    defined_names.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined_names.add(node.args.kwarg.arg)
            elif isinstance(node, ast.ClassDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_names.add(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                defined_names.add(elt.id)
            elif isinstance(node, ast.For):
                if isinstance(node.target, ast.Name):
                    defined_names.add(node.target.id)
            elif isinstance(node, (ast.Import,)):
                for alias in node.names:
                    name = alias.asname or alias.name.split('.')[0]
                    imported_names.add(name)
                    import_lines[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names.add(name)
                    import_lines[name] = node.lineno
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                defined_names.add(node.name)
            elif isinstance(node, ast.With):
                for item in node.items:
                    if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                        defined_names.add(item.optional_vars.id)
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in node.generators:
                    if isinstance(gen.target, ast.Name):
                        defined_names.add(gen.target.id)

        # Built-in names that shouldn't be flagged
        builtins_set = {
            'True', 'False', 'None', 'print', 'len', 'range', 'int', 'str', 'float',
            'list', 'dict', 'set', 'tuple', 'bool', 'type', 'isinstance', 'issubclass',
            'hasattr', 'getattr', 'setattr', 'delattr', 'input', 'open', 'super',
            'property', 'staticmethod', 'classmethod', 'abs', 'all', 'any', 'bin',
            'chr', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter', 'format',
            'frozenset', 'globals', 'hash', 'hex', 'id', 'iter', 'map', 'max', 'min',
            'next', 'object', 'oct', 'ord', 'pow', 'repr', 'reversed', 'round',
            'slice', 'sorted', 'sum', 'vars', 'zip', 'breakpoint', 'callable',
            'compile', 'complex', 'copyright', 'credits', 'exit', 'help', 'license',
            'memoryview', 'quit', 'bytes', 'bytearray', 'Exception', 'BaseException',
            'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError',
            'ImportError', 'RuntimeError', 'StopIteration', 'OSError', 'IOError',
            'FileNotFoundError', 'NotImplementedError', 'ZeroDivisionError',
            'NameError', 'SyntaxError', 'ModuleNotFoundError', 'OverflowError',
            'RecursionError', 'SystemExit', 'KeyboardInterrupt', 'AssertionError',
            'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError',
            'PermissionError', 'ProcessLookupError', 'TimeoutError',
            'ConnectionError', 'BrokenPipeError', 'ConnectionRefusedError',
            'ConnectionResetError', 'ConnectionAbortedError',
            'self', 'cls', '__name__', '__file__', '__doc__', '__all__',
            '__init__', '__main__', 'NotImplemented', 'Ellipsis',
        }

        all_defined = defined_names | imported_names | builtins_set

        # Unused imports
        for name in imported_names:
            if name not in used_names and name != '*':
                diagnostics.append({
                    "line": import_lines.get(name, 1),
                    "severity": "warning",
                    "message": f"Ungenutzter Import: '{name}'",
                })

    except SyntaxError:
        pass  # Already caught above

    # Deduplicate by (line, message)
    seen = set()
    unique_diags = []
    for d in diagnostics:
        key = (d['line'], d['message'])
        if key not in seen:
            seen.add(key)
            unique_diags.append(d)

    return unique_diags


def _static_lint_javascript(code: str) -> List[Dict]:
    """Basic JavaScript/TypeScript lint via heuristics."""
    import re
    diagnostics: List[Dict] = []
    lines = code.split('\n')

    # Track bracket balance
    total_parens = 0
    total_brackets = 0
    total_braces = 0

    in_multiline_comment = False
    in_template_literal = False

    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        lstripped = line.lstrip()

        # Track multiline comments
        if in_multiline_comment:
            if '*/' in stripped:
                in_multiline_comment = False
            continue
        if '/*' in stripped and '*/' not in stripped:
            in_multiline_comment = True
            continue

        # Skip single-line comments
        if lstripped.startswith('//'):
            continue

        # Track template literals (backticks)
        backtick_count = stripped.count('`')
        if backtick_count % 2 == 1:
            in_template_literal = not in_template_literal
        if in_template_literal:
            # Still count brackets inside template literals (${...} contains real code)
            total_parens += stripped.count('(') - stripped.count(')')
            total_brackets += stripped.count('[') - stripped.count(']')
            total_braces += stripped.count('{') - stripped.count('}')
            continue

        # Track brackets
        total_parens += stripped.count('(') - stripped.count(')')
        total_brackets += stripped.count('[') - stripped.count(']')
        total_braces += stripped.count('{') - stripped.count('}')

        # Assignment in condition
        if re.match(r'^\s*(if|while)\s*\(', stripped):
            # Check for = instead of === or ==
            cond = re.search(r'\((.+)\)', stripped)
            if cond:
                cond_text = cond.group(1)
                if re.search(r'[^=!<>]=[^=]', cond_text) and ':=' not in cond_text:
                    diagnostics.append({
                        "line": i,
                        "severity": "warning",
                        "message": "Möglicher Fehler: '=' statt '===' in Bedingung?",
                    })

        # == instead of === (JS)
        if '==' in stripped and '===' not in stripped and '!==' not in stripped:
            # Avoid false positives with !=
            parts = stripped.split('==')
            if len(parts) >= 2 and not parts[0].rstrip().endswith('!'):
                diagnostics.append({
                    "line": i,
                    "severity": "info",
                    "message": "Hinweis: '==' statt '===' — strikte Gleichheit empfohlen",
                })

        # console.log left in code
        if 'console.log(' in stripped:
            diagnostics.append({
                "line": i,
                "severity": "info",
                "message": "console.log() gefunden — vor Produktion entfernen?",
            })

        # var usage (should be let/const)
        if re.match(r'^\s*var\s+', stripped):
            diagnostics.append({
                "line": i,
                "severity": "warning",
                "message": "'var' ist veraltet — 'let' oder 'const' verwenden",
            })

    # Final bracket balance
    if total_parens != 0:
        diagnostics.append({
            "line": len(lines),
            "severity": "error",
            "message": f"Unbalancierte Klammern: {abs(total_parens)} {'fehlende' if total_parens > 0 else 'überschüssige'} ')'",
        })
    if total_braces != 0:
        diagnostics.append({
            "line": len(lines),
            "severity": "error",
            "message": f"Unbalancierte geschweifte Klammern: {abs(total_braces)} {'fehlende' if total_braces > 0 else 'überschüssige'} '}}'",
        })

    return diagnostics


def lint_code(
    code: str,
    filename: str = "untitled.py",
    language: str = "python",
    max_tokens: int = 800,
) -> List[Dict]:
    """Analyze code for errors, warnings, and issues.

    Uses a HYBRID approach:
    1. Deterministic static analysis (ast.parse for Python, heuristics for JS/TS)
       — Always catches syntax errors reliably
    2. Optional LLM analysis via Hamster (Qwen2.5-Coder) for deeper semantic issues

    Args:
        code: Full file content to analyze
        filename: Name of the file
        language: Programming language

    Returns:
        List of diagnostic dicts: [{line, severity, message}, ...]
        severity: "error" | "warning" | "info"
    """
    if not _coder_lint_enabled:
        return []
    if not code.strip():
        return []

    # ── Phase 1: Deterministic static analysis (instant, always works) ──
    diagnostics: List[Dict] = []

    lang_lower = language.lower()
    if lang_lower in ('python', 'py'):
        diagnostics = _static_lint_python(code)
    elif lang_lower in ('javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx'):
        diagnostics = _static_lint_javascript(code)

    # ── Phase 2: LLM analysis for deeper issues (if model available) ──
    # Only run LLM lint if no syntax errors found (saves GPU time)
    # and if coder model is available
    has_errors = any(d['severity'] == 'error' for d in diagnostics)
    if not has_errors and not _ailey_busy:
        llm_diags = _llm_lint_code(code, filename, language, max_tokens)
        # Merge: add LLM findings that don't duplicate static ones
        existing_lines = {(d['line'], d['severity']) for d in diagnostics}
        for d in llm_diags:
            if (d['line'], d['severity']) not in existing_lines:
                diagnostics.append(d)

    # Sort by line number
    diagnostics.sort(key=lambda d: d['line'])

    if diagnostics:
        print(f"[Hamster 🐹] Lint: {len(diagnostics)} issues in {filename}")
    return diagnostics


def _llm_lint_code(
    code: str,
    filename: str = "untitled.py",
    language: str = "python",
    max_tokens: int = 800,
) -> List[Dict]:
    """LLM-based lint using Qwen2.5-Coder for semantic analysis."""
    global _coder_last_used

    if _ailey_busy:
        return []
    if not _ensure_coder_loaded():
        return []

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    system = (
        "You are a code linter. Find bugs, logic errors, undefined variables, "
        "type mismatches, and potential runtime errors.\n\n"
        "For each issue, output one line:\n"
        "LINE:<number>|SEVERITY:<error|warning|info>|MSG:<description>\n\n"
        "If no issues: output NO_ISSUES\n"
        "No markdown, no explanations."
    )

    code_truncated = code[:3000]
    if len(code) > 3000:
        code_truncated += f"\n... (truncated, {len(code)} chars total)"

    user_msg = f"File: {filename} ({language})\n\n```{language}\n{code_truncated}\n```"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=0.1, top_p=0.8)

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            result = mlx_lm.generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            _schedule_coder_unload()
        except Exception as e:
            print(f"[Hamster 🐹] LLM lint error: {e}")
            return []

    # Parse structured output
    result = result.strip() if result else ""
    for stop in ("<|im_end|>", "<|im_start|>"):
        if stop in result:
            result = result[:result.index(stop)]

    if "NO_ISSUES" in result:
        return []

    diagnostics = []
    for line in result.strip().split('\n'):
        line = line.strip()
        if not line or not line.startswith('LINE:'):
            continue
        try:
            parts = {}
            for segment in line.split('|'):
                if ':' in segment:
                    key, val = segment.split(':', 1)
                    parts[key.strip()] = val.strip()
            if 'LINE' in parts and 'MSG' in parts:
                line_no = int(parts['LINE'])
                severity = parts.get('SEVERITY', 'warning').lower()
                if severity not in ('error', 'warning', 'info'):
                    severity = 'warning'
                diagnostics.append({
                    "line": line_no,
                    "severity": severity,
                    "message": parts['MSG'],
                })
        except (ValueError, KeyError):
            continue

    return diagnostics


# ══════════════════════════════════════════════════════════════════════════════
# Settings & Status
# ══════════════════════════════════════════════════════════════════════════════

def set_ailey_busy(busy: bool):
    """Called by API when Ailey main model starts/finishes code-chat or action.
    While busy, coder autocomplete/lint silently yield (return empty)."""
    global _ailey_busy
    _ailey_busy = busy


# ══════════════════════════════════════════════════════════════════════════════
# PROSE LINT — Used by Prose Pipeline v2 for mechanical text checks
# ══════════════════════════════════════════════════════════════════════════════

def generate_prose_lint(system: str, user: str, max_tokens: int = 1500, temperature: float = 0.15) -> Optional[str]:
    """Run a prose-linting prompt through the Qwen Coder model.

    The Coder model (Qwen2.5-Coder-1.5B) is small and fast — ideal for
    mechanical checks like finding English words in German text, repetition
    detection, and formatting issues.  Returns raw LLM output (expected JSON).

    Uses the shared _mlx_lock so it won't collide with Ministral.
    Auto-loads the coder model if not already loaded.

    Returns:
        Raw string output from the model, or None on failure.
    """
    global _coder_last_used
    if not _ensure_coder_loaded():
        return None

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        prompt = _coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.8)

    with _coder_lock:
        try:
            _coder_last_used = time.time()
            start = time.time()
            result = mlx_lm.generate(
                _coder_model, _coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            elapsed = time.time() - start
            _schedule_coder_unload()

            result = result.strip() if result else ""
            for stop in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
                if stop in result:
                    result = result[:result.index(stop)]

            result = result.strip()
            if len(result) < 3:
                print(f"[Hamster 🐹] prose_lint: result too short ({len(result)} chars)")
                return None

            print(f"[Hamster 🐹] ✅ prose_lint: {len(result)} chars in {elapsed:.1f}s")
            return result
        except Exception as e:
            print(f"[Hamster 🐹] ❌ prose_lint error: {e}")
            return None


def get_coder_settings() -> Dict:
    """Get current coder settings."""
    return {
        "autocomplete_enabled": _coder_autocomplete_enabled,
        "lint_enabled": _coder_lint_enabled,
        "model_loaded": _coder_model is not None,
        "model_loading": _coder_loading,
        "model_id": CODER_LOCAL_NAME_FUSED if os.path.isdir(os.path.join(_BASE, "mlx_models", CODER_LOCAL_NAME_FUSED)) else CODER_LOCAL_NAME_BASE,
        "idle_timeout": _CODER_IDLE_TIMEOUT,
        "last_used": _coder_last_used if _coder_last_used > 0 else None,
        "ailey_busy": _ailey_busy,
    }


def update_coder_settings(autocomplete: Optional[bool] = None, lint: Optional[bool] = None) -> Dict:
    """Update coder settings."""
    global _coder_autocomplete_enabled, _coder_lint_enabled
    if autocomplete is not None:
        _coder_autocomplete_enabled = autocomplete
        print(f"[Hamster 🐹] Autocomplete: {'✅ ON' if autocomplete else '⏹ OFF'}")
    if lint is not None:
        _coder_lint_enabled = lint
        print(f"[Hamster 🐹] Lint: {'✅ ON' if lint else '⏹ OFF'}")
    return get_coder_settings()


# ══════════════════════════════════════════════════════════════════════════════
# 🧠 CodeA!ley (Qwen 14B) — Korean Rap Writing for Song Pipeline
# ══════════════════════════════════════════════════════════════════════════════

CODER_14B_LOCAL_NAME_FUSED = "CodeAiley-14B"                     # DoRA-fused CodeA!ley
CODER_14B_LOCAL_NAME_BASE  = "Qwen2.5-Coder-14B-Instruct-4bit"  # Base model fallback
_large_coder_model = None
_large_coder_tokenizer = None


def _large_coder_model_path() -> str:
    """Return the local path for the large coder model (14B).
    Prefers DoRA-fused CodeAiley-14B, falls back to base Qwen2.5-Coder-14B."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fused_path = os.path.join(project_root, "mlx_models", CODER_14B_LOCAL_NAME_FUSED)
    if os.path.isdir(fused_path):
        return fused_path
    return os.path.join(project_root, "mlx_models", CODER_14B_LOCAL_NAME_BASE)


def load_large_coder() -> bool:
    """Load the Qwen2.5-Coder-14B model. Must hold _coder_lock externally or be single-threaded.
    
    Call unload_coder() first if the small model is loaded.
    Call this AFTER unloading Ministral to have enough GPU memory (~10GB needed).
    
    Returns True if loaded successfully.
    """
    global _large_coder_model, _large_coder_tokenizer
    if _large_coder_model is not None:
        return True

    model_path = _large_coder_model_path()
    if not os.path.isdir(model_path):
        print(f"[CodeA!ley 🧠] ❌ Model not found at {model_path}")
        return False

    try:
        import mlx_lm
        import gc
        import mlx.core as mx

        # Ensure small coder is unloaded first
        unload_coder()
        gc.collect()
        mx.metal.clear_cache()

        _is_fused = CODER_14B_LOCAL_NAME_FUSED in model_path
        _label = f"CodeA!ley-14B (DoRA-fused)" if _is_fused else CODER_14B_LOCAL_NAME_BASE
        print(f"[CodeA!ley 🧠] 🔄 Loading {_label} (~8 GB)...")
        start = time.time()
        with _coder_lock:
            _large_coder_model, _large_coder_tokenizer = mlx_lm.load(model_path)
        elapsed = time.time() - start
        print(f"[CodeA!ley 🧠] ✅ Loaded in {elapsed:.1f}s")
        return True
    except Exception as e:
        print(f"[CodeA!ley 🧠] ❌ Load failed: {e}")
        _large_coder_model = None
        _large_coder_tokenizer = None
        return False


def unload_large_coder():
    """Unload the Qwen 14B model and free GPU memory."""
    global _large_coder_model, _large_coder_tokenizer
    with _coder_lock:
        if _large_coder_model is None:
            return
        try:
            import mlx.core as mx
            mx.synchronize()
        except Exception:
            pass
        _large_coder_model = None
        _large_coder_tokenizer = None
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass
        gc.collect()
        print("[CodeA!ley 🧠] ✅ Unloaded, RAM freed")


def generate_korean_rap(system: str, user: str, max_tokens: int = 600,
                        temperature: float = 0.7) -> Optional[str]:
    """Generate Korean rap lyrics using the large Qwen 14B model.
    
    Must call load_large_coder() first!
    Uses the shared _coder_lock to avoid GPU conflicts.
    
    Returns:
        Raw string output, or None on failure.
    """
    if _large_coder_model is None:
        print("[CodeA!ley 🧠] ❌ generate_korean_rap called but model not loaded")
        return None

    import mlx_lm
    from mlx_lm.sample_utils import make_sampler

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        prompt = _large_coder_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    sampler = make_sampler(temp=temperature, top_p=0.8)

    with _coder_lock:
        try:
            start = time.time()
            result = mlx_lm.generate(
                _large_coder_model, _large_coder_tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
            elapsed = time.time() - start

            result = result.strip() if result else ""
            for stop in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
                if stop in result:
                    result = result[:result.index(stop)]

            result = result.strip()
            if len(result) < 5:
                print(f"[CodeA!ley 🧠] ⚠️ Result too short ({len(result)} chars)")
                return None

            print(f"[CodeA!ley 🧠] ✅ Korean rap: {len(result)} chars in {elapsed:.1f}s")
            return result
        except Exception as e:
            print(f"[CodeA!ley 🧠] ❌ Generation error: {e}")
            return None
