#!/usr/bin/env python3
"""Colour-temperature presets in fw_sim (#278): VCP 0x14 per preset -> g_stColorProcData and the CTS contrast-coefficient writes.

usage: AWTO_SIM_CORE=fast ctemp_sim.py BIN MAP [--mode 1080p60]
  Per preset (VCP 0x14 value): the gains in RAM equal fw/colour_temp.tsv; the CTS set-A coefficients written to the scaler
  (P0_65 port data, PT_03..05 high bytes, PT_21 / PT_22 low nibbles) equal gain x contrast / 2048 (+-1 LSB, 10-bit compensation).
  The traced preset-to-coefficient ratios must differ between presets (the #278 symptom: all equal).
Exit 1 on a failed check. Log: tmp/logs/ctemp_sim.log
"""
import argparse
import csv
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import fw_sim as S
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/ctemp_sim.log"
VCP_COLOUR_TEMP = 0x14
VCP_OF = {"9300": 0x08, "7500": 0x06, "6500": 0x05, "5800": 0x04, "SRGB": 0x01}   # registry option_vcp
CTS_PORT_ADD, CTS_PORT_DATA = 0x0064, 0x0065                                      # P0_64 / P0_65 (regdb)
PT_RED_H, PT_GRN_H, PT_BLU_H, PT_RG_L, PT_B_L = 0x03, 0x04, 0x05, 0x21, 0x22     # set A coefficient ports (regdb)
TOL = 1


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


class CtsTrace(S.Dev):
    def __init__(self):
        self.reads, self.writes, self.port, self.seen = (), (CTS_PORT_ADD, CTS_PORT_DATA), 0, {}

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == CTS_PORT_ADD:
            self.port = v
        else:
            self.seen[self.port] = v

    def coef(self):
        s = self.seen
        try:
            lo_rg, lo_b = s[PT_RG_L], s[PT_B_L]
            return [s[PT_RED_H] << 4 | lo_rg >> 4, s[PT_GRN_H] << 4 | lo_rg & 15, s[PT_BLU_H] << 4 | lo_b >> 4]
        except KeyError:
            return None


def table(root):
    with open(root / "fw/colour_temp.tsv") as f:
        rd = csv.DictReader((ln for ln in f if not ln.startswith("#")), delimiter="\t")
        return {r["preset"]: [int(r[c], 16) for c in "rgb"] for r in rd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    eng, tr = D.DdcEngine(), CtsTrace()
    s = R.Session(a.bin, a.map, a.mode, devs=[eng, tr])
    s.boot()
    mccs = D.Mccs(s.bus, eng)
    m = s.bus.m
    gp = m.addr("g_stColorProcData")
    tbl, fails, got, ref = table(ROOT), 0, {}, None

    def check(ok, what, detail=""):
        nonlocal fails
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        fails += 0 if ok else 1

    # sRGB is the default (#355): a set to the current preset applies nothing, so 9300 first, then sRGB = the unity reference
    for name in ("9300", "SRGB", "9300", "7500", "6500", "5800", "SRGB"):
        tr.seen.clear()
        mccs.set(VCP_COLOUR_TEMP, VCP_OF[name])
        s.bus.wait(0.4)
        b = m.rd(gp, 6)
        g = [b[0] << 8 | b[1], b[2] << 8 | b[3], b[4] << 8 | b[5]]
        check(g == tbl[name], f"{name}: g_stColorProcData = table", f"{[hex(x) for x in g]} want {[hex(x) for x in tbl[name]]}")
        c = tr.coef()
        check(c is not None, f"{name}: CTS set-A coefficient writes traced", f"{c}")
        if c is None:
            continue
        got[name] = c
        if ref is None and name == "SRGB":
            ref = max(c)                                       # unity gain: coefficient = contrast term
        if ref is not None:
            want = [min(4095, round(x * ref / 0x800)) for x in tbl[name]]
            check(all(abs(x - y) <= TOL for x, y in zip(c, want)), f"{name}: coefficient = gain x contrast / 2048",
                  f"{c} want {want}")
    check(len({tuple(v) for v in got.values()}) == len(got), "presets give different coefficients", f"{ {k: v for k, v in got.items()} }")
    say(f"{'PASS' if fails == 0 else 'FAIL'} ctemp_sim {a.bin.name}: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
