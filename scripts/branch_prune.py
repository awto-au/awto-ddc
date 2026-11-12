#!/usr/bin/env python3
"""Delete fully merged local branches (branch_status.py 'merged': no commit outside wb-p14ui / main) and their worktrees.

usage: branch_prune.py [--keep BRANCH ...] [--dry-run]
- Worktree folders are MOVED to the machine wastebasket /mnt/2tb/wastebasket/awto-ddc-worktrees-<stamp>/ (recoverable;
  their tmp/ holds images and logs), then `git worktree prune`, then `git branch -D` (only branches re-checked as merged).
- --keep: branches of running agents. The base and main branches are never touched.
Log: tmp/logs/branch_prune.log
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import branch_status as S  # noqa: E402

LOG = S.REPO / "tmp/logs/branch_prune.log"
BIN = Path("/mnt/2tb/wastebasket")


def log(s: str) -> None:
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def merged() -> list[tuple[str, str]]:
    out = subprocess.run([sys.executable, str(Path(__file__).with_name("branch_status.py"))], capture_output=True,
                         text=True, check=True).stdout.splitlines()[1:]
    return [(c[3], c[4]) for c in (ln.split("\t") for ln in out) if c[0] == "merged"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    dest = BIN / f"awto-ddc-worktrees-{time.strftime('%Y%m%d-%H%M%S')}"
    for b, wt in merged():
        if b in a.keep:
            log(f"keep {b} ({wt})")
            continue
        if wt != "-" and Path(wt).resolve() == S.REPO.resolve():
            log(f"skip {b}: checked out in the main worktree")
            continue
        if a.dry_run:
            log(f"would delete {b} (worktree {wt})")
            continue
        if wt != "-":
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(wt, dest / Path(wt).name)
            log(f"worktree {wt} -> {dest / Path(wt).name}")
    if not a.dry_run:
        S.git("worktree", "prune")
        for b, wt in merged():
            if b in a.keep or (wt != "-" and Path(wt).exists()):
                continue
            S.git("branch", "-D", b)               # -d only knows HEAD (main); 'merged' was proven against base + main
            log(f"branch {b} deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
