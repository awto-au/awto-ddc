#!/usr/bin/env python3
"""Drive the full-screen Pac-Man demo from a VS Code terminal keyboard.

Arrow keys steer.  The firmware keeps moving in demo mode between key presses.
Escape or Q closes the OSD and exits.
"""
from __future__ import annotations

import argparse
import os
import select
import sys
import termios
import time
import tty
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import rtd_i2c_bridge as B
import settings_cli as C

DEV8 = 0x6A
TESTCMD_OFFSET = 0x28
KEY_CMD = {b"\x1b[A": 0x62, b"\x1b[B": 0x63, b"\x1b[D": 0x64, b"\x1b[C": 0x65}


def read_key(fd: int) -> bytes:
    key = os.read(fd, 1)
    if key != b"\x1b":
        return key
    end = time.monotonic() + 0.04
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], end - time.monotonic())
        if not ready:
            break
        key += os.read(fd, 1)
        if len(key) >= 3:
            break
    return key


def write_cmd(dev: B.Real, address: int, command: int) -> None:
    ok = (dev.write(DEV8, 0x01, bytes([address >> 8])) and
          dev.write(DEV8, 0x03, bytes([command])) and
          dev.write(DEV8, 0x3B, bytes([address & 0xFF])))
    if not ok:
        raise SystemExit(f"debug write 0x{address:04X} <- 0x{command:02X}: no ACK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True)
    args = ap.parse_args()
    if not sys.stdin.isatty():
        raise SystemExit("keyboard control needs the VS Code terminal")
    i2cbus.require_unit(args.bus, args.serial)
    B.setup_logs("pacman_cli", map=args.map)
    diag = C.xaddr(Path(args.map).read_text(errors="replace"), "g_stAwtoDiag")
    testcmd = diag + TESTCMD_OFFSET
    dev = B.Real(args.bus, allow_write=True)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    write_cmd(dev, testcmd, 0x60)
    print("Pac-Man demo: arrows steer | Esc/Q closes", flush=True)
    try:
        tty.setcbreak(fd)
        while True:
            key = read_key(fd)
            if key in (b"q", b"Q", b"\x03", b"\x1b"):
                break
            command = KEY_CMD.get(key)
            if command is not None:
                write_cmd(dev, testcmd, command)
    finally:
        write_cmd(dev, testcmd, 0x61)
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    print("Pac-Man demo closed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
