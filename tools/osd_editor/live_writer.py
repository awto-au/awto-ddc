"""Live sliders (awto-ddc#277): a drag writes to the unit while it moves, but sends few values.
Per control (unit + setting): at most ONE write in flight and ONE pending value (the latest); when a write completes the latest pending
value goes at once, so the send rate follows the real write latency. Equal values are skipped, a floor spaces the writes, and the exact
released value is always the last write. RAM-apply only: no save is sent (the firmware's own gate writes NVRAM after the last change).
Design, numbers and the NVRAM finding: docs/monitor-gui.md "Live sliders"."""
from __future__ import annotations

import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import settings_table as T  # noqa: E402

FLOOR_MIN_S = 0.030          # a write below this gains nothing: firmware serves DDC/CI once per 20 ms pass (AWTO_SET_LOOP_MS)
FLOOR_FACTOR = 1.25          # floor = 1.25 x the unit's median write time (last LAT_WINDOW writes): the bus is never kept busy back to back
FLOOR_INITIAL_S = 0.040      # before a unit has a measured latency (docs/monitor-gui.md "Live sliders" for the measured value)
LAT_WINDOW = 8
SETTLE_S = 0.5               # keyboard / wheel steps have no release: this long without a change = released (above key repeat and wheel gaps)
SEND_WATCH_S = 1.0           # a write that has not completed after this is logged once (worker stuck behind a slow call), never abandoned


def wire(r: dict, v: int) -> tuple[int, int | None, int]:
    """(vcp code, registry row id or None, raw value) for a row value: rows with a VCP code write it direct (enum = the option's VCP value),
    the rest go through the paged pair 0xE0 / 0xE1 (value = the row's own value)"""
    if r.get("vcp") is not None:
        raw = r["option_vcp"][v - r["min"]] if r.get("option_vcp") else v
        return r["vcp"], None, raw
    return 0xE1, r["id"], v


def from_wire(r: dict, raw: int) -> int | None:
    """row value of a value read from the unit (inverse of wire); None = not one of the row's options"""
    if r.get("vcp") is not None and r.get("option_vcp"):
        return r["min"] + r["option_vcp"].index(raw) if raw in r["option_vcp"] else None
    return raw


@dataclass
class Ctl:
    unit: str
    name: str
    r: dict
    last_sent: int | None = None
    pending: int | None = None
    inflight: bool = False
    finishing: bool = False
    cancelled: bool = False
    failed: str = ""
    pre: int | None = None
    values: int = 0
    writes: int = 0
    skipped: int = 0
    first: int | None = None
    t0: float = 0.0
    reselect: bool = True
    active: bool = False
    held: bool = False
    timer: QTimer | None = None
    settle: QTimer | None = None
    sent_log: list = field(default_factory=list)


class LiveWriter(QObject):
    state = Signal(str, str, str)                # unit, name, "" | "sending" | "reading" | text: the row's indicator

    def __init__(self, page, clock=time.monotonic):
        super().__init__(page)
        self.page, self.clock = page, clock
        self.ctls: dict[tuple[str, str], Ctl] = {}
        self.lat: dict[str, deque] = {}
        self.unit_t: dict[str, float] = {}       # start of the unit's last write (all its controls share the bus)
        self.listeners: list = []                # callables(summary dict) per finished drag
        self.history: list[dict] = []

    # --- floor
    def floor_s(self, unit: str) -> float:
        d = self.lat.get(unit)
        return max(FLOOR_MIN_S, FLOOR_FACTOR * statistics.median(d)) if d else FLOOR_INITIAL_S

    def median_ms(self, unit: str) -> float | None:
        d = self.lat.get(unit)
        return round(statistics.median(d) * 1000, 1) if d else None

    # --- control events (UI thread)
    def ctl(self, unit: str, name: str) -> Ctl:
        k = (unit, name)
        c = self.ctls.get(k)
        if c is None:
            c = self.ctls[k] = Ctl(unit, name, T.BY_NAME[name])
            c.timer = QTimer(self)
            c.timer.setSingleShot(True)
            c.timer.timeout.connect(lambda c=c: self._pump(c))
            c.settle = QTimer(self)
            c.settle.setSingleShot(True)
            c.settle.setInterval(int(SETTLE_S * 1000))
            c.settle.timeout.connect(lambda c=c: self.release(c.unit, c.name, c.pending if c.pending is not None else c.last_sent))
        return c

    def busy(self, unit: str, name: str) -> bool:
        c = self.ctls.get((unit, name))
        return bool(c and c.active)

    def begin(self, unit: str, name: str, start: int | None):
        """a drag starts (slider pressed) or a first step arrives: `start` = the value the unit has now (the pre-drag value)"""
        c = self.ctl(unit, name)
        if c.active:                             # a new drag while the last one still reads back: it resumes the same session
            c.finishing, c.cancelled = False, False
            return c
        c.active, c.finishing, c.cancelled, c.failed, c.held = True, False, False, "", False
        c.pending, c.pre, c.last_sent, c.first = None, start, start, start
        c.values = c.writes = c.skipped = 0
        c.t0, c.reselect, c.sent_log = self.clock(), True, []
        return c

    def change(self, unit: str, name: str, v: int, before: int | None = None):
        """the control now shows v (a valueChanged): becomes the pending value; sent as soon as the coalescing rules allow"""
        c = self.ctls.get((unit, name))
        if c is None or not c.active or c.finishing:
            c = self.begin(unit, name, before)
        c.values += 1
        if not c.held:
            c.settle.start()                     # restarts on every change; only a quiet control (keyboard / wheel) ever lets it fire
        if v == c.last_sent and c.pending is None:
            c.skipped += 1
            return
        if c.pending is not None and c.pending != v:
            c.skipped += 1                       # an older pending value replaced by this newer one: never sent
        c.pending = v
        self._pump(c)

    def hold(self, unit: str, name: str, start: int | None):
        """the mouse is down on the slider: a drag begins and the settle timer must not end it while the pointer rests"""
        c = self.begin(unit, name, start)
        c.held = True
        c.settle.stop()

    def release(self, unit: str, name: str, final: int | None):
        """slider released / control settled: `final` (the exact value) is sent if it is not already the last sent value, then read back"""
        c = self.ctls.get((unit, name))
        if c is None or not c.active or c.finishing:
            return
        c.settle.stop()
        c.held = False
        c.finishing = True
        if final is not None and final != c.last_sent:
            c.pending = final
        elif final == c.last_sent:
            c.pending = None
        self._pump(c)

    def cancel(self, unit: str, name: str):
        """Esc during a drag: the pre-drag value is written back (one write, none if nothing was sent) and read back"""
        c = self.ctls.get((unit, name))
        if c is None or not c.active:
            return
        c.cancelled = True
        self.release(unit, name, c.pre)

    # --- send loop
    def _pump(self, c: Ctl):
        if c.inflight:
            return
        if c.failed:
            c.pending = None
        if c.pending is not None and c.pending == c.last_sent:
            c.pending = None
        if c.pending is None:
            if c.finishing:
                self._readback(c)
            return
        wait = self.floor_s(c.unit) - (self.clock() - self.unit_t.get(c.unit, -1e9))
        if wait > 0:
            if not c.timer.isActive():
                c.timer.start(max(1, int(wait * 1000 + 0.999)))
            return
        self._send(c)

    def _send(self, c: Ctl):
        v, c.pending = c.pending, None
        code, row_id, raw = wire(c.r, v)
        reselect, c.reselect = c.reselect, False
        u = self.page.states[c.unit].info
        backend = self.page.queues.backend
        c.inflight = True
        c.last_sent = v
        c.writes += 1
        self.unit_t[c.unit] = self.clock()
        c.sent_log.append(v)
        self.state.emit(c.unit, c.name, "sending")
        jid = self.page.queues.submit_fn(c.unit, lambda: backend.live_set(u, code, raw, row_id, reselect))
        self.page.live_jobs[jid] = lambda rc, out, secs: self._wrote(c, rc, out, secs)

    def _wrote(self, c: Ctl, rc: int, out: str, secs: float):
        c.inflight = False
        if rc == 0:
            self.lat.setdefault(c.unit, deque(maxlen=LAT_WINDOW)).append(secs)
        else:
            c.failed = out.strip() or f"rc {rc}"
            c.reselect = True
        self._pump(c)

    def _readback(self, c: Ctl):
        if c.failed:
            return self._done(c, None, "")
        u = self.page.states[c.unit].info
        code, row_id, _ = wire(c.r, c.last_sent if c.last_sent is not None else c.r["min"])
        backend = self.page.queues.backend
        c.inflight = True
        self.state.emit(c.unit, c.name, "reading")
        jid = self.page.queues.submit_fn(c.unit, lambda: backend.live_get(u, code, row_id))
        self.page.live_jobs[jid] = lambda rc, out, secs: self._read(c, rc, out)

    def _read(self, c: Ctl, rc: int, out: str):
        c.inflight = False
        if not c.finishing or c.pending is not None:   # the user moved again while the read-back ran: its answer is for an older value
            return self._pump(c)
        if rc != 0:
            return self._done(c, None, out.strip() or f"rc {rc}")
        try:
            raw = int(out.split()[1])
        except (IndexError, ValueError):
            return self._done(c, None, f"reply not understood: {out.strip()!r}")
        self._done(c, from_wire(c.r, raw), "")

    def _done(self, c: Ctl, got: int | None, err: str):
        dur = self.clock() - c.t0
        c.active = False
        c.finishing = False
        why = c.failed or err
        res = {"unit": c.unit, "name": c.name, "from": c.first, "to": c.last_sent, "values": c.values, "writes": c.writes,
               "skipped": c.skipped, "saves": 0, "readback": got, "cancelled": c.cancelled, "error": why,
               "verified": got is not None and got == c.last_sent, "duration_s": round(dur, 3),
               "floor_ms": round(self.floor_s(c.unit) * 1000), "median_write_ms": self.median_ms(c.unit), "sent": list(c.sent_log)}
        self.history.append(res)
        self.state.emit(c.unit, c.name, "")
        self.page.live_finished(res)
        for f in list(self.listeners):
            f(res)
