#!/usr/bin/env python3
"""The ONLY code that opens /dev/i2c-N (awto-ddc#48). tests/test_i2c_single_layer.py fails otherwise.

Layers: Bus (open, I2C_RDWR, raw read/write, retries/timeout ioctls, protocol-decoder taps) ->
        helpers (edid_serial, require_unit, gmbus_nudge, bus listing) -> fast_bus (1 MHz around ISP flashing only).
Everything else (rtd_isp_probe.Isp, rtd_i2c_bridge.Real, rtd_osd, ...) goes through Bus.
Direct script runs print dev_hint(); ./dev.py <command> is the entry point (unit -> bus by EDID serial, rate, logs).
"""
from __future__ import annotations

import ctypes
import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_proto  # noqa: E402

I2C_RETRIES, I2C_TIMEOUT, I2C_SLAVE, I2C_RDWR = 0x0701, 0x0702, 0x0703, 0x0707   # linux/i2c-dev.h
I2C_M_RD = 1
I2C_RETRIES_DEFAULT = 1     # i915 gmbus sets adapter.retries = 1 (intel_gmbus.c); restored after a page
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]


class RdWr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.c_void_p), ("nmsgs", ctypes.c_uint32)]


def run_ops(xfer, addr: int, ops) -> list[bytes]:
    """Build Msg structs for ops (bytes = write msg, int n = read msg), call xfer(msgs), return the read buffers.
    xfer is a parameter so a fake bus (tests) can sit below the message construction."""
    keep, msgs, reads = [], [], []
    for op in ops:
        if isinstance(op, int):
            b = ctypes.create_string_buffer(op)
            msgs.append(Msg(addr, I2C_M_RD, op, ctypes.addressof(b)))
            reads.append(b)
        else:
            b = ctypes.create_string_buffer(bytes(op), len(op))
            msgs.append(Msg(addr, 0, len(op), ctypes.addressof(b)))
        keep.append(b)
    xfer(msgs)
    return [b.raw for b in reads]


def dev_hint(cmd: str, script: str) -> None:
    """One-line pointer printed when a script is run directly (it still works); silent under dev.py."""
    if os.environ.get("AWTO_VIA_DEV"):
        return
    print(f"note: ./dev.py {cmd} is the entry point (unit/EDID guard, bus rate, logs); running {script} directly",
          file=sys.stderr)


class Bus:
    """One open /dev/i2c-N. Every transfer is shown to the rtd_proto taps (decoded + raw logs)."""

    def __init__(self, bus: int):
        self.bus = bus
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- ioctl knobs ------------------------------------------------------------------------------------
    def set_retries(self, n: int) -> None:
        fcntl.ioctl(self.fd, I2C_RETRIES, n)          # adapter-wide, not per fd

    def set_timeout_ms(self, ms: int) -> None:
        fcntl.ioctl(self.fd, I2C_TIMEOUT, max(1, ms // 10))   # kernel unit is 10 ms

    # -- transfers ----------------------------------------------------------------------------------------
    def xfer(self, msgs) -> None:
        """One I2C_RDWR over Msg structs. Raises OSError (ENXIO = NAK, EAGAIN = GMBUS timeout, ETIMEDOUT)."""
        arr = (Msg * len(msgs))(*msgs)
        fcntl.ioctl(self.fd, I2C_RDWR, RdWr(ctypes.addressof(arr), len(msgs)))

    def ops(self, addr: int, ops) -> list[bytes]:
        """One I2C_RDWR to 7-bit addr: ops = bytes (write msg) | int n (read msg). Returns the read buffers."""
        return run_ops(self.xfer, addr, ops)

    def read(self, addr: int, reg: int, n: int) -> bytes:
        """Write [reg], repeated start, read n. Traced; OSError re-raised after the tap saw it."""
        try:
            data = self.ops(addr, [bytes([reg]), n])[0]
        except OSError as e:
            rtd_proto.trace(addr, "r", reg, None, n, str(e))
            raise
        rtd_proto.trace(addr, "r", reg, data, n)
        return data

    def write(self, addr: int, reg: int, data: bytes) -> None:
        """Write [reg] + data in one message. Traced; OSError re-raised after the tap saw it."""
        data = bytes(data)
        try:
            self.ops(addr, [bytes([reg]) + data])
        except OSError as e:
            rtd_proto.trace(addr, "w", reg, data, 0, str(e))
            raise
        rtd_proto.trace(addr, "w", reg, data)

    def raw_read(self, addr: int, n: int) -> bytes:
        fcntl.ioctl(self.fd, I2C_SLAVE, addr)
        return os.read(self.fd, n)

    def raw_write(self, addr: int, data: bytes) -> None:
        fcntl.ioctl(self.fd, I2C_SLAVE, addr)
        os.write(self.fd, data)

    def probe(self, addr: int) -> bool:
        """Does addr ACK a 1-byte read (no write)."""
        try:
            self.raw_read(addr, 1)
            return True
        except OSError:
            return False


# ---- helpers ------------------------------------------------------------------------------------------------
def list_buses(display_only: bool = False) -> list[int]:
    """Bus numbers present; display_only = i915 gmbus / NVIDIA / DP AUX adapters (where monitors hang)."""
    out = []
    for d in Path("/sys/class/i2c-dev").iterdir():
        if display_only and not any(k in (d / "name").read_text() for k in ("i915 gmbus", "NVIDIA", "AUX")):
            continue
        out.append(int(d.name.split("-")[1]))
    return sorted(out)


def adapter_name(bus: int) -> str:
    try:
        return Path(f"/sys/class/i2c-dev/i2c-{bus}/name").read_text().strip()
    except OSError:
        return ""


def parse_edid_serial(e: bytes) -> str | None:
    for i in range(54, 126, 18):
        if e[i:i + 3] == b"\0\0\0" and e[i + 3] == 0xFF:
            return e[i + 5:i + 18].split(b"\n")[0].decode("latin-1").strip()
    return None


def edid_serial(bus: int) -> str | None:
    """Text serial (descriptor 0xFF) of the EDID block 0 at 0x50, or None (no EDID / not readable / bus missing)."""
    try:
        b = Bus(bus)
    except OSError:
        return None
    try:
        b.raw_write(0x50, b"\x00")
        e = b.raw_read(0x50, 128)
        rtd_proto.trace(0x50, "w", 0, b"")
        rtd_proto.trace(0x50, "r", 0, e, 128)
    except OSError as ex:
        rtd_proto.trace(0x50, "r", 0, None, 128, str(ex))
        return None
    finally:
        b.close()
    return parse_edid_serial(e)


def require_unit(bus: int, serial: str, identity: str | None = None) -> str | None:
    """Unit guard: the EDID serial on `bus` must equal `serial` (a recabled unit once took a flash meant for another).
    EDID silent (MCU halted in ISP) is accepted only with identity='<how the caller proved the bus>'.
    Returns the serial read; SystemExit on mismatch."""
    s = edid_serial(bus)
    if s != serial and not (s is None and identity):
        raise SystemExit(f"bus {bus}: EDID serial {s!r} != {serial!r}; refusing"
                         + (" (EDID silent: pass --identity '<how proven>')" if s is None else ""))
    return s


NUDGE_ADDR = 0x08          # reserved I2C address: nothing answers, so the transfer NAKs
NUDGE_COUNT = 20           # one NAK did not take on 2026-11-06; 20 did (#26)


def gmbus_nudge(bus: int) -> None:
    """i915 falls back to bit-banging after a GMBUS timeout and returns to GMBUS only after a bit-banged
    transfer fails: NAK a few transfers to an empty address (#26: 25 s -> 2.5 s per sector)."""
    with Bus(bus) as b:
        for _ in range(NUDGE_COUNT):
            b.probe(NUDGE_ADDR)


# ---- bus rate (tools/gmbus_rate kernel module, #12) -----------------------------------------------------------
FAST_KHZ = 1000
RATE_PARAM = Path("/sys/module/gmbus_rate/parameters/reg0")
RATE_KHZ = {0: 100, 1: 50, 2: 100, 3: 1000}      # GMBUS0 bits 10:8; code 2 ("400 kHz") measured at 100 kHz on UHD 770
# gmbus_rate.py: make <= 60 s cold, sudo steps <= 10 s each; stall backstop 3x measured (load ~1 s warm).
T_LOAD, T_UNLOAD = 90, 20


def rate_khz() -> int:
    """Live DDC clock: 100 when the module is not loaded (i915 default)."""
    try:
        return RATE_KHZ.get((int(RATE_PARAM.read_text().strip(), 16) >> 8) & 7, 100)
    except (OSError, ValueError):
        return 100


def _gmbus(*args, timeout) -> int:
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "gmbus_rate.py"), *map(str, args)]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"gmbus_rate {' '.join(map(str, args))}: timeout {timeout}s", file=sys.stderr)
        return 124


def reset_rate() -> bool:
    """Back to the 100 kHz default (unload the module if a crashed session left it). True if it was loaded."""
    if not RATE_PARAM.exists():
        return False
    _gmbus("unload", timeout=T_UNLOAD)
    return True


@contextmanager
def fast_bus(bus: int, khz: int = FAST_KHZ):
    """1 MHz DDC clock around ISP flashing (slave 0x4A) only; unloaded in finally. Yields the rate in effect.
    Debug slave 0x35 NAKs intermittently at 1 MHz (#12), so diag/OSD/EDID/DDC stay at 100 kHz.
    Not an i915 GMBUS adapter (NVIDIA, DP AUX), or load refused (sudo): yields 100, flash proceeds slowly."""
    if "i915 gmbus" not in adapter_name(bus):
        yield 100
        return
    try:
        rc = _gmbus("load", khz, "--adapter", bus, timeout=T_LOAD)
        got = rate_khz()
        if rc or got != khz:
            print(f"fast_bus: load rc={rc} rate={got} kHz (wanted {khz}); continuing at {got} kHz", file=sys.stderr)
        yield got
    finally:
        _gmbus("unload", timeout=T_UNLOAD)


if __name__ == "__main__":
    dev_hint("<command>", "i2cbus.py")
    print(f"buses: {list_buses()}  display: {list_buses(True)}  rate: {rate_khz()} kHz")
