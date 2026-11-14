#!/usr/bin/env python3
"""Compiled but not linked: functions the compiler emitted (tmp/sdcc-port/asm, before any pruning) with no CH_ area in the map.

usage: dead_code.py MAP [--asm DIR] [--tsv OUT]
  MAP: the image's map (tmp/fw/<tag>.map). DIR: the same build's full compiler output (default tmp/sdcc-port/asm).
  Per source module: functions compiled, not linked. Unused in THIS build configuration only: check the other
  variants (freeze / no-FRC / audio test) before deleting source.
Log: ./tmp/logs/dead_code.log
"""
import argparse, os, re, sys, time
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/dead_code.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    ap.add_argument("--asm", type=Path, default=ROOT / "tmp/sdcc-port/asm")
    ap.add_argument("--tsv", type=Path, default=ROOT / "tmp/logs/dead_code.tsv")
    a = ap.parse_args()
    linked = set(re.findall(r"^CH_(\w+)\s+[0-9A-F]{8}\s+[0-9A-F]{8} =", a.map.read_text(errors="replace"), re.M))
    per = defaultdict(lambda: [0, []])                   # module -> functions compiled, names not linked
    for p in sorted(a.asm.glob("*.asm")):
        t = p.read_text(errors="replace")
        src = re.search(r"^;\s+(/\S.*?\.c):\d+:", t, re.M)
        mod = src.group(1).split("/sdcc-port/src/")[-1].split("/awto-ddc/")[-1] if src else p.stem
        for f in re.findall(r"^;\s+function\s+(\w+)", t, re.M):
            per[mod][0] += 1
            if f not in linked:
                per[mod][1].append(f)
    rows = sorted(per.items(), key=lambda kv: -len(kv[1][1]))
    n_all, n_dead = sum(r[0] for _, r in rows), sum(len(r[1]) for _, r in rows)
    whole = [m for m, r in rows if r[0] and len(r[1]) == r[0]]
    say(f"{a.map.name}: {n_all} functions compiled, {n_dead} not linked ({100 * n_dead // max(n_all, 1)} %) in "
        f"{sum(1 for _, r in rows if r[1])} files; {len(whole)} files with nothing linked")
    for mod, r in rows[:30]:
        if r[1]:
            say(f"  {len(r[1]):4d}/{r[0]:4d}  {mod}")
    with a.tsv.open("w") as f:
        f.write("source\tfunction\n")
        for mod, r in rows:
            for n in r[1]:
                f.write(f"{mod}\t{n}\n")
    say(f"per-function list: {a.tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
