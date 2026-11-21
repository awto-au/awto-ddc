"""delay_audit blocking budget: a function over its cap fails unless docs/delay-budget.tsv raises it with a reason."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import delay_audit as DA


def _fake(total_us, ctx="main", fn="NewWaitFn"):
    return [{"function": fn, "context": ctx, "own_us": total_us, "extra_us": 0.0, "total_us": total_us, "rows": 1, "loop_rows": 0, "variable": 0}]


def test_new_long_wait_fails(monkeypatch):
    monkeypatch.setattr(DA, "blocking", lambda t, m: _fake(5000.0))
    monkeypatch.setattr(DA, "load_budget", dict)
    assert DA.check_budget(None, None) == 1


def test_isr_cap_is_100_us(monkeypatch):
    monkeypatch.setattr(DA, "load_budget", dict)
    monkeypatch.setattr(DA, "blocking", lambda t, m: _fake(150.0, "isr"))
    assert DA.check_budget(None, None) == 1
    monkeypatch.setattr(DA, "blocking", lambda t, m: _fake(90.0, "isr"))
    assert DA.check_budget(None, None) == 0


def test_allow_row_with_reason_passes_and_without_fails(monkeypatch):
    monkeypatch.setattr(DA, "blocking", lambda t, m: _fake(5000.0))
    row = {"function": "NewWaitFn", "context": "main", "budget_us": "5000", "extra_us": "", "reason": "why", "review": "ok"}
    monkeypatch.setattr(DA, "load_budget", lambda: {("NewWaitFn", "main"): row})
    assert DA.check_budget(None, None) == 0
    monkeypatch.setattr(DA, "load_budget", lambda: {("NewWaitFn", "main"): {**row, "reason": ""}})
    assert DA.check_budget(None, None) == 1
    monkeypatch.setattr(DA, "blocking", lambda t, m: _fake(5001.0))
    monkeypatch.setattr(DA, "load_budget", lambda: {("NewWaitFn", "main"): row})
    assert DA.check_budget(None, None) == 1


def test_budget_tsv_rows_have_reasons():
    rows = DA.load_budget()
    assert rows and all(r["reason"].strip() for r in rows.values())
