#!/usr/bin/env python3
"""#273 in fw_sim: host notes (text slot + test cmd AWTO_TC_HOST_NOTE) -> ring entry, console row, host decoder line.

usage: AWTO_SIM_CORE=fast host_note_sim.py BIN [--map MAP]
- Boot, console open; host_note.note_io-equivalent writes (slot bytes + test cmd) through the sim RAM.
- Checks: one ring entry per note (arg = length, value = sequence); the console log row shows the text; sync_log prints the
  same text; two identical notes = two lines; a slot taken by a newer note prints "text overwritten" (host and screen);
  a note longer than the slot is cut with '>' by host_note.prepare.
Exit 1 on a failed check. Log: tmp/logs/host_note_sim.log
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_note as HN
import host_time_sim as H
import sync_log as SL

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/host_note_sim.log"
NOTE_S = 1.0        # test cmd -> ring entry + console row: one main pass + one row draw (~0.3 s sim) x3


def say(s: str) -> None:
    _log_line(s, LOG)


H.say = say


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/console_pages", help="text + PNG of the console with the notes (sim render)")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    if " _g_aucAwtoNote " not in mapp.read_text(errors="replace"):
        say(f"SKIP {a.bin.name}: no _g_aucAwtoNote (image without #273)")
        return 0
    say(f"=== host_note_sim {a.bin.name} ===")
    d = SL.note_defs()
    s = H.Sim(a.bin, mapp)
    s.boot()
    s.bus.wait(H.CON_S)
    slot, cnt = s.m.addr("g_aucAwtoNote"), s.m.addr("g_usAwtoNoteN")
    cmd = s.m.addr("isr_g_stAwtoDiag") + HN.TESTCMD_OFF

    def seq() -> int:
        return int.from_bytes(bytes(s.m.rd(cnt, 2)), "big")

    def put(text: str, send: bool = True) -> tuple[int, bool]:
        body, cut = HN.prepare(text, d["CHARS"])
        n = (seq() + 1) & 0xFFFF
        for off, v in HN.slot_bytes(n, body, d):
            s.m.wr(slot + off, bytes([v]))
        if send:
            s.m.wr(cmd, bytes([HN.TC_HOST_NOTE]))
            s.bus.wait(NOTE_S)
        return n, cut

    def lines() -> list[str]:
        raw = bytes(SL.read_ring(s.m.rd, s.a_sync))
        note = bytes(s.m.rd(slot, d["SIZE"]))
        return SL.decode(raw, s.rows, whole=True, note=note)[1]

    n0 = seq()
    n1, _ = put("step 1: ddr fill 0x000000-0x3FFFFF")
    s.check(seq() == n1 == n0 + 1, "counter advanced by the test cmd", f"{n0} -> {seq()}")
    s.check(any(x.endswith("step 1: ddr fill 0x000000-0x3FFFFF") for x in lines()), "sync_log prints the note text", next((x for x in lines() if "step 1" in x), ""))
    s.check(any("step 1: ddr fill 0x000000-0x3FFFFF" in r for r in s.text()), "console log row shows the note")
    put("same")
    put("same")
    ls = lines()
    s.check(ls[-1].endswith("same") and ls[-2].endswith("text overwritten"), "two identical notes = two lines; the older text is gone from the one slot",
            f"{ls[-2][-40:]!r} / {ls[-1][-40:]!r}")
    s.check(sum(r.rstrip().endswith("same") for r in s.text()) == 2, "console: both identical notes shown as separate rows")
    long = "L" * (d["CHARS"] + 40)
    _n, cut = put(long)
    marked = "L" * (d["CHARS"] - 1) + ">"
    s.check(cut and lines()[-1].endswith(marked), "long note cut at the slot size with '>'")
    s.check(any(marked in r for r in s.text()), "console shows the cut note with its marker")
    raw = bytes(SL.read_ring(s.m.rd, s.a_sync))
    ev = [int.from_bytes(raw[SL.HDR + k * SL.EV + 4:SL.HDR + k * SL.EV + 8], "big") for k in range(raw[12]) if raw[SL.HDR + k * SL.EV] == SL.NOTE_EV]
    s.check(len(ev) == 4 and len(set(ev)) == 4, "one ring entry (id 0xEE) per note, sequences distinct", str(sorted(ev)))
    body, _ = HN.prepare("newer text", d["CHARS"])
    for off, v in HN.slot_bytes((seq() + 5) & 0xFFFF, body, d):
        s.m.wr(slot + off, bytes([v]))                     # slot taken by a note that has no entry yet
    s.check(lines()[-1].endswith("text overwritten"), "host decoder: a slot with a newer tag says text overwritten", lines()[-1][-40:])
    s.dump(a.out, "host_note")
    say("FAILED" if s.fails else "all checks passed")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
