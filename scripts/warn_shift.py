#!/usr/bin/env python3
"""Re-key fw/warn_policy.tsv rows after an insert moved SDK lines (the warn gate keys rows on file + line).

usage: warn_shift.py --tree WORKTREE [--write]
  Reads WORKTREE/tmp/sdcc-port/warnings.txt (last compile) and WORKTREE/fw/warn_policy.tsv.
  Per file: stale rows (no warning at their line) vs unreviewed warnings (no row); picks the one line shift d that maps the
  most stale rows onto unreviewed warnings of the same pattern, and moves those rows by d. Rows it cannot map stay stale;
  warnings it cannot map stay unreviewed (review them by hand). Dry run unless --write. Log: ./tmp/logs/warn_shift.log
"""
import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

WARN = re.compile(r"/tmp/sdcc-port/src/(.+?):(\d+): warning \d+: (.*)$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True, type=Path)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (root / "tmp/logs/warn_shift.log").open("a")

    def say(s):
        print(s); lf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n")

    warns = defaultdict(list)                           # file -> [(line, text)]
    for ln in (a.tree / "tmp/sdcc-port/warnings.txt").read_text(errors="replace").splitlines():
        m = WARN.search(ln)
        if m:
            warns[m.group(1)].append((int(m.group(2)), m.group(3)))
    pol = a.tree / "fw/warn_policy.tsv"
    rows = pol.read_text().split("\n")
    parsed = [r.split("\t") for r in rows]
    moved = 0
    for f, ws in warns.items():
        idx = [i for i, p in enumerate(parsed) if len(p) > 3 and p[1] == f and p[2].isdigit()]

        def hit(i, line):
            return any(w_line == line and re.search(parsed[i][0], w_txt) for w_line, w_txt in ws)
        stale = [i for i in idx if not hit(i, int(parsed[i][2]))]
        unrev = [(wl, wt) for wl, wt in ws if not any(int(parsed[i][2]) == wl and re.search(parsed[i][0], wt) for i in idx)]
        if not stale or not unrev:
            continue
        votes = Counter(wl - int(parsed[i][2]) for i in stale for wl, wt in unrev if re.search(parsed[i][0], wt))
        if not votes:
            continue
        d, n = votes.most_common(1)[0]
        for i in stale:
            new = int(parsed[i][2]) + d
            if any(wl == new and re.search(parsed[i][0], wt) for wl, wt in unrev):
                say(f"{f}: {parsed[i][2]} -> {new} (shift {d:+d})")
                parsed[i][2] = str(new)
                moved += 1
    left = sum(1 for f, ws in warns.items() for wl, wt in ws
               if not any(len(p) > 3 and p[1] == f and p[2] == str(wl) and re.search(p[0], wt) for p in parsed))
    say(f"{'moved' if a.write else 'would move'} {moved} rows; {left} warning sites still without a row")
    if a.write:
        pol.write_text("\n".join("\t".join(p) for p in parsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
