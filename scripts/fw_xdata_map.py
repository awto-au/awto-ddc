#!/usr/bin/env python3
"""Histogram of XDATA addresses an 8051 firmware image references via `MOV DPTR,#imm16` (opcode 0x90).

usage: fw_xdata_map.py <image.bin> [--banks N] [--bucket 0x100]
- Scans code banks (64 KB each, default 7 = old JXC fw banks 0-6) byte-wise; 0x90 hits inside data tables
  add noise, so read the result as a density map, not an exact list.
- Prints per-bucket hit counts for 0xC000-0xFFFF (XRAM candidates + MCU XFR) and the lowest/highest
  densely-used RAM address. Question answered: how much XRAM does the shipped firmware actually use (#8).
Log: tmp/logs/fw_xdata_map.log
"""
import os, subprocess, sys, time
import isostamp  # noqa: E402
from collections import Counter
from pathlib import Path


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 2
    img = Path(a[0]).read_bytes()
    banks = int(a[a.index("--banks") + 1]) if "--banks" in a else 7
    bucket = int(a[a.index("--bucket") + 1], 0) if "--bucket" in a else 0x100
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/fw_xdata_map.log").open("a")

    def out(s):
        print(s); log.write(s + "\n")
    out(f"{isostamp.now()} {a[0]} banks={banks}")
    hits = Counter()
    end = min(len(img), banks * 0x10000)
    for i in range(end - 2):
        if img[i] == 0x90:
            addr = (img[i + 1] << 8) | img[i + 2]
            hits[addr] += 1
    buckets = Counter()
    for addr, n in hits.items():
        if addr >= 0xC000:
            buckets[addr // bucket * bucket] += n
    for b in sorted(buckets):
        out(f"  0x{b:04X}-0x{b + bucket - 1:04X} {buckets[b]:6d} {'#' * min(60, buckets[b] // 10)}")
    ram = [addr for addr, n in hits.items() if 0xC000 <= addr < 0xFB00 and n >= 2]
    if ram:
        out(f"RAM-range refs (>=2 hits, 0xC000-0xFAFF): lowest 0x{min(ram):04X} highest 0x{max(ram):04X}, "
            f"{len(ram)} distinct addresses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
