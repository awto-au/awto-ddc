#!/usr/bin/env python3
"""Read-only VCP scan 0x00..0xFF of the Philips 288E2 (bus found by EDID serial).

Logs to tmp/logs/philips_probe.log; raw table to tmp/philips/<date>-vcp-scan.txt.
Aborts after 3 consecutive transaction errors (not "unsupported" replies).
No setvcp, no writes.
"""
import datetime
import os
import re
import subprocess
import sys

SERIAL = "UK52307000611"


def repo():
    r = os.environ.get("AWTO_DDC_REPO")
    if r:
        return r
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout + p.stderr


def find_bus():
    _, out = run(["ddcutil", "detect", "--brief"])
    for blk in out.split("Display "):
        if SERIAL in blk:
            m = re.search(r"/dev/i2c-(\d+)", blk)
            if m:
                return m.group(1)
    sys.exit("Philips not found by serial " + SERIAL)


def main():
    root = repo()
    day = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(os.path.join(root, "tmp/philips"), exist_ok=True)
    os.makedirs(os.path.join(root, "tmp/logs"), exist_ok=True)
    out_path = os.path.join(root, f"tmp/philips/{day}-vcp-scan.txt")
    bus = find_bus()
    errs = 0
    with open(out_path, "w") as f, open(os.path.join(root, "tmp/logs/philips_probe.log"), "a") as log:
        for code in range(256):
            rc, out = run(["ddcutil", "--bus", bus, "getvcp", f"{code:02x}"])
            line = out.strip().replace("\n", " | ")
            f.write(f"{code:02X} rc={rc} {line}\n")
            f.flush()
            log.write(f"{code:02X} rc={rc} {line}\n")
            if rc == 0 or "nsupported" in out or "not readable" in out:
                errs = 0
            else:
                errs += 1
                if errs >= 3:
                    print("abort: 3 consecutive errors at", f"{code:02X}")
                    break
    print("done", out_path)


if __name__ == "__main__":
    main()
