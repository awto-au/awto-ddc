"""Firmware simulator with a stable HDMI source on D2 (#38): register model (pure) + the real image (slow). Offline."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fw_sim  # noqa: E402

IMG = ROOT / "tmp/fw/AWT26110003-wb-clu3-be"
needs_img = pytest.mark.skipif(not IMG.with_suffix(".bin").exists() or not IMG.with_suffix(".map").exists(),
                               reason="image tmp/fw/AWT26110003-wb-clu3-be.{bin,map} absent")


def w(c, hi, lo, mask):
    return ((c[hi] & mask) << 8 | c[lo]) + 1


def test_hdmi_input_registers_decode_like_the_sdk():
    """ScalerMeasureGetOfflineMeasureResult / GetAutoResult arithmetic applied to the preset cells."""
    h = fw_sim.HdmiInput("1080p60")
    c = h.cells()
    assert w(c, 0x300E, 0x300F, 0x1F) == 2200 and w(c, 0x3013, 0x3014, 0x1F) == 1920     # htotal, hwidth (digital)
    assert w(c, 0x3008, 0x3009, 0x3F) == 1125 and w(c, 0x3011, 0x3012, 0x3F) == 1080     # vtotal, vheight
    clk = fw_sim.HdmiInput.MEAS_KHZ
    hsp = w(c, 0x3005, 0x3006, 0x1F)
    assert (clk * 10 * 2 // hsp + 1) // 2 == 675                                      # usHFreq 0.1 kHz
    assert (clk * 1000 * 10 * 2 // hsp // 1125 + 1) // 2 == 600                              # usVFreq 0.1 Hz
    a = h.auto(False)
    vs = (a[0x007E] & 0xF0) << 4 | a[0x007F]
    ve = (a[0x007E] & 0x0F) << 8 | a[0x0080]
    hs = ((a[0x0081] & 0xF0) << 4 | a[0x0082]) + 1
    he = ((a[0x0081] & 0x0F) << 8 | a[0x0083]) + 1
    assert (he - hs + 1, ve - vs + 1) == (1920, 1080)
    af = h.auto(True)                                                                      # F-to-P on: hardware reports field lines
    assert ((af[0x007E] & 0x0F) << 8 | af[0x0080]) - ((af[0x007E] & 0xF0) << 4 | af[0x007F]) + 1 == 540


@pytest.fixture(scope="module")
def vbus():
    b = fw_sim.SimBus(IMG.with_suffix(".bin"), IMG.with_suffix(".map"), video="1080p60")
    yield b
    b.close()


@needs_img
@pytest.mark.slow
def test_video_source_found_and_mode_active(vbus):
    import unit_health as H
    assert vbus.run_until_mode(H.MODE_ACTIVE), f"mode state {vbus.mode_state()}"
    t = H.decode_timing(vbus.xdata(vbus.addr("g_stMDomainInputData"), 17))
    assert (t["hwidth"], t["vheight"], t["vfreq"], t["hfreq"]) == (1920, 1080, 600, 675)


@needs_img
@pytest.mark.slow
def test_all_ten_health_checks_pass_in_the_sim(vbus):
    import unit_health as H
    vbus.run_until_mode(H.MODE_ACTIVE)
    maps = {n: H.sym_addr(IMG.with_suffix(".map").read_text(errors="replace"), n) for n in H.MAP_SYMS}
    rep = H.Report()
    rep.add("bus rate", True, "sim")
    H.run(H.Dbg(vbus, wait=vbus.wait, now=vbus.now), maps, (1920, 1080, 60.0), rep, wait=vbus.wait)
    assert len(rep.rows) == 10 and all(ok for _, ok, _ in rep.rows), rep.rows


# ---- 2160p60 (#26): data path above _DATA_PATH_SPEED_LIMIT, line-buffer 4K60 ----------------------------------
IMG_B = ROOT / "tmp/fw/AWT26110003-wb-stepB-be"
IMG_FRC = ROOT / "tmp/fw/AWT26110003-wb-frc-be"


def _needs(img):
    return pytest.mark.skipif(not img.with_suffix(".bin").exists() or not img.with_suffix(".map").exists(),
                              reason=f"image {img.name}.{{bin,map}} absent")


def _video(img, mode, fault=None, max_instr=200_000_000):
    import io
    log = io.StringIO()
    rc = fw_sim.video_check(img.with_suffix(".bin"), img.with_suffix(".map"), mode, max_instr, log, fault)
    return rc, log.getvalue()


def test_hdmi_input_2160p60_registers_follow_the_data_path():
    """594 MHz > 300 MHz limit: measure divider /2 halves the offline H total/width (code doubles), 1/2 scaling down halves the
    auto-function H window (code doubles), F-to-P keeps full H; auto-function H end > 4095 sets P0_78 bit0. Same register values as the
    vendor 4K60 dump (tmp/regs/AWT26110003-20261105-180523.json: P30_0E/0F 0x0897, P30_13/14 0x077F)."""
    h = fw_sim.HdmiInput("2160p60")
    assert h.fast and set(h.writes) == {0x3000, 0x3105, 0x3106, 0x0044, 0x3045}       # + last-line / display-count models
    h.div = True
    c = h.cells()
    assert w(c, 0x300E, 0x300F, 0x1F) == 2200 and (c[0x300E], c[0x300F]) == (0x08, 0x97)
    assert w(c, 0x3013, 0x3014, 0x1F) == 1920 and (c[0x3013], c[0x3014]) == (0x07, 0x7F)
    h.halfsd = True
    a = h.auto(False)
    hs = ((a[0x0081] & 0xF0) << 4 | a[0x0082]) + 1
    he = ((a[0x0081] & 0x0F) << 8 | a[0x0083]) + 1
    assert (he - hs + 1) * 2 == 3840 and a[0x0078] == 0                                  # half pixels, no bit 12
    h.halfsd = False
    a = h.auto(True)                                                                      # F-to-P: full H, half V
    he = ((a[0x0081] & 0x0F) << 8 | a[0x0083]) + 1 + (a[0x0078] & 1) * 4096
    hs = ((a[0x0081] & 0xF0) << 4 | a[0x0082]) + 1
    assert he - hs + 1 == 3840 and a[0x0078] & 1 == 1                                    # end 4223 needs P0_78 bit0
    assert fw_sim.HdmiInput("1080p60").writes == (0x3106, 0x0044, 0x3045) and not fw_sim.HdmiInput("1080p60").fast


def test_hdmi_input_60_000_vs_59_940_hs_period():
    """Unit 3 measured 4K60.000 as 60.1 Hz and 4K59.940 as 60.0 (mode_sweep 2026-11-07): HS period whole counts, truncated (#26)."""
    sdk = lambda h: (lambda hsp: ((87697 * 20 // hsp + 1) // 2, (87697 * 20000 // hsp // h.VTOT + 1) // 2))(
        w(h.cells(), 0x3005, 0x3006, 0x1F))                                             # _MEASURE_CLK 350791 / 4 (kHz)
    a, b = fw_sim.HdmiInput("2160p60"), fw_sim.HdmiInput("2160p59.94")
    assert sdk(a) == (1351, 601) and sdk(b) == (1349, 600)
    assert a.PCLK == 5940 and b.PCLK == 5934 and abs(b.vfreq_hz - 59.94006) < 1e-4


@_needs(IMG_B)
@pytest.mark.slow
def test_2160p60_decodes_and_reaches_active_with_healthy_status():
    rc, txt = _video(IMG_B, "2160p60")
    assert rc == 0, txt
    assert "3840x2160@60.0 htotal 4400 vtotal 2250" in txt
    assert "P30_00 0x82 P31_05 0x88 P31_06 0x80" in txt                                   # vendor dump values
    assert "g_ulDClkFreq 539553 kHz" in txt and "in range" in txt


@_needs(IMG_B)
@pytest.mark.slow
def test_2160p60_ends_in_power_saving_on_fifo_underflow():
    """Hardware dump of the unit-3 build at 4K60 has P0_02 bit0 (M-domain FIFO underflow) set, the vendor dump not: with that flag
    kept raised ScalerMDomainMemoryCheck fails, display setting is never ready, NOSUPPORT after 2 s, then POWER_SAVING."""
    rc, txt = _video(IMG_B, "2160p60", "underflow")
    assert rc == 1
    assert "final mode 6 POWER_SAVING" in txt and "DISPLAY_SETTING@" in txt and "NOSUPPORT@" in txt
    assert "decision ScalerMDomainMemoryCheck" in txt and "FAIL: P0_02.0 FIFO underflow" in txt
    assert "supported" in txt and "in range" in txt                                       # the SDK-level checks all pass


@_needs(IMG_FRC)
@pytest.mark.slow
def test_frc_image_2160p60_line_buffer_reaches_active():
    rc, txt = _video(IMG_FRC, "2160p60")
    assert rc == 0, txt
    assert "ScalerMDomainMemoryCheck" in txt and "pass" in txt
