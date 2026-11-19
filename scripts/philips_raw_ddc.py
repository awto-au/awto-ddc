#!/usr/bin/env python3
"""Raw DDC/CI READ requests to the Philips 288E2 (bus found by EDID serial); saves raw replies.

Sends only Get-VCP frames (opcode 01) and the SmartControl support probe (opcode 01, 6-byte payload).
No set / save / write opcodes: the frame table below is the whole list.
Output: tmp/philips/<date>-rawddc.txt, log tmp/logs/philips_raw_ddc.log.
"""

import datetime
import os
import re
import subprocess
import sys
import time

import i2cbus

SERIAL = "UK52307000611"
# DDC/CI spec: >= 40 ms between request and reply read; coded at spec minus 10 % (house delay rule).
REPLY_DELAY_S = 0.036
FRAMES = [  # (label, payload after 0x51/len: opcode + data), reads only
    ("getvcp E9", [0x01, 0xE9]),
    ("getvcp EC", [0x01, 0xEC]),
    ("getvcp F6", [0x01, 0xF6]),
    ("getvcp F7", [0x01, 0xF7]),
    ("getvcp FE", [0x01, 0xFE]),
    ("getvcp 10 (control)", [0x01, 0x10]),
    ("probe FE EF 13 00 00 20", [0x01, 0xFE, 0xEF, 0x13, 0x00, 0x00, 0x20]),
]


def repo():
    return os.environ.get("AWTO_DDC_REPO") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )


def find_bus():
    out = subprocess.run(
        ["ddcutil", "detect", "--brief"], capture_output=True, text=True, check=False
    ).stdout
    for blk in out.split("Display "):
        if SERIAL in blk:
            m = re.search(r"/dev/i2c-(\d+)", blk)
            if m:
                return int(m.group(1))
    sys.exit("Philips not found by serial " + SERIAL)


def frame(payload):
    msg = [0x51, 0x80 | len(payload)] + payload
    chk = 0x6E
    for b in msg:
        chk ^= b
    return bytes(msg + [chk])


def main():
    root = repo()
    day = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(os.path.join(root, "tmp/philips"), exist_ok=True)
    os.makedirs(os.path.join(root, "tmp/logs"), exist_ok=True)
    bus = find_bus()
    dev = i2cbus.Bus(bus)
    lines = ["bus /dev/i2c-%d serial %s" % (bus, SERIAL)]
    for label, payload in FRAMES:
        req = frame(payload)
        dev.raw_write(0x37, req)
        time.sleep(REPLY_DELAY_S)
        try:
            rep = dev.raw_read(0x37, 40)
        except OSError as e:
            rep = b""
            lines.append(f"# read error {e}")
        lines.append("{} | req {} | rep {}".format(label, req.hex(" "), rep.hex(" ")))
        time.sleep(REPLY_DELAY_S)  # spacing between requests
    dev.close()
    open(os.path.join(root, f"tmp/philips/{day}-rawddc.txt"), "a").write(
        "\n".join(lines) + "\n"
    )
    open(os.path.join(root, "tmp/logs/philips_raw_ddc.log"), "a").write(
        "\n".join(lines) + "\n"
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
