#!/usr/bin/env python3
"""Does the DDR keep a marker over an event? (note-store log-keep; #348 test 2: free range on chip A and chip B)

usage: ./dev.py ddr-keep [--unit N] [--port a|b|ab] [--blk0 B] [--blocks N] [--no-prep] [--label TEXT] fill | verify | cmd 0xNN
  Freeze image (`./dev.py build --freeze`, fw/test/ddr_draw.c ops addrfill / addrverify, docs/ddr-draw.md).
  fill    address-in-data pattern (seed) over blocks blk0 .. blk0+N-1 (128 bursts of 16 B each) on each port (A = chip A, B = chip B);
          default = units 0x200000.. (2.5 MB). A region reaching the chip A DRAM log (0x3EBFFE..) is refused. Seed + region: tmp/scratch/ddr_keep.json.
  verify  read the whole region back in the firmware (single reads, lane swap AWTO_SWAP): per port checked / bad / timeouts / first bad unit.
  Without --no-prep each call freezes the picture for the op (frame mode 0x0C + test cmd 0xFE ... 0xFF): that is a mode set, so
  event runs (#348) use --no-prep (live picture, marker outside the capture block).
Log: ./tmp/logs/ddr_keep_probe.log (one line per op and port); raw bytes in ddr_frame_test.raw.log
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddr_addr_test as A
from _repo import ROOT

STATE_FILE = ROOT / "tmp/scratch/ddr_keep.json"
DDR_UNITS = 1 << 22                                   # address wrap: 2^22 units of 8 B = 32 MiB per chip (docs/ddr-draw.md, #267, #348)
BLOCK_UNITS = A.BLOCK_BURSTS * A.BURST_UNITS
BLK0 = 0x200000 // BLOCK_UNITS                        # default region: unit 0x200000, free on both chips in the 4K60 1-buffer mode (#348)
AWTO_BLOCKS = 1221                                    # 1221 x 128 bursts x 16 B = 2 500 608 B (#348 test 2)
AWTO_SWAP = 1                                         # read lane order, port A (ddr_addr_test.py) and port B (#348 test 1): halves swapped
HOLD_S = 0.3                                          # the frozen frame stays up this long after the op (ddr_draw session)
EST_VERIFY_BURST_S = 207e-6                           # worst measured per burst: every burst bad (bookkeeping), unit 3 #348 E10: 32.4 s / 156 288; limit = 1.25 x + 2 s
LOG_A_FIRST = 0x3EBFFE                                # DRAM log + note store on chip A (fw/log/hostnote.c): never inside a region


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
    ap.add_argument("--port", choices=("a", "b", "ab"), default=None, help="fill: ports to fill (default a); verify: default = the filled ones")
    ap.add_argument("--blk0", type=lambda v: int(v, 0), default=BLK0, help="fill: first block (256 units each)")
    ap.add_argument("--blocks", type=int, default=AWTO_BLOCKS, help="fill: block count")
    ap.add_argument("--label", default="", help="event name for the log line")
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
        st = {"seed": a.seed if a.seed is not None else int(time.time() * 1000) & A.SEED_MASK, "blk0": a.blk0, "blocks": a.blocks, "ports": a.port or "a"}
        u0, u1 = a.blk0 * BLOCK_UNITS, (a.blk0 + a.blocks) * BLOCK_UNITS
        if u1 > DDR_UNITS or ("a" in st["ports"] and u1 > LOG_A_FIRST):
            raise SystemExit(f"region units 0x{u0:X}..0x{u1 - 1:X} overlaps the chip A DRAM log (0x{LOG_A_FIRST:X}..) or the 2^22 wrap; nothing done")
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st) + "\n")
    else:
        st = json.loads(STATE_FILE.read_text())
    ports = a.port or st["ports"]
    seed, blk0, blocks = st["seed"], st["blk0"], st["blocks"]
    bursts = blocks * A.BLOCK_BURSTS
    if a.what == "verify":
        D.LIMIT_S[0] = 1.25 * bursts * EST_VERIFY_BURST_S + 2.0      # + up to 40 flag timeouts of 50 ms
    d = T.Dbg(a.unit, a.bus)
    dr = D.Draw(d, SW.sym(a.map, "g_stAwtoDraw"))
    base = SW.sym(a.map, "g_stAwtoAddr")

    def run(op: str, port: str) -> dict:
        v = {"blk0": blk0, "blocks": blocks, "seed": seed, "stride": 0, "step_ms": 0, "inv": 0, "swap": AWTO_SWAP if op == A.OP_VERIFY else 0,
             "retry": 0, "samples": 0, "port": int(port == "b")}
        raw = b"".join(v[n].to_bytes(s, "big") for n, s in A.FIELDS[:A.RESULT_FROM_IDX])
        for i, byte in enumerate(raw):
            d.wr(base + i, byte)
        t = time.monotonic()
        r = dr.run(op, {"est_bursts": bursts})
        r["wall_s"] = time.monotonic() - t
        raw = bytes(d.rd(base + A.RESULT_FROM + i) for i in range(A.SIZE - A.RESULT_FROM))
        return {**r, "res": A.parse_result(b"\0" * A.RESULT_FROM + raw)}

    region = f"units 0x{blk0 * BLOCK_UNITS:X}..0x{(blk0 + blocks) * BLOCK_UNITS - 1:X} ({bursts} bursts = {bursts * A.BURST_BYTES} B)"
    with D.session(a, d, HOLD_S):
        for port in ports:
            if a.what == "fill":
                r = run(A.OP_FILL, port)
                T.log(f"ddr-keep fill port {port.upper()} {a.label}: seed 0x{seed:08X}, {region}, state {r['state']}, {r['bursts']} bursts in {r['ms']} ms")
            else:
                r = run(A.OP_VERIFY, port)
                res = r["res"]
                first = f"0x{A.BURST_UNITS * res['first'][0][0]:X}" if res["first"] else "none"
                T.log(f"ddr-keep verify port {port.upper()} {a.label}: seed 0x{seed:08X}, {region}, state {r['state']}, read {res['checked']} of {bursts} bursts "
                      f"in {r['ms']} ms fw / {r['wall_s']:.1f} s host; intact {res['checked'] - res['bad'] - res['tmo']} BAD {res['bad']} timeouts {res['tmo']}; "
                      f"first bad unit {first}; " + A.decode_line(res, seed, False))
        A.log_regs(d, T)                                  # memory mode of the event (1/2/3 buffers, capture on)
    d.io.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
