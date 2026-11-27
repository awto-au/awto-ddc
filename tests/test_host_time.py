"""host_time.py unit selection and --wait retry, offline (no bus: `one` is replaced)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import host_time as HT


def _run(monkeypatch, argv, results):
    calls = []

    def fake_one(n, u, bus):
        calls.append(n)
        return results.pop(0) if results else True, None
    monkeypatch.setattr(HT, "one", fake_one)
    monkeypatch.setattr(HT.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sys, "argv", ["host_time.py", *argv])
    return HT.main(), calls


def test_units_test_sends_each_test_unit_once(monkeypatch):
    rc, calls = _run(monkeypatch, ["--units", "test", "--once"], [])
    assert rc == 0 and calls == sorted(set(calls), key=calls.index) and len(calls) >= 1


def test_unreachable_unit_skipped_no_retry(monkeypatch):
    rc, calls = _run(monkeypatch, ["--units", "test", "--once"], [False])
    assert rc == 1 and len(calls) == len(set(calls))


def test_wait_retries_until_sent(monkeypatch):
    rc, calls = _run(monkeypatch, ["--unit", "3", "--once", "--wait", "5"], [False, False, True])
    assert rc == 0 and calls == ["3", "3", "3"]


def test_refuses_unknown_unit(monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, ["--unit", "99", "--once"], [])


def test_unit_or_units_required(monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, ["--once"], [])
