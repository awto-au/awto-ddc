#!/usr/bin/env python3
"""Warm-reset timing of a unit's input sync (internal module of `./dev.py syncbench`, #78 / #239).

usage (via dev.py): ./dev.py syncbench [--unit N] [--map F] [--runs 5] [--label NAME] [--switch AWAY,BACK]
  --switch D1,D2: per run the input goes to D1 (monitor side, VCP 0x60 via kvm) and straight back to D2; the row is the D2 episode.
  Per run (no --switch): ISP reset (the DP AUX reset write times out although it resets), then `./dev.py synclog` until the picture line
  is in the ring (RUN_LIMIT_S, 5 s max wait for a monitor to come back: memory monitor-wait-5s). One TSV row per run, then the median.
  Columns: ms from the timer start (episode start). edid = first EDID read by the source (HPD edges: the FA lines in the run files); scan = ms inside the scan call (F2 ok line).
Log: ./tmp/logs/sync_bench.log (every row, every synclog line of the run in sync_bench.<label>.run<k>.txt)
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import isostamp

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/sync_bench.log"
RUN_LIMIT_S = 5.0       # picture comes ~1.5 s after the reset; synclog itself takes ~1.5 s per read: 3 reads max
LINE = re.compile(r"^\S+\s+(\d+):(.*)$")
COLS = ["first", "edid", "scan", "scan_start", "measure", "display", "colour", "picture", "to_picture"]


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{isostamp.now()} {s}\n")
    print(s, flush=True)


def parse(text: str) -> dict:
    """Times in ms (episode clock) of the lines that make up the timeline; None when the line is not there."""
    r: dict = dict.fromkeys(COLS)
    stages: list[str] = []
    for ln in text.splitlines():
        m = LINE.match(ln)
        if not m:
            continue
        ms, t = int(m.group(1)), m.group(2)
        if t.startswith("boot:main() entered"):
            r["first"] = ms
        elif "EDID read by source" in t and r["edid"] is None:
            r["edid"] = ms
        elif t.startswith("scan ok:"):
            mm = re.search(r"(\d+)ms$", t)
            r["scan"] = int(mm.group(1)) if mm else None
            r["scan_start"] = ms - (r["scan"] or 0)
        elif t.startswith("stage:measure took"):
            r["measure"] = int(re.search(r"(\d+)ms", t).group(1))
        elif t.startswith("stage:display setting took"):
            r["display"] = int(re.search(r"(\d+)ms", t).group(1))
        elif t.startswith("stage:colour set-up took"):
            r["colour"] = int(re.search(r"(\d+)ms", t).group(1))
        elif "picture on screen" in t and r["picture"] is None:
            r["picture"] = ms
        if t.startswith(("scan ", "slow delay", "EXPIRED", "slow poll", "slow wait")):
            stages.append(f"{ms}:{t}")
    if r["picture"] is not None:
        r["to_picture"] = r["picture"] - (r["first"] or 0)       # a switch episode has no boot lines: it starts at 0
    r["stages"] = stages
    return r


def sh(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout + p.stderr


def one_run(unit: str, mp: str, label: str, k: int, switch: str) -> dict:
    if switch:
        away, back = switch.split(",")
        sh(["./dev.py", "kvm", away, "--units", unit])
        sh(["./dev.py", "kvm", back, "--units", unit])
    else:
        sh(["./dev.py", "reset", "--unit", unit])     # rc 1 on DP AUX (the write times out as the MCU resets): not an error
    t0 = time.monotonic()
    text, r = "", {}
    while time.monotonic() - t0 < RUN_LIMIT_S:
        _rc, text = sh(["./dev.py", "synclog", "--unit", unit, "--map", mp])
        r = parse(text)
        if r["picture"] is not None:
            break
    (ROOT / "tmp/logs" / f"sync_bench.{label}.run{k}.txt").write_text(text)
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="run")
    ap.add_argument("--switch", default="")
    a = ap.parse_args()
    rows = []
    say(f"syncbench unit {a.unit} label {a.label} map {a.map} runs {a.runs}")
    say("run\t" + "\t".join(COLS))
    for k in range(1, a.runs + 1):
        r = one_run(a.unit, a.map, a.label, k, a.switch)
        rows.append(r)
        say(f"{k}\t" + "\t".join("-" if r[c] is None else str(r[c]) for c in COLS))
        for s in r["stages"]:
            say(f"  {s}")
    med = ["-" if not [x[c] for x in rows if x[c] is not None] else str(int(statistics.median([x[c] for x in rows if x[c] is not None]))) for c in COLS]
    say("median\t" + "\t".join(med))
    return 0 if all(r["picture"] is not None for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
