#!/usr/bin/env python3
"""Audit / prune git branches (local + origin).

usage: branch_prune.py [--apply] [--keep NAME ...]
  Active = main, working-base, every branch checked out in a worktree, --keep.
  Others:
    contained  tip is an ancestor of main or working-base -> delete local + origin branch
    dead-end   not contained -> tag archive/<name> (pushed), then delete local + origin branch
  Branches only on origin are handled the same. Nothing is lost: contained commits live on, dead ends keep a tag.
  Without --apply: report only. Writes via gh_claudia (agent identity).
Log: ./tmp/logs/branch_prune.log
"""
import argparse, os, subprocess, sys
from datetime import datetime
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
GH = "/mnt/2tb/git/awto-dan/scripts/gh_claudia.py"
LOG = REPO / "tmp/logs/branch_prune.log"
ALWAYS = {"main", "working-base"}


def log(msg: str) -> None:
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}\n")


def git(*a: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=check)


def out(*a: str) -> list[str]:
    return [x for x in git(*a, check=True).stdout.splitlines() if x]


def gh(*a: str) -> bool:
    r = subprocess.run([GH, "git", *a], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        log(f"  FAILED git {' '.join(a)}: {r.stderr.strip()}")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep", nargs="*", default=[])
    a = ap.parse_args()
    git("fetch", "--prune", "-q", "origin")
    local = set(out("for-each-ref", "--format=%(refname:short)", "refs/heads"))
    remote = {r.removeprefix("origin/") for r in out("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
              if r not in ("origin", "origin/HEAD")}
    wt = {ln.removeprefix("branch refs/heads/") for ln in out("worktree", "list", "--porcelain") if ln.startswith("branch ")}
    active = ALWAYS | wt | set(a.keep)
    tip = {b: (f"refs/heads/{b}" if b in local else f"refs/remotes/origin/{b}") for b in local | remote}
    rows = []
    for b in sorted(local | remote - active):
        if b in active:
            continue
        holder = next((h for h in sorted(ALWAYS) if h in tip and          # only permanent branches count as holders
                       git("merge-base", "--is-ancestor", tip[b], tip[h]).returncode == 0), None)
        date = out("log", "-1", "--format=%cs", tip[b])[0]
        kind = f"contained in {holder}" if holder else "dead-end -> tag archive/" + b
        rows.append((b, date, kind))
        if not a.apply:
            continue
        if not holder:
            sha = out("rev-parse", tip[b])[0]
            if not (gh("tag", "-f", f"archive/{b}", sha) and gh("push", "-f", "origin", f"refs/tags/archive/{b}")):
                continue
        if b in remote and not gh("push", "origin", "--delete", b):
            continue
        if b in local:
            gh("branch", "-D", b)
    for b, d, k in rows:
        log(f"{b:<40} {d}  {k}")
    log(f"DONE: {len(active)} active ({', '.join(sorted(active))}); {len(rows)} other: "
        f"{sum('contained' in r[2] for r in rows)} contained, {sum('dead-end' in r[2] for r in rows)} dead-end"
        f"{' -- applied' if a.apply else ' -- report only'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
