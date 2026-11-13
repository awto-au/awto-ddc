#!/usr/bin/env python3
"""Selector switch to ANOTHER input on unit 2 (Dan 2026-11-12: "cannot switch to input with cable", awto-ddc#132).

usage: selector_switch_unit.py MAP [--how idle|auto|both] [--keep-link]
- MAP = tmp/fw/<image>.map of the image ON unit 2 (checked against tmp/fw/AWT26110002-flashed.json: a wrong map = wrong addresses).
- Cases per --how: D2 -> D1 -> D2, D2 -> D3 -> D2. SOURCE opens the selector, SOURCE steps until the highlighted item
  (g_stOSDUserData.ucOsdInputPort) is the target, then the idle commit (AWTO_SRC_IDLE_COMMIT_MS) or AUTO takes it.
- Every key waits for its effect (OSD state / item byte), never a fixed settle. Per case: port + mode after, the new ring lines.
- A target with no cable must be refused with its ring line (#84), then MENU cancels. No video on D1 (host DP-1 off): no signal
  on D1 counts as switched; the way back is taken before the SDK's power-saving card (debug slave silent in power saving).
- A target disabled by its setting (#81 d1..d3_enable, g_ucAwtoPortOff): the take must enable it (ring line "<port> enabled by
  the input selector", mask bit clear) and then switch. The run ends with each port's enable as it was at the start.
- The debug slave follows the port with a signal: D1 (DP) with host video answers on DP-1's bus (15), not HDMI-2's (11).
  follow() moves the reads to whichever of BUSES has the diag magic (after a take, at each case start, at the end).
- Unit 2 only (keymap_unit.Unit checks the serial). Ends on D2 fixed (settings_cli set input 1), debug link off.
Log: tmp/logs/selector_switch_unit.log
"""
import re
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keymap_unit as K  # noqa: E402

K.ROOT = Path(os.environ.get("AWTO_DDC_REPO") or K.ROOT)  # repo with tmp/fw (images), tmp/logs
K.LOG = K.ROOT / "tmp/logs/selector_switch_unit.log"
SEL_STATE = 144                                 # _MENU_HOTKEY_SOURCE (g_stOsdInfo.usOsdState)
ITEM_OFS = 19                                   # g_stOSDUserData.ucOsdInputPort (fw_sim probe: rows 0..3 -> 0, 3, 4, 5)
ITEM = {"Auto": 0, "D1": 3, "D2": 4, "D3": 5}   # _OSD_INPUT_AUTO, _OSD_INPUT_D1..D3
PORT = {"D1": 0x04, "D2": 0x05, "D3": 0x06}
NAME = {v: k for k, v in PORT.items()}
MODE_NOSIGNAL, MODE_SEARCH = 5, 1
BUSES = (11, 15)                                # unit 2: HDMI-2 (D2), DP-1 (D1) connector buses (panel_unit.AUTO_BUSES)
CLI = Path(__file__).resolve().parent / "settings_cli.py"   # this checkout's host settings table (K.ROOT may be another repo)
# selector open / step: one main pass + the card draw (sim 175 ms, #139), unit loop ~3x slower with the debug link polled
# = ~0.5 s; x1.25 -> 0.65 s. Expiry = the key line says NO EFFECT, measured time logged.
DRAW_S = 0.65
IDLE_S = 2.0 * 1.25                             # AWTO_SRC_IDLE_COMMIT_MS x1.25: the take must be in by then
SETTLE_S = 5.0                                  # take -> ACTIVE / no signal: HDMI ~1.5 s, DP search 3 s worst; x1.25


class Unit(K.Unit):
    def __init__(self, mp):
        super().__init__(mp)
        import settings_cli as C
        self.pri, self.sidx = C.xaddr(self.mt, "g_pucSourceSearchPriority"), C.xaddr(self.mt, "g_ucSearchIndex")
        self.off_a = C.xaddr(self.mt, "g_ucAwtoPortOff") if "_g_ucAwtoPortOff" in self.mt else None   # #81 images only

    def follow(self):
        """reads on the bus whose 0x35 answers (the debug slave moves with the port that has a signal); True = moved"""
        import dbg_link
        from rtd_i2c_bridge import Real
        import settings_cli as C
        if dbg_link.dbg_ok(K.BUS):
            return False
        for b in BUSES:
            if b != K.BUS and dbg_link.dbg_ok(b):
                K.say(f"  debug slave on bus {b} now (bus {K.BUS} silent): reads follow")
                self.io.close()
                K.BUS = b
                self.io = Real(b, allow_write=True)
                self.box = C.Box(self.io, self.mt)
                return True
        return False

    def off(self, p):
        """port p disabled by its setting (AWTO_PORT_BIT: bit = port - _D0_INPUT_PORT)"""
        return self.off_a is not None and (self.rd(self.off_a)[0] >> (PORT[p] - 3)) & 1 == 1

    def item(self):
        return self.rd(self.ud + ITEM_OFS)[0]

    def port(self):
        return self.rd(self.pri, 10)[self.rd(self.sidx)[0] % 10]

    def press(self, k, what, ok):
        """one key, then its effect: ok() within DRAW_S; returns seconds or None"""
        self.key(k, settle=0)
        t = self.until(ok, DRAW_S)
        K.say(f"  key {what}: {'done' if t is not None else 'NO EFFECT'} after {t if t is not None else DRAW_S:.2f} s"
              f" (osd {self.osd()}, item {self.item()})")
        return t


def bus_now():
    """the bus whose 0x35 answers, polled up to SETTLE_S (an input switch moves the slave); expiry: K.BUS, logged"""
    import dbg_link
    t0 = time.monotonic()
    while time.monotonic() - t0 < SETTLE_S:
        for b in BUSES:
            if dbg_link.dbg_ok(b):
                K.BUS = b
                return b
        time.sleep(0.1)
    K.say(f"  no bus of {BUSES} answers 0x35 after {SETTLE_S} s: using bus {K.BUS}")
    return K.BUS


def name(p):
    return NAME.get(p, hex(p))


def ring_new(u, before):
    """ring lines without sync_log's host-time column (it changes every read), and the ones not in `before`"""
    lines = [ln.strip().split(None, 1)[-1] for ln in u.ring(whole=True).splitlines() if re.match(r"\S+\s+\d+:", ln.strip())]
    return lines, [ln for ln in lines if ln not in before]


def case(u, frm, to, how, seen):
    u.follow()
    K.say(f"case {frm} -> {to} by {how}: port {name(u.port())} mode {u.mode()} osd {u.osd()}")
    if u.osd() == SEL_STATE:
        u.press(K.K_MENU, "MENU (selector left open)", lambda: u.osd() != SEL_STATE)
    if u.press(K.K_SOURCE, "SOURCE (open)", lambda: u.osd() == SEL_STATE) is None:
        u.check(f"{frm} -> {to} by {how}: SOURCE opens the selector", False, f"osd {u.osd()}")
        return seen
    opened = u.item()
    for _ in range(4):
        if u.item() == ITEM[to]:
            break
        i0 = u.item()
        u.press(K.K_SOURCE, "SOURCE (step)", lambda: u.item() != i0)
    if u.item() != ITEM[to]:
        u.check(f"{frm} -> {to} by {how}: highlight reaches {to}", False, f"item {u.item()}")
        return seen
    was_off = u.off(to)
    t0 = time.monotonic()
    if how == "auto":
        u.key(K.K_AUTO, settle=0)
    closed = u.until(lambda: u.osd() != SEL_STATE, IDLE_S if how == "idle" else DRAW_S)
    want = (K.MODE_ACTIVE,) if to != "D1" else (K.MODE_ACTIVE, MODE_NOSIGNAL)     # D1 = DP: host DP-1 may be off (no video)
    went = []                                   # D1: settled only after its search (a stale mode before the reset is no result)

    def done():
        u.follow()
        m = u.mode()
        went.append(m)
        return u.port() == PORT[to] and m in want and (to != "D1" or MODE_SEARCH in went)
    settled = u.until(done, SETTLE_S)
    seen, new = ring_new(u, seen)
    K.say(f"  take: selector {'closed after %.2f s' % closed if closed is not None else 'STILL OPEN'}; port {name(u.port())} "
          f"mode {u.mode()} ({'settled %.2f s' % settled if settled is not None else 'not settled'}, "
          f"{time.monotonic() - t0:.1f} s after the take); opened on item {opened}")
    K.say("  ring:\n" + "\n".join("    " + ln.strip() for ln in new))
    if closed is None and any(f"input selector:{to} refused, no cable" in ln for ln in new):   # still open + its line (old lines may re-show)
        u.check(f"{frm} -> {to} by {how}: no cable on {to}: refused with its line, selector still open", u.osd() == SEL_STATE)
        u.press(K.K_MENU, "MENU (cancel)", lambda: u.osd() != SEL_STATE)
        return ring_new(u, seen)[0]
    u.check(f"{frm} -> {to} by {how}: switched (port {to}, ACTIVE or no signal), ring has the switch + request lines",
            settled is not None and any(ln.rstrip().endswith(f"switch to {to}") for ln in new)
            and any("by input selector" in ln for ln in new), f"port {name(u.port())} mode {u.mode()}")
    if was_off:
        u.check(f"{frm} -> {to} by {how}: {to} was disabled: enabled by the take (line + mask bit clear)",
                any(f"{to} enabled by the input selector" in ln for ln in new) and not u.off(to))
    u.check(f"{frm} -> {to} by {how}: one search (no kept reset searching again after display setting)",
            not any(("in DISPLAY SETTING for " in ln and "->SEARCH:" in ln) for ln in new))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    ap.add_argument("--how", choices=("idle", "auto", "both"), default="both")
    ap.add_argument("--keep-link", action="store_true", help="leave the debug link on (a next run follows)")
    a = ap.parse_args()
    flashed = json.loads((K.ROOT / f"tmp/fw/{K.SERIAL}-flashed.json").read_text())["tag"]
    if flashed != a.map.stem:
        raise SystemExit(f"unit 2 runs {flashed}, map is {a.map.stem}: wrong map = wrong addresses")
    import dbg_link
    K.say(f"selector_switch_unit {a.map.name} on unit {K.UNIT} (bus {K.BUS})")
    dbg_link.on(K.BUS, 10)
    u = Unit(a.map)
    off0 = []
    try:
        K.nothing_open(u)
        off0 = [p for p in PORT if u.off(p)]
        K.say(f"  disabled by setting at the start: {' '.join(off0) or 'none'}")
        seen = ring_new(u, [])[0]
        for how in (("idle", "auto") if a.how == "both" else (a.how,)):
            for frm, to in (("D2", "D1"), ("D1", "D2"), ("D2", "D3"), ("D3", "D2")):
                u.follow()
                if u.port() != PORT[frm]:
                    K.say(f"skip {frm} -> {to} by {how}: on {name(u.port())}, not {frm}")
                    continue
                seen = case(u, frm, to, how, seen)
    finally:
        u.io.close()
        out = K.run(CLI, "--bus", bus_now(),  "--serial", K.SERIAL, "--map", a.map, "set", "input", "1", limit=60)
        K.say(f"  input back to D2 fixed: {out.strip().splitlines()[-1] if out.strip() else 'no output'}")
        for p in off0:                          # enables as at the start (the take enabled a disabled target)
            out = K.run(CLI, "--bus", bus_now(), "--serial", K.SERIAL, "--map", a.map, "set",
                        f"{p.lower()}_enable", "0", limit=60)
            last = out.strip().splitlines()[-1] if out.strip() else "no output"
            K.say(f"  {p} disabled again: {last}")
            u.check(f"{p} disabled again at the end", last.startswith("set "), last)
        if not a.keep_link:
            dbg_link.off(bus_now())
            K.say("  debug link off")
    K.say(f"{'PASS' if u.fails == 0 else 'FAIL'} selector_switch_unit: {u.fails} failed")
    return 1 if u.fails else 0


if __name__ == "__main__":
    sys.exit(main())
