#!/usr/bin/env python3
"""Follow fw/warn_policy.tsv line numbers through a source edit (#209): a row's site moves with its source line.

usage: warn_rekey.py [--base REV] [--policy fw/warn_policy.tsv] [--write]
  For every row with a numeric line: the line's text in REV (default HEAD) is looked up in the working-tree file;
  the identical line nearest the old position (same previous line preferred) becomes the new number.
  Rows whose line is gone are reported, not removed: the next build + warn_policy_check.py --prune drops them.
  Without --write: report only. Files: <glob> under fw/sdk/, else under the repo root (src-relative, as fw_compile).
Log: ./tmp/logs/warn_rekey.log
"""
import argparse, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/warn_rekey.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s)


def resolve(glob: str) -> Path | None:
    for p in (ROOT / "fw/sdk" / glob, ROOT / glob):
        if p.is_file():
            return p
    return None


def old_lines(rev: str, p: Path, cache: dict) -> list[str] | None:
    rel = p.relative_to(ROOT).as_posix()
    if rel not in cache:
        r = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=ROOT, capture_output=True, timeout=30)
        cache[rel] = r.stdout.decode(errors="replace").splitlines() if r.returncode == 0 else None
    return cache[rel]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--policy", type=Path, default=ROOT / "fw/warn_policy.tsv")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    rows = a.policy.read_text().splitlines()
    old_cache, new_cache, moved, gone = {}, {}, 0, 0
    for i, row in enumerate(rows):
        c = row.split("\t")
        if row.startswith("#") or len(c) < 4 or not c[2].isdigit():
            continue
        p = resolve(c[1])
        n = int(c[2])
        if p is None:
            say(f"row {i + 1}: {c[1]}: file gone"); gone += 1; continue
        ol = old_lines(a.base, p, old_cache)
        if ol is None or n > len(ol):
            continue                                  # new file or line past the old end: nothing to follow
        new = new_cache.setdefault(p, p.read_text(errors="replace").splitlines())
        if n <= len(new) and new[n - 1] == ol[n - 1]:
            continue                                  # unchanged position
        text, prev = ol[n - 1], (ol[n - 2] if n > 1 else None)
        hits = [k + 1 for k, t in enumerate(new) if t == text]
        if not hits:
            say(f"row {i + 1}: {c[1]}:{n}: line gone ({text.strip()[:60]!r})"); gone += 1; continue
        same_prev = [h for h in hits if h > 1 and new[h - 2] == prev]
        best = min(same_prev or hits, key=lambda h: abs(h - n))
        say(f"row {i + 1}: {c[1]}:{n} -> {best}")
        c[2] = str(best)
        rows[i] = "\t".join(c)
        moved += 1
    if a.write and moved:
        a.policy.write_text("\n".join(rows) + "\n")
    say(f"{moved} rows moved, {gone} rows whose line is gone{'' if a.write else ' (report only: --write to apply)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
