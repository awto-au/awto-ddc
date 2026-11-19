"""#pragma place: asm normalising, ;@place markers, group placement (#149). Run: python3 -m pytest tests/test_place_rules.py"""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import place_rules as PR
import sdcc_bank as SB
import sdcc_layout as L

SB.LOG = io.StringIO()

# compiler output of `#pragma place group(font)` on a function, a table, and `bank(5)` on a table (awto-sdcc#141)
ASM = """\
\t.area CSEG    (CODE)
\t.area PLACE_font(CODE)
;\t -----------------------------------------
;\t function font_blob
;\t -----------------------------------------
_font_blob:
\tret
\t.area CSEG    (CODE)
_other:
\tret
\t.area CSEG    (CODE)
\t.area CONST   (CODE)
\t.area PLACE_font(CODE)
_blob:
\t.db #0x01\t; 1
\t.area CSEG    (CODE)
\t.area CONST   (CODE)
\t.area BANK5(CODE)
_pinned:
\t.db #0x02\t; 2
\t.area CSEG    (CODE)
"""


def test_normalise_rewrites_sections():
    out, n = PR.normalise_text(ASM)
    assert n == 3
    assert "PLACE_" not in out and "BANK5" not in out
    assert out.count(";@place group=font") == 2 and out.count(";@place bank=5") == 1
    lines = out.split("\n")
    i = lines.index(";@place group=font")                      # function section: CSEG, marker, then its body
    assert lines[i - 1].split()[:2] == [".area", "CSEG"] and "_font_blob:" in lines[i:i + 6]
    k = [x for x, l in enumerate(lines) if l == ";@place group=font"][1]   # table: CONST, marker, label
    assert lines[k - 1].split()[:2] == [".area", "CONST"] and lines[k + 1] == "_blob:"


def test_normalise_leaves_plain_asm(tmp_path):
    f = tmp_path / "a.asm"
    f.write_text("\t.area CSEG    (CODE)\n_x:\n\tret\n")
    assert PR.normalise(f) == 0 and f.read_text() == "\t.area CSEG    (CODE)\n_x:\n\tret\n"


def test_banker_reads_markers(tmp_path):
    f = tmp_path / "m.asm"
    f.write_text(PR.normalise_text(ASM)[0])
    m = SB.Module(f)
    tag = {c.name: (c.group, c.pin, c.area) for c in m.chunks}
    assert tag["_font_blob"] == ("font", None, "CSEG")
    assert tag["_blob"] == ("font", None, "CONST")
    assert tag["_pinned"] == (None, 5, "CONST")
    assert tag["_other"] == (None, None, "CSEG")
    funcs = {c.name: c for c in m.chunks if c.area == "CSEG"}
    consts = {c.name: c for c in m.chunks if c.area == "CONST"}
    pl = SB.load_place(funcs, consts)
    assert sorted(c.name for c in pl["groups"]["font"]) == ["_blob", "_font_blob"]
    assert [(c.name, b) for c, b in pl["pins"]] == [("_pinned", 5)]


def test_pin_to_a_data_bank_refused(tmp_path):
    f = tmp_path / "m.asm"
    f.write_text(PR.normalise_text(ASM.replace("BANK5", "BANK15"))[0])
    m = SB.Module(f)
    with pytest.raises(SystemExit, match="not a code bank"):
        SB.load_place({c.name: c for c in m.chunks if c.area == "CSEG"}, {c.name: c for c in m.chunks if c.area == "CONST"})


def ch(name, bank, size=100, area="CSEG"):
    return SimpleNamespace(name=name, area=area, size=size, bank=bank, common=False)


def place(groups, pins=()):
    labels = {("fn" if c.area == "CSEG" else "const", c.name): "#pragma place test" for g in groups.values() for c in g}
    labels.update({("fn" if c.area == "CSEG" else "const", c.name): "#pragma place test" for c, _ in pins})
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
    with pytest.raises(SystemExit, match=r"#pragma place group\(font\).*no room for _big .*bank 0: 4096 B free"):
        L.assign([it], L.Layout(), 0, 0x100, 2, 4096, log=lambda *_: None,
                 labels={it.key: "#pragma place group(font) (x.c:1) [group 5000 B -> bank 0]"})
