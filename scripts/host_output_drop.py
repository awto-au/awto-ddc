#!/usr/bin/env python3
"""Drop ONE host output (its logical monitor) for N seconds, then put the layout back exactly as it was.

usage: host_output_drop.py UNIT [--hold-s N]
  UNIT = devices.json unit number (its gdctl connector, e.g. 3 -> HDMI-2). Default hold 5 s (monitor-wait limit).
  The restore args are taken from `gdctl show` BEFORE the drop (dev.gdctl_set_args with the monitor's own current mode =
  every logical monitor unchanged), so the layout returns to the same positions; no keep-changes dialog (temporary set).
  The restore runs in a finally block and on SIGTERM / SIGINT; a primary or only monitor is refused (dev.gdctl_set_args).
Log: ./tmp/logs/host_output_drop.log
"""
import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from _log import log_line as _log_line

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/host_output_drop.log"
SHOW_S = 3          # `gdctl show` is one D-Bus call (~0.1 s); 30x margin, expiry = nothing changed (as dev.py GDCTL_SHOW_S)
SET_S = 15          # a modeset of 4 outputs takes ~2-3 s (as dev.py GDCTL_SET_S); expiry = reported, layout left as mutter has it


def say(s: str) -> None:
    _log_line(s, LOG)


def gdctl_set(args: list[str]) -> int:
    say("gdctl set " + " ".join(args))
    return subprocess.call(["gdctl", "set", *args], timeout=SET_S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("unit")
    ap.add_argument("--hold-s", type=float, default=5.0)
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("awto_dev", ROOT / "dev.py")
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    target = dev._units()[a.unit]["gdctl"]
    show = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=SHOW_S, check=False).stdout
    restore = dev.gdctl_set_args(show, target, _current_mode(show, target))
    drop = _normalise(dev.gdctl_set_args(show, target, "off"))

    def back(*_):
        say(f"restoring {target}")
        gdctl_set(restore)
        sys.exit(1)

    signal.signal(signal.SIGTERM, back)
    signal.signal(signal.SIGINT, back)
    try:
        say(f"dropping {target} (unit {a.unit}) for {a.hold_s:.0f} s")
        if gdctl_set(drop) != 0:
            return 1
        end = time.monotonic() + a.hold_s
        while time.monotonic() < end:
            time.sleep(0.5)             # one gdctl set is already done; 0.5 s polls only for the SIGTERM restore
    finally:
        say(f"restoring {target}")
        gdctl_set(restore)
    say("done")
    return 0


def _normalise(args: list[str]) -> list[str]:
    """mutter wants the remaining layout to start at (0,0): shift every --x / --y by the smallest one"""
    xs = [int(args[i + 1]) for i, v in enumerate(args) if v == "--x"]
    ys = [int(args[i + 1]) for i, v in enumerate(args) if v == "--y"]
    out = list(args)
    for i, v in enumerate(args):
        if v == "--x":
            out[i + 1] = str(int(args[i + 1]) - min(xs))
        elif v == "--y":
            out[i + 1] = str(int(args[i + 1]) - min(ys))
    return out


def _current_mode(show: str, target: str) -> str:
    lines = [ln.strip("│├└─ ") for ln in show.splitlines()]
    name = None
    for i, s in enumerate(lines):
        if s.startswith("Monitor "):
            name = s.split(" ")[1]
        elif s == "Current mode" and name == target:
            return lines[i + 1]
    raise SystemExit(f"{target} has no current mode in gdctl show; nothing done")


if __name__ == "__main__":
    sys.exit(main())
