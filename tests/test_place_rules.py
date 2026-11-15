"""AWTO_PLACE source markers + group placement (#149). Run: python3 -m pytest tests/test_place_rules.py"""
import io, sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import place_rules as PR  # noqa: E402
import sdcc_bank as SB  # noqa: E402
import sdcc_layout as L  # noqa: E402

SB.LOG = io.StringIO()

SRC = """\
AWTO_PLACE(group=font)  /* reader */
static void font_blob(const uint8_t __code *b, uint16_t tile)
{
}
AWTO_PLACE(group=font)
static const uint8_t __code font_blob_spleen[4] = { 1, 2, 3, 4 };
AWTO_PLACE(bank=3) // pinned
BYTE __code tTab[] = { 0 };
AWTO_PLACE(common)
void IsrHelper(void);
"""


def test_scan_markers():
    r = PR.scan_text(SRC, "x.c")
    assert [(x["sym"], x.get("group"), x.get("bank"), x.get("common")) for x in r] == [
        ("_font_blob", "font", None, None), ("_font_blob_spleen", "font", None, None),
        ("_tTab", None, 3, None), ("_IsrHelper", None, None, True)]


@pytest.mark.parametrize("bad, msg", [
    ("AWTO_PLACE(group=a)\n\n\n\n\nint x;\n", "not followed by a definition"),
    ("AWTO_PLACE(colour=red)\nint x;\n", "use group="),
    ("AWTO_PLACE(bank=x)\nint x;\n", "not a bank number"),
    ("AWTO_PLACE(common, bank=2)\nint x;\n", "common together with bank"),
])
def test_bad_markers(bad, msg):
    with pytest.raises(PR.PlaceError, match=msg):
        PR.scan_text(bad, "x.c")


def test_duplicate_marker(tmp_path):
    f = tmp_path / "a.c"
    f.write_text("AWTO_PLACE(group=a)\nint x;\n")
    g = tmp_path / "b.c"
    g.write_text("AWTO_PLACE(bank=1)\nint x;\n")
    with pytest.raises(PR.PlaceError, match="already placed"):
        PR.scan([f, g])


def ch(name, bank, size=100, area="CSEG"):
    return SimpleNamespace(name=name, area=area, size=size, bank=bank, common=False)


def place(groups, pins=()):
    labels = {("fn" if c.area == "CSEG" else "const", c.name): "AWTO_PLACE test" for g in groups.values() for c in g}
    labels.update({("fn" if c.area == "CSEG" else "const", c.name): "AWTO_PLACE test" for c, _ in pins})
    return {"groups": groups, "pins": list(pins), "labels": labels}


def test_group_follows_most_bytes():
    rd, b1, b2 = ch("_rd", 3), ch("_b1", 10, 900, "CONST"), ch("_b2", 10, 900, "CONST")
    SB.apply_place(place({"font": [rd, b1, b2]}), "t")
    assert {c.bank for c in (rd, b1, b2)} == {10}


def test_group_follows_pin():
    rd, b1 = ch("_rd", 3), ch("_b1", 10, 900, "CONST")
    SB.apply_place(place({"g": [rd, b1]}, [(rd, 5)]), "t")
    assert (rd.bank, b1.bank) == (5, 5)


def test_group_conflicting_pins():
    a, b = ch("_a", 1), ch("_b", 2)
    with pytest.raises(SystemExit, match="pinned to different places"):
        SB.apply_place(place({"g": [a, b]}, [(a, 1), (b, 2)]), "t")


def test_split_group_fails():
    a, b = ch("_a", 1), ch("_b", 2)
    with pytest.raises(SystemExit, match="split across regions"):
        SB.check_place(place({"g": [a, b]}), lambda c: c.bank)


def test_fixed_group_member_no_room_names_rule():
    it = L.Item("const", "_big", 5000, 0, "m")
    it.fixed = True
    with pytest.raises(SystemExit, match=r"AWTO_PLACE group=font.*no room for _big .*bank 0: 4096 B free"):
        L.assign([it], L.Layout(), 0, 0x100, 2, 4096, log=lambda *_: None,
                 labels={it.key: "AWTO_PLACE group=font (x.c:1) [group 5000 B -> bank 0]"})
