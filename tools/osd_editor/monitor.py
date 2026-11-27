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

from PySide6.QtCore import QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QFileDialog, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget,
                               QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from unit_jobs import ROOT, SubprocessBackend, UnitQueues

sys.path.insert(0, str(ROOT / "scripts"))
import flash_job  # noqa: E402
import unit_log  # noqa: E402
import isostamp  # noqa: E402
import unit_lock  # noqa: E402
import settings_table as T  # noqa: E402
import unit_status  # noqa: E402
import gui_client  # noqa: E402
from live_writer import LiveWriter  # noqa: E402

PYTHON = "python3"
LOG = ROOT / "tmp" / "logs" / "osd_editor.log"
# Per-call limits = 3x the slowest unit-3 call measured 2026-11-18 (docs/osd-editor-spec.md section 7).
# Expiry: TERM (dev.py's finally switches the debug link off), kill after TERM_GRACE_S, log line + banner.
# synclog is sized per request instead (gui_client.synclog_limit: entries x DDR rate x 1.25, awto-ddc#358); "note" keeps the old 4 s.
LIMIT_S = {"list": 20, "one": 4, "health": 13, "note": 4, "host_time": 5, "kvm": 10, "ddc": 5, "ddcmany": 10, "i2c": 5}
REFRESH_S = 15                                           # live refresh and status probe pace: one "list" takes ~6.4 s
STALE_S = 60                                             # a unit view older than this is re-read when selected (Dan 2026-11-20)
NO_ANSWER_RE = re.compile(r"no bus with (?:that )?EDID serial|DDC communication failed|no monitors detected")
TREE = f"{ROOT} @{gui_client.git_head(ROOT)}"              # the tree this app runs: in every job log line (awto-ddc#358)
SLOW_MS = 100                                            # sync log: a step slower than this is highlighted (#216)
SLOW_BRUSH = QBrush(QColor("#ff5050"))
INPUTS = ("D1", "D2", "D3")                              # scripts/kvm.py port names
VCP_VOLUME, VCP_MUTE, VCP_SAVER = "0x62", "0x8D", "0xEB"
PROBE_FAILS_DOWN = 2
STATUS_S = 2                                             # pause between status-line reads of the selected unit (a pass is ~0.5-1 s on the bus; 2 s = at most one pass in flight, 1-2 s asked in #277)
FLASH_POLL_S = 1                                         # flash progress poll: the log gains a line every few sectors (SAVE_EVERY), 1 s keeps the bar live
ROUTED = ("ddc", "settings", "synclog", "note", "kvm", "i2c", "flash")   # dev.py commands that are thin port clients: workers add --direct
PROBE_VCP = VCP_VOLUME                                   # status dot: cheapest read-only call, dev.py ddc get (EDID guard inside)
# VCP 0xEB start / stop values (registry row screensaver_now: 5 flash warning, 6 alert tone, 7 boot splash)
SAVER_NOW = (("Stop", 0), ("Flash warning", 5), ("Boot splash", 7))
QUICK_ROWS = ("volume", "mute", "brightness")            # registry rows reused as widgets in the Quick strip
VCP_ROW = {"volume": VCP_VOLUME, "mute": VCP_MUTE}       # quick rows written through DDC/CI, the rest through the mailbox
QUICK_VCP = ("volume", "mute", "brightness", "input", "screensaver_now")   # registry rows read by DDC/CI VCP code
VALUE_RE = re.compile(r"(?:^|\s)(\w+) = .* \(raw (-?\d+)\)\s*$")
VCP_GET_RE = re.compile(r"VCP\s+([0-9A-Fa-f]{2})\s+(C|SNC|CNC)\s+((?:x?[0-9A-Fa-f]+\s*){1,4})")   # dev.py ddc get (ddcutil --brief)
# sync_log row (scripts/sync_log.py with_delta / row_lines; docs/sync-log-design.md "Console time columns"): [abs index] [real time] delta:text.
# Real: " HH:MM:SS.mmm" host clock, "uHH:MM:SS.mmm" / "u-0:00:00.ddd" / "uhhhh:mm:ss.t" uptime. Delta: fmt_delta, 7 cells, blank = none.
LINE_STAMP = r"^(?:\d{4}-\d\d-\d\dT\S+ )?"                                  # dev.py / _log.py time prefix of a printed line
ROW_RE = re.compile(LINE_STAMP + r"\s*(?:(?P<abs>\d+) )?(?P<real>[ u](?:-0|\s*\d+):\d\d:\d\d\.\d{1,3})? ?"
                    r"(?P<delta>[+-][ \d]{3} ms|[+-][ \d]\d\.\d s|[+-][ \d]{3}\d [sh]| {7}):(?P<text>.*)$")
HOST_STAMP_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d)(~?) +")   # sync_log.stamp (decoder without the real column)
RAW_TAIL_RE = re.compile(r"\s+(\[fw [^\]]*\])$")                          # row_lines: raw times last
BOOT_RE = re.compile(LINE_STAMP + r"\s*--- boot (\d+)")                                   # --dram: boot counter separator
WRAP_TEXT = "relative time reset: counter wrap"                               # sync_log.WRAP_TEXT
START_BRUSH, START_BG = QBrush(QColor("#ffffff")), QBrush(QColor("#8b1a1a"))  # episode start / wrap rows: the console's red rule
DOT = {"ok": "#3fb950", "busy": "#d29922", "down": "#ff5050", "unknown": "#808080", "flash": "#a371f7"}
PAGE_ROLE = Qt.UserRole
ROW_ROLE = Qt.UserRole + 1
EDID_GLOB = "/sys/class/drm/*/edid"                      # kernel's copy of each connected monitor's EDID: no I2C from the GUI
ADVANCED_PAGES = ("debug", "service")                    # hidden unless "show advanced" (QSettings monitor/advanced)
INPUT_VCP = "0x60"
BACKLIGHT_ROWS = ("brightness",)                         # registry label "Backlight", VCP 0x10, apply backlight (black_level is the digital "Brightness")
BL_MIN = 5                                               # a dragged / stepped backlight never goes below this %: 0 is a black screen (unit 2 was blacked 2026-11-20)
BL_LOW = 10                                              # a backlight set below this % shows "Restore previous backlight"
BL_RESTORE_MS = 10_000                                   # how long that button stays: long enough to notice a dark screen and reach for it
BL_ZERO_ASK = "Backlight 0 % = black screen. Set?"


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


def probe_policy(info: dict) -> str:
    """"light" = a unit on DP AUX (connector card*-DP-*): the dot comes from the sysfs scan, no periodic DDC/CI traffic (#unit2-blank);
    "ddc" = HDMI / DVI: a read-only VCP 0x62 get on the unit's own bus"""
    return "light" if "-DP-" in str(info.get("connector", "")) else "ddc"


def flash_state(serial: str) -> str:
    """"owner tool" while a live flash holds the unit lock (flashing keeps its own ISP path; the GUI only shows it), else ''"""
    cur = unit_lock.read(serial)
    if not cur or "flash" not in cur.get("tool", "") or not unit_lock.alive(int(cur.get("pid", "0") or 0)):
        return ""
    return f"{cur.get('owner')} {cur.get('tool')}"


def delta_ms(d: str) -> int | None:
    """sync_log.fmt_delta text -> ms (None = blank)"""
    if not d.strip():
        return None
    v, unit = d[1:].split()
    ms = round(float(v) * {"ms": 1, "s": 1000, "h": 3_600_000}[unit])
    return -ms if d[0] == "-" else ms


def sync_rows(text: str) -> list[dict]:
    """rows of a dev.py synclog output, the decoder's own columns (never recomputed here):
    {real, delta, ms, text, raw, slow, start, wrap, boot}; boot = a `--- boot N` separator row"""
    rows = []
    for ln in text.splitlines():
        b = BOOT_RE.match(ln)
        if b:
            rows.append({"real": "", "delta": "", "ms": None, "text": f"boot {b.group(1)}", "raw": "", "slow": False, "start": False,
                         "wrap": False, "boot": int(b.group(1))})
            continue
        m = ROW_RE.match(ln)
        if not m:
            continue
        body, raw = m.group("text").rstrip(), ""
        if (t := RAW_TAIL_RE.search(body)):
            body, raw = body[:t.start()], t.group(1)
        start = body.startswith("-- ") and body.endswith(" --") or body.endswith(" ---")
        if start:
            body = body[3:].rstrip("-").rstrip()
        real = (m.group("real") or "").strip()
        if (h := HOST_STAMP_RE.match(body)):
            real, body = h.group(1)[11:23] + h.group(2), body[h.end():]
        body = body.strip()
        wrap = body == WRAP_TEXT
        d = delta_ms(m.group("delta"))
        rows.append({"real": real, "delta": m.group("delta").strip(), "ms": d, "text": body, "raw": raw, "slow": d is not None and d > SLOW_MS,
                     "start": start and not wrap, "wrap": wrap, "boot": None})
    return rows


def sync_summary(rows: list[dict]) -> str:
    """timing line: rows, episode starts, wrap rows, the slowest step, rows over SLOW_MS"""
    if not rows:
        return "no lines"
    steps = [r for r in rows if r["ms"] is not None and not r["start"] and not r["boot"]]
    slow = max(steps, key=lambda r: r["ms"], default=None)
    return (f"{len(rows)} rows, {sum(r['start'] for r in rows)} episode starts, {sum(r['wrap'] for r in rows)} wrap rows, "
            + (f"slowest step {slow['delta']}" if slow else "no steps") + f", {sum(r['slow'] for r in rows)} over {SLOW_MS} ms")


REASON_RE = re.compile(r"missing|not found|no bus|failed|expired|refus|not booted")
ERROR_RE = re.compile(r"\bERROR\b|Traceback")


def reason_line(out: str) -> str:
    """banner text: the line that says why (mailbox missing, map not found, ...), else an ERROR line, else the last line"""
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    for rx in (REASON_RE, ERROR_RE):
        hit = next((ln for ln in reversed(lines) if rx.search(ln)), None)
        if hit:
            return hit
    return lines[-1] if lines else "no output"


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
    last_read_iso: str = ""                              # wall time of the last successful read of any kind (strip tooltip)
    probe_fails: int = 0                                 # consecutive failed probes: one miss is an EDID read glitch (#76), two = down
    unknown: bool = False                                # monitor seen by EDID, not in devices.json: shown, never touched
    node: str | None = None                              # selected tree node: "page:N" or "row:name"
    out: str = ""
    banner: str = ""
    pending: int = 0                                     # queued + running jobs (not probes)
    track: object = None                                 # FlashTrack of this unit's latest flash job
    shown_dot: str = ""                                  # last dot sent to the event stream
    sline: dict = field(default_factory=dict)            # last status-line pass (unit_ops.status), {} = none yet
    sline_busy: bool = False                             # a status pass is queued or running: never a second one

    @property
    def flash(self) -> str:
        """"owner tool" while a flash runs on this unit (jobs refused), else "". Derived on every read from the unit lock and the
        job file + wrapper pid of the tracked job: no cached belief (a stale one blocked quit, #276 follow-up)"""
        held = flash_state(self.info["serial"])
        if held:
            return held
        t = self.track
        return f"gui-flash-{self.info['serial']}-{t.job['id']} flash" if t is not None and t.live(self.info["serial"])[0] else ""

    @property
    def writable(self) -> bool:
        return bool(self.info.get("test")) and not self.unknown

    def flash_pct(self) -> str:
        t = self.track
        return f"FLASHING {t.progress.percent():.0f} %" if t is not None and t.progress.rc is None else "FLASHING" if self.flash else ""

    def dot(self) -> str:
        if self.unknown:
            return "unknown"
        if not self.writable:
            return "unknown"
        if self.flash:
            return "flash"
        if self.detected is False:
            return "down"
        return "busy" if self.pending else self.status


class FlashTrack:
    """one flash job as the GUI follows it: parsed progress, log read offset, the job file's identity"""

    def __init__(self, job: dict):
        self.job, self.offset, self.rest = job, 0, ""
        self.progress = flash_job.Progress(job.get("started_mono_wall", time.time()))
        self.sent = None                                  # last snapshot sent to the event stream (without clock fields)
        self.finished_sent = False

    def live(self, serial: str) -> tuple[bool, str]:
        """(still flashing, why): not finished here, and the job file still holds THIS job without rc and with its wrapper alive"""
        if self.progress.rc is not None:
            return False, "finished"
        job = flash_job.load(serial)
        if job is None:
            return False, "no job file on disk"
        if job.get("id") != self.job["id"]:
            return False, f"job file now holds job {job.get('id')}"
        if "rc" in job:
            return False, f"job file has rc {job['rc']}"
        pid = int(job.get("pid") or 0)
        if not flash_job.wrapper_alive(pid):
            return False, f"wrapper pid {pid} is not alive"
        return True, f"job {job['id']} pid {pid} alive, age {time.time() - job.get('started_mono_wall', time.time()):.0f} s"


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


SEGMENT_MAX = 4                                          # enums up to this many options are one-click buttons, larger ones a combo box


class Choice(QWidget):
    """One-click chooser with all options visible: a switch (2 on/off options) or a segmented button row.
    Quacks like the combo box the row used before (currentIndex / setCurrentIndex / count); `picked` fires on a user click only."""

    picked = Signal(int)

    def __init__(self, options: list[str], switch: bool = False):
        super().__init__()
        self.options, self.switch, self.idx = list(options), switch, 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.btns: list[QPushButton] = []
        for i, o in enumerate(self.options if not switch else [self.options[0]]):
            b = QPushButton(o)
            b.setCheckable(True)
            b.setMinimumHeight(28)
            b.setStyleSheet("QPushButton:checked { background: #2a6fb0; color: white; font-weight: bold; }")
            b.clicked.connect(lambda _=False, i=i: self._click(i))
            self.btns.append(b)
            lay.addWidget(b)
        lay.addStretch(1)
        self.setCurrentIndex(0)

    def _click(self, i: int):
        self.setCurrentIndex(1 - self.idx if self.switch else i)
        self.picked.emit(self.idx)

    def count(self) -> int:
        return len(self.options)

    def currentIndex(self) -> int:
        return self.idx

    def currentText(self) -> str:
        return self.options[self.idx]

    def setCurrentIndex(self, i: int):
        self.idx = max(0, min(i, len(self.options) - 1))
        if self.switch:
            self.btns[0].setText(f"{self.options[self.idx]}")
            self.btns[0].setChecked(self.idx == 1)
        else:
            for k, b in enumerate(self.btns):
                b.setChecked(k == self.idx)

    def setCurrentText(self, t: str):
        self.setCurrentIndex(self.options.index(t))


def instant_options(r: dict) -> tuple[list[str], bool] | None:
    """(options, is_switch) for a row that is one click (bool, enum with 2..SEGMENT_MAX options), None = slider or combo"""
    if r["type"] == "bool":
        return ["off", "on"], True
    if r["type"] == "enum" and 2 <= len(r["options"]) <= SEGMENT_MAX:
        return r["options"], [o.lower() for o in r["options"]] == ["off", "on"]
    return None


class LiveSlider(QSlider):
    """slider that reports Esc (restore the pre-drag value) and swallows the rest of a cancelled drag until the mouse is released"""

    escape = Signal()

    def __init__(self, *a):
        super().__init__(*a)
        self.cancelling = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.escape.emit()
            return
        super().keyPressEvent(e)

    def cancel_drag(self):
        if self.isSliderDown():
            self.cancelling = True
            self.setSliderDown(False)

    def mouseMoveEvent(self, e):
        if not self.cancelling:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.cancelling = False


def live_row(r: dict) -> bool:
    """rows that write while they are moved: registry flag `live`, a slider or a many-option combo (one-click rows are instant already);
    risky / read-only rows never; a combo only when it is a stored setting (nv): power_mode and screensaver_now are commands (they sleep the
    unit / start a screensaver on pick) and keep Set"""
    return "live" in r["flags"] and not ({"risky", "ro"} & set(r["flags"])) and (r["type"] == "int" or (
        r["type"] == "enum" and "nv" in r["flags"] and instant_options(r) is None))


class SettingRow(QWidget):
    """One registry row: widget + value label + Set (the page runs the call). `ro` rows are shown, never writable.
    A row the user touched (drag, pick) keeps its widget value on refresh until Set succeeds."""

    def __init__(self, r: dict, on_set, compact: bool = False, live: LiveWriter | None = None):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.r, self.dirty, self.instant = r, False, False
        self.on_set = on_set
        self.live = live if live is not None and live_row(r) else None   # LiveWriter: this row writes while it moves (awto-ddc#277)
        self.is_bl = r["name"] in BACKLIGHT_ROWS
        self.zero = None
        self.base = None                                 # the value the unit has (last read / set): the pre-drag value
        self.ind = None
        self.read_only = "ro" in r["flags"]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(r["label"])
        lab.setMinimumWidth(70 if compact else 150)
        lab.setToolTip(f"{r['name']} (id {r['id']}) {','.join(r['flags'])}\n{r['note']}")
        lay.addWidget(lab)
        if r["type"] == "int":
            self.w = LiveSlider(Qt.Horizontal)
            self.w.setRange(r["min"], r["max"])
            self.w.setSingleStep(r["step"])
            self.w.valueChanged.connect(self._shown)
            self.w.sliderMoved.connect(self._touched)
            self.w.actionTriggered.connect(self._touched)
            if self.live:
                self.w.sliderPressed.connect(self._live_press)
                self.w.valueChanged.connect(self._live_changed)
                self.w.sliderReleased.connect(self._live_release)
                self.w.escape.connect(self._live_escape)
            self.val = QLabel()
            self.val.setMinimumWidth(60 if compact else 80)
        elif (ch := instant_options(r)) is not None:     # bool / small enum: one click = one write (Set button hidden)
            self.w = Choice(*ch)
            self.w.picked.connect(self._picked)
            self.val = None
            self.instant = True
        else:                                            # large enum: combo box + Set
            self.w = QComboBox()
            self.w.addItems(r["options"] or ["off", "on"])
            self.w.activated.connect(self._touched)
            if self.live:
                self.w.activated.connect(self._live_picked)
            self.val = None
        lay.addWidget(self.w, 1)
        if self.val:
            lay.addWidget(self.val)
        self.cur = QLabel("-")
        self.cur.setMinimumWidth(70 if compact else 130)
        lay.addWidget(self.cur)
        if self.live:
            self.ind = QLabel("")                        # "sending" while a write or the read-back is in flight
            self.ind.setStyleSheet("color: #d29922;")
            self.ind.setMinimumWidth(10 if compact else 60)
            lay.addWidget(self.ind)
        self.btn = QPushButton("Set")
        self.btn.clicked.connect(lambda: on_set(self))
        lay.addWidget(self.btn)
        self.btn.setVisible(not self.instant and not self.live)   # a live row has no Set: it is written as it moves
        if self.is_bl:                                   # 0 % is never one drag away: an explicit button, then a confirm dialog
            self.zero = QPushButton("0 %…")
            self.zero.setToolTip(f"{BL_ZERO_ASK} (asks first); the slider stops at {BL_MIN} %")
            self.zero.clicked.connect(self._zero)
            lay.addWidget(self.zero)
        self.w.setEnabled(not self.read_only)
        self.btn.setEnabled(not self.read_only)
        self._shown()

    def _touched(self, *_):
        self.dirty = True

    def _unit(self) -> str:
        return self.live.page.cur

    def _live_ok(self) -> bool:
        pg = self.live.page
        st = pg.states[pg.cur]
        if not st.writable or st.flash:
            pg.say(f"unit {pg.cur} live {self.r['name']}: refused, {'read-only unit' if not st.writable else 'unit is flashing'}")
            return False
        return True

    def _live_press(self):
        if self._live_ok():
            self.live.hold(self._unit(), self.r["name"], self.base)

    def _zero(self):
        self._move(0, base=False)
        self.dirty = True
        self.on_set(self)

    def _live_changed(self, v: int):
        if self.w.cancelling or not self._live_ok():
            return
        if self.is_bl and v < BL_MIN:                    # safety floor: clamp, say so
            v = BL_MIN
            self.w.blockSignals(True)
            self.w.setValue(v)
            self.w.blockSignals(False)
            self.val.setText(f"min {BL_MIN} %")
        self.dirty = True
        self.live.change(self._unit(), self.r["name"], v, self.base)

    def _live_release(self):
        if not self.w.cancelling:
            self.live.release(self._unit(), self.r["name"], self.w.value())

    def _live_escape(self):
        n, name = self._unit(), self.r["name"]
        if self.live.busy(n, name):
            self.w.cancel_drag()
            self.live.cancel(n, name)
            if self.base is not None:
                self._move(self.base)

    def _live_picked(self, *_):
        if self._live_ok():
            self.live.begin(self._unit(), self.r["name"], self.base)
            self.live.change(self._unit(), self.r["name"], self.raw(), self.base)
            self.live.release(self._unit(), self.r["name"], self.raw())

    def set_sending(self, text: str):
        if self.ind is not None:
            self.ind.setText("●" if text and self.ind.minimumWidth() < 20 else text)

    def _picked(self, *_):
        self.dirty = True
        self.on_set(self)

    def set_writable(self, w: bool):
        """greyed on a read-only unit; the one-click widget itself is the control, so it follows"""
        on = w and not self.read_only
        self.btn.setEnabled(on)
        if self.instant:
            self.w.setEnabled(on)
        if self.zero is not None:
            self.zero.setEnabled(on)
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

    def _move(self, v: int, base: bool = True):
        if base:
            self.base = v
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

    def set_value(self, v: int):
        """what a click or drag does to the widget (control port): the value is touched, not yet set"""
        self.dirty = True
        self._move(v, base=False)


class ActionRow(QWidget):
    """An action row of the registry: one Run button (the page asks before it runs)"""

    read_only, dirty, instant = False, False, False

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

    def set_value(self, v):
        pass

    def set_writable(self, w: bool):
        self.btn.setEnabled(w)


class MonitorPage(QWidget):
    def __init__(self, backend=None, log_path: Path = LOG, settings: QSettings | None = None, detect=detect_serials):
        super().__init__()
        self.log_path, self.detect = log_path, detect
        self.settings = settings or QSettings("awto", "osd_editor")
        self.queues = UnitQueues(backend or SubprocessBackend(), self)
        self.log_hold: dict[str, bool] = {}              # unit -> a flash waits for the log view's read (log_view.LogView yields)
        self.log_view = None                             # set by the window (app.Window)
        self.queues.done.connect(self._finish, Qt.QueuedConnection)   # UI-thread slot, emitted from the worker
        self.live_jobs: dict[int, object] = {}              # job id -> callback(rc, out, secs) of an in-process live write / read-back
        self.live_writer = LiveWriter(self)                 # live sliders: coalesced writes while a control moves (awto-ddc#277)
        self.live_writer.state.connect(self._live_state)
        self.units = load_units()                        # devices.json only; self.states also holds unknown monitors
        self.states = {n: UnitState(n, u) for n, u in self.units.items()}
        self.advanced = str(self.settings.value("monitor/advanced", "false")).lower() == "true"
        self.cur = next(iter(self.units))
        self.rows: dict[str, SettingRow] = {}               # registry rows with a value widget (int / enum / bool)
        self.all_rows: dict[str, QWidget] = {}              # every registry row's form widget (action rows too)
        self.quick: dict[str, SettingRow] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.page_items: dict[int, QTreeWidgetItem] = {}
        self.page_scroll: dict[int, QScrollArea] = {}
        self.jobs: dict[int, tuple] = {}
        self.listeners: list = []                        # callables(event dict): control port event stream
        self.refused = ""                                # why the last run() was refused (the port reports it)
        self.buttons: list[QPushButton] = []
        self.unit_btns: dict[str, QPushButton] = {}
        self.highlight: QWidget | None = None
        lay = QVBoxLayout(self)
        self.strip_row = self._strip()
        lay.addLayout(self.strip_row)
        self.banner = QLabel()                           # unit does not answer / call timed out
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("color: #ff5050; font-weight: bold;")
        self.banner.hide()
        lay.addWidget(self.banner)
        lay.addWidget(self._flash_panel())
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
        self.status_label = QLabel("status: -")           # bottom status line of the selected unit (awto-ddc#277), read-only
        self.status_label.setObjectName("statusline")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setStyleSheet("font-family: monospace; padding: 3px 6px; background: #101820; color: #c8e6c8;")
        lay.addWidget(self.status_label)
        self.status_timer = QTimer(self)                 # single shot, re-armed when a pass ends: passes never overlap
        self.status_timer.setSingleShot(True)
        self.status_timer.setInterval(STATUS_S * 1000)
        self.status_timer.timeout.connect(self.status_tick)
        self.timer = QTimer(self)                        # live refresh of the selected unit (checkbox)
        self.timer.setInterval(REFRESH_S * 1000)
        self.timer.timeout.connect(self.refresh_tick)
        self.probe_timer = QTimer(self)                  # unit scan + status dots while the page is visible
        self.probe_timer.setInterval(REFRESH_S * 1000)
        self.probe_timer.timeout.connect(self.probe_tick)
        self.flash_cmd = default_flash_cmd                # (unit, args) -> argv of the detached flash worker; tests swap in a fake
        self.flash_timer = QTimer(self)                   # follows the detached flash jobs (progress panel, strip, events)
        self.flash_timer.setInterval(FLASH_POLL_S * 1000)
        self.flash_timer.timeout.connect(self.flash_tick)
        self.flash_timer.start()
        self._hotkeys()
        self.apply_filters()
        last = str(self.settings.value("monitor/last_unit", ""))
        self.scan()
        self.select_unit(last if last in self.units else next((n for n, u in self.units.items() if u.get("test")), self.cur), read=False)
        self.adopt_flash_jobs()

    # --- layout
    def _btn(self, text, fn) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda: fn())
        self.buttons.append(b)
        return b

    def _strip(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for n in self.states:
            self._add_unit_btn(n, row)
        row.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search name, label, id, VCP (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(280)
        self.search.textChanged.connect(self.apply_filters)
        self.search.returnPressed.connect(self.jump_first_match)
        row.addWidget(self.search)
        return row

    def _add_unit_btn(self, n: str, row: QHBoxLayout):
        b = QPushButton()
        b.setCheckable(True)
        b.setAutoExclusive(True)
        b.setMinimumHeight(44)
        b.clicked.connect(lambda _=False, n=n: self.select_unit(n))
        self.unit_btns[n] = b
        row.insertWidget(len(self.unit_btns) - 1, b)
        self._strip_text(n)

    def _strip_text(self, n: str):
        st, b = self.states[n], self.unit_btns[n]
        i = list(self.states).index(n) + 1
        if st.unknown:
            b.setText(f"{i}  unknown  (ro)\n{st.info['serial'][-6:]}")
        else:
            b.setText(f"{i}  unit {n}  {'' if st.writable else '(ro) '}\n{st.flash_pct() or st.info['serial'][-4:] + '  ' + st.info['input']}")
        b.setIcon(dot_icon(DOT[st.dot()]))
        if st.shown_dot != st.dot():
            st.shown_dot = st.dot()
            self.emit("status", unit=n, dot=st.dot(), pending=st.pending)
        why = {"ok": "answers", "busy": "job running", "down": "no answer / not detected", "unknown": "not probed",
               "flash": f"flashing ({st.flash}), jobs refused"}[st.dot()]
        if st.unknown:
            why = "monitor seen by EDID, not in devices.json: read-only, not probed"
        b.setToolTip(f"unit {n} {st.info['serial']}: {why}; hotkey {i}\n"
                     + (f"last read {st.last_read_iso}" if st.last_read_iso else "not read yet"))

    def _flash_panel(self) -> QWidget:
        f = self.flash_box = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        top = QHBoxLayout()
        self.flash_title = QLabel()
        top.addWidget(self.flash_title, 1)
        self.flash_bar = QProgressBar()
        self.flash_bar.setRange(0, 1000)
        top.addWidget(self.flash_bar, 2)
        lay.addLayout(top)
        self.flash_info = QLabel()
        lay.addWidget(self.flash_info)
        self.flash_log = QPlainTextEdit(readOnly=True)
        self.flash_log.setMaximumHeight(90)
        lay.addWidget(self.flash_log)
        f.hide()
        return f

    def _quick_panel(self) -> QWidget:
        f = QFrame()
        f.setObjectName("panel")
        lay = QVBoxLayout(f)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("<b>Quick</b>"))
        for name in QUICK_ROWS:
            sr = SettingRow(row_of(name), self.set_row, compact=True, live=self.live_writer)
            self.quick[name] = sr
            r1.addWidget(sr, 1)
        lay.addLayout(r1)
        self.bl_prev: dict[str, int] = {}                # unit -> last backlight >= BL_LOW (what Restore writes)
        self.restore_btn = QPushButton("Restore previous backlight")
        self.restore_btn.setStyleSheet("background: #b03030; color: white; font-weight: bold;")
        self.restore_btn.clicked.connect(self.bl_restore)
        self.restore_btn.hide()
        self.restore_timer = QTimer(self)
        self.restore_timer.setSingleShot(True)
        self.restore_timer.setInterval(BL_RESTORE_MS)
        self.restore_timer.timeout.connect(self.restore_btn.hide)
        r1.addWidget(self.restore_btn)
        r2 = QHBoxLayout()
        self.inp = Choice(list(INPUTS))                  # one click = kvm.py selects that input
        self.inp_touched = False
        self.inp.picked.connect(self._input_picked)
        r2.addWidget(QLabel("input"))
        r2.addWidget(self.inp)
        r2.addSpacing(20)
        self.saver = QComboBox()
        for label, v in SAVER_NOW:
            self.saver.addItem(label, v)
        r2.addWidget(QLabel("screensaver (VCP 0xEB)"))
        r2.addWidget(self.saver)
        r2.addWidget(self._btn("Start", self.saver_start))
        r2.addWidget(self._btn("Stop", self.saver_stop))
        r2.addStretch()
        self.now_state = QLabel("unit shows: -")
        r2.addWidget(self.now_state)
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
        self.adv = QCheckBox(f"show advanced ({', '.join(ADVANCED_PAGES)})")
        self.adv.setChecked(self.advanced)
        self.adv.toggled.connect(self.set_advanced)
        lay.addWidget(self.adv)
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
                    sr = SettingRow(r, self.set_row, live=self.live_writer)
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
        self.log_tabs = QTabWidget()
        lay.addWidget(self.log_tabs, 3)
        syncw = QWidget()
        sl = QVBoxLayout(syncw)
        sl.setContentsMargins(0, 0, 0, 0)
        sb = QHBoxLayout()
        sb.addWidget(QLabel("<b>boot / sync log</b>"))
        sb.addStretch()
        self.whole = QCheckBox("whole ring")
        self.whole.setChecked(True)
        sb.addWidget(self.whole)
        sb.addWidget(self._btn("Read sync log", self.sync_log))
        sl.addLayout(sb)
        self.sync_info = QLabel("")
        sl.addWidget(self.sync_info)
        self.sync = QTableWidget(0, 3)
        self.sync.setHorizontalHeaderLabels(["time", "+delta", "line"])
        self.sync.horizontalHeader().setStretchLastSection(False)
        self.sync.horizontalHeader().setSectionResizeMode(2, self.sync.horizontalHeader().ResizeMode.Stretch)
        self.sync.setColumnWidth(0, 100)
        self.sync.setColumnWidth(1, 64)
        self.sync.verticalHeader().hide()
        sl.addWidget(self.sync, 3)
        self.log_tabs.addTab(syncw, "Sync log")
        self.log_tabs.addTab(self._unit_log_tab(), "Unit log")
        lay.addWidget(QLabel("<b>last output</b>"))
        self.out = QPlainTextEdit(readOnly=True)
        self.out.setMaximumBlockCount(500)
        lay.addWidget(self.out, 1)
        return f

    # --- Unit log: the saved history of the unit's sync ring (scripts/unit_log.py), never wiped by a console open / close or a reset
    def _unit_log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        r = QHBoxLayout()
        self.ulog_search = QLineEdit()
        self.ulog_search.setPlaceholderText("search the saved log")
        self.ulog_search.textChanged.connect(lambda *_: self.unit_log_show())
        r.addWidget(self.ulog_search, 1)
        self.ulog_follow = QCheckBox(f"follow ({unit_log.INTERVAL_S} s)")
        self.ulog_follow.setToolTip("append the unit's ring to the saved log every poll while the unit is idle (not during a flash)")
        r.addWidget(self.ulog_follow)
        r.addWidget(self._btn("Read now", self.unit_log_read))
        r.addWidget(self._btn("Save as...", self.unit_log_save_as))
        lay.addLayout(r)
        self.ulog_info = QLabel("")
        lay.addWidget(self.ulog_info)
        self.ulog = QPlainTextEdit(readOnly=True)
        self.ulog.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.ulog, 1)
        self.ulog_timer = QTimer(self)
        self.ulog_timer.setInterval(unit_log.INTERVAL_S * 1000)
        self.ulog_timer.timeout.connect(self._unit_log_tick)
        self.ulog_follow.toggled.connect(lambda on: self.ulog_timer.start() if on else self.ulog_timer.stop())
        return w

    def unit_log_path(self, unit: str | None = None) -> Path:
        return unit_log.log_path(self.states[unit or self.cur].info["serial"])

    def unit_log_text(self, unit: str | None = None) -> str:
        try:
            return self.unit_log_path(unit).read_text(errors="replace")
        except OSError:
            return ""

    def unit_log_show(self, unit: str | None = None):
        q = self.ulog_search.text().lower()
        lines = self.unit_log_text(unit).splitlines()
        shown = [x for x in lines if q in x.lower()] if q else lines
        self.ulog.setPlainText("\n".join(shown))
        self.ulog.verticalScrollBar().setValue(self.ulog.verticalScrollBar().maximum())
        self.ulog_info.setText(f"{len(shown)} of {len(lines)} saved lines" + (f" matching '{q}'" if q else "") + f"  ({self.unit_log_path(unit)})")

    def unit_log_read(self, unit: str | None = None, after=None):
        n = unit or self.cur

        def done(rc, out, secs):
            snap = unit_log.parse_output(out) if rc == 0 else None
            if snap is not None:
                added = unit_log.Store(snap["serial"] or self.states[n].info["serial"]).ingest(snap)
                self.say(f"unit {n} unit log: {len(added)} new lines saved")
            else:
                self.say(f"unit {n} unit log: read failed (rc {rc}), nothing saved")
            if n == self.cur:
                self.unit_log_show(n)
            if after:
                after(rc, out, secs)
        return self.sync_log(n, whole=True, after=done, as_json=True)

    def _unit_log_tick(self):
        st = self.states.get(self.cur)
        if st is not None and st.writable and not st.flash and not st.pending:
            self.unit_log_read()

    def unit_log_save_as(self, path: str | None = None):
        dest = path or QFileDialog.getSaveFileName(self, "Save the unit log as", f"{self.states[self.cur].info['serial']}-sync.log")[0]
        if dest:
            Path(dest).write_text(self.unit_log_text())
            self.say(f"unit {self.cur} unit log saved as {dest}")
        return dest

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
        if i < len(self.states):
            self.select_unit(list(self.states)[i])

    def next_unit(self):
        ns = list(self.states)
        self.select_unit(ns[(ns.index(self.cur) + 1) % len(ns)])

    # --- visibility: scan + probes only while the page is shown
    def showEvent(self, e):
        super().showEvent(e)
        self.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.probe_timer.stop()
        self.status_timer.stop()

    def start(self):
        self.probe_timer.start()
        self.probe_tick()
        self.status_tick()
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
        known = any(st.info["serial"] in seen for n, st in self.states.items() if n in self.units)
        for n in self.units:
            st = self.states[n]
            st.detected = (st.info["serial"] in seen) if known else None
            self._strip_text(n)
        self._sync_unknown(seen)

    def _sync_unknown(self, seen: set[str]):
        """monitors seen by EDID that devices.json does not list: read-only 'unknown' units, removed when unplugged"""
        listed = {u["serial"] for u in self.units.values()}
        have = {st.info["serial"]: n for n, st in self.states.items() if st.unknown}
        for ser in sorted(seen - listed - set(have)):
            n = f"?{ser}"
            self.states[n] = UnitState(n, {"serial": ser, "input": "?"}, detected=True, unknown=True)
            self._add_unit_btn(n, self.strip_row)
            self.say(f"unknown monitor seen: EDID serial {ser}, not in devices.json (read-only)")
        for ser, n in have.items():
            if ser not in seen:
                if self.cur == n:
                    self.select_unit(next(iter(self.units)), read=False)
                b = self.unit_btns.pop(n)
                self.strip_row.removeWidget(b)
                b.deleteLater()
                del self.states[n]
                self.say(f"unknown monitor {ser} unplugged")
        for n in self.states:
            self._strip_text(n)

    def select_unit(self, n: str, read: bool = True):
        self._save_view()
        self.cur = n
        st = self.states[n]
        self.status_show(n)
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
            sr.set_writable(w)
        for sr in self.all_rows.values():
            if isinstance(sr, ActionRow):
                sr.btn.setEnabled(w)
        self.inp.setEnabled(w)
        self.saver.setEnabled(w)
        if not w:
            self.refresh.setChecked(False)
        self.refresh.setEnabled(w)
        self.state.setText("test unit: writable" if w else
                           "unknown monitor (not in devices.json): read-only, controls greyed" if st.unknown else
                           "working screen: read-only, controls greyed")
        self.state.setStyleSheet("" if w else "color: #ff5050;")
        self.out.setPlainText(st.out)
        self.inp_touched = False
        self._quick_state(n)
        self.banner.setText(st.banner)
        self.banner.setVisible(bool(st.banner))
        node = st.node or str(self.settings.value(f"monitor/node/{n}", "") or "") or "page:0"
        self._select_node(node)
        self.show_flash(n)
        self.say(f"unit {n} selected ({'test, writable' if w else 'read-only'})")
        self.emit("select", unit=n)
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
            self.quick_get(n)                            # DDC/CI reads first: they work on every image, Get all needs the mailbox
            self.get_all(n)

    # --- tree, search
    def _select_node(self, node: str):
        kind, _, key = node.partition(":")
        it = self.page_items.get(int(key)) if kind == "page" and key.isdigit() else self.items.get(key) if kind == "row" else None
        top = it if it is not None and it.parent() is None else it.parent() if it is not None else None
        self.tree.setCurrentItem(it if it is not None and not top.isHidden() else self.page_items[0])

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
            if PAGES[p] in ADVANCED_PAGES and not self.advanced:
                n = 0                                    # advanced pages are out of the tree, the form and the search
            pi.setHidden(n == 0)
            total = len(PAGE_ROWS[p])
            pi.setText(0, f"{PAGES[p]} ({n}/{total})" if (q.strip() or hide) else f"{PAGES[p]} ({total})")
            if q.strip():
                pi.setExpanded(n > 0)

    def set_advanced(self, on: bool):
        self.advanced = on
        self.settings.setValue("monitor/advanced", "true" if on else "false")
        self.apply_filters()
        it = self.tree.currentItem()
        top = it if it is not None and it.parent() is None else it.parent() if it is not None else None
        if top is not None and top.isHidden():           # the selected page just went away
            self.tree.setCurrentItem(self.page_items[0])

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
    def emit(self, kind: str, **kw):
        for f in list(self.listeners):
            f({"event": kind, **kw})

    def run(self, label: str, argv: list, done, limit: str | float = "one", unit: str | None = None, probe: bool = False, after=None,
            limit_why: str = "", stall_s: float | None = None):
        """queue a job on the unit's worker; returns the job id, or None when refused (reason in self.refused).
        limit: a LIMIT_S key or seconds (limit_why = its arithmetic, logged). after(rc, out, secs) runs on the UI thread."""
        n = unit or self.cur
        st = self.states[n]
        self.refused = ""
        if not st.writable:                              # same guard as the disabled buttons; dev.py refuses it too
            self.refused = f"unit {n} is read-only (not a test unit in devices.json)"
        elif st.flash:
            self.refused = f"unit {n} is flashing ({st.flash}): jobs refused until the unit lock is released"
        if self.refused:
            self.say(f"unit {n} {label}: refused, {self.refused}")
            return None
        lim = LIMIT_S[limit] if isinstance(limit, str) else float(limit)
        jid = self.queues.submit(n, argv, lim, stall_s)
        self.jobs[jid] = (label, done, n, lim, probe, after)
        if not probe:
            st.pending += 1
            self._strip_text(n)
            self.say(f"unit {n} {label}: started (limit {lim:g} s{': ' + limit_why if limit_why else ''}; tree {TREE})")
        return jid

    def bl_seen(self, n: str, v: int | None, before: int | None):
        """a backlight value was set on unit n: remember the last normal one; a low one offers Restore for BL_RESTORE_MS"""
        if v is None:
            return
        if v >= BL_LOW:
            self.bl_prev[n] = v
            return
        if before is not None and before >= BL_LOW:
            self.bl_prev[n] = before
        if n in self.bl_prev and n == self.cur:
            self.restore_btn.setText(f"Restore previous backlight ({self.bl_prev[n]} %)")
            self.restore_btn.show()
            self.restore_timer.start()

    def bl_restore(self):
        n = self.cur
        v = self.bl_prev.get(n)
        self.restore_btn.hide()
        if v is None:
            return
        sr = self.quick["brightness"]
        self.say(f"unit {n}: restore previous backlight {v} %")
        sr._move(v, base=False)
        sr.dirty = True
        self.live_writer.begin(n, "brightness", sr.base)
        self.live_writer.change(n, "brightness", v, sr.base)
        self.live_writer.release(n, "brightness", v)

    def live_call(self, label: str, fn, after, unit: str | None = None):
        """run fn() -> (rc, out) in-process on the unit's worker thread (persistent DDC/CI fd); after(rc, out, secs) on the UI thread.
        Same refusals as run(); one log line per call. Returns the job id, or None when refused (reason in self.refused)."""
        n = unit or self.cur
        st = self.states[n]
        self.refused = ""
        if not st.writable:
            self.refused = f"unit {n} is read-only (not a test unit in devices.json)"
        elif st.flash:
            self.refused = f"unit {n} is flashing ({st.flash}): jobs refused until the unit lock is released"
        if self.refused:
            self.say(f"unit {n} {label}: refused, {self.refused}")
            return None
        jid = self.queues.submit_fn(n, fn)

        def cb(rc, out, secs):
            self.say(f"unit {n} {label}: {'ok' if rc == 0 else 'FAILED ' + out.strip()} ({secs * 1000:.0f} ms, in-process)")
            after(rc, out, secs)
        self.live_jobs[jid] = cb
        return jid

    def _live_state(self, unit: str, name: str, text: str):
        if unit == self.cur:
            for d in (self.rows, self.quick):
                if name in d:
                    d[name].set_sending(text)

    def live_finished(self, res: dict):
        """a drag / keyboard run / combo pick ended: show what the unit reports, log one summary line, emit the event"""
        n, name = res["unit"], res["name"]
        st = self.states[n]
        peers = [d[name] for d in (self.rows, self.quick) if name in d]
        v = res["readback"] if res["readback"] is not None else res["to"]
        if name in BACKLIGHT_ROWS and not res["error"]:
            self.bl_seen(n, v, res["from"])
        what = f"{res['from']} -> {res['to']}{' (cancelled, pre-drag value restored)' if res['cancelled'] else ''}"
        stats = (f"{res['values']} value changes, {res['writes']} writes sent, {res['skipped']} values never sent, {res['saves']} saves, "
                 f"{res['duration_s']:.2f} s, median write {res['median_write_ms']} ms, floor {res['floor_ms']} ms")
        if res["error"]:
            st.banner = f"unit {n}: live {name} failed: {res['error']}"
            self.say(f"unit {n} live {name}: FAILED {res['error']} ({what}; {stats})")
            st.dirty.pop(name, None)
            if n == self.cur:
                self.banner.setText(st.banner)
                self.banner.setVisible(True)
                for p in peers:
                    p.load(st.values.get(name), None)
        else:
            st.banner = ""
            st.values[name] = v
            st.dirty.pop(name, None)
            st.last_read_iso = isostamp.now()
            if n == self.cur:
                self.banner.setVisible(False)
                for p in peers:
                    p.set_ok(v)
            self.say(f"unit {n} live {name}: drag {what}: {stats}, read back {res['readback']}{'' if res['verified'] else ' (differs)'}")
        self._strip_text(n)
        self.emit("live", **{k: res[k] for k in ("unit", "name", "from", "to", "values", "writes", "saves", "readback", "verified", "error")})

    def _finish(self, jid, rc, out, secs):
        cb = self.live_jobs.pop(jid, None)
        if cb is not None:                               # in-process live write / read-back: no job log line, no banner, no strip state
            return cb(rc, out, secs)
        label, done, unit, limit, probe, after = self.jobs.pop(jid)
        st = self.states[unit]
        if probe:
            old = st.dot()
            st.probe_fails = 0 if rc == 0 else st.probe_fails + 1
            st.status = "ok" if rc == 0 else "down" if st.probe_fails >= PROBE_FAILS_DOWN else st.status
            if rc == 0:
                self._vcp_got(unit, out)                 # the probe is a volume read: keep the quick value fresh
                st.last_read_iso = isostamp.now()
            if st.dot() != old:
                self.say(f"unit {unit} status {old} -> {st.dot()}")
            self._strip_text(unit)
            return
        st.pending -= 1
        st.out = out.rstrip()
        if unit == self.cur:
            self.out.setPlainText(st.out)
        extra = done(rc, out) if done else ""
        last = reason_line(out)
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
        self.say(f"unit {unit} {label}: {verdict}{extra} ({secs:.1f} s, tree {TREE})")
        self.emit("job", unit=unit, label=label, rc=rc, secs=round(secs, 3))
        if after:
            after(rc, out, secs)

    def show_banner(self, text: str):
        self.banner.setText(text)
        self.banner.show()

    def wait_idle(self):
        self.queues.wait_idle()

    def busy(self, n: str | None = None) -> bool:
        return self.states[n or self.cur].pending > 0

    def dev(self, *args, unit: str | None = None):
        """argv of a worker call: the routed dev.py commands are thin port clients, the app's workers run them --direct"""
        return [PYTHON, ROOT / "dev.py", *args, "--unit", unit or self.cur, *(["--direct"] if args and args[0] in ROUTED else [])]

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Confirm", text) == QMessageBox.Yes

    # --- timers
    def probe_tick(self):
        """rescan the connected monitors; probe each idle, detected test unit (read-only) for its status dot"""
        self.scan()
        for n, st in self.states.items():
            if st.writable and st.detected is not False and not st.pending and not st.flash:
                if probe_policy(st.info) == "light":
                    self._probe_light(n, st)
                    continue
                self.run(f"probe VCP {PROBE_VCP}", self.dev("ddc", "get", PROBE_VCP, unit=n), None, "ddc", unit=n, probe=True)

    def _probe_light(self, n: str, st: UnitState):
        """no DDC/CI: the scan (sysfs EDID present = cable and sink answered the kernel) is the whole probe"""
        old = st.dot()
        if st.detected:
            st.probe_fails, st.status = 0, "ok"
        if st.dot() != old:
            self.say(f"unit {n} status {old} -> {st.dot()} (light probe: sysfs scan, no DDC)")
        self._strip_text(n)

    # --- status line (awto-ddc#277): read-only passes for the selected unit only, through its queue
    def status_text(self, n: str) -> str:
        st = self.states[n]
        if st.unknown or not st.writable:
            return f"unit {n}: read-only unit, not read"
        if st.flash:
            return f"unit {n}: {st.flash_pct() or 'FLASHING'}, status reads paused"
        if st.detected is False:
            return f"unit {n}: monitor not detected"
        if probe_policy(st.info) == "light":
            return f"unit {n}: DP AUX link, no DDC/CI: status line not read"
        if not st.sline:
            return f"unit {n}: reading ..."
        s = st.sline
        tail = "".join(f"  [{k}: {s[k]}]" for k in ("ddc_err", "dbg_err") if s.get(k))
        return f"unit {n}  " + unit_status.format_line(s) + tail

    def status_show(self, n: str):
        if n == self.cur:
            self.status_label.setText(self.status_text(n))

    def status_tick(self):
        """one status pass for the selected unit unless it is flashing, busy with a job or a drag, or already being read"""
        self.status_timer.start()
        n, st = self.cur, self.states[self.cur]
        self.status_show(n)
        if (not st.writable or st.flash or st.detected is False or st.sline_busy or st.pending
                or probe_policy(st.info) == "light" or self.live_writer.any_busy(n)):
            return
        self.status_read(n)

    def status_read(self, n: str, after=None):
        """queue one status pass on unit n's worker; after(rc, st or None, secs) on the UI thread. Returns the job id or None (refused)"""
        u = self.states[n].info
        self.refused = ""
        if not self.states[n].writable:
            self.refused = f"unit {n} is read-only (not a test unit in devices.json)"
        elif self.states[n].flash:
            self.refused = f"unit {n} is flashing ({self.states[n].flash}): status reads paused"
        if self.refused:
            return None

        def done(rc, out, secs):
            st = self.states[n]
            st.sline_busy = False
            try:
                st.sline = json.loads(out) if rc == 0 else {"ddc_err": reason_line(out) or f"rc {rc}", "ddc": st.sline.get("ddc", {}), "tag": st.sline.get("tag", "")}
            except ValueError:
                st.sline = {"ddc_err": f"reply not understood: {out[:80]}"}
            if rc == 0:
                st.last_read_iso = isostamp.now()
            self.status_show(n)
            self.emit("sline", unit=n, line=unit_status.format_line(st.sline), secs=round(secs, 3))
            if after:
                after(rc, st.sline, secs)
        self.states[n].sline_busy = True
        jid = self.queues.submit_fn(n, lambda: self.queues.backend.status_read(u))
        self.live_jobs[jid] = done
        return jid

    def refresh_toggled(self, on: bool):
        self.timer.start() if on else self.timer.stop()
        self.say(f"live refresh {'on' if on else 'off'}")

    def refresh_tick(self):
        if not self.busy():                              # never queue behind a running call
            self.get_all()

    # --- actions
    def get_all(self, unit: str | None = None, after=None):
        n = unit or self.cur
        return self.run("settings get all", self.dev("settings", "list", unit=n), lambda rc, out: self._got(n, rc, out, full=True), "list",
                        unit=n, after=after)

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
        if rc == 0:
            self.states[n].last_read_iso = isostamp.now()
            if full:
                self.states[n].last_read = time.monotonic()
        return f", {k} rows"

    def set_row(self, sr, confirmed: bool | None = None, after=None, readback: bool | None = None) -> int | None:
        """write the widget's value on the current unit. confirmed None = ask (dialog), True / False = the port's answer
        (no dialog). readback None = what the row does itself (one-click rows read back); after(rc, out, secs) = job done."""
        n, v, r = self.cur, sr.raw(), sr.r
        name = r["name"]
        if r["type"] == "action" or "risky" in r["flags"]:
            what = "run" if r["type"] == "action" else f"set {v} on"
            ok_ask = confirmed if confirmed is not None else self.confirm(
                f"Unit {n}: {what} {r['label']} ({name})?" + ("\nNeeds a reboot." if "reboot" in r["flags"] else ""))
            if not ok_ask:
                self.say(f"unit {n} {name}: cancelled at the confirm dialog" if confirmed is None else
                         f"unit {n} {name}: not confirmed, nothing sent")
                self._revert(n, sr)
                return None
        if name in BACKLIGHT_ROWS and v == 0:
            if not (confirmed if confirmed is not None else self.confirm(BL_ZERO_ASK)):
                self.say(f"unit {n} {name}: 0 % not confirmed, nothing sent")
                self._revert(n, sr, force=True)
                return None
        peers = [d[name] for d in (self.rows, self.quick) if name in d]
        read_after = sr.instant if readback is None else readback

        def ok(rc, out):
            if rc != 0:
                self._revert(n, sr, force=after is not None)
                return ", unit kept its value"
            before = self.states[n].values.get(name)
            self.states[n].values[name] = v
            self.states[n].dirty.pop(name, None)
            if name in BACKLIGHT_ROWS:
                self.bl_seen(n, v, before)
            if n == self.cur:
                for p in peers:
                    p.set_ok(v)
            if read_after:
                self._readback(n, name, r)               # a flip shows what the unit now reports, not what was sent
            return ""

        if name in VCP_ROW and sr in self.quick.values():       # volume / mute: DDC/CI like a host would
            vv = r["option_vcp"][v - r["min"]] if r["option_vcp"] else v
            return self.run(f"set {name} = {v} (VCP {VCP_ROW[name]} = {vv})", self.dev("ddc", "set", VCP_ROW[name], vv), ok, "ddc", after=after)
        return self.run(f"{'run' if r['type'] == 'action' else 'set'} {name} = {v}", self.dev("settings", "set", name, v), ok, after=after)

    def _revert(self, n: str, sr, force: bool = False):
        """a cancelled or failed one-click flip (any failed port write: force) puts the widget back to the unit's last known value"""
        if sr.instant or force:
            name = sr.r["name"]
            self.states[n].dirty.pop(name, None)
            if n == self.cur:
                for d in (self.rows, self.quick):
                    if name in d:
                        d[name].load(self.states[n].values.get(name), None)

    def read_via_vcp(self, name: str) -> bool:
        return name in VCP_ROW or name in ("input", "screensaver_now")

    def _readback(self, n: str, name: str, r: dict, after=None):
        if self.read_via_vcp(name):
            code = VCP_ROW.get(name) or f"0x{r['vcp']:02X}"
            return self.run(f"readback {name}", self.dev("ddc", "get", code, unit=n), lambda rc, out: self._vcp_got(n, out), "ddc", unit=n, after=after)
        return self.run(f"readback {name}", self.dev("settings", "get", name, unit=n), lambda rc, out: self._got(n, rc, out), unit=n, after=after)

    def saver_start(self):
        self._saver(self.saver.currentData(), self.saver.currentText())

    def saver_stop(self):
        self._saver(0, "Stop")

    def _saver(self, v: int, label: str, unit: str | None = None, after=None):
        return self.run(f"screensaver now = {label} (VCP {VCP_SAVER} = {v})", self.dev("ddc", "set", VCP_SAVER, v, unit=unit), None, "ddc",
                        unit=unit, after=after)

    def quick_get(self, unit: str | None = None, after=None):
        """volume, mute, brightness, input select, screensaver: DDC/CI reads of their VCP codes, one call each (no mailbox)"""
        n = unit or self.cur
        codes = [f"0x{row_of(name)['vcp']:02X}" for name in QUICK_VCP]
        return self.run(f"get quick values (VCP {' '.join(codes)})", self.dev("ddc", "get", *codes, unit=n),
                 lambda rc, out, n=n: self._vcp_got(n, out), "ddcmany", unit=n, after=after)

    def _vcp_got(self, n: str, out: str) -> str:
        """every `VCP xx ...` reply line in out (one per code); returns the log suffix"""
        lines = [ln for ln in out.splitlines() if VCP_GET_RE.search(ln)]
        if not lines:
            return ", reply not understood"
        return "".join(self._vcp_line(n, VCP_GET_RE.search(ln)) for ln in lines)

    def _vcp_line(self, n: str, m) -> str:
        name = next((k for k in QUICK_VCP if f"{row_of(k)['vcp']:02x}" == m.group(1).lower()), None)
        if name is None:
            return ""
        f = m.group(3).split()
        hx = [int(x.lstrip("x"), 16) for x in f]
        raw = {"C": lambda: int(f[0]), "SNC": lambda: hx[0], "CNC": lambda: hx[2] << 8 | hx[3] if len(hx) == 4 else -1}[m.group(2)]()
        st = self.states[n]
        st.last_read_iso = isostamp.now()
        r = row_of(name)
        if r["option_vcp"]:
            if raw not in r["option_vcp"]:
                return f", value {raw} not in the registry options"
            raw = r["min"] + r["option_vcp"].index(raw)
        self._put(n, name, raw)
        self._quick_state(n)
        return f", {name} = {raw}"

    def _quick_state(self, n: str):
        """quick strip read-out of the two rows that have no slider: input select and screensaver"""
        if n != self.cur:
            return
        v = self.states[n].values
        inp, sav = v.get("input"), v.get("screensaver_now")
        if inp is not None and not self.inp_touched:
            self.inp.setCurrentIndex(inp)
        self.now_state.setText(f"unit shows: input {row_of('input')['options'][inp] if inp is not None else '?'}, "
                               f"screensaver {row_of('screensaver_now')['options'][sav] if sav is not None else '?'}")

    def save(self, unit: str | None = None, after=None):
        return self.run("settings save", self.dev("settings", "save", unit=unit), None, unit=unit, after=after)

    def _input_picked(self, *_):
        self.inp_touched = True
        self.input_select()

    def input_select(self, port: str | None = None, unit: str | None = None, after=None):
        p, n = port or self.inp.currentText(), unit or self.cur
        return self.run(f"input select {p}", [PYTHON, ROOT / "scripts" / "kvm.py", p, "--units", n], None, "kvm", unit=n, after=after)

    def note(self, text: str, unit: str | None = None, open_console: bool = False, after=None):
        return self.run("host note", self.dev("note", *(["--open-console"] if open_console else []), text, unit=unit), None, "note",
                        unit=unit, after=after)

    def host_time(self, unit: str | None = None, after=None):
        n = unit or self.cur
        return self.run("host time send now", [PYTHON, ROOT / "scripts" / "host_time.py", "--unit", n, "--once"], None, "host_time",
                        unit=n, after=after)

    def health(self, unit: str | None = None, after=None):
        return self.run("health", self.dev("health", unit=unit), lambda rc, out: ", " + next(
            (ln.strip() for ln in reversed(out.splitlines()) if "PASS" in ln or "FAIL" in ln), "no verdict line"), "health",
            unit=unit, after=after)

    def sync_log(self, unit: str | None = None, whole: bool | None = None, after=None, as_json: bool = False):
        w = self.whole.isChecked() if whole is None else whole
        args = [*(["--whole"] if w else []), *(["--json"] if as_json else [])]
        return self.synclog_job("sync log", args, None if as_json else self._synced, unit=unit, after=after)

    def synclog_job(self, label: str, args: list[str], done, unit: str | None = None, after=None):
        """a dev.py synclog job with its limit sized from the request (gui_client.synclog_limit)"""
        lim, why = gui_client.synclog_limit(args)
        stall = gui_client.synclog_stall_s(args)
        if stall:
            why += f"; stall guard {stall} s"
        return self.run(label, self.dev("synclog", *args, unit=unit), done, lim, unit=unit, after=after, limit_why=why, stall_s=stall)

    def _synced(self, rc, out) -> str:
        rows = sync_rows(out)
        self.sync.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, t in enumerate((r["real"], r["delta"], r["text"])):
                it = QTableWidgetItem(t)
                if r["raw"]:
                    it.setToolTip(r["raw"])
                if r["start"] or r["wrap"] or r["boot"] is not None:
                    it.setForeground(START_BRUSH)
                    it.setBackground(START_BG if r["boot"] is None else QBrush(QColor("#30363d")))
                elif r["slow"] and c == 1:
                    it.setForeground(SLOW_BRUSH)
                    it.setBackground(QBrush(QColor("#3a1a1a")))
                self.sync.setItem(i, c, it)
        self.sync_info.setText(sync_summary(rows))
        return f", {sync_summary(rows)}"

    # --- flash: a detached job (scripts/flash_job.py), tracked here; the app never signals it
    def flash_running(self) -> list[str]:
        """units with a flash running, from the job files + wrapper pids on every call. A tracked job the disk no longer backs
        (file gone, replaced, wrapper dead) is closed here as rc 255 with a log line, so it can never block quit or the idle exit."""
        out = []
        for n, st in self.states.items():
            t = st.track
            if t is None or t.progress.rc is not None:
                continue
            if t.live(st.info["serial"])[0]:
                out.append(n)
            else:
                self._flash_update(n, st, t)                 # closes the stale job (rc 255 + log) or picks up the real rc
        return out

    def flash_why(self, n: str) -> str:
        """why unit n counts as flashing: unit lock holder or the tracked job (id, pid, age); logged when it refuses something"""
        st = self.states[n]
        parts = []
        if held := flash_state(st.info["serial"]):
            lk = unit_lock.read(st.info["serial"]) or {}
            parts.append(f"unit lock held by {held} pid {lk.get('pid')}")
        if st.track is not None and st.track.progress.rc is None:
            parts.append(st.track.live(st.info["serial"])[1])
        why = "; ".join(parts) or "not flashing"
        self.say(f"unit {n} counts as flashing: {why}")
        return why

    def flash_jobs(self) -> list[dict]:
        """the app's view of its flash jobs, re-derived from disk: one row per unit with a tracked job"""
        self.flash_running()
        rows = []
        for n, st in self.states.items():
            t = st.track
            if t is None:
                continue
            serial = st.info["serial"]
            disk = flash_job.load(serial) or {}
            pid = int(t.job.get("pid") or 0)
            rows.append({"unit": n, "job": t.job["id"], "pid": pid, "alive": flash_job.wrapper_alive(pid),
                         "age_s": round(time.time() - t.job.get("started_mono_wall", time.time())), "rc": t.progress.rc,
                         "reported": t.finished_sent, "disk_job": disk.get("id"), "disk_rc": disk.get("rc"), "log": t.job["log"],
                         "lock": flash_state(serial) or None})
        return rows

    def flash_start(self, n: str, args: list[str]) -> dict:
        """start `dev.py flash ARGS --unit n --direct` as a detached job; refusals raise ValueError with the reason"""
        st = self.states[n]
        if not st.writable:
            raise ValueError(f"unit {n} is read-only (not a test unit in devices.json)")
        if n in self.flash_running() or st.flash:
            raise ValueError(f"unit {n} is already flashing ({self.flash_why(n)})")
        if st.pending:
            raise ValueError(f"unit {n} has {st.pending} job(s) running; wait for them, a flash holds the MCU in ISP")
        try:
            job = flash_job.start(st.info["serial"], n, [str(a) for a in self.flash_cmd(n, args)])
        except SystemExit as e:
            raise ValueError(str(e)) from None
        st.track = FlashTrack(job)
        self.say(f"unit {n} flash started: job {job['id']} pid {job['pid']}, log {job['log']}")
        self._strip_text(n)
        self._flash_event(n, st.track, [])
        self.show_flash(n)
        return job

    def adopt_flash_jobs(self):
        """after a restart: follow jobs the previous app run started (still running, or finished and not yet reported)"""
        for n, st in self.states.items():
            if st.unknown or st.track is not None:
                continue
            job = flash_job.load(st.info["serial"])
            if job and (flash_job.running(job) or flash_job.lost(job) or ("rc" in job and not job.get("reported"))):
                st.track = FlashTrack(job)
                self.say(f"unit {n}: re-attached to flash job {job['id']} (pid {job.get('pid')})")

    def flash_tick(self):
        for n, st in list(self.states.items()):
            if st.track is not None and not st.track.finished_sent:
                self._flash_update(n, st, st.track)

    def _flash_update(self, n: str, st: UnitState, t: FlashTrack):
        lines: list[str] = []
        try:
            with open(t.job["log"], "rb") as f:
                f.seek(t.offset)
                data = f.read()
            t.offset += len(data)
            text = t.rest + data.decode("utf-8", "replace")
            *whole, t.rest = text.split("\n")
            lines = [ln for ln in whole if ln.strip()]
        except FileNotFoundError:
            pass
        for ln in lines:
            t.progress.feed(ln)
        job = flash_job.load(st.info["serial"])
        if job and job.get("id") == t.job["id"]:
            if "rc" in job and t.progress.rc is None:
                t.progress.rc = int(job["rc"])
            elif flash_job.lost(job) and t.progress.rc is None:
                t.progress.rc = 255
                t.progress.feed("ERROR: flash worker is gone without a result (killed from outside?); the unit may hold a partial image, see the log")
            if "rc" in job and t.progress.rc == 255 and job.get("error") and not any("stale" in ln for ln in t.progress.last):
                t.progress.feed(f"ERROR: {job['error']}; the unit may hold a partial image, see the log")
        elif t.progress.rc is None:
            why = "its job file is gone" if job is None else f"its job file now holds job {job.get('id')}"
            t.progress.rc = 255
            t.progress.feed(f"ERROR: stale flash job {t.job['id']} (pid {t.job.get('pid')}): {why}; closed as rc 255")
            self.say(f"unit {n}: tracked flash job {t.job['id']} pid {t.job.get('pid')} closed as stale (rc 255): {why}")
        snap = t.progress.snapshot()
        key = {k: v for k, v in snap.items() if k not in ("elapsed_s", "eta_s", "last")}
        if lines or key != t.sent:
            t.sent = key
            self._flash_event(n, t, lines)
        if t.progress.rc is not None and not t.finished_sent:
            t.finished_sent = True
            self.say(f"unit {n} flash finished rc {t.progress.rc} in {snap['elapsed_s']:.0f} s")
            self.emit("flash_done", unit=n, job=t.job["id"], rc=t.progress.rc, elapsed_s=snap["elapsed_s"], lines=snap["last"])
            if job and job.get("id") == t.job["id"] and "rc" in job:
                flash_job.save({**job, "reported": True})
        self._strip_text(n)
        if n == self.cur:
            self.show_flash(n)

    def _flash_event(self, n: str, t: FlashTrack, lines: list[str]):
        snap = t.progress.snapshot()
        self.emit("flash", unit=n, job=t.job["id"], lines=lines, **{k: v for k, v in snap.items() if k != "last"})

    def flash_status(self, n: str) -> dict | None:
        t = self.states[n].track
        if t is None:
            return None
        self._flash_update(n, self.states[n], t) if not t.finished_sent else None
        snap = t.progress.snapshot()
        return {"job": t.job["id"], "pid": t.job.get("pid"), "done": t.progress.rc is not None, "log": t.job["log"], **snap}

    def show_flash(self, n: str):
        t = self.states[n].track
        self.flash_box.setVisible(t is not None)
        if t is None:
            return
        sn = t.progress.snapshot()
        self.flash_bar.setValue(int(sn["percent"] * 10))
        self.flash_title.setText(f"<b>unit {n}: {'FLASHING' if t.progress.rc is None else 'flash ' + ('done' if t.progress.rc == 0 else 'FAILED')}</b>"
                                 f"  {sn['phase']}  {sn['percent']:.0f} %")
        eta = f"{sn['eta_s']:.0f} s" if sn["eta_s"] else "-"
        self.flash_info.setText(f"sectors written {sn['written']}/{sn['total']} (erased {sn['erased']}), errors {sn['errors']}, ISP recoveries "
                                f"{sn['recoveries']}, burst redone {sn['redo']}, elapsed {sn['elapsed_s']:.0f} s, ETA {eta}"
                                + (f", rc {sn['rc']}" if sn["rc"] is not None else "; the unit's other operations are refused"))
        self.flash_log.setPlainText("\n".join(sn["last"][-6:]))


def default_flash_cmd(unit: str, args: list[str]) -> list:
    return [PYTHON, ROOT / "dev.py", "flash", *args, "--unit", unit, "--direct"]
