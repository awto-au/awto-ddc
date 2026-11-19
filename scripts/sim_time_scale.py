#!/usr/bin/env python3
"""Sim-only test-timing scale: a copy of the production image whose monitor sample period is 1/N (tests, not a firmware build option).

Why not a -D build: the NORMAL gates run against the image under test (the one that gets flashed); a scaled build would be a second
full build (a -D change rebuilds every TU, 40-90 s). Here the production image stays byte-identical and the SIM runs a patched copy.
How: AwtoDiagMainPass compares (usNow - usLastMon) >= AWTO_MON_MS as `subb a,#lo ... subb a,#hi`; the two immediates are rewritten.
Exactly one match inside the function or the patch refuses (nothing guessed). The monitor logic is unchanged: only the period differs.

usage: sim_time_scale.py BIN MAP --scale N --out PATCHED.bin      (prints the new period in ms)
Proof the scale changes durations only: tests/test_time_scale.py (same sample / row sequence at scale 1 and N).
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
FN = "AwtoDiagMainPass"
FN_SPAN = 0x150          # bytes searched from the function entry (the function is 0x142 long)


def define(name: str) -> int:
    return int(re.search(rf"^#define\s+{name}\s+(\d+)", HDR.read_text(), re.M).group(1))


def patch_monitor(img: bytes, map_text: str, scale: int) -> tuple[bytes, int]:
    """-> (patched image, new period ms). Big-endian image (subb a,#lo first, then subb a,#hi)."""
    ms = define("AWTO_MON_MS")
    new = max(1, ms // scale)
    m = re.search(rf"^C:\s+([0-9A-F]{{8}})\s+_{FN}\b", map_text, re.M)
    if not m:
        raise SystemExit(f"{FN} not in the map")
    a = int(m.group(1), 16)
    want = bytes([0x94, ms & 0xFF, 0xEC, 0x94, ms >> 8])          # subb a,#lo ; mov a,r4 (ec) ; subb a,#hi
    hits = [i for i in range(a, a + FN_SPAN) if img[i:i + len(want)] == want]
    if len(hits) != 1:
        raise SystemExit(f"monitor period compare: {len(hits)} matches of {want.hex()} in {FN} (want exactly 1); image not patched")
    out = bytearray(img)
    i = hits[0]
    out[i + 1], out[i + 4] = new & 0xFF, new >> 8
    return bytes(out), new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--scale", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    img, ms = patch_monitor(a.bin.read_bytes(), a.map.read_text(errors="replace"), a.scale)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(img)
    print(f"{a.out}: monitor period {define('AWTO_MON_MS')} -> {ms} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
