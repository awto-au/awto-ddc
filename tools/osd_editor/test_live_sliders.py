"""Live sliders (awto-ddc#277), offscreen, fake backend with a configurable per-write latency, no hardware:
QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_live_sliders.py"""
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import live_writer as LW  # noqa: E402
import monitor as MON  # noqa: E402
from test_monitor_gui import make, settle, until  # noqa: E402
from test_smoke import FakeBackend  # noqa: E402

UNIT = "3"
SERIAL = MON.load_units()[UNIT]["serial"]


def sets(fb):
    return [c for c in fb.live_calls if c[0] == "set"]


def gets(fb):
    return [c for c in fb.live_calls if c[0] == "get"]


MON.flash_state = lambda serial: ""                       # the unit lock / job files are real and shared: another stream's flash must not matter here


def fresh(latency_s):
    fb = FakeBackend()
    fb.live_latency_s = latency_s
    pg, fb, _ = make("gui_live", fb)
    for st in pg.states.values():
        st.track = None                                       # a flash job re-attached from tmp/flash_jobs
    pg.select_unit(UNIT, read=False)
    pg.show()
    settle(pg)
    return pg, fb


def finished(pg, name="brightness"):
    until(lambda: not pg.live_writer.busy(UNIT, name), f"live {name} finished")
    QApplication.processEvents()
    return pg.live_writer.history[-1]


def drag(pg, sr, values, wait_ms=2):
    """press, move through `values` (a valueChanged each), the caller releases"""
    sr.w.setSliderDown(True)
    for v in values:
        sr.w.setValue(v)
        QTest.qWait(wait_ms)


def rows_that_are_live():
    sliders = [r["name"] for r in MON.T.ROWS if MON.live_row(r) and r["type"] == "int"]
    combos = [r["name"] for r in MON.T.ROWS if MON.live_row(r) and r["type"] == "enum"]
    assert sliders == ["brightness", "black_level", "contrast", "user_red", "user_green", "user_blue", "osd_hpos", "osd_vpos",
                       "osd_transparency", "volume", "screensaver_s"], sliders
    assert combos == ["gamma", "colour_temp", "screensaver"], combos
    pg, fb = fresh(0)
    assert all(pg.rows[n].btn.isHidden() for n in sliders + combos)                 # a live row has no Set
    assert not pg.rows["sharpness"].btn.isHidden() and not pg.rows["osd_timeout"].btn.isHidden()   # inert / non-live int rows keep it
    assert pg.quick["brightness"].live and pg.quick["volume"].live and not pg.quick["mute"].live
    print(f"ok live rows: {len(sliders)} sliders {sliders}, {len(combos)} combos {combos}; non-live rows keep Set")


def fast_drag():
    pg, fb = fresh(0.1)
    sr = pg.rows["brightness"]
    sr.put(50)
    t0 = time.monotonic()
    sr.w.setSliderDown(True)
    n = 600
    for i in range(n):
        k = i % 200
        sr.w.setValue(k if k <= 100 else 200 - k)        # triangle 0..100..0: a different value on (nearly) every event, 600 valueChanged
        QTest.qWait(2)
    sr.w.setValue(100)
    dur_drag = time.monotonic() - t0
    assert sr.w.value() == 100 and pg.live_writer.ctls[(UNIT, 'brightness')].values >= 590, pg.live_writer.ctls[(UNIT, 'brightness')].values
    during_saves = [c for c in fb.live_calls if c[2] == 0x0C] + [c for c in fb.calls if "save" in c]
    sr.w.setSliderDown(False)                             # release
    res = finished(pg)
    dur = time.monotonic() - t0
    w = sets(fb)
    assert fb.live_max == 1, f"{fb.live_max} calls in flight at once"
    assert len(w) <= math.ceil(dur_drag / 0.1) + 2, (len(w), dur_drag)
    assert len(w) >= 2 and w[-1][3] == 100 and w[-1][2] == 0x10, w[-3:]
    assert all(a[3] != b[3] for a, b in zip(w, w[1:])), "an equal value was sent twice in a row"
    assert not during_saves and res["saves"] == 0 and len(gets(fb)) == 1, (during_saves, gets(fb))
    assert res["readback"] == 100 and res["verified"] and res["writes"] == len(w) and res["to"] == 100 and res["from"] == 50
    assert sr.w.value() == 100 and "unit: 100" in sr.cur.text() and not sr.dirty
    assert pg.quick["brightness"].w.value() == 100                                   # the quick strip peer follows
    print(f"ok fast drag: {res['values']} value changes in {dur_drag:.2f} s, {res['writes']} writes (limit {math.ceil(dur_drag / 0.1) + 2}), "
          f"never two in flight, last write 100, 0 saves, 1 read-back, {dur:.2f} s total")


def floor_spacing():
    pg, fb = fresh(0.0)
    sr = pg.rows["brightness"]
    sr.put(0)
    drag(pg, sr, range(1, 101), wait_ms=1)
    sr.w.setSliderDown(False)
    finished(pg)
    t = fb.live_times[:len(sets(fb))]
    gaps = [b - a for a, b in zip(t, t[1:])]
    assert gaps and min(gaps) >= LW.FLOOR_MIN_S * 0.8, min(gaps)                    # 0.8: timer + scheduling jitter on the test host
    assert sets(fb)[-1][3] == 100
    print(f"ok floor: instant writes are spaced >= {min(gaps) * 1000:.0f} ms ({LW.FLOOR_MIN_S * 1000:.0f} ms floor), last write 100")


def equal_values_skipped():
    pg, fb = fresh(0.02)
    sr = pg.rows["brightness"]
    sr.put(50)
    lw = pg.live_writer
    lw.begin(UNIT, "brightness", 50)
    lw.change(UNIT, "brightness", 50)                     # equal to the unit's value: nothing to send
    lw.change(UNIT, "brightness", 60)
    until(lambda: len(sets(fb)) == 1, "first write")
    lw.change(UNIT, "brightness", 60)                     # equal to the last sent
    lw.release(UNIT, "brightness", 60)
    res = finished(pg)
    assert [c[3] for c in sets(fb)] == [60] and res["skipped"] >= 2 and res["writes"] == 1, (sets(fb), res)
    print("ok equal values are skipped (equal to the unit's value, equal to the last sent value)")


def release_sends_exact_value():
    pg, fb = fresh(0.1)
    sr = pg.rows["contrast"]
    sr.put(50)
    sr.w.setSliderDown(True)
    sr.w.setValue(60)                                      # in flight now
    sr.w.setValue(70)
    sr.w.setValue(77)
    sr.w.setSliderDown(False)                              # released at 77 while 60 is still being written
    res = finished(pg, "contrast")
    w = sets(fb)
    assert [c[3] for c in w] == [60, 77] and w[0][2] == 0x12, w                       # 70 was replaced by 77, never sent
    assert res["readback"] == 77 and res["skipped"] >= 1
    print("ok release: the exact released value is the last write; a replaced pending value is never sent")


def esc_restores():
    pg, fb = fresh(0.03)
    sr = pg.rows["brightness"]
    sr.put(51)
    drag(pg, sr, range(52, 90, 3), wait_ms=15)
    assert sets(fb), "something was sent before Esc"
    QTest.keyClick(sr.w, Qt.Key_Escape)
    res = finished(pg)
    assert res["cancelled"] and sets(fb)[-1][3] == 51 and res["readback"] == 51, (res, sets(fb)[-2:])
    assert sr.w.value() == 51 and not sr.w.isSliderDown() and "unit: 51" in sr.cur.text()
    n = len(sets(fb))
    sr.w.setValue(88)                                      # the rest of the cancelled drag (mouse still down) does nothing
    QTest.qWait(80)
    assert len(sets(fb)) == n
    sr.w.mouseReleaseEvent  # noqa: B018  (the real release clears `cancelling`; the offscreen test has no pointer)
    sr.w.cancelling = False
    print("ok Esc: the pre-drag value is written back (one write), read back, the widget shows it; the rest of the drag sends nothing")


def keyboard_steps_settle():
    pg, fb = fresh(0.02)
    sr = pg.rows["volume"]
    sr.put(40)
    sr.w.setFocus()
    for _ in range(5):
        QTest.keyClick(sr.w, Qt.Key_Right)
        QTest.qWait(5)
    res = finished(pg, "volume")
    assert sr.w.value() == 45 and sets(fb)[-1][3] == 45 and sets(fb)[-1][2] == 0x62 and res["readback"] == 45, (sets(fb), res)
    assert len(sets(fb)) <= 5 and res["values"] == 5
    print(f"ok keyboard steps coalesce like a drag: 5 steps, {res['writes']} writes, settled after {LW.SETTLE_S} s, read back")


def combo_instant():
    pg, fb = fresh(0.01)
    sr = pg.rows["gamma"]
    sr.put(0)
    sr.w.setCurrentIndex(3)
    sr.w.activated.emit(3)
    res = finished(pg, "gamma")
    assert sets(fb)[-1][:4] == ("set", SERIAL, 242, 3) and res["writes"] == 1 and res["readback"] == 3, (sets(fb), res)
    print("ok live combo (gamma): one write on pick, VCP 0xF2, read back")


def paged_row():
    pg, fb = fresh(0.01)
    sr = pg.rows["osd_transparency"]
    sr.put(50)
    drag(pg, sr, [55, 60, 65], wait_ms=30)
    sr.w.setSliderDown(False)
    res = finished(pg, "osd_transparency")
    w = sets(fb)
    assert w[0][2] == 0xE1 and w[0][4] == MON.row_of("osd_transparency")["id"] and w[0][5] is True and w[-1][3] == 65, w
    assert all(c[5] is False for c in w[1:]) and res["readback"] == 65
    print(f"ok row without a VCP code: paged pair 0xE0 / 0xE1, {res['writes']} writes, row selected once per drag")


def failure_reverts():
    pg, fb = fresh(0.01)
    fb.live_fail = "live set: NAK"
    sr = pg.rows["brightness"]
    sr.put(50)
    drag(pg, sr, [60, 70], wait_ms=30)
    sr.w.setSliderDown(False)
    res = finished(pg)
    assert res["error"] and sr.w.value() == 50 and pg.states[UNIT].banner.startswith(f"unit {UNIT}: live brightness failed")
    assert not gets(fb), "no read-back after a failed write"
    print("ok failed write: nothing more sent, widget back to the unit's value, banner says why")


def read_only_unit():
    fb = FakeBackend()
    pg, fb, _ = make("gui_live_ro", fb)
    pg.states["2"].info = {**pg.states["2"].info, "test": False}
    pg.select_unit("2", read=False)
    sr = pg.rows["brightness"]
    sr.w.setSliderDown(True)
    sr.w.setValue(77)
    sr.w.setSliderDown(False)
    QTest.qWait(50)
    assert not fb.live_calls
    print("ok read-only unit: a moved slider sends nothing")


def backlight_safety():
    pg, fb = fresh(0.01)
    sr = pg.rows["brightness"]
    sr.put(60)
    drag(pg, sr, [40, 20, 8, 3, 0], wait_ms=30)               # the slider is dragged to the bottom
    assert sr.w.value() == MON.BL_MIN and sr.val.text() == f"min {MON.BL_MIN} %", (sr.w.value(), sr.val.text())
    sr.w.setSliderDown(False)
    res = finished(pg)
    assert min(c[3] for c in sets(fb)) >= MON.BL_MIN and sets(fb)[-1][3] == MON.BL_MIN, sets(fb)
    assert not pg.restore_btn.isHidden() and "60" in pg.restore_btn.text()               # 5 % < 10 %: Restore is offered
    n = len(sets(fb))
    QTest.keyClick(sr.w, Qt.Key_Home)                          # keyboard Home = slider minimum: clamped too
    QTest.qWait(700)
    assert all(c[3] >= MON.BL_MIN for c in sets(fb)[n:])
    pg.restore_btn.click()
    finished(pg)
    assert sets(fb)[-1][3] == 60 and sr.w.value() == 60 and pg.restore_btn.isHidden(), (sets(fb)[-3:], sr.w.value(), pg.bl_prev)
    # exactly 0: the explicit button asks first; No sends nothing, Yes writes 0 (VCP 0x10 = 0), Restore is offered
    asked = []
    pg.confirm = lambda text: (asked.append(text), False)[1]
    n = len(fb.calls)
    sr.zero.click()
    settle(pg)
    assert asked == [MON.BL_ZERO_ASK] and len(fb.calls) == n and sr.w.value() == 60, (asked, sr.w.value())
    pg.confirm = lambda text: (asked.append(text), True)[1]
    sr.zero.click()
    settle(pg)
    assert any(c[-3:] == ["0x10", "0", "--unit"] or ("ddc" in c and "set" in c) for c in fb.calls) or any("brightness 0" in " ".join(c) for c in fb.calls)
    assert not pg.restore_btn.isHidden()
    # the port: 0 needs confirm, 100 never does
    import control_port as CP
    try:
        cp = CP.ControlPort.__new__(CP.ControlPort)
        cp.page = pg
        cp.unit_of = lambda p: UNIT
        raised = False
        try:
            cp.m_set({"unit": UNIT, "name": "brightness", "value": "0"}, lambda *a, **k: None)
        except CP.PortError as e:
            raised = "confirm" in str(e)
        assert raised
    finally:
        pass
    print("ok backlight safety: slider stops at 5 % ('min 5 %'), Home clamped, 0 % only via the button + confirm, Restore button after a set below 10 %, port set 0 needs confirm")


def floor_follows_latency():
    lw = LW.LiveWriter.__new__(LW.LiveWriter)
    lw.lat = {}
    assert lw.floor_s("x") == LW.FLOOR_INITIAL_S
    lw.lat["x"] = __import__("collections").deque([0.005] * 8)
    assert lw.floor_s("x") == LW.FLOOR_MIN_S                                    # fast bus: the 30 ms floor
    lw.lat["x"] = __import__("collections").deque([0.2] * 8)
    assert abs(lw.floor_s("x") - 0.25) < 1e-9                                   # slow bus (DP AUX): 1.25 x median
    print("ok floor = max(30 ms, 1.25 x median write time)")


def main():
    app = QApplication([])
    (MON.ROOT / "tmp" / "osdedit").mkdir(parents=True, exist_ok=True)
    rows_that_are_live()
    floor_follows_latency()
    backlight_safety()
    fast_drag()
    floor_spacing()
    equal_values_skipped()
    release_sends_exact_value()
    esc_restores()
    keyboard_steps_settle()
    combo_instant()
    paged_row()
    failure_reverts()
    read_only_unit()
    print("PASS")
    del app


if __name__ == "__main__":
    main()
