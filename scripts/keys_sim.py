#!/usr/bin/env python3
"""Offline proof of the front-key decode and the key test screen (#85, #39): firmware image in fw_sim, ADC / P3.0 injected.

usage: keys_sim.py BIN MAP [--png-dir tmp/osd39] [--skip-decode]
  1. decode: every band edge of A0 / A1 (in and out of band), P3.0, and combos -> g_stAwtoKey.ucMask == the model's mask
  2. test screen: open by test cmd 0x41 (no idle redraw, main-loop rate kept), keys while open, combo release,
     close / open by UP+DOWN, open by UP+DOWN over the #67 menu and close to no menu
  3. wake from DDC/CI D6 off by POWER, MENU and AUTO (#85); AUTO opens the #67 menu, MENU backs out (keys6); SOURCE opens the four-row selector without switching immediately
  4. rtd_keywatch.py --log against the sim bus
  --calibrate: every bound 3 s, prints the worst latency per kind (set the bounds to 1.25x of it)
Every step waits for its condition (sim time, polled every POLL_MS) up to a bound; bounds and their derivation: below.
Last line: RESULT PASS | RESULT FAIL <check names>. Needs the main tree's sim tools: AWTO_DDC_MAIN (default /mnt/2tb/git/awto-ddc).
Log: ./tmp/logs/keys_sim.log
"""
import argparse, contextlib, importlib.util, io as _io, os, sys, time
from pathlib import Path

MAIN = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc")) / "scripts"
sys.path.insert(0, str(MAIN))
sys.path.insert(1, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import osd_model as M  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/keys_sim.log"
IDLE = (0xF8, 0xF8, 1)
# raw (A0, A1) of one key down, as read on unit 2 (idle 0xF8): A0 = MENU AUTO UP, A1 = SOURCE DOWN. Keys are pressed by these
# values only (physical keys), never by SDK key message.
V_MENU, V_AUTO, V_UP, V_SOURCE, V_DOWN = (0xD0, 0xF8), (0x80, 0xF8), (0x38, 0xF8), (0xF8, 0x80), (0xF8, 0x38)
SOURCE, MENU, DOWN, UP, AUTO, POWER = 0x20, 0x10, 0x08, 0x04, 0x02, 0x01      # SDK masks (_KEY5, _EXIT, _LEFT, _RIGHT, _MENU, _POWER): roles swapped, keys6
MSG_AUTO, MSG_UP, MSG_DOWN, MSG_MENU = 0, 1, 2, 3                              # SDK key messages _MENU _RIGHT _LEFT _EXIT as the key block logs them
NAMES = {SOURCE: "SOURCE", MENU: "MENU", DOWN: "DOWN", UP: "UP", AUTO: "AUTO", POWER: "POWER"}

# Bounds, sim ms (T2 tick) = 1.25 x the worst latency `--calibrate` measured on wb-p14keys4 (numbers: #85). Expiry = FAIL naming the step.
# KEY: ADC change -> debounced mask (10 ms scan timer + 2 equal scans; a test-screen redraw blocks the loop meanwhile).
# DRAW: open -> AwtoOsdKeyLines ran. CLOSE: close -> OSD off (waits for DEN stop + any redraw in progress).
# MENU: AUTO press -> #67 menu on / MENU press -> menu off (same pass as the key message: KEY bound). CMD: test cmd written -> acted on.
# PS: D6 off -> mode POWER_SAVING. WAKE: key -> mode ACTIVE (panel on + link training, #78). INPUT: switch -> input row = port.
POLL_MS = 2
KEY_MS, DRAW_MS, CLOSE_MS, MENU_MS, CMD_MS = 453, 68, 225, 453, 223  # CLOSE = 223 ms bound + one 2 ms poll quantum
MODE_ACTIVE, MODE_PS = 3, 6                      # EnumModeStatus (Kernel/Common/Global.h)
PS_MS, WAKE_MS, INPUT_MS, DBG_MS = 595, 2374, 527, 375
REFRESH_MS = 80     # AWTO_KEY_REFRESH_MS (RL6449_Project.h)
REDRAW_MS = 250     # one redraw of the 6 rows takes ~175 ms in the sim (calibrate: CLOSE); +40 % for the main loop around it
RESET_REDRAW_MS = 250 + 2 * CLOSE_MS  # mode reset can interrupt the first draw: retry interval + two bounded draws
STABLE_MS = KEY_MS  # hold after a match: a late band hit shows one scan later, which a slow pass delays up to the KEY bound
LOOP_MS = 1000      # main-loop rate window: closed vs idle open screen (redraw only on change, so the same rate)
LOOP_MIN = 0.95     # open / closed: the open screen adds a few checks per pass and 4 timer cancels per 80 ms
WORST, WHERE, CUR = {}, {}, ["boot"]      # CUR[0] = the check being run (worst-case attribution)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def model(a0, a1, p3):
    """Expected SDK mask: lo <= R < hi (buttons.md section 2, unit 2 press log #85), POWER = P3.0 low."""
    m = 0
    inb = lambda v, lo, hi: lo <= v < hi
    if inb(a0, 0xC0, 0xE0):
        m |= MENU
    if inb(a0, 0x70, 0x90):
        m |= AUTO
    if inb(a0, 0x28, 0x48):
        m |= UP
    if inb(a1, 0x68, 0x88):
        m |= SOURCE
    if inb(a1, 0x28, 0x48):
        m |= DOWN
    if p3 == 0:
        m |= POWER
    return m


EDGES0 = [0xBF, 0xC0, 0xDF, 0xE0, 0x27, 0x28, 0x47, 0x48, 0x6F, 0x70, 0x8F, 0x90]
EDGES1 = [0x67, 0x68, 0x87, 0x88, 0x27, 0x28, 0x47, 0x48]


class Keys:
    def __init__(self, s):
        self.s, self.m = s, s.bus.m
        self.base = self.m.addr("g_stAwtoKey")
        self.menu_on = self.m.addr("g_ucAwtoMenuOn")
        self.mode_a = s.bus.addr("g_stModeInfo")

    def put(self, a0, a1, p3):
        self.m.wr(0xFF09, bytes([a0]))
        self.m.wr(0xFF0A, bytes([a1]))
        self.m.wr(0xB0, bytes([0xFF if p3 else 0xFE]), "sfr")

    def state(self, log=True):
        b = self.m.rd(self.base, 16 + 16 * 8 if log else 16)
        st = {"open": b[3], "drawn": b[4], "count": b[5], "a0": b[6], "a1": b[7], "p30": b[8], "mask": b[9], "msg": b[10], "flags": b[11], "redraws": b[12],
              "menu": self.m.rd(self.menu_on)[0], "mode": self.m.rd(self.mode_a)[0] & 0x1F}
        if log:
            st["log"] = [dict(seq=e[0], tick=e[1] << 8 | e[2], a0=e[3], a1=e[4], flags=e[5], mask=e[6], msg=e[7])
                         for e in (b[16 + 8 * i:24 + 8 * i] for i in range(16))]
        return st

    def until(self, what, pred, bound_ms, log=False):
        """Poll the key block every POLL_MS sim ms until pred(state); (state, elapsed ms or None on expiry)."""
        t0 = self.s.ms()
        while True:
            st = self.state(log)
            el = self.s.ms() - t0
            if pred(st):
                if el > WORST.get(what, 0.0):
                    WORST[what] = el
                    WHERE[what] = CUR[0]
                return st, el
            if el > bound_ms:
                say(f"  expired: {what} after {el:.0f} ms (bound {bound_ms} ms) state {({k: v for k, v in st.items() if k != 'log'})}")
                return st, None
            self.s.bus.wait(POLL_MS / 1000.0)

    def dwell(self, ms):
        self.s.bus.wait(ms / 1000.0)

    def cmd(self, v):
        d = self.s.diag + 0x28
        for _ in range(4):                                      # 0x35 NAKs while the OSD draws: retry after one KEY bound
            if self.s.bus.write(0x6A, 0x01, bytes([d >> 8])) and self.s.bus.write(0x6A, 0x03, bytes([v])) and \
                    self.s.bus.write(0x6A, 0x3B, bytes([d & 0xFF])):
                return True
            self.dwell(STABLE_MS)
        say(f"  cmd 0x{v:02X}: NAK x4")
        return False

    def press(self, what, a0, a1, want):
        """Hold until the debounced mask == want, then release until mask == 0."""
        self.put(a0, a1, 1)
        st, el = self.until("KEY", lambda s: s["mask"] == want, KEY_MS)
        self.put(*IDLE)
        st2, el2 = self.until("KEY", lambda s: s["mask"] == 0, KEY_MS)
        return el is not None and el2 is not None


FAILS = []


def chk(name, ok, detail=""):
    CUR[0] = "after " + name
    say(f"{'ok  ' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)
    return ok


def osd_en(s):
    """OSD visible: frame enable and the 0x6C[0] overlay port (OsdFuncDisableOsd clears only the port, osd_model #86)"""
    st = s.snap()
    return bool(M.frame_geometry(st)["en"]) and bool(st.ovl[0] & 1)


def until_off(k, what, bound_ms):
    """open == 0 and the OSD off: the close waits for DEN stop (one frame) before it disables the port"""
    st, el = k.until(what, lambda st: st["open"] == 0, bound_ms)
    t0 = k.s.ms()
    while osd_en(k.s):
        if k.s.ms() - t0 > bound_ms:
            say(f"  expired: {what} OSD still on after {k.s.ms() - t0:.0f} ms")
            return st, None
        k.s.bus.wait(POLL_MS / 1000.0)
    if el is not None:
        el += k.s.ms() - t0
        WORST[what] = max(WORST.get(what, 0.0), el)
    return st, el


def check_decode(k):
    cases = [(v, 0xF8, 1) for v in EDGES0] + [(0xF8, v, 1) for v in EDGES1]
    cases += [(*V_MENU, 1), (*V_AUTO, 1), (*V_UP, 1), (*V_SOURCE, 1), (*V_DOWN, 1), (0xF8, 0xF8, 0)]      # every key as read on unit 2, POWER
    cases += [(0x38, 0x80, 1), (0x80, 0x38, 1), (0xD0, 0x80, 1)]       # UP+SOURCE, AUTO+DOWN, MENU+SOURCE: A0 + A1 pairs without an action
    cases += [(0xA0, 0xF8, 1), (0xF8, 0xA0, 1), IDLE]                  # a mixed voltage between two bands matches none
    for a0, a1, p3 in cases:
        if (a0, a1, p3) == (0xF8, 0xF8, 0):
            continue                                            # POWER would power the sim off: decode of P3.0 is checked on the open screen
        want = model(a0, a1, p3)
        k.put(a0, a1, p3)
        st, el = k.until("KEY", lambda s: s["a0"] == a0 and s["a1"] == a1 and s["mask"] == want, KEY_MS)
        k.dwell(STABLE_MS)                                      # an out-of-band value must not hit late
        st = k.state(False)
        chk(f"decode A0={a0:02X} A1={a1:02X} P3.0={p3}", el is not None and st["mask"] == want and st["a0"] == a0 and st["a1"] == a1,
            f"mask {st['mask']:02X} want {want:02X} ({'+'.join(n for b, n in NAMES.items() if want & b) or 'none'}) in "
            f"{'-' if el is None else f'{el:.0f}'} ms, msg {st['msg']:02X} count {st['count']}")
        k.put(*IDLE)
        k.until("KEY", lambda s: s["mask"] == 0, KEY_MS)


def screen_ink(s):
    """ink cell columns of the 6 text rows (map rows 2..7) of the pop-up"""
    return [tuple(c) for c in M.ink_cells(s.snap())[2:8]]


ICON0 = None        # cells < 12 (the pop-up icon) as drawn at open: text that overflows the 24 cell text area wraps into them


def ink_ok(rows):
    """text cells inside 13..34 (one cell of margin each side of the text area 12..35) and the icon area untouched"""
    global ICON0
    icon = [tuple(c for c in r if c < 12) for r in rows]
    if ICON0 is None:
        ICON0 = icon
    return len(rows) == 6 and all(13 <= c <= 34 for r in rows for c in r if c >= 12) and icon == ICON0


def ink_show(rows):
    return "text cells per row " + " ".join(f"{(min(c for c in r if c >= 12), max(r)) if any(c >= 12 for c in r) else '-'}" for r in rows)


def loop_rate(s, ms=LOOP_MS):
    """main-loop passes per sim second over ms (diag heartbeat, u16)"""
    d0 = s.bus.diag()
    s.bus.wait(ms / 1000.0)
    d1 = s.bus.diag()
    return ((d1["hb"] - d0["hb"]) & 0xFFFF) * 1000.0 / max(1, (d1["t2"] - d0["t2"]) & 0xFFFF)


def leave_menu(k):
    for _ in range(6):                                          # menu depth <= page + edit + confirm: MENU backs out one level each
        if k.state(False)["menu"] == 0:
            return True
        k.press("MENU", *V_MENU, MENU)
        k.until("MENU", lambda st: st["menu"] == 0, MENU_MS)
    return k.state(False)["menu"] == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--png-dir", type=Path, default=ROOT / "tmp/osd39")
    ap.add_argument("--skip-decode", action="store_true")
    ap.add_argument("--dump-after-decode", action="store_true", help="print every settings row after the decode stage and stop (A/B of two images)")
    ap.add_argument("--mode-reset-only", action="store_true", help="run only the non-ACTIVE key-screen regression with a call trace")
    ap.add_argument("--calibrate", action="store_true", help="every bound 3000 ms: measure the worst latencies (then set the bounds to 1.25x)")
    a = ap.parse_args()
    if a.calibrate:
        global KEY_MS, DRAW_MS, CLOSE_MS, MENU_MS, CMD_MS, PS_MS, WAKE_MS, INPUT_MS, DBG_MS
        KEY_MS = DRAW_MS = CLOSE_MS = MENU_MS = CMD_MS = PS_MS = WAKE_MS = INPUT_MS = 3000
    say(f"keys_sim {a.bin.name}: bounds KEY {KEY_MS} DRAW {DRAW_MS} CLOSE {CLOSE_MS} MENU {MENU_MS} CMD {CMD_MS} PS {PS_MS} WAKE {WAKE_MS} INPUT {INPUT_MS} ms, poll {POLL_MS} ms")
    s = R.Session(a.bin, a.map, "2160p60")
    try:
        s.boot()
        s.bus.dbg_link_on()                                     # production parks debug for three-port DDC/CI; tests use debug transport
        # fw_sim's legacy helper parks only IIC_1.  The three-port build owns DDC1..3 with IIC_1..3,
        # so park the engine for this simulated host as AwtoDdcciDebugLink() does on hardware.
        ddc_iic = {2: 0xFE86, 3: 0xFE94, 4: 0xFEA3}.get(s.bus.ddc)
        if ddc_iic is not None:
            s.bus.m.wr(ddc_iic, bytes([(s.bus.m.rd(ddc_iic)[0] & 0xF8) | 1]))
        k = Keys(s)
        k.put(*IDLE)
        k.until("KEY", lambda st: st["a0"] == 0xF8 and st["mask"] == 0, KEY_MS)
        if a.mode_reset_only:
            calls = []
            for fn in ("AwtoKeyOsdReset", "AwtoOsdKeyLines", "OsdDispDisableOsd", "OsdFuncDisableOsd", "OsdFuncApplyMap",
                       "ScalerGlobalResetProc", "UserCommonInterfaceOsdResetProc", "UserInterfaceAdjustOsdResetProc"):
                if "_" + fn in k.m.sym:
                    k.m.stub(fn, lambda m, r, fn=fn: calls.append((m.instr, fn)) or None)
            for mode in (0, 1, MODE_PS):
                calls.clear()
                k.cmd(0x42)
                until_off(k, "CLOSE", CLOSE_MS)
                s.bus.m.wr(k.mode_a, bytes([mode]))
                k.cmd(0x41)
                st, el = k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1, CMD_MS + DRAW_MS)
                k.dwell(RESET_REDRAW_MS)
                rows = screen_ink(s)
                chk(f"cmd 0x41 with mode {mode} (not ACTIVE): drawn, rows in the model", el is not None and osd_en(s) and all(rows),
                    f"open={st['open']} drawn={st['drawn']} mode={st['mode']} {ink_show(rows)}")
                say(f"mode {mode} calls " + " ".join(fn for _, fn in calls))
            say("RESULT " + ("PASS" if not FAILS else "FAIL " + ", ".join(FAILS)))
            return int(bool(FAILS))
        if not a.skip_decode:
            check_decode(k)
        chk("decode leaves no menu up", leave_menu(k))
        if a.dump_after_decode:
            import settings_cli as C
            import settings_table as T
            box = C.Box(s.bus, a.map.read_text(errors="replace"), sim=True)
            say("ROWS " + " ".join(f"{r['name']}={box.get_row(r)}" for r in T.ROWS))
            say(f"STATE {k.state(False)} cursor {k.m.rd(k.m.addr('menu_diag') + 4)[0]}")
            return 0
        # 1. open by test cmd (mode may be NOSIGNAL: SOURCE presses in the decode switched inputs)
        r_closed = loop_rate(s)
        rd0 = k.state(False)["redraws"]
        k.cmd(0x41)
        st, el = k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1, CMD_MS + DRAW_MS)
        chk("cmd 0x41 opens, drawn", el is not None, f"open={st['open']} drawn={st['drawn']} mode={st['mode']} in {el} ms")
        k.dwell(REDRAW_MS)
        st, rows = k.state(False), screen_ink(s)
        chk("cmd 0x41: redraws > 0, OSD on, all 6 rows have ink in the model", st["redraws"] != rd0 and osd_en(s) and all(rows),
            f"redraws {rd0} -> {st['redraws']} drawn={st['drawn']} osd_en={osd_en(s)} {ink_show(rows)}")
        k.dwell(2 * 80)                                         # one change redraw after the first draw (AWTO_KEY_REFRESH_MS), then idle
        n0 = k.state(False)["redraws"]
        r_open = loop_rate(s)
        n1 = k.state(False)["redraws"]
        chk("idle open screen: no redraw", n1 == n0, f"{(n1 - n0) & 0xFF} redraws in {LOOP_MS} ms")
        chk("idle open screen keeps the main-loop rate", r_open >= LOOP_MIN * r_closed,
            f"{r_open:.0f}/s open vs {r_closed:.0f}/s closed (min {LOOP_MIN:.0%})")
        # 1b. text fit (unit 2: characters wrapped): every text row's ink stays in the pop-up's text area (cells 12..35), the worst
        # case row (three keys down: one per ladder + POWER) fits, and a shorter text leaves nothing of the longer one behind
        base = screen_ink(s)
        chk("key screen text inside the pop-up text area", ink_ok(base), ink_show(base))
        n0 = k.state(False)["redraws"]
        k.put(V_UP[0], V_SOURCE[1], 0)
        k.until("KEY", lambda st: st["mask"] == UP | SOURCE | POWER, KEY_MS)
        k.until("DRAW", lambda st: st["redraws"] != n0, DRAW_MS + 2 * REFRESH_MS)
        k.dwell(REDRAW_MS)
        worst = screen_ink(s)
        chk("three keys down: the KEY row fits", ink_ok(worst) and len(worst[2]) > len(base[2]), ink_show(worst))
        n0 = k.state(False)["redraws"]
        k.put(*IDLE)
        k.until("KEY", lambda st: st["mask"] == 0, KEY_MS)
        k.until("DRAW", lambda st: st["redraws"] != n0, DRAW_MS + 2 * REFRESH_MS)
        k.dwell(REDRAW_MS)
        after = screen_ink(s)
        chk("shorter text leaves no ghost cells", after[:3] == base[:3], f"rows A0 / A1 / KEY cells now {[len(r) for r in after[:3]]} fresh {[len(r) for r in base[:3]]}")
        # 2. keys while open: real DOWN, POWER (P3.0 low; swallowed, no power toggle), injected UP
        c0 = k.state(False)["count"]
        chk("DOWN press seen", k.press("DOWN", *V_DOWN, DOWN))
        k.put(0xF8, 0xF8, 0)
        st, el = k.until("KEY", lambda st: st["mask"] == POWER and st["p30"] == 0, KEY_MS)
        k.put(*IDLE)
        k.until("KEY", lambda st: st["mask"] == 0, KEY_MS)
        chk("POWER (P3.0 low) decoded while open", el is not None)
        k.cmd(0x02)
        st, el = k.until("CMD", lambda st: (st["count"] - c0) & 0xFF >= 3, CMD_MS, log=True)
        new = [e for e in st["log"] if (e["seq"] - c0) & 0xFF < ((st["count"] - c0) & 0xFF)]
        chk("DOWN logged", any(e["mask"] == DOWN and not e["flags"] & 0x80 for e in new), f"count {st['count']}")
        chk("POWER logged", any(e["mask"] == POWER and not e["flags"] & 0x01 for e in new))
        chk("injected UP logged", any(e["mask"] == 0 and e["msg"] == 1 and e["flags"] & 0x80 for e in new))
        chk("keys swallowed while open", st["open"] == 1, f"mode {st['mode']}")
        a.png_dir.mkdir(parents=True, exist_ok=True)
        R.save(s.snap(), a.png_dir / "keytest.png", "grey", 1)
        for e in st["log"][:st["count"] if st["count"] < 16 else 16]:
            say(f"log seq {e['seq']:3d} tick {e['tick']:5d} A0={e['a0']:02X} A1={e['a1']:02X} flags {e['flags']:02X} mask {e['mask']:02X} msg {e['msg']:02X}")
        # 2b. the debug pop-up (#34) rows, same fit check (held by test cmd 0x26 on top of the closed key screen is not possible: close first)
        k.cmd(0x42)
        until_off(k, "CLOSE", CLOSE_MS)
        k.cmd(0x26)
        t0 = s.ms()
        dbg, prev = None, None
        while s.ms() - t0 < DBG_MS:                              # drawn = the OSD is on and the 5 rows stopped changing for 150 ms
            k.dwell(150)
            dbg = screen_ink(s)
            if osd_en(s) and all(dbg[:5]) and dbg == prev:
                break
            prev = dbg
        WORST["DBG"] = max(WORST.get("DBG", 0.0), s.ms() - t0 - 150)
        chk("debug pop-up text inside the pop-up text area", ink_ok(dbg) and all(dbg[:5]), ink_show(dbg))
        k.cmd(0x27)
        until_off(k, "CLOSE", CLOSE_MS)
        # 2c. keys5 (unit 2): opened while the mode is not ACTIVE the SDK's DP-info branch skipped the draw: open=1 drawn=0 for good,
        # and a second 0x41 did nothing. Now: drawn anyway, and a second 0x41 on an open, undrawn screen draws it.
        for mode in (0, 1, MODE_PS):
            k.cmd(0x42)
            until_off(k, "CLOSE", CLOSE_MS)
            s.bus.m.wr(k.mode_a, bytes([mode]))
            k.cmd(0x41)
            st, el = k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1, CMD_MS + DRAW_MS)
            k.dwell(RESET_REDRAW_MS)
            rows = screen_ink(s)
            chk(f"cmd 0x41 with mode {mode} (not ACTIVE): drawn, rows in the model", el is not None and osd_en(s) and all(rows),
                f"open={st['open']} drawn={st['drawn']} mode={st['mode']} {ink_show(rows)}")
        s.bus.m.wr(k.mode_a, bytes([MODE_ACTIVE]))
        k.cmd(0x41)
        k.dwell(CMD_MS)
        chk("second 0x41 on a drawn screen: still open, drawn", k.state(False)["open"] == 1 and k.state(False)["drawn"] == 1)
        k.cmd(0x42)
        until_off(k, "CLOSE", CLOSE_MS)
        k.cmd(0x41)
        k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1, CMD_MS + DRAW_MS)
        # 3. close by UP+DOWN, let go of UP first (a hand does): the DOWN left down is no press (no LEFT message)
        k.put(V_UP[0], V_DOWN[1], 1)
        k.until("KEY", lambda st: st["mask"] == UP | DOWN, KEY_MS)
        k.put(*V_DOWN, 1)
        st, el = k.until("KEY", lambda st: st["mask"] == DOWN, KEY_MS, log=True)
        k.dwell(STABLE_MS)                                      # the message, if any, is converted in the same pass
        st = k.state()
        last = st["log"][(st["count"] - 1) & 15]
        k.put(*IDLE)
        k.until("KEY", lambda st: st["mask"] == 0, KEY_MS)
        chk("combo release: key left down sends no message", el is not None and last["mask"] == DOWN and last["msg"] == 0xFF,
            f"last log mask {last['mask']:02X} msg {last['msg']:02X}")
        rel_seq = last["seq"]
        st, el = until_off(k, "CLOSE", CLOSE_MS)
        chk("UP+DOWN closes", el is not None, f"open={st['open']} osd_en={osd_en(s)} in {el} ms")
        # 4. open by UP+DOWN from no menu
        k.press("UP+DOWN", V_UP[0], V_DOWN[1], UP | DOWN)
        st, el = k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1, DRAW_MS)
        chk("UP+DOWN opens, drawn", el is not None, f"open={st['open']} drawn={st['drawn']} mode={st['mode']}")
        k.cmd(0x42)
        st, el = until_off(k, "CLOSE", CLOSE_MS)
        chk("cmd 0x42 closes", el is not None, f"in {el} ms")
        # 5. roles (keys6): MENU with no menu does nothing; AUTO opens the #67 menu (message 0); UP / DOWN move the cursor; MENU backs
        # out and closes it (message 3); AUTO again to have the menu up for the key screen
        md = k.m.addr("menu_diag")
        k.press("MENU", *V_MENU, MENU)
        k.dwell(STABLE_MS)
        st = k.state(False)
        chk("MENU with no menu up does nothing", st["menu"] == 0 and st["open"] == 0 and not osd_en(s), f"menu={st['menu']} open={st['open']} osd_en={osd_en(s)}")
        k.press("AUTO", *V_AUTO, AUTO)
        st, el = k.until("MENU", lambda st: st["menu"] == 1, MENU_MS)
        chk("AUTO opens the #67 menu", el is not None and st["msg"] == MSG_AUTO, f"menu={st['menu']} mode={st['mode']} msg {st['msg']:02X}")
        cur = lambda: k.m.rd(md + 4)[0]                         # menu_diag.cursor (menu_cli FIELDS)
        c0 = cur()
        k.press("DOWN", *V_DOWN, DOWN)
        k.dwell(STABLE_MS)
        c1 = cur()
        k.press("UP", *V_UP, UP)
        k.dwell(STABLE_MS)
        chk("DOWN and UP move the cursor", c1 != c0 and cur() == c0, f"cursor {c0} -> {c1} -> {cur()}")
        k.press("MENU", *V_MENU, MENU)
        st, el = k.until("MENU", lambda st: st["menu"] == 0, MENU_MS)
        k.dwell(STABLE_MS)
        chk("MENU backs out and closes the menu", el is not None and k.state(False)["menu"] == 0 and k.state(False)["msg"] == MSG_MENU,
            f"menu={k.state(False)['menu']} msg {k.state(False)['msg']:02X}")
        k.press("AUTO", *V_AUTO, AUTO)
        st, el = k.until("MENU", lambda st: st["menu"] == 1, MENU_MS)
        chk("AUTO opens the #67 menu again", el is not None, f"menu={st['menu']}")
        k.press("UP+DOWN", V_UP[0], V_DOWN[1], UP | DOWN)
        st, el = k.until("DRAW", lambda st: st["open"] == 1 and st["drawn"] == 1 and st["menu"] == 0, DRAW_MS)
        chk("UP+DOWN over the menu opens, drawn, menu closed", el is not None, f"open={st['open']} drawn={st['drawn']} menu={st['menu']}")
        R.save(s.snap(), a.png_dir / "keytest_over_menu.png", "grey", 1)
        k.press("UP+DOWN", V_UP[0], V_DOWN[1], UP | DOWN)
        st, el = until_off(k, "CLOSE", CLOSE_MS)
        k.dwell(STABLE_MS)                                      # nothing reopens the menu afterwards
        st = k.state(False)
        chk("UP+DOWN closes to no menu", el is not None and st["menu"] == 0 and not osd_en(s), f"open={st['open']} menu={st['menu']} osd_en={osd_en(s)}")
        # 5b. MENU + DOWN (A0 + A1, physical MENU kept for the chord) = debug link toggle (#79; also the boot recovery chord): off, then on again
        dl = k.m.addr("g_ucAwtoDbgLink")
        d0 = k.m.rd(dl)[0]
        k.press("MENU+DOWN", V_MENU[0], V_DOWN[1], MENU | DOWN)
        st, el = k.until("CMD", lambda st: k.m.rd(dl)[0] != d0, CMD_MS)
        chk("MENU+DOWN toggles the debug link", el is not None, f"g_ucAwtoDbgLink {d0} -> {k.m.rd(dl)[0]}")
        k.press("MENU+DOWN", V_MENU[0], V_DOWN[1], MENU | DOWN)
        st, el = k.until("CMD", lambda st: (k.m.rd(dl)[0] != 0) == (d0 != 0), CMD_MS)
        chk("MENU+DOWN again toggles it back", el is not None, f"g_ucAwtoDbgLink {k.m.rd(dl)[0]}")
        s.bus.dbg_link_on()                                     # a key-opened link times out after minutes: the sim host wants it unlimited
        st = k.state(False)
        chk("no menu left up by the chord", st["menu"] == 0 and st["open"] == 0, f"menu={st['menu']} open={st['open']}")
        # 6. wake from DDC/CI D6 off (forced power saving, settings row power_mode = Off): POWER, MENU and AUTO wake and are used up (no menu opens)
        import settings_cli as C
        import settings_table as T
        box = C.Box(s.bus, a.map.read_text(errors="replace"), sim=True)
        pm = next(r for r in T.ROWS if r["name"] == "power_mode")
        for what, a0, a1, p3, mask in (("POWER", 0xF8, 0xF8, 0, POWER), ("MENU", *V_MENU, 1, MENU), ("AUTO", *V_AUTO, 1, AUTO)):
            box.set_row(pm, pm["options"].index("Off"))
            st, el = k.until("PS", lambda st: st["mode"] == MODE_PS, PS_MS)
            chk(f"D6 off -> power saving (before {what})", el is not None, f"mode {st['mode']} in {el} ms")
            k.put(a0, a1, p3)
            k.until("KEY", lambda st: st["mask"] == mask, KEY_MS)
            st, el = k.until("WAKE", lambda st: st["mode"] == MODE_ACTIVE, WAKE_MS)
            k.put(*IDLE)
            k.until("KEY", lambda st: st["mask"] == 0, KEY_MS)
            k.dwell(STABLE_MS)
            st = k.state(False)
            chk(f"{what} wakes from D6 off", el is not None and st["mode"] == MODE_ACTIVE and st["menu"] == 0 and st["open"] == 0,
                f"mode {st['mode']} menu={st['menu']} in {el} ms")
        # 7. #67 rows: power delays take any value in range (step = menu increment); input follows every switch path
        for name, v in (("pwr_l2_s", 5), ("pwr_l3_s", 45)):
            r = next(r_ for r_ in T.ROWS if r_["name"] == name)
            got = box.set_row(r, v)
            chk(f"{name} set {v}", got == v and box.get_row(r) == v, f"firmware kept {got}")
        rin = next(r for r in T.ROWS if r["name"] == "input")
        rinfo = next(r for r in T.ROWS if r["name"] == "info_input")
        home = box.get_row(rinfo)
        for tc, want, how in ((0x31, 0, "test cmd 0x31"), (0x32, 1, "test cmd 0x32"), (0x33, 2, "test cmd 0x33"), (0x31 + home, home, "back home")):
            k.cmd(tc)
            t0 = s.ms()
            while True:
                cur, info = box.get_row(rin), box.get_row(rinfo)
                if cur == want and info == want or s.ms() - t0 > INPUT_MS:
                    break
                k.dwell(POLL_MS * 5)
            el = s.ms() - t0
            if el > WORST.get("INPUT", 0.0):
                WORST["INPUT"], WHERE["INPUT"] = el, how
            chk(f"input row follows {how}", cur == want and info == want, f"input {cur} info_input {info} want {want} in {el:.0f} ms")
        # SOURCE (A1) opens the visible four-row selector; opening alone must not switch input.
        osd_width = k.m.addr("g_ucOsdWidth")
        k.press("SOURCE", *V_SOURCE, SOURCE)
        st, el = k.until("MENU", lambda st: k.m.rd(osd_width)[0] == 36 and osd_en(s), MENU_MS)
        chk("SOURCE opens four-row selector", el is not None, f"OSD width {k.m.rd(osd_width)[0]} in {el} ms")
        chk("SOURCE open does not switch input", box.get_row(rinfo) == home, f"info_input stayed {box.get_row(rinfo)} want {home}")
        k.press("MENU", *V_MENU, MENU)                         # physical MENU = Back / cancel
        st, el = k.until("CLOSE", lambda st: not osd_en(s), CLOSE_MS)
        chk("MENU closes source selector", el is not None, f"OSD visible {osd_en(s)}")
        st = k.state()
        e = st["log"][rel_seq & 15]
        chk("combo release entry still has no message", e["seq"] == rel_seq and e["msg"] == 0xFF, f"seq {e['seq']} msg {e['msg']:02X}")
        # 8. the host tool against the sim bus: reads the same block over the 0x35 protocol
        sp = importlib.util.spec_from_file_location("kw", Path(__file__).resolve().parent / "rtd_keywatch.py")
        kw = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(kw)
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            kw.log_mode(["0", "--log", "--map", str(a.map), "--once", "--history"], ROOT, io=s.bus)
        out = buf.getvalue()
        say("rtd_keywatch --log (sim bus):\n" + out)
        chk("rtd_keywatch reads the block", "key block ok" in out and "PRESS #" in out, out.splitlines()[0][26:100] if out else "")
    finally:
        s.bus.close()
    say("worst measured (sim ms): " + ", ".join(f"{k_} {v:.0f} ({WHERE.get(k_, '-')})" for k_, v in sorted(WORST.items())))
    say("RESULT " + ("PASS" if not FAILS else "FAIL " + ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
