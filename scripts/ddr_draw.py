#!/usr/bin/env python3
"""awto-ddc#267: firmware-side DDR draw ops (fw/test/ddr_draw.c, freeze image only): one command from the host, the monitor draws.

usage: ./dev.py ddr-draw [--unit N] [--map F] [--no-prep] [--hold S] [--count] OP:key=val,... [OP:...]
  OPs (keys; SCREEN pixels, rgb = R/G/B 0..255): fill x y w h rgb | hline x y w rgb | vline x y h rgb | grid x y w n | circle x y w rgb
        figure x y | bars x y w h | frame rgb | gradh | gradv | masktest x y        e.g. fill:x=100,y=100,w=2000,h=1000,rgb=255/0/0
  Session (default): frame mode (0x0C), black host window, wait for it, freeze, the ops in order (each: fw ms, bursts, MB/s),
  hold (--hold S, default SCREEN_CAP_S), freeze off, window off, 0x0D, 0x27. --no-prep: only the ops (set-up done by hand).
  The ops run in the firmware main pass: params into g_stAwtoDraw (map symbol), ucGo last, poll ucGo == 0 (limit = 3 x est + margin).
Log: ./tmp/logs/ddr_frame_test.log
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddr_frame_test as T
import ddr_freeze_test as F
import sw_timeline as SW

OPS = {"fill": 1, "hline": 2, "vline": 3, "grid": 4, "circle": 5, "figure": 6, "bars": 7, "frame": 8, "gradh": 9, "gradv": 10, "masktest": 11,
       "addrfill": 12, "addrverify": 13, "addrwatch": 14}   # 12-14: params in g_stAwtoAddr (scripts/ddr_addr_test.py)
# StAwtoDraw (fw/test/ddr_draw.c), big endian
O_GO, O_SEQ, O_STATE, O_FROZEN, O_X, O_Y, O_W, O_H, O_R, O_G, O_B, O_N, O_MS, O_BURSTS, O_SLOW = 0, 1, 2, 3, 4, 6, 8, 10, 12, 13, 14, 15, 16, 18, 22
STATES = {0: "idle", 2: "ok", 3: "REFUSED (op unknown / empty / off screen)", 4: "STALL (CMD busy > 50 ms, aborted)"}
SCREEN_W, SCREEN_H, LINE_DOUBLE, BPP, BURST = 3840, 2160, 2, 3, 16
MCU_MHZ = 87.7                           # 351 MHz PLL / 4 (docs/diag-block.md)
EST_BURST_S = 1.7e-6                     # the issue's pessimistic per-burst figure (docs/data-channels.md row 3): limits only, not a result
EST_ADDR_BURST_S = 40e-6                 # address-in-data fill / read-back per burst: limit only (read burst ~25 MOVX + flag poll)
EST_SPAN_S = 20e-6                       # per DrwSpan call (address maths, mask), generous
LIMIT_MULT, LIMIT_MARGIN_S = 3.0, 0.5    # stall guard: 3 x the estimate (no measurement yet) + one main pass / I2C polls
PATTERN_SETTLE_S = 1.0                   # host window up + SDK mode settled (window draw ~0.3 s, mode change ~2 frames; limit 3x)
LIMIT_S = [0.0]                          # --limit-s: fixed stall limit for every op (estimates were off by 2-3x on hardware)
POLL_RETRY = 40                          # a debug-link read NAKs while the main pass is busy drawing


def est_s(op: str, p: dict) -> float:
    if op.startswith("addr"):
        return p.get("est_bursts", 0) * EST_ADDR_BURST_S
    w, h = p.get("w", 0), p.get("h", 0)
    lines = (min(h, SCREEN_H) + 1) // LINE_DOUBLE + 1
    if op == "fill":
        return lines * (EST_SPAN_S + EST_BURST_S * w * BPP / BURST)
    if op == "frame":
        return (SCREEN_H // LINE_DOUBLE) * (EST_SPAN_S + EST_BURST_S * SCREEN_W * BPP / BURST)
    if op == "gradh":
        return 240 * (SCREEN_H // LINE_DOUBLE) * (EST_SPAN_S + 3 * EST_BURST_S)
    if op == "gradv":
        return (SCREEN_H // LINE_DOUBLE) * (EST_SPAN_S + EST_BURST_S * SCREEN_W * BPP / BURST)
    return 0.3                           # lines, circle, grid, figure, bars, masktest: a few hundred bursts


class Draw:
    def __init__(self, d: T.Dbg, base: int):
        self.d, self.base = d, base

    def wr16(self, off: int, v: int) -> None:
        self.d.wr(self.base + off, v >> 8)
        self.d.wr(self.base + off + 1, v & 0xFF)

    def rd(self, off: int) -> int:
        for _ in range(POLL_RETRY):
            try:
                return self.d.rd(self.base + off)
            except OSError:
                pass
        raise OSError(f"debug read at +{off} failed {POLL_RETRY} times")

    def rd_n(self, off: int, n: int) -> int:
        return int.from_bytes(bytes(self.rd(off + i) for i in range(n)), "big")

    def run(self, op: str, p: dict) -> dict:
        d, b = self.d, self.base
        seq0 = self.rd(O_SEQ)
        for off, k in ((O_X, "x"), (O_Y, "y"), (O_W, "w"), (O_H, "h")):
            if k in p:
                self.wr16(off, p[k])
        r, g, bl = p.get("rgb", (0, 0, 0))
        for off, v in ((O_R, r), (O_G, g), (O_B, bl), (O_N, p.get("n", 0))):
            d.wr(b + off, v)
        t0 = time.monotonic()
        d.wr(b + O_GO, OPS[op])
        limit = LIMIT_S[0] or (LIMIT_MULT * est_s(op, p) + LIMIT_MARGIN_S)
        while self.rd(O_GO) != 0:
            if time.monotonic() - t0 > limit:
                T.log(f"{op}: ucGo still set after {time.monotonic() - t0:.2f} s (limit {limit:.2f} s = {LIMIT_MULT:g} x est {est_s(op, p):.2f} s + {LIMIT_MARGIN_S} s)")
                raise TimeoutError(op)
        wall = time.monotonic() - t0
        st, ms, bursts, slow = self.rd(O_STATE), self.rd_n(O_MS, 2), self.rd_n(O_BURSTS, 4), self.rd(O_SLOW)
        mbs = bursts * BURST / ms / 1000 if ms else float("nan")
        T.log(f"{op} {p}: state {STATES.get(st, st)}, seq {seq0} -> {self.rd(O_SEQ)}, frozen {self.rd(O_FROZEN)}, fw {ms} ms, {bursts} bursts "
              f"= {bursts * BURST} B -> {mbs:.2f} MB/s (fw ms tick 1 ms), slow CMD polls {slow}, host wall {wall * 1000:.0f} ms")
        return {"state": st, "ms": ms, "bursts": bursts, "mbs": mbs, "slow": slow}


def parse_op(tok: str) -> tuple[str, dict]:
    name, _, kv = tok.partition(":")
    if name not in OPS:
        raise SystemExit(f"unknown op {name!r}: {sorted(OPS)}")
    p: dict = {}
    for item in filter(None, kv.split(",")):
        k, _, v = item.partition("=")
        p[k] = tuple(int(c) for c in v.split("/")) if k == "rgb" else int(v, 0)
    return name, p


@contextlib.contextmanager
def session(a, d: T.Dbg, hold_s: float | None = None):
    """Host window, frame mode, freeze (the prep of ddr-draw); the body runs the ops; then hold, freeze off, window off, 0x0D, 0x27."""
    proc, t_on = None, time.monotonic()
    try:
        if not a.no_prep:
            if not a.no_pattern:                          # first: the host mode change resets the memory choice, 0x0C after it
                proc = F.pattern_start("solid 0 0 0")
                time.sleep(PATTERN_SETTLE_S)
            t_on = time.monotonic()
            F.frame_mode(d.io)
            if not a.no_pattern:
                F.wait_marker(d, 0, bytes([0] * 16))
            if getattr(a, "live", False):                 # ddr-addr --watch: the capture keeps running
                pass
            elif a.sdk_freeze:
                F.cmd(d.io, F.TC_FREEZE_ON)
            else:
                F.freeze(d.io, True)
        yield
        if not a.no_prep:
            t_h = time.monotonic()
            while time.monotonic() - t_h < (a.hold if hold_s is None else hold_s):
                F.prd(d.io, F.OVERLAY)
    finally:
        if a.sdk_freeze and not a.no_prep and not getattr(a, "live", False):
            F.cmd(d.io, F.TC_FREEZE_OFF)
        if proc is not None:
            F.finish(d, proc, t_on)
        elif not a.no_prep:
            F.freeze(d.io, False)
            F.cmd(d.io, F.TC_SDK)
            F.cmd(d.io, F.TC_CLEAR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--no-prep", action="store_true")
    ap.add_argument("--no-pattern", action="store_true", help="prep without the host window (frame mode + freeze of whatever the host shows)")
    ap.add_argument("--sdk-freeze", action="store_true", help="freeze with test cmd 0xFE (SDK path, freeze image) instead of the P5_27 / P45_27 poke")
    ap.add_argument("--limit-s", type=float, default=0.0, help="stall limit per op in s (default 3 x estimate + 0.5 s)")
    ap.add_argument("--hold", type=float, default=F.SCREEN_CAP_S)
    ap.add_argument("--count", action="store_true", help="DCR above-threshold count (sel 0, TH1 32) after the ops: lit pixels = hit-count check")
    ap.add_argument("ops", nargs="+")
    a = ap.parse_args()
    LIMIT_S[0] = a.limit_s
    ops = [parse_op(t) for t in a.ops]
    if a.hold > F.HOLD_MAX_S:
        raise SystemExit(f"--hold {a.hold}: above the backstop {F.HOLD_MAX_S:.0f} s")
    d = T.Dbg(a.unit, a.bus)
    try:
        dr = Draw(d, SW.sym(a.map, "g_stAwtoDraw"))
        with session(a, d):
            for op, p in ops:
                dr.run(op, p)
            if a.count:
                for sel in range(4):                       # sel 0 = R+G+B sum (#255); 1..3 per channel to be told by this log
                    r = T.dcr_measure(d, 32, 768, sel)
                    T.log(f"DCR sel {sel} TH1 32: above {r.get('th1_num') if r else None}; high R/G/B " + (f"{r['hi_r']}/{r['hi_g']}/{r['hi_b']}" if r else "-")
                          + "; low R/G/B " + (f"{r['lo_r']}/{r['lo_g']}/{r['lo_b']}" if r else "-"))
    finally:
        d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
