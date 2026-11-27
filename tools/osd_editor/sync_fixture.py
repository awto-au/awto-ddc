"""Test input for the GUI's sync table (monitor.sync_rows): `dev.py synclog` text built with the current scripts/sync_log.py,
the same calls as its main(). No unit, no Qt. LOG_TIMES = the log-times branch's row_lines form (docs/sync-log-design.md, #354)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import sync_log as S  # noqa: E402

BOOT, BEGIN = S.BOOT_EV, S.BEGIN_EV
# (id, arg, ms16, value, text): a boot, steps of 40 / 350 / 30 ms, a switch episode (BEGIN not power-on = a start row)
EVENTS = [(BOOT, 0, 5, 0, "boot: power on"), (0x01, 0, 45, 0, "panel on"), (0x02, 0, 395, 0, "input lock D2"),
          (0x03, 0, 425, 0, "backlight on"), (BEGIN, 2, 9000, 0, "switch to D1"), (0x04, 0, 9120, 0, "sync DONE")]
HT = {"syncs": 1, "ofs": 40, "frac": 0, "epoch": 1_795_000_000, "fw": 0, "drift": 0, "up_hi": 0}   # one host sync at fw 0, +10:00


def ring_text(synced: bool = True) -> str:
    """`dev.py synclog` (ring read) as sync_log.main prints it: delta column, then host time when synced, then "nnnnn:" + text"""
    evs = [e[:4] for e in EVENTS]
    t0 = evs[0][2]
    lines = [f"{(e[2] - t0) & 0xFFFF:5d}:{e[4]}" for e in EVENTS]
    h = {"events": evs}
    ht, t2 = (HT, 9200) if synced else (None, None)
    ds = S.deltas(evs, S.unwrap(evs, S.fw_now(ht, t2) if ht else None))
    lines = S.stamp(h, lines, ht, t2)
    out = [S.ht_line(ht, t2), f"sync episode: switch, {len(lines)} lines"]
    out += ["  " + dl for dl in S.with_delta(lines, ds)]
    return "\n".join(out) + "\n"


def dram_text() -> str:
    """`dev.py synclog --dram` as sync_log.main prints it: `--- boot N` separators, `  <abs> <delta>:<text>`"""
    ents = [{"id": e[0], "arg": e[1], "ms": e[2], "val": e[3], "text": e[4], "boot": 7 if k < 4 else 8, "abs": 100 + k}
            for k, e in enumerate(EVENTS)]
    out, boot = ["dram log: gen 1 boot 8 next index 106 (wraps 0), 6 entries, 6 DDR bursts in 0.2 s"], None
    for e, dl in zip(ents, S.with_delta([e["text"] for e in ents], S.dram_deltas(ents))):
        if e["boot"] != boot:
            boot = e["boot"]
            out.append(f"--- boot {boot}")
        out.append(f"  {e['abs']:6d} {dl}")
    return "\n".join(out) + "\n"


# log-times row_lines form (not on main yet): real 13 cells, space, delta 7 cells, ':', text, raw times; a wrap row before a 16-bit gap
LOG_TIMES = """  u00:00:00.005 +  5 ms:-- boot: power on --  [fw 5 ms, ring 5]
   14:58:59.640 + 40 ms:panel on  [fw 45 ms, ring 45]
   14:59:00.000 +350 ms:input lock D2  [fw 395 ms, ring 395]
                       :-- relative time reset: counter wrap --
                       :monitor: IOSC 2001 | 300/s gap 12.6ms  [fw ? ms, ring 120]
   15:20:11.500 +  0 ms:-- switch to D1 --  [fw 1272000 ms, ring 26304]
   15:20:11.620 +120 ms:sync DONE  [fw 1272120 ms, ring 26424]
"""
