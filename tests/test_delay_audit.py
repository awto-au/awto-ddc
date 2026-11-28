"""delay_audit.py: the typed inventory is complete in form, and the loop-count formula holds at every clock state (docs/delay-audit.md)."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import delay_audit as DA


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
    assert DA.counts(350791 // 4) == (36, 28)       # formula at 12 clk per count, 87.7 MHz
    assert DA.counts(350791 // 2) == (73, 57)       # 175.4 MHz
    assert DA.counts(350791) == (146, 116)          # 350.8 MHz (default)


def test_no_runtime_calibration_left():
    for f in (DA.ROOT / "fw/diag/delaycal.c", DA.ROOT / "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c"):
        assert not re.search(r"g_ucAwtoCal[5X]", f.read_text())


def test_tree_image_match_guard(tmp_path):
    # a listing tree whose bank layout differs from the image's frozen one is a stale / variant tmp/sdcc-port: --check must refuse
    # it (else a foreign build's static-fn sites misattribute to the preceding map symbol -> false sites / budget / masked hits; #365/#392).
    (tmp_path / "tmp/sdcc-port").mkdir(parents=True)
    (tmp_path / "tmp/fw").mkdir(parents=True)
    live = tmp_path / "tmp/sdcc-port/bank_layout.new.tsv"
    mapp = tmp_path / "tmp/fw/AWT-x-be.map"
    frozen = tmp_path / "tmp/fw/AWT-x-be.bank_layout.tsv"
    mapp.write_text("")
    live.write_text("fn\tbank\nAwtoFoo\t0\n")
    frozen.write_text("fn\tbank\nAwtoFoo\t0\n")
    assert DA.tree_matches_image(tmp_path, mapp) is True             # identical layout = same build
    frozen.write_text("fn\tbank\nAwtoFoo\t0\nAwtoClkMeasDelay\t3\n")  # image lacks a fn the tree has (or vice versa)
    assert DA.tree_matches_image(tmp_path, mapp) is False
    frozen.unlink()                                                  # no frozen layout next to the image: unchecked, do not block
    assert DA.tree_matches_image(tmp_path, mapp) is True
