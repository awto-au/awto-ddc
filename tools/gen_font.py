#!/usr/bin/env python3
"""Build the menu font from the monitor SDK's normal Realtek UI font.

The SDK stores proportional glyphs as one or two 12 x 18, 1-bpp tiles.  The
AWTO menu has a fixed 40-column character map, so this tool centres normal
glyphs in a cell and condenses the three wide glyphs (%, @, W/w) to 12 px.
The letterforms are therefore the same ones used by the information/debug
cards; only their cell spacing differs.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DDC = Path(os.environ.get("AWTO_DDC_MAIN", "/mnt/2tb/git/awto-ddc"))
SDK = Path(os.environ.get("AWTO_SDK_PORT", DDC / "tmp/sdcc-port/src"))
BODY = SDK / "User/RTD Series/RTD2014Osd/Header/TextTableBody/Rtd2014OsdTextTableBody_0.h"
WIDTHS = SDK / "User/RTD Series/RTD2014Osd/Header/TextTableBody/Rtd2014OsdTextTableBody_FontWidthTable.h"
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
    text = (ROOT / "awto/osd/charset.txt").read_text()
    return sorted(set(c for c in text if FIRST <= ord(c) <= LAST and c != "\n"))


def bits(tile):
    """Apply the SDK's triple-byte reorder to its proportional source tile."""
    rows = []
    for k in range(0, TILE_BYTES, 3):
        a, b, c = tile[k:k + 3]
        for row in ((a >> 4) << 8 | (b >> 4) << 4 | c >> 4,
                    (a & 0xF) << 8 | (b & 0xF) << 4 | c & 0xF):
            rows.append([(row >> bit) & 1 for bit in range(CW - 1, -1, -1)])
    return rows


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


def sdk_glyphs():
    width_text = WIDTHS.read_text().split("BYTE __code tsFontWidth0[] =", 1)[1].split("};", 1)[0]
    widths = [int(x) for x in re.findall(r"\d+", width_text)]
    wi = 0
    glyphs = {}
    for line in BODY.read_text().splitlines():
        if "//" not in line:
            continue
        data, comment = line.split("//", 1)
        raw = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", data))
        m = re.match(r"(U[0-9A-F]{4}|_FONT_SPACE_1),\s*(\d+),", comment)
        if not m or not raw:
            continue
        count = int(m.group(2))
        ws = widths[wi:wi + count]
        wi += count
        if len(raw) != count * TILE_BYTES:
            raise SystemExit(f"bad SDK glyph {m.group(1)}: {len(raw)} bytes for {count} tiles")
        if not m.group(1).startswith("U"):
            continue
        cp = int(m.group(1)[1:], 16)
        src_rows = [bits(raw[k * TILE_BYTES:(k + 1) * TILE_BYTES]) for k in range(count)]
        width = sum(ws)
        rows = [sum((src_rows[k][y][:ws[k]] for k in range(count)), []) for y in range(CH)]
        if width > CW:
            im = Image.new("1", (width, CH))
            im.putdata([255 if p else 0 for row in rows for p in row])
            im = im.resize((CW, CH), Image.Resampling.LANCZOS).convert("1")
            rows = [[1 if im.getpixel((x, y)) else 0 for x in range(CW)] for y in range(CH)]
        else:
            left = (CW - width) // 2
            rows = [[0] * left + row + [0] * (CW - width - left) for row in rows]
        tile = packed(rows)
        assert unpacked(tile) == rows
        glyphs[chr(cp)] = tile
    return glyphs


def symbol(ch):
    """Four menu marks absent from the SDK's Latin table, drawn at its weight."""
    rows = [[0] * CW for _ in range(CH)]
    def px(x, y):
        if 0 <= x < CW and 0 <= y < CH:
            rows[y][x] = 1
    if ch in "<>":
        for k in range(5):
            x = 3 + k if ch == ">" else 8 - k
            for d in (0, 1):
                px(x, 5 + k + d); px(x, 12 - k - d)
    elif ch == "^":
        for k in range(4):
            for d in (0, 1):
                px(5 - k, 5 + k + d); px(6 + k, 5 + k + d)
    else:  # *
        for k in range(-3, 4):
            px(6 + k, 9); px(6, 9 + k); px(6 + k, 9 + k); px(6 + k, 9 - k)
    return packed(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", type=Path)
    args = ap.parse_args()
    normal = sdk_glyphs()
    chars = charset()
    for ch in "<>^*":
        normal[ch] = symbol(ch)
    blank = bytes(TILE_BYTES)
    tiles, ids = [blank], {blank: 0}
    glyphs = {}
    fallback = normal["?"]
    for ch in chars:
        tile = normal.get(ch, fallback)
        if tile not in ids:
            ids[tile] = len(tiles)
            tiles.append(tile)
        glyphs[ch] = ids[tile]
    rows = [f"    {glyphs.get(chr(c), glyphs.get('?', 0))},  /* {chr(c)!r} */"
            for c in range(FIRST, LAST + 1)]
    data = b"".join(tiles)
    chunks = osd_vlc.encode_chunks(data, TILE_BYTES, limit=4096)
    joined = b"".join(blob for _, _, blob in chunks)
    out = ["/* font_data.inc: GENERATED by tools/gen_font.py from the normal Realtek UI font.",
           f" * {len(chars)} characters, {len(tiles)} tiles, {len(data)} B raw, {len(joined)} B VLC. Do not edit. */",
           f"#define OSD_FONT_FIRST  0x{FIRST:02X}", f"#define OSD_FONT_LAST   0x{LAST:02X}",
           f"#define OSD_FONT_TILES  {len(tiles)}",
           f"static const uint8_t __code font_ids[{LAST - FIRST + 1}] = {{"] + rows + ["};", "",
           f"static const uint8_t __code font_blob0[{len(joined)}] = {{"]
    for k in range(0, len(joined), 16):
        out.append("    " + ", ".join(f"0x{x:02X}" for x in joined[k:k + 16]) + ",")
    out.append("};")
    offset, load = 0, []
    for first, count, blob in chunks:
        load.append(f"font_blob(font_blob0 + {offset}, {first});")
        offset += len(blob)
        assert osd_vlc.decode(blob) == data[first * TILE_BYTES:(first + count) * TILE_BYTES]
    out.append("#define FONT_LOAD_CHUNKS " + " ".join(load))
    (ROOT / "awto/osd/font_data.inc").write_text("\n".join(out) + "\n")
    if args.png:
        cols = 16
        im = Image.new("1", (cols * (CW + 2), ((len(chars) + cols - 1) // cols) * (CH + 2)))
        for i, ch in enumerate(chars):
            tile_rows = unpacked(normal.get(ch, fallback))
            glyph = Image.new("1", (CW, CH))
            glyph.putdata([255 if p else 0 for row in tile_rows for p in row])
            im.paste(glyph, ((i % cols) * (CW + 2), (i // cols) * (CH + 2)))
        args.png.parent.mkdir(parents=True, exist_ok=True)
        im.resize((im.width * 3, im.height * 3), Image.Resampling.NEAREST).save(args.png)
    log(f"normal Realtek UI font: {len(chars)} chars, {len(tiles)} tiles, {len(joined)} B VLC; round trip byte-exact")


if __name__ == "__main__":
    main()
