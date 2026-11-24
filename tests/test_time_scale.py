"""Sim-only test-timing scale (scripts/sim_time_scale.py): the patched image changes the monitor period and nothing else.

Offline, --slow. Image: fixture fw_image (scripts/test_image.py).
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

IMG = None          # the tree's image stem, set per module from the fw_image fixture


@pytest.fixture(autouse=True, scope="module")
def _use_image(fw_image):
    global IMG
    IMG = fw_image.stem


pytestmark = [pytest.mark.slow]


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
