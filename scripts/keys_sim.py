#!/usr/bin/env python3
"""Offline proof of the front-key decode and the key test screen (#85, #39): firmware image in fw_sim, ADC / P3.0 injected.

usage: keys_sim.py BIN MAP [--png-dir tmp/osd39] [--skip-decode]
  1. decode: every band edge of A0 / A1 (in and out of band), P3.0, and combos -> g_stAwtoKey.ucMask == the model's mask
  2. test screen: open by test cmd 0x41, inject a key, render to PNG, close by the UP+DOWN combo, press log check
Needs the sim tools of the main tree (fw_sim, osd_render, osd_model): AWTO_DDC_MAIN (default /mnt/2tb/git/awto-ddc).
Log: ./tmp/logs/keys_sim.log
"""
import argparse, os, sys, time
from pathlib import Path

MAIN = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc")) / "scripts"
sys.path.insert(0, str(MAIN))
sys.path.insert(1, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/keys_sim.log"
IDLE = (0xF8, 0xF8, 1)
SOURCE, MENU, DOWN, UP, AUTO, POWER = 0x20, 0x02, 0x08, 0x04, 0x10, 0x01      # SDK masks (_KEY5, _MENU, _LEFT, _RIGHT, _EXIT, _POWER)
NAMES = {SOURCE: "SOURCE", MENU: "MENU", DOWN: "DOWN", UP: "UP", AUTO: "AUTO", POWER: "POWER"}


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def model(a0, a1, p3, a0top_source=True):
    """Expected SDK mask: vendor bands lo <= R < hi (buttons.md), POWER = P3.0 low."""
    m = 0
    inb = lambda v, lo, hi: lo <= v < hi
    if inb(a0, 0xC0, 0xE0):
        m |= SOURCE if a0top_source else AUTO
    if inb(a0, 0x70, 0x90):
        m |= MENU
    if inb(a0, 0x28, 0x48):
        m |= DOWN
    if inb(a1, 0x68, 0x88):
        m |= AUTO if a0top_source else SOURCE
    if inb(a1, 0x28, 0x48):
        m |= UP
    if p3 == 0:
        m |= POWER
    return m


EDGES0 = [0xBF, 0xC0, 0xDF, 0xE0, 0x27, 0x28, 0x47, 0x48, 0x6F, 0x70, 0x8F, 0x90]
EDGES1 = [0x67, 0x68, 0x87, 0x88, 0x27, 0x28, 0x47, 0x48]


class Keys:
    def __init__(self, s):
        self.s, self.m = s, s.bus.m
        self.base = self.m.addr("g_stAwtoKey")

    def put(self, a0, a1, p3):
        self.m.wr(0xFF09, bytes([a0]))
        self.m.wr(0xFF0A, bytes([a1]))
        self.m.wr(0xB0, bytes([0xFF if p3 else 0xFE]), "sfr")

    def state(self):
        b = self.m.rd(self.base, 16 + 16 * 8)
        return {"open": b[3], "drawn": b[4], "count": b[5], "a0": b[6], "a1": b[7], "p30": b[8], "mask": b[9], "msg": b[10], "flags": b[11],
                "log": [dict(seq=e[0], tick=e[1] << 8 | e[2], a0=e[3], a1=e[4], flags=e[5], mask=e[6], msg=e[7])
                        for e in (b[16 + 8 * i:24 + 8 * i] for i in range(16))]}

    def settle(self, ms=120):
        self.s.bus.wait(ms / 1000.0)

    def cmd(self, v):
        d = self.s.diag + 0x28
        for _ in range(4):                                      # 0x35 NAKs while the OSD draws
            if self.s.bus.write(0x6A, 0x01, bytes([d >> 8])) and self.s.bus.write(0x6A, 0x03, bytes([v])) and \
                    self.s.bus.write(0x6A, 0x3B, bytes([d & 0xFF])):
                return True
            self.settle(50)
        return False


FAILS = []


def chk(name, ok, detail=""):
    say(f"{'ok  ' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)
    return ok


def check_decode(k):
    cases = [(v, 0xF8, 1) for v in EDGES0] + [(0xF8, v, 1) for v in EDGES1]
    cases += [(0x30, 0xF8, 1), (0xD0, 0x78, 1), (0x80, 0x78, 1), IDLE]       # single DOWN, SOURCE+AUTO, MENU+AUTO (no combo with an action)
    for a0, a1, p3 in cases:
        k.put(a0, a1, p3)
        k.settle(150)
        st = k.state()
        want = model(a0, a1, p3)
        chk(f"decode A0={a0:02X} A1={a1:02X} P3.0={p3}", st["mask"] == want and st["a0"] == a0 and st["a1"] == a1,
            f"mask {st['mask']:02X} want {want:02X} ({'+'.join(n for b, n in NAMES.items() if want & b) or 'none'}) msg {st['msg']:02X} count {st['count']}")


def state_open(k, want, why):
    st = k.state()
    chk(why, st["open"] == want, f"open={st['open']} drawn={st['drawn']} count={st['count']}")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--png-dir", type=Path, default=ROOT / "tmp/osd39")
    ap.add_argument("--skip-decode", action="store_true")
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, "2160p60")
    try:
        s.boot()
        k = Keys(s)
        k.put(*IDLE)
        k.settle(200)
        if not a.skip_decode:
            check_decode(k)
            k.put(0x80, 0xF8, 1)                                # MENU may have opened our menu: leave it with AUTO presses
            k.settle(200)
            for _ in range(2):
                k.put(0xF8, 0x78, 1); k.settle(300)
                k.put(*IDLE); k.settle(300)
        # 1. open by test cmd, screen drawn
        k.cmd(0x41)
        k.settle(900)
        st = state_open(k, 1, "cmd 0x41 opens")
        chk("screen drawn", st["drawn"] == 1)
        # 2. keys while open: real DOWN, injected UP, MENU + UP (no debug-link side effect needed to be checked here)
        c0 = st["count"]
        k.put(0x30, 0xF8, 1); k.settle(1500)
        k.put(*IDLE); k.settle(600)
        k.cmd(0x02); k.settle(900)
        st = k.state()
        new = [e for e in st["log"] if (e["seq"] - c0) & 0xFF < 8 and (e["seq"] - c0) & 0xFF < ((st["count"] - c0) & 0xFF)]
        chk("DOWN logged", any(e["mask"] == DOWN and not e["flags"] & 0x80 for e in new), f"count {st['count']}")
        chk("injected UP logged", any(e["mask"] == 0 and e["msg"] == 1 and e["flags"] & 0x80 for e in new))
        chk("keys swallowed while open", st["open"] == 1)
        a.png_dir.mkdir(parents=True, exist_ok=True)
        R.save(s.snap(), a.png_dir / "keytest.png", "grey", 1)
        for e in st["log"][:st["count"] if st["count"] < 16 else 16]:
            say(f"log seq {e['seq']:3d} tick {e['tick']:5d} A0={e['a0']:02X} A1={e['a1']:02X} flags {e['flags']:02X} mask {e['mask']:02X} msg {e['msg']:02X}")
        # 3. close by UP+DOWN
        k.put(0x30, 0x30, 1); k.settle(1500)
        k.put(*IDLE); k.settle(900)
        state_open(k, 0, "UP+DOWN closes")
        # 4. open by UP+DOWN from idle
        k.put(0x30, 0x30, 1); k.settle(1500)
        k.put(*IDLE); k.settle(900)
        st = state_open(k, 1, "UP+DOWN opens")
        chk("combo-opened screen drawn", st["drawn"] == 1)
        k.cmd(0x42); k.settle(900)
        state_open(k, 0, "cmd 0x42 closes")
        # 5. the host tool against the sim bus: reads the same block over the 0x35 protocol
        import importlib.util
        sp = importlib.util.spec_from_file_location("kw", Path(__file__).resolve().parent / "rtd_keywatch.py")
        kw = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(kw)
        import io as _io, contextlib
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            kw.log_mode(["0", "--log", "--map", str(a.map), "--once", "--history"], ROOT, io=s.bus)
        out = buf.getvalue()
        say("rtd_keywatch --log (sim bus):\n" + out)
        chk("rtd_keywatch reads the block", "key block ok" in out and "PRESS #" in out, out.splitlines()[0][26:100] if out else "")
    finally:
        s.bus.close()
    say("RESULT " + ("PASS" if not FAILS else "FAIL " + ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
