#!/usr/bin/env python3
"""Live DPLL fine-offset test for awto-ddc#26: does P1_C4[3:0]/P1_C5 cause the 4K60 M1 underflow (P0_02 bit0)?

usage: dpll_hold.py --unit N --bus B --serial S [--values 0x7F8,0x7F0,...] [--fupdn 0|1]
  Starts `dev.py mode 4k60`, waits for a failed 4K pass (P0_40==0x24, P0_02&0x61==1), freezes main (debug 0x80 01),
  then per VALUE: write C4=fupdn<<4|v>>8, C5=v&FF, C6=04 (double-buffer apply), clear P0_02, sample P0_02 x25.
  Finally restores the original C4/C5, resumes main. Offset format: SDK ScalerPLL.c (12-bit, C4[4]=1 FreqDn, C6[2] apply).
Paths: debug slave 0x35 ScalerSetByte/GetByte (as p037_test.py). Log: ./tmp/logs/dpll_hold.log
"""
import argparse, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr, DBG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOGF = ROOT / "tmp/logs/dpll_hold.log"
f2 = lambda v: "--" if v is None else format(v, "02x")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--values", default="0x7F8,0x7F0,0x7E0,0x7C0,0x820")
    ap.add_argument("--fupdn", type=int, default=0)             # live 1080p60 reads C4=08 (FreqUp)
    ap.add_argument("--n", type=int, default=25)
    a = ap.parse_args()
    LOGF.parent.mkdir(parents=True, exist_ok=True)
    lf = LOGF.open("a")
    t0 = time.monotonic()

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} +{(time.monotonic() - t0) * 1000:7.1f}ms {s}"
        print(line); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)
    proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
    t0 = time.monotonic()
    end = t0 + 12.0                                             # host mode switch + DDC storm + a few 217 ms retry passes
    while time.monotonic() < end:
        nxt = time.monotonic() + 0.03                           # light polling: the host modeset also uses this bus (DDC)
        while time.monotonic() < nxt:
            pass
        p, r40 = rd(d, 0x0002), rd(d, 0x0040)
        if p is None or r40 is None:
            continue
        if r40 == 0x24 and (p & 0x61) == 0x01:                  # failed 4K pass: M1 flag only
            break
    else:
        log("no failed 4K pass seen; aborting"); proc.wait(); return 1
    d.write(DBG, 0x80, bytes([0x01]))                           # pause main (g_bFwHalt); debug reads/writes still serviced
    c4o, c5o = rd(d, 0x01C4), rd(d, 0x01C5)
    log(f"froze main at P0_02={p:02x}; original C4={f2(c4o)} C5={f2(c5o)}")

    def burst(tag, n=a.n):
        vals = [rd(d, 0x0002) for _ in range(n)]
        log(f"{tag}: P0_02 x{n} = " + " ".join(f2(v) for v in vals) + f"  C4={f2(rd(d, 0x01C4))} C5={f2(rd(d, 0x01C5))}")

    def setoff(c4, c5):
        for ad, v in ((0x01C4, c4), (0x01C5, c5), (0x01C6, 0x04)):
            if not any(wr(d, ad, v) for _ in range(3)):
                log(f"write 0x{ad:04X} failed")

    burst("A original offset, no clear")
    wr(d, 0x0002, 0xFF); burst("B original offset, clear")
    for v in (int(x, 0) for x in a.values.split(",")):
        setoff((a.fupdn << 4) | ((v >> 8) & 0x0F), v & 0xFF)
        wr(d, 0x0002, 0xFF); burst(f"C offset 0x{v:03X} + clear")
    setoff(c4o, c5o)
    wr(d, 0x0002, 0xFF); burst("D original restored + clear")
    d.write(DBG, 0x80, bytes([0x00])); log("resumed main")
    proc.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
