#!/usr/bin/env python3
"""Hardware watchdog and Timer0 event scheduler checks in fw_sim (awto-ddc#138, docs/watchdog.md).

usage: AWTO_SIM_CORE=fast wdt_sim.py boot BIN MAP        reset -> startup clear -> ScalerMcuInitial -> first poke / feed
       AWTO_SIM_CORE=fast wdt_sim.py events BIN MAP      arm each WD-timer event ID on Timer0, measure fire time (+-10 %)
       AWTO_SIM_CORE=fast wdt_sim.py rate BIN MAP        main-loop passes per fw second in ACTIVE (before / after a change)
- Time = fw_sim ChipReset clock: machine cycles / cycles per fw ms (Timer2 reload; crystal / 12 before Timer2 runs).
  Before the M2PLL switch the ucsim model's 12 clocks per machine cycle make it an upper bound (DW8051: 4).
- boot: every FFEA write (clear / mode) and the first hit of the watch points, with the gap since the last clear; PASS when
  the longest gap before the first main-loop pass is < half the period in force (N from FFEA).
- events: after boot to ACTIVE, test cmds 0x2A..0x2F arm events through the arm macro of ScalerTimerWDActivateTimerEvent_EXINT0
  (AwtoT0EvTest entry = arm time); fire = AwtoT0EvFire entry. On M2PLL, two pending, and across a forced Timer2 reload to the
  power-saving count and back (ScalerTimerSetTimerCount: the SDK's clock-switch reload point). PASS = each within +-10 %.
Log: tmp/logs/wdt_sim.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/wdt_sim.log"
BOOT_WATCH = ("main", "SysMainSystemInitial", "ScalerMcuInitial", "ScalerTimerWDInitial", "AwtoWdtCheck", "AwtoDiagMainPass")
BOOT_BUDGET = 40_000_000       # instr to the first main-loop pass: ~6 M in the sim (docs/delays.md stage 5 at 506 ms); x6
STEP = 20_000


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def chip_reset(m):
    return next(d for d in m.devs if type(d).__name__ == "ChipReset")


def boot(a) -> int:
    bus = S.SimBus(a.bin, a.map, video="1080p60", boot=False, dbg_link=False)
    m, cr = bus.m, chip_reset(bus.m)
    first = {}

    def hit(name):
        def f(m_, r):
            if name not in first:
                first[name] = cr.advance(m_)
        return f
    for n in BOOT_WATCH:
        if "_" + n in m.sym:
            m.stub(n, hit(n))
    used = 0
    while used < BOOT_BUDGET and ("AwtoDiagMainPass" not in first or len(cr.clears) < a.clears):
        m.run(STEP); used += STEP
    writes = cr.clears
    fails = 0
    say(f"wdt_sim boot {a.bin.name}: {used} instr, resets {cr.resets}, {len(writes)} clears")
    for clk, gap, ffea, ffeb, who in writes[:a.clears]:
        say(f"  clear at {clk:8.1f} ms, gap {gap:7.1f} ms, FFEA 0x{ffea:02X} N={(ffea & 7) + 1}, "
            f"{'timer' if ffeb & 0x10 else 'normal'} mode, by {who}")
    for n in BOOT_WATCH:
        if n in first:
            say(f"  first {n:22s} at {first[n]:8.1f} ms")
    # gap k ran under the N written by clear k-1 (the reset value N = 1 before the first)
    ns = [1] + [(w[2] & 7) + 1 for w in writes]
    gaps = [(w[1], ns[k], w[4]) for k, w in enumerate(writes)]
    worst = max(gaps, key=lambda g: g[0] / (g[1] * S.ChipReset.CNT3_MS)) if gaps else (cr.since, ns[-1], "-")
    ratio = worst[0] / (worst[1] * S.ChipReset.CNT3_MS)
    ok = cr.resets == 0 and "AwtoDiagMainPass" in first and ratio < 0.5
    say(f"  worst gap {worst[0]:.1f} ms of the {worst[1] * S.ChipReset.CNT3_MS:.0f} ms period in force (N={worst[1]}), "
        f"{ratio * 100:.0f} % (limit 50 %), ended by {worst[2]}")
    say(f"{'PASS' if ok else 'FAIL'} wdt_sim boot")
    fails += 0 if ok else 1
    bus.m.close()
    return fails


# test cmd -> (case, [(event ID name, ms)]): fw/sdcc/awto_t0ev.inc AwtoT0EvTest
EVENT_CASES = ((0x2A, "M2PLL", [("RX1_DP_REBUILD_PHY", 30)]), (0x2B, "M2PLL", [("RX2_HDMI_RR_RETRY", 10)]),
               (0x2C, "M2PLL", [("RX3_HDMI_RR_RETRY", 10)]),
               (0x2D, "two pending", [("RX2_HDMI_RR_RETRY", 10), ("RX1_DP_REBUILD_PHY", 30)]),
               (0x2E, "clock switch", [("RX1_DP_REBUILD_PHY", 30)]), (0x2F, "clock switch", [("RX2_HDMI_RR_RETRY", 10)]))
EVENT_IDS = {"RX1_DP_REBUILD_PHY": 1, "RX2_HDMI_RR_RETRY": 4, "RX3_HDMI_RR_RETRY": 5}    # enum order, D1 DP + no D0 DP build
EVENT_BUDGET = 20_000_000      # instr from the test cmd to the last fire: cmd latency ~0.1 s + 30 ms ~ 2 M; x10


def fw_ms(bus) -> float:
    """Firmware time: Timer2 ISR count (diag usT2Isr, 16 bit) + the running fraction of the current Timer2 period (TL2/TH2
    against RCAP2; TF2 pending = its ISR not run yet). The Timer0 events are specified in this time, whatever the reload."""
    m = bus.m
    tl, th, rl, rh = *m.rd(0xCC, 2, "sfr"), *m.rd(0xCA, 2, "sfr")
    cnt, rc = th << 8 | tl, rh << 8 | rl
    frac = min(max((cnt - rc) / (0x10000 - rc), 0.0), 1.0) if rc else 0.0
    return bus.diag_t2() + (1 if m.rd(0xC8, 1, "sfr")[0] & 0x80 else 0) + frac


def events(a) -> int:
    import osd_test as T
    bus = S.SimBus(a.bin, a.map, video="1080p60")
    m, cr = bus.m, chip_reset(bus.m)
    if not bus.run_until_mode(3):
        say("FAIL events: no ACTIVE")
        return 1
    fired, armed = [], []
    m.stub("AwtoT0EvFire", lambda m_, r: fired.append((r["r"][7] if m_.keil else r["a1"] & 255, fw_ms(bus))) or None)
    m.stub("AwtoT0EvTest", lambda m_, r: armed.append(fw_ms(bus)) or None)
    diag = T.diag_addr(a.map)
    fails = 0
    say(f"wdt_sim events {a.bin.name}")
    for cmd, case, want in EVENT_CASES:
        fired.clear(); armed.clear()
        ad = diag + T.TESTCMD_OFF
        bus.write(0x6A, 0x01, bytes([ad >> 8])); bus.write(0x6A, 0x03, bytes([cmd])); bus.write(0x6A, 0x3B, bytes([ad & 0xFF]))
        used = 0
        while used < EVENT_BUDGET and len(fired) < len(want):
            m.run(STEP); used += STEP
        if not armed or len(fired) < len(want):
            say(f"  FAIL cmd 0x{cmd:02X} {case}: armed {len(armed)}, fired {fired}"); fails += 1; continue
        for (name, ms), (fid, t) in zip(want, fired):
            dt = (t - armed[0]) % 65536
            ok = abs(dt - ms) <= ms * 0.10 and fid == EVENT_IDS[name]
            fails += 0 if ok else 1
            say(f"  {'PASS' if ok else 'FAIL'} 0x{cmd:02X} {case:12s} {name} (id {fid}) {ms} ms -> fired after {dt:6.2f} ms "
                f"({(dt - ms) / ms * 100:+5.1f} %, limit +-10 %)")
    ok = cr.resets == 0
    say(f"  {'PASS' if ok else 'FAIL'} no chip reset (resets {cr.resets})")
    fails += 0 if ok else 1
    say(f"{'PASS' if fails == 0 else 'FAIL'} wdt_sim events {a.bin.name}: {fails} failed")
    bus.m.close()
    return fails


def rate(a) -> int:
    """main-loop passes per fw second in ACTIVE (diag heartbeat / Timer2 ISR count), 1080p60 D2, after 2 s settle"""
    bus = S.SimBus(a.bin, a.map, video="1080p60")
    if not bus.run_until_mode(3):
        say("FAIL rate: no ACTIVE"); return 1
    bus.wait(2.0)
    d0 = bus.diag()
    bus.wait(3.0)
    d1 = bus.diag()
    hb, t2 = (d1["hb"] - d0["hb"]) & 0xFFFF, (d1["t2"] - d0["t2"]) & 0xFFFF
    say(f"wdt_sim rate {a.bin.name}: {hb} passes in {t2} fw ms = {hb * 1000 / max(t2, 1):.1f} /s (ACTIVE 1080p60, sim)")
    bus.m.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("boot", "events", "rate"))
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--clears", type=int, default=12, help="boot: watchdog clears to list (run on until that many)")
    a = ap.parse_args()
    return 1 if {"boot": boot, "events": events, "rate": rate}[a.what](a) else 0


if __name__ == "__main__":
    sys.exit(main())
