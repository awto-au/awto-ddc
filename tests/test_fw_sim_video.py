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
