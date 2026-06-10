# -*- coding: utf-8 -*-
"""
Venv Doctor — Diagnostik & Schutz für Ailey-Environments
==========================================================
Prüft ob venvs, Binaries und C-Extensions intakt sind.
Erkennt APFS-Kompressionsschäden automatisch und loggt Reparatur-Hinweise.

Wird aufgerufen:
  - Beim API-Start (health_check_all)
  - Bei fehlgeschlagenen Subprocess-Aufrufen (diagnose_subprocess_failure)
  - Manuell: python -m ailey_system.venv_doctor

Typische APFS-Symptome:
  - Bus Error (signal 10 / exit 138) beim Import von C-Extensions
  - Hängende Imports (transformers, torch, tokenizers)
  - "killed" Processes (signal 9 / exit 137)
  - Corrupted .so/.dylib Dateien

Schutzmaßnahmen:
  - chflags nocompressed auf allen venv-Ordnern
  - Spotlight-Exclusion (.metadata_never_index)
  - xattr -d com.apple.decmpfs auf verdächtigen .so-Dateien
"""
from __future__ import annotations

import os
import sys
import time
import json
import subprocess
import glob
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE = os.path.join(_BASE_DIR, "venv_doctor.log")

# All environments we need to protect
ENVIRONMENTS = {
    "ailey_main": {
        "venv": os.path.join(_BASE_DIR, ".venv"),
        "python": os.path.join(_BASE_DIR, ".venv", "bin", "python"),
        "test_imports": ["flask", "torch", "mlx.core", "sentence_transformers", "transformers", "lancedb", "mflux"],
        "test_binaries": [
            os.path.join(_BASE_DIR, ".venv", "bin", "mflux-generate-z-image-turbo"),
            os.path.join(_BASE_DIR, ".venv", "bin", "mflux-upscale-seedvr2"),
        ],
        "repair_cmd": f"cd '{_BASE_DIR}' && bash repair_venv.sh",
    },
    "ace_step": {
        "venv": os.path.join(_BASE_DIR, "ACE-Step", ".venv"),
        "python": os.path.join(_BASE_DIR, "ACE-Step", ".venv", "bin", "python"),
        "test_imports": ["torch", "torchaudio", "transformers", "diffusers", "acestep"],
        "test_binaries": [],
        "repair_cmd": (
            f"cd '{_BASE_DIR}/ACE-Step' && rm -rf .venv && uv venv --python 3.12 .venv && "
            f"uv pip install 'torch>=2.9.1' 'torchaudio>=2.9.1' torchvision 'safetensors==0.7.0' "
            f"'transformers>=4.51.0,<4.58.0' diffusers 'gradio==6.2.0' 'matplotlib>=3.7.5' "
            f"'scipy>=1.10.1' 'soundfile>=0.13.1' 'loguru>=0.7.3' 'einops>=0.8.1' "
            f"'accelerate>=1.12.0' 'fastapi>=0.110.0' 'uvicorn[standard]>=0.27.0' "
            f"'numba>=0.63.1' 'vector-quantize-pytorch>=1.27.15' toml modelscope xxhash "
            f"'peft>=0.18.0' lycoris-lora 'lightning>=2.0.0' 'tensorboard>=2.0.0' "
            f"'mlx>=0.25.2' 'mlx-lm>=0.20.0' && uv pip install -e . && "
            f"bash '{_BASE_DIR}/protect_venvs.sh'"
        ),
    },
}

# Protected directories (models, weights, etc.)
PROTECTED_DIRS = [
    os.path.join(_BASE_DIR, ".venv"),
    os.path.join(_BASE_DIR, "ACE-Step", ".venv"),
    os.path.join(_BASE_DIR, "mlx_models"),
    os.path.join(_BASE_DIR, "ACE-Step", "checkpoints"),
]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(level: str, msg: str, *, to_stdout: bool = True):
    """Log to file and optionally stdout."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    if to_stdout:
        prefix = {"OK": "✅", "WARN": "⚠️", "ERROR": "❌", "INFO": "ℹ️", "FIX": "🔧"}.get(level, "•")
        print(f"  {prefix} {msg}")
    try:
        with open(_LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# APFS Compression Detection
# ---------------------------------------------------------------------------
def check_file_compressed(filepath: str) -> bool:
    """Check if a file has APFS compression (com.apple.decmpfs xattr)."""
    try:
        result = subprocess.run(
            ["xattr", "-l", filepath],
            capture_output=True, text=True, timeout=5,
        )
        return "com.apple.decmpfs" in result.stdout
    except Exception:
        return False


def find_compressed_so_files(venv_path: str) -> list[str]:
    """Find .so/.dylib files in a venv that have APFS compression."""
    compressed = []
    patterns = [
        os.path.join(venv_path, "**", "*.so"),
        os.path.join(venv_path, "**", "*.dylib"),
    ]
    for pattern in patterns:
        for filepath in glob.iglob(pattern, recursive=True):
            if check_file_compressed(filepath):
                compressed.append(filepath)
    return compressed


# ---------------------------------------------------------------------------
# Protection: Prevent APFS compression
# ---------------------------------------------------------------------------
def protect_directory(dirpath: str) -> dict:
    """Apply APFS compression protection to a directory.

    Returns dict with results of each protection step.
    """
    results = {"path": dirpath, "exists": os.path.isdir(dirpath), "actions": []}

    if not results["exists"]:
        return results

    # 1. Spotlight exclusion — prevents indexer from touching files
    marker = os.path.join(dirpath, ".metadata_never_index")
    try:
        if not os.path.exists(marker):
            with open(marker, "w") as f:
                f.write("# Prevent Spotlight indexing — protects venv from APFS corruption\n")
            results["actions"].append("spotlight_exclusion: created .metadata_never_index")
        else:
            results["actions"].append("spotlight_exclusion: already exists")
    except Exception as e:
        results["actions"].append(f"spotlight_exclusion: FAILED ({e})")

    # 2. nocompressed flag (may need sudo for some files)
    try:
        r = subprocess.run(
            ["chflags", "-R", "nocompressed", dirpath],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            results["actions"].append("chflags_nocompressed: OK")
        else:
            results["actions"].append(f"chflags_nocompressed: partial ({r.stderr.strip()[:100]})")
    except Exception as e:
        results["actions"].append(f"chflags_nocompressed: FAILED ({e})")

    # 3. Remove any existing com.apple.decmpfs xattrs from .so/.dylib files
    decompressed = 0
    for pattern in ["**/*.so", "**/*.dylib"]:
        for filepath in glob.iglob(os.path.join(dirpath, pattern), recursive=True):
            try:
                r = subprocess.run(
                    ["xattr", "-d", "com.apple.decmpfs", filepath],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0:
                    decompressed += 1
            except Exception:
                pass
    if decompressed:
        results["actions"].append(f"decompressed_files: {decompressed} .so/.dylib files fixed")
    else:
        results["actions"].append("decompressed_files: none needed")

    return results


def protect_all():
    """Apply APFS protection to ALL Ailey-managed directories."""
    print("\n🛡️  APFS Kompressionsschutz für Ailey …")
    all_results = []
    for dirpath in PROTECTED_DIRS:
        if os.path.isdir(dirpath):
            _log("FIX", f"Schütze: {os.path.relpath(dirpath, _BASE_DIR)}")
            result = protect_directory(dirpath)
            all_results.append(result)
            for action in result["actions"]:
                _log("INFO", f"  → {action}", to_stdout=True)
        else:
            _log("INFO", f"Überspringe (nicht vorhanden): {os.path.relpath(dirpath, _BASE_DIR)}")
    return all_results


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------
def check_python_binary(python_path: str) -> dict:
    """Check if a Python binary is functional."""
    result = {"path": python_path, "exists": False, "runs": False, "version": None}

    if not os.path.isfile(python_path):
        return result
    result["exists"] = True

    try:
        r = subprocess.run(
            [python_path, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            result["runs"] = True
            result["version"] = r.stdout.strip()
        elif r.returncode == 138:  # Bus error
            result["error"] = "BUS_ERROR (APFS corruption)"
        elif r.returncode == 137:  # Killed
            result["error"] = "KILLED (OOM or corrupted)"
        else:
            result["error"] = f"exit_code={r.returncode}"
    except subprocess.TimeoutExpired:
        result["error"] = "TIMEOUT (possible deadlock)"
    except Exception as e:
        result["error"] = str(e)

    return result


def check_import(python_path: str, module: str, timeout: int = 15) -> dict:
    """Test if a Python module can be imported without crashing."""
    result = {"module": module, "ok": False}

    try:
        r = subprocess.run(
            [python_path, "-c", f"import {module}; print('OK')"],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "TOKENIZERS_PARALLELISM": "false"},
        )
        if r.returncode == 0 and "OK" in r.stdout:
            result["ok"] = True
        elif r.returncode == 138:
            result["error"] = "BUS_ERROR — C-Extension korrupt (APFS)"
            result["apfs_likely"] = True
        elif r.returncode == 137:
            result["error"] = "KILLED — Speicher oder Binary korrupt"
            result["apfs_likely"] = True
        else:
            stderr_short = (r.stderr or "")[:200].strip()
            result["error"] = f"exit={r.returncode}: {stderr_short}"
    except subprocess.TimeoutExpired:
        result["error"] = f"TIMEOUT nach {timeout}s — Import hängt (APFS oder Deadlock)"
        result["apfs_likely"] = True
    except Exception as e:
        result["error"] = str(e)

    return result


def check_binary(binary_path: str) -> dict:
    """Check if a binary tool is functional."""
    result = {"path": binary_path, "exists": False, "runs": False}

    if not os.path.isfile(binary_path):
        return result
    result["exists"] = True

    try:
        r = subprocess.run(
            [binary_path, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        result["runs"] = r.returncode == 0
        if not result["runs"]:
            if r.returncode == 138:
                result["error"] = "BUS_ERROR — Binary korrupt (APFS)"
            else:
                result["error"] = f"exit={r.returncode}"
    except subprocess.TimeoutExpired:
        result["error"] = "TIMEOUT"
    except Exception as e:
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Full Health Check
# ---------------------------------------------------------------------------
def health_check_all(verbose: bool = True) -> dict:
    """Run full health check on all Ailey environments.

    Returns dict with results per environment + overall status.
    """
    report = {"timestamp": datetime.now().isoformat(), "environments": {}, "healthy": True}

    for env_name, env_cfg in ENVIRONMENTS.items():
        if verbose:
            print(f"\n🔍 Prüfe {env_name} …")

        env_report = {"healthy": True, "issues": []}

        # 1. Check Python binary
        py_check = check_python_binary(env_cfg["python"])
        if not py_check.get("runs"):
            env_report["healthy"] = False
            error = py_check.get("error", "Binary nicht gefunden")
            env_report["issues"].append(f"Python binary kaputt: {error}")
            _log("ERROR", f"{env_name}: Python binary kaputt — {error}")
            if py_check.get("error", "").startswith("BUS_ERROR"):
                env_report["issues"].append(f"→ APFS-Kompression hat das venv zerstört!")
                env_report["issues"].append(f"→ Reparatur: {env_cfg['repair_cmd']}")
        else:
            _log("OK", f"{env_name}: Python {py_check['version']}")

        # 2. Check imports (only if Python binary works)
        if py_check.get("runs"):
            for module in env_cfg["test_imports"]:
                imp_check = check_import(env_cfg["python"], module)
                if not imp_check["ok"]:
                    env_report["healthy"] = False
                    error = imp_check.get("error", "Import fehlgeschlagen")
                    env_report["issues"].append(f"Import '{module}' kaputt: {error}")
                    _log("ERROR", f"{env_name}: import {module} — {error}")
                    if imp_check.get("apfs_likely"):
                        env_report["issues"].append(
                            f"→ Wahrscheinlich APFS-Schaden! Reparatur: {env_cfg['repair_cmd']}"
                        )
                else:
                    _log("OK", f"{env_name}: import {module}")

        # 3. Check binaries
        for bin_path in env_cfg.get("test_binaries", []):
            bin_check = check_binary(bin_path)
            bin_name = os.path.basename(bin_path)
            if not bin_check.get("runs"):
                env_report["healthy"] = False
                error = bin_check.get("error", "nicht gefunden")
                env_report["issues"].append(f"Binary '{bin_name}' kaputt: {error}")
                _log("ERROR", f"{env_name}: {bin_name} — {error}")
            else:
                _log("OK", f"{env_name}: {bin_name}")

        if not env_report["healthy"]:
            report["healthy"] = False

        report["environments"][env_name] = env_report

    # Save report
    report_path = os.path.join(_BASE_DIR, "venv_doctor_report.json")
    try:
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return report


# ---------------------------------------------------------------------------
# Diagnose Subprocess Failure — called by music_generator / image_generator
# ---------------------------------------------------------------------------
def diagnose_subprocess_failure(
    env_name: str,
    returncode: int,
    stderr: str = "",
    command: str = "",
) -> str:
    """Analyze a subprocess failure and return diagnostic message.

    Called when ACE-Step, mflux-generate, or mflux-upscale-seedvr2 fails.
    Checks if the problem is an APFS-corrupted venv/binary.

    Returns human-readable diagnosis string (also logged to venv_doctor.log).
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    diagnosis_lines = [
        f"═══ Venv Doctor Diagnosis — {ts} ═══",
        f"  Environment: {env_name}",
        f"  Command: {command[:200]}",
        f"  Exit Code: {returncode}",
    ]

    is_apfs = False

    # Detect APFS corruption signals
    if returncode == 138:  # SIGBUS (10)
        is_apfs = True
        diagnosis_lines.append("  🔴 BUS ERROR (Signal 10) — C-Extension korrupt!")
        diagnosis_lines.append("  → Ursache: macOS APFS-Kompression hat .so/.dylib Dateien zerstört")
    elif returncode == 137:  # SIGKILL (9)
        diagnosis_lines.append("  🟡 KILLED (Signal 9) — OOM oder korrupt")
        diagnosis_lines.append("  → Mögliche Ursache: APFS-Kompression oder Speichermangel")
    elif returncode == 139:  # SIGSEGV (11)
        is_apfs = True
        diagnosis_lines.append("  🔴 SEGFAULT (Signal 11) — Speicherzugriffsfehler!")
        diagnosis_lines.append("  → Ursache: Korrupte Shared Library (.so/.dylib)")

    # Check stderr for known patterns
    stderr_lower = stderr.lower()
    if "bus error" in stderr_lower:
        is_apfs = True
        diagnosis_lines.append("  → stderr bestätigt: Bus Error")
    if "illegal instruction" in stderr_lower:
        is_apfs = True
        diagnosis_lines.append("  → stderr: Illegal Instruction — Binary für falsche Architektur oder korrupt")
    if "killed" in stderr_lower and "oom" not in stderr_lower:
        diagnosis_lines.append("  → stderr: Process killed")

    # If APFS corruption detected, run targeted checks
    if is_apfs and env_name in ENVIRONMENTS:
        env_cfg = ENVIRONMENTS[env_name]
        diagnosis_lines.append("")
        diagnosis_lines.append("  🔍 Starte venv-Diagnose …")

        # Check Python binary
        py_check = check_python_binary(env_cfg["python"])
        if not py_check.get("runs"):
            diagnosis_lines.append(f"  ❌ Python binary kaputt: {py_check.get('error', 'N/A')}")
        else:
            diagnosis_lines.append(f"  ✅ Python binary OK: {py_check.get('version')}")

        # Check critical imports
        for module in env_cfg["test_imports"][:3]:  # first 3 to keep it fast
            imp = check_import(env_cfg["python"], module, timeout=10)
            if not imp["ok"]:
                diagnosis_lines.append(f"  ❌ import {module}: {imp.get('error', 'FAIL')}")
            else:
                diagnosis_lines.append(f"  ✅ import {module}: OK")

        # Check for compressed .so files
        venv_path = env_cfg["venv"]
        if os.path.isdir(venv_path):
            compressed = find_compressed_so_files(venv_path)
            if compressed:
                diagnosis_lines.append(f"  🔴 {len(compressed)} komprimierte .so-Dateien gefunden!")
                for cf in compressed[:5]:
                    diagnosis_lines.append(f"     → {os.path.relpath(cf, _BASE_DIR)}")
                if len(compressed) > 5:
                    diagnosis_lines.append(f"     → … und {len(compressed) - 5} weitere")

        diagnosis_lines.append("")
        diagnosis_lines.append(f"  🔧 REPARATUR:")
        diagnosis_lines.append(f"     {env_cfg['repair_cmd']}")

    diagnosis = "\n".join(diagnosis_lines)

    # Log to file
    _log("ERROR", f"Subprocess-Fehler diagnostiziert für {env_name}", to_stdout=False)
    try:
        with open(_LOG_FILE, "a") as f:
            f.write("\n" + diagnosis + "\n\n")
    except Exception:
        pass

    # Also print to stdout for the API log
    print(f"\n[VenvDoctor] Diagnose für {env_name}:")
    print(diagnosis)

    return diagnosis


# ---------------------------------------------------------------------------
# Quick Startup Check (lightweight, < 2s for healthy systems)
# ---------------------------------------------------------------------------
def quick_startup_check() -> tuple[bool, list[str]]:
    """Fast check at API startup — only tests Python binaries and critical imports.

    Returns (all_ok, list_of_issues).
    Doesn't block startup on failure, just logs warnings.
    """
    issues = []

    for env_name, env_cfg in ENVIRONMENTS.items():
        venv_path = env_cfg["venv"]
        if not os.path.isdir(venv_path):
            # Environment not installed — not an error, just skip
            continue

        python_path = env_cfg["python"]
        if not os.path.isfile(python_path):
            issues.append(f"{env_name}: Python binary fehlt ({python_path})")
            continue

        # Quick binary test — just "python -c pass"
        try:
            r = subprocess.run(
                [python_path, "-c", "pass"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                code_desc = {138: "BUS_ERROR/APFS", 137: "KILLED", 139: "SEGFAULT"}.get(
                    r.returncode, f"exit={r.returncode}"
                )
                issues.append(f"{env_name}: Python binary defekt ({code_desc}) — venv neu aufbauen!")
        except subprocess.TimeoutExpired:
            issues.append(f"{env_name}: Python binary hängt — venv wahrscheinlich korrupt!")
        except Exception as e:
            issues.append(f"{env_name}: Python binary Fehler: {e}")

    return (len(issues) == 0, issues)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Run full diagnostics from command line."""
    import argparse
    parser = argparse.ArgumentParser(description="Ailey Venv Doctor — Diagnose & Schutz")
    parser.add_argument("--check", action="store_true", help="Voller Health-Check aller Environments")
    parser.add_argument("--protect", action="store_true", help="APFS-Schutz auf alle Verzeichnisse anwenden")
    parser.add_argument("--quick", action="store_true", help="Schneller Startup-Check")
    parser.add_argument("--all", action="store_true", help="Alles: Check + Protect")
    args = parser.parse_args()

    if not any([args.check, args.protect, args.quick, args.all]):
        args.all = True  # Default: everything

    print("╔══════════════════════════════════════════════╗")
    print("║     🩺 Ailey Venv Doctor                     ║")
    print("╚══════════════════════════════════════════════╝")

    if args.all or args.protect:
        protect_all()

    if args.all or args.check:
        report = health_check_all(verbose=True)
        print("\n" + "─" * 50)
        if report["healthy"]:
            print("✅ Alle Environments sind gesund!")
        else:
            print("❌ Probleme gefunden:")
            for env_name, env_report in report["environments"].items():
                if not env_report["healthy"]:
                    print(f"\n  🔴 {env_name}:")
                    for issue in env_report["issues"]:
                        print(f"     {issue}")
            print(f"\n  📋 Vollständiger Report: {os.path.join(_BASE_DIR, 'venv_doctor_report.json')}")

    if args.quick:
        ok, issues = quick_startup_check()
        if ok:
            print("✅ Quick-Check: Alle Environments OK")
        else:
            print("⚠️  Quick-Check Probleme:")
            for issue in issues:
                print(f"  ❌ {issue}")

    print(f"\n📋 Log: {_LOG_FILE}")


if __name__ == "__main__":
    main()
