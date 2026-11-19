"""settings_keep.plan (awto-ddc#219): what a flash reset, what is dropped / new / out of range. Run: python3 -m pytest tests/test_settings_keep.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import settings_keep as K

ROWS = {"disp_rotate": {"name": "disp_rotate", "min": 0, "max": 1}, "osd_font": {"name": "osd_font", "min": 0, "max": 1},
        "console_mode": {"name": "console_mode", "min": 0, "max": 2}, "contrast": {"name": "contrast", "min": 0, "max": 100}}


def test_wiped_rows_are_restored():
    todo, notes, kept = K.plan({"disp_rotate": 1, "osd_font": 1, "contrast": 50},
                               {"disp_rotate": 0, "osd_font": 0, "contrast": 50, "console_mode": 1}, ROWS)
    assert [(r["name"], old, cur) for r, old, cur in todo] == [("disp_rotate", 1, 0), ("osd_font", 1, 0)]
    assert kept == 1 and notes == ["console_mode: new row, default 1"]


def test_unchanged_flash_does_nothing():
    todo, _notes, kept = K.plan({"disp_rotate": 1, "contrast": 40}, {"disp_rotate": 1, "contrast": 40, "osd_font": 0, "console_mode": 1}, ROWS)
    assert todo == [] and kept == 2


def test_dropped_and_out_of_range_rows_are_reported_not_guessed():
    todo, notes, kept = K.plan({"sync_console": 1, "console_mode": 7}, {"disp_rotate": 0, "osd_font": 0, "contrast": 50, "console_mode": 1}, ROWS)
    assert todo == [] and kept == 0
    assert "sync_console: no longer a stored row (was 1); dropped" in notes
    assert "console_mode: was 7, outside the new range 0..2; default 1 stays" in notes
