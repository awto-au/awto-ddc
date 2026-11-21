"""irq_masks gate: a masked section missing from docs/irq-masks.tsv, or over its budget without a reasoned budget_us, fails."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import irq_masks as IM


def _row(key="a.c|F|EX0|clr|1", us="50.0"):
    return {"key": key, "function": "F", "bit": "EX0", "static_us": us}


def test_unlisted_site_fails():
    assert IM.judge([_row()], {})[0] == ["a.c|F|EX0|clr|1"]


def test_default_budget_100_us():
    old = {"a.c|F|EX0|clr|1": {"budget_us": "", "reason": ""}}
    assert IM.judge([_row(us="99.0")], old) == ([], [])
    assert IM.judge([_row(us="101.0")], old)[1]


def test_raised_budget_needs_reason_and_holds():
    key = "a.c|F|EX0|clr|1"
    ok = {key: {"budget_us": "9000", "reason": "PHY set-up"}}
    assert IM.judge([_row(us="8800.0")], ok) == ([], [])
    assert IM.judge([_row(us="9001.0")], ok)[1]
    assert IM.judge([_row(us="8800.0")], {key: {"budget_us": "9000", "reason": ""}})[1]


def test_tsv_rows_over_default_have_reasons():
    for r in IM.load().values():
        assert not r["budget_us"] or r["reason"].strip()
        assert r["action"].strip(), r["key"]
