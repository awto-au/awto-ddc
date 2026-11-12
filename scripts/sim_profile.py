#!/usr/bin/env python3
"""Where the fw_sim wall time goes (boot to ACTIVE + N s of firmware time): ucsim round trips by cause, device-event
addresses, stub hits, PC-sample histogram per function.

usage: sim_profile.py BIN MAP [--mode 2160p60] [--secs 3] [--chunk 20000] [--top 20]
Log: tmp/logs/sim_profile.log
"""
import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60")
    ap.add_argument("--secs", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--ffwd", action="store_true")
    a = ap.parse_args()
    lf = (S.ROOT / "tmp/logs/sim_profile.log").open("a", buffering=1)

    def say(s):
        print(s); lf.write(s + "\n")

    t0 = time.monotonic()
    bus = S.SimBus(a.bin, a.map, video=a.mode, boot=False, ffwd=a.ffwd)
    m = bus.m
    stats = Counter()
    evaddr = Counter()
    cmd0 = m.cmd

    def cmd(c, *k, **kw):
        stats["ucsim cmd " + c.split()[0]] += 1
        out = cmd0(c, *k, **kw)
        for kind, sp, ad in re.findall(r"Event `(\w+)' at (xram|sfr)\[0x([0-9a-f]+)\]", out):
            evaddr[f"{kind} {sp}[0x{ad}]"] += 1
        if "Breakpoint" in out:
            stats["breakpoint stops"] += 1
        return out
    m.cmd = cmd
    hist = Counter()
    phase = {}
    for name, until in (("boot->ACTIVE", None), (f"+{a.secs:g}s fw time", a.secs)):
        t1, i1 = time.monotonic(), m.instr
        if until is None:
            used = 0
            while bus.mode_state() != 3 and used < 150_000_000:
                out = m.run(200_000); used += 200_000
                mt = re.search(r"0x([0-9a-f]{4,6}) ", out or "")
        else:
            bus.wait(until)
        phase[name] = (time.monotonic() - t1, m.instr - i1)
    say(f"=== {a.bin.name} {a.mode} (wall incl. setup {time.monotonic() - t0:.1f} s) ===")
    for k, (dt, n) in phase.items():
        say(f"{k:16s} {dt:7.1f} s wall  {n / 1e6:7.1f} M instr  {n / max(dt, 1e-9) / 1e6:5.2f} M instr/s")
    for k, v in stats.most_common(12):
        say(f"  {v:8d}  {k}")
    say("  top device-event addresses:")
    for k, v in evaddr.most_common(a.top):
        say(f"  {v:8d}  {k}")
    say(f"  stub hits: {dict(sorted(m.stub_hits.items(), key=lambda kv: -kv[1])[:a.top])}")
    bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
