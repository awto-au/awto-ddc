"""fw_gates.py stall guard: kills real hangs, spares a CPU-starved gate, reruns a guard kill once (awto-dan#53)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fw_gates as G


def test_verdict_quiet_is_a_stall():
    assert G.guard_verdict(100, 0, last_out=30, last_cpu=30, limit=150)[0] == "stall"


def test_verdict_cpu_progress_spares_a_slow_gate():
    assert G.guard_verdict(100, 0, last_out=30, last_cpu=95, limit=150) is None


def test_verdict_limit_scales_with_load():
    assert G.guard_verdict(200, 0, 199, 199, limit=150, factor=1.0)[0] == "limit"
    assert G.guard_verdict(200, 0, 199, 199, limit=150, factor=2.0) is None


def _run(tmp_path, code, monkeypatch, stall=2):
    monkeypatch.setattr(G, "STALL_S", stall)
    monkeypatch.setattr(G, "ROOT", tmp_path)
    res, lines = {}, []
    G.run("t", [sys.executable, "-c", code], tmp_path / "t.log", res, lines.append)
    return res["t"], lines


def test_hang_without_load_is_killed_and_rerun_once(tmp_path, monkeypatch):
    (rc, dt, last), lines = _run(tmp_path, "import time; print('x', flush=True); time.sleep(60)", monkeypatch)
    assert rc != 0 and dt < 30
    kills = [l for l in lines if "KILL (stall)" in l]
    assert len(kills) == 2 and any("failing" in l for l in lines) and all("loadavg" in l for l in kills)


def test_own_failure_not_rerun(tmp_path, monkeypatch):
    (rc, dt, last), lines = _run(tmp_path, "import sys; sys.exit(3)", monkeypatch)
    assert rc == 3 and not lines


def test_pass_first_time(tmp_path, monkeypatch):
    (rc, dt, last), lines = _run(tmp_path, "print('ok')", monkeypatch)
    assert rc == 0 and last == "ok"
