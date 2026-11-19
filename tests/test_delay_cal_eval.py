"""rtd_diag.cal_eval (health 'delay cal'): the sim's numbers are judged like the unit's; a loop 20 % short, a lost tick or a wrong T3 FAIL."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rtd_diag as R  # noqa: E402

PER = R.PERIOD[0x8D]                                            # 350 MHz: Timer2 counts per ms


def block(**over):
    d = {"rcap2h": 0x8D, "xms4": round(10 * PER / (1 << R.XMS_SHIFT)),
         "t3_64": round(R.CAL_T3_MS * PER / (1 << R.T3_SHIFT))}
    for key, _, calls, nom, _, _ in R.CAL_ROWS:
        d[key] = round(nom * 1.05 * calls * PER / 1000.0)        # 5 % over nominal: inside 97..150 %
    d.update(over)
    return d


def fails(rows):
    return [n for n, ok, _ in rows if ok is False]


def test_good_block_passes_as_on_the_unit():
    assert fails(R.cal_eval(block(), sim=False)) == []


def test_loop_20_percent_short_fails():
    d = block()
    d["d5us10"] = round(0.8 * 5.0 * 10 * PER / 1000.0)
    assert fails(R.cal_eval(d, sim=False)) == ["DELAY_5US"]


def test_lost_tick_fails():
    assert "tick" in fails(R.cal_eval(block(xms4=round(9 * PER / (1 << R.XMS_SHIFT))), sim=False))


def test_wrong_t3_fails():
    assert "T3 wait" in fails(R.cal_eval(block(t3_64=round(300 * PER / (1 << R.T3_SHIFT))), sim=False))
