#!/usr/bin/env python3
"""M-domain memory-select decision trace + wide register diff vs the vendor 4K60 dump, offline (#26).

usage: fw_sim_mdomain.py BIN MAP [--mode 2160p60] [--max-instr 200000000] [--vendor tmp/regs/AWT26110003-20261105-180523.json]
  Runs the image in fw_sim's ucsim model with a stable HDMI source and logs, at the entry of each decision function
  (ScalerMDomainMemorySettings .. ScalerMDomainMemoryCheck), g_stMDomainInfo (memory select / DVF select / config), DVF, panel DVF
  window, M-domain in/out timing, P31_06 (F-to-P), P5_AC (bit2 = frame-sync line buffer source), P0_28.
  Then lists every register in P0/P1/P5/P45/P20/P30/P31/P37/P40 the firmware wrote whose last value differs from the vendor dump
  (vendor dump = ACTIVE at 4K60; status/measure registers differ by nature).
Log: tmp/logs/fw_sim_mdomain_<bin>_<mode>.log
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as S  # noqa: E402
import fw_regs  # noqa: E402

ROOT = S.ROOT
PAGES = (0x00, 0x01, 0x05, 0x45, 0x20, 0x30, 0x31, 0x37, 0x40)
MODE_ACTIVE, MODE_POWER_SAVING = 3, 6
FNS = ("ScalerMDomainMemorySettings", "ScalerDisplaySetDVFreq", "ScalerMDomainMemoryConfig", "ScalerMDomainFSLineBufferDclkDvtotalCheck",
       "ScalerMDomainMemorySelectConfirm", "ScalerMDomainCalculateDclkDVtotal", "ScalerMDomainSetDisplayFormat", "ScalerMemoryInitial",
       "ScalerFRCInitial", "ScalerMemoryFrameSyncSetDt", "ScalerFRCControl", "ScalerFRCEn", "ScalerMemoryReset", "ScalerMDomainMemoryCheck",
       "ScalerDPLLFineTuneFrameSyncLineBuffer", "ScalerFmtCnvFinalSetting")


def snapshot(m: "S.Machine", name: str) -> str:
    w = lambda a, n: [int.from_bytes(m.rd(a + 2 * i, 2), "big") for i in range(n)]
    info = m.rd(m.addr("g_stMDomainInfo"), 2)
    sel, dvf, conf = info[0] & 7, (info[0] >> 3) & 7, info[0] >> 6
    cust = m.rd(m.addr("g_stDVCustomizedFreq"), 7)
    out = w(m.addr("g_stMDomainOutputData"), 10)
    ind = m.rd(m.addr("g_stMDomainInputData"), 17)
    dclk = int.from_bytes(m.rd(m.addr("g_ulDClkFreq"), 4), "big")
    dvf_hz = int.from_bytes(m.rd(m.addr("g_usDVFreq"), 2), "big")
    return (f"{name}: memsel={sel} dvfsel={dvf} memconf={conf} | g_usDVFreq={dvf_hz} DVCust force_fr/8b={cust[0] & 3} "
            f"max/typ/min={int.from_bytes(cust[1:3], 'big')}/{int.from_bytes(cust[3:5], 'big')}/{int.from_bytes(cust[5:7], 'big')} | "
            f"out htot/hst/hw/hbs/hbw={out[0]}/{out[1]}/{out[2]}/{out[3]}/{out[4]} vtot/vst/vh/vbs/vbh={out[5]}/{out[6]}/{out[7]}/{out[8]}/{out[9]} | "
            f"in={ind.hex()} | dclk={dclk} kHz | P31_06={m.rd(0x3106)[0]:02X} P5_AC={m.rd(0x05AC)[0]:02X} P0_28={m.rd(0x0028)[0]:02X} "
            f"P0_02={m.rd(0x0002)[0]:02X} P5_27={m.rd(0x0527)[0]:02X}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("map")
    ap.add_argument("--mode", default="2160p60", choices=sorted(S.HdmiInput.MODES))
    ap.add_argument("--max-instr", type=int, default=200_000_000)
    ap.add_argument("--vendor", default=str(ROOT / "tmp/regs/AWT26110003-20261105-180523.json"))
    a = ap.parse_args()
    binp, mapp = Path(a.bin), Path(a.map)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / f"tmp/logs/fw_sim_mdomain_{binp.stem}_{a.mode}.log").open("w", buffering=1)
    img = binp.read_bytes()
    devs, hdmi = S.video_devs(img, a.mode)
    taken = {ad for d in devs for ad in (*d.reads, *d.writes)}            # one hook per address: keep the source/IO models' registers
    ranges = {pg << 8 | i for pg in PAGES for i in range(256)} - taken
    wl = S.WriteLog(ranges)
    m = S.Machine(img, mapp, binp.stem + "-mdom", log, [*devs, wl])
    S.video_stubs(m, hdmi)
    m.t2_scale = S.T2_SCALE
    rows: list[str] = []
    for fn in FNS:
        if "_" + fn in m.sym:
            m.stub(fn, lambda m_, r, fn=fn: rows.append(f"{m_.instr:>10} " + snapshot(m_, fn)) or None)
    ma, last, done, tl = m.addr("isr_g_stModeInfo"), None, 0, []
    while done < a.max_instr:
        m.run(1_000_000)
        done += 1_000_000
        ms = m.rd(ma)[0] & 0x1F
        if ms != last:
            tl.append((done, ms))
            last = ms
        if ms in (MODE_ACTIVE, MODE_POWER_SAVING) and any(s_ in (2, 4) for _, s_ in tl):
            break
    out = [f"{binp.name} {a.mode}: final mode {S.MODE_NAMES[last]} after ~{done} instr; timeline "
           + " -> ".join(f"{S.MODE_NAMES[s]}@{n // 1_000_000}M" for n, s in tl)]
    out += rows
    final = {}
    for _, _, _, ad, v in wl.rows:
        final[ad] = v
    vend = S.vendor_pages(Path(a.vendor))
    names = fw_regs.names()
    diff = [(ad, v, vend[ad]) for ad, v in sorted(final.items()) if ad in vend and vend[ad] != v]
    out.append(f"written registers in pages {[hex(p) for p in PAGES]}: {len(final)}; equal to vendor "
               f"{sum(1 for ad in final if ad in vend and vend[ad] == final[ad])}; differ {len(diff)}:")
    out += [f"  0x{ad:04X} {names.get(ad, '?'):<38} ours 0x{v:02X} vendor 0x{w:02X}" for ad, v, w in diff]
    m.close()
    for ln in out:
        print(ln)
        log.write(ln + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
