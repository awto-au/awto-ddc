#!/usr/bin/env python3
"""Compare two osd_catalog.py output directories pixel for pixel: prints the screen names that differ.

usage: screens_diff.py DIR_A DIR_B [--ignore NAME ...]
- Screens = the per-screen PNGs in each directory (index/sheet/crop images are skipped); a screen in one directory only counts as differing.
- Exit 0 = every screen identical, 1 = differences. Regression tool for removals (#122, #137).
Log: ./tmp/logs/screens_diff.log
"""
import argparse
import sys
from pathlib import Path

import isostamp
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp" / "logs" / "screens_diff.log"
SKIP = {"sheet"}


def screens(d: Path) -> dict:
    return {p.stem: p for p in sorted(d.glob("*.png")) if p.stem not in SKIP and "_crop" not in p.stem}


def same(a: Path, b: Path) -> bool:
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    return ia.size == ib.size and ImageChops.difference(ia, ib).getbbox() is None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--ignore", nargs="*", default=[])
    a = ap.parse_args()
    sa, sb = screens(a.a), screens(a.b)
    bad = []
    for name in sorted(set(sa) | set(sb)):
        if name in a.ignore:
            continue
        if name not in sa or name not in sb:
            bad.append(f"{name} (only in {'B' if name in sb else 'A'})")
        elif not same(sa[name], sb[name]):
            bad.append(name)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    msg = f"{isostamp.now()} screens_diff {a.a} vs {a.b}: {len(set(sa) | set(sb))} screens, {len(bad)} differ: {', '.join(bad) or 'none'}"
    print(msg)
    with LOG.open("a") as f:
        f.write(msg + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
