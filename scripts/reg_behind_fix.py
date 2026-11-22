#!/usr/bin/env python3
"""Candidate-register test for the read-behind artifact (unit with a debug link; WRITES one register, restores it).

usage: reg_behind_fix.py --unit N --reg FFBC --values 10,14,1F [--restore 0F] [--pages A0,8E,88,CE] [--pairs 12] [--force]
  Per value: write REG (debug slave 0x01 hi / 0x03 val / 0x3B lo), read it back, heartbeat (0x0000 == 0xCF), diag loop
  rate (0xF6D0 + 0x2A), reg_behind_cause.run_page on the pages, block read rate on page 00 and on 8E, heartbeat, restore,
  read back. Stops at the first failed write / read-back / heartbeat (restore attempted; link loss: the firmware WDT resets
  the unit). Result JSON: tmp/regs/live/<serial>-behindfix-<REG>-<stamp>.json; log tmp/logs/reg_behind_fix.log.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import isostamp
import reg_behind_cause as C
import reg_live_scan as S
from _log import log_line as _log_line

LOG = S.ROOT / "tmp/logs/reg_behind_fix.log"
DIAG_LOOP = 0xF6D0 + 0x2A                 # u16 main-loop passes in the last ~1 s
BLK_N = 300                               # blocks per rate measurement


def log(s: str) -> None:
    _log_line(s, LOG)


def wr(io, addr: int, val: int) -> bool:
    return (io.write(X.DEV8, X.CMD_HI, bytes([addr >> 8])) and io.write(X.DEV8, X.CMD_HI + 2, bytes([val]))
            and io.write(X.DEV8, 0x3B, bytes([addr & 0xFF])))


def rd(io, addr: int) -> int | None:
    b = X.read_bytes(io, addr, 1)
    return None if b is None else b[0]


def heartbeat(io) -> bool:
    return rd(io, S.ID_ADDR) == S.ID_VALUE


def loop_rate(io) -> int | None:
    b = X.read_bytes(io, DIAG_LOOP, 2)
    return None if b is None else b[0] | b[1] << 8


def blk_rate(io, addr: int) -> float | None:
    """us per 24-byte block read (host + I2C included; the difference between two register values is the stall cost)."""
    t = time.perf_counter()
    bad = 0
    for _ in range(BLK_N):
        bad += X.read_chunk(io, addr, X.BLK_MAX, tries=1) is None
    return None if bad > BLK_N // 10 else (time.perf_counter() - t) / BLK_N * 1e6


def summary(rec: dict) -> dict:
    o = rec["order"]
    first = [v for k, v in o.items() if k.split(":")[1] == "0"]
    n = sum(v[0] for v in first)
    return {"first_read_informative": n, "first_read_ok": sum(v[1] for v in first), "first_read_stale": sum(v[2] for v in first)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--reg", default="FFBC")
    ap.add_argument("--values", default="10,14,1F")
    ap.add_argument("--restore", default="0F")
    ap.add_argument("--pages", default="A0,8E,88,CE")
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--minutes", type=int, default=20)
    a = ap.parse_args()
    import dbg_link
    import rtd_i2c_bridge
    u = S.unit_info(a.unit)
    bus = a.bus if a.bus is not None else S.resolve_bus(u)
    reg, restore = int(a.reg, 16), int(a.restore, 16)
    out = S.ROOT / f"tmp/regs/live/{u['serial']}-behindfix-{a.reg}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = {"serial": u["serial"], "bus": bus, "reg": a.reg, "restore": a.restore, "start": isostamp.now(), "steps": []}
    log(f"start {res}")
    res["link"] = dbg_link.on(bus, a.minutes)
    io = rtd_i2c_bridge.Real(bus, allow_write=True)
    failed = None
    try:
        res["base"] = {"reg": rd(io, reg), "loop": loop_rate(io), "blk00_us": blk_rate(io, 0x0000), "blk8E_us": blk_rate(io, 0x8E00)}
        log(f"base {res['base']}")
        for vs in [a.restore] + a.values.split(","):
            v = int(vs, 16)
            step = {"value": vs}
            res["steps"].append(step)
            if not wr(io, reg, v):
                failed = f"write {a.reg}={vs} no ack"
                break
            step["readback"] = rd(io, reg)
            step["hb_before"] = heartbeat(io)
            if step["readback"] != v or not step["hb_before"]:
                failed = f"{a.reg}={vs}: readback {step['readback']} heartbeat {step['hb_before']}"
                break
            step["loop"] = loop_rate(io)
            step["blk00_us"], step["blk8E_us"] = blk_rate(io, 0x0000), blk_rate(io, 0x8E00)
            pages: dict = {}
            with (S.ROOT / "tmp/logs/reg_behind_cause.log").open("a") as lf:
                r = C.Rd(io, lf)
                for ps in a.pages.split(","):
                    C.run_page(r, int(ps, 16), a.pairs, pages)
            step["pages"] = {pg: {"order": dict(rec["order"]), "gap": dict(rec["gap"]), "pairs": rec["pairs"]} for pg, rec in pages.items()}
            step["first_read"] = {pg: summary(rec) for pg, rec in pages.items()}
            step["hb_after"] = heartbeat(io)
            log(f"{a.reg}={vs}: loop {step['loop']} blk00 {step['blk00_us']} us blk8E {step['blk8E_us']} us first-read {step['first_read']} hb {step['hb_after']}")
            out.write_text(json.dumps(res))
            if not step["hb_after"]:
                failed = f"{a.reg}={vs}: heartbeat lost after the pages"
                break
    finally:
        ok = False
        try:
            ok = wr(io, reg, restore) and rd(io, reg) == restore and heartbeat(io)
        except OSError as e:
            log(f"restore raised {e}")
        res["restored"], res["failed"], res["end"] = ok, failed, isostamp.now()
        log(f"restore {a.reg}={a.restore}: {ok}; failed={failed}")
        io.close()
        res["link_off"] = dbg_link.off(bus)
        out.write_text(json.dumps(res))
    print(out)
    return 0 if ok and not failed else 2


if __name__ == "__main__":
    sys.exit(main())
