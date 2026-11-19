"""scripts/flash_screen.py and scripts/gen_flash_screen.py mirror constants of fw/test/flash_screen.c (#232): they must agree."""
import pytest
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import flash_screen as FS  # noqa: E402
import gen_flash_screen as L  # noqa: E402


def c_define(name: str, text: str | None = None) -> int:
    src = text if text is not None else (ROOT / "fw/test/flash_screen.c").read_text()
    m = re.search(rf"#define\s+{name}\s+(\S+)", src)
    assert m, name
    return eval(m.group(1), {}, {})       # numbers / simple expressions of numbers only


def test_layout_matches_generated_header():
    inc = (ROOT / "fw/test/flash_screen_data.inc").read_text()
    for name, val in (("COLS", L.COLS), ("ROWS", L.ROWS), ("PM_COLS", L.PM_COLS), ("PM_ROWS", L.PM_ROWS), ("PM_COL0", L.PM_COL0),
                      ("PM_ROW0", L.PM_ROW0), ("PM_OPEN", L.PM_OPEN), ("PM_CLOSED", L.PM_CLOSED), ("GLYPHS", L.GLYPHS)):
        assert c_define(f"AWTO_FS_{name}", inc) == val, name


def test_char_commands():
    assert FS.CHAR_B0 == c_define("AWTO_FS_CHAR_B0")
    assert FS.BG == c_define("AWTO_FS_BG") and FS.YELLOW == c_define("AWTO_FS_YELLOW") and FS.WHITE == c_define("AWTO_FS_WHITE")
    assert FS.FG_SHIFT == c_define("AWTO_FS_FG_SHIFT")
    assert FS.CHAR_WORD == L.ROWS + 1 == c_define("AWTO_FS_ROWS", (ROOT / "fw/test/flash_screen_data.inc").read_text()) + 1


def test_generated_file_current():
    assert (ROOT / "fw/test/flash_screen_data.inc").read_text() == L.text()


def test_vcp_value():
    reg = [r for r in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines() if r.startswith("121\t")][0].split("\t")
    assert reg[14].split("|")[FS.VCP_FLASH_SCREEN] == "Flash warning"
    assert reg[11] == f"0x{FS.VCP_SAVER:02X}"


def test_text_rows_fit():
    info = {"phase": "BANKED", "bank": 14, "nbank": 15, "addr": 0xFF000, "sec": 224, "nsec": 224, "pct": 100, "iface": "DP-AUX 1000 KHZ BURST", "bad": 12, "recov": 3, "t": 3599, "skip": 224, "nimg": 224}
    assert len(FS.rows_text(info)) == len(L.ROW_LINES)
    assert FS.rows_text(info)[0].endswith("SKIP 224/224")
    for t in FS.rows_text(info):
        assert len(t) <= L.COLS and all(ch in L.FONT_CHARS for ch in t.upper()), t


def test_duty_cap_skips_ticks_while_holding(monkeypatch, tmp_path):
    """DUTY_MAX holds the next redraw for (1/duty - 1) x the last redraw's time (DP AUX, #254)."""
    clock = [0.0]
    monkeypatch.setattr(FS.time, "monotonic", lambda: clock[0])
    marker = tmp_path / "shown"
    marker.write_text('{"rot": 0}')
    monkeypatch.setattr(FS, "MARKER", marker)
    monkeypatch.setattr(FS, "DUTY_MAX", 0.10)
    monkeypatch.setattr(FS, "_hold_until", 0.0)
    monkeypatch.setattr(FS, "_prev", {})
    puts = []

    def put(o, cell, gid):
        puts.append(cell)
        clock[0] += 0.01                                   # 10 ms per cell
    monkeypatch.setattr(FS, "_put", put)
    monkeypatch.setattr(FS, "_osd", lambda isp: type("O", (), {"set_opt": lambda self, x: None})())
    info = {"phase": "BANKED", "bank": 0, "nbank": 15, "addr": 0, "sec": 1, "nsec": 10, "pct": 10, "bad": 0, "recov": 0, "t": 1.0}
    FS.tick(None, 0, info)
    first = len(puts)
    cost = clock[0]
    assert first > 0 and FS._hold_until == pytest.approx(cost + cost * 9)
    FS.tick(None, 1, {**info, "sec": 2})                   # inside the hold: nothing drawn
    assert len(puts) == first
    clock[0] = FS._hold_until + 0.001
    FS.tick(None, 2, {**info, "sec": 3})
    assert len(puts) > first
