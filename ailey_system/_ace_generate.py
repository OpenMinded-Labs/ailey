#!/usr/bin/env python3
"""
ACE-Step Music Generation — LEGACY Subprocess Worker (v1.0)
============================================================
⚠️  THIS FILE IS NO LONGER USED BY ACE-Step v1.5.

v1.5 uses an HTTP API server (see music_generator.py):
  - Start server: uv run acestep-api --host 127.0.0.1 --port 8001
  - POST /release_task with caption + lyrics
  - Poll /query_result until complete
  - Kill server to free memory

This file is kept for reference only. The v1.0 pipeline
(ACEStepPipeline direct import) is not compatible with v1.5.
"""

import sys
import json


def main():
    print(json.dumps({
        "success": False,
        "error": "ACE-Step v1.0 subprocess worker is deprecated. "
                 "Use music_generator.py with ACE-Step v1.5 HTTP API instead.",
    }))
    sys.exit(1)


if __name__ == "__main__":
    main()
