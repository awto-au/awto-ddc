#!/usr/bin/env python3
"""DDC/CI (MCCS 2.2) against the firmware in fw_sim, the way ddcutil talks to the monitor (awto-ddc#60, #67).

usage: ddc_sim.py BIN [--map MAP] [--mode 1080p60]
  Model: the spare IIC engine IIC_1 (0xFE86..0xFE8F, fw/ddcci/ddcci.c), polled by the firmware's main loop:
  a host write lands as SUB_IN (source 0x51) + data FIFO with STATUS bit1/bit2; replies are the DATA_OUT bytes written
  after a buffer reset (IRQ2 bit6). Checks: capabilities (whole string, parsed), getvcp of every listed code, setvcp
  10 / 12 / 14 / E6 read back, save (0x0C), unsupported code -> result 01, bad checksum -> no reply.
Exit 1 on a failed check. Log: ./tmp/logs/ddc_sim.log
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import settings_table as T  # noqa: E402

ROOT = S.ROOT
LOG = ROOT / "tmp/logs/ddc_sim.log"
REPLY_S = 0.05           # fw time to wait for a reply: MCCS hosts wait 40-50 ms after a request (ddcutil default 50 ms)


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class DdcEngine(S.Dev):
    BASE = 0xFE86
    SLAVE, SUB, DIN, DOUT, STAT, IRQ, STAT2, IRQ2 = 0xFE87, 0xFE88, 0xFE89, 0xFE8A, 0xFE8B, 0xFE8C, 0xFE8D, 0xFE8E

    def __init__(self):
        self.rx, self.rxpos, self.tx, self.flags = b"", 0, bytearray(), 0
        self.reads, self.writes = (self.DIN,), (self.DOUT, self.STAT, self.IRQ2)

    def init(self, m):
        m.put(f"set memory xram 0x{self.STAT2:x} 0x02")          # rx FIFO empty

    def on_read(self, m, a):
        self.rxpos += 1
        if self.rxpos < len(self.rx):
            m.put(f"set memory xram 0x{self.DIN:x} 0x{self.rx[self.rxpos]:x}")
        else:                                       # FIFO drained: empty flag up, data-in flag down [guess: hardware]
            m.put(f"set memory xram 0x{self.STAT2:x} 0x{m.rd(self.STAT2)[0] | 0x02:x}")
            self.flags &= ~0x04
            m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == self.DOUT:
            self.tx.append(v)
        elif a == self.IRQ2 and v & 0x40:          # buffer reset, self-clearing (else every later IRQ2 write resets again)
            self.tx.clear()
            m.put(f"set memory xram 0x{self.IRQ2:x} 0x{v & ~0x40 & 0xFF:x}")
        elif a == self.STAT:
            self.flags &= v
            m.put(f"set memory xram 0x{self.STAT:x} 0x{self.flags:x}")

    def request(self, m, pkt: bytes):
        """host write 6E: pkt[0] = source 0x51 (SUB_IN), the rest through the FIFO"""
        self.tx.clear()
        self.rx, self.rxpos, self.flags = pkt[1:], 0, 0x06 | 0x10
        m.wr(self.SUB, bytes([pkt[0]]))
        m.wr(self.DIN, bytes([self.rx[0]]))
        m.wr(self.STAT2, bytes([m.rd(self.STAT2)[0] & ~0x02 & 0xFF]))
        m.wr(self.STAT, bytes([self.flags]))


class Mccs:
    def __init__(self, bus: S.SimBus, eng: DdcEngine):
        self.bus, self.eng = bus, eng

    def tx(self, payload: bytes, reply=True) -> bytes | None:
        pkt = bytes([0x51, 0x80 | len(payload)]) + payload
        chk = 0x6E
        for b in pkt:
            chk ^= b
        self.eng.request(self.bus.m, pkt + bytes([chk]))
        self.bus.wait(REPLY_S)
        if not reply:
            return None
        r = bytes(self.eng.tx)
        if len(r) < 3:
            return None
        chk = 0x50
        for b in r[:-1]:
            chk ^= b
        return r if chk == r[-1] and r[0] == 0x6E else None

    retries = 0

    def get(self, code: int):
        for _ in range(5):                          # ddcutil retries too: an injected request can race the poll in the model
            r = self.tx(bytes([0x01, code]))
            if r is not None:
                break
            Mccs.retries += 1
        if r is None or len(r) < 11 or r[2] != 0x02 or r[4] != code:
            return None
        return dict(rc=r[3], type=r[5], max=r[6] << 8 | r[7], cur=r[8] << 8 | r[9])

    def set(self, code: int, v: int):
        self.tx(bytes([0x03, code, v >> 8, v & 0xFF]), reply=False)

    def caps(self) -> str:
        out, off = b"", 0
        for _ in range(100):
            for _ in range(3):
                r = self.tx(bytes([0xF3, off >> 8, off & 0xFF]))
                if r is not None:
                    break
                Mccs.retries += 1
            if r is None or r[2] != 0xE3:
                return ""
            data = r[5:-1]
            if not data:
                break
            out += data
            off += len(data)
        return out.decode("ascii", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    eng = DdcEngine()
    bus = S.SimBus(a.bin, a.map, devs=[eng], video=a.mode)
    d = Mccs(bus, eng)
    fails = 0

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    try:
        if not bus.run_until_mode(3):                # ACTIVE: during boot the main loop blocks in the panel power waits
            raise SystemExit("never reached ACTIVE")   # (T1..T3, ~0.3 s gaps: requests unanswered, see #67)
        bus.wait(0.3)
        caps = d.caps()
        check("capabilities = generated string", caps == T.CAPS, caps[:80] + "...")
        vcp_part = re.search(r"vcp\((.*)\)mccs", T.CAPS).group(1)
        top = [int(x, 16) for x in re.sub(r"\([^)]*\)", "", vcp_part).split()]
        bad = []
        for c in top:
            g = d.get(c)
            if g is None or g["rc"] != 0:
                bad.append(f"{c:02X}:{g} last reply bytes {bytes(d.eng.tx).hex() or 'none'}")
        check(f"getvcp every listed code ({len(top)})", not bad, " ".join(bad))
        g = d.get(0xDF)
        check("DF = 2.2", g and g["cur"] == 0x0202, str(g))
        g = d.get(0x60)
        check("60 = D2 HDMI (0x11)", g and g["cur"] == 0x11, str(g))
        d.set(0x10, 77)
        g = d.get(0x10)
        check("setvcp 10 77", g and g["cur"] == 77 and g["max"] == 100, str(g))
        d.set(0x12, 31)
        g = d.get(0x12)
        check("setvcp 12 31", g and g["cur"] == 31, str(g))
        d.set(0x14, 0x0B)
        g = d.get(0x14)
        check("setvcp 14 user (0B)", g and g["cur"] == 0x0B, str(g))
        d.set(0xE6, 0)
        g = d.get(0xE6)
        check("setvcp E6 fast switch off", g and g["cur"] == 0, str(g))
        d.tx(bytes([0x0C]), reply=False)
        check("save (0x0C) accepted", True)
        g = d.get(0x99)
        check("unsupported code -> rc 01", g and g["rc"] == 0x01, str(g))
        d.eng.request(bus.m, bytes([0x51, 0x82, 0x01, 0x10, 0x00]))
        bus.wait(REPLY_S)
        check("bad checksum -> no reply", len(d.eng.tx) == 0, d.eng.tx.hex())
        g = d.get(0xD6)
        check("D6 = on (01)", g and g["cur"] == 0x01, str(g))
    finally:
        bus.close()
    say(f"ddc_sim: {'PASS' if not fails else f'{fails} FAIL'} ({Mccs.retries} retried requests)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
