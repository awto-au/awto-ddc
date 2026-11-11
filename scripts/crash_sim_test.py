#!/usr/bin/env python3
"""Watchdog + crash canary test in fw_sim (awto-ddc#131, docs/watchdog.md).

usage: AWTO_SIM_CORE=fast crash_sim_test.py BIN MAP [--mode 1080p60] [--steady 10] [--out tmp/wdt]
- Boot to ACTIVE (HDMI D2) and --steady s more: no chip reset; record read over the 0x35 block path (rtd_crash.read).
- Test cmd 0x4C (spin, no feed): sof_rst within AWTO_WDT_FEED_CHECKS checks; record = STALL TEST, PC in AwtoWdtHang (checks
  AWTO_WDT_FRAME against the real ISR prologue), bites 1; reboot to ACTIVE, the console opens by itself, PNG of it.
- Test cmd 0x4D (spin in a feeding wait): bite as PASS TEST within AWTO_WDT_PASS_CHECKS checks; bites 2.
- Host clear (rtd_crash.clear): record invalid afterwards.
- Reset model: fw_sim ChipReset (FFEE bit1). Limits from RL6449_Project.h of the tree (--header).
Log: tmp/logs/crash_sim_test.log; PNG + json: <out>/crash_panel.png
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402
import rtd_crash as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/crash_sim_test.log"
HEADER = Path("/mnt/2tb/git/awto-ddc-wdt/fw/overlay/Project/Header/RL6449_Project.h")
CMD_LATENCY_MS = 300       # test cmd sent -> consumed: <= one main-loop pass + the I2C write in the sim (~0.1 s); x3
STEP = 200_000             # instr per poll while waiting for the reset (~16 fw ms at 12.6 k instr/ms)
BOOT_LEAVE_INSTR = 20_000_000     # reset -> mode leaves the stale ACTIVE: SysMainSystemInitial, ~0.6 fw s in the sim (docs/delays.md); x2.5
READ_TRIES, READ_GAP_S = 5, 0.5   # record read retries: the 0x35 slave answers once the main loop runs (boot, pop-up draws)
# workload before the hang tests (test cmd, fw s after it): console, awto menu, source selector, D3 (no source) and back to D2
WORKLOAD = ((0x20, 2.0), (0x27, 1.0), (0x01, 1.5), (0x04, 1.0), (0x05, 1.5), (0x04, 1.0), (0x33, 5.0), (0x32, 8.0))


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def limits(header: Path) -> dict:
    t = header.read_text()
    return {k: int(re.search(rf"#define {k}\s+(\d+)", t).group(1)) for k in ("AWTO_WDT_CHECK_MS", "AWTO_WDT_FEED_CHECKS", "AWTO_WDT_PASS_CHECKS")}


class Run:
    def __init__(self, a):
        self.a, self.fails = a, 0
        self.s = R.Session(a.bin, a.map, a.mode)
        self.m = self.s.bus.m
        self.cr = next(d for d in self.m.devs if type(d).__name__ == "ChipReset")
        mt = a.map.read_text(errors="replace")
        self.addr, self.syms = C.map_addr(mt), C.load_syms(mt)
        self.diag = T.diag_addr(a.map)
        self.lim = limits(a.header)

    def check(self, ok: bool, what: str):
        say(f"  {'PASS' if ok else 'FAIL'} {what}")
        self.fails += 0 if ok else 1

    def rec(self) -> dict:
        for k in range(READ_TRIES):
            b = C.read(self.s.bus, self.addr)
            if b is not None:
                break
            bus = self.s.bus
            say(f"  record read {k + 1} failed (NAKs {bus.naks}; FF22 0x{self.m.rd(0xFF22)[0]:02X} IIC channel {bus.iic.channel(self.m)} "
                f"host DDC {bus.ddc}; mode {bus.mode_state()}); retry in {READ_GAP_S} s")
            self.s.bus.wait(READ_GAP_S)
        else:
            raise SystemExit("record read over 0x35 failed")
        d = C.decode(b)
        say(f"  record: {C.line(d, self.syms)}")
        return d

    def cmd(self, c: int):
        a = self.diag + T.TESTCMD_OFF
        bus = self.s.bus
        ok = bus.write(0x6A, 0x01, bytes([a >> 8])) and bus.write(0x6A, 0x03, bytes([c])) and bus.write(0x6A, 0x3B, bytes([a & 0xFF]))
        say(f"  test cmd 0x{c:02X} {'sent' if ok else 'NAK'}")
        return ok

    def wait_reset(self, n: int, max_ms: int) -> int | None:
        """Run until ChipReset has fired n times; fw ms from now to the reset (diag usT2Isr), None if not within max_ms."""
        t0 = self.s.bus.diag_t2()
        while self.cr.resets < n:
            self.m.run(STEP)
            if self.cr.resets < n and (self.s.bus.diag_t2() - t0) & 0xFFFF > max_ms:
                return None
        return (self.cr.at_t2[n - 1] - t0) & 0xFFFF

    def reboot(self):
        bus, used = self.s.bus, 0
        while bus.mode_state() == 3 and used < BOOT_LEAVE_INSTR:       # g_stModeInfo is RAM: ACTIVE stays until init rewrites it
            self.m.run(STEP); used += STEP
        if not bus.run_until_mode(3):
            raise SystemExit("no ACTIVE after the watchdog reset")
        self.s.bus.dbg_link_on()
        say(f"  ACTIVE again after the reset ({self.m.instr} instr total)")

    def hang(self, c: int, cause: int, n: int, checks: int):
        lim_ms = checks * self.lim["AWTO_WDT_CHECK_MS"]
        self.cmd(c)
        dt = self.wait_reset(n, lim_ms + self.lim["AWTO_WDT_CHECK_MS"] + CMD_LATENCY_MS)
        self.check(dt is not None and lim_ms - self.lim["AWTO_WDT_CHECK_MS"] <= dt <= lim_ms + self.lim["AWTO_WDT_CHECK_MS"] + CMD_LATENCY_MS,
                   f"cmd 0x{c:02X}: chip reset {dt} ms after the command (limit {lim_ms} ms, one check {self.lim['AWTO_WDT_CHECK_MS']} ms of phase)")
        self.reboot()
        d = self.rec()
        sym = C.symbolize(self.syms, d["bank"], d["pc"])
        self.check(d["valid"] and d["bites"] == n and d["cause"] == (cause | 0x80), f"record valid, bites {n}, cause 0x{cause | 0x80:02X}")
        return d, sym


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--steady", type=float, default=10.0, help="fw s in ACTIVE before the hang tests")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/wdt")
    ap.add_argument("--header", type=Path, default=HEADER)
    ap.add_argument("--tests", default="workload,stall,pass", help="comma list: workload, stall (0x4C), pass (0x4D)")
    a = ap.parse_args()
    say(f"crash_sim_test {a.bin.name}")
    r = Run(a)
    r.s.boot()
    r.s.bus.wait(a.steady)
    d = r.rec()
    r.check(r.cr.resets == 0, f"no chip reset over boot + {a.steady:.0f} s ACTIVE")
    r.check(d["valid"] and d["bites"] == 0 and (d["boot"] & 0x01) != 0, "cold boot: fresh record, LVR flag")
    say(f"  measured, boot + idle ACTIVE: max feed age {d['max_feed']} checks, max pass age {d['max_pass']} checks "
        f"(limits {r.lim['AWTO_WDT_FEED_CHECKS']} / {r.lim['AWTO_WDT_PASS_CHECKS']})")
    tests = a.tests.split(",")
    if "workload" in tests:
        for c, sec in WORKLOAD:
            r.cmd(c)
            r.s.bus.wait(sec)
        if not r.s.bus.run_until_mode(3):
            r.check(False, "ACTIVE again after the workload")
        d = r.rec()
        r.check(r.cr.resets == 0, "no chip reset over the workload")
        say(f"  measured, + workload: max feed age {d['max_feed']} checks, max pass age {d['max_pass']} checks")
    n = 0
    if "stall" in tests:
        n += 1
        d, sym = r.hang(0x4C, 1, n, r.lim["AWTO_WDT_FEED_CHECKS"])
        r.check(sym.startswith("AwtoWdtHang+"), f"PC {C.where(d, d['pc'])} = {sym} (AWTO_WDT_FRAME matches the ISR prologue)")
        r.check(d["mode"] == 3 and d["stage"] == 8, f"mode {d['mode']} stage {d['stage']} at the bite (ACTIVE, stage 8)")
        r.s.bus.wait(3.0)                              # info pop-up at ACTIVE opens the console (ucDbgPopup)
        d2 = r.rec()
        r.check((d2["boot"] & 0x08) == 0, "console drew the watchdog panel (NEW flag cleared)")
        a.out.mkdir(parents=True, exist_ok=True)
        R.save(r.s.snap(), a.out / "crash_panel.png", "grey", 2)
        say(f"  host line: {C.line(d2, r.syms)}")
    if "pass" in tests:
        n += 1
        d, sym = r.hang(0x4D, 2, n, r.lim["AWTO_WDT_PASS_CHECKS"])
        r.check(sym.startswith(("AwtoWdtHang+", "ScalerTimerDelayXms+")), f"PC {C.where(d, d['pc'])} = {sym} (spin in the wait)")

    r.check(C.clear(r.s.bus, r.addr) and not C.decode(C.read(r.s.bus, r.addr))["valid"], "host clear: record invalid")
    r.check(r.cr.resets == n, f"chip resets {r.cr.resets} ({n} test bites only)")
    say(f"{'PASS' if r.fails == 0 else 'FAIL'} crash_sim_test {a.bin.name}: {r.fails} failed checks")
    r.s.bus.close()
    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
