"""Offscreen smoke test: QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_smoke.py"""
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import QSettings  # noqa: E402
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
    """canned script output; records every argv (no hardware, no subprocess).
    live_set / live_get = the in-process DDC/CI writes of the live sliders: `live_latency_s` per call, recorded in `live_calls`"""

    live_latency_s = 0.0

    def __init__(self):
        self.calls, self.limits, self.fail, self.direct = [], [], None, 0
        self.fail_on = []                                # [(substring of the argv, rc, text)] consumed by the first matching call
        self.live_calls, self.live_active, self.live_max, self.live_value, self.live_fail, self.live_times = [], 0, 0, {}, None, []
        self._live_lock = threading.Lock()

    def _live(self, call):
        with self._live_lock:
            self.live_active += 1
            self.live_max = max(self.live_max, self.live_active)
            self.live_calls.append(call)
            self.live_times.append(time.monotonic())
        try:
            time.sleep(self.live_latency_s)                 # the fake write time (a test stand-in for the bus latency)
            if self.live_fail:
                return 1, self.live_fail
            return 0, ""
        finally:
            with self._live_lock:
                self.live_active -= 1

    def live_set(self, u, code, value, row_id, reselect):
        rc, out = self._live(("set", u["serial"], code, value, row_id, reselect))
        if rc == 0:
            self.live_value[(u["serial"], code, row_id)] = value
        return rc, out

    def live_get(self, u, code, row_id):
        rc, out = self._live(("get", u["serial"], code, row_id))
        v = self.live_value.get((u["serial"], code, row_id), 0)
        return (0, f"value {v} max 100") if rc == 0 else (rc, out)

    status_reply = {"ddc": {"volume": 50, "mute": 1, "brightness": 51, "contrast": 75, "power_mode": 0, "input": 1}, "ddc_err": "",
                    "dbg": {"stage": 8, "loop": 4100, "clk": {"cpu": 350.8, "pll": 350.8, "spi": 116.9}, "pwm": 125,
                            "timing": {"w": 1920, "h": 1080, "hz": 60.0}, "timing_why": ""}, "dbg_err": "", "tag": "wb-test",
                    "info": {"info_hres": 1920, "info_vres": 1080, "info_vfreq": 600, "info_loop": 4100}}
    status_calls: list = []

    def status_read(self, u):
        self.status_calls = [*self.status_calls, (time.monotonic(), u["serial"])]
        time.sleep(self.live_latency_s)
        return 0, json.dumps({**self.status_reply, "serial": u["serial"]})

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        if "--direct" in a:                              # the app's workers run dev.py --direct; recorded without it (own test checks it)
            a.remove("--direct")
            self.direct += 1
        self.calls.append(a)
        self.limits.append(limit_s)
        if self.fail:
            rc, text, self.fail = self.fail[0], self.fail[1], None
            return rc, text
        for hit in self.fail_on:
            if hit[0] in " ".join(a):
                self.fail_on.remove(hit)
                return hit[1], hit[2]
        if "ddc" in a and "get" in a:
            vals = {"0x62": "VCP 62 CNC x00 x64 x00 x25", "0x8D": "VCP 8D CNC x00 x01 x00 x01", "0x10": "VCP 10 C 64 100",
                    "0x60": "VCP 60 SNC x11", "0xEB": "VCP EB CNC x00 x08 x00 x00"}
            codes = a[a.index("get") + 1:a.index("--unit") if "--unit" in a else None]
            return 0, "".join(f"HDMI-A-2         bus=11  {vals[c]}\n" for c in codes)
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


def settle(app, pg):
    pg.wait_idle()
    app.processEvents()


def quick_test(app, pg, fb):
    """Quick group, read-only rows, enum labels, refresh vs drag, limits, error banner"""
    pg.select_unit("3", read=False)
    n = len(fb.calls)
    pg.saver.setCurrentText("Scope 2")
    pg.saver_start()
    pg.saver_stop()
    pg.saver.setCurrentText("Flash warning")
    pg.saver_start()
    pg.quick["volume"].set_value(33)
    pg.set_row(pg.quick["volume"])
    pg.quick["mute"].w.setCurrentIndex(1)                          # On -> VCP 0x8D = 1
    pg.set_row(pg.quick["mute"])
    pg.rows["disp_rotate"].w.setCurrentIndex(0)
    pg.set_row(pg.rows["disp_rotate"])
    settle(app, pg)
    sent = [" ".join(c[2:]) for c in fb.calls[n:]]
    assert sent == ["ddc set 0xEB 4 --unit 3", "ddc set 0xEB 0 --unit 3", "ddc set 0xEB 5 --unit 3", "ddc set 0x62 33 --unit 3",
                    "ddc set 0x8D 1 --unit 3", "settings set disp_rotate 0 --unit 3", "ddc get 0x8D --unit 3",
                    "settings get disp_rotate --unit 3"], sent          # the two one-click rows read back after their write
    pg.quick["brightness"].set_value(70)                         # quick brightness: mailbox row like the tree
    pg.set_row(pg.quick["brightness"])
    settle(app, pg)
    assert " ".join(fb.calls[-1][2:]) == "settings set brightness 70 --unit 3" and pg.rows["brightness"].w.value() == 70
    assert pg.rows["volume"].w.value() == 33 and pg.rows["mute"].w.currentIndex() == 1       # main rows follow
    pg.quick_get()
    settle(app, pg)
    assert pg.quick["volume"].w.value() == 37 and pg.quick["mute"].w.currentIndex() == 1
    # read-only rows stay disabled on the writable unit; enum rows show the option label
    ro = [sr for sr in pg.rows.values() if sr.read_only]
    assert ro and all(not sr.w.isEnabled() and not sr.btn.isEnabled() for sr in ro), ro
    assert pg.rows["gamma"].label_of(3).strip("( )") == pg.rows["gamma"].r["options"][3]
    assert len(pg.page_items) == 15 and len(pg.all_rows) == len(MON.T.ROWS)
    # a refresh keeps a touched row and a dragged slider
    sr = pg.rows["brightness"]
    sr.set_value(80)
    pg.get_all()
    settle(app, pg)
    assert sr.w.value() == 80 and sr.cur.text() == "unit: 51", (sr.w.value(), sr.cur.text())
    sr.dirty = False
    pg.get_all()
    settle(app, pg)
    assert sr.w.value() == 51
    # timer tick refreshes only when idle; limits come from LIMIT_S
    n = len(fb.calls)
    pg.refresh_tick()
    settle(app, pg)
    assert len(fb.calls) == n + 1 and fb.limits[-1] == MON.LIMIT_S["list"]
    # unit does not answer / call timed out: banner, never a hang, one log line each
    fb.fail = (1, "AWT26110003: no bus with that EDID serial (unit off, wedged, or cabled elsewhere)\n")
    pg.health()
    settle(app, pg)
    assert not pg.banner.isHidden() and "does not answer" in pg.banner.text(), pg.banner.text()
    fb.fail = (124, "limit 13 s expired, process stopped\n")
    pg.health()
    settle(app, pg)
    assert "did not finish in 13 s" in pg.banner.text(), pg.banner.text()
    pg.health()
    settle(app, pg)
    assert pg.banner.isHidden()
    log = pg.log_path.read_text()
    assert "NO ANSWER rc 1" in log and "TIMEOUT limit 13 s" in log
    print("ok quick controls, read-only rows, enum labels, refresh vs drag, limits, error banner")


def screens_2bpp_test(app, win):
    """a 2 bpp glyph rendered by osd_model shows on the Screens page (bit-plane layout, tests/test_osd_model.py)"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import osd_model as OM
    import osd_vlc
    lv = [[(x // 3 + y) % 4 for x in range(12)] for y in range(18)]
    data = b"".join(osd_vlc.pack_unit([[(v >> (1 - p)) & 1 for v in row] for row in lv], 1) for p in range(2))
    regs = bytearray(256)
    regs[0x02], regs[0x0A] = 1, 0
    regs[0x0C], regs[0x0D], regs[0x0E] = 2, 0x00, 0x10
    st = OM.OsdState(regs=bytes(regs), font={}, ovl=(1, 0))
    st.pal[1], st.pal[2], st.pal[3] = (50, 0, 0), (150, 0, 0), (250, 0, 0)
    for k in range(18):
        st.font[0x100 + 18 * 3 + k] = list(data[3 * k:3 * k + 3])
    st.font[0], st.font[1], st.font[2] = [0x80, 17, 1], [0, 0, 0], [0x80 | 0x20 | 0x04 | 0x02, 3, 0x08 | 0x01 | 0x40]
    img = OM.render(st, 32, 32, bg=(9, 9, 9))
    d = ROOT / "tmp" / "osdedit" / "catalog_2bpp"
    d.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.fromarray(img).save(d / "glyph2.png")
    (d / "catalog.tsv").write_text(f"name\twhat\tpng\nglyph2\t2 bpp glyph\t{d / 'glyph2.png'}\n")
    win.screens.dirs.addItem("smoke 2 bpp", str(d))
    win.screens.dirs.setCurrentIndex(win.screens.dirs.count() - 1)
    win.go(1)
    app.processEvents()
    assert len(win.screens.rows) == 1 and not win.screens.img.pixmap().isNull()
    shown = {tuple(int(x) for x in img[y, x]) for y in range(18) for x in range(12)}
    assert len(shown - {(9, 9, 9)}) >= 2, shown                        # more than one non-background level drawn
    print("ok screens page shows a 2 bpp glyph rendered by osd_model:", len(shown), "colours")


def monitor_test(app, win):
    fb = FakeBackend()
    logf = ROOT / "tmp" / "osdedit" / "monitor_test.log"
    logf.unlink(missing_ok=True)
    ini = ROOT / "tmp" / "osdedit" / "monitor_test.ini"
    ini.unlink(missing_ok=True)
    pg = MON.MonitorPage(fb, logf, QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    pg.select_unit("3", read=False)
    win.stack.addWidget(pg)
    win.stack.setCurrentWidget(pg)                                 # shown: the stale view is read, status probes run
    settle(app, pg)
    fb.calls.clear()
    assert pg.writable() and pg.n() == "3", pg.n()
    pg.get_all()
    pg.wait_idle()
    app.processEvents()
    assert fb.calls[-1][-5:] == ["settings", "list", "--unit", "3"][-4:] or fb.calls[-1][2:] == ["settings", "list", "--unit", "3"]
    assert pg.rows["brightness"].w.value() == 51 and pg.rows["gamma"].w.currentIndex() == 0
    pg.rows["brightness"].set_value(60)
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
    quick_test(app, pg, fb)
    n = len(fb.calls)
    pg.states["1"].info = {**pg.states["1"].info, "test": False}  # a working screen: read-only
    pg.select_unit("1", read=False)
    assert not pg.writable() and not pg.rows["brightness"].btn.isEnabled()
    pg.run("probe", ["x"], None)
    assert len(fb.calls) == n
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.states["1"].info = {**pg.states["1"].info, "test": True}
    pg.select_unit("3", read=False)
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
    screens_2bpp_test(app, win)
    monitor_test(app, win)
    print("PASS")


if __name__ == "__main__":
    main()
