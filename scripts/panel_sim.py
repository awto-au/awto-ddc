#!/usr/bin/env python3
"""Panel owner gate (awto-ddc#162 step 2) in fw_sim: one driver of panel VDD, eDP-1 link / stream, backlight pin and PWM.

usage: AWTO_SIM_CORE=fast panel_sim.py BIN MAP [--mode 1080p60] [--tree DIR] [--report]
Scenario (dw8051 core, eDP panel model fw_sim.EdpPanel): cold boot -> ACTIVE; POWER off (test cmd 0x3E) and on after the
panel's T6; signal lost (L1 hold) and back; power saving (target SAVING) and a SOURCE-key wake.
Recorded: every write to the panel VDD pin (FE1A), backlight pins (FE25 / FE2A), backlight PWM4 duty (FF50), and every call of
the DPTx link / stream / PHY functions, each with the firmware's g_ucAwtoPanelOwn (1 = written by the panel machine).
FAIL (gate): a write or call outside the machine after its first step; a firmware 'outside the panel machine' line; a
backlight blink (pin off -> on with no panel-off between); a link training outside a panel bring-up; backlight pin on with VDD
off, or later than BL_AFTER_VDD_MS after a VDD on (Dan 2026-11-13: backlight at once, no T3 wait; registry bl_on_delay default 0);
cold boot: backlight pin later than BL_AFTER_M2PLL_MS after the M2PLL line (D1 03); VDD off sooner than T4 + T5 after backlight off;
VDD on sooner than T6 after VDD off;
#162 s3b: a VDD / backlight pin edge by the machine without its line (OFF -> VDD, * -> T6, backlight pin on (11 C1 / D1) / off
(11 CC)) at the edge's time (+-LINE_SLACK_MS), or such a line without an edge (the lines are the pin record).
--report: print the timeline only (old images have no owner flag; nothing is judged). Log: tmp/logs/panel_sim.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import osd_test as T  # noqa: E402
import sync_log as L  # noqa: E402
import led_check as LED  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/panel_sim.log"
VDD, BL, BL_EN_N, PWM4 = 0xFE1A, 0xFE25, 0xFE2A, 0xFF50      # RL6449_AWTO_JXC4K.h P7.2 / P8.5 / P9.2; Project_Option.h PWM4 duty
DPTX_FNS = ("ScalerDisplayDPTxLinkSequence", "ScalerDisplayDPTxStreamHanlder", "ScalerDisplayDPTxPhyInitial",
            "ScalerDisplayDPTxAnalogPhyConrol", "ScalerDisplayDPTxSSCSet")
POWER_KEY, K_SOURCE = 0x3E, 0x05                             # test cmds (fw/test/testcmd.c): POWER key, injected SOURCE
PWR_OFF, PWR_NORMAL, PWR_SAVING = 1, 2, 3                    # Global.h EnumPowerStatus (isr_g_stPowerInfo high nibble)
MODE_DS, MODE_ACTIVE = 2, 3
# Panel times: registry defaults in fw/sdk/Panel/AWTO_M280DCA_E3B.h (read from --tree when given).
PANEL = {"T4": 250, "T5": 20, "T6": 900}
# Backlight on (Dan 2026-11-13): pin in the same machine step as VDD on (bl_on_delay 0): sim 1-4 ms (VDD line, pin log, PWM
# frequency set) x1.25 = 5 ms.
# Cold boot: request right after pin share + timer-event init, both after the M2PLL switch (SysMainSystemInitial): ~1 ms x5.
BL_AFTER_VDD_MS, BL_AFTER_M2PLL_MS = 5, 5
M2PLL_LINE = (0xD1, 0x03)                                    # sync.tsv 'boot:MCU set up (M2PLL clock, ...)'
# Phase bounds (firmware ms; expiry = FAIL): cold boot to ACTIVE sim ~0.9 s (s2-1) x ~2; power off = T4 + T5 + T6 + flash
# flush, sim worst x1.25 (#54); signal-loss hold: L1 needs one judge run (10 ms slow path) + a pass; settle 1 s.
BOOT_INSTR = 160_000_000
# Wake: SDK auto search after PS_TO_NORMAL = DP dwell 3 s (D1) + HDMI 2 s worst, sim 4.2 s seen (s2-2) x1.25 -> 5.5 s.
OFF_MS, ON_MS, SETTLE_MS, HOLD_MS, PS_MS, WAKE_MS = 1810, 3000, 1000, 1500, 3000, 5500
STEP = 20_000
LINE_SLACK_MS = 3      # pin edge -> its transition line: the line is pushed right after the action (pin, DPTx call), ~1 ms x3
EDGE_LINES = {("VDD pin", 1): (0x01,), ("VDD pin", 0): (0x1B, 0x2B, 0xAB), ("BL pin", 1): (0xC1, 0xC2, 0xD1), ("BL pin", 0): (0xCC,)}


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def panel_times(tree):
    h = Path(tree) / "fw/sdk/Panel/AWTO_M280DCA_E3B.h" if tree else None
    if h and h.is_file():
        for k, v in re.findall(r"#define\s+_PANEL_POWER_(?:ON|OFF)_(T[4-6])\s+(\d+)", h.read_text()):
            if k in PANEL:
                PANEL[k] = int(v)
    return PANEL


class PinWatch(S.Dev):
    """Writes to the backlight pins and PWM4 duty; VDD comes from fw_sim.EdpPanel (one Dev per address)."""

    def __init__(self, run):
        self.run, self.writes = run, (BL, BL_EN_N, PWM4)

    def on_write(self, m, a):
        v = m.rd(a)[0]
        name = {BL: "BL pin", BL_EN_N: "BL_EN_N pin", PWM4: "PWM4 duty"}[a]
        self.run.rec(name, v)


class Run:
    def __init__(self, a):
        self.a, self.fails, self.events, self.phase = a, 0, [], "boot"
        w1c = S.W1C({0xFE69: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, 0xBADC: 0x01})    # wake latches as wake_sim.py: no stale latch
        self.led = LED.LedWatch(self)
        self.bus = S.SimBus(a.bin, a.map, "panel-" + a.bin.stem, None, boot=False, devs=[PinWatch(self), w1c, self.led], video=a.mode)
        self.m = self.bus.m
        mt = self.m.map_text
        self.led_addr = self.m.addr("isr_g_ucAwtoLedMode") if re.search(r"\s_g_ucAwtoLedMode\b", mt) else None
        self.led_table = []
        self.own = self.m.addr("g_ucAwtoPanelOwn") if re.search(r"\s_g_ucAwtoPanelOwn\b", mt) else None
        self.pwr = self.m.addr("isr_g_stPowerInfo")
        self.diag = T.diag_addr(a.map)
        self.ring = L.sym(a.map, "g_stAwtoSync")
        self.rows = L.load_rows(L.tsv_for(a.map))
        self.panel = next(d for d in self.m.devs if type(d).__name__ == "EdpPanel")
        self.panel.listeners.append(lambda m, on: self.rec("VDD pin", int(on)))
        for fn in DPTX_FNS:
            if "_" + fn in self.m.sym:
                self.m.stub(fn, lambda m_, r, fn=fn: self.rec(fn.replace("ScalerDisplayDPTx", "DPTx "), r["r"][7] & 1) and None)
        pre = self.m.sym.get("_ScalerTMDSNormalPreDetect", 0) & 0xFFFF
        self.signal = True
        if pre in self.m.stubs:                      # video_stubs' pre-detect: answer by the signal switch
            b, n, f = self.m.stubs[pre][0]
            self.m.stubs[pre][0] = (b, n, lambda m_, r, f=f: f(m_, r) if self.signal else {"carry": 0})
        self.lines_seen = []
        self.ring_ev = []                            # (id, arg, ms16, value) of every ring entry, by seq
        self.seq = None

    def t(self):
        return self.bus._t2()

    def rec(self, what, val):
        own = self.m.rd(self.own)[0] if self.own is not None else None
        self.events.append((self.t(), self.phase, what, val, own))

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def cmd(self, c):
        addr = self.diag + T.TESTCMD_OFF
        b = self.bus
        return b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))

    def power(self):
        return self.m.rd(self.pwr)[0] >> 4

    def until(self, cond, ms):
        t0 = self.t()
        while self.t() - t0 < ms:
            if cond():
                return True, self.t() - t0
            self.m.run(STEP)
        return cond(), self.t() - t0

    def ring_lines(self, title):
        """ring entries pushed since the last read (by seq, all episodes: a power-off's lines sit in the episode before)"""
        raw = L.read_ring(self.m.rd, self.ring)
        seq, n, wrap = raw[3], raw[12], raw[13]
        last = self.seq if self.seq is not None else (seq - n) % wrap
        k = (seq - last) % wrap
        if k > n:
            self.check(False, f"ring read in time ({title})", f"{k - n} entries overwritten")
            last, k = (seq - n) % wrap, n
        evs = []
        for j in range(k):
            s = (last + j) % wrap
            e = raw[L.HDR + L.EV * (s % n):L.HDR + L.EV * (s % n) + L.EV]
            if e[0]:
                evs.append((e[0], e[1], e[2] << 8 | e[3], int.from_bytes(e[4:8], "big")))
        self.seq = seq
        self.ring_ev += evs
        new = [L.line(self.rows, ev, 0) for ev in evs]
        self.lines_seen += new
        say(f"  ring ({title}): {len(new)} new lines")
        for x in new:
            say(f"    {x}")
        st = next((m.group(1) for x in reversed(self.lines_seen) if (m := re.search(r"system:in .+? for \d+ms->(.+?):", x))), None)
        LED.sample(self.m, self.led, st, self.phase, self.led_addr, self.led_check, self.led_table)
        return new

    def led_check(self, ok, what, detail=""):
        if self.a.report:
            say(f"  {'ok' if ok else 'MISMATCH'} {what}{(': ' + detail) if detail else ''}")
        else:
            self.check(ok, what, detail)

    def stable_detect(self, ok: bool):
        if "_ScalerTMDSStableDetect" in self.m.sym and getattr(self.m, "hle", True):
            self.m.patch_const("ScalerTMDSStableDetect", 1 if ok else 0)

    def scenario(self):
        ok = self.bus.run_until_mode(MODE_ACTIVE, BOOT_INSTR)
        self.check(ok, "cold boot:ACTIVE")
        self.bus.dbg_link_on()
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("cold boot")
        self.phase = "power off"
        self.cmd(POWER_KEY)
        ok, ms = self.until(lambda: self.power() == PWR_OFF, OFF_MS)
        self.check(ok, "POWER key: power OFF", f"{ms} ms")
        self.bus.wait((PANEL["T6"] + 200) / 1000)
        self.ring_lines("power off")
        self.phase = "power on"
        self.cmd(POWER_KEY)
        ok, ms = self.until(lambda: self.bus.mode_state() == MODE_ACTIVE, ON_MS)
        self.check(ok, "POWER key: ACTIVE again", f"{ms} ms")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("power on")
        self.phase = "off in DS"                     # POWER off while display setting asks for video: power-down wins (no ping-pong)
        self.cmd(POWER_KEY)
        self.until(lambda: self.power() == PWR_OFF, OFF_MS)   # T6 runs inside power-down: a press before OFF calls it off
        self.cmd(POWER_KEY)
        ok, _ = self.until(lambda: self.bus.mode_state() == MODE_DS, ON_MS)
        self.check(ok, "POWER on again: DISPLAY SETTING reached")
        self.cmd(POWER_KEY)
        ok, ms = self.until(lambda: self.power() == PWR_OFF, OFF_MS)
        self.check(ok, "POWER key during DISPLAY SETTING: power OFF", f"{ms} ms")
        self.bus.wait((PANEL["T6"] + 200) / 1000)
        self.ring_lines("off in display setting")
        self.phase = "power on 2"
        self.cmd(POWER_KEY)
        ok, ms = self.until(lambda: self.bus.mode_state() == MODE_ACTIVE, ON_MS)
        self.check(ok, "POWER key: ACTIVE again", f"{ms} ms")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("power on 2")
        self.phase = "signal lost"
        self.signal = False
        self.stable_detect(False)
        self.bus.wait(HOLD_MS / 1000)
        self.ring_lines("signal lost")
        self.phase = "signal back"
        self.signal = True
        self.stable_detect(True)
        ok, ms = self.until(lambda: self.bus.mode_state() == MODE_ACTIVE and self.bl_lit(), HOLD_MS)
        self.bus.wait(SETTLE_MS / 1000)
        self.check(ok and self.bus.mode_state() == MODE_ACTIVE, "signal back: ACTIVE, backlight on", f"{ms} ms")
        self.ring_lines("signal back")
        self.phase = "power saving"
        b = self.m.rd(self.pwr)[0]
        self.m.wr(self.pwr, bytes([(b & 0xF0) | PWR_SAVING]))
        ok, ms = self.until(lambda: self.power() == PWR_SAVING, PS_MS)
        self.check(ok, "power saving reached", f"{ms} ms")
        self.bus.wait(0.3)
        self.ring_lines("power saving")
        self.phase = "wake"
        self.cmd(K_SOURCE)
        ok, ms = self.until(lambda: self.bus.mode_state() == MODE_ACTIVE, WAKE_MS)
        self.check(ok, "SOURCE key wake: ACTIVE", f"{ms} ms")
        self.bus.wait(SETTLE_MS / 1000)
        self.ring_lines("wake")

    def bl_lit(self):
        try:
            return self.m.rd(self.m.addr("s_ucPnlBl"))[0] == 2      # AWTO_PNL_BL_LIT
        except S.SimError:
            return True                              # static: not in the map; the ring lines carry it

    def judge(self):
        ev = self.events
        say("  timeline (fw ms, phase, write / call, value, owner flag):")
        for t, ph, w, v, o in ev:
            say(f"    {t:7d} {ph:13s} {w:22s} {v:3d} {'-' if o is None else o}")
        LED.print_table(say, self.led_table)
        LED.judge_lines(self.lines_seen, self.led_check)
        if self.a.report or self.own is None:
            say("  report only (no g_ucAwtoPanelOwn in this image)" if self.own is None else "  report only")
            return
        first = next((i for i, e in enumerate(ev) if e[4] == 1), None)
        outside = [e for e in ev[first or 0:] if e[4] == 0]
        ev = ev[first or 0:]                         # before the machine's first step: boot pin init (ScalerMcuInitial)
        self.check(first is not None and not outside, "every panel pin / PWM write and DPTx call after the machine's first step is the machine's",
                   "; ".join(f"{t} {ph} {w}={v}" for t, ph, w, v, _ in outside[:6]))
        txt = "\n".join(self.lines_seen)
        self.check("outside the panel machine" not in txt, "firmware logged no 'outside the panel machine' line")
        bl = [(t, ph, v) for t, ph, w, v, _ in ev if w == "BL pin"]
        vdd = [(t, ph, v) for t, ph, w, v, _ in ev if w == "VDD pin"]
        blink = [(a, b) for a, b in zip(bl, bl[1:]) if a[2] == 0 and b[2] == 1 and
                 not any(a[0] <= t <= b[0] and v == 0 for t, _, v in vdd) and a[1] == b[1] and a[1] not in ("signal back",)]
        self.check(not blink, "no backlight blink (pin off -> on inside one phase without a panel off)", str(blink[:3]))
        links = [(t, ph) for t, ph, w, v, _ in ev if w == "DPTx LinkSequence"]
        per = {ph: sum(1 for _, p in links if p == ph) for ph in ("boot", "power on", "power on 2", "signal lost", "signal back", "wake")}
        self.check(per["boot"] == 1 and per["power on"] == 1 and per["power on 2"] == 1 and per["signal lost"] == 0 and per["signal back"] == 0 and per["wake"] <= 1,
                   "eDP link trained once per panel bring-up (none at display setting, none in the L1 hold)", str(per))
        blon = [t for t, ph, v in bl if v == 1]
        vdd_all = [(t, v) for t, _, w, v, _ in self.events if w == "VDD pin"]   # incl. GPIO init (VDD default on)
        lvl = lambda t: next((v for tv, v in reversed(vdd_all) if tv <= t), 0)
        self.check(blon and all(lvl(t) == 1 for t in blon), "backlight pin on only with VDD on", str([t for t in blon if lvl(t) != 1][:4]))
        late = []                                    # every VDD on (a bring-up, backlight wanted in every phase here): pin follows at once
        for tv, ph, v in vdd:
            if v == 1:
                b = next((t for t in blon if t >= tv), None)
                if b is None or b - tv > BL_AFTER_VDD_MS:
                    late.append(f"{ph} VDD@{tv} -> BL {'never' if b is None else f'+{b - tv}'}")
        self.check(not late, f"backlight pin on <= {BL_AFTER_VDD_MS} ms after each VDD on (no T3 wait)", "; ".join(late[:4]))
        self.m2pll_check()
        offs = []                                    # backlight off -> the VDD off that follows with no backlight on between
        for x in (x for x in bl if x[2] == 0):
            v = next((y for y in vdd if y[0] >= x[0] and y[2] == 0), None)
            if v and not any(x[0] < t < v[0] and val == 1 for t, _, val in bl):
                offs.append((x[0], v[0]))
        self.check(all(v - b >= PANEL["T4"] + PANEL["T5"] for b, v in offs), f"VDD off >= T4 + T5 ({PANEL['T4'] + PANEL['T5']} ms) after backlight off",
                   str([f"{v - b} (@{b})" for b, v in offs]))
        t6 = [(b[0] - a[0]) for a, b in zip(vdd, vdd[1:]) if a[2] == 0 and b[2] == 1]
        self.check(all(x >= PANEL["T6"] for x in t6), f"VDD on >= T6 ({PANEL['T6']} ms) after VDD off", str(t6))
        self.edge_lines(self.events)                 # all writes: boot pin init gives the level before the first edge

    def m2pll_check(self):
        """cold boot:the first backlight pin-on line within BL_AFTER_M2PLL_MS of the M2PLL line (ring ms, same clock)"""
        m = next((ms for i, a, ms, _ in self.ring_ev if (i, a) == M2PLL_LINE), None)
        b = next((ms for i, a, ms, _ in self.ring_ev if i == 0x11 and a in EDGE_LINES[("BL pin", 1)]), None)
        d = None if m is None or b is None else ((b - m) & 0xFFFF)
        self.check(d is not None and d <= BL_AFTER_M2PLL_MS, f"cold boot:backlight pin <= {BL_AFTER_M2PLL_MS} ms after the M2PLL switch line",
                   f"M2PLL @{m}, backlight pin @{b}, {d} ms")

    def edge_lines(self, ev):
        """#162 s3b: the machine's transition lines are the pin record: one line per machine pin edge, at the edge's time"""
        edges, last = [], {"VDD pin": 0, "BL pin": 0}     # reset level: both pins low (off)
        for t, ph, w, v, own in ev:
            if w in ("VDD pin", "BL pin"):
                if last[w] != v and own == 1:
                    edges.append((t, w, v))
                last[w] = v
        off = (self.bus.diag_t2() - self.t()) & 0xFFFF   # event times count from the sim's first read; ring ms = usT2Isr
        edges = [((te + off) & 0xFFFF, w, v) for te, w, v in edges]
        t_first = edges[0][0] if edges else 0
        lines = [(ms, a) for i, a, ms, _ in self.ring_ev if i == 0x11 and any(a in x for x in EDGE_LINES.values())]
        miss, used = [], set()
        for t, w, v in edges:
            k = next((j for j, (ms, a) in enumerate(lines) if j not in used and a in EDGE_LINES[(w, v)] and
                      abs((((ms - t) + 0x8000) & 0xFFFF) - 0x8000) <= LINE_SLACK_MS), None)
            if k is None:
                miss.append(f"{w}={v}@{t}")
            else:
                used.add(k)
        extra = [f"11 {a:02X}@{ms}" for j, (ms, a) in enumerate(lines) if j not in used and ((ms - t_first) & 0xFFFF) < 0x8000]
        self.check(edges and not miss, f"every machine pin edge has its transition line within {LINE_SLACK_MS} ms "
                   f"({len(edges)} edges)", "missing: " + ", ".join(miss[:6]))
        self.check(not extra, "no pin transition line without a pin edge", ", ".join(extra[:6]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--tree", help="worktree: panel T-values from fw/sdk/Panel/AWTO_M280DCA_E3B.h")
    ap.add_argument("--report", action="store_true", help="timeline only, no verdict (old images)")
    a = ap.parse_args()
    panel_times(a.tree)
    say(f"panel_sim {a.bin.name} (panel {PANEL})")
    r = Run(a)
    try:
        r.scenario()
        r.judge()
    finally:
        r.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} panel_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
