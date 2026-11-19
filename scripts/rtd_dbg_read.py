#!/usr/bin/env python3
"""Read live XDATA bytes (scaler registers / firmware variables) through the firmware debug slave 0x35.

usage: rtd_dbg_read.py <bus> <addr|symbol>[:len] ... [--map tmp/fw/AWT26110003/fw.map] [--halt]
  Protocol (SDK ScalerCommonDebug.c, RTDCustomerTool log): W [0x01, hi] stage, W [0x3A, lo] -> ScalerGetByte(hi:lo),
  R sub 0x08 -> 1 byte. Only these commands are sent (plus 0x80 01/00 with --halt). Never writes memory.
  Without --halt the firmware keeps running; replies come from its EXINT1/ScalerDebug path (none = not serviced).
  Read-behind pages (dbg_xdata.BEHIND_PAGES): the first read of each new dword is repeated, the second is printed.
  Symbols resolve via the link map (XDATA `C:` lines); multi-byte values print hex as stored (SDCC LE build).
Log: ./tmp/logs/rtd_dbg_read.log
"""
import argparse
import os
import re
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
from rtd_i2c_bridge import Real

DBG = 0x35 << 1


def repo_root() -> Path:
    return Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("items", nargs="+")
    ap.add_argument("--map", default=str(repo_root() / "tmp/fw/AWT26110003/fw.map"))
    ap.add_argument("--halt", action="store_true", help="pause main (0x80 01) around the reads, resume after")
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    import rtd_i2c_bridge as B
    log = B.setup_logs("rtd_dbg_read", map=a.map).main     # decoded I2C + result lines; byte trace in .raw.log
    mp = Path(a.map).read_text(errors="replace") if Path(a.map).exists() else ""
    # only XDATA symbols ("D:" lines): 0x3A reads XDATA; DATA/IDATA variables are not reachable this way
    sym = {n: int(v, 16) for v, n in re.findall(r"^D:\s+([0-9A-F]{8})\s+(_\w+)", mp, re.MULTILINE)}
    dev = Real(a.bus, allow_write=True)                       # writes below are debug read commands only
    if a.halt:
        dev.write(DBG, 0x80, bytes([0x01]))
    last = None
    try:
        for it in a.items:
            name, _, n = it.partition(":")
            addr = int(name, 16) if re.match(r"^(0x)?[0-9a-fA-F]+$", name) else sym.get(name)   # bare hex = hex
            if addr is None:
                print(f"{name}: not in map"); continue
            vals = []
            for k in range(int(n or 1)):
                x = (addr + k) & 0xFFFF
                for _ in range(2 if X.stale_prone(x, last) else 1):
                    ok = dev.write(DBG, 0x01, bytes([x >> 8])) and dev.write(DBG, 0x3A, bytes([x & 0xFF]))
                    r = dev.read(DBG, 0x08, 1) if ok else None
                last = x
                vals.append(f"{r[0]:02x}" if r else "--")
            line = f"{name} @0x{addr:04x}: {' '.join(vals)}"
            print(line); log.write(f"{isostamp.now()} {line}\n")
    finally:
        if a.halt:
            dev.write(DBG, 0x80, bytes([0x00]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
