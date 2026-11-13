#!/usr/bin/env python3
"""Live A/B for awto-ddc#26: does P0_37 bits 5:4 (scaling coef_fix_h/v) cause the 4K60 M1 underflow (P0_02 bit0)?

usage: p037_test.py --unit N hold  [--secs S] [--period-ms P]   # re-arm ring, switch host to 4k60, keep P0_37[5:4]=0 for S s
       p037_test.py --unit N once                                # P0_37[5:4]=0, then P0_02 clear, sample P0_02 for ~0.4 s
Paths: debug slave 0x35 ScalerGetByte (0x3A) / ScalerSetByte (0x3B) with 0xPPRR addresses; MCU not halted.
Log: ./tmp/logs/p037_test.log (one line per P0_02 change / P0_37 write burst)
"""
import argparse, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402

DBG = 0x35 << 1
ROOT = Path(__file__).resolve().parent.parent
LOGF = ROOT / "tmp/logs/p037_test.log"


def rd(d, a):
    if not (d.write(DBG, 0x01, bytes([a >> 8])) and d.write(DBG, 0x3A, bytes([a & 0xFF]))):
        return None
    r = d.read(DBG, 0x08, 1)
    return r[0] if r else None


def wr(d, a, v):
    return d.write(DBG, 0x01, bytes([a >> 8])) and d.write(DBG, 0x03, bytes([v])) and d.write(DBG, 0x3B, bytes([a & 0xFF]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("op", choices=["hold", "once", "freeze"])
    ap.add_argument("--secs", type=float, default=3.0)       # covers ~14 retry passes of 217 ms
    ap.add_argument("--period-ms", type=float, default=10.0)  # ~ one 4K60 frame is 16.7 ms
    a = ap.parse_args()
    LOGF.parent.mkdir(parents=True, exist_ok=True)
    lf = LOGF.open("a")
    t0 = time.monotonic()

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} +{(time.monotonic() - t0) * 1000:7.1f}ms {s}"
        print(line); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)
    proc = None
    if a.op == "hold":
        log("re-arm ring F052=00: " + str(wr(d, 0xF052, 0x00)))
        proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
        t0 = time.monotonic()
        end, last, nwr, nrd, p02_last, nfail = t0 + a.secs, None, 0, 0, None, 0
        hist37 = {}
        while time.monotonic() < end:
            c = None
            if wr(d, 0x0037, 0x00):             # blind write: a read-modify-write costs 2 more transactions
                nwr += 1
            else:
                d.close(); d = Real(a.bus, allow_write=True); nfail += 1
            p = rd(d, 0x0002); nrd += 1
            r37 = rd(d, 0x0037)
            hist37[r37] = hist37.get(r37, 0) + 1
            if p != p02_last:
                log(f"P0_02={p if p is None else format(p, '02x')} P0_37_seen={c if c is None else format(c, '02x')}")
                p02_last = p
            dt = a.period_ms / 1000 - 0.0
            nxt = time.monotonic() + dt
            while time.monotonic() < nxt:
                pass
        log(f"done: {nrd} P0_02 reads, {nwr} P0_37 blind writes ok, {nfail} failed reads; P0_37 readback after write: " + str({(None if k is None else format(k, "02x")): v for k, v in hist37.items()}))
        proc.wait()
    elif a.op == "freeze":
        wr(d, 0xF052, 0x00)
        proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
        end = time.monotonic() + 8.0                   # mode switch + a few 217 ms retry passes
        seen_err = False
        hist = []
        while time.monotonic() < end:
            p = rd(d, 0x0002)
            if p != hist[-1][1] if hist else True:
                hist.append((round((time.monotonic() - t0) * 1000), p))
            if p is None:
                d.close(); d = Real(a.bus, allow_write=True); continue
            seen_err |= bool(p & 0x60)
            c37 = rd(d, 0x0037)
            if c37 is not None and (c37 & 0x30) and (p & 0x61) == 0x01:
                break
        else:
            log("never reached P0_02=01 state; P0_02 history (ms,val): " + str(hist)); proc.wait(); return 1
        d.write(DBG, 0x80, bytes([0x01]))              # pause main (SDK d_g_bFwHalt); reads/writes still serviced
        log(f"froze main at P0_02={p:02x}")

        def burst(tag, n=25):
            vals = [rd(d, 0x0002) for _ in range(n)]
            log(f"{tag}: P0_02 x{n} = " + " ".join("--" if v is None else format(v, "02x") for v in vals)
                + f"  P0_37={rd(d, 0x0037):02x} P0_0C={rd(d, 0x000C):02x}")
        burst("A before")
        wr(d, 0x0002, 0xFF); burst("B clear only (baseline)")
        c = rd(d, 0x0037); wr(d, 0x0037, c & ~0x30 & 0xFF); log(f"P0_37 {c:02x} -> {rd(d, 0x0037):02x}")
        burst("C P0_37 fixed, no clear")
        wr(d, 0x0002, 0xFF); burst("D P0_37 fixed + clear")
        wr(d, 0x0037, c); wr(d, 0x0002, 0xFF); burst("E P0_37 restored + clear")
        d.write(DBG, 0x80, bytes([0x00])); log("resumed main")
        proc.wait()
    else:
        c = rd(d, 0x0037)
        log(f"P0_37 before={c:02x}")
        wr(d, 0x0037, (c or 0) & ~0x30 & 0xFF)
        wr(d, 0x0002, 0xFF)
        log(f"P0_37 now={rd(d, 0x0037):02x}; P0_02 cleared")
        end, p02_last = time.monotonic() + 0.4, None
        while time.monotonic() < end:
            p = rd(d, 0x0002)
            if p != p02_last:
                log(f"P0_02={p:02x}"); p02_last = p
    return 0


if __name__ == "__main__":
    sys.exit(main())
