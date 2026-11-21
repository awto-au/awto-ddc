"""Long-block check of AwtoDelayXus (fw/timer/delay.c): a stall injected at the tail (TH2 jumps) lands in isr_g_stAwtoDlyLong, the poll writes the sync line.

Offline, --slow. Image: $AWTO_TEST_IMAGE (stem) or the newest tmp/fw/*-be.bin whose map has _AwtoDelayLong.
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
JUMP_TICKS = 40                     # TH2 ticks added at the tail: far over expected + AWTO_DLY_SLACK_TICKS


def _image():
    e = os.environ.get("AWTO_TEST_IMAGE")
    if e:
        return Path(e)
    for p in sorted((ROOT / "tmp/fw").glob("*-be.bin"), key=lambda p: p.stat().st_mtime, reverse=True):
        if "-clk" not in p.name and "_AwtoDelayLong" in p.with_suffix(".map").read_text(errors="replace"):
            return p.with_suffix("")
    return None


IMG = _image()
pytestmark = [pytest.mark.slow, pytest.mark.skipif(IMG is None, reason="no image with AwtoDelayLong in tmp/fw")]


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
                m_.wr(TH2, bytes([(m_.rd(TH2, 1, "sfr")[0] + JUMP_TICKS) & 0xFF]), "sfr")

        m.stubs.setdefault(end, []).append((None, "probe", jump))
        m.core.pch[end] |= 0xFFFF
        m.stub("AwtoDelayLongPoll", lambda m_, r: {})         # keep the record: the sync line itself is covered by sync_log / gensync
        run.scenario()
        seen = (m.rd(rec)[0], m.rd(rec + 4)[0])
        rec_bytes = m.rd(rec, 6)
    finally:
        run.bus.close()
    assert fired, "AwtoDelayEnd never ran"
    assert seen[0] >= 1 and seen[1] >= JUMP_TICKS - 2, rec_bytes.hex()
