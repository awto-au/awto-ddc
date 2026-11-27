"""OSD fit, static half (scripts/osd_fit.py): the tree passes; a too-long text, a narrowed box and a bad spec each FAIL."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import osd_fit as F

SRC = (ROOT / F.CONSOLE).read_text()
D = F.defines([SRC, (ROOT / F.HEADER).read_text()])
CT = F.card_texts(SRC)
ROWS = F.load_rows(ROOT / F.TSV)


def fails(res):
    return [line for ok, line in res if not ok]


def test_tree_fits():
    assert fails(F.check(ROWS, D, CT, F.evaluate("AWTO_CARD_COLS", D))) == []


def test_too_long_literal_fails_with_cells_over():
    res = F.check([("test box", "1", "10", "lit:0123456789AB", "deliberately too long")], D, CT)
    assert len(fails(res)) == 1 and "3 cell(s) over" in fails(res)[0] and "test box" in fails(res)[0]


def test_too_long_card_text_fails():
    ct = [*CT, "x" * 40]                         # a new tAwtoCardS text wider than a message card row
    assert any("card text" in f for f in fails(F.check([], D, ct, F.evaluate("AWTO_CARD_COLS", D))))


def test_old_info_width_fails():
    d = dict(D, AWTO_INFO_COLS="28")             # before 2026-11-27: the swing row reached the frame cell (unit 2, Dan)
    assert any(f.startswith("FAIL info swing") for f in fails(F.check(ROWS, d, CT)))


def test_old_wdt_width_fails():
    d = dict(D, AWTO_WDT_POP_W="36")             # the GPIO page boot row dropped "MS AT n" (osd_fit_sim, 2026-11-27)
    assert any(f.startswith("FAIL wdt boot row") for f in fails(F.check(ROWS, d, CT)))


def test_bad_index_and_token_fail():
    res = F.check([("idx", "0", "99", "ct:500", "out of range"), ("tok", "0", "99", "zz:abc", "bad token")], D, CT)
    assert len(fails(res)) == 2


def test_card_texts_indexes_match_defines():
    assert CT[F.evaluate("AWTO_CT_INFO", D)] == "Information"
    assert CT[F.evaluate("AWTO_CT_FOUND", D)] == "Found by"
    assert CT[F.evaluate("AWTO_CT_WHY", D) + F.evaluate("AWTO_SEL_WHY_FAST_WAKE", D)] == "Fast wake"
