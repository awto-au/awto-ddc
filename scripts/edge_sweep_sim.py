#!/usr/bin/env python3
"""Edge-value sweep of the settings registry in fw_sim (awto-ddc#214): every row at min, min+1, mid, max-1, max.

usage: edge_sweep_sim.py BIN MAP [--rows a,b,...] [--quick]
  Per value, set through the menu (row on a page: open page, select row, MO_SET; the row is drawn) or the mailbox (no page):
  - read back (VCP mailbox get) = the value written (no silent clamp / overflow);
  - every enabled OSD window has x1 > x0, y1 > y0 and ends on the panel (the 1 % backlight line: x0 = x1 drew to the line end);
  - no divide by 0 (scripts/div0_sim.py: --keil-div helpers with a 0 divisor, DIV AB with B = 0), attributed per value;
  - brightness: the backlight card (UP / DOWN hot key) drawn at the value, PWM4 duty (info_pwm) = 255 at 0 %, falling with the value.
  ro rows: read once, inside min..max. action rows: not run. Each row goes back to its default after its values.
  --quick: only min, min+1, max-1, max.
Exit 1 on a failed check. Log: tmp/logs/edge_sweep_sim.log
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
from pathlib import Path

from _log import log_line as _log_line

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import div0_sim
import menu_cli as MC
import osd_model as M
import osd_render as R
import settings_cli as C
import settings_table as T

LOG = R.ROOT / "tmp/logs/edge_sweep_sim.log"
SETTLE_S = 0.05            # sim: a set is applied in the pass that serves the mailbox; one more pass for a deferred draw (~3 ms each)
PWM_OFF = 0xFF             # PWM4 duty byte with the backlight off (inverse drive, #279)
SKIP = {   # row -> why the sweep does not drive it (logged as SKIP; the named sim covers the row)
    "input": "switches the port: the sim host is on D2's DDC only, 0x35 leaves with the input (deadport_sim, portcfg_sim)",
    "power_mode": "standby..off power the unit down: the mailbox goes with it (wake_sim, sysm_sim)",
}
PRE = {   # row -> settings it needs first (set before, defaults after)
    "user_red": {"colour_temp": 5}, "user_green": {"colour_temp": 5}, "user_blue": {"colour_temp": 5},   # User preset only (nv_gate.c, #371)
}
REFUSE = {   # row -> {value: why the firmware refuses it}: checked refused, value unchanged
    "d2_enable": {0: "the input on screen is never disabled (registry note, #81)"},
}
WIN_BL_FILL = 5           # AWTO_WIN_BL_FILL (fw/osd/console.c): the backlight card's fill bar; off at 0 %
KEY_UP, KEY_DOWN, KEY_MENU = MC.KEYS["right"], MC.KEYS["left"], MC.KEYS["exit"]   # roles -> physical UP / DOWN / MENU


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def values(r: dict, quick: bool) -> list[int]:
    lo, hi = r["min"], r["max"]
    v = {lo, lo + 1, hi - 1, hi} | (set() if quick else {(lo + hi) // 2})
    return sorted(x for x in v if lo <= x <= hi)


def page_of_row(r: dict) -> int | None:
    k = T.ROWS.index(r)
    return next((i for i, p in enumerate(T.PAGES) if k in p["entries"]), None)


def win_faults(st: M.OsdState) -> list[str]:
    g = M.frame_geometry(st)
    if not g["en"] or not st.ovl[0] & 1:
        return []
    out = []
    for i in range(26):
        w = M.decode_window(st.win, i)
        if not w["en"]:
            continue
        hd, vd = (g["hd2"], g["vd2"]) if w["dsel"] else (g["hd"], g["vd"])
        X1, Y1 = hd * g["step"] * g["sx"] + (w["x1"] + 1) * g["sx"], vd * g["sy"] + (w["y1"] + 1) * g["sy"]
        box = f"W{i} ({w['x0']},{w['y0']})..({w['x1']},{w['y1']})"
        if w["x1"] <= w["x0"] or w["y1"] <= w["y0"]:
            out.append(f"{box}: end <= start")
        if X1 > R.PANEL_W or Y1 > R.PANEL_H:
            out.append(f"{box}: ends at panel ({X1},{Y1}), outside {R.PANEL_W}x{R.PANEL_H}")
    return out


class Sweep:
    def __init__(self, binp: Path, mapp: Path):
        self.s = R.Session(binp, mapp, "1080p60")
        self.div = div0_sim.Div0Watch(self.s.bus.m)
        self.s.boot()
        mt = mapp.read_text(errors="replace")
        self.box = C.Box(self.s.bus, mt, True)
        self.menu = MC.Menu(self.box, mt, True)
        self.fails = 0
        self.boot_div0 = self.div.hits()               # reported, not failed: sim has no eDP AUX model, DPTx1 link rate stays 0 (#214)
        for c, h, n in self.boot_div0:
            say(f"  boot divide by 0 (sim: eDP link rate 0, #214): {c} {h} x{n}")

    def check(self, ok: bool, what: str, detail: str = "") -> bool:
        self.fails += not ok
        if not ok:
            say(f"  FAIL {what}{': ' + detail if detail else ''}")
        return ok

    def settle(self):
        self.s.bus.wait(SETTLE_S)

    def common(self, r: dict, v: int, mk: dict, how: str):
        tag = f"{r['name']} = {v} ({how})"
        got = self.box.get_row(r)
        self.check(got == v, f"{tag}: read back", f"{got}")
        wf = win_faults(self.s.snap())
        self.check(not wf, f"{tag}: OSD windows", "; ".join(wf))
        d0 = self.div.since(mk)
        self.check(not d0, f"{tag}: no divide by 0", "; ".join(f"{c} {h} x{n}" for c, h, n in d0))

    def row(self, r: dict, quick: bool):
        if "ro" in r["flags"]:
            v = self.box.get_row(r)
            self.check(r["min"] <= v <= r["max"], f"{r['name']} (ro) = {v} inside {r['min']}..{r['max']}")
            return
        if r["name"] in SKIP:
            say(f"  SKIP {r['name']}: {SKIP[r['name']]}")
            return
        pre = [(T.BY_NAME[k], v) for k, v in PRE.get(r["name"], {}).items()]
        for q, v in pre:
            self.box.set_row(q, v)
        pg = page_of_row(r)
        if pg is not None:
            self.menu.cmd("open", pg)
            self.menu.cmd("select", r["id"])
        for v in values(r, quick):
            mk, before = self.div.mark(), self.box.get_row(r)
            how = "menu" if pg is not None else "mailbox"
            try:
                if pg is not None:
                    self.menu.cmd("set", v)
                    if "risky" in r["flags"]:
                        self.box.call(2, C.CMD, 1)          # confirm, as settings_cli set: no 15 s auto-revert mid-sweep
                else:
                    self.box.set_row(r, v)
                why = None
            except SystemExit as e:                        # result 0 = refused; a dead link (NAK / no answer) goes up
                if "refused" not in str(e) and "unsupported" not in str(e):
                    raise
                why = str(e)
            self.settle()
            want = REFUSE.get(r["name"], {}).get(v)
            if want or why:
                self.check(bool(want) and bool(why), f"{r['name']} = {v} ({how}): refused = {bool(why)}",
                           f"expected {'refused: ' + want if want else 'accepted'}{'; ' + why if why else ''}")
                self.common(r, before, mk, f"{how}, refused {v}")
                continue
            self.common(r, v, mk, how)
        if pg is not None:
            self.menu.cmd("close")
        if r["type"] == "int":
            self.outside(r)
        self.box.set_row(r, r["default"])
        for q, _ in pre:
            self.box.set_row(q, q["default"])
        self.settle()

    def outside(self, r: dict):
        """max + 1 and min - 1 (16-bit wire value, as DDC/CI sends it) through the mailbox: refused or clamped, never stored."""
        for v in (r["max"] + 1, (r["min"] - 1) & 0xFFFF):
            try:
                self.box.call(2, C.SEL, r["id"])
                self.box.call(2, C.VAL, v)
            except SystemExit as e:
                if "unsupported" not in str(e):
                    raise
            self.settle()
            got = self.box.get_row(r)
            self.check(r["min"] <= got <= r["max"], f"{r['name']} = {v} (outside, mailbox): read back inside {r['min']}..{r['max']}",
                       f"{got}")

    def backlight(self, quick: bool):
        """The hot-key card at each value: set one step off, then the UP / DOWN key that lands on it (the card draws the fill)."""
        r, pwm = T.BY_NAME["brightness"], T.BY_NAME["info_pwm"]
        duty = {}
        for v in values(r, quick):
            mk = self.div.mark()
            up = v > r["min"]
            self.box.set_row(r, v - 1 if up else v + 1)
            self.settle()
            self.menu.physical_key(KEY_UP if up else KEY_DOWN)
            self.settle()
            self.common(r, v, mk, "backlight card")
            w = M.decode_window(self.s.snap().win, WIN_BL_FILL)
            self.check(bool(w["en"]) == (v > 0), f"brightness = {v} (backlight card): fill window {'on' if v else 'off'}",
                       f"en {w['en']} ({w['x0']},{w['y0']})..({w['x1']},{w['y1']})")
            duty[v] = self.box.get_row(pwm)
            self.menu.physical_key(KEY_MENU)               # another key closes the card; MENU then opens the menu
            self.settle()
            self.menu.cmd("close")
        lo = min(duty)
        self.check(duty[lo] == PWM_OFF if lo == 0 else True, "brightness 0 %: PWM4 duty = off", f"{duty[lo]}")
        ks = sorted(duty)
        self.check(all(duty[a] > duty[b] for a, b in itertools.pairwise(ks)), "PWM4 duty falls as brightness rises", f"{duty}")
        self.box.set_row(r, r["default"])
        self.settle()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--rows", help="comma list of row names (default: every row)")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    rows = [T.BY_NAME[n] for n in a.rows.split(",")] if a.rows else [r for r in T.ROWS if r["type"] != "action"]
    sw = Sweep(a.bin, a.map)
    n = 0
    for r in rows:
        f0 = sw.fails
        say(f"{r['name']}: fw {sw.s.ms():.0f} ms")
        try:
            sw.row(r, a.quick)
        except SystemExit as e:                            # mailbox / debug slave gone: the row's failure, then stop
            sw.check(False, f"{r['name']}: host link", str(e))
            break
        n += 1 if "ro" in r["flags"] else len(values(r, a.quick))
        if sw.fails != f0:
            say(f"{r['name']}: {sw.fails - f0} failed")
    if not a.rows or "brightness" in a.rows.split(","):
        sw.backlight(a.quick)
    hits = sw.div.hits()
    say(f"divide by 0 over the run: {sw.div.total()}" + "".join(f"\n  {c} {h} x{k}" for c, h, k in hits))
    say(f"{'PASS' if sw.fails == 0 else 'FAIL'} edge_sweep_sim {a.bin.name}: {len(rows)} rows, {n} values, {sw.fails} failed, "
        f"fw {sw.s.ms():.0f} ms")
    return 1 if sw.fails else 0


if __name__ == "__main__":
    sys.exit(main())
