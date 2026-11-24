#!/usr/bin/env python3
"""Renumber fw/warn_policy.tsv rows whose file:line moved after code was inserted into a ported SDK file.

usage: warn_policy_renum.py BUILD_LOG [--policy PATH]
  BUILD_LOG = a dev.py build log with `WARN-GATE unreviewed: FILE:LINE: TEXT` lines (tmp/logs/build_<tag>_<serial>.out in the tree).
  Per file, the policy rows whose pattern matches are paired with the unreviewed warnings in line order (most pairs, least
  total line distance); each paired row's line is rewritten. Rows a real warning of the build still matches (--warnings,
  default tmp/sdcc-port/warnings-*.txt) never move. Warnings with no row are listed and left alone (they need a real review).
Log: tmp/logs/warn_policy_renum.log
"""
import argparse
import fnmatch
import re
import sys
from pathlib import Path

from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/warn_policy_renum.log"
DEFAULT_POLICY = ROOT / "fw/warn_policy.tsv"
WARN_RE = re.compile(r"^(.+?):(\d+)(?::\d+)?: warning(?: (\d+))?: (.*)$")   # as fw_compile.WARN_RE


def log(s):
    _log_line(s, LOG)


def satisfied_rows(rows, warnings):
    """indexes of rows a real warning of the build already matches at the row's own line (they must not move)"""
    hit = set()
    for path, line, text in warnings:
        for i, row in enumerate(rows):
            c = row.split("\t")
            if len(c) > 3 and c[2] == line and re.search(c[0], text) and fnmatch.fnmatch(path, c[1]):
                hit.add(i)
    return hit


def _pair(cands, warns):
    """order-preserving assignment of rows to warnings: most pairs, then least total line distance.
    cands = [(row index, old line, compatible warning indexes)], warns = [new line]; returns {row index: warning index}"""
    n, m = len(cands), len(warns)
    best = {}                                    # (i, j) -> (-pairs, cost, choice) for cands[i:], warns[j:]

    def go(i, j):
        if i == n or j == m:
            return (0, 0)
        if (i, j) in best:
            return best[i, j][:2]
        opts = [go(i + 1, j), go(i, j + 1)]
        ch = [("skip_row", None), ("skip_warn", None)]
        if j in cands[i][2]:
            k, c = go(i + 1, j + 1)
            opts.append((k - 1, c + abs(cands[i][1] - warns[j])))
            ch.append(("pair", None))
        o = min(range(len(opts)), key=lambda x: opts[x])
        best[i, j] = (*opts[o], ch[o][0])
        return opts[o]

    sys.setrecursionlimit(max(1000, 4 * (n + m) + 100))
    go(0, 0)
    out, i, j = {}, 0, 0
    while i < n and j < m:
        how = best[i, j][2]
        if how == "pair":
            out[cands[i][0]] = j
            i, j = i + 1, j + 1
        elif how == "skip_row":
            i += 1
        else:
            j += 1
    return out


def renumber(rows, unreviewed, warnings=()):
    """(rows with moved lines, number moved, unmatched unreviewed warnings); rows matched by `warnings` stay"""
    keep = satisfied_rows(rows, warnings)
    rows = list(rows)
    left, done = [], 0
    for base in sorted({p.split("/")[-1] for p, _, _ in unreviewed}):
        ws = sorted(((int(ln), t, p) for p, ln, t in unreviewed if p.split("/")[-1] == base), key=lambda w: w[0])
        cands = []
        for i, row in enumerate(rows):
            c = row.split("\t")
            if len(c) > 3 and i not in keep and c[1].endswith(base) and c[2].isdigit():
                cands.append((i, int(c[2]), {j for j, (_, t, _) in enumerate(ws) if re.search(c[0], t)}))
        cands.sort(key=lambda x: x[1])
        got = _pair(cands, [w[0] for w in ws])
        for i, j in got.items():
            c = rows[i].split("\t")
            c[2] = str(ws[j][0])
            rows[i] = "\t".join(c)
            done += 1
        left += [f"{ws[j][2]}:{ws[j][0]}: {ws[j][1]}" for j in range(len(ws)) if j not in set(got.values())]
    return rows, done, left


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build_log", type=Path)
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ap.add_argument("--warnings", type=Path, nargs="*", help="all warnings of the build (default: tmp/sdcc-port/warnings-*.txt)")
    a = ap.parse_args()
    unreviewed = re.findall(r"WARN-GATE unreviewed: (.+?):(\d+): (.*)", a.build_log.read_text(errors="replace"))
    wf = a.warnings if a.warnings is not None else sorted((ROOT / "tmp/sdcc-port").glob("warnings-*.txt"))
    src = str(ROOT / "tmp/sdcc-port/src") + "/"
    warns = []
    for w in wf:
        for ln in w.read_text(errors="replace").splitlines():
            m = WARN_RE.match(ln)
            if m:
                warns.append((m.group(1).removeprefix(src), m.group(2), m.group(4)))
    rows, done, left = renumber(a.policy.read_text().split("\n"), unreviewed, warns)
    a.policy.write_text("\n".join(rows))
    log(f"{a.policy}: {done} of {len(unreviewed)} unreviewed warnings renumbered; {len(left)} need review")
    for x in left:
        log(f"  needs review: {x}")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
