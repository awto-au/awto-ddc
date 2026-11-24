#!/usr/bin/env python3
"""Start / stop a screen by name on a unit (VCP 0xEB from fw/awto/savers.tsv). Entry point: ./dev.py saver.

usage (via dev.py): saver [--unit N] NAME
  NAME = a name in fw/awto/savers.tsv with a VCP value (stop, flash, splash, alert).
Log: ./tmp/logs/saver_ctl.log
"""
import argparse
import subprocess
import sys

import saver_names
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/saver_ctl.log"
TRIES = 3  # per DDC call: bus 11 is shared with agents and a set can fail transiently; every try is logged
VCP_SAVER = "0xEB"


def say(msg):
    _log_line(msg, LOG)


def ddc_set(bus, code, val):
    for attempt in range(1, TRIES + 1):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/ddc_ctl.py"), "--bus", str(bus), "set", code, str(val)],
                           capture_output=True, text=True, check=False)
        say(f"set {code} {val} rc={r.returncode} try {attempt}")
        if r.returncode == 0:
            return True
    return False


def start(bus, name):
    v = saver_names.vcp(name)
    say(f"saver {name} (VCP {VCP_SAVER} = {v})")
    return ddc_set(bus, VCP_SAVER, v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("action", help="saver name")
    a = ap.parse_args()
    return 0 if start(a.bus, a.action) else 1


if __name__ == "__main__":
    sys.exit(main())
