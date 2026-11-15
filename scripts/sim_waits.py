#!/usr/bin/env python3
"""Blocking waits on the boot path, with their callers (fw_sim, #216): reset -> ACTIVE.

usage: sim_waits.py BIN MAP [--mode 1080p60|2160p60] [--until-active] [--top 25]
  Watches ScalerTimerDelayXms (fixed software delays: the argument is real time on the unit), ScalerTimerPollingFlagProc (bound
  = the timeout argument; the sim answers at once, the unit takes as long as the hardware needs) and ScalerTimerWaitForEvent
  (frame / sync events). Per caller: calls, summed delay ms. Caller = the return address on the 8051 stack at the entry,
  resolved to a function with the current bank (a common-code callee runs in the caller's bank).
Log: ./tmp/logs/sim_waits.log
"""
import argparse, bisect, collections, re, sys
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

LOG = S.ROOT / "tmp/logs/sim_waits.log"
SFR_SP = 0x81
COMMON_END = 0x5000       # fw/rl6449_memory.toml common_end: below it the address is the same in every bank
BANK_SIZE = 0x10000


def chunk_table(map_path: Path):
    """sorted flat address -> name of every code chunk start in the map: globals (`_name`) and statics (area `s_CH_<name>`)"""
    rows = []
    for l in map_path.read_text(errors="replace").splitlines():
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(?:s_CH_|s_ST_|_)(\w+)", l)
        if m:
            rows.append((int(m.group(1), 16), m.group(2)))
    rows.sort()
    return [r[0] for r in rows], [r[1] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    bus = S.SimBus(a.bin, a.map, video=a.mode, port="D2", boot=False)
    m = bus.m
    rows = []                                              # (fw ms, kind, arg, caller)
    starts, names = chunk_table(a.map)

    def caller(bank, pc):
        flat = pc if pc < COMMON_END else bank * BANK_SIZE + pc
        i = bisect.bisect_right(starts, flat) - 1
        return names[i] if i >= 0 else f"?{flat:x}"

    def watch(kind):
        def fn(m_, r):
            sp = m.rd(SFR_SP, 1, "sfr")[0]
            lo, hi = m.rd(sp - 1, 2, "iram")               # LCALL pushes PCL then PCH
            rows.append((bus.now() * 1000, kind, r["a1"] & 0xFFFF, caller(m.p.bank, hi << 8 | lo)))
            return None                                    # watch only: the function runs
        return fn

    for name in ("ScalerTimerDelayXms", "ScalerTimerPollingFlagProc", "ScalerTimerWaitForEvent"):
        m.stub(name, watch(name.replace("ScalerTimer", "")))
    bus.boot()                                             # to ACTIVE
    t_end = bus.now() * 1000
    LOG.parent.mkdir(parents=True, exist_ok=True)
    out = [f"{a.bin.name}: reset -> ACTIVE at {t_end:.0f} ms (sim clock)"]
    for kind in ("DelayXms", "PollingFlagProc", "WaitForEvent"):
        per = collections.defaultdict(lambda: [0, 0])
        for t, k, arg, who in rows:
            if k == kind:
                per[who][0] += 1
                per[who][1] += arg if kind == "DelayXms" else 0
        total = sum(v[1] for v in per.values())
        out.append(f"{kind}: {sum(v[0] for v in per.values())} calls" + (f", {total} ms in all" if kind == "DelayXms" else ""))
        for who, (n, ms) in sorted(per.items(), key=lambda x: (-x[1][1], -x[1][0]))[:a.top]:
            out.append(f"   {n:4d} calls" + (f"  {ms:5d} ms" if kind == "DelayXms" else "          ") + f"  {who}")
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + "\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
