#!/usr/bin/env python3
"""Boot-logo glyph/tile-map encoder for the RL6449 OSD (VLC-compressed 1-bit 12x18 tiles + char maps).

usage: osd_logo_encode.py selftest            decode the SDK Realtek logo consts, re-encode, require byte-identical
       osd_logo_encode.py preview [OUT.png]   render the SDK logo and the awto logo (no hardware)
       osd_logo_encode.py generate            write fw/sdcc/awto_logo_icons.inc + awto_logo_maps.inc (our consts)
Formats (awto-ddc#46, confirmed by selftest; decoder = glyph_decode.py):
- blob  = [8 B VLC value map][2 B BE N][N B stream, ends with END code 0xFF]; N = stream bytes incl. END
          (SDK VLC_TABLE_SIZE(x) = x[8]<<8 | x[9]); sizeof = 10 + N
- codes = 16 prefix codes + END, bits LSB-first; code i (CODES order) -> nibble = map[i]; nibbles pair high-first
- tile  = 1 bpp 12x18 = 27 B (9 words x 3 B, bytes stored B2,B1,B0, MSB = leftmost pixel); font address = tile index
- map   = rows of tile ids, _NEXT_ ends a row, _END_ ends the table (RTD2014OsdFontTable.c tiOSD_*)
- polarity: 1 = box fill (black), 0 = artwork (OsdEdit 'Inv'); the SDK logo is solid 1s with the letters cut out
- layout: LOGO0 = 80 tiles / 19x10 map at COL(0); LOGO1 = 71 tiles / 51x10 map at COL(19) (tile id = _Logo1_0xNN)
Source of the SDK arrays: tmp/sdcc-port/src (after msg_tokenise.py port). Log: tmp/logs/osd_logo_encode.log
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from glyph_decode import CODES, decode_blob, tile  # noqa: E402


def repo_root() -> Path:
    if os.environ.get("AWTO_DDC_REPO"):
        return Path(os.environ["AWTO_DDC_REPO"])
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parent)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


ROOT = repo_root()
OSD = ROOT / "tmp/sdcc-port/src/User/RTD Series/RTD2014Osd/Code"
LOG = ROOT / "tmp/logs/osd_logo_encode.log"
TW, TH, TB = 12, 18, 27
END_CODE = "11111111"
MAP_ROWS = 10
MARK_PNG = ROOT / "docs/logo/awto-monitor-mark.png"
# LOGO0 grid = cols 0-18, LOGO1 grid = cols 19-69 of one 70x10 tile grid (840x180 px)
COLS0, COLS1 = 19, 51
N0_MAX, N1_MAX = 80, 71            # font slots of the SDK logo (_Logo_0x00.. / _Logo1_0x00..): do not exceed


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(s + "\n")
    print(s)


# ---- SDK source parsing -------------------------------------------------------------------------
def sdk_blob(name):
    src = (OSD / "RTD2014OsdFontVLC.c").read_text()
    m = re.search(r"tICON_REALTEK_1BIT_%s\[\]=\s*\{(.*?)\n\};" % name, src, re.S)
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(1)))


def sdk_map(name):
    """tiOSD_REALTEK_1BIT_<name> -> list of rows of tile ids (suffix of _Logo[1]_0xNN)."""
    src = (OSD / "RTD2014OsdFontTable.c").read_text()
    m = re.search(r"tiOSD_REALTEK_1BIT_%s\[\]=\s*\{(.*?)\n\};" % name, src, re.S)
    rows, cur = [], []
    for t in re.findall(r"_Logo1?_0x[0-9a-f]{2}|_NEXT_|_END_", m.group(1)):
        if t == "_NEXT_":
            rows.append(cur); cur = []
        elif t == "_END_":
            rows.append(cur)
        else:
            cur.append(int(t[-2:], 16))
    return rows


# ---- codec --------------------------------------------------------------------------------------
def tiles_of(by):
    return [bytes(by[i * TB:(i + 1) * TB]) for i in range(len(by) // TB)]


def tile_bytes(g):
    """18x12 bit array -> 27 B (inverse of glyph_decode.tile)."""
    out = bytearray(TB)
    for w in range(9):
        line = [int(v) for v in list(g[2 * w]) + list(g[2 * w + 1])]
        for k, off in enumerate((2, 1, 0)):
            b = 0
            for bit in line[k * 8:k * 8 + 8]:
                b = (b << 1) | bit
            out[w * 3 + off] = b
    return bytes(out)


def freq_map(by):
    """Value map: nibble values ordered by descending frequency (ties: lower value first)."""
    cnt = [0] * 16
    for b in by:
        cnt[b >> 4] += 1
        cnt[b & 15] += 1
    return sorted(range(16), key=lambda v: (-cnt[v], v))


def encode_blob(by, vmap):
    """tile bytes + value map (16 nibble values in CODES order) -> blob bytes."""
    code_of = {v: CODES[i] for i, v in enumerate(vmap)}
    bits = "".join(code_of[n] for b in by for n in (b >> 4, b & 15))
    bits += "1" * (-len(bits) % 8) + END_CODE       # vendor: pad data with 1s to a byte boundary, then a 0xFF byte
    stream = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))      # LSB-first
    head = bytes((vmap[i] << 4) | vmap[i + 1] for i in range(0, 16, 2))
    return head + len(stream).to_bytes(2, "big") + stream


def decode_map_header(blob):
    v = []
    for b in blob[:8]:
        v += [b >> 4, b & 15]
    return v


def c_array(name, data, per=12, comment=None):
    lines = [f"    {','.join('0x%02x' % b for b in data[i:i + per])}," for i in range(0, len(data), per)]
    return (f"// {comment}\n" if comment else "") + f"BYTE __code {name}[] =\n{{\n" + "\n".join(lines) + "\n};\n"


# ---- selftest -----------------------------------------------------------------------------------
def selftest():
    ok = True
    for n in ("LOGO0", "LOGO1"):
        blob = sdk_blob(n)
        mh, N, by = decode_blob(blob, 0)
        vm = decode_map_header(blob)
        assert len(blob) == 10 + N, (n, len(blob), N)
        # tile bytes -> bit array -> bytes (tile codec)
        tl = tiles_of(by)
        rt = b"".join(tile_bytes(tile(by, i)) for i in range(len(tl)))
        enc = encode_blob(by, vm)
        fm = freq_map(by)
        ok_tile, ok_enc, ok_freq = rt == by, enc == blob, fm == vm
        log(f"selftest {n}: tiles={len(tl)} N={N} sizeof={len(blob)} tile-roundtrip={ok_tile} "
            f"vlc-encode(vendor map)==SDK={ok_enc} freq-derived-map==vendor-map={ok_freq}")
        ok &= ok_tile and ok_enc
        if not ok_enc:
            i = next((k for k in range(min(len(enc), len(blob))) if enc[k] != blob[k]), None)
            log(f"  first diff at byte {i}; len enc={len(enc)} sdk={len(blob)}")
        m = sdk_map(n)
        log(f"  map {n}: {len(m[0])} cols x {len(m)} rows, ids max 0x{max(max(r) for r in m):02x}")
    log("selftest " + ("PASS (byte-identical)" if ok else "FAIL"))
    return 0 if ok else 1


# ---- awto mark ----------------------------------------------------------------------------------
def render_mark(cols=15):
    """Mark line art -> 1-bit (rows*18 x cols*12), 1 = ink (white strokes of the mark), centred."""
    im = Image.open(MARK_PNG).convert("RGB")
    a = np.asarray(im).astype(int)
    white = (a.min(axis=2) > 160)                         # white strokes; red/ background -> 0
    ys, xs = np.where(white)
    crop = Image.fromarray((white[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype("uint8"))
    H, W = MAP_ROWS * TH, cols * TW
    s = min((H - 4) / crop.height, (W - 4) / crop.width)
    sz = (max(1, round(crop.width * s)), max(1, round(crop.height * s)))
    crop = crop.resize(sz, Image.LANCZOS)
    canvas = Image.new("L", (W, H), 0)
    canvas.paste(crop, ((W - sz[0]) // 2, (H - sz[1]) // 2))
    return (np.asarray(canvas) >= 128).astype(np.uint8)


def build_awto():
    """-> (tiles0 bytes, map0 rows, tiles1 bytes, map1 rows).
    LOGO0 = one solid tile / all-blank map; the mark sits centred on the 69-col grid, inside LOGO1's cols."""
    cols = 15
    bm = 1 - render_mark(cols)                             # SDK polarity: 1 = box (black), 0 = artwork (transparent -> window colour)
    start = (COLS0 + COLS1 - cols) // 2 - COLS0            # first mark col inside LOGO1
    blank = b"\xff" * TB                                # tile 0 = solid 1s, as in the SDK logo (its padding tile)
    uniq, ids = [blank], {blank: 0}
    rows1 = []
    for r in range(MAP_ROWS):
        row = [0] * COLS1
        for c in range(cols):
            g = bm[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW]
            tb = tile_bytes(g)
            if tb not in ids:
                ids[tb] = len(uniq); uniq.append(tb)
            row[start + c] = ids[tb]
        rows1.append(row)
    if len(uniq) > N1_MAX:
        sys.exit(f"awto mark needs {len(uniq)} unique tiles > {N1_MAX} font slots of LOGO1")
    rows0 = [[0] * COLS0 for _ in range(MAP_ROWS)]
    return blank, rows0, b"".join(uniq), rows1, bm, start


def map_c(name, rows, prefix):
    out = [f"BYTE __code {name}[]=", "{"]
    for i, row in enumerate(rows):
        out.append("    " + ",".join(f"_{prefix}_0x{v:02x}" for v in row) + (",_NEXT_," if i < len(rows) - 1 else ",_END_,"))
    out.append("};")
    return "\n".join(out) + "\n"


def generate():
    t0, m0, t1, m1, bm, start = build_awto()
    b0 = encode_blob(t0, freq_map(t0))
    b1 = encode_blob(t1, freq_map(t1))
    for n, b, mx in (("LOGO0", b0, 1258), ("LOGO1", b1, 1126)):
        log(f"awto {n}: blob {len(b)} B (SDK {mx} B) {'OK fits' if len(b) <= mx else 'TOO BIG'}")
        if len(b) > mx:
            sys.exit("blob larger than SDK slot")
    # round-trip our own output through the decoder
    for b, t in ((b0, t0), (b1, t1)):
        assert decode_blob(b, 0)[2] == t
    hdr = "// GENERATED by scripts/osd_logo_encode.py from docs/logo/awto-monitor-mark.png (awto-ddc#46). Do not edit.\n"
    icons = hdr + c_array("tICON_REALTEK_1BIT_LOGO0", b0, comment="awto boot logo, tiles for _REALTEK_1BIT_LOGO0 (solid)") + \
        c_array("tICON_REALTEK_1BIT_LOGO1", b1, comment=f"awto boot logo, {len(t1) // TB} tiles, mark at LOGO1 col {start}")
    maps = hdr + map_c("tiOSD_REALTEK_1BIT_LOGO0", m0, "Logo") + map_c("tiOSD_REALTEK_1BIT_LOGO1", m1, "Logo1")
    (ROOT / "fw/sdcc/awto_logo_icons.inc").write_text(icons)
    (ROOT / "fw/sdcc/awto_logo_maps.inc").write_text(maps)
    log(f"awto: {len(t1) // TB} unique tiles in LOGO1 (max {N1_MAX}); wrote fw/sdcc/awto_logo_icons.inc, awto_logo_maps.inc")
    png = ROOT / "tmp/logs/awto_logo_preview.png"
    Image.fromarray((255 - bm * 255).astype("uint8")).resize((bm.shape[1] * 3, bm.shape[0] * 3), Image.NEAREST).save(png)
    log(f"preview {png}")
    return 0


def sdk_grid(name0="LOGO0", name1="LOGO1"):
    g = np.zeros((MAP_ROWS * TH, (COLS0 + COLS1) * TW), dtype=np.uint8)
    for off, n in ((0, name0), (COLS0, name1)):
        _, _, by = decode_blob(sdk_blob(n), 0)
        for r, row in enumerate(sdk_map(n)):
            for c, t in enumerate(row):
                g[r * TH:(r + 1) * TH, (off + c) * TW:(off + c + 1) * TW] = tile(by, t)
    return g


def preview(out):
    g = sdk_grid()
    t0, m0, t1, m1, bm, start = build_awto()
    full = np.ones_like(g)
    x0 = (COLS0 + start) * TW
    full[:, x0:x0 + bm.shape[1]] = bm
    both = np.concatenate([g, np.zeros((6, g.shape[1]), np.uint8), full])
    Image.fromarray((255 - both * 255).astype("uint8")).save(out)
    log(f"preview {out} (top: SDK Realtek logo, bottom: awto; black = 1)")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "generate":
        sys.exit(generate())
    if cmd == "preview":
        sys.exit(preview(sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "tmp/logs/logo_preview.png")))
    print(__doc__)
    sys.exit(2)
