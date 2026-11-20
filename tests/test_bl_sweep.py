"""bl_sweep.py host logic: interleaved order, knob bytes from the firmware header, sync-log parsing, verdicts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bl_sweep as B


def test_order_interleaved_not_sorted_and_complete():
    seq = B.order(list(B.DEFAULT_VALUES), 3)
    rnd = seq[:7]
    assert len(seq) == 21 and sorted(rnd) == sorted(B.DEFAULT_VALUES) and rnd != sorted(rnd)
    assert seq == rnd * 3


def test_order_two_values_one_run():
    assert sorted(B.order([150, 0], 1)) == [0, 150]


def test_knob_bytes_match_header_check():
    d = B.knob_defs()
    b = B.knob_bytes(400, d)
    assert b[0] == d["MAGIC"] and b[1] | b[2] << 8 == 400 and b[3] == d["SEED"] ^ b[0] ^ b[1] ^ b[2]
    assert d["ADDR"] == 0xF698 and d["MAX_MS"] >= 400


def test_parse_and_verdict():
    out = (
        "  1500:panel:test knob backlight on delay 150ms, counts from video ready\n"
        "  1700:panel:backlight on, 1702ms after MCU boot, 152ms after video ready (test knob)\n"
        "2026-11-20T21:49:15+11:00   1550:system:in DISPLAY SETTING for 111ms->ACTIVE:display set, panel video ready; picture on screen\n"
    )
    m = B.parse(out)
    assert (m["knob"], m["boot"], m["ref"], m["active"]) == (150, 1702, 152, 1550)
    assert B.verdict(150, m) == "OK"
    assert B.verdict(100, m).startswith("KNOB-MISMATCH")
    assert B.verdict(150, {**m, "ref": None}) == "NO-BL-ROW"
    assert B.verdict(150, {**m, "late": 5000}).startswith("LATE")
