#!/usr/bin/env python3
"""#60 timing table: alternate D2 -> D1 and D1 -> D2 switches N times each (DP-1 mirrored), ms to mode ACTIVE per run.

usage: sw_table.py --hdmi-bus 11 --dp-bus 15 --serial S --map MAP [--runs 5] [--label TEXT]
- Each switch = one scripts/sw_timeline.py run (its fixed 8 s settle), the log read on the new port's bus.
- Ends on D2; send 0x30 (auto search) afterwards. Log: ./tmp/logs/sw_table.log; one TSV row per run in tmp/logs/sw_table.tsv.
"""
import argparse, re, statistics, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = re.compile(r"\+\s*(\d+) ms\s+mode ACTIVE")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hdmi-bus", type=int, required=True)
    ap.add_argument("--dp-bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/sw_table.log").open("a", buffering=1)
    tsv = (ROOT / "tmp/logs/sw_table.tsv").open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    res = {"D1": [], "D2": []}
    legs = (("D1", a.hdmi_bus, a.dp_bus), ("D2", a.dp_bus, a.hdmi_bus))
    for run in range(a.runs):
        for to, bus, rbus in legs:
            out = subprocess.run([sys.executable, str(ROOT / "scripts/sw_timeline.py"), str(bus), "--serial", a.serial,
                                  "--map", a.map, "--to", to, "--read-bus", str(rbus)],
                                 capture_output=True, text=True).stdout
            m = ACTIVE.findall(out)
            ms = int(m[-1]) if m else None
            res[to].append(ms)
            say(f"{a.label} run {run + 1} to {to}: ACTIVE at {ms} ms")
            tsv.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\t{a.label}\t{to}\t{run + 1}\t{ms}\n")
    for to, v in res.items():
        ok = [x for x in v if x is not None]
        say(f"SUMMARY {a.label} to {to}: {v} median {statistics.median(ok) if ok else None} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
