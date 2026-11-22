#!/usr/bin/env python3
"""Paced main loop, minimum sim tests (docs/main-loop-pacing.md). One named failure each, about a second of firmware time per test.

usage: loop_pacing_test.py BIN [MAP] --period MS      (BIN built with -D AWTO_LOOP_PACING=MS; period 0 = free-run default: only `keys` runs)
- headroom: ACTIVE, nothing open: passes/s, busy %, worst pass, busy hook off. Catches: pacing never engages, a pass that stays long.
- race:     a Timer0 IRQ (its ISR sets a wake bit) lands between the flag check and the IDL write (stub at AwtoLoopIdle sets TF0 before the
            IDL instruction). Catches: a lost wake sleeping longer than one Timer2 tick (1 ms).
- keys:     ADC press -> debounced mask, 3 phases from idle, ms. Catches: key sampling slower than 2 x AWTO_KEY_SAMPLE_MS + a pass at any period.
- stuck:    a stuck busy producer (AwtoLoopBusy stubbed to 1): pacing off, and the health `headroom` row says FAIL. Catches: a silent stuck hook.
- console:  the diagnostic console opened by test cmd (as `dev.py note --open-console`) and left open, log drained: pacing engages (busy hook 0 %).
            Catches: an open idle console holding the loop off (seen on unit 2: 842 passes/s, busy 94 %).
Log: tmp/logs/loop_pacing_test.log
"""
import argparse
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")
import fw_sim as S
import host_note as N
import unit_health as H

LOG = ROOT / "tmp/logs/loop_pacing_test.log"
A0, IDLE, UP_BAND = 0xFF09, 0xF8, 0x38        # ADC_A0 cell, idle value, centre of the UP band (fw/awto/inputs.tsv)
KEY_MASK_OFS = 9                              # StAwtoKey.ucMask
SAMPLE_MS = 10                                # AWTO_KEY_SAMPLE_MS
fails = 0


def say(s: str) -> None:
    _log_line(s, LOG)


def check(name: str, ok: bool, detail: str) -> None:
    global fails
    fails += 0 if ok else 1
    say(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


class Dbg:
    def __init__(self, bus):
        self.bus = bus

    def read(self, addr, n=1):
        return bytes(self.bus.m.rd(addr, n))


def head(bus, addr):
    b = bytes(bus.m.rd(addr, 12))
    return [int.from_bytes(b[2 * i:2 * i + 2], "big" if bus.be else "little") for i in range(6)]


def t_headroom(bus, addr, period):
    bus.wait(5.0)                               # the boot console closes 3 s after ACTIVE (busy hook)
    passes, sleep_pm, worst_q4, hold_pm, idles, wk = head(bus, addr)
    busy, worst = 100 - sleep_pm / 10, worst_q4 / 16
    lo = 1000 / period * 0.8
    check("headroom", passes >= lo and busy < H.HEAD_BUSY_MAX_PCT and worst < H.HEAD_WORST_MAX_MS and hold_pm == 0,
          f"{passes} passes/s (>= {lo:.0f}), busy {busy:.1f} % (< {H.HEAD_BUSY_MAX_PCT}), worst {worst:.2f} ms (< {H.HEAD_WORST_MAX_MS}), "
          f"busy hook {hold_pm / 10:.1f} %, {idles} idle exits, {wk} wake-bit passes")


def t_race(bus):
    m, p = bus.m, bus.m.p
    st = {"armed": True, "t2": None, "nidle": None, "next": None}

    def inj(m_, r):
        if st["armed"]:
            st["armed"] = False
            m_.wr(0x88, bytes([m_.rd(0x88, 1, "sfr")[0] | 0x20]), "sfr")      # TCON.TF0: the Timer0 ISR runs before the IDL instruction
            st["t2"], st["nidle"] = bus.diag()["t2"], p.nidle

    def nxt(m_, r):                              # the next pass starts: the pace loop was left
        if not st["armed"] and st["next"] is None:
            st["next"], st["nidle2"] = bus.diag()["t2"], p.nidle

    m.stub("AwtoLoopIdle", inj)
    m.stub("SysTimerHandler", nxt)
    for _ in range(100):
        bus.wait(0.001)
        if st["next"] is not None:
            break
    ok = st["next"] is not None
    dt = ((st["next"] - st["t2"]) & 0xFFFF) if ok else -1
    check("race", ok and dt <= 2, f"wake bit set before the IDL write: next pass starts {dt} Timer2 ticks later (limit 2 = one tick + the pass), "
          f"IDL entries in between {p.nidle - st['nidle'] if ok else -1}")


def t_keys(bus, kaddr, period):
    snap = bus.snapshot()
    lat = []
    for off in (0.0, 0.0033, 0.0071):           # three phases against the 10 ms sample grid
        bus.restore(snap)
        bus.wait(off)
        bus.m.wr(A0, bytes([UP_BAND]))
        t0 = bus.now()
        while bus.m.rd(kaddr + KEY_MASK_OFS, 1)[0] == 0 and bus.now() - t0 < 0.1:
            bus.wait(0.0005)
        lat.append((bus.now() - t0) * 1000)
        bus.m.wr(A0, bytes([IDLE]))
    lim = 2 * SAMPLE_MS + (period or 1)
    check("keys", max(lat) <= lim, f"press -> debounced mask {', '.join(f'{x:.1f}' for x in lat)} ms (limit {lim} = two samples + a pass)")


def t_console(bus, addr, period):
    isr = bus.m.addr("isr_g_stAwtoDiag")
    bus.m.wr(isr + N.TESTCMD_OFF, bytes([N.TC_CONSOLE]))
    bus.wait(3.1)                                # draw + log backlog (one line per pass) + two windows
    passes, sleep_pm, _worst, hold_pm, _idles, _wk = head(bus, addr)
    busy = 100 - sleep_pm / 10
    check("console", hold_pm == 0 and busy < H.HEAD_BUSY_MAX_PCT and passes >= 1000 / period * 0.8,
          f"console open and idle: {passes} passes/s, busy {busy:.1f} % (< {H.HEAD_BUSY_MAX_PCT}), busy hook {hold_pm / 10:.1f} % (must be 0)")


def t_stuck(bus, addr):
    bus.m.stub("AwtoLoopBusy", lambda m, r: {"val": 1})      # a producer that never lets go
    bus.wait(2.1)                                # two windows: the first straddles the start
    rep = H.Report()
    ok = H.check_headroom(rep, Dbg(bus), addr, bus.wait)
    h = head(bus, addr)
    check("stuck", (not ok) and h[3] > H.HEAD_HOLD_MAX_PM, f"busy producer stuck: busy hook {h[3] / 10:.1f} % of passes, health headroom row {'PASS' if ok else 'FAIL'} (must FAIL)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--period", type=int, required=True)
    ap.add_argument("--only", default="headroom,race,keys,console,stuck")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    bus = S.SimBus(a.bin, mapp, "lpt-" + a.bin.stem, None, video="1080p60")
    if not bus.run_until_mode(3):
        say(f"FAIL {a.bin.name}: never reached ACTIVE")
        return 1
    only = a.only.split(",") if a.period else ["keys"]
    head_a = bus.m.addr("g_stAwtoHead") if a.period else None
    say(f"{a.bin.name} period {a.period} ms")
    if "headroom" in only:
        t_headroom(bus, head_a, a.period)
    else:
        bus.wait(5.0)
    if "race" in only:
        t_race(bus)
    if "keys" in only:
        t_keys(bus, bus.m.addr("g_stAwtoKey"), a.period)
    if "console" in only:
        t_console(bus, head_a, a.period)
    if "stuck" in only:
        t_stuck(bus, head_a)
    say(f"{'FAIL' if fails else 'PASS'} loop_pacing_test {a.bin.name}: {fails} failed")
    bus.m.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
