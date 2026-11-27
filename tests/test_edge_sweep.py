"""edge_sweep_sim (#214): the OSD window check and the value list, offline (no image)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import edge_sweep_sim as E
import osd_model as M


def state(x0, y0, x1, y1, win=5):
    regs = bytearray(0x100)
    regs[2] = 1                                     # frame enable (3A02 bit 0)
    b = M.win_base(win)
    w = {b + 0: [0, 0, 0], b + 1: [(x0 >> 8) << 4 | y0 >> 8, x0 & 255, y0 & 255],
         b + 2: [(x1 >> 8) << 4 | y1 >> 8, x1 & 255, y1 & 255], b + 3: [0, 0, 1]}
    return M.OsdState(win=w, regs=bytes(regs), ovl=(1, 0))


def test_one_px_window_is_a_fault():
    """the 1 % backlight bar: x1 = x0 draws to the line end"""
    assert any("end <= start" in f for f in E.win_faults(state(11, 40, 11, 50)))


def test_two_px_window_passes():
    assert E.win_faults(state(11, 40, 12, 50)) == []


def test_window_off_the_panel_is_a_fault():
    assert any("outside" in f for f in E.win_faults(state(0, 0, 4000, 10)))


def test_values_are_the_edges():
    r = {"min": 0, "max": 100}
    assert E.values(r, quick=False) == [0, 1, 50, 99, 100]
    assert E.values(r, quick=True) == [0, 1, 99, 100]
    assert E.values({"min": 0, "max": 1}, quick=False) == [0, 1]
