#!/usr/bin/env python3
"""Build/load/unload tools/gmbus_rate (i915 GMBUS DDC clock, #12).

usage: gmbus_rate.py build | load <kHz> [--adapter N] | unload | status
  load: rmmod any previous instance, insmod with adapter/rate. Needs `sudo -n`; if refused it stops.
  status: live reg0 from /sys/module/gmbus_rate/parameters/reg0 (rate bits 10:8: 0=100k 1=50k 2=400k 3=1M).
Log: ./tmp/logs/gmbus_rate.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from _log import log_line as _log_line


def repo_root():
    e = os.environ.get("AWTO_DDC_REPO")
    if e:
        return Path(e)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent, check=False)
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
    _log_line(msg, LOG)


def run(cmd, timeout):
    log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    for l in (r.stdout + r.stderr).splitlines():
        log("  " + l)
    return r


def sudo(cmd):
    r = run(["sudo", "-n"] + cmd, T_SUDO)
    if r.returncode != 0 and "password" in (r.stderr or "").lower():
        log("sudo -n refused: STOP")
        sys.exit(2)
    return r


def vermagic_release(text: str) -> str:
    """Kernel release a module was built for: the first word of modinfo's vermagic line ("7.3.4-300.fc45.x86_64 SMP preempt ...")."""
    words = text.split()
    return words[0] if words else ""


def ko_matches_kernel() -> bool:
    """False when the built module is missing or was built for another kernel (insmod then fails with 'Invalid module format')."""
    if not KO.exists():
        return False
    r = subprocess.run(["modinfo", "-F", "vermagic", str(KO)], capture_output=True, text=True, timeout=T_SUDO, check=False)
    return r.returncode == 0 and vermagic_release(r.stdout) == os.uname().release


def ensure_built() -> int:
    """Build for the running kernel unless the .ko already matches it; 0 = ready. A kernel update therefore needs no manual step."""
    if ko_matches_kernel():
        return 0
    log(f"module missing or built for another kernel (running {os.uname().release}): rebuilding")
    if KO.exists():
        run(["make", "-C", str(SRC), "clean"], T_MAKE)
    return run(["make", "-C", str(SRC)], T_MAKE).returncode


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
    if a.cmd == "build":
        sys.exit(ensure_built())
    if a.cmd == "status":
        status()
    elif a.cmd == "unload":
        if PARAM.exists():
            sudo(["rmmod", "gmbus_rate"])
        status()
    else:
        if a.khz not in (50, 100, 400, 1000):
            sys.exit("khz must be 50|100|400|1000")
        if ensure_built():
            sys.exit(1)
        if PARAM.exists():
            sudo(["rmmod", "gmbus_rate"])
        r = sudo(["insmod", str(KO), f"adapter={a.adapter}", f"rate={a.khz}"])
        status()
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
