#!/usr/bin/env python3
"""Wait pump (awto-ddc#216 stage 2): a DDC/CI Get-VCP that lands inside a blocking delay is answered inside it; a Set waits.

usage: pump_sim.py BIN [--map MAP] [--mode 1080p60]
  Boots in fw_sim; at the first ScalerTimerDelayXms(N >= 2) after the engine is ours it injects (1) Get VCP 0x10 and (2) Set VCP 0x10 = 77, and checks:
    - the Get reply is complete and valid and was written before the delay ended (sim time < entry + N ms),
    - the Set is NOT applied before the delay ended (it runs from the main loop) and IS applied afterwards.
  Reuses the MCCS engine model of ddc_sim.py. Exit 1 on a failed check. Log: ./tmp/logs/pump_sim.log
"""
from __future__ import annotations

import argparse
import sys
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D  # noqa: E402
import fw_sim as S  # noqa: E402

LOG = S.ROOT / "tmp/logs/pump_sim.log"
MIN_DELAY_MS = 2         # the boot path has no longer delay once the engine is ours (45 ms ones come while the SDK still parks it at 0x3D)
OUR_SLAVE = 0x6E         # AWTO_DDCCI_WR_ADDR in IIC_1_SET_SLAVE: set by the firmware's first poll
SET_VALUE = 77


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class StampedEngine(D.DdcEngine):
    def __init__(self):
        super().__init__()
        self.t_reply = None
        self.snap = None
        self.bus = None

    def on_write(self, m, a):
        before = len(self.tx)
        super().on_write(m, a)
        if a == self.DOUT and before == 0 and self.t_reply is None:
            self.t_reply = self.bus.now()
        elif a == self.IRQ2 and self.t_reply is not None and self.snap is None and self.tx and not self.m_reset(m):
            self.snap = bytes(self.tx)                  # the reply is complete when the firmware drops IRQ2 bit5 after the data

    @staticmethod
    def m_reset(m):
        return bool(m.rd(D.DdcEngine.IRQ2)[0] & 0x40)

    def arm(self):
        self.t_reply = None


def pkt(payload: bytes) -> bytes:
    p = bytes([0x51, 0x80 | len(payload)]) + payload
    chk = 0x6E
    for b in p:
        chk ^= b
    return p + bytes([chk])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    eng = StampedEngine()
    bus = S.SimBus(a.bin, a.map, devs=[eng], video=a.mode, boot=False)
    eng.bus = bus
    d = D.Mccs(bus, eng)
    fails = 0
    got = {}

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    def on_delay(m, r):
        n = r["a1"] & 0xFFFF
        sl = m.rd(eng.SLAVE)[0]
        got["parked"] = got.get("parked", False) or sl != OUR_SLAVE        # the SDK parks IIC_1 at 0x3D before our first poll takes it
        if n >= MIN_DELAY_MS and got["parked"] and sl == OUR_SLAVE and "t_in" not in got:
            got.update(t_in=bus.now(), n=n)
            eng.arm()
            eng.request(m, pkt(bytes([0x01, 0x10])))
        return None

    bus.m.stub("ScalerTimerDelayXms", on_delay)
    try:
        bus.boot()
        check("a delay of >= 2 ms with the engine ours was reached", "t_in" in got, "none in the boot path" if "t_in" not in got else f"{got['n']} ms at {got['t_in'] * 1000:.0f} ms")
        if "t_in" in got:
            t_end = got["t_in"] + got["n"] / 1000
            r = eng.snap or b""
            chk = 0x50
            for b in r[:-1]:
                chk ^= b
            ok = len(r) >= 11 and r[0] == 0x6E and r[2] == 0x02 and r[4] == 0x10 and chk == r[-1]
            check("Get VCP 0x10 answered, valid frame", ok, r.hex())
            check("... before the delay ended", eng.t_reply is not None and eng.t_reply < t_end,
                  f"reply at {(eng.t_reply or 0) * 1000:.1f} ms, delay ends {t_end * 1000:.1f} ms")
        d.set(0x10, SET_VALUE)
        g = d.get(0x10)
        check("Set VCP 0x10 applied by the main loop", g is not None and g["cur"] == SET_VALUE, str(g))
    finally:
        bus.close()
    say(f"pump_sim {a.bin.name}: {'PASS' if not fails else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
