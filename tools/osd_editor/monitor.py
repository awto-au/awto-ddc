"""Monitor page (awto-ddc#217): quick controls, settings, input, host time, health, boot/sync log of one unit.
Every action is a scripts/ subprocess off the UI thread (unit lock, EDID serial check and test-unit guard stay in the
scripts); no I2C in here. dev.py wraps the debug link on/off around each call and finds bus + map itself."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QSlider, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import isostamp  # noqa: E402
import settings_table as T  # noqa: E402

PYTHON = "python3"
LOG = ROOT / "tmp" / "logs" / "osd_editor.log"
# Per-call limits = 3x the slowest unit-3 call measured 2026-11-18 (docs/osd-editor-spec.md section 7).
# Expiry: TERM (dev.py's finally switches the debug link off), kill after TERM_GRACE_S, log line + banner.
LIMIT_S = {"list": 20, "one": 4, "health": 13, "synclog": 4, "host_time": 5, "kvm": 10, "ddc": 5}
TERM_GRACE_S = 2                                         # debug-link swap is 0.5 s
REFRESH_S = 15                                           # live refresh: one "list" takes ~6.4 s, bus stays under half busy
NO_ANSWER_RE = re.compile(r"no bus with (?:that )?EDID serial|DDC communication failed|no monitors detected|not found")
SLOW_MS = 100                                            # sync log: a step slower than this is highlighted (#216)
SLOW_BRUSH = QBrush(QColor("#ff5050"))
INPUTS = ("D1", "D2", "D3")                              # scripts/kvm.py port names
VCP_VOLUME, VCP_MUTE, VCP_SAVER = "0x62", "0x8D", "0xEB"
# VCP 0xEB start / stop values; the registry row screensaver_now lists 0..4, 5 = flash warning
SAVER_NOW = (("Stop", 0), ("Selected", 1), ("Pac-Man", 2), ("Scope 2", 4), ("Flash warning", 5), ("Boot splash", 7), ("Asteroids", 8))
QUICK_ROWS = ("volume", "mute", "disp_rotate")           # registry rows reused as widgets in the Quick group
VCP_ROW = {"volume": VCP_VOLUME, "mute": VCP_MUTE}       # quick rows written through DDC/CI, the rest through the mailbox
VALUE_RE = re.compile(r"(?:^|\s)(\w+) = .* \(raw (-?\d+)\)\s*$")
VCP_GET_RE = re.compile(r"VCP\s+([0-9A-Fa-f]{2})\s+(C|SNC|CNC)\s+((?:x?[0-9A-Fa-f]+\s*){1,4})")   # dev.py ddc get (ddcutil --brief)
STEP_RE = re.compile(r"(?:^|\s)(\d{1,5}):(?!\d)")        # sync_log line: "<ms since episode start>:text"


def load_units() -> dict:
    return json.loads((ROOT / "scripts" / "devices.json").read_text())["units"]


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


class _Done(QObject):
    done = Signal(int, int, str, float)                  # job id, rc, output, seconds


class _Job(QRunnable):
    def __init__(self, backend, argv, limit, sig, jid):
        super().__init__()
        self.backend, self.argv, self.limit, self.sig, self.jid = backend, argv, limit, sig, jid

    def run(self):
        t0 = time.monotonic()
        try:
            rc, out = self.backend.run(self.argv, self.limit)
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


def sync_summary(rows: list[tuple[str, str, bool]]) -> str:
    """boot timing line: lines, last episode length (last '<ms>:' field), slowest step"""
    if not rows:
        return "no lines"
    steps = [(int(d[1:]), ln) for d, ln, _ in rows if d]
    last = STEP_RE.search(rows[-1][1])
    slow = max(steps, default=None)
    return (f"{len(rows)} lines, last episode {last.group(1) if last else '?'} ms, " +
            (f"slowest step +{slow[0]} ms" if slow else "no steps") + f", {sum(s for *_, s in rows)} over {SLOW_MS} ms")


class SettingRow(QWidget):
    """One registry row: widget + value label + Set (the page runs the call). `ro` rows are shown, never writable.
    A row the user touched (drag, pick) keeps its widget value on refresh until Set succeeds."""

    def __init__(self, r: dict, on_set):
        super().__init__()
        self.r, self.dirty = r, False
        self.read_only = "ro" in r["flags"]
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
            self.w.sliderMoved.connect(self._touched)
            self.w.actionTriggered.connect(self._touched)
            self.val = QLabel()
            self.val.setMinimumWidth(80)
        else:                                            # enum, bool (0/1 as combo too)
            self.w = QComboBox()
            self.w.addItems(r["options"] or ["off", "on"])
            self.w.activated.connect(self._touched)
            self.val = None
        lay.addWidget(self.w, 1)
        if self.val:
            lay.addWidget(self.val)
        self.cur = QLabel("-")
        self.cur.setMinimumWidth(130)
        lay.addWidget(self.cur)
        self.btn = QPushButton("Set")
        self.btn.clicked.connect(lambda: on_set(self))
        lay.addWidget(self.btn)
        self.w.setEnabled(not self.read_only)
        self.btn.setEnabled(not self.read_only)
        self._shown()

    def _touched(self, *_):
        self.dirty = True

    def _shown(self, *_):
        if self.val:
            self.val.setText(f"{self.w.value()} {dict(percent='%', ms='ms', s='s').get(self.r['unit'], '')}".strip())

    def raw(self) -> int:
        return self.w.value() if self.r["type"] == "int" else self.r["min"] + self.w.currentIndex()

    def label_of(self, v: int) -> str:
        opts = self.r["options"] or (["off", "on"] if self.r["type"] == "bool" else [])
        i = v - self.r["min"]
        return f" ({opts[i]})" if self.r["type"] != "int" and 0 <= i < len(opts) else ""

    def dragging(self) -> bool:
        return self.r["type"] == "int" and self.w.isSliderDown()

    def put(self, v: int):
        """value read from the unit; the widget follows unless the user is changing it"""
        self.cur.setText(f"unit: {v}{self.label_of(v)}")
        if self.dirty or self.dragging():
            return
        self.w.blockSignals(True)
        if self.r["type"] == "int":
            self.w.setValue(v)
        else:
            self.w.setCurrentIndex(max(0, min(v - self.r["min"], self.w.count() - 1)))
        self.w.blockSignals(False)
        self._shown()

    def set_ok(self, v: int):
        self.dirty = False
        self.cur.setText(f"unit: {v}{self.label_of(v)}")


def row_of(name: str) -> dict:
    return next(r for r in T.ROWS if r["name"] == name)


class MonitorPage(QWidget):
    def __init__(self, backend=None, log_path: Path = LOG):
        super().__init__()
        self.backend, self.log_path = backend or SubprocessBackend(), log_path
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)                   # one script at a time: they share the unit's bus
        self.units = load_units()
        self.rows: dict[str, SettingRow] = {}
        self.quick: dict[str, SettingRow] = {}
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
        self.banner = QLabel()                           # unit does not answer / call timed out
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("color: #ff5050; font-weight: bold;")
        self.banner.hide()
        lay.addWidget(self.banner)
        lay.addWidget(self._quick_panel())
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._settings_panel())
        split.addWidget(self._side_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_S * 1000)
        self.timer.timeout.connect(self.refresh_tick)
        self.unit.currentIndexChanged.connect(self.unit_changed)
        self.unit.setCurrentIndex(max(0, next((i for i, (n, u) in enumerate(self.units.items()) if u.get("test")), 0)))
        self.unit_changed()

    # --- layout
    def _btn(self, text, fn) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda: fn())
        self.buttons.append(b)
        return b

    def _quick_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        head = QHBoxLayout()
        head.addWidget(QLabel("<b>Quick</b>"))
        self.saver = QComboBox()
        for label, v in SAVER_NOW:
            self.saver.addItem(label, v)
        head.addWidget(QLabel("screensaver now (VCP 0xEB)"))
        head.addWidget(self.saver)
        head.addWidget(self._btn("Start", self.saver_start))
        head.addWidget(self._btn("Stop", self.saver_stop))
        head.addStretch()
        head.addWidget(self._btn("Read quick values", self.quick_get))
        lay.addLayout(head)
        for name in QUICK_ROWS:
            sr = SettingRow(row_of(name), self.set_row)
            self.quick[name] = sr
            lay.addWidget(sr)
        return f

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
        self.refresh = QCheckBox(f"live refresh ({REFRESH_S} s)")
        self.refresh.toggled.connect(self.refresh_toggled)
        bar.addWidget(self.refresh)
        bar.addWidget(self._btn("Get all", self.get_all))
        bar.addWidget(self._btn("Save", self.save))
        lay.addLayout(bar)
        inner = QWidget()
        il = QVBoxLayout(inner)
        group = None
        self.headers: list[tuple[QLabel, list]] = []
        for r in sorted(T.ROWS, key=lambda r: (r["page"], r["index"])):
            if r["type"] not in ("int", "enum", "bool"):
                continue
            if (r["page"], r["group"]) != group:
                group = (r["page"], r["group"])
                h = QLabel(f"<b>{r['group']}</b>  (page {r['page']})")
                il.addWidget(h)
                self.headers.append((h, []))
            sr = SettingRow(r, self.set_row)
            self.rows[r["name"]] = sr
            self.headers[-1][1].append(sr)
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
        self.whole = QCheckBox("whole ring")
        self.whole.setChecked(True)
        sb.addWidget(self.whole)
        sb.addWidget(self._btn("Read sync log", self.sync_log))
        lay.addLayout(sb)
        self.sync_info = QLabel("")
        lay.addWidget(self.sync_info)
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
        for sr in [*self.rows.values(), *self.quick.values()]:
            sr.btn.setEnabled(w and not sr.read_only)
            sr.dirty = False
        self.inp.setEnabled(w)
        self.saver.setEnabled(w)
        self.banner.hide()
        if not w:
            self.refresh.setChecked(False)
        self.refresh.setEnabled(w)
        self.state.setText("test unit: writable" if w else "working screen: read-only, controls greyed")
        self.state.setStyleSheet("" if w else "color: #ff5050;")
        self.say(f"unit {self.n()} selected ({'test, writable' if w else 'read-only'})")

    def filter_rows(self, hide: bool):
        for sr in self.rows.values():
            sr.setVisible(not (hide and "inert" in sr.r["flags"]))
        for h, members in self.headers:
            h.setVisible(any(not (hide and "inert" in m.r["flags"]) for m in members))

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
    def run(self, label: str, argv: list, done, limit: str = "one"):
        if not self.writable():                          # same guard as the disabled buttons; dev.py refuses it too
            self.say(f"unit {self.n()} {label}: refused, read-only unit")
            return
        argv = [str(a) for a in argv]
        jid = self.next_id = self.next_id + 1
        self.jobs[jid] = (label, done, self.n(), LIMIT_S[limit])
        self.say(f"unit {self.n()} {label}: started (limit {LIMIT_S[limit]} s)")
        self.pool.start(_Job(self.backend, argv, LIMIT_S[limit], self.sig, jid))

    def _finish(self, jid, rc, out, secs):
        label, done, unit, limit = self.jobs.pop(jid)
        self.out.setPlainText(out.rstrip())
        extra = done(rc, out) if done else ""
        last = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip()), "no output")
        if rc == 0:
            verdict = "ok"
            if unit == self.n():
                self.banner.hide()
        elif rc == 124:
            verdict = f"TIMEOUT limit {limit} s, elapsed {secs:.1f} s"
            self.show_banner(f"unit {unit}: {label} did not finish in {limit} s and was stopped (unit busy, flashing or off?)")
        elif NO_ANSWER_RE.search(out):
            verdict = f"NO ANSWER rc {rc}"
            self.show_banner(f"unit {unit} does not answer: {last}")
        else:
            verdict = f"FAILED rc {rc}"
            self.show_banner(f"unit {unit}: {label} failed (rc {rc}): {last}")
        self.say(f"unit {unit} {label}: {verdict}{extra} ({secs:.1f} s)")

    def show_banner(self, text: str):
        self.banner.setText(text)
        self.banner.show()

    def wait_idle(self):
        self.pool.waitForDone()

    def dev(self, *args):
        return [PYTHON, ROOT / "dev.py", *args, "--unit", self.n()]

    # --- actions
    def get_all(self):
        self.run("settings get all", self.dev("settings", "list"), self._got, "list")

    def refresh_toggled(self, on: bool):
        self.timer.start() if on else self.timer.stop()
        self.say(f"live refresh {'on' if on else 'off'}")

    def refresh_tick(self):
        if not self.jobs:                                # never queue behind a running call
            self.get_all()

    def _got(self, rc, out) -> str:
        k = 0
        for ln in out.splitlines():
            m = VALUE_RE.search(ln)
            if m:
                for d in (self.rows, self.quick):
                    if m.group(1) in d:
                        d[m.group(1)].put(int(m.group(2)))
                k += m.group(1) in self.rows
        return f", {k} rows"

    def set_row(self, sr: SettingRow):
        v, name = sr.raw(), sr.r["name"]
        peers = [d[name] for d in (self.rows, self.quick) if name in d]

        def ok(rc, out):
            if rc != 0:
                return ", unit kept its value"
            for p in peers:
                p.set_ok(v)
                p.w.blockSignals(True)
                (p.w.setValue(v) if p.r["type"] == "int" else p.w.setCurrentIndex(v - p.r["min"]))
                p.w.blockSignals(False)
                p._shown()
            return ""

        if name in VCP_ROW and sr in self.quick.values():       # volume / mute: DDC/CI like a host would
            vv = sr.r["option_vcp"][v - sr.r["min"]] if sr.r["option_vcp"] else v
            self.run(f"set {name} = {v} (VCP {VCP_ROW[name]} = {vv})", self.dev("ddc", "set", VCP_ROW[name], vv), ok, "ddc")
        else:
            self.run(f"set {name} = {v}", self.dev("settings", "set", name, v), ok)

    def saver_start(self):
        self._saver(self.saver.currentData(), self.saver.currentText())

    def saver_stop(self):
        self._saver(0, "Stop")

    def _saver(self, v: int, label: str):
        self.run(f"screensaver now = {label} (VCP {VCP_SAVER} = {v})", self.dev("ddc", "set", VCP_SAVER, v), None, "ddc")

    def quick_get(self):
        for name, code in VCP_ROW.items():
            self.run(f"get {name} (VCP {code})", self.dev("ddc", "get", code), lambda rc, out, n=name: self._vcp_got(n, out), "ddc")
        for name in ("screensaver_now", "disp_rotate"):
            self.run(f"get {name}", self.dev("settings", "get", name), self._got)

    def _vcp_got(self, rc, out) -> str:
        m = VCP_GET_RE.search(out)
        if not m:
            return ", reply not understood"
        name = next(n for n, c in VCP_ROW.items() if c.lower() == "0x" + m.group(1).lower())
        f = m.group(3).split()
        hx = [int(x.lstrip("x"), 16) for x in f]
        raw = {"C": lambda: int(f[0]), "SNC": lambda: hx[0], "CNC": lambda: hx[2] << 8 | hx[3] if len(hx) == 4 else -1}[m.group(2)]()
        r = self.quick[name].r
        if r["option_vcp"]:
            if raw not in r["option_vcp"]:
                return f", value {raw} not in the registry options"
            raw = r["min"] + r["option_vcp"].index(raw)
        self.quick[name].put(raw)
        if name in self.rows:
            self.rows[name].put(raw)
        return f", {name} = {raw}"

    def save(self):
        self.run("settings save", self.dev("settings", "save"), None)

    def input_select(self):
        p = self.inp.currentText()
        self.run(f"input select {p}", [PYTHON, ROOT / "scripts" / "kvm.py", p, "--units", self.n()], None, "kvm")

    def host_time(self):
        self.run("host time send now", [PYTHON, ROOT / "scripts" / "host_time.py", "--unit", self.n(), "--once"], None, "host_time")

    def health(self):
        self.run("health", self.dev("health"), lambda rc, out: ", " + next(
            (ln.strip() for ln in reversed(out.splitlines()) if "PASS" in ln or "FAIL" in ln), "no verdict line"), "health")

    def sync_log(self):
        self.run("sync log", self.dev("synclog", *(["--whole"] if self.whole.isChecked() else [])), self._synced, "synclog")

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
        self.sync_info.setText(sync_summary(rows))
        return f", {sync_summary(rows)}"
