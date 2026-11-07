#!/usr/bin/env python3
"""Mode-set maths trace, offline: every M-domain / DPLL / frame-sync intermediate for two source timings, side by side (#26).

usage: fw_sim_vfreq.py BIN MAP [--modes 2160p60 2160p59.94] [--max-instr 200000000]
  Runs the image in fw_sim's ucsim model (HdmiInput) once per mode, from reset to ACTIVE / NOSUPPORT, and logs at each watched
  function entry: its arguments (DWORD arg 1 from DPL/DPH/B/A, the rest from the _PARM_ cells; MulDiv / GetNewCount results
  computed here) and the M-domain globals (input timing, output timing, g_ulDClkFreq, g_usDVFreq, pixel clock, memory select).
  Also every write to P0_36..46 (frame sync, IVS2DVS, last line) and P1_B0..FF / P38_D0..EF (DPLL).
  Events are aligned by order (difflib on name) and every row whose values differ is listed.
Log: tmp/logs/fw_sim_vfreq_<bin>.log (full traces per mode + diff)
"""
import argparse, difflib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402

ROOT = S.ROOT
MODE_ACTIVE, MODE_NOSUPPORT, MODE_POWER_SAVING = 3, 4, 6
# name -> extra argument decoder kind: "d" = DWORD arg 1 in registers, "w" = WORD arg 1 (DPH:DPL), "b" = byte arg 1 (DPL)
WATCH = {"ScalerMeasureUpdateInputTimingData": "", "ScalerMDomainControl": "", "ScalerMDomainMemorySettings": "",
         "ScalerDisplaySetDVFreq": "", "ScalerMDomainMemoryConfig": "", "ScalerMDomainFSLineBufferDclkDvtotalCheck": "",
         "ScalerMDomainMemorySelectConfirm": "", "ScalerMDomainCalculateDclkDVtotal": "b", "ScalerMDomainDHVtotalFinetune": "d",
         "ScalerMDomainDHtotalFinetune": "d", "ScalerPLLSetDPLLFreqNfCascade": "d", "ScalerPLLSetDPLLOffset": "w",
         "ScalerMemoryFrameSyncSetDt": "b", "ScalerMDomainSetDisplayFormat": "b", "ScalerMDomainSetDisplayTimingGen": "",
         "ScalerDPLLFineTuneFrameSyncLineBuffer": "", "ScalerMDomainGetDisplayActiveRegion": "",
         "ScalerMeasureGetInputRegionCountResult": "", "ScalerMeasureGetDisplayRegionCountResult": "",
         "ScalerPLLGetNewCount": "d", "ScalerComputeDwordMulDiv": "d", "ScalerMemorySetIVS2DVSLineDelay": "w",
         "ScalerMemoryFineTuneIVS2DVSDelay": "", "ScalerIDomainVgipAdjustIHVDelay": "", "ScalerMDomainMemoryCheck": "",
         "ScalerMDomainUpdateLineBufferModeDVtotal": "", "ScalerMemoryGetIVS2DVSDelayPixel": "", "ScalerMDomainDisplayTimingGenCheck": "",
         "ScalerMemoryCompensateDtForLastLine": "d", "ScalerMDomainDtotalLastLineFinetune": "d"}
PARMS = {"ScalerComputeDwordMulDiv": (4, 4), "ScalerPLLGetNewCount": (4, 4), "ScalerMDomainDHtotalFinetune": (4, 4),
         "ScalerMDomainDHVtotalFinetune": (1,)}
REG_RANGES = [*range(0x0036, 0x0047), *range(0x01B0, 0x0200), *range(0x38D0, 0x38F0)]


def be(b: bytes) -> int:
    return int.from_bytes(b, "big")


def globals_(m) -> dict:
    ind = m.rd(m.addr("g_stMDomainInputData"), 21)
    out = m.rd(m.addr("g_stMDomainOutputData"), 20)
    w = lambda b, i: be(b[i:i + 2])
    return {"IHF": w(ind, 1), "IHT": w(ind, 3), "IHW": w(ind, 5), "IVF": w(ind, 11), "IVT": w(ind, 13), "IVH": w(ind, 15),
            "IVS": w(ind, 17), "DHT": w(out, 0), "DHW": w(out, 4), "DVT": w(out, 10), "DVS": w(out, 12), "DVH": w(out, 14),
            "DVBH": w(out, 18), "dclk": be(m.rd(m.addr("g_ulDClkFreq"), 4)), "DVF": be(m.rd(m.addr("g_usDVFreq"), 2)),
            "pclk": be(m.rd(m.addr("g_usInputPixelClk"), 2)), "memsel": m.rd(m.addr("g_stMDomainInfo"))[0] & 7,
            "iact": be(m.rd(m.addr("g_ulInputActiveRegionBackUp"), 4))}


def args_(m, name: str, kind: str, r: dict) -> dict:
    a = {}
    if kind == "d":
        a["a1"] = r["acc"] << 24 | r["b"] << 16 | r["dptr"]
    elif kind == "w":
        a["a1"] = r["dptr"]
    elif kind == "b":
        a["a1"] = r["dptr"] & 0xFF
    for i, n in enumerate(PARMS.get(name, ()), 2):
        try:
            a[f"a{i}"] = be(m.rd(m.addr(f"{name}_PARM_{i}"), n))
        except S.SimError:
            pass
    if name == "ScalerComputeDwordMulDiv" and a.get("a3"):
        a["=a1*a2/a3"] = a["a1"] * a["a2"] // a["a3"]
    if name == "ScalerPLLGetNewCount" and a.get("a2") and a.get("a1"):
        a["=a1*a3/a2"], a["=a2*a3/a1"] = a["a1"] * a["a3"] // a["a2"], a["a2"] * a["a3"] // a["a1"]
    return a


def run_mode(binp: Path, mapp: Path, mode: str, max_instr: int, log) -> tuple[list, str]:
    img = binp.read_bytes()
    devs, hdmi = S.video_devs(img, mode)
    taken = {ad for d in devs for ad in (*d.reads, *d.writes)}
    wl = S.WriteLog(set(REG_RANGES) - taken)
    m = S.Machine(img, mapp, binp.stem + "-vfreq-" + mode, log, [*devs, wl])
    S.video_stubs(m, hdmi)
    m.t2_scale = S.T2_SCALE
    ev: list = []
    seen_md = [False]

    def hook(name, kind):
        def fn(m_, r):
            if name == "ScalerMDomainControl":
                seen_md[0] = True
            if name in ("ScalerComputeDwordMulDiv", "ScalerPLLGetNewCount") and not seen_md[0]:
                return None                                   # OSD / timer users before the first mode set: noise
            ev.append(("call", m_.instr, name, args_(m_, name, kind, r), globals_(m_)))
            return None
        return fn
    for name, kind in WATCH.items():
        if "_" + name in m.sym:
            m.stub(name, hook(name, kind))
    ma, last, done, tl = m.addr("g_stModeInfo"), None, 0, []
    while done < max_instr:
        m.run(1_000_000)
        done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        if ms != last:
            tl.append((done, ms))
            last = ms
        if ms in (MODE_ACTIVE, MODE_NOSUPPORT, MODE_POWER_SAVING) and any(s_ == 2 for _, s_ in tl):
            break
    for ins, _, _, ad, v in wl.rows:
        ev.append(("reg", ins, f"W {ad:04X}", {"v": v}, {}))
    ev.sort(key=lambda e: e[1])
    final = {k: v for k, v in globals_(m).items()}
    summary = (f"{mode}: final {S.MODE_NAMES[last]} after ~{done // 1_000_000}M instr; "
               + " -> ".join(f"{S.MODE_NAMES[s]}@{n // 1_000_000}M" for n, s in tl)
               + f"; source model hs count {hdmi.hs_count():.3f} (reg {int(hdmi.hs_count()) - 1}, fra {int((hdmi.hs_count() % 1) * 16)}/16)"
               + f", true {hdmi.hfreq_hz / 1e3:.4f} kHz {hdmi.vfreq_hz:.4f} Hz pclk {hdmi.pclk_hz / 1e6:.4f} MHz; final globals {final}")
    m.close()
    return ev, summary


def fmt(e) -> str:
    kind, ins, name, a, g = e
    av = " ".join(f"{k}={v}" for k, v in a.items())
    gv = " ".join(f"{k}={v}" for k, v in g.items())
    return f"{ins:>10} {name:<44} {av:<60} {gv}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("map")
    ap.add_argument("--modes", nargs="+", default=["2160p60", "2160p59.94"], choices=sorted(S.HdmiInput.MODES))
    ap.add_argument("--max-instr", type=int, default=200_000_000)
    a = ap.parse_args()
    binp, mapp = Path(a.bin), Path(a.map)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / f"tmp/logs/fw_sim_vfreq_{binp.stem}.log").open("w", buffering=1)
    runs = {}
    for mode in a.modes:
        ev, summ = run_mode(binp, mapp, mode, a.max_instr, None)
        runs[mode] = ev
        print(summ)
        log.write(f"=== {summ}\n")
        for e in ev:
            log.write(fmt(e) + "\n")
    if len(a.modes) >= 2:
        A, B = runs[a.modes[0]], runs[a.modes[1]]
        sm = difflib.SequenceMatcher(None, [e[2] for e in A], [e[2] for e in B], autojunk=False)
        out = [f"=== diff {a.modes[0]} (<) vs {a.modes[1]} (>): rows whose arguments or globals differ"]
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                for x, y in zip(A[i1:i2], B[j1:j2]):
                    if x[3] != y[3] or x[4] != y[4]:
                        keys = [k for k in {**x[3], **x[4]} if {**x[3], **x[4]}.get(k) != {**y[3], **y[4]}.get(k)]
                        out.append(f"  {x[2]:<44} " + "  ".join(f"{k} {({**x[3], **x[4]}).get(k)} | {({**y[3], **y[4]}).get(k)}" for k in keys))
            else:
                out += [f"< {fmt(e)}" for e in A[i1:i2]] + [f"> {fmt(e)}" for e in B[j1:j2]]
        for ln in out:
            print(ln)
            log.write(ln + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
