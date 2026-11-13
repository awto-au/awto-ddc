#!/usr/bin/env python3
"""Ear test of loudness/clipping per user volume (#94): for each VCP 0x62 volume, play tones; volume restored after.

Each tone is announced on the diagnostics console (VCP 0x63 Hz announce). Log: tmp/logs/audio_levels.log.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def _repo() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True,
                                            cwd=Path(__file__).parent).strip())
    except (OSError, subprocess.CalledProcessError):
        return Path(__file__).resolve().parent.parent


REPO = _repo()
LOG = REPO / "tmp/logs/audio_levels.log"
DDC_S = 5.0          # one ddcutil set/get: ~0.2 s typical on bus 11 at 1 MHz; 5 s = hung bus, logged + exit 1
HZ_FLAG = 0x8000     # VCP 0x63 high bit = tone announce (fw/sdcc/awto_audio.inc AWTO_AUDIO_TEST_HZ_FLAG)


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def ddc(bus: int, *args: str) -> str:
    t0 = time.monotonic()
    try:
        r = subprocess.run(["ddcutil", "--bus", str(bus), "--noverify", *args], capture_output=True, text=True, timeout=DDC_S)
    except subprocess.TimeoutExpired:
        log(f"ddcutil {' '.join(args)}: no answer in {DDC_S:.0f} s (elapsed {time.monotonic() - t0:.1f} s)")
        sys.exit(1)
    if r.returncode:
        log(f"ddcutil {' '.join(args)}: rc {r.returncode} {r.stderr.strip()[:160]}")
        sys.exit(1)
    return r.stdout.strip()


def getvol(bus: int) -> int:
    out = ddc(bus, "getvcp", "62")                 # "VCP code 0x62 (...): Volume level: 100 (00x64)"
    m = re.search(r"(?:current value\s*=|Volume level:)\s*(\d+)", out)
    if not m:
        log(f"getvcp 62: unparsed reply {out[:120]!r}")
        sys.exit(1)
    return int(m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--connector", required=True)
    ap.add_argument("--vols", default="90,80,70,60,50", help="VCP 0x62 volumes, played in this order")
    ap.add_argument("--freqs", default="200,1000")
    ap.add_argument("--secs", type=float, default=2.0)
    a = ap.parse_args()
    vols = [int(v) for v in a.vols.split(",")]
    freqs = [int(f) for f in a.freqs.split(",")]
    before = getvol(a.bus)
    log(f"LEVELS START: volumes {vols}, tones {freqs} Hz, {a.secs:.0f} s each; volume before {before}")
    tone = [sys.executable, str(REPO / "scripts/audio_test.py"), "tone", "--bus", str(a.bus), "--serial", a.serial,
            "--connector", a.connector, "--secs", str(a.secs)]
    bad = 0
    try:
        for v in vols:
            ddc(a.bus, "setvcp", "62", str(v))
            log(f"VOLUME {v} START {time.strftime('%H:%M:%S')} (read back {getvol(a.bus)})")
            for hz in freqs:
                ddc(a.bus, "setvcp", "63", f"0x{HZ_FLAG | hz:04X}")
                r = subprocess.run([*tone, "--hz", str(hz)], capture_output=True, text=True)
                bad += r.returncode != 0
                log(f"  VOLUME {v} TONE {hz} Hz END {time.strftime('%H:%M:%S')} rc {r.returncode}")
    finally:
        ddc(a.bus, "setvcp", "62", str(before))
        log(f"LEVELS END {time.strftime('%H:%M:%S')}: {bad} tone failure(s); volume restored to {getvol(a.bus)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
