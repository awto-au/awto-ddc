"""Sim-only test-timing scale (scripts/sim_time_scale.py): the patched image changes the monitor period and nothing else.

Offline, --slow. Image: $AWTO_TEST_IMAGE (stem) or the newest tmp/fw/*-be.bin that has the monitor.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sim_time_scale as TS


def _image():
    e = os.environ.get("AWTO_TEST_IMAGE")
    if e:
        return Path(e)
    for p in sorted((ROOT / "tmp/fw").glob("*-be.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
        if "_g_stAwtoMon" in p.with_suffix(".map").read_text(errors="replace") and "-clk" not in p.name:
            return p.with_suffix("")
    return None


IMG = _image()
pytestmark = [pytest.mark.slow, pytest.mark.skipif(IMG is None, reason="no image with the monitor in tmp/fw")]


def test_patch_changes_exactly_the_two_immediates():
    img = IMG.with_suffix(".bin").read_bytes()
    out, ms = TS.patch_monitor(img, IMG.with_suffix(".map").read_text(errors="replace"), 10)
    assert ms == TS.define("AWTO_MON_MS") // 10
    diff = [i for i in range(len(img)) if img[i] != out[i]]
    assert len(diff) == 2 and diff[1] - diff[0] == 3          # the lo and hi byte of one `subb a,#imm` pair


def test_patch_refuses_an_image_that_does_not_have_the_compare():
    mp = IMG.with_suffix(".map").read_text(errors="replace")
    out, _ = TS.patch_monitor(IMG.with_suffix(".bin").read_bytes(), mp, 10)
    with pytest.raises(SystemExit):                            # already patched: the period no longer matches the header
        TS.patch_monitor(out, mp, 10)


def run(scale):
    r = subprocess.run([sys.executable, str(ROOT / "scripts/mon_sim_test.py"), str(IMG.with_suffix(".bin")), str(IMG.with_suffix(".map")),
                        "--no-beat", "--scale", str(scale)], capture_output=True, text=True, env={**os.environ, "AWTO_SIM_CORE": "fast"}, timeout=300, check=False)
    checks = [re.sub(r"\d+", "#", x.split(": ", 1)[0]) for x in r.stdout.splitlines() if x.startswith(("PASS ", "FAIL "))]
    return r.returncode, checks


def test_same_checks_at_scale_1_and_10():
    rc1, c1 = run(1)
    rc10, c10 = run(10)
    assert rc1 == 0 and rc10 == 0
    assert c1[:-1] == c10[:-1] and len(c1) >= 9               # the same checks, in the same order, all PASS (the last line names the image)
