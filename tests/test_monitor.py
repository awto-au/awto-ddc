"""Health monitor host side (fw/diag/monitor.c): g_stAwtoMon decode, sync row text, registry row, constants (docs/monitoring.md)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mon_decode as D
import sync_log as SL

BLOCK = bytes([ord("M"), ord("N"), 1, 1, 7, 0xF8, 0xF8, 0x58, 0x20, 0x07, 0xCF, 0x02, 0xBC, 0x0F, 3, 0xBC, 1, 0, 0x0E, 0x10, 9])
STALL = bytes([0, 157, 1, 0xC1, 0, 34, 8, 0xBE, 1, 1, 2, 10])      # g_stAwtoStall: usGap x 8.938 us, ucSite


def test_decode_block():
    d = D.decode(BLOCK, STALL)
    assert d["adc"] == [0xF8, 0xF8, 0x58, 0x20] and d["trim"] == 1999 and d["loop"] == 700
    assert d["up_s"] == 3600 and d["stack"] == 0xBC and d["rows"] == 9 and d["poke_ms"] == round(15 * 293 / 64)
    assert d["gap"] == [1.4, 4.0, 0.3, 20.0] and d["gap_site"] == [1, 1, 2, 10]
    assert "longest stall 20.0 ms (main 1.4 ms at site 1" in D.text(d)
    assert "ADC A0 F8 A1 F8 A2 58 A3 20" in D.text(d) and "boot cold power-up" in D.text(d)


def test_decode_no_sample():
    assert D.decode(bytes(D.SIZE)) is None and D.decode(b"MN") is None


def test_sync_row_text():
    assert SL.mon_text(1, 0 << 16 | 0xF8 << 8 | 0x70) == "ADC A0 key ladder F8 -> 70"        # an ADC row = one channel that moved
    assert SL.mon_text(1, 3 << 16 | 0xF8 << 8 | 0x00) == "ADC A3 DP HPD out (pin 97) F8 -> 00"
    assert SL.mon_text(2, 1999) == "IOSC 1999"
    assert SL.mon_text(3, 700 << 16 | 18) == "700/s gap 1.8ms"
    assert SL.mon_text(5, 15 << 24 | 11 << 12 | 300) == "free 300/s busy 15% worst 0.687ms"
    assert SL.mon_text(4, 3600 << 8 | 0xBC) == "up 3600s stk BC"
    rows = SL.load_rows(ROOT / "fw/awto/sync.tsv")
    ev = (0xEA, 2, 0, 1999)
    assert SL.line(rows, ev, 0).endswith("monitor: IOSC 1999")


def test_heartbeat_one_row():
    """a heartbeat (pushed in one call) is one console row, every value kept (Dan 2026-11-27)"""
    rows = SL.load_rows(ROOT / "fw/awto/sync.tsv")
    evs = [(0xEA, 2, 100, 2001), (0xEA, 3, 100, 300 << 16 | 126), (0xEA, 5, 101, 39 << 24 | 31 << 12 | 301), (0xEA, 4, 101, 1150 << 8 | 0xD4)]
    texts = [SL.line(rows, e, 0).split(":", 1)[1] for e in evs]
    rs = SL.con_rows(evs, texts, [(100, True), (100, True), (101, True), (101, True)])
    assert len(rs) == 1 and rs[0]["text"] == "monitor: IOSC 2001 | 300/s gap 12.6ms | free 301/s busy 39% worst 1.937ms | up 1150s stk D4"
    late = evs[:2] + [(0xEA, 5, 105, evs[2][3])]                 # 5 ms later (> JOIN_MS): another call, its own row
    assert len(SL.con_rows(late, texts[:3], [(100, True), (100, True), (105, True)])) == 2


def test_constants_and_registry():
    h = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
    v = {k: int(x) for k, x in re.findall(r"#define (AWTO_MON_\w+)\s+(\d+)", h)}
    assert v["AWTO_MON_MS"] == 10000 and v["AWTO_MON_BEAT_K"] == 30
    assert v["AWTO_MON_ADC_STEP"] == 2 * 8                 # two 5-bit codes
    reg = [ln.split("\t") for ln in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines() if ln.startswith("124\t")]
    assert reg and reg[0][1] == "monitor" and reg[0][9] == "1"    # default on: the cost is measured (docs/monitoring.md)
