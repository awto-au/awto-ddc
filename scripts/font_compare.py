#!/usr/bin/env python3
"""Render the current RTD/AWTO fonts and native bitmap-font candidates."""

import importlib.util
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
RTDFW = Path("/mnt/2tb/git/awto-rtdfw-ui")
GEN = RTDFW / "tools/gen_font.py"
OUT = ROOT / "tmp/font-comparison.png"
FONT_DIR = ROOT / "tmp/font-candidates"
SDK = ROOT / "tmp/sdcc-port/src"
BODY = SDK / "User/RTD Series/RTD2014Osd/Header/TextTableBody/Rtd2014OsdTextTableBody_0.h"
WIDTHS = SDK / "User/RTD Series/RTD2014Osd/Header/TextTableBody/Rtd2014OsdTextTableBody_FontWidthTable.h"
SAMPLE = (
    "GPIO INPUT DIAGNOSTICS",
    "INPUT  PIN S  RAW  VALUE",
    "GPIO   65  1  -    DIGITAL",
    "ADC2   96  1  248  3.209V",
    "I 1 l i    I1li    W M 0",
)


def load_generator():
    spec = importlib.util.spec_from_file_location("awto_gen_font", GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sdk_bits(tile):
    """Apply the SDK source font's triple-byte row reorder."""
    rows = []
    for k in range(0, 27, 3):
        a, b, c = tile[k:k + 3]
        for row in ((a >> 4) << 8 | (b >> 4) << 4 | c >> 4,
                    (a & 0xF) << 8 | (b & 0xF) << 4 | c & 0xF):
            rows.append([(row >> bit) & 1 for bit in range(11, -1, -1)])
    return rows


def proportional_glyphs():
    """Return the SDK's original glyph bitmap and advertised pixel width."""
    width_text = WIDTHS.read_text().split("BYTE __code tsFontWidth0[] =", 1)[1].split("};", 1)[0]
    widths = [int(x) for x in re.findall(r"\d+", width_text)]
    wi = 0
    glyphs = {}
    for line in BODY.read_text().splitlines():
        if "//" not in line:
            continue
        data, comment = line.split("//", 1)
        raw = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", data))
        match = re.match(r"(U[0-9A-F]{4}|_FONT_SPACE_1),\s*(\d+),", comment)
        if not match or not raw:
            continue
        count = int(match.group(2))
        glyph_widths = widths[wi:wi + count]
        wi += count
        if not match.group(1).startswith("U"):
            continue
        rows_by_tile = [sdk_bits(raw[k * 27:(k + 1) * 27]) for k in range(count)]
        rows = [sum((rows_by_tile[k][y][:glyph_widths[k]] for k in range(count)), []) for y in range(18)]
        glyphs[chr(int(match.group(1)[1:], 16))] = (rows, sum(glyph_widths))
    return glyphs


def rows_image(rows):
    height = len(rows)
    width = len(rows[0]) if rows else 1
    image = Image.new("1", (width, height))
    image.putdata([255 if pixel else 0 for row in rows for pixel in row])
    return image


def load_bdf(path):
    """Load encoded glyph bitmaps verbatim from a fixed-cell BDF."""
    lines = path.read_text().splitlines()
    glyphs = {}
    encoding = None
    bitmap = None
    for line in lines:
        if line.startswith("ENCODING "):
            encoding = int(line.split()[1])
        elif line == "BITMAP":
            bitmap = []
        elif line == "ENDCHAR":
            if encoding is not None and bitmap is not None:
                width = max(1, max((len(value) * 4 for value in bitmap), default=1))
                glyphs[chr(encoding)] = [
                    [(int(value, 16) >> bit) & 1 for bit in range(width - 1, -1, -1)]
                    for value in bitmap
                ]
            encoding = None
            bitmap = None
        elif bitmap is not None:
            bitmap.append(line.strip())
    return glyphs


def render_prop(glyphs, scale):
    widths = []
    for line in SAMPLE:
        widths.append(sum((glyphs.get(ch, glyphs["?"])[1] if ch != " " else 4) + 1 for ch in line))
    canvas = Image.new("RGB", (max(widths) * scale + 32, len(SAMPLE) * 22 * scale + 24), "white")
    for row, line in enumerate(SAMPLE):
        x = 16
        y = 12 + row * 22 * scale
        for ch in line:
            if ch == " ":
                x += 5 * scale
                continue
            rows, width = glyphs.get(ch, glyphs["?"])
            glyph = rows_image(rows).resize((width * scale, 18 * scale), Image.Resampling.NEAREST).convert("RGB")
            blue = Image.new("RGB", glyph.size, "#0756b5")
            canvas.paste(blue, (x, y), glyph.convert("L"))
            x += (width + 1) * scale
    return canvas


def render_fixed(glyphs, cell_w, cell_h, scale):
    canvas = Image.new("RGB", (max(len(x) for x in SAMPLE) * cell_w * scale + 32,
                               len(SAMPLE) * (cell_h + 3) * scale + 24), "white")
    fallback = glyphs["?"]
    for row, line in enumerate(SAMPLE):
        for col, ch in enumerate(line):
            rows = glyphs.get(ch, fallback)
            glyph = rows_image(rows)
            glyph = glyph.resize((cell_w * scale, cell_h * scale), Image.Resampling.NEAREST).convert("RGB")
            blue = Image.new("RGB", glyph.size, "#0756b5")
            canvas.paste(blue, (16 + col * cell_w * scale, 12 + row * (cell_h + 3) * scale), glyph.convert("L"))
    return canvas


def main():
    gen = load_generator()
    prop = proportional_glyphs()
    spleen = {ch: [row[:8] for row in gen.unpacked(tile)]
              for ch, tile in gen.bitmap_glyphs(gen.SPLEEN, 16, "Spleen").items()}
    tamzen = {ch: [row[:8] for row in gen.unpacked(tile)]
              for ch, tile in gen.bitmap_glyphs(gen.TAMZEN, 15, "Tamzen").items()}

    panels = (
        ("1. EXISTING REALTEK PROPORTIONAL - pop-ups/status", render_prop(prop, 2)),
        ("2. AWTO DEFAULT: SPLEEN FIXED 8x16 - no scaling", render_fixed(spleen, 8, 18, 2)),
        ("3. AWTO OPTION: TAMZEN FIXED 8x15 - no scaling", render_fixed(tamzen, 8, 18, 2)),
    )
    label_font = ImageFont.load_default(size=20)
    width = max(panel.width for _, panel in panels) + 40
    height = sum(panel.height + 54 for _, panel in panels) + 20
    out = Image.new("RGB", (width, height), "#d7d7d7")
    y = 20
    draw = ImageDraw.Draw(out)
    for label, panel in panels:
        draw.text((20, y), label, fill="#111111", font=label_font)
        y += 34
        out.paste(panel, (20, y))
        y += panel.height + 20
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
