#!/usr/bin/env python3
"""#144 task 4 in fw_sim: wake from power saving on source events (cable plug, EDID read, DP AUX command, DPCD 600h = D0).

usage: AWTO_SIM_CORE=fast wake_sim.py BIN MAP [--mode 1080p60] [--out tmp/boot]
- Boot to ACTIVE on D2, switch to D3 (test cmd 0x33: fixed port, no source), force power saving (g_stPowerInfo target).
- Each step forces power saving again, injects one event, and checks wake / no wake within the bound:
  D2 unplug (wake, "D2 cable unplugged: wake", #138 task 6), D2 plug (wake, "D2 cable plugged in: wake"), sleep with every
  cable in (no wake: no edge), unplug / plug again in the same episode (suppressed, once per direction),
  D2 EDID read latch (wake), the same latch again (no wake, "wake suppressed"), DP AUX rx latch (wake), DPCD 600h = D0 (wake).
- Measured: edge -> wake line (fw ms), wake line -> console drawn / backlight on (ring), PS main-loop pass time.
- Sim devices: W1C on the latches (DDCn_EDID_IRQ bit0, AUX_IRQ_STATUS bit0), cable pins (low = cable), DPCD port memory.
PNG: <out>/wake_cable_console.png (console after the cable wake). Log: tmp/logs/wake_sim.log
"""
import argparse
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
# Event -> wake line (firmware ms). Cable: detection every AWTO_SLOW_MS 10 ms + SDK 10 ms debounce re-read + 1 PS pass
# (8 ms worst, measured below) = 28 ms, x1.25 -> 35 ms. Latches / DPCD: 1 PS pass 8 ms + this test's sample step 2 ms
# + 1 ms tick = 11 ms, x1.25 -> 13 ms. Over = FAIL.
BOUND_CABLE_MS, BOUND_LATCH_MS = 35, 13
QUIET_MS = 1000         # no-wake checks: 1 s = 50x the latch bound; a wake would show well inside it
SLEEP_SETTLE_MS = 300   # after the forced power saving: power-down switch done, wake triggers armed
STEP = 20_000           # instructions per sample (~0.3-1 ms of fw time)


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.model = M.OsdModel()
        self.model.img = a.bin.read_bytes()
        w1c = S.W1C({DDC_D2: 0x01, 0xFFE5: 0x01, 0xFE72: 0x01, 0xB7DC: 0x01, AUX_RX1: 0x01})
        self.bus = S.SimBus(a.bin, a.map, "wake-" + a.bin.stem, None, boot=False, devs=[self.model, w1c], video=a.mode)
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
        hit = [e for e in ev if e[0] in (0xCB, 0xCC, 0xCD, 0xCE, 0xD3)]
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
        r.wake_case("DP AUX command", lambda: r.m.wr(AUX_RX1, bytes([r.m.rd(AUX_RX1)[0] | 1])), "D1 AUX command from source: wake",
                    BOUND_LATCH_MS)
        r.wake_case("DPCD 600h = D0", lambda: r.dpcd.mem.__setitem__(DPCD_600, 0x01), "D1 DPCD 600h = D0", BOUND_LATCH_MS)
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
