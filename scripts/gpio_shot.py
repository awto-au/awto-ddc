#!/usr/bin/env python3
"""Render the GPIO input diagnostic screen (test cmd 0x43) in fw_sim, save a PNG.

usage: gpio_shot.py BIN MAP [--out OUT.png] [--mode 1080p60]
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
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, a.mode)
    s.boot()
    addr = s.diag + T.TESTCMD_OFF
    ok = (s.bus.write(0x6A, 0x01, bytes([addr >> 8])) and s.bus.write(0x6A, 0x03, bytes([0x43]))
          and s.bus.write(0x6A, 0x3B, bytes([addr & 0xFF])))
    R.say(f"GPIO open (0x43) {'sent' if ok else 'NAK'}")
    s.bus.wait(1.0)                                  # screen draws within a few main-loop passes
    R.save(s.snap(), a.out, "grey", 2)
    s.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
