#!/usr/bin/env python3
"""Code / XDATA size difference between two firmware .map files (sdld area table), per area and in total.

usage: map_size_diff.py OLD.map NEW.map [--min 1]
- Areas: CH_<fn> (code + consts chunk per function, sdcc_bank.py), ST_<fn> (bank stub, 8 B), XSEG* / XISEG (XDATA).
- Prints changed areas (new, gone, size delta >= --min) and totals per kind.
Log: tmp/logs/map_size_diff.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

AREA = re.compile(r"^([A-Za-z_][\w]*)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+(\d+)\. bytes", re.M)


def areas(path: Path) -> dict:
    return {m.group(1): int(m.group(4)) for m in AREA.finditer(path.read_text(errors="replace"))}


def kind(name: str) -> str:
    if name.startswith("CH_"):
        return "code (CH_)"
    if name.startswith("ST_"):
        return "stubs (ST_)"
    if name.startswith(("XSEG", "XISEG")):
        return "xdata"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--min", type=int, default=1, help="smallest |delta| listed")
    a = ap.parse_args()
    old, new = areas(a.old), areas(a.new)
    out = [f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {a.old} -> {a.new}"]
    tot = {}
    for n in sorted(set(old) | set(new)):
        o, w = old.get(n, 0), new.get(n, 0)
        k = kind(n)
        to, tw = tot.get(k, (0, 0))
        tot[k] = (to + o, tw + w)
        if abs(w - o) >= a.min:
            tag = "new" if n not in old else ("gone" if n not in new else "")
            out.append(f"  {n:<40} {o:>6} -> {w:>6}  {w - o:+6d} {tag}")
    for k, (o, w) in sorted(tot.items()):
        out.append(f"total {k:<12} {o:>8} -> {w:>8}  {w - o:+7d}")
    text = "\n".join(out)
    print(text)
    log = repo_root() / "tmp/logs/map_size_diff.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
