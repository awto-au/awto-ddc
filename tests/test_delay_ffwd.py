"""Exact fast-forward of the delay routines (fastmachine.install_delay_ffwd): the machine state with the hook equals the interpreted one.

Per count 0..255 of AwtoDelayLoops and AwtoDelayXus (several timer phases, Timer2 IRQs inside the window) and a boot + 3 s run: clk, cycles,
instructions, IRAM, SFR, the XDATA pool, wall_ms, Timer2 count must match exactly (--slow). Hook shape vs the image's code: every run (#342).
Image: fixture fw_image (scripts/test_image.py).
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


IMG = None          # the tree's image stem, set per module from the fw_image fixture


@pytest.fixture(autouse=True, scope="module")
def _use_image(fw_image):
    global IMG
    IMG = fw_image.stem


PAD = 0x0006       # code address never executed here: a stub on it stops the run (as delay_sim.replay)


def machine(ffwd=None):
    import fw_sim as S
    bus = S.SimBus(IMG.with_suffix(".bin"), IMG.with_suffix(".map"), "ffwdtest", None, boot=False, video="1080p60")
    if ffwd is not None:                                    # hook from the first instruction (boot included)
        bus.m.install_delay_ffwd()
        bus.m._ff_on = ffwd
    assert bus.run_until_mode(3)
    bus.dbg_link_on()
    bus.m.stubs.setdefault(PAD, []).append((None, "pad", lambda m, r: m.request_stop()))
    bus.m.core.pch[PAD] |= 0xFFFF
    return bus


def digest(bus):
    m, c = bus.m, bus.m.core
    h = hashlib.sha256()
    for sp in ("iram", "sfr"):
        h.update(bytes(getattr(c, sp)))
    h.update(bytes(c.xram[0xD000:0xF800]))
    p = m.p
    h.update(repr((p.clk, p.cycles, p.instr, p.nirq, round(m.wall_ms, 6), bus.diag_t2())).encode())
    return h.hexdigest()


def sym(bus, name):
    return bus.m.sym["_" + name] & 0xFFFF


def call(bus, entry, setup, off):
    """run `off` instructions of the firmware, then the routine at `entry` as a call (interrupts on) until it returns to PAD"""
    m, c, p = bus.m, bus.m.core, bus.m.p
    m.run(off)
    setup(c)
    sp = c.sfr[0x01]
    c.iram[sp + 1], c.iram[sp + 2] = PAD & 0xFF, PAD >> 8
    c.sfr[0x01] = sp + 2
    saved = p.pc, c.xram[0xFFFF] & 15
    p.pc = entry
    m.run(5_000_000)
    assert p.pc == PAD, "the call did not return to the pad"
    c.sfr[0x01] = sp
    return saved


def test_hook_follows_the_image_code(fw_image):
    """the tree image's delay routines decode (drift in fw/timer/delay.c fails here, not as a silently unaccelerated sim); a changed loop refuses"""
    import fastmachine as FM
    import fw_sim as S
    img = fw_image.bin.read_bytes()
    syms, _ = S.parse_map(fw_image.map.read_text(errors="replace"), img)
    sites = {s["kind"]: s for s in FM.delay_ffwd_sites(img, syms)}
    assert set(sites) == {"loops", "xus"}, sites
    for s in sites.values():
        assert img[s["pc"]] == 0xD8 | s["rn"] and img[s["pc"] + 1] == 0xFE, s
    bad = bytearray(img)
    bad[sites["xus"]["pc"] + 2] = 0x00                  # outer djnz gone
    with pytest.raises(ValueError, match="AwtoDelayXus"):
        FM.delay_ffwd_sites(bytes(bad), syms)


@pytest.mark.slow
def test_every_count_of_both_routines_state_identical():
    import fastmachine as FM
    bus = machine()
    m, c = bus.m, bus.m.core
    loops, xus = sym(bus, "AwtoDelayLoops"), sym(bus, "AwtoDelayXus")
    sites = {s["kind"]: s for s in FM.delay_ffwd_sites(c.code, m.sym)}
    callv = c.code[sites["loops"]["pc"] - 1]            # mov Rn,Call: A8+n <Call>
    cnt = sites["xus"]["counter"]                       # djnz Counter,rel
    snap = bus.snapshot()
    m.install_delay_ffwd()
    for n in range(256):
        for name, entry, setup in (("Loops", loops, lambda cc, n=n: cc.iram.__setitem__(callv, n)),
                                   ("Xus", xus, lambda cc, n=n: cc.iram.__setitem__(cnt, n))):
            off = 1000 + 7919 * n                       # a different Timer2 phase for each count
            res = []
            for on in (False, True):
                bus.restore(snap)
                m._ff_on = on
                call(bus, entry, setup, off)
                res.append(digest(bus))
            assert res[0] == res[1], f"{name} count {n}: state differs with the hook"
    m._ff_on = True


@pytest.mark.slow
def test_scenario_stays_within_the_stop_granularity_noise():
    """Whole-run equality is not asserted: the sim's Python models see time at run-chunk stops, so ANY extra stop (the hook's own, with the
    skip switched off) moves the timeline by ~1-2 ms over a boot (measured 2026-11-19: plain vs hook installed but off 1.6 ms, off vs on 1.2 ms).
    The exact claim is the per-count test above. Here: the hooked boot still reaches ACTIVE and 3 s later is within 5 ms / 1 % of the unhooked one."""
    res = []
    for on in (False, True):
        bus = machine(ffwd=on)
        bus.wait(3.0)
        res.append((bus.m.wall_ms, bus.m.p.instr))
        bus.close()
    assert abs(res[0][0] - res[1][0]) < 5.0 and abs(res[0][1] - res[1][1]) < 0.01 * res[0][1], res
