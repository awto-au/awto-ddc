#!/usr/bin/env python3
"""Stage table + gaps over tmp/logs/bringup/ep/*.txt (scratch). Prints markdown-ish tables."""
import re, statistics, sys, glob, collections
from pathlib import Path
EP = Path("/mnt/2tb/git/awto-ddc/tmp/logs/bringup/ep")
GAP_MS = 300
STAGES = [  # name, regex of the fw line (first match)
    ("boot", r"boot:main\(\) entered"),
    ("panel VDD/HPD", r"in VDD for .*->HPD"),
    ("backlight pin on", r"backlight pin on"),
    ("eDP stream on", r"link trained in (\d+)ms"),
    ("search start", r"->SEARCH"),
    ("input taken", r"input taken"),
    ("timing", r"D[123] timing|D1 DP link"),
    ("display set", r"stage:display setting took"),
    ("ACTIVE (picture)", r"picture on screen"),
]


def load(p):
    hdr, rows = None, []
    for ln in p.read_text().splitlines():
        if ln.startswith("#"):
            hdr = ln
        elif ln.startswith("fw"):
            m = re.match(r"fw\s+\+\s*(-?[\d.]+)s\s+ms=\s*(\d+)\s+(.*)", ln)
            rows.append((int(m.group(2)), float(m.group(1)), m.group(3)))
    return hdr, rows


def med(v):
    v = [x for x in v if x is not None]
    return (min(v), statistics.median(v), max(v), len(v)) if v else None


def main():
    groups = collections.defaultdict(list)
    for p in sorted(EP.glob("*.txt")):
        if p.name.endswith(".synclog.txt"):
            continue
        typ, unit = p.name.split("-")[:2]
        groups[(typ, unit)].append(p)
    for (typ, unit), ps in sorted(groups.items()):
        print(f"\n### {typ} unit {unit[1:]}  ({len(ps)} episodes)   times = ms from episode clock 0 (MCU boot for isp/cold)")
        per = collections.defaultdict(list)
        gaps = []
        for p in ps:
            hdr, rows = load(p)
            if not rows:
                continue
            for name, rx in STAGES:
                t = next((ms for ms, _, tx in rows if re.search(rx, tx)), None)
                per[name].append(t)
            t0 = rows[0][0]
            per["first line"].append(t0)
            act = next((ms for ms, _, tx in rows if "picture on screen" in tx), None)
            if act is not None:
                per["first->ACTIVE"].append(act - t0)
            # gaps with nothing logged, over the episode's first 3 s of lines
            prev = None
            for ms, _, tx in rows:
                if ms > (act if act is not None else t0 + 6000):
                    break
                if prev and ms - prev[0] >= GAP_MS and not tx.startswith("(the"):
                    gaps.append((p.name[:-4], prev[0], ms, ms - prev[0], prev[1][:50], tx[:60]))
                prev = (ms, tx)
        for name in ["first line"] + [s for s, _ in STAGES] + ["first->ACTIVE"]:
            r = med(per[name])
            if r:
                print(f"  {name:18s} min {r[0]:6d}  med {r[1]:8.0f}  max {r[2]:6d}  n={r[3]}")
        for g in gaps:
            print(f"  GAP>= {GAP_MS} ms {g[0]}: {g[1]} -> {g[2]} ({g[3]} ms) after '{g[4]}' before '{g[5]}'")


main()
