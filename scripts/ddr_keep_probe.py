#!/usr/bin/env python3
"""Does the DDR keep a marker at its top over an event? (awto-ddc log-keep, option F of the note store)

usage: ddr_keep_probe.py --unit N --map MAP [--bus B] [--seed S] fill | verify | cmd 0xNN
  Freeze image (`./dev.py build --freeze --savers pacman`, fw/test/ddr_draw.c ops addrfill / addrverify, docs/ddr-draw.md).
  fill    write the address-in-data pattern (seed) to the top region: AWTO_BLOCKS blocks ending at the 2^22-unit wrap (32 MiB)
  verify  read it back with single reads (lane swap AWTO_SWAP, as ddr_addr_test.py): bad bursts of N; the seed is kept in tmp/scratch/ddr_keep.seed
  Each call freezes the picture for the op (test cmd 0xFE ... 0xFF) and releases it: a few hundred ms.
Log: ./tmp/logs/ddr_keep_probe.log (decoded line per action); raw bytes in ddr_frame_test.raw.log
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddr_addr_test as A
from _repo import ROOT

SEED_FILE = ROOT / "tmp/scratch/ddr_keep.seed"
DDR_UNITS = 1 << 22                                   # address wrap: 2^22 units of 8 B = 32 MiB (docs/ddr-draw.md, #267)
BLOCK_UNITS = A.BLOCK_BURSTS * A.BURST_UNITS
AWTO_BLOCKS = 64                                      # 64 x 128 bursts x 16 B = 128 KiB at the top
BLK0 = DDR_UNITS // BLOCK_UNITS - AWTO_BLOCKS
AWTO_SWAP = 1                                         # measured read lane order (ddr_addr_test.py --swap)
HOLD_S = 0.3                                          # the frozen frame stays up this long after the op (ddr_draw session)


def main() -> int:
    import ddr_draw as D
    import ddr_frame_test as T
    import sw_timeline as SW

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("fill", "verify", "cmd"))
    ap.add_argument("code", nargs="?", type=lambda v: int(v, 0), help="cmd: the test cmd to send (an event: 0x27 close console, 0x26 open, 0x32 switch to D2, 0x4C watchdog reset)")
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--no-prep", action="store_true", help="no frame mode / freeze: the ops run on the live picture in whatever memory mode the SDK chose")
    ap.add_argument("--seed", type=lambda v: int(v, 0), default=None)
    a = ap.parse_args()
    a.no_pattern, a.sdk_freeze, a.live, a.hold = True, True, False, HOLD_S
    T.LOG = ROOT / "tmp/logs/ddr_keep_probe.log"
    D.LIMIT_S[0] = 0.0
    if a.what == "cmd":
        d = T.Dbg(a.unit, a.bus)
        import ddr_freeze_test as F
        F.cmd(d.io, a.code)
        T.log(f"ddr-keep: test cmd 0x{a.code:02X} sent")
        d.io.close()
        return 0
    if a.what == "fill":
        seed = a.seed if a.seed is not None else int(time.time() * 1000) & A.SEED_MASK
        SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEED_FILE.write_text(f"{seed}\n")
    else:
        seed = int(SEED_FILE.read_text())
    d = T.Dbg(a.unit, a.bus)
    dr = D.Draw(d, SW.sym(a.map, "g_stAwtoDraw"))
    base = SW.sym(a.map, "g_stAwtoAddr")

    def run(op: str, **kw) -> dict:
        v = {"blk0": BLK0, "blocks": AWTO_BLOCKS, "seed": seed, "stride": 0, "step_ms": 0, "inv": 0, "swap": AWTO_SWAP if op == A.OP_VERIFY else 0,
             "retry": 0, "samples": 0}
        v.update(kw)
        raw = b"".join(v[n].to_bytes(s, "big") for n, s in A.FIELDS[:A.RESULT_FROM_IDX])
        for i, byte in enumerate(raw):
            d.wr(base + i, byte)
        r = dr.run(op, {"est_bursts": AWTO_BLOCKS * A.BLOCK_BURSTS})
        raw = bytes(d.rd(base + A.RESULT_FROM + i) for i in range(A.SIZE - A.RESULT_FROM))
        return {**r, "res": A.parse_result(b"\0" * A.RESULT_FROM + raw)}

    with D.session(a, d, HOLD_S):
        if a.what == "fill":
            r = run(A.OP_FILL)
            T.log(f"ddr-keep fill: seed 0x{seed:08X}, blocks {BLK0}..{BLK0 + AWTO_BLOCKS - 1} (units 0x{BLK0 * BLOCK_UNITS:X}..), state {r['state']}, "
                  f"{r['bursts']} bursts in {r['ms']} ms")
        else:
            r = run(A.OP_VERIFY)
            res = r["res"]
            T.log(f"ddr-keep verify: seed 0x{seed:08X}, state {r['state']}, checked {res['checked']} bursts, BAD {res['bad']}, timeouts {res['tmo']}; "
                  + A.decode_line(res, seed, False))
    d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
