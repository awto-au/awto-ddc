#!/usr/bin/env python3
"""Launcher: creates tools/osd_editor/.venv (uv, Python 3.13) on first run, then starts the editor."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
PY = VENV / "bin" / "python"
PY313 = Path.home() / ".local/bin/python3.13"      # default python3 is free-threaded 3.15: no PySide6 wheels


def main() -> int:
    if not PY.exists():
        subprocess.check_call(["uv", "venv", "--python", str(PY313 if PY313.exists() else "3.13"), str(VENV)])
        subprocess.check_call(["uv", "pip", "install", "--python", str(PY), "PySide6-Essentials", "numpy", "pillow"])
    os.execv(str(PY), [str(PY), str(HERE / "app.py"), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
