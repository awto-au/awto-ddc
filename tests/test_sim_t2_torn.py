"""SimBus._t2: torn Timer2 counter reads (diag usT2Isr read mid-ISR) never become the time reference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fw_sim as S  # noqa: E402


def bus(samples):
    b = object.__new__(S.SimBus)
    b.t2_abs, b._t2_last, b.t2_back = 0, None, []
    it = iter(samples)
    b.diag_t2 = lambda: next(it)
    return b


def test_torn_forward_rejected():
    b = bus([0x12F0, 0x13FF, 0x1301, 0x1305])       # 0x13FF: high bumped, low still FF (true value ~0x1300)
    assert b._t2() == 0
    assert b._t2() == 0                              # rejected, time unchanged
    assert b._t2() == 0x1301 - 0x12F0               # no 256 ms freeze: the next read counts from the good reference
    assert b._t2() == 0x1305 - 0x12F0
    assert len(b.t2_back) == 1


def test_real_long_gap_ending_ff_taken_next_read():
    b = bus([0x1000, 0x11FF, 0x1201])                # 511 ms gap, a real value ending in FF
    b._t2()
    assert b._t2() == 0                              # skipped once
    assert b._t2() == 0x1201 - 0x1000                # accepted on the next read, no time lost


def test_torn_backward_rejected():
    b = bus([0x1300, 0x1200, 0x1301])                # low wrapped, high not yet
    b._t2()
    assert b._t2() == 0
    assert b._t2() == 1
