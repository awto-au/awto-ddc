#!/usr/bin/env python3
"""Wait for a scaler to appear on an I2C bus after power-on, then record which slaves ACK, every POLL_S, for WINDOW_S.

usage: rtd_boot_probe.py <bus> [--window S]
  Probes 0x35 (debug), 0x4A (ISP), 0x50 (EDID), 0x54 (SCDC) with zero-length-safe 1-byte reads (no writes).
  Shows whether the slaves stay up through the firmware's safe-boot window (#26).
Log: ./tmp/logs/rtd_boot_probe.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, fcntl, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

I2C_SLAVE = 0x0703
ADDRS = (0x35, 0x4A, 0x50, 0x54)
POLL_S = 0.05            # 20 samples/s: resolves the 2 s safe window (_AWTO_SAFE_BOOT_MS) into 40 rows
WAIT_S = 1800            # waiting for a human power cycle
WINDOW_S = 6.0           # 2 s window + ~0.6 s init + margin to see the main loop take over


def acks(fd) -> str:
    out = []
    for a in ADDRS:
        try:
            fcntl.ioctl(fd, I2C_SLAVE, a)
            os.read(fd, 1)
            out.append(f"{a:02x}")
        except OSError:
            out.append("--")
    return " ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--window", type=float, default=WINDOW_S)
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/rtd_boot_probe.log").open("a")

    def out(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); log.write(line + "\n"); log.flush()
    fd = os.open(f"/dev/i2c-{a.bus}", os.O_RDWR)
    t0 = time.monotonic()
    out(f"bus {a.bus}: waiting for any of {' '.join(f'{x:02x}' for x in ADDRS)} (power-cycle the unit)")
    while "".join(acks(fd).split()).strip("-") == "":
        if time.monotonic() - t0 > WAIT_S:
            out("timeout: nothing answered"); return 1
        time.sleep(POLL_S)
    t1 = time.monotonic()
    prev = None
    while time.monotonic() - t1 < a.window:
        s = acks(fd)
        if s != prev:
            out(f"+{time.monotonic() - t1:5.2f} s  {' '.join(f'{x:02x}' for x in ADDRS)}: {s}")
            prev = s
        time.sleep(POLL_S)
    out(f"+{a.window:.2f} s  end: {prev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
