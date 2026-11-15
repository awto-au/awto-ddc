"""Offscreen smoke test: QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_smoke.py"""
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as A  # noqa: E402
import monitor as MON  # noqa: E402
import model as M  # noqa: E402

ROOT = A.ROOT
SHOTS = ROOT / "tmp" / "osdedit" / "shots"
TTF = "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf"


def roundtrip(bpp, geom, win):
    gs = M.import_ttf(TTF, bpp, geom)
    win.load_set(gs)
    n = len(gs.tiles)
    win.glyphs.list.setCurrentRow(40)                              # 'A'
    ed = win.glyphs.editor
    ed.color = (1 << bpp) - 1
    before = gs.tiles[40][3, 3]
    assert ed.set_pixel(3, 3, (int(before) + 1) % (1 << bpp))      # edit one pixel
    edited = [t.copy() for t in gs.tiles]
    with tempfile.TemporaryDirectory() as d:
        for vlc in (True, False):
            p = Path(d) / f"f_{bpp}_{geom}_{vlc}.inc"
            M.export_c(gs, p, vlc=vlc)
            back = M.import_c(p)
            assert (back.bpp, back.geom, len(back.tiles)) == (bpp, geom, n), (back.bpp, back.geom, len(back.tiles))
            assert all((a == b).all() for a, b in zip(edited, back.tiles)), "tiles differ after re-import"
            assert M.GlyphSet(bpp, geom, back.tiles).raw() == gs.raw(), "raw bytes differ"
    ed.undo_last()
    assert gs.tiles[40][3, 3] == before
    b = gs.budget()
    print(f"ok {bpp} bpp {geom}: {n} tiles, {b['font_words']} words ({b['pct']:.1f} %), raw {b['raw']} B, vlc {b['vlc']} B")


class FakeBackend:
    """canned script output; records every argv (no hardware, no subprocess)"""

    def __init__(self):
        self.calls = []

    def run(self, argv):
        a = [str(x) for x in argv]
        self.calls.append(a)
        if "settings" in a and "list" in a:
            return 0, "\n".join(f"{r['name']} = x (raw {r['default'] + (1 if r['type'] == 'int' and r['name'] == 'brightness' else 0)})"
                                for r in MON.T.ROWS if r["type"] != "action") + "\n"
        if "synclog" in a:
            return 0, ("2026-11-15T10:00:00+10:00 sync episode: power on, 4 lines\n"
                       "2026-11-15T10:00:00+10:00      0:power on\n2026-11-15T10:00:00+10:00     40:panel on\n"
                       "2026-11-15T10:00:00+10:00    390:input lock D2\n2026-11-15T10:00:00+10:00    420:backlight on\n")
        if "health" in a:
            return 0, "diag ok\nPASS\n"
        return 0, "ok\n"


def monitor_test(app, win):
    fb = FakeBackend()
    logf = ROOT / "tmp" / "osdedit" / "monitor_test.log"
    logf.unlink(missing_ok=True)
    pg = MON.MonitorPage(fb, logf)
    win.stack.addWidget(pg)
    win.stack.setCurrentWidget(pg)
    assert pg.writable() and pg.n() == "3", pg.n()
    pg.get_all()
    pg.wait_idle()
    app.processEvents()
    assert fb.calls[-1][-5:] == ["settings", "list", "--unit", "3"][-4:] or fb.calls[-1][2:] == ["settings", "list", "--unit", "3"]
    assert pg.rows["brightness"].w.value() == 51 and pg.rows["gamma"].w.currentIndex() == 0
    pg.rows["brightness"].w.setValue(60)
    pg.rows["gamma"].w.setCurrentIndex(3)
    pg.set_row(pg.rows["brightness"])
    pg.set_row(pg.rows["gamma"])
    pg.save()
    pg.inp.setCurrentText("D2")
    pg.input_select()
    pg.host_time()
    pg.health()
    pg.sync_log()
    pg.wait_idle()
    app.processEvents()
    sent = [" ".join(c[1:]) for c in fb.calls]
    for want in ("settings set brightness 60", "settings set gamma 3", "settings save", "kvm.py D2 --units 3",
                 "host_time.py --unit 3 --once", "health", "synclog --whole"):
        assert any(want in x for x in sent), (want, sent)
    assert pg.sync.rowCount() == 4
    assert [pg.sync.item(i, 0).text() for i in range(4)] == ["", "+40", "+350", "+30"]
    assert pg.sync.item(2, 0).foreground().color().name() == "#ff5050" and pg.sync.item(1, 0).foreground().color().name() != "#ff5050"
    log = logf.read_text().splitlines()
    iso = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d unit 3 ")
    assert sum(bool(iso.match(x)) for x in log) >= 8 and any("health: ok, PASS" in x for x in log), log
    n = len(fb.calls)
    pg.unit.setCurrentIndex(0)                                     # unit 1: working screen, read-only
    assert not pg.writable() and not pg.rows["brightness"].btn.isEnabled()
    pg.run("probe", ["x"], None)
    assert len(fb.calls) == n
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.unit.setCurrentIndex(2)
    win.resize(1400, 900)
    app.processEvents()
    win.grab().save(str(SHOTS / "editor_monitor.png"))
    print("ok monitor page: get/set/save/input/host time/health/sync log through the fake backend,", len(log), "log lines")


def main():
    app = QApplication([])
    win = A.Window()
    win.show()
    for bpp, geom in ((1, "12x18"), (2, "24x36"), (4, "24x36")):
        roundtrip(bpp, geom, win)
    # OsdEdit 2523V txt (scratch output of the vendor tool, not committed) decodes to a 1 bpp 12x18 tile
    ox = ROOT / "tmp" / "osdedit" / "o_2523v.txt"
    if ox.exists():
        gs = M.import_c(ox)
        assert gs.tiles and gs.tiles[0].shape == (18, 12), gs.tiles[:1]
        print("ok OsdEdit 2523V txt import:", len(gs.tiles), "tile(s)")
    SHOTS.mkdir(parents=True, exist_ok=True)
    win.load_set(M.import_ttf(TTF, 2, "24x36"))
    win.glyphs.list.setCurrentRow(40)
    win.go(0)
    app.processEvents()
    win.grab().save(str(SHOTS / "editor_glyphs.png"))
    win.go(1)
    win.screens.load_dir()
    win.resize(1280, 760)
    app.processEvents()
    win.grab().save(str(SHOTS / "editor_screens.png"))
    print("screens loaded:", len(win.screens.rows))
    monitor_test(app, win)
    print("PASS")


if __name__ == "__main__":
    main()
