#!/usr/bin/env python3
"""tmp/ audit (read-only): per entry size, newest mtime, and who cites it (code / docs / GitHub issues).

- `./dev.py tmp-audit [--tree <repo checkout>] [--sub scratch] [--refresh]`; default tree = this one.
- Code/docs corpus = this tree's tracked files; issues = bodies + comments, cached 1 day in tmp/tmp_audit/gh.jsonl.
- TSV: tmp/tmp_audit/<tree>-<sub>.tsv; log: tmp/logs/tmp_audit.log. Deletes nothing.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import Logger
from _repo import ROOT

OUT = ROOT / "tmp/tmp_audit"
log = Logger(ROOT / "tmp/logs/tmp_audit.log").say
GH_REPO = "awto-au/awto-ddc"
CACHE_S = 24 * 3600          # issue text changes slowly; a day-old cache is fine for an audit
HAND = {".md", ".txt", ".py", ".c", ".h", ".s", ".asm", ".json", ".tsv", ".csv"}
CODE_DIRS = ("scripts/", "dev.py", "fw/", "tests/", "tools/", "systemd/")


def gh_corpus(refresh: bool) -> list[tuple[str, str]]:
    cache = OUT / "gh.jsonl"
    if refresh or not cache.is_file() or time.time() - cache.stat().st_mtime > CACHE_S:
        rows = []
        for path, num in ((f"repos/{GH_REPO}/issues?state=all&per_page=100", ".number"),
                          (f"repos/{GH_REPO}/issues/comments?per_page=100", '(.issue_url|split("/")|last)')):
            r = subprocess.run(["gh", "api", "--paginate", path, "--jq", f'.[] | [{num}, .body // ""] | @json'],
                               capture_output=True, text=True, check=True)
            rows += [json.loads(ln) for ln in r.stdout.splitlines()]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("".join(json.dumps(x) + "\n" for x in rows))
        log(f"gh: {len(rows)} issue bodies + comments fetched")
    return [(f"#{n}", b) for n, b in (json.loads(ln) for ln in cache.read_text().splitlines())]


def file_corpus() -> list[tuple[str, str]]:
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    out = []
    for f in files:
        p = ROOT / f
        if f.startswith(("fw/rtdfw/", "re/regdb/")) or not p.is_file() or p.stat().st_size > 4_000_000:
            continue
        try:
            out.append((f, p.read_text(errors="ignore")))
        except OSError:
            pass
    return out


def scan(entry: Path) -> tuple[int, int, float, int]:
    size = files = hand = 0
    newest = entry.lstat().st_mtime
    for d, dirs, fs in os.walk(entry) if entry.is_dir() else [(str(entry.parent), [], [entry.name])]:
        for f in fs:
            try:
                st = os.lstat(os.path.join(d, f))
            except OSError:
                continue
            size += st.st_size
            files += 1
            newest = max(newest, st.st_mtime)
            hand += Path(f).suffix.lower() in HAND
    return size, files, newest, hand


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--sub", default="", help="audit tmp/<sub>/* instead of tmp/*")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    base = a.tree / "tmp" / a.sub
    prefix = "tmp/" + (a.sub.strip("/") + "/" if a.sub else "")
    pat = re.compile(re.escape(prefix) + r"([\w.+\-]+)")
    refs: dict[str, dict[str, set]] = defaultdict(lambda: {"code": set(), "docs": set(), "gh": set()})
    for src, text in file_corpus():
        kind = "code" if src.startswith(CODE_DIRS) else "docs"
        for m in pat.finditer(text):
            refs[m.group(1)][kind].add(src)
    for src, text in gh_corpus(a.refresh):
        for m in pat.finditer(text):
            refs[m.group(1)]["gh"].add(src)
    rows = []
    for e in sorted(base.iterdir()):
        size, files, newest, hand = scan(e)
        r = refs.get(e.name) or refs.get(e.stem) or {"code": set(), "docs": set(), "gh": set()}
        rows.append((size, e.name, files, hand, time.strftime("%Y-%m-%d", time.localtime(newest)),
                     ",".join(sorted(r["code"]))[:200], ",".join(sorted(r["docs"]))[:200],
                     ",".join(sorted(r["gh"], key=lambda s: int(s[1:]))) if r["gh"] else ""))
    rows.sort(reverse=True)
    OUT.mkdir(parents=True, exist_ok=True)
    tsv = OUT / f"{a.tree.name}-{a.sub.replace('/', '_') or 'top'}.tsv"
    with tsv.open("w") as f:
        f.write("bytes\tentry\tfiles\thand_suffix_files\tnewest\tcode_refs\tdoc_refs\tissue_refs\n")
        for row in rows:
            f.write("\t".join(map(str, row)) + "\n")
    log(f"{base}: {len(rows)} entries, {sum(r[0] for r in rows)/1e9:.2f} GB; "
        f"{sum(1 for r in rows if r[5] or r[6] or r[7])} cited; table {tsv.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
