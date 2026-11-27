"""dw8051 timing model vs DW8051 databook Table 2-4, all 256 opcodes (#362).

- tests/data/dw8051_table_2_4.tsv = Table 2-4 transcribed (scripts/dw8051_model.py --table).
- json model (what the sims load) and dw8051_model.py both diffed against it: cycles and bytes per opcode, MOVX base.
- Databook text present (~/vendors): the TSV is re-parsed from it and must match.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dw8051_model as D

MOVX = (0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3)


def table() -> dict[int, tuple[str, int, str]]:
    rows = {}
    for ln in D.TABLE.read_text().splitlines()[2:]:
        op, mn, b, c = ln.split("\t")
        rows[int(op, 16)] = (mn, int(b), c)
    return rows


def want_cycles(op, c):
    return int(c.split("-")[0]) if op in MOVX else int(c)


@pytest.mark.parametrize("src", ["json", "py"])
def test_model_matches_table_2_4(src):
    t = table()
    assert sorted(t) == list(range(256))
    m = json.loads(D.OUT.read_text()) if src == "json" else D.model()
    diffs = [f"{op:02X} {mn}: model {m['oplen'][op]} B / {m['cycles'][op]} cyc, databook {b} B / {c} cyc"
             for op, (mn, b, c) in t.items() if (m["oplen"][op], m["cycles"][op]) != (b, want_cycles(op, c))]
    assert not diffs, "\n".join(diffs)
    assert {t[op][2] for op in MOVX} == {"2-9"} and m["movx"]["base_cycles"] == 2


@pytest.mark.skipif(not D.DATABOOK.exists(), reason=f"databook text not here: {D.DATABOOK}")
def test_table_matches_databook_text():
    assert D.parse_table_2_4(D.DATABOOK.read_text()) == table()
