#!/usr/bin/env python3
"""Which local branches still carry work: commits not in the firmware line (wb-p14ui) and not in main.

usage: branch_status.py [--base wb-p14ui] [--main main]
- Per branch: ahead of base / ahead of main (commits not reachable from either), last commit date + subject, worktree.
- 'merged' = nothing outside base or main (safe to delete); 'open' = has unmerged commits.
Log: tmp/logs/branch_status.log
"""
import argparse
import subprocess
import time
from pathlib import Path


def _repo() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


REPO = _repo()
LOG = REPO / "tmp/logs/branch_status.log"


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="wb-p14ui")
    ap.add_argument("--main", default="main")
    a = ap.parse_args()
    wt = {}
    cur = None
    for ln in git("worktree", "list", "--porcelain").splitlines():
        if ln.startswith("worktree "):
            cur = ln.split(" ", 1)[1]
        elif ln.startswith("branch refs/heads/"):
            wt[ln[len("branch refs/heads/"):]] = cur
    rows = []
    for b in git("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines():
        if b in (a.base, a.main):
            continue
        n = int(git("rev-list", "--count", b, "--not", a.base, a.main))
        date, subj = git("log", "-1", "--format=%cs%x09%s", b).split("\t", 1)
        rows.append((n, date, b, subj[:70], wt.get(b, "-")))
    rows.sort(key=lambda r: (r[0] == 0, r[1]), reverse=False)
    out = [f"{'open' if n else 'merged'}\t{n}\t{d}\t{b}\t{w}\t{s}" for n, d, b, s, w in
           sorted(rows, key=lambda r: (r[0] == 0, [-ord(c) for c in r[1]]))]
    text = "\n".join(["state\tunmerged\tdate\tbranch\tworktree\tlast subject", *out])
    print(text)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + f" base {a.base} main {a.main}\n{text}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
