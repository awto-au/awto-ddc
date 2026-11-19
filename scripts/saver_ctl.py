#!/usr/bin/env python3
"""Start / stop a saver by name on a unit (VCP 0xEB from fw/awto/savers.tsv), or tour them all. Entry point: ./dev.py saver.

usage (via dev.py): saver [--unit N] NAME | tour [--hold S] [--volume PCT]
  NAME = a name in fw/awto/savers.tsv with a VCP value (off, selected, pacman, scope2, flash, splash, alert, asteroids, stop).
  tour: each tour saver for HOLD_S s with the alert tone at the start; volume (VCP 0x62) set first, restored at the end.
Log: ./tmp/logs/saver_ctl.log
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

import isostamp
import saver_names

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/saver_ctl.log"
TOUR = ("pacman", "scope2", "asteroids")
HOLD_S = 10.0  # Dan's viewing time per saver (2026-11-19)
VOLUME_PCT = 50  # Dan's request for the tour
REST_VOLUME_PCT = 10  # the monitor's usual volume (alert-dan memory)
TRIES = 3  # per DDC call: bus 11 is shared with agents and a set can fail transiently; every try is logged
VCP_SAVER, VCP_VOLUME = "0xEB", "0x62"


def say(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {msg}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def ddc_set(bus, code, val):
    for attempt in range(1, TRIES + 1):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/ddc_ctl.py"), "--bus", str(bus), "set", code, str(val)],
                           capture_output=True, text=True)
        say(f"set {code} {val} rc={r.returncode} try {attempt}")
        if r.returncode == 0:
            return True
    return False


def alert(bus):
    r = subprocess.run([sys.executable, str(ROOT / "scripts/alert.py"), "--bus", str(bus), "--wait"], capture_output=True, text=True)
    say(f"alert rc={r.returncode}")


def start(bus, name):
    v = saver_names.vcp(name)
    say(f"saver {name} (VCP {VCP_SAVER} = {v})")
    return ddc_set(bus, VCP_SAVER, v)


def tour(bus, hold, volume):
    ddc_set(bus, VCP_VOLUME, volume)
    try:
        for name in TOUR:
            start(bus, name)
            alert(bus)
            start(bus, name)  # the alert replaces the saver (VCP 0xEB = 6): start it again
            threading.Event().wait(hold)  # the hold is the point: Dan watches each saver
    finally:
        start(bus, "stop")
        ddc_set(bus, VCP_VOLUME, REST_VOLUME_PCT)
    say("tour done")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("action", help="saver name or 'tour'")
    ap.add_argument("--hold", type=float, default=HOLD_S)
    ap.add_argument("--volume", type=int, default=VOLUME_PCT)
    a = ap.parse_args()
    if a.action == "tour":
        return tour(a.bus, a.hold, a.volume)
    return 0 if start(a.bus, a.action) else 1


if __name__ == "__main__":
    sys.exit(main())
