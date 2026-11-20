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


class FakeDbgIo:
    """debug slave 0x35 over a memory image: byte path (0x01 hi, 0x3A lo, read 0x08) and block path (0x3C lo hi len seq); records every write"""

    def __init__(self, mem):
        self.mem, self.log, self.hi, self.cmd = mem, [], 0, None

    def write(self, dev8, sub, data):
        self.log.append((sub, bytes(data)))
        if sub == 0x01:
            self.hi = data[0]
        elif sub == 0x3A:
            self.cmd = ("byte", self.hi << 8 | data[0])
        elif sub == 0x3C:
            self.cmd = ("blk", data[1] << 8 | data[0], data[2], data[3])
        return True

    def read(self, dev8, sub, n):
        if self.cmd[0] == "byte":
            return bytes([self.mem.get(self.cmd[1], 0)])
        _, a, ln, seq = self.cmd
        body = bytes(self.mem.get(a + i, 0) for i in range(ln))
        return body + bytes([(seq + (a & 0xFF) + (a >> 8) + sum(body)) & 0xFF])

    def close(self):
        pass


def test_status_is_read_only_and_decodes(monkeypatch):
    import rtd_i2c_bridge as B
    import unit_status as S
    mem = {S.DIAG_BASE: 0x41, S.DIAG_BASE + 1: 0x44, S.DIAG_BASE + 2: 2, S.DIAG_BASE + S.DIAG_STAGE_OFS: 8,
           S.DIAG_BASE + S.DIAG_LOOP_OFS: 0x10, S.DIAG_BASE + S.DIAG_LOOP_OFS + 1: 0x04,       # big endian 4100
           S.PLL_E0: 0x5E, S.PLL_E1: 0x1D, S.PLL_E7: 0x30, S.MCU_FFE9: 3, S.MCU_FFED: 0x0A, S.MCU_FFEE: 0x08, S.FF_PWM4H_DUT: 125}
    io = FakeDbgIo(mem)
    monkeypatch.setattr(B, "Real", lambda bus, allow_write, regread=False: (setattr(io, "allow_write", allow_write), io)[1])
    bus = FakeBus(5)
    s = U.DdcSession(5, "AWT1", bus_cls=lambda n: bus, clock=Clock(), nap=lambda x: None, prove=False)
    import settings_table as T
    vals = {0x62: 50, 0x8D: 1, 0x10: 51, 0x12: 75, 0xD6: 1, 0x60: 17, U.VCP_VAL: 0}
    paged = {T.BY_NAME["info_hres"]["id"]: 1920, T.BY_NAME["info_vres"]["id"]: 1080, T.BY_NAME["info_vfreq"]["id"]: 600,
             T.BY_NAME["info_loop"]["id"]: 4100}
    code = {"c": 0}
    orig_send = s._send

    def send(frame):
        orig_send(frame)
        code["c"] = frame[3]
        if frame[3] == U.VCP_SEL:
            vals[U.VCP_VAL] = paged[frame[4] << 8 | frame[5]]
    monkeypatch.setattr(s, "_send", send)

    def ops(addr, o):
        v = vals[code["c"]]
        body = bytes([0x6E, 0x88, 0x02, 0x00, code["c"], 0x00, 0x00, 0x64, v >> 8, v & 0xFF])
        return [(body + bytes([xor_sum(0x50, *body)]))[:o[0]]]
    bus.ops = ops
    monkeypatch.setattr(U, "session_for", lambda d, u: s)
    monkeypatch.setattr("flash_registry.current", lambda serial: {"tag": "wb-x"})
    st = U.status(None, {"serial": "AWT1", "be": True})
    assert st["ddc"] == {"volume": 50, "mute": 1, "brightness": 51, "contrast": 75, "power_mode": 0, "input": 1}, st
    assert st["info"] == {"info_hres": 1920, "info_vres": 1080, "info_vfreq": 600, "info_loop": 4100}, st
    assert st["dbg"]["loop"] == 4100 and st["dbg"]["stage"] == 8 and st["dbg"]["pwm"] == 125 and st["tag"] == "wb-x", st
    assert st["dbg"]["clk"]["pll"] > st["dbg"]["clk"]["cpu"] > 0 and st["dbg"]["timing"] is None and "no map" in st["dbg"]["timing_why"]
    sets = [w[1] for w in bus.writes if w[1][2] == U.OP_SET]                                         # [51 len op code ...]
    assert sets and all(f[3] == U.VCP_SEL for f in sets), "the only Set frames are the RAM-only row selector 0xE0"
    assert io.allow_write is False and all(sub in (0x01, 0x3A, 0x3C) for sub, _ in io.log), io.log   # staging + read commands only
    assert S.format_line({**st, "dbg": None}).count("1920x1080 60.0Hz") == 1 and "loop 4100/s" in S.format_line({**st, "dbg": None})
    assert "CPU" in S.format_line(st) and "PWM 125 (51 %)" in S.format_line(st)


def test_status_without_debug_link_names_it(monkeypatch):
    import rtd_i2c_bridge as B
    io = FakeDbgIo({})                                       # 0x35 reads 0 / no magic: the link is on the DDC side
    monkeypatch.setattr(B, "Real", lambda bus, allow_write, regread=False: io)
    bus = FakeBus(5)
    s = U.DdcSession(5, "AWT1", bus_cls=lambda n: bus, clock=Clock(), nap=lambda x: None, prove=False)
    bus.fail = True                                          # DDC down too: both reasons reported, nothing raised
    monkeypatch.setattr(U, "session_for", lambda d, u: s)
    monkeypatch.setattr("flash_registry.current", lambda serial: {})
    st = U.status(None, {"serial": "AWT1"})
    assert st["ddc"] == {} and st["ddc_err"].startswith("volume:") and st["dbg"] is None and "0x35 not answering" in st["dbg_err"], st
