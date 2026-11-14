#!/usr/bin/env python3
"""Renumber fw/warn_policy.tsv rows whose file:line moved after code was inserted into a ported SDK file.

usage: warn_policy_renum.py BUILD_LOG [--policy PATH]
  BUILD_LOG = a wb_build log with `WARN-GATE unreviewed: FILE:LINE: TEXT` lines (tmp/logs/build_<tag>_<serial>.out in the tree).
  Each unreviewed warning is matched to the policy row of the same file whose pattern matches the text and whose line is nearest;
  that row's line number is rewritten. Warnings with no matching row are listed and left alone (they need a real review).
Log: tmp/logs/warn_policy_renum.log
"""
import argparse
import re
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/warn_policy_renum.log"
DEFAULT_POLICY = Path("/mnt/2tb/git/awto-ddc-ui/fw/warn_policy.tsv")


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build_log", type=Path)
    ap.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    a = ap.parse_args()
    unreviewed = re.findall(r"WARN-GATE unreviewed: (.+?):(\d+): (.*)", a.build_log.read_text(errors="replace"))
    rows = a.policy.read_text().split("\n")
    used, done, left = set(), 0, []
    for path, line, text in unreviewed:
        cand = []
        for i, row in enumerate(rows):
            c = row.split("\t")
            if len(c) > 3 and c[1].endswith(path.split("/")[-1]) and c[2].isdigit() and i not in used and re.search(c[0], text):
                cand.append((abs(int(c[2]) - int(line)), i))
        if not cand:
            left.append(f"{path}:{line}: {text}")
            continue
        _, i = min(cand)
        c = rows[i].split("\t")
        c[2] = line
        rows[i] = "\t".join(c)
        used.add(i)
        done += 1
    a.policy.write_text("\n".join(rows))
    log(f"{a.policy}: {done} of {len(unreviewed)} unreviewed warnings renumbered; {len(left)} need review")
    for x in left:
        log(f"  needs review: {x}")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
