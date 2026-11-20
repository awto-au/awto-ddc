"""Monitor page (awto-ddc#217, docs/monitor-gui.md): unit strip, page tree, quick strip, search, per-unit job queues.
Every action is a scripts/ subprocess off the UI thread (unit lock, EDID serial check and test-unit guard stay in the
scripts); no I2C in here. dev.py wraps the debug link on/off around each call and finds bus + map itself."""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from unit_jobs import ROOT, SubprocessBackend, UnitQueues

sys.path.insert(0, str(ROOT / "scripts"))
import isostamp  # noqa: E402
import settings_table as T  # noqa: E402

PYTHON = "python3"
LOG = ROOT / "tmp" / "logs" / "osd_editor.log"
# Per-call limits = 3x the slowest unit-3 call measured 2026-11-18 (docs/osd-editor-spec.md section 7).
# Expiry: TERM (dev.py's finally switches the debug link off), kill after TERM_GRACE_S, log line + banner.
LIMIT_S = {"list": 20, "one": 4, "health": 13, "synclog": 4, "host_time": 5, "kvm": 10, "ddc": 5}
REFRESH_S = 15                                           # live refresh and status probe pace: one "list" takes ~6.4 s
STALE_S = 60                                             # a unit view older than this is re-read when selected (Dan 2026-11-20)
NO_ANSWER_RE = re.compile(r"no bus with (?:that )?EDID serial|DDC communication failed|no monitors detected|not found")
SLOW_MS = 100                                            # sync log: a step slower than this is highlighted (#216)
SLOW_BRUSH = QBrush(QColor("#ff5050"))
INPUTS = ("D1", "D2", "D3")                              # scripts/kvm.py port names
VCP_VOLUME, VCP_MUTE, VCP_SAVER = "0x62", "0x8D", "0xEB"
PROBE_VCP = VCP_VOLUME                                   # status dot: cheapest read-only call, dev.py ddc get (EDID guard inside)
# VCP 0xEB start / stop values; the registry row screensaver_now lists 0..4, 5 = flash warning
SAVER_NOW = (("Stop", 0), ("Selected", 1), ("Pac-Man", 2), ("Scope 2", 4), ("Flash warning", 5), ("Boot splash", 7), ("Asteroids", 8))
QUICK_ROWS = ("volume", "mute", "brightness")            # registry rows reused as widgets in the Quick strip
VCP_ROW = {"volume": VCP_VOLUME, "mute": VCP_MUTE}       # quick rows written through DDC/CI, the rest through the mailbox
VALUE_RE = re.compile(r"(?:^|\s)(\w+) = .* \(raw (-?\d+)\)\s*$")
VCP_GET_RE = re.compile(r"VCP\s+([0-9A-Fa-f]{2})\s+(C|SNC|CNC)\s+((?:x?[0-9A-Fa-f]+\s*){1,4})")   # dev.py ddc get (ddcutil --brief)
STEP_RE = re.compile(r"(?:^|\s)(\d{1,5}):(?!\d)")        # sync_log line: "<ms since episode start>:text"
DOT = {"ok": "#3fb950", "busy": "#d29922", "down": "#ff5050", "unknown": "#808080"}
PAGE_ROLE = Qt.UserRole
ROW_ROLE = Qt.UserRole + 1
EDID_GLOB = "/sys/class/drm/*/edid"                      # kernel's copy of each connected monitor's EDID: no I2C from the GUI


def load_units() -> dict:
    return json.loads((ROOT / "scripts" / "devices.json").read_text())["units"]


def detect_serials() -> set[str]:
    """EDID text serials of the connected monitors, from the kernel's sysfs EDID copies"""
    import i2cbus
    out = set()
    for p in Path("/").glob(EDID_GLOB.lstrip("/")):
        try:
            s = i2cbus.parse_edid_serial(p.read_bytes()[:128])
        except OSError:
            continue
        if s:
            out.add(s)
    return out


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


def row_of(name: str) -> dict:
    return next(r for r in T.ROWS if r["name"] == name)


def row_matches(r: dict, q: str) -> bool:
    """search: name, label, id and VCP code (0x10, 10 or decimal) as substrings"""
    q = q.strip().lower()
    hay = [r["name"], r["label"].lower(), str(r["id"])]
    if r["vcp"] is not None:
        hay += [f"0x{r['vcp']:02x}", f"{r['vcp']:02x}", str(r["vcp"])]
    return not q or any(q in h.lower() for h in hay)


PAGES = {r["page"]: r["group"] for r in T.ROWS}           # registry: group == page name
PAGE_ROWS = {p: sorted((r for r in T.ROWS if r["page"] == p), key=lambda r: r["index"]) for p in sorted(PAGES)}


@dataclass
class UnitState:
    n: str
    info: dict
    detected: bool | None = None                         # None = scan not done
    status: str = "unknown"                              # ok / down / unknown (busy is derived from pending)
    values: dict = field(default_factory=dict)           # registry row name -> raw value last read or set
    dirty: dict = field(default_factory=dict)            # touched widget values not yet set (kept across a unit switch)
    last_read: float | None = None                       # monotonic time of the last full "settings list"
    node: str | None = None                              # selected tree node: "page:N" or "row:name"
    out: str = ""
    banner: str = ""
    pending: int = 0                                     # queued + running jobs (not probes)

    @property
    def writable(self) -> bool:
        return bool(self.info.get("test"))

    def dot(self) -> str:
        if not self.writable:
            return "unknown"
        if self.detected is False:
            return "down"
        return "busy" if self.pending else self.status


def dot_icon(colour: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(colour))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pm)


class SettingRow(QWidget):
    """One registry row: widget + value label + Set (the page runs the call). `ro` rows are shown, never writable.
    A row the user touched (drag, pick) keeps its widget value on refresh until Set succeeds."""

    def __init__(self, r: dict, on_set, compact: bool = False):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.r, self.dirty = r, False
        self.read_only = "ro" in r["flags"]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(r["label"])
        lab.setMinimumWidth(70 if compact else 150)
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
            self.val.setMinimumWidth(60 if compact else 80)
        else:                                            # enum, bool (0/1 as combo too)
            self.w = QComboBox()
            self.w.addItems(r["options"] or ["off", "on"])
            self.w.activated.connect(self._touched)
            self.val = None
        lay.addWidget(self.w, 1)
        if self.val:
            lay.addWidget(self.val)
        self.cur = QLabel("-")
        self.cur.setMinimumWidth(70 if compact else 130)
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

    def _move(self, v: int):
        self.w.blockSignals(True)
        if self.r["type"] == "int":
            self.w.setValue(v)
        else:
            self.w.setCurrentIndex(max(0, min(v - self.r["min"], self.w.count() - 1)))
        self.w.blockSignals(False)
        self._shown()

    def put(self, v: int):
        """value read from the unit; the widget follows unless the user is changing it"""
        self.cur.setText(f"unit: {v}{self.label_of(v)}")
        if not (self.dirty or self.dragging()):
            self._move(v)

    def load(self, v: int | None, pending: int | None):
        """show a unit's stored state (unit switch): last known value and a not-yet-set touched value, no read"""
        self.cur.setText("-" if v is None else f"unit: {v}{self.label_of(v)}")
        self.dirty = pending is not None
        self._move(pending if pending is not None else v if v is not None else self.r["default"])

    def set_ok(self, v: int):
        self.dirty = False
        self.cur.setText(f"unit: {v}{self.label_of(v)}")
        self._move(v)


class ActionRow(QWidget):
    """An action row of the registry: one Run button (the page asks before it runs)"""

    read_only, dirty = False, False

    def __init__(self, r: dict, on_set):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.r = r
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(r["label"])
        lab.setMinimumWidth(150)
        lab.setToolTip(f"{r['name']} (id {r['id']}) action\n{r['note']}")
        lay.addWidget(lab)
        lay.addStretch(1)
        self.btn = QPushButton("Run")
        self.btn.clicked.connect(lambda: on_set(self))
        lay.addWidget(self.btn)

    def raw(self) -> int:
        return 1

    def load(self, v, pending):
        pass

    def put(self, v):
        pass

    def set_ok(self, v):
        pass


class MonitorPage(QWidget):
    def __init__(self, backend=None, log_path: Path = LOG, settings: QSettings | None = None, detect=detect_serials):
        super().__init__()
        self.log_path, self.detect = log_path, detect
        self.settings = settings or QSettings("awto", "osd_editor")
        self.queues = UnitQueues(backend or SubprocessBackend(), self)
        self.queues.done.connect(self._finish, Qt.QueuedConnection)   # UI-thread slot, emitted from the worker
        self.units = load_units()
        self.states = {n: UnitState(n, u) for n, u in self.units.items()}
        self.cur = next(iter(self.units))
        self.rows: dict[str, SettingRow] = {}               # registry rows with a value widget (int / enum / bool)
        self.all_rows: dict[str, QWidget] = {}              # every registry row's form widget (action rows too)
        self.quick: dict[str, SettingRow] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.page_items: dict[int, QTreeWidgetItem] = {}
        self.page_scroll: dict[int, QScrollArea] = {}
        self.jobs: dict[int, tuple] = {}
        self.buttons: list[QPushButton] = []
        self.unit_btns: dict[str, QPushButton] = {}
        self.highlight: QWidget | None = None
        lay = QVBoxLayout(self)
        lay.addLayout(self._strip())
        self.banner = QLabel()                           # unit does not answer / call timed out
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("color: #ff5050; font-weight: bold;")
        self.banner.hide()
        lay.addWidget(self.banner)
        lay.addWidget(self._quick_panel())
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._tree_panel())
        split.addWidget(self._form_panel())
        split.addWidget(self._side_panel())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes([240, 620, 420])
        lay.addWidget(split, 1)
        self.timer = QTimer(self)                        # live refresh of the selected unit (checkbox)
        self.timer.setInterval(REFRESH_S * 1000)
        self.timer.timeout.connect(self.refresh_tick)
        self.probe_timer = QTimer(self)                  # unit scan + status dots while the page is visible
        self.probe_timer.setInterval(REFRESH_S * 1000)
        self.probe_timer.timeout.connect(self.probe_tick)
        self._hotkeys()
        last = str(self.settings.value("monitor/last_unit", ""))
        self.scan()
        self.select_unit(last if last in self.units else next((n for n, u in self.units.items() if u.get("test")), self.cur), read=False)

    # --- layout
    def _btn(self, text, fn) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda: fn())
        self.buttons.append(b)
        return b

    def _strip(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for i, (n, u) in enumerate(self.units.items(), 1):
            b = QPushButton()
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setMinimumHeight(44)
            b.setToolTip(f"hotkey {i}" if i < 10 else "")
            b.clicked.connect(lambda _=False, n=n: self.select_unit(n))
            self.unit_btns[n] = b
            row.addWidget(b)
            self._strip_text(n)
        row.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search name, label, id, VCP (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(280)
        self.search.textChanged.connect(self.apply_filters)
        self.search.returnPressed.connect(self.jump_first_match)
        row.addWidget(self.search)
        return row

    def _strip_text(self, n: str):
        st, b = self.states[n], self.unit_btns[n]
        i = list(self.units).index(n) + 1
        b.setText(f"{i}  unit {n}  {'' if st.writable else '(ro) '}\n{st.info['serial'][-4:]}  {st.info['input']}")
        b.setIcon(dot_icon(DOT[st.dot()]))
        why = {"ok": "answers", "busy": "job running", "down": "no answer / not detected", "unknown": "not probed"}[st.dot()]
        b.setToolTip(f"unit {n} {st.info['serial']}: {why}; hotkey {i}")

    def _quick_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("<b>Quick</b>"))
        for name in QUICK_ROWS:
            sr = SettingRow(row_of(name), self.set_row, compact=True)
            self.quick[name] = sr
            r1.addWidget(sr, 1)
        lay.addLayout(r1)
        r2 = QHBoxLayout()
        self.inp = QComboBox()
        self.inp.addItems(INPUTS)
        r2.addWidget(QLabel("input"))
        r2.addWidget(self.inp)
        r2.addWidget(self._btn("Input select", self.input_select))
        r2.addSpacing(20)
        self.saver = QComboBox()
        for label, v in SAVER_NOW:
            self.saver.addItem(label, v)
        r2.addWidget(QLabel("screensaver (VCP 0xEB)"))
        r2.addWidget(self.saver)
        r2.addWidget(self._btn("Start", self.saver_start))
        r2.addWidget(self._btn("Stop", self.saver_stop))
        r2.addStretch()
        r2.addWidget(self._btn("Read quick values", self.quick_get))
        lay.addLayout(r2)
        return f

    def _tree_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        for p, name in PAGES.items():
            pi = QTreeWidgetItem(self.tree, [f"{name} ({len(PAGE_ROWS[p])})"])
            pi.setData(0, PAGE_ROLE, p)
            self.page_items[p] = pi
            for r in PAGE_ROWS[p]:
                tag = "  [action]" if r["type"] == "action" else "  [risky]" if "risky" in r["flags"] else "  [ro]" if "ro" in r["flags"] else ""
                it = QTreeWidgetItem(pi, [r["label"] + tag])
                it.setData(0, ROW_ROLE, r["name"])
                it.setToolTip(0, f"{r['name']} (id {r['id']})")
                self.items[r["name"]] = it
        self.tree.currentItemChanged.connect(self._node_changed)
        lay.addWidget(self.tree, 1)
        self.live = QCheckBox("hide inert rows")
        self.live.toggled.connect(self.apply_filters)
        lay.addWidget(self.live)
        return f

    def _form_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        bar = QHBoxLayout()
        self.state = QLabel()
        bar.addWidget(self.state, 1)
        self.refresh = QCheckBox(f"live refresh ({REFRESH_S} s)")
        self.refresh.toggled.connect(self.refresh_toggled)
        bar.addWidget(self.refresh)
        bar.addWidget(self._btn("Get all", self.get_all))
        bar.addWidget(self._btn("Save", self.save))
        lay.addLayout(bar)
        self.stack = QStackedWidget()
        for p, name in PAGES.items():
            inner = QWidget()
            il = QVBoxLayout(inner)
            il.addWidget(QLabel(f"<b>{name}</b>  (page {p}, {len(PAGE_ROWS[p])} rows)"))
            for r in PAGE_ROWS[p]:
                if r["type"] == "action":
                    sr = ActionRow(r, self.set_row)
                else:
                    sr = SettingRow(r, self.set_row)
                    self.rows[r["name"]] = sr
                self.all_rows[r["name"]] = sr
                il.addWidget(sr)
            il.addStretch()
            sa = QScrollArea()
            sa.setWidget(inner)
            sa.setWidgetResizable(True)
            self.page_scroll[p] = sa
            self.stack.addWidget(sa)
        lay.addWidget(self.stack, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)
        return f

    def _side_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        r1 = QHBoxLayout()
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

    # --- hotkeys
    def _hotkeys(self):
        def key(seq, fn):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
            return sc

        self.shortcuts = []
        for i in range(1, 10):
            self.shortcuts.append(key(f"Ctrl+{i}", lambda i=i: self.select_index(i - 1)))
            self.shortcuts.append(key(str(i), lambda i=i: self.select_index(i - 1, plain=True)))
        self.shortcuts.append(key("Ctrl+Tab", self.next_unit))
        self.shortcuts.append(key("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())))

    def select_index(self, i: int, plain: bool = False):
        fw = QApplication.focusWidget()
        if plain and isinstance(fw, (QLineEdit, QAbstractSpinBox, QPlainTextEdit)):
            return                                       # a digit typed into a field is text
        if i < len(self.units):
            self.select_unit(list(self.units)[i])

    def next_unit(self):
        ns = list(self.units)
        self.select_unit(ns[(ns.index(self.cur) + 1) % len(ns)])

    # --- visibility: scan + probes only while the page is shown
    def showEvent(self, e):
        super().showEvent(e)
        self.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.probe_timer.stop()

    def start(self):
        self.probe_timer.start()
        self.probe_tick()
        self.maybe_read(self.cur)

    # --- state
    def n(self) -> str:
        return self.cur

    def writable(self, n: str | None = None) -> bool:
        return self.states[n or self.cur].writable

    def scan(self):
        """mark which units' monitors are connected; no known serial seen = no scan result, devices.json stands"""
        try:
            seen = self.detect()
        except Exception as e:                           # a failed scan leaves the list as devices.json gives it
            self.say(f"monitor scan failed: {e!r}")
            return
        known = any(st.info["serial"] in seen for st in self.states.values())
        for n, st in self.states.items():
            st.detected = (st.info["serial"] in seen) if known else None
            self._strip_text(n)

    def select_unit(self, n: str, read: bool = True):
        self._save_view()
        self.cur = n
        st = self.states[n]
        self.settings.setValue("monitor/last_unit", n)
        for k, b in self.unit_btns.items():
            b.setChecked(k == n)
        for name, sr in self.all_rows.items():
            sr.load(st.values.get(name), st.dirty.get(name))
        for name, sr in self.quick.items():
            sr.load(st.values.get(name), st.dirty.get(name))
        w = st.writable
        for b in self.buttons:
            b.setEnabled(w)
        for sr in [*self.rows.values(), *self.quick.values()]:
            sr.btn.setEnabled(w and not sr.read_only)
        for sr in self.all_rows.values():
            if isinstance(sr, ActionRow):
                sr.btn.setEnabled(w)
        self.inp.setEnabled(w)
        self.saver.setEnabled(w)
        if not w:
            self.refresh.setChecked(False)
        self.refresh.setEnabled(w)
        self.state.setText("test unit: writable" if w else "working screen: read-only, controls greyed")
        self.state.setStyleSheet("" if w else "color: #ff5050;")
        self.out.setPlainText(st.out)
        self.banner.setText(st.banner)
        self.banner.setVisible(bool(st.banner))
        node = st.node or str(self.settings.value(f"monitor/node/{n}", "") or "") or "page:0"
        self._select_node(node)
        self.say(f"unit {n} selected ({'test, writable' if w else 'read-only'})")
        if read:
            self.maybe_read(n)

    unit_changed = select_unit

    def _save_view(self):
        st = self.states[self.cur]
        st.dirty = {name: sr.raw() for name, sr in [*self.all_rows.items(), *self.quick.items()] if sr.dirty}

    def maybe_read(self, n: str):
        """Get all when this unit's view is stale; a fresh view is shown as it is"""
        st = self.states[n]
        stale = st.last_read is None or time.monotonic() - st.last_read > STALE_S
        if stale and st.writable and st.detected is not False and not st.pending:
            self.get_all(n)

    # --- tree, search
    def _select_node(self, node: str):
        kind, _, key = node.partition(":")
        it = self.page_items.get(int(key)) if kind == "page" and key.isdigit() else self.items.get(key) if kind == "row" else None
        self.tree.setCurrentItem(it or self.page_items[0])

    def _node_changed(self, it, _prev=None):
        if it is None:
            return
        name = it.data(0, ROW_ROLE)
        if self.highlight is not None:
            self.highlight.setStyleSheet("")
            self.highlight = None
        if name is None:
            p = it.data(0, PAGE_ROLE)
            self.stack.setCurrentIndex(p)
            self.detail.setText(f"page {PAGES[p]}: {len(PAGE_ROWS[p])} rows")
            node = f"page:{p}"
        else:
            r = row_of(name)
            self.stack.setCurrentIndex(r["page"])
            w = self.all_rows[name]
            w.setStyleSheet("background: #1e3a5f;")
            self.highlight = w
            self.page_scroll[r["page"]].ensureWidgetVisible(w)
            vcp = f"VCP 0x{r['vcp']:02X}" if r["vcp"] is not None else "no VCP code"
            rng = "" if r["type"] == "action" else f", {r['min']}..{r['max']} step {r['step']}, default {r['default']}"
            self.detail.setText(f"<b>{r['label']}</b> {r['name']} (id {r['id']}), {vcp}{rng}, flags: {','.join(r['flags']) or '-'}"
                                f"<br>{r['note']}")
            node = f"row:{name}"
        self.states[self.cur].node = node
        self.settings.setValue(f"monitor/node/{self.cur}", node)

    def apply_filters(self, *_):
        q, hide = self.search.text(), self.live.isChecked()

        def shown(r):
            return row_matches(r, q) and not (hide and "inert" in r["flags"])

        for p, pi in self.page_items.items():
            n = 0
            for r in PAGE_ROWS[p]:
                ok = shown(r)
                self.items[r["name"]].setHidden(not ok)
                self.all_rows[r["name"]].setVisible(ok)
                n += ok
            pi.setHidden(n == 0)
            total = len(PAGE_ROWS[p])
            pi.setText(0, f"{PAGES[p]} ({n}/{total})" if (q.strip() or hide) else f"{PAGES[p]} ({total})")
            if q.strip():
                pi.setExpanded(n > 0)

    def jump_first_match(self):
        for p, pi in self.page_items.items():
            for i in range(pi.childCount()):
                if not pi.child(i).isHidden():
                    self.tree.setCurrentItem(pi.child(i))
                    return

    def filter_rows(self, hide: bool):
        self.live.setChecked(hide)

    # --- log
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
    def run(self, label: str, argv: list, done, limit: str = "one", unit: str | None = None, probe: bool = False):
        n = unit or self.cur
        st = self.states[n]
        if not st.writable:                              # same guard as the disabled buttons; dev.py refuses it too
            self.say(f"unit {n} {label}: refused, read-only unit")
            return
        jid = self.queues.submit(n, argv, LIMIT_S[limit])
        self.jobs[jid] = (label, done, n, LIMIT_S[limit], probe)
        if not probe:
            st.pending += 1
            self._strip_text(n)
            self.say(f"unit {n} {label}: started (limit {LIMIT_S[limit]} s)")

    def _finish(self, jid, rc, out, secs):
        label, done, unit, limit, probe = self.jobs.pop(jid)
        st = self.states[unit]
        if probe:
            old = st.dot()
            st.status = "ok" if rc == 0 else "down"
            if st.dot() != old:
                self.say(f"unit {unit} status {old} -> {st.dot()}")
            self._strip_text(unit)
            return
        st.pending -= 1
        st.out = out.rstrip()
        if unit == self.cur:
            self.out.setPlainText(st.out)
        extra = done(rc, out) if done else ""
        last = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip()), "no output")
        st.banner = ""
        if rc == 0:
            verdict, st.status = "ok", "ok"
        elif rc == 124:
            verdict, st.status = f"TIMEOUT limit {limit} s, elapsed {secs:.1f} s", "down"
            st.banner = f"unit {unit}: {label} did not finish in {limit} s and was stopped (unit busy, flashing or off?)"
        elif NO_ANSWER_RE.search(out):
            verdict, st.status = f"NO ANSWER rc {rc}", "down"
            st.banner = f"unit {unit} does not answer: {last}"
        else:
            verdict = f"FAILED rc {rc}"
            st.banner = f"unit {unit}: {label} failed (rc {rc}): {last}"
        if unit == self.cur:
            self.banner.setText(st.banner)
            self.banner.setVisible(bool(st.banner))
        self._strip_text(unit)
        self.say(f"unit {unit} {label}: {verdict}{extra} ({secs:.1f} s)")

    def show_banner(self, text: str):
        self.banner.setText(text)
        self.banner.show()

    def wait_idle(self):
        self.queues.wait_idle()

    def busy(self, n: str | None = None) -> bool:
        return self.states[n or self.cur].pending > 0

    def dev(self, *args, unit: str | None = None):
        return [PYTHON, ROOT / "dev.py", *args, "--unit", unit or self.cur]

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Confirm", text) == QMessageBox.Yes

    # --- timers
    def probe_tick(self):
        """rescan the connected monitors; probe each idle, detected test unit (read-only) for its status dot"""
        self.scan()
        for n, st in self.states.items():
            if st.writable and st.detected is not False and not st.pending:
                self.run(f"probe VCP {PROBE_VCP}", self.dev("ddc", "get", PROBE_VCP, unit=n), None, "ddc", unit=n, probe=True)

    def refresh_toggled(self, on: bool):
        self.timer.start() if on else self.timer.stop()
        self.say(f"live refresh {'on' if on else 'off'}")

    def refresh_tick(self):
        if not self.busy():                              # never queue behind a running call
            self.get_all()

    # --- actions
    def get_all(self, unit: str | None = None):
        n = unit or self.cur
        self.run("settings get all", self.dev("settings", "list", unit=n), lambda rc, out: self._got(n, rc, out, full=True), "list", unit=n)

    def _put(self, n: str, name: str, v: int):
        self.states[n].values[name] = v
        if n == self.cur:
            for d in (self.rows, self.quick):
                if name in d:
                    d[name].put(v)

    def _got(self, n: str, rc, out, full: bool = False) -> str:
        k = 0
        for ln in out.splitlines():
            m = VALUE_RE.search(ln)
            if m and m.group(1) in {r["name"] for r in T.ROWS}:
                self._put(n, m.group(1), int(m.group(2)))
                k += 1
        if full and rc == 0:
            self.states[n].last_read = time.monotonic()
        return f", {k} rows"

    def set_row(self, sr):
        n, v, r = self.cur, sr.raw(), sr.r
        name = r["name"]
        if r["type"] == "action" or "risky" in r["flags"]:
            what = "run" if r["type"] == "action" else f"set {v} on"
            if not self.confirm(f"Unit {n}: {what} {r['label']} ({name})?" + ("\nNeeds a reboot." if "reboot" in r["flags"] else "")):
                self.say(f"unit {n} {name}: cancelled at the confirm dialog")
                return
        peers = [d[name] for d in (self.rows, self.quick) if name in d]

        def ok(rc, out):
            if rc != 0:
                return ", unit kept its value"
            self.states[n].values[name] = v
            self.states[n].dirty.pop(name, None)
            if n == self.cur:
                for p in peers:
                    p.set_ok(v)
            return ""

        if name in VCP_ROW and sr in self.quick.values():       # volume / mute: DDC/CI like a host would
            vv = r["option_vcp"][v - r["min"]] if r["option_vcp"] else v
            self.run(f"set {name} = {v} (VCP {VCP_ROW[name]} = {vv})", self.dev("ddc", "set", VCP_ROW[name], vv), ok, "ddc")
        else:
            self.run(f"{'run' if r['type'] == 'action' else 'set'} {name} = {v}", self.dev("settings", "set", name, v), ok)

    def saver_start(self):
        self._saver(self.saver.currentData(), self.saver.currentText())

    def saver_stop(self):
        self._saver(0, "Stop")

    def _saver(self, v: int, label: str):
        self.run(f"screensaver now = {label} (VCP {VCP_SAVER} = {v})", self.dev("ddc", "set", VCP_SAVER, v), None, "ddc")

    def quick_get(self):
        n = self.cur
        for name, code in VCP_ROW.items():
            self.run(f"get {name} (VCP {code})", self.dev("ddc", "get", code), lambda rc, out, name=name: self._vcp_got(n, out), "ddc")
        for name in ("screensaver_now", "brightness"):
            self.run(f"get {name}", self.dev("settings", "get", name), lambda rc, out: self._got(n, rc, out))

    def _vcp_got(self, n: str, out: str) -> str:
        m = VCP_GET_RE.search(out)
        if not m:
            return ", reply not understood"
        name = next(k for k, c in VCP_ROW.items() if c.lower() == "0x" + m.group(1).lower())
        f = m.group(3).split()
        hx = [int(x.lstrip("x"), 16) for x in f]
        raw = {"C": lambda: int(f[0]), "SNC": lambda: hx[0], "CNC": lambda: hx[2] << 8 | hx[3] if len(hx) == 4 else -1}[m.group(2)]()
        r = row_of(name)
        if r["option_vcp"]:
            if raw not in r["option_vcp"]:
                return f", value {raw} not in the registry options"
            raw = r["min"] + r["option_vcp"].index(raw)
        self._put(n, name, raw)
        return f", {name} = {raw}"

    def save(self):
        self.run("settings save", self.dev("settings", "save"), None)

    def input_select(self):
        p = self.inp.currentText()
        self.run(f"input select {p}", [PYTHON, ROOT / "scripts" / "kvm.py", p, "--units", self.cur], None, "kvm")

    def host_time(self):
        self.run("host time send now", [PYTHON, ROOT / "scripts" / "host_time.py", "--unit", self.cur, "--once"], None, "host_time")

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
