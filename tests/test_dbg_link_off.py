"""dbg_link.off (#351): confirmed only by 0x35 NAK + 0x37 ACK, re-sent when not confirmed, one line per attempt; fake bus + clock."""
import errno
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dbg_link as DL


class Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeUnit:
    """debug slave 0x35 and DDC/CI 0x37; one of them owns the DDC. Debug slave protocol (fw/diag/dbgisr.c):
    write 0x01 [hi], 0x03 [val], 0x3B [lo] = XDATA hi:lo <- val; read 0x01 [hi], 0x3A [lo], then 0x08 = XDATA hi:lo.
    The main loop runs a pending test byte `run_after_s` after its write; `lose` writes vanish (staging clobbered);
    `stuck`: consumed, but the swap never happens."""

    def __init__(self, clk, run_after_s=0.02, lose=0, stuck=False):
        self.clk, self.run_after_s, self.lose, self.stuck = clk, run_after_s, lose, stuck
        self.linked, self.pending, self.at = True, 0, 0.0
        self.hi = self.val = self.addr = 0
        self.writes = 0

    def step(self):
        if self.pending and self.clk.t - self.at >= self.run_after_s:
            self.pending = 0                          # AwtoDiagTestCmd -> AwtoDbgLinkSet(0): swapped in the same pass
            self.linked = self.stuck

    def xdata(self, a):
        return {DL.DIAG_MAGIC: ord("A"), DL.DIAG_MAGIC + 1: ord("D"), DL.TESTCMD: self.pending}.get(a, 0)


class FakeBus:
    unit: FakeUnit

    def __init__(self, bus):
        self.u = FakeBus.unit

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def _ack(self, addr):
        self.u.step()
        if (addr == DL.DBG) != self.u.linked:
            raise OSError(errno.ENXIO, "No such device or address")

    def write(self, addr, reg, data):
        self._ack(addr)
        u = self.u
        if reg == 0x01:
            u.hi = data[0]
        elif reg == 0x03:
            u.val = data[0]
        elif reg == 0x3A:
            u.addr = u.hi << 8 | data[0]
        elif reg == 0x3B and (u.hi << 8 | data[0]) == DL.TESTCMD:
            u.writes += 1
            if u.lose:
                u.lose -= 1
            elif not u.pending:                       # a re-write of a pending byte does not delay the pass that runs it
                u.pending, u.at = u.val, u.clk.t

    def read(self, addr, reg, n):
        self._ack(addr)
        return bytes([self.u.xdata(self.u.addr)]) * n

    def raw_read(self, addr, n):
        self._ack(addr)
        return b"\x00" * n


@pytest.fixture
def rig(monkeypatch):
    clk, lines = Clock(), []
    monkeypatch.setattr(DL.time, "monotonic", clk.monotonic)
    monkeypatch.setattr(DL.time, "sleep", clk.sleep)
    monkeypatch.setattr(DL.i2cbus, "Bus", FakeBus)
    monkeypatch.setattr(DL, "log", lines.append)

    def make(**kw):
        FakeBus.unit = FakeUnit(clk, **kw)
        return FakeBus.unit, lines, clk
    return make


def test_derived_bounds():
    assert pytest.approx(1.25 * 0.5859) == DL.OFF_WINDOW_S
    assert DL.OFF_ATTEMPTS == 3                         # ceil(4 x 0.5 s / 0.732 s)


def test_fake_speaks_the_debug_protocol(rig):
    rig()
    assert DL.dbg_ok(11) and not DL.ddcci_ok(11)


def test_confirmed_first_attempt(rig):
    u, lines, _ = rig()
    assert DL.off(11) is True
    assert u.writes == 1 and not u.linked
    assert len(lines) == 1 and "attempt 1/3: sent; confirmed 0x35 NAK + 0x37 ACK" in lines[0]


def test_lost_write_is_resent(rig):
    u, lines, _ = rig(lose=1)
    assert DL.off(11) is True
    assert u.writes == 2 and len(lines) == 2
    assert "attempt 1/3: sent; not confirmed" in lines[0] and "test byte 0x00 = consumed or lost" in lines[0] and "0x37 NAK" in lines[0]
    assert "attempt 2/3: sent; confirmed" in lines[1]


def test_blocked_loop_names_the_pending_byte(rig):
    _u, lines, _ = rig(run_after_s=DL.OFF_WINDOW_S + 0.3)       # a pass longer than the window (a watchdog reset on the unit)
    assert DL.off(11) is True
    assert f"test byte 0x{DL.CMD_BACK:02X} = not run" in lines[0]
    assert "attempt 2/3" in lines[1] and "confirmed" in lines[1]


def test_never_swaps_fails_after_bound(rig):
    u, lines, clk = rig(stuck=True)
    assert DL.off(11) is False
    assert u.writes == DL.OFF_ATTEMPTS and len(lines) == DL.OFF_ATTEMPTS + 1
    assert all(f"attempt {k}/3: sent; not confirmed" in ln for k, ln in enumerate(lines[:3], 1))
    assert "FAILED after 3 attempts" in lines[-1]
    assert clk.t <= DL.OFF_ATTEMPTS * (DL.OFF_WINDOW_S + DL.MCCS_WAIT_S)


def test_already_off_is_confirmed_without_a_send(rig):
    u, lines, _ = rig()
    u.linked = False
    assert DL.off(11) is True
    assert u.writes == 0 and "not sent (0x35 NAK" in lines[0] and "confirmed" in lines[0]


def _swapped_off_fails(mp):
    mp.setattr(DL, "on", lambda bus, minutes=10: "swapped")
    mp.setattr(DL, "hold", lambda bus: None)
    mp.setattr(DL, "off", lambda bus: False)


def test_linked_fails_loudly_when_off_not_confirmed(monkeypatch):
    _swapped_off_fails(monkeypatch)
    with pytest.raises(SystemExit, match="OFF not confirmed"), DL.linked(11):
        pass


def test_linked_keeps_the_blocks_own_error(monkeypatch):
    _swapped_off_fails(monkeypatch)
    with pytest.raises(ValueError, match="own failure"), DL.linked(11):
        raise ValueError("the block's own failure")
