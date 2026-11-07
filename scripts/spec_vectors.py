#!/usr/bin/env python3
"""Spec-side oracle vectors for the helpers wave (#65): computed from the maths in specs/arith.md and specs/reg.md, not from code.

usage: spec_vectors.py [--out specs/vectors]
  arith.tsv : fn a b_or_k c expected   (ar_muldiv a b c; ar_shldiv a k c), hex
  osdgap.tsv: dclk_khz hdouble expected (hb_osd_gap)
  Deterministic (fixed seed). Verifier step: the same inputs run through the reference image in fw_sim must agree.
Log: tmp/logs/spec_vectors.log
"""
from __future__ import annotations

import argparse, os, random, subprocess, sys, time
from pathlib import Path

M32 = 0xFFFFFFFF


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def shldiv(a: int, k: int, c: int) -> int:
    """round half up of a * 2^k / c, mod 2^32 (spec arith; domain 1 <= c <= 2^31)."""
    q, r = divmod(a << k, c)
    return (q + (2 * r >= c)) & M32


def muldiv(a: int, b: int, c: int) -> int:
    if c == 0:
        return M32                                         # x / 0 = all ones (spec arith section 1)
    if a == 0 or b == 0 or a < M32 // b:
        return (a * b // c) & M32                          # exact floor; a*b < 2^32 here
    p = a * b
    return (shldiv(p >> 32, 32, c) + shldiv(p & M32, 0, c)) & M32


def osd_gap(dclk_khz: int, hdouble: int, m2pll_mhz: int = 351, flash_div: int = 4, mcu_div: int = 1) -> int:
    num = (57 + 4 * 3) * m2pll_mhz * 1000 * 2
    q = num // (dclk_khz * flash_div * mcu_div) if dclk_khz else M32
    g = (q - 2) & 0xFFFF
    if hdouble:
        g = (g * 2) & 0xFFFF
    return max(min(g, 0xFF), 2)


def arith_cases(rng: random.Random):
    edge = [0, 1, 2, 3, 0xFFFF, 0x10000, 0x10001, 0x7FFFFFFF, 0x80000000, M32]
    for a in edge:
        for b in edge:
            for c in (1, 2, 3, 7, 1000, 0x10000, 0x7FFFFFFF, 0x80000000):
                yield ("muldiv", a, b, c)
    for b in (1, 2, 3, 0x10, 0x1000, 0x10000, 0xFFFF):          # fast/slow branch boundary
        lim = M32 // b
        for a in (lim - 1, lim, lim + 1):
            if 0 <= a <= M32:
                for c in (3, 1000, 594000):
                    yield ("muldiv", a, b, c)
    for _ in range(400):
        c = rng.choice([rng.randint(1, 0xFFFF), rng.randint(1, 0x80000000)])
        yield ("muldiv", rng.getrandbits(rng.choice([8, 16, 24, 32])), rng.getrandbits(rng.choice([8, 16, 24, 32])), c)
    for k in (0, 1, 8, 16, 20, 31, 32):
        for a in (0, 1, 3, 0x12345678, M32):
            for c in (1, 3, 0x10000, 0x80000000):
                yield ("shldiv", a, k, c)
    for _ in range(200):
        yield ("shldiv", rng.getrandbits(32), rng.randint(0, 32), rng.randint(1, 0x80000000))
    for a, b in ((0, 0), (1, 1), (0x3C0, 0x82320), (0x3C0, 0x83D7C), (0x10000, 0x10000), (M32, M32), (M32, 2)):   # c = 0
        yield ("muldiv", a, b, 0)


GAMMA_IDX = (0, 1, 2, 3, 4, 5, 10, 50, 100, 256, 512, 768, 1000, 1022, 1023, 1024, 1025)


def gamma_entry(g10: int, i: int, native10: int = 22) -> int:
    """spec gamma section 5: u14 with 4 fraction bits; 1024 power-law points, then 0x3FF0, then 0."""
    if i == 1024:
        return 0x3FF0
    if i == 1025:
        return 0
    return int(16368 * (i / 1023) ** (g10 / native10) + 0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=repo_root() / "specs" / "vectors")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(65)
    rows = []
    for fn, x, y, c in arith_cases(rng):
        v = muldiv(x, y, c) if fn == "muldiv" else shldiv(x, y, c)
        rows.append(f"{fn}\t{x:08x}\t{y:08x}\t{c:08x}\t{v:08x}")
    (a.out / "arith.tsv").write_text("# fn\ta\tb_or_k\tc\texpected (hex; spec arith)\n" + "\n".join(rows) + "\n")
    gaps = [f"{d}\t{h}\t{osd_gap(d, h):02x}" for d in (0, 1, 25000, 74250, 148500, 297000, 533250, 594000, 600000, 6054000, 7000000)
            for h in (0, 1)]
    (a.out / "osdgap.tsv").write_text("# dclk_khz\thdouble\texpected (hex; spec reg R5)\n" + "\n".join(gaps) + "\n")
    gam = [f"{g}\t{i}\t{gamma_entry(g, i):04x}" for g in (18, 20, 22, 24) for i in GAMMA_IDX]
    (a.out / "gamma.tsv").write_text("# gamma_x10\tindex\texpected u16 (hex; spec gamma section 5; accept +-1)\n" + "\n".join(gam) + "\n")
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    with (root / "tmp/logs/spec_vectors.log").open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} arith {len(rows)} rows, osdgap {len(gaps)} rows -> {a.out}\n")
    print(f"arith {len(rows)}, osdgap {len(gaps)} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
