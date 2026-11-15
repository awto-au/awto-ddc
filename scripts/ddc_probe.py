#!/usr/bin/env python3
"""DDC/CI Get-VCP answer latency while the unit blocks in waits (awto-ddc#216 stage 2).

usage: ddc_probe.py BUS --serial S [--secs 3] [--vcp 0x10] [--cycle]
  Loops `ddcutil getvcp` (--maxtries 1,1,1: one request, no retry) for --secs and prints per call: time since start, ok / NAK, ms. Run it while
  the unit boots / switches mode (e.g. in a second shell: boot_prof.py --power-key). Without the wait pump a request that lands
  in a 130 ms delay or a 190 ms run of frame waits is answered late or not at all.
Log: ./tmp/logs/ddc_probe.log
"""
import argparse, os, subprocess, sys, time
import isostamp  # noqa: E402
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/ddc_probe.log"
OFF_S = 4.0             # DPM off: panel off sequence + T6 + settle (boot_prof.py OFF_S)
CALL_S = 2.0            # ddcutil with --noretry answers or fails inside ~0.1 s; 2 s = hung call, killed and counted as a failure


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--vcp", default="0x10")
    ap.add_argument("--cycle", action="store_true", help="DPM off, wait OFF_S, DPM on, then probe from the on write")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import i2cbus  # noqa: E402

    i2cbus.require_unit(a.bus, a.serial)
    if a.cycle:
        subprocess.run(["ddcutil", "--bus", str(a.bus), "setvcp", "0xD6", "4"], capture_output=True, timeout=CALL_S)
        time.sleep(OFF_S)
        subprocess.run(["ddcutil", "--bus", str(a.bus), "--maxtries", "1,1,1", "setvcp", "0xD6", "1"], capture_output=True, timeout=CALL_S)
    t0, ok, bad, worst = time.monotonic(), 0, 0, 0.0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        while time.monotonic() - t0 < a.secs:
            t1 = time.monotonic()
            try:
                r = subprocess.run(["ddcutil", "--bus", str(a.bus), "--maxtries", "1,1,1", "--terse", "getvcp", a.vcp], capture_output=True, text=True, timeout=CALL_S)
                good = r.returncode == 0
            except subprocess.TimeoutExpired:
                good = False
            ms = (time.monotonic() - t1) * 1000
            ok, bad, worst = ok + good, bad + (not good), max(worst, ms)
            line = f"{isostamp.now()} +{t1 - t0:5.2f} s  {'ok ' if good else 'FAIL'} {ms:6.0f} ms"
            f.write(line + "\n")
            print(line, flush=True)
    print(f"{ok} ok, {bad} failed, slowest {worst:.0f} ms")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
