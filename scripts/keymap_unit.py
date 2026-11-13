#!/usr/bin/env python3
"""Front-key map (awto-ddc#132) on unit 2: every row of docs/keys.md with injected keys, state read back over the debug slave.

usage: keymap_unit.py MAP            (MAP = tmp/fw/<image>.map of the image on unit 2; unit 2 only, bus 11)
- Keys: test cmd 0x01..0x05 (AUTO UP DOWN MENU SOURCE, same route as a front key); UP+DOWN: menu mailbox HOLD (key_hold mask).
- Read: OSD state (g_stOsdInfo.usOsdState via the diag offset), menu_diag, console flags, backlight (g_stOSDUserData), mode,
  power; the sync ring (sync_log.py) for the request lines.
- Not here: UP+DOWN in power saving (debug slave silent in power saving; wake_sim covers it).
- Ends with the input back on D2 fixed (settings_cli set input 1 = D2 HDMI) and the debug link off.
Log: tmp/logs/keymap_unit.log
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "tmp/logs/keymap_unit.log"
BUS, SERIAL, UNIT = 11, "AWT26110002", 2        # unit 2 (scripts/devices.json); units 1 / 3 are hands off
TESTCMD_OFF, OSD_OFS = 0x28, 44                 # g_stAwtoDiag: test cmd byte, offset of usOsdState in g_stOsdInfo
K_AUTO, K_UP, K_DOWN, K_MENU, K_SOURCE = 1, 2, 3, 4, 5      # test cmd = key message + 1
KM_UP, KM_DOWN = 0x04, 0x08                     # RL6449_Project.h AWTO_KM_UP / AWTO_KM_DOWN (key_hold mask)
MODE_ACTIVE = 3
# One injected key: queued, routed by the next AwtoKeyPoll (one main pass, ~3 ms at 323 passes/s) + its OSD draw (selector
# ~175 ms in the sim, #139) = 0.2 s; x1.25 -> 0.25 s, then the state is read. A late draw shows as a FAIL naming the row.
KEY_S = 0.25
IDLE_COMMIT_S = 2.0 * 1.25                      # AWTO_SRC_IDLE_COMMIT_MS 2 s x1.25: then the selector must be closed
SEARCH_S = 5.0                                  # auto search -> ACTIVE: HDMI search + display setting ~1 s, DP search 3 s worst x1.25


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(*a, limit=60):
    r = subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, cwd=ROOT, timeout=limit)
    return r.stdout + r.stderr


class Unit:
    def __init__(self, mp):
        import i2cbus
        import settings_cli as C
        from rtd_i2c_bridge import Real
        i2cbus.require_unit(BUS, SERIAL)
        self.mp, self.mt = mp, mp.read_text(errors="replace")
        self.io = Real(BUS, allow_write=True)
        self.box = C.Box(self.io, self.mt)
        x = lambda n: C.xaddr(self.mt, n)                       # noqa: E731
        self.diag, self.osdi, self.md = x("g_stAwtoDiag"), x("g_stOsdInfo"), x("menu_diag")
        self.gpio, self.key_a, self.ud = x("g_stAwtoGpio"), x("g_stAwtoKey"), x("g_stOSDUserData")
        self.mode_a, self.pwr_a, self.menu_on = x("g_stModeInfo"), x("g_stPowerInfo"), x("g_ucAwtoMenuOn")
        self.fails = 0

    def rd(self, a, n=1):
        return self.box.xrd(a, n)

    def key(self, k, settle=KEY_S):
        a = self.diag + TESTCMD_OFF
        self.box.xwr(a, bytes([k]))
        t0 = time.monotonic()
        while self.rd(a)[0] != 0 and time.monotonic() - t0 < KEY_S:
            pass                                                # the test byte is cleared when the firmware takes it
        time.sleep(settle)

    def hold(self, mask, ms):
        self.box.call(3, 8, (ms // 50) << 5 | mask)            # menu.h MO_HOLD: key_hold(mask, ms)

    def osd(self):
        ofs = self.rd(self.diag + OSD_OFS)[0]
        b = self.rd(self.osdi + ofs, 2)
        return b[0] << 8 | b[1]

    def menu(self):
        b = self.rd(self.md, 8)
        return {"open": b[2], "page": b[3], "cursor": b[4], "item": b[5], "mode": b[7]}

    def console(self):
        return self.rd(self.gpio + 3)[0] | self.rd(self.key_a + 3)[0]

    def backlight(self):
        b = self.rd(self.ud, 2)
        return b[0] << 8 | b[1]

    def mode(self):
        return self.rd(self.mode_a)[0] & 0x1F

    def power(self):
        return self.rd(self.pwr_a)[0] >> 4

    def check(self, what, ok, detail=""):
        say(f"{'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def ring(self, whole=False):
        return run("scripts/sync_log.py", BUS, "--serial", SERIAL, "--map", self.mp, *(["--whole"] if whole else []), limit=30)

    def until(self, f, limit_s):
        t0 = time.monotonic()
        while time.monotonic() - t0 < limit_s:
            if f():
                return time.monotonic() - t0
            time.sleep(0.1)
        return None


def nothing_open(u):
    for _ in range(3):
        if u.osd() == 0 and u.menu()["open"] == 0 and u.console() == 0:
            return True
        if u.console():
            u.key(K_MENU)
        elif u.menu()["open"]:
            u.key(K_SOURCE)
        else:
            u.key(K_MENU)
    return u.osd() == 0 and u.menu()["open"] == 0 and u.console() == 0


def rows(u):
    u.check("start: ACTIVE, nothing open", u.mode() == MODE_ACTIVE and nothing_open(u), f"mode {u.mode()} osd {u.osd()}")
    u.key(K_MENU)
    u.check("nothing open: MENU opens the awto menu", u.menu()["open"] == 1, str(u.menu()))
    u.key(K_AUTO)
    m = u.menu()
    u.check("menu: AUTO enters (sub-page)", m["open"] == 1 and m["page"] != 0xFE, str(m))
    u.key(K_DOWN)
    u.check("menu: DOWN moves", u.menu()["cursor"] != m["cursor"], str(u.menu()))
    u.key(K_MENU)
    u.check("menu: MENU backs out to the main list", u.menu()["page"] == 0xFE and u.menu()["open"] == 1, str(u.menu()))
    u.key(K_AUTO)
    u.key(K_SOURCE)
    u.check("menu: SOURCE closes it from a sub-page, no selector", u.menu()["open"] == 0 and u.osd() == 0, f"{u.menu()} osd {u.osd()}")
    u.key(K_MENU)
    run("scripts/menu_cli.py", "--bus", BUS, "--serial", SERIAL, "--map", u.mp, "open", "picture", limit=30)
    run("scripts/menu_cli.py", "--bus", BUS, "--serial", SERIAL, "--map", u.mp, "select", "sharpness", limit=30)
    m0 = u.menu()
    u.key(K_AUTO)
    m1 = u.menu()
    u.check("menu: inert row (sharpness): AUTO does not enter edit", m1["open"] == 1 and m1["mode"] == 0 and m1["item"] == m0["item"],
            f"{m0} -> {m1}")
    u.key(K_SOURCE)

    b0 = u.backlight()
    u.key(K_UP)
    bar = u.osd()
    b1 = u.backlight()
    u.check("nothing open, ACTIVE: UP opens the backlight bar, value up", bar != 0 and b1 > b0, f"osd {bar}, backlight {b0} -> {b1}")
    u.key(K_DOWN)
    u.key(K_DOWN)
    b2 = u.backlight()
    u.check("bar: DOWN x2 value down", b2 < b1 and u.osd() == bar, f"backlight {b1} -> {b2}")
    u.key(K_UP)
    u.check("bar: back to the start value", u.backlight() == b0, f"{u.backlight()} (start {b0})")
    u.key(K_MENU)
    u.check("bar: MENU closes it and opens the menu", u.osd() == 0 and u.menu()["open"] == 1, f"osd {u.osd()} {u.menu()}")
    u.key(K_SOURCE)

    u.key(K_SOURCE)
    sel = u.osd()
    u.check("nothing open: SOURCE opens the selector", sel != 0 and sel != bar, f"osd {sel}")
    time.sleep(IDLE_COMMIT_S)
    u.check(f"selector: open without a step stays ({IDLE_COMMIT_S} s)", u.osd() == sel)
    u.key(K_SOURCE)
    u.key(K_SOURCE)
    u.key(K_SOURCE)
    u.key(K_SOURCE)                                             # 4 items (Auto, D1, D2, D3): back on D2
    u.check("selector: SOURCE steps (4 steps wrap), still open", u.osd() == sel)
    u.key(K_UP)
    u.key(K_DOWN)
    time.sleep(IDLE_COMMIT_S)
    u.check("selector: idle commit on the current input closes it, picture kept", u.osd() == 0 and u.mode() == MODE_ACTIVE,
            f"osd {u.osd()} mode {u.mode()}")
    u.key(K_SOURCE)
    u.key(K_UP)
    u.key(K_MENU)
    u.check("selector: MENU cancels (closed, picture kept)", u.osd() == 0 and u.mode() == MODE_ACTIVE)
    u.key(K_SOURCE)
    u.key(K_AUTO)
    u.check("selector: AUTO takes the current input at once (closes)", u.osd() == 0 and u.mode() == MODE_ACTIVE)

    u.hold(KM_UP | KM_DOWN, 300)
    time.sleep(0.6)
    u.check("UP+DOWN (key_hold) opens the console", u.console() != 0, f"console {u.console()}")
    u.key(K_AUTO)
    u.key(K_UP)
    u.check("console main page: AUTO / UP do nothing", u.console() != 0 and u.menu()["open"] == 0)
    u.key(K_MENU)
    u.check("console main page: MENU closes it", u.console() == 0)

    u.key(K_AUTO, settle=0.5)
    t = u.until(lambda: u.mode() == MODE_ACTIVE, SEARCH_S)
    txt = u.ring()
    req = [ln for ln in txt.splitlines() if "AUTO key:auto source select" in ln]
    u.check("nothing open: AUTO = auto source select, picture back", t is not None and bool(req),
            f"ACTIVE after {t} s; {req[-1].strip() if req else 'no request line'}")
    say("  ring after AUTO:\n" + "\n".join("    " + ln for ln in txt.splitlines()[-12:]))

    say("SKIP power saving + UP+DOWN: the debug slave does not answer in power saving (no injection path) and a live D2 source "
        "wakes the unit by itself; covered by wake_sim, physical press on the unit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    a = ap.parse_args()
    import dbg_link
    say(f"keymap_unit {a.map.name} on unit {UNIT} (bus {BUS})")
    dbg_link.on(BUS, 10)
    u = Unit(a.map)
    try:
        rows(u)
        nothing_open(u)
    finally:
        u.io.close()
        out = run("scripts/settings_cli.py", "--bus", BUS, "--serial", SERIAL, "--map", a.map, "set", "input", "1", limit=60)
        say(f"  input back to D2 fixed: {out.strip().splitlines()[-1] if out.strip() else 'no output'}")
        dbg_link.off(BUS)
        say("  debug link off")
    say(f"{'PASS' if u.fails == 0 else 'FAIL'} keymap_unit: {u.fails} failed")
    return 1 if u.fails else 0


if __name__ == "__main__":
    sys.exit(main())
