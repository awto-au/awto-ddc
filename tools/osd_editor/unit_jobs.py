"""Job backend of the monitor page: dev.py / scripts subprocesses, one queue (one worker) per unit.
Units sit on different buses, so their jobs run in parallel; one unit's jobs run one at a time (one bus)."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

ROOT = Path(__file__).resolve().parents[2]
TERM_GRACE_S = 2                                         # debug-link swap is 0.5 s


class SubprocessBackend:
    """run(argv, limit_s) -> (rc, output); rc 124 = limit expired, process stopped."""

    def run(self, argv: list[str], limit_s: float) -> tuple[int, str]:
        p = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=limit_s)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                out, _ = p.communicate(timeout=TERM_GRACE_S)
            except subprocess.TimeoutExpired:
                p.kill()
                out, _ = p.communicate()
            return 124, f"limit {limit_s} s expired, process stopped: {' '.join(map(str, argv))}\n{out or ''}"
        return p.returncode, out or ""


class _Job(QRunnable):
    def __init__(self, backend, argv, limit, owner, jid):
        super().__init__()
        self.backend, self.argv, self.limit, self.owner, self.jid = backend, argv, limit, owner, jid

    def run(self):
        t0 = time.monotonic()
        try:
            rc, out = self.backend.run(self.argv, self.limit)
        except Exception as e:                           # backend failure is a result, never a dead worker
            rc, out = 125, f"backend error: {e!r}"
        self.owner.done.emit(self.jid, rc, out, time.monotonic() - t0)


class UnitQueues(QObject):
    done = Signal(int, int, str, float)                  # job id, rc, output, seconds (emitted from the worker)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.pools: dict[str, QThreadPool] = {}
        self.next_id = 0

    def submit(self, unit: str, argv: list, limit_s: float) -> int:
        pool = self.pools.get(unit)
        if pool is None:
            pool = self.pools[unit] = QThreadPool(self)
            pool.setMaxThreadCount(1)                    # one script at a time per unit: they share its bus
        jid = self.next_id = self.next_id + 1
        pool.start(_Job(self.backend, [str(a) for a in argv], limit_s, self, jid))
        return jid

    def wait_idle(self):
        for p in self.pools.values():
            p.waitForDone()
