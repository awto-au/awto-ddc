#!/usr/bin/env python3
"""Remove merged / fully-twinned git worktrees. Dry-run by default; --apply acts.

Log: ./tmp/logs/worktree_sweep.log. Never force, never delete remote branches.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

MAIN = Path("/mnt/2tb/git/awto-ddc")
BASE = "origin/main"
KEEP_NAMES = {"awto-ddc-ports2", "awto-ddc-ports2-main", "awto-ddc-tmdsphy", "awto-ddc-s2b14"}
KEEP_SUFFIX = ("tmp/scratch/qcsim",)
HOT_BRANCHES = {"hot-data", "fix-340-hwtest-build", "conwrap-host-gate"}
APPROVED = {"audio-merged", "pacman-sound", "freeze-port-255"}  # Dan: remove despite unique work
GENERATED_TRACKED = {"fw/bank_layout.tsv"}
RECENT_S = 2 * 3600


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    return Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, check=True).stdout.strip())


ROOT = repo_root()
LOG = ROOT / "tmp/logs/worktree_sweep.log"


def log(msg: str) -> None:
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}\n")


def git(*args, cwd=MAIN):
    return subprocess.run(["git", *args], check=False, cwd=cwd, capture_output=True, text=True)


def parse():
    out, cur = [], {}
    for line in git("worktree", "list", "--porcelain").stdout.splitlines() + [""]:
        if not line:
            if cur:
                out.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        cur[k] = v
    return out


def du(path: str) -> int:
    r = subprocess.run(["du", "-sk", path], check=False, capture_output=True, text=True)
    return int(r.stdout.split()[0]) * 1024 if r.stdout else 0


def dirty(path: str):
    """Return (blocking, ignored) status lines."""
    blocking, ignored = [], []
    for ln in git("status", "--porcelain", "-uall", cwd=path).stdout.splitlines():
        code, p = ln[:2], ln[3:]
        if code == "??" and p.startswith("tmp/") or code.strip() == "M" and p in GENERATED_TRACKED:
            ignored.append(ln)
        else:
            blocking.append(ln)
    return blocking, ignored


def decide(wt):
    path = wt["worktree"]
    br = wt.get("branch", "").removeprefix("refs/heads/")
    ref = br or wt["HEAD"]
    name = Path(path).name
    if Path(path) == MAIN:
        return "KEEP", "main checkout", [], br
    if Path(path).resolve() == ROOT.resolve():
        return "KEEP", "running script's own worktree", [], br
    if "locked" in wt:
        return "KEEP", "locked", [], br
    if name in KEEP_NAMES or path.endswith(KEEP_SUFFIX):
        return "KEEP", "protected path", [], br
    if br in HOT_BRANCHES:
        return "KEEP", "hot branch", [], br
    if br.startswith("worktree-agent-"):
        adm = Path(git("rev-parse", "--git-dir", cwd=path).stdout.strip())
        age = time.time() - (adm / "gitdir").stat().st_mtime if (adm / "gitdir").exists() else 0
        if age < RECENT_S:
            return "KEEP", f"agent worktree {age/60:.0f} min old", [], br
    blocking, ignored = dirty(path)
    if blocking:
        return "KEEP", f"dirty: {blocking[:3]}", ignored, br
    anc = git("merge-base", "--is-ancestor", ref, BASE).returncode == 0
    plus = [ln for ln in git("cherry", BASE, ref).stdout.splitlines() if ln.startswith("+")]
    if anc:
        return "REMOVE", "ancestor of origin/main", ignored, br
    if not plus:
        return "REMOVE", "all commits have patch twin on main", ignored, br
    if br in APPROVED:
        return "REMOVE", f"approved by Dan ({len(plus)} unique commits dropped)", ignored, br
    return "KEEP", f"{len(plus)} unique commit(s) (git cherry +)", ignored, br


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    git("fetch", "-q", "origin")
    freed = 0
    rows = []
    for wt in parse():
        verdict, why, ignored, br = decide(wt)
        size = du(wt["worktree"])
        rows.append((verdict, wt["worktree"], br or "(detached)", why, ignored, size))
    for v, p, br, why, ign, size in rows:
        log(f"{v:6} {p} [{br}] {size/1e6:.0f}MB: {why}" + (f" | ignored: {ign}" if ign else ""))
    n = sum(r[0] == "REMOVE" for r in rows)
    log(f"{n} to remove, {len(rows)-n} kept, {sum(r[5] for r in rows if r[0]=='REMOVE')/1e6:.0f}MB")
    if not a.apply:
        log("dry-run; pass --apply")
        return 0
    for v, p, br, why, ign, size in rows:
        if v != "REMOVE":
            continue
        for ln in ign:  # approved discard of generated tracked file
            if ln[3:] in GENERATED_TRACKED:
                git("checkout", "--", ln[3:], cwd=p)
        r = git("worktree", "remove", p)
        if r.returncode:
            log(f"FAIL remove {p}: {r.stderr.strip()}")
            continue
        freed += size
        log(f"removed {p}")
        if br and br != "(detached)":
            r = git("branch", "-d", br)
            log(f"branch -d {br}: {(r.stdout + r.stderr).strip()}")
    log(f"freed ~{freed/1e6:.0f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
