#!/usr/bin/env python3
"""Measured-vs-host refresh offset per mode from a mode_sweep TSV (measure-clock calibration).

usage: sweep_ppm.py TSV [TSV...]
  One line per ACTIVE row: host mode, firmware timing, offset in ppm, frc flag; then the median per frc path.
  Host refresh = the gdctl mode string (exact to 1 mHz), so offsets below ~20 ppm at 60 Hz are rounding.
Log: ./tmp/logs/sweep_ppm.log
"""
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RX = re.compile(r"(\d+)x(\d+)@([\d.]+)")


def main() -> int:
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    out = (ROOT / "tmp/logs/sweep_ppm.log").open("a", buffering=1)
    by = {}
    for f in sys.argv[1:]:
        rows = Path(f).read_text().splitlines()
        hdr = rows[0].split("\t")
        for r in rows[1:]:
            d = dict(zip(hdr, r.split("\t")))
            h, m = RX.match(d.get("mode", "")), RX.match(d.get("timing", "") or "")
            if not (h and m) or d.get("mode_state") != "ACTIVE":
                continue
            ppm = (float(m.group(3)) / float(h.group(3)) - 1) * 1e6
            frc = d.get("frc", "?")
            by.setdefault(frc, []).append(ppm)
            line = f"{Path(f).name}\t{d['mode']}\t{d['timing']}\t{ppm:+.0f} ppm\tfrc={frc}"
            print(line); out.write(line + "\n")
    for k, v in sorted(by.items()):
        line = f"frc={k}: n={len(v)} median {statistics.median(v):+.0f} ppm, range {min(v):+.0f}..{max(v):+.0f}"
        print(line); out.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
