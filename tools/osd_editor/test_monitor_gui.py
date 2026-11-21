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


class FailUnit3(FakeBackend):
    fail_unit3 = False

    def run(self, argv, limit_s):
        if self.fail_unit3 and "3" == str(argv[list(map(str, argv)).index("--unit") + 1]) and "ddc" in argv:
            return 1, "AWT26110003: no bus with that EDID serial\n"
        return super().run(argv, limit_s)


class ReadbackBackend(FakeBackend):
    """`settings get NAME` answers with a chosen raw value (what the unit reports back after a write)"""
    readback = {}

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        if "settings" in a and "get" in a and a[a.index("get") + 1] in self.readback:
            a = [x for x in a if x != "--direct"]
            self.calls.append(a)
            n = a[a.index("get") + 1]
            return 0, f"{n} = x (raw {self.readback[n]})\n"
        return super().run(argv, limit_s)


def click(w):
    QTest.mouseClick(w, Qt.LeftButton)


def writes(fb):
    return [" ".join(c[2:]) for c in fb.calls if ("set" in c and ("settings" in c or "ddc" in c)) or "kvm.py" in " ".join(c)]


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
    got = [" ".join(c[2:]) for c in fb.calls]
    assert got == ["ddc get 0x62 0x8D 0x10 0x60 0xEB --unit 2", "settings list --unit 2"], got
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
    assert pg.tree.topLevelItemCount() == len(pages)
    total = 0
    for i in range(len(pages)):
        pi = pg.tree.topLevelItem(i)
        p = pi.data(0, MON.PAGE_ROLE)
        assert pi.childCount() == pages[p] and pi.text(0).endswith(f"({pages[p]})"), (pi.text(0), pages[p])
        total += pi.childCount()
    assert total == len(MON.T.ROWS)
    assert sum("[risky]" in it.text(0) for it in pg.items.values()) == 11
    assert sum("[action]" in it.text(0) for it in pg.items.values()) == 6
    pg.search.setText("volume")
    vis = [n for n, it in pg.items.items() if not it.isHidden()]
    assert "volume" in vis and 0 < len(vis) < 10, vis
    assert sum(not pg.tree.topLevelItem(i).isHidden() for i in range(len(pages))) < len(pages)
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
    print("ok tree: pages and rows from the registry, counts match settings_table; search filters by name, label, id and VCP; Enter jumps")


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
    pg.rows["brightness"].set_value(20)
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
    pg, fb, _ = make("gui_detect", FailUnit3(), detect=lambda: seen)
    assert pg.states["2"].detected is False and pg.states["1"].detected and pg.states["2"].dot() == "down"
    pg.probe_tick()
    settle(pg)
    probed = sorted(c[-1] for c in fb.calls if "ddc" in c and "get" in c)
    assert probed == ["1", "3"], probed                                # absent unit 2 is not probed
    assert pg.states["1"].dot() == "ok" and pg.states["3"].dot() == "ok"
    fb.fail_unit3 = True
    pg.probe_tick()
    settle(pg)
    assert pg.states["3"].dot() == "ok" and pg.states["1"].dot() == "ok"             # one miss is a glitch: dot stays
    pg.probe_tick()
    settle(pg)
    assert pg.states["3"].dot() == "down" and pg.states["1"].dot() == "ok"           # two misses in a row: red
    fb.fail_unit3 = False
    pg.probe_tick()
    settle(pg)
    assert pg.states["3"].dot() == "ok"
    seen.add(units["2"]["serial"])                                     # hotplug: the next scan finds it
    n0 = len(fb.calls)
    pg.probe_tick()
    settle(pg)
    assert pg.states["2"].detected is True
    assert MON.probe_policy(units["2"]) == "light" and MON.probe_policy(units["1"]) == "ddc"
    assert pg.states["2"].dot() == "ok"                                # DP AUX unit: dot from the scan, never a DDC call
    assert sorted(c[-1] for c in fb.calls[n0:] if "ddc" in c) == ["1", "3"], fb.calls[n0:]
    print("ok scan marks absent units (no probe), probes set green / red dots, hotplug is picked up, DP AUX unit gets the light probe")


def advanced_pages():
    pg, fb, ini = make("gui_adv")
    hidden = lambda: [pg.page_items[p].isHidden() for p in pg.page_items]            # noqa: E731
    adv = [p for p, name in MON.PAGES.items() if name in MON.ADVANCED_PAGES]
    assert len(adv) == 2 and not pg.adv.isChecked()
    assert [p for p, it in pg.page_items.items() if it.isHidden()] == adv, "debug + service hidden by default"
    pg.search.setText("debug")                                                       # search skips hidden pages
    assert all(pg.page_items[p].isHidden() for p in adv)
    pg.search.clear()
    pg.adv.setChecked(True)
    assert not any(hidden()) and pg.settings.value("monitor/advanced") == "true"
    pg.tree.setCurrentItem(pg.page_items[adv[0]])
    pg.adv.setChecked(False)                                                         # the selected page goes away
    assert pg.tree.currentItem() is pg.page_items[0] and pg.states[pg.cur].node == "page:0"
    pg.adv.setChecked(True)
    pg.settings.sync()
    pg2 = MON.MonitorPage(FakeBackend(), WORK / "gui_adv2.log", QSettings(str(ini), QSettings.IniFormat), detect=lambda: set())
    assert pg2.adv.isChecked() and not any(pg2.page_items[p].isHidden() for p in adv)
    print("ok show advanced: debug + service hidden by default, remembered in QSettings, selection leaves a hidden page")


def unknown_units():
    units = MON.load_units()
    seen = {u["serial"] for u in units.values()} | {"UK52307000611"}
    pg, fb, _ = make("gui_unknown", detect=lambda: seen)
    names = list(pg.states)
    assert names[-1] == "?UK52307000611" and pg.states[names[-1]].unknown and len(pg.unit_btns) == len(units) + 1
    b = pg.unit_btns[names[-1]]
    assert "unknown" in b.text() and "not in devices.json" in b.toolTip() and pg.states[names[-1]].dot() == "unknown"
    pg.select_index(len(units))                                                      # hotkey reaches it
    assert pg.cur == names[-1] and not pg.writable()
    assert "unknown monitor" in pg.state.text() and all(not x.isEnabled() for x in pg.buttons)
    fb.calls.clear()
    pg.probe_tick()
    pg.set_row(pg.rows["brightness"])
    pg.get_all()
    settle(pg)
    assert all(c[-1] in units for c in fb.calls) and not any("set" in c for c in fb.calls), fb.calls   # only the listed units are probed
    seen.discard("UK52307000611")                                                    # unplugged: the button goes, view falls back
    pg.probe_tick()
    settle(pg)
    assert "?UK52307000611" not in pg.states and len(pg.unit_btns) == len(units) and pg.cur in units
    print("ok monitors seen by EDID but not in devices.json show as read-only unknown units, never touched, gone when unplugged")


def last_read_tooltip():
    pg, fb, _ = make("gui_lastread", fresh=False)
    assert "not read yet" in pg.unit_btns["3"].toolTip()
    pg.select_unit("3")
    settle(pg)
    tip = pg.unit_btns["3"].toolTip()
    assert "last read 20" in tip and "T" in tip and "not read yet" not in tip, tip
    print("ok strip tooltip carries the per-unit last-read time")


def quick_reads():
    pg, fb, _ = make("gui_quickread")
    pg.select_unit("3", read=False)
    pg.quick_get()
    settle(pg)
    assert pg.quick["volume"].w.value() == 37 and pg.quick["mute"].w.currentIndex() == 1 and pg.quick["brightness"].w.value() == 64
    assert pg.inp.currentText() == "D2" and "input D2 HDMI" in pg.now_state.text() and "screensaver Stop" in pg.now_state.text(), pg.now_state.text()
    assert pg.states["3"].values["volume"] == 37 and not any("settings" in c for c in fb.calls), fb.calls    # DDC only, no mailbox
    assert len(fb.calls) == 1, fb.calls                                              # one call (one ddcutil detect) for all five
    print("ok quick strip reads volume / mute / brightness / input / screensaver by VCP code, no mailbox")


def switch_and_parallel_speed():
    fb = GateBackend()
    pg, fb, _ = make("gui_speed", fb)
    for n in ("1", "2", "3"):
        pg.select_unit(n, read=False)
        pg.get_all(n)
    settle(pg)
    pg.show()
    settle(pg)
    t0 = time.perf_counter()
    for i in range(30):
        pg.select_unit(("1", "2", "3")[i % 3], read=False)
    ms = (time.perf_counter() - t0) / 30 * 1000
    assert ms < 100, ms                                                              # a switch is a view swap
    print(f"ok unit switch = {ms:.1f} ms per switch (offscreen, fake values, no read)")
    pg.hide()
    fb.gated = {"1", "2", "3"}
    for n in ("1", "2", "3"):
        pg.get_all(n)
    until(lambda: fb.max_all == 3, "three Get all at once")
    fb.gate.set()
    settle(pg)
    assert all(st.pending == 0 for st in pg.states.values())
    print("ok three units' Get all run in parallel")


def one_click_rows():
    plain = lambda r: r["type"] != "action" and not {"ro", "risky"} & set(r["flags"])        # noqa: E731
    boolr = next(r for r in MON.T.ROWS if r["type"] == "bool" and plain(r))
    enum3 = next(r for r in MON.T.ROWS if r["type"] == "enum" and len(r["options"]) == 3 and plain(r))
    big = next(r for r in MON.T.ROWS if r["type"] == "enum" and len(r["options"]) > MON.SEGMENT_MAX and not MON.live_row(r))
    kinds = {"bool": 0, "seg": 0, "combo": 0, "slider": 0}
    for r in MON.T.ROWS:
        if r["type"] != "action":
            kinds["bool" if r["type"] == "bool" else "slider" if r["type"] == "int" else "seg" if MON.instant_options(r) else "combo"] += 1
    assert sum(kinds.values()) == sum(r["type"] != "action" for r in MON.T.ROWS) and min(kinds.values()) > 0, kinds
    fb = ReadbackBackend()
    pg, fb, _ = make("gui_click", fb)
    pg.select_unit("3", read=False)
    pg.show()
    settle(pg)
    fb.calls.clear()
    fb.readback = {boolr["name"]: 1, enum3["name"]: 2}
    sr = pg.rows[boolr["name"]]
    assert sr.instant and sr.btn.isHidden() and isinstance(sr.w, MON.Choice) and sr.w.switch
    assert isinstance(pg.rows[big["name"]].w, MON.QComboBox) and not pg.rows[big["name"]].btn.isHidden()
    sr.w.setCurrentIndex(0)
    click(sr.w.btns[0])                                                              # flip 0 -> 1: one write, then the read-back
    settle(pg)
    assert writes(fb) == [f"settings set {boolr['name']} {boolr['min'] + 1} --unit 3"], fb.calls
    assert sr.w.currentIndex() == 1 and "unit: " in sr.cur.text() and not sr.dirty
    fb.readback[boolr["name"]] = 0
    click(sr.w.btns[0])                                                              # A then B: second click flips back
    settle(pg)
    assert writes(fb)[-1] == f"settings set {boolr['name']} {boolr['min']} --unit 3" and len(writes(fb)) == 2
    assert sr.w.currentIndex() == 0 and sr.cur.text().startswith(f"unit: {boolr['min']}"), sr.cur.text()
    # segmented enum: a click on a segment writes that option, the read-back is what the unit reports
    seg = pg.rows[enum3["name"]]
    assert seg.instant and not seg.w.switch and len(seg.w.btns) == 3 and not any(b.isHidden() for b in seg.w.btns)
    n0 = len(writes(fb))
    click(seg.w.btns[2])
    settle(pg)
    click(seg.w.btns[0])
    settle(pg)
    assert writes(fb)[n0:] == [f"settings set {enum3['name']} {enum3['min'] + 2} --unit 3", f"settings set {enum3['name']} {enum3['min']} --unit 3"]
    assert seg.w.currentIndex() == 0 or fb.readback[enum3["name"]] != 0              # shows the unit's answer, not the click
    # a failed write puts the widget back
    fb.fail_on.append((f"settings set {enum3['name']} {enum3['min'] + 1}", 1, "write failed\n"))   # keyed to this write: a timer job cannot take it
    before = seg.w.currentIndex()
    click(seg.w.btns[1])
    settle(pg)
    assert seg.w.currentIndex() == before and not seg.dirty, (seg.w.currentIndex(), before)
    # risky one-click rows ask first: cancel = no write and the widget stays; yes = exactly one write
    risky = next(r for r in MON.T.ROWS if "risky" in r["flags"] and instant_ok(r))
    rr = pg.rows[risky["name"]]
    n0 = len(writes(fb))
    asked = []
    pg.confirm = lambda t: (asked.append(t), False)[1]
    was = rr.w.currentIndex()
    click(rr.w.btns[0 if rr.w.switch else (1 if was != 1 else 0)])
    settle(pg)
    assert len(asked) == 1 and len(writes(fb)) == n0 and rr.w.currentIndex() == was, (asked, was, rr.w.currentIndex())
    pg.confirm = lambda t: (asked.append(t), True)[1]
    click(rr.w.btns[0 if rr.w.switch else (1 if was != 1 else 0)])
    settle(pg)
    assert len(asked) == 2 and len(writes(fb)) == n0 + 1
    # quick strip: mute is a switch, input a segmented row; one click = one write
    assert pg.quick["mute"].w.switch and pg.quick["mute"].instant
    n0 = len(writes(fb))
    pg.quick["mute"].w.setCurrentIndex(0)
    click(pg.quick["mute"].w.btns[0])
    settle(pg)
    assert writes(fb)[n0:] == ["ddc set 0x8D 1 --unit 3"], writes(fb)
    click(pg.inp.btns[2])
    settle(pg)
    assert writes(fb)[-1] == "D3 --units 3" and len(writes(fb)) == n0 + 2, writes(fb)
    # read-only unit: the one-click widgets are greyed
    pg.select_unit("1", read=False)
    pg.states["1"].info = {**pg.states["1"].info, "test": False}
    pg.select_unit("1", read=False)
    assert not sr.w.isEnabled() and not pg.quick["mute"].w.isEnabled() and not pg.inp.isEnabled()
    pg.hide()
    print("ok one-click rows: bool = switch, 2..4 options = segmented, larger enum = combo; one write per click, read-back shown, "
          "A then B flips, failed / cancelled flip reverts, risky asks first, quick mute / input use them, greyed on a read-only unit")


def instant_ok(r):
    return r["type"] != "action" and MON.instant_options(r) is not None


def ddc_serialised():
    """ddc calls of different units never overlap (each runs a detect over all buses); other jobs still run in parallel"""
    fb = GateBackend()
    pg, fb, _ = make("gui_ddclock", fb)
    fb.gated = {"1", "2", "3"}
    for n in ("1", "2", "3"):
        pg.run("probe", ["dev.py", "ddc", "get", "0x62", "--unit", n], None, "ddc", unit=n)
    QTest.qWait(150)
    fb.gate.set()
    settle(pg)
    assert fb.max_all == 1 and len(fb.calls) == 3, (fb.max_all, fb.calls)
    print("ok ddc calls of three units run one at a time")


def banner_reason():
    pg, fb, _ = make("gui_reason")
    pg.select_unit("1", read=False)
    fb.fail = (1, "bus 18: debug link ON\n2026-11-20T20:38:00 mailbox magic missing: firmware has not run vcp_box_service\n"
                  "2026-11-20 ERROR [dev.py] rc=1: settings_cli.py\n")
    pg.get_all()
    settle(pg)
    assert "mailbox magic missing" in pg.banner.text() and "does not answer" not in pg.banner.text(), pg.banner.text()
    assert pg.states["1"].dot() != "down"                                            # the unit answered, only the image lacks the mailbox
    fb.fail = (1, "map /x/tmp/fw/a.map not found (flash an image first, or --map PATH); nothing done\n")
    pg.get_all()
    settle(pg)
    assert "map /x/tmp/fw/a.map not found" in pg.banner.text() and pg.states["1"].dot() != "down"
    print("ok banner names the reason line (mailbox missing, map not found); those are not 'no answer'")


def real_backend_limit():
    """the real SubprocessBackend stops a hung call at its limit (unplugged unit, wedged dev.py): rc 124, bounded time"""
    import unit_jobs
    t0 = time.monotonic()
    rc, out = unit_jobs.SubprocessBackend().run(["python3", "-c", "import threading; threading.Event().wait()"], 0.5)
    dt = time.monotonic() - t0
    assert rc == 124 and "limit 0.5 s expired" in out and dt < 0.5 + unit_jobs.TERM_GRACE_S + 1, (rc, out, dt)
    print(f"ok a hung call is stopped at its limit: rc 124 after {dt:.2f} s")


def status_line():
    """status line (#277): read-only passes for the selected unit only, paused while it flashes or a drag runs, one pass at a time"""
    import unit_status as US
    pg, fb, _ = make("gui_status")
    for st in pg.states.values():
        st.track = None
    MON.flash_state = lambda serial: ""
    pg.cur = "3"
    pg.select_unit("3", read=False)
    pg.status_tick()
    until(lambda: pg.states["3"].sline, "first status pass")
    txt = pg.status_label.text()
    for want in ("CPU 350.8 PLL 350.8 SPI 116.9", "1920x1080 60.000Hz", "sound muted vol 50", "bright 51", "contrast 75", "PWM 125 (51 %)",
                 "loop 4100/s", "fw wb-test", "power On", "input D2 HDMI"):
        assert want in txt, (want, txt)
    assert "[" not in txt, ("a complete pass shows no error tag", txt)
    serials = {s for _, s in fb.status_calls}
    assert serials == {pg.states["3"].info["serial"]}, serials              # selected unit only
    assert not any(c[0] == "set" for c in fb.live_calls) and not writes(fb), "the status line never writes"
    settle(pg)
    n0 = len(fb.status_calls)                                                # flashing: no pass, the line says so
    pg.states["3"].track = type("T", (), {"live": lambda s, ser: (True, ""), "job": {"id": "j1"},
                                          "progress": type("P", (), {"percent": lambda s: 47.0, "rc": None})()})()
    pg.status_tick()
    settle(pg)
    assert len(fb.status_calls) == n0 and "status reads paused" in pg.status_label.text(), pg.status_label.text()
    pg.states["3"].track = None
    pg.live_writer.begin("3", "brightness", 50)                              # a drag runs: no pass behind its writes
    pg.status_tick()
    settle(pg)
    assert len(fb.status_calls) == n0
    pg.live_writer.release("3", "brightness", 50)
    until(lambda: not pg.live_writer.any_busy("3"), "drag release")
    pg.states["3"].sline_busy = True                                         # a pass in flight: never a second one
    pg.status_tick()
    settle(pg)
    assert len(fb.status_calls) == n0
    pg.states["3"].sline_busy = False
    pg.status_tick()                                                         # a failed source is named, the rest stays
    fb.status_reply = {**fb.status_reply, "dbg": None, "dbg_err": "clocks n/a: 0x35 not answering (debug link is on the DDC side)"}
    pg.states["3"].sline = {}
    pg.status_tick()
    until(lambda: pg.states["3"].sline.get("dbg_err"), "pass without debug link")
    txt = pg.status_label.text()
    assert "CPU n/a PLL n/a SPI n/a" in txt and "1920x1080 60.0Hz" in txt and "loop 4100/s" in txt and "sound muted vol 50" in txt and "[dbg_err: clocks n/a: 0x35 not answering" in txt, txt
    pg.select_unit("1", read=False)                                          # another unit: its own (empty) line, no read of unit 3
    pg.states["1"].sline = {}
    assert "reading" in pg.status_text("1") or "read-only" in pg.status_text("1")
    print("ok status line: selected unit only, read-only, paused while flashing / dragging, one at a time, failed source named")


def status_clocks():
    """the clock decode matches the firmware title formula (fw/osd/console.c AwtoPutClocks): crystal = CPU only"""
    import unit_status as US
    assert US.clocks(0, 0, 0, 0, 0x00, 0) == {"cpu": 14.318, "pll": None, "spi": None}
    c = US.clocks(0x5E, 0x0D | 0x10, 0x30, 0x03, 0x0A, 0x08)     # M = 0x5E + 0x300 + 2, N = 0x0D + 2, O = 2, FFED div 2
    pll = 14.318 * (0x35E + 2) / ((0x0D + 2) * 2)
    assert abs(c["pll"] - pll) < 1e-9 and abs(c["cpu"] - pll / 2 / 2) < 1e-9 and abs(c["spi"] - pll / 2 / 3) < 1e-9, c
    assert US.backlight_pct(0) == 100 and US.backlight_pct(255) == 0 and US.backlight_pct(125) == 51
    print("ok status clocks + PWM decode")


def screenshot(app):
    units = MON.load_units()
    pg, fb, _ = make("gui_shot", detect=lambda: {u["serial"] for u in units.values()} | {"UK52307000611"})
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
    real = {"1": dict(volume=100, mute=1, brightness=64, input=1), "2": dict(volume=100, mute=1, brightness=100, input=0),
            "3": dict(volume=50, mute=1, brightness=51, input=1)}      # values read live from the three units, 2026-11-20
    for n, v in real.items():
        pg.states[n].values.update(v)
        pg.states[n].last_read_iso = "2026-11-20T20:43:05+11:00"
        pg._strip_text(n)
    for n in ("1", "2", "3"):
        pg.states[n].status = "ok"
        pg._strip_text(n)
    pg.select_unit("1", read=False)                                     # reload the stored values into the form
    pg.states["1"].sline = {**FakeBackend.status_reply, "serial": pg.states["1"].info["serial"]}
    pg.status_show("1")
    pg.tree.setCurrentItem(pg.items["d1_enable"])
    app.processEvents()
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / "monitor-gui.png"
    pg.grab().save(str(out))
    pg.hide()
    print("screenshot", out)


class RingBackend(FakeBackend):
    """`synclog --json` answers a ring of `count` lines (the unit's serial from devices.json)"""
    count = 5

    def run(self, argv, limit_s):
        a = [str(x) for x in argv]
        if "synclog" in a and "--json" in a:
            import json as _json
            unit = MON.load_units()[a[a.index("--unit") + 1]]
            ents = [{"seq": k, "raw": f"01{k:02x}000100000000", "text": f"    {k}:mark {k}", "id": 1, "val": 0, "wall": None, "sure": False}
                    for k in range(self.count)]
            snap = {"serial": unit["serial"], "read": "2026-11-21T10:00:00.000+10:00", "seq": self.count, "n": 80, "wrap": 240, "ep_seq": 0,
                    "kind": "power on", "lost": 0, "entries": ents}
            return 0, "2026-11-21T10:00:00+10:00 SYNCJSON " + _json.dumps(snap) + "\n"
        return super().run(argv, limit_s)


def unit_log_tab(app):
    """Unit log tab: Read now appends the ring to the saved log, a second read adds only new lines, search filters, Save as writes the file"""
    import unit_log
    unit_log.LOGDIR = WORK / "units"
    for f in unit_log.LOGDIR.glob("*") if unit_log.LOGDIR.exists() else []:
        f.unlink()
    fb = RingBackend()
    pg, fb, _ = make("gui_ulog", fb)
    pg.show()
    settle(pg)
    pg.select_unit("3", read=False)
    assert pg.log_tabs.tabText(1) == "Unit log"
    pg.unit_log_read()
    settle(pg)
    assert len(pg.unit_log_text().splitlines()) == 5 and "5 of 5 saved lines" in pg.ulog_info.text(), pg.ulog_info.text()
    pg.unit_log_read()                                   # nothing new: the log is not wiped, not doubled
    settle(pg)
    assert len(pg.unit_log_text().splitlines()) == 5
    fb.count = 8
    pg.unit_log_read()
    settle(pg)
    assert len(pg.unit_log_text().splitlines()) == 8 and "mark 7" in pg.ulog.toPlainText()
    pg.ulog_search.setText("mark 3")
    assert "1 of 8 saved lines matching" in pg.ulog_info.text() and pg.ulog.toPlainText().count("mark") == 1
    dest = WORK / "units" / "saved-copy.log"
    assert pg.unit_log_save_as(str(dest)) == str(dest) and len(dest.read_text().splitlines()) == 8
    pg.hide()
    print("ok unit log tab")


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
    advanced_pages()
    unknown_units()
    last_read_tooltip()
    quick_reads()
    switch_and_parallel_speed()
    one_click_rows()
    ddc_serialised()
    banner_reason()
    real_backend_limit()
    unit_log_tab(app)
    status_clocks()
    status_line()
    screenshot(app)
    print("PASS")


if __name__ == "__main__":
    main()
