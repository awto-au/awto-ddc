"""Sync log colour classes: sync_classes.tsv, the 5th sync.tsv column, generator tables, console palette constants, host colour on a TTY only."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gen_awto_sync as G
import sync_classes as C
import sync_log as SL

CON = (ROOT / "fw/osd/console.c").read_text()
TL = (ROOT / "fw/osd/text_layer.c").read_text()
HDR = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
STYLE_COLOURS = {"AWTO_T_STYLE_TEXT": "AWTO_PAL_DIAG_TEXT", "AWTO_T_STYLE_ALERT": "AWTO_PAL_DIAG_ALERT", "AWTO_T_STYLE_WARN": "AWTO_PAL_DIAG_WARN",
                 "AWTO_T_STYLE_TIMING": "AWTO_PAL_DIAG_TIMING", "AWTO_T_STYLE_BOOT": "AWTO_PAL_DIAG_BOOT"}
FG_MAX = 15                                          # 1-bit glyph foreground = 4 bit palette index


def define(text: str, name: str) -> int:
    return int(re.search(rf"^#define\s+{name}\s+(\d+)", text, re.MULTILINE).group(1))


def test_class_file_parses():
    c = C.load()
    assert next(iter(c)) == "normal" and set(c) >= {"normal", "error", "warning", "timing", "boot", "flash"}
    assert c["normal"]["ansi"] == 0 and all(v["ansi"] for k, v in c.items() if k != "normal")


def test_unknown_class_fails():
    with pytest.raises(AssertionError):
        C.check("purple")


def test_tsv_rows_carry_known_classes_and_default_is_normal():
    r = G.rows()
    assert {x["cls"] for x in r} <= set(C.load())
    assert {x["cls"] for x in r} >= {"normal", "error", "warning", "timing", "boot", "flash"}
    assert next(x for x in r if (x["id"], x["arg"]) == (0xC4, 0xFF))["cls"] == "error"          # signal lost
    assert next(x for x in r if (x["id"], x["arg"]) == (0xCF, 0x01))["cls"] == "normal"         # no column


def test_name_rows_take_no_class(tmp_path):
    tsv = tmp_path / "s.tsv"
    tsv.write_text("30\t01\t-\ta\n15\t01\t-\tAC ON\terror\n")
    with pytest.raises(AssertionError):
        G.rows(tsv)


def test_generated_table_follows_the_class_column(tmp_path):
    tsv = tmp_path / "s.tsv"
    tsv.write_text("30\t01\t-\tplain\n30\t02\t-\tbad\terror\n30\t03\t-\tslow\ttiming\n30\t04\t-\tsaved\tflash\n")
    blk = G.cls_block(G.rows(tsv), C.load())
    assert ("static const __code BYTE tAwtoSyncCls[4] = {\n    AWTO_T_STYLE_TEXT, AWTO_T_STYLE_ALERT, AWTO_T_STYLE_TIMING, AWTO_T_STYLE_BOOT};") in blk
    assert "static BYTE AwtoSyncClsOf(WORD usRow)" in blk


def test_generated_blocks_are_current():
    r = G.rows()
    assert G.cls_block(r, C.load()) in (ROOT / "fw/osd/console.c").read_text()


def test_style_palette_constants():
    classes = C.load()
    pals = {}
    for cls in classes.values():
        style = cls["style"]
        assert style in STYLE_COLOURS, style
        num, pal = define(CON, style), define(HDR, STYLE_COLOURS[style])
        assert 0 <= pal <= FG_MAX
        table = re.search(r"tAwtoStyle\[\d+\]\s*=\s*\{([^}]*)\}", TL, re.DOTALL).group(1)
        entry = [t.strip() for t in re.sub(r"//.*", "", table).split(",") if t.strip()][num]
        assert define(HDR, entry) == pal, f"{style}: tAwtoStyle[{num}] = {entry}, header says {pal}"
        pals.setdefault(pal, style)
        assert f"ScalerOsdSetColorPalette({STYLE_COLOURS[style]}," in CON, f"{STYLE_COLOURS[style]} is never set when the console opens"
    new = {p for p in pals if p > define(HDR, "AWTO_PAL_N")}
    assert len(new) == 3                                # warning / timing / boot: entries above the 12 the text layer owns


def test_host_row_class_and_plain_text_unchanged(tmp_path):
    tsv = tmp_path / "s.tsv"
    tsv.write_text("30\t01\t-\tplain\n30\t02\t-\tbad\terror\n")
    rows = SL.load_rows(tsv)
    assert [r["cls"] for r in rows] == ["normal", "error"]
    assert SL.line(rows, (0x30, 1, 5, 0), 0) == "    5:plain"             # the decoded text never carries the class
    assert SL.row_class(rows, (0x30, 2, 0, 0)) == "error" and SL.row_class(rows, (0x99, 0, 0, 0)) == "normal"


def test_colour_only_on_a_tty():
    h = {"events": [(0x30, 1, 0, 0), (0x30, 2, 0, 0), (0x30, 3, 0, 0)]}
    rows = [{"id": 0x30, "arg": 1, "cls": "normal"}, {"id": 0x30, "arg": 2, "cls": "error"}, {"id": 0x30, "arg": 3, "cls": "timing"}]
    lines = ["a", "b", "c"]
    assert SL.paint_lines(h, lines, rows, False) == lines                  # file / pipe: plain, same order
    on = SL.paint_lines(h, lines, rows, True)
    assert on == ["a", "\x1b[31mb\x1b[0m", "\x1b[36mc\x1b[0m"]             # normal: no escape; one line out per line in
    assert SL.paint_lines(h, lines[:2], rows, True) == lines[:2]           # lines and events out of step: plain, nothing dropped


def test_use_colour_follows_the_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("AWTO_TTY", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert not C.use_colour()
    monkeypatch.setenv("AWTO_TTY", "1")
    assert C.use_colour()                                                  # dev.py runs the child on a pipe under a terminal
    monkeypatch.setenv("NO_COLOR", "1")
    assert not C.use_colour()


def test_dly_line_decodes():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sync_log
    assert sync_log.value("dly", 0x2B, (0x4F12 << 16) | 123) == "0B:4F12 took 123 us +2 more"
    assert sync_log.value("dly", 0x0B, (0x4F12 << 16) | 9) == "0B:4F12 took 9 us"
