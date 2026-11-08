"""awto OSD editor: glyph/tile editor + screen viewer + budget panel (PySide6). Builds on scripts/ (never re-encodes)."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QProcess, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QStackedWidget, QToolBar, QVBoxLayout, QWidget)

import model as M

ROOT = Path(__file__).resolve().parents[2]
CSS = """
* { font-family: monospace; font-size: 12px; color: #d8d8d8; }
QMainWindow, QWidget#root { background: #141414; }
QFrame#panel, QListWidget, QScrollArea, QSpinBox, QComboBox { background: #1e1e1e; border: 1px solid #2a2a2a; }
QToolBar { background: #141414; border: none; spacing: 6px; }
QPushButton, QToolButton { background: #1e1e1e; border: 1px solid #2a2a2a; padding: 4px 10px; }
QPushButton:hover, QToolButton:hover { background: #2a2a2a; }
QPushButton:checked, QToolButton:checked { background: #3a1a1a; border-color: #ff3030; }
QScrollArea > QWidget > QWidget { background: #1e1e1e; }
QStatusBar { background: #141414; } QStatusBar::item { border: none; }
"""


def qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class TileEditor(QWidget):
    """Pixel editor for one tile. Left button paints the current colour, right button paints colour 0."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.gs = None
        self.idx = -1
        self.color = 1
        self.cell = 16
        self.undo = []
        self.setMouseTracking(True)

    def set_tile(self, gs, idx):
        self.gs, self.idx = gs, idx
        if gs:
            self.setFixedSize(gs.uw * self.cell + 1, gs.uh * self.cell + 1)
        self.update()

    def tile(self):
        return self.gs.tiles[self.idx] if self.gs and 0 <= self.idx < len(self.gs.tiles) else None

    def set_pixel(self, x, y, v):
        t = self.tile()
        if t is None or not (0 <= x < self.gs.uw and 0 <= y < self.gs.uh) or t[y, x] == v:
            return False
        self.undo.append((self.idx, t.copy()))
        t[y, x] = v
        self.update()
        self.changed.emit()
        return True

    def undo_last(self):
        if self.undo:
            i, t = self.undo.pop()
            self.gs.tiles[i] = t
            self.update()
            self.changed.emit()

    def _paint(self, ev):
        b = ev.buttons()
        if b & (Qt.LeftButton | Qt.RightButton):
            p = ev.position()
            self.set_pixel(int(p.x()) // self.cell, int(p.y()) // self.cell, self.color if b & Qt.LeftButton else 0)

    mousePressEvent = mouseMoveEvent = _paint

    def paintEvent(self, _):
        p = QPainter(self)
        t = self.tile()
        if t is None:
            return
        rgb = self.gs.rgb(t)
        for y in range(self.gs.uh):
            for x in range(self.gs.uw):
                p.fillRect(x * self.cell, y * self.cell, self.cell, self.cell, QColor(*map(int, rgb[y, x])))
        p.setPen(QColor("#2a2a2a"))
        for x in range(self.gs.uw + 1):
            p.setPen(QColor("#555" if x % 12 == 0 else "#2a2a2a"))      # 12x18 cell borders (2x2 in 24x36)
            p.drawLine(x * self.cell, 0, x * self.cell, self.gs.uh * self.cell)
        for y in range(self.gs.uh + 1):
            p.setPen(QColor("#555" if y % 18 == 0 else "#2a2a2a"))
            p.drawLine(0, y * self.cell, self.gs.uw * self.cell, y * self.cell)


def panel(title):
    f = QFrame()
    f.setObjectName("panel")
    lay = QVBoxLayout(f)
    lay.addWidget(QLabel(f"<b>{title}</b>"))
    return f, lay


class GlyphPage(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.gs = M.GlyphSet()
        self.gs.tiles = [self.gs.blank()]
        root = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setIconSize(QSize(48, 72))
        self.list.setMinimumWidth(330)
        self.list.currentRowChanged.connect(self.select)
        root.addWidget(self.list, 2)
        mid, ml = panel("tile")
        self.editor = TileEditor()
        self.editor.changed.connect(self.refresh_tile)
        ml.addWidget(self.editor, 0, Qt.AlignCenter)
        self.pal_row = QHBoxLayout()
        ml.addLayout(self.pal_row)
        ml.addStretch()
        root.addWidget(mid, 3)
        right, rl = panel("preview")
        self.p1, self.p2 = QLabel(), QLabel()
        for lab, txt in ((self.p1, "1x"), (self.p2, "2x (OSD scale)")):
            rl.addWidget(QLabel(txt))
            rl.addWidget(lab)
        rl.addStretch()
        root.addWidget(right, 1)
        self.load(self.gs)

    def load(self, gs):
        self.gs = gs
        self.editor.undo.clear()
        self.list.blockSignals(True)
        self.list.clear()
        for i in range(len(gs.tiles)):
            self.list.addItem(QListWidgetItem(self.icon(i), str(i)))
        self.list.blockSignals(False)
        while self.pal_row.count():
            w = self.pal_row.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
        for i, c in enumerate(gs.palette):
            b = QPushButton(str(i))
            b.setCheckable(True)
            b.setFixedSize(34, 28)
            b.setStyleSheet(f"background: rgb{tuple(c)}; color: {'#000' if sum(c) > 300 else '#fff'};")
            b.clicked.connect(lambda _=False, i=i: self.pick(i))
            self.pal_row.addWidget(b)
        self.editor.color = min(1, len(gs.palette) - 1)
        self.list.setCurrentRow(0 if gs.tiles else -1)
        self.select(0 if gs.tiles else -1)
        self.changed.emit()

    def pick(self, i):
        self.editor.color = i

    def icon(self, i):
        return QIcon(QPixmap.fromImage(qimage(self.gs.rgb(self.gs.tiles[i], 2))))

    def select(self, row):
        self.editor.set_tile(self.gs, row)
        self.refresh_preview()

    def refresh_preview(self):
        t = self.editor.tile()
        if t is None:
            return
        for lab, s in ((self.p1, 1), (self.p2, 2)):
            lab.setPixmap(QPixmap.fromImage(qimage(self.gs.rgb(t, s))))

    def refresh_tile(self):
        r = self.editor.idx
        if r >= 0:
            self.list.item(r).setIcon(self.icon(r))
        self.refresh_preview()
        self.changed.emit()


class ScreensPage(QWidget):
    def __init__(self):
        super().__init__()
        self.rows, self.i, self.zoom = [], 0, 0
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.dirs = QComboBox()
        self.dirs.currentIndexChanged.connect(self.load_dir)
        self.title = QLabel("no catalogue")
        bar.addWidget(self.dirs, 1)
        bar.addWidget(self.title, 2)
        for txt, fn in (("<", lambda: self.step(-1)), (">", lambda: self.step(1))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            bar.addWidget(b)
        self.zs = QSpinBox()
        self.zs.setRange(0, 400)
        self.zs.setSpecialValueText("fit")
        self.zs.setValue(self.zoom)
        self.zs.setSuffix(" %")
        self.zs.valueChanged.connect(lambda v: (setattr(self, "zoom", v), self.show_row()))
        bar.addWidget(self.zs)
        r = QPushButton("render BIN...")
        r.clicked.connect(self.render_bin)
        bar.addWidget(r)
        lay.addLayout(bar)
        self.img = QLabel(alignment=Qt.AlignCenter)
        sa = QScrollArea()
        sa.setWidget(self.img)
        sa.setWidgetResizable(True)
        lay.addWidget(sa, 1)
        self.proc = None
        for d in sorted((ROOT / "tmp" / "osd_catalog").glob("*/catalog.tsv"), key=lambda p: -p.stat().st_mtime):
            self.dirs.addItem(d.parent.name, str(d.parent))

    def load_dir(self, _=0):
        d = self.dirs.currentData()
        self.rows, self.i = [], 0
        if d and (Path(d) / "catalog.tsv").exists():
            with open(Path(d) / "catalog.tsv") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    p = Path(r["png"])
                    if p.exists():
                        self.rows.append((r["name"], r["what"], p))
        self.show_row()

    def step(self, n):
        if self.rows:
            self.i = (self.i + n) % len(self.rows)
            self.show_row()

    def show_row(self):
        if not self.rows:
            self.img.setText("no rendered screens: use render BIN...")
            return
        name, what, p = self.rows[self.i]
        self.title.setText(f"{self.i + 1}/{len(self.rows)}  {name}: {what}")
        pm = QPixmap(str(p))
        if self.zoom == 0:
            vp = self.img.parentWidget().size() - QSize(4, 4)
            self.img.setPixmap(pm.scaled(vp, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.img.setPixmap(pm.scaled(pm.size() * self.zoom / 100, Qt.KeepAspectRatio, Qt.FastTransformation))

    def render_bin(self):
        f, _ = QFileDialog.getOpenFileName(self, "firmware image (.bin with .map beside)", str(ROOT), "*.bin")
        if not f:
            return
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.finished.connect(lambda *_: self.reload(Path(f).stem))
        self.title.setText("rendering (osd_catalog.py)...")
        self.proc.start(sys.executable, [str(ROOT / "scripts" / "osd_catalog.py"), f])

    def reload(self, stem):
        self.dirs.clear()
        for d in sorted((ROOT / "tmp" / "osd_catalog").glob("*/catalog.tsv"), key=lambda p: -p.stat().st_mtime):
            self.dirs.addItem(d.parent.name, str(d.parent))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("awto OSD editor")
        self.resize(1280, 760)
        self.setStyleSheet(CSS)
        self.stack = QStackedWidget()
        self.glyphs, self.screens = GlyphPage(), ScreensPage()
        self.stack.addWidget(self.glyphs)
        self.stack.addWidget(self.screens)
        root = QWidget()
        root.setObjectName("root")
        lay = QVBoxLayout(root)
        self.budget = QLabel()
        bf, bl = panel("budget")
        bl.addWidget(self.budget)
        bf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        lay.addWidget(bf)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.glyphs.changed.connect(self.update_budget)
        self.build_toolbar()
        self.statusBar().addPermanentWidget(QLabel("awto-ddc#89"))         # right side only
        self.update_budget()
        self.undo = QAction(self)
        self.undo.setShortcut(QKeySequence.Undo)
        self.undo.triggered.connect(self.glyphs.editor.undo_last)
        self.addAction(self.undo)

    def build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)
        sp = QWidget()
        sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(sp)                                               # actions + navigation sit top-right
        for txt, fn in (("open", self.open), ("import", self.import_), ("export C", self.export_),
                        ("new", self.new_set)):
            a = tb.addAction(txt)
            a.triggered.connect(fn)
        tb.addSeparator()
        self.nav = []
        for i, txt in enumerate(("glyphs", "screens")):
            a = tb.addAction(txt)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, i=i: self.go(i))
            self.nav.append(a)
        self.go(0)

    def go(self, i):
        self.stack.setCurrentIndex(i)
        for k, a in enumerate(self.nav):
            a.setChecked(k == i)

    def update_budget(self):
        b = self.glyphs.gs.budget()
        gs = self.glyphs.gs
        self.budget.setStyleSheet("color: #ff5050;" if b["pct"] > 100 else "")
        self.budget.setText(
            f"{gs.name}: {gs.bpp} bpp  {gs.geom}  {b['tiles']} tiles | font SRAM {b['font_words']} / {b['sram_words']} words "
            f"({b['pct']:.1f} %) | flash raw {b['raw']} B, VLC {b['vlc']} B")

    def load_set(self, gs):
        self.glyphs.load(gs)
        self.update_budget()

    def new_set(self):
        bpp, ok = QInputDialog.getItem(self, "new", "bpp", ["1", "2", "4"], 1, False)
        if not ok:
            return
        geom, ok = QInputDialog.getItem(self, "new", "tile", list(M.GEOMS), 1, False)
        if ok:
            gs = M.GlyphSet(int(bpp), geom)
            gs.tiles = [gs.blank() for _ in range(16)]
            self.load_set(gs)

    def open(self):
        f, _ = QFileDialog.getOpenFileName(self, "open font table", str(ROOT), "C tables / OsdEdit txt (*.inc *.c *.h *.txt)")
        if f:
            self.load_set(M.import_c(f))

    def import_(self):
        f, _ = QFileDialog.getOpenFileName(self, "import PNG / SVG / TTF", str(ROOT), "images + fonts (*.png *.svg *.ttf *.otf)")
        if not f:
            return
        bpp, ok = QInputDialog.getItem(self, "import", "bpp", ["1", "2", "4"], 1, False)
        geom, ok2 = QInputDialog.getItem(self, "import", "tile", list(M.GEOMS), 1, False)
        if not (ok and ok2):
            return
        self.import_file(f, int(bpp), geom)

    def import_file(self, f, bpp, geom):
        ext = Path(f).suffix.lower()
        if ext in (".ttf", ".otf"):
            gs = M.import_ttf(f, bpp, geom)
        elif ext == ".svg":
            from PySide6.QtSvg import QSvgRenderer
            r = QSvgRenderer(f)
            w, h = M.GEOMS[geom][:2]
            cols = max(1, r.defaultSize().width() // w) if r.defaultSize().width() > w else 1
            img = QImage(w * cols, h * max(1, round(r.defaultSize().height() / h)), QImage.Format_Grayscale8)
            img.fill(0)
            p = QPainter(img)
            r.render(p)
            p.end()
            g = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width()]
            gs = M.from_gray(g.copy(), bpp, geom, Path(f).stem)
        else:
            gs = M.import_png(f, bpp, geom)
        self.load_set(gs)

    def export_(self):
        f, _ = QFileDialog.getSaveFileName(self, "export C table (VLC)", str(ROOT / "tmp" / f"{self.glyphs.gs.name}.inc"), "*.inc *.c")
        if f:
            M.export_c(self.glyphs.gs, f)
            self.statusBar().showMessage("")


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setFont(QFont("monospace", 9))
    w = Window()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
