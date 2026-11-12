#!/usr/bin/env python3
"""menu_cli walk in fw_sim with a wide mailbox budget, timing every mailbox answer in sim ms (finds what the 40-poll budget misses).

usage: menu_walk_timing.py BIN MAP [--polls 300]
  Prints each answer slower than settings_cli.POLLS x 10 ms (the gate's budget) with the op, then the slowest five.
  Also reads the key state at boot (g_ucKeyStateCurr, ADC A0/A1, P3) and the power status: an image whose idle decode is
  a held key (old PCB_KEY_STATE: ADC 0 = POWER + LEFT) walks a powered-off monitor.
Needs the main tree's sim tools: AWTO_DDC_MAIN (default /mnt/2tb/git/awto-ddc). Log: ./tmp/logs/menu_walk_timing.log
"""
import argparse, os, sys, time
from pathlib import Path

MAIN = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc")) / "scripts"
sys.path.insert(0, str(MAIN))
import fw_sim  # noqa: E402
import menu_cli  # noqa: E402
import settings_cli as C  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/menu_walk_timing.log"


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--polls", type=int, default=300, help="mailbox budget, 10 ms sim each (default 3 s)")
    a = ap.parse_args()
    gate_ms = C.POLLS * 10
    C.POLLS = a.polls
    bus = fw_sim.SimBus(a.bin, a.map)
    mt = a.map.read_text(errors="replace")
    m = bus.m
    key = m.rd(m.addr("g_ucKeyStateCurr"))[0]
    p3 = m.rd(0xB0, 1, "sfr")[0]
    a0, a1 = m.rd(0xFF09, 2)
    try:
        pw = m.rd(m.addr("g_stPowerInfo"))[0]
    except fw_sim.SimError:
        pw = -1
    say(f"{a.bin.name}: boot key mask 0x{key:02X}, ADC A0=0x{a0:02X} A1=0x{a1:02X}, P3=0x{p3:02X}, g_stPowerInfo[0]=0x{pw & 0xFF:02X}, mode {bus.mode_state()}")
    times = []
    orig = C.Box.call

    def timed(self, cmd, code, v=0):
        t0 = bus.now()
        try:
            return orig(self, cmd, code, v)
        finally:
            dt = (bus.now() - t0) * 1000.0
            times.append((dt, cmd, code, v))
            if dt > gate_ms:
                say(f"  slow: cmd {cmd} code 0x{code:02X} arg {v}: {dt:.0f} ms sim (gate budget {gate_ms} ms), mode {bus.mode_state()}")
    C.Box.call = timed
    menu_cli.say = say
    rc = menu_cli.walk(menu_cli.Menu(C.Box(bus, mt, True), mt, True), None, None)
    times.sort(reverse=True)
    say("slowest answers (sim ms): " + ", ".join(f"{dt:.0f} (cmd {c} code 0x{k:02X} arg {v})" for dt, c, k, v in times[:5]))
    bus.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
