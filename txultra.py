#!/usr/bin/env python3
"""TxUltra entry point.

Run from the project root:

    python txultra.py

All modules are auto-discovered from ``plugins/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``core`` / ``ui`` / ``utils`` / ``plugins`` importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.app import main  # noqa: E402

if __name__ == "__main__":
    main()
