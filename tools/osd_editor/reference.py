"""Reference monitor pane (awto-ddc#390): live standard DDC/CI reads of a devices.json `reference` monitor (Philips 288E2).
- Bus, pacing and write checks: scripts/reference_mon.py (unit_ops.DdcSession underneath). One worker thread owns the bus.
- Writes: standard Set VCP 10 / 12 / 14 / 60 only, behind the "enable writes" toggle (off at start and whenever the pane hides)."""
from __future__ import annotations

import queue
import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from unit_jobs import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import isostamp
import reference_mon as R

LOG = ROOT / "tmp" / "logs" / "osd_editor.log"
COLS = ("code", "name", "value", "raw (mh ml ch cl)", "read at")


class Worker(QObject):
    """the bus owner: passes over every code while live, one-shot passes and writes from a queue"""
    row = Signal(int, str, str, str)                     # code, value text, raw bytes, read-at stamp
    passed = Signal(float, str)                          # pass seconds, error of the pass ("" = all read)
    said = Signal(str)

    def __init__(self, ddc: R.ReferenceDdc):
        super().__init__()
        self.ddc, self.q, self.live = ddc, queue.Queue(), False
        self.codes = (*R.STANDARD, *R.MANUFACTURER)
        self.thread = threading.Thread(target=self._loop, name="reference-ddc", daemon=True)
        self.thread.start()

    def set_live(self, on: bool):
        self.live = on
        self.q.put(("wake",))

    def read_now(self):
        self.q.put(("pass",))

    def write(self, code: int, value: int):
        self.q.put(("set", code, value))

    def stop(self):
        self.live = False
        self.q.put(("stop",))

    def _loop(self):
        while True:
            try:
                job = self.q.get(block=not self.live)
            except queue.Empty:
                job = ("pass",)
            if job[0] == "stop":
                break
            if job[0] == "set":
                self._set(job[1], job[2])
            elif job[0] == "pass" and not self._pass():
                break
        self.ddc.close()

    def _read(self, code: int) -> str:
        try:
            cur, mx = self.ddc.get(code)
            self.row.emit(code, R.decode(code, cur, mx), R.raw4(cur, mx), isostamp.now_ms())
            return ""
        except Exception as e:  # noqa: BLE001  OSError / ValueError / LookupError / NoHardware: shown in the row, the pass goes on
            if isinstance(e, ValueError) and "result 0x1 " in str(e):
                self.row.emit(code, "unsupported (reply result 1)", "", isostamp.now_ms())
                return ""                                # an answer, not a failure
            self.row.emit(code, f"error: {e}", "", isostamp.now_ms())
            return str(e)

    def _pass(self) -> bool:
        """False = a stop came in mid-pass"""
        t0, err = time.monotonic(), ""
        for code, _label in self.codes:
            while True:                                  # a write waits at most one code read
                try:
                    job = self.q.get_nowait()
                except queue.Empty:
                    break
                if job[0] == "stop":
                    return False
                if job[0] == "set":
                    self._set(job[1], job[2])
            e = self._read(code)
            err = e or err
            if e and self.ddc.session is None:
                break                                    # bus lookup / proof failed: one try per pass, not one per code
        self.passed.emit(time.monotonic() - t0, err)
        return True

    def _set(self, code: int, value: int):
        try:
            self.ddc.set(code, value)
        except Exception as e:  # noqa: BLE001  PermissionError (refused) / transfer errors: logged, nothing retried
            self.said.emit(f"set VCP {code:02X} = {value:#x}: refused / failed: {e}")
            return
        self.said.emit(f"set VCP {code:02X} = {value:#x} sent on bus {self.ddc.bus}; read-back follows")
        self._read(code)


class ReferencePane(QWidget):
    def __init__(self, name: str = "philips", ref: dict | None = None, ddc: R.ReferenceDdc | None = None, log_path=LOG):
        super().__init__()
        self.name, self.ref, self.log_path = name, ref or R.load()[name], log_path
        self.ddc = ddc or R.ReferenceDdc(self.ref)
        self.worker = Worker(self.ddc)
        self.worker.row.connect(self._row, Qt.QueuedConnection)
        self.worker.passed.connect(self._passed, Qt.QueuedConnection)
        self.worker.said.connect(self.say, Qt.QueuedConnection)
        self.rows = {code: i for i, (code, _l) in enumerate(self.worker.codes)}
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.title = QLabel(f"<b>{self.ref.get('model', name)}</b>  reference monitor, EDID serial {self.ref['serial']}  "
                            f"(standard DDC/CI only, >= {R.GAP_S * 1000:.0f} ms between transactions)")
        top.addWidget(self.title, 1)
        self.live = QCheckBox("live")
        self.live.setChecked(True)
        self.live.toggled.connect(self._live_toggled)
        top.addWidget(self.live)
        self.read_btn = QPushButton("Read now")
        self.read_btn.clicked.connect(self.worker.read_now)
        top.addWidget(self.read_btn)
        lay.addLayout(top)
        self.info = QLabel("not read yet")
        lay.addWidget(self.info)
        self.table = QTableWidget(len(self.rows), len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.horizontalHeader().setStretchLastSection(True)
        for code, label in self.worker.codes:
            i = self.rows[code]
            self.table.setItem(i, 0, QTableWidgetItem(f"0x{code:02X}"))
            self.table.setItem(i, 1, QTableWidgetItem(label or "(manufacturer, meaning unknown)"))
            for c in (2, 3, 4):
                self.table.setItem(i, c, QTableWidgetItem("-"))
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 280)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 160)
        lay.addWidget(self.table, 1)
        lay.addWidget(self._write_panel())
        self.out = QLabel("")
        self.out.setWordWrap(True)
        lay.addWidget(self.out)
        self.values: dict[int, tuple[str, str]] = {}

    def _write_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QHBoxLayout(f)
        self.writes = QCheckBox("enable writes (standard Set VCP 10 / 12 / 14 / 60 only)")
        self.writes.setStyleSheet("color: #ff5050;")
        self.writes.toggled.connect(self._writes_toggled)
        lay.addWidget(self.writes)
        self.w_widgets: dict[int, QWidget] = {}
        for code, label in ((0x10, "brightness"), (0x12, "contrast")):
            sb = QSpinBox()
            sb.setRange(0, 100)                           # the monitor's max replaces this after the first read
            self.w_widgets[code] = sb
            lay.addWidget(QLabel(label))
            lay.addWidget(sb)
        for code, label, names in ((0x14, "preset", R.PRESET), (0x60, "input", R.INPUT)):
            cb = QComboBox()
            for v, t in names.items():
                cb.addItem(f"{t} ({v:#04x})", v)
            self.w_widgets[code] = cb
            lay.addWidget(QLabel(label))
            lay.addWidget(cb)
        self.set_btns: dict[int, QPushButton] = {}
        for code in R.WRITE_CODES:
            b = QPushButton(f"Set {code:02X}")
            b.clicked.connect(lambda _=False, c=code: self.set_code(c))
            self.set_btns[code] = b
            lay.addWidget(b)
        lay.addStretch()
        self._writes_toggled(False)
        return f

    # --- worker results (UI thread)
    def _row(self, code: int, text: str, raw: str, at: str):
        i = self.rows[code]
        self.table.item(i, 2).setText(text)
        self.table.item(i, 3).setText(raw)
        self.table.item(i, 4).setText(at)
        if raw and code in self.values and self.values[code][1] != raw:
            self.log(f"VCP {code:02X} changed: {self.values[code][1]} -> {raw} ({text})")
        self.values[code] = (text, raw)
        mx = self.ddc.maxes.get(code)
        w = self.w_widgets.get(code)
        if w is None or not raw or self.writes.isChecked():
            return                                       # a value being edited is not overwritten by the live read
        cur = int("".join(raw.split()[2:]), 16)
        if isinstance(w, QSpinBox):
            w.setMaximum(mx)
            w.setValue(cur)
        elif (k := w.findData(cur & 0xFF)) >= 0:
            w.setCurrentIndex(k)

    def _passed(self, secs: float, err: str):
        self.info.setText(f"bus {self.ddc.bus if self.ddc.bus is not None else '-'}: {len(self.rows)} codes in {secs:.2f} s, "
                          f"last pass {isostamp.now_ms()}" + (f"; last error: {err}" if err else ""))

    # --- controls
    def _live_toggled(self, on: bool):
        if self.isVisible():
            self.worker.set_live(on)

    def _writes_toggled(self, on: bool):
        self.ddc.enable_writes(on)
        for w in (*self.w_widgets.values(), *self.set_btns.values()):
            w.setEnabled(on)
        if hasattr(self, "out"):
            self.log(f"writes {'ENABLED' if on else 'off'}")

    def set_code(self, code: int):
        w = self.w_widgets[code]
        v = w.value() if isinstance(w, QSpinBox) else w.currentData()
        if not self.writes.isChecked():
            self.say(f"set VCP {code:02X}: writes are off")
            return
        self.log(f"set VCP {code:02X} = {v:#x} queued")
        self.worker.write(code, v)

    def say(self, msg: str):
        self.out.setText(msg)
        self.log(msg)

    def log(self, msg: str):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(f"{isostamp.now_ms()} reference {self.name}: {msg}\n")
        except OSError:
            pass

    # --- visibility: bus traffic only while shown
    def showEvent(self, e):
        super().showEvent(e)
        self.worker.set_live(self.live.isChecked())
        if not self.live.isChecked():
            self.worker.read_now()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.worker.set_live(False)
        self.writes.setChecked(False)

    def shutdown(self):
        self.worker.stop()
