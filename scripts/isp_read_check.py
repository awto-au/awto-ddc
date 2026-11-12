#!/usr/bin/env python3
"""Read-path check: flash read with 64 B vs N B FIFO reads must give the same bytes; times both (#61). Read-only.

usage: isp_read_check.py <bus> --serial AWT2611000N [--kib 64] [--chunk 256]
       isp_read_check.py <bus> --serial S --integrity [--sectors 0,1,38] [--fast]
  Enters ISP (MCU halted), reads the first --kib KiB with read_chunk 64 and with --chunk, compares, resets the scaler.
  --integrity: per sector two readbacks + on-chip CRC vs crc8 (the flasher's trust gate, #71).
  ISP enter / exit also go to the unit log tmp/logs/unit-<serial>.log. Log: ./tmp/logs/isp_read_check.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_isp_probe as P
import rtd_proto
import flash_state as S
from rtd_flash_sector import Rtd


def integrity(isp, sectors) -> bool:
    """Two readbacks + hw CRC per sector; True when all agree."""
    ok = True
    for i in sectors:
        a = i * 4096
        r1, r2 = isp.read_flash(a, 4096), isp.read_flash(a, 4096)
        hw, py = isp.flash_crc(a, 4096), S.crc8(r1)
        diff = [k for k in range(4096) if r1[k] != r2[k]]
        bad = sorted({k for k in range(0, 4096, 1024)} & set(diff))
        good = hw == py and not diff
        ok &= good
        P.log(f"sector {i} 0x{a:06x}: {'OK' if good else 'BAD'} hw crc 0x{hw:02x} py 0x{py:02x}; readback 1 vs 2: "
              f"{len(diff)} byte(s) differ" + (f" (first {[hex(k) for k in diff[:8]]}, at 1 KiB starts {bad})" if diff else "")
              + f"; byte0/400/800/c00 = {r1[0]:02x} {r1[0x400]:02x} {r1[0x800]:02x} {r1[0xc00]:02x}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--kib", type=int, default=64)
    ap.add_argument("--chunk", type=int, default=256, choices=(128, 256))
    ap.add_argument("--integrity", action="store_true")
    ap.add_argument("--sectors", default="0,1,38")
    ap.add_argument("--fast", action="store_true", help="1 MHz GMBUS (the flasher's rate) for the ISP session")
    a = ap.parse_args()
    root = P.repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    P.LOG = rtd_proto.setup_logs("isp_read_check").main
    ulog = (root / f"tmp/logs/unit-{a.serial}.log").open("a")

    def unit(s):
        ulog.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} [isp_read_check] {s}\n"); ulog.flush(); P.log(s)

    i2cbus.require_unit(a.bus, a.serial, "isp_read_check: caller-proven bus (EDID silent)" if a.integrity else None)
    if a.fast:
        with i2cbus.fast_bus(a.bus) as khz:
            P.log(f"bus rate {khz} kHz")
            return session(a, unit)
    return session(a, unit)


def session(a, unit) -> int:
    isp = Rtd(a.bus)
    unit(f"ISP enter (MCU halted) bus {a.bus}")
    t_in = time.monotonic()
    isp.write(0x6F, 0x80)
    try:
        if a.integrity:
            same = integrity(isp, [int(x, 0) for x in a.sectors.split(",")])
            P.log(f"INTEGRITY {'OK' if same else 'BAD'}")
            return 0 if same else 1
        res = {}
        for ch in (64, a.chunk):
            isp.read_chunk = ch
            t0 = time.monotonic()
            res[ch] = isp.read_flash(0, a.kib * 1024)
            P.log(f"chunk {ch}: {a.kib} KiB in {time.monotonic() - t0:.2f} s")
        same = res[64] == res[a.chunk]
        P.log(f"{'SAME' if same else 'DIFFER'}: chunk 64 vs {a.chunk} over {a.kib} KiB")
    finally:
        try:
            isp.write(0xEE, 0x02)                 # scaler reset = ISP exit (monitor reboots)
        except OSError:
            pass                                  # the reset can cut its own ACK (as in rtd_flash_image)
        unit(f"ISP exit (reset) after {time.monotonic() - t_in:.1f} s")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
