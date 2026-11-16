#!/usr/bin/env python3
"""BDF to the awto fixed-font hex subset: printable ASCII 0x20..0x7E, one byte per row (cell width <= 8).

usage: tools/bdf_to_hex.py IN.bdf OUT.hex "source url"
Line format: CODEPOINT(4 hex):ROWS(2 hex digits per cell row, MSB = leftmost pixel). Cell = FONTBOUNDINGBOX.
"""
import sys
from pathlib import Path


def main(src, dst, url):
    lines = Path(src).read_text().splitlines()
    fw = fh = fx = fy = 0
    glyphs, cur, bitmap = {}, None, None
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0] == "FONTBOUNDINGBOX":
            fw, fh, fx, fy = map(int, t[1:5])
        elif t[0] == "ENCODING":
            cur = {"cp": int(t[1])}
        elif t[0] == "BBX" and cur is not None:
            cur["bbx"] = tuple(map(int, t[1:5]))
        elif t[0] == "BITMAP":
            bitmap = []
        elif t[0] == "ENDCHAR":
            if cur is not None and bitmap is not None:
                cur["rows"] = bitmap
                glyphs[cur["cp"]] = cur
            cur, bitmap = None, None
        elif bitmap is not None:
            bitmap.append(int(t[0], 16) << (8 * (4 - len(t[0]) // 2 - 0)) if False else t[0])
    assert 0 < fw <= 8, f"cell width {fw} does not fit one byte per row"
    out = [f"# {Path(dst).stem} printable ASCII subset, codepoint:{fh} native bitmap rows (cell {fw}x{fh})",
           f"# Source: {url}", "# Licence: see third_party/ (BSD-2-Clause Spleen, MIT-style Tamzen)"]
    for cp in range(0x20, 0x7F):
        g = glyphs.get(cp)
        if g is None:
            continue
        gw, gh, gx, gy = g["bbx"]
        cell = [0] * fh
        top = (fy + fh) - (gy + gh)            # cell row of the glyph's top line
        for k, hexrow in enumerate(g["rows"][:gh]):
            nbits = len(hexrow) * 4
            v = int(hexrow, 16)
            row = 0
            for x in range(gw):
                if (v >> (nbits - 1 - x)) & 1:
                    px = gx - fx + x
                    if 0 <= px < fw:
                        row |= 1 << (7 - px)
            if 0 <= top + k < fh:
                cell[top + k] = row
        out.append(f"{cp:04X}:{bytes(cell).hex().upper()}")
    Path(dst).write_text("\n".join(out) + "\n")
    print(f"{dst}: {len(out) - 3} glyphs, cell {fw}x{fh}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
