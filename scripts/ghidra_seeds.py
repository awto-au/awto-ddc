#!/usr/bin/env python3
"""Write re/jxc-4k/seeds_bank<N>.txt for banks without hand-picked seeds.

usage: ghidra_seeds.py <bank> [<bank> ...]
Seeds = the 7 interrupt vectors + LCALL targets (opcode 0x12) that land in the bank-specific region
(past the code common with bank 0) and are called >= 2 times. Heuristic [guess]: data bytes 0x12 can add
false functions; they are harmless entries, not names. Existing seed files are never overwritten.
Log: ./tmp/logs/ghidra_seeds.log
"""
import os, sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
BANKS = Path.home() / "vendors/realtek/analysis/banks"
VECTORS = (0x00, 0x03, 0x0B, 0x13, 0x1B, 0x23, 0x2B)
MIN_CALLS = 2


def main():
    log = (ROOT / "tmp" / "logs" / "ghidra_seeds.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    b0 = (BANKS / "bank0.bin").read_bytes()
    for bank in map(int, sys.argv[1:]):
        out = ROOT / "re" / "jxc-4k" / f"seeds_bank{bank}.txt"
        if out.exists():
            print(f"{out.name}: exists, skipped"); continue
        d = (BANKS / f"bank{bank}.bin").read_bytes()
        common = next((i for i in range(len(d)) if d[i] != b0[i]), len(d))
        end = max(i for i, x in enumerate(d) if x != 0xFF) + 1
        calls = Counter(t for i in range(common, end - 2) if d[i] == 0x12
                        for t in [d[i + 1] << 8 | d[i + 2]] if common <= t < end)
        targets = sorted(t for t, n in calls.items() if n >= MIN_CALLS)
        lines = [f"# bank {bank}: vectors, then LCALL targets in the bank-specific region 0x{common:04X}-0x{end:04X} called >= {MIN_CALLS}x [guess]"]
        lines += [f"0x{v:04X}" for v in VECTORS] + [f"0x{t:04X}" for t in targets]
        out.write_text("\n".join(lines) + "\n")
        msg = f"bank{bank}: common 0x{common:04X}, end 0x{end:04X}, {len(targets)} call-target seeds -> {out}"
        print(msg); log.open("a").write(msg + "\n")


if __name__ == "__main__":
    main()
