#!/usr/bin/env python3
"""Which monitor input the cable is in, from the EDID's port tag (#28). Read-only.

usage: edid_port.py <bus> --serial AWT2611000N [--sysfs /sys/class/drm/<connector>/edid]
  Reads the 256-B EDID live at 0x50 (both blocks), finds the CTA vendor-specific block OUI A7-70-D0 payload "AWTO" + port
  (make_edid.py PORT_TAG: 1 = D1 DP, 2 = D2 HDMI, 3 = D3 HDMI). No tag = image older than the tag (fall back: isp_port.py).
  --sysfs: also decode the copy the host read at hot-plug (differs after a reflash until the next hot-plug).
Exit 0 = tagged port found, 1 = no tag / no EDID. Log: ./tmp/logs/edid_port.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus

OUI = bytes.fromhex("D070A7")            # little-endian in the block (edid-decode prints A7-70-D0)
PORTS = {1: "D1 (DP)", 2: "D2 (HDMI)", 3: "D3 (HDMI)"}


def port_tag(e: bytes):
    """Port number from the CTA extension's awto VSDB, or None."""
    if len(e) < 256 or e[128] != 0x02:
        return None
    c = e[128:256]
    i, end = 4, c[2]
    while i < end:
        tag, ln = c[i] >> 5, c[i] & 0x1F
        pl = c[i + 1:i + 1 + ln]
        if tag == 3 and pl[:3] == OUI and pl[3:7] == b"AWTO" and len(pl) >= 8:
            return pl[7]
        i += 1 + ln
    return None


def read_live(bus: int) -> bytes:
    with i2cbus.Bus(bus) as b:
        b.raw_write(0x50, b"\x00")
        return b.raw_read(0x50, 256)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--sysfs", default="")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (root / "tmp/logs/edid_port.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line); lf.write(line + "\n")

    i2cbus.require_unit(a.bus, a.serial)
    e = read_live(a.bus)
    p = port_tag(e)
    log(f"bus {a.bus} {a.serial}: live EDID port tag {p} = {PORTS.get(p, 'none (image without the #28 tag; try isp_port.py)')}")
    if a.sysfs and Path(a.sysfs).exists():
        hp = port_tag(Path(a.sysfs).read_bytes())
        log(f"host copy {a.sysfs}: port tag {hp} = {PORTS.get(hp, 'none')}{'' if hp == p else ' (differs: host has not re-read since a reflash)'}")
    return 0 if p in PORTS else 1


if __name__ == "__main__":
    sys.exit(main())
