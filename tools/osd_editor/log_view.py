"""Log view (awto-ddc#358, docs/monitor-gui.md "Log view"): a unit's whole DRAM log, not only the 88-line ring view.
History in chunks of `dev.py synclog --dram --json` through the unit's job queue, then a follow poll (`--since next`).
Columns and starts / deltas come from the decoder's own functions (scripts/sync_log.py); rows deduplicated by absolute index."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableView,
                               QVBoxLayout, QWidget)

import monitor as MON
import sync_log as S
import unit_log

# Bus budget (measured 2026-11-27, unit 3, docs/monitor-gui.md "Log view"): a `--since` poll with a few new lines = 1.2 s job,
# debug link held ~0.4 s; FOLLOW_S 10 s = link held ~4 % of the time. A history chunk of CHUNK entries at 77 per s = 3.9 s + 2.2 s.
FOLLOW_S = 10
CHUNK = 300
FALLBACK_N = 1000                   # decoder without a range read: one `--last` job, 13 s at 77 per s (no older history)
MAX_ROWS = 40_000                   # AWTO_DLOG_SLOTS (32768) + boot separators
SEP_BG, START_BG = QBrush(QColor("#30363d")), MON.START_BG
WHITE = MON.START_BRUSH


def has_range_read() -> bool:
    """the decoder reads a DDR index range (`--since A --count K`, sync_log.py since #358)"""
    try:
        return '"--count"' in (MON.ROOT / "scripts" / "sync_log.py").read_text()
    except OSError:
        return False


def build_rows(ents: list[dict], cur_boot=None) -> list[dict]:
    """entries (sorted by abs) -> view rows with the decoder's console rows (sync_log.con_rows, as dram_log.con_lines): real time,
    delta, joined groups, starts; a `--- boot N ---` separator per boot counter. Time: the read join `poll_wall` (this boot, `~`)
    over the decoder's uptime column (`u`), as the JSON carries no host-time block"""
    if not ents:
        return []
    evs = [(e["id"], e["arg"], e["ms"] & 0xFFFF, e["val"]) for e in ents]
    ts = [(S.signed32(e["ms"]), True) for e in ents]
    texts = [e["text"].split(":", 1)[1] if ":" in e["text"] else e["text"] for e in ents]
    rs = S.con_rows(evs, texts, ts, None, [e["boot"] for e in ents], ents[-1]["boot"] if cur_boot is None else cur_boot)
    rows, boot = [], None
    for r in rs:
        e = ents[r["i"][0]]
        if e["boot"] != boot:
            boot = e["boot"]
            rows.append({"abs": None, "boot": boot, "sep": True, "real": "", "delta": "", "text": f"--- boot {boot} ---", "start": False, "wrap": False})
        if r["wrap"]:
            rows.append({"abs": None, "boot": boot, "sep": False, "real": "", "delta": "", "text": S.WRAP_TEXT, "start": False, "wrap": True})
        real = e["poll_wall"][11:23] + "~" if e.get("poll_wall") else r["real"].strip()
        rows.append({"abs": e["abs"], "boot": boot, "sep": False, "real": real, "delta": S.fmt_delta(r["delta"]).strip(),
                     "text": r["text"] + (f" {S.START_WORD}" if r["start"] else ""), "start": r["start"], "wrap": False})
    return rows


class LogModel(QAbstractTableModel):
    COLS = ("index", "time", "+delta", "line")

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.shown: list[int] = []
        self.q = ""

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self.rows = rows
        self._filter()
        self.endResetModel()

    def set_filter(self, q: str):
        self.beginResetModel()
        self.q = q.lower()
        self._filter()
        self.endResetModel()

    def _filter(self):
        q = self.q
        self.shown = [i for i, r in enumerate(self.rows) if not q or r["sep"] or q in r["text"].lower()]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.shown)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        return self.COLS[s] if o == Qt.Horizontal and role == Qt.DisplayRole else None

    def row(self, i: int) -> dict:
        return self.rows[self.shown[i]]

    def data(self, ix, role=Qt.DisplayRole):
        r = self.row(ix.row())
        if role == Qt.DisplayRole:
            return ("" if r["abs"] is None else str(r["abs"]), r["real"], r["delta"], r["text"])[ix.column()]
        if role == Qt.BackgroundRole and (r["sep"] or r["start"] or r["wrap"]):
            return SEP_BG if r["sep"] else START_BG
        if role == Qt.ForegroundRole and (r["sep"] or r["start"] or r["wrap"]):
            return WHITE
        return None

    def line(self, r: dict) -> str:
        return r["text"] if r["sep"] else f"{'' if r['abs'] is None else r['abs']:>6} {r['real']:<14}{r['delta']:>8}:{r['text']}"


class UnitLog:
    """one unit's entries by abs index + read state"""

    def __init__(self):
        self.ents: dict[int, dict] = {}
        self.boundary: int | None = None    # ring end, separate from a consumed follow page
        self.next: int | None = None        # consumed follow index at the last read
        self.lo: int | None = None          # oldest index read so far (history goes down from here)
        self.done = False                   # history complete (index 0, or the ring's oldest slot)
        self.slots = None
        self.gaps: list[dict] = []
        self.gen = None
        self.cur_boot = None                # the unit's current boot counter (DDR header)


class LogView(QWidget):
    def __init__(self, page: MON.MonitorPage):
        super().__init__()
        self.page = page
        self.logs: dict[str, UnitLog] = {}
        self.inflight: dict[str, int] = {}          # unit -> job id of its running log read (never two per unit)
        self.range_read = has_range_read()
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.unit = QComboBox()
        for n in page.states:
            self.unit.addItem(f"unit {n}", n)
        self.unit.currentIndexChanged.connect(lambda *_: self.show_unit())
        bar.addWidget(self.unit)
        self.hist_btn = QPushButton("Read history")
        self.hist_btn.clicked.connect(lambda: self.read_history())
        bar.addWidget(self.hist_btn)
        self.follow = QCheckBox(f"follow ({FOLLOW_S} s)")
        self.follow.setChecked(True)
        self.follow.setToolTip("poll the unit's DRAM log for new lines while this view is shown and the unit is idle (never during a flash)")
        bar.addWidget(self.follow)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter lines")
        self.filter.textChanged.connect(lambda q: (self.model.set_filter(q), self._jumps()))
        bar.addWidget(self.filter, 1)
        self.jump = QComboBox()
        self.jump.setMinimumWidth(260)
        self.jump.activated.connect(self._jump_to)
        bar.addWidget(self.jump)
        for txt, fn in (("Copy", self.copy), ("Save...", lambda: self.save())):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            bar.addWidget(b)
        lay.addLayout(bar)
        self.info = QLabel("")
        lay.addWidget(self.info)
        self.model = LogModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.setFont(QFont("monospace", 9))                     # the console's columns line up
        self.table.setSelectionBehavior(QTableView.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 60), (1, 110), (2, 70)):
            self.table.setColumnWidth(c, w)
        self.table.verticalHeader().setDefaultSectionSize(18)
        lay.addWidget(self.table, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(FOLLOW_S * 1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.started = False

    # --- reads
    def n(self) -> str:
        return self.unit.currentData() or self.page.cur

    def can_read(self, n: str) -> str:
        """'' = a log read may go now, else why not (yields to flashes and to the unit's other jobs)"""
        st = self.page.states[n]
        if not st.writable:
            return "read-only unit"
        if st.flash or getattr(self.page, "log_hold", {}).get(n):
            return "flashing"
        if n in self.inflight:
            return "a log read is running"
        if st.pending:
            return "the unit has other jobs"
        return ""

    def _read(self, n: str, args: list[str], label: str, then) -> bool:
        if self.can_read(n):
            return False

        def done(rc, out, secs):
            self.inflight.pop(n, None)
            snap = unit_log.parse_output(out)
            if snap is not None and (snap.get("complete") is False or snap.get("status") == "error"):
                self.info.setText(f"unit {n} {label}: read failed: {snap['error']['message']}; previous lines kept")
                return
            if snap is None or rc != 0:
                self.info.setText(f"unit {n} {label}: failed (rc {rc}): {MON.reason_line(out)}")
                return
            self.ingest(n, snap)
            then(snap)
        lg = self.logs.get(n)
        if "--since" in args and lg is not None and lg.gen is not None:
            args = [*args, "--since-gen", str(lg.gen)]
        jid = self.page.synclog_job(f"log view {label}", ["--dram", "--json", *args], None, unit=n, after=done)
        if jid is None:
            return False
        self.inflight[n] = jid
        return True

    def read_history(self, n: str | None = None) -> bool:
        """newest chunk first, then older chunks one job at a time down to the oldest slot (each job <= CHUNK entries)"""
        n = n or self.n()
        lg = self.logs.setdefault(n, UnitLog())
        if lg.next is None or not self.range_read:
            count = CHUNK if self.range_read else FALLBACK_N
            return self._read(n, ["--last", str(count)], f"history newest {count}", lambda snap: self._more(n))
        return self._more(n)

    def _more(self, n: str) -> bool:
        lg = self.logs[n]
        if not self.range_read or lg.done or lg.lo is None:
            lg.done = True
            self.show_unit()
            return False
        bottom = max(0, (lg.boundary or lg.next) - (lg.slots or lg.next))
        if lg.lo <= bottom:
            lg.done = True
            self.show_unit()
            return False
        a = max(bottom, lg.lo - CHUNK)
        cnt = lg.lo - a
        QTimer.singleShot(0, lambda: self._read(n, ["--since", str(a), "--count", str(cnt)], f"history {a}..{a + cnt - 1}",
                                                lambda snap: (setattr(lg, "lo", min(lg.lo, a)), self._more(n))))
        return True

    def tick(self):
        """follow: new lines since the last read; history continues when it was cut by a flash or another job"""
        if not (self.follow.isChecked() and self.isVisible()):
            return
        n = self.n()
        lg = self.logs.get(n)
        if lg is None or lg.next is None:
            self.read_history(n)
        elif self.range_read and not lg.done:
            self._more(n)
        else:
            cnt = ["--count", str(CHUNK)] if self.range_read else []       # bounded job; more than CHUNK new lines = the next poll goes on
            self._read(n, ["--since", str(lg.next), *cnt], f"follow since {lg.next}", lambda snap: None)

    def showEvent(self, e):
        super().showEvent(e)
        if not self.started:
            self.started = True
            QTimer.singleShot(0, self.tick)

    def ingest(self, n: str, snap: dict):
        unit_log.require_complete(snap)
        lg = self.logs.setdefault(n, UnitLog())
        if lg.gen is not None and (snap.get("gen") != lg.gen or
                                   (snap.get("cursor_reset") and snap.get("next", 0) < (lg.next or 0))):
            # A new generation reuses indices. Keep this object for pending history callbacks.
            self.page.say(f"unit {n} log view: DDR log generation {lg.gen} -> {snap.get('gen')}, earlier lines dropped from the view")
            lg.__init__()
        lg.gen, lg.slots, lg.cur_boot = snap.get("gen"), snap.get("slots"), snap.get("boot")
        for gap in snap.get("gaps", []):
            if gap not in lg.gaps:
                lg.gaps.append(gap)
                self.page.say(f"unit {n} log view gap: indexes {gap['start']}..{gap['end'] - 1} {gap['reason']}")
        new = [e for e in snap["entries"] if e["abs"] not in lg.ents]
        for e in snap["entries"]:
            lg.ents[e["abs"]] = e                    # a re-read replaces (poll_wall of the current boot gets sharper)
        lg.boundary = snap.get("next")
        lg.next = max(lg.next or 0, snap.get("end", snap.get("next")) or 0)
        if snap["entries"]:
            lo = min(e["abs"] for e in snap["entries"])
            lg.lo = lo if lg.lo is None else min(lg.lo, lo)
        if len(lg.ents) > MAX_ROWS:
            for a in sorted(lg.ents)[:len(lg.ents) - MAX_ROWS]:
                del lg.ents[a]
        self.page.say(f"unit {n} log view: {len(new)} new of {len(snap['entries'])} read, {len(lg.ents)} kept, next index {lg.next}")
        if n == self.n():
            self.show_unit()

    # --- view
    def show_unit(self):
        n = self.n()
        lg = self.logs.get(n)
        bar = self.table.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 2
        ents = [lg.ents[a] for a in sorted(lg.ents)] if lg else []
        gaps = [{"abs": None, "boot": None, "sep": True, "real": "", "delta": "", "start": False, "wrap": False,
                 "text": f"--- gap: indexes {g['start']}..{g['end'] - 1} {g['reason']} ---"} for g in (lg.gaps if lg else [])]
        self.model.set_rows(gaps + build_rows(ents, lg.cur_boot if lg else None))
        self._jumps()
        if at_end:
            self.table.scrollToBottom()
        why = "" if self.range_read else f"; history = newest {FALLBACK_N} only (decoder without a range read, #358)"
        span = f"index {min(lg.ents)}..{max(lg.ents)}" if lg and lg.ents else "nothing read yet"
        hist = "complete" if lg and lg.done else "reading" if n in self.inflight else "partial"
        self.info.setText(f"unit {n}: {len(ents)} lines, {span}, history {hist}, next {lg.next if lg else '-'}{why}")

    def _jumps(self):
        self.jump.clear()
        self.jump.addItem("jump to episode / boot ...", -1)
        for i, k in enumerate(self.model.shown):
            r = self.model.rows[k]
            if r["sep"] or r["start"]:
                self.jump.addItem(f"{r['real'] or ''} {r['text'][:60]}".strip(), i)

    def _jump_to(self, idx: int):
        i = self.jump.itemData(idx)
        if i is not None and i >= 0:
            self.table.scrollTo(self.model.index(i, 0), QTableView.ScrollHint.PositionAtTop)
            self.table.selectRow(i)

    def text(self, rows: list[dict] | None = None) -> str:
        return "\n".join(self.model.line(r) for r in (rows if rows is not None else [self.model.row(i) for i in range(self.model.rowCount())])) + "\n"

    def copy(self):
        sel = sorted({ix.row() for ix in self.table.selectionModel().selectedRows()})
        QGuiApplication.clipboard().setText(self.text([self.model.row(i) for i in sel] if sel else None))

    def save(self, path: str | None = None) -> str | None:
        n = self.n()
        dest = path or QFileDialog.getSaveFileName(self, "Save the log view as",
                                                   f"{self.page.states[n].info['serial']}-log-{time.strftime('%Y%m%d-%H%M%S')}.log")[0]
        if dest:
            Path(dest).write_text(self.text())
            self.page.say(f"unit {n} log view saved as {dest} ({self.model.rowCount()} rows)")
        return dest or None
