"""build_guard (#316): memory check and the one-build lock."""
import fcntl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_guard as G


def test_avail_mb_reads_meminfo(tmp_path):
    m = tmp_path / "mi"
    m.write_text("MemTotal: 100 kB\nMemAvailable:   2097152 kB\n")
    assert G.avail_mb(m) == 2048


def test_low_memory_refuses(tmp_path):
    with pytest.raises(SystemExit, match="available"):
        G.acquire(tmp_path, lock=tmp_path / "l", min_mb=1 << 30)


def test_lock_taken_and_second_waiter_times_out(tmp_path):
    lock = tmp_path / "locks" / "build.lock"
    G.acquire(tmp_path, lock=lock, wait_s=1, min_mb=1)
    assert "pid" in lock.read_text()
    other = lock.open("a+")
    with pytest.raises(BlockingIOError):
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)   # held by this process's descriptor
    G._held.close()
