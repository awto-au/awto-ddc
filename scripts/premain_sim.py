#!/usr/bin/env python3
"""Instructions and machine cycles from reset to main() in the sim, and where they go (#63 pre-main boot time).

usage: premain_sim.py BIN MAP
  Runs the image from reset to the `_main` entry (breakpoint), reports instructions, ticks and the time at the reset
  clock: crystal 14.318 MHz, 12 ticks per machine cycle in the ucsim model (the M2PLL switch happens later, in
  ScalerMcuInitial). Also prints the map's XINIT/XISEG sizes (initialised XDATA the startup copies).
Log: tmp/logs/premain_sim.log
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S

XTAL_HZ = 14_318_180


def main() -> int:
    binp, mapp = Path(sys.argv[1]), Path(sys.argv[2])
    mp = mapp.read_text(errors="replace")
    m = S.Machine(binp.read_bytes(), mapp, binp.stem + "-premain", None, [S.FlashDev(binp.read_bytes())])
    hit = []
    m.stub("main", lambda m_, r: hit.append((m_.instr, m_.ticks)) or m_.request_stop() or None)
    used = 0
    while not hit and used < 50_000_000:
        m.run(1_000_000); used += 1_000_000
    m.close()
    sizes = {n: int(sz, 16) for n, sz in re.findall(r"^(XINIT|XISEG|XINIT_\w*|XISEG_\w*)\s+[0-9A-F]{8}\s+([0-9A-F]{8})", mp, re.M)}
    lines = [f"{binp.name}: reset -> main " + (f"{hit[0][0]} instr, {hit[0][1]} ticks = {hit[0][1] / XTAL_HZ * 1000:.1f} ms at the "
             f"14.318 MHz reset clock (ucsim tick = 1 oscillator clock)" if hit else "main not reached"),
             f"initialised XDATA (map): {sizes}"]
    with (S.ROOT / "tmp/logs/premain_sim.log").open("a") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
