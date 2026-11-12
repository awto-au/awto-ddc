#!/usr/bin/env python3
"""Rasterise Material Symbols SVGs to 1-bpp OSD cell sizes + contact sheet next to the Realtek SDK icons.

usage: icon_raster.py [--svg-dir DIR] [--out DIR] [--thr 0.5]
  SVGs: /vendors/google/material-symbols/svg-400-outlined (Apache-2.0, see README there).
  Render: inkscape -> 512 px PNG, crop to ink bbox, fit into the cell (BOX downsample), threshold.
Writes OUT/ (default tmp/icons/):
  grids/<name>.txt   one `#`/`.` grid per size, for hand fixing
  sheet.png, index.html   left = SDK icons (asset_sheet decoder), right = Material at each size x4 + pixel grid
Log: tmp/logs/icon_raster.log
"""
import argparse
import html
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asset_sheet as AS  # noqa: E402  (SDK blob decoder)

ROOT = HERE.parent
LOG = ROOT / "tmp/logs/icon_raster.log"
SVG_DIR = Path("/vendors/google/material-symbols/svg-400-outlined")
SIZES = [(12, 18), (16, 16), (8, 16), (24, 24), (6, 12), (5, 8)]
HI = 512
SDK_PANELS = ["tFONT1_GLOBAL", "tOSD_ONE_PIECE_ICON", "tFONT1_ICON_HDMI", "tFONT1_ICON_DP", "tFONT1_ICON_VGA",
              "tFONT1_ICON_DVI", "tFONT1_ICON_NO_PORT", "tFONT1_ICON_INPUT", "tFONT1_ICON_TYPE_C_MODE",
              "tFONT1_ICON_AUTOSELECT", "tFONT1_ICON_INFORMATION"]
BG, FG = (24, 24, 24), (230, 230, 230)
F16 = ImageFont.load_default(size=16)
F22 = ImageFont.load_default(size=22)
SC = 4


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def render_hi(svg, png):
    r = subprocess.run(["inkscape", str(svg), "-o", str(png), "-w", str(HI), "-h", str(HI), "--export-background-opacity=0"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"inkscape {svg.name}: {r.stderr[-200:]}")
    a = np.asarray(Image.open(png).convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(a > 8)
    return Image.fromarray(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1])


def to_cell(alpha, w, h, thr):
    """Fit alpha bbox into w x h (1 px margin when the cell is >= 12 wide), BOX-downsample, threshold -> bool array."""
    m = 1 if min(w, h) >= 12 else 0
    bw, bh = w - 2 * m, h - 2 * m
    s = min(bw / alpha.width, bh / alpha.height)
    nw, nh = max(1, round(alpha.width * s)), max(1, round(alpha.height * s))
    im = alpha.resize((nw, nh), Image.BOX)
    out = np.zeros((h, w), bool)
    ox, oy = (w - nw) // 2, (h - nh) // 2
    out[oy:oy + nh, ox:ox + nw] = np.asarray(im) / 255.0 >= thr
    return out


def grid_text(b):
    return "\n".join("".join("#" if v else "." for v in row) for row in b)


def cell_image(b):
    h, w = b.shape
    im = Image.new("RGB", (w * SC + 1, h * SC + 1), (40, 40, 40))
    d = ImageDraw.Draw(im)
    for y in range(h):
        for x in range(w):
            d.rectangle([x * SC + 1, y * SC + 1, x * SC + SC - 1, y * SC + SC - 1], fill=(255, 255, 255) if b[y, x] else (0, 0, 0))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--svg-dir", type=Path, default=SVG_DIR)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/icons")
    ap.add_argument("--thr", type=float, default=0.5)
    a = ap.parse_args()
    out = a.out
    (out / "grids").mkdir(parents=True, exist_ok=True)
    (out / "hi").mkdir(exist_ok=True)
    names = sorted(p.stem for p in a.svg_dir.glob("*.svg"))
    panels = []
    for n in names:
        alpha = render_hi(a.svg_dir / f"{n}.svg", out / "hi" / f"{n}.png")
        cells = [to_cell(alpha, w, h, a.thr) for w, h in SIZES]
        (out / "grids" / f"{n}.txt").write_text(
            "\n\n".join(f"# {n} {w}x{h}\n{grid_text(c)}" for (w, h), c in zip(SIZES, cells)) + "\n")
        # panel: name header, then each size with its label above
        ims = [cell_image(c) for c in cells]
        W = sum(i.width + 10 for i in ims) + 6
        H = 24 + 16 + max(i.height for i in ims) + 6
        p = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(p)
        d.text((4, 2), n, fill=(150, 200, 255), font=F16)
        x = 4
        for (w, h), im in zip(SIZES, ims):
            d.text((x, 22), f"{w}x{h}", fill=FG, font=ImageFont.load_default(size=12))
            p.paste(im, (x, 38))
            x += im.width + 10
        panels.append(p)
    log(f"rendered {len(names)} symbols x {len(SIZES)} sizes")

    # left: SDK icons
    blobs = {n: (s, b) for n, s, b in AS.parse_blobs() if b}
    left = []
    for n in SDK_PANELS:
        if n in blobs:
            pn, _ = AS.blob_panel(n, *blobs[n])
            left.append(pn)
        else:
            log(f"SDK blob {n} not found")
    LW = 1900
    RW = 2200

    def shelf(ps, width, title):
        x, y, rowh, placed = 4, 40, 0, []
        for p in ps:
            if x + p.width > width:
                x, y, rowh = 4, y + rowh + 8, 0
            placed.append((p, x, y))
            x += p.width + 8
            rowh = max(rowh, p.height)
        img = Image.new("RGB", (width, y + rowh + 8), BG)
        ImageDraw.Draw(img).text((8, 8), title, fill=FG, font=F22)
        for p, px, py in placed:
            img.paste(p, (px, py))
        return img

    li = shelf(left, LW, "Realtek SDK icons (12x18 tiles, x3)")
    ri = shelf(panels, RW, f"Material Symbols outlined w400 ({len(names)}), x{SC}, sizes WxH")
    sheet = Image.new("RGB", (LW + RW + 8, max(li.height, ri.height)), BG)
    sheet.paste(li, (0, 0))
    sheet.paste(ri, (LW + 8, 0))
    sheet.save(out / "sheet.png")
    (out / "index.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>icons</title><style>body{{background:#111;color:#ddd;font:14px system-ui}}"
        f"img{{width:100%;image-rendering:pixelated}}</style><h1>Material vs SDK icons</h1><img src=sheet.png>"
        f"<p>Material Symbols: Apache-2.0, {html.escape(str(a.svg_dir))}. Grids: grids/*.txt</p>")
    log(f"wrote {out / 'sheet.png'} ({sheet.width}x{sheet.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
