#!/usr/bin/env python3
"""Longest EX0-masked stretch seen on a unit: repeated HDMI re-locks, the sync DONE line's PHY span (= ScalerTMDSPhySetDeferred, EX0 masked, #281).

usage: irq_masks_hw.py N [--method sleep|kvm] [--away D1] [--unit 3]
- Per lock: DDC/CI sleep + wake (default) or input switch away and back; the sync ring is read until a new `sync DONE` line shows.
- PHY span = `PHY N ms (M set-ups)` of that line (0.1 ms steps are not in the line: ms resolution). Not covered: DP AUX / training, flash erase halt, panel sequences.
- End: dev.py health `monitor` row (longest watchdog gap per class: includes every ISR and masked section inside the gap).
Table: tmp/logs/irq_masks_hw.tsv; log: tmp/logs/irq_masks_hw.log. Take the unit lock first (scripts/unit_lock.py).
"""
import argparse
import json
import re
import subprocess
import sys

import isostamp
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/irq_masks_hw.log"
TSV = ROOT / "tmp/logs/irq_masks_hw.tsv"
POLLS = 12          # ring reads per step, each ~0.5 s; a lock + display set-up takes ~1.5 s (docs/sync-log-design.md)


def say(s: str) -> None:
    _log_line(s, LOG)


def dev(*a: str) -> str:
    r = subprocess.run([str(ROOT / "dev.py"), *a], capture_output=True, text=True, cwd=ROOT, check=False)
    return r.stdout + r.stderr


def ring(unit: str) -> list[dict]:
    for ln in dev("synclog", "--unit", unit, "--json").splitlines():
        if "SYNCJSON" in ln:
            d = json.loads(ln.split("SYNCJSON", 1)[1])
            for e in d["entries"]:
                e["seq"] = (d["ep_seq"], e["seq"])
            return d["entries"]
    return []


def new_done(unit: str, seen: set):
    for e in ring(unit):
        if e["seq"] not in seen and "sync DONE" in e["text"]:
            return e
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int)
    ap.add_argument("--method", default="sleep", choices=["sleep", "kvm"])
    ap.add_argument("--away", default="D1")
    ap.add_argument("--unit", default="3")
    a = ap.parse_args()
    seen = {e["seq"] for e in ring(a.unit)}
    rows = []
    for k in range(a.n):
        if a.method == "sleep":
            dev("ddc", "--unit", a.unit, "sleep")
            for _ in range(POLLS):
                if any("POWER SAVING" in e["text"] or "->SAVING" in e["text"] for e in ring(a.unit) if e["seq"] not in seen):
                    break
            seen.update(e["seq"] for e in ring(a.unit))
            dev("ddc", "--unit", a.unit, "wake")
        else:
            dev("kvm", a.away, "--units", a.unit)
            for _ in range(POLLS):
                if any("->ACTIVE" in e["text"] or "->NO SIGNAL" in e["text"] for e in ring(a.unit) if e["seq"] not in seen):
                    break
            seen.update(e["seq"] for e in ring(a.unit))
            dev("kvm", "D2", "--units", a.unit)
        e = None
        for _ in range(POLLS):
            e = new_done(a.unit, seen)
            if e:
                break
        if not e:
            say(f"{a.method} {k}: no sync DONE line within {POLLS} ring reads")
            continue
        seen.update(x["seq"] for x in ring(a.unit))
        m = re.search(r"PHY (\d+)ms \((\d+\+?) set-ups?\)", e["text"])
        phy, nset = (int(m.group(1)), m.group(2)) if m else (-1, "-")
        rows.append((a.method, k, phy, nset))
        say(f"{a.method} {k}: PHY span {phy} ms ({nset} set-ups): {e['text'].strip()[:150]}")
    with TSV.open("a") as f:
        for r in rows:
            f.write(f"{isostamp.now()}\t" + "\t".join(map(str, r)) + "\n")
    spans = [r[2] for r in rows if r[2] >= 0]
    say(f"{a.method}: {len(rows)} locks, PHY span max {max(spans) if spans else '-'} ms")
    for ln in dev("health", "--unit", a.unit).splitlines():
        if " monitor " in ln:
            say("health " + ln.strip()[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
