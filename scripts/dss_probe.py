#!/usr/bin/env python3
"""DDR PHY speed sensor (DSS) read-out next to the IOSC trim counter, at stock and at a held clock step (docs/clock-sweep.md "temperature proxy").

usage: dss_probe.py --bus B --serial S --map MAP [--bin BIN] [--chan A|B] [--step STEP] [--reps N]
  Dan approved the write (2026-11-18): ONE channel, CTRL_3 (0xA753 / 0xAF53) <- Realtek 3-step sequence (rst_n 0 | rst_n 1 | speed_en 1) with ro_sel / wire_sel, poll STATUS_3 bit 0 (ready),
  count_out = STATUS_1[7:0] << 12 | STATUS_2[7:0] << 4 | STATUS_3[7:4] (regdb DC_PHY_SPEED_SENSOR_*). The original CTRL_3 byte is read first and written back at the end
  (also on an error). Nothing else is written. STEP = a clk_sweep step held while reading (host KEEP ops), default none (the running clock).
Log ./tmp/logs/dss_probe.log
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_sweep as C

BASE = {"A": 0xA750, "B": 0xAF50}
CTRL3, STAT1, STAT2, STAT3 = 3, 5, 6, 7                    # offsets from BASE
EN, RDY, WIRE, ROSH, RST_N = 0x40, 0x20, 0x10, 1, 0x01
READY_POLL_S = 0.5                                         # conversion time unknown (20-bit counter at dss_clk): first run measures it; expiry = logged, no count
VARIANTS = [(f"ro{ro} {w}", (ro << 1) | (0x10 if w == "short" else 0)) for ro in (1, 2, 3, 4, 5) for w in ("long", "short")]     # ctrl without speed_en / rst_n; ro_sel 001 NAND .. 101 mixed (regdb)


def rd(ctx, a: int, n: int = 1) -> bytes:
    b = ctx.rdabs(a, n)
    if b is None:
        raise RuntimeError(f"read 0x{a:04X} failed")
    return b


def read_count(ctx, base: int, ctrl: int) -> tuple[int | None, float, int]:
    """Realtek's sequence (Speed-Monitor.c on a sibling SoC, [sdk-hypothesis]): rst_n 0 + speed_en 0 with wire / ro set, rst_n 1, speed_en 1, poll ready, then speed_en 0 + rst_n 0."""
    C.xwr(ctx, base + CTRL3, ctrl)
    C.xwr(ctx, base + CTRL3, ctrl | RST_N)
    C.xwr(ctx, base + CTRL3, ctrl | RST_N | EN)
    t0 = time.monotonic()
    while time.monotonic() - t0 < READY_POLL_S:
        st = rd(ctx, base + STAT1, 3)
        if st[2] & 1:
            return (st[0] << 12) | (st[1] << 4) | (st[2] >> 4), time.monotonic() - t0, st[2]
    return None, time.monotonic() - t0, rd(ctx, base + STAT3)[0]


def sample(ctx, base: int, tag: str, reps: int, keep) -> list[int]:
    out = []
    for name, ctrl in VARIANTS:
        ctrl &= ~(EN | RST_N)
        vals = []
        for _ in range(reps):
            keep()
            cnt, dt, st3 = read_count(ctx, base, ctrl)
            C.xwr(ctx, base + CTRL3, ctrl | RST_N)              # speed_en 0
            C.xwr(ctx, base + CTRL3, ctrl)                      # rst_n 0
            vals.append(cnt)
            io = C.iosc(ctx, f"{tag} {name}")
            C.say(f"  dss {tag} {name} (CTRL_3 0x{ctrl:02X}): count_out {cnt} ready after {dt * 1000:.0f} ms, STATUS_3 0x{st3:02X} (wsort_go {(st3 >> 1) & 1}); IOSC trim_cnt {io['cnt'] if io else None}")
        got = [v for v in vals if v is not None]
        C.say(f"  dss {tag} {name}: {len(got)} of {reps} reads, min {min(got) if got else None} max {max(got) if got else None}")
        out += got
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--chan", choices=("A", "B"), default="A")
    ap.add_argument("--step")
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    import dbg_link
    import dbg_xdata
    import i2cbus
    import osd_hw_test as H
    import sync_log as S
    i2cbus.require_unit(a.bus, a.serial)
    base = BASE[a.chan]
    with dbg_link.linked(a.bus, 5):
        dev = H.Unit(a.bus, a.map)
        ck = copy.copy(dev)
        ck.base = S.sym(a.map, "g_stAwtoClk")

        def rdabs(addr, n):
            for _ in range(dev.RD_TRIES):
                r = dbg_xdata.read_blocks(dev.io, addr, n)
                if r is not None:
                    return r
            return None
        ctx = C.Ctx(dev, ck, rdabs, S.sym(a.map, "g_stAwtoSync"), None)
        orig = rd(ctx, base + CTRL3)[0]
        C.say(f"DSS channel {a.chan}: original CTRL_3 0x{orig:02X} (regdb reset value 0x01); step {a.step or 'running clock (no change)'}")
        keep = (lambda: None)
        try:
            if a.step:
                C.OPTS["fps"] = False
                f, f2, m, fl = C.STEPS[a.step]
                r = C.send(ctx, C.OP_APPLY, 6.0, f, f2, m, fl, hold_s=20.0, label=f"apply {a.step}", name_=a.step)
                if r is None or r[C.C_STATE] != C.ST_HELD:
                    C.say("step not held: no DSS read")
                    return 1
                last = [time.monotonic()]

                def keep():
                    if time.monotonic() - last[0] > 4.0:
                        C.send(ctx, C.OP_KEEP, 2.0, label="keep")
                        last[0] = time.monotonic()
            sample(ctx, base, a.step or "running", a.reps, keep)
        finally:
            C.xwr(ctx, base + CTRL3, orig)
            back = rd(ctx, base + CTRL3)[0]
            C.say(f"CTRL_3 restored: wrote 0x{orig:02X}, reads 0x{back:02X}: {'OK' if back == orig else 'MISMATCH'}")
            if a.step:
                C.send(ctx, C.OP_REVERT, 2.0, label="revert")
            dev.close()
    return 0 if back == orig else 1


if __name__ == "__main__":
    sys.exit(main())
