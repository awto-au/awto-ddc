"""SimBus.snapshot / restore (fastmachine core_snap): a restored machine runs exactly as the original did from that point.

Image: $AWTO_TEST_IMAGE (stem, no suffix) or the newest tmp/fw/*-be.bin with the monitor; skipped when absent. Offline, fast core.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")


def _image():
    e = os.environ.get("AWTO_TEST_IMAGE")
    if e:
        return Path(e)
    c = sorted((ROOT / "tmp/fw").glob("*-be.bin"), key=lambda p: p.stat().st_mtime)
    return c[-1].with_suffix("") if c else None


IMG = _image()
pytestmark = pytest.mark.skipif(IMG is None or not IMG.with_suffix(".map").exists(), reason="no image in tmp/fw")


def digest(bus):
    m = bus.m
    h = hashlib.sha256()
    for sp in ("iram", "sfr", "xram"):
        h.update(bytes(getattr(m.core, sp)))
    h.update(repr((m.p.clk, m.p.instr, round(m.wall_ms, 6), bus.diag_t2(), bus.t2_abs)).encode())
    return h.hexdigest()


def boot():
    import fw_sim as S
    bus = S.SimBus(IMG.with_suffix(".bin"), IMG.with_suffix(".map"), "snaptest", None, boot=False, video="1080p60")
    assert bus.run_until_mode(3)
    bus.dbg_link_on()
    return bus


@pytest.mark.slow
def test_restore_replays_the_same_run():
    bus = boot()
    try:
        snap = bus.snapshot()
        bus.wait(2.0)
        a = digest(bus)
        bus.restore(snap)
        bus.wait(2.0)
        b = digest(bus)
        bus.restore(snap)                      # a second restore of the same snapshot
        bus.wait(2.0)
        assert a == b == digest(bus)
    finally:
        bus.close()


@pytest.mark.slow
def test_restore_undoes_host_writes_and_keeps_stubs():
    bus = boot()
    try:
        snap = bus.snapshot()
        hits = []
        bus.m.stub("AwtoMs", lambda m, r: hits.append(1) and None)     # installed after the snapshot: survives the restore
        d0 = digest(bus)
        bus.m.wr(0xFF09, b"\x38")
        bus.wait(0.5)
        assert digest(bus) != d0
        bus.restore(snap)
        assert digest(bus) == d0, "state back at the snapshot"
        bus.wait(0.5)
        assert hits, "the stub set after the snapshot still fires"
    finally:
        bus.close()
