"""Delay routines (fw/timer/delay.c) and their gate (scripts/delay_sim.py F probes + site replay): the clean image passes, each injected fault FAILS.

Offline, --slow (each run ~10 s). Image: $AWTO_TEST_IMAGE (stem) or the newest tmp/fw/*-be.bin whose map has _AwtoDelayLoops.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "AWTO_SIM_CORE": "fast", "PYTHONHASHSEED": "0"}


def _image():
    e = os.environ.get("AWTO_TEST_IMAGE")
    if e:
        return Path(e)
    for p in sorted((ROOT / "tmp/fw").glob("*-be.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
        if "-clk" not in p.name and "_AwtoDelayLoops" in p.with_suffix(".map").read_text(errors="replace"):
            return p.with_suffix("")
    return None


IMG = _image()
pytestmark = [pytest.mark.slow, pytest.mark.skipif(IMG is None, reason="no image with AwtoDelayLoops in tmp/fw")]


def sym(name):
    return int(re.search(rf"^C:\s+([0-9A-F]{{8}})\s+_{name}\b", IMG.with_suffix(".map").read_text(errors="replace"), re.MULTILINE).group(1), 16)


def run_gate(binp):
    r = subprocess.run([sys.executable, str(ROOT / "scripts/delay_sim.py"), str(binp), str(IMG.with_suffix(".map")), "--tree", str(ROOT)],
                       capture_output=True, text=True, env=ENV, timeout=300, check=False)
    return r.returncode, r.stdout + r.stderr


def mutated(tmp_path, edits):
    img = bytearray(IMG.with_suffix(".bin").read_bytes())
    for off, old, new in edits:
        for bank in range(len(img) >> 16):                   # the common area is copied into every bank's 64 KiB slice
            o = (bank << 16) + off
            assert bytes(img[o:o + len(old)]) == old, f"anchor at 0x{o:x}: {bytes(img[o:o + len(old)]).hex()} != {old.hex()}"
            img[o:o + len(new)] = new
    b = tmp_path / "mut-be.bin"
    b.write_bytes(img)
    return b


def test_clean_image_passes():
    rc, out = run_gate(IMG.with_suffix(".bin"))
    assert rc == 0, out[-1200:]


def dsym(name):
    return int(re.search(rf"^\s+([0-9A-F]{{8}})\s+_{name}\s", IMG.with_suffix(".map").read_text(errors="replace"), re.MULTILINE).group(1), 16)


def test_loop_removed_from_delay_loops_fails(tmp_path):
    a = sym("AwtoDelayLoops")
    rc, out = run_gate(mutated(tmp_path, [(a + 4, bytes.fromhex("dffe"), b"\x00\x00")]))        # djnz R7 -> 2 nops: no wait
    assert rc != 0 and "FAIL" in out, out[-800:]


def test_outer_loop_removed_from_delay_xus_fails(tmp_path):
    a = sym("AwtoDelayXus")
    rc, out = run_gate(mutated(tmp_path, [(a + 17, bytes.fromhex("d506f9"), b"\x00\x00\x00")]))   # outer djnz R6 -> 3 nops: one pass only
    assert rc != 0 and "FAIL" in out, out[-800:]


def test_wrong_base_count_in_delay_xus_fails(tmp_path):
    a = sym("AwtoDelayXus")
    good, wrong = dsym("d_isr_g_ucDelayXusN_Base"), dsym("d_g_ucDelay5usN_Base")
    rc, out = run_gate(mutated(tmp_path, [(a + 13, bytes([0xAF, good]), bytes([0xAF, wrong]))]))     # reads the 5 us count (146) not the 4 us one (116): +26 %
    assert rc != 0 and "FAIL" in out, out[-800:]
