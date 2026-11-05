#!/usr/bin/env python3
"""Read-only dump of a sink's HDMI 2.0 SCDC registers (I2C 0x54) over a host DDC bus.

usage: hdmi_scdc.py <bus>
  Source: HDMI 2.0 spec SCDC map. Reads only (write offset, read N); never writes a register.
  0x01 sink ver | 0x20 TMDS config (b0 scrambling enable, b1 clock ratio 1/40) | 0x21 scrambler status (b0)
  0x40 status flags 0 (b0 clock detected, b1-3 ch0-2 locked) | 0x50-0x55 ch0-2 char error count (15 bit, b15 valid)
Log: ./tmp/logs/hdmi_scdc.log. Repo root: $AWTO_DDC_REPO -> git -> file-relative.
"""
import argparse, ctypes, fcntl, os, subprocess, time
from pathlib import Path

SCDC = 0x54
I2C_RDWR, I2C_M_RD = 0x0707, 0x0001


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16), ("len", ctypes.c_uint16),
                ("buf", ctypes.POINTER(ctypes.c_uint8))]


class RdWr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


def repo_root() -> Path:
    if os.environ.get("AWTO_DDC_REPO"):
        return Path(os.environ["AWTO_DDC_REPO"])
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True,
                                            cwd=Path(__file__).parent).strip())
    except (subprocess.CalledProcessError, OSError):
        return Path(__file__).resolve().parent.parent


def read(fd: int, off: int, n: int) -> bytes:
    wbuf, rbuf = (ctypes.c_uint8 * 1)(off), (ctypes.c_uint8 * n)()
    msgs = (Msg * 2)(Msg(SCDC, 0, 1, wbuf), Msg(SCDC, I2C_M_RD, n, rbuf))
    fcntl.ioctl(fd, I2C_RDWR, RdWr(msgs, 2))
    return bytes(rbuf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    a = ap.parse_args()
    logd = repo_root() / "tmp/logs"
    logd.mkdir(parents=True, exist_ok=True)
    fd = os.open(f"/dev/i2c-{a.bus}", os.O_RDWR)
    try:
        ver, cfg, scr = read(fd, 0x01, 1)[0], read(fd, 0x20, 1)[0], read(fd, 0x21, 1)[0]
        st, err = read(fd, 0x40, 1)[0], read(fd, 0x50, 7)
    except OSError as e:
        line = f"bus {a.bus}: SCDC 0x54 no answer ({e})"
    else:
        errs = [(err[2 * i + 1] << 8 | err[2 * i]) for i in range(3)]
        cnt = " ".join(f"ch{i}={'' if e & 0x8000 else '(invalid)'}{e & 0x7FFF}" for i, e in enumerate(errs))
        line = (f"bus {a.bus}: sink ver {ver}  TMDS cfg 0x{cfg:02x} (scramble {cfg & 1}, ratio 1/{40 if cfg & 2 else 10})"
                f"  scrambler status {scr & 1}  flags 0x{st:02x} (clock {st & 1}, lock ch0-2 "
                f"{(st >> 1) & 1}{(st >> 2) & 1}{(st >> 3) & 1})  errors {cnt}")
    finally:
        os.close(fd)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}"
    print(line)
    with open(logd / "hdmi_scdc.log", "a") as f:
        f.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
