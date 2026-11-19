#!/usr/bin/env python3
"""Flash clock default (docs/clock-sweep.md "Default flash clock"): boot order and end state of FF6C / FFE9 / FFED in fw_sim.

usage: flash_clk_sim.py BIN [--map MAP] [--f2 N] [--tune HEX]
  Taps FF6C writes and the flash divider changes (sim_clock.f2_log) from reset to ACTIVE and checks:
    - end state: FFE9[3:0] = F2 (default 3 = 116.9 MHz of the 350.8 MHz M2PLL), FF6C[5:2] = the fast tune (latch_so_rise 1, drive_si_fall 1, si_dly_sel 1 = 0x34),
    - the fast tune is written before the CPU clock becomes the M2PLL (set on the crystal: no transient at the fast clock),
    - on the M2PLL every (F2, tune) state is a proven pair; flash write sessions switch F2 to 5 and back.
  Sim: the cache stall model follows FFE9 (sim_clock.py ratio_x256 = F2 / M); reports sim ns per cache line fill (168 flash clocks) next to the measured value.
Exit 1 on a failed check. Log: ./tmp/logs/flash_clk_sim.log
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S

LOG = S.ROOT / "tmp/logs/flash_clk_sim.log"
A_TUNE, A_F2, A_SRC = 0xFF6C, 0xFFE9, 0xFFED
TUNE_MASK = 0x3C
AWTO_SLOW = 0x20                        # stock tune: latch_so_rise 1, drive_si_fall 0, si_dly_sel 0
WR_F2 = 5                               # flash writes / erases: 350.8 / 5 = 70.2 MHz
PROVEN = {(2, 0x20), (3, 0x34), (3, 0x20), (4, 0x34), (4, 0x20), (5, 0x20)}   # (F2, FF6C[5:2]) pairs passed on unit 3 (clk_sweep.tsv oc117 / oc88 l1_f1_d1 + l1_f0_d0; stock tune at 70.2)
M2PLL_KHZ = 350790                      # 14318 kHz x 49 / 2
FILL_FLASH_CLK = json.loads((Path(__file__).resolve().parent / "dw8051_model.json").read_text())["flash_fetch"]["fill_flash_clk"]   # measured, see the model's fill_source


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


class Tap(S.Dev):
    writes = (A_TUNE, A_F2, A_SRC)

    def __init__(self):
        self.rows = []                  # (instr, addr, value, source_is_m2pll after the write)

    def on_write(self, m, a):
        v = m.rd(a)[0]
        self.rows.append((m.instr, a, v, bool(m.rd(A_SRC)[0] & 0x02)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--f2", type=int, default=None, help="expected FFE9[3:0] (default: whatever the build set; the tune is then 0x34 with the write switch in the image, else 0x20)")
    ap.add_argument("--tune", type=lambda s: int(s, 16), default=None)
    a = ap.parse_args()
    a.map = a.map or a.bin.with_suffix(".map")
    tap = Tap()
    bus = S.SimBus(a.bin, a.map, devs=[tap], video="1080p60", boot=False)
    fails = 0

    def check(name, ok, detail=""):
        nonlocal fails
        fails += not ok
        say(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    try:
        bus.boot()
        m = bus.m
        f2, tune = m.rd(A_F2)[0] & 0x0F, m.rd(A_TUNE)[0] & TUNE_MASK
        a.f2 = f2 if a.f2 is None else a.f2
        f2s = [f for _, f, p in m.clock.f2_log if p]
        fast_build = a.f2 < WR_F2 and WR_F2 in f2s        # write sessions seen = the 350 build with flash above 70 MHz: fast tune; otherwise the stock tune
        a.tune = (0x34 if fast_build else AWTO_SLOW) if a.tune is None else a.tune
        check("end state FFE9[3:0] = F2", f2 == a.f2, f"{f2} (want {a.f2})")
        check("end state FF6C[5:2] = fast tune", tune == a.tune, f"0x{tune:02X} (want 0x{a.tune:02X})")
        # flash-write sessions on the M2PLL: slow tune -> F2 5 ... F2 back -> fast tune (every transient pair is a proven one)
        ev = sorted([(r[0], "T", r[2] & TUNE_MASK, r[3]) for r in tap.rows if r[1] == A_TUNE] + [(i, "F", f, p) for i, f, p in m.clock.f2_log])
        cur_f2, cur_tune, bad, pairs, sessions = None, None, [], set(), 0
        for _, k, v, pll in ev:
            if k == "F":
                cur_f2 = v
            else:
                cur_tune = v
                if pll:
                    pairs.add((cur_f2, v))
                    sessions += v == AWTO_SLOW
            if pll and cur_f2 is not None and cur_tune is not None and (cur_f2, cur_tune) not in PROVEN:
                bad.append((cur_f2, cur_tune))
        check("every (F2, tune) state on the M2PLL is a proven pair", not bad, f"{sorted(set(bad))}; seen {sorted(pairs)}")
        check("write sessions run F2 5 and return to the fast F2 (none when the build is in spec)", bool(f2s) and f2s[-1] == a.f2 and ((WR_F2 in f2s) if fast_build else set(f2s) == {a.f2}), f"{sessions} sessions, F2 on M2PLL {f2s[:6]}... last {f2s[-1] if f2s else None}")
        first_pll = next((i for i, r in enumerate(tap.rows) if r[3]), None)
        fast = next((i for i, r in enumerate(tap.rows) if r[1] == A_TUNE and (r[2] & TUNE_MASK) == a.tune), None)
        check("fast tune written before the M2PLL is the CPU clock", first_pll is not None and fast is not None and fast < first_pll, f"tune row {fast}, first M2PLL row {first_pll}")
        flash_khz = M2PLL_KHZ / max(1, f2)
        say(f"INFO sim cache line fill = {FILL_FLASH_CLK} flash clocks = {FILL_FLASH_CLK * 1e6 / flash_khz:.0f} ns at {flash_khz / 1000:.1f} MHz "
            f"(ratio_x256 {bus.m.clock.ratio_x256 if hasattr(bus.m, 'clock') else '?'}); unit 3 meter (176 CPU cycles + the fill) 1404 ns at 350.8 / 70.2, 1099 ns at 350.8 / 116.9")
    finally:
        bus.close()
    say(f"{'PASS' if not fails else 'FAIL'} flash_clk_sim {a.bin.name}: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
