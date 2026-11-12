#!/usr/bin/env python3
"""#84 dead-port cases in the fw_sim model: a single-cable unit must not be switched to a port with no cable and stay there.

usage: deadport_sim.py BIN MAP [--case vcp|sel|cmd|all] [--mode 1080p60] [--secs 16]
  Board: HDMI source on D3 (the only cable; D1 / D2 cable pins read unplugged), boot to ACTIVE on D3.
  vcp  DDC/CI set VCP 0x60 = 0x11 (D2) over the spare IIC engine. PASS: refused, still ACTIVE on D3 after --secs.
  sel  front keys: SOURCE opens the selector (on Auto), 2x DOWN steps to D2, AUTO takes it. PASS: refused, still ACTIVE on D3.
  cmd  test cmd 0x32 (switch to D2, fixed port; test cmds are not refused).
       PASS: back to ACTIVE on D3 within --secs (guard: fixed port, no cable, no signal -> auto search).
  Each case also needs its log line: switch-log 0xB8 (vcp / sel: arg 1, cmd: arg 3) and the sync-log line (sync.tsv DF).
  Prints the switch log (g_stAwtoSw) decoded with sw_timeline.name.
Log: tmp/logs/deadport_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import sw_timeline as T  # noqa: E402
import ddc_sim as DD  # noqa: E402
import sync_log as SL  # noqa: E402

D3 = 6                                  # Global.h _D3_INPUT_PORT
TESTCMD = 0xF6F8                        # g_stAwtoDiag + 0x28
A0, A1, IDLE = 0xFF09, 0xFF0A, 0xF8     # key ADC cells (key_sim_test.py KEY_ADC band centres below)
KEY_SOURCE, KEY_DOWN, KEY_UP, KEY_AUTO, KEY_MENU = (A1, 0x80), (A1, 0x38), (A0, 0x38), (A0, 0x80), (A0, 0xD0)
NOCABLE_D1 = {0xFE33: 0, 0xFE34: 1, 0xFE35: 1}     # cable status = !bD1_CONNECT (SysSource.c); unit 3 cabled reads 01 01 00


class Pins(S.Cells):
    """Input pins: values held even when the firmware writes the cell (GPIO init writes the port latches)."""

    def __init__(self, cells):
        super().__init__(cells)
        self.writes = tuple(cells)

    def on_write(self, m, a):
        m.put(f"set memory xram 0x{a:x} 0x{self.cells[a]:x}")


def port_now(bus) -> int:
    pri = bus.xdata(bus.addr("g_pucSourceSearchPriority"), 10)
    return pri[bus.xdata(bus.addr("g_ucSearchIndex"))[0] % 10]


def tap(bus, key, ms=150, gap=0.4):
    bus.m.wr(key[0], bytes([key[1]]))
    bus.wait(ms / 1000.0)
    bus.m.wr(key[0], bytes([IDLE]))
    bus.wait(gap)


def swlog(bus, say):
    raw = bus.xdata(bus.addr("g_stAwtoSw"), 12 + 4 * T.N_EV)
    hdr, evs = T.decode(raw, bus.be) if hasattr(T, "decode") else (None, [])
    for ms, i, g in evs[-40:]:
        say(f"  +{ms:6d} ms  {T.name(i, g)}")
    return [(i, g) for _, i, g in evs]


def synclog(a, bus, say):
    """every line still in the sync ring, decoded with fw/awto/sync.tsv (a.sync_tsv or beside the map)"""
    rows = SL.load_rows(a.sync_tsv or SL.tsv_for(a.map))
    _, lines = SL.decode(SL.read_ring(bus.xdata, SL.sym(a.map, "g_stAwtoSync")), rows, whole=True)
    for ln in lines:
        say(f"  sync {ln}")
    return lines


def run_case(a, case: str, say) -> bool:
    eng = DD.DdcEngine()
    bus = S.SimBus(a.bin, a.map, video=a.mode, port="D3", devs=[Pins(NOCABLE_D1), eng])
    try:
        if not bus.run_until_mode(3):
            say(f"{case}: FAIL no ACTIVE at boot"); return False
        say(f"{case}: ACTIVE on port 0x{port_now(bus):02X}, cable status 0x{bus.xdata(bus.addr('g_stPortCableStatus'))[0]:02X} "
            "(bit4 D1, bit5 D2, bit6 D3)")
        bus.wait(1.0)
        if case == "vcp":
            DD.Mccs(bus, eng).set(0x60, 0x11)
        elif case == "sel":
            if bus.m.rd(bus.addr("g_stAwtoGpio") + 3)[0] | bus.m.rd(bus.addr("g_stAwtoKey") + 3)[0]:
                tap(bus, KEY_MENU)                  # the sync console opened by itself at ACTIVE: MENU closes it, the rest is swallowed
            tap(bus, KEY_SOURCE)
            tap(bus, KEY_DOWN)                      # opens on Auto (auto scan): DOWN wraps to D3, then D2
            tap(bus, KEY_DOWN)
            tap(bus, KEY_AUTO)
        else:
            bus.m.wr(TESTCMD, bytes([0x32]))
        t0, seen = bus.now(), []
        while bus.now() - t0 < a.secs:
            bus.wait(0.25)
            st = (bus.mode_state(), port_now(bus))
            if not seen or seen[-1][1:] != st:
                seen.append((round(bus.now() - t0, 2), *st))
        ms, port = bus.mode_state(), port_now(bus)
        say("  timeline: " + " -> ".join(f"{S.MODE_NAMES[m] if m < len(S.MODE_NAMES) else m}/0x{p:02X}@{t}s" for t, m, p in seen))
        sw = swlog(bus, say)
        sl = synclog(a, bus, say)
        want = 3 if case == "cmd" else 1                       # switch-log 0xB8 arg, sync.tsv DF row
        lines = (not any(ln.endswith("refused: no cable on D2") for ln in sl)) if want == 1 else \
            (not any("auto search" in ln for ln in sl))
        if (0xB8, want) not in sw or lines:
            say(f"{case}: FAIL log line missing (switch-log 0xB8 arg {want}, sync log DF)")
            return False
        ok = ms == 3 and port == D3
        say(f"{case}: {'PASS' if ok else 'FAIL'} {a.bin.name}: end {S.MODE_NAMES[ms] if ms < len(S.MODE_NAMES) else ms} "
            f"port 0x{port:02X} (want ACTIVE on D3 0x{D3:02X}) after {a.secs:g} s")
        return ok
    finally:
        bus.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", choices=["vcp", "sel", "cmd", "all"], default="all")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--sync-tsv", dest="sync_tsv", type=Path, help="default: the .sync.tsv beside the map / $AWTO_SYNC_TSV")
    ap.add_argument("--secs", type=float, default=16.0, help="NOSIGNAL ~2 s + PS ~10 s after a switch (#84 log), then margin")
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (S.ROOT / "tmp/logs/deadport_sim.log").open("a", buffering=1)

    def say(s):
        print(s); log.write(s + "\n")

    rc = 0
    for case in (["vcp", "sel", "cmd"] if a.case == "all" else [a.case]):
        rc |= 0 if run_case(a, case, say) else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
