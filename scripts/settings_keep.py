#!/usr/bin/env python3
"""Keep a unit's stored settings across a flash (awto-ddc#219): snapshot by name before it, restore after the first boot.

usage: settings_keep.py snapshot --bus B --serial S --map MAP [--table T] --out FILE
       settings_keep.py restore  --bus B --serial S --map MAP [--table T] --snapshot FILE
  snapshot: every stored row (flag nv, not ro) of the running image, read over the debug link: {name: raw}.
  restore:  waits for the new image to answer, then per snapshot row that still exists: a value that differs from the
            snapshot (a registry change reset it) is written back, saved once. Rows that are gone / out of the new range /
            new are logged, never guessed. --table = the image's own host table (tmp/fw/<tag>.settings_table.py).
  dev.py flash runs both around every flash; a failure here only warns, it never fails the flash.
Log: ./tmp/logs/settings_keep.log (one line per row that changed)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import isostamp
from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/settings_keep.log"
# a flashed unit answers the mailbox ~1.5 s after the reset (boot log: ACTIVE at ~1.5 s); 5 s = the repo's monitor-wait limit,
# expiry: nothing restored, the snapshot file stays for a manual `restore`
BOOT_WAIT_S = 5.0
POLL_S = 0.5            # one mailbox probe (debug link on + schema read) per poll; the link probe itself waits ~0.5 s


def say(s: str):
    _log_line(s, LOG)


def stored_rows(C):
    return [r for r in C.T.ROWS if "nv" in r["flags"] and "ro" not in r["flags"] and r["type"] != "action"]


def read_values(C, B, a):
    """{name: raw} of every stored row, over the debug link; None while the unit does not answer"""
    import dbg_link
    try:
        with dbg_link.linked(a.bus):
            io = B.Real(a.bus, allow_write=True, regread=True)
            try:
                box = C.Box(io, Path(a.map).read_text(errors="replace"))
                box.schema()
                return {r["name"]: box.get_row(r) for r in stored_rows(C)}
            finally:
                io.close()
    except SystemExit:
        return None


def plan(old: dict, now: dict, rows: dict):
    """(rows to write back [(row, old, now)], log notes, number kept): what a flash changed in the stored settings."""
    todo, notes, kept = [], [], 0
    for name, v in old.items():
        r = rows.get(name)
        if r is None:
            notes.append(f"{name}: no longer a stored row (was {v}); dropped")
        elif not r["min"] <= v <= r["max"]:
            notes.append(f"{name}: was {v}, outside the new range {r['min']}..{r['max']}; default {now[name]} stays")
        elif now[name] != v:
            todo.append((r, v, now[name]))
        else:
            kept += 1
    notes += [f"{n}: new row, default {now[n]}" for n in rows if n not in old]
    return todo, notes, kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["snapshot", "restore"])
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--table", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--snapshot", type=Path)
    a = ap.parse_args()
    if a.table and a.table.is_file():
        os.environ["AWTO_SETTINGS_TABLE"] = str(a.table.resolve())      # before settings_table is imported
    import i2cbus
    import rtd_i2c_bridge as B
    import settings_cli as C

    if a.cmd == "snapshot":
        i2cbus.require_unit(a.bus, a.serial)
        vals = read_values(C, B, a)
        if vals is None:
            say(f"snapshot {a.serial}: the unit does not answer over the debug link; nothing saved")
            return 1
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"serial": a.serial, "map": Path(a.map).name, "time": isostamp.now(), "values": vals}, indent=1))
        say(f"snapshot {a.serial}: {len(vals)} stored rows of {Path(a.map).name} -> {a.out}")
        return 0

    snap = json.loads(a.snapshot.read_text())
    if snap["serial"] != a.serial:
        say(f"restore refused: snapshot is of {snap['serial']}, not {a.serial}")
        return 2
    t0, now = time.monotonic(), None
    while now is None and time.monotonic() - t0 < BOOT_WAIT_S:
        now = read_values(C, B, a)
        if now is None:
            time.sleep(POLL_S)
    if now is None:
        say(f"restore {a.serial}: the unit did not answer within {BOOT_WAIT_S:.0f} s; snapshot {a.snapshot} kept")
        return 1
    i2cbus.require_unit(a.bus, a.serial)            # EDID serial: never write another unit's values
    todo, notes, kept = plan(snap["values"], now, {r["name"]: r for r in stored_rows(C)})
    for n in notes:
        say("  " + n)
    if not todo:
        say(f"restore {a.serial}: all {kept} kept rows unchanged by the flash")
        return 0
    import dbg_link
    bad = 0
    with dbg_link.linked(a.bus):
        io = B.Real(a.bus, allow_write=True, regread=True)
        try:
            box = C.Box(io, Path(a.map).read_text(errors="replace"))
            for r, old, cur in todo:
                got = box.set_row(r, old, True)
                say(f"  {r['name']}: flash reset it to {cur}, restored {old}" if got == old else
                    f"  {r['name']}: flash reset it to {cur}, restore to {old} REFUSED (firmware kept {got})")
                bad += got != old
            box.call(2, C.CMD, 2)                   # save: VCP 0xE3 = 2
        finally:
            io.close()
    say(f"restore {a.serial}: {len(todo) - bad} restored, {bad} refused, {kept} unchanged; saved")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
