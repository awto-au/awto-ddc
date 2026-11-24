#!/usr/bin/env python3
"""Blocking-wait log of the running image (awto-ddc#216): every ScalerTimerDelayXms / PollingFlagProc / WaitForEvent call.

usage: wait_log.py BUS --serial S --map MAP [--min-ms N] [--n 32 for a -D _AWTO_OSD_HWTEST image]
  Waits under 2 ms (and not expired) are only counted.
  Reads g_stAwtoWait (fw/log/sync.c, struct in RL6449_Project.h) over the debug link: the newest AWTO_WAIT_N waits, oldest first,
  with fw time at the start, ms waited, kind and argument (ms asked / register polled / event type). TIMEOUT = the poll or
  event expired. Callers per argument: scripts/sim_waits.py (offline, return addresses).
Log: ./tmp/logs/wait_log.log
"""
import argparse
import bisect
import re
import sys
from pathlib import Path

from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/wait_log.log"
N = 64                      # AWTO_WAIT_N
HDR = 3                     # ucTotal, ucQuick, ucSpMax
EV = 8                      # sizeof StAwtoWaitEv: usMs(2) ucKind(1) usArg(2) ucDur(1) usPc(2), big-endian image
KINDS = {0: "delay", 1: "poll", 2: "event"}
EVENTS = {0x01: "IVS", 0x02: "IEN_START", 0x04: "IEN_STOP", 0x08: "DVS", 0x10: "DEN_START", 0x20: "DEN_STOP"}  # EnumWaitEventType bits


def say(s: str) -> None:
    _log_line(s, LOG)


COMMON_END = 0x5000      # fw/rl6449_memory.toml common_end: below it an address is the same in every bank
BANK_SIZE = 0x10000


def chunk_table(map_path: Path):
    """sorted flat address -> name of every code chunk start in the map: globals (`_name`) and statics (area `s_CH_<name>`)"""
    rows = []
    for l in map_path.read_text(errors="replace").splitlines():
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(?:s_CH_|s_ST_|_)(\w+)", l)
        if m:
            rows.append((int(m.group(1), 16), m.group(2)))
    rows.sort()
    return [r[0] for r in rows], [r[1] for r in rows]


def caller_name(table, pc: int, bank: int) -> str:
    starts, names = table
    flat = pc if pc < COMMON_END else bank * BANK_SIZE + pc
    i = bisect.bisect_right(starts, flat) - 1
    return names[i] if i >= 0 else f"?{flat:x}"


def decode(raw: bytes, n_ring: int = N):
    """(total, quick, [(end_ms, kind, timeout, arg, dur, pc, bank)] oldest first)"""
    total, rows = raw[0], []
    n = min(total, n_ring)                          # total >= n_ring: ring full
    start = (total - n) % n_ring
    for k in range(n):
        o = HDR + ((start + k) % n_ring) * EV
        rows.append((raw[o] << 8 | raw[o + 1], raw[o + 2] & 0x03, bool(raw[o + 2] & 0x80), raw[o + 3] << 8 | raw[o + 4], raw[o + 5],
                     raw[o + 6] << 8 | raw[o + 7], (raw[o + 2] >> 3) & 0x0F))
    return total, raw[1], rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--min-ms", type=int, default=0)
    ap.add_argument("--n", type=int, default=N, help="AWTO_WAIT_N of the image (32 on a -D _AWTO_OSD_HWTEST image)")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dbg_link
    import dbg_xdata as X
    import i2cbus
    import rtd_i2c_bridge as B
    import sw_timeline as T

    i2cbus.require_unit(a.bus, a.serial)
    base, raw = T.sym(a.map, "g_stAwtoWait"), None
    with dbg_link.linked(a.bus, 2):
        io = B.Real(a.bus, allow_write=False, regread=True)
        for _ in range(3):
            raw = X.read_blocks(io, base, HDR + EV * a.n)
            if raw is not None:
                break
        io.close()
    if raw is None:
        say("wait log read failed")
        return 1
    total, quick, rows = decode(raw, a.n)
    say(f"stack: highest SP inside a wait 0x{raw[2]:02X} (guard 0xF0, {0xF0 - raw[2]} B below it; includes the logger's own frame)")
    say(f"{a.map.name}: {total} waits >= 2 ms or expired + {quick} that answered under 2 ms (quick wraps at 256), last {len(rows)} shown")
    table = chunk_table(a.map)
    for end, kind, tmo, arg, dur, pc, bank in rows:
        if dur < a.min_ms:
            continue
        what = {0: f"{arg} ms asked", 1: f"reg 0x{arg:04X}", 2: f"event {EVENTS.get(arg, hex(arg))}"}[kind] if kind in KINDS else f"kind {kind}"
        say(f"  {(end - dur) & 0xFFFF:6d} ms  waited {dur:3d} ms  {KINDS.get(kind, '?'):5s} {what}" + ("  TIMEOUT" if tmo else "") + f"  <- {caller_name(table, pc, bank)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
