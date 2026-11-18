"""pump gate: the reply-inside-the-delay check counts instructions, so it does not flip with the Timer2 tick phase."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pump_sim as P  # noqa: E402

IMGS = sorted((ROOT / "tmp/fw").glob("AWT26110003-*-clk87-be.bin"))      # the stock-clock build: at 350.8 MHz the old 1 ms stamp check never fails (nothing left to show)
PHASES = (0.1, 0.5, 0.9)     # fraction of a Timer2 tick left at injection: 0.1 is the phase where the old 1 ms stamp check failed
IPM = 7500.0                 # order of the measured sim rate; the formula is what is tested here


def test_budget_formula_and_margin():
    lim = P.reply_limit(2, IPM)
    assert lim == pytest.approx((1 - P.REPLY_MARGIN) * 2 * IPM)
    assert P.reply_check(int(lim), 2, IPM)[0]
    ok, msg = P.reply_check(int(lim) + 1, 2, IPM)
    assert not ok and "limit" in msg and "instr/ms" in msg


@pytest.mark.skipif(not IMGS, reason="image tmp/fw/AWT26110003-*-be.bin absent")
def test_real_image_passes_every_phase_and_a_slow_path_fails():
    old, new = [], []
    for ph in PHASES:
        r = P.run(IMGS[0], IMGS[0].with_suffix(".map"), phase=ph)
        old.append(r["t_reply"] < r["t_in"] + r["n"] / 1000)      # the former tick-stamp check
        new.append(P.reply_check(r["instr"], r["n"], r["ipm"])[0])
        assert r["set_val"] == P.SET_VALUE
    assert all(new)
    assert not all(old), "old tick check no longer flips on these phases (nothing left to show)"
    slow = P.run(IMGS[0], IMGS[0].with_suffix(".map"), phase=0.5, extra_instr=int(P.reply_limit(r["n"], r["ipm"])))
    assert not P.reply_check(slow["instr"], slow["n"], slow["ipm"])[0]
