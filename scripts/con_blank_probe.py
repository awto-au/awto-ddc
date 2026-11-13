#!/usr/bin/env python3
"""Blank power-on console probe (Dan 2026-11-12: console blank after mains power-on until DOWN).

usage: con_blank_probe.py --map MAP [--unit 2] [--no-cycle] [--lo 0x3A00 --hi 0x3B00]
- Mains cycle via Home Assistant (hass_power.py), wait for the boot to settle, dump XDATA lo..hi + key firmware vars,
  send test cmd 0x47 (console scroll down, = the DOWN that makes it visible), dump again, print every byte that differs.
Log: tmp/logs/con_blank_probe.log
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_link as L  # noqa: E402
import dbg_xdata as X  # noqa: E402
import i2cbus  # noqa: E402
import rtd_i2c_bridge as B  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp" / "logs" / "con_blank_probe.log"
SETTLE_S = 6.0        # power-up -> ACTIVE 1.8 s on m4 (sync log 2026-11-12) + console redraw; x3 margin; then dump
AFTER_S = 1.0         # test cmd consumed in < 10 ms (health osd test cmd); 1 s covers the main-loop pass + redraw
BUS, SERIAL = 11, "AWT26110002"
VARS = ("g_usFontSelectStart", "g_ucOsdWidth", "g_ucOsdHeight", "g_stOsdInfo")


def log(msg: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='milliseconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sym(mt: str, name: str) -> int | None:
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{name}\b", mt, re.M)
    return int(m[1], 16) & 0xFFFF if m else None


def dump(io, lo: int, hi: int, mt: str) -> dict:
    out = {}
    b = X.read_blocks(io, lo, hi - lo)
    if b:
        out.update({lo + i: v for i, v in enumerate(b)})
    for n in VARS:
        a = sym(mt, n)
        if a is not None:
            v = X.read_bytes(io, a, 16 if n == "g_stOsdInfo" else 2)
            if v:
                out.update({(n, i): x for i, x in enumerate(v)})
    return out


def testcmd(io, mt: str, cmd: int) -> bool:
    from osd_test import TESTCMD_OFF
    a = sym(mt, "isr_g_stAwtoDiag") + TESTCMD_OFF
    return (io.write(0x6A, 0x01, bytes([a >> 8])) and io.write(0x6A, 0x03, bytes([cmd]))
            and io.write(0x6A, 0x3B, bytes([a & 0xFF])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--no-cycle", action="store_true")
    ap.add_argument("--lo", type=lambda s: int(s, 0), default=0x3A00)
    ap.add_argument("--hi", type=lambda s: int(s, 0), default=0x3B00)
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    mt = a.map.read_text(errors="replace")
    if not a.no_cycle:
        rc = subprocess.call([sys.executable, str(ROOT / "scripts/hass_power.py"), "cycle", "--unit", "2"])
        if rc:
            log("power cycle failed")
            return 1
        time.sleep(SETTLE_S)                   # let the power-on episode reach ACTIVE (see SETTLE_S)
    i2cbus.require_unit(BUS, SERIAL)
    L.on(BUS, 5)
    io = B.Real(BUS, allow_write=True)
    try:
        d0 = dump(io, a.lo, a.hi, mt)
        log(f"blank state dumped: {len(d0)} bytes")
        if not testcmd(io, mt, 0x47):
            log("test cmd 0x47 write failed")
            return 1
        time.sleep(AFTER_S)                    # one main-loop pass consumes it (see AFTER_S)
        d1 = dump(io, a.lo, a.hi, mt)
        diff = [(k, d0.get(k), d1.get(k)) for k in sorted(d1, key=str) if d0.get(k) != d1.get(k)]
        for k, x, y in diff:
            ks = f"{k:04X}" if isinstance(k, int) else f"{k[0]}+{k[1]}"
            log(f"  {ks}: {x if x is None else f'{x:02X}'} -> {y:02X}")
        log(f"{len(diff)} byte(s) differ after the scroll")
    finally:
        io.close()
        L.off(BUS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
