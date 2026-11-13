#!/usr/bin/env python3
"""Build the awto-identity EDIDs (256 B = base + CTA-861 ext) for the JXC 4K monitor (Innolux M280DCA-E3B 28" panel).

usage: make_edid.py [--out DIR] [--serial AWT26110001] [--no-decode]
  writes DIR/awto-dp.bin and DIR/awto-hdmi.bin (default DIR: $VENDORS/realtek/analysis/edid)
  then runs `edid-decode -c` on each if installed and prints the result.
  --serial sets the per-unit serial text in the 0xFF descriptor (default AWT26110001).
  Also writes DIR/awto-hdmi-d3.bin: = awto-hdmi.bin except the port tag (PORT_VSDB). Name + serial are the same on every
  port (the host keys monitor identity on them: mutter layout, dev.py serial guard); only the tag tells D1/D2/D3 apart.
Design + per-port rationale: docs/edid-fix.md.  Log: ./tmp/logs/make_edid.log
"""
import os, shutil, subprocess, sys
from pathlib import Path

OUT_DEFAULT = Path("/mnt/2tb/vendors/realtek/analysis/edid")
MFR, PRODUCT, SERIAL32 = "AWT", 0x0001, 0   # serial text lives in the 0xFF descriptor
SERIAL_TXT, MODEL_TXT = "AWT26110001", "awto-mon"
WEEK, YEAR = 44, 2026
W_MM, H_MM = 621, 341   # M280DCA-E3B active area 620.928 x 341.28 mm (datasheet; panel label, #3)


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


# 3840x2160 @60.000 Hz = CTA VIC 97 exactly: 594.00 MHz, htotal 4400 (fp176 sw88 bp296), vtotal 2250
# (fp8 sw10 bp72), +H +V. Works on our firmware since the ~bit fix (wb-vfreq, #26); PC use, no 59.94 broadcast rates.
DTD_4K = dtd(59400, 3840, 560, 176, 88, 2160, 90, 8, 10, 1, 1)
# VIC 16 exact: 148.5 MHz, htotal 2200 (88/44/148), vtotal 1125 (4/5/36), +H +V
DTD_1080 = dtd(14850, 1920, 280, 88, 44, 1080, 45, 4, 5, 1, 1)

# Chromaticity: M280DCA-E3B datasheet 5.2 typical (CIE 1931): R 0.678,0.312  G 0.267,0.617  B 0.146,0.061  W 0.313,0.329.
# Not sRGB (panel is DCI-P3 90%), so the sRGB-default feature bit (0x04) is clear. Encoding: x * 1024, 10 bit.
PRIMARIES = (0.678, 0.312, 0.267, 0.617, 0.146, 0.061, 0.313, 0.329)   # Rx Ry Gx Gy Bx By Wx Wy


def chroma(xy):
    q = [round(v * 1024) for v in xy]
    lo = [((q[i] & 3) << 2) | (q[i + 1] & 3) for i in range(0, 8, 2)]
    return bytes([(lo[0] << 4) | lo[1], (lo[2] << 4) | lo[3]] + [v >> 2 for v in q])


CHROMA = chroma(PRIMARIES)


def std_timing(x, ratio, hz):
    return bytes([(x // 8) - 31, (ratio << 6) | (hz - 60)])


def base_block(port, serial=SERIAL_TXT):
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
    # Feature byte, sRGB-default bit (0x04) clear: primaries are the panel's, not sRGB.
    # 1.4: preferred=DTD1, continuous freq, RGB+YCbCr444/422; 1.3: RGB, preferred, GTF.
    b[24] = 0x3B if port == "dp" else 0x2B
    b[25:35] = CHROMA                              # panel primaries (see PRIMARIES)
    b[35:38] = bytes.fromhex("210800")             # est. timings 640x480, 800x600, 1024x768
    # ratio codes: 0=16:10 1=4:3 2=5:4 3=16:9; unused slots = 0x0101
    std = [(1920, 3), (1440, 0), (1400, 1), (1280, 2), (1280, 1), (1280, 3)]
    sb = b"".join(std_timing(x, r, 60) for x, r in std)
    b[38:54] = sb.ljust(16, b"\x01")
    b[54:72] = DTD_4K
    b[72:90] = text_desc(0xFC, MODEL_TXT)
    b[90:108] = text_desc(0xFF, serial)
    # range limits (type 0x01 = range limits only; GTF is deprecated in 1.4): 48-60 Hz V, 15-135 kHz H, <=600 MHz pixel clock (byte = MHz/10)
    b[108:126] = bytes([0, 0, 0, 0xFD, 0, 48, 60, 15, 135, 60, 0x01 if port == "dp" else 0x00, 0x0A] + [0x20] * 6)
    b[126] = 1
    b[127] = cksum(b[:127])
    return bytes(b)


# Port tag (#28): CTA vendor-specific data block, OUI AWTO_OUI (unregistered, not used by any known vendor), payload
# "AWTO" + port number (1 = D1 DP, 2 = D2 HDMI, 3 = D3 HDMI). Read by dev.py port.
AWTO_OUI = 0xA770D0
PORT_TAG = {"dp": 1, "hdmi": 2, "hdmi-d3": 3}


def port_vsdb(port):
    pl = AWTO_OUI.to_bytes(3, "little") + b"AWTO" + bytes([PORT_TAG[port]])
    return bytes([(3 << 5) | len(pl)]) + pl


# Production (#26 sweep 2026-11-07, test EDID on HDMI + DP): every listed rate ACTIVE in line-buffer mode. Left out:
# 1080p24 / 23.976 (NOSIGNAL / SEARCH via FRC) and the vendor 533.12 MHz 4K DTD (i915 HDMI prunes it).
VICS = [97, 96, 95, 94, 93, 16, 31, 34, 33, 4, 19, 62, 61, 60, 1, 2, 3]
# TEST profile (EDID_PROFILE=test, sweep only, never a production unit): every mode removed on 2026-11-07, for the mode sweep
# (#26): 4K 60/50/30/25/24 (+ x1000/1001), 1080p 60/50/30/25/24, 720p 60/50/24/25/30, SD 640x480 / 480p; DTDs 4K 533.12 MHz
# (vendor 59.982), 2560x1600 and 1920x1200 CVT-RB, 2560x1440. Colorimetry + HDR blocks left out to make room for 4 DTDs.
TEST = os.environ.get("EDID_PROFILE") == "test"
VICS_TEST = [97, 96, 95, 94, 93, 16, 31, 34, 33, 32, 4, 19, 60, 61, 62, 1, 2, 3]
DTDS_RB = (dtd(26850, 2560, 160, 48, 32, 1600, 46, 3, 6, 1, 0)       # 2560x1600@60 CVT-RB
           + dtd(24150, 2560, 160, 48, 32, 1440, 41, 3, 5, 1, 0)     # 2560x1440@60 CVT-RB
           + dtd(15400, 1920, 160, 48, 32, 1200, 35, 3, 6, 1, 0))    # 1920x1200@60 CVT-RB
DTDS_TEST = dtd(53312, 3840, 160, 48, 32, 2160, 62, 3, 5, 1, 0) + DTDS_RB   # + vendor 4K 59.982 (htotal 4000, vtotal 2222)


def cta_block(port):
    d = bytearray()
    vdb = bytes(v for v in (VICS_TEST if TEST else VICS))
    d += bytes([(2 << 5) | len(vdb)]) + vdb
    # Audio (#93): Audio Data Block = one Short Audio Descriptor, Linear PCM 2 ch, 32/44.1/48 kHz, 16/20/24 bit;
    # Speaker Allocation Block = FL/FR. Header basic-audio bit set (b[3] below). The units' embedded DAC drives the audio pins.
    d += bytes([(1 << 5) | 3, (1 << 3) | (2 - 1), 0b00000111, 0b00000111])
    d += bytes([(4 << 5) | 3, 0x01, 0x00, 0x00])
    # Colorimetry Data Block (ext tag 0x05): byte1 0x06 = xvYCC709 + sYCC601 extended-gamut YCC;
    # byte2 0x20 = sRGB colorimetry (CTA-861-H) — the panel covers sRGB, and setting it is what
    # edid-decode recommends to avoid interop issues. BT.2020 is NOT advertised (panel: DCI-P3 90%, not BT.2020).
    if not TEST:
        d += bytes([(7 << 5) | 3, 0x05, 0x06, 0x20])
    # HDR Static Metadata Data Block (ext tag 0x06): EOTF = Traditional gamma SDR only (bit0); Static
    # Metadata Type 1 supported. NO PQ(SMPTE2084)/HLG — this is a 300 cd/m2 SDR panel, not HDR10.
    if not TEST:
        d += bytes([(7 << 5) | 3, 0x06, 0x01, 0x01])
    d += bytes([(7 << 5) | 2, 0x00, 0xCA])                 # VCDB: QY+QS (YCC/RGB quant selectable), IT/CE underscan
    if port.startswith("hdmi"):
        # HDMI 1.4 VSDB: PA 1.0.0.0, DC_30bit+DC_Y444, legacy max TMDS 340 MHz (0x44 x 5 MHz)
        d += bytes([(3 << 5) | 7, 0x03, 0x0C, 0x00, 0x10, 0x00, 0x18, 0x44])
        # HF-VSDB: v1, max TMDS char rate 600 MHz (0x78 x 5; i915 rejects the 533.12 MHz DTD as CLOCK_RANGE with 540), SCDC present + LTE_340Mcsc scrambling
        d += bytes([(3 << 5) | 7, 0xD8, 0x5D, 0xC4, 0x01, 0x78, 0x88, 0x00])
        # AMD FreeSync VSDB removed (business monitor, fixed 60 Hz; firmware FreeSync is off): re-add tracked in an issue
    d += port_vsdb(port)
    dtds = DTDS_TEST if TEST else DTDS_RB                  # 1080p60 = VIC 16
    b = bytearray(128)
    b[0], b[1] = 0x02, 0x03
    b[2] = 4 + len(d)
    b[3] = 0x80 | 0x40 | 0x20 | 0x10 | 1                   # underscan, basic audio, YCbCr444/422, 1 native DTD (base DTD1)
    b[4:4 + len(d)] = d
    o = 4 + len(d)
    b[o:o + len(dtds)] = dtds
    b[127] = cksum(b[:127])
    return bytes(b)


def build(port, serial=SERIAL_TXT):
    return base_block(port, serial) + cta_block(port)


def main():
    out = OUT_DEFAULT
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    serial = SERIAL_TXT
    if "--serial" in sys.argv:
        serial = sys.argv[sys.argv.index("--serial") + 1]
    assert len(serial) <= 13, "serial text must fit the 13-byte 0xFF descriptor"
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for port in ("dp", "hdmi", "hdmi-d3"):
        e = build(port, serial)
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
