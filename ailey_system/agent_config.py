"""Central agent-mode configuration.

This module exposes two values used throughout the codebase:
- AGENT_MODE: enable extended timeouts and relaxed limits when True
- AGENT_TIMEOUT: timeout in seconds to use in agent mode (default 1800 = 30min)

Both can be controlled via environment variables:
  AILEY_AGENT_MODE (1/0, true/false)
  AILEY_AGENT_TIMEOUT (integer seconds)
"""
from __future__ import annotations
import os
import subprocess
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


AGENT_MODE = _env_bool("AILEY_AGENT_MODE", True)
try:
    AGENT_TIMEOUT = int(os.environ.get("AILEY_AGENT_TIMEOUT", "1800"))
except Exception:
    AGENT_TIMEOUT = 1800


__all__ = ["AGENT_MODE", "AGENT_TIMEOUT"]


def run_subprocess(*popen_args, timeout: int | None = None, **popen_kwargs) -> subprocess.CompletedProcess:
    """Wrapper around subprocess.run that applies AGENT_TIMEOUT when AGENT_MODE.

    Usage: run_subprocess(["cmd", "arg"], capture_output=True, text=True, timeout=30)
    If timeout is None, the wrapper will set it to AGENT_TIMEOUT when AGENT_MODE else leave it as None.
    """
    if timeout is None:
        timeout = AGENT_TIMEOUT if AGENT_MODE else None
    return subprocess.run(*popen_args, timeout=timeout, **popen_kwargs)


def call_subprocess(*popen_args, timeout: int | None = None, **popen_kwargs) -> int:
    """Call subprocess.run and return returncode only (convenience)."""
    res = run_subprocess(*popen_args, timeout=timeout, **popen_kwargs)
    return getattr(res, "returncode", -1)

