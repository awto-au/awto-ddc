#!/usr/bin/env python3
"""OSD font trade-off: smoothness (1/2/4 bpp) vs SRAM/flash for the RL6449 OSD (#87, #89). Host-only.

Variants = bpp {1,2,4} x geometry {a: 12x18 cell drawn at the OSD 2x scale, b: 24x36 glyph at 1x}
x pitch {fixed (1 unit per char, DejaVu Sans Mono), proportional (string packed into consecutive units,
DejaVu Sans)}. Text = docs/settings.md labels + default values (14 pages) + status strip + key legend.
Fonts: DejaVu Sans / Sans Mono (Bitstream Vera licence + public-domain additions; free to embed).
Outputs: tmp/fontcmp/{table.tsv,sheet.png,var_*.png,zoom_*.png}; log tmp/logs/font_compare.log.
Tags in table notes: [measured] computed here from rendered glyphs; [derived] from docs (not measured on HW).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRAM_WORDS = 12288                      # [sdk] osd-limits.md; HW read-back not yet done
TILE_W, TILE_H = 12, 18                 # [spec/oss] 1-bpp cell
FONTS = {
    "fixed": "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
    "prop": "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
}
ICON_TILES = 64                         # headroom to quote: 1-bpp icon tiles (existing set = 53 glyphs)


def repo():
    e = os.environ.get("AWTO_DDC_REPO")
    if e:
        return Path(e)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True,
                                            cwd=Path(__file__).parent).strip())
    except Exception:
        return Path(__file__).resolve().parent.parent


ROOT = repo()
OUT = ROOT / "tmp" / "fontcmp"
LOG = ROOT / "tmp" / "logs" / "font_compare.log"


def log(msg):
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


# ---------------- text ----------------
def settings_pages():
    pages, cur = {}, None
    for ln in (ROOT / "docs/settings.md").read_text().splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip()
            pages[cur] = []
        elif cur and ln.startswith("| ") and re.match(r"\| \d+ \|", ln):
            c = [x.strip() for x in ln.strip("|").split("|")]
            label, default = c[2], c[4]
            pages[cur].append(f"{label}  {default}")
    return pages


STATUS = ["Input HDMI-2   3840x2160 59.94 Hz", "Backlight 44 %   DDC/CI on"]
LEGEND = ["Menu: enter   Right/Left: change", "Exit: back   Hold Menu+Left 1 s: defaults"]


def screen_lines(page, rows):
    return [page] + rows + [""] + STATUS + [""] + LEGEND


# ---------------- glyph raster ----------------
class Variant:
    def __init__(self, bpp, geom, pitch):
        self.bpp, self.geom, self.pitch = bpp, geom, pitch
        self.uw, self.uh = (12, 18) if geom == "a" else (24, 36)          # unit = one char-map entry
        self.size = 15 if geom == "a" else 30
        self.scale = 2 if geom == "a" else 1                              # on-screen px per OSD px
        self.font = ImageFont.truetype(FONTS[pitch], self.size, layout_engine=ImageFont.Layout.BASIC)
        asc, desc = self.font.getmetrics()
        self.top = max(0, (self.uh - (asc + desc)) // 2)
        self.name = f"{pitch}-{geom}-{bpp}bpp"
        self.words_per_unit = (self.uw * self.uh * bpp) // 24

    def quant(self, im):
        a = np.asarray(im, dtype=np.float32)
        if self.bpp == 1:
            return (a >= 128).astype(np.uint8)
        n = (1 << self.bpp) - 1
        return np.rint(a * n / 255).astype(np.uint8)

    def draw(self, text, width_px):
        im = Image.new("L", (width_px, self.uh), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = "1" if self.bpp == 1 else "L"       # 1 bpp: hinted bitmap; 2/4 bpp: AA then quantise
        if self.pitch == "fixed":
            for i, ch in enumerate(text):
                x = i * self.uw + int((self.uw - self.font.getlength(ch)) // 2)
                d.text((x, self.top), ch, 255, font=self.font)
        else:
            d.text((0, self.top), text, 255, font=self.font)
        return self.quant(im)

    def line_units(self, text):
        """Return (levels array uh x ncols*uw, ncols)."""
        if self.pitch == "fixed":
            n = len(text)
        else:
            n = -(-int(np.ceil(self.font.getlength(text))) // self.uw) if text else 0
        n = max(n, 1)
        return self.draw(text, n * self.uw), n

    def units(self, arr, n):
        return [arr[:, i * self.uw:(i + 1) * self.uw] for i in range(n)]

    def pack(self, unit):
        """Row-major pixels, MSB-first bpp bits, 24-bit words, stored byte order B0,B1,B2 [derived for
        2/4 bpp and for 24x36; 1-bpp 12x18 matches osd-font-download.md section 5]."""
        bits = "".join(format(int(v), f"0{self.bpp}b") for v in unit.flatten())
        out = bytearray()
        for i in range(0, len(bits), 24):
            w = int(bits[i:i + 24], 2)
            out += bytes([w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF])
        return bytes(out)


# ---------------- VLC (osd-font-download.md section 2-3) ----------------
CODES = ["0", "100", "1010", "1011", "1100", "11010", "11011", "11100", "111010", "111011", "111100",
         "111101", "1111100", "1111101", "1111110", "11111110"]
END = "11111111"


def vlc_encode(data):
    """Return blob bytes: 8-byte map + 2-byte BE length + stream (LSB-first bits, END, zero pad)."""
    nib = []
    for b in data:
        nib += [b >> 4, b & 15]
    freq = {v: 0 for v in range(16)}
    for v in nib:
        freq[v] += 1
    order = sorted(range(16), key=lambda v: (-freq[v], v))           # most frequent -> shortest code
    code_of = {v: CODES[i] for i, v in enumerate(order)}
    bits = "".join(code_of[v] for v in nib) + END
    bits += "0" * (-len(bits) % 8)
    stream = bytearray()
    for i in range(0, len(bits), 8):
        stream.append(int(bits[i:i + 8][::-1], 2))
    mp = bytes((order[2 * i] << 4) | order[2 * i + 1] for i in range(8))
    return mp + len(stream).to_bytes(2, "big") + bytes(stream)


def vlc_decode(blob):
    order = []
    for b in blob[:8]:
        order += [b >> 4, b & 15]
    n = int.from_bytes(blob[8:10], "big")
    bits = "".join(format(b, "08b")[::-1] for b in blob[10:10 + n])
    table = {c: order[i] for i, c in enumerate(CODES)}
    nib, cur = [], ""
    for ch in bits:
        cur += ch
        if cur == END:
            break
        if cur in table:
            nib.append(table[cur])
            cur = ""
    return bytes((nib[i] << 4) | nib[i + 1] for i in range(0, len(nib) - 1, 2))


def selftest():
    rng = np.random.default_rng(1)
    d = bytes(int(x) for x in rng.integers(0, 256, 270)) + bytes(27 * 5)
    assert vlc_decode(vlc_encode(d)) == d
    log("selftest OK: VLC encode/decode round-trip")


# ---------------- measurement ----------------
def measure(v, lines_by_page, extra_strings=None):
    """Unique non-blank units over a set of lines; returns dict."""
    def collect(lines):
        uniq = {}
        for t in lines:
            if not t:
                continue
            arr, n = v.line_units(t)
            for u in v.units(arr, n):
                if u.any():
                    uniq.setdefault(u.tobytes(), u)
        return uniq
    return collect


def blob_sizes(v, uniq):
    data = b"".join(v.pack(u) for u in uniq.values())
    raw = len(data)
    step = 24000                                   # blob length field is 16 bit: split, 10 B header each
    vlc = sum(len(vlc_encode(data[i:i + step])) for i in range(0, raw, step))
    return raw, vlc


def budget(v, screen, uniq_all):
    lines = [t for t in screen]
    H = len(lines)
    W = max(v.line_units(t)[1] if t else 0 for t in lines)
    map_words = H + 1 + W * H
    font_words = v.words_per_unit * len(uniq_all)
    return H, W, map_words, font_words


def render_screen(v, lines):
    wmax = max(v.line_units(t)[1] if t else 0 for t in lines) * v.uw
    canvas = np.zeros((len(lines) * v.uh, max(wmax, 1)), np.uint8)
    for i, t in enumerate(lines):
        if t:
            arr, n = v.line_units(t)
            canvas[i * v.uh:(i + 1) * v.uh, :arr.shape[1]] = arr
    lv = canvas.astype(np.float32) / ((1 << v.bpp) - 1)
    rgb = np.zeros(canvas.shape + (3,), np.uint8)
    rgb[..., 0] = np.rint(lv * 255)                       # red on black, linear palette ramp
    im = Image.fromarray(rgb, "RGB")
    return im.resize((im.width * v.scale, im.height * v.scale), Image.NEAREST)


def label_img(text, w, h=96, size=17):
    im = Image.new("RGB", (w, h), (24, 24, 24))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONTS["prop"], size)
    d.multiline_text((8, 6), text, (230, 230, 230), font=f, spacing=3)
    return im


def main():
    LOG.write_text("")
    selftest()
    OUT.mkdir(parents=True, exist_ok=True)
    pages = settings_pages()
    log(f"pages={len(pages)} rows={sum(len(r) for r in pages.values())}")
    biggest = max(pages, key=lambda p: len(pages[p]))
    screen = screen_lines(biggest, pages[biggest])
    all_lines = [p for p in pages] + [r for rows in pages.values() for r in rows] + STATUS + LEGEND
    ascii_chars = [chr(c) for c in range(32, 127)]
    ascii_str = "".join(ascii_chars)
    log(f"sample screen = page '{biggest}' ({len(pages[biggest])} rows) + status + legend; "
        f"union = all {len(pages)} pages + status + legend")

    rows, panels = [], {}
    for pitch in ("fixed", "prop"):
        for geom in ("a", "b"):
            for bpp in (1, 2, 4):
                v = Variant(bpp, geom, pitch)
                collect = measure(v, None)
                u_scr = collect(screen)
                u_all = collect(all_lines)
                if pitch == "fixed":
                    u_asc = collect(ascii_chars)
                    asc_note = "alphabet"
                else:
                    u_asc = collect([ascii_str])
                    asc_note = "one 95-char string"
                H, W, mapw, fw = budget(v, screen, u_all)
                total = mapw + fw
                free = SRAM_WORDS - total
                raw, vlc = blob_sizes(v, u_all)
                sraw, svlc = blob_sizes(v, u_scr)
                sfw = v.words_per_unit * len(u_scr)
                araw, avlc = blob_sizes(v, u_asc)
                rows.append(dict(
                    variant=v.name, font=Path(FONTS[pitch]).stem, bpp=bpp,
                    geometry="12x18 @2x" if geom == "a" else "24x36 @1x", pitch=pitch,
                    words_per_unit=v.words_per_unit,
                    ascii_units=len(u_asc), ascii_words=len(u_asc) * v.words_per_unit,
                    ascii_raw_B=araw, ascii_vlc_B=avlc, ascii_note=asc_note,
                    screen_units=len(u_scr), union_units=len(u_all),
                    font_words=fw, map_HxW=f"{H}x{W}", map_words=mapw, total_words=total,
                    sram_pct=round(100 * total / SRAM_WORDS, 1), free_words=free,
                    icons_1bpp_fit=free // 9,
                    raw_B=raw, vlc_B=vlc, vlc_ratio=round(vlc / raw, 2) if raw else 0,
                    scr_total_words=mapw + sfw, scr_sram_pct=round(100 * (mapw + sfw) / SRAM_WORDS, 1),
                    scr_raw_B=sraw, scr_vlc_B=svlc,
                    line_px=W * v.uw * v.scale,
                ))
                im = render_screen(v, screen)
                im.save(OUT / f"var_{v.name}.png")
                # 400% zoom of the first menu row, first 12 units wide; cropped at screen px
                y0 = v.uh * v.scale * 1
                zoom = im.crop((0, y0, min(im.width, 12 * 24), y0 + v.uh * v.scale))
                zoom = zoom.resize((zoom.width * 4, zoom.height * 4), Image.NEAREST)
                zoom.save(OUT / f"zoom_{v.name}.png")
                panels[v.name] = (im, zoom, rows[-1])
                log(f"{v.name}: units scr/all/ascii={len(u_scr)}/{len(u_all)}/{len(u_asc)} "
                    f"words={total} ({rows[-1]['sram_pct']}%) raw={raw} vlc={vlc}")

    # table.tsv
    cols = list(rows[0].keys()) + ["notes"]
    note = ("[measured] units, words, bytes, VLC (real encoder, round-trip tested); [derived] 2/4-bpp "
            "words per tile (18/36) and bit packing, 24x36-mode packing/36 words (osd-font-download.md "
            "sections 5, open item); SRAM size 12288 is the SDK constant, not read back")
    with (OUT / "table.tsv").open("w") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols[:-1]) + "\t" + note + "\n")

    # sheet: columns = pitch x geom, rows = bpp
    PW, CROP_H, ZH = 600, 300, 150
    combos = [(p, g) for p in ("fixed", "prop") for g in ("a", "b")]
    PH = 100 + CROP_H + ZH + 20
    sheet = Image.new("RGB", (PW * len(combos), PH * 3), (0, 0, 0))
    for ci, (p, g) in enumerate(combos):
        for ri, bpp in enumerate((1, 2, 4)):
            name = f"{p}-{g}-{bpp}bpp"
            im, zoom, r = panels[name]
            txt = (f"{name}  {r['geometry']}\n"
                   f"font {r['font_words']} w + map {r['map_words']} w = {r['total_words']} w = {r['sram_pct']} % "
                   f"of 12288 (1 screen: {r['scr_sram_pct']} %)\nflash {r['raw_B']} B raw / {r['vlc_B']} B VLC "
                   f"({r['vlc_ratio']})  units {r['union_units']} (screen {r['screen_units']})")
            x, y = ci * PW, ri * PH
            sheet.paste(label_img(txt, PW, 100, 15), (x, y))
            sheet.paste(im.crop((0, 0, PW, CROP_H)), (x, y + 100))
            sheet.paste(zoom.crop((0, 0, PW, ZH)), (x, y + 100 + CROP_H))
    sheet.save(OUT / "sheet.png")
    log(f"wrote {OUT/'sheet.png'} {sheet.size}, {OUT/'table.tsv'}")


if __name__ == "__main__":
    sys.exit(main())
