#!/usr/bin/env python3
"""#84 dead-port cases in the fw_sim model: a single-cable unit must not be switched to a port with no cable and stay there.

usage: deadport_sim.py BIN MAP [--case key|cmd|all] [--mode 1080p60] [--secs 16]
  Board: HDMI source on D3 (the only cable; D1 / D2 cable pins read unplugged), boot to ACTIVE on D3.
  key  EXIT key with no menu (mailbox KEY = VCP 0xE4, the firmware key path) = #60 "next input".
       PASS: still ACTIVE on D3 after --secs (swap7: fixed port D1, NOSIGNAL -> POWER_SAVING, never back).
  cmd  test cmd 0x32 (switch to D2, fixed port; test cmds are not refused).
       PASS: back to ACTIVE on D3 within --secs (guard: fixed port, no cable, no signal -> auto search).
  Prints the switch log (g_stAwtoSw) decoded with sw_timeline.name.
Log: tmp/logs/deadport_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import menu_cli as MC  # noqa: E402
import settings_cli as C  # noqa: E402
import sw_timeline as T  # noqa: E402

D3 = 6                                  # Global.h _D3_INPUT_PORT
TESTCMD = 0xF6F8                        # g_stAwtoDiag + 0x28
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


def swlog(bus, say):
    raw = bus.xdata(bus.addr("g_stAwtoSw"), 12 + 4 * T.N_EV)
    hdr, evs = T.decode(raw, bus.be) if hasattr(T, "decode") else (None, [])
    for ms, i, g in evs[-40:]:
        say(f"  +{ms:6d} ms  {T.name(i, g)}")


def run_case(a, case: str, say) -> bool:
    bus = S.SimBus(a.bin, a.map, video=a.mode, port="D3", devs=[Pins(NOCABLE_D1)])
    try:
        if not bus.run_until_mode(3):
            say(f"{case}: FAIL no ACTIVE at boot"); return False
        say(f"{case}: ACTIVE on port 0x{port_now(bus):02X}, cable status 0x{bus.xdata(bus.addr('g_stPortCableStatus'))[0]:02X} "
            "(bit4 D1, bit5 D2, bit6 D3)")
        bus.wait(1.0)
        if case == "key":
            mt = a.map.read_text(errors="replace")
            MC.Menu(C.Box(bus, mt, True), mt, True).box.call(3, MC.OPS["key"], MC.KEYS["exit"])
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
        swlog(bus, say)
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
    ap.add_argument("--case", choices=["key", "cmd", "all"], default="all")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--secs", type=float, default=16.0, help="NOSIGNAL ~2 s + PS ~10 s after a switch (#84 log), then margin")
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (S.ROOT / "tmp/logs/deadport_sim.log").open("a", buffering=1)

    def say(s):
        print(s); log.write(s + "\n")

    rc = 0
    for case in (["key", "cmd"] if a.case == "all" else [a.case]):
        rc |= 0 if run_case(a, case, say) else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
