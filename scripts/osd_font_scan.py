#!/usr/bin/env python3
"""Scan the real OSD font SRAM (M1) of a unit through the QC harness image's dump command and locate Realtek's QC glyph tables in it (awto-ddc#227).

usage: osd_font_scan.py BUS --serial S --map MAP [--words N]
  Needs an image with the dump harness (test cmd 0xCA: g_usQcDumpAddr in, 54 words out in g_aucQcDump, marker 0xA5 at byte 7).
  Reads N words (default 12288 = the measured SRAM extent) in chunks, saves tmp/scratch/font_sram.bin (3 bytes per word, B0 B1 B2),
  then searches it for the first words of tQCFONT_GLOBAL / 2BITBROOK / 4BITLUFFY (decoded, canonical c0 c1 c2 -> stored c2 c1 c0).
Log: ./tmp/logs/osd_font_scan.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(Path(__file__).resolve().parent))
LOG = ROOT / "tmp/logs/osd_font_scan.log"
CHUNK = 54                   # g_aucQcDump holds 54 words
PRE_S = 2.0                  # the QC pattern run takes ~1 s on the unit: 2x
DONE_S = 0.5                 # one main-loop pass takes the cmd (~1 ms) + 54 x 6 register accesses (~10 ms): 50x margin
POLL_S = 0.02


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
    ap.add_argument("--words", type=int, default=12288)
    ap.add_argument("--sel", type=int, default=0, choices=(0, 1), help="SRAM read select: 0 = M1, 1 = M2")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--pre-cmd", type=lambda x: int(x, 0), default=None, help="test cmd sent first (0xB2 = QC pattern); its run settles for PRE_S")
    a = ap.parse_args()
    import dbg_link
    import dbg_xdata as X
    import i2cbus
    import osd_vlc as V
    import qc_osd_patterns as Q
    import rtd_i2c_bridge as B

    i2cbus.require_unit(a.bus, a.serial)
    txt = a.map.read_text(errors="replace")

    def sym(n):
        return int(re.search(r"^\S*\s+([0-9A-F]{8})\s+_?" + n + r"\b", txt, re.MULTILINE).group(1), 16) & 0xFFFF
    diag, dump, addr, selad = sym("isr_g_stAwtoDiag") + 0x28, sym("g_aucQcDump"), sym("g_usQcDumpAddr"), sym("g_ucQcDumpSel")
    mem = bytearray()
    with dbg_link.linked(a.bus, 8):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            def wr(ad, v):
                return io.write(0x6A, 0x01, bytes([ad >> 8])) and io.write(0x6A, 0x03, bytes([v])) and io.write(0x6A, 0x3B, bytes([ad & 0xFF]))
            wr(selad, a.sel)
            if a.pre_cmd is not None:
                wr(diag, a.pre_cmd)
                time.sleep(PRE_S)
            for w0 in range(0, a.words, CHUNK):
                wr(addr, w0 >> 8)
                wr(addr + 1, w0 & 0xFF)
                wr(dump + 7, 0)
                wr(diag, 0xCA)
                t0 = time.monotonic()
                raw = None
                while time.monotonic() - t0 < DONE_S:
                    time.sleep(POLL_S)
                    raw = X.read_blocks(io, dump, 8 + 3 * CHUNK)
                    if raw is not None and raw[7] == 0xA5:
                        break
                if raw is None or raw[7] != 0xA5:
                    say(f"no dump at word {w0}")
                    return 1
                mem += bytes(raw[8:8 + 3 * CHUNK])
        finally:
            io.close()
    out = a.out or ROOT / f"tmp/scratch/font_sram_m{a.sel + 1}.bin"
    out.write_bytes(bytes(mem))
    say(f"{len(mem) // 3} words -> {out}")
    words = [bytes(mem[i:i + 3]) for i in range(0, len(mem), 3)]
    t = Q.tables(Q.QC.read_text(errors="replace"))
    for name in ("tQCFONT_GLOBAL", "tQCFONT_2BITBROOK", "tQCFONT_4BITLUFFY"):
        d = V.decode(t[name])
        src = [bytes(reversed(d[i:i + 3])) for i in range(0, len(d) - 2, 3)]
        key = [w for w in src[:40] if w != b"\0\0\0"][:6]
        hits = []
        for i in range(len(words) - 8):
            if words[i] == key[0]:
                j, k = i, 0
                ok = 0
                for w in src[:40]:
                    if j < len(words) and words[j] == w:
                        ok += 1
                    j += 1
                if ok >= 30:
                    hits.append((i, ok))
        say(f"{name}: {len(src)} words; first 40 matched at {hits[:6] if hits else 'NOWHERE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
