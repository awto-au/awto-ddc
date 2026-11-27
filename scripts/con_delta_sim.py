#!/usr/bin/env python3
"""Console delta column + episode-start rules in fw_sim (Dan 2026-11-27): snapshots of a boot and a wake, checked against the ring.

usage: AWTO_SIM_CORE=fast con_delta_sim.py BIN [--map MAP] [--out tmp/len/con_delta]
Scenario: cold boot 1080p60 with the console opened at the first main-loop passes (test cmd 0x26), shot at DISPLAY SETTING and
at ACTIVE; power saving (VCP D6 = 4), SOURCE-key wake, console again, shot (the sim's wake goes on searching: power NORMAL
is the check, as con_wrap_sim).
FAIL: a shown line whose delta column is not the ring's (sync_log.deltas); a ring episode start in view that is not a red rule row
(`-- text ---`, palette AWTO_PAL_DIAG_ALERT); a rule row that is no episode start; no rule in the boot and wake shots.
Out: <name>.txt / .png per shot, host.txt = sync_log's decoded ring (same delta column and rules). Log: tmp/logs/con_delta_sim.log
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import con_wrap_sim as W
import osd_model as M
import osd_render as R
import sync_log as SL
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/con_delta_sim.log"
CMD_CON = 0x26                          # test cmd: console open
MODE_DISPLAY, MODE_ACTIVE = 2, 3        # SysModeGetModeState (fw_sim.SimBus.mode_state)
FIRST_LINES_S = 0.4                     # cold boot -> a few ring lines (MCU set-up, INITIAL): sim s, the 0x26 open follows
ALERT = int(re.search(r"^#define AWTO_PAL_DIAG_ALERT\s+(\d+)", (ROOT / "fw/osd/console.c").read_text() + (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text(), re.MULTILINE).group(1))


def say(s: str):
    _log_line(s, LOG)


def shot(s: W.Sim, name: str, out: Path) -> int:
    """save the shown page; check each line's delta and rule state against the ring; return the rule rows shown"""
    t = s.text()
    st = s.model.snapshot(s.m, 0)
    (out / f"{name}.txt").write_text("\n".join(r.rstrip() for r in t) + "\n")
    R.render_snap(st, "black", 1).save(out / f"{name}.png")
    h, lines = SL.decode(bytes(SL.read_ring(s.m.rd, s.a_sync)), s.rows, whole=True)
    want: dict[str, set] = {}
    for ln, ev, (d, start) in zip(lines, h["events"], SL.deltas(h["events"])):
        want.setdefault(W.norm(ln.split(":", 1)[1]), set()).add((SL.fmt_delta(d), start))
    lay = M.layout_rows(st, M.frame_geometry(st))
    bad, rules = [], 0
    for r, lr in zip(t[1:], lay[1:]):
        r = r[W.LOG_COL:]
        m = W.HEAD.match(r)
        if not m:
            continue
        body = r[m.end():].rstrip()
        rule = W.RULE.match(body)
        txt = W.norm(rule.group(1) if rule else body)
        if txt not in want:
            continue                                     # a wrapped first row (its text is a prefix): con_wrap_sim checks those
        if (m.group(1), bool(rule)) not in want[txt]:
            bad.append(f"{m.group(1)!r} rule {bool(rule)} vs ring {sorted(want[txt])}: {txt[:50]}")
        if rule:
            rules += 1
            fg = {c["fg"] for c, ch in zip(lr["chars"], t[lay.index(lr)]) if c["kind"] == "1bit" and ch != " "}
            if fg != {ALERT}:
                bad.append(f"rule row colours {sorted(fg)}, want palette {ALERT} (AWTO_PAL_DIAG_ALERT): {txt[:40]}")
    s.check(not bad, f"{name}: delta column and episode-start rules match the ring", "; ".join(bad[:3]))
    say(f"  {name}: {rules} rule row(s); page {out / name}.txt")
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/len/con_delta")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    out = a.out / a.bin.stem
    out.mkdir(parents=True, exist_ok=True)
    say(f"=== con_delta_sim {a.bin.name} ===")
    s = W.Sim(a.bin, mapp)
    s.bus.wait(FIRST_LINES_S)
    s.cmd(CMD_CON)
    s.check(s.until(lambda: s.bus.mode_state() == MODE_DISPLAY, W.ON_S + W.PS_S), "cold boot: DISPLAY SETTING")
    s.check(shot(s, "1-boot-display-setting", out) >= 1, "boot: the boot line is a red rule in view")
    s.check(s.until(lambda: s.bus.mode_state() == MODE_ACTIVE, W.ON_S), "cold boot: ACTIVE")
    s.bus.wait(W.DRAW_S)
    shot(s, "2-boot-active", out)
    s.mccs.set(0xD6, 4)
    s.check(s.until(lambda: s.power() == W.PWR_SAVING, W.PS_S), "VCP D6 = 4: power saving")
    s.cmd(W.K_SOURCE)
    s.check(s.until(lambda: s.power() == W.PWR_NORMAL, W.WAKE_S), "SOURCE key: woke (power NORMAL)")
    s.cmd(CMD_CON)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], W.DRAW_S)
    s.bus.wait(W.DRAW_S)
    s.check(shot(s, "3-wake", out) >= 1, "wake: the wake BEGIN is a red rule in view")
    h, lines = SL.decode(bytes(SL.read_ring(s.m.rd, s.a_sync)), s.rows, whole=True)
    host = SL.with_delta(lines, SL.deltas(h["events"]))
    (out / "host.txt").write_text("\n".join(host) + "\n")
    say(f"{'PASS' if s.fails == 0 else 'FAIL'} con_delta_sim {a.bin.name}: {s.fails} failed (pages: {out})")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
