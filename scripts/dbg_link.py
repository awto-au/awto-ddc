#!/usr/bin/env python3
"""#79 runtime DDC swap, host side: move the debug slave 0x35 onto the unit's DDC (DDC/CI owns it by default) and back.

usage: dbg_link.py on|off|state|expiry BUS [--minutes N]
- state: does 0x35 answer (diag version byte) / does 0x37 ACK.
- on: 0x35 answers already = nothing sent ("already"). Else DDC/CI setvcp E3 = A5 NN (NN minutes, FF = until told back)
  to 0x37, then 0x35 is re-probed after each MCCS wait. Exit 0 = linked ("swapped" / "already"), 1 = no link.
- off: test cmd 0x3B over 0x35 (back to DDC/CI); then 0x37 must ACK.
- expiry: test of the firmware timeout: 0x37 back within 1.25 x --minutes (checked once per second).
- Firmware: fw/diag/dbgport.c + fw/ddcci/ddcci.c (wb-p14swap); sim check: scripts/swap_sim.py.
- dev.py wraps every debug-slave command in on/off (`linked`), so it does not matter which side owns the DDC.
Log: ./tmp/logs/dbg_link.log
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus  # noqa: E402

LOG = i2cbus.ROOT / "tmp/logs/dbg_link.log"
DBG, DDCCI = 0x35, 0x37
VCP_LINK, MAGIC = 0xE3, 0xA5            # RL6449_Project.h AWTO_DBG_LINK_VCP / _MAGIC
TESTCMD = 0xF6F8                        # isr_g_stAwtoDiag (0xF6D0) + 0x28
CMD_BACK = 0x3B
DIAG_MAGIC = 0xF6D0                     # isr_g_stAwtoDiag.ucMagic[2] = 'AD' (docs/diag-block.md)
MCCS_WAIT_S = 0.050                     # MCCS 2.2: host waits 50 ms after a set before the next transaction
# swap = one main-loop pass (~1 ms); worst case the loop is blocked by the input-info pop-up draw, 375 ms (#60 phase
# table). 1.25 x 375 ms / 50 ms -> 10 probes. Expiry: "no link" logged with the elapsed time, exit 1.
PROBES = 10
DEFAULT_MIN = 10                        # firmware falls back to DDC/CI by itself if `off` never comes


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def dbg_ok(bus: int) -> bool:
    """0x35 answers with the diag magic 'AD' (byte path: stage hi, 0x3A lo, read). An ACK alone is not enough: a parked
    engine on a reserved channel once ACKed 0x35 on DDC2 and returned 0xCD (#79)."""
    try:
        with i2cbus.Bus(bus) as b:
            got = b""
            for a in (DIAG_MAGIC, DIAG_MAGIC + 1):
                b.write(DBG, 0x01, bytes([a >> 8]))
                b.write(DBG, 0x3A, bytes([a & 0xFF]))
                got += b.read(DBG, 0x08, 1)
            return got == b"AD"
    except OSError:
        return False


def ddcci_ok(bus: int) -> bool:
    try:
        with i2cbus.Bus(bus) as b:
            b.raw_read(DDCCI, 1)
        return True
    except OSError:
        return False


def _setvcp(bus: int, code: int, hi: int, lo: int) -> None:
    body = bytes([0x84, 0x03, code, hi, lo])
    chk = 0x6E ^ 0x51
    for x in body:
        chk ^= x
    with i2cbus.Bus(bus) as b:
        b.write(DDCCI, 0x51, body + bytes([chk]))


def on(bus: int, minutes: int = DEFAULT_MIN) -> str:
    """"already" | "swapped"; raises SystemExit when 0x35 does not come up."""
    if dbg_ok(bus):
        return "already"
    t0 = time.monotonic()
    try:
        _setvcp(bus, VCP_LINK, MAGIC, minutes & 0xFF)
    except OSError as e:
        raise SystemExit(f"dbg_link on bus {bus}: 0x35 NAK and DDC/CI 0x37 NAK too ({e}): firmware without #79, "
                         f"or the unit is not on this bus")
    for k in range(PROBES):
        time.sleep(MCCS_WAIT_S)         # MCCS reply wait, not a poll interval
        if dbg_ok(bus):
            log(f"bus {bus}: debug link ON ({minutes if minutes != 0xFF else 'until off'} min), "
                f"0x35 up after {(time.monotonic() - t0) * 1000:.0f} ms ({k + 1} probes)")
            return "swapped"
    raise SystemExit(f"dbg_link on bus {bus}: setvcp E3 sent, 0x35 still NAK after {PROBES} probes / "
                     f"{(time.monotonic() - t0) * 1000:.0f} ms")


def off(bus: int) -> bool:
    t0 = time.monotonic()
    try:
        with i2cbus.Bus(bus) as b:
            b.write(DBG, 0x01, bytes([TESTCMD >> 8]))
            b.write(DBG, 0x03, bytes([CMD_BACK]))
            b.write(DBG, 0x3B, bytes([TESTCMD & 0xFF]))
    except OSError as e:
        log(f"bus {bus}: debug link OFF failed: 0x35 NAK ({e}); firmware times out to DDC/CI by itself")
        return False
    for k in range(PROBES):
        time.sleep(MCCS_WAIT_S)
        if ddcci_ok(bus):
            log(f"bus {bus}: debug link OFF, DDC/CI 0x37 back after {(time.monotonic() - t0) * 1000:.0f} ms")
            return True
    log(f"bus {bus}: debug link OFF sent, 0x37 still NAK after {(time.monotonic() - t0) * 1000:.0f} ms")
    return False


@contextlib.contextmanager
def linked(bus: int, minutes: int = DEFAULT_MIN):
    """0x35 on `bus` for the block; swapped back afterwards only if this call swapped it."""
    how = on(bus, minutes)
    try:
        yield how
    finally:
        if how == "swapped":
            off(bus)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["on", "off", "state", "expiry"])
    ap.add_argument("bus", type=int)
    ap.add_argument("--minutes", type=int, default=DEFAULT_MIN, help="1..254, 255 = until off")
    a = ap.parse_args()
    if a.action == "state":
        log(f"bus {a.bus}: 0x35 {'answers' if dbg_ok(a.bus) else 'NAK'}, 0x37 {'ACK' if ddcci_ok(a.bus) else 'NAK'}")
        return 0
    if a.action == "expiry":
        t0, limit = time.monotonic(), a.minutes * 60 * 1.25
        while time.monotonic() - t0 < limit:
            time.sleep(1.0)             # 1 s resolution: the firmware counts whole seconds
            if ddcci_ok(a.bus):
                log(f"bus {a.bus}: DDC/CI back by itself after {time.monotonic() - t0:.0f} s (limit {limit:.0f} s)")
                return 0
        log(f"bus {a.bus}: debug link did NOT expire within {limit:.0f} s")
        return 1
    if a.action == "on":
        log(f"bus {a.bus}: {on(a.bus, a.minutes)}")
        return 0
    return 0 if off(a.bus) else 1


if __name__ == "__main__":
    sys.exit(main())
