"""Offscreen test of the monitor page (unit strip, tree, search, confirm, per-unit queues); fake backend, no hardware:
QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_monitor_gui.py"""
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import monitor as MON  # noqa: E402
from test_smoke import FakeBackend  # noqa: E402

ROOT = MON.ROOT
SHOTS = ROOT / "tmp" / "scratch" / "qt"
WORK = ROOT / "tmp" / "osdedit"
WAIT_S = 3.0                                    # a fake job is instant; 3 s = the queue is stuck


class GateBackend(FakeBackend):
    """jobs for the units in `gated` block until `gate` is set; tracks how many run at once (total and per unit)"""

    def __init__(self):
        super().__init__()
        self.gate, self.gated = threading.Event(), set()
        self.lock = threading.Lock()
        self.active, self.max_unit, self.max_all = Counter(), Counter(), 0

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        u = a[a.index("--unit") + 1] if "--unit" in a else "?"
        if u not in self.gated:
            return super().run(argv, limit_s)
        with self.lock:
            self.active[u] += 1
            self.max_unit[u] = max(self.max_unit[u], self.active[u])
            self.max_all = max(self.max_all, sum(self.active.values()))
        try:
            if not self.gate.wait(WAIT_S):
                return 124, "gate not released\n"
            return super().run(argv, limit_s)
        finally:
            with self.lock:
                self.active[u] -= 1


def until(cond, what):
    t0 = time.monotonic()
    while not cond():
        assert time.monotonic() - t0 < WAIT_S, f"timeout waiting for {what}"
        QTest.qWait(5)


def settle(pg):
    pg.wait_idle()
    QTest.qWait(0)
    QApplication.processEvents()


def make(name, backend=None, detect=lambda: set(), fresh=True):
    ini = WORK / f"{name}.ini"
    ini.unlink(missing_ok=True)
    log = WORK / f"{name}.log"
    log.unlink(missing_ok=True)
    fb = backend or FakeBackend()
    pg = MON.MonitorPage(fb, log, QSettings(str(ini), QSettings.IniFormat), detect=detect)
    if fresh:
        for st in pg.states.values():
            st.last_read = time.monotonic()
    return pg, fb, ini


def strip_and_hotkeys(app):
    pg, fb, _ = make("gui_strip")
    pg.show()
    settle(pg)
    fb.calls.clear()
    units = MON.load_units()
    assert list(pg.unit_btns) == list(units) and len(units) >= 3
    for n, b in pg.unit_btns.items():
        u = units[n]
        assert u["serial"][-4:] in b.text() and u["input"] in b.text() and f"unit {n}" in b.text(), b.text()
    pg.select_unit("1", read=False)
    pg.setFocus()
    pg.tree.setFocus()
    QTest.keyClick(pg.tree, Qt.Key_2)
    assert pg.cur == "2" and pg.unit_btns["2"].isChecked(), pg.cur
    QTest.keyClick(pg.tree, Qt.Key_3, Qt.ControlModifier)
    assert pg.cur == "3"
    QTest.keyClick(pg.tree, Qt.Key_Tab, Qt.ControlModifier)
    assert pg.cur == "1", pg.cur
    assert not fb.calls, fb.calls                                      # a view swap, no read
    pg.search.setFocus()
    QTest.keyClick(pg.search, Qt.Key_2)                                # a digit typed in the search box is text
    assert pg.cur == "1" and pg.search.text() == "2", (pg.cur, pg.search.text())
    pg.search.clear()
    assert not fb.calls
    # a stale view is read on select, a fresh one is not
    pg.states["2"].last_read = time.monotonic() - MON.STALE_S - 1
    pg.select_unit("2")
    settle(pg)
    assert [" ".join(c[2:]) for c in fb.calls] == ["settings list --unit 2"], fb.calls
    assert pg.states["2"].last_read > time.monotonic() - 5
    fb.calls.clear()
    pg.select_unit("3")
    pg.select_unit("2")
    assert not fb.calls
    print("ok unit strip lists the units, hotkeys 1..9 / Ctrl+n / Ctrl+Tab switch the view without a read, stale view reads")
    pg.hide()


def tree_and_search():
    pg, fb, _ = make("gui_tree")
    pages = Counter(r["page"] for r in MON.T.ROWS)
    assert len(MON.T.ROWS) == 118 and len(pages) == 15
    assert pg.tree.topLevelItemCount() == 15
    total = 0
    for i in range(15):
        pi = pg.tree.topLevelItem(i)
        p = pi.data(0, MON.PAGE_ROLE)
        assert pi.childCount() == pages[p] and pi.text(0).endswith(f"({pages[p]})"), (pi.text(0), pages[p])
        total += pi.childCount()
    assert total == 118
    assert sum("[risky]" in it.text(0) for it in pg.items.values()) == 11
    assert sum("[action]" in it.text(0) for it in pg.items.values()) == 6
    pg.search.setText("volume")
    vis = [n for n, it in pg.items.items() if not it.isHidden()]
    assert "volume" in vis and 0 < len(vis) < 10, vis
    assert sum(not pg.tree.topLevelItem(i).isHidden() for i in range(15)) < 15
    pg.search.setText("0x62")                                          # VCP code
    assert not pg.items["volume"].isHidden() and pg.items["brightness"].isHidden()
    pg.search.setText("0x10")
    assert not pg.items["brightness"].isHidden() and pg.items["volume"].isHidden()
    pg.search.setText("GAMMA")                                         # label / name, any case
    assert [n for n, it in pg.items.items() if not it.isHidden()] == ["gamma"]
    pg.jump_first_match()
    assert pg.states[pg.cur].node == "row:gamma" and pg.stack.currentIndex() == MON.row_of("gamma")["page"]
    gid = MON.row_of("gamma")["id"]
    pg.search.setText(str(gid))                                        # id
    assert not pg.items["gamma"].isHidden()
    pg.search.setText("zzzz")
    assert all(it.isHidden() for it in pg.items.values())
    pg.search.clear()
    assert all(not it.isHidden() for it in pg.items.values())
    print("ok tree: 15 pages, 118 rows, counts match settings_table; search filters by name, label, id and VCP; Enter jumps")


def risky_confirm():
    pg, fb, _ = make("gui_confirm")
    pg.select_unit("3", read=False)
    asked = []
    pg.confirm = lambda text: (asked.append(text), False)[1]
    risky = next(r for r in MON.T.ROWS if "risky" in r["flags"] and r["type"] != "action")
    act = next(r for r in MON.T.ROWS if r["type"] == "action")
    pg.set_row(pg.rows[risky["name"]])
    pg.set_row(pg.all_rows[act["name"]])
    settle(pg)
    assert len(asked) == 2 and not fb.calls, (asked, fb.calls)
    assert risky["label"] in asked[0] and act["label"] in asked[1]
    pg.confirm = lambda text: (asked.append(text), True)[1]
    pg.set_row(pg.all_rows[act["name"]])
    pg.rows["brightness"].w.setValue(20)
    pg.set_row(pg.rows["brightness"])                                  # not risky: no dialog
    settle(pg)
    assert len(asked) == 3 and [" ".join(c[2:]) for c in fb.calls] == [
        f"settings set {act['name']} 1 --unit 3", "settings set brightness 20 --unit 3"], fb.calls
    print("ok risky and action rows ask first (cancel sends nothing), plain rows do not")


def read_only_unit():
    pg, fb, _ = make("gui_ro")
    pg.states["2"].info = {**pg.states["2"].info, "test": False}
    pg.select_unit("2", read=False)
    assert not pg.writable() and not pg.rows["brightness"].btn.isEnabled() and not pg.quick["volume"].btn.isEnabled()
    assert all(not sr.btn.isEnabled() for sr in pg.all_rows.values())
    pg.set_row(pg.rows["brightness"])
    pg.probe_tick()
    settle(pg)
    assert not [c for c in fb.calls if c[-1] == "2"], fb.calls          # no write, no probe
    assert pg.states["2"].dot() == "unknown"
    print("ok a unit without test=true is greyed, nothing is sent to it")


def parallel_jobs():
    fb = GateBackend()
    pg, fb, _ = make("gui_jobs", fb)
    fb.gated = {"1", "3"}
    pg.select_unit("1", read=False)
    pg.run("slow a", ["x", "--unit", "1"], None)
    pg.select_unit("3", read=False)
    pg.run("slow b", ["x", "--unit", "3"], None)
    until(lambda: fb.max_all == 2, "two units' jobs running at once")
    assert pg.states["1"].dot() == "busy" and pg.states["3"].dot() == "busy"
    fb.gate.set()
    settle(pg)
    assert pg.states["1"].pending == 0 and pg.states["3"].pending == 0
    assert fb.max_unit["1"] == 1 and fb.max_unit["3"] == 1
    # same unit: the second waits for the first
    fb2 = GateBackend()
    pg2, fb2, _ = make("gui_jobs2", fb2)
    fb2.gated = {"1"}
    pg2.select_unit("1", read=False)
    pg2.run("one", ["x", "--unit", "1"], None)
    pg2.run("two", ["y", "--unit", "1"], None)
    until(lambda: fb2.active["1"] == 1, "first job running")
    QTest.qWait(100)                                                   # the second would have started by now
    assert fb2.active["1"] == 1 and len(fb2.calls) == 0
    fb2.gate.set()
    settle(pg2)
    assert fb2.max_unit["1"] == 1 and [c[0] for c in fb2.calls] == ["x", "y"], (fb2.max_unit, fb2.calls)
    print("ok jobs of two units run concurrently, two jobs of one unit run one after the other")


def remembered():
    pg, fb, ini = make("gui_mem")
    pg.select_unit("2", read=False)
    pg.tree.setCurrentItem(pg.items["volume"])
    pg.select_unit("3", read=False)
    pg.tree.setCurrentItem(pg.items["gamma"])
    pg.select_unit("2", read=False)
    assert pg.states["2"].node == "row:volume" and pg.tree.currentItem() is pg.items["volume"]
    pg.select_unit("3", read=False)
    assert pg.tree.currentItem() is pg.items["gamma"]
    pg.rows["gamma"].w.setCurrentIndex(3)                              # a touched row stays with its unit
    pg.rows["gamma"]._touched()
    pg.select_unit("2", read=False)
    assert pg.rows["gamma"].w.currentIndex() == 0 and not pg.rows["gamma"].dirty
    pg.select_unit("3", read=False)
    assert pg.rows["gamma"].w.currentIndex() == 3 and pg.rows["gamma"].dirty
    pg.settings.sync()
    pg2 = MON.MonitorPage(FakeBackend(), WORK / "gui_mem2.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    assert pg2.cur == "3" and pg2.tree.currentItem() is pg2.items["gamma"], (pg2.cur, pg2.tree.currentItem().text(0))
    pg2.select_unit("2", read=False)
    assert pg2.tree.currentItem() is pg2.items["volume"]
    print("ok last unit and the tree node per unit are remembered (QSettings), touched values stay with their unit")


def detect_and_probe():
    units = MON.load_units()
    seen = {units["1"]["serial"], units["3"]["serial"]}
    pg, fb, _ = make("gui_detect", detect=lambda: seen)
    assert pg.states["2"].detected is False and pg.states["1"].detected and pg.states["2"].dot() == "down"
    pg.probe_tick()
    settle(pg)
    probed = sorted(c[-1] for c in fb.calls if "ddc" in c and "get" in c)
    assert probed == ["1", "3"], probed                                # absent unit 2 is not probed
    assert pg.states["1"].dot() == "ok" and pg.states["3"].dot() == "ok"
    fb.fail = (1, "AWT26110003: no bus with that EDID serial\n")
    pg.probe_tick()
    settle(pg)
    assert "down" in {pg.states["1"].dot(), pg.states["3"].dot()}
    seen.add(units["2"]["serial"])                                     # hotplug: the next scan finds it
    pg.probe_tick()
    settle(pg)
    assert pg.states["2"].detected is True
    print("ok scan marks absent units (no probe), probes set green / red dots, hotplug is picked up")


def screenshot(app):
    units = MON.load_units()
    pg, fb, _ = make("gui_shot", detect=lambda: {u["serial"] for u in units.values()})
    pg.select_unit("3", read=False)
    pg.get_all()
    pg.select_unit("1", read=False)
    pg.get_all()
    pg.select_unit("2", read=False)
    pg.get_all()
    settle(pg)
    pg.probe_tick()
    settle(pg)
    pg.tree.collapseAll()
    pg.page_items[4].setExpanded(True)
    pg.page_items[1].setExpanded(True)
    pg.tree.setCurrentItem(pg.items["d1_enable"])
    pg.states["2"].banner = ""
    pg.say("unit 2 selected")
    pg.resize(1500, 860)
    pg.show()
    settle(pg)
    pg.states["1"].status = "down"                                      # red: no answer
    pg.states["3"].pending = 1                                          # amber: a job on unit 3
    pg._strip_text("1")
    pg._strip_text("3")
    app.processEvents()
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / "monitor-gui.png"
    pg.grab().save(str(out))
    pg.states["3"].pending = 0
    pg.hide()
    print("screenshot", out)


def main():
    app = QApplication([])
    WORK.mkdir(parents=True, exist_ok=True)
    strip_and_hotkeys(app)
    tree_and_search()
    risky_confirm()
    read_only_unit()
    parallel_jobs()
    remembered()
    detect_and_probe()
    screenshot(app)
    print("PASS")


if __name__ == "__main__":
    main()
