"""scripts/flash_screen.py and scripts/gen_flash_screen.py mirror constants of fw/test/flash_screen.c (#232): they must agree."""
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
    info = {"phase": "BANKED", "bank": 14, "nbank": 15, "addr": 0xFF000, "sec": 224, "nsec": 224, "pct": 100, "iface": "DP-AUX 1000 KHZ BURST", "bad": 12, "recov": 3, "t": 3599}
    assert len(FS.rows_text(info)) == len(L.ROW_LINES)
    for t in FS.rows_text(info):
        assert len(t) <= L.COLS and all(ch in L.FONT_CHARS for ch in t.upper()), t
