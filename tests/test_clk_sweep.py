"""scripts/clk_sweep.py: the step table stays inside the flash rating and the firmware's own refusal rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import clk_sweep as C

PLL_KHZ = 350_791                       # M2PLL of the unit: 14318 kHz x 49 / 2


def test_steps_inside_rating():
    for name, (f, f2, m, fl) in C.STEPS.items():
        assert 1 <= f <= 15 and 1 <= f2 <= 15 and 1 <= m <= 15, name
        spi = C.spi_mhz(C.pll_khz(*C.PLL[name]) if name in C.PLL else PLL_KHZ, f, f2)
        cap = C.RATED_OC_MHZ if fl & C.FL_OC else (C.RATED_DUAL_MHZ if fl & C.FL_DUAL else C.RATED_FAST_MHZ)
        assert spi <= cap, f"{name}: SPI {spi:.1f} MHz above the rating"
        assert not (name in C.FLASH_TESTS and spi > C.RATED_FAST_MHZ), f"{name}: flash write above the rating"
        assert m <= f2, f"{name}: MCU slower than the SPI (the firmware refuses it)"


def test_groups_name_known_steps():
    for g, names in C.GROUPS.items():
        assert all(n in C.STEPS for n in names), g
    assert all(n in C.STEPS for n in C.PADS)


def test_stock_step_is_the_stock_clock():
    f, f2, m, _ = C.STEPS["stock"]
    assert abs(C.mcu_mhz(PLL_KHZ, f, m) - C.STOCK_MHZ) < 0.1
    assert abs(C.spi_mhz(PLL_KHZ, f, f2) - 43.9) < 0.1


def test_struct_offsets_do_not_overlap():
    offs = [C.C_GO, C.C_SEQ, C.C_STATE, C.C_F, C.C_F2, C.C_M, C.C_CKCON, C.C_FLAGS, C.C_HOLD, C.C_RCAP, C.C_D5, C.C_DX, C.C_D5P, C.C_DXP,
            C.C_TICK, C.C_CRC, C.C_CRCBAD, C.C_XDBAD, C.C_ALU, C.C_MISS, C.C_CRCMS, C.C_FFED, C.C_PLL, C.C_DEB, C.C_REF, C.C_MISSN,
            C.C_RST, C.C_NOW, C.C_DRIVE, C.C_AST, C.C_TUNE, C.C_PASSES, C.C_SC, C.C_FLN, C.C_FLCK, C.C_FLDONE, C.C_FLFAIL, C.C_FLBADE,
            C.C_FLBADP, C.C_FLERMS, C.C_FLPRMS, C.C_FLMAX, C.C_IMGN, C.C_IMGDONE, C.C_IMGBAD, C.C_IMGMASK, C.C_IMGMS]
    assert offs == sorted(offs) and len(set(offs)) == len(offs)
    assert C.C_SC + 2 == C.C_SIZE
    assert C.C_IMGMS + 2 == C.C_END and C.C_FLN == C.C_SIZE2


def test_pll_steps_keep_spi_under_target_and_mcu_not_slower():
    for name, (m, n, o) in C.PLL.items():
        f, f2, mdiv, fl = C.STEPS[name]
        assert fl & C.FL_PLL and mdiv <= f2, name
        assert C.spi_mhz(C.pll_khz(m, n, o), f, f2) <= C.SPI_TARGET_MHZ, name
        assert f2 == 1 or C.spi_mhz(C.pll_khz(m, n, o), f, f2 - 1) > C.SPI_TARGET_MHZ, f"{name}: F2 not the smallest"


def test_named_pll_points():
    assert abs(C.pll_khz(*C.PLL["p372"]) / 1000 - 372.3) < 0.1
    assert abs(C.pll_khz(*C.PLL["p401"]) / 1000 - 400.9) < 0.1
    assert abs(C.pll_khz(*C.PLL["p430"]) / 1000 - 429.5) < 0.1
    assert abs(C.pll_khz(*C.PLL["p487"]) / 1000 - 486.8) < 0.1
    assert C.PASSES["pm60L"] == 200


def test_tail_offsets_contiguous():
    assert C.C_PLLM == C.C_SIZE and C.C_KEEP == C.C_MAXMHZ + 2 and C.C_E0 == C.C_PTMO + 1
    assert C.C_DIVOLD + C.N_DIV == C.C_DIVNEW and C.C_DIVNEW + C.N_DIV == C.C_PWMOLD
    assert C.C_PWMOLD + 2 * C.N_PWM == C.C_PWMNEW and C.C_PWMNEW + 2 * C.N_PWM == C.C_SIZE2
    assert len(C.DIV_NAMES) == C.N_DIV + 1 and len(C.DIV_REGS) == C.N_DIV


def test_default_envelope_names_the_487_point_inside():
    assert C.pll_khz(*C.PLL["p487"]) <= C.MAX_M2PLL_DEF_MHZ * 1000 < C.pll_khz(*C.PLL["pm69"])
