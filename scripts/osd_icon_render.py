#!/usr/bin/env python3
"""Render a 6x4-tile 1-bit main-menu icon (tFONT1_ICON_<NAME>) from the ported SDK source to a PNG (#46).

usage: osd_icon_render.py NAME [NAME...]   -> tmp/logs/osd_icon_<NAME>.png (black = foreground)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from glyph_decode import decode_blob, tile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tmp/sdcc-port/src/User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_1.c"


def render(name):
    m = re.search(r"tFONT1_ICON_%s\[\]=\s*\{(.*?)\n\};" % name, SRC.read_text(), re.S)
    blob = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))
    _, _, by = decode_blob(blob, 0)
    n = len(by) // 27
    g = np.zeros((4 * 18, 6 * 12), np.uint8)
    for t in range(min(n, 24)):
        r, c = divmod(t, 6)
        g[r * 18:(r + 1) * 18, c * 12:(c + 1) * 12] = tile(by, t)
    out = ROOT / f"tmp/logs/osd_icon_{name}.png"
    Image.fromarray(255 - g * 255).resize((g.shape[1] * 4, g.shape[0] * 4), Image.NEAREST).save(out)
    print(f"{name}: {n} tiles -> {out}")


for a in sys.argv[1:]:
    render(a)
