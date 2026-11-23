#!/usr/bin/env python3
"""Send the host time to a monitor over DDC/CI (awto-ddc#157) so its logs can be matched to host logs.

usage: host_time.py [--unit N] --once
       host_time.py [--unit N] --loop 60          one send per 60 s, aligned to the host clock (systemd/host-time.service)
- Carrier: MCCS table write (op 0xE7) to manufacturer VCP 0xE9, offset 0000, 7 data bytes: unix s BE x4, ms BE x2, UTC offset
  in 15 min units (signed). 51 8B E7 E9 00 00 t3 t2 t1 t0 mH mL ofs chk. No reply (MCCS table write). docs/ddcci.md.
- Read back: get VCP 0xE9 -> max = syncs since boot, cur = drift of this sync (host - fw tick, ms, int16).
- Debug link on (0x37 silent): the same 7 bytes go over 0x35 into g_stAwtoHt.aucPend, then test cmd 0x0E applies
  them (AwtoHtSync); a few ms older than over DDC/CI. Needs the running image's map (tmp/fw/<serial>-flash-state.json).
- Unit guard: the devices.json test unit only (default; another --unit is refused); bus = the one with the unit's EDID serial that ACKs DDC/CI 0x37
  (kvm.find_bus), EDID serial checked before every send. Debug link on (0x35 on the port) = no DDC/CI: logged, next round.
- No unit lock: a RAM write; the firmware's NVRAM flush gate sees it as DDC/CI (500 ms busy) once a minute.
Log: tmp/logs/host_time.log (one decoded line per send), tmp/logs/host_time.raw.log (bytes)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus
import kvm
from _log import log_line as _log_line

ROOT = kvm.REPO
LOG = ROOT / "tmp/logs/host_time.log"
RAW = ROOT / "tmp/logs/host_time.raw.log"
VCP = 0xE9
REPLY_WAIT_S = kvm.REPLY_WAIT_S  # MCCS: >= 40 ms between a request and its reply read
READ_TRIES = kvm.READ_TRIES      # null message = main loop busy (OSD draw): re-read; 3 x 40 ms, worst ~130 ms
WRITE_GAP_S = 0.050              # after the table write (no reply), before the get: DDC/CI 1.1 host gap after a
                                 # write-only command = 50 ms (a request sent at once got only null replies, #157);
                                 # a fixed wait, the get follows it


def log(s: str) -> None:
    _log_line(s, LOG)


def raw(kind: str, b: bytes) -> None:
    with RAW.open("a") as f:
        f.write(f"{dt.datetime.now().astimezone().isoformat(timespec='milliseconds')} {kind} {b.hex(' ')}\n")


def packet(t: float, ofs15: int) -> bytes:
    s = int(t)
    body = bytes([0x8B, 0xE7, VCP, 0, 0]) + s.to_bytes(4, "big") + min(999, round((t - s) * 1000)).to_bytes(2, "big") + \
        (ofs15 & 0xFF).to_bytes(1, "big")
    return body + bytes([kvm._chk(0x6E ^ 0x51, body)])


def get_e9(b: i2cbus.Bus) -> tuple[int, int]:
    """(syncs, drift ms) from get VCP 0xE9"""
    body = bytes([0x82, 0x01, VCP])
    b.write(kvm.DDCCI, 0x51, body + bytes([kvm._chk(0x6E ^ 0x51, body)]))
    for _ in range(READ_TRIES):
        time.sleep(REPLY_WAIT_S)     # spec reply wait, not a poll
        r = b.raw_read(kvm.DDCCI, 11)
        raw("r", r)
        if r[:2] == b"\x6e\x80" or r[:3] == body[:3]:
            continue
        if r[0] != 0x6E or r[1] != 0x88 or r[2] != 0x02 or kvm._chk(0x50, r[:10]) != r[10]:
            raise OSError(f"bad reply {r.hex(' ')}")
        if r[3] != 0:
            raise OSError("VCP 0xE9 unsupported: image without #157")
        return r[7], int.from_bytes(r[8:10], "big", signed=True)
    raise OSError(f"no reply after {READ_TRIES} reads")


def send(u: dict, bus: int) -> bool:
    i2cbus.require_unit(bus, u["serial"])
    with i2cbus.Bus(bus) as b:
        lt = time.localtime()
        ofs15 = lt.tm_gmtoff // 900
        t = time.time()
        p = packet(t, ofs15)
        b.write(kvm.DDCCI, 0x51, p)
        raw("w 51", p)
        time.sleep(WRITE_GAP_S)      # spec gap, not a poll
        syncs, drift = get_e9(b)
    when = dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(seconds=lt.tm_gmtoff))).isoformat(timespec="milliseconds")
    log(f"sent {when} (UTC offset {ofs15 * 15} min) -> unit {u['_n']} {u['serial']} bus {bus}: syncs since boot {syncs}, "
        f"drift {drift:+d} ms" + (" (first sync of this boot)" if syncs == 1 else ""))
    return True


DIAG_TEST_CMD = 0xF6D0 + 0x28     # isr_g_stAwtoDiag.ucTestCmd (RL6449_Project.h, fixed address)
TC_HOST_TIME = 0x0E               # AWTO_TC_HOST_TIME
HT_PEND = 16                      # offsetof(StAwtoHt, aucPend)
DBG_DEV8 = 0x6A                   # debug slave 0x35, 8-bit address


def dbg_bus(u: dict) -> int | None:
    """The unit's bus by EDID serial alone (DDC/CI is off while the debug link is on): kvm's cache, else a scan."""
    try:
        b = json.loads(kvm.BUS_CACHE.read_text()).get(u["serial"])
        if b is not None and i2cbus.edid_serial(b) == u["serial"]:
            return b
    except (OSError, ValueError):
        pass
    return next((b for b in i2cbus.list_buses(display_only=True) if i2cbus.edid_serial(b) == u["serial"]), None)


def send_dbg(u: dict, bus: int) -> bool:
    """Host time over the debug link: payload into aucPend, then the apply command; confirmed by the sync count."""
    import dbg_xdata as X
    import rtd_i2c_bridge as B
    from sync_log import sym
    st = json.loads((ROOT / f"tmp/fw/{u['serial']}-flash-state.json").read_text())
    ht = sym(ROOT / f"tmp/fw/{st['image']}.map", "g_stAwtoHt")
    i2cbus.require_unit(bus, u["serial"])
    io = B.Real(bus, allow_write=True, regread=True)
    try:
        before = (X.read_bytes(io, ht, 1) or b"\0")[0]
        lt = time.localtime()
        ofs15 = lt.tm_gmtoff // 900
        t = time.time()
        pay = packet(t, ofs15)[5:12]                         # unix s x4, ms x2, offset: the DDC/CI table data
        for ad, v in [(ht + HT_PEND + i, x) for i, x in enumerate(pay)] + [(DIAG_TEST_CMD, TC_HOST_TIME)]:
            if not (io.write(DBG_DEV8, 0x01, bytes([ad >> 8])) and io.write(DBG_DEV8, 0x03, bytes([v]))
                    and io.write(DBG_DEV8, 0x3B, bytes([ad & 0xFF]))):
                raise OSError(f"0x35 write 0x{ad:04X} failed")
        raw("w 35", pay + bytes([TC_HOST_TIME]))
        time.sleep(WRITE_GAP_S)      # one main-loop pass applies the command; then read the count
        after = (X.read_bytes(io, ht, 1) or b"\0")[0]
    finally:
        io.close()
    if after == before and before != 0xFF:
        raise OSError(f"0x35: sync count stayed {before} (image without AWTO_TC_HOST_TIME?)")
    when = dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(seconds=lt.tm_gmtoff))).isoformat(timespec="milliseconds")
    log(f"sent {when} (UTC offset {ofs15 * 15} min) over the debug link 0x35 -> unit {u['_n']} {u['serial']} bus {bus}: "
        f"syncs since boot {after}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", help="default: the devices.json test unit")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", type=float, metavar="SEC", help="send every SEC seconds (Dan: 60)")
    a = ap.parse_args()
    us = json.loads((ROOT / "scripts/devices.json").read_text())["units"]
    test = [n for n, d in us.items() if d.get("test")]
    a.unit = a.unit or (test[0] if len(test) == 1 else None)
    if a.unit not in test:
        raise SystemExit(f"unit {a.unit}: refused (host time goes to the devices.json test unit only: {test})")
    u = dict(us[a.unit], _n=a.unit)
    bus = None
    while True:
        try:
            bus = bus if bus is not None else kvm.find_bus(u)
            if bus is not None:
                try:
                    send(u, bus)
                except OSError as e:                 # 0x37 gone mid-session: the debug link took the port
                    log(f"unit {a.unit} bus {bus}: DDC/CI failed ({e}); trying the debug link 0x35")
                    send_dbg(u, bus)
            else:                                    # no DDC/CI: the debug link is on (or the cable is out)
                db = dbg_bus(u)
                if db is None:
                    raise OSError(f"no bus with EDID serial {u['serial']}")
                send_dbg(u, db)
            ok = True
        except (OSError, SystemExit) as e:
            log(f"unit {a.unit} {u['serial']} bus {bus}: not sent / not confirmed: {e} (debug link on? cable? image without #157?)")
            bus, ok = None, False                    # rescan next round: bus numbers change on re-enumeration
        if a.once:
            return 0 if ok else 1
        time.sleep(a.loop - (time.time() % a.loop))  # next multiple of SEC on the host clock: the send period itself


if __name__ == "__main__":
    sys.exit(main())
