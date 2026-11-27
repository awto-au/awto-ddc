#!/usr/bin/env python3
"""#79 runtime DDC swap, host side: move the debug slave 0x35 onto the unit's DDC (DDC/CI owns it by default) and back.

usage: dbg_link.py on|off|state|expiry BUS [--minutes N]
- state: does 0x35 answer (diag version byte) / does 0x37 ACK.
- on: 0x35 answers already = nothing sent ("already"). Else DDC/CI setvcp E3 = A5 NN (NN minutes, FF = until told back)
  to 0x37, then 0x35 is re-probed after each MCCS wait. Exit 0 = linked ("swapped" / "already"), 1 = no link.
- off: test cmd 0x3B over 0x35 (back to DDC/CI); confirmed = 0x35 NAK + 0x37 ACK, else re-sent (OFF_ATTEMPTS); exit 1 = not confirmed.
- expiry: test of the firmware timeout: 0x37 back within 1.25 x --minutes (checked once per second).
- Firmware: fw/diag/dbgport.c + fw/ddcci/ddcci.c (wb-p14swap); sim check: scripts/swap_sim.py.
- dev.py wraps every debug-slave command in on/off (`linked`), so it does not matter which side owns the DDC.
- `linked` closes a console / pop-up the block opened (ucHold bit1: clear before, set after; test cmd 0x27, verified) unless
  keep_console (osd, gpio, menu). `dev.py health --no-osd` skips the info card + debug pop-up round-trip.
Log: ./tmp/logs/dbg_link.log
"""
from __future__ import annotations

import argparse
import contextlib
import math
import sys
import time
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddcutil_run
import i2cbus

LOG = i2cbus.ROOT / "tmp/logs/dbg_link.log"
DBG, DDCCI = 0x35, 0x37
VCP_LINK, MAGIC = 0xE3, 0xA5            # RL6449_Project.h AWTO_DBG_LINK_VCP / _MAGIC
TESTCMD = 0xF6F8                        # isr_g_stAwtoDiag (0xF6D0) + 0x28
CMD_BACK = 0x3B
CMD_CLEAR = 0x27                        # fw/test/testcmd.c: closes the console, clears ucHold
HOLD = 0xF6D0 + 0x2F                    # isr_g_stAwtoDiag.ucHold (docs/diag-block.md)
HOLD_POPUP = 0x02                       # AWTO_HOLD_POPUP: debug pop-up / console held
# Close wait: a console draw stalls the debug slave ~0.4 s (unit_health.CONSUME_WAIT_S 0.5 = 1.25 x worst seen).
CLOSE_POLL_S, CLOSE_LIMIT_S = 0.05, 0.5
DIAG_MAGIC = 0xF6D0                     # isr_g_stAwtoDiag.ucMagic[2] = 'AD' (docs/diag-block.md)
MCCS_WAIT_S = 0.050                     # MCCS 2.2: host waits 50 ms after a set before the next transaction
# swap = one main-loop pass (~1 ms); worst case the loop is blocked by the input-info pop-up draw, 375 ms (#60 phase
# table). 1.25 x 375 ms / 50 ms -> 10 probes. Expiry: "no link" logged with the elapsed time, exit 1.
PROBES = 10
DEFAULT_MIN = 10                        # firmware falls back to DDC/CI by itself if `off` never comes
# off (#351): the test byte runs once per main-loop pass and swaps in that pass (AwtoDiagTestCmd -> AwtoDbgLinkSet);
# a pass > 585.9 ms is a watchdog reset (docs/main-loop-pacing.md §2): window 1.25 x 585.9 ms. Expiry: re-send.
OFF_WINDOW_S = 1.25 * 0.5859
# re-sends cover a lost staged write; budget = the next DDC/CI caller's own retry budget (ddcutil_run: 4 x 0.5 s = 2 s)
OFF_ATTEMPTS = math.ceil(ddcutil_run.DDC_TRIES * ddcutil_run.DDC_RETRY_S / OFF_WINDOW_S)


def log(s: str) -> None:
    _log_line(s, LOG)


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


def _test_byte(bus: int) -> int | None:
    """isr_g_stAwtoDiag.ucTestCmd over 0x35: 0 = consumed (or never landed), CMD_BACK = not run yet; None = 0x35 NAK"""
    try:
        with i2cbus.Bus(bus) as b:
            return _rd(b, TESTCMD)
    except OSError:
        return None


def off(bus: int) -> bool:
    """test cmd 0x3B, confirmed by 0x35 NAK + 0x37 ACK; re-sent up to OFF_ATTEMPTS times (#351). One decoded line per attempt."""
    t0 = time.monotonic()
    for k in range(1, OFF_ATTEMPTS + 1):
        ta = time.monotonic()
        try:
            with i2cbus.Bus(bus) as b:
                _wr(b, TESTCMD, CMD_BACK)
            sent = "sent"
        except OSError as e:
            sent = f"not sent (0x35 NAK: {e})"
        while True:
            if ddcci_ok(bus) and not dbg_ok(bus):
                log(f"bus {bus}: debug link OFF attempt {k}/{OFF_ATTEMPTS}: {sent}; confirmed 0x35 NAK + 0x37 ACK after "
                    f"{(time.monotonic() - ta) * 1000:.0f} ms ({(time.monotonic() - t0) * 1000:.0f} ms in all)")
                return True
            if time.monotonic() - ta >= OFF_WINDOW_S:
                break
            time.sleep(MCCS_WAIT_S)     # MCCS 2.2 wait between transactions, not a poll interval
        tb = _test_byte(bus)
        what = ("0x35 NAK" if tb is None else f"0x35 answers, test byte 0x{tb:02X} = "
                + ("not run (main loop blocked)" if tb == CMD_BACK else "consumed or lost (no swap)" if tb == 0 else "another command pending"))
        log(f"bus {bus}: debug link OFF attempt {k}/{OFF_ATTEMPTS}: {sent}; not confirmed in {(time.monotonic() - ta) * 1000:.0f} ms "
            f"(window {OFF_WINDOW_S * 1000:.0f} ms): {what}, 0x37 {'ACK' if ddcci_ok(bus) else 'NAK'}")
    log(f"bus {bus}: debug link OFF FAILED after {OFF_ATTEMPTS} attempts, {(time.monotonic() - t0) * 1000:.0f} ms "
        f"(limit {OFF_ATTEMPTS * OFF_WINDOW_S * 1000:.0f} ms); DDC/CI stays off until the firmware link timer")
    return False


def _rd(b, addr: int) -> int:
    b.write(DBG, 0x01, bytes([addr >> 8]))
    b.write(DBG, 0x3A, bytes([addr & 0xFF]))
    return b.read(DBG, 0x08, 1)[0]


def _wr(b, addr: int, v: int) -> None:
    b.write(DBG, 0x01, bytes([addr >> 8]))
    b.write(DBG, 0x03, bytes([v]))
    b.write(DBG, 0x3B, bytes([addr & 0xFF]))


def hold(bus: int) -> int | None:
    try:
        with i2cbus.Bus(bus) as b:
            return _rd(b, HOLD)
    except OSError:
        return None


def close_console(bus: int) -> bool:
    """Test cmd 0x27, then verify ucHold bit1 reads 0. The firmware takes the command in its main loop: wait for the
    previous test byte to be consumed first (it would be overwritten)."""
    t0 = time.monotonic()
    try:
        with i2cbus.Bus(bus) as b:
            while _rd(b, TESTCMD) != 0 and time.monotonic() - t0 < CLOSE_LIMIT_S:
                time.sleep(CLOSE_POLL_S)        # previous test byte still being consumed (pop-up draw)
            _wr(b, TESTCMD, CMD_CLEAR)
            while time.monotonic() - t0 < 2 * CLOSE_LIMIT_S:
                time.sleep(CLOSE_POLL_S)        # clear + OsdDispDisableOsd run in the main loop
                if _rd(b, TESTCMD) == 0 and (_rd(b, HOLD) & HOLD_POPUP) == 0:
                    log(f"bus {bus}: console closed (0x27) after {(time.monotonic() - t0) * 1000:.0f} ms, ucHold bit1 = 0")
                    return True
    except OSError as e:
        log(f"bus {bus}: console close failed: {e}")
        return False
    log(f"bus {bus}: console close: ucHold bit1 still set after {(time.monotonic() - t0) * 1000:.0f} ms "
        f"(limit {2 * CLOSE_LIMIT_S * 1000:.0f} ms)")
    return False


@contextlib.contextmanager
def linked(bus: int, minutes: int = DEFAULT_MIN, keep_console: bool = False):
    """0x35 on `bus` for the block; swapped back afterwards only if this call swapped it.
    A console / pop-up this block opened (ucHold bit1 clear before, set after) is closed again unless keep_console:
    a debug session must leave the picture as it found it (visual tests run under it)."""
    how = on(bus, minutes)
    before = hold(bus)
    failed = True
    try:
        yield how
        failed = False
    finally:
        if not keep_console and before is not None and (before & HOLD_POPUP) == 0:
            now = hold(bus)
            if now is not None and (now & HOLD_POPUP) != 0:
                close_console(bus)
        if how == "swapped" and not off(bus) and not failed:     # #351: fail loudly; the block's own error wins when it raised
            raise SystemExit(f"dbg_link bus {bus}: debug link OFF not confirmed (0x35 still answers or 0x37 NAK); see {LOG}")


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
