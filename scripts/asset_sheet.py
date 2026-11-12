#!/usr/bin/env python3
"""Contact sheets of every OSD screen, font and image in the firmware.

usage: asset_sheet.py CATALOG_DIR [--out DIR]
  CATALOG_DIR = osd_catalog.py output (screens: sheet.png). Reads the ported SDK source (tmp/sdcc-port/src) and the awto fonts.
Writes OUT/ (default tmp/asset_sheet/<catalog tag>/):
  screens.png        copy of the catalogue sheet (every pop-up, card and menu page)
  sdk_blobs_N.png    every SDK VLC blob (icons, logos, global fonts) decoded to 12x18 1 bpp tiles
  sdk_text_font.png  the SDK proportional text font (English table), glyph + width
  awto_fonts.png     Spleen 8x16 and Tamzen 8x15 (the awto menu fonts)
  index.html         all of the above on one page (VS Code opens it rendered)
Realtek-derived output stays in tmp/ (repo is private; scrub before any public use).
Log: tmp/logs/asset_sheet.log
"""
import argparse
import html
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import glyph_decode as GD  # noqa: E402
import font_compare as FC  # noqa: E402

ROOT = HERE.parent
LOG = ROOT / "tmp/logs/asset_sheet.log"
SDK = ROOT / "tmp/sdcc-port/src/User"
BLOB_FILES = [
    SDK / "RTD Series/RTD2014Osd/Code/RTD2014OsdFontVLC.c",
    SDK / "RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_1.c",
    SDK / "RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_2.c",
    SDK / "RTD Factory/Code/RTDFactoryFunction.c",
    SDK / "RTD Series/RTD2014Osd/Code/RTD2014OsdFontTable.c",
]
HEX_FONTS = [("Spleen 8x16 (awto menu default)", Path("/mnt/2tb/git/awto-rtdfw-ui/awto/osd/spleen-8x16.hex"), 8, 16),
             ("Tamzen 8x15 (awto menu option)", Path("/mnt/2tb/git/awto-rtdfw-ui/awto/osd/tamzen-8x15.hex"), 8, 15)]
PAGE_W, PAGE_MAX_H, SCALE = 3840, 7000, 3
BG, FG, PANEL = (24, 24, 24), (230, 230, 230), (255, 255, 255)
FONT = ImageFont.load_default(size=22)


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def parse_blobs():
    """(name, source file, bytes) for each `BYTE __code NAME[] = { 0x.. }` array in the SDK OSD font sources."""
    out = []
    pat = re.compile(r"BYTE\s+__code\s+(t[A-Za-z0-9_]+)\s*\[\s*\]\s*=\s*\{(.*?)\};", re.S)
    for f in BLOB_FILES:
        if not f.exists():
            log(f"missing source {f}")
            continue
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", f.read_text(errors="replace"), flags=re.S)
        for m in pat.finditer(text):
            by = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(2)))
            out.append((m.group(1), f.name, by))
    return out


def blob_panel(name, src, by):
    """Decode a VLC blob to a panel image (12x18 tiles, 1 bpp); raw/short arrays are listed as not decoded."""
    try:
        _, _, tiles = GD.decode_blob(by, 0)
    except Exception as e:  # noqa: BLE001 - any malformed header = not a VLC blob
        return label_panel(name, src, f"{len(by)} B, not a VLC blob ({e})"), 0
    n = len(tiles) // 27
    if n == 0:
        return label_panel(name, src, f"{len(by)} B, no tiles"), 0
    cols = 6 if n == 24 else min(n, 16)                  # dynamic icons are 6 x 4 tiles; atlases 16 wide
    rows = (n + cols - 1) // cols
    g = Image.new("L", (cols * 13, rows * 19), 255)
    for t in range(n):
        r, c = divmod(t, cols)
        tile = GD.tile(tiles, t)
        im = Image.fromarray(255 - tile * 255).convert("L")
        g.paste(im, (c * 13, r * 19))
    g = g.resize((g.width * SCALE, g.height * SCALE), Image.NEAREST).convert("RGB")
    cap = f"{name}  [{src}]  {len(by)} B, {n} tiles" + ("" if len(tiles) % 27 == 0 else f" (+{len(tiles) % 27} B tail)")
    return caption(g, cap), n


def caption(im, text):
    w = max(im.width, 420)
    out = Image.new("RGB", (w + 8, im.height + 34), BG)
    ImageDraw.Draw(out).text((4, 4), text[:90], fill=FG, font=FONT)
    out.paste(im, (4, 30))
    return out


def label_panel(name, src, text):
    im = Image.new("RGB", (420, 40), (60, 30, 30))
    ImageDraw.Draw(im).text((6, 8), "-", fill=FG, font=FONT)
    return caption(im, f"{name}  [{src}]  {text}")


def pack(panels, stem, out, title):
    """Shelf-pack panels left to right into pages of PAGE_W x <= PAGE_MAX_H."""
    pages, cur, x, y, rowh = [], [], 4, 40, 0
    for p in panels:
        if x + p.width + 4 > PAGE_W:
            x, y, rowh = 4, y + rowh + 8, 0
        if y + p.height > PAGE_MAX_H and cur:
            pages.append((cur, y + rowh))
            cur, x, y, rowh = [], 4, 40, 0
        cur.append((p, x, y))
        x += p.width + 8
        rowh = max(rowh, p.height)
    pages.append((cur, y + rowh))
    names = []
    for i, (items, h) in enumerate(pages, 1):
        img = Image.new("RGB", (PAGE_W, h + 8), BG)
        ImageDraw.Draw(img).text((8, 8), f"{title} (page {i}/{len(pages)})", fill=FG, font=FONT)
        for p, px, py in items:
            img.paste(p, (px, py))
        name = f"{stem}_{i}.png" if len(pages) > 1 else f"{stem}.png"
        img.save(out / name)
        names.append(name)
    return names


def text_font_sheet(out):
    glyphs = FC.proportional_glyphs()
    cells = []
    for ch, (rows, w) in sorted(glyphs.items()):
        im = FC.rows_image(rows).convert("L")
        im = Image.eval(im, lambda v: 255 - v).convert("RGB").resize((im.width * 4, im.height * 4), Image.NEAREST)
        cell = Image.new("RGB", (max(im.width, 90) + 8, im.height + 60), BG)
        d = ImageDraw.Draw(cell)
        d.text((4, 2), f"U+{ord(ch):04X} w{w}", fill=FG, font=ImageFont.load_default(size=16))
        d.text((4, 22), ch if ch.isprintable() else "", fill=(150, 200, 255), font=FONT)
        cell.paste(im, (4, 52))
        cells.append(cell)
    names = pack(cells, "sdk_text_font", out, f"SDK proportional text font (English table): {len(glyphs)} glyphs")
    return names, len(glyphs)


def hex_font_panel(title, path, w, h):
    glyphs = []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        cp, bits = line.split(":")
        rows = [int(bits[i:i + 2], 16) for i in range(0, len(bits), 2)]
        glyphs.append((int(cp, 16), rows))
    cols = 24
    n = len(glyphs)
    rws = (n + cols - 1) // cols
    cw, ch = w + 2, h + 2
    im = Image.new("RGB", (cols * cw, rws * ch), (255, 255, 255))
    px = im.load()
    for i, (cp, rows) in enumerate(glyphs):
        gx, gy = (i % cols) * cw + 1, (i // cols) * ch + 1
        for y, rv in enumerate(rows[:h]):
            for x in range(w):
                if (rv >> (7 - x)) & 1:
                    px[gx + x, gy + y] = (0, 68, 166)
    im = im.resize((im.width * 4, im.height * 4), Image.NEAREST)
    chars = "".join(chr(cp) for cp, _ in glyphs)
    return caption(im, f"{title}: {n} glyphs: {chars}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    tag = a.catalog.resolve().name
    out = (a.out or ROOT / "tmp/asset_sheet" / tag).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sections = []

    shutil.copyfile(a.catalog / "sheet.png", out / "screens.png")
    sections.append(("Screens: every pop-up, card and menu page", ["screens.png"], "osd_catalog.py"))

    blobs = parse_blobs()
    panels, tiles, failed = [], 0, []
    for name, src, by in blobs:
        p, n = blob_panel(name, src, by)
        panels.append(p)
        tiles += n
        if n == 0:
            failed.append(name)
    names = pack(panels, "sdk_blobs", out, f"SDK VLC blobs: {len(blobs)} arrays, {tiles} tiles")
    sections.append((f"SDK icons, logos and global fonts: {len(blobs)} arrays, {tiles} tiles decoded, {len(failed)} not decodable "
                     f"({', '.join(failed[:12])}{'...' if len(failed) > 12 else ''})", names, "RTD2014OsdFont*.c"))

    names, n = text_font_sheet(out)
    sections.append((f"SDK proportional text font: {n} glyphs", names, "Rtd2014OsdTextTableBody_0.h"))

    fpanels = [hex_font_panel(*f) for f in HEX_FONTS if f[1].exists()]
    names = pack(fpanels, "awto_fonts", out, "awto menu fonts")
    sections.append(("awto menu fonts (Spleen, Tamzen)", names, "awto-rtdfw-ui awto/osd/*.hex"))

    body = "\n".join(
        f"<section><h2>{html.escape(t)}</h2><p>{html.escape(s)}</p>" + "".join(f'<a href="{n}"><img src="{n}"></a>' for n in ns) + "</section>"
        for t, ns, s in sections)
    (out / "index.html").write_text(f"""<!doctype html><meta charset=utf-8><title>OSD asset sheets {html.escape(tag)}</title>
<style>body{{font:14px system-ui;background:#111;color:#ddd;margin:16px}}img{{width:100%;image-rendering:pixelated;margin:8px 0}}
p{{color:#888}}</style><h1>OSD screens, fonts and images: {html.escape(tag)}</h1>{body}""")
    log(f"asset sheets {tag}: {len(blobs)} blobs ({tiles} tiles, {len(failed)} undecoded), -> {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
