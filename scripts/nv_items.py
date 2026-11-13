#!/usr/bin/env python3
"""List the SDK EEPROM-emulation items in dumped NVRAM pages (bank 15 pages 11-12 = 0xFB000 / 0xFC000, RL6449_Project.h).

usage: nv_items.py PAGE.bin [PAGE.bin ...]     (dump: rtd_flash_sector.py <bus> 0xFB000 <any 4 KiB file> --backup-dir tmp/nvdump)
Item = 16 B (_DATA_ITEM_LENGTH): id, 14 data, checksum. Per page: item count per id, newest copy (highest address) of each.
Log: ./tmp/logs/nv_items.log
"""
import os, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/nv_items.log"
ITEM = 16                     # _DATA_ITEM_LENGTH (RTD2014UserInclude.h)
AUX = range(0x40, 0x44)       # AWTO_NV_AUX_ID .. + AWTO_NV_AUX_ITEMS (RL6449_Project.h)


def crc(data: bytes) -> int:
    """Item checksum: the SDK's bitwise CRC-8 (UserCommonFlashCalculateCheckSumData), & 0x7F as the loader compares it."""
    c = 0
    for d in data:
        D = [(d >> k) & 1 for k in range(8)]
        L = [(c >> k) & 1 for k in range(8)]
        t = [D[7] ^ D[6] ^ D[0] ^ L[7] ^ L[6] ^ L[0],
             D[6] ^ D[1] ^ D[0] ^ L[6] ^ L[1] ^ L[0],
             D[6] ^ D[2] ^ D[1] ^ D[0] ^ L[6] ^ L[2] ^ L[1] ^ L[0],
             D[7] ^ D[3] ^ D[2] ^ D[1] ^ L[7] ^ L[3] ^ L[2] ^ L[1],
             D[4] ^ D[3] ^ D[2] ^ L[4] ^ L[3] ^ L[2],
             D[5] ^ D[4] ^ D[3] ^ L[5] ^ L[4] ^ L[3],
             D[6] ^ D[5] ^ D[4] ^ L[6] ^ L[5] ^ L[4],
             D[7] ^ D[6] ^ D[5] ^ L[7] ^ L[6] ^ L[5]]
        c = sum(b << k for k, b in enumerate(t))
    return c & 0x7F


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s)


def main() -> int:
    for p in map(Path, sys.argv[1:]):
        b = p.read_bytes()
        items = [(o, b[o], b[o + 1:o + ITEM - 1], b[o + ITEM - 1]) for o in range(0, len(b), ITEM)]
        used = [it for it in items if it[1] != 0xFF]
        say(f"{p.name}: {len(used)} items used of {len(items)}; last 16 B (page info?) {b[-ITEM:].hex(' ')}")
        say("  ids: " + ", ".join(f"0x{k:02X} x{v}" for k, v in sorted(Counter(it[1] for it in used).items())))
        for a in AUX:
            last = [it for it in used if it[1] == a]
            if not last:
                say(f"  aux 0x{a:02X}: none")
                continue
            o, _, d, c = last[-1]
            ok = crc(b[o:o + ITEM - 1]) == c
            say(f"  aux 0x{a:02X}: {len(last)} copies, newest @0x{o:03X}: {d.hex(' ')} chk {c:02X} {'OK' if ok else 'BAD'}")
        bad = [(o, i) for o, i, _, c in used if i != 0xA3 and crc(b[o:o + ITEM - 1]) != c]
        say(f"  checksum BAD: {len(bad)} items" + (f" (first: {', '.join(f'0x{i:02X}@0x{o:03X}' for o, i in bad[:8])})" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
