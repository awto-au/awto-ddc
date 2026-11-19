#!/usr/bin/env python3
"""Review every git worktree of a repo (read only): merged into main? ahead / behind? dirty? age?

usage: worktree_review.py [REPO ...]   (default: /mnt/2tb/git/awto-ddc)
  Per worktree: path, branch (or detached sha), last commit date + subject, ahead / behind main, tracked changes, untracked files,
  class: MERGED (HEAD is an ancestor of main, clean: removable), MERGED-DIRTY (merged but local changes), AHEAD (commits not in
  main), DETACHED (no branch), MISSING (directory gone: `git worktree prune`).
  "ahead" counts commits not in main by patch id (`git cherry`), so a rebased / squash-free copy of a merged commit is not counted.
Output: ./tmp/worktree_review.tsv + ./tmp/logs/worktree_review.log
"""
import subprocess
import sys
from pathlib import Path

import isostamp

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/worktree_review.log"
OUT = ROOT / "tmp/worktree_review.tsv"
GIT_S = 20          # one git status on the largest tree takes ~2 s (2026-11-16); 10x margin, expiry = row marked TIMEOUT


def git(cwd: str, *a: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, timeout=GIT_S)
    except subprocess.TimeoutExpired:
        return 124, ""
    return p.returncode, p.stdout.strip()


def worktrees(repo: str) -> list[dict]:
    out, cur = [], {}
    for ln in git(repo, "worktree", "list", "--porcelain")[1].splitlines() + [""]:
        if not ln:
            if cur:
                out.append(cur)
            cur = {}
        elif " " in ln:
            k, v = ln.split(" ", 1)
            cur[k] = v
        else:
            cur[ln] = ""
    return out


def review(repo: str) -> list[list[str]]:
    rows = []
    for w in worktrees(repo):
        path = w["worktree"]
        branch = w.get("branch", "").replace("refs/heads/", "") or "(detached)"
        if not Path(path).is_dir():
            rows.append([Path(repo).name, path, branch, "", "", "", "", "", "", "MISSING"])
            continue
        rc, date = git(path, "log", "-1", "--format=%cs|%s")
        d, subj = (date.split("|", 1) + [""])[:2]
        _, cher = git(path, "cherry", "main", "HEAD")
        ahead = sum(1 for ln in cher.splitlines() if ln.startswith("+"))
        _, behind = git(path, "rev-list", "--count", "HEAD..main")
        _, st = git(path, "status", "--porcelain")
        tracked = sum(1 for ln in st.splitlines() if not ln.startswith("??"))
        untracked = sum(1 for ln in st.splitlines() if ln.startswith("??"))
        if path == repo:
            cls = "MAIN"
        elif branch == "(detached)" and ahead == 0 and not tracked:
            cls = "MERGED" if not untracked else "MERGED-DIRTY"
        elif branch == "(detached)":
            cls = "DETACHED"
        elif ahead == 0 and tracked == 0:
            cls = "MERGED" if untracked == 0 else "MERGED-DIRTY"
        elif ahead == 0:
            cls = "MERGED-DIRTY"
        else:
            cls = "AHEAD"
        rows.append([Path(repo).name, path, branch, d, subj[:70], str(ahead), behind, str(tracked), str(untracked), cls])
    return rows


def main() -> int:
    repos = sys.argv[1:] or ["/mnt/2tb/git/awto-ddc"]
    rows = []
    for r in repos:
        rows += review(r)
    head = ["repo", "path", "branch", "last", "subject", "ahead", "behind", "tracked_changes", "untracked", "class"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join("\t".join(x) for x in [head] + rows) + "\n")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    cnt = {}
    for r in rows:
        cnt[(r[0], r[-1])] = cnt.get((r[0], r[-1]), 0) + 1
    with LOG.open("a") as f:
        f.write(f"{isostamp.now()} {len(rows)} worktrees: {cnt} -> {OUT}\n")
    print(f"{len(rows)} worktrees: {cnt}\n{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
