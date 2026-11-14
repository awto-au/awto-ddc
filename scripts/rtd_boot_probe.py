#!/usr/bin/env python3
"""Wait for a scaler to appear on an I2C bus after power-on, then record which slaves ACK, every POLL_S, for WINDOW_S.

usage: rtd_boot_probe.py <bus>|all [--window S]   (all = every i915/NVIDIA/AUX display bus)
  Probes 0x35 (debug), 0x4A (ISP), 0x50 (EDID), 0x54 (SCDC) with zero-length-safe 1-byte reads (no writes).
  Shows whether the slaves stay up through the firmware's safe-boot window (#26).
Log: ./tmp/logs/rtd_boot_probe.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import i2cbus  # noqa: E402

ADDRS = (0x35, 0x4A, 0x50, 0x54)
POLL_S = 0.05            # 20 samples/s: resolves the 2 s safe window (_AWTO_SAFE_BOOT_MS) into 40 rows
WAIT_S = 1800            # waiting for a human power cycle
WINDOW_S = 6.0           # default watch length; use --window 60 to cover a power cycle


def acks(bus: i2cbus.Bus) -> str:
    return " ".join(f"{a:02x}" if bus.probe(a) else "--" for a in ADDRS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus")
    ap.add_argument("--window", type=float, default=WINDOW_S)
    a = ap.parse_args()
    i2cbus.dev_hint("probe", "rtd_boot_probe.py")
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/rtd_boot_probe.log").open("a")

    def out(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); log.write(line + "\n"); log.flush()
    if a.bus == "all":
        buses = i2cbus.list_buses(display_only=True)
    else:
        buses = [int(a.bus)]
    fds = {b: i2cbus.Bus(b) for b in buses}
    t0 = time.monotonic()
    out(f"buses {buses}: logging every change of {' '.join(f'{x:02x}' for x in ADDRS)} for {a.window:.0f} s")
    prev = {}
    while time.monotonic() - t0 < a.window:
        for b, fd in fds.items():
            s = acks(fd)
            if s != prev.get(b):
                out(f"+{time.monotonic() - t0:6.2f} s  bus {b:2d}: {s}")
                prev[b] = s
        time.sleep(POLL_S)
    return 0


if __name__ == "__main__":
    sys.exit(main())
