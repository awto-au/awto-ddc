"""Glyph set model: tiles at 1/2/4 bpp, 12x18 or 24x36 (2x2 cells); pack, import, export. No Qt."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

import vlc_adapter as V

GEOMS = {"12x18": (12, 18, "a"), "24x36": (24, 36, "b")}
HEADER = re.compile(r"//\s*osd_editor:\s*name=(\S+)\s+bpp=(\d)\s+geom=(\S+)\s+tiles=(\d+)\s+chunks=(\d+)")


def ramp(bpp: int, rgb=(255, 40, 40)):
    n = (1 << bpp) - 1
    return [tuple(round(c * i / n) for c in rgb) for i in range(n + 1)]


@dataclass
class GlyphSet:
    bpp: int = 1
    geom: str = "12x18"
    tiles: list = field(default_factory=list)          # uint8 arrays (uh, uw), values 0..2^bpp-1
    palette: list = None
    name: str = "font"

    def __post_init__(self):
        if self.palette is None:
            self.palette = ramp(self.bpp)

    @property
    def uw(self): return GEOMS[self.geom][0]
    @property
    def uh(self): return GEOMS[self.geom][1]
    @property
    def tile_bytes(self): return self.uw * self.uh * self.bpp // 8
    @property
    def words_per_tile(self): return self.uw * self.uh * self.bpp // 24

    def variant(self):
        return V.Variant(self.bpp, GEOMS[self.geom][2], "fixed")

    def blank(self):
        return np.zeros((self.uh, self.uw), np.uint8)

    def pack(self, tile) -> bytes:
        return self.variant().pack(tile)

    def unpack(self, data: bytes):
        bits = "".join(format(data[i + 2], "08b") + format(data[i + 1], "08b") + format(data[i], "08b")
                       for i in range(0, len(data), 3))
        vals = [int(bits[i:i + self.bpp], 2) for i in range(0, len(bits), self.bpp)]
        return np.array(vals, np.uint8).reshape(self.uh, self.uw)

    def raw(self) -> bytes:
        return b"".join(self.pack(t) for t in self.tiles)

    def from_raw(self, data: bytes):
        tb = self.tile_bytes
        self.tiles = [self.unpack(data[i:i + tb]) for i in range(0, len(data) - tb + 1, tb)]

    def blobs(self) -> list:
        raw, step = self.raw(), (V.CHUNK // self.tile_bytes) * self.tile_bytes
        return [V.vlc_encode(raw[i:i + step]) for i in range(0, len(raw), step)] or [V.vlc_encode(b"")]

    def budget(self) -> dict:
        raw = len(self.tiles) * self.tile_bytes
        vlc = sum(len(b) for b in self.blobs()) if self.tiles else 0
        words = len(self.tiles) * self.words_per_tile
        return {"tiles": len(self.tiles), "font_words": words, "sram_words": V.SRAM_WORDS,
                "pct": 100.0 * words / V.SRAM_WORDS, "raw": raw, "vlc": vlc}

    def rgb(self, tile, scale=1):
        pal = np.array(self.palette, np.uint8)
        img = pal[np.minimum(tile, len(pal) - 1)]
        return np.kron(img, np.ones((scale, scale, 1), np.uint8)) if scale > 1 else img


# ---- export / import ------------------------------------------------------------------------------
def c_array(name, data, per=12):
    rows = [",".join("0x%02x" % b for b in data[i:i + per]) + "," for i in range(0, len(data), per)]
    return f"BYTE __code {name}[] =\n{{\n    " + "\n    ".join(rows) + "\n};\n"


def export_c(gs: GlyphSet, path, name=None, vlc=True):
    name = name or gs.name
    blobs = gs.blobs() if vlc else [gs.raw()]
    b = gs.budget()
    out = [f"// osd_editor: name={name} bpp={gs.bpp} geom={gs.geom} tiles={len(gs.tiles)} chunks={len(blobs)} "
           f"{'vlc' if vlc else 'raw'}",
           f"// font SRAM {b['font_words']} words ({b['pct']:.1f} % of {b['sram_words']}); flash raw {b['raw']} B, vlc {b['vlc']} B"]
    out += [c_array(f"{name}_{'VLC' if vlc else 'RAW'}{i}", blob) for i, blob in enumerate(blobs)]
    Path(path).write_text("\n".join(out))


def _hex_arrays(text):
    return [bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m)) for m in re.findall(r"\{(.*?)\}", text, re.S)]


def import_c(path) -> GlyphSet:
    """Our export (header line), or an OsdEdit 'HardWare VLC 2523V' .txt (1 bpp 12x18, one blob, no header)."""
    text = Path(path).read_text()
    m = HEADER.search(text)
    if m:
        gs = GlyphSet(int(m[2]), m[3], [], name=m[1])
        arrays = _hex_arrays(text)
        data = b"".join(V.vlc_decode(a) if "vlc" in text.split("\n", 1)[0] else a for a in arrays)
    else:
        gs = GlyphSet(1, "12x18", [], name=Path(path).stem)
        body = text.split("Palette End")[-1]
        data = V.vlc_decode(bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", body)))
    data = data[: len(data) // gs.tile_bytes * gs.tile_bytes]
    gs.from_raw(data)
    return gs


def quantise(gray: np.ndarray, bpp: int):
    n = (1 << bpp) - 1
    return np.rint(gray.astype(np.float32) * n / 255).astype(np.uint8)


def from_gray(gray: np.ndarray, bpp: int, geom: str, name="sheet", skip_blank=False) -> GlyphSet:
    gs = GlyphSet(bpp, geom, [], name=name)
    q = quantise(gray, bpp)
    for r in range(q.shape[0] // gs.uh):
        for c in range(q.shape[1] // gs.uw):
            t = q[r * gs.uh:(r + 1) * gs.uh, c * gs.uw:(c + 1) * gs.uw].copy()
            if not (skip_blank and not t.any()):
                gs.tiles.append(t)
    return gs


def import_png(path, bpp, geom, invert=False) -> GlyphSet:
    g = np.asarray(Image.open(path).convert("L"))
    return from_gray(255 - g if invert else g, bpp, geom, Path(path).stem)


def import_ttf(path, bpp, geom, chars=None, size=None) -> GlyphSet:
    gs = GlyphSet(bpp, geom, [], name=Path(path).stem.replace("-", "_"))
    v = gs.variant()
    size = size or v.size
    v.font = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)
    asc, desc = v.font.getmetrics()
    v.top = max(0, (v.uh - (asc + desc)) // 2)
    for ch in chars or [chr(c) for c in range(0x20, 0x7F)]:
        gs.tiles.append(v.draw(ch, v.uw).astype(np.uint8))
    return gs
