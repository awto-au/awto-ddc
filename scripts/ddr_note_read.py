#!/usr/bin/env python3
"""Read host-note lines back from the DDR note store over the debug link (awto-ddc log-keep, docs/note-store.md).

usage: ddr_note_read.py --unit N --bus B --map MAP [--last K | --seq S ...]
  The firmware writes each note's 128 B line to the top of the DDR (RL6449_Project.h AWTO_DDRN_*); this pokes MCU_DC port A (page 37)
  the same way the firmware does and prints tag / length / text per line. Default: the last 5 notes (counter g_usAwtoNoteN).
Log: ./tmp/logs/ddr_note_read.log
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _repo import ROOT

HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
POLL_S = 0.5                    # CMD idle / read flag: the burst takes ~64 us on the MCU, one I2C poll ~1 ms: 0.5 s = 500x, expiry = error


def hdef(name: str) -> int:
    m = re.search(rf"^#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)", HDR.read_text(), re.MULTILINE)
    if not m:
        raise SystemExit(f"{name} not in {HDR.name}")
    return int(m.group(1), 0)


def regs() -> dict:
    t = (ROOT / "fw/sdk/Project/Header/AwtoRegs.h").read_text()
    return {n: int(re.search(rf"^#define\s+{n}\s+(0x[0-9A-Fa-f]+)", t, re.MULTILINE).group(1), 0)
            for n in ("AWTO_R_MCU_DC_CMD_A", "AWTO_F_MCU_DC_CMD_A_DDR_A_CMD", "AWTO_R_MCU_DC_ADDR_H_A", "AWTO_R_MCU_DC_ADDR_M_A", "AWTO_R_MCU_DC_ADDR_L_A",
                      "AWTO_R_MCU_DC_ADDR_A", "AWTO_R_MCU_DC_DATABUF_R_00_A", "AWTO_R_MCU_DC_READ_FLAG_A")}


def read_line(d, r: dict, seq: int) -> bytes:
    n_slots, line_units, bursts = hdef("AWTO_DDRN_SLOTS"), hdef("AWTO_DDRN_LINE_UNITS"), hdef("AWTO_DDRN_BURSTS")
    base, half, size = hdef("AWTO_DDRN_UNITS0"), hdef("AWTO_DDRN_HALF"), hdef("AWTO_DDRN_BURST_BYTES")
    out = b""
    for b in range(bursts):
        u = base + (seq & (n_slots - 1)) * line_units + b * (size // 8)
        t0 = time.monotonic()
        while d.rd(r["AWTO_R_MCU_DC_CMD_A"]) & r["AWTO_F_MCU_DC_CMD_A_DDR_A_CMD"]:
            if time.monotonic() - t0 > POLL_S:
                raise OSError("MCU_DC port A busy")
        for reg, sh in (("AWTO_R_MCU_DC_ADDR_H_A", 24), ("AWTO_R_MCU_DC_ADDR_M_A", 16), ("AWTO_R_MCU_DC_ADDR_L_A", 8), ("AWTO_R_MCU_DC_ADDR_A", 0)):
            d.wr(r[reg], (u >> sh) & 0xFF)
        d.wr(r["AWTO_R_MCU_DC_CMD_A"], hdef("AWTO_DDRN_CMD_READ"))
        t0 = time.monotonic()
        while not d.rd(r["AWTO_R_MCU_DC_READ_FLAG_A"]) & hdef("AWTO_DDRN_READ_FLAG"):
            if time.monotonic() - t0 > POLL_S:
                raise OSError("read flag timeout")
        buf = bytes(d.rd(r["AWTO_R_MCU_DC_DATABUF_R_00_A"] + k) for k in range(size))
        out += bytes(buf[(j + half) % size] for j in range(size))
    return out


def text_of(io, seq: int) -> str | None:
    """the note's text from the DDR line over an open debug-link io; None when the tag does not match or the port does not answer"""
    import ddr_frame_test as T
    d = T.Dbg.__new__(T.Dbg)                         # Dbg over an io that is already open (rd / wr = the debug slave XDATA window)
    d.io, d.bus, d.n_tx = io, None, 0
    try:
        line = read_line(d, regs(), seq)
    except OSError:
        return None
    if int.from_bytes(line[hdef("AWTO_NOTE_TAG"):hdef("AWTO_NOTE_TAG") + 2], "big") != seq & 0xFFFF:
        return None
    n, o = min(line[hdef("AWTO_NOTE_LEN")], hdef("AWTO_NOTE_CHARS")), hdef("AWTO_NOTE_TXT")
    return "".join(chr(c) if 0x20 <= c <= 0x7E else "?" for c in line[o:o + n])


def main() -> int:
    import ddr_frame_test as T
    import sw_timeline as SW

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--last", type=int, default=5)
    ap.add_argument("--seq", type=int, nargs="*")
    a = ap.parse_args()
    T.LOG = ROOT / "tmp/logs/ddr_note_read.log"
    d = T.Dbg(a.unit, a.bus)
    r = regs()
    seqs = a.seq
    if not seqs:
        n = (d.rd(SW.sym(a.map, "g_usAwtoNoteN")) << 8) | d.rd(SW.sym(a.map, "g_usAwtoNoteN") + 1)
        seqs = list(range(max(1, n - a.last + 1), n + 1))
    note_tag, note_len, note_txt = hdef("AWTO_NOTE_TAG"), hdef("AWTO_NOTE_LEN"), hdef("AWTO_NOTE_TXT")
    for s in seqs:
        line = read_line(d, r, s)
        tag, ln = int.from_bytes(line[note_tag:note_tag + 2], "big"), line[note_len]
        txt = "".join(chr(c) if 0x20 <= c <= 0x7E else "?" for c in line[note_txt:note_txt + ln])
        T.log(f"ddr note {s}: tag {tag} {'OK' if tag == s & 0xFFFF else 'MISMATCH'}, len {ln}: {txt!r}")
    d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
