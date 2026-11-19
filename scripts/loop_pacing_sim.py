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
    ap.add_argument("--settle", type=float, default=5.0, help="fw seconds after ACTIVE before the window (the boot console closes after 3 s)")
    ap.add_argument("--bench", metavar="LABEL", help="append a row to docs/speed-bench.tsv: pacing_ms, passes_s_idle, busy_pct_idle, worst_ms_idle (idle ACTIVE, last 1 s window)")
    ap.add_argument("--mode", default="1080p60")
    a = ap.parse_args()
    mapp = a.map or a.bin.with_suffix(".map")
    bus = S.SimBus(a.bin, mapp, "pace-" + a.bin.stem, None, video=a.mode)
    if not bus.run_until_mode(3):
        say(f"FAIL {a.bin.name}: never reached ACTIVE")
        return 1
    bus.wait(a.settle)
    p = bus.m.p
    d0, c0, i0, k0, n0, t0 = bus.diag(), p.clk, p.instr, p.idle_clk, p.nidle, time.perf_counter()
    q0 = p.nirq
    m = re.search(r"^[XD]:\s+([0-9A-Fa-f]+)\s+_?g_stAwtoHead\b", Path(mapp).read_text(), re.M)
    for _ in range(int(a.window)):                      # per-second headroom rows of the window
        bus.wait(1.0)
        if m:
            w = [int.from_bytes(bytes(bus.m.rd(int(m.group(1), 16) + 2 * i, 2)), "big" if bus.be else "little") for i in range(6)]
            say(f"  t+: {w[0]} passes/s, sleep {w[1] / 10:.1f} %, worst {w[2] / 16:.2f} ms, hold {w[3] / 10:.1f} %, {w[4]} idles, {w[5]} wake-bit")
    host = time.perf_counter() - t0
    d1 = bus.diag()
    hb, t2 = (d1["hb"] - d0["hb"]) & 0xFFFF, (d1["t2"] - d0["t2"]) & 0xFFFF
    clk, idle = p.clk - c0, p.idle_clk - k0
    say(f"{a.bin.name} {a.mode}: {hb} passes in {t2} fw ms = {hb * 1000 / max(t2, 1):.1f} /s, "
        f"duty {100 * (1 - idle / max(clk, 1)):.1f} % (idle {idle} of {clk} clk, {p.nidle - n0} idles), "
        f"{p.instr - i0} instr, {(p.nirq - q0) * 1000 / max(t2, 1):.0f} IRQ/s, host {host:.1f} s for {t2} fw ms (sim/host {t2 / 1000 / host:.2f})")
    if m:                                               # headroom counters of the last 1 s window (AWTO_LOOP_PACING image)
        w = [int.from_bytes(bytes(bus.m.rd(int(m.group(1), 16) + 2 * i, 2)), "big" if bus.be else "little") for i in range(6)]
        say(f"  headroom (last 1 s): {w[0]} passes, sleep {w[1] / 10:.1f} % (busy {100 - w[1] / 10:.1f} %), worst busy pass {w[2] / 16:.2f} ms, "
            f"free-run (busy hook) {w[3] / 10:.1f} % of passes, {w[4]} IDL exits, {w[5]} passes by wake bit")
    if a.bench and m:
        import subprocess
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        period = re.search(r"-lp(\d+)-", a.bin.name)
        row = [isostamp.now(), sha, a.bin.stem, a.bench] + [""] * 12 + [period.group(1) if period else "0", str(w[0]), f"{100 - w[1] / 10:.1f}", f"{w[2] / 16:.2f}"]
        with (ROOT / "docs/speed-bench.tsv").open("a") as f:
            f.write("\t".join(row) + "\n")
    bus.m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
