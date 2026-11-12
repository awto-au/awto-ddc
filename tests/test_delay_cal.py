"""rtd_diag.cal_eval limits and delay_cal_check cycle model (#53.6). No hardware, no simulator."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import delay_cal_check as D  # noqa: E402
import rtd_diag  # noqa: E402

PER = 7309


def block(xms=10 * PER, d5us10=10 * 5.0 * PER / 1000, xus=100.0 * PER / 1000, xusisr=100.0 * PER / 1000, d5isr=10 * 5.0 * PER / 1000, t3=550 * PER):
    b = bytearray(48)
    b[0:4] = b"AD\x02\x08"
    b[26] = 26
    b[31] = 0xE3
    struct.pack_into(">H", b, 27, int(xms) // 4)
    struct.pack_into(">H", b, 29, int(d5us10))
    struct.pack_into(">4H", b, 32, int(xus), int(xusisr), int(d5isr), int(t3) // 64)
    return rtd_diag.decode(bytes(b), True)


def test_nominal_passes():
    assert all(ok for _, ok, _ in rtd_diag.cal_eval(block()))


def test_short_delay_fails():
    rows = {n: ok for n, ok, _ in rtd_diag.cal_eval(block(d5us10=10 * 3.0 * PER / 1000))}   # 3 us instead of 5
    assert rows["DELAY_5US"] is False and rows["DELAY_XUS(100)"] is True


def test_t3_and_tick_limits():
    rows = {n: ok for n, ok, _ in rtd_diag.cal_eval(block(t3=540 * PER, xms=11 * PER))}
    assert rows["T3 wait"] is False and rows["tick"] is False


def test_not_run():
    assert rtd_diag.cal_eval(block(xms=0))[0][1] is False


def test_djnz_model():
    # mov d,d (3) + 26 x djnz d,r (3) = 81: the Keil reference loop
    assert D.pattern_cycles("single", 26, 26, 0) == 81
    assert D.static_cycles(bytes([0x85, 0x08, 0x0A, 0xD5, 0x0A, 0xFD])) + 3 * 25 == 81
