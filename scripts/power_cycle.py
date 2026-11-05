#!/usr/bin/env python3
"""Mains power-cycle test unit 3 (AWT26110003) via the Sonoff TH outlet so-th-1 (moved from the UNVR bench, Dan 2026-11-06).

usage: power_cycle.py [--on | --off] [--off-s S]
  Uses awto-unvr scripts/_power.py power_set_verified() (ESPHome API via the awto-terminal venv): one implementation.
  Off time: the monitor PSU holds the scaler's standby rail after the relay opens; RAM (safe-block marker) must decay.
Log: ./tmp/logs/power_cycle.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

sys.path.insert(0, "/mnt/2tb/git/awto-unvr/scripts")
from _power import power_set_verified  # noqa: E402

# 10 s: PSU bulk caps keep the 5 V standby rail up for seconds after mains cut; not measured yet (check with
# rtd_diag.py --safe: "last reset: power-on" = RAM decayed). Raise if a cycle still reports WARM.
OFF_S = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    ap.add_argument("--off-s", type=float, default=OFF_S)
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    f = (root / "tmp/logs/power_cycle.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); f.write(line + "\n"); f.flush()
    try:
        if not a.on:
            power_set_verified(False, log=log)
        if a.off:
            return 0
        if not a.on:
            log(f"off for {a.off_s:.0f} s")
            time.sleep(a.off_s)
        power_set_verified(True, log=log)
    except Exception as e:  # noqa: BLE001 - report any outlet failure and exit non-zero
        log(f"FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
