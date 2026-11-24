"""Long-block check of AwtoDelayXus (fw/timer/delay.c): a stall injected at the tail (TH2 jumps) lands in isr_g_stAwtoDlyLong, the poll writes the sync line.

Offline, --slow. Image: fixture fw_image (scripts/test_image.py).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")

TH2 = 0xCD
START_TH2, JUMP_TICKS = 0x90, 40   # TH2 at entry and the elapsed ticks injected: no Timer2 reload inside, far over expected + AWTO_DLY_SLACK_TICKS


IMG = None          # the tree's image stem, set per module from the fw_image fixture


@pytest.fixture(autouse=True, scope="module")
def _use_image(fw_image):
    global IMG
    IMG = fw_image.stem


pytestmark = [pytest.mark.slow]


def test_injected_stall_is_recorded():
    import argparse

    import panel_sim as P
    mapp = IMG.with_suffix(".map")
    end = int(re.search(r"^C:\s+([0-9A-F]{8})\s+_AwtoDelayEnd\b", mapp.read_text(errors="replace"), re.MULTILINE).group(1), 16) & 0xFFFF
    run = P.Run(argparse.Namespace(bin=IMG.with_suffix(".bin"), map=mapp, mode="1080p60", report=False, tree=ROOT))
    try:
        m = run.m
        rec = m.addr("isr_g_stAwtoDlyLong")
        fired = []

        def jump(m_, r):
            if not fired:
                fired.append(1)
                m_.wr(0xE0, bytes([START_TH2]), "sfr")                 # ACC = TH2 at entry, R7 = expected ticks: a clean no-wrap case
                m_.wr(7, bytes([0]), "iram")
                m_.wr(TH2, bytes([START_TH2 + JUMP_TICKS]), "sfr")

        m.stubs.setdefault(end, []).append((None, "probe", jump))
        m.core.pch[end] |= 0xFFFF
        m.stub("AwtoDelayLongPoll", lambda m_, r: {})         # keep the record: the sync line itself is covered by sync_log / gensync
        run.scenario()
        seen = (m.rd(rec)[0], m.rd(rec + 4)[0])
        rec_bytes = m.rd(rec, 6)
    finally:
        run.bus.close()
    assert fired, "AwtoDelayEnd never ran"
    assert seen[0] >= 1 and seen[1] == JUMP_TICKS, rec_bytes.hex()
