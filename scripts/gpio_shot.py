#!/usr/bin/env python3
"""Render the GPIO input diagnostic screen (test cmd 0x43) in fw_sim, save a PNG.

usage: gpio_shot.py BIN MAP [--out OUT.png] [--mode 1080p60] [--cmds 0x43,...]
  --cmds: test command bytes sent in order (default 0x43 = GPIO screen; 0x60+n font n; 0x45 probe; 0x80+n probe with n lines)
Log: tmp/logs/gpio_shot.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/gpio_shot.png")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--cmds", default="0x43")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds to run after the last command before the snapshot")
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, a.mode)
    s.boot()
    addr = s.diag + T.TESTCMD_OFF
    for c in (int(x, 0) for x in a.cmds.split(",")):
        ok = (s.bus.write(0x6A, 0x01, bytes([addr >> 8])) and s.bus.write(0x6A, 0x03, bytes([c]))
              and s.bus.write(0x6A, 0x3B, bytes([addr & 0xFF])))
        R.say(f"test cmd 0x{c:02X} {'sent' if ok else 'NAK'}")
        s.bus.wait(0.5)                              # the main loop consumes one command per pass
    s.bus.wait(a.wait)                               # screen draws within a few main-loop passes; --wait shows later redraws
    R.save(s.snap(), a.out, "grey", 2)
    s.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
