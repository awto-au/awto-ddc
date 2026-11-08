"""dev.py hardware commands refuse bad arguments BEFORE touching a bus (#48). No hardware: every case exits at validation."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1] / "dev.py"


@pytest.mark.parametrize("args", [
    ["osd", "--bogus"], ["osd"], ["osd", "nosuchaction"],
    ["poke", "zz"], ["poke"], ["poke", "--nope", "FE34=1"],
    ["dump", "--pages"], ["dump", "extra"],
    ["dbg-write", "1234"], ["dbg-read", "--nope"], ["dbg-read"],
    ["ddc", "get"], ["ddc", "bogus"],
])
def test_refused_before_hardware(args):
    r = subprocess.run([sys.executable, str(DEV), *args, "--unit", "3", "--force"], capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "nothing done" in r.stderr + r.stdout


@pytest.mark.parametrize("args", [["scdc", "--help"], ["bench", "--help"], ["identify", "--help"], ["ddc", "list", "--help"],
                                  ["build", "--help"], ["flash", "-h"]])
def test_help_prints_usage_and_runs_nothing(args):
    """#72: --help is intercepted in main(): usage, exit 0, handler never called (build --help used to build)."""
    r = subprocess.run([sys.executable, str(DEV), *args, "--unit", "3", "--force"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert r.stdout.startswith(f"./dev.py {args[0]}") and "run:" not in r.stdout + r.stderr

