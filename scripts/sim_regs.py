#!/usr/bin/env python3
"""Boot an image in fw_sim to ACTIVE and print scaler registers: compare two builds (e.g. two compilers) by the values the
firmware programs, not by bytes (#137 check: the same registers from both images = the code change is not behavioural).

usage: sim_regs.py BIN MAP [--mode 1080p60|2160p60] ADDR[:N] ...    (ADDR hex, N bytes, default 1)
  Output: one line per ADDR: "0x003D: 7f 0c ..." (page-0 and 0x3Axx OSD registers read from the sim's register file).
  Diff two runs: sim_regs.py A.bin A.map ... > a.txt; sim_regs.py B.bin B.map ... > b.txt; diff a.txt b.txt
  Not run in the sim (stubbed, fw_sim_vfreq.py / fw_sim_trace.py skip lists, e.g. ScalerMemorySetIVS2DVSLineDelay): registers they
  program are the sim's, not the image's; read those on the unit (rtd_dbg_read.py) instead.
Log: ./tmp/logs/sim_regs.log
"""
import argparse, sys
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402

LOG = R.ROOT / "tmp/logs/sim_regs.log"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60", choices=sorted(R.PANEL))
    ap.add_argument("regs", nargs="+")
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, a.mode)
    s.boot(sync_console=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for item in a.regs:
        ad, _, n = item.partition(":")
        ad, n = int(ad, 16), int(n or 1)
        out.append(f"0x{ad:04X}: " + " ".join(f"{b:02x}" for b in s.bus.m.rd(ad, n)))
    print("\n".join(out))
    with LOG.open("a") as f:
        f.write(f"{isostamp.now()} {a.bin.name} {a.mode}\n" + "\n".join("  " + o for o in out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
