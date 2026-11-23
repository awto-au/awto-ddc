"""scripts/flash_screen.py and scripts/gen_flash_screen.py mirror constants of fw/test/flash_screen.c (#232): they must agree."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import flash_screen as FS
import gen_flash_screen as L


def c_define(name: str, text: str | None = None) -> int:
    src = text if text is not None else (ROOT / "fw/test/flash_screen.c").read_text()
    m = re.search(rf"#define\s+{name}\s+(\S+)", src)
    assert m, name
    return eval(m.group(1), {}, {})       # numbers / simple expressions of numbers only


def test_layout_matches_generated_header():
    inc = (ROOT / "fw/test/flash_screen_data.inc").read_text()
    for name, val in (("COLS", L.COLS), ("ROWS", L.ROWS), ("PM_COLS", L.PM_COLS), ("PM_ROWS", L.PM_ROWS), ("PM_COL0", L.PM_COL0),
                      ("PM_ROW0", L.PM_ROW0), ("PM_OPEN", L.PM_OPEN), ("GLYPHS", L.GLYPHS)):
        assert c_define(f"AWTO_FS_{name}", inc) == val, name


def test_char_commands():
    assert FS.CHAR_B0 == c_define("AWTO_FS_CHAR_B0")
    assert FS.BG == c_define("AWTO_FS_BG") and FS.YELLOW == c_define("AWTO_FS_YELLOW") and FS.WHITE == c_define("AWTO_FS_WHITE")
    assert FS.FG_SHIFT == c_define("AWTO_FS_FG_SHIFT")
    assert FS.CHAR_WORD == L.ROWS + 1 == c_define("AWTO_FS_ROWS", (ROOT / "fw/test/flash_screen_data.inc").read_text()) + 1


def test_generated_file_current():
    assert (ROOT / "fw/test/flash_screen_data.inc").read_text() == L.text()


def test_vcp_value():
    reg = next(r for r in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines() if r.startswith("121\t")).split("\t")
    assert reg[14].split("|")[FS.VCP_FLASH_SCREEN] == "Flash warning"
    assert reg[11] == f"0x{FS.VCP_SAVER:02X}"


def test_text_rows_fit():
    info = {"phase": "BANKED", "bank": 14, "nbank": 15, "addr": 0xFF000, "sec": 224, "nsec": 224, "pct": 100, "iface": "DP-AUX 1000 KHZ BURST", "bad": 12, "recov": 3, "t": 3599, "skip": 224, "nimg": 224}
    assert len(FS.rows_text(info)) == len(L.ROW_LINES)
    assert FS.rows_text(info)[0].endswith("SKIP 224/224")
    for t in FS.rows_text(info):
        assert len(t) <= L.COLS and all(ch in L.FONT_CHARS for ch in t.upper()), t


INFO = {"phase": "BANKED", "bank": 0, "nbank": 15, "addr": 0, "sec": 1, "nsec": 10, "pct": 10, "bad": 0, "recov": 0, "t": 1.0}


@pytest.fixture
def rig(monkeypatch, tmp_path):
    clock = [100.0]
    monkeypatch.setattr(FS.time, "monotonic", lambda: clock[0])
    marker = tmp_path / "shown"
    marker.write_text('{"rot": 0}')
    monkeypatch.setattr(FS, "_marker", lambda: marker)
    monkeypatch.setattr(FS, "_prev", {})
    monkeypatch.setattr(FS, "_next_at", 0.0)
    monkeypatch.setattr(FS, "_errs", ())
    puts = []
    monkeypatch.setattr(FS, "_put", lambda o, cell, gid: puts.append((cell, gid)))
    monkeypatch.setattr(FS, "_osd", lambda isp: type("O", (), {"set_opt": lambda self, x: None})())
    return clock, puts


def test_pacman_static_and_smaller():
    assert (L.PM_DISC, L.PM_DISC) == (3 * L.TILE_W, 2 * L.TILE_H)       # 36 x 36 px = 3 x 2 tiles
    assert L.GLYPHS == L.PM_OPEN + L.PM_COLS * L.PM_ROWS               # one frame, no closed-mouth tiles


def test_host_never_writes_pacman_cells(rig):
    clock, puts = rig
    pm = {(L.PM_ROW0 + r) * L.COLS + L.PM_COL0 + c for r in range(L.PM_ROWS) for c in range(L.PM_COLS)}
    for k in range(5):
        FS.tick(None, k, {**INFO, "sec": k + 1, "pct": k})
        clock[0] += 1.1
    assert puts and not pm & {c for c, _ in puts} and all(g < L.PM_OPEN for _, g in puts)


def test_text_throttled_to_THROTTLE_S(rig):
    clock, puts = rig
    FS.tick(None, 0, INFO)
    first = len(puts)
    assert first > 0
    for k in range(1, 6):                                   # sectors 0.1 s apart (first draw at t = 0): nothing drawn
        clock[0] += 0.1
        FS.tick(None, k, {**INFO, "sec": k + 1, "pct": 20, "t": 2.0})
    assert len(puts) == first
    assert FS.THROTTLE_S == 5.0
    clock[0] += FS.THROTTLE_S                               # deadline reached
    FS.tick(None, 6, {**INFO, "sec": 7, "pct": 70})
    assert len(puts) > first


def test_errors_draw_immediately(rig):
    clock, puts = rig
    FS.tick(None, 0, INFO)
    n = len(puts)
    clock[0] += 0.1
    FS.tick(None, 1, {**INFO, "sec": 2, "bad": 1})
    assert len(puts) > n


def test_last_sector_draws_immediately(rig):
    clock, puts = rig
    FS.tick(None, 0, INFO)
    n = len(puts)
    clock[0] += 0.1
    FS.tick(None, 9, {**INFO, "sec": 10, "pct": 100})
    assert len(puts) > n
