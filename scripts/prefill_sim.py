#!/usr/bin/env python3
"""#83 idle-port cache pre-fill in the fw_sim model: HDMI on D2 on screen, a live DP source on idle D1.

usage: prefill_sim.py BIN MAP [--mode 2160p60] [--secs 12] [--no-switch]
  DP is modelled at the ScalerDp* dispatch level (as fw_sim_dp.py), armed only after ACTIVE on D2 (else the boot search
  could pick D1): PreDetect / StableDetect true for D1; ScanInputPort(D1) returns DP and, like the SDK scan, writes the
  shared globals (isr_g_usInputPixelClk = D1's clock, isr_g_stColorInfo byte 0 changed) so the restore is tested.
  PASS: D1 cache valid 2 after --secs, one background scan, on-screen pixel clock / colour info / P31_00 / P0_28 bit5 /
  FF22 / mode / port unchanged; then test cmd 0x31 takes the fast path (switch log 0xA0 arg 0), ACTIVE on D1, P31_00 0x40.
Log: tmp/logs/prefill_sim.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import sw_timeline as T  # noqa: E402

D1, D2 = 4, 5
SOURCE_DP = 4
TESTCMD = 0xF6F8
CACHE_ENTRY = 2 + 48                    # StAwtoSwCache: ucValid, ucSourceType, pucScaler[AWTO_FAST_SCALER_BYTES]


def port_now(bus) -> int:
    pri = bus.xdata(bus.addr("g_pucSourceSearchPriority"), 10)
    return pri[bus.xdata(bus.addr("g_ucSearchIndex"))[0] % 10]


def snap(bus) -> dict:
    return {"pclk": bus.xdata(bus.addr("isr_g_usInputPixelClk"), 2).hex(), "color": bus.xdata(bus.addr("isr_g_stColorInfo"), 8).hex(),
            "P31_00": bus.xdata(0x3100)[0] & 0xF0, "P0_28.5": bus.xdata(0x0028)[0] & 0x20, "FF22": bus.xdata(0xFF22)[0],
            "mode": bus.mode_state(), "port": port_now(bus)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60")
    ap.add_argument("--secs", type=float, default=12.0, help="first try at 2 s (AWTO_PF_STEP_MS) after ACTIVE, then margin")
    ap.add_argument("--no-switch", action="store_true")
    a = ap.parse_args()
    (S.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (S.ROOT / "tmp/logs/prefill_sim.log").open("a", buffering=1)

    def say(s):
        print(s); log.write(s + "\n")

    bus = S.SimBus(a.bin, a.map, video=a.mode, port="D2")
    armed, scans = [False], []
    m = bus.m

    def scan(m_, r):
        if not armed[0] or (r["a1"] & 255) != D1:
            return {"val": 5}
        scans.append(round(bus.now(), 3))
        m_.wr(m_.addr("isr_g_usInputPixelClk"), bus.hdmi.PCLK.to_bytes(2, "big"))
        c = m_.rd(m_.addr("isr_g_stColorInfo"), 1)[0]
        m_.wr(m_.addr("isr_g_stColorInfo"), bytes([c ^ 0x5A]))
        return {"val": SOURCE_DP}
    m.stub("ScalerDpNormalPreDetect", lambda m_, r: {"carry": int(armed[0] and (r["a1"] & 255) == D1)})
    m.stub("ScalerDpScanInputPort", scan)
    m.stub("ScalerDpStableDetect", lambda m_, r: {"carry": int(armed[0] and (r["a1"] & 255) == D1)})
    try:
        if not bus.run_until_mode(3):
            say(f"FAIL {a.bin.name}: no ACTIVE on D2"); return 1
        bus.wait(0.5)
        before = snap(bus)
        cache = bus.addr("s_pstAwtoSwCache")
        say(f"{a.bin.name}: ACTIVE on 0x{before['port']:02X}, cache valid D1..D3 {list(bus.xdata(cache, 3 * CACHE_ENTRY)[0::CACHE_ENTRY])}")
        armed[0] = True
        bus.wait(a.secs)
        after = snap(bus)
        v = list(bus.xdata(cache, 3 * CACHE_ENTRY)[0::CACHE_ENTRY])
        _, evs = T.decode(bus.xdata(bus.addr("isr_g_stAwtoSw"), 12 + 4 * T.N_EV), bus.be)
        pf = [g for _, i, g in evs if i == 0xB9]
        same = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        ok = v[0] == 2 and len(scans) == 1 and not same and pf[-1:] == [1] and set(pf[:-1]) <= {2}    # tries before the arm: pre-detect false
        say(f"  scans at fw s {scans}; prefill events {pf}; cache valid {v}; on-screen state changed: {same or 'none'}")
        say(f"prefill: {'PASS' if ok else 'FAIL'} (want D1 valid 2, 1 scan, events 2.. then 1, nothing changed)")
        if not a.no_switch:
            bus.m.wr(TESTCMD, bytes([0x31]))
            bus.wait(1.5)
            _, evs = T.decode(bus.xdata(bus.addr("isr_g_stAwtoSw"), 12 + 4 * T.N_EV), bus.be)
            fast = [g for _, i, g in evs if i == 0xA0]
            s2 = snap(bus)
            for ms, i, g in evs[-16:]:
                say(f"    +{ms:6d} ms  {T.name(i, g)}")
            ok2 = 0 in fast and s2["mode"] == 3 and s2["port"] == D1 and s2["P31_00"] == 0x40
            say(f"switch: {'PASS' if ok2 else 'FAIL'} fast events {fast}, mode {s2['mode']} port 0x{s2['port']:02X} P31_00 0x{s2['P31_00']:02X}")
            ok = ok and ok2
        return 0 if ok else 1
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main())
