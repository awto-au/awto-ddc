#!/usr/bin/env python3
"""List / remove git worktrees that hold nothing unsaved.

usage: worktree_prune.py [--remove] [--keep NAME ...]
  Per worktree: branch, dirty files (excluding tmp/), commits not on any remote, last commit date.
  Removable = clean + every commit on a remote + not in --keep + not locked. Branches are kept (only the checkout goes).
  Before removing, its tmp/fw images are archived (fw_archive.py) so no built image is lost.
  Without --remove: report only.
Log: ./tmp/logs/worktree_prune.log
"""
import argparse, os, subprocess, sys
from datetime import datetime
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = REPO / "tmp/logs/worktree_prune.log"


def log(msg: str) -> None:
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}\n")


def git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True).stdout.strip()


def worktrees() -> list[dict]:
    out, cur = [], {}
    for ln in git(REPO, "worktree", "list", "--porcelain").splitlines() + [""]:
        if not ln:
            if cur:
                out.append(cur)
            cur = {}
        else:
            k, _, v = ln.partition(" ")
            cur[k] = v or True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--keep", nargs="*", default=[], help="worktree dir names or branch names to keep")
    a = ap.parse_args()
    rows, gone = [], 0
    for w in worktrees()[1:]:                                   # [0] is the main checkout
        p = Path(w["worktree"])
        br = str(w.get("branch", "(detached)")).removeprefix("refs/heads/")
        dirty = [ln for ln in git(p, "status", "--porcelain").splitlines() if not ln[3:].startswith("tmp/")]
        unpushed = git(p, "rev-list", "--count", "HEAD", "--not", "--remotes")
        date = git(p, "log", "-1", "--format=%cs")
        keep = p.name in a.keep or br in a.keep or "locked" in w
        why = "locked" if "locked" in w else "kept" if keep else f"{len(dirty)} dirty" if dirty \
            else f"{unpushed} unpushed" if unpushed not in ("", "0") else ""
        rows.append((p.name, br, date, why or "removable"))
        if not why and a.remove:
            bins = [str(b) for b in (p / "tmp/fw").glob("*.bin")]
            if bins:                                            # no args would make fw_archive scan every worktree
                subprocess.run([sys.executable, str(REPO / "scripts/fw_archive.py"), *bins], cwd=REPO, check=True)
            r = subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(p)], capture_output=True, text=True)
            gone += r.returncode == 0
            log(f"removed {p} ({br})" if r.returncode == 0 else f"FAILED remove {p}: {r.stderr.strip()}")
    for r in rows:
        log("  ".join(f"{c:<34}" if i < 2 else c for i, c in enumerate(r)))
    log(f"DONE: {len(rows)} worktrees, {sum(r[3] == 'removable' for r in rows)} removable, {gone} removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
