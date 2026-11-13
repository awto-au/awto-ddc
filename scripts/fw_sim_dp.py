#!/usr/bin/env python3
"""DP Rx1 (D1) scenarios in the firmware sim (#28): which input goes ACTIVE, the DPCD caps the firmware set, the debug IIC channel.

usage: fw_sim_dp.py BIN MAP [--case dp|hdmi-dpidle|all] [--mode 1080p60] [--instr 120000000]
  dp           D1 DP source with video, HDMI D2 cable in but no TMDS: want ACTIVE on D1
  hdmi-dpidle  HDMI video on D2, DP cable in (HPD/AUX up) but no video stream: want ACTIVE on D2 (DP must not take over)
Model: fw_sim.video_devs (regdb reset, D2 cable, DPCD access port PBA_C1..C4, measure/auto-function cells) + DP cable pins
  PA3=0 PA4=1 PA5=1 (bD1_CONNECT, RL6449_AWTO_JXC4K.h). DP is modelled at the ScalerDp* dispatch level, like HDMI at
  ScalerTMDS*: NormalPreDetect / ScanInputPort / StableDetect stubbed; link training, MSA and the DP PHY are not modelled.
Report: mode timeline, active port, DPCD 0x00000..0x0000F from the access-port model, IIC_CH_SEL (FF22 bits 2:0 = DDC n).
Log: tmp/logs/fw_sim_dp.log
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import unit_health as H  # noqa: E402

D1, D2 = 4, 5                       # Global.h _D1_INPUT_PORT / _D2_INPUT_PORT
SOURCE_HDMI, SOURCE_DP, SOURCE_NONE = 3, 4, 5
DP_CABLE = {0xFE33: 0, 0xFE34: 1, 0xFE35: 1}
DDC_NAMES = {0: "VGA_DDC", 1: "DDC0", 2: "DDC1 (D1 DP AUX)", 3: "DDC2 (D2 HDMI)", 4: "DDC3"}
PORT_NAMES = {D1: "D1 DP", D2: "D2 HDMI", 6: "D3 HDMI", 0x0A: "none"}


def stubs(m, case: str, pclk: int, calls: list):
    def pre_tmds(m_, r):
        return {"carry": int(case == "hdmi-dpidle" and (r["a1"] & 255) == D2)}

    def scan_tmds(m_, r):
        if case == "hdmi-dpidle" and (r["a1"] & 255) == D2:
            m_.wr(m_.addr("isr_g_usInputPixelClk"), pclk.to_bytes(2, "big"))
            return {"val": SOURCE_HDMI}
        return {"val": SOURCE_NONE}

    def pre_dp(m_, r):              # hdmi-dpidle: link trained / idle pattern -> pre-detect true, scan finds no stream
        return {"carry": int((r["a1"] & 255) == D1)}

    def scan_dp(m_, r):
        if case == "dp" and (r["a1"] & 255) == D1:
            m_.wr(m_.addr("isr_g_usInputPixelClk"), pclk.to_bytes(2, "big"))
            return {"val": SOURCE_DP}
        return {"val": SOURCE_NONE}
    m.stub("ScalerTMDSNormalPreDetect", pre_tmds)
    m.stub("ScalerTMDSScanInputPort", scan_tmds)
    m.stub("ScalerTMDSStableDetect", lambda m_, r: {"carry": 1})
    m.stub("ScalerDpNormalPreDetect", pre_dp)
    m.stub("ScalerDpScanInputPort", scan_dp)
    m.stub("ScalerDpStableDetect", lambda m_, r: {"carry": int(case == "dp")})
    m.stub("ScalerSyncDpCheckUrgentHotPlugEventExist", lambda m_, r: {"carry": 0})
    m.stub("ScalerMcuDdcciSwitchPort", lambda m_, r: calls.append(r["a2"]))     # watch: port argument per call


def run_case(binp: Path, mapp: Path, case: str, mode: str, max_instr: int, log) -> tuple[bool, list[str]]:
    img = binp.read_bytes()
    devs, hdmi = S.video_devs(img, mode)
    devs.append(S.Cells(DP_CABLE))
    dpcd = next(d for d in devs if isinstance(d, S.IndPort))
    m = S.Machine(img, mapp, f"{binp.stem}-dp-{case}", log, devs)
    calls: list[int] = []
    stubs(m, case, hdmi.PCLK, calls)
    m.t2_scale = S.T2_SCALE
    ma, timeline, done, last = m.addr("isr_g_stModeInfo"), [], 0, None
    while done < max_instr:
        m.run(1_000_000); done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        if ms != last:
            timeline.append((done, ms)); last = ms
            if ms == H.MODE_ACTIVE:
                break
    n0 = len(calls)
    for _ in range(40):                                  # until the active proc's DDC-CI switch (SDK: to the active port)
        m.run(1_000_000)
        if len(calls) > n0:
            m.run(1_000_000); break
    ms = m.rd(ma)[0] & 0x1F
    pri = m.rd(m.addr("g_pucSourceSearchPriority"), 10)
    port = pri[m.rd(m.addr("g_ucSearchIndex"))[0] % 10]
    t = H.decode_timing(m.rd(m.addr("g_stMDomainInputData"), 17))
    ch = m.rd(0xFF22)[0] & 7
    caps = [dpcd.mem.get(a, None) for a in range(0x10)]
    want = D1 if case == "dp" else D2
    ok = ms == H.MODE_ACTIVE and port == want and ch == 3 and len(calls) >= 2
    lines = [f"{case}: {'PASS' if ok else 'FAIL'} mode {S.MODE_NAMES[ms] if ms < len(S.MODE_NAMES) else ms}, "
             f"port 0x{port:02X} {PORT_NAMES.get(port, '?')} (want {PORT_NAMES[want]}), "
             f"IIC_CH_SEL {ch} {DDC_NAMES.get(ch, '?')} (want DDC2); DdcciSwitchPort port args "
             + (" ".join(f"0x{c:02X}" for c in calls) or "none"),
             "  timeline: " + " -> ".join(f"{S.MODE_NAMES[s]}@{n // 1_000_000}M" for n, s in timeline),
             f"  input {t['hwidth']}x{t['vheight']}@{t['vfreq'] / 10:.1f} htotal {t['htotal']} vtotal {t['vtotal']}",
             "  DPCD 00000..0000F: " + " ".join("--" if v is None else f"{v:02X}" for v in caps)
             + f"  (rev {caps[0] or 0:02X}, max rate {caps[1] or 0:02X}, lanes {(caps[2] or 0) & 0x1F})",
             f"  stub hits: {m.stub_hits}"]
    m.close()
    return ok, lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--case", choices=["dp", "hdmi-dpidle", "all"], default="all")
    ap.add_argument("--mode", default="1080p60", choices=sorted(S.HdmiInput.MODES))
    ap.add_argument("--instr", type=int, default=120_000_000)
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (S.ROOT / "tmp/logs/fw_sim_dp.log").open("a", buffering=1)
    rc = 0
    for case in (["dp", "hdmi-dpidle"] if a.case == "all" else [a.case]):
        ok, lines = run_case(a.bin, a.map, case, a.mode, a.instr, log)
        for ln in lines:
            print(ln); log.write(ln + "\n")
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
