"""Offscreen test of the reference monitor pane (#390): fake bus, no hardware; screenshot -> tmp/scratch/qt/reference_pane.png.
QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_reference_pane.py [--hw]
--hw: one live read-only pass of the real monitor for the screenshot (standard Get VCP only; the write toggle stays off)."""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference as P
from PySide6.QtWidgets import QApplication

ROOT = P.ROOT
sys.path.insert(0, str(ROOT / "tests"))
SHOTS = ROOT / "tmp" / "scratch" / "qt"
WAIT_S = 3.0                                    # a fake pass of 30 codes is instant (fake clock); 3 s = the worker is stuck
HW_WAIT_S = 5.7                                 # one real pass: 30 codes x (110 ms gap + 40 ms reply) = 4.5 s, x1.25; expiry = AssertionError


def fake_ddc():
    from reference_fakes import PHILIPS, Clock, FakeMonitor
    clk = Clock()
    FakeMonitor.log, FakeMonitor.clock = [], clk
    FakeMonitor.values = {0x10: (100, 100), 0x12: (50, 100), 0x14: (0x05, 0x0B), 0x16: (100, 100), 0x18: (100, 100),
                          0x1A: (100, 100), 0x72: (0x78, 0xFB), 0x60: (0x2F0F, 0x200E), 0x62: (82, 100), 0xC0: (0x367D, 0xFFFF),
                          0xD6: (1, 4), 0x8D: (2, 2), 0xE0: (3, 4), 0xE9: (2, 2), 0xEC: (0, 0x0403), 0xF7: (0x42, 0x42)}
    import reference_mon as R
    d = R.ReferenceDdc(PHILIPS, find=lambda ref: 11, guard=lambda b, s: None, bus_cls=FakeMonitor, clock=clk, nap=clk.nap)
    return d, FakeMonitor


def wait(app, cond, limit_s):
    t0 = time.monotonic()
    while not cond():
        if time.monotonic() - t0 > limit_s:
            raise AssertionError(f"not reached in {limit_s} s")
        app.processEvents()
        time.sleep(0.01)


def fake_pane(app):
    d, mon = fake_ddc()
    pane = P.ReferencePane("philips", d.ref, ddc=d, log_path=ROOT / "tmp" / "logs" / "test_reference_pane.log")
    pane.live.setChecked(False)                  # one pass, not a loop: the fake answers at once
    pane.resize(1180, 820)
    pane.show()
    wait(app, lambda: pane.table.item(pane.rows[0xA8], 2).text() != "-", WAIT_S)
    assert pane.table.item(pane.rows[0x14], 2).text() == "6500K"
    assert pane.table.item(pane.rows[0x60], 2).text() == "DP-1"
    assert pane.table.item(pane.rows[0xC0], 2).text() == "13949 h"
    assert pane.table.item(pane.rows[0xEC], 3).text() == "04 03 00 00"
    assert pane.table.item(pane.rows[0xA8], 2).text().startswith("unsupported")   # result 1: shown, pass goes on
    assert "last error" not in pane.info.text()
    print("ok pass: decoded standard values, raw manufacturer bytes, unsupported shown")

    assert not pane.writes.isChecked() and not any(b.isEnabled() for b in pane.set_btns.values())
    n = len(mon.log)
    pane.set_code(0x10)
    app.processEvents()
    assert len(mon.log) == n, "a write went out with the toggle off"
    print("ok writes off by default: Set buttons disabled, no frame sent")

    pane.writes.setChecked(True)
    pane.w_widgets[0x10].setValue(70)
    pane.set_code(0x10)
    wait(app, lambda: any(isinstance(f, bytes) and f[2] == 0x03 for _t, _a, f in mon.log), WAIT_S)
    sets = [f for _t, a, f in mon.log if isinstance(f, bytes) and f[2] == 0x03]
    import unit_ops as U
    assert sets == [U.set_frame(0x10, 70)] and {a for _t, a, _f in mon.log} == {0x37}
    pane.hide()
    assert not pane.writes.isChecked(), "write toggle survives a hide"
    print("ok toggle on: one standard Set VCP 0x10 to 0x37; hide turns writes off again")
    pane.show()
    return pane


def hw_pane(app):
    pane = P.ReferencePane("philips")
    pane.live.setChecked(False)
    pane.resize(1180, 820)
    pane.show()
    wait(app, lambda: pane.table.item(pane.rows[0xA8], 2).text() != "-", HW_WAIT_S)
    print(f"ok hw pass: {pane.info.text()}")
    return pane


def main():
    app = QApplication([])
    SHOTS.mkdir(parents=True, exist_ok=True)
    pane = hw_pane(app) if "--hw" in sys.argv else fake_pane(app)
    app.processEvents()
    shot = SHOTS / ("reference_pane_hw.png" if "--hw" in sys.argv else "reference_pane.png")
    pane.grab().save(str(shot))
    pane.shutdown()
    print(f"screenshot {shot}")
    print("PASS")


if __name__ == "__main__":
    main()
