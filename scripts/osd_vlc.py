#!/usr/bin/env python3
"""The one VLC codec for RTD OSD glyph data (RTD2795T): blob encode / decode, tile pack / unpack for 1 / 2 / 4 bpp.

usage: osd_vlc.py selftest [--sdk]      round-trips; --sdk also checks byte-identity against the SDK logo blobs
       (import it: encode / decode / freq_map / pack_unit / unpack_unit; font_compare, the logo generators, the font
        generator and tools/osd_editor all use this module, awto-ddc#87)
Format (docs/reversing/realtek-rtd/osd-font-download.md section 2-3; byte-identical to the SDK logo blobs, --sdk):
- blob = [8 B value map][2 B BE N][N B stream]; N counts the END byte; sizeof = 10 + N
- 16 prefix codes + END (11111111), bits LSB-first per byte; code i of CODES -> nibble map[i]; nibbles pair high-first
- encoder: value map = nibble values by descending frequency (ties: lower value first); data bits are padded with 1s to a
  byte boundary, then one END byte (the vendor stream layout)
- tile (unit) = w x h px at bpp bits, row-major, MSB-first, 24-bit words stored low byte first [1 bpp 12x18: osd-font-download.md
  section 5; 2 / 4 bpp: derived, not yet seen on hardware]
Log: tmp/logs/osd_vlc.log
"""
import os
import sys
from pathlib import Path

CODES = ["0", "100", "1010", "1011", "1100", "11010", "11011", "11100", "111010", "111011",
         "111100", "111101", "1111100", "1111101", "1111110", "11111110"]
END_CODE = "11111111"


def freq_map(data):
    """Value map: nibble values ordered by descending frequency (ties: lower value first)."""
    cnt = [0] * 16
    for b in data:
        cnt[b >> 4] += 1
        cnt[b & 15] += 1
    return sorted(range(16), key=lambda v: (-cnt[v], v))


def encode(data, vmap=None):
    """bytes (+ optional 16-entry value map in CODES order) -> blob bytes (the stream must fit the 16 bit length)."""
    blob = _encode(data, vmap)
    assert len(blob) - 10 < 65536, "stream too long for the 16-bit length: split with encode_chunks"
    return blob


def _encode(data, vmap=None):
    vmap = list(vmap) if vmap is not None else freq_map(data)
    assert sorted(vmap) == list(range(16)), "value map must be a permutation of 0..15"
    code_of = {v: CODES[i] for i, v in enumerate(vmap)}
    bits = "".join(code_of[n] for b in data for n in (b >> 4, b & 15))
    bits += "1" * (-len(bits) % 8) + END_CODE
    stream = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))
    head = bytes((vmap[i] << 4) | vmap[i + 1] for i in range(0, 16, 2))
    return head + (len(stream) & 0xFFFF).to_bytes(2, "big") + stream


def encode_chunks(data, unit_bytes, limit=60000):
    """Whole units as few blobs as possible: one blob unless its stream passes `limit` bytes (the length field is 16 bit), then halves:
    [(first_unit, n_units, blob)]."""
    out = []

    def rec(a, b):
        blob = _encode(data[a * unit_bytes:b * unit_bytes]) if b - a > 0 else b""
        if len(blob) - 10 <= limit or b - a == 1:
            out.append((a, b - a, blob))
        else:
            m = (a + b) // 2
            rec(a, m)
            rec(m, b)
    rec(0, len(data) // unit_bytes)
    return out


def vmap_of(blob):
    v = []
    for b in blob[:8]:
        v += [b >> 4, b & 15]
    return v


def decode(blob, off=0):
    """blob -> data bytes. Raises ValueError on a bad code, a missing END or a length mismatch."""
    vm = vmap_of(blob[off:off + 8])
    n = int.from_bytes(blob[off + 8:off + 10], "big")
    table = {c: vm[i] for i, c in enumerate(CODES)}
    nib, cur, end = [], "", False
    for b in blob[off + 10:off + 10 + n]:
        for k in range(8):
            cur += "1" if (b >> k) & 1 else "0"
            if cur in table:
                nib.append(table[cur])
                cur = ""
            elif cur == END_CODE:
                end = True
                break
            elif len(cur) > 8:
                raise ValueError("bad VLC code")
        if end:
            break
    if not end:
        raise ValueError("no END code within the stream length")
    if len(nib) % 2:
        raise ValueError("odd nibble count")
    return bytes((nib[i] << 4) | nib[i + 1] for i in range(0, len(nib), 2))


def decode_blob(d, off):
    """glyph_decode.decode_blob-compatible: (map hex, N, data)."""
    return d[off:off + 8].hex(), int.from_bytes(d[off + 8:off + 10], "big"), decode(d, off)


def size_of(data, vmap=None):
    return len(encode(data, vmap))


# ---- tile pack / unpack ---------------------------------------------------------------------
def pack_unit(levels, bpp):
    """levels: rows of ints 0..2^bpp-1 (h rows x w px) -> bytes; 24-bit words, low byte first. w*h*bpp must be a multiple of 24."""
    bits = "".join(format(int(v), f"0{bpp}b") for row in levels for v in row)
    assert len(bits) % 24 == 0, "unit is not a whole number of 24-bit words"
    out = bytearray()
    for i in range(0, len(bits), 24):
        w = int(bits[i:i + 24], 2)
        out += bytes([w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF])
    return bytes(out)


def unpack_unit(data, w, h, bpp):
    """inverse of pack_unit -> list of h rows of w levels."""
    bits = ""
    for i in range(0, len(data), 3):
        bits += format(data[i] | data[i + 1] << 8 | data[i + 2] << 16, "024b")
    v = [int(bits[i:i + bpp], 2) for i in range(0, w * h * bpp, bpp)]
    return [v[r * w:(r + 1) * w] for r in range(h)]


def log(s):
    root = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
    p = root / "tmp/logs/osd_vlc.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(s + "\n")
    print(s)


def selftest(sdk=False):
    import random
    rnd = random.Random(1)
    cases = [bytes(rnd.randrange(256) for _ in range(270)) + bytes(27 * 5), b"\x00" * 27, b"\xff" * 27,
             bytes(rnd.choice((0, 0, 0, 0x55, 0xAA, 0xFF)) for _ in range(432)), bytes(range(256)) * 4]
    for d in cases:
        b = encode(d)
        assert decode(b) == d and len(b) == 10 + int.from_bytes(b[8:10], "big")
    for bpp in (1, 2, 4):
        for w, h in ((12, 18), (24, 36)):
            if w * h * bpp % 24:
                continue
            lv = [[rnd.randrange(1 << bpp) for _ in range(w)] for _ in range(h)]
            assert unpack_unit(pack_unit(lv, bpp), w, h, bpp) == lv
    big = bytes(rnd.randrange(256) for _ in range(90000))
    ch = encode_chunks(big, 54)
    assert len(ch) > 1 and b"".join(decode(b) for _, _, b in ch) == big[:len(big) // 54 * 54]
    assert len(encode_chunks(big[:5400], 54)) == 1
    try:
        decode(encode(b"abc")[:-1])
        raise SystemExit("truncated blob decoded")
    except ValueError:
        pass
    log("osd_vlc selftest OK: encode/decode round-trip, pack/unpack 1/2/4 bpp, chunking, truncation")
    if sdk:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import osd_logo_encode as E
        for n in ("LOGO0", "LOGO1"):
            blob = E.sdk_blob(n)
            assert encode(decode(blob), vmap_of(blob)) == blob, n
            assert decode(blob) == E.decode_blob(blob, 0)[2]
        log("osd_vlc selftest OK: byte-identical to the SDK logo blobs (vendor map)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest("--sdk" in sys.argv))
    sys.exit(__doc__)
