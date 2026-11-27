#!/usr/bin/env python3
"""Console delta column + episode-start rules in fw_sim (Dan 2026-11-27): snapshots of a boot and a wake, checked against the ring.

usage: AWTO_SIM_CORE=fast con_delta_sim.py BIN [--map MAP] [--out tmp/len/con_delta]
Scenario: cold boot 1080p60 with the console opened at the first main-loop passes (test cmd 0x26), shot at DISPLAY SETTING and
at ACTIVE; power saving (VCP D6 = 4), SOURCE-key wake, console again, shot (the sim's wake goes on searching: power NORMAL
is the check, as con_wrap_sim); then a host time sync, the fw clock jumped 131 s (a gap over the 16-bit ring time), a monitor
pair injected, console reopened, shot.
Also: 200 lines added to the boot episode, console reopened: the red boot row is still the first row ("(N lines not shown)").
FAIL: a shown row whose real-time column or delta is not the ring's (sync_log.con_rows); a ring episode start in view that is not a red rule row
(`-- text ---`, palette AWTO_PAL_DIAG_ALERT); a rule row that is no episode start; no rule in the boot and wake shots.
Out: <name>.txt / .png per shot, host.txt = sync_log's decoded ring (same delta column and rules). Log: tmp/logs/con_delta_sim.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import con_wrap_sim as W
import host_time as HT
import osd_model as M
import osd_render as R
import sync_log as SL
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/con_delta_sim.log"
CMD_CON = 0x26                          # test cmd: console open
CMD_CLOSE = 0x27                        # test cmd: console closed, holds cleared
MODE_DISPLAY, MODE_ACTIVE = 2, 3        # SysModeGetModeState (fw_sim.SimBus.mode_state)
FIRST_LINES_S = 0.4                     # cold boot -> a few ring lines (MCU set-up, INITIAL): sim s, the 0x26 open follows
UP_HI_OFF = 14                          # StAwtoHt.usUpHi (RL6449_Project.h; sync_log.ht_decode b[14:16])
GAP_UNITS = 2                           # the gap: 2 x 65.536 s = 131.072 s, over the 16-bit ring time
OFS = 44                                # +11:00, 15 min units
T0 = dt.datetime(2026, 11, 27, 15, 18, 14, 833000, dt.timezone(dt.timedelta(hours=11)))
FILLER = (0xE7, 3, 0)                   # "D1 EDID read" (AWTO_SYNC_EV_EDID): a plain row, never joined
OVERFLOW_N = 200                        # lines added to the boot episode: past the console map (57 rows), the 88-line window and a seq wrap (176)
JOIN_PAIR = ((0xEA, 2, 2001), (0xEA, 4, 1150 << 8 | 0xD4))     # monitor IOSC + uptime rows (AWTO_MON_EV_TRIM / _UP)
ALERT = int(re.search(r"^#define AWTO_PAL_DIAG_ALERT\s+(\d+)", (ROOT / "fw/osd/console.c").read_text() + (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text(), re.MULTILINE).group(1))


def say(s: str):
    _log_line(s, LOG)


def shot(s: W.Sim, name: str, out: Path) -> int:
    """save the shown page; check each row's real-time column, delta and rule state against the ring rows (sync_log.con_rows with
    the firmware's host-time state); return the rule rows shown"""
    t = s.text()
    st = s.model.snapshot(s.m, 0)
    (out / f"{name}.txt").write_text("\n".join(r.rstrip() for r in t) + "\n")
    R.render_snap(st, "black", 1).save(out / f"{name}.png")
    want: dict[str, set] = {}
    for r in s.con_rows(ht(s)):
        want.setdefault(W.norm(r["text"]), set()).add((r["real"], SL.fmt_delta(r["delta"]), r["start"]))
    lay = M.layout_rows(st, M.frame_geometry(st))
    bad, rules, n = [], 0, 0
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
        n += 1
        if (m.group("real"), m.group(2), bool(rule)) not in want[txt]:
            bad.append(f"{m.group('real')!r} {m.group(2)!r} rule {bool(rule)} vs ring {sorted(want[txt])}: {txt[:50]}")
        if rule:
            rules += 1
            fg = {c["fg"] for c, ch in zip(lr["chars"], t[lay.index(lr)]) if c["kind"] == "1bit" and ch != " "}
            if fg != {ALERT}:
                bad.append(f"rule row colours {sorted(fg)}, want palette {ALERT} (AWTO_PAL_DIAG_ALERT): {txt[:40]}")
    s.check(not bad and n > 0, f"{name}: real time, delta column and episode-start rules match the ring ({n} rows)", "; ".join(bad[:3]))
    say(f"  {name}: {rules} rule row(s); page {out / name}.txt")
    return rules


def reopen(s: W.Sim):
    """console closed and opened again: drawn anew from the ring"""
    s.cmd(CMD_CLOSE)
    s.bus.wait(W.DRAW_S)
    s.cmd(CMD_CON)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], W.DRAW_S)
    s.bus.wait(W.DRAW_S)


def ht(s: W.Sim) -> dict:
    return SL.ht_decode(bytes(s.m.rd(s.m.addr("g_stAwtoHt"), SL.HT_SIZE)))


def jump(s: W.Sim, units: int):
    """fw clock + units x 65.536 s at once (g_stAwtoHt.usUpHi = AwtoMs bits 31..16): a gap over the 16-bit ring time without the sim time"""
    a = s.m.addr("g_stAwtoHt") + UP_HI_OFF
    hi = int.from_bytes(bytes(s.m.rd(a, 2)), "big")
    s.m.wr(a, (hi + units).to_bytes(2, "big"))
    return hi + units


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
    hi = int.from_bytes(bytes(s.m.rd(s.m.addr("g_stAwtoHt") + UP_HI_OFF, 2)), "big")
    SL.inject_lines(s.m.rd, s.m.wr, s.a_sync, [FILLER] * OVERFLOW_N, bytes(s.m.rd(0xF6D0 + SL.DIAG_T2, 2)), hi)
    reopen(s)
    first = next((r[W.LOG_COL:] for r in s.text()[1:] if W.HEAD.match(r[W.LOG_COL:])), "")
    body = first[W.HEAD.match(first).end():] if first else ""
    s.check(body.startswith("-- boot:") and "lines not shown)" in body,
            f"boot overflowing the console ({OVERFLOW_N} more lines): the red boot row is still the first row", body.strip()[:90])
    shot(s, "2b-boot-overflow", out)
    s.mccs.set(0xD6, 4)
    s.check(s.until(lambda: s.power() == W.PWR_SAVING, W.PS_S), "VCP D6 = 4: power saving")
    s.cmd(W.K_SOURCE)
    s.check(s.until(lambda: s.power() == W.PWR_NORMAL, W.WAKE_S), "SOURCE key: woke (power NORMAL)")
    s.cmd(CMD_CON)
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], W.DRAW_S)
    s.bus.wait(W.DRAW_S)
    s.check(shot(s, "3-wake", out) >= 1, "wake: the wake BEGIN is a red rule in view")
    s.mccs.tx(HT.packet(T0.timestamp(), OFS)[1:-1], reply=False)      # host time sync mid-run (host_time.py encoding)
    s.check(s.until(lambda: ht(s)["syncs"] == 1, W.DRAW_S), "host time sync 1 taken")
    hi = jump(s, GAP_UNITS)
    ms2 = bytes(s.m.rd(0xF6D0 + SL.DIAG_T2, 2))
    SL.inject_lines(s.m.rd, s.m.wr, s.a_sync, JOIN_PAIR, ms2, hi)        # a monitor pair after the gap: one joined row
    say(f"  fw clock + {GAP_UNITS} x 65.536 s, then {len(JOIN_PAIR)} monitor lines (one call) injected")
    reopen(s)                                                            # every row drawn with the host sync known
    shot(s, "4-gap-host-time", out)
    rs = s.con_rows(ht(s))
    gap = [r for r in rs if r["delta"] is not None and r["delta"] >= GAP_UNITS * 0x10000]
    s.check(len(gap) == 1 and not any(r["wrap"] for r in rs), "host: one row after the gap shows the full delta (32-bit ms), no wrap row",
            str([(SL.fmt_delta(r["delta"]), r["text"][:30]) for r in gap]))
    s.check(any(r["text"].startswith("monitor: IOSC 2001 | ") for r in rs), "host: the injected monitor pair is one row")
    txt = s.text()
    s.check(any(re.search(r"[ ]\d\d:\d\d:\d\d\.\d{3} \+ 13\d s:", x) for x in txt), "console: a row with host clock and the > 65 s delta (+ 13x s)")
    s.check(any("monitor: IOSC 2001 | " in x for x in txt), "console: the monitor pair on one row")
    h, lines = SL.decode(SL.read_ring(s.m.rd, s.a_sync), s.rows, whole=True)
    host = [ln for ln, _ in SL.ring_rows(h, lines, ht(s), int.from_bytes(ms2, "big"))]
    (out / "host.txt").write_text("\n".join(host) + "\n")
    say(f"{'PASS' if s.fails == 0 else 'FAIL'} con_delta_sim {a.bin.name}: {s.fails} failed (pages: {out})")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
