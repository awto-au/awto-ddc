#!/usr/bin/env python3
"""OSD transparency on unit 2 (awto-ddc#176): open every awto screen with injected keys, read the blend registers back.

usage: osdt_unit.py MAP [--pct 50] [--leave-menu]   (MAP = tmp/fw/<image>.map of the image on unit 2; unit 2 only, bus 11)
- Sets osd_transparency to --pct through the settings mailbox (NVRAM through the gate), then per screen (awto menu, selector,
  backlight bar, info card, console, GPIO page): alpha_blending_level (OVERLAY_CTRL[4:2] = bits 7:5, OVERLAY_CTRL1[7:3] =
  bits 4:0) and alpha_blend_type (FRAME_CTRL_0A[3:2]); want level = pct x 255 / 100, type 3 (windows + character background).
- Live check: with the menu open, pct x 2 then back; the level must follow without a reopen.
- --leave-menu: osd_timeout 0 (never) and the awto menu left open for a look (visual-checks-persistent); debug link off.
Register addresses by regdb name (re/regdb). Keys / reads: keymap_unit.Unit. Log: tmp/logs/osdt_unit.log
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import keymap_unit as K  # noqa: E402
import regdb_query as Q  # noqa: E402
import settings_cli as C  # noqa: E402

LOG = ROOT / "tmp/logs/osdt_unit.log"
CHIP = "RTD2795T-CG"
TC_CLEAR, TC_CONSOLE, TC_GPIO, TC_GPIO_CLOSE, TC_INFO = 0x27, 0x20, 0x43, 0x44, 0x55   # fw/sdcc/awto_testcmd.inc
TYPE_WIN_CHAR_BG = 3                            # FRAME_CTRL_0A alpha_blend_type 11 (01 showed nothing: backgrounds are char cells)
OVERLAY_PORT_EN = 0x01                          # OVERLAY_CTRL overlay_port_en: the OSD is on screen
# screen shown (overlay_port_en) after the key: console open = map clear + font load, the longest; 1.2 s if unmeasured x1.25.
# On expiry: FAIL naming the screen. The measured time is logged per screen (tmp/logs/osdt_unit.log).
SHOW_LIMIT_S = 1.5


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def reg_addr(rows, name):
    a = {int(r["address"], 0) for r in rows if r["register"] == name and r["kind"] == "REG" and not r["port_idx"]}
    if len(a) != 1:
        raise SystemExit(f"regdb {CHIP}: register {name} -> {sorted(a)}")
    return a.pop()


def pct_level(p):
    return p * 255 // 100                       # AwtoSetIds.h AWTO_PCT_TO_255


class Blend:
    def __init__(self, u):
        rows = Q.load(CHIP)
        self.u = u
        self.a = {n: reg_addr(rows, n) for n in ("OVERLAY_CTRL", "OVERLAY_CTRL1", "FRAME_CTRL_0A")}

    def read(self):
        r = {n: self.u.rd(a)[0] for n, a in self.a.items()}
        level = (r["OVERLAY_CTRL"] >> 2 & 7) << 5 | r["OVERLAY_CTRL1"] >> 3
        typ = r["FRAME_CTRL_0A"] >> 2 & 3
        raw = " ".join(f"{n} 0x{a:04X}=0x{r[n]:02X}" for n, a in self.a.items())
        return level, typ, raw


def screen(u, b, name, want, open_fn):
    u.key(TC_CLEAR)                             # holds first: a held card blocks the closing paths
    K.nothing_open(u)
    open_fn()
    t = u.until(lambda: u.rd(b.a["OVERLAY_CTRL"])[0] & OVERLAY_PORT_EN, SHOW_LIMIT_S)
    osd = u.osd()
    level, typ, raw = b.read()
    u.check(f"{name}: shown {'NOT' if t is None else f'after {t:.2f} s'}, OSD state 0x{osd:04X}, level {level}/256, type {typ}",
            t is not None and level == want and typ == TYPE_WIN_CHAR_BG, f"want level {want}, type {TYPE_WIN_CHAR_BG}; {raw}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    ap.add_argument("--pct", type=int, default=50)
    ap.add_argument("--leave-menu", action="store_true")
    a = ap.parse_args()
    import dbg_link
    say(f"osdt_unit {a.map.name} on unit {K.UNIT} (bus {K.BUS}), osd_transparency {a.pct} %")
    dbg_link.on(K.BUS, 10)
    u = K.Unit(a.map)
    b = Blend(u)
    tr = C.row_of("osd_transparency")
    want = pct_level(a.pct)
    try:
        old = u.box.get_row(tr)
        got = u.box.set_row(tr, a.pct)
        say(f"osd_transparency {old} -> {got} % (mailbox; stored through the NVRAM gate)")
        screen(u, b, "awto menu", want, lambda: u.key(K.K_MENU))
        hi = min(2 * a.pct, 100)
        u.box.set_row(tr, hi)
        lv, _, raw = b.read()
        u.check(f"live: menu open, {hi} % -> level {lv}", lv == pct_level(hi), raw)
        u.box.set_row(tr, a.pct)
        lv, _, raw = b.read()
        u.check(f"live: back to {a.pct} % -> level {lv}", lv == want, raw)
        screen(u, b, "selector", want, lambda: u.key(K.K_SOURCE))
        screen(u, b, "backlight bar", want, lambda: (u.key(K.K_UP), u.key(K.K_DOWN)))   # UP then DOWN: value unchanged
        screen(u, b, "info card", want, lambda: u.key(TC_INFO))
        screen(u, b, "console", want, lambda: u.key(TC_CONSOLE))
        screen(u, b, "GPIO page", want, lambda: u.key(TC_GPIO))
        u.key(TC_GPIO_CLOSE)
        u.key(TC_CLEAR)
        K.nothing_open(u)
        if a.leave_menu:
            to = C.row_of("osd_timeout")
            say(f"osd_timeout {u.box.get_row(to)} -> {u.box.set_row(to, 0)} s (0 = never): the menu stays open")
            u.key(K.K_MENU)
            level, typ, raw = b.read()
            u.check(f"menu left open: OSD state 0x{u.osd():04X}, menu {u.menu()}, level {level}, type {typ}",
                    level == want and typ == TYPE_WIN_CHAR_BG, raw)
    finally:
        u.io.close()
        dbg_link.off(K.BUS)
        say("debug link off")
    say(f"{'PASS' if u.fails == 0 else 'FAIL'} osdt_unit: {u.fails} failed")
    return 1 if u.fails else 0


if __name__ == "__main__":
    sys.exit(main())
