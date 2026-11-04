#!/usr/bin/env python3
"""Static: list every `MOV DPTR,#addr` + following read/modify/write for given XFR addresses in a flash image.

usage: fw_xfr_writes.py <image.bin> <addr-hex>[-<addr-hex>] [...]
  Prints offset, address and the next few instructions (dis51 linear decode), to diff two firmwares'
  register programming (e.g. old fw vs ours). Pattern search only: data bytes can false-match.
Log: ./tmp/logs/fw_xfr_writes.log
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dis51  # noqa: E402
from sdcc_overlay import repo_root  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__); return 2
    img = Path(sys.argv[1]).read_bytes()
    addrs = []
    for a in sys.argv[2:]:
        lo, _, hi = a.partition("-")
        addrs += range(int(lo, 16), int(hi or lo, 16) + 1)
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/fw_xfr_writes.log").open("a")
    log.write(f"=== {sys.argv[1]} {sys.argv[2:]} ===\n")
    for x in addrs:
        pat = bytes([0x90, x >> 8, x & 0xFF])
        i = img.find(pat)
        while i >= 0:
            ops, pc = [], i + 3
            for _ in range(4):
                txt, n = dis51.dis(img, pc)
                ops.append(txt); pc += n
            line = f"{i:06X} {x:04X}: " + " ; ".join(ops)
            print(line); log.write(line + "\n")
            i = img.find(pat, i + 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
