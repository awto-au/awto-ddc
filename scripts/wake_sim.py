#!/usr/bin/env python3
"""#144 task 4 in fw_sim: wake from power saving on source events (cable plug, EDID read, DP AUX command, DPCD 600h = D0).

usage: AWTO_SIM_CORE=fast wake_sim.py BIN MAP [--mode 1080p60] [--out tmp/boot]
- Boot to ACTIVE on D2, switch to D3 (test cmd 0x33: fixed port, no source), force power saving (g_stPowerInfo target).
- Each step forces power saving again, injects one event, and checks wake / no wake within the bound:
  D2 unplug (wake, "D2 cable unplugged: wake", #138 task 6), D2 plug (wake, "D2 cable plugged in: wake"), sleep with every
  cable in (no wake: no edge), unplug / plug again in the same episode (suppressed, once per direction),
  D2 EDID read latch (wake), the same latch again (no wake, "wake suppressed"), DP AUX rx latch (wake), DPCD 600h = D0 (wake).
- PS wake-poll period (g_usAwtoPsPolls over 500 ms, longest gap g_usAwtoPsGap) against AWTO_PS_POLL_MS.
- TMDS clock (#144 q7): on D3 without a cable (no wake), on D2 (wake after the AWTO_PS_TMDS_HOLD_MS hold, "D2 wake by TMDS
  clock"), still on after re-sleep (wakes again: the hold is the gate), 15 ms bursts every 50 ms for 1 s (no wake, burst line).
- Measured: edge -> wake line (fw ms), wake line -> console drawn / backlight on (ring), PS main-loop pass time.
- Sim devices: W1C on the latches (DDCn_EDID_IRQ bit0, AUX_IRQ_STATUS bit0), cable pins (low = cable), DPCD port memory,
  FreqDet (HDMI freq detector P71 / P72, off until the TMDS cases).
PNG: <out>/wake_cable_console.png (console after the cable wake). Log: tmp/logs/wake_sim.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import fw_sim as S  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402
import rtd_crash as C  # noqa: E402
import sync_log as L  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/wake_sim.log"
PWR_NORMAL, PWR_SAVING, MODE_NOSIGNAL = 2, 3, 5     # Global.h EnumPowerStatus, MODE_NAMES
D2_PIN, DDC_D2, AUX_RX1, DPCD_600 = 0xFE32, 0xFE69, 0xBADC, 0x000600
PS_POLL_MS = 5          # RL6449_Project.h AWTO_PS_POLL_MS
IOSC_KHZ = 28_000       # freq-detect reference in power saving (_INTERNAL_OSC_XTAL)
# Event -> wake line (firmware ms). Cable: detection every AWTO_SLOW_MS 10 ms + SDK 10 ms debounce re-read + 1 PS pass
# (8 ms worst, measured below) = 28 ms, x1.25 -> 35 ms. Latches / DPCD: 1 PS pass 8 ms + this test's sample step 2 ms
# + 1 ms tick = 11 ms, x1.25 -> 13 ms. Over = FAIL.
BOUND_CABLE_MS, BOUND_LATCH_MS = 35, 13
# TMDS: clock up after the last restart -> unstable latched -> restart -> stable 2 polls later (2 x (5 + 2) + 2 + 1 = 17 ms),
# + hold AWTO_PS_TMDS_HOLD_MS 50 + the poll that sees it (5 + 2 + 1) = 75 ms, x1.25 -> 94 ms.
BOUND_TMDS_MS = 94
BURST_ON_MS, BURST_PERIOD_MS = 15, 50   # host-like TMDS bursts (#144): shorter than the hold, must not wake
# Poll gap: AWTO_PS_POLL_MS 5 + one PS pass (2 ms worst, measured below) + 1 ms tick = 8 ms, x1.25 -> 10 ms. Over = FAIL.
BOUND_POLL_GAP_MS = 10
POLL_WINDOW_MS = 500    # PS poll period sample: 100 polls at 5 ms
QUIET_MS = 1000         # no-wake checks: 1 s = 50x the latch bound; a wake would show well inside it
SLEEP_SETTLE_MS = 300   # after the forced power saving: power-down switch done, wake triggers armed
STEP = 20_000           # instructions per sample (~0.3-1 ms of fw time)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class FreqDet(S.Dev):
    """HDMI freq detector of P71 (D2) / P72 (D3) in power saving (regdb HDMI_FREQDET_CTRL E6, ERROR_TH EF, result ED/EE):
    off until on(); then per port clock_khz (None = no clock). Started (E6[7]) without a clock: done, unstable latched (count 0
    is under the lower bound), no_clock. A clock that comes up keeps the latched unstable until its W1C (a restart), after
    which done, stable latched, result = count. W1C: E6[2], EF[6]."""

    def __init__(self):
        self.on, self.clk = False, {0x71: None, 0x72: None}
        self.writes = tuple(p << 8 | r for p in (0x71, 0x72) for r in (0xE6, 0xEF))
        self.last = {}

    def on_write(self, m, a):
        if not self.on:
            return
        p, r = a >> 8, a & 0xFF
        v = m.rd(a)[0]
        if r == 0xE6 and v & 0x04:
            self.last[p] = "unstable-clear"
        if r == 0xEF and v & 0x40:
            self.last[p] = "stable-clear"
        self.update(m, p, w1c_e6=r == 0xE6 and bool(v & 0x04), w1c_ef=r == 0xEF and bool(v & 0x40))

    def update(self, m, p, w1c_e6=False, w1c_ef=False):
        b = p << 8
        e6, ef = m.rd(b | 0xE6)[0], m.rd(b | 0xEF)[0]
        if w1c_e6:
            e6 &= ~0x04
        if w1c_ef:
            ef &= ~0x40
        khz = self.clk[p]
        if e6 & 0x80:                                    # started
            e6 |= 0x40
            if khz is None:
                e6 |= 0x04; ef = (ef & ~0x40) | 0x20
            else:
                ef &= ~0x20
                if not e6 & 0x04:
                    ef |= 0x40
                n = int(khz * 1000 / IOSC_KHZ)           # F6[1:0] 0 (1000 reference cycles), E7[6] 0 (no divider)
                m.put(f"set memory xram 0x{b | 0xED:x} 0x{(n >> 8) & 0xFF:x}")
                m.put(f"set memory xram 0x{b | 0xEE:x} 0x{n & 0xFF:x}")
        m.put(f"set memory xram 0x{b | 0xE6:x} 0x{e6 & 0xFF:x}")
        m.put(f"set memory xram 0x{b | 0xEF:x} 0x{ef & 0xFF:x}")
        m.flush()

    def set_clock(self, m, p, khz):
        self.on, self.clk[p] = True, khz
        for q in (0x71, 0x72):
            m.put(f"set memory xram 0x{q << 8 | 0xF6:x} 0x0")
            m.put(f"set memory xram 0x{q << 8 | 0xE7:x} 0x0")
            self.update(m, q)


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.model = M.OsdModel()
        self.model.img = a.bin.read_bytes()
        w1c = S.W1C({DDC_D2: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, AUX_RX1: 0x01})
        self.fd = FreqDet()
        self.bus = S.SimBus(a.bin, a.map, "wake-" + a.bin.stem, None, boot=False, devs=[self.model, w1c, self.fd], video=a.mode)
        self.m = self.bus.m
        self.diag = T.diag_addr(a.map)
        self.pwr = self.m.addr("g_stPowerInfo")
        self.ring = L.sym(a.map, "g_stAwtoSync")
        self.rows = L.load_rows(L.tsv_for(a.map))
        self.gpio = self.m.addr("g_stAwtoGpio")
        self.dpcd = next(d for d in self.m.devs if type(d).__name__ == "IndPort")
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        self.caddr = C.map_addr(a.map.read_text(errors="replace"))
        self.pass_ms = []
        if a.trace:
            for fn in ("AwtoPsWakeFire",):
                self.m.stub(fn, lambda m_, r, fn=fn: say(f"    trace call {fn} r7 {r['r'][7]:02x} r5 {r['r'][5]:02x}") and None)

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def t2(self):
        return self.bus.diag_t2()

    def power(self):
        return self.m.rd(self.pwr)[0] >> 4          # SDCC bit-fields from bit 0: b4PowerAction low nibble, b4PowerStatus high

    def cmd(self, c, wait=0.3):
        addr = self.diag + T.TESTCMD_OFF
        b = self.bus
        b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))
        b.wait(wait)

    def ring_events(self):
        """[(id, arg, abs ms, value)] of the ring in seq order (sync_log layout)."""
        raw = self.m.rd(self.ring, L.HDR + L.N * L.EV)
        seq = raw[3]
        out = []
        for k in range(L.N):
            s = (seq - L.N + k) % L.WRAP
            e = raw[L.HDR + L.EV * (s % L.N):L.HDR + L.EV * (s % L.N) + L.EV]
            if e[0]:
                out.append((e[0], e[1], e[2] << 8 | e[3], int.from_bytes(e[4:8], "big")))
        return out

    def lines(self):
        return L.decode(self.m.rd(self.ring, L.HDR + L.N * L.EV), self.rows)[1]

    def sleep(self):
        """Force power saving (target = SAVING) and let it settle; returns the PS pass time (ms, diag heartbeat)."""
        b = self.m.rd(self.pwr)[0]
        self.m.wr(self.pwr, bytes([(b & 0xF0) | PWR_SAVING]))
        t0 = self.t2()
        while self.power() != PWR_SAVING and (self.t2() - t0) & 0xFFFF < 2000:
            self.m.run(STEP)
        ok = self.power() == PWR_SAVING
        self.bus.wait(SLEEP_SETTLE_MS / 1000.0)
        hb0, t1 = self.bus.diag()["hb"], self.t2()
        self.bus.wait(0.1)
        n = (self.bus.diag()["hb"] - hb0) & 0xFFFF
        if n:
            self.pass_ms.append(((self.t2() - t1) & 0xFFFF) / n)
        return ok

    def until_wake(self, limit_ms):
        """Run until power status NORMAL or target NORMAL; (woke, ms since the call)."""
        t0 = self.t2()
        while (self.t2() - t0) & 0xFFFF < limit_ms:
            b = self.m.rd(self.pwr)[0]
            if (b >> 4) == PWR_NORMAL or (b & 0x0F) == PWR_NORMAL:
                return True, (self.t2() - t0) & 0xFFFF
            self.m.run(STEP)
        return False, (self.t2() - t0) & 0xFFFF

    def watch(self, ms):
        """Run ms of fw time; log (power, mode, OSD grid, OSD on) changes when --trace."""
        w, h, t0, last = self.m.addr("g_ucOsdWidth"), self.m.addr("g_ucOsdHeight"), self.t2(), None
        while (self.t2() - t0) & 0xFFFF < ms:
            self.m.run(STEP)
            if self.a.trace:
                st = (self.power(), self.bus.mode_state(), self.m.rd(w)[0], self.m.rd(h)[0], self.m.rd(self.gpio + 3)[0],
                      M.summary(self.model.snapshot(self.m, 0.0))["en"])
                if st != last:
                    say(f"    trace +{(self.t2() - t0) & 0xFFFF} ms: power {st[0]} mode {st[1]} grid {st[2]}x{st[3]} console {st[4]} osd {st[5]}")
                    last = st

    def poll_period(self):
        """#144: the wake poll in power saving runs every AWTO_PS_POLL_MS (counter + longest gap, test readouts)."""
        if not re.search(r"\s_g_usAwtoPsGap\b", self.m.map_text):     # XDATA symbol: in the map, not in m.sym (code)
            say("  SKIP poll period: image without g_usAwtoPsGap (pre-tmds image)")
            return
        self.check(self.sleep(), "poll period: power saving reached")
        pa, ga = self.m.addr("g_usAwtoPsPolls"), self.m.addr("g_usAwtoPsGap")
        n0, t0 = int.from_bytes(self.m.rd(pa, 2), "big"), self.t2()
        self.bus.wait(POLL_WINDOW_MS / 1000.0)
        n1, t1 = int.from_bytes(self.m.rd(pa, 2), "big"), self.t2()
        gap, ms = int.from_bytes(self.m.rd(ga, 2), "big"), (t1 - t0) & 0xFFFF
        per = ms / (n1 - n0) if n1 > n0 else None
        say(f"  measured, power-saving wake poll: {n1 - n0} polls in {ms} ms (period {per and round(per, 2)} ms), "
            f"longest gap {gap} ms since power saving")
        self.check(per is not None and PS_POLL_MS <= per <= BOUND_POLL_GAP_MS, f"poll period {PS_POLL_MS}..{BOUND_POLL_GAP_MS} ms",
                   f"{per and round(per, 2)} ms")
        self.check(gap <= BOUND_POLL_GAP_MS, f"longest poll gap <= {BOUND_POLL_GAP_MS} ms", f"{gap} ms")

    def wake_case(self, name, inject, want, bound):
        ok = self.sleep()
        self.check(ok, f"{name}: power saving reached")
        t_inj = self.t2()
        inject()
        if self.a.trace:
            say(f"    trace after inject: BADC {self.m.rd(AUX_RX1)[0]:02x} B7DC {self.m.rd(0xB7DC)[0]:02x} FE69 {self.m.rd(DDC_D2)[0]:02x}")
        woke, ms = self.until_wake(QUIET_MS if want is None else max(bound * 4, 50))
        if want is None:
            self.check(not woke, f"{name}: no wake within {QUIET_MS} ms", f"woke after {ms} ms" if woke else "")
            if woke:
                self.bus.wait(0.5)
                for ln in self.lines()[-8:]:
                    say(f"    {ln}")
            return None
        self.check(woke, f"{name}: woke (power target / status NORMAL)", f"seen after {ms} ms (test sampling)" if woke else "no wake")
        self.watch(1500)                            # console + panel on, search: the ring has the follow-up lines
        ev = self.ring_events()
        hit = [e for e in ev if e[0] in (0xCB, 0xCC, 0xCD, 0xCE, 0xD3, 0xDC)]
        lat = ((hit[-1][2] - t_inj) & 0xFFFF) if hit else None
        self.check(lat is not None and lat <= bound, f"{name}: event -> wake (firmware wake line) within {bound} ms", f"{lat} ms")
        txt = "\n".join(self.lines())
        self.check(want in txt, f"{name}: log line '{want}'")
        for ln in self.lines()[-12:]:
            say(f"    {ln}")
        if hit:
            tw = hit[-1][2]
            after = lambda i, a=None: next(((e[2] - tw) & 0xFFFF for e in ev if e[0] == i and (a is None or e[1] == a)
                                            and ((e[2] - tw) & 0xFFFF) < 30000 and ev.index(e) > ev.index(hit[-1])), None)
            say(f"  measured, {name}: event -> wake line {(tw - t_inj) & 0xFFFF} ms; wake line -> console drawn "
                f"{after(0xCA)} ms, backlight on {after(0x10, 2)} ms, eDP link trained {after(0x90, 0x1B)} ms")
        return hit


def _burst_case(self):
    """#144: TMDS clock bursts shorter than the hold never wake; the burst line is logged once per sleep"""
    self.check(self.sleep(), "TMDS bursts: power saving reached")
    t0, woke = self.t2(), False
    while (self.t2() - t0) & 0xFFFF < QUIET_MS and not woke:
        self.fd.set_clock(self.m, 0x71, 148_500)
        woke, _ = self.until_wake(BURST_ON_MS)
        self.fd.set_clock(self.m, 0x71, None)
        if not woke:
            woke, _ = self.until_wake(BURST_PERIOD_MS - BURST_ON_MS)
    self.check(not woke, f"TMDS bursts {BURST_ON_MS} / {BURST_PERIOD_MS} ms: no wake within {QUIET_MS} ms")
    self.check(any("D2 TMDS clock burst" in x for x in self.lines()), "TMDS bursts: burst line logged",
               str(self.lines()[-4:]))


Run.burst_case = _burst_case


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/boot")
    ap.add_argument("--trace", action="store_true", help="log power / mode / OSD changes after each wake")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"wake_sim {a.bin.name}")
    r = Run(a)
    try:
        if not r.bus.run_until_mode(3):
            r.check(False, "boot to ACTIVE"); return 1
        r.bus.dbg_link_on()
        r.cmd(0x33, 0.2)                            # D3, fixed port: no source there
        t0 = r.t2()
        while r.bus.mode_state() != MODE_NOSIGNAL and (r.t2() - t0) & 0xFFFF < 5000:
            r.m.run(200_000)
        r.check(r.bus.mode_state() == MODE_NOSIGNAL, "D3 fixed: NO SIGNAL")
        r.wake_case("D2 cable unplugged", lambda: r.m.wr(D2_PIN, b"\x01"), "D2 cable unplugged: wake", BOUND_CABLE_MS)
        r.wake_case("D2 cable plugged in", lambda: r.m.wr(D2_PIN, b"\x00"), "D2 cable plugged in: wake", BOUND_CABLE_MS)
        st = r.model.snapshot(r.m, 0.0)
        img = np.array(R.render_snap(st, "black", 1))
        Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(a.out / "wake_cable_console.png")
        sm = M.summary(st)
        say(f"  png {a.out / 'wake_cable_console.png'} (OSD {'on' if sm['en'] else 'OFF'}, grid {sm['cols']}x{sm['rows']}, "
            f"console {r.m.rd(r.gpio + 3)[0]})")
        r.check(sm["en"] and sm["cols"] == 120 and r.m.rd(r.gpio + 3)[0] != 0, "console on screen after the cable wake")
        r.wake_case("sleep again, cables in, no edge", lambda: None, None, 0)
        # same episode (no picture since): each direction has woken once; a second unplug / plug is suppressed
        r.wake_case("D2 unplug again (no picture since)", lambda: r.m.wr(D2_PIN, b"\x01"), None, 0)
        r.wake_case("D2 plug again (no picture since)", lambda: r.m.wr(D2_PIN, b"\x00"), None, 0)
        sup = [x for x in r.lines() if "suppressed (cable" in x]
        r.check(any("cable unplug, once per sleep): D2" in x for x in sup) and any("(cable, once per sleep): D2" in x for x in sup),
                "repeat plug / unplug: suppressed once per direction", str(sup))
        r.wake_case("D2 EDID read", lambda: r.m.wr(DDC_D2, bytes([r.m.rd(DDC_D2)[0] | 1])), "D2 EDID read by source: wake",
                    BOUND_LATCH_MS)
        r.wake_case("D2 EDID read again (no picture since)", lambda: r.m.wr(DDC_D2, bytes([r.m.rd(DDC_D2)[0] | 1])), None, 0)
        r.check(any("wake suppressed (EDID read, once per sleep): D2" in x for x in r.lines()), "suppression logged once",
                str([x for x in r.lines() if "suppressed" in x]))
        if re.search(r"\s_g_ucAwtoPsAuxWakeOff\b", r.m.map_text):   # #144 test image: an AUX command is logged, no wake
            r.wake_case("DP AUX command (AUX wake off)", lambda: r.m.wr(AUX_RX1, bytes([r.m.rd(AUX_RX1)[0] | 1])), None, 0)
            r.check(any("D1 AUX command from source in power saving: no wake" in x for x in r.lines()), "AUX command logged")
        else:
            r.wake_case("DP AUX command", lambda: r.m.wr(AUX_RX1, bytes([r.m.rd(AUX_RX1)[0] | 1])),
                        "D1 AUX command from source: wake", BOUND_LATCH_MS)
        r.wake_case("DPCD 600h = D0", lambda: r.dpcd.mem.__setitem__(DPCD_600, 0x01), "D1 DPCD 600h = D0", BOUND_LATCH_MS)
        r.poll_period()
        if "_AwtoPsTmdsLive" not in r.m.sym:
            say("  SKIP TMDS clock cases: image without AwtoPsTmdsLive (pre-tmds image)")
        else:
            r.fd.set_clock(r.m, 0x71, None)         # freq detector model on, no clock on D2 / D3
            r.wake_case("D3 TMDS clock, no cable on D3", lambda: r.fd.set_clock(r.m, 0x72, 148_500), None, 0)
            r.fd.set_clock(r.m, 0x72, None)
            r.wake_case("D2 TMDS clock", lambda: r.fd.set_clock(r.m, 0x71, 148_500), "D2 wake by TMDS clock, about 148.",
                        BOUND_TMDS_MS)
            n0 = sum(1 for e in r.ring_events() if e[0] == 0xDC)     # still on: wakes again during the re-sleep settle
            r.sleep()
            r.until_wake(4 * BOUND_TMDS_MS)
            r.watch(300)
            n1 = sum(1 for e in r.ring_events() if e[0] == 0xDC)
            r.check(n1 == n0 + 1, "D2 TMDS clock still on (no picture since): wakes again", f"TMDS wake lines {n0} -> {n1}")
            r.fd.set_clock(r.m, 0x71, None)
            r.burst_case()
        if r.pass_ms:
            say(f"  measured, power-saving main-loop pass: {min(r.pass_ms):.2f}..{max(r.pass_ms):.2f} ms")
        d = C.decode(C.read(r.bus, r.caddr))
        say(f"  measured, watchdog: {C.ages(d)}")
        r.check(r.cr.resets == 0, "no chip reset (watchdog)", f"resets {r.cr.resets}")
    finally:
        r.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} wake_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
