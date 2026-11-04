#!/usr/bin/env python3
"""Find the RTD2795T's real XRAM extent over ISP (MCU halted): dump and/or write-readback test XDATA pages.

usage: rtd_xram_probe.py <bus> [--from 0xD100] [--to 0xFAFF] [--write] [--no-reset]
  default  read-only dump of the range -> tmp/xram_<bus>_<ts>.bin + per-page summary
  --write  per 256-B page: 4 probe addresses, save byte, write 0xA5 then 0x5A, read back, RESTORE original.
           A page is RAM if every probe read back both patterns. Volatile: MCU halted, monitor reset after.
Access path: ISP F4/F5 with page select 0x9F reaches the MCU XDATA bus (proven: rd 0xFF09 = live ADC XFR).
Facts: regdb scaler register pages end at 0xD0 (0xD000-0xD0FF INT_STATUS3); MCU XFRs start 0xFB00;
SDK RL6449 _XRAM_ADDR_START/END = 0xD700/0xF6FF. Tracking: awto-ddc#8. Log: tmp/logs/rtd_xram_probe.log
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
from rtd_osd import Osd

PROBE_OFFS = (0x00, 0x55, 0xAA, 0xFF)
PATTERNS = (0xA5, 0x5A)


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_xram_probe.log").open("a")
    bus = int(a[0])
    lo = int(a[a.index("--from") + 1], 0) if "--from" in a else 0xD100
    hi = int(a[a.index("--to") + 1], 0) if "--to" in a else 0xFAFF
    write = "--write" in a
    o = Osd(bus)
    P.log(f"=== xram probe bus={bus} 0x{lo:04X}-0x{hi:04X} write={write} ===")
    o.enter()
    try:
        if not write:
            t0 = time.time()
            data = bytes(o.rd(addr) for addr in range(lo, hi + 1))
            out = root / "tmp" / f"xram_{bus}_{time.strftime('%Y%m%d-%H%M%S')}.bin"
            out.write_bytes(data)
            P.log(f"dumped {len(data)} B in {time.time() - t0:.0f}s -> {out}")
            for page in range(lo & 0xFF00, hi + 1, 0x100):
                chunk = data[max(page, lo) - lo:min(page + 0x100, hi + 1) - lo]
                distinct = len(set(chunk))
                P.log(f"  0x{page:04X} distinct={distinct:3d} ff={chunk.count(0xFF):3d} 00={chunk.count(0):3d}")
        else:
            ram_pages = []
            for page in range(lo & 0xFF00, hi + 1, 0x100):
                ok = True
                for off in PROBE_OFFS:
                    addr = page + off
                    orig = o.rd(addr)
                    got = []
                    for pat in PATTERNS:
                        o.wr(addr, pat)
                        got.append(o.rd(addr))
                    o.wr(addr, orig)
                    back = o.rd(addr)
                    if got != list(PATTERNS):
                        ok = False
                    if back != orig:
                        P.log(f"  WARN 0x{addr:04X} restore read 0x{back:02X} != orig 0x{orig:02X}")
                P.log(f"  0x{page:04X} {'RAM' if ok else 'not RAM'}")
                if ok:
                    ram_pages.append(page)
            if ram_pages:
                P.log(f"RAM pages: 0x{ram_pages[0]:04X}..0x{ram_pages[-1] + 0xFF:04X} "
                      f"({len(ram_pages)} pages = {len(ram_pages) * 256} B; contiguous="
                      f"{ram_pages == list(range(ram_pages[0], ram_pages[-1] + 1, 0x100))})")
    finally:
        if "--no-reset" not in a:
            o.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
