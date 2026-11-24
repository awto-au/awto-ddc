#!/usr/bin/env python3
"""Build the emulated-monitor profile for the SmartControl dxva2 shim.

Input: tmp/philips/<date>-{caps-verbose,vcp-scan}.txt + -edid.bin (read-only probe of the 288E2).
Output: tmp/wine/monitor_profile.txt (caps / edid / vcp lines read by tools/smartcontrol_dxva2/dxva2_shim.c).
Optional: --model NAME renames the monitor (EDID name + caps model()) to a model the app lists.
Log: tmp/logs/smartcontrol_profile.log. No hardware access.
"""

import binascii
import glob
import os
import re
import sys
from pathlib import Path


def repo():
    r = os.environ.get("AWTO_DDC_REPO")
    return r or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def latest(root, suffix):
    f = sorted(glob.glob(os.path.join(root, "tmp/philips", "*-" + suffix)))
    if not f:
        sys.exit("missing tmp/philips/*-" + suffix)
    return f[-1]


def vcp_values(scan):
    """code -> (type, cur, max) with cur = sh<<8|sl, max = mh<<8|ml."""
    out = {}
    with open(scan) as _f:
        for ln in _f:
            m = re.match(r"([0-9A-F]{2}) rc=0 (.*)", ln)
            if not m:
                continue
            code, rest = int(m.group(1), 16), m.group(2)
            cv = re.search(r"current value =\s*(\d+), max value =\s*(\d+)", rest)
            mh = re.search(r"mh=0x(\w\w), ml=0x(\w\w), sh=0x(\w\w), sl=0x(\w\w)", rest)
            sl = re.search(r"sl=0x(\w\w)", rest)
            sh = re.search(r"sh=0x(\w\w)", rest)
            if cv:
                out[code] = (0, int(cv.group(1)), int(cv.group(2)))
            elif mh:
                a = [int(x, 16) for x in mh.groups()]
                out[code] = (1, a[2] << 8 | a[3], a[0] << 8 | a[1])
            elif sl:
                out[code] = (
                    1,
                    (int(sh.group(1), 16) if sh else 0) << 8 | int(sl.group(1), 16),
                    0xFF,
                )
    # text-only replies, values read off the same scan lines
    over = {
        0x02: (1, 0x02, 0xFF),
        0x0B: (0, 100, 0xFF),
        0x0C: (0, 0x0000, 0xFF),
        0x1E: (1, 0, 1),
        0x52: (1, 0, 0xFF),
        0x62: (0, 0x54, 100),
        0x72: (1, 0x78, 0xFF),
        0xAC: (0, 2228, 0xFFFF),
        0xAE: (0, 5999, 0xFFFF),
        0xC6: (0, 0x006F, 0xFFFF),
        0xC9: (0, 0x0100, 0xFFFF),
        0x14: (1, 0x05, 0xFF),
        0xDF: (1, 0x0202, 0xFFFF),
    }
    for c, v in over.items():
        if c in out and c not in (
            0x02,
            0x0B,
            0x0C,
            0x14,
            0x1E,
            0x52,
            0x62,
            0x72,
            0xAC,
            0xAE,
            0xC6,
            0xC9,
            0xDF,
        ):
            continue
        out[c] = v
    return out


def patch_model(edid, caps, model):
    """Rename the monitor-name descriptor (0xFC) + caps model(): SmartControl only lists 288E2UAE."""
    b = bytearray(edid)
    for off in (54, 72, 90, 108):
        if b[off : off + 4] == b"\x00\x00\x00\xfc":
            b[off + 5 : off + 18] = ("PHL " + model + "\n").ljust(13).encode()[:13]
    b[127] = (-sum(b[:127])) & 0xFF
    return bytes(b), re.sub(r"model\([^)]*\)", f"model({model})", caps)


def main():
    root = repo()
    caps = [
        ln
        for ln in Path(latest(root, "caps-verbose.txt")).read_text().splitlines(keepends=True)
        if ln.startswith("Unparsed capabilities string:")
    ]
    capstr = caps[0].split(":", 1)[1].strip()
    with open(latest(root, "edid.bin"), "rb") as _f:
        raw = _f.read()
    if len(sys.argv) > 2 and sys.argv[1] == "--model":
        raw, capstr = patch_model(raw, capstr, sys.argv[2])
    edid = binascii.hexlify(raw).decode()
    vals = vcp_values(latest(root, "vcp-scan.txt"))
    os.makedirs(os.path.join(root, "tmp/wine"), exist_ok=True)
    os.makedirs(os.path.join(root, "tmp/logs"), exist_ok=True)
    p = os.path.join(root, "tmp/wine/monitor_profile.txt")
    with open(p, "w") as f:
        f.write("caps " + capstr + "\n")
        f.write("edid " + edid + "\n")
        for c in sorted(vals):
            t, cur, mx = vals[c]
            f.write(f"vcp {c:02X} {t:d} {cur:d} {mx:d}\n")
    msg = f"profile {p}: caps {len(capstr)} chars, edid {len(edid) // 2} bytes, {len(vals)} vcp codes"
    with open(os.path.join(root, "tmp/logs/smartcontrol_profile.log"), "a") as _f:
        _f.write(msg + "\n")
    print(msg)


if __name__ == "__main__":
    main()
