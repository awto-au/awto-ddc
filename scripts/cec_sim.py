#!/usr/bin/env python3
"""CEC sink in the firmware sim (docs/cec.md): a minimal CEC block + bus model, frames injected like a source on the HDMI cable.

usage: cec_sim.py BIN MAP [--mode 1080p60]
  Boot to ACTIVE (HDMI D2), check the block came up (registry cec_en default 1), then send frames from a playback device
  (logical address 4) and compare the reply frames and the decoded sync-log lines (fw/awto/sync.tsv row EA, fmt cec).
- Register model [sdk-hypothesis]: names and bit meanings are from the SDK header / ScalerCec.c, none is confirmed on a unit
  (re/regmap tests C-CEC*). Page 18: B0 rx control (bit4 rx IRQ enable, bit6 reset, low nibble = initiator of the frame),
  B1 (bit7 rx EOM, bit6 rx IRQ flag w1c, 4:0 data length), B2 bit7 header EOM, D3.. rx data, B4 (bit2 tx enable, bit1 reset, 6:3 initiator),
  B5 (bit2 tx EOM, 6:3 destination), B9 length, C0.. tx data. The model completes a transmit at once with tx EOM set (acked);
  the block's real ack / error reporting (gen type 0 has no result register) is a Phase B question.
- The frame arrives as an EXINT0 (IE0) with B1 / B2 / D3.. filled; destination is not visible to the firmware (gen type 0).
Log: tmp/logs/cec_sim.log
"""
import argparse
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import sync_log as SL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/cec_sim.log"
CR0, RXCR0_1, RXCR0_2, RTCR0_RSV_1 = 0x18A0, 0x18B0, 0x18B1, 0x18B2          # P18_A0 / B0 / B1 / B2
TXCR0_1, TXCR0_2, TXDR0, TXDR1, RXDR1 = 0x18B4, 0x18B5, 0x18B9, 0x18C0, 0x18D3
IE0_BIT = 0x89                                                                  # TCON.1: external interrupt 0 flag
PLAYBACK, TV, BCAST = 4, 0, 15
SET_CEC_EN, SET_CEC_CTL = 124, 125                                              # registry ids (AwtoSetIds.h)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class CecBlock(S.Dev):
    """see the module docstring"""
    writes = (RXCR0_1, RXCR0_2, TXCR0_1, TXCR0_2)

    def __init__(self):
        self.sent = []                                  # (header, data) frames the firmware transmitted

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == RXCR0_2 and v & 0x40:                   # w1c rx IRQ flag
            m.put(f"set memory xram 0x{a:x} 0x{v & ~0x40 & 0xFF:x}")
        elif a == RXCR0_1 and v & 0x40:                 # rx reset: frame state cleared (the initiator nibble stays readable)
            m.put(f"set memory xram 0x{RXCR0_2:x} 0x0")
            m.put(f"set memory xram 0x{RTCR0_RSV_1:x} 0x0")
        elif a == TXCR0_1:
            if v & 0x02:                                # tx reset
                m.put(f"set memory xram 0x{TXCR0_2:x} 0x{m.rd(TXCR0_2)[0] & ~0x06 & 0xFF:x}")
            elif v & 0x04:                              # tx enable: send, done at once
                n = m.rd(TXDR0)[0] & 0x1F
                data = bytes(m.rd(TXDR1, n)) if n else b""
                hdr = ((v >> 3) & 0x0F) << 4 | ((m.rd(TXCR0_2)[0] >> 3) & 0x0F)
                self.sent.append((hdr, data))
                m.put(f"set memory xram 0x{TXCR0_2:x} 0x{m.rd(TXCR0_2)[0] | 0x04:x}")

    def inject(self, m, init: int, db: bytes):
        """a frame from logical address init (to the TV or a broadcast: the block does not tell which)"""
        n = len(db)
        keep = m.rd(RXCR0_1)[0] & 0xF0
        m.wr(RXCR0_1, bytes([keep | init]))
        m.wr(RXCR0_2, bytes([0xC0 | n]))                # rx EOM + rx IRQ flag + length
        m.wr(RTCR0_RSV_1, bytes([0x80]))                # header EOM
        if n:
            m.wr(RXDR1, db)
        m.put(f"set bit 0x{IE0_BIT:x} 1")
        m.flush()


# (name, initiator, data, expected reply (header, data) or None, expected log substrings)
CASES = [
    ("poll", PLAYBACK, b"", None, ["rx 4>? poll"]),
    ("give physical address", PLAYBACK, b"\x83", (0x0F, b"\x84\x00\x00\x00"), ["rx 4>? Give Physical Address", "tx 0>F Report Physical Address 00 00+"]),
    ("give device vendor id", PLAYBACK, b"\x8c", (0x0F, b"\x87\xa7\x70\xd0"), ["rx 4>? Give Device Vendor ID", "tx 0>F Device Vendor ID A7 70+"]),
    ("get cec version", PLAYBACK, b"\x9f", (0x04, b"\x9e\x05"), ["rx 4>? Get CEC Version", "tx 0>4 CEC Version 05"]),
    ("give osd name", PLAYBACK, b"\x46", (0x04, b"\x47awto-mon"), ["rx 4>? Give OSD Name", "tx 0>4 Set OSD Name 61 77+"]),
    ("give power status", PLAYBACK, b"\x8f", (0x04, b"\x90\x00"), ["rx 4>? Give Device Power Status", "tx 0>4 Report Power Status 00"]),
    ("unsupported opcode", PLAYBACK, b"\x1a", (0x04, b"\x00\x1a\x00"), ["rx 4>? op 1A", "tx 0>4 Feature Abort 1A 00"]),
    ("abort", PLAYBACK, b"\xff", (0x04, b"\x00\xff\x04"), ["rx 4>? Abort", "tx 0>4 Feature Abort FF 04"]),
    ("active source (logged, no reply)", PLAYBACK, b"\x82\x10\x00", None, ["rx 4>? Active Source 10 00"]),
    ("standby (logged, no reply)", PLAYBACK, b"\x36", None, ["rx 4>? Standby"]),
    ("image view on (logged, no reply)", PLAYBACK, b"\x04", None, ["rx 4>? Image View On"]),
    ("user control pressed (logged, no reply)", PLAYBACK, b"\x44\x41", None, ["rx 4>? User Control Pressed 41"]),
    ("feature abort in (never answered)", PLAYBACK, b"\x00\x8f\x04", None, ["rx 4>? Feature Abort 8F 04"]),
    ("vendor command broadcast opcode (no abort)", PLAYBACK, b"\x89\x01", None, ["rx 4>? op 89 01"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    say(f"cec_sim {a.bin.name}")
    cec = CecBlock()
    bus = S.SimBus(a.bin, a.map, video=a.mode, devs=[cec])
    fails = 0
    try:
        if not bus.run_until_mode(3):
            say("FAIL never reached ACTIVE")
            return 1
        st = {SET_CEC_EN: 1, SET_CEC_CTL: 0}                # registry defaults; the test flips them through the set_get stub
        bus.m.stub("set_get", lambda m_, q: {"val": st[q["a1"] & 0xFF]} if (q["a1"] & 0xFF) in st else None)
        bus.wait(0.5)
        on = bus.m.rd(CR0)[0] & 0x40
        say(f"block enable bit (18A0 bit6) = {on >> 6}")
        fails += on == 0
        rows = SL.load_rows(SL.tsv_for(a.map))
        for name, init, db, want, logs in CASES:
            n0 = len(cec.sent)
            cec.inject(bus.m, init, db)
            bus.wait(0.12)
            got = cec.sent[n0:]
            _, lines = SL.decode(SL.read_ring(bus.xdata, SL.sym(a.map, "g_stAwtoSync")), rows, whole=True)
            text = "\n".join(lines)
            ok = (got == [want]) if want else (got == [])
            miss = [s for s in logs if s not in text]
            say(f"{'PASS' if ok and not miss else 'FAIL'} {name}: sent {[(f'{h:02X}', d.hex()) for h, d in got]}"
                + (f", log missing {miss}" if miss else ""))
            fails += (not ok) or bool(miss)
        # registry cec_ctl on: hooks are logged ("no action yet"); cec_en off: block off, frames ignored; on again: answers
        st[SET_CEC_CTL] = 1
        cec.inject(bus.m, PLAYBACK, b"\x36")
        bus.wait(0.12)
        _, lines = SL.decode(SL.read_ring(bus.xdata, SL.sym(a.map, "g_stAwtoSync")), rows, whole=True)
        ok = any("hook:Standby (no action)" in x for x in lines)
        say(f"{'PASS' if ok else 'FAIL'} cec_ctl on: <Standby> logs a hook row, no action")
        fails += not ok
        st[SET_CEC_CTL] = 0
        st[SET_CEC_EN] = 0
        bus.wait(0.12)
        off = bus.m.rd(CR0)[0] & 0x40
        n0 = len(cec.sent)
        cec.inject(bus.m, PLAYBACK, b"\x8f")
        bus.wait(0.12)
        ok = off == 0 and len(cec.sent) == n0
        say(f"{'PASS' if ok else 'FAIL'} cec_en off: block bit {off >> 6}, frame not answered")
        fails += not ok
        st[SET_CEC_EN] = 1
        bus.wait(0.12)
        n0 = len(cec.sent)
        cec.inject(bus.m, PLAYBACK, b"\x8f")
        bus.wait(0.12)
        ok = (bus.m.rd(CR0)[0] & 0x40) != 0 and len(cec.sent) == n0 + 1
        say(f"{'PASS' if ok else 'FAIL'} cec_en on again: block on, frame answered")
        fails += not ok
        _, lines = SL.decode(SL.read_ring(bus.xdata, SL.sym(a.map, "g_stAwtoSync")), rows, whole=True)
        for ln in [x for x in lines if "CEC" in x][-12:]:
            say(f"  sync {ln}")
        results = [x for x in lines if "tx result" in x]
        say(f"tx result lines: {len(results)} (model: every transmit acked)")
        fails += not any("acked" in x for x in results)
    finally:
        bus.close()
    say(f"{'PASS' if fails == 0 else 'FAIL'} cec_sim {a.bin.name}: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    t = time.time()
    rc = main()
    say(f"cec_sim took {time.time() - t:.0f} s")
    sys.exit(rc)
