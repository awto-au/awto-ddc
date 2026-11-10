#!/usr/bin/env python3
"""Unused-GPIO monitor over the running firmware's debug I2C slave 0x35.

The firmware samples package pins 65,66,67,68,69,70,74,75,96 and the six physical buttons. `_g_stAwtoGpio` contains
an initial/current bitmap plus a 32-entry transition ring. `watch` reads the small header continuously and fetches
the ring only when its sequence changes. `open`/`close` control the live OSD through the normal test-command byte.
"""
import argparse, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

INPUTS = ("pin65", "pin66", "pin67", "pin68", "pin69", "pin70", "pin74", "pin75", "pin96",
          "SOURCE", "MENU", "DOWN", "UP", "AUTO", "POWER")
HDR_N, ENTRY_N, LOG_N, TOTAL_N = 20, 4, 32, 20 + 4 * 32
DEV8, TESTCMD_OFF = 0x6A, 0x28
# Board IO rows (screen page 2), same order as tAwtoIoPin in fw/sdcc/awto_gpio.inc: (name, package pin, direction)
BOARD_IO = (("IR", 194, "in"), ("HPSEL", 113, "in"), ("H2HPD", 1, "in"), ("H1HPD", 14, "in"), ("DPHPD", 97, "in"),
            ("H2CBL", 198, "in"), ("H1CBL", 204, "in"), ("DPS17", 206, "in"), ("DPS15", 207, "in"), ("DPS16", 208, "in"),
            ("BLEN", 196, "out"), ("PNLPW", 159, "out"), ("MUTE", 161, "out"), ("PWR1", 184, "out"), ("PWR2", 185, "out"),
            ("PWR3", 201, "out"), ("PWR4", 202, "out"), ("FLWP", 190, "out"))


def symbol(text: str, name: str) -> int:
    # SDCC emits some absolute XDATA symbols without the leading ``D:`` that
    # it uses for relocatable data symbols.  Both forms are data addresses.
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{re.escape(name)}\b", text, re.M)
    if not m:
        raise SystemExit(f"_{name} is not present in this image map")
    return int(m.group(1), 16)


def read_stable(io, addr: int) -> bytes:
    for _ in range(4):
        data = X.read_blocks(io, addr, TOTAL_N)
        tail = X.read_blocks(io, addr, HDR_N)
        if data and tail and data[:2] == b"GP" and data[2] in (1, 2, 3) and data[5] == tail[5]:
            return data
    raise SystemExit("GPIO diagnostic block was changing or unreadable over I2C")


def levels(h: bytes) -> int:
    return h[6] | h[7] << 8


def show_snapshot(h: bytes) -> None:
    v = levels(h)
    gpio = " ".join(f"{name}={(v >> i) & 1}" for i, name in enumerate(INPUTS[:9]))
    keys = " ".join(f"{name}={(v >> i) & 1}" for i, name in enumerate(INPUTS[9:], 9))
    adc = ""
    if h[2] >= 3:
        adc = "  " + " ".join(f"ADC{i}={h[13 + i]}({h[13 + i] * 3.3 / 255:.3f}V)" for i in range(3))
        adc += f"  VGA_SYNC=0x{h[16]:02x} VGA_CMP=0x{h[17]:02x} VGA_PWR=0x{h[18]:02x}"
    print(f"snapshot {gpio}  buttons {keys}{adc}  transitions={h[5]} changed=0x{(h[8] | h[9] << 8):04x}")


def show_board_io(io, mp: str) -> None:
    """Board IO levels and the open screen page, read from the firmware's own sampler (images before txt5 lack them)."""
    try:
        lv_addr, page_addr = symbol(mp, "g_ucAwtoIoLv"), symbol(mp, "g_ucAwtoGpioPage")
    except SystemExit:
        print("board IO: not in this image")
        return
    lv, page = X.read_blocks(io, lv_addr, 3), X.read_blocks(io, page_addr, 1)
    if not lv or not page:
        print("board IO: I2C read failed")
        return
    v = lv[0] | lv[1] << 8 | lv[2] << 16
    row = lambda sel: " ".join(f"{n}({pin})={(v >> i) & 1}" for i, (n, pin, d) in enumerate(BOARD_IO) if d == sel)
    print(f"board IO (screen page {page[0] + 1}/2)  inputs: {row('in')}")
    print(f"board IO  outputs read back: {row('out')}")


def write_cmd(io, diag: int, cmd: int) -> None:
    a = diag + TESTCMD_OFF
    ok = (io.write(DEV8, 0x01, bytes([a >> 8])) and io.write(DEV8, 0x03, bytes([cmd])) and
          io.write(DEV8, 0x3B, bytes([a & 0xFF])))
    if not ok:
        raise SystemExit(f"I2C write of GPIO OSD command 0x{cmd:02x} failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("command", choices=("snapshot", "watch", "open", "close"), nargs="?", default="snapshot")
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--secs", type=float, default=30.0)
    a = ap.parse_args()
    i2cbus.require_unit(a.bus, a.serial)
    mp = a.map.read_text(errors="replace")
    base, diag = symbol(mp, "g_stAwtoGpio"), symbol(mp, "g_stAwtoDiag")
    logs = B.setup_logs("gpio_diag", map=str(a.map))
    io = B.Real(a.bus, allow_write=True)
    try:
        if a.command in ("open", "close"):
            write_cmd(io, diag, 0x43 if a.command == "open" else 0x44)
            print(f"GPIO input screen {a.command} command sent")
            return 0
        data = read_stable(io, base)
        show_snapshot(data)
        show_board_io(io, mp)
        if a.command == "snapshot":
            return 0
        last = data[5]
        end = time.monotonic() + a.secs
        while time.monotonic() < end:
            h = X.read_blocks(io, base, HDR_N)
            if not h or h[:2] != b"GP":
                time.sleep(0.02)
                continue
            cur = h[5]
            if cur == last:
                time.sleep(0.02)
                continue
            data = read_stable(io, base)
            cur = data[5]
            delta = (cur - last) & 0xFF
            if delta > LOG_N:
                print(f"lost {delta - LOG_N} transitions (ring holds {LOG_N})")
                last = (cur - LOG_N) & 0xFF
            while last != cur:
                off = HDR_N + (last & (LOG_N - 1)) * ENTRY_N
                seq, hi, lo, ps = data[off:off + ENTRY_N]
                if seq != last:
                    print(f"ring overwrite at sequence {last}; resynchronising")
                    break
                idx, state = ps >> 1, ps & 1
                name = INPUTS[idx] if idx < len(INPUTS) else f"input{idx}"
                line = f"seq={seq:03d} tick={(hi << 8 | lo):05d}ms input={name} state={state}"
                print(line, flush=True)
                logs.main.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n"); logs.main.flush()
                last = (last + 1) & 0xFF
            last = cur
        return 0
    finally:
        io.close()


if __name__ == "__main__":
    raise SystemExit(main())
