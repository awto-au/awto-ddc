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
