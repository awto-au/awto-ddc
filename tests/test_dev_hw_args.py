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
    ["scdc", "--help"], ["bench", "--help"], ["identify", "--help"],
    ["ddc", "get"], ["ddc", "bogus"], ["ddc", "list", "--help"],
])
def test_refused_before_hardware(args):
    r = subprocess.run([sys.executable, str(DEV), *args, "--unit", "3"], capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "nothing done" in r.stderr + r.stdout
