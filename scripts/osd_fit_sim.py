#!/usr/bin/env python3
"""OSD fit, sim half: every card / selector / menu shot of card_shot.py, drawn with the firmware's own values; FAIL on a cut row.

usage: AWTO_SIM_CORE=fast osd_fit_sim.py BIN MAP [--modes 1080p60,2160p60]
- The firmware's fit guard (fw/osd/console.c AwtoFitCheck) pushes sync line ED 7E for a row whose text reaches the box's
  last cell (under the frame) or was dropped past it. Every AwtoSyncPushW call is watched: any ED 7E = FAIL, named by shot.
- Covers rows drawn by AwtoTextLine / AwtoFieldEnd with this sim's inputs (HDMI D2, the --modes timings). DP-only rows (DP link,
  swing) and other widths come from the static half, scripts/osd_fit.py (fw/osd/osd_fit.tsv worst cases).
- Also a guard check: a shot whose OSD is off is listed (nothing drawn, nothing judged).
Log: tmp/logs/osd_fit_sim.log
"""
import argparse
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_shot as CS
import osd_model as M
import osd_render as R
from _repo import ROOT

LOG = ROOT / "tmp/logs/osd_fit_sim.log"
EV_CARD, ARG_CUT = 0xED, 0x7E       # sync.tsv: OSD text row cut (RL6449_Project.h AWTO_SYNC_EV_CARD / AWTO_CARD_ROW_CUT)


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def run_mode(a, mode: str) -> int:
    cuts, shot = [], ["boot"]
    s = R.Session(a.bin, a.map, mode)
    s.bus.m.stub("AwtoSyncPushW", lambda m_, r: (cuts.append((shot[0], r["r"][2] << 8 | r["r"][3]))
                                                 if (r["r"][7], r["r"][5]) == (EV_CARD, ARG_CUT) else None) and None)
    off = []
    try:
        s.boot()
        for name, cmds in CS.SHOTS:
            shot[0] = name
            if name not in CS.CHAIN:
                CS.send(s, CS.CLEAR)
                CS.send(s, CS.K_MENU)
            for c in cmds:
                CS.send(s, c)
            s.bus.wait(a.wait)
            if not M.summary(s.snap())["en"]:
                off.append(name)
    finally:
        s.bus.close()
    for nm, v in cuts:
        say(f"  FAIL {mode} {nm}: OSD text row cut, {v} cell(s) over its box")
    say(f"  {'PASS' if not cuts else 'FAIL'} {mode}: {len(CS.SHOTS)} shots, {len(cuts)} cut row(s); OSD off in: {', '.join(off) or 'none'}")
    return len(cuts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--modes", default="1080p60,2160p60")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds after the last command of a shot")
    a = ap.parse_args()
    say(f"osd_fit_sim {a.bin.name}")
    bad = sum(run_mode(a, md) for md in a.modes.split(","))
    say(f"=== {a.bin.name}: {'ALL PASS' if not bad else f'{bad} cut row(s)'} ===")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
