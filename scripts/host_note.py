#!/usr/bin/env python3
"""Add a free-text line to a monitor's diag log (awto-ddc#273): the unit shows what a hardware test is doing.

Internal module behind `./dev.py note` (the only entry point); library helpers for test drivers:
  host_note(unit, text, open_console=False)   one call per test step (runs `./dev.py note`, debug link on for the call)
  note_io(io, map_path, text)                 same over an already open debug-slave io (drivers that hold the link)
  note_step(io, map_path, text)               note_io that never raises: skipped + logged (image without the feature)
Transport: text slot g_aucAwtoNote (fw/log/hostnote.c) written over debug slave 0x35, then test cmd AWTO_TC_HOST_NOTE; the
  firmware logs ONE sync ring entry (arg = length, value = sequence). Console and sync_log.py print the slot text; a note
  whose slot was taken by a newer one prints "text overwritten". No main-loop polling: the test cmd is already polled.
Text: ASCII, control chars -> '?', cut at AWTO_NOTE_CHARS with a '>' last char and a "truncated" log line.
Safe on an image without the feature: the map has no g_aucAwtoNote -> clear message, nothing written; a cmd the firmware does
  not know leaves the counter unchanged -> "not logged" after NOTE_WAIT_S.
Log: tmp/logs/host_note.log
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_log as S

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOG = ROOT / "tmp/logs/host_note.log"
DEV8 = 0x6A                      # debug slave 0x35, 8-bit address
TESTCMD_OFF = 0x28               # isr_g_stAwtoDiag.ucTestCmd
TC_HOST_NOTE = 0x35              # AWTO_TC_HOST_NOTE (RL6449_Project.h)
TC_CONSOLE = 0x20                # debug pop-up = the diagnostic console (testcmd.c)
MARK = ">"                       # last char of a truncated note
NOTE_WAIT_S = 0.32               # main pass that takes the cmd: worst 255 ms (docs/monitoring.md) x 1.25; expiry = "not logged"
NOTE_POLL_S = 0.02               # counter re-read period (an I2C read of 2 bytes takes a few ms)


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def prepare(text: str, chars: int) -> tuple[bytes, bool]:
    """(text bytes, truncated): ASCII only, control / non-ASCII -> '?', cut at `chars` with MARK as the last char"""
    b = bytes(c if 0x20 <= c <= 0x7E else ord("?") for c in text.encode("utf-8", "replace"))
    if len(b) <= chars:
        return b, False
    return b[:chars - 1] + MARK.encode(), True


def slot_bytes(seq: int, text: bytes, d: dict) -> list[tuple[int, int]]:
    """(offset in the slot, byte) writes: tag (sequence, BE), length, text; unused text bytes are not written"""
    out = [(d["TAG"], (seq >> 8) & 0xFF), (d["TAG"] + 1, seq & 0xFF), (d["LEN"], len(text))]
    return out + [(d["TXT"] + i, c) for i, c in enumerate(text)]


def _sym(mp: Path, name: str) -> int | None:
    m = re.search(rf"^\S*\s+([0-9A-F]{{8}})\s+_{name}\b", mp.read_text(errors="replace"), re.MULTILINE)
    return None if m is None else int(m.group(1), 16) & 0xFFFF


def _wr(io, ad: int, v: int) -> None:
    if not (io.write(DEV8, 0x01, bytes([ad >> 8])) and io.write(DEV8, 0x03, bytes([v])) and io.write(DEV8, 0x3B, bytes([ad & 0xFF]))):
        raise OSError(f"0x35 write 0x{ad:04X} not acknowledged")


def note_io(io, map_path: Path, text: str, open_console: bool = False) -> int:
    """log `text` on the unit; returns the note sequence. SystemExit with a clear message on an image without the feature."""
    import dbg_xdata as X
    mp = Path(map_path)
    d = S.note_defs()
    slot, cnt, diag = _sym(mp, "g_aucAwtoNote"), _sym(mp, "g_usAwtoNoteN"), _sym(mp, "isr_g_stAwtoDiag")
    if slot is None or cnt is None or diag is None:
        raise SystemExit(f"note: {mp.name} has no host note (g_aucAwtoNote / g_usAwtoNoteN; image built before #273): nothing written")
    cmd = diag + TESTCMD_OFF
    body, cut = prepare(text, d["CHARS"])
    if cut:
        say(f"note truncated: {len(text)} chars cut to {d['CHARS']} (last char '{MARK}')")
    r = X.read_bytes(io, cnt, 2)
    if r is None:
        raise OSError("note: counter read over 0x35 failed")
    seq = (int.from_bytes(bytes(r), "big") + 1) & 0xFFFF
    if open_console:
        _wr(io, cmd, TC_CONSOLE)
    for off, v in slot_bytes(seq, body, d):
        _wr(io, slot + off, v)
    _wr(io, cmd, TC_HOST_NOTE)
    t0 = time.monotonic()
    while True:
        r = X.read_bytes(io, cnt, 2)
        if r is not None and int.from_bytes(bytes(r), "big") == seq:
            break
        if time.monotonic() - t0 > NOTE_WAIT_S:
            raise OSError(f"note: counter stayed {None if r is None else int.from_bytes(bytes(r), 'big')} for {NOTE_WAIT_S} s "
                          f"(limit = worst main pass 255 ms x 1.25): firmware without test cmd 0x{TC_HOST_NOTE:02X}? not logged")
        time.sleep(NOTE_POLL_S)
    say(f"note {seq}: {body.decode()!r}{' (truncated)' if cut else ''}")
    return seq


def note_step(io, map_path: Path, text: str) -> bool:
    """test-driver step note: never fatal (an image without the feature, a NAK): logged as skipped, False"""
    try:
        note_io(io, map_path, text)
        return True
    except (SystemExit, OSError) as e:
        say(f"note skipped: {e}")
        return False


def host_note(unit: int | str, text: str, open_console: bool = False) -> None:
    """one test step on the unit's diag log: `./dev.py note` (debug link on for the call). Raises on failure, never hangs
    longer than the dev.py link swap."""
    args = [sys.executable, str(ROOT / "dev.py"), "note", "--unit", str(unit), *(["--open-console"] if open_console else []), text]
    r = subprocess.run(args, cwd=ROOT, check=False)
    if r.returncode:
        raise OSError(f"host note to unit {unit} failed (rc {r.returncode}); see tmp/logs/host_note.log")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--open-console", action="store_true")
    ap.add_argument("text")
    a = ap.parse_args()
    import i2cbus
    import rtd_i2c_bridge as B
    i2cbus.require_unit(a.bus, a.serial)
    io = B.Real(a.bus, allow_write=True, regread=True)
    try:
        note_io(io, a.map, a.text, a.open_console)
    except OSError as e:
        say(str(e))
        return 1
    finally:
        io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
