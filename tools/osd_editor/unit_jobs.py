"""Job backend of the monitor page: dev.py / scripts subprocesses, one queue (one worker) per unit.
Units sit on different buses, so their jobs run in parallel; one unit's jobs run one at a time (one bus)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

ROOT = Path(__file__).resolve().parents[2]
TERM_GRACE_S = 2                                         # debug-link swap is 0.5 s
STALL_POLL_S = 0.1                                       # stall / limit check pace of a guarded job (a stall limit is seconds)


class SubprocessBackend:
    """run(argv, limit_s) -> (rc, output); rc 124 = limit expired, process stopped.
    live_set / live_get = DDC/CI frames straight on the unit's bus from the unit's worker thread (persistent fd, awto-ddc#277)."""

    def run(self, argv: list[str], limit_s: float, stall_s: float | None = None) -> tuple[int, str]:
        p = subprocess.Popen(argv, cwd=ROOT, env={**os.environ, "AWTO_GUI_WORKER": "1"}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if stall_s:
            return self._run_stall(p, argv, limit_s, stall_s)
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

    def _run_stall(self, p, argv, limit_s: float, stall_s: float) -> tuple[int, str]:
        """limit_s overall (backstop) + stall_s without an output line (the read's progress lines): expiry = TERM, rc 124, named"""
        lines, last = [], [time.monotonic()]

        def pump():
            for ln in p.stdout:
                lines.append(ln)
                last[0] = time.monotonic()
        t = threading.Thread(target=pump, daemon=True)
        t.start()
        t0, why = time.monotonic(), ""
        while p.poll() is None:
            now = time.monotonic()
            if now - t0 > limit_s:
                why = f"limit {limit_s} s expired"
            elif now - last[0] > stall_s:
                why = f"no output for {stall_s} s (stall guard; last line: {lines[-1].strip() if lines else 'none'})"
            if why:
                p.terminate()
                try:
                    p.wait(TERM_GRACE_S)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                t.join(TERM_GRACE_S)
                return 124, f"{why} after {now - t0:.1f} s, process stopped: {' '.join(map(str, argv))}\n{''.join(lines)}"
            try:
                p.wait(STALL_POLL_S)
            except subprocess.TimeoutExpired:
                pass
        t.join(TERM_GRACE_S)
        return p.returncode, "".join(lines)

    def _session(self, u: dict):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))                # dev.py (the EDID-proven bus lookup) sits at the repo root
        import dev
        import unit_ops
        return unit_ops.session_for(dev, u)

    def live_set(self, u: dict, code: int, value: int, row_id: int | None, reselect: bool) -> tuple[int, str]:
        try:
            self._session(u).set_vcp(code, value, reselect=reselect, row_id=row_id)
        except (OSError, ValueError, SystemExit) as e:   # SystemExit = dev._bus: no bus with that EDID serial
            return 1, f"live set {code:#04x} = {value}: {e!r}"
        return 0, ""

    def live_get(self, u: dict, code: int, row_id: int | None) -> tuple[int, str]:
        try:
            cur, mx = self._session(u).get_vcp(code, row_id=row_id)
        except (OSError, ValueError, SystemExit) as e:
            return 1, f"live get {code:#04x}: {e!r}"
        return 0, f"value {cur} max {mx}"

    def status_read(self, u: dict) -> tuple[int, str]:
        """one read-only status pass of the unit (unit_ops.status: Get VCP + debug-slave reads), JSON text, on the unit's worker thread"""
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            import dev
            import unit_ops
            return 0, json.dumps(unit_ops.status(dev, u))
        except (OSError, ValueError, SystemExit) as e:
            return 1, f"status read: {e!r}"


DDC_LOCK = threading.Lock()   # every dev.py ddc call runs `ddcutil detect` over all buses: parallel calls slow each other (measured 3x) and time out


def is_ddc(argv) -> bool:
    return "ddc" in argv and any(a in argv for a in ("get", "set"))


class _Job(QRunnable):
    def __init__(self, backend, argv, limit, owner, jid, fn=None, stall=None):
        super().__init__()
        self.backend, self.argv, self.limit, self.owner, self.jid, self.fn, self.stall = backend, argv, limit, owner, jid, fn, stall

    def run(self):
        t0 = time.monotonic()
        try:
            if self.fn is not None:                       # in-process call on this unit's worker thread (live writes): no ddcutil, no DDC_LOCK
                rc, out = self.fn()
            elif is_ddc(self.argv):                         # the limit starts when the call starts, not while it waits its turn
                with DDC_LOCK:
                    t0 = time.monotonic()
                    rc, out = self.backend.run(self.argv, self.limit)
            else:
                rc, out = self.backend.run(self.argv, self.limit, **({"stall_s": self.stall} if self.stall else {}))
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

    def submit(self, unit: str, argv: list, limit_s: float, stall_s: float | None = None) -> int:
        pool = self.pools.get(unit)
        if pool is None:
            pool = self.pools[unit] = QThreadPool(self)
            pool.setMaxThreadCount(1)                    # one script at a time per unit: they share its bus
        jid = self.next_id = self.next_id + 1
        pool.start(_Job(self.backend, [str(a) for a in argv], limit_s, self, jid, stall=stall_s))
        return jid

    def submit_fn(self, unit: str, fn) -> int:
        """run fn() -> (rc, output) on the unit's worker thread, in order with that unit's other jobs; same `done` signal"""
        pool = self.pools.get(unit)
        if pool is None:
            pool = self.pools[unit] = QThreadPool(self)
            pool.setMaxThreadCount(1)
        jid = self.next_id = self.next_id + 1
        pool.start(_Job(self.backend, [], 0, self, jid, fn))
        return jid

    def wait_idle(self):
        for p in self.pools.values():
            p.waitForDone()
