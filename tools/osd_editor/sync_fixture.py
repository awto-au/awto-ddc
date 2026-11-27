"""Test input for the GUI's sync table and log view: `dev.py synclog` text built with the current scripts/sync_log.py /
dram_log.py (ring_rows, con_lines: the same calls as sync_log.main). No unit, no Qt. Format: docs/sync-log-design.md "Host decoded row"."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dram_log as D  # noqa: E402
import sync_log as S  # noqa: E402

STAMP = "2026-11-27T15:20:33+11:00   "     # _log.py stamp + the two spaces sync_log.main puts before a row
BOOT, BEGIN = S.BOOT_EV, S.BEGIN_EV
# (id, arg, ms32, value, text): a boot, steps of 40 / 350 / 30 ms, a 285 s gap (over the 16-bit 65.5 s), a switch episode (a start row)
EVENTS = [(BOOT, 0, 5, 0, "boot: power on"), (0x01, 0, 45, 0, "panel on"), (0x02, 0, 395, 0, "input lock D2"),
          (0x03, 0, 425, 0, "backlight on"), (0x04, 0, 285_425, 0, "heartbeat"), (BEGIN, 2, 290_000, 0, "switch to D1"),
          (0x05, 0, 290_120, 0, "sync DONE")]
HT = {"syncs": 1, "ofs": 44, "frac": 0, "epoch": 1_795_753_094, "fw": 0, "drift": 0, "up_hi": 4}   # one host sync at fw 0, +11:00


def ring_text(synced: bool = True, ms32: bool = True) -> str:
    """`dev.py synclog` (ring read) as sync_log.main prints it. ms32=False: a version 3 ring (16-bit times: the 285 s gap is a wrap row)"""
    evs = [(e[0], e[1], e[2] & 0xFFFF, e[3]) for e in EVENTS]
    lines = [f"{(e[2] - EVENTS[0][2]) & 0xFFFF:5d}:{e[4]}" for e in EVENTS]
    h = {"events": evs, "ms32": [e[2] for e in EVENTS] if ms32 else None, "boot_base": None}
    ht, t2 = (HT, 290_200 & 0xFFFF) if synced else (None, None)
    out = [S.ht_line(ht, t2), f"sync episode: switch, {len(lines)} lines"]
    out += [STAMP + ln for ln, _ in S.ring_rows(h, lines, ht, t2)]
    return "\n".join(out) + "\n"


def dram_entries(boots=(7, 8)) -> list[dict]:
    """dram_log.snapshot entries (abs, boot, 32-bit ms, text as dram_log.decode) of EVENTS: the first 5 in boot 7, the rest in boot 8"""
    out = []
    for k, e in enumerate(EVENTS):
        out.append({"abs": 100 + k, "boot": boots[0] if k < 5 else boots[1], "ms": e[2], "id": e[0], "arg": e[1], "val": e[3],
                    "text": f"{e[2] / 1000:9.3f}s:{e[4]}", "poll_wall": None})
    return out


def dram_text() -> str:
    """`dev.py synclog --dram` as sync_log.main prints it: dram_log.con_lines (`--- boot N`, `  <abs> <row>`)"""
    ents = dram_entries()
    out = ["dram log: gen 1 boot 8 next index 107 (wraps 0), 7 entries, 7 DDR bursts in 0.2 s"]
    out += [STAMP + ln for ln in D.con_lines([], ents, 8)]
    return "\n".join(out) + "\n"
