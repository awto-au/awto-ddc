"""scripts/gen_scope2.py: the committed fw/test/scope2_data.inc is current and the dynamic tile budget fits the 256 glyph ids."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gen_scope2 as G


def test_committed_header_current():
    assert G.OUT.read_text() == G.emit(G.BASE_RASTER)


def test_slot_budget():
    geo = G.Geo(G.BASE_RASTER)
    ids, cell = G.tiles(geo)
    t, k, slots = G.model(geo, len(ids), cell)
    assert t + k <= slots
    assert len(cell) == geo.cols * geo.rows
