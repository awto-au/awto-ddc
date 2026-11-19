#!/usr/bin/env python3
"""Wait pump (awto-ddc#216 stage 2): a DDC/CI Get-VCP that lands inside a blocking delay is answered inside it; a Set waits.

usage: pump_sim.py BIN [--map MAP] [--mode 1080p60]
  Boots in fw_sim; at the first ScalerTimerDelayXms(N >= 2) after the engine is ours it injects (1) Get VCP 0x10 and (2) Set VCP 0x10 = 77, and checks:
    - the Get reply is complete and valid and its first byte came within the delay: instructions from injection to first byte <= (1 - REPLY_MARGIN) x N x measured instr/ms (docs/sim.md),
    - the Set is NOT applied before the delay ended (it runs from the main loop) and IS applied afterwards.
  --phase F sets Timer2 to F of a tick left when the request is injected. Reuses the MCCS engine model of ddc_sim.py. Exit 1 on a failed check. Log: ./tmp/logs/pump_sim.log
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import fw_sim as S

LOG = S.ROOT / "tmp/logs/pump_sim.log"
MIN_DELAY_MS = 2         # the boot path has no longer delay once the engine is ours (45 ms ones come while the SDK still parks it at 0x3D)
OUR_SLAVE = 0x6E         # AWTO_DDCCI_WR_ADDR in IIC_1_SET_SLAVE: set by the firmware's first poll
SET_VALUE = 77
REPLY_MARGIN = 0.25      # limit = (1 - margin) x N ms x measured instr/ms; fails 'X instr ... limit L' (docs/sim.md)
RATE_WINDOW_S = 0.1      # firmware time over which instr/ms is measured (+-1 tick = +-1 %)


def reply_limit(n_ms: int, instr_per_ms: float) -> float:
    return (1 - REPLY_MARGIN) * n_ms * instr_per_ms


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class StampedEngine(D.DdcEngine):
    def __init__(self):
        super().__init__()
        self.t_reply = self.i_in = self.i_reply = None
        self.snap = None
        self.bus = None

    def on_write(self, m, a):
        before = len(self.tx)
        super().on_write(m, a)
        if a == self.DOUT and before == 0 and self.t_reply is None:
            self.t_reply, self.i_reply = self.bus.now(), self.bus.m.instr
        elif a == self.IRQ2 and self.t_reply is not None and self.snap is None and self.tx and not self.m_reset(m):
            self.snap = bytes(self.tx)                  # the reply is complete when the firmware drops IRQ2 bit5 after the data

    @staticmethod
    def m_reset(m):
        return bool(m.rd(D.DdcEngine.IRQ2)[0] & 0x40)

    def arm(self):
        self.t_reply, self.i_in = None, self.bus.m.instr


def pkt(payload: bytes) -> bytes:
    p = bytes([0x51, 0x80 | len(payload)]) + payload
    chk = 0x6E
    for b in p:
        chk ^= b
    return p + bytes([chk])


def reply_check(instr: int, n_ms: int, instr_per_ms: float):
    lim = reply_limit(n_ms, instr_per_ms)
    return instr <= lim, f"{instr} instr from request to first reply byte, limit {lim:.0f} ({1 - REPLY_MARGIN:.2f} x {n_ms} ms x {instr_per_ms:.0f} instr/ms)"


def run(binp: Path, mapp: Path, mode: str = "1080p60", phase: float = 0.0, extra_instr: int = 0) -> dict:
    """One boot + Get/Set. phase: 0..1, fraction of a Timer2 period left to the next tick when the request is injected (0 = leave as is). extra_instr: added to the counted path (test hook).
    Returns n, instr, ipm, t_in, t_reply (tick stamps, for comparison only), reply, set_val."""
    eng = StampedEngine()
    bus = S.SimBus(binp, mapp, devs=[eng], video=mode, boot=False)
    eng.bus = bus
    d = D.Mccs(bus, eng)
    got = {}

    def on_delay(m, r):
        n = r["a1"] & 0xFFFF
        sl = m.rd(eng.SLAVE)[0]
        got["parked"] = got.get("parked", False) or sl != OUR_SLAVE        # the SDK parks IIC_1 at 0x3D before our first poll takes it
        if n >= MIN_DELAY_MS and got["parked"] and sl == OUR_SLAVE and "t_in" not in got:
            got.update(t_in=bus.now(), n=n)
            if phase:
                lo, hi = m.rd(0xCA, 2, "sfr")                      # RCAP2: counts per tick = 0x10000 - reload
                left = max(1, round(phase * (0x10000 - (hi << 8 | lo))))
                m.wr(0xCC, bytes([(0x10000 - left) & 0xFF, (0x10000 - left) >> 8]), "sfr")      # TL2 TH2
            eng.arm()
            eng.request(m, pkt(bytes([0x01, 0x10])))

    bus.m.stub("ScalerTimerDelayXms", on_delay)
    try:
        bus.boot()
        if "t_in" not in got:
            return {}
        i0, t0 = bus.m.instr, bus._t2()
        bus.wait(RATE_WINDOW_S)
        t1 = bus._t2()
        res = dict(got, instr=(eng.i_reply or 0) - eng.i_in + extra_instr, t_reply=eng.t_reply, reply=eng.snap or b"",
                   ipm=(bus.m.instr - i0) / (t1 - t0))
        d.set(0x10, SET_VALUE)
        g = d.get(0x10)
        res["set_val"] = g["cur"] if g else None
        return res
    finally:
        bus.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--phase", type=float, default=0.0, help="0..1: fraction of a Timer2 tick left at injection (default: as the firmware runs)")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    fails = 0

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    r = run(a.bin, a.map, a.mode, a.phase)
    check("a delay of >= 2 ms with the engine ours was reached", "t_in" in r, "none in the boot path" if "t_in" not in r else f"{r['n']} ms at {r['t_in'] * 1000:.0f} ms")
    if r:
        fr = r["reply"]
        chk = 0x50
        for b in fr[:-1]:
            chk ^= b
        ok = len(fr) >= 11 and fr[0] == 0x6E and fr[2] == 0x02 and fr[4] == 0x10 and chk == fr[-1]
        check("Get VCP 0x10 answered, valid frame", ok, fr.hex())
        ok, det = reply_check(r["instr"], r["n"], r["ipm"])
        check("... first byte inside the delay (instruction budget)", ok, det)
        check("Set VCP 0x10 applied by the main loop", r["set_val"] == SET_VALUE, str(r["set_val"]))
    else:
        fails += 1
    say(f"pump_sim {a.bin.name}: {'PASS' if not fails else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
