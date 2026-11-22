#!/usr/bin/env python3
"""Flash-sector churn probe: build, add one XDATA variable to one module, rebuild, count changed 4 KiB sectors (docs/flash-sector-churn.md).

usage: xdata_churn_probe.py [--unit 3] FILE[:BYTES] ... [--max N]
- Per FILE (repo-relative C file): `volatile __xdata unsigned char g_ucChurnProbe[BYTES];` appended after its first line, build, diff
  against the clean build with scripts/image_sector_diff.py; FILE edited back after each run. FAIL if changed > --max.
- Runs ./dev.py builds (~40 s each); fw/xdata_layout.tsv restored after each probe; fw/bank_layout.tsv left as built (git checkout it to discard).
Log: tmp/logs/xdata_churn_probe.log
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from _log import log_line as _log_line

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/xdata_churn_probe.log"
BUILD_LIMIT = 300         # s: build ~40 s warm, ~90 s cold (2026-11-19); 3x cold worst case, stall guard in dev.py


def say(s):
    _log_line(s, LOG)


def build(unit, tag) -> Path:
    r = subprocess.run([str(ROOT / "dev.py"), "build", "--unit", str(unit), "--tag", tag], capture_output=True, text=True,
                       timeout=BUILD_LIMIT, cwd=ROOT, check=False)
    if r.returncode:
        sys.exit(f"build {tag} failed:\n{(r.stdout + r.stderr)[-2000:]}")
    return next((ROOT / "tmp/fw").glob(f"*-{tag}-be.bin"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--max", type=int, default=20, help="sectors; doc target for a one-module change (docs/flash-sector-churn.md)")
    a = ap.parse_args()
    base = build(a.unit, "pb0")
    xl = ROOT / "fw/xdata_layout.tsv"
    xl0 = xl.read_text()                                    # every probe starts from the layout of the clean build
    fail = 0
    for i, t in enumerate(a.targets):
        f, _, n = t.partition(":")
        p = ROOT / f
        orig = p.read_text()
        lines = orig.splitlines(keepends=True)
        p.write_text("".join(lines[:1] + [f"volatile __xdata unsigned char g_ucChurnProbe[{int(n or 7)}];\n"] + lines[1:]))
        try:
            img = build(a.unit, f"pb{i + 1}")
        finally:
            p.write_text(orig)
            xl.write_text(xl0)
        out = subprocess.run([sys.executable, str(ROOT / "scripts/image_sector_diff.py"), str(base), str(img)], capture_output=True, text=True,
                             timeout=60, check=False).stdout
        ch = int(re.search(r"changed (\d+) / \d+", out).group(1))
        mv = re.search(r"data symbols: \d+ / \d+, moved (\d+)", out).group(1)
        say(f"{f} +{n or 7} B: {ch} sectors changed ({mv} data symbols moved){'' if ch <= a.max else f'  FAIL > {a.max}'}")
        fail += ch > a.max
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
