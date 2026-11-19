#!/usr/bin/env python3
"""Asteroids screensaver shape data -> fw/test/asteroids_data.inc (gitignored; fw_build.py runs this first, docs/asteroids.md).

usage: gen_asteroids.py [--out PATH] [--fallback] [--png OUT.png]
  - Source of rocks / saucer / ship hulls / thrust flames: the local ROM through scripts/asteroids_dvg.py (decoded geometry, never committed).
    ROM absent or undecodable (or --fallback): our own outlines below, same shape ids. Digits are always our own.
  - Shapes: int8 vertex pairs (x, y; y up), polylines [n, x0, y0, ..] ended by n = 0. Ship hulls / flames are the 16 angles r * 5.625 deg
    (r = 0..15, tip right at r = 0, counter-clockwise); the firmware turns them by quarter turns.
Log: ./tmp/logs/gen_asteroids.log
"""
import argparse
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asteroids_dvg as D
import isostamp
import osd_gfx as OG

STEPS = 16                      # ship angles per quarter turn
STEP_DEG = 90.0 / STEPS
N_ROCKS = 4
ID_SAUCER = N_ROCKS
ID_HULL = ID_SAUCER + 1
ID_FLAME = ID_HULL + STEPS
ID_DIGIT = ID_FLAME + STEPS
N_CHARS = 5                     # info-line letters after the digits: x . F P S (fw/test/asteroids.c AWTO_AST_CH_*)
N_SHAPES = ID_DIGIT + 10 + N_CHARS
INT8_MAX = 127
CODE_BANK = 8                   # data and its readers (fw/test/asteroids.c) share this bank; bank 8 had the most room, bank 13 only ~3 KB (message table reserve)

# own outlines (fallback and digits); units as the ROM shapes: rocks +-32, saucer +-40 x, ship tip radius ~56, digits 8 x 12
FB_ROCK_R = ((30, 24, 32, 26, 31, 22, 28, 32, 25, 30, 23, 29),
             (32, 27, 21, 30, 25, 32, 23, 28, 31, 22, 29, 26),
             (26, 32, 24, 29, 32, 23, 30, 27, 21, 31, 28, 25),
             (31, 23, 29, 32, 26, 22, 30, 24, 32, 27, 21, 30))
FB_SAUCER = (((-36, -6), (-14, -18), (14, -18), (36, -6), (14, 6), (-14, 6), (-36, -6)), ((-12, 6), (-8, 16), (8, 16), (12, 6)))
FB_SHIP = ((48, 0), (-36, 22), (-22, 0), (-36, -22), (48, 0))       # pointing right
FB_FLAME = ((-26, -8), (-46, 0), (-26, 8))
DIGITS = (
    (((0, 0), (0, 12), (8, 12), (8, 0), (0, 0)),),
    (((4, 0), (4, 12)),),
    (((0, 12), (8, 12), (8, 6), (0, 6), (0, 0), (8, 0)),),
    (((0, 12), (8, 12), (8, 0), (0, 0)), ((0, 6), (8, 6))),
    (((0, 12), (0, 6), (8, 6)), ((8, 12), (8, 0))),
    (((8, 12), (0, 12), (0, 6), (8, 6), (8, 0), (0, 0)),),
    (((8, 12), (0, 12), (0, 0), (8, 0), (8, 6), (0, 6)),),
    (((0, 12), (8, 12), (8, 0)),),
    (((0, 0), (0, 12), (8, 12), (8, 0), (0, 0)), ((0, 6), (8, 6))),
    (((8, 6), (0, 6), (0, 12), (8, 12), (8, 0), (0, 0)),),
    (((0, 0), (8, 12)), ((0, 12), (8, 0))),                                          # x
    (((3, 0), (5, 0)),),                                                             # .
    (((8, 12), (0, 12), (0, 0)), ((0, 6), (6, 6))),                                  # F
    (((0, 0), (0, 12), (8, 12), (8, 6), (0, 6)),),                                   # P
    (((8, 12), (0, 12), (0, 6), (8, 6), (8, 0), (0, 0)),),                           # S
)

LOG = None


def say(s):
    line = f"{isostamp.now()} {s}"
    LOG.write(line + "\n")
    LOG.flush()
    print(line, flush=True)


def rot(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (round(p[0] * c - p[1] * s), round(p[0] * s + p[1] * c))


def quarter(p, n):                       # exact turns of n * 90 degrees counter-clockwise (y up)
    for _ in range(n % 4):
        p = (-p[1], p[0])
    return p


def fallback_shapes():
    sh = {}
    for i, radii in enumerate(FB_ROCK_R):
        pts = [rot((r, 0), k * 360.0 / len(radii)) for k, r in enumerate(radii)]
        sh[i] = [pts + [pts[0]]]
    sh[ID_SAUCER] = [list(p) for p in FB_SAUCER]
    for r in range(STEPS):
        sh[ID_HULL + r] = [[rot(p, r * STEP_DEG) for p in FB_SHIP]]
        sh[ID_FLAME + r] = [[rot(p, r * STEP_DEG) for p in FB_FLAME]]
    return sh


def rom_shapes(zip_path):
    words = D.load_rom(zip_path)
    dvg = D.Dvg(words)
    cat = D.catalog(dvg, words)

    def lines(name):
        segs, _ = dvg.decode(cat[name])
        return [[(int(round(x)), int(round(y))) for x, y in pl] for pl in D.polylines(segs, 0)]

    sh = {i: lines("rock%d" % i) for i in range(N_ROCKS)}
    sh[ID_SAUCER] = lines("saucer")
    for r in range(STEPS):
        if r == 0:                                       # tip right = the 90 degree hull turned back a quarter
            hull = [[quarter(p, 3) for p in pl] for pl in lines("hull%02d" % (STEPS - 1))]
            flame = lines("flame00")
        else:
            hull = lines("hull%02d" % (r - 1))
            flame = lines("flame%02d" % r)
        ex, ey = hull[-1][-1]                            # the flame hangs from the closed hull's end point
        sh[ID_HULL + r] = hull
        sh[ID_FLAME + r] = [[(x + ex, y + ey) for x, y in pl] for pl in flame]
    return sh


def encode(sh):
    blob, offs = bytearray(), []
    for i in range(N_SHAPES):
        offs.append(len(blob))
        for pl in sh[i]:
            assert 2 <= len(pl) <= 255
            blob.append(len(pl))
            for x, y in pl:
                assert -INT8_MAX <= x <= INT8_MAX and -INT8_MAX <= y <= INT8_MAX, (i, x, y)
                blob += bytes([x & 0xFF, y & 0xFF])
        blob.append(0)
    return bytes(blob), offs


def inc_text(sh, src):
    blob, offs = encode(sh)
    out = [f"/* asteroids_data.inc: GENERATED by scripts/gen_asteroids.py, source: {src}. Gitignored, never committed (docs/asteroids.md). */",
           f"#define AWTO_AST_FROM_ROM {1 if src == 'rom' else 0}",
           f"#define AWTO_AST_N_SHAPES {N_SHAPES}", "#define AWTO_AST_SH_ROCK0 0", f"#define AWTO_AST_SH_SAUCER {ID_SAUCER}",
           f"#define AWTO_AST_SH_HULL {ID_HULL}", f"#define AWTO_AST_SH_FLAME {ID_FLAME}", f"#define AWTO_AST_SH_DIGIT {ID_DIGIT}",
           f"#define AWTO_AST_DATA_BYTES {len(blob)}", f"#define AWTO_AST_MAX_POLYS {max(len(v) for v in sh.values())}", f"#pragma place bank({CODE_BANK})",
           "static __code int8_t g_tAstData[AWTO_AST_DATA_BYTES] = {"]
    s = [str(b - 256 if b > 127 else b) for b in blob]
    out += ["    " + ", ".join(s[i:i + 24]) + "," for i in range(0, len(s), 24)]
    out += ["};", f"#pragma place bank({CODE_BANK})", "static __code uint16_t g_tAstOff[AWTO_AST_N_SHAPES] = {"]
    out += ["    " + ", ".join(str(o) for o in offs[i:i + 12]) + "," for i in range(0, len(offs), 12)]
    out += ["};"]
    return "\n".join(out) + "\n", len(blob)


def preview(sh, path):
    from PIL import Image, ImageDraw
    cell, cols = 130, 10
    img = Image.new("RGB", (cols * cell, ((N_SHAPES + cols - 1) // cols) * cell), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    for i in range(N_SHAPES):
        cx, cy = (i % cols) * cell + cell // 2, (i // cols) * cell + cell // 2
        k = 0.9 if i >= ID_DIGIT else 0.9
        for pl in sh[i]:
            dr.line([(cx + x * k, cy - y * k) for x, y in pl], fill=(230, 230, 230))
    img.save(path)


repo_root = OG.repo_root


def main():
    global LOG
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=root / "fw/test/asteroids_data.inc")
    ap.add_argument("--fallback", action="store_true", help="own outlines even when the ROM is there")
    ap.add_argument("--zip", default=os.environ.get("ASTEROIDS_ZIP", D.DEFAULT_ZIP))
    ap.add_argument("--png", type=Path)
    ap.add_argument("--check", action="store_true", help="exit 1 when the file on disk differs (nothing written)")
    a = ap.parse_args()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (root / "tmp/logs/gen_asteroids.log").open("a")
    sh, src = None, "fallback"
    if not a.fallback and Path(a.zip).is_file():
        try:
            sh, src = rom_shapes(a.zip), "rom"
        except Exception as e:                           # noqa: BLE001  any decode problem = the fallback, logged
            say(f"ROM {a.zip} not usable ({type(e).__name__}: {e}): own outlines")
    elif not a.fallback:
        say(f"ROM {a.zip} absent: own outlines")
    base = fallback_shapes()
    if sh is None:
        sh = base
    for i, d in enumerate(DIGITS):
        sh[ID_DIGIT + i] = [list(pl) for pl in d]
    text, n = inc_text(sh, src)
    same = a.out.exists() and a.out.read_text() == text
    if a.check:
        say(f"{a.out.name}: {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    if not same:
        a.out.write_text(text)
    say(f"asteroids shapes: {src}, {N_SHAPES} shapes, {n} B -> {a.out}")
    if a.png:
        preview(sh, a.png)
        say(f"preview {a.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
