"""Offscreen smoke test: QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_smoke.py"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as A  # noqa: E402
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
    print("PASS")


if __name__ == "__main__":
    main()
