"""flash_job.load closes records with no live wrapper (rc 255); a zombie wrapper is not alive (awto-ddc#276 follow-up)"""
import importlib
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture()
def fj(tmp_path, monkeypatch):
    monkeypatch.setenv("AWTO_FLASH_JOBS_DIR", str(tmp_path))
    monkeypatch.setenv("AWTO_LOCK_DIR", str(tmp_path / "locks"))
    import flash_job
    return importlib.reload(flash_job)


def test_dead_pid_record_is_closed(fj):
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    fj.save({"id": "j1", "serial": "S1", "pid": p.pid, "started_mono_wall": 0})
    job = fj.load("S1")
    assert job["rc"] == 255 and "stale" in job["error"] and str(p.pid) in job["error"]
    assert fj.load("S1")["rc"] == 255 and not fj.running(job)


def test_foreign_pid_is_not_our_wrapper(fj):
    fj.save({"id": "j2", "serial": "S2", "pid": os.getpid(), "started_mono_wall": 0})     # alive, but not a flash_job.py process
    assert fj.load("S2")["rc"] == 255


def test_zombie_is_not_alive(fj):
    import unit_lock
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    while os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOWAIT) is None:
        pass                                                   # exited, not reaped: a zombie
    assert not unit_lock.alive(p.pid)
    p.wait()
