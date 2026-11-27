#!/usr/bin/env python3
"""Info card after boot in fw_sim: on-screen time and the "Found by" row (Dan 2026-11-27).

usage: AWTO_SIM_CORE=fast info_card_sim.py BIN MAP [--mode 1080p60] [--out tmp/info_card]
- console_mode Off (stubbed): the console keeps no screen, the info card opens at the first ACTIVE.
- Runs to ACTIVE, PNG of the card, then waits for the card's timeout close line (sync.tsv ED 7F).
- Checks: one "information card" open line, one timeout close line, its on-screen ms within TIME_SLACK_MS of
  _AWTO_INFO_POPUP_SEC (RL6449_Project.h); prints the F0 "input taken" line the card's row comes from.
Log: tmp/logs/info_card_sim.log
"""
import argparse
import re
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import osd_model as M
import osd_render as R
import sync_log as S
from _repo import ROOT
from PIL import Image

LOG = ROOT / "tmp/logs/info_card_sim.log"
HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
SET_ID_CONSOLE_MODE, CON_OFF = 110, 0   # registry id 110 console_mode, value Off
BUDGET_INSTR = 160_000_000              # boot to ACTIVE ~75 M instructions (boot_sim.py); x2; expiry = FAIL
STEP = 100_000                          # instructions per sample (~1-2 ms fw time)
TIME_SLACK_MS = 50                      # timer event period (SDK timer list polled per main-loop pass) + one pass, x~1.25


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def hdr_sec() -> int:
    t = HDR.read_text()
    v = {k: int(n) for k, n in re.findall(r"^#define (_AWTO_INFO_POPUP_(?:BASE|EXTRA)_SEC)\s+(\d+)", t, re.MULTILINE)}
    return v["_AWTO_INFO_POPUP_BASE_SEC"] + v["_AWTO_INFO_POPUP_EXTRA_SEC"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/info_card")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    want_ms = hdr_sec() * 1000
    say(f"info_card_sim {a.bin.name}: want the card up {want_ms} ms")
    s = R.Session(a.bin, a.map, a.mode)
    m = s.bus.m
    m.stub("set_get", lambda m_, r: {"val": CON_OFF} if (r["a1"] & 0xFF) == SET_ID_CONSOLE_MODE else None)
    rows = S.load_rows(S.tsv_for(a.map))
    ring = S.sym(a.map, "g_stAwtoSync")
    used = 0
    while used < BUDGET_INSTR and s.bus.mode_state() != 3:
        m.run(STEP)
        used += STEP
    if s.bus.mode_state() != 3:
        say(f"  FAIL no ACTIVE after {used} instr")
        return 1
    s.bus.wait(1.0)                     # card drawn (ACTIVE one-time OSD event, next passes)
    snap = s.model.snapshot(m, 0.0)
    Image.fromarray(np.array(R.render_snap(snap, "grey", 1))).save(a.out / "info_card_boot.png")
    say(f"  png {a.out / 'info_card_boot.png'} (OSD {'on' if M.summary(snap)['en'] else 'OFF'})")
    s.bus.wait(want_ms / 1000.0 + 1.0)
    evs = S.read_ring(m.rd, ring)
    _h, lines = S.decode(evs, rows)
    say(f"  {len(lines)} lines, last: {lines[-1] if lines else ''}")
    for ln in lines:
        if "pop-up" in ln or "input taken" in ln:
            say(f"    {ln}")
    opens = [ln for ln in lines if "pop-up opened: information card" in ln]
    closes = [ln for ln in lines if "pop-up closed: its on-screen time ran out" in ln]
    up = [int(x) for x in re.findall(r"up (\d+) ?ms", " ".join(closes))]
    fails = 0
    for ok, what, det in ((len(opens) == 1, "one information card open line", str(len(opens))),
                          (len(closes) == 1, "one timeout close line", str(len(closes))),
                          (len(up) == 1 and abs(up[0] - want_ms) <= TIME_SLACK_MS, f"card up {want_ms} ms (+-{TIME_SLACK_MS})", str(up))):
        say(f"  {'PASS' if ok else 'FAIL'} {what}: {det}")
        fails += 0 if ok else 1
    say(f"=== {a.bin.name}: {'ALL PASS' if not fails else f'{fails} FAIL'} ===")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
