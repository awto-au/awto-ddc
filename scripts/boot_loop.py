#!/usr/bin/env python3
"""Boot loop on the test unit: N x `./dev.py reset`, wait for a verdict, keep every boot's sync log (docs/clock-sweep.md "Default image at 350.8 MHz").

usage: boot_loop.py [--unit 3] [--boots N] [--tag T]
  Per boot: reset (ISP 0xEE, no mains), then poll `./dev.py synclog` until the boot episode shows ACTIVE ("display set") or NO SIGNAL, or VERDICT_S expires.
  Result per boot: ACTIVE / NO PICTURE / UNKNOWN, TMDS clock measured, count of eDP "link training FAIL". Sync log text -> ./tmp/logs/boot_loop/<tag>-<n>.txt,
  one line per boot + a summary -> ./tmp/logs/boot_loop.log. Only ./dev.py is used for the unit.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/boot_loop.log"
DIR = ROOT / "tmp/logs/boot_loop"
# Verdict wait: the firmware reports ACTIVE ~1.3 s after the reset (sync log) and the no-signal verdict at 4.3 s (SEARCH timeout): 4.3 s x 1.25 + link up time ~ 7 s; expiry = UNKNOWN
VERDICT_S = 7.0


def say(s: str) -> None:
    _log_line(s, LOG)


def dev(*a: str) -> str:
    r = subprocess.run([str(ROOT / "dev.py"), *a], capture_output=True, text=True, cwd=ROOT, check=False)  # rc ignored: callers parse the dev.py output
    return r.stdout + r.stderr


def one(unit: str, n: int, tag: str, dump: list[str], after: list[str]) -> tuple[str, bool, int]:
    dev("reset", "--unit", unit)
    t0 = time.monotonic()
    out = ""
    while time.monotonic() - t0 < VERDICT_S:
        out = dev("synclog", "--unit", unit)
        if "ACTIVE:display set" in out or "NO SIGNAL" in out:
            break
    DIR.mkdir(parents=True, exist_ok=True)
    for d in dump:
        out += f"\n--- dbg-read {d}\n" + dev("dbg-read", "--unit", unit, d)
    if after:
        out += "\n--- dev.py " + " ".join(after) + "\n" + dev(after[0], "--unit", unit, *after[1:])
    (DIR / f"{tag}-{n:03d}.txt").write_text(out)
    ok = "ACTIVE:display set" in out
    verdict = "ACTIVE" if ok else ("NO PICTURE" if "NO SIGNAL" in out else "UNKNOWN")
    return verdict, "TMDS clock" in out, out.count("link training FAIL")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="3")
    ap.add_argument("--boots", type=int, default=20)
    ap.add_argument("--tag", default="boot")
    ap.add_argument("--after", default="", help="extra ./dev.py command (words) run after the verdict, its output is saved with the sync log, e.g. 'diag --messages --secs 2'")
    ap.add_argument("--dump", default="", help="comma list ADDR:LEN read over the debug link after the verdict (dbg-read), saved next to the sync log, e.g. 0x71E0:32")
    a = ap.parse_args()
    res = []
    for n in range(a.boots):
        v, tm, fl = one(a.unit, n, a.tag, [x for x in a.dump.split(",") if x], a.after.split())
        res.append(v)
        say(f"boot {n}: {v}, TMDS clock measured {tm}, eDP link training FAIL x{fl}")
    say(f"SUMMARY {a.tag}: {res.count('ACTIVE')} of {a.boots} boots with a picture, {res.count('NO PICTURE')} no picture, {res.count('UNKNOWN')} unknown")
    return 0 if res.count("ACTIVE") == a.boots else 1


if __name__ == "__main__":
    sys.exit(main())
