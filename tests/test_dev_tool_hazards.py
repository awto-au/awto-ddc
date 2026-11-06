"""Tool-hazard fixes from reviews #52 / #50 (dev.py level). No hardware."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def dev(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("dev_under_test", REPO / "dev.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["dev_under_test"] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "TMP", tmp_path / "tmp")
    monkeypatch.setattr(m, "FW", tmp_path / "tmp" / "fw")
    monkeypatch.setattr(m, "LOGS", tmp_path / "tmp" / "logs")
    monkeypatch.setattr(m, "LOG", tmp_path / "tmp" / "logs" / "dev.log")
    import json
    real = json.loads((REPO / "scripts/devices.json").read_text())["units"]
    monkeypatch.setattr(m, "_units", lambda: real)
    yield m
    sys.modules.pop("dev_under_test", None)


def test_clean_keeps_images_state_regs_logs(dev, tmp_path):
    t = tmp_path / "tmp"
    keep = ["fw/AWT1-abc-be.bin", "fw/AWT1-abc-be.map", "fw/AWT1-abc-be.ids.tsv", "fw/AWT1-flashed.json",
            "fw/AWT1-flash-state.json", "regs/dump.txt", "logs/x.log", "notes.md"]
    gone = ["sdcc-port/asm/a.asm", "fw/AWT1/fw.bin", "fw/AWT1/fw.map"]
    for f in keep + gone:
        (t / f).parent.mkdir(parents=True, exist_ok=True)
        (t / f).write_text("x")
    assert dev.cmd_clean([]) == 0
    for f in keep:
        assert (t / f).exists(), f
    for f in gone:
        assert not (t / f).exists(), f


# --- #52.9 power_cycle honours the relay name --------------------------------

def _run_power_cycle(monkeypatch, tmp_path, argv):
    spec = importlib.util.spec_from_file_location("pc_under_test", REPO / "scripts" / "power_cycle.py")
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    calls = []
    monkeypatch.setitem(pc.OUTLETS, "so-th-1", lambda state, log=print: calls.append(state))
    monkeypatch.setattr(pc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(pc.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["power_cycle.py", *argv])
    return pc.main(), calls


def test_power_cycle_requires_relay(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_power_cycle(monkeypatch, tmp_path, ["--off"])


def test_power_cycle_refuses_unknown_relay(monkeypatch, tmp_path):
    rc, calls = _run_power_cycle(monkeypatch, tmp_path, ["--relay", "so-th-9", "--off"])
    assert rc == 2 and calls == []


def test_power_cycle_known_relay_cycles(monkeypatch, tmp_path):
    rc, calls = _run_power_cycle(monkeypatch, tmp_path, ["--relay", "so-th-1"])
    assert rc == 0 and calls == [False, True]


def test_dev_passes_unit_relay(dev, monkeypatch):
    seen = []
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None: seen.append((script, a)) or 0)
    assert dev.cmd_power_cycle(["--unit", "3", "--off"]) == 0
    assert seen == [("power_cycle.py", ("--relay", "so-th-1", "--off"))]
