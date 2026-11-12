#!/usr/bin/env python3
"""Build/load/unload tools/gmbus_rate (i915 GMBUS DDC clock, #12).

usage: gmbus_rate.py build | load <kHz> [--adapter N] | unload | status
  load: rmmod any previous instance, insmod with adapter/rate. Needs `sudo -n`; if refused it stops.
  status: live reg0 from /sys/module/gmbus_rate/parameters/reg0 (rate bits 10:8: 0=100k 1=50k 2=400k 3=1M).
Log: ./tmp/logs/gmbus_rate.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, os, subprocess, sys
from datetime import datetime
from pathlib import Path


def repo_root():
    e = os.environ.get("AWTO_DDC_REPO")
    if e:
        return Path(e)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parent.parent


ROOT = repo_root()
SRC = ROOT / "tools" / "gmbus_rate"
KO = SRC / "gmbus_rate.ko"
PARAM = Path("/sys/module/gmbus_rate/parameters/reg0")
LOG = ROOT / "tmp" / "logs" / "gmbus_rate.log"
CODES = {0: "100 kHz", 1: "50 kHz", 2: "400 kHz", 3: "1 MHz"}
# Stall guard: each command prints/returns in well under a second; make takes ~5 s cold.
T_MAKE, T_SUDO = 60, 10


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run(cmd, timeout):
    log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    for l in (r.stdout + r.stderr).splitlines():
        log("  " + l)
    return r


def sudo(cmd):
    r = run(["sudo", "-n"] + cmd, T_SUDO)
    if r.returncode != 0 and "password" in (r.stderr or "").lower():
        log("sudo -n refused: STOP")
        sys.exit(2)
    return r


def status():
    if not PARAM.exists():
        log("status: module not loaded (100 kHz, i915 default)")
        return None
    v = int(PARAM.read_text().strip(), 16)
    log(f"status: reg0=0x{v:x} rate={CODES.get((v >> 8) & 7, '?')}")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "load", "unload", "status"])
    ap.add_argument("khz", nargs="?", type=int)
    ap.add_argument("--adapter", type=int, default=11)
    a = ap.parse_args()
    if a.cmd == "load":
        log("load refused: gmbus_rate is retired (#159, host hang 2026-11-12); bus stays 100 kHz")
        sys.exit(2)
    if a.cmd == "build":
        sys.exit(run(["make", "-C", str(SRC)], T_MAKE).returncode)
    if a.cmd == "status":
        status()
    elif a.cmd == "unload":
        if PARAM.exists():
            sudo(["rmmod", "gmbus_rate"])
        status()
    else:
        if a.khz not in (50, 100, 400, 1000):
            sys.exit("khz must be 50|100|400|1000")
        if not KO.exists() and run(["make", "-C", str(SRC)], T_MAKE).returncode:
            sys.exit(1)
        if PARAM.exists():
            sudo(["rmmod", "gmbus_rate"])
        r = sudo(["insmod", str(KO), f"adapter={a.adapter}", f"rate={a.khz}"])
        status()
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
