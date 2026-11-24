#!/usr/bin/env python3
"""ISP transfer cost bench on a DP-AUX (or DDC) bus (awto-ddc#254 flash speed). Never erases or programs data.

usage: dp_isp_bench.py <bus> --serial AWT2611000N
- enters ISP (MCU halted), times: single / batched register messages, auto-increment on 0x4A vs 0x4B, 0x70 data writes
  by size, whole dry page (256 x 0xFF, flash unchanged), CRC op, status read; resets the scaler on exit
Log: ./tmp/logs/dp_isp_bench.log
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_flash_sector as F
from _log import Logger
from rtd_flash_sector import ENGINE_OPS, PAGE, SECTOR, Rtd

ISP = 0x4A
LOG = None


def log(s: str) -> None:
    LOG.say(s)


def timeit(fn, n: int) -> float:
    t = time.monotonic()
    for _ in range(n):
        fn()
    return (time.monotonic() - t) / n


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    a = ap.parse_args()
    root = F.repo_root()
    LOG = Logger(root / "tmp/logs/dp_isp_bench.log")
    F.LOG = LOG
    log(f"bench bus {a.bus} {i2cbus.adapter_name(a.bus)} kind {i2cbus.bus_kind(a.bus)}")
    i2cbus.require_unit(a.bus, a.serial, None)
    isp = Rtd(a.bus)
    run = lambda ops, addr=ISP: i2cbus.run_ops(isp._xfer, addr, ops)
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        log("ISP not entered"); return 3
    try:
        for ops in ENGINE_OPS:
            isp.write(*ops)
        ms = lambda s: f"{s * 1e3:.3f} ms"
        log(f"single write 0x64: {ms(timeit(lambda: isp.write(0x64, 0), 30))}")
        log(f"single read 0x6F: {ms(timeit(lambda: isp.read(0x6F), 30))}")
        for n in (2, 4, 8, 16):
            ops = [bytes([0x64 + (i & 1), i]) for i in range(n)]
            t = timeit(lambda ops=ops: run(ops), 10)
            log(f"{n} writes in one ioctl: {ms(t)} total, {ms(t / n)} per message")
        # auto-increment: write [0x64, AA, BB], read back 0x64, 0x65 on 0x4A and 0x4B
        for addr in (0x4A, 0x4B):
            try:
                run([bytes([0x64, 0x12, 0x34])], addr)
                got = run([bytes([0x64]), 2], addr)[0]
                one = run([bytes([0x65]), 1], 0x4A)[0]
                log(f"write [0x64,12,34] via 0x{addr:02X} -> read(0x64..65) via same {got.hex()}, 0x65 via 4A {one.hex()}")
            except OSError as e:
                log(f"auto-inc via 0x{addr:02X}: {e!r}")
        # read 0x6F then multi-register read in one transaction
        log(f"read 0x60..0x6F (16 B) one message: {ms(timeit(lambda: run([bytes([0x60]), 16]), 10))}")
        log(f"2 x [write idx, read 1] in one ioctl: {ms(timeit(lambda: run([bytes([0x6F]), 1, bytes([0x60]), 1]), 10))}")
        # whole dry page by chunk size
        addr = 0xE0000 - PAGE
        sec = addr & ~(SECTOR - 1)
        crc0 = isp.flash_crc(sec, SECTOR)
        log(f"flash_crc 4 KiB: {ms(timeit(lambda: isp.flash_crc(sec, SECTOR), 3))}; status read: {ms(timeit(isp.status, 5))}")
        isp.write_mode = "burst"
        for ch in (256, 128):
            isp.burst_chunk = ch
            isp.burst_fails = 0
            isp._byte_sector = None
            isp.dry = True
            isp.program_setup()
            polls = {"n": 0}
            orig = isp.read

            def counting(reg, orig=orig, polls=polls):
                polls["n"] += 1
                return orig(reg)
            isp.read = counting
            try:
                t = timeit(lambda: isp.program_page(addr, b"\xff" * PAGE), 5)
            except (OSError, RuntimeError) as e:
                isp.read = orig
                log(f"dry page burst_chunk {ch}: FAILED {e!r}")
                continue
            isp.read = orig
            log(f"dry page burst_chunk {ch}: {ms(t)} per page, {polls['n'] / 5:.1f} register reads/page, fails {isp.burst_fails}")
        isp.dry = False
        log(f"0x6F idle = 0x{isp.read(0x6F):02x}")
        if isp.enable_aux_fast():
            isp.dry = True
            isp.program_setup()
            isp.aux_pages = isp.aux_polls = 0
            t = timeit(lambda: isp.program_page(addr, b"\xff" * PAGE), 20)
            log(f"dry page aux-fast: {ms(t)} per page, extra polls {isp.aux_polls / max(isp.aux_pages, 1):.2f}/page, 0x6F after = 0x{isp._rdy:02x}")
            isp.dry = False
            t = timeit(lambda: isp.write_regs(0x64, [0, 1, 2]), 10)
            log(f"write_regs 3 B via 0x4B: {ms(t)}; flash_crc 4 KiB: {ms(timeit(lambda: isp.flash_crc(sec, SECTOR), 3))}")
        if isp.flash_crc(sec, SECTOR) != crc0:
            log("ERROR: sector changed")
    finally:
        try:
            isp.write(0xEE, 0x02)
        except OSError:
            pass
        log("scaler reset sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
