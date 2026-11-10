#!/usr/bin/env python3
"""Build the AWTO fixed menu fonts from native Spleen and Tamzen bitmaps.

The RTD OSD always stores 12 x 18, 1-bpp tiles.  Each 8-pixel-wide source is
copied pixel for pixel into tile columns 2..9 (the 8-pixel cell is a centred window, zone 0) and vertically centred;
the character map selects an eight-pixel display width.  There is deliberately
no scaling, antialiasing, or outline-font rasterisation in this path.
"""
import argparse
import os
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DDC = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc"))
OSD = ROOT / "awto/osd"
# name, hex file, glyph rows, cell width px, row height px (the RTD row command 5-bit height), top tile row of the glyph.
# 8-wide fonts keep the 18 px row; smaller fonts use their own height from the top of the 12x18 tile.
FONT_SPECS = [
    ("spleen", "spleen-8x16.hex", 16, 8, 18, 1),
    ("tamzen", "tamzen-8x15.hex", 15, 8, 18, 1),
    ("spleen6", "spleen-6x12.hex", 12, 6, 12, 0),
    ("spleen5", "spleen-5x8.hex", 8, 5, 8, 0),
    ("tamzen5", "tamzen-5x9.hex", 9, 5, 9, 0),
    ("tamzen6", "tamzen-6x12.hex", 12, 6, 12, 0),
    ("tamzen7", "tamzen-7x13.hex", 13, 7, 13, 0),
]
sys.path.insert(0, str(DDC / "scripts"))
import osd_vlc  # noqa: E402

CW, CH, TILE_BYTES = 12, 18, 27
FIRST, LAST = 0x20, 0x7E
LOG = ROOT / "tmp/logs/gen_font.log"


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def charset():
    """Every printable ASCII character: the diagnostic console shows arbitrary text, so the set is not limited to the menu strings."""
    return [chr(c) for c in range(FIRST, LAST + 1)]


def packed(rows):
    """Pack 18 rows into nine little-endian 24-bit OSD font words."""
    out = bytearray()
    for k in range(0, CH, 2):
        upper = sum(p << (CW - 1 - x) for x, p in enumerate(rows[k]))
        lower = sum(p << (CW - 1 - x) for x, p in enumerate(rows[k + 1]))
        word = upper << 12 | lower
        out.extend((word & 0xFF, word >> 8 & 0xFF, word >> 16 & 0xFF))
    return bytes(out)


def unpacked(tile):
    """Decode a final little-endian OSD SRAM tile (the inverse of packed)."""
    rows = []
    for k in range(0, TILE_BYTES, 3):
        word = tile[k] | tile[k + 1] << 8 | tile[k + 2] << 16
        for shift in (12, 0):
            row = word >> shift & 0xFFF
            rows.append([(row >> bit) & 1 for bit in range(CW - 1, -1, -1)])
    return rows


def bitmap_glyphs(path, height, name, cw, top):
    """Read a vendored printable-ASCII subset; preserve every source pixel."""
    glyphs = {}
    for line in path.read_text().splitlines():
        line = line.partition("#")[0].strip()
        if not line:
            continue
        cp_text, raw_text = line.split(":", 1)
        raw = bytes.fromhex(raw_text)
        if len(raw) != height:
            raise SystemExit(f"bad {name} glyph U+{cp_text}: {len(raw)} rows")
        rows = [[0] * CW for _ in range(CH)]
        x0 = (CW - cw + 1) // 2                # the cell is a centred window of the tile (zone 0); odd widths start on the right column (seen on hardware, 5 px)
        for y, value in enumerate(raw, top):
            for x in range(cw):
                rows[y][x0 + x] = (value >> (7 - x)) & 1
        tile = packed(rows)
        assert unpacked(tile) == rows
        glyphs[chr(int(cp_text, 16))] = tile
    return glyphs


def atlas(chars, glyphs):
    """Use identical character IDs in both atlases so the map need not change."""
    blank = bytes(TILE_BYTES)
    fallback = glyphs["?"]
    tiles = [blank]
    ids = {" ": 0}
    for ch in chars:
        if ch != " ":
            ids[ch] = len(tiles)
            tiles.append(glyphs.get(ch, fallback))
    return tiles, ids


def emit_blob(out, name, tiles):
    data = b"".join(tiles)
    chunks = osd_vlc.encode_chunks(data, TILE_BYTES, limit=4096)
    joined = b"".join(blob for _, _, blob in chunks)
    out.append(f"static const uint8_t __code font_blob_{name}[{len(joined)}] = {{")
    for k in range(0, len(joined), 16):
        out.append("    " + ", ".join(f"0x{x:02X}" for x in joined[k:k + 16]) + ",")
    out.append("};")
    offset, load = 0, []
    for first, count, blob in chunks:
        load.append(f"font_blob(font_blob_{name} + {offset}, {first});")
        offset += len(blob)
        assert osd_vlc.decode(blob) == data[first * TILE_BYTES:(first + count) * TILE_BYTES]
    out.append(f"#define FONT_LOAD_{name.upper()} " + " ".join(load))
    out.append("")
    return len(joined)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", type=Path)
    ap.add_argument("--preview-font", default="spleen")
    args = ap.parse_args()
    chars = charset()
    fonts = {n: bitmap_glyphs(OSD / f, h, n, cw, top) for n, f, h, cw, rh, top in FONT_SPECS}
    atlases = {name: atlas(chars, glyphs) for name, glyphs in fonts.items()}
    ids = atlases["spleen"][1]
    rows = [f"    {ids.get(chr(c), ids.get('?', 0))},  /* {chr(c)!r} */"
            for c in range(FIRST, LAST + 1)]
    out = ["/* font_data.inc: GENERATED by tools/gen_font.py from Spleen and Tamzen bitmaps (FONT_SPECS).",
           f" * {len(chars)} characters, {len(atlases['spleen'][0])} tiles per atlas. Do not edit. */",
           f"#define OSD_FONT_FIRST  0x{FIRST:02X}", f"#define OSD_FONT_LAST   0x{LAST:02X}",
           f"#define OSD_FONT_TILES  {len(atlases['spleen'][0])}",
           f"#define OSD_FONT_N      {len(FONT_SPECS)}",
           f"static const uint8_t __code font_ids[{LAST - FIRST + 1}] = {{"] + rows + ["};", "",
           f"static const uint8_t __code font_cw[{len(FONT_SPECS)}] = {{" + ", ".join(str(f[3]) for f in FONT_SPECS) + "};",
           f"static const uint8_t __code font_rh[{len(FONT_SPECS)}] = {{" + ", ".join(str(f[4]) for f in FONT_SPECS) + "};", ""]
    sizes = {name: emit_blob(out, name, tiles) for name, (tiles, _) in atlases.items()}
    (ROOT / "awto/osd/font_data.inc").write_text("\n".join(out) + "\n")
    if args.png:
        spec = next(f for f in FONT_SPECS if f[0] == args.preview_font)
        normal, cwp = fonts[args.preview_font], spec[3]
        x0 = (CW - cwp + 1) // 2
        fallback = normal["?"]
        cols = 16
        im = Image.new("1", (cols * (CW + 2), ((len(chars) + cols - 1) // cols) * (CH + 2)))
        for i, ch in enumerate(chars):
            tile_rows = unpacked(normal.get(ch, fallback))
            glyph = Image.new("1", (cwp, CH))
            glyph.putdata([255 if p else 0 for row in tile_rows for p in row[x0:x0 + cwp]])
            im.paste(glyph, ((i % cols) * (CW + 2), (i // cols) * (CH + 2)))
        args.png.parent.mkdir(parents=True, exist_ok=True)
        im.resize((im.width * 3, im.height * 3), Image.Resampling.NEAREST).save(args.png)
    log(f"fixed fonts: {len(chars)} chars, {len(atlases['spleen'][0])} tiles each, "
        + ", ".join(f"{n} {sz} B" for n, sz in sizes.items()) + " VLC; native bitmap round trips byte-exact")


if __name__ == "__main__":
    main()
