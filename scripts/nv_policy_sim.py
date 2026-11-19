#!/usr/bin/env python3
"""NVRAM write policy in fw_sim (#151, Dan 2026-11-18): count flash halts (g_stAwtoNv: page programs + sector erases) per scenario.

usage: nv_policy_sim.py BIN MAP [--mode 1080p60] [--minutes 25]
  - 10 equal VCP 0x10 sets, menu open + close without a change, a selector input switch, N minutes of backlight, then
    a changed VCP set (must write through the gate) and a POWER off (flush: panel time written here only).
  - ops = g_stAwtoNv.usOps (programs + erases), items = usItemWr; every scenario states its expected ops.
Exit 1 on a failed check. Log: ./tmp/logs/nv_policy_sim.log
"""
import argparse
import os
import sys
from pathlib import Path

import isostamp

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as D
import key_sim_test as K
import osd_render as R

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/nv_policy_sim.log"
VCP_BRIGHTNESS = 0x10
NV_OFF = {"flush": 6, "items": 8, "ops": 10, "erase": 16, "bytes": 18, "defer": 4}   # StAwtoNv, big-endian words


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class Run:
    def __init__(self, a):
        self.eng = D.DdcEngine()
        self.s = R.Session(a.bin, a.map, a.mode, devs=[self.eng])
        self.s.boot()
        self.k = K.Keys(self.s)
        self.mccs = D.Mccs(self.s.bus, self.eng)
        self.nv = self.s.bus.m.addr("g_stAwtoNv")
        self.fails = 0

    def cnt(self):
        b = self.s.bus.m.rd(self.nv, 20)
        return {n: b[o] << 8 | b[o + 1] for n, o in NV_OFF.items()}

    def panel(self):
        b = self.s.bus.m.rd(self.s.bus.m.addr("g_stPanelTimeData"), 3)        # usHour (2 B big-endian), ucMin
        return (b[0] << 8 | b[1]) * 60 + b[2]

    def scenario(self, name, fn, want_ops):
        c0 = self.cnt()
        fn()
        c1 = self.cnt()
        d = {n: c1[n] - c0[n] for n in c0}
        ok = want_ops(d["ops"])
        self.fails += 0 if ok else 1
        say(f"{'PASS' if ok else 'FAIL'} {name}: flash halt ops {d['ops']} (erases {d['erase']}), items {d['items']}, flushes {d['flush']}, "
            f"deferred saves {d['defer']}, bytes {d['bytes']}")
        return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--minutes", type=int, default=25)
    a = ap.parse_args()
    say(f"nv_policy_sim {a.bin.name}")
    r = Run(a)
    k, mc = r.k, r.mccs
    try:
        k.wait(40000)                                           # boot writes + the gate settle (forced write after 30 s at the latest)
        cur = mc.get(VCP_BRIGHTNESS)
        say(f"brightness {cur}")

        def equal_sets():
            for _ in range(10):
                mc.set(VCP_BRIGHTNESS, cur["cur"])
                k.wait(300)
            k.wait(6000)
        r.scenario("10 equal VCP 0x10 sets", equal_sets, lambda o: o == 0)

        def menu():
            k.tap("MENU")
            k.tap("DOWN")
            k.tap("MENU")
            for _ in range(4):
                if k.menu() == 0:
                    break
                k.tap("MENU")
            k.wait(6000)
        r.scenario("menu open + close, nothing changed", menu, lambda o: o == 0)

        def switch():
            K.live_ports(k, ("D2", "D3"))
            k.ring0 = K.ring(k)
            k.wait(500)
            K.take(k, "D2", "D3", "idle")
            k.wait(10000)
        r.scenario("input switch D2 -> D3 (selector, idle commit)", switch, lambda o: 1 <= o <= 6)

        def backlight():
            m0 = r.panel()
            k.wait(a.minutes * 60 * 1000)
            say(f"  panel used time advanced {r.panel() - m0} min in {a.minutes} min")
        r.scenario(f"{a.minutes} min of backlight", backlight, lambda o: o == 0)

        def changed():
            mc.set(VCP_BRIGHTNESS, (cur["cur"] + 7) % 101)
            k.wait(6000)
        r.scenario("one changed VCP 0x10 set (through the gate)", changed, lambda o: 1 <= o <= 4)

        def power():
            k.power(True)
            k.wait(150)
            k.power(False)
            k.wait(3000)
        r.scenario("POWER off (flush, panel time written here)", power, lambda o: o >= 1)
    finally:
        r.s.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} nv_policy_sim: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
