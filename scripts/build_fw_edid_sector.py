#!/usr/bin/env python3
"""Build the one per-monitor sector applied after a shared firmware image.

The AWTO firmware keeps its three served EDIDs (DP, HDMI 1, HDMI 2) as
256-byte code tables.  This tool finds those tables in a complete firmware
image and emits:

* the unmodified 4 KiB sector expected immediately after the shared image is
  flashed; and
* the same sector with only the three EDID tables replaced for one serial.

Nothing is written to hardware here.  ``dev.py deploy`` passes both files to
the guarded sector writer.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_edid import build  # noqa: E402

EDID_HEADER = bytes.fromhex("00ffffffffffff00")
EDID_SIZE = 256
SECTOR_SIZE = 4096


def edid_offsets(image: bytes) -> list[int]:
    # Arbitrary firmware data (notably packed OSD glyphs) can contain the
    # eight-byte EDID header by chance.  Count only complete EDID 1.3/1.4
    # tables whose base and extension blocks both have valid checksums.
    offsets = [
        i for i in range(len(image) - EDID_SIZE + 1)
        if image.startswith(EDID_HEADER, i)
        and (image[i + 18], image[i + 19]) in ((1, 3), (1, 4))
        and sum(image[i:i + 128]) % 256 == 0
        and sum(image[i + 128:i + EDID_SIZE]) % 256 == 0
    ]
    if len(offsets) != 3:
        raise ValueError(f"shared image must contain exactly 3 EDID tables; found {len(offsets)}")
    if len({i // SECTOR_SIZE for i in offsets}) != 1:
        raise ValueError("the 3 EDID tables do not occupy one 4 KiB sector")
    if any(i + EDID_SIZE > len(image) for i in offsets):
        raise ValueError("truncated EDID table in image")
    versions = [(image[i + 18], image[i + 19]) for i in offsets]
    if versions.count((1, 4)) != 1 or versions.count((1, 3)) != 2:
        raise ValueError(f"expected one DP EDID 1.4 and two HDMI EDID 1.3 tables; found {versions}")
    return offsets


def build_sectors(image: bytes, serial: str) -> tuple[int, bytes, bytes]:
    offsets = edid_offsets(image)
    base = (offsets[0] // SECTOR_SIZE) * SECTOR_SIZE
    expected = image[base:base + SECTOR_SIZE]
    if len(expected) != SECTOR_SIZE:
        raise ValueError("EDID sector is truncated in image")
    patched = bytearray(expected)
    for off in offsets:
        version = (image[off + 18], image[off + 19])
        port = "dp" if version == (1, 4) else "hdmi"
        replacement = build(port, serial)
        rel = off - base
        patched[rel:rel + EDID_SIZE] = replacement
    return base, expected, bytes(patched)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--out", required=True, type=Path, help="per-monitor sector output")
    ap.add_argument("--expect-out", required=True, type=Path,
                    help="unmodified sector from the shared image")
    a = ap.parse_args()
    try:
        addr, expected, patched = build_sectors(a.image.read_bytes(), a.serial)
    except (OSError, ValueError, AssertionError) as e:
        ap.error(str(e))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.expect_out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(patched)
    a.expect_out.write_bytes(expected)
    changed = sum(x != y for x, y in zip(expected, patched))
    print(f"sector=0x{addr:x} serial={a.serial} changed={changed} bytes")
    print(f"expected: {a.expect_out}")
    print(f"patched:  {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
