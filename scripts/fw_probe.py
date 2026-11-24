#!/usr/bin/env python3
"""Read-only check: does the running firmware answer at the flash record's map? (docs/flash-record.md)

usage: fw_probe.py BUS --serial S [--map M] [--scan [--max N]]
  Layout probe over debug slave 0x35 (reads only): diag block magic 'AD' at _isp_g_stAwtoDiag and the settings
  mailbox magic 'V' at _vcp_box, both addresses from the map. Layout only: images of one layout all pass.
  default: the record's map; stale -> exit 3 + message naming the known maps that do answer; --scan: every known map.
  exit: 0 answers, 3 stale, 4 no debug answer.
Log: ./tmp/logs/fw_probe.log
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import flash_registry as R
import unit_lock
from _log import Logger

DIAG_SYM, BOX_SYM = "isr_g_stAwtoDiag", "vcp_box"
DIAG_MAGIC, BOX_MAGIC = b"AD", b"V"
ATTEMPTS = 2        # first read right after a reset can NAK (unit_health.check_diag): one retry


def sym(map_text: str, name: str) -> int | None:
    m = re.search(rf"([0-9A-F]{{8}})\s+_{name}\b", map_text)
    return int(m.group(1), 16) & 0xFFFF if m else None


class NoAnswer(Exception):
    pass


def layout_ok(io, map_text: str) -> bool:
    """True when both magics read back at the map's addresses; NoAnswer when the debug slave NAKs every try."""
    want = [(sym(map_text, DIAG_SYM), DIAG_MAGIC), (sym(map_text, BOX_SYM), BOX_MAGIC)]
    if any(a is None for a, _ in want):
        return False
    for a, m in want:
        got = b""
        for k in range(len(m)):
            for _ in range(ATTEMPTS):
                b = X.read_byte(io, a + k)
                if b is not None:
                    break
            else:
                raise NoAnswer(f"debug slave NAK reading 0x{a + k:04X}")
            got += b[:1]
        if got != m:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--max", type=int, default=R.SCAN_MAX)
    a = ap.parse_args()
    say = Logger(unit_lock.repo_root() / "tmp/logs/fw_probe.log", stamp_echo=False).say

    import i2cbus
    import rtd_i2c_bridge as B
    with unit_lock.held(a.serial, "fw_probe"):
        i2cbus.require_unit(a.bus, a.serial)
        io = B.Real(a.bus, allow_write=False, regread=True)
        try:
            probe = lambda m: layout_ok(io, Path(m).read_text(errors="replace"))
            if a.scan:
                for c in R.candidates(a.serial, a.max):
                    say(f"{'PASS' if probe(c['map']) else 'fail'} {c['tag']}")
                return 0
            if a.map:
                ok = probe(a.map)
                say(f"{'PASS' if ok else 'FAIL'} {a.map.name}")
                return 0 if ok else 3
            r = R.check(a.serial, probe)
            if r["ok"]:
                say(f"registry ok: unit {a.serial} answers at the map of {r['tag']} (layout check)")
                return 0
            say(R.stale_message(a.serial, r))
            return 3
        except NoAnswer as e:
            say(f"fw_probe: {e}; nothing done")
            return 4
        finally:
            io.close()


if __name__ == "__main__":
    sys.exit(main())
