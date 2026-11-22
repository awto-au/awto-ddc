#!/usr/bin/env python3
"""1 s alert tone on the monitor's speaker: before a flash, or when an agent needs Dan (#229).

usage: alert.py --bus N [--wait] [--auto]      DDC/CI VCP 0xEB = 6 (screensaver_now "Alert tone"); firmware plays the 1 s rising beep-beep-BEEEP
  --wait: return after the tone has finished (a flash must not start while the generator is on: a held tone stays on while the MCU is halted).
  Old firmware (VCP 0xEB max < 6): logged, nothing played, exit 0.
  --auto: automatic callers (flash warning, saver tour): skipped when the unit is muted (VCP 0x8D = 1), when the mute state can't be read,
  or when env AWTO_SOUND=off; one log line either way. Without --auto (explicit `./dev.py alert`) the tone always plays.
Library: alert(bus, wait=False) -> bool; alert_auto(bus, wait=False) -> bool. Volume = the monitor's own (VCP 0x62).
Log: ./tmp/logs/alert.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from _log import log_line as _log_line
from ddcutil_run import ddc as _ddc

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/alert.log"
VCP_SAVER = 0xEB
VCP_ALERT = 6                   # screensaver_now option "Alert tone" (registry row 121)
VCP_MUTE = 0x8D                 # Audio Mute: sl 1 = muted, 2 = unmuted
MUTED = 1
TONE_S = 1.0                    # the track length (scripts/pacman_sound.py ALERT: 150+50+150+50+600 ms)
TAIL_S = 0.3                    # + the main-loop pass that starts it (<= 0.1 s) and the DDC write time, with margin


def say(s: str) -> None:
    _log_line(s, LOG)


def alert(bus: int, wait: bool = False) -> bool:
    r = _ddc(bus, "getvcp", f"{VCP_SAVER:02X}")
    m = re.search(r"ml=0x([0-9a-f]+)", r.stdout) if r else None
    top = int(m.group(1), 16) if m else 0
    if top < VCP_ALERT:
        say(f"alert: firmware accepts VCP {VCP_SAVER:02X} up to {top} < {VCP_ALERT}: no tone")
        return False
    ok = _ddc(bus, "setvcp", f"{VCP_SAVER:02X}", str(VCP_ALERT)) is not None
    say(f"alert: setvcp {VCP_SAVER:02X} {VCP_ALERT} on bus {bus}: {'ok' if ok else 'FAILED'}")
    if ok and wait:
        time.sleep(TONE_S + TAIL_S)
    return ok


def muted(bus: int) -> bool | None:
    """True = muted, False = not muted, None = unreadable."""
    r = _ddc(bus, "getvcp", f"{VCP_MUTE:02X}")
    m = re.search(r"sl=0x([0-9a-f]+)", r.stdout) if r else None
    return None if not m else int(m.group(1), 16) == MUTED


def alert_auto(bus: int, wait: bool = False) -> bool:
    """Tone for automatic callers; mute means mute. Unreadable mute state = skip (safe default). Always logs one line."""
    if os.environ.get("AWTO_SOUND", "").lower() == "off":
        say("alert tone skipped: AWTO_SOUND=off")
        return False
    m = muted(bus)
    if m is None:
        say(f"alert tone skipped: mute state (VCP {VCP_MUTE:02X}) unreadable on bus {bus}")
        return False
    if m:
        say("alert tone skipped: unit muted")
        return False
    ok = alert(bus, wait)
    say("alert tone played" if ok else "alert tone not played (see above)")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--auto", action="store_true", help="automatic caller: honour mute and AWTO_SOUND=off")
    a = ap.parse_args()
    (alert_auto if a.auto else alert)(a.bus, a.wait)
    return 0


if __name__ == "__main__":
    sys.exit(main())
