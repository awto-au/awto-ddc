"""con_wrap_host.py (the NORMAL conwrap gate) tests the real fw/osd/conwrap.c: it passes clean and FAILS on each injected fault."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "fw/osd/conwrap.c"

FAULTS = {
    "a clipped row (the break one cell early)": ("return ucI;", "return ucI - 1;"),
    "a break inside the text column edge (<= becomes <)": ("if(ucI <= ucTxt0)", "if(ucI < ucTxt0)"),
    "no-space case drops too many cells": ("*pucDrop = ucLen - 1;", "*pucDrop = ucLen;"),
    "a tab as the break character": ("pcRow[ucI] != ' '", "pcRow[ucI] != '\\t'"),
    "the no-space case draws one cell too few": ("        return ucLen;", "        return ucLen - 1;"),
}


def gate(src):
    return subprocess.run([sys.executable, str(ROOT / "scripts/con_wrap_host.py"), "--src", str(src)], capture_output=True, text=True, timeout=60, check=False)


def test_real_source_passes():
    r = gate(SRC)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("what", sorted(FAULTS))
def test_injected_fault_fails(tmp_path, what):
    old, new = FAULTS[what]
    text = SRC.read_text()
    assert old in text, f"fault anchor for {what!r} not in conwrap.c"
    bad = tmp_path / "conwrap.c"
    bad.write_text(text.replace(old, new, 1))
    r = gate(bad)
    assert r.returncode != 0 and "FAIL" in r.stdout, what + "\n" + r.stdout + r.stderr
