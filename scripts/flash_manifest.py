#!/usr/bin/env python3
"""On-device flash manifest (docs/flash-registry.md): one CRC32 per image sector, kept in flash sector 0xFD000.

usage: flash_manifest.py build <image.bin> [--out SECTOR.bin]          the 4 KiB manifest sector for an image
       flash_manifest.py check <flash-dump.bin | sector.bin> [--image image.bin]
                                                                       parse + verify (vs the image: per-sector match)
Offline only: reading the device goes through rtd_flash_image.py (ISP halts the MCU).

CRC-32/ISO-HDLC (zlib.crc32): poly 0x04C11DB7 reflected 0xEDB88320, init 0xFFFFFFFF, refin/refout, xorout 0xFFFFFFFF,
check("123456789") = 0xCBF43926; stored little endian. Firmware can compute it bytewise with a 16-entry table.

Layout (4 KiB sector, 0xFF = erased):
  0x000  magic "AWFM", version u8, flags u8 (0), count u16, image_id u32 (first 4 B of the image SHA-256), reserved u32 (0)
  0x010  CRC32 of sector 0..count-1 of the image, 4 B each; the word at 0x200 is skipped (stays 0xFF): the retired
         nvram.c record log (fw/rtdfw/awto/nvram/nvram.c) scans 512 B slots for the magic byte 0xA7 at 0x000 / 0x200 ..
  0xF00  commit page, programmed LAST: "AWOK" + CRC32 over [0x000, 0x400). Erased / torn commit = invalid.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

SECTOR = 4096
PAGE = 256
MANIFEST_ADDR = 0xFD000                 # retired registry record sector (docs/flash-registry.md: unused by firmware)
SPARE_ADDR = 0xFE000                    # kept free (alternation / self-flash T1)
MAGIC, VALID = b"AWFM", b"AWOK"
VERSION = 1
HEADER = 0x10
TABLE_AT = HEADER
SKIP_AT = 0x200                         # word never used: erased 0xFF at the legacy log's slot boundary
BODY_END = 0x400                        # header + table < this; commit CRC covers [0, BODY_END)
COMMIT_AT = 0xF00                       # last page of the sector
ENTRY = 4
CRC32_CHECK = 0xCBF43926


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _slot(i: int) -> int:
    off = TABLE_AT + i * ENTRY
    return off + ENTRY if off >= SKIP_AT else off


def capacity() -> int:
    return (BODY_END - ENTRY - TABLE_AT) // ENTRY


@dataclass
class Manifest:
    count: int
    image_id: int
    crcs: list[int] = field(default_factory=list)

    def matches(self, img: bytes) -> list[int]:
        """Image sector indexes whose CRC32 equals the manifest's."""
        n = min(self.count, len(img) // SECTOR)
        return [i for i in range(n) if crc32(img[i * SECTOR:(i + 1) * SECTOR]) == self.crcs[i]]


def image_id(img: bytes) -> int:
    return struct.unpack("<I", hashlib.sha256(img).digest()[:4])[0]


def build(img: bytes) -> bytes:
    n = len(img) // SECTOR
    if n > capacity():
        raise ValueError(f"{n} sectors do not fit the manifest (max {capacity()})")
    s = bytearray(b"\xff" * SECTOR)
    s[:HEADER] = MAGIC + struct.pack("<BBHII", VERSION, 0, n, image_id(img), 0)
    for i in range(n):
        o = _slot(i)
        s[o:o + ENTRY] = struct.pack("<I", crc32(img[i * SECTOR:(i + 1) * SECTOR]))
    s[COMMIT_AT:COMMIT_AT + 8] = VALID + struct.pack("<I", crc32(bytes(s[:BODY_END])))
    return bytes(s)


def pages(sector: bytes) -> list[tuple[int, bytes]]:
    """(offset, page) to program in write order: body pages first, the commit page last; blank pages skipped."""
    body = [(o, sector[o:o + PAGE]) for o in range(0, COMMIT_AT, PAGE) if sector[o:o + PAGE] != b"\xff" * PAGE]
    return body + [(COMMIT_AT, sector[COMMIT_AT:COMMIT_AT + PAGE])]


def parse(sector: bytes) -> tuple[Manifest | None, str]:
    """(manifest, '') when valid, else (None, why)."""
    if len(sector) != SECTOR:
        return None, f"{len(sector)} B, not a sector"
    if sector[COMMIT_AT:COMMIT_AT + 4] != VALID:
        return None, "no valid word (erased, or a flash that did not finish)"
    if sector[:4] != MAGIC:
        return None, "bad magic"
    if struct.unpack_from("<I", sector, COMMIT_AT + 4)[0] != crc32(sector[:BODY_END]):
        return None, "commit CRC mismatch (torn write)"
    ver, _flags, count, iid, _rsv = struct.unpack_from("<BBHII", sector, 4)
    if ver != VERSION or count > capacity():
        return None, f"version {ver} / count {count} not understood"
    return Manifest(count, iid, [struct.unpack_from("<I", sector, _slot(i))[0] for i in range(count)]), ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("image", type=Path)
    b.add_argument("--out", type=Path)
    c = sub.add_parser("check")
    c.add_argument("dump", type=Path, help="1 MiB flash dump, or a 4 KiB manifest sector")
    c.add_argument("--image", type=Path)
    a = ap.parse_args()
    if a.cmd == "build":
        data = build(a.image.read_bytes())
        if a.out:
            a.out.write_bytes(data)
        print(f"manifest for {a.image.name}: {len(data)} B, {len(a.image.read_bytes()) // SECTOR} sectors, CRC32 table")
        return 0
    raw = a.dump.read_bytes()
    sector = raw[MANIFEST_ADDR:MANIFEST_ADDR + SECTOR] if len(raw) > SECTOR else raw
    m, why = parse(sector)
    if m is None:
        print(f"INVALID: {why}")
        return 1
    print(f"valid: {m.count} sectors, image_id {m.image_id:08x}")
    if a.image:
        img = a.image.read_bytes()
        ok = m.matches(img)
        bad = [i for i in range(min(m.count, len(img) // SECTOR)) if i not in set(ok)]
        print(f"vs {a.image.name}: {len(ok)} sector(s) match, {len(bad)} differ {bad[:12]}; image_id "
              f"{'equal' if image_id(img) == m.image_id else 'differs'}")
        return 0 if not bad else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
