#!/usr/bin/env python3
"""awto-ddc#255 step 5 on a freeze image: frozen-frame readback + beat-offset statistics, then a few-burst write with a DCR count.

usage: ddr_freeze_test.py --unit 1 --bus 18 map|write
  One debug-link session per run (the link pops the diag console: it is cleared with test cmd 0x27 at the end, the link is
  switched off by the caller). The host pattern window (scripts/host_pattern.py, system python) is started here and quit at the
  end; its time on screen is capped at SCREEN_CAP_S (Dan: quick visible tests, hard cap 5 s).
  map:   frame mode (0x0C) with the desktop visible, pattern `xbits 3` (8-px colour groups, period 64 px = 24 units), wait for the
         marker, freeze (test cmd 0xFE), N bursts per address on port A / B, freeze off (0xFF), pattern quit, 0x0D, 0x27.
         Per read: the 8 B halves decoded to unit numbers mod 24; offset d = (unit - address) mod 24 per half.
  write: same set-up with a black frame; DCR count (sel R+G+B, TH1 32), then WRITES bursts of 0xFF at address WADDR (LEN 2, full
         mask, port A), DCR count again, readback, freeze off. At most 3 write bursts (Dan: a few).
Log: ./tmp/logs/ddr_freeze_test.log (decoded), raw bytes in tmp/logs/ddr_frame_test.raw.log
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddr_frame_test as T  # noqa: E402
from p037_test import rd as prd, wr as pwr  # noqa: E402

ROOT = T.ROOT
FIFO = ROOT / "tmp/scratch/pat.fifo"
TC_FRAME, TC_SDK, TC_FREEZE_ON, TC_FREEZE_OFF, TC_CLEAR = 0x0C, 0x0D, 0xFE, 0xFF, 0x27
TESTCMD = 0xF6F8                 # g_stAwtoDiag + 0x28 (docs/diag-block.md)
P5_AC = 0x05AC
SCREEN_CAP_S = 4.5               # pattern on screen: 5 s hard cap minus margin
MARK_WAIT_S = 2.0                # pattern arrives within ~2 frames of the draw; the window draw takes ~0.3 s
PERIOD_U = 24                    # xbits 3: 64 px * 3 B / 8 B
WRITES_MAX = 3
MASK = [0xFFFF]             # WMASK value written (set by --mask)


def stream(i: int) -> int:
    x, c = divmod(i, 3)
    v = (x >> 3) & 7
    return 255 * (((v >> 2) & 1, (v >> 1) & 1, v & 1)[c])        # memory order B, G, R


STREAM = bytes(stream(i) for i in range(8 * PERIOD_U * 2))


def units(half: bytes) -> list[int]:
    return [u for u in range(PERIOD_U) if STREAM[8 * u:8 * u + 8] == half]


def freeze(io, on: bool) -> None:
    """Capture freeze = P5_27 / P45_27 bit2 (what ScalerFRCDisplayFreeze writes): works on the default FRC image too (#255)."""
    for a in (0x0527, 0x4527):
        v = prd(io, a)
        pwr(io, a, (v | 0x04) if on else (v & ~0x04 & 0xFF))


def debruijn(k: int = 8, n: int = 2) -> list[int]:
    a, seq = [0] * k * n, []

    def db(t, p):
        if t > n:
            if n % p == 0:
                seq.extend(a[1:p + 1])
        else:
            a[t] = a[t - p]
            db(t + 1, p)
            for j in range(a[t - p] + 1, k):
                a[t] = j
                db(t + 1, t)
    db(1, 1)
    return seq


DB = debruijn()                  # 64 symbols, every ordered pair once
ROW_SHIFT = 7                    # symbol of pixel (x, y) = DB[(x + 7 y) % 64]


def px_bytes(p: int) -> bytes:
    x, y = p % 3840, p // 3840
    v = DB[(x + ROW_SHIFT * y) % 64]
    return bytes([255 * ((v >> 2) & 1), 255 * ((v >> 1) & 1), 255 * (v & 1)])      # memory order B, G, R


def unit_bytes(u: int) -> bytes:
    return bytes(px_bytes((8 * u + i) // 3)[(8 * u + i) % 3] for i in range(8))


def cmd(io, c: int) -> None:
    pwr(io, TESTCMD, c)
    t = time.monotonic()
    while time.monotonic() - t < 0.5 and prd(io, TESTCMD) != 0:     # consumed within one main pass (~1 ms); 0.5 s = stall cap
        pass


def frame_mode(io) -> None:
    cmd(io, TC_FRAME)
    t = time.monotonic()
    while time.monotonic() - t < 2.5 and prd(io, P5_AC) != 0x01:    # SELECT_LIMIT_S of mem_mode.py
        pass
    T.log(f"frame mode P5_AC={prd(io, P5_AC):02x} P0_02={prd(io, 0x0002):02x}")


def pattern_start(initial: str) -> subprocess.Popen:
    if FIFO.exists():
        FIFO.unlink()
    return subprocess.Popen(["/usr/bin/python3", str(ROOT / "scripts/host_pattern.py"), "--connector", "HDMI-3", "--fifo", str(FIFO),
                             "--initial", initial], stdout=open(ROOT / "tmp/logs/host_pattern.out", "w"), stderr=subprocess.STDOUT)


def pattern_cmd(s: str) -> None:
    fd = FIFO.open("w")
    fd.write(s + "\n")
    fd.close()


def wait_marker(d, addr: int, want: bytes) -> bool:
    t = time.monotonic()
    while time.monotonic() - t < MARK_WAIT_S:
        b = T.dc_burst_read(d, "a", addr, 2)
        if b is not None and (want in b):
            return True
    return False


def finish(d, proc, t_on: float) -> None:
    pattern_cmd("quit")
    freeze(d.io, False)
    T.log(f"pattern on screen {time.monotonic() - t_on:.2f} s")
    proc.wait(timeout=3)
    cmd(d.io, TC_SDK)
    cmd(d.io, TC_CLEAR)
    T.log(f"hold byte (diag+0x2F) {prd(d.io, 0xF6FF):02x} P5_AC {prd(d.io, P5_AC):02x}")


def do_map2(d, reads: int) -> None:
    """Hypothesis test: a burst at address a returns unit a + k (k per 8 B half); histogram of k, timed-out bursts dropped."""
    frame_mode(d.io)
    t_on = time.monotonic()
    proc = pattern_start("debruijn")
    t = time.monotonic()
    while time.monotonic() - t < MARK_WAIT_S:                         # marker: unit 3 of the pattern decodes once drawn
        b = T.dc_burst_read(d, "a", 3, 2)
        if b is not None and (b[:8] == unit_bytes(3) or b[8:] == unit_bytes(3) or b[:8] == unit_bytes(4) or b[8:] == unit_bytes(4)):
            break
    T.log(f"marker after {time.monotonic() - t_on:.2f} s")
    freeze(d.io, True)
    for port in "ab":
        for a in (0, 1, 5, 100, 1440, 1441, 7203, 0x100000, 0x2F0000):
            hist = [Counter(), Counter()]
            bad = 0
            for _ in range(reads):
                if time.monotonic() - t_on > SCREEN_CAP_S:
                    break
                x = T.dc_burst_read(d, port, a, 2)
                if x is None:
                    bad += 1
                    continue
                for h in (0, 1):
                    half = x[8 * h:8 * h + 8]
                    hist[h][tuple(k for k in range(-1500, 1501) if a + k >= 0 and unit_bytes(a + k) == half) or ("none",)] += 1
            T.log(f"port {port} a={a}: k first half {dict(hist[0])} | second half {dict(hist[1])} | timeouts {bad}")
    finish(d, proc, t_on)


def do_map(d, reads: int) -> None:
    frame_mode(d.io)
    t_on = time.monotonic()
    proc = pattern_start("xbits 3")
    ok = wait_marker(d, 3, bytes([0, 0, 255]))                         # x = 8..: v = 1: R on
    T.log(f"marker {'seen' if ok else 'NOT seen'} after {time.monotonic() - t_on:.2f} s")
    freeze(d.io, True)
    for port in "ab":
        for a in (0, 1, 2, 3, 24, 1440, 1441, 2880):
            res = Counter()
            for _ in range(reads):
                if time.monotonic() - t_on > SCREEN_CAP_S:
                    break
                x = T.dc_burst_read(d, port, a, 2)
                if x is None:
                    res["timeout"] += 1
                    continue
                f, s = units(x[:8]), units(x[8:])
                res[(tuple(sorted({(u - a) % PERIOD_U for u in f})), tuple(sorted({(u - a) % PERIOD_U for u in s})))] += 1
            T.log(f"port {port} addr {a}: offsets d=(unit-a) mod {PERIOD_U} (first half, second half): {dict(res)}")
        if time.monotonic() - t_on > SCREEN_CAP_S:
            T.log("screen cap reached: stopped")
            break
    finish(d, proc, t_on)


def do_write(d, waddr: int, n: int) -> None:
    n = min(n, WRITES_MAX)
    frame_mode(d.io)
    t_on = time.monotonic()
    proc = pattern_start("solid 0 0 0")
    wait_marker(d, 0, bytes([0] * 16))
    freeze(d.io, True)
    c0 = T.dcr_measure(d, 32, 768, 0)
    T.log(f"DCR before: ABOVE_TH1_NUM={c0.get('th1_num')}")
    for i in range(n):
        T.cmd_ddr_write(d, type("A", (), dict(yes_hang_risk=True, port="a", hex="ff" * 16, mask=MASK[0], len=2, addr=waddr + 2 * i))())
    c1 = T.dcr_measure(d, 32, 768, 0)
    T.log(f"DCR after {n} burst(s) at {waddr}: ABOVE_TH1_NUM={c1.get('th1_num')} (delta {(c1.get('th1_num') or 0) - (c0.get('th1_num') or 0)})")
    for i in range(n):
        x = T.dc_burst_read(d, "a", waddr + 2 * i, 2)
        T.log(f"readback burst {i}: {x.hex() if x else None}")
    finish(d, proc, t_on)


def do_block(d, waddr: int) -> None:
    """Visible run: 16 white bursts (4 rows x 4 bursts) on a frozen black frame, held HOLD_S with DCR counts, then released."""
    frame_mode(d.io)
    t_on = time.monotonic()
    proc = pattern_start("solid 0 0 0")
    wait_marker(d, 0, bytes([0] * 16))
    freeze(d.io, True)
    r = T.MCU_DC["a"]
    d.wr(r["len"], 2)
    for i in range(16):
        d.wr(r["wbuf"] + i, 0xFF)
    d.wr(r["wmask"], 0)
    d.wr(r["wmask"] + 1, 0)
    c0 = T.dcr_measure(d, 32, 768, 0)
    n = 0
    for row in range(4):
        for k in range(4):
            a = waddr + row * 1440 + 2 * k
            for i, sh in enumerate((24, 16, 8, 0)):
                d.wr(r["addr"] + i, (a >> sh) & 0xFF)
            d.wr(r["cmd"], T.DC_CMD_WRITE)
            t = time.monotonic()
            while time.monotonic() - t < 0.05 and (d.rd(r["cmd"]) & 0xE0) != 0:
                pass
            n += 1
    T.log(f"{n} bursts written at {waddr}+row*1440+2k, rows 0..3, k 0..3")
    T.log(f"DCR before {c0.get('th1_num')}")
    t_hold = time.monotonic()
    while time.monotonic() - t_on < SCREEN_CAP_S - 0.4:               # hold: DCR counts are the wait (one per frame)
        c = T.dcr_measure(d, 32, 768, 0)
        last = c.get("th1_num")
    T.log(f"DCR during hold {last} after {time.monotonic() - t_hold:.1f} s")
    finish(d, proc, t_on)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("op", choices=["map", "map2", "write", "block"])
    ap.add_argument("--reads", type=int, default=6)
    ap.add_argument("--waddr", type=lambda x: int(x, 0), default=0x100000)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--mask", type=lambda x: int(x, 0), default=0xFFFF)
    a = ap.parse_args()
    MASK[0] = a.mask
    d = T.Dbg(a.unit, a.bus)
    try:
        if a.op == "map":
            do_map(d, a.reads)
        elif a.op == "map2":
            do_map2(d, a.reads)
        elif a.op == "block":
            do_block(d, a.waddr)
        else:
            do_write(d, a.waddr, a.n)
    finally:
        d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
