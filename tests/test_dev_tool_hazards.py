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


# --- #52.7 mode: every logical monitor copied, only the target changed --------

SHOW = (REPO / "tests/data/gdctl_show.txt").read_text()


def _groups(args):
    out, cur = [], None
    for a in args:
        if a == "--logical-monitor":
            cur = []
            out.append(cur)
        else:
            cur.append(a)
    return out


def test_mode_copies_all_monitors_changes_target(dev):
    args = dev.gdctl_set_args(SHOW, "HDMI-2", dev.MODES["4k30"])
    g = _groups(args)
    assert len(g) == 4
    flat = [" ".join(x) for x in g]
    assert "--primary --monitor DP-4 --mode 3840x2160@60.000 --x 0 --y 0" in flat
    assert "--monitor DP-2 --mode 3840x2160@59.997 --x 3840 --y 0" in flat
    assert "--monitor HDMI-3 --mode 3840x2160@60.000 --x 7680 --y 0" in flat
    assert "--monitor HDMI-2 --mode 3840x2160@30.000 --x 11520 --y 0" in flat


def test_mode_dp_connector_not_in_layout_refused(dev):
    with pytest.raises(SystemExit):
        dev.gdctl_set_args(SHOW, "DP-1", dev.MODES["4k30"])


def test_mode_dp_flag_targets_dp_connector(dev, monkeypatch):
    shown = SHOW.replace("HDMI-2", "DP-1")
    calls = []

    def fake_run(cmd, **kw):
        assert kw.get("timeout")
        class R: returncode, stdout, stderr = 0, shown, ""
        return R()
    monkeypatch.setattr(dev.subprocess, "run", fake_run)
    monkeypatch.setattr(dev.subprocess, "call", lambda cmd, **kw: calls.append((cmd, kw)) or 0)
    assert dev.cmd_mode(["--unit", "3", "--dp", "4k30"]) == 0
    cmd, kw = calls[0]
    assert kw.get("timeout")
    assert cmd[cmd.index("DP-1") + 2] == "3840x2160@30.000"


def test_mode_gdctl_timeout_changes_nothing(dev, monkeypatch):
    def boom(cmd, **kw):
        raise dev.subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(dev.subprocess, "run", boom)
    monkeypatch.setattr(dev.subprocess, "call", lambda *a, **k: pytest.fail("gdctl set must not run"))
    assert dev.cmd_mode(["--unit", "3", "4k30"]) == 1


def test_mode_set_timeout_reported(dev, monkeypatch):
    class R: returncode, stdout, stderr = 0, SHOW, ""
    monkeypatch.setattr(dev.subprocess, "run", lambda *a, **k: R())

    def boom(cmd, **kw):
        raise dev.subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(dev.subprocess, "call", boom)
    assert dev.cmd_mode(["--unit", "3", "4k30"]) == 1


def test_mode_keeps_nondefault_scale_and_transform(dev):
    show = SHOW.replace("Scale: 1.0", "Scale: 2.0", 1).replace("Transform: normal", "Transform: 90", 1)
    g = " ".join(dev.gdctl_set_args(show, "HDMI-2", dev.MODES["4k30"]))
    assert "--x 0 --y 0 --scale 2.0 --transform 90" in g
