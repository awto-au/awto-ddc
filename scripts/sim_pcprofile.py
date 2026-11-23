#!/usr/bin/env python3
"""Where does the firmware spend a window of boot time? PC sampling in fw_sim (#216).

usage: sim_pcprofile.py BIN MAP --from MS --to MS [--mode 1080p60|2160p60] [--every N] [--top 20]
  Boots from reset; at fw time --from starts sampling the PC every N instructions until --to (fw ms, the ring's clock).
  Prints functions by share of the samples (the function the PC is in, banked code resolved by bank + pc).
  The sim has no peripherals: hardware polls and frame waits (ScalerTimerWaitForEvent) are not modelled; CPU-bound stretches
  (OSD draws, flash reads, loops) are real. A function that dominates a window the unit also spends is where to look.
Log: ./tmp/logs/sim_pcprofile.log
"""
import argparse
import collections
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S

LOG = S.ROOT / "tmp/logs/sim_pcprofile.log"
STEP = 20_000            # instructions between clock checks while skipping to --from (1.6 ms of fw time)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--from", dest="t0", type=float, required=True)
    ap.add_argument("--to", dest="t1", type=float, required=True)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--every", type=int, default=500)
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    bus = S.SimBus(a.bin, a.map, video=a.mode, port="D2", boot=False)
    m = bus.m
    while bus.now() * 1000 < a.t0:
        m.run(STEP)
    hits, n = collections.Counter(), 0
    while bus.now() * 1000 < a.t1:
        m.run(a.every)
        hits[m.where(m.p.bank, m.p.pc)] += 1
        n += 1
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{a.bin.name} window {a.t0:.0f}..{a.t1:.0f} ms ({n} samples every {a.every} instr)"]
    lines += [f"  {100 * c / n:5.1f} %  {f}" for f, c in hits.most_common(a.top)]
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + "\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
