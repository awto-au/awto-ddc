"""dev.py hardware commands refuse bad arguments BEFORE touching a bus (#48). No hardware: every case exits at validation."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1] / "dev.py"
# ddc is a thin client of the GUI app: it auto-starts one. Own socket, so the suite never restarts or uses the shared per-user
# app (gui_client.check_tree restarts an app of another tree, #358); the app is asked to quit after the module.
SOCK = Path(__file__).resolve().parents[1] / "tmp" / "run" / "test-hw-args.sock"
ENV = {**os.environ, "AWTO_GUI_SOCKET": str(SOCK)}


@pytest.fixture(scope="module", autouse=True)
def own_gui_app():
    SOCK.parent.mkdir(parents=True, exist_ok=True)
    yield
    subprocess.run([sys.executable, str(DEV), "gui", "quit"], env=ENV, capture_output=True, text=True, timeout=30, check=False)


@pytest.mark.parametrize("args", [
    ["osd", "--bogus"], ["osd"], ["osd", "nosuchaction"],
    ["poke", "zz"], ["poke"], ["poke", "--nope", "FE34=1"],
    ["dump", "--pages"], ["dump", "extra"],
    ["dbg-write", "1234"], ["dbg-read", "--nope"], ["dbg-read"],
    ["ddc", "get"], ["ddc", "bogus"],
])
def test_refused_before_hardware(args):
    r = subprocess.run([sys.executable, str(DEV), *args, "--unit", "3"], capture_output=True, text=True, timeout=30, check=False, env=ENV)
    assert r.returncode != 0
    assert "nothing done" in r.stderr + r.stdout


@pytest.mark.parametrize("args", [["scdc", "--help"], ["bench", "--help"], ["identify", "--help"], ["ddc", "list", "--help"],
                                  ["build", "--help"], ["flash", "-h"]])
def test_help_prints_usage_and_runs_nothing(args):
    """#72: --help is intercepted in main(): usage, exit 0, handler never called (build --help used to build)."""
    r = subprocess.run([sys.executable, str(DEV), *args, "--unit", "3"], capture_output=True, text=True, timeout=30, check=False, env=ENV)
    assert r.returncode == 0
    assert r.stdout.startswith(f"./dev.py {args[0]}") and "run:" not in r.stdout + r.stderr
