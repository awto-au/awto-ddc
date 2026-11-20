"""DDC/CI frames and the persistent-fd session of the fast VCP path (awto-ddc#277); fake bus, no hardware."""
import sys
import typing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unit_ops as U


def xor_sum(*bs):
    c = 0
    for b in bs:
        c ^= b
    return c


def test_set_frame_known_good():
    f = U.set_frame(0x10, 50)                                   # backlight 50: 51 84 03 10 00 32, chk = 6E ^ all
    assert f == bytes([0x51, 0x84, 0x03, 0x10, 0x00, 0x32, 0x9A])
    assert xor_sum(0x6E, *f) == 0
    g = U.set_frame(0x62, 0x1234)                               # two value bytes, big endian
    assert g[:6] == bytes([0x51, 0x84, 0x03, 0x62, 0x12, 0x34]) and xor_sum(0x6E, *g) == 0
    assert U.set_frame(0xD6, 4)[:6] == bytes([0x51, 0x84, 0x03, 0xD6, 0x00, 0x04])    # same body as tests/test_rtd_proto.py's frame


def test_set_frame_matches_kvm_and_dbg_link_builders():
    import dbg_link  # noqa: F401  (its _setvcp builds 0x84 0x03 code hi lo + 0x6E ^ 0x51 ^ ...)
    body = bytes([0x84, 0x03, 0x60, 0x00, 0x11])
    assert U.set_frame(0x60, 0x11) == bytes([0x51]) + body + bytes([xor_sum(0x6E, 0x51, *body)])


def test_get_frame_and_reply():
    assert U.get_frame(0x10) == bytes([0x51, 0x82, 0x01, 0x10, xor_sum(0x6E, 0x51, 0x82, 0x01, 0x10)])
    body = bytes([0x6E, 0x88, 0x02, 0x00, 0x10, 0x00, 0x00, 0x64, 0x00, 0x32])
    reply = body + bytes([xor_sum(0x50, *body)])
    assert U.parse_get_reply(reply, 0x10) == (50, 100)
    with pytest.raises(ValueError):
        U.parse_get_reply(reply[:-1] + b"\x00", 0x10)         # bad checksum
    with pytest.raises(ValueError):
        U.parse_get_reply(reply, 0x12)                        # reply for another code
    bad = bytearray(body)
    bad[3] = 1
    with pytest.raises(ValueError):
        U.parse_get_reply(bytes(bad) + bytes([xor_sum(0x50, *bad)]), 0x10)     # unsupported-code result


def test_set_frame_range():
    for c, v in ((256, 0), (0, 0x10000), (-1, 0), (0, -1)):
        with pytest.raises(ValueError):
            U.set_frame(c, v)


class FakeBus:
    opened: typing.ClassVar[list] = []

    def __init__(self, n):
        self.n, self.writes, self.reply, self.closed, self.fail = n, [], b"", False, None
        FakeBus.opened.append(self)

    def write(self, addr, reg, data):
        if self.fail:
            raise OSError(6, "NAK")
        self.writes.append((addr, bytes([reg]) + bytes(data)))

    def ops(self, addr, ops):
        return [self.reply[:ops[0]]]

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.t, self.naps = 0.0, []

    def __call__(self):
        return self.t

    def nap(self, s):
        self.naps.append(s)
        self.t += s


def session(clk):
    FakeBus.opened = []
    return U.DdcSession(11, "SER", bus_cls=FakeBus, clock=clk, nap=clk.nap, prove=False)


def test_session_one_fd_frames_spaced():
    clk = Clock()
    s = session(clk)
    s.set_vcp(0x10, 10)
    s.set_vcp(0x10, 11)
    assert len(FakeBus.opened) == 1 and [w[1] for w in FakeBus.opened[0].writes] == [U.set_frame(0x10, 10), U.set_frame(0x10, 11)]
    assert FakeBus.opened[0].writes[0][0] == 0x37
    assert clk.naps == [pytest.approx(U.MIN_FRAME_GAP_S)]       # the second frame waited out the gap (the fake clock does not advance on its own)


def test_session_paged_row_selects_once_then_values():
    clk = Clock()
    s = session(clk)
    s.set_vcp(0, 5, row_id=61)
    s.set_vcp(0, 6, row_id=61)
    s.set_vcp(0, 7, row_id=61, reselect=True)
    frames = [w[1] for w in FakeBus.opened[0].writes]
    assert frames == [U.set_frame(0xE0, 61), U.set_frame(0xE1, 5), U.set_frame(0xE1, 6), U.set_frame(0xE0, 61), U.set_frame(0xE1, 7)]


def test_session_error_closes_fd_and_reopens():
    clk = Clock()
    s = session(clk)
    s.set_vcp(0x10, 1)
    first = FakeBus.opened[0]
    first.fail = True
    with pytest.raises(OSError):
        s.set_vcp(0x10, 2)
    assert first.closed and s.bus is None
    s.set_vcp(0x10, 3)
    assert len(FakeBus.opened) == 2 and FakeBus.opened[1].writes[0][1] == U.set_frame(0x10, 3)


def test_session_get():
    clk = Clock()
    s = session(clk)
    s.open()
    body = bytes([0x6E, 0x88, 0x02, 0x00, 0x62, 0x00, 0x00, 0x64, 0x00, 0x25])
    s.bus.reply = body + bytes([xor_sum(0x50, *body)])
    assert s.get_vcp(0x62) == (37, 100)
    assert s.bus.writes[-1][1] == U.get_frame(0x62) and U.GET_WAIT_S in clk.naps


class FakeDev:
    """the dev module as unit_ops sees it: unit lookup, bus lookup, log, and the ddc_ctl runner (the old path)"""

    def __init__(self):
        self.logs, self.py = [], []

    def _unit(self, extra):
        return "1", {"serial": "SER"}

    def _bus(self, u):
        return 11

    def log(self, msg, level="INFO"):
        self.logs.append((level, msg))

    def _py(self, script, *args):
        self.py.append((script, args))
        return 0


def test_ddc_set_fast_path_and_fallback():
    U.SESSIONS.clear()
    FakeBus.opened = []
    d = FakeDev()
    U.BUS_CLS = FakeBus
    U.SESSIONS["SER"] = U.DdcSession(11, "SER", bus_cls=FakeBus, prove=False)
    assert U.ddc(d, ["set", "0x10", "50"]) == 0
    assert FakeBus.opened[0].writes == [(0x37, U.set_frame(0x10, 50))] and not d.py          # no ddcutil, no detect
    assert any("fast DDC/CI write ok" in m for _, m in d.logs)
    FakeBus.opened[0].fail = True                                                          # bus error: said out loud, then the old path
    assert U.ddc(d, ["set", "0x10", "60"]) == 0
    assert d.py == [("ddc_ctl.py", ("--bus", 11, "set", "0x10", "60"))]
    assert any(lv == "WARN" and "falling back to ddcutil" in m for lv, m in d.logs)
    assert U.ddc(d, ["get", "0x10"]) == 0 and d.py[-1][1][2] == "get"                      # reads / list / sleep stay on the old path
    U.SESSIONS.clear()
    U.SESSIONS.clear()
    U.BUS_CLS = U.i2cbus.Bus
