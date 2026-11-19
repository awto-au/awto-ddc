#!/usr/bin/env python3
"""Show every saver on a unit for HOLD_S seconds each, with the alert tone at the start of each.

usage: saver_tour.py [--unit N] [--volume PCT] [--hold S] [--restore-volume PCT]
  Per saver: VCP 0xEB = n, alert tone (VCP 0xEB = 6, 1 s), VCP 0xEB = n again, hold, next; ends with 0xEB = 0.
  Volume (VCP 0x62) is set first and restored at the end.
Log: ./tmp/logs/saver_tour.log
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

import isostamp
import saver_names

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/saver_tour.log"
DEV = ROOT / "dev.py"
TOUR = ("pacman", "scope2", "asteroids")   # VCP 0xEB values come from fw/awto/savers.tsv
HOLD_S = 10.0  # Dan's viewing time per saver (2026-11-19)
VOLUME_PCT = 50  # Dan's request
REST_VOLUME_PCT = 10  # alert-dan memory: monitor's usual 10 %
TRIES = 3  # per DDC call, a failed set is retried; each try is logged


def say(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {msg}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def dev(*args):
    for attempt in range(1, TRIES + 1):  # bus 11 is shared with agents: a set can fail transiently
        r = subprocess.run([sys.executable, str(DEV), *args], capture_output=True, text=True, check=False)
        say(f"dev.py {' '.join(args)} rc={r.returncode} try {attempt}")
        if r.returncode == 0:
            break
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="3")
    ap.add_argument("--volume", type=int, default=VOLUME_PCT)
    ap.add_argument("--hold", type=float, default=HOLD_S)
    ap.add_argument("--restore-volume", type=int, default=REST_VOLUME_PCT)
    a = ap.parse_args()
    u = ["--unit", a.unit]
    dev("ddc", *u, "set", "0x62", str(a.volume))
    try:
        for name in TOUR:
            n = saver_names.vcp(name)
            say(f"saver {name} (0xEB = {n})")
            dev("ddc", *u, "set", "0xEB", str(n))
            dev("alert", *u, "--wait")
            dev("ddc", *u, "set", "0xEB", str(n))
            threading.Event().wait(a.hold)  # the hold is the point: Dan watches each saver
    finally:
        dev("ddc", *u, "set", "0xEB", "0")
        dev("ddc", *u, "set", "0x62", str(a.restore_volume))
    say("tour done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
