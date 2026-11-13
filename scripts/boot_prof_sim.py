#!/usr/bin/env python3
"""Boot profile in the sim (#144 / #162): the probe times of boot_prof.py (unit) for a sim cold boot, ring ms since reset.

usage: AWTO_SIM_CORE=fast boot_prof_sim.py BIN MAP [--mode 1080p60|2160p60] [--unit-ref]
- Runs from reset to ACTIVE (+ settle), decodes isr_g_stAwtoSw (sw log; ms since Timer2 start + the ring time of the Timer2 start).
- --unit-ref: prints the unit-2 m15 cold boot (tmp/logs/coldboot-m15.txt milestones) next to the sim values.
Log: tmp/logs/boot_prof_sim.log
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osd_render as R  # noqa: E402
import sw_timeline as T  # noqa: E402
import sync_log as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/boot_prof_sim.log"
STEP = 100_000                  # instructions per poll
BUDGET_INSTR = 400_000_000      # 4K boot with the fetch model ~150 M; expiry = FAIL
PROBES = {0x30: "TimerEvent init done", 0x31: "UserCommonInterfaceInitial done", 0x32: "DdcRamEnable done", 0x33: "SysSourceInitial done",
          0x34: "SysPowerInitial done = SysMainSystemInitial end", 0x35: "chip reset done", 0x36: "IOSC trimming done",
          0x37: "LDO done, EDID load next", 0x38: "EDID loaded", 0x39: "HDCP key + D0 init done", 0x3A: "DP init done",
          0x3B: "mode INITIAL entered", 0x3C: "UserInterfaceInitial done"}
UNIT = {"main()": 109, "first main-loop pass": 522, "mode SEARCH": 1028, "mode ACTIVE": 2289}      # coldboot-m15.txt


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    s = R.Session(a.bin, a.map, a.mode)
    bus, m = s.bus, s.bus.m
    used = 0
    try:
        while used < BUDGET_INSTR and bus.mode_state() != 3:
            m.run(STEP); used += STEP
        bus.wait(0.3)
        h, lines = S.decode(S.read_ring(m.rd, S.sym(a.map, "g_stAwtoSync")), S.load_rows(S.tsv_for(a.map)))
        for ln in lines:
            say(f"  {ln}")
        t2 = next((int(ln[1:].split("ms")[0]) for ln in lines if "Timer2 1 ms tick" in ln), 0)
        raw = m.rd(T.sym(a.map, "isr_g_stAwtoSw"), 12 + 4 * T.N_EV)
        hdr, evs = T.decode(raw)
        say(f"sw log: {hdr['n']} events; ring offset of Timer2 start {t2} ms; sim CPU {getattr(m, 'cpu', 'ucsim')}")
        prev = 0
        for ms, i, g in evs:
            if i == 0x90 and g in PROBES:
                say(f"  probe +{ms + t2:5d} ms ({ms - prev:+5d})  {PROBES[g]}")
                prev = ms
    finally:
        bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
