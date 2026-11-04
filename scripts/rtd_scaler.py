#!/usr/bin/env python3
"""One ISP session on a Realtek scaler: stop the MCU, run register ops, reset (the monitor reboots).

usage: rtd_scaler.py <bus> [--keep] OP [OP ...]
  r:0x9f            read scaler register (via ISP F4/F5, page = reg 0x9F)
  w:0x9f=0x00       write scaler register (F4 <- reg, F5 <- value)
  osd:0x0000:64     OSD RAM read: reg 0x90/0x91 <- address, then N reads of data port 0x92 (page 0)
  osdw:0x0000=41,42 OSD RAM write: address, then bytes to data port 0x92
  --keep            do NOT reset at the end (monitor stays halted; use `rtd_isp_probe.py <bus> --resume`)
The OSD is drawn by hardware, so an OSD already on screen stays visible while the MCU is halted.
Register names/addresses: public RTD2660 SDK (ScalerDef.h: 0x90 OSD addr MSB, 0x91 LSB, 0x92 data port) [oss];
unverified on this scaler. Log: ./tmp/logs/rtd_scaler.log
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P


def main() -> int:
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_scaler.log").open("a")
    bus, keep = int(sys.argv[1]), "--keep" in sys.argv
    ops = [a for a in sys.argv[2:] if a != "--keep"]
    isp = P.Isp(bus)
    P.log(f"bus={bus} ops={ops} keep={keep}")
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        P.log("ISP mode not enabled; aborting"); return 3

    def rd(r):
        isp.write(0xF4, r); return isp.read(0xF5)

    def wr(r, v):
        isp.write(0xF4, r); isp.write(0xF5, v)
    try:
        for op in ops:
            kind, _, arg = op.partition(":")
            if kind == "r":
                r = int(arg, 0); P.log(f"r 0x{r:02x} = 0x{rd(r):02x}")
            elif kind == "w":
                r, v = (int(x, 0) for x in arg.split("="))
                wr(r, v); P.log(f"w 0x{r:02x} <- 0x{v:02x}")
            elif kind == "osd":
                a, n = (int(x, 0) for x in arg.split(":"))
                wr(0x90, a >> 8); wr(0x91, a & 0xFF)
                isp.write(0xF4, 0x92)
                data = bytes(isp.read(0xF5) for _ in range(n))
                P.log(f"osd 0x{a:04x} +{n}: {data.hex(' ')}")
            elif kind == "osdw":
                a, d = arg.split("=")
                a = int(a, 0); data = bytes(int(x, 16) for x in d.split(","))
                wr(0x90, a >> 8); wr(0x91, a & 0xFF)
                isp.write(0xF4, 0x92)
                for b in data:
                    isp.write(0xF5, b)
                P.log(f"osdw 0x{a:04x} <- {data.hex(' ')}")
    finally:
        if not keep:
            try:
                isp.write(0xEE, 0x02)
            except OSError:
                pass   # expected: scaler resets mid-transfer
            P.log("reset scaler MCU (0xEE <- 0x02): monitor reboots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
