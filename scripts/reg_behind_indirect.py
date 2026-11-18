#!/usr/bin/env python3
"""Read-behind candidate 3: read the scaler page through the MCU host interface FFF4 (index) / FFF5 (data) instead of a direct XFR MOVX.

usage: reg_behind_indirect.py --unit N [--pages A0,8E,CE] [--pairs 12]
  Truth from the direct path (d2 == d3). Indirect: write page index to 0x009F, FFF4 = offset, read FFF5 (auto-increment on,
  FFF3[5] = 0). Pairs X -> Y: FFF4 = X, read FFF5, FFF4 = Y, read FFF5 -> first read of the new dword ok / stale.
  Writes: 009F (restored), FFF4 (restored). WRITES the unit: test units only (Dan 2026-11-19: unit 1 allowed).
  Result JSON tmp/regs/live/<serial>-behindind-<stamp>.json, log tmp/logs/reg_behind_indirect.log.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import reg_behind_cause as C
import reg_behind_fix as F
import reg_live_scan as S

PAGE_REG, IDX, DAT = 0x009F, 0xFFF4, 0xFFF5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--pages", default="A0,8E,CE")
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--bus", type=int)
    a = ap.parse_args()
    import dbg_link
    import rtd_i2c_bridge
    u = S.unit_info(a.unit)
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    out = S.ROOT / f"tmp/regs/live/{u['serial']}-behindind-{time.strftime('%Y%m%d-%H%M%S')}.json"
    res = {"serial": u["serial"], "start": isostamp.now(), "pages": {}}
    F.log(f"indirect start {res}")
    res["link"] = dbg_link.on(bus, 15)
    io = rtd_i2c_bridge.Real(bus, allow_write=True)
    saved = (F.rd(io, PAGE_REG), F.rd(io, IDX), F.rd(io, 0xFFF3))
    res["saved"] = saved
    F.log(f"saved 009F/FFF4/FFF3 = {saved}")
    failed = None
    try:
        with (S.ROOT / "tmp/logs/reg_behind_cause.log").open("a") as lf:
            r = C.Rd(io, lf)
            for ps in a.pages.split(","):
                p = int(ps, 16)
                d = C.sample_dwords(r, p, a.pairs)
                prs = C.pairs_of(d, a.pairs)
                tally = {"dir_first": [0, 0, 0], "ind_first": [0, 0, 0], "ind_lanes": [0, 0, 0, 0], "ind_n": [0, 0, 0, 0]}
                for x, y in prs:
                    tx, ty = d[x], d[y]
                    C.settle(r, x)
                    v = r.rd(y, "direct-first")
                    tally["dir_first"][0] += 1
                    tally["dir_first"][1] += v == ty[0]
                    tally["dir_first"][2] += v == tx[0]
                    for ln_first in (0, 2):
                        if not (F.wr(io, PAGE_REG, p) and F.wr(io, IDX, x & 0xFF)):
                            failed = "stage write"
                            break
                        xs = [F.rd(io, DAT) for _ in range(4)]          # X lanes via auto-increment
                        if not F.wr(io, IDX, (y & 0xFF) + ln_first):
                            failed = "index write"
                            break
                        first = F.rd(io, DAT)
                        if ty[ln_first] != tx[ln_first]:
                            tally["ind_first"][0] += 1
                            tally["ind_first"][1] += first == ty[ln_first]
                            tally["ind_first"][2] += first == tx[ln_first]
                        res.setdefault("sample", []).append([f"{x:04X}", f"{y:04X}", ln_first, xs, first, ty[ln_first]])
                    if failed or not F.heartbeat(io):
                        failed = failed or "heartbeat"
                        break
                res["pages"][ps] = tally
                F.log(f"page {ps}: pairs {len(prs)} {tally}")
                out.write_text(json.dumps(res))
                if failed:
                    break
    finally:
        ok = F.wr(io, IDX, saved[1]) and F.wr(io, PAGE_REG, saved[0]) and F.heartbeat(io)
        res["restored"], res["failed"] = ok, failed
        F.log(f"restore 009F/FFF4: {ok} failed={failed}")
        io.close()
        res["link_off"] = dbg_link.off(bus)
        out.write_text(json.dumps(res))
    print(out)
    return 0 if ok and not failed else 2


if __name__ == "__main__":
    sys.exit(main())
