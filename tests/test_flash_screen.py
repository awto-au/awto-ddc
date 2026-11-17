"""scripts/flash_screen.py mirrors constants of fw/test/flash_screen.c (#232): they must agree."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import flash_screen as FS  # noqa: E402


def c_define(name: str) -> int:
    m = re.search(rf"#define\s+{name}\s+(\S+)", (ROOT / "fw/test/flash_screen.c").read_text())
    assert m, name
    return eval(m.group(1), {}, {})       # numbers / simple shifts of numbers only


def test_cell_word():
    assert FS.FS_CHAR_WORD == c_define("AWTO_FS_CHAR_WORD")
    assert FS.CHAR_B0 == c_define("AWTO_FS_CHAR_B0")
    assert FS.CHAR_B2 == ((c_define("AWTO_FS_FG") << c_define("AWTO_FS_FG_SHIFT")) | c_define("AWTO_FS_BG"))


def test_vcp_value():
    reg = [r for r in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines() if r.startswith("121\t")][0].split("\t")
    options = reg[14].split("|")
    assert options[FS.VCP_FLASH_SCREEN] == "Flash warning"
    assert reg[11] == f"0x{FS.VCP_SAVER:02X}"


def test_glyph_ids():
    assert (FS.GLYPH_OPEN, FS.GLYPH_CLOSED) == (0, 1)       # glyph 0 = open, 1 = closed (gen_flash_screen.py)
