"""dev.py hardware commands refuse bad arguments BEFORE touching a bus (#48). No hardware: every case exits at validation.
ddc is a thin client of the GUI app: conftest.py gives this run its own socket and tests/fake_gui_app.py as the app (#358)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1] / "dev.py"
sys.path.insert(0, str(DEV.parent / "scripts"))
import gui_client
import i2cbus

pytestmark = pytest.mark.skipif(os.environ.get("AWTO_NO_HW") != "1", reason="needs the no-hardware run (conftest.py, not --hw)")
DEV_LIMIT_S = 30    # one dev.py run that stops at validation, plus a fake app start (~0.3 s each); 30 s = hung


def dev(*args):
    return subprocess.run([sys.executable, str(DEV), *args, "--unit", "3"], capture_output=True, text=True, timeout=DEV_LIMIT_S, check=False)


@pytest.mark.parametrize("args", [
    ["osd", "--bogus"], ["osd"], ["osd", "nosuchaction"],
    ["poke", "zz"], ["poke"], ["poke", "--nope", "FE34=1"],
    ["dump", "--pages"], ["dump", "extra"],
    ["dbg-write", "1234"], ["dbg-read", "--nope"], ["dbg-read"],
    ["ddc", "get"], ["ddc", "bogus"],
])
def test_refused_before_hardware(args):
    r = dev(*args)
    assert r.returncode != 0
    assert "nothing done" in r.stderr + r.stdout


def test_thin_client_reaches_only_the_fake_app():
    """a valid ddc read goes through the port to the fake app; no unit answers it, and the app that served it says it is the fake"""
    r = dev("ddc", "get", "0x10")
    assert r.returncode != 0 and "never reaches one" in r.stdout + r.stderr
    ping = gui_client.try_call(gui_client.socket_path(), "ping", {})
    assert ping and ping["result"].get("fake") is True


def test_bus_open_refused():
    with pytest.raises(i2cbus.NoHardware):
        i2cbus.Bus(11)


@pytest.mark.parametrize("args", [["scdc", "--help"], ["bench", "--help"], ["identify", "--help"], ["ddc", "list", "--help"],
                                  ["build", "--help"], ["flash", "-h"]])
def test_help_prints_usage_and_runs_nothing(args):
    """#72: --help is intercepted in main(): usage, exit 0, handler never called (build --help used to build)."""
    r = dev(*args)
    assert r.returncode == 0
    assert r.stdout.startswith(f"./dev.py {args[0]}") and "run:" not in r.stdout + r.stderr
