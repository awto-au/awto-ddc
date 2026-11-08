"""osd_model decoders against known data, no ucsim: VLC download vs glyph_decode, port word writes, protection,
window/char/geometry decode, palette, a rendered pixel check. Reference blobs = the encoder's own output (osd_logo_encode)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import osd_model as M  # noqa: E402
from glyph_decode import decode_blob, tile  # noqa: E402


class FakeM:
    """XRAM dict standing in for fw_sim.Machine: rd(a, n) -> bytes."""

    def __init__(self):
        self.x = {}

    def rd(self, a, n=1, space="xram"):
        return bytes(self.x.get(a + i, 0) for i in range(n))

    def set(self, a, v):
        self.x[a] = v


def port_write(m: FakeM, o: M.OsdModel, a: int, v: int):
    m.set(a, v)
    o.on_write(m, a)


def set_addr(m, o, addr, wopt):
    m.set(M.WOPT, wopt)
    port_write(m, o, M.WOPT, wopt)
    port_write(m, o, M.ADR_MSB, addr >> 8)
    port_write(m, o, M.ADR_LSB, addr & 255)


def make_blob(by: bytes) -> bytes:
    """Own minimal encoder (frequency-ordered value map, END = 0xFF code), independent of the decoder under test."""
    from glyph_decode import CODES
    cnt = [0] * 16
    for b in by:
        cnt[b >> 4] += 1
        cnt[b & 15] += 1
    vmap = sorted(range(16), key=lambda v: (-cnt[v], v))
    code = {v: CODES[i] for i, v in enumerate(vmap)}
    bits = "".join(code[n] for b in by for n in (b >> 4, b & 15))
    bits += "1" * (-len(bits) % 8) + "11111111"
    stream = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))
    return bytes(vmap[i] << 4 | vmap[i + 1] for i in range(0, 16, 2)) + len(stream).to_bytes(2, "big") + stream


def test_vlc_download_matches_glyph_decode():
    rng = np.random.default_rng(1)
    tiles = bytes(int(v) for v in rng.choice([0, 0, 0, 0xFF, 0xF0, 0x0F, 0x3C, 0xAA], size=27 * 6))
    blob = make_blob(tiles)
    m, o = FakeM(), M.OsdModel()
    for i in range(8):
        m.set(M.FRAME + 0x0F + i, blob[i])                        # VLC value map regs 0x3A0F..16
    m.set(M.FRAME + 0x17, 1)                                      # osd_compression_en
    base = 0x40
    set_addr(m, o, base, 0xE8)                                    # all planes, font SRAM
    for b in blob[10:]:
        port_write(m, o, M.DATA, b)
    assert decode_blob(blob, 0)[2] == tiles
    for t in range(6):
        words = [o.st.font[base + 9 * t + k] for k in range(9)]
        by = bytes(b for w in words for b in w)
        assert by == tiles[27 * t:27 * t + 27]
        assert (tile(by, 0) == tile(tiles, t)).all()
    assert base + 54 not in o.st.font                             # END code stops the decode


def test_plain_word_write_all_planes_and_single_plane():
    m, o = FakeM(), M.OsdModel()
    set_addr(m, o, 0x100, 0xE0)                                   # window SRAM, all bytes
    for v in (1, 2, 3, 4, 5, 6):
        port_write(m, o, M.DATA, v)
    assert o.st.win[0x100] == [1, 2, 3] and o.st.win[0x101] == [4, 5, 6]
    set_addr(m, o, 0x100, 0x40 | 0xE0 & 0x20)                     # bytesel 010 (B1 only)
    m.set(M.WOPT, 0x40)
    port_write(m, o, M.ADR_LSB, 0x00)
    port_write(m, o, M.DATA, 0x77)
    port_write(m, o, M.DATA, 0x88)
    assert o.st.win[0x100] == [1, 0x77, 3] and o.st.win[0x101] == [4, 0x88, 6]


def test_two_plane_write_order_and_protection():
    m, o = FakeM(), M.OsdModel()
    set_addr(m, o, 0x10, 0xA8)                                    # bytesel 101 = B0 + B2, font SRAM
    for v in (0x4C, 0x21):
        port_write(m, o, M.DATA, v)
    assert o.st.font[0x10] == [0x4C, 0, 0x21]
    m.set(M.FRAME + 0x33, 0x01)                                   # protect byte 0, bits in 0x3A34 kept
    m.set(M.FRAME + 0x34, 0x1F)
    set_addr(m, o, 0x10, 0x28)                                    # B0 only
    port_write(m, o, M.DATA, 0x60)
    assert o.st.font[0x10][0] == 0x4C & 0x1F | 0x60 & ~0x1F & 0xFF


def test_palette_autoincrement():
    m, o = FakeM(), M.OsdModel()
    port_write(m, o, M.LUT_ADDR, 0x80 | 5)
    for v in (1, 2, 3, 4, 5, 6):
        port_write(m, o, M.LUT_PORT, v)
    port_write(m, o, M.LUT_ADDR, 0)
    port_write(m, o, M.LUT_PORT, 9)
    assert o.st.pal[5] == (1, 2, 3) and o.st.pal[6] == (4, 5, 6) and o.st.pal[7] == (0, 0, 0)


def test_window_decode_boot_values():
    """osd.md measured firmware WIN0: ADR1 = 00 00 04, ADR2 = 00 9C 50, ADR3 = 00 04 81 -> (0,4)-(156,80), colour 4, win_en + blend."""
    win = {0x100: [0, 0, 0], 0x101: [0, 0, 4], 0x102: [0, 0x9C, 0x50], 0x103: [0, 4, 0x81]}
    w = M.decode_window(win, 0)
    assert (w["x0"], w["y0"], w["x1"], w["y1"], w["color"], w["en"], w["blend"]) == (0, 4, 156, 80, 4, 1, 1)
    win[0x103] = [0x20, 0x04, 0x81]
    assert M.decode_window(win, 0)["color"] == 0x24                   # win_color[5] in B0 bit5
    assert M.win_base(10) == 0x200 and M.win_base(18) == 0x220


def test_char_and_geometry_decode():
    assert M.decode_char([0x4C, 7, 0x10]) == dict(kind="1bit", id=7, width=12, fg=1, bg=0)
    assert M.decode_char([0x6C, 7, 0x00])["id"] == 263                  # B0[5]: font 256..511
    assert M.decode_char([0xC1, 0, 0])["kind"] == "4bit" and M.decode_char([0x80, 0, 0])["kind"] == "2bit"
    regs = bytearray(256)
    regs[0x01], regs[0x02], regs[0x00] = 0x21, 0x40 | 0x08 | 1, 0x10        # hori 0x21<<2|1, vert 0x10<<3|1, osd_en
    regs[0x0A], regs[0x0C], regs[0x0D], regs[0x0E] = 3, 0x19, 0x01, 0x3F
    st = M.OsdState(regs=bytes(regs))
    g = M.frame_geometry(st)
    assert (g["hd"], g["vd"], g["sx"], g["sy"], g["en"]) == (0x21 << 2 | 1, 0x10 << 3 | 1, 2, 2, 1)
    assert (g["fs_base"], g["font_base"]) == (0x019, 0x3F1)               # osd.md measured firmware boot values


def test_render_pixels():
    """Window 0 (red) under two glyphs at 2x: glyph 0 solid fg (blue), glyph 1 blank with bg 0 = transparent -> window shows."""
    regs = bytearray(256)
    regs[0x02], regs[0x0A] = 1, 3
    regs[0x0C], regs[0x0D], regs[0x0E] = 2, 0x00, 0x10                         # fs_base 2, font_base 0x100
    st = M.OsdState(regs=bytes(regs), ovl=(1, 0))                             # 0x6C[0] overlay port on (6652bc4)
    st.pal[1], st.pal[2] = (255, 0, 0), (0, 0, 255)
    st.font[0] = [0x80, 17, 2]                                                 # row command: 2 chars, height 18
    st.font[1] = [0, 0, 0]                                                     # end of rows
    st.font[2] = [0x4C, 0, 0x20]                                               # glyph 0: fg 2, bg 0
    st.font[3] = [0x4C, 1, 0x20]                                               # glyph 1
    for w in range(9):
        st.font[0x100 + w] = [0xFF, 0xFF, 0xFF]                                # glyph 0 solid
        st.font[0x100 + 9 + w] = [0, 0, 0]                                     # glyph 1 empty
    st.win[0x101], st.win[0x102], st.win[0x103] = [0, 0, 0], [0, 23, 17], [0, 1, 1]   # (0,0)-(23,17), colour 1, enabled
    img = M.render(st, 64, 64, bg=(9, 9, 9))
    assert tuple(img[0, 0]) == (0, 0, 255) and tuple(img[35, 23]) == (0, 0, 255)       # glyph 0 = 24x36 px at 2x
    assert tuple(img[0, 24]) == (255, 0, 0) and tuple(img[35, 47]) == (255, 0, 0)      # glyph 1 transparent: window colour
    assert tuple(img[36, 0]) == (9, 9, 9) and tuple(img[0, 48]) == (9, 9, 9)           # outside window and cells


def test_summary_counts():
    st = M.OsdState(regs=bytes(256))
    assert M.summary(st)["cells"] == 0


def sdk_pack2(c0, c1, c2, c3):
    """OsdFontPut2Bit colour packing (SDK RTD2014OsdFontTable.c), the encoder side of decode_char."""
    b0 = 0x80 | ((c0 & 8) << 2) | ((c1 & 8) << 1) | ((c3 & 7) << 1) | ((c0 & 4) >> 2)
    return b0, ((c0 & 3) << 6) | ((c2 & 7) << 3) | (c1 & 7)


def test_char_2bit_colours_roundtrip():
    for cols in ((0, 1, 2, 3), (9, 15, 7, 7), (4, 8, 5, 6), (15, 0, 0, 0)):
        b0, b2 = sdk_pack2(*cols)
        ch = M.decode_char([b0, 5, b2])
        assert ch["kind"] == "2bit" and ch["id"] == 5 and ch["width"] == 12
        assert ch["cols"] == (cols[0], cols[1], cols[2] & 7, cols[3] & 7), cols


def test_render_2bit_pixels_and_vlc_download():
    """A 2-bpp glyph loaded through the VLC data-port path draws its four levels with the char's four colours (derived layout)."""
    import osd_vlc
    lv = [[(x // 3 + y) % 4 for x in range(12)] for y in range(18)]
    data = osd_vlc.pack_unit(lv, 2)
    assert len(data) == 54
    blob = osd_vlc.encode(data)
    m, o = FakeM(), M.OsdModel()
    for i in range(8):
        m.set(M.FRAME + 0x0F + i, blob[i])
    m.set(M.FRAME + 0x17, 1)
    base = 0x100 + 18 * 3                                                       # font_base 0x100, glyph id 3 (offset 0)
    set_addr(m, o, base, 0xE8)
    for b in blob[10:]:
        port_write(m, o, M.DATA, b)
    assert bytes(b for k in range(18) for b in o.st.font[base + k]) == data
    regs = bytearray(256)
    regs[0x02], regs[0x0A] = 1, 0                                               # 1x scale
    regs[0x0C], regs[0x0D], regs[0x0E] = 2, 0x00, 0x10
    st = M.OsdState(regs=bytes(regs), font=o.st.font, ovl=(1, 0))
    st.pal[1], st.pal[2], st.pal[3] = (50, 0, 0), (150, 0, 0), (250, 0, 0)
    b0, b2 = sdk_pack2(0, 1, 2, 3)
    st.font[0] = [0x80, 17, 1]
    st.font[1] = [0, 0, 0]
    st.font[2] = [b0, 3, b2]
    img = M.render(st, 32, 32, bg=(9, 9, 9))
    for y in (0, 5, 17):
        for x in (0, 4, 11):
            v = lv[y][x]
            want = (9, 9, 9) if v == 0 else ((50, 0, 0), (150, 0, 0), (250, 0, 0))[v - 1]    # level 0 = colour index 0 = transparent
            assert tuple(img[y, x]) == want, (x, y, v)
