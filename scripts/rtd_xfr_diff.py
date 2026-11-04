#!/usr/bin/env python3
"""Read-only: dump MCU XFR ranges (DDC / DDC-CI / bank control) from several monitors and diff them.

usage: rtd_xfr_diff.py <bus>[=label] [<bus>[=label] ...] [--ranges FF1B-FF39,FFB1-FFB3,FFD1-FFE5,FFFC-FFFF]
  Each bus: ISP enter (MCU halted, XFRs frozen), read, ISP reset (monitor reboots). No writes to XFRs.
  Prints one row per address with any difference marked '*'. Names: RL6449 SDK ScalerMcu XFR decls (#8).
Log: ./tmp/logs/rtd_xfr_diff.log
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import Osd

NAMES = {0xFF1B: "ADC_DDC_ENABLE", 0xFF1C: "ADC_DDC_CTRL1", 0xFF1D: "ADC_DDC_CTRL2",
         0xFF1E: "DDC0_ENABLE", 0xFF1F: "DDC0_CTRL1", 0xFF20: "DDC0_CTRL2",
         0xFF22: "IIC_CH_SEL", 0xFF23: "IIC_SET_SLAVE", 0xFF24: "IIC_SUB_IN", 0xFF25: "IIC_DATA_IN",
         0xFF26: "IIC_DATA_OUT", 0xFF27: "IIC_STATUS", 0xFF28: "IIC_IRQ_CTRL", 0xFF29: "IIC_STATUS2",
         0xFF2A: "IIC_IRQ_CTRL2", 0xFF2B: "IIC_CH_CTRL", 0xFF2C: "DDC1_ENABLE", 0xFF2D: "DDC1_CTRL1",
         0xFF2E: "DDC1_CTRL2", 0xFF35: "DDCCI_REMAIN", 0xFFB1: "DDCCI_NULL1", 0xFFB2: "DDCCI_NULL2",
         0xFFB3: "DDCCI_NULL3", 0xFFD1: "DDCRAM0_CTRL", 0xFFD2: "DDCRAM1_CTRL", 0xFFD3: "DDCRAM2_CTRL",
         0xFFD4: "DDCRAM3_CTRL", 0xFFE4: "DDC0_EDID_IRQ", 0xFFE5: "DDC1_EDID_IRQ",
         0xFFFC: "BANK_SWITCH_CTRL", 0xFFFD: "XDATA_BANK_START", 0xFFFE: "XDATA_BANK_SEL", 0xFFFF: "PBANK"}


def parse_ranges(s):
    out = []
    for part in s.split(","):
        lo, _, hi = part.partition("-")
        out += range(int(lo, 16), int(hi or lo, 16) + 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("buses", nargs="+")
    ap.add_argument("--ranges", default="FF1B-FF39,FFB1-FFB3,FFD1-FFE5,FFFC-FFFF")
    a = ap.parse_args()
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp/logs/rtd_xfr_diff.log").open("a")
    addrs = parse_ranges(a.ranges)
    cols = {}
    for b in a.buses:
        bus, _, label = b.partition("=")
        o = Osd(int(bus))
        P.log(f"=== xfr read bus={bus} ({label or bus}) {a.ranges} ===")
        o.enter()
        try:
            cols[label or bus] = {x: o.rd(x) for x in addrs}
        finally:
            o.reset()
    hdr = "addr  name              " + " ".join(f"{k:>12}" for k in cols)
    lines = [hdr]
    for x in addrs:
        vals = [c[x] for c in cols.values()]
        mark = "*" if len(set(vals)) > 1 else " "
        lines.append(f"{x:04X}{mark} {NAMES.get(x, ''):17} " + " ".join(f"{v:>#12x}" for v in vals))
    for ln in lines:
        P.log(ln); print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
