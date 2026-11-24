#!/usr/bin/env python3
"""Colour-temperature presets on a running unit (#278): per preset VCP 0x14, then the CTS set-A coefficients read from the scaler.

usage: ctemp_regs.py --map MAP [--unit 3] [--presets 5,8,6,4,1,5]
  Reads P0_65 data-port entries PT_03/04/05 (high bytes) and PT_21/22 (low nibbles) over the debug link (dbg-write sets the port
  address, dbg-read reads P0_65), plus g_stColorProcData. Coefficient = gain x contrast / 2048 (12 bit). No picture capture here.
Log: tmp/logs/ctemp_regs.log
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/ctemp_regs.log"
DEV = str(ROOT / "dev.py")
VCP_COLOUR_TEMP = "0x14"
PORT_ADD, PORT_DATA = "0064", "0065"                    # P0_64 / P0_65 CTS_BRI port (regdb)
PT = {"r_h": "03", "g_h": "04", "b_h": "05", "rg_l": "21", "b_l": "22"}   # set A coefficient ports (regdb)


def say(s):
    _log_line(s, LOG, stamp_stdout=True)


def run(*a):
    return subprocess.run([DEV, *a], capture_output=True, text=True, check=False).stdout


def rd(unit, mp, what):
    out = run("dbg-read", "--unit", unit, "--map", mp, what)
    m = re.search(r"@0x[0-9a-f]+: ((?:[0-9a-f]{2} ?)+)", out)
    return bytes.fromhex(m.group(1).replace(" ", "")) if m else None


def port(unit, mp, pt):
    run("dbg-write", "--unit", unit, "--map", mp, "--label", "ctemp-port", f"{PORT_ADD}={pt}")
    b = rd(unit, mp, f"{PORT_DATA}:1")
    return b[0] if b else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--unit", default="3")
    ap.add_argument("--presets", default="5,8,6,4,1,5")
    a = ap.parse_args()
    for v in a.presets.split(","):
        run("ddc", "--unit", a.unit, "set", VCP_COLOUR_TEMP, v)
        g = rd(a.unit, a.map, "_g_stColorProcData:6")
        p = {k: port(a.unit, a.map, pt) for k, pt in PT.items()}
        if None in p.values() or g is None:
            say(f"preset VCP 0x14 = {v}: read failed {p} {g}")
            continue
        c = [p["r_h"] << 4 | p["rg_l"] >> 4, p["g_h"] << 4 | p["rg_l"] & 15, p["b_h"] << 4 | p["b_l"] >> 4]
        gw = [g[i] << 8 | g[i + 1] for i in (0, 2, 4)]
        say(f"preset VCP 0x14 = {v}: gains R,G,B = {[hex(x) for x in gw]}, CTS coefficient R,G,B = {c} ({[hex(x) for x in c]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
