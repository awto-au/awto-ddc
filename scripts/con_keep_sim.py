#!/usr/bin/env python3
"""Log keeping in fw_sim (awto-ddc log-keep, #139 / #144): the console is a VIEW of the sync ring, never a wipe.

usage: AWTO_SIM_CORE=fast con_keep_sim.py BIN [--map MAP]
Marked lines = ring entries id 0x01 (no sync.tsv row, prints "event 01 NN"), injected like AwtoSyncPush writes them.
- keep-episode: marks 1-5, a new episode (BEGIN + ep_seq moved), marks 6-7; the console closed and reopened (test cmd 0x27 / 0x26)
  must show all seven (older episodes stay in the view); the ring itself unchanged by the close / reopen.
- keep-flood: 70 more marks (ring 80, map ~54 rows): after a reopen the newest lines are on the console, contiguous, newest last.
- keep-warm: watchdog reset (test cmd 0x4C; the chip keeps RAM): the ring still holds the marks, followed by the boot line of the
  new boot ("previous boot" = the lines above it); a cold power-up (canary lost) starts an empty ring.
Exit 1 on a failed check. Log: tmp/logs/con_keep_sim.log
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import con_wrap_sim as C
import sync_log as SL

ROOT = Path(__file__).resolve().parents[1]
C.LOG = ROOT / "tmp/logs/con_keep_sim.log"
MARK = 0x01
BEGIN, K_SWITCH = 0xC0, 2
CMD_OPEN, CMD_CLOSE = 0x26, 0x27
MODE_ACTIVE = 3
OPEN_S = 4.0            # console open: font load + map clear + backfill (one line per main pass, 3 ms): 1 s measured, x4 for the first draw
DRAW_MAX_S = 60.0       # 80 ring lines x 0.34 s per line in the sim (measured 2026-11-21, fast core), x2
BITE_INSTR = 40_000_000  # boot_sim.py: test cmd 0x4C -> reset = 14 M instr (cmd 0.1 s + warning 1.03 s), x2.5
RESET_S = 160_000_000   # boot instruction budget (con_wrap_sim)


def marks_on(s: C.Sim) -> list[int]:
    """mark numbers drawn on the console, top to bottom"""
    out = []
    for r in s.text()[1:]:
        m = re.search(r"event 01 ([0-9A-F]{2})", r)
        if m:
            out.append(int(m.group(1), 16))
    return out


def ring_marks(s: C.Sim) -> list[int]:
    raw = bytes(SL.read_ring(s.m.rd, s.a_sync))
    n, wrap, seq = raw[12], raw[13], raw[3]
    out = []
    for k in range(n):
        e = raw[SL.HDR + SL.EV * ((seq - n + k) % wrap % n):][:SL.EV]
        if e[0] == MARK:
            out.append(e[1])
    return out


def push(s: C.Sim, evs):
    s.inject(evs)


def drawn(s: C.Sim, want, sec: float = DRAW_MAX_S) -> bool:
    """until the console shows what `want(marks)` accepts (the console draws one line per main pass: 3 rows / s in the sim)"""
    return s.until(lambda: want(marks_on(s)), sec)


def reopen(s: C.Sim, want):
    s.cmd(CMD_CLOSE)
    s.until(lambda: "AWTO DIAGNOSTICS" not in (s.text() or [""])[0], 2.0)
    s.cmd(CMD_OPEN)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], OPEN_S)
    drawn(s, want)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    C.say(f"=== con_keep_sim {a.bin.name} ===")
    s = C.Sim(a.bin, mapp)
    s.cr = next(d for d in s.m.devs if type(d).__name__ == "ChipReset")
    s.check(s.bus.run_until_mode(MODE_ACTIVE, RESET_S), "cold boot: ACTIVE")
    s.bus.wait(C.NV_IDLE_S)
    s.cmd(CMD_OPEN)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], OPEN_S)

    # keep-episode
    push(s, [(MARK, k, 0) for k in range(1, 6)])
    seq = s.m.rd(s.a_sync + 3)[0]
    push(s, [(BEGIN, K_SWITCH, 0xFF)])
    s.m.wr(s.a_sync + 4, bytes([seq]))                      # ep_seq = the BEGIN line (AwtoSyncBegin)
    push(s, [(MARK, k, 0) for k in (6, 7)])
    before = ring_marks(s)
    reopen(s, lambda m: m == [1, 2, 3, 4, 5, 6, 7])
    s.check(ring_marks(s) == before, "keep-episode: close + reopen leaves the ring alone", f"{before} -> {ring_marks(s)}")
    s.check(marks_on(s) == [1, 2, 3, 4, 5, 6, 7], "keep-episode: reopened console shows marks 1-7 (older episode kept)", str(marks_on(s)))

    # keep-flood
    push(s, [(MARK, 0x10 + k, 0) for k in range(70)])
    want = list(range(0x10 + 70 - 27, 0x10 + 70))
    reopen(s, lambda m: m[-27:] == want)
    on = marks_on(s)
    s.check(on[-27:] == want, "keep-flood: newest 27 marks on the reopened console, contiguous, newest last", f"{len(on)} marks, tail {on[-3:]}")
    s.check(len(on) >= 45 and on == sorted(on), "keep-flood: at least 45 of the map's 54 rows are log lines (49 measured), in ring order", f"{len(on)} marks")

    # keep-warm
    held = ring_marks(s)
    s.cmd(0x4C)                                             # test cmd 0x4C: the main loop hangs, the hardware watchdog resets the chip (warm)
    used = 0
    while s.cr.resets == 0 and used < BITE_INSTR:
        s.m.run(1_000_000)
        used += 1_000_000
    s.check(s.cr.resets == 1, "keep-warm: watchdog reset", f"{used} instr")
    while s.bus.mode_state() == MODE_ACTIVE and used < 2 * BITE_INSTR:        # ACTIVE in RAM until the init rewrites it
        s.m.run(1_000_000)
        used += 1_000_000
    s.check(s.bus.run_until_mode(MODE_ACTIVE, RESET_S), "keep-warm: ACTIVE again after the reset")
    raw = bytes(SL.read_ring(s.m.rd, s.a_sync))
    kept = ring_marks(s)
    s.check(kept[-10:] == held[-10:] and len(kept) > 0, "keep-warm: the ring still holds the previous boot's marks", f"{len(kept)} of {len(held)}")
    _, lines = SL.decode(raw, s.rows, whole=True)
    boots = [i for i, x in enumerate(lines) if "boot:" in x]
    last_mark = max((i for i, x in enumerate(lines) if "event 01" in x), default=-1)
    s.check(boots and last_mark >= 0 and boots[-1] > last_mark, "keep-warm: this boot's reason line comes after the previous boot's lines", f"boot at {boots[-1:]} last mark {last_mark}")
    C.say(f"{'PASS' if s.fails == 0 else 'FAIL'} con_keep_sim {a.bin.name}: {s.fails} failed")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
