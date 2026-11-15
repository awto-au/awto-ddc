"""Monitor page (awto-ddc#217): settings, input, host time, health, boot/sync log of one unit.
Every action is a scripts/ subprocess off the UI thread (unit lock, EDID serial check and test-unit guard stay in the
scripts); no I2C in here. dev.py wraps the debug link on/off around each call and finds bus + map itself."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QSlider, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import isostamp  # noqa: E402
import settings_table as T  # noqa: E402

PYTHON = "python3"
LOG = ROOT / "tmp" / "logs" / "osd_editor.log"
# backstop above the scripts' own guards (mailbox 0.47 s, DDC/CI 1.7 s, debug-link swap 0.5 s); expiry: kill + log line
CALL_LIMIT_S = 60
SLOW_MS = 100                                            # sync log: a step slower than this is highlighted (#216)
SLOW_BRUSH = QBrush(QColor("#ff5050"))
INPUTS = ("D1", "D2", "D3")                              # scripts/kvm.py port names
VALUE_RE = re.compile(r"(?:^|\s)(\w+) = .* \(raw (-?\d+)\)\s*$")
STEP_RE = re.compile(r"(?:^|\s)(\d{1,5}):(?!\d)")        # sync_log line: "<ms since episode start>:text"
WRITABLE_TIP = "writes go to the test unit only (scripts/devices.json)"


def load_units() -> dict:
    return json.loads((ROOT / "scripts" / "devices.json").read_text())["units"]


class SubprocessBackend:
    """run(argv) -> (rc, output); the stall guard is the scripts' own, CALL_LIMIT_S the backstop."""

    def run(self, argv: list[str]) -> tuple[int, str]:
        try:
            p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=CALL_LIMIT_S)
        except subprocess.TimeoutExpired as e:
            return 124, f"killed after {CALL_LIMIT_S} s (backstop): {' '.join(map(str, argv))}\n{e.stdout or ''}"
        return p.returncode, (p.stdout or "") + (p.stderr or "")


class _Done(QObject):
    done = Signal(int, int, str, float)                  # job id, rc, output, seconds


class _Job(QRunnable):
    def __init__(self, backend, argv, sig, jid):
        super().__init__()
        self.backend, self.argv, self.sig, self.jid = backend, argv, sig, jid

    def run(self):
        t0 = time.monotonic()
        try:
            rc, out = self.backend.run(self.argv)
        except Exception as e:                           # backend failure is a result, never a dead worker
            rc, out = 125, f"backend error: {e!r}"
        self.sig.done.emit(self.jid, rc, out, time.monotonic() - t0)


def sync_rows(text: str) -> list[tuple[str, str, bool]]:
    """(+ms, line, slow) per sync_log line that carries a '<ms>:' field; +ms = step since the previous line"""
    rows, prev = [], None
    for ln in text.splitlines():
        m = STEP_RE.search(ln)
        if not m:
            continue
        t = int(m.group(1))
        d = None if prev is None or t < prev else t - prev      # t < prev: new episode in a --whole dump
        prev = t
        rows.append(("" if d is None else f"+{d}", ln.rstrip(), d is not None and d > SLOW_MS))
    return rows


class SettingRow(QWidget):
    """One registry row: widget + value label + Set (the page runs the call)."""

    def __init__(self, r: dict, on_set):
        super().__init__()
        self.r = r
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(r["label"])
        lab.setMinimumWidth(150)
        lab.setToolTip(f"{r['name']} (id {r['id']}) {','.join(r['flags'])}\n{r['note']}")
        lay.addWidget(lab)
        if r["type"] == "int":
            self.w = QSlider(Qt.Horizontal)
            self.w.setRange(r["min"], r["max"])
            self.w.setSingleStep(r["step"])
            self.w.valueChanged.connect(self._shown)
            self.val = QLabel()
            self.val.setMinimumWidth(80)
        else:                                            # enum, bool (0/1 as combo too)
            self.w = QComboBox()
            self.w.addItems(r["options"] or ["off", "on"])
            self.val = None
        lay.addWidget(self.w, 1)
        if self.val:
            lay.addWidget(self.val)
        self.cur = QLabel("-")
        self.cur.setMinimumWidth(120)
        lay.addWidget(self.cur)
        self.btn = QPushButton("Set")
        self.btn.clicked.connect(lambda: on_set(self))
        lay.addWidget(self.btn)
        self._shown()

    def _shown(self, *_):
        if self.val:
            self.val.setText(f"{self.w.value()} {dict(percent='%', ms='ms', s='s').get(self.r['unit'], '')}".strip())

    def raw(self) -> int:
        return self.w.value() if self.r["type"] == "int" else self.r["min"] + self.w.currentIndex()

    def put(self, v: int):
        if self.r["type"] == "int":
            self.w.setValue(v)
        else:
            self.w.setCurrentIndex(max(0, min(v - self.r["min"], self.w.count() - 1)))
        self.cur.setText(f"unit: {v}")


class MonitorPage(QWidget):
    def __init__(self, backend=None, log_path: Path = LOG):
        super().__init__()
        self.backend, self.log_path = backend or SubprocessBackend(), log_path
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)                   # one script at a time: they share the unit's bus
        self.units = load_units()
        self.rows: dict[str, SettingRow] = {}
        self.next_id = 0
        self.jobs: dict[int, tuple] = {}
        self.sig = _Done(self)
        self.sig.done.connect(self._finish, Qt.QueuedConnection)    # UI-thread slot, emitted from the worker
        self.buttons: list[QPushButton] = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.unit = QComboBox()
        for n, u in self.units.items():
            self.unit.addItem(f"unit {n}  {u['serial']}  {u['input']}{'' if u.get('test') else '  (read-only)'}", n)
        top.addWidget(QLabel("unit"))
        top.addWidget(self.unit, 1)
        self.state = QLabel()
        top.addWidget(self.state, 2)
        lay.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._settings_panel())
        split.addWidget(self._side_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self.unit.currentIndexChanged.connect(self.unit_changed)
        self.unit.setCurrentIndex(max(0, next((i for i, (n, u) in enumerate(self.units.items()) if u.get("test")), 0)))
        self.unit_changed()

    # --- layout
    def _btn(self, text, fn) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda: fn())
        self.buttons.append(b)
        return b

    def _settings_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("<b>settings</b>"))
        bar.addStretch()
        self.live = QCheckBox("hide inert rows")
        self.live.toggled.connect(self.filter_rows)
        bar.addWidget(self.live)
        bar.addWidget(self._btn("Get all", self.get_all))
        bar.addWidget(self._btn("Save", self.save))
        lay.addLayout(bar)
        inner = QWidget()
        il = QVBoxLayout(inner)
        group = None
        for r in T.ROWS:
            if r["type"] not in ("int", "enum", "bool"):
                continue
            if r["group"] != group:
                group = r["group"]
                il.addWidget(QLabel(f"<b>{group}</b>"))
            sr = SettingRow(r, self.set_row)
            self.rows[r["name"]] = sr
            self.buttons.append(sr.btn)
            il.addWidget(sr)
        il.addStretch()
        sa = QScrollArea()
        sa.setWidget(inner)
        sa.setWidgetResizable(True)
        lay.addWidget(sa, 1)
        return f

    def _side_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        r1 = QHBoxLayout()
        self.inp = QComboBox()
        self.inp.addItems(INPUTS)
        r1.addWidget(QLabel("input"))
        r1.addWidget(self.inp)
        r1.addWidget(self._btn("Input select", self.input_select))
        r1.addWidget(self._btn("Host time: send now", self.host_time))
        r1.addWidget(self._btn("Health", self.health))
        lay.addLayout(r1)
        lay.addWidget(QLabel("<b>actions</b>"))
        self.actions = QPlainTextEdit(readOnly=True)
        self.actions.setMaximumBlockCount(2000)
        lay.addWidget(self.actions, 1)
        sb = QHBoxLayout()
        sb.addWidget(QLabel("<b>boot / sync log</b>"))
        sb.addStretch()
        sb.addWidget(self._btn("Read sync log", self.sync_log))
        lay.addLayout(sb)
        self.sync = QTableWidget(0, 2)
        self.sync.setHorizontalHeaderLabels(["+ms", "line"])
        self.sync.horizontalHeader().setStretchLastSection(False)
        self.sync.horizontalHeader().setSectionResizeMode(1, self.sync.horizontalHeader().ResizeMode.Stretch)
        self.sync.setColumnWidth(0, 60)
        self.sync.verticalHeader().hide()
        lay.addWidget(self.sync, 3)
        lay.addWidget(QLabel("<b>last output</b>"))
        self.out = QPlainTextEdit(readOnly=True)
        self.out.setMaximumBlockCount(500)
        lay.addWidget(self.out, 1)
        return f

    # --- state
    def n(self) -> str:
        return self.unit.currentData()

    def writable(self) -> bool:
        return bool(self.units[self.n()].get("test"))

    def unit_changed(self, *_):
        w = self.writable()
        for b in self.buttons:
            b.setEnabled(w)
        self.inp.setEnabled(w)
        self.state.setText("test unit: writable" if w else "working screen: read-only, controls greyed")
        self.state.setStyleSheet("" if w else "color: #ff5050;")
        self.say(f"unit {self.n()} selected ({'test, writable' if w else 'read-only'})")

    def filter_rows(self, hide: bool):
        for sr in self.rows.values():
            sr.setVisible(not (hide and "inert" in sr.r["flags"]))

    def say(self, msg: str):
        line = f"{isostamp.now()} {msg}"
        self.actions.appendPlainText(line)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(line + "\n")
        except OSError as e:
            self.actions.appendPlainText(f"{isostamp.now()} log file not written: {e}")

    # --- jobs
    def run(self, label: str, argv: list, done):
        if not self.writable():                          # same guard as the disabled buttons; dev.py refuses it too
            self.say(f"unit {self.n()} {label}: refused, read-only unit")
            return
        argv = [str(a) for a in argv]
        jid = self.next_id = self.next_id + 1
        self.jobs[jid] = (label, done, self.n())
        self.say(f"unit {self.n()} {label}: started")
        self.pool.start(_Job(self.backend, argv, self.sig, jid))

    def _finish(self, jid, rc, out, secs):
        label, done, unit = self.jobs.pop(jid)
        self.out.setPlainText(out.rstrip())
        extra = done(rc, out) if done else ""
        self.say(f"unit {unit} {label}: {'ok' if rc == 0 else f'FAILED rc {rc}'}{extra} ({secs:.1f} s)")

    def wait_idle(self):
        self.pool.waitForDone()

    def dev(self, *args):
        return [PYTHON, ROOT / "dev.py", *args, "--unit", self.n()]

    # --- actions
    def get_all(self):
        self.run("settings get all", self.dev("settings", "list"), self._got)

    def _got(self, rc, out) -> str:
        k = 0
        for ln in out.splitlines():
            m = VALUE_RE.search(ln)
            if m and m.group(1) in self.rows:
                self.rows[m.group(1)].put(int(m.group(2)))
                k += 1
        return f", {k} rows"

    def set_row(self, sr: SettingRow):
        v = sr.raw()
        self.run(f"set {sr.r['name']} = {v}", self.dev("settings", "set", sr.r["name"], v),
                 lambda rc, out: (sr.cur.setText(f"unit: {v}") or "") if rc == 0 else ", unit kept its value")

    def save(self):
        self.run("settings save", self.dev("settings", "save"), None)

    def input_select(self):
        p = self.inp.currentText()
        self.run(f"input select {p}", [PYTHON, ROOT / "scripts" / "kvm.py", p, "--units", self.n()], None)

    def host_time(self):
        self.run("host time send now", [PYTHON, ROOT / "scripts" / "host_time.py", "--unit", self.n(), "--once"], None)

    def health(self):
        self.run("health", self.dev("health"), lambda rc, out: ", " + next(
            (ln.strip() for ln in reversed(out.splitlines()) if "PASS" in ln or "FAIL" in ln), "no verdict line"))

    def sync_log(self):
        self.run("sync log", self.dev("synclog", "--whole"), self._synced)

    def _synced(self, rc, out) -> str:
        rows = sync_rows(out)
        self.sync.setRowCount(len(rows))
        for i, (d, ln, slow) in enumerate(rows):
            for c, t in enumerate((d, ln)):
                it = QTableWidgetItem(t)
                if slow and c == 0:
                    it.setForeground(SLOW_BRUSH)
                    it.setBackground(QBrush(QColor("#3a1a1a")))
                self.sync.setItem(i, c, it)
        return f", {len(rows)} lines, {sum(s for *_, s in rows)} over {SLOW_MS} ms"
