#!/usr/bin/env python3
"""OSD SRAM probe run by the firmware itself (awto-ddc#226): marker writes + read-back of M1 / M2 on the MCU, results read from RAM.

usage: osd_sram_probe.py BUS --serial S --map MAP
  Sends test cmd 0x0F (AWTO_TC_OSD_SRAM_PROBE) over the debug link, then reads g_stAwtoOsdProbe (fw/test/testcmd.c) and prints per
  address: the words before, and (only where the old content was all zero, so the marker could be written and zeros restored) the
  words after the marker write, for M1 and M2. Marker = <addr hi> <addr lo> A5, written to both memories at once.
  Needs the OSD off (console_mode Off, no menu): the firmware refuses otherwise (state 3).
Log: ./tmp/logs/osd_sram_probe.log
"""
import argparse
import os
import struct
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/osd_sram_probe.log"
N = 13                       # AWTO_OSDP_N
SIZE = 2 + 2 * N + 6 * N + 6 * N + N   # StAwtoOsdProbe
TESTCMD_OFF = 0x28           # isr_g_stAwtoDiag.ucTestCmd
TC = 0x0F                    # AWTO_TC_OSD_SRAM_PROBE
DONE_WAIT_S = 0.5            # the main loop takes one test cmd per pass (~1 ms) and the probe is ~1 ms of register work: 500x margin
MARK_B2 = 0xA5


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_link, dbg_xdata as X, i2cbus, sw_timeline as T  # noqa: E401
    import rtd_i2c_bridge as B  # noqa: E402

    i2cbus.require_unit(a.bus, a.serial)
    res = T.sym(a.map, "g_stAwtoOsdProbe")
    import re
    hit = re.search(r"^\S*\s+([0-9A-F]{8})\s+_isr_g_stAwtoDiag\b", a.map.read_text(errors="replace"), re.M)   # listed without the D: prefix
    if not hit:
        sys.exit(f"isr_g_stAwtoDiag not in {a.map}")
    cmd = (int(hit.group(1), 16) & 0xFFFF) + TESTCMD_OFF
    with dbg_link.linked(a.bus, 2):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            ok = (io.write(0x6A, 0x01, bytes([cmd >> 8])) and io.write(0x6A, 0x03, bytes([TC])) and io.write(0x6A, 0x3B, bytes([cmd & 0xFF])))
            if not ok:
                say("test cmd write NAK")
                return 1
            t0 = time.monotonic()
            raw = None
            while time.monotonic() - t0 < DONE_WAIT_S:
                raw = X.read_blocks(io, res, SIZE)
                if raw is not None and raw[0] in (2, 3):
                    break
            if raw is None or raw[0] not in (2, 3):
                say(f"no result within {DONE_WAIT_S} s (state {None if raw is None else raw[0]})")
                return 1
        finally:
            io.close()
    state = raw[0]
    if state == 3:
        say("refused: the OSD is on (close the console / menu first)")
        return 2
    circuit = raw[1]
    addrs = struct.unpack(f">{N}H", raw[2:2 + 2 * N])
    o = 2 + 2 * N
    orig = [raw[o + 6 * i:o + 6 * i + 6] for i in range(N)]
    o += 6 * N
    mark = [raw[o + 6 * i:o + 6 * i + 6] for i in range(N)]
    o += 6 * N
    skip = raw[o:o + N]
    say(f"{a.map.name}: OSD SRAM probe on the MCU (OSD circuit was {'on' if circuit else 'off'} before), marker = <hi> <lo> {MARK_B2:02X} to M1 and M2")
    say("  addr    before M1       before M2       after  M1       after  M2       result")
    for i in range(N):
        h = lambda b: " ".join(f"{x:02X}" for x in b)
        want = bytes([addrs[i] >> 8, addrs[i] & 0xFF, MARK_B2])
        if skip[i]:
            res_txt = "in use (not all zero): read only"
            aft = ("-- -- --", "-- -- --")
        else:
            m1, m2 = mark[i][:3], mark[i][3:]
            aft = (h(m1), h(m2))
            res_txt = f"M1 {'OK' if m1 == want else 'differs'}, M2 {'OK' if m2 == want else 'differs'}"
        say(f"  0x{addrs[i]:04X}  {h(orig[i][:3])}   {h(orig[i][3:])}   {aft[0]}   {aft[1]}   {res_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
