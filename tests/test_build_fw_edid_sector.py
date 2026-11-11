from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_fw_edid_sector import EDID_HEADER, build_sectors, edid_offsets  # noqa: E402
from make_edid import build  # noqa: E402


def image_with_tables(serial="AWT26110002"):
    image = bytearray(b"\xff" * 0x8000)
    offsets = (0x528c, 0x5398, 0x54a4)
    image[offsets[0]:offsets[0] + 256] = build("dp", serial)
    for off in offsets[1:]:
        image[off:off + 256] = build("hdmi", serial)
    return bytes(image), offsets


def test_build_changes_only_three_edid_tables():
    image, offsets = image_with_tables()
    addr, expected, patched = build_sectors(image, "AWT26110003")
    assert addr == 0x5000
    assert len(expected) == len(patched) == 4096
    changed = {i for i, (a, b) in enumerate(zip(expected, patched)) if a != b}
    allowed = set().union(*(range(off - addr, off - addr + 256) for off in offsets))
    assert changed and changed <= allowed
    assert patched[offsets[0] - addr:offsets[0] - addr + 256] == build("dp", "AWT26110003")


def test_refuses_missing_table_but_ignores_header_in_graphics():
    image, _ = image_with_tables()
    with pytest.raises(ValueError, match="exactly 3"):
        edid_offsets(image.replace(EDID_HEADER, b"\x00" * 8, 1))
    false_match = EDID_HEADER + b"\x04\x40" * 124
    assert len(false_match) == 256
    assert len(edid_offsets(image + false_match)) == 3


def test_refuses_four_checksum_valid_edid_tables():
    image, _ = image_with_tables()
    with pytest.raises(ValueError, match="exactly 3"):
        edid_offsets(image + build("hdmi", "AWT26110004"))
