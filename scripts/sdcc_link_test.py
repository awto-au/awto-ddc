#!/usr/bin/env python3
"""Offline test for sdcc_link.dseg_runs: DSEG split around the bit bytes (sdld -M grid), no false IRAM overlap."""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_link as L  # noqa: E402

ROWS = ["|0|0|0|0|0|0|0|0|a|a|b|b|b|d|d|d|", "|d|e| | | | | | | | | | | | | | |",
        "|B|c|c|c|c|c|c|c|c|c|c|c|c|c|c|c|", "|c|c|c|c|c|c|c|c|c|c|c|c|c|c| | |"]


def main():
    with tempfile.TemporaryDirectory() as d:
        mem = Path(d, "out.mem")
        mem.write_text("Internal RAM layout:\n      0 1 2 3 4 5 6 7 8 9 A B C D E F\n"
                       + "".join(f"0x{i * 16:02x}:{r}\n" for i, r in enumerate(ROWS)))
        runs = L.dseg_runs("", [], mem)
        assert runs == [(0x08, 0x12), (0x21, 0x3E)], runs    # bit byte 0x20 is not DSEG
        rel = Path(d, "ovl.rel")
        rel.write_text("A DDOVL1 size 1 flags 0 addr 0\n")
        assert L.dseg_runs("", [rel], mem) == [(0x08, 0x11), (0x21, 0x3E)]   # last letter (e) = the DDOVL area
    assert L.dseg_runs("", [], Path("/nonexistent.mem")) == []
    print("PASS sdcc_link_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
