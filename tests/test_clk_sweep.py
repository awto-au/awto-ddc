"""scripts/clk_sweep.py: the step table stays inside the flash rating and the firmware's own refusal rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import clk_sweep as C  # noqa: E402

PLL_KHZ = 350_791                       # M2PLL of the unit: 14318 kHz x 49 / 2


def test_steps_inside_rating():
    for name, (f, f2, m, fl) in C.STEPS.items():
        assert 1 <= f <= 15 and 1 <= f2 <= 15 and 1 <= m <= 15, name
        spi = C.spi_mhz(PLL_KHZ, f, f2)
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
    assert C.C_IMGMS + 2 == C.C_SIZE
