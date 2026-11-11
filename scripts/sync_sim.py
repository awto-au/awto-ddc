#!/usr/bin/env python3
"""#139 in fw_sim: power-on log, selector with per-port status, D2 -> D3 -> D2 switch log; PNGs, ring decode, loop rate.

usage: AWTO_SIM_CORE=fast sync_sim.py BIN MAP [--mode 1080p60] [--out tmp/sync]
       AWTO_SIM_CORE=fast sync_sim.py --rate BIN MAP     loop rate only (console auto-open off): idle ACTIVE, selector open;
                                                          works on images without #139 (A/B)
- Boot with the console auto-open ON (firmware default): the power-on episode opens the console once settled.
  Checks: ring magic, power-on lines (mode ACTIVE, backlight on, timing), console opened by itself, no chip reset.
- Console closed, selector opened (SOURCE): PNG; loop rate with the selector open vs closed (diag usLoopRate).
- Test cmd 0x33 (D3, no source in the sim) then 0x32 (back to D2): switch episodes decoded by scripts/sync_log.py
  (the host decoder), console auto-open on each; PNG per episode.
- Watchdog ages from the crash record (rtd_crash) after all of it.
PNGs: <out>/poweron_console.png, selector_status.png, switch_d3_console.png, switch_d2_console.png (+ _crop).
Log: tmp/logs/sync_sim.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402
import rtd_crash as C  # noqa: E402
import sync_log as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/sync_sim.log"
K_MENU, K_SOURCE, CON_CLOSE = 0x04, 0x05, 0x44     # injected MENU / SOURCE; test cmd 0x44 = console close (awto_testcmd.inc)
SETTLE_S = 3.0      # a switch to ACTIVE + console open: AWTO_SYNC_OPEN_MS 2 s + one console draw (~0.3 s sim) x ~1.25
RATE_S = 2.5        # usLoopRate covers the last ~1 s; 2.5 s = two full windows after a change


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def rate_only(a) -> int:
    s = R.Session(a.bin, a.map, a.mode)
    try:
        s.boot()
        s.bus.wait(RATE_S)
        rd = lambda: int.from_bytes(s.bus.m.rd(s.diag + 42, 2), "big")
        idle = rd()
        addr = s.diag + T.TESTCMD_OFF
        s.bus.write(0x6A, 0x01, bytes([addr >> 8])) and s.bus.write(0x6A, 0x03, bytes([K_SOURCE])) and \
            s.bus.write(0x6A, 0x3B, bytes([addr & 0xFF]))
        s.bus.wait(RATE_S)
        say(f"  measured, sim loop rate {a.bin.name}: idle ACTIVE {idle}/s, selector open {rd()}/s")
    finally:
        s.bus.close()
    return 0


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.s = R.Session(a.bin, a.map, a.mode)
        self.m = self.s.bus.m
        self.rows = S.load_rows(S.tsv_for(a.map))
        self.ring = S.sym(a.map, "g_stAwtoSync")
        self.gpio = self.m.addr("g_stAwtoGpio")
        self.key = self.m.addr("g_stAwtoKey")
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        mt = a.map.read_text(errors="replace")
        self.caddr, self.csyms = C.map_addr(mt), C.load_syms(mt)

    def check(self, ok, what, detail=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1

    def cmd(self, c, wait=0.5):
        addr = self.s.diag + T.TESTCMD_OFF
        b = self.s.bus
        ok = b.write(0x6A, 0x01, bytes([addr >> 8])) and b.write(0x6A, 0x03, bytes([c])) and b.write(0x6A, 0x3B, bytes([addr & 0xFF]))
        if not ok:
            say(f"  test cmd 0x{c:02X} NAK")
        b.wait(wait)

    def episode(self, title):
        h, lines = S.decode(self.m.rd(self.ring, S.HDR + S.N * S.EV), self.rows)
        say(f"  {title}: episode {S.KINDS.get(h['kind'], h['kind'])}, {len(lines)} lines, done {h['done']}, lost {h.get('lost', 0)}")
        for ln in lines:
            say(f"    {ln}")
        return h, lines

    def console(self):
        return self.m.rd(self.gpio + 3)[0] | self.m.rd(self.key + 3)[0]

    def loop_rate(self):
        return int.from_bytes(self.m.rd(self.s.diag + 42, 2), "big")     # StAwtoDiag.usLoopRate at 42 (BE image)

    def shot(self, name):
        st = self.s.snap()
        out = self.a.out / f"{name}.png"
        img = np.array(R.render_snap(st, "grey", 1))
        Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(out)
        mask = np.any(img != np.array(R.BGS["grey"], np.uint8), axis=2)
        if M.summary(st)["en"] and mask.any():
            ys, xs = np.nonzero(mask)
            Image.fromarray(img[max(0, ys.min() - 16):ys.max() + 17, max(0, xs.min() - 16):xs.max() + 17]).save(
                out.with_name(name + "_crop.png"))
        say(f"  png {out} (OSD {'on' if M.summary(st)['en'] else 'OFF'}, grid {M.summary(st)['cols']}x{M.summary(st)['rows']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/sync")
    ap.add_argument("--rate", action="store_true", help="loop rate only (A/B against older images)")
    a = ap.parse_args()
    if a.rate:
        return rate_only(a)
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"sync_sim {a.bin.name}")
    r = Run(a)
    try:
        r.s.boot(sync_console=True)
        r.s.bus.wait(SETTLE_S)
        h, lines = r.episode("power-on")
        txt = "\n".join(lines)
        r.check(h["magic"] == b"SY" and h["kind"] == 1, "ring: power-on episode", f"magic {h['magic']!r} kind {h['kind']}")
        for want in ("power on", "mode ACTIVE", "backlight on", "timing ", "console opened"):
            r.check(want in txt, f"power-on log has '{want}'")
        r.check(r.console() != 0, "console opened by itself after power-on")
        r.shot("poweron_console")
        r.cmd(CON_CLOSE, 1.0)
        r.check(r.console() == 0, "console closed (test cmd 0x44)")
        r.s.bus.wait(RATE_S)
        idle = r.loop_rate()
        r.cmd(K_SOURCE, 1.5)
        r.shot("selector_status")
        r.s.bus.wait(RATE_S)
        sel = r.loop_rate()
        say(f"  measured, sim loop rate: idle ACTIVE {idle}/s, selector open {sel}/s")
        r.cmd(K_MENU, 1.0)
        for port, c, name, want in ((3, 0x33, "switch_d3", "mode NO SIGNAL"), (2, 0x32, "switch_d2", "mode ACTIVE")):
            r.cmd(c, 0.2)
            if port == 2:
                r.s.bus.run_until_mode(3)
            r.s.bus.wait(SETTLE_S)
            h, lines = r.episode(f"switch to D{port}")
            txt = "\n".join(lines)
            r.check(h["kind"] == 2 and h["port"] == port + 3, f"switch episode for D{port}", f"kind {h['kind']} port {h['port']}")
            r.check(want in txt and "console opened" in txt, f"D{port} log has '{want}' and the console opened")
            r.check(r.console() != 0, f"console open after the switch to D{port}")
            r.shot(f"{name}_console")
            r.cmd(CON_CLOSE, 0.5)
        d = C.decode(C.read(r.s.bus, r.caddr))
        say(f"  measured, watchdog: max feed age {d['max_feed']} checks, max pass age {d['max_pass']} checks")
        r.check(r.cr.resets == 0, "no chip reset (watchdog) over power-on, selector and two switches", f"resets {r.cr.resets}")
    finally:
        r.s.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} sync_sim {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
