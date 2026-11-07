#!/usr/bin/env python3
"""Per-call cost of the data-port routines, reference image (SDK) vs an image with the clean dataport module (#65, spec dataport 4).

usage: dp_cycles.py REF_STEM NEW_STEM        (STEM = path without .bin/.map; BE images; AWTO_SDCC_BE=1)
  Runs each routine from its entry to a return trap in ucsim (bank register set, args in DPL/DPH, R7, PARM_n) and prints machine
  cycles (ticks / 12) and executed MOVX instructions (single-stepped). Pairs: SDK name vs clean name, same arguments.
  Peripherals are not modelled: XDATA reads return RAM, so this is the instruction cost, not the bus cost.
Log: tmp/logs/dp_cycles.log
"""
import re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

PAIRS = [("write byte", "ScalerSetDataPortByte", "dp_wr", {3: [0x80]}),
         ("test (get bit)", "ScalerGetDataPortBit", "dp_test", {3: [0x0F]}),
         ("rmw (set bit)", "ScalerSetDataPortBit", "dp_rmw", {3: [0xF0], 4: [0x01]}),
         ("write word", "ScalerSetDataPortWord", "dp_wr16", {3: [0x12, 0x34]})]


def machine(stem):
    img = Path(stem + ".bin").read_bytes()
    m = S.Machine(img, Path(stem + ".map"), "dpcyc", None, [S.FlashDev(img)])
    trap = m.sym["_main"] & 0xFFFF
    m.s.send(f"break 0x{trap:x}"); m.flush()
    return m, trap


def setup(m, trap, fn, port, r7, parms):
    v = m.sym["_" + fn]
    m.wr(0xFFFF, bytes([v >> 16 & 15]))
    for i, b in parms.items():
        m.wr(m.addr(f"{fn}_PARM_{i}"), bytes(b))
    m.wr(0x80, bytes([trap & 255, trap >> 8]), "iram")
    for c in ("set memory sfr 0x81 0x81", f"set memory sfr 0x82 0x{port & 255:x}", f"set memory sfr 0x83 0x{port >> 8:x}",
              f"set memory iram 0x7 0x{r7:x}", "set memory sfr 0xd0 0x0", f"pc 0x{v & 0xFFFF:x}"):
        m.put(c)
    m.flush()


def cost(m, trap, fn, parms, port=0x0031, r7=0x20):
    setup(m, trap, fn, port, r7, parms)
    cyc = int(re.search(r"Simulated (\d+) ticks", m.cmd("step 100000")).group(1)) / 12
    setup(m, trap, fn, port, r7, parms)
    n = mx = 0
    while n < 2000:
        mm = re.search(r"\n0x([0-9a-f]{4}) .. +(?:[0-9a-f]{2} )+ *(\w+)", m.cmd("info registers"))
        if int(mm.group(1), 16) == trap:
            break
        mx += mm.group(2) == "MOVX"
        m.cmd("step 1"); n += 1
    return cyc, mx, n


def main():
    ref, new = (machine(a) for a in sys.argv[1:3])
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    with (S.ROOT / "tmp/logs/dp_cycles.log").open("a") as lg:
        for lab, a, b, pa in PAIRS:
            ra, rb = cost(*ref, a, pa), cost(*new, b, pa)
            line = (f"{lab:14s} ref {a:22s} {ra[0]:5.0f} cyc {ra[1]:3d} movx {ra[2]:3d} insn | "
                    f"clean {b:8s} {rb[0]:5.0f} cyc {rb[1]:3d} movx {rb[2]:3d} insn")
            print(line); lg.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n")
    for m, _ in (ref, new):
        m.close()


if __name__ == "__main__":
    main()
