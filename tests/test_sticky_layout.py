"""Dev layout: chunks keep (region, offset, slot) while they fit their slot; release / compact packs back to back."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdcc_layout as L


def _lay(rows):
    lay = L.Layout()
    lay.rows = rows
    return lay


def _items(sizes):
    return [L.Item("fn", n, s, 0, "m") for n, s in sizes.items()]


def test_unchanged_chunks_keep_offsets_when_one_grows_within_its_slot():
    placed, _ = L.assign(_items({"a": 100, "b": 100}), _lay({}), 0, 0x100, 1, 4096, log=lambda s: None, sticky=True)
    a_off = placed[("fn", "b")][1]
    placed2, _ = L.assign(_items({"a": 110, "b": 100}), _lay(placed), 0, 0x100, 1, 4096, log=lambda s: None, sticky=True)
    assert placed2[("fn", "b")][1] == a_off and placed2[("fn", "a")][1] == placed[("fn", "a")][1]


def test_chunk_over_its_slot_moves_alone():
    placed, _ = L.assign(_items({"a": 100, "b": 100}), _lay({}), 0, 0x100, 1, 4096, log=lambda s: None, sticky=True)
    placed2, _ = L.assign(_items({"a": 400, "b": 100}), _lay(placed), 0, 0x100, 1, 4096, log=lambda s: None, sticky=True)
    assert placed2[("fn", "b")][1] == placed[("fn", "b")][1]
    assert placed2[("fn", "a")][1] != placed[("fn", "a")][1]


def test_compact_packs_back_to_back():
    placed, _ = L.assign(_items({"a": 100, "b": 50}), _lay({}), 0, 0x100, 1, 4096, log=lambda s: None)
    assert sorted(o for _, o, _ in placed.values()) == [0, 50] or sorted(o for _, o, _ in placed.values()) == [0, 100]
    assert sum(s for _, _, s in placed.values()) == 150


def test_map_text_sticky_has_offsets_and_stubs():
    lay = _lay({("fn", "a"): (0, 16, 120), ("stub", "0_a"): (1, 0, 8)})
    assert "fn\ta\t0\t0x0010\t120" in lay.map_text(sticky=True) and "stub\t0_a" in lay.map_text(sticky=True)
    assert "stub" not in lay.map_text()
