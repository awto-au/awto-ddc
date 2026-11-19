#!/usr/bin/env python3
"""Health monitor (fw/diag/monitor.c, docs/monitoring.md) in fw_sim: sample period, rows, change thresholds, registry switch, heartbeat.

usage: AWTO_SIM_CORE=fast mon_sim_test.py BIN MAP [--mode 1080p60] [--no-beat]
- LSADC result cells FF09..FF0C are set by the test; the sync ring rows are decoded by scripts/sync_log.py (the host copy of the console text).
- First sample AWTO_MON_MS after boot: g_stAwtoMon filled, four rows (ADC, IOSC trim, loop + watchdog gap, uptime + stack) = a heartbeat.
- Nothing changed: no row. A2 moved one code (8): no row. A2 moved 2 codes (AWTO_MON_ADC_STEP): one ADC row, no other.
- Registry monitor off (set_get stub): no sample, no row; on again: the first sample is a heartbeat (all four).
- Heartbeat: AWTO_MON_BEAT_K samples after a heartbeat all four rows again (never dropped: the uptime row differs every time).
- Sample count: AwtoMonSample is called once per AWTO_MON_MS (call watch), not per pass.
Log: tmp/logs/mon_sim_test.log
"""
import argparse
import re
import sys
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import sync_log as SL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/mon_sim_test.log"
ADC = 0xFF09                                    # A0..A3 = FF09..FF0C
SET_ID_MONITOR = 124                            # registry id monitor (AwtoSetIds.h)
HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


def define(name):
    return int(re.search(rf"^#define\s+{name}\s+(\d+)", HDR.read_text(), re.M).group(1))


class Rig:
    def __init__(self, a):
        self.s = R.Session(a.bin, a.map, a.mode)
        self.s.boot()
        self.m = self.s.bus.m
        self.mon = self.m.addr("g_stAwtoMon")
        self.rows = SL.load_rows(SL.tsv_for(a.map))
        self.mapp = a.map
        self.on = {SET_ID_MONITOR: 1}
        self.m.stub("set_get", lambda m_, q: {"val": self.on[q["a1"] & 0xFF]} if (q["a1"] & 0xFF) in self.on else None)
        self.calls = 0
        self.m.stub("AwtoMonSample", self._count)
        self.fails = 0
        self.seen = 0

    def _count(self, m, r):
        self.calls += 1
        return None

    def wait(self, s):
        self.s.bus.wait(s)

    def adc(self, *v):
        self.m.wr(ADC, bytes(v))

    def beat(self):
        return self.m.rd(self.mon + 4)[0]

    def lines(self):
        _, ln = SL.decode(SL.read_ring(lambda a, n: self.m.rd(a, n), self.m.addr("g_stAwtoSync")), self.rows, whole=True)
        return [x for x in ln if "monitor:" in x]

    def new(self):
        ln = self.lines()
        out = ln[self.seen:] if len(ln) >= self.seen else ln
        self.seen = len(ln)
        return out

    def check(self, what, ok, detail=""):
        say(f"{'PASS' if ok else 'FAIL'} {what}{(': ' + detail) if detail else ''}")
        self.fails += 0 if ok else 1


def kinds(ln):
    return sorted(re.search(r"monitor: (ADC|IOSC|main loop|headroom|uptime)", x).group(1) for x in ln)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--scale", type=int, default=1, help="sim-only: run a copy of the image with the sample period 1/N (scripts/sim_time_scale.py); the checks are the same, the durations shorter")
    ap.add_argument("--no-beat", action="store_true", help="skip the heartbeat case (AWTO_MON_BEAT_K x AWTO_MON_MS of sim time)")
    a = ap.parse_args()
    ms, k = define("AWTO_MON_MS"), define("AWTO_MON_BEAT_K")
    pad = 1.0                                   # s of margin after a period: a main-loop pass + the sample
    if a.scale > 1:
        import sim_time_scale as TS
        img, ms = TS.patch_monitor(a.bin.read_bytes(), a.map.read_text(errors="replace"), a.scale)
        a.bin = ROOT / "tmp/scratch" / f"{a.bin.stem}-ts{a.scale}-be.bin"
        a.bin.parent.mkdir(parents=True, exist_ok=True)
        a.bin.write_bytes(img)
        pad = 0.3
    beat_rows = sorted(["ADC", "IOSC", "main loop", "uptime"] + (["headroom"] if "_g_stAwtoHead" in a.map.read_text(errors="replace") else []))   # a paced image adds the headroom row
    say(f"mon_sim_test {a.bin.name}: period {ms} ms, heartbeat every {k} samples")
    r = Rig(a)
    try:
        r.adc(0xF8, 0xF8, 0x58, 0x20)
        t0 = r.s.bus.now()
        while r.beat() == 0 and r.s.bus.now() - t0 < ms / 1000.0 * 1.5 + pad:
            r.wait(0.5)
        magic = bytes(r.m.rd(r.mon, 2))
        first = r.new()
        say("  first sample rows:\n" + "\n".join("    " + x for x in first))
        r.check("first sample: g_stAwtoMon 'MN', on, A0..A3 = the cells", magic == b"MN" and r.m.rd(r.mon + 3)[0] == 1
                and bytes(r.m.rd(r.mon + 5, 4)) == bytes([0xF8, 0xF8, 0x58, 0x20]), f"{magic!r} {bytes(r.m.rd(r.mon + 5, 4)).hex()}")
        r.check("first sample: the four rows (+ headroom on a paced image) on the heartbeat, ADC row decoded", kinds(first) == beat_rows
                and any("ADC A0 F8 A1 F8 A2 58 A3 20" in x for x in first), str(kinds(first)))
        r.check("first sample: loop rate > 0 and a watchdog gap are in the row",
                any(re.search(r"main loop [1-9]\d* passes/s, longest watchdog gap \d+ms", x) for x in first))
        c0 = r.calls
        r.wait(ms / 1000.0 + pad)
        r.check("one sample period, nothing changed: no new row", r.new() == [] or kinds(r.new()) == [], f"{r.new()}")
        r.seen = len(r.lines())
        r.adc(0xF8, 0xF8, 0x60, 0x20)
        r.wait(ms / 1000.0 + pad)
        r.check("A2 moved one code (8 < AWTO_MON_ADC_STEP): no row", r.new() == [])
        r.adc(0xF8, 0xF8, 0x78, 0x20)
        r.wait(ms / 1000.0 + pad)
        n = r.new()
        r.check("A2 moved two codes from the last row: exactly the ADC row, with the new value", kinds(n) == ["ADC"] and "A2 78" in n[0], str(n))
        r.check(f"sample calls: one per {ms} ms (not per pass)", 3 <= r.calls - c0 <= 5, f"{r.calls - c0} in ~{3 * (ms / 1000 + pad):.0f} s")
        r.on[SET_ID_MONITOR] = 0
        b = r.beat()
        r.adc(0xF8, 0xF8, 0x20, 0x20)
        r.wait(2 * ms / 1000.0 + 2 * pad)
        r.check("registry monitor off: no sample, no row", r.beat() == b and r.new() == [] and r.m.rd(r.mon + 3)[0] == 0)
        r.on[SET_ID_MONITOR] = 1
        r.wait(ms / 1000.0 + pad)
        n = r.new()
        r.check("monitor on again: the first sample is a heartbeat (four rows)", kinds(n) == beat_rows, str(n))
        if not a.no_beat:
            r.wait(k * ms / 1000.0 - ms / 2000.0)          # the K-th sample after the heartbeat lands inside this window
            n = r.new()
            r.check(f"heartbeat {k} samples after the last one: the four rows again", kinds(n) == beat_rows, str(n))
    finally:
        r.s.bus.close()
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} mon_sim_test {a.bin.name}: {r.fails} failed")
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
