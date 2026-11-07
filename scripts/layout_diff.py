#!/usr/bin/env python3
"""Diff two bank_layout.tsv files: symbols whose region (C = common / bank N) or kind changed.

Use: layout_diff.py OLD.tsv NEW.tsv [--names a,b,...]   (old/new may be `git show REV:fw/bank_layout.tsv` exports)
Log: tmp/logs/layout_diff.log
"""
import argparse, os, subprocess, sys
from pathlib import Path


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=Path(__file__).parent)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


def load(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) >= 4:
            rows[f[1]] = (f[0], f[2])  # name -> (kind, region)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--names", default="", help="comma list: report only these symbols")
    a = ap.parse_args()
    old, new = load(a.old), load(a.new)
    want = set(n for n in a.names.split(",") if n)
    out = []
    for n in sorted(set(old) | set(new)):
        if want and n not in want:
            continue
        o, w = old.get(n), new.get(n)
        if o != w:
            out.append(f"{n}\t{o[0] + ':' + o[1] if o else '-'}\t->\t{w[0] + ':' + w[1] if w else '-'}")
    to_c = sum(1 for n in new if new[n][1] == "C" and old.get(n, ("", ""))[1] != "C")
    from_c = sum(1 for n in old if old[n][1] == "C" and new.get(n, ("", ""))[1] != "C")
    out.append(f"# changed {len(out)}; into common {to_c}; out of common {from_c}")
    log = repo_root() / "tmp" / "logs" / "layout_diff.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(f"## {a.old} -> {a.new}\n" + "\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
