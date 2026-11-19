#!/usr/bin/env python3
"""Main-loop pacing in the sim (docs/main-loop-pacing.md): passes/s, CPU duty (1 - idle clk / clk), sim speed, per image.

usage: loop_pacing_sim.py BIN [MAP] [--window 3] [--mode 1080p60]
- boots to ACTIVE, settles 2 s fw, measures `--window` fw seconds: diag heartbeat (passes), Timer2 ms, core clk, idle clk (PCON.IDL entries),
  instructions, host seconds. Idle is modelled exactly in the fast core (dw8051): CPU halted until the next accepted IRQ, timers run.
- an image without AWTO_LOOP_PACING never writes PCON.IDL: idle 0, duty 100 %.
Log: tmp/logs/loop_pacing_sim.log
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

import isostamp

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AWTO_SIM_CORE", "fast")
import fw_sim as S  # noqa: E402

LOG = ROOT / "tmp/logs/loop_pacing_sim.log"


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = isostamp.now() + " " + s
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--window", type=float, default=3.0)
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    bus = S.SimBus(a.bin, mapp, "pace-" + a.bin.stem, None, video=a.mode)
    if not bus.run_until_mode(3):
        say(f"FAIL {a.bin.name}: never reached ACTIVE")
        return 1
    bus.wait(2.0)
    p = bus.m.p
    d0, c0, i0, k0, n0, t0 = bus.diag(), p.clk, p.instr, p.idle_clk, p.nidle, time.perf_counter()
    bus.wait(a.window)
    host = time.perf_counter() - t0
    d1 = bus.diag()
    hb, t2 = (d1["hb"] - d0["hb"]) & 0xFFFF, (d1["t2"] - d0["t2"]) & 0xFFFF
    clk, idle = p.clk - c0, p.idle_clk - k0
    say(f"{a.bin.name} {a.mode}: {hb} passes in {t2} fw ms = {hb * 1000 / max(t2, 1):.1f} /s, "
        f"duty {100 * (1 - idle / max(clk, 1)):.1f} % (idle {idle} of {clk} clk, {p.nidle - n0} idles), "
        f"{p.instr - i0} instr, host {host:.1f} s for {t2} fw ms (sim/host {t2 / 1000 / host:.2f})")
    m = re.search(r"^[XD]:\s+([0-9A-Fa-f]+)\s+_?g_stAwtoHead\b", Path(mapp).read_text(), re.M)
    if m:                                               # headroom counters of the last 1 s window (AWTO_LOOP_PACING image)
        w = [int.from_bytes(bytes(bus.m.rd(int(m.group(1), 16) + 2 * i, 2)), "big" if bus.be else "little") for i in range(3)]
        say(f"  headroom (last 1 s): {w[0]} passes, sleep {w[1] / 10:.1f} % (busy {100 - w[1] / 10:.1f} %), worst busy pass {w[2] / 16:.2f} ms")
    bus.m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
