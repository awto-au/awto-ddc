#!/usr/bin/env python3
"""Orphan scan of scripts/*.py (#304): module names referenced nowhere, or only from docs.

- Word-match of each module name over tracked text files, excluding fw/sdk, fw/sdk-parked, re/, debris/ and the file itself.
- "code" = dev.py, scripts/, tests/, tools/, fw/ (ours), systemd/, *.json/toml; "docs" = everything else.
- `./dev.py orphans` -> tmp/tmp_audit/orphans.tsv (status, script, bytes, last commit, refs); log tmp/logs/orphan_scripts.log.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import Logger
from _repo import ROOT

log = Logger(ROOT / "tmp/logs/orphan_scripts.log").say
TEXT = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".service", ".c", ".h", ".tsv", ".inc", ".txt", ".cfg", ".ini", ""}
SKIP = ("fw/sdk/", "fw/sdk-parked/", "re/", "debris/")
CODE = ("dev.py", "scripts/", "tests/", "tools/", "fw/", "systemd/", "pyproject.toml", ".github/")


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout


def main() -> int:
    files = [f for f in git("ls-files").splitlines() if not f.startswith(SKIP) and Path(f).suffix in TEXT]
    texts = {}
    for f in files:
        p = ROOT / f
        if p.is_file() and p.stat().st_size < 3_000_000:
            texts[f] = p.read_text(errors="ignore")
    rows = []
    for s in sorted((ROOT / "scripts").glob("*.py")):
        mod = s.stem
        if mod.startswith("_") or mod == "conftest":
            continue
        pat = re.compile(r"(?<![\w])" + re.escape(mod) + r"(?![\w])")
        refs = [f for f, t in texts.items() if f != f"scripts/{s.name}" and pat.search(t)]
        code = [f for f in refs if f.startswith(CODE)]
        status = "used" if code else "docs-only" if refs else "orphan"
        last = git("log", "-1", "--format=%cs", "--", f"scripts/{s.name}").strip()
        rows.append((status, f"scripts/{s.name}", s.stat().st_size, last, ",".join((code or refs)[:6])))
    out = ROOT / "tmp/tmp_audit/orphans.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        f.write("status\tscript\tbytes\tlast_commit\trefs\n")
        for r in sorted(rows):
            f.write("\t".join(map(str, r)) + "\n")
    n = {k: sum(r[0] == k for r in rows) for k in ("used", "docs-only", "orphan")}
    log(f"{len(rows)} scripts: {n['used']} used by code, {n['docs-only']} docs only, {n['orphan']} orphan; table {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
