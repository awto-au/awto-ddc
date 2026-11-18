"""delay_audit.py: the typed inventory is complete in form, and the loop-count formula holds at every clock state (docs/delay-audit.md)."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import delay_audit as DA  # noqa: E402


def test_tsv_typed_and_resolved():
    rows = list(csv.DictReader(DA.TSV.open(), delimiter="\t"))
    assert rows, "docs/delay-audit.tsv is empty: run scripts/delay_audit.py --write"
    assert list(rows[0].keys()) == DA.COLS
    assert len({r["key"] for r in rows}) == len(rows), "duplicate keys"
    assert {r["class"] for r in rows} <= set("ABCDE")
    assert not [r["key"] for r in rows if r["verdict"] in ("FIX", "UNKNOWN", "")], "unresolved rows"
    assert not [r["key"] for r in rows if r["verdict"] == "SCALES-BENIGN" and not r["note"]], "a benign scale needs its reason"


def test_counts_at_every_clock_state():
    per, o5, ox = DA.header_consts()
    for name, khz in DA.clock_states():
        c5, cx = DA.counts(khz)
        w5, wx = (per * c5 + o5) * 1000.0 / khz, (per * cx + ox) * 1000.0 / khz
        assert 5.0 <= w5 <= 5.0 + 2 * per * 1000.0 / khz, (name, c5, w5)      # a wait is a minimum: never below nominal, at most 2 counts over
        assert 4.0 <= wx <= 4.0 + 2 * per * 1000.0 / khz, (name, cx, wx)


def test_counts_are_what_the_sim_measured():
    assert DA.counts(350791 // 4) == (27, 21)       # docs/delay-audit.md, delay_sim.py at 87.7 MHz: hot 101 % / 104 %
    assert DA.counts(350791 // 2) == (54, 43)       # at 175.4 MHz: hot 100 % / 102 %
    assert DA.counts(350791) == (109, 87)           # at 350.8 MHz (default)


def test_no_runtime_calibration_left():
    for f in (DA.ROOT / "fw/diag/delaycal.c", DA.ROOT / "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c"):
        assert not re.search(r"g_ucAwtoCal[5X]", f.read_text())
