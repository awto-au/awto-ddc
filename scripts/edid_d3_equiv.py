#!/usr/bin/env python3
"""Sim proof for #317: D3 EDID RAM of an image (D2 table + patch) == the D3 table of make_edid.py, and == the old image's RAM.

usage: edid_d3_equiv.py BIN MAP BIN_OLD MAP_OLD --serial S
  Boots both images to ACTIVE (fw_sim, panel_sim.Run), reads MCU_DDCRAM_D3 and MCU_DDCRAM_D2 (256 B each) from the DW8051 xdata.
  Pass: new D3 == old D3 == tmp/fw-edid/S/awto-hdmi-d3.bin, new D2 == old D2 == awto-hdmi.bin.
Log: ./tmp/logs/edid_d3_equiv.log
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_sim as P
from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/edid_d3_equiv.log"


def ram(bin_, map_):
    run = P.Run(
        argparse.Namespace(
            bin=bin_, map=map_, mode="1080p60", report=True, tree=str(ROOT)
        )
    )
    try:
        run.bus.run_until_mode(P.MODE_ACTIVE, P.BOOT_INSTR)
        m = run.m
        return {p: bytes(m.rd(m.addr(f"MCU_DDCRAM_{p}"), 256)) for p in ("D2", "D3")}
    finally:
        run.bus.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("new", nargs=2, type=Path)
    ap.add_argument("old", nargs=2, type=Path)
    ap.add_argument("--serial", required=True)
    a = ap.parse_args()
    new, old = ram(*a.new), ram(*a.old)
    gen = ROOT / "tmp/fw-edid" / a.serial
    want = {
        "D2": (gen / "awto-hdmi.bin").read_bytes(),
        "D3": (gen / "awto-hdmi-d3.bin").read_bytes(),
    }
    bad = 0
    for p in ("D2", "D3"):
        ok = new[p] == old[p] == want[p]
        bad += not ok
        log_line(
            f"{p}: new == old == make_edid: {ok} (new != old at {[i for i in range(256) if new[p][i] != old[p][i]]})",
            LOG,
            stamp_stdout=False,
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
