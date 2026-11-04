#!/usr/bin/env python3
"""Show byte offsets in the settings area (default 0xFB000-0xFD000) that differ between dumps.

usage: rtd_settings_diff.py <dump_a> <dump_b> [<dump_c> ...] [--start 0xFB000 --end 0xFD000]
Prints offset and the value in each dump. Use dumps taken with known differing settings
(e.g. brightness 80 vs 100) to locate the settings bytes. Log: ./tmp/logs/rtd_settings_diff.log
"""
import os, sys
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opt = lambda k, d: int(sys.argv[sys.argv.index(k) + 1], 0) if k in sys.argv else d
start, end = opt("--start", 0xFB000), opt("--end", 0xFD000)
paths = [p for p in args if p.endswith(".bin")]
blobs = [Path(p).read_bytes() for p in paths]
root = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
(root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
log = (root / "tmp" / "logs" / "rtd_settings_diff.log").open("w")

def out(s):
    print(s); log.write(s + "\n")

out("# " + "  ".join(f"{i}={Path(p).name}" for i, p in enumerate(paths)))
n = 0
for o in range(start, end):
    vals = [b[o] for b in blobs]
    if len(set(vals)) > 1:
        n += 1
        out(f"0x{o:06x}  " + " ".join(f"{v:02x}" for v in vals))
out(f"# {n} differing bytes in 0x{start:x}-0x{end:x}")
