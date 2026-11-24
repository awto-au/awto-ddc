"""tools/osd_lines (clipped walk, incremental cursor) against the original prototype in docs/osd-prototypes/osd-lines-12x18.zip:
same pixels and dirty flags after every call, host gcc, several tile sizes."""
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "docs/osd-prototypes/osd-lines-12x18.zip"
NEW = ROOT / "tools/osd_lines"
WORK = None          # per-run scratch dir, set by the fixture below


@pytest.fixture(autouse=True, scope="module")
def _work(tmp_path_factory):
    global WORK
    WORK = tmp_path_factory.mktemp("osd_lines_clip")


TILES = [(12, 18), (8, 8), (5, 7), (16, 16), (32, 32), (1, 1), (32, 3)]
RUN_LIMIT_S = 60                 # one harness run: ~1 s measured; expiry = hung harness

HARNESS = r"""
#include <stdio.h>
#include <string.h>
#include "osd_lines.h"
#define MAXC 6
#define MAXR 8
static uint8_t pix[MAXC * MAXR * OSD_TILE_BYTES], dirty[(MAXC * MAXR + 7) / 8];
static osd_canvas cv;
static uint32_t rng = 0x12345678u;
static uint32_t rnd(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static int16_t coord(int span)
{
    uint32_t k = rnd() % 100;
    if (k < 70) return (int16_t)((int32_t)(rnd() % (uint32_t)(span + 80)) - 40);
    if (k < 95) return (int16_t)((int32_t)(rnd() % 4001) - 2000);
    return (int16_t)(rnd() & 0xFFFF);
}
static uint32_t digest(void)
{
    uint32_t h = 2166136261u; size_t i;
    for (i = 0; i < sizeof(pix); i++) h = (h ^ pix[i]) * 16777619u;
    for (i = 0; i < sizeof(dirty); i++) h = (h ^ dirty[i]) * 16777619u;
    return h;
}
int main(void)
{
    int round, op;
    for (round = 0; round < 400; round++) {
        uint8_t cols = (uint8_t)(1 + rnd() % MAXC), rows = (uint8_t)(1 + rnd() % MAXR);
        int w = cols * OSD_TILE_W, h = rows * OSD_TILE_H;
        memset(pix, 0, sizeof(pix)); memset(dirty, 0, sizeof(dirty));
        osd_canvas_init(&cv, cols, rows, pix, sizeof(pix), dirty, sizeof(dirty));
        printf("i %08x\n", digest());
        for (op = 0; op < 400; op++) {
            uint32_t k = rnd() % 100;
            uint8_t ink = (rnd() % 8) != 0;
            if (k < 2) { osd_clear(&cv); printf("c %08x\n", digest()); }
            else if (k < 4) { memset(dirty, 0, sizeof(dirty)); }
            else if (k < 20) { int16_t x = coord(w), y = coord(h); osd_pixel(&cv, x, y, ink); printf("p %08x\n", digest()); }
            else { int16_t x0 = coord(w), y0 = coord(h), x1 = coord(w), y1 = coord(h); osd_line(&cv, x0, y0, x1, y1, ink); printf("l %d %d %d %d %08x\n", x0, y0, x1, y1, digest()); }
        }
    }
    return 0;
}
"""


def build(src: Path, tag: str, tw: int, th: int) -> Path:
    exe = WORK / f"{tag}_{tw}x{th}"
    r = subprocess.run(["gcc", "-std=c99", "-O1", "-Wall", "-Werror", f"-DOSD_TILE_W={tw}", f"-DOSD_TILE_H={th}", f"-I{src}",
                        str(src / "osd_lines.c"), str(WORK / "harness.c"), "-o", str(exe)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    return exe


@pytest.mark.skipif(shutil.which("gcc") is None, reason="needs host gcc")
@pytest.mark.parametrize("tw,th", TILES)
def test_same_pixels_as_prototype(tw, th):
    ref = WORK / "ref"
    ref.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        for n in ("osd_lines.c", "osd_lines.h"):
            (ref / n).write_bytes(z.read("osd-lines/" + n))
    (WORK / "harness.c").write_text(HARNESS)
    out = []
    for src, tag in ((ref, "ref"), (NEW, "new")):
        r = subprocess.run([str(build(src, tag, tw, th))], capture_output=True, text=True, timeout=RUN_LIMIT_S, check=False)
        assert r.returncode == 0
        out.append(r.stdout.splitlines())
    assert len(out[0]) == len(out[1]) > 100000
    bad = [(a, b) for a, b in zip(*out) if a != b]
    assert not bad, f"{len(bad)} calls differ, first: ref {bad[0][0]} / new {bad[0][1]}"
