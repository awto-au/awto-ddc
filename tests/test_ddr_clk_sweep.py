"""scripts/ddr_clk_sweep.py: the PLL code model, the step ladder and the firmware struct layout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ddr_clk_sweep as D  # noqa: E402

STOCK_N, STOCK_F = 81, 6639          # unit 3, both channels, 2026-11-19


def test_stock_models_the_1200m_option():
    assert abs(D.mhz(STOCK_N, STOCK_F, 0) - 1200.0) < 0.05


def test_half_percent_step_is_3432_units():
    sc = D.code(STOCK_N, STOCK_F)
    assert D.delta8_for(0.5, sc) * D.UNIT == 3432
    assert abs(D.pct_of(D.delta8_for(0.5, sc), sc) - 0.5) < 0.001


def test_steps_never_exceed_half_percent_and_carry_into_n():
    sc = D.code(STOCK_N, STOCK_F)
    lv = [k * 0.5 for k in range(0, 11)]
    d8 = [D.delta8_for(x, sc) for x in lv]
    assert all((b - a) * D.UNIT <= 3440 for a, b in zip(d8, d8[1:]))
    top = sc + d8[-1] * D.UNIT
    assert (top >> D.CODE_BITS) - D.N_BIAS == 86 and (top & 0x1FFF) == 7        # +5 %: N 86, F 7 as measured


def test_struct_offsets_are_sequential():
    offs = [D.D_GO, D.D_SEQ, D.D_STATE, D.D_REFUSE, D.D_FLAGS, D.D_PDIV, D.D_DELTA, D.D_HOLD, D.D_ENV, D.D_NOW_NA, D.D_NOW_NB, D.D_NOW_FA, D.D_NOW_FB,
            D.D_STK_NA, D.D_STK_NB, D.D_STK_FA, D.D_STK_FB, D.D_FIFO_PRE, D.D_FIFO_POST, D.D_NOWMS]
    assert offs == sorted(offs) and len(set(offs)) == len(offs)
    assert D.D_NOWMS + 2 == D.D_SIZE and D.D_FIFO_POST + 5 == D.D_NOWMS


def test_envelope_limits():
    assert D.ENVELOPE_PCT == 5.0 and D.OVERRIDE_PCT == 10.0 and D.STEP_PCT == 0.5
    assert D.HOLD_MS <= 30000                      # firmware AWTO_DDR_HOLD_MAX_MS
