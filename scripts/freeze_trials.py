#!/usr/bin/env python3
"""awto-ddc#26: freeze a failed 4K60 pass, then try vendor-value register candidates, one per trial.

usage: freeze_trials.py --unit N --bus B --serial S [--only T1,T2] [--n 30]
  Freeze as dpll_hold.py/freeze_dump.py (main paused 0x80 01). Per trial: write candidate regs (0xPPRR=VV via 0x35),
  clear P0_02 (write FF), read P0_02 x n; then restore the originals. A baseline burst (no write) precedes each trial.
  Candidates = registers that differ from the vendor 4K60 dump and are config (regs_diff4k.py). Log: tmp/logs/freeze_trials.log
"""
import argparse, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr, DBG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
f2 = lambda v: "--" if v is None else format(v, "02x")
LS = [(0x03BF, 0x00), (0x03D1, 0x20), (0x03D4, 0x1D), (0x03D5, 0xA9), (0x03D9, 0x30), (0x03DB, 0x38), (0x03DC, 0x94),
      (0x43D1, 0x20), (0x43D4, 0x1D), (0x43D5, 0xA9), (0x43D9, 0x30), (0x43DB, 0x38), (0x43DC, 0x94)]
MEAS = [(0x1602, 0x21), (0x1617, 0x07), (0x1618, 0x30), (0x161C, 0x80)]
DITH = [(0x0062, 0x07), (0x006A, 0x30), (0x0089, 0x30), (0x0068, 0x40)]
DFP = lambda *kv: [(0x2A00 | k, v) for k, v in kv]            # 0x2Axx = display-format port index xx (port 0x2A/0x2B)
TRIALS = {
    "D1_vtot_vstart": DFP((0x0B, 0x09), (0x0C, 0x07), (0x0F, 0x08), (0x11, 0x08), (0x13, 0x78), (0x15, 0x78)),
    "D2_vstart_only": DFP((0x0F, 0x08), (0x11, 0x08), (0x13, 0x78), (0x15, 0x78)),
    "D3_vtotal_only": DFP((0x0B, 0x09), (0x0C, 0x07)),
    "D4_fixed_dvtotal": DFP((0x30, 0x09), (0x31, 0x08)),
    "D5_all": DFP((0x0B, 0x09), (0x0C, 0x07), (0x0F, 0x08), (0x11, 0x08), (0x13, 0x78), (0x15, 0x78), (0x30, 0x09), (0x31, 0x08)),                                                      # vendor value from tmp/regs/AWT26110003-20261105-180523.json
    "T1_28_0b": [(0x0028, 0x0B)],                               # frame_sync_en, no force_en/force_bg (vendor ACTIVE)
    "T2_28_2b": [(0x0028, 0x2B)],
    "T3_28_ab": [(0x0028, 0xAB)],
    "T4_31C0_80": [(0x31C0, 0x80)],                             # imd_db_en
    "T5_SDF_c1": [(0x0026, 0xC1), (0x4026, 0xC1)],              # sd_mask_lsb2bits_en M1/M2
    "T6_ivs2dvs": [(0x003D, 0xD0), (0x0041, 0xD1)],
    "T7_3040_00": [(0x3040, 0x00)],
    "T8_LS": LS,
    "T9_dpllm_45": [(0x01BF, 0x45), (0x01C0, None)],            # None = rewrite current value (latch trigger)
    "T10_07FC_15": [(0x07FC, 0x15)],
    "T11_dither": DITH,
    "T12_meas": MEAS,
    "A1_a32e_fe": [(0xA32E, 0xFE)],                             # DDR PHY LPDDR mode_reg_addr bit6 set (vendor value), #26
    "A2_ddr_err_clr": [(0xA851, 0x00), (0xA852, 0x00), (0xA853, 0x00), (0xA86E, 0x00), (0xA86F, 0x00)],   # clear DDR PHY sticky FIFO errors
    # full write-trace diff candidates (#26): ISP-dump values vendor ACTIVE vs ours failing that the sim trace shows the vendor writing
    "V1_dptx_drive": [(0x38B6, 0xFF), (0x38B7, 0xFF), (0x38BA, 0xDD), (0x38BB, 0xDD), (0x38BE, 0x22), (0x38BF, 0x22),
                      (0x38AE, 0x00), (0x38AF, 0x00), (0x38B0, 0x00), (0x38B1, 0x00)],
    "V2_ycc2rgb": [(0x14A1, 0x11)],
    "V3_pin_fe1b": [(0xFE1B, 0x00)],
    "V4_all": [(0x38B6, 0xFF), (0x38B7, 0xFF), (0x38BA, 0xDD), (0x38BB, 0xDD), (0x38BE, 0x22), (0x38BF, 0x22), (0x38AE, 0x00),
               (0x38AF, 0x00), (0x38B0, 0x00), (0x38B1, 0x00), (0x14A1, 0x11), (0xFE1B, 0x00)],
    "T13_all": [(0x0028, 0x0B), (0x31C0, 0x80), (0x0026, 0xC1), (0x4026, 0xC1), (0x003D, 0xD0), (0x0041, 0xD1),
                (0x3040, 0x00), (0x07FC, 0x15)] + LS + DITH + MEAS,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--only")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    lf = (ROOT / "tmp/logs/freeze_trials.log").open("a")

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    i2cbus.require_unit(a.bus, a.serial)
    d = Real(a.bus, allow_write=True)
    proc = subprocess.Popen(["./dev.py", "mode", "--unit", str(a.unit), "4k60"], cwd=ROOT)
    end = time.monotonic() + 12.0
    while time.monotonic() < end:
        nxt = time.monotonic() + 0.03
        while time.monotonic() < nxt:
            pass
        p, r40 = rd(d, 0x0002), rd(d, 0x0040)
        if p is not None and r40 == 0x24 and (p & 0x61) == 0x01:
            break
    else:
        log("no failed 4K pass seen; aborting"); proc.wait(); return 1
    d.write(DBG, 0x80, bytes([0x01]))
    log(f"froze main at P0_02={p:02x} P0_40={r40:02x} P0_28={f2(rd(d, 0x28))}")

    def burst(tag):
        wr(d, 0x0002, 0xFF)
        vals = [rd(d, 0x0002) for _ in range(a.n)]
        flags = {v for v in vals if v}
        log(f"{tag}: P0_02 x{a.n} = " + " ".join(f2(v) for v in vals) + f"  -> {'CLEAN' if not flags else 'flags ' + ','.join(f2(f) for f in sorted(flags))}")

    def prd(ad):                                                # 0x2Axx -> display-format port read, else plain
        if ad >> 8 != 0x2A or ad > 0x2AFF:
            return rd(d, ad)
        wr(d, 0x002A, ad & 0xFF); return rd(d, 0x002B)

    def pwr(ad, v):
        if ad >> 8 != 0x2A:
            return wr(d, ad, v)
        return wr(d, 0x002A, ad & 0xFF) and wr(d, 0x002B, v)

    sel = a.only.split(",") if a.only else list(TRIALS)
    for name in sel:
        regs = TRIALS[name]
        burst(f"{name} baseline")
        a2a = rd(d, 0x002A); orig = [(ad, prd(ad)) for ad, _ in regs]
        for ad, v in regs:
            v = prd(ad) if v is None else v
            if not any(pwr(ad, v) for _ in range(3)):
                log(f"  write {ad:04X} failed")
        log(f"  wrote {' '.join(f'{ad:04X}={f2(prd(ad))}' for ad, _ in regs[:6])}{' ...' if len(regs) > 6 else ''}")
        burst(f"{name} candidate")
        if name.startswith("A"):
            log("  readback " + " ".join(f"{ad:04X}={f2(prd(ad))}" for ad in (0xA32E, 0xAB28, 0xA851, 0xA852, 0xA853, 0xA86E, 0xA86F)))
        for ad, v in orig:
            if v is not None:
                pwr(ad, v)
        if a2a is not None:
            wr(d, 0x002A, a2a)
    d.write(DBG, 0x80, bytes([0x00])); log("resumed main")
    proc.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
