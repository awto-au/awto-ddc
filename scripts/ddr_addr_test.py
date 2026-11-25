#!/usr/bin/env python3
"""DDR address-in-data fill + read-back (freeze image, fw/test/ddr_draw.c ops 12-14; docs/ddr-draw.md).

usage: ./dev.py ddr-addr [--unit N] [--map F] [--seed S] [--double] [--extend] [--watch] [--no-prep] [--hold S]
  default  UHD block 1 (1 555 200 units = 777 600 bursts of 16 B = 3840 x 1080 x 3 B, line-doubled on screen):
           fill with the unit index (seed XOR), read back with SINGLE reads in the firmware, then the same with every byte inverted.
           Result per pass: bursts, bad, by address bit, first mismatches, fw ms. Lane swap of the read buffer: found on 8 blocks first.
  --double a separate second result: the same read-back with 2 extra reads of a bad burst (stale count).
  --extend a separate result: fill + sampled read-back in doubling steps beyond block 1 up to the 28-bit MCU_DC address; capacity = first aliasing.
  --watch  LIVE input (not frozen): a marker block is written, read back 8 times at 5 ms and at 17 ms steps; bad bursts per sample.
Pattern (memory order, per 8 B unit u): bytes 0..3 = (u ^ seed) little endian, bytes 4..7 = lane constants; inverted pass: every byte ^ 0xFF.
Log: ./tmp/logs/ddr_addr_test.log (decoded line per action); raw in ddr_frame_test.raw.log
"""
from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

UNIT_BYTES, BURST_BYTES, BURST_UNITS = 8, 16, 2
IDX_BYTES = 4
IDX_BITS = 28                                     # MCU_DC address: ADDR_H 4 bits + 3 bytes
LANES = (0x5A, 0xA5, 0x3C, 0xC3)
INV = 0xFF
BLOCK_BURSTS = 128
SHOWN_UNITS = 1440 * 1080                         # block 1: line pitch x 1080 memory lines
SHOWN_BURSTS = SHOWN_UNITS // BURST_UNITS
SHOWN_BLOCKS = SHOWN_BURSTS // BLOCK_BURSTS
REC_N, WATCH_N = 4, 8
OP_FILL, OP_VERIFY, OP_WATCH = "addrfill", "addrverify", "addrwatch"
SEED_MASK = 0xFFFFFFFF

# StAwtoAddr (fw/test/ddr_draw.c), big endian: (name, size) in C order
FIELDS = (("blk0", 4), ("blocks", 4), ("seed", 4), ("stride", 2), ("step_ms", 2), ("inv", 1), ("swap", 1), ("retry", 1), ("samples", 1), ("port", 1),
          ("checked", 4), ("bad", 4), ("stale", 4), ("shift", 4), ("data", 4), ("tmo", 4), ("spin", 4), ("slow", 4), ("bits", 4 * IDX_BITS), ("watch", 2 * WATCH_N),
          ("rec_n", 1), ("rec_idx", 4 * REC_N), ("rec", BURST_BYTES * REC_N))
OFF: dict[str, int] = {}
_o = 0
for _n, _s in FIELDS:
    OFF[_n] = _o
    _o += _s
SIZE = _o
RESULT_FROM = OFF["checked"]


# ---- pattern model (the firmware computes the same thing; tests/test_ddr_addr.py checks both) ----
def unit_bytes(u: int, seed: int, inv: bool) -> bytes:
    x = INV if inv else 0
    return bytes(b ^ x for b in struct.pack("<I", (u ^ seed) & SEED_MASK) + bytes(LANES))


def burst_bytes(b: int, seed: int, inv: bool) -> bytes:
    return unit_bytes(BURST_UNITS * b, seed, inv) + unit_bytes(BURST_UNITS * b + 1, seed, inv)


def decode_index(got: bytes, seed: int, inv: bool) -> int:
    """Unit index held by the first unit of a read burst."""
    x = INV if inv else 0
    return struct.unpack("<I", bytes(b ^ x for b in got[:IDX_BYTES]))[0] ^ seed


def diff_bits(expected: int, got: int) -> list[int]:
    d = (expected ^ got) & ((1 << IDX_BITS) - 1)
    return [k for k in range(IDX_BITS) if (d >> k) & 1]


def parse_result(raw: bytes) -> dict:
    """Result part of StAwtoAddr (offsets from RESULT_FROM)."""
    def u(name: str, n: int) -> int:
        return int.from_bytes(raw[OFF[name]:OFF[name] + n], "big")
    r = {k: u(k, 4) for k in ("checked", "bad", "stale", "shift", "data", "tmo", "spin", "slow")}
    r["bits"] = [int.from_bytes(raw[OFF["bits"] + 4 * k:OFF["bits"] + 4 * k + 4], "big") for k in range(IDX_BITS)]
    r["watch"] = [int.from_bytes(raw[OFF["watch"] + 2 * k:OFF["watch"] + 2 * k + 2], "big") for k in range(WATCH_N)]
    n = raw[OFF["rec_n"]]
    r["first"] = [(int.from_bytes(raw[OFF["rec_idx"] + 4 * k:OFF["rec_idx"] + 4 * k + 4], "big"),
                   bytes(raw[OFF["rec"] + BURST_BYTES * k:OFF["rec"] + BURST_BYTES * (k + 1)])) for k in range(min(n, REC_N))]
    return r


def decode_line(r: dict, seed: int, inv: bool) -> str:
    bits = " ".join(f"b{k}={c}" for k, c in enumerate(r["bits"]) if c) or "none"
    first = "; ".join(f"burst {i} (unit {BURST_UNITS * i}): got unit {decode_index(g, seed, inv)} bytes {g.hex()} expected {burst_bytes(i, seed, inv).hex()}" for i, g in r["first"])
    return (f"checked {r['checked']} bad {r['bad']} (index right data wrong {r['data']}, neighbour unit {r['shift']}), timeouts {r['tmo']}, retry-recovered {r['stale']}; "
            f"bad bursts by address bit: {bits}; first: {first or 'none'}")


RESULT_FROM_IDX = [n for n, _ in FIELDS].index("checked")
MAX_BLOCKS = (1 << IDX_BITS) // (BLOCK_BURSTS * BURST_UNITS)     # 28-bit address of 8 B units
EXT_RETRY = 2                                                      # extra reads: a flag timeout (~0.05 % of reads) is retried, not a finding
EXT_LIMIT_S = 10.0                                                 # per op: 33 k reads x 64 us = 2.1 s + ~16 flag timeouts x 50 ms x 3 reads; fills 0.06 s per 50 k bursts per doubling
WATCH_BLOCKS = (100, 800, 1500, 2200, 2900, 3600, 4300, 5000, 5900)   # marker positions: different memory lines = different capture phases
WATCH_LIMIT_S = 3.0                                                # 8 samples x 128 reads x 64 us = 66 ms + a few 50 ms flag timeouts
WATCH_BLOCKS_2ND = (100, 3037, 5900)                                # same offsets in the memory after block 1 (regdb: the 2nd memory block, unused with cap_db_en = 0: hypothesis)
EXT_SAMPLES = 256                                                  # blocks read back per step, evenly over [0, N)
REGS = (("CAP_M1_MEM_ADDR_MSB", 0x0500), ("CAP_M1_MEM_ADDR_H", 0x0501), ("CAP_M1_MEM_ADDR_M", 0x0502), ("CAP_M1_MEM_ADDR_L", 0x0503),
        ("CAP_M1_DDR_CTRL1", 0x0527), ("CAP_M1_DDR_CTRL2", 0x0528), ("CAP_M1_DDR_CTRL3", 0x0529), ("CAP_M1_STATUS", 0x052A),
        ("DISP_M1_DISP_CTRL1", 0x05AC), ("DISP_M1_DISP_CTRL2", 0x05AE), ("DISP_M1_DISP_CTRL3", 0x05AF),
        ("CAP_M2_DDR_CTRL1", 0x4527), ("CAP_M2_DDR_CTRL3", 0x4529), ("DISP_M2_DISP_CTRL1", 0x45AC), ("DISP_M2_DISP_CTRL2", 0x45AE), ("DISP_M2_DISP_CTRL3", 0x45AF))


def log_regs(d, T) -> None:
    """Buffer-mode bits (regdb: cap_db_en 0527[5], cap_sb_sel 0527[3], cap_3buf_en 0529[0], disp_db_en 05AC[6], disp_buf_sel_en 05AE[2], disp_3buf_en 05AF[0])."""
    vals = []
    for name, addr in REGS:
        v = d.rd(addr)
        vals.append(f"{name}(0x{addr:04X})={'--' if v is None else f'{v:02X}'}")
    T.log("buffer registers: " + " ".join(vals))


def extend(run, results, T, seed: int, swap: int) -> None:
    """SECOND RESULT: fill and sampled read-back in doubling steps past block 1 up to the 28-bit address; capacity = first aliasing."""
    import ddr_draw as D
    D.LIMIT_S[0] = EXT_LIMIT_S
    run(OP_FILL, SHOWN_BURSTS, blocks=SHOWN_BLOCKS)
    n = SHOWN_BLOCKS
    T.log(f"EXTEND (separate result): block 1 = {SHOWN_BLOCKS} blocks filled; steps double the filled region; read-back = {EXT_SAMPLES} blocks over [0, N) + the last 8 blocks")
    while n < MAX_BLOCKS:
        n2 = min(2 * n, MAX_BLOCKS)
        f = run(OP_FILL, (n2 - n) * BLOCK_BURSTS, blk0=n, blocks=n2 - n)
        stride = max(1, n2 // EXT_SAMPLES)
        v = run(OP_VERIFY, EXT_SAMPLES * BLOCK_BURSTS, blk0=0, blocks=n2 // stride, stride=stride, swap=swap, retry=EXT_RETRY)
        r = results()
        t = run(OP_VERIFY, 8 * BLOCK_BURSTS, blk0=n2 - 8, blocks=8, swap=swap, retry=EXT_RETRY)
        rt = results()
        T.log(f"extend to {n2 * BLOCK_BURSTS * BURST_UNITS} units ({n2 * BLOCK_BURSTS * BURST_BYTES // 2**20} MB): fill state {f['state']} {f['ms']} ms; sampled {r['checked']} bursts bad {r['bad']} "
              f"timeouts {r['tmo']} state {v['state']}; tail 8 blocks bad {rt['bad']} timeouts {rt['tmo']} state {t['state']}")
        if r["bad"] or rt["bad"] or f["state"] != 2 or v["state"] != 2 or t["state"] != 2:
            T.log("extend first bits by address bit: " + " ".join(f"b{k}={c}" for k, c in enumerate(r["bits"]) if c)
                  + "; first: " + "; ".join(f"burst {i} (unit {BURST_UNITS * i}): got unit {decode_index(g, seed, False)} (diff bits {diff_bits(BURST_UNITS * i, decode_index(g, seed, False))})" for i, g in r["first"]))
            return
        n = n2
    T.log(f"extend: no aliasing up to the 28-bit address limit ({MAX_BLOCKS * BLOCK_BURSTS * BURST_BYTES // 2**20} MB)")


def watch(run, results, T, seed: int, swap: int) -> None:
    """THIRD result: LIVE input, not frozen. A marker block is written; read back WATCH_N times, step ms apart, bad bursts per sample."""
    import ddr_draw as D
    D.LIMIT_S[0] = WATCH_LIMIT_S
    for blk, step in ((SHOWN_BLOCKS // 2, 5), (SHOWN_BLOCKS // 2, 17)) + tuple((b, 0) for b in WATCH_BLOCKS) + tuple((SHOWN_BLOCKS + b, 0) for b in WATCH_BLOCKS_2ND):
        try:
            f = run(OP_WATCH, BLOCK_BURSTS * WATCH_N, blk0=blk, blocks=1, step_ms=step, swap=swap, samples=WATCH_N)
        except TimeoutError:
            T.log(f"watch marker block {blk}: op not finished after {WATCH_LIMIT_S} s (flag timeouts of 50 ms each); stopping")
            r = results()
            T.log(f"  partial: checked {r['checked']} bad {r['bad']} timeouts {r['tmo']} spin {r['spin']} slow {r['slow']}")
            return
        r = results()
        T.log(f"watch marker block {blk} (memory line {blk * BLOCK_BURSTS // 720} of the frame, {BLOCK_BURSTS} bursts), live, step {step} ms (0 = back to back; sample k starts at least {step} ms x (k+1) after the write, each read takes ~8 ms): "
              f"bad bursts per sample {r['watch']} of {BLOCK_BURSTS} (state {f['state']}, timeouts {r['tmo']}); first bad: "
              + "; ".join(f"burst {i} got {g.hex()} (unit {decode_index(g, seed, False)})" for i, g in r["first"][:2]))


def main() -> int:
    import ddr_draw as D
    import ddr_frame_test as T
    import sw_timeline as SW

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", type=int, default=2)
    ap.add_argument("--bus", type=int, default=None)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--seed", type=lambda v: int(v, 0), default=None, help="32-bit seed XORed into the unit index (default: from the clock)")
    ap.add_argument("--no-prep", action="store_true")
    ap.add_argument("--no-pattern", action="store_true")
    ap.add_argument("--no-sdk-freeze", dest="sdk_freeze", action="store_false", help="freeze with the P5_27 poke (did not hold on the freeze image)")
    ap.add_argument("--hold", type=float, default=0.5, help="seconds the frozen frame stays up after the passes")
    ap.add_argument("--double", action="store_true")
    ap.add_argument("--extend", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--limit-s", type=float, default=0.0)
    ap.add_argument("--swap", type=int, default=None, help="read lane swap (default: found on 8 blocks); the measured order is 1")
    ap.add_argument("--regs", action="store_true", help="log the M1 capture / display buffer registers (regdb names), then exit")
    ap.add_argument("--no-primary", action="store_true", help="skip the UHD single-read passes")
    a = ap.parse_args()
    a.live = False
    T.LOG = T.ROOT / "tmp/logs/ddr_addr_test.log"
    D.LIMIT_S[0] = a.limit_s
    seed = a.seed if a.seed is not None else int(time.time() * 1000) & SEED_MASK
    d = T.Dbg(a.unit, a.bus)
    dr = D.Draw(d, SW.sym(a.map, "g_stAwtoDraw"))
    base = SW.sym(a.map, "g_stAwtoAddr")

    def params(**kw) -> None:
        v = {"blk0": 0, "blocks": 0, "seed": seed, "stride": 0, "step_ms": 0, "inv": 0, "swap": 0, "retry": 0, "samples": 0, "port": 0}
        v.update(kw)
        raw = b"".join(v[n].to_bytes(s, "big") for n, s in FIELDS[:RESULT_FROM_IDX])
        for i, byte in enumerate(raw):
            d.wr(base + i, byte)

    def results() -> dict:
        raw = bytes(dr_rd(base + RESULT_FROM + i) for i in range(SIZE - RESULT_FROM))
        return parse_result(b"\0" * RESULT_FROM + raw)

    def dr_rd(addr: int) -> int:
        for _ in range(D.POLL_RETRY):
            try:
                return d.rd(addr)
            except OSError:
                pass
        raise OSError(f"read {addr:04X} failed")

    def run(op: str, est_bursts: int, **kw) -> dict:
        params(**kw)
        r = dr.run(op, {"est_bursts": est_bursts})
        r["bytes"] = r["bursts"] * BURST_BYTES
        return r

    def pass_(inv: bool, retry: int, label: str) -> dict:
        t = time.monotonic()
        f = run(OP_FILL, SHOWN_BURSTS, inv=int(inv))
        T.log(f"{label} fill: state {f['state']}, {f['bursts']} bursts, fw {f['ms']} ms = {f['mbs']:.2f} MB/s, host {time.monotonic() - t:.1f} s")
        v = run(OP_VERIFY, SHOWN_BURSTS, inv=int(inv), swap=SWAP[0], retry=retry)
        r = results()
        T.log(f"{label} verify (extra reads {retry}): state {v['state']}, fw {v['ms']} ms = {v['mbs']:.2f} MB/s; " + decode_line(r, seed, inv))
        return {"fill": f, "verify": v, "res": r}

    SWAP = [0 if a.swap is None else a.swap]
    if a.regs:
        log_regs(d, T)
        d.io.close()
        return 0
    if a.watch:
        a.live = True
        with D.session(a, d, 0.0):
            watch(run, results, T, seed, SWAP[0])
            log_regs(d, T)
        d.io.close()
        return 0
    with D.session(a, d, a.hold):
        T.log(f"ddr-addr: seed 0x{seed:08X}, region {SHOWN_UNITS} units = {SHOWN_BURSTS} bursts = {SHOWN_BURSTS * BURST_BYTES} B (3840 x 1080 x 3 B)")
        if a.swap is None:
            run(OP_FILL, SHOWN_BURSTS, blocks=8)
            bad_by_swap = []
            for sw in (0, 1):
                run(OP_VERIFY, 8 * BLOCK_BURSTS, blocks=8, swap=sw)
                r = results()
                bad_by_swap.append(r["bad"])
                T.log(f"lane swap {sw}: first 8 blocks bad {r['bad']} of {r['checked']} (timeouts {r['tmo']})")
            SWAP[0] = int(bad_by_swap[1] < bad_by_swap[0])
        if not a.no_primary:
            T.log(f"PRIMARY single-read results (swap {SWAP[0]})")
            p1 = pass_(False, 0, "pass 1 normal")
            p2 = pass_(True, 0, "pass 2 inverted")
            T.log(f"PRIMARY total bad {p1['res']['bad'] + p2['res']['bad']} of {p1['res']['checked'] + p2['res']['checked']}")
        if a.double:
            T.log("SECOND RESULT (not primary): read-back with 2 extra reads of a bad burst")
            pass_(False, 2, "double-read pass 1 normal")
        if a.extend:
            extend(run, results, T, seed, SWAP[0])
    d.io.close()
    return 0



if __name__ == "__main__":
    sys.exit(main())
