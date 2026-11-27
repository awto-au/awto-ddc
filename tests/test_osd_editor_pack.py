"""#234: the OSD editor packs 2 / 4 bpp tiles as the hardware stores them (bit planes, plane k = bit k), and osd_model reads them back."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools/osd_editor"))
import model as E
import osd_gfx as OG
import osd_model as M

RNG = np.random.default_rng(234)


def tile(bpp, h=18, w=12):
    return RNG.integers(0, 1 << bpp, (h, w), dtype=np.uint8)


def pacman_pack(g, bits):
    """gen_pacman_classic.pack() (removed in 723dc3df; 2-bit glyphs shown on unit 3): planes low bit first via osd_gfx.pack_rows."""
    rows = [list(map(int, r)) for r in g]
    if bits == 1:
        return OG.pack_rows(rows, lambda v: v & 1)
    return OG.pack_rows(rows, lambda v: v & 1) + OG.pack_rows(rows, lambda v: v >> 1 & 1)


def model_levels(data: bytes, bpp: int) -> np.ndarray:
    """Store the packed words as glyph id 0 and decode them with osd_model (2-bit offset 0, 4-bit offset 0)."""
    st = M.OsdState(regs=bytes(256))
    for k in range(len(data) // 3):
        st.font[k] = list(data[3 * k:3 * k + 3])
    g = {"font_base": 0}
    return M.glyph_levels2(st, g, 0) if bpp == 2 else M.glyph_levels4(st, g, 0) if bpp == 4 else M.glyph_bits(st, g, 0).astype(np.uint8)


def test_editor_2bpp_equals_pacman_packer():
    gs = E.GlyphSet(2, "12x18")
    for _ in range(8):
        t = tile(2)
        assert gs.pack(t) == pacman_pack(t, 2)
    assert E.GlyphSet(1, "12x18").pack(t & 1) == pacman_pack(t & 1, 1)


def test_editor_pack_reads_back_through_osd_model():
    for bpp in (1, 2, 4):
        t = tile(bpp)
        assert np.array_equal(model_levels(E.GlyphSet(bpp, "12x18").pack(t), bpp), t), bpp


def test_editor_pack_unpack_round_trip():
    for bpp in (1, 2, 4):
        for geom, (w, h, _) in E.GEOMS.items():
            gs = E.GlyphSet(bpp, geom)
            ts = [tile(bpp, h, w) for _ in range(3)]
            gs.tiles = ts
            back = E.GlyphSet(bpp, geom)
            back.from_raw(gs.raw())
            assert all(np.array_equal(a, b) for a, b in zip(ts, back.tiles, strict=True)), (bpp, geom)


def test_planes_not_row_major():
    t = np.zeros((18, 12), np.uint8)
    t[0, 0] = 1                                                    # 2 bpp value 1: bit 0 plane only, first word MSB
    by = E.GlyphSet(2, "12x18").pack(t)
    assert by[2] == 0x80 and not any(by[27:])                      # plane 0 = the first 9 words; plane 1 empty
