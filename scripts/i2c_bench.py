#!/usr/bin/env python3
"""Read-throughput benchmark of /dev/i2c-N buses against an RTD scaler. No writes except the register-pointer byte.

usage: i2c_bench.py <bus> [<bus> ...]
For each bus, address (0x50 EDID, 0x4A ISP reg 0x70) and read size, runs a fixed window and prints KB/s.
Window: 3 s per combo = >=60 transactions at the ~50 ms/64 B seen on DP AUX; enough for a stable mean.
Stops a combo after 3 consecutive errors (logs errno). Log: ./tmp/logs/i2c_bench.log
"""
import ctypes, fcntl, os, sys, time
from pathlib import Path

I2C_RDWR, I2C_M_RD = 0x0707, 1
WINDOW_S = 3.0
SIZES = (16, 32, 64, 128, 255)
TARGETS = ((0x50, 0x00, "EDID"), (0x4A, 0x70, "ISP reg 0x70"))


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]


class RdWr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


def xfer(fd, addr, reg, n):
    w = ctypes.create_string_buffer(bytes([reg]), 1)
    r = ctypes.create_string_buffer(n)
    arr = (Msg * 2)(Msg(addr, 0, 1, ctypes.addressof(w)), Msg(addr, I2C_M_RD, n, ctypes.addressof(r)))
    fcntl.ioctl(fd, I2C_RDWR, RdWr(arr, 2))


def main() -> int:
    root = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp" / "logs" / "i2c_bench.log").open("a")

    def out(s):
        print(s); log.write(s + "\n"); log.flush()

    out(f"# {time.strftime('%Y-%m-%dT%H:%M:%S%z')} window={WINDOW_S}s")
    for bus in map(int, sys.argv[1:]):
        fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        for addr, reg, label in TARGETS:
            for n in SIZES:
                done = errs = consec = 0
                err_no = None
                t0 = time.time()
                while time.time() - t0 < WINDOW_S and consec < 3:
                    try:
                        xfer(fd, addr, reg, n); done += 1; consec = 0
                    except OSError as e:
                        errs += 1; consec += 1; err_no = e.errno
                dt = time.time() - t0
                kbs = done * n / dt / 1024
                out(f"bus={bus:2d} {label:12s} n={n:3d}  {kbs:6.2f} KB/s  ok={done} err={errs}"
                    + (f" errno={err_no}" if err_no else ""))
        os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
