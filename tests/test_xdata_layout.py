"""Pinned XDATA layout (scripts/xdata_layout.py): growth re-homes only the grown module, shrink keeps slots, fit errors."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import xdata_layout as XL

HOLES = [(0x1000, 0x1100), (0x2000, 0x2200)]


def test_first_place_then_stable():
    rows, _ = XL.place({}, {"a": 100, "b": 50, "c": 30}, HOLES, [])
    again, info = XL.place(rows, {"a": 100, "b": 50, "c": 30}, HOLES, [])
    assert again == rows and info["moved"] == []


def test_growth_moves_only_that_module():
    sizes = {"a": 100, "b": 50, "c": 30}
    rows, _ = XL.place({}, sizes, HOLES, [])
    new, info = XL.place(rows, {**sizes, "b": 60}, HOLES, [])
    assert info["moved"] == ["b"] and not info["compacted"]
    assert {m: v for m, v in new.items() if m != "b"} == {m: v for m, v in rows.items() if m != "b"}


def test_shrink_and_removal_keep_other_slots():
    rows, _ = XL.place({}, {"a": 100, "b": 50}, HOLES, [])
    new, info = XL.place(rows, {"a": 90}, HOLES, [])
    assert new == {"a": rows["a"]} and info["moved"] == []


def test_new_module_takes_a_gap_and_nothing_else_moves():
    rows, _ = XL.place({}, {"a": 100}, HOLES, [])
    new, info = XL.place(rows, {"a": 100, "n": 40}, HOLES, [])
    assert info["moved"] == ["n"] and new["a"] == rows["a"]


def test_reserved_range_is_never_used():
    rows, _ = XL.place({}, {"a": 200}, HOLES, [(0x2000, 0x2040)])
    assert XL.addr(rows["a"]) >= 0x2040 or XL.addr(rows["a"]) + 200 <= 0x2000


def test_does_not_fit():
    with pytest.raises(SystemExit, match="does not fit"):
        XL.place({}, {"a": 600}, HOLES, [])


def test_fragmented_compacts():
    sizes = {"a": 100, "b": 100, "c": 56, "d": 200}
    rows, _ = XL.place({}, sizes, HOLES, [])
    grown = {**sizes, "d": 300}
    new, info = XL.place(rows, grown, HOLES, [])
    assert info["compacted"] or info["moved"]            # fits: either by eviction or by compaction
    assert sum(v[2] for v in new.values()) == sum(grown.values())


def test_check_matches_map(tmp_path):
    rows, _ = XL.place({}, {"a": 100}, HOLES, [])
    f = tmp_path / "l.tsv"
    f.write_text(XL.dump(rows))
    mp = f"XS_a                                 {XL.addr(rows['a']):08X}    00000064 =         100. bytes (REL,CON,XDATA)\n"
    assert XL.check(f, mp) == []
    assert XL.check(f, mp.replace("00000064", "00000065"))


def test_exact_fit_needs_best_fit():
    """Sizes 4+3+3 into holes 6+4: first-fit decreasing strands 1-2 B gaps, best-fit packs it (#268)."""
    rows, _ = XL.place({}, {"a": 4, "b": 3, "c": 3}, [(0x1000, 0x1006), (0x2000, 0x2004)], [])
    assert sum(v[2] for v in rows.values()) == 10
