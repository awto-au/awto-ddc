#!/usr/bin/env python3
"""Build a per-unit 4 KiB EDID sector (0x13000) from the IPS/sRGB template + a unique serial.

usage: build_edid_sector.py --serial AWT26110002 --out <path/to/sector.bin> [--template <ips_sector.bin>]
  Template = the verified IPS patched_sector_13000.bin (default $VENDORS/realtek/analysis/edid/...).
  Overlays 3 EDID slots with make_edid.py output for the given serial, keeping ALL other factory
  framing bytes byte-identical. Slots: DP @0x8d8, HDMI @0x9d8, HDMI @0xad8 (verified layout).
  Only the 0xFF serial descriptor + per-block checksum change vs the template.
Log: ./tmp/logs/build_edid_sector.log
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_edid import build  # noqa: E402

VENDORS = Path("/mnt/2tb/vendors/realtek/analysis/edid")
TEMPLATE_DEFAULT = VENDORS / "patched_sector_13000.bin"
SECTOR = 4096
# Verified slot layout in the factory 0x13000 sector (3 EDID headers found by scan):
#   0x8d8 = DP (EDID 1.4), 0x9d8 = HDMI (1.3), 0xad8 = HDMI (1.3). Each 256 B (base+CTA).
SLOTS = (("dp", 0x8d8), ("hdmi", 0x9d8), ("hdmi", 0xad8))


def build_sector(serial, template):
    sec = bytearray(Path(template).read_bytes())
    assert len(sec) == SECTOR, f"template must be {SECTOR} B (is {len(sec)})"
    for port, off in SLOTS:
        e = build(port, serial)
        assert len(e) == 256 and sum(e[:128]) % 256 == 0 and sum(e[128:]) % 256 == 0
        sec[off:off + 256] = e
    return bytes(sec)


def main():
    a = sys.argv
    if "--serial" not in a or "--out" not in a:
        print(__doc__); return 2
    serial = a[a.index("--serial") + 1]
    out = Path(a[a.index("--out") + 1])
    template = Path(a[a.index("--template") + 1]) if "--template" in a else TEMPLATE_DEFAULT
    sec = build_sector(serial, template)
    out.write_bytes(sec)
    # Report what changed vs template.
    tpl = Path(template).read_bytes()
    diff = [i for i in range(SECTOR) if sec[i] != tpl[i]]
    print(f"wrote {out} ({len(sec)} B); serial={serial!r}; {len(diff)} bytes differ from template")
    for port, off in SLOTS:
        d = [hex(i) for i in diff if off <= i < off + 256]
        print(f"  slot {port}@{hex(off)}: {len(d)} changed bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
