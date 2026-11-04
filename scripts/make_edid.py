#!/usr/bin/env python3
"""Build the awto-identity EDIDs (256 B = base + CTA-861 ext) for the JXC 28in 4K panel.

usage: make_edid.py [--out DIR] [--no-decode]
  writes DIR/awto-dp.bin and DIR/awto-hdmi.bin (default DIR: $VENDORS/realtek/analysis/edid)
  then runs `edid-decode -c` on each if installed and prints the result.
Design + per-port rationale: docs/edid-fix.md.  Log: ./tmp/logs/make_edid.log
"""
import shutil, subprocess, sys
from pathlib import Path

OUT_DEFAULT = Path("/mnt/2tb/vendors/realtek/analysis/edid")
MFR, PRODUCT, SERIAL32 = "AWT", 0x0001, 0   # serial text lives in the 0xFF descriptor
SERIAL_TXT, MODEL_TXT = "AWT26110001", "awto-mon"
WEEK, YEAR = 44, 2026
W_MM, H_MM = 597, 336   # measured active area (Dan 2026-11-04): 336 mm high -> 27.0" 16:9, square pixels


def pnp(s):
    a, b, c = (ord(x) - 64 for x in s)
    return ((a << 10) | (b << 5) | c).to_bytes(2, "big")


def cksum(b):
    return (-sum(b)) & 0xFF


def text_desc(tag, s):
    assert len(s) <= 13
    return bytes([0, 0, 0, tag, 0]) + (s + "\n").ljust(13).encode("ascii")


def dtd(clk10k, ha, hb, hfp, hsw, va, vb, vfp, vsw, hpol, vpol):
    """Detailed timing descriptor; hb/vb = blanking totals; image size = panel size."""
    f = 0x18 | (vpol << 2) | (hpol << 1)          # digital separate sync
    return bytes([
        clk10k & 0xFF, clk10k >> 8,
        ha & 0xFF, hb & 0xFF, ((ha >> 8) << 4) | (hb >> 8),
        va & 0xFF, vb & 0xFF, ((va >> 8) << 4) | (vb >> 8),
        hfp & 0xFF, hsw & 0xFF, ((vfp & 0xF) << 4) | (vsw & 0xF),
        ((hfp >> 8) << 6) | ((hsw >> 8) << 4) | ((vfp >> 4) << 2) | (vsw >> 4),
        W_MM & 0xFF, H_MM & 0xFF, ((W_MM >> 8) << 4) | (H_MM >> 8),
        0, 0, f])


# 3840x2160 533.12 MHz: htotal 4000 (fp48 sw32 bp80), vtotal 2222 (fp3 sw5 bp54), +H -V
DTD_4K = dtd(53312, 3840, 160, 48, 32, 2160, 62, 3, 5, 1, 0)
# VIC 16 exact: 148.5 MHz, htotal 2200 (88/44/148), vtotal 1125 (4/5/36), +H +V
DTD_1080 = dtd(14850, 1920, 280, 88, 44, 1080, 45, 4, 5, 1, 1)
# CVT-RB 2560x1440: 241.7 MHz, htotal 2720 (48/32/80), vtotal 1481 (3/5/33), +H -V... as in original (+/+)
DTD_1440 = dtd(24170, 2560, 160, 48, 32, 1440, 41, 3, 5, 1, 1)

def std_timing(x, ratio, hz):
    return bytes([(x // 8) - 31, (ratio << 6) | (hz - 60)])


def base_block(port):
    b = bytearray(128)
    b[0:8] = bytes.fromhex("00ffffffffffff00")
    b[8:10] = pnp(MFR)
    b[10:12] = PRODUCT.to_bytes(2, "little")
    b[12:16] = SERIAL32.to_bytes(4, "little")
    b[16], b[17] = WEEK, YEAR - 1990
    b[18], b[19] = 1, (4 if port == "dp" else 3)   # HDMI VSDB requires EDID 1.3; DP requires 1.4
    # 10 bpc; interface: 5 = DisplayPort, 2 = HDMI-a
    b[20] = (0x80 | (3 << 4) | 5) if port == "dp" else 0x81   # 1.4 DP: 10 bpc + DP; 1.3: digital, DFP 1.x
    b[21], b[22] = W_MM // 10, H_MM // 10
    b[23] = 0x78                                   # gamma 2.20
    # 1.4: sRGB, preferred=DTD1, continuous freq, RGB+YCbCr444/422; 1.3: RGB, sRGB, preferred, GTF
    b[24] = 0x3F if port == "dp" else 0x27
    b[25:35] = bytes.fromhex("ee91a3544c99260f5054")  # chromaticity (unchanged)
    b[35:38] = bytes.fromhex("210800")             # est. timings 640x480, 800x600, 1024x768
    # ratio codes: 0=16:10 1=4:3 2=5:4 3=16:9; unused slots = 0x0101
    std = [(1920, 3), (1440, 0), (1400, 1), (1280, 2), (1280, 1), (1280, 3)]
    sb = b"".join(std_timing(x, r, 60) for x, r in std)
    b[38:54] = sb.ljust(16, b"\x01")
    b[54:72] = DTD_4K
    b[72:90] = text_desc(0xFC, MODEL_TXT)
    b[90:108] = text_desc(0xFF, SERIAL_TXT)
    # range limits (type 0x01 = range limits only; GTF is deprecated in 1.4): 24-60 Hz V (24p modes), 15-135 kHz H, <=600 MHz pixel clock (byte = MHz/10)
    b[108:126] = bytes([0, 0, 0, 0xFD, 0, 24, 60, 15, 135, 60, 0x01 if port == "dp" else 0x00, 0x0A] + [0x20] * 6)
    b[126] = 1
    b[127] = cksum(b[:127])
    return bytes(b)


VICS = [97, 96, 95, 94, 93, 16, 31, 32, 33, 34, 4, 19, 60, 61, 62, 1, 2, 3]


def cta_block(port):
    d = bytearray()
    vdb = bytes(v for v in VICS)
    d += bytes([(2 << 5) | len(vdb)]) + vdb
    d += bytes([(1 << 5) | 3, 0x09, 0x7F, 0x07])           # LPCM 2ch, 32-192 kHz, 16/20/24 bit
    d += bytes([(4 << 5) | 3, 0x01, 0x00, 0x00])           # speakers FL/FR
    d += bytes([(7 << 5) | 2, 0x00, 0xCA])                 # VCDB: QY+QS (YCC/RGB quant selectable), IT/CE underscan
    if port == "hdmi":
        # HDMI 1.4 VSDB: PA 1.0.0.0, DC_30bit+DC_Y444, legacy max TMDS 340 MHz (0x44 x 5 MHz)
        d += bytes([(3 << 5) | 7, 0x03, 0x0C, 0x00, 0x10, 0x00, 0x18, 0x44])
        # HF-VSDB: v1, max TMDS char rate 600 MHz (0x78 x 5), SCDC present + LTE_340Mcsc scrambling
        d += bytes([(3 << 5) | 7, 0xD8, 0x5D, 0xC4, 0x01, 0x78, 0x88, 0x00])
        # AMD FreeSync VSDB (carried over): v1, caps 01, 48-60 Hz
        d += bytes([(3 << 5) | 8, 0x1A, 0x00, 0x00, 0x01, 0x01, 0x30, 0x3C, 0xE6])
    dtds = DTD_1080 + DTD_1440
    b = bytearray(128)
    b[0], b[1] = 0x02, 0x03
    b[2] = 4 + len(d)
    b[3] = 0x80 | 0x40 | 0x20 | 0x10 | 1                   # underscan, audio, YCbCr444/422, 1 native DTD (base DTD1)
    b[4:4 + len(d)] = d
    o = 4 + len(d)
    b[o:o + len(dtds)] = dtds
    b[127] = cksum(b[:127])
    return bytes(b)


def build(port):
    return base_block(port) + cta_block(port)


def main():
    out = OUT_DEFAULT
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for port in ("dp", "hdmi"):
        e = build(port)
        assert len(e) == 256 and sum(e[:128]) % 256 == 0 and sum(e[128:]) % 256 == 0
        p = out / f"awto-{port}.bin"
        p.write_bytes(e)
        print(f"== {p} ({len(e)} B)")
        if "--no-decode" not in sys.argv and shutil.which("edid-decode"):
            r = subprocess.run(["edid-decode", "-c", str(p)], capture_output=True, text=True)
            print(r.stdout, r.stderr)
            rc |= r.returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
