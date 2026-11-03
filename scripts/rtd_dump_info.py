#!/usr/bin/env python3
"""Fingerprint and diff Realtek scaler SPI flash dumps.

usage: rtd_dump_info.py <dump.bin> [<dump2.bin> ...]
Per dump: sha256, 64 KB bank usage (non-0xFF %), last used offset, 8051 vector check,
EDID blocks (header + 'JXC' monitor-name text), DDC caps strings. For >1 dump: pairwise diff.
Log: ./tmp/logs/rtd_dump_info.log
"""
import hashlib, itertools, os, re, sys
from pathlib import Path

BANK = 0x10000
EDID_HDR = bytes([0, 255, 255, 255, 255, 255, 255, 0])
CAPS_RE = re.compile(rb"\(prot\(monitor\)[ -~]{20,300}?mccs_ver\([0-9.]+\)\)")
LOG = None


def out(s: str) -> None:
    print(s); LOG.write(s + "\n"); LOG.flush()


def info(path: Path, data: bytes) -> None:
    out(f"== {path.name}: {len(data)} B sha256 {hashlib.sha256(data).hexdigest()[:16]}")
    last = max((i for i, b in enumerate(data) if b != 0xFF), default=-1)
    out(f"   last non-FF offset 0x{last:06x}")
    banks = []
    for b in range(0, len(data), BANK):
        blk = data[b:b + BANK]
        used = sum(1 for x in blk if x != 0xFF)
        banks.append(f"{b >> 16:X}:{100 * used // BANK}%")
    out("   bank usage " + " ".join(banks))
    v = data[:0x2E]
    ok = v[0] == 0x02 and all(v[o] == 0x02 for o in (0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B))
    out(f"   8051 vectors (LJMP @0x00,0x03..0x2B step 8): {'yes' if ok else 'no'}; reset -> 0x{int.from_bytes(data[1:3], 'big'):04x}")
    pos = 0
    while (pos := data.find(EDID_HDR, pos)) != -1:
        e = data[pos:pos + 128]
        name = re.search(rb"\x00\x00\x00\xfc\x00([ -~]{1,13})", e)
        sn = re.search(rb"\x00\x00\x00\xff\x00([ -~]{1,13})", e)
        mfg = (((e[8] << 8) | e[9]) >> 10 & 31, ((e[8] << 8) | e[9]) >> 5 & 31, ((e[8] << 8) | e[9]) & 31)
        out(f"   EDID @0x{pos:06x} mfg={''.join(chr(64 + c) for c in mfg)} prod=0x{e[11]:02x}{e[10]:02x} "
            f"name={name.group(1).strip().decode() if name else '?'} serial={sn.group(1).strip().decode() if sn else '?'} sum={sum(e) & 255}")
        pos += 128
    for m in CAPS_RE.finditer(data):
        out(f"   caps @0x{m.start():06x} len={len(m.group())}: {m.group().decode()}")


def diff(a: bytes, b: bytes, na: str, nb: str) -> None:
    n = min(len(a), len(b))
    ranges, start = [], None
    for i in range(n):
        if a[i] != b[i]:
            start = i if start is None else start
            end = i
        elif start is not None and i - end > 16:
            ranges.append((start, end)); start = None
    if start is not None:
        ranges.append((start, end))
    total = sum(1 for i in range(n) if a[i] != b[i])
    out(f"-- diff {na} vs {nb}: {total} differing bytes in {len(ranges)} ranges")
    for s, e in ranges[:20]:
        out(f"   0x{s:06x}-0x{e:06x} ({e - s + 1} B)")


def main() -> int:
    global LOG
    root = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp" / "logs" / "rtd_dump_info.log").open("a")
    paths = [Path(p) for p in sys.argv[1:]]
    blobs = [p.read_bytes() for p in paths]
    for p, d in zip(paths, blobs):
        info(p, d)
    for (pa, da), (pb, db) in itertools.combinations(zip(paths, blobs), 2):
        diff(da, db, pa.name, pb.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
