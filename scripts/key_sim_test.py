#!/usr/bin/env python3
"""Front-key path test in fw_sim (awto-ddc#129, key map #132): physical presses through the ADC result cells, injected keys through the test cmd.

usage: AWTO_SIM_CORE=fast key_sim_test.py BIN MAP [--mode 1080p60] [--shots DIR]
- Boots to ACTIVE (HDMI D2), then per screen (docs/keys.md):
  - nothing open, picture: UP / DOWN = backlight bar (value up / down, held key repeats, bar closes on the OSD timeout, value
    stored by the NVRAM gate); no info pop-up; MENU = awto menu; AUTO = auto source select (request by the AUTO key, picture back).
  - selector: SOURCE opens it and steps forward, UP forward, DOWN back (wrap, no repeat); AUTO takes, MENU cancels; the
    highlighted input is taken after AWTO_SRC_IDLE_COMMIT_MS without a key (every step restarts it); no OSD timeout (#139).
  - awto menu: AUTO = enter (menu_key 0), DOWN moves, held DOWN repeats at the rate limit, MENU = back / close.
  - console: UP+DOWN opens (no single-key leak); main page only MENU / POWER act; GPIO page DOWN scrolls + repeats.
  - injected test cmd keys (0x01..0x05 = AUTO UP DOWN MENU SOURCE) under the same rules; MENU+DOWN no combo; POWER off / on.
- Physical key = ADC_A0 (0xFF09) / ADC_A1 (0xFF0A) cell value in a fw/awto/inputs.tsv band; idle = regdb reset 0xF8; POWER = P3.0 low.
- Actions are counted with call watches (fw_sim Machine.watch): the assertions name the function that must / must not run.
- --shots DIR: PNG renders of the screens (menu, inert row, backlight bar, selector, auto select result).
Log: tmp/logs/key_sim_test.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/key_sim_test.log"
A0, A1, IDLE = 0xFF09, 0xFF0A, 0xF8
KEY_ADC = {"MENU": (A0, 0xD0), "AUTO": (A0, 0x80), "UP": (A0, 0x38), "SOURCE": (A1, 0x80), "DOWN": (A1, 0x38)}   # band centres
WATCH = ("AwtoKeyNoOsd", "OsdDispOsdMessage", "AwtoSourceOpen", "AwtoSourceRows", "AwtoSrcSet", "AwtoSourceKey", "AwtoSourceStep",
         "menu_open", "menu_key", "AwtoKeyTestSet", "AwtoConScroll", "SysPowerSetTargetPowerStatus", "SysMachineRequest",
         "AwtoPsField", "AwtoSrcPortFields", "AwtoBlKey", "AwtoSourceIdle", "AwtoSourceAuto", "AwtoNvWrite", "AwtoSaveCard")
PWR = "SysPowerSetTargetPowerStatus"             # power requests: counted from SysMachineRequest (#162 step 3) when the image has it
REPEAT_MS, RATE_MS = 500, 100                    # RL6449_Project.h AWTO_KEY_REPEAT_MS / AWTO_KEY_RATE_MS


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class Keys:
    def __init__(self, s):
        self.s, self.m = s, s.bus.m
        self.hits = {}
        self.args = {}
        self.who = []
        self.shots = None
        for n in WATCH:
            if "_" + n in self.m.sym:                           # older images lack the #134 names: those checks then fail
                self.m.stub(n, self._watch(n))
        mt = s.mapp.read_text(errors="replace")
        self.diag = T.diag_addr(s.mapp)
        self.osd = T.osdinfo_addr(s.mapp)
        self.menu_on = self.m.addr("g_ucAwtoMenuOn")
        self.gpio = self.m.addr("g_stAwtoGpio")
        self.key = self.m.addr("g_stAwtoKey")
        self.osd_w = self.m.addr("g_ucOsdWidth")
        self.fails = 0
        self.mt = mt

    def _watch(self, n):
        def f(m, r):
            a = r["a1"] & 0xFF
            if n == "SysMachineRequest":             # #162 step 3: the one request entry; power targets are < 0x10
                self.who.append((a, r["a2"] & 0xFF))            # (request, who): AWTO_SYS_BY_* of the request line
                if a >= 0x10:
                    return None
                n2 = PWR
            else:
                n2 = n
            self.hits[n2] = self.hits.get(n2, 0) + 1
            self.args.setdefault(n2, []).append(a)
            return None
        return f

    def wait(self, ms):
        self.s.bus.wait(ms / 1000.0)

    def adc(self, a0=IDLE, a1=IDLE):
        self.m.wr(A0, bytes([a0]))
        self.m.wr(A1, bytes([a1]))

    def down(self, *keys):
        v = {A0: IDLE, A1: IDLE}
        for k in keys:
            a, x = KEY_ADC[k]
            v[a] = x
        self.adc(v[A0], v[A1])

    def tap(self, *keys, ms=150, gap=300):
        self.down(*keys)
        self.wait(ms)
        self.adc()
        self.wait(gap)

    def power(self, pressed):
        p3 = self.m.rd(0xB0, 1, "sfr")[0]
        self.m.wr(0xB0, bytes([(p3 & 0xFE) | (0 if pressed else 1)]), "sfr")

    def cmd(self, c):
        a = self.diag + T.TESTCMD_OFF
        bus = self.s.bus
        ok = (bus.write(0x6A, 0x01, bytes([a >> 8])) and bus.write(0x6A, 0x03, bytes([c])) and bus.write(0x6A, 0x3B, bytes([a & 0xFF])))
        self.wait(300)
        return ok

    def osd_state(self):
        ofs = self.m.rd(self.diag + 44)[0]
        b = self.m.rd(self.osd + ofs, 2)
        return b[0] << 8 | b[1]

    def menu(self):
        return self.m.rd(self.menu_on)[0]

    def console(self):
        return self.m.rd(self.gpio + 3)[0] | self.m.rd(self.key + 3)[0]

    def osd_on(self):
        return self.m.rd(self.osd_w)[0] != 0                    # the map width is 0 once the OSD is closed (the enable bit stays)

    def n(self, name):
        return self.hits.get(name, 0)

    def snap(self):
        return dict(self.hits)

    def delta(self, before, name):
        return self.hits.get(name, 0) - before.get(name, 0)

    def shot(self, name):
        if self.shots is not None:
            path = self.shots / f"{name}.png"
            R.render_snap(self.s.snap(), "grey", 2).save(path)
            say(f"  png {path}")

    def backlight(self):
        b = self.m.rd(self.m.addr("g_stOSDUserData"), 2)            # StructOSDUserDataType.usBackLight (first field, SDK raw 30..255)
        return b[0] << 8 | b[1]

    def check(self, what, ok, detail=""):
        say(f"{'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1


SRC_COLS = 46               # awto_osdcard.inc AWTO_SRC_COLS (#139: per-port status lines)
OSD_TIMEOUT_S = 30          # an SDK OSD timeout > 10 s (RTD2014Key: <= 10 = never); registry osd_timeout default is 30
OSD_TIMEOUT_OFF = 4         # StructOSDUserDataType.ucOsdTimeout (RTD2014NVRamOsd.h: usBackLight, ucOsdHPos, ucOsdVPos first)
SDK_PSAVE_S = 3 + 2         # SDK no-signal way in: power-saving card after 3 s, power saving 2 s later (RTD2014Osd.c)


def stay_open(k):
    """#139: an open selector without a step closes only on a choice or a cancel (no OSD timeout, no stale bar timeout, no 3 s sleep)."""
    to = k.m.addr("g_stOSDUserData") + OSD_TIMEOUT_OFF
    old = k.m.rd(to)[0]
    k.m.wr(to, bytes([OSD_TIMEOUT_S]))                          # SDK OSD timeout armed (sim NVRAM default is <= 10 s = never)
    k.tap("SOURCE")
    sel = k.osd_state()
    k.wait((OSD_TIMEOUT_S + 5) * 1000)
    k.check(f"selector: still open {OSD_TIMEOUT_S + 5} s after the last key (no OSD timeout)", sel != 0 and k.osd_state() == sel,
            f"osd state {k.osd_state()} (open {sel})")
    k.tap("MENU")
    k.tap("DOWN")                                               # backlight bar: arms the OSD timeout close
    k.tap("SOURCE")                                             # closes the bar, opens the selector
    k.wait((OSD_TIMEOUT_S + 2) * 1000)
    k.check("selector: the bar's pending close does not close a selector opened after it", k.osd_state() == sel,
            f"osd state {k.osd_state()}")
    k.tap("MENU")
    b = k.snap()
    k.cmd(0x17)                                                 # OSD event 7, the no-signal way in
    k.wait((SDK_PSAVE_S + 2) * 1000)
    k.check(f"selector (no-signal way in, picture on): open after {SDK_PSAVE_S + 2} s, no power saving",
            k.osd_state() == sel and k.delta(b, "SysPowerSetTargetPowerStatus") == 0,
            f"osd state {k.osd_state()}, power requests {k.delta(b, 'SysPowerSetTargetPowerStatus')}")
    k.tap("MENU")
    k.check("selector: MENU closes it", k.osd_state() == 0)
    k.m.wr(to, bytes([old]))


D3_CABLE = 0xFE2C            # D3 cable-detect pin (fw_sim CABLE, board header bD3_CONNECT), low = cable


def status_rows(k):
    """#139: the selector's port fields are polled; only a changed value is redrawn (field update)."""
    k.tap("SOURCE")
    k.wait(1500)
    b = k.snap()
    k.wait(1500)                                                # >= 5 polls (AWTO_SRC_POLL_MS 250) with nothing changing
    k.check("selector status: polled, nothing redrawn while nothing changes",
            k.delta(b, "AwtoSrcPortFields") >= 4 and k.delta(b, "AwtoPsField") == 0,
            f"port polls {k.delta(b, 'AwtoSrcPortFields')}, signal fields drawn {k.delta(b, 'AwtoPsField')}")
    old = k.m.rd(D3_CABLE)[0]
    b = k.snap()
    k.m.wr(D3_CABLE, bytes([old ^ 1]))                          # D3 cable pin flips: its 5V field (and later cbl) change
    k.wait(800)
    k.check("selector status: a D3 cable-pin change redraws its fields only", 1 <= k.delta(b, "AwtoPsField") <= 4,
            f"signal fields drawn {k.delta(b, 'AwtoPsField')}")
    k.m.wr(D3_CABLE, bytes([old]))
    k.wait(800)
    k.tap("MENU")


SRC_IDLE_MS = 2000          # RL6449_Project.h AWTO_SRC_IDLE_COMMIT_MS (#132)
OSD_TIMEOUT_BAR_S = 11      # smallest SDK OSD timeout that closes (<= 10 = never)
SYS_BY_KEY_AUTO, SYS_BY_SELECTOR, SYS_BY_SELECTOR_IDLE = 0x1C, 0x06, 0x1E    # RL6449_Project.h AWTO_SYS_BY_*
REQ_SEARCH = 0x10 | 0x01    # AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH


def backlight_bar(k, sel):
    """#132: UP / DOWN with a picture and nothing open = backlight bar; repeat; OSD timeout close; NVRAM gate write."""
    bar = sel + 1                                               # _MENU_HOTKEY_BACKLIGHT follows _MENU_HOTKEY_SOURCE
    to = k.m.addr("g_stOSDUserData") + OSD_TIMEOUT_OFF
    old = k.m.rd(to)[0]
    k.m.wr(to, bytes([OSD_TIMEOUT_BAR_S]))
    v0 = k.backlight()
    b = k.snap()
    k.tap("UP")
    v1 = k.backlight()
    k.check("no OSD: UP -> backlight bar open, value up", k.osd_state() == bar and k.osd_on() and k.delta(b, "AwtoBlKey") == 1 and v1 > v0
            and k.delta(b, "OsdDispOsdMessage") == 0, f"osd state {k.osd_state()} (bar {bar}), backlight {v0} -> {v1}")
    k.shot("backlight_bar")
    b = k.snap()
    k.tap("DOWN")
    k.tap("DOWN")
    v2 = k.backlight()
    k.check("bar: DOWN x2 -> value down, no info pop-up", k.delta(b, "AwtoBlKey") == 2 and v2 < v1 and k.delta(b, "OsdDispOsdMessage") == 0,
            f"backlight {v1} -> {v2}")
    b = k.snap()
    hold = 1500
    k.down("UP")
    k.wait(hold)
    k.adc()
    k.wait(300)
    want = 1 + (hold - REPEAT_MS) // RATE_MS
    got = k.delta(b, "AwtoBlKey")
    k.check(f"bar: UP held {hold} ms -> about {want} steps (repeat)", want - 3 <= got <= want + 2, f"{got}, backlight {k.backlight()}")
    k.shot("backlight_bar_held")
    b = k.snap()
    k.wait((OSD_TIMEOUT_BAR_S + 1) * 1000)
    k.check(f"bar: closed by the OSD timeout ({OSD_TIMEOUT_BAR_S} s)", k.osd_state() == 0 and not k.osd_on(), f"osd state {k.osd_state()}")
    k.wait(4000)                                                # gate: ACTIVE 3 s stable, written within AWTO_NV_SAVE_MS of the last change
    k.check("bar: value written by the NVRAM gate", k.delta(b, "AwtoNvWrite") + k.n("AwtoNvWrite") >= 1,
            f"gate writes {k.n('AwtoNvWrite')}, saving cards {k.n('AwtoSaveCard')}")
    b = k.snap()
    k.tap("UP")
    k.tap("SOURCE")                                             # another key closes the bar, then acts as with nothing open
    k.check("bar: SOURCE closes it and opens the selector", k.osd_state() == sel and k.delta(b, "AwtoSourceOpen") == 1, f"osd {k.osd_state()}")
    k.tap("MENU")
    k.m.wr(to, bytes([old]))


def selector(k):
    b = k.snap()                                                # SOURCE = selector; SOURCE / UP / DOWN step, no repeat
    k.tap("SOURCE")
    sel = k.osd_state()
    w = k.m.rd(k.osd_w)[0]
    k.check(f"SOURCE -> selector on the text layer ({SRC_COLS}-cell rows drawn)", k.delta(b, "AwtoSourceOpen") == 1 and sel != 0 and w == SRC_COLS
            and k.delta(b, "AwtoSourceRows") == 1, f"osd state {sel}, map width {w}, rows drawn {k.delta(b, 'AwtoSourceRows')}")
    k.shot("selector_open")
    n_items = 4                                                 # Auto + D1 DP, D2 HDMI 1, D3 HDMI 2 (fw/sdk Pcb)
    b = k.snap()
    rows = []
    for _ in range(n_items):
        k.tap("SOURCE", ms=100, gap=150)                        # steps 250 ms apart: inside the idle commit
        rows.append(k.args.get("AwtoSrcSet", [None])[-1])
    k.check(f"selector: {n_items} SOURCE steps visit every item once and wrap, rows redrawn each step",
            sorted(rows) == list(range(n_items)) and rows[0] == (rows[-1] + 1) % n_items and k.delta(b, "AwtoSourceRows") == n_items
            and k.osd_state() == sel, f"rows {rows}, redraws {k.delta(b, 'AwtoSourceRows')}")
    b = k.snap()
    k.tap("UP", ms=100, gap=150)
    k.tap("DOWN", ms=100, gap=150)
    back = k.args.get("AwtoSrcSet", [None])[-1]
    k.check("selector: UP steps forward, DOWN back", k.delta(b, "AwtoSourceStep") == 2 and back == rows[-1], f"row {back} after {rows[-1]}")
    b = k.snap()
    k.down("DOWN")
    k.wait(1200)
    k.adc()
    k.wait(150)
    k.check("selector: held DOWN steps once (no repeat)", k.delta(b, "AwtoSourceStep") == 1, f"steps {k.delta(b, 'AwtoSourceStep')}")
    k.tap("MENU")
    k.check("selector: MENU cancels (closed, no request)", k.osd_state() == 0 and not any(w in (SYS_BY_SELECTOR, SYS_BY_SELECTOR_IDLE) for _, w in k.who))
    b = k.snap()                                                # idle commit: steps back to the current input -> closes, no switch
    k.tap("SOURCE")
    k.tap("SOURCE", ms=100, gap=150)
    k.tap("DOWN", ms=100, gap=SRC_IDLE_MS - 600)
    k.check(f"selector: still open {SRC_IDLE_MS - 600 + 100} ms after the last step", k.osd_state() == sel and k.delta(b, "AwtoSourceIdle") == 0)
    k.tap("UP", ms=100, gap=SRC_IDLE_MS - 600)
    k.check("selector: a step restarts the idle wait", k.osd_state() == sel and k.delta(b, "AwtoSourceIdle") == 0)
    k.tap("DOWN", ms=100, gap=SRC_IDLE_MS + 400)
    k.check(f"selector: idle commit after {SRC_IDLE_MS} ms (current input highlighted: closes, no switch)",
            k.delta(b, "AwtoSourceIdle") == 1 and k.osd_state() == 0 and k.delta(b, PWR) == 0
            and not any(r == REQ_SEARCH for r, _ in k.who[len(k.who) - 3:]), f"idle {k.delta(b, 'AwtoSourceIdle')}, osd {k.osd_state()}")
    b = k.snap()                                                # opening alone arms no idle commit (#139 stays)
    k.tap("SOURCE")
    k.wait(SRC_IDLE_MS + 1000)
    k.check("selector: open without a step stays (no idle commit)", k.osd_state() == sel and k.delta(b, "AwtoSourceIdle") == 0)
    b = k.snap()
    k.down("AUTO")
    k.wait(40)                                                  # debounce 20 ms < 40 ms < the 80 ms UP / DOWN combo window
    k.check("selector: AUTO acts at once (no combo wait): takes the current input = closes", k.delta(b, "AwtoSourceKey") == 1
            and k.osd_state() == 0, f"osd state {k.osd_state()}")
    k.adc()
    k.wait(300)
    return sel


def auto_select(k, how):
    """#132: AUTO with nothing open = auto source select through SysMachineRequest (who = AUTO key); the search finds D2 again."""
    b = k.snap()
    n0 = len(k.who)
    if how == "front":
        k.tap("AUTO")
    else:
        k.cmd(0x01)
    req = k.who[n0:]
    k.check(f"{how} AUTO, nothing open -> auto source select (request by the AUTO key)", k.delta(b, "AwtoSourceAuto") == 1
            and (REQ_SEARCH, SYS_BY_KEY_AUTO) in req and k.menu() == 0 and k.delta(b, "menu_open") == 0, f"requests {req}")
    t0 = k.s.ms()
    while k.s.bus.mode_state() != 3 and k.s.ms() - t0 < 8000:
        k.wait(200)
    k.check(f"{how} AUTO: picture back after the auto search", k.s.bus.mode_state() == 3, f"mode {k.s.bus.mode_state()} after {k.s.ms() - t0:.0f} ms")
    k.wait(1500)


def run(k):
    s = k.s
    k.wait(1000)                                                # main loop is blocked ~150 ms after ACTIVE (pop-up, panel on): a press then is not sampled
    gi =[k.m.rd(k.gpio + 16 + i)[0] for i in range(44)]        # StAwtoGpio.ucIn starts at byte 16
    keys = {n: gi[i] for n, i in (("SOURCE", 39), ("MENU", 40), ("DOWN", 41), ("UP", 42), ("AUTO", 43), ("POWER", 11))}
    k.check("idle: no key decoded", not any(keys.values()), str(keys))
    k.check("idle: no OSD, menu, console", k.osd_state() == 0 and k.menu() == 0 and k.console() == 0,
            f"osd {k.osd_state()} menu {k.menu()} console {k.console()}")

    sel = selector(k)
    backlight_bar(k, sel)
    stay_open(k)
    status_rows(k)

    b = k.snap()                                                # awto menu: MENU opens, AUTO enters, keys go to menu_key, repeat rate-limited
    k.tap("MENU")
    k.check("MENU -> awto menu", k.delta(b, "menu_open") == 1 and k.menu() == 1, f"menu {k.menu()}")
    k.shot("menu_open")
    b = k.snap()
    k.tap("DOWN")
    k.check("menu: DOWN -> menu_key(2)", k.delta(b, "menu_key") == 1 and k.args["menu_key"][-1] == 2, str(k.args.get("menu_key", [])[-3:]))
    b = k.snap()
    k.tap("AUTO")
    k.check("menu: AUTO -> menu_key(0) (enter, roles kept)", k.delta(b, "menu_key") == 1 and k.args["menu_key"][-1] == 0 and k.menu() == 1,
            str(k.args.get("menu_key", [])[-3:]))
    k.shot("menu_page")
    b = k.snap()
    hold = 1500
    k.down("DOWN")
    k.wait(hold)
    k.adc()
    k.wait(300)
    want = 1 + (hold - REPEAT_MS) // RATE_MS
    got = k.delta(b, "menu_key")
    k.check(f"menu: DOWN held {hold} ms -> about {want} keys (repeat {REPEAT_MS} ms, then every {RATE_MS} ms)", want - 3 <= got <= want + 2, f"{got}")
    b = k.snap()
    k.tap("SOURCE")
    k.check("menu: SOURCE closes it from a sub-page (no selector)", k.delta(b, "menu_key") == 0 and k.delta(b, "AwtoSourceOpen") == 0
            and k.menu() == 0 and k.osd_state() == 0, f"menu {k.menu()} osd {k.osd_state()}")
    k.tap("MENU")
    k.tap("AUTO")
    for _ in range(4):
        if k.menu() == 0:
            break
        k.tap("MENU")
    k.check("menu: MENU backs out and closes", k.menu() == 0)

    b = k.snap()                                                # UP + DOWN combo: console, no single-key leak
    k.down("UP")
    k.wait(30)
    k.down("UP", "DOWN")
    k.wait(300)
    k.adc()
    k.wait(500)
    k.check("UP+DOWN -> console open", k.delta(b, "AwtoKeyTestSet") == 1 and k.console() != 0, f"console {k.console()}")
    k.check("UP+DOWN: no UP / DOWN action leaked", k.delta(b, "AwtoBlKey") == 0 and k.delta(b, "AwtoSourceOpen") == 0
            and k.delta(b, "AwtoConScroll") == 0, str({n: k.delta(b, n) for n in ("AwtoBlKey", "AwtoSourceOpen", "AwtoConScroll")}))
    b = k.snap()                                                # main page = terminal: only MENU / POWER act (Dan, 2026-11-12)
    for key in ("DOWN", "UP", "AUTO", "SOURCE"):
        k.tap(key)
    k.check("console main page: DOWN / UP / AUTO / SOURCE do nothing", k.console() != 0 and k.delta(b, "menu_open") == 0
            and k.delta(b, "AwtoSourceOpen") == 0 and k.menu() == 0 and k.delta(b, "AwtoBlKey") == 0 and k.delta(b, "AwtoSourceAuto") == 0,
            f"console {k.console()}")
    b = k.snap()
    k.cmd(0x02)                                                 # injected keys follow the same page rules
    k.check("console main page: injected UP does nothing", k.console() != 0 and k.delta(b, "AwtoBlKey") == 0)
    k.cmd(0x04)
    k.check("console main page: injected MENU closes it", k.console() == 0 and k.menu() == 0, f"console {k.console()} menu {k.menu()}")
    b = k.snap()
    k.cmd(0x43)                                                 # GPIO (key test) page: UP / DOWN scroll, the rest swallowed
    k.tap("DOWN")
    k.check("console GPIO page: DOWN scrolls once", k.delta(b, "AwtoConScroll") == 1, f"{k.delta(b, 'AwtoConScroll')}")
    b = k.snap()
    k.down("UP")
    k.wait(hold)
    k.adc()
    k.wait(300)
    got = k.delta(b, "AwtoConScroll")
    k.check(f"console GPIO page: UP held {hold} ms -> about {want} scrolls", want - 3 <= got <= want + 2, f"{got}")
    b = k.snap()
    k.tap("AUTO")
    k.tap("SOURCE")
    k.check("console GPIO page: AUTO / SOURCE swallowed", k.console() != 0 and k.delta(b, "menu_open") == 0
            and k.delta(b, "AwtoSourceOpen") == 0 and k.menu() == 0 and k.delta(b, "AwtoSourceAuto") == 0, f"console {k.console()}")
    b = k.snap()
    k.tap("UP", "DOWN", ms=300)
    k.check("UP+DOWN -> console closed, no scroll", k.console() == 0 and k.delta(b, "AwtoConScroll") == 0, f"console {k.console()}")

    b = k.snap()                                                # injected keys (test cmd 0x01..0x05 = messages 0..4)
    k.cmd(0x04)
    k.check("injected MENU -> menu", k.delta(b, "menu_open") == 1 and k.menu() == 1)
    for _ in range(4):
        if k.menu() == 0:
            break
        k.cmd(0x04)
    k.check("injected MENU closes the menu", k.menu() == 0)
    b = k.snap()
    k.cmd(0x05)
    k.check("injected SOURCE -> selector", k.delta(b, "AwtoSourceOpen") == 1 and k.osd_state() != 0)
    k.cmd(0x05)
    k.cmd(0x02)
    k.check("injected SOURCE / UP step the selector", k.delta(b, "AwtoSourceStep") == 2)
    k.cmd(0x04)
    k.check("injected MENU cancels the selector", k.osd_state() == 0)
    b = k.snap()
    k.cmd(0x03)
    k.check("injected DOWN -> backlight bar", k.delta(b, "AwtoBlKey") == 1 and k.osd_state() == sel + 1)
    k.cmd(0x05)
    k.tap("MENU")

    auto_select(k, "front")
    k.shot("auto_select_result")
    auto_select(k, "injected")

    dbg = k.m.addr("g_ucAwtoDbgLink")
    link0 = k.m.rd(dbg)[0]
    b = k.snap()                                                # MENU + DOWN: no combo any more; the debug link is not toggled
    k.down("DOWN")
    k.wait(30)
    k.down("MENU", "DOWN")
    k.wait(300)
    k.adc()
    k.wait(300)
    k.check("MENU+DOWN: no debug link (DOWN acts alone, as the waiting key)", k.m.rd(dbg)[0] == link0)
    for _ in range(4):
        if k.osd_state() == 0 and k.menu() == 0:
            break
        k.tap("MENU")
    s.bus.dbg_link_on()

    b = k.snap()                                                # POWER: off, then on
    k.power(True)
    k.wait(150)
    k.power(False)
    k.wait(500)
    a = k.args.get("SysPowerSetTargetPowerStatus", [])[-1:] if k.delta(b, "SysPowerSetTargetPowerStatus") else []
    k.check("POWER -> power off requested", bool(a), f"SysPowerSetTargetPowerStatus args {a}")
    k.power(True)
    k.wait(150)
    k.power(False)
    k.wait(1500)
    a2 = k.args.get("SysPowerSetTargetPowerStatus", [])[-1:]
    k.check("POWER again -> power on requested", k.delta(b, "SysPowerSetTargetPowerStatus") >= 2 and a2 != a, f"args {k.args.get('SysPowerSetTargetPowerStatus', [])[-4:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--shots", type=Path, help="write PNG renders of the screens here")
    a = ap.parse_args()
    say(f"key_sim_test {a.bin.name}")
    s = R.Session(a.bin, a.map, a.mode)
    s.boot()
    k = Keys(s)
    if a.shots:
        a.shots.mkdir(parents=True, exist_ok=True)
        k.shots = a.shots
    try:
        run(k)
    finally:
        s.bus.close()
    say(f"{'PASS' if k.fails == 0 else 'FAIL'} key_sim_test {a.bin.name}: {k.fails} failed")
    return 1 if k.fails else 0


if __name__ == "__main__":
    sys.exit(main())
