#!/usr/bin/env python3
"""#84 dead-port cases in the fw_sim model: a single-cable unit must not be switched to a port with no cable and stay there.

usage: deadport_sim.py BIN MAP [--case vcp|sel|cmd|all] [--mode 1080p60] [--secs 16]
  Board: HDMI source on D3 (the only cable; D1 / D2 cable pins read unplugged), boot to ACTIVE on D3.
  vcp  DDC/CI set VCP 0x60 = 0x11 (D2) over the spare IIC engine. PASS: refused, still ACTIVE on D3 after --secs.
  sel  front keys: SOURCE opens the selector (on Auto), 2x DOWN steps to D2, AUTO takes it (no cable on D2, Dan 2026-11-19:
       taken anyway). PASS: still on D2 without a picture after --secs (inside AWTO_SRC_NOCABLE_HOLD_MS), "taken, no cable" line.
  selhold  as sel, --secs past AWTO_SRC_NOCABLE_HOLD_MS: PASS: D2 held, then the dead-port auto search is back ACTIVE on D3.
  cmd  test cmd 0x32 (switch to D2, fixed port; test cmds are not refused).
       PASS: back to ACTIVE on D3 within --secs (guard: fixed port, no cable, no signal -> auto search).
  Each case also needs its log line: switch-log 0xB8 (vcp / sel: arg 1, cmd: arg 3) and the sync-log line (sync.tsv DF; sel: E0 06).
  Prints the switch log (isr_g_stAwtoSw) decoded with sw_timeline.name.
Log: tmp/logs/deadport_sim.log
"""
import argparse
import sys
from pathlib import Path

from _log import Logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddc_sim as DD
import fw_sim as S
import sw_timeline as T
import sync_log as SL

D3 = 6                                  # Global.h _D3_INPUT_PORT
D2 = 5
TESTCMD = 0xF6F8                        # isr_g_stAwtoDiag + 0x28
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
    raw = bus.xdata(bus.addr("isr_g_stAwtoSw"), 12 + 4 * T.N_EV)
    _hdr, evs = T.decode(raw, bus.be) if hasattr(T, "decode") else (None, [])
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


class Rig:
    """One booted unit (ACTIVE on D3 + 1 s) kept as a snapshot: each case starts from it, as from a fresh boot (tests/test_sim_snapshot.py)."""

    def __init__(self, a):
        self.eng = DD.DdcEngine()
        cells = {**NOCABLE_D1, **({0xFE32: 0} if a.d2_cabled else {})}
        self.bus = S.SimBus(a.bin, a.map, video=a.mode, port="D3", devs=[Pins(cells), self.eng])
        self.up = self.bus.run_until_mode(3)
        self.pre = ""
        if self.up:
            self.pre = (f"ACTIVE on port 0x{port_now(self.bus):02X}, cable status 0x{self.bus.xdata(self.bus.addr('g_stPortCableStatus'))[0]:02X} "
                        "(bit4 D1, bit5 D2, bit6 D3)")
            self.bus.wait(1.0)
            self.snap = self.bus.snapshot()
        self.fresh = True

    def start(self):
        if not self.fresh:
            self.bus.restore(self.snap)
        self.fresh = False
        return self.bus, self.eng


def run_case(a, case: str, say, rig) -> bool:
    bus, eng = rig.start()
    try:
        if not rig.up:
            say(f"{case}: FAIL no ACTIVE at boot"); return False
        say(f"{case}: {rig.pre}")
        if case == "vcp":
            DD.Mccs(bus, eng).set(0x60, 0x11)
        elif case in ("sel", "selhold"):
            if bus.m.rd(bus.addr("g_stAwtoGpio") + 3)[0] | bus.m.rd(bus.addr("g_stAwtoKey") + 3)[0]:
                tap(bus, KEY_MENU)                  # the sync console opened by itself at ACTIVE: MENU closes it, the rest is swallowed
            tap(bus, KEY_SOURCE)
            tap(bus, KEY_DOWN)                      # opens on Auto (auto scan): DOWN wraps to D3, then D2
            tap(bus, KEY_DOWN)
            tap(bus, KEY_AUTO)
        else:
            bus.m.wr(TESTCMD, bytes([0x32]))
        t0, seen, early = bus.now(), [], None
        while bus.now() - t0 < a.secs:
            bus.wait(0.25)
            st = (bus.mode_state(), port_now(bus))
            if early is None and st[0] != 3 and st[0] != 0:
                early = synclog(a, bus, lambda _s: None)       # the ring wraps by the end (power-saving episode): keep the take's lines
            if not seen or seen[-1][1:] != st:
                seen.append((round(bus.now() - t0, 2), *st))
        ms, port = bus.mode_state(), port_now(bus)
        say("  timeline: " + " -> ".join(f"{S.MODE_NAMES[m] if m < len(S.MODE_NAMES) else m}/0x{p:02X}@{t}s" for t, m, p in seen))
        sw = swlog(bus, say)
        sl = (early or []) + synclog(a, bus, say)
        want = {"cmd": 3, "sel": 4, "selhold": 4}.get(case, 1)  # switch-log 0xB8 arg; sync.tsv DF row (vcp, cmd), E0 06 (sel, #132)
        text = {"vcp": "refused:no cable on D2", "sel": "input selector:D2 taken, no cable: no-signal card, dead-port auto search held off",
                "selhold": "input selector:D2 taken, no cable: no-signal card, dead-port auto search held off"}.get(case)
        lines = (not any(ln.endswith(text) for ln in sl)) if text else (not any(ln.endswith("another port cabled:auto search") for ln in sl))
        if case == "selhold":
            lines = lines or not any(ln.endswith("another port cabled:auto search") for ln in sl)
        if (0xB8, want) not in sw or lines:
            say(f"{case}: FAIL log line missing (switch-log 0xB8 arg {want}, sync log {text or 'auto search'})")
            return False
        if case == "sel":
            ok = ms != 3 and port == D2 and not any(ln.endswith("another port cabled:auto search") for ln in sl)
            say(f"{case}: {'PASS' if ok else 'FAIL'} {a.bin.name}: end {S.MODE_NAMES[ms] if ms < len(S.MODE_NAMES) else ms} "
                f"port 0x{port:02X} (want no picture on D2 0x{D2:02X} inside the hold) after {a.secs:g} s")
            return ok
        ok = ms == 3 and port == D3
        say(f"{case}: {'PASS' if ok else 'FAIL'} {a.bin.name}: end {S.MODE_NAMES[ms] if ms < len(S.MODE_NAMES) else ms} "
            f"port 0x{port:02X} (want ACTIVE on D3 0x{D3:02X}) after {a.secs:g} s")
        return ok
    finally:
        pass                                    # the rig owns the bus


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", choices=["vcp", "sel", "selhold", "cmd", "all"], default="all")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--sync-tsv", dest="sync_tsv", type=Path, help="default: the .sync.tsv beside the map / $AWTO_SYNC_TSV")
    ap.add_argument("--d2-cabled", action="store_true", help="test hook (tests/test_gate_mutations.py): a cable on D2, so a switch to it is allowed and the gate must FAIL")
    ap.add_argument("--secs", type=float, default=16.0, help="NOSIGNAL ~2 s + PS ~10 s after a switch (#84 log), then margin; selhold: hold 30 s x1.25 + margin")
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = Logger(S.ROOT / "tmp/logs/deadport_sim.log", stamp_echo=False)

    say = log.say

    rc, secs, rig = 0, a.secs, Rig(a)
    try:
        for case in (["vcp", "sel", "selhold", "cmd"] if a.case == "all" else [a.case]):
            a.secs = max(secs, 40.0) if case == "selhold" else secs      # selhold: AWTO_SRC_NOCABLE_HOLD_MS 30 s + the search after it; the others keep --secs
            rc |= 0 if run_case(a, case, say, rig) else 1
    finally:
        rig.bus.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
