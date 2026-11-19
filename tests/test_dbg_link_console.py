"""dbg_link.linked closes a console the block opened (ucHold bit1 clear before, set after), unless keep_console."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dbg_link


class FakeFw:
    def __init__(self):
        self.hold, self.cmd, self.cleared = 0, 0, 0


def patch(mp, fw, opened_in_block):
    mp.setattr(dbg_link, "on", lambda bus, minutes=10: "already")
    mp.setattr(dbg_link, "hold", lambda bus: fw.hold)
    mp.setattr(dbg_link, "close_console", lambda bus: (setattr(fw, "hold", 0), setattr(fw, "cleared", fw.cleared + 1), True)[2])
    mp.setattr(dbg_link, "off", lambda bus: True)
    return opened_in_block


def run(mp, fw, keep, pre_hold, opens):
    fw.hold = pre_hold
    patch(mp, fw, opens)
    with dbg_link.linked(1, keep_console=keep):
        if opens:
            fw.hold |= dbg_link.HOLD_POPUP


def test_closes_console_opened_in_block(monkeypatch):
    fw = FakeFw()
    run(monkeypatch, fw, False, 0, True)
    assert fw.cleared == 1 and fw.hold == 0


def test_keep_console_leaves_it(monkeypatch):
    fw = FakeFw()
    run(monkeypatch, fw, True, 0, True)
    assert fw.cleared == 0 and fw.hold == dbg_link.HOLD_POPUP


def test_console_already_open_before_is_not_touched(monkeypatch):
    fw = FakeFw()
    run(monkeypatch, fw, False, dbg_link.HOLD_POPUP, False)
    assert fw.cleared == 0
