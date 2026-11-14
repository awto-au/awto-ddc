#!/usr/bin/env python3
"""awto-ddc#26: live DDR PHY read-path sweep, flags as pass/fail (debug slave 0x35, MCU not paused).

usage: ddr_sweep.py --unit N --bus B --serial S CMD [args]
  state                       print the read-path controls (both channels)
  base [--n 5]                baseline flag measurement (both channels)
  sweep NAME [--ch A|B|AB]    step one control through its range, restore after
  trig NAME                   re-trigger calibration (pulse registers), measure before/after
Channel A = pages 8E/8F/A0, B = CE/CF/A8. Flags: VW = VALID_WIN_DET_SLIC0/1 (8F04-0B), CALINT = INT_STATUS1 (8FF0-F7).
Settle 200 ms after each step: flags returned within ~0.5 s of a clear (#26), 200 ms is a 2.5x margin on 80 ms observed re-set.
Log: tmp/logs/ddr_sweep.log; maps: tmp/ddr_sweep/<cmd>-<name>-<ts>.json
"""
import argparse, json, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rtd_i2c_bridge import Real  # noqa: E402
import i2cbus  # noqa: E402
from p037_test import rd, wr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PG = {"A": (0x8E, 0x8F), "B": (0xCE, 0xCF)}
SETTLE_S = 0.2
RD_TAPS = [0xB8, 0xBC, 0xC8, 0xCC, 0xD8, 0xDC, 0xE8, 0xEC]  # slice0/1 SET0/1 base, 4 bytes each (rise/fall DQ[3:0]..)
QUAD = lambda base: [base, base + 1, base + 2, base + 3]
APPLY_RD_DLY = (0x8F83, 0x0C)  # DPI_CTRL1_0: write_en bit3 + fw_set_rd_dly
APPLY_RD_DET = (0x8F83, 0xC0)  # write_en bit7 + fw_set_rd_det
APPLY_CAL_RANGE = (0x8F83, 0x30)  # write_en bit5 + fw_set_cal_range


class Phy:
    def __init__(self, d, lf):
        self.d, self.lf = d, lf

    def log(self, s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True)
        self.lf.write(line + "\n")
        self.lf.flush()

    def r(self, ch, page_sel, reg):  # page_sel 0 = 8E-type, 1 = 8F-type
        return rd(self.d, PG[ch][page_sel] << 8 | reg)

    def w(self, ch, page_sel, reg, v):
        return wr(self.d, PG[ch][page_sel] << 8 | reg, v)

    def clear(self, ch):
        for a in range(0x00, 0x14):
            self.w(ch, 1, a, 0)
        for a in range(0xEC, 0x100):
            self.w(ch, 1, a, 0)
        self.w(ch, 1, 0xEB, 0x30)  # INT_CTRL_0: write_en + fw_clr_dqs_int

    def measure(self, ch, settle=SETTLE_S, clear=True):
        if clear:
            self.clear(ch)
        time.sleep(settle)  # wait for flags to re-set (see module doc)
        g = lambda a: self.r(ch, 1, a)
        vw = [g(a) for a in range(0x04, 0x0C)]
        ci = [g(a) for a in range(0xF0, 0xF8)]
        cal = [g(a) for a in (0x88, 0x8A, 0x8C, 0x8E)]
        if None in vw + ci + cal:
            return {"err": "i2c"}
        return {"vw": sum(1 for x in vw if x), "calint": sum(1 for x in ci if x), "vwb": vw, "cal": cal}

    def dword(self, ch, page_sel, base):
        return [self.r(ch, page_sel, base + i) for i in range(4)]


def fmt(m):
    if "err" in m:
        return "ERR"
    return f"VW={m['vw']}/8 CALINT={m['calint']}/8 cal={','.join(f'{x:02x}' for x in m['cal'])}"


def worst(ms):
    """Worst of repeated measures: any flag in any repeat counts."""
    return {"vw": max(m.get("vw", 9) for m in ms), "calint": max(m.get("calint", 9) for m in ms),
            "cal": ms[-1].get("cal"), "vwb": ms[-1].get("vwb")}


# name -> (page_sel, regs to write the value to, range, apply, description)
def controls():
    taps_all = [(0, b + i) for b in RD_TAPS for i in range(4)]
    return {
        "rd_dly_all": (taps_all, range(0, 0x20), APPLY_RD_DLY, "read DQ delay tap, all DQ rise+fall, slice0/1 (8E B8..EF)"),
        "rd_dly_rise": ([(0, b + i) for b in (0xB8, 0xBC, 0xC8, 0xCC) for i in range(4)], range(0, 0x20), APPLY_RD_DLY, "rise taps only"),
        "rd_dly_fall": ([(0, b + i) for b in (0xD8, 0xDC, 0xE8, 0xEC) for i in range(4)], range(0, 0x20), APPLY_RD_DLY, "fall taps only"),
        "vw_sel": ([(1, 0x14), (1, 0x15), (1, 0x16), (1, 0x17)], range(0, 0x20), APPLY_RD_DET, "VALID_WIN_SEL_ODD 3..0 (8F14-17), reset 0a/33/0a/33"),
        "vw_ph": ([(1, 0x18), (1, 0x19), (1, 0x1A), (1, 0x1B)], range(0, 0x20), APPLY_RD_DET, "VALID_WIN_PH_ODD 3..0 (8F18-1B), reset 0"),
        "dqs_en": ([(0, 0x57), (0, 0x5B)], range(0x04, 0x12), None, "READ_CTRL0 SET0/1 RDQS enable latency (0.5 cycle units), SDK 0x0B"),
        "rx_fifo": ([(0, 0x67)], range(0x04, 0x12), None, "READ_CTRL1 Rx FIFO latency (cycles), SDK 0x0A"),
        "odt_en": ([(0, 0x6B), (0, 0x6F)], [0x00, 0x0F, 0x1F, 0x3F, 0x7F, 0xFC, 0xFE, 0xFF], None, "READ_CTRL2 SET0/1 ODT enable interval, SDK 0xFC"),
        "cal_mode": ([(1, 0x7F)], [0x55, 0x45, 0x65, 0x75, 0x15, 0x05, 0x25, 0x35], None, "DPI_CTRL0_0: dqsen/cal_set/rst_fifo/fw_set; 55 = SDK; x5 = cal_set_mode 3 disable at 75"),
        "rd_update_dly": ([(1, 0x7D)], [0xEF, 0xE0, 0xE4, 0xE8, 0xF0, 0xF8, 0xFF, 0x4F, 0x2F, 0x0F, 0x1F], None, "DPI_CTRL0_2: wr_update_dly[7:5] rd_update_dly[4:0], SDK EF"),
        "ref_update_dly": ([(1, 0x7E)], [0x20, 0x00, 0x08, 0x10, 0x30, 0x3F], None, "DPI_CTRL0_1 ref_update_dly, SDK 0x20"),
        "cal_shift": ([(0, 0x94), (0, 0x95), (0, 0x96), (0, 0x97)], [0x77, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x00], None, "CAL_SHIFT_CTRL lag shift, default 22/11/66/77"),
        "cal_ls": ([(0, a) for a in (0x98, 0x99, 0x9A, 0x9B)], [0x22, 0x11, 0x33, 0x44, 0x55, 0x66, 0x77], None, "CAL_LS_SEL_SET0 left sample point, 22"),
        "cal_rs": ([(0, a) for a in (0xA8, 0xA9, 0xAA, 0xAB)], [0x22, 0x11, 0x33, 0x44, 0x55, 0x66, 0x77], None, "CAL_RS_SEL_SET0 right sample point, 22"),
        "pad_dqs_odt": ([(1, 0x2D), (1, 0x2E), (1, 0x31), (1, 0x32)], [0x60, 0x50, 0x40, 0x70, 0x90, 0xA0, 0x00, 0xF0], None, "PAD_DQS01 CTRL_2/1 (TTPC/TTNC termination), see dump"),
        "pad_dq_ctrl": ([(1, 0x35), (1, 0x37)], [0x80, 0x00, 0x40, 0xC0, 0x90, 0xA0, 0x88, 0x84], None, "PAD_DQ_CTRL e2/pd/sden/pnt/ppt"),
        "pad_dq01": ([(1, 0x37)], [0x80, 0xC0, 0x40, 0x81, 0x82, 0x83, 0x84, 0x88, 0x8C, 0x90, 0xA0, 0xC1, 0xC3, 0xC4, 0xCC], None, "PAD_DQ_CTRL_0 (dq01 e2/pd/sden/pnt/ppt), SDK 80"),
        "pad_dq23": ([(1, 0x35)], [0x80, 0xC0, 0x40, 0x81, 0x82, 0x83, 0x84, 0x88, 0x8C, 0x90, 0xA0, 0xC1, 0xC3, 0xC4, 0xCC], None, "PAD_DQ_CTRL_2 (dq23), SDK 80"),
        "pad_dq_hi": ([(1, 0x34), (1, 0x36)], [0x50, 0x00, 0x40, 0x10, 0x20, 0x60, 0x80, 0xA0], None, "PAD_DQ_CTRL_3/1 TTPC/TTNC termination, SDK 50/00"),
        "pad_vref": ([(1, 0x3F)], [0x00, 0x01, 0x02, 0x03, 0x04], None, "PAD_VREF_CTRL_0 vp/vn/pd"),
    }


def cmd_state(p):
    for ch in "AB":
        p.log(f"== channel {ch}")
        for name, (regs, rng, ap, desc) in controls().items():
            vals = [p.r(ch, ps, rg) for ps, rg in regs]
            p.log(f"{name:15s} {','.join('--' if v is None else format(v, '02x') for v in vals)}  # {desc}")
        for nm, ps, base in (("DPI_CTRL0", 1, 0x7C), ("DPI_CTRL1", 1, 0x80), ("PAD_DQS01", 1, 0x2C), ("PAD_DQS23", 1, 0x30), ("PAD_DQ", 1, 0x34),
                             ("PAD_CK", 1, 0x24), ("PAD_CA", 1, 0x28), ("PAD_VREF", 1, 0x3C), ("WRLVL", 0, 0x28), ("READ_CTRL1", 0, 0x64),
                             ("VWSEL_ODD", 1, 0x14), ("VWPH_ODD", 1, 0x18), ("VWSEL_E", 0, 0xF8), ("VWPH_E", 0, 0xFC), ("DQSEN_CAL_ST", 0, 0x90)):
            p.log(f"{nm:15s} {' '.join('--' if v is None else format(v, '02x') for v in p.dword(ch, ps, base))}")
        taps = [p.r(ch, 0, b + i) for b in RD_TAPS for i in range(4)]
        p.log("rd taps 8E B8.. " + " ".join(f"{x:02x}" for x in taps))
    return 0


def cmd_base(p, n):
    for i in range(n):
        for ch in "AB":
            p.log(f"base {i} ch{ch} {fmt(p.measure(ch))}")
    return 0


def cmd_sweep(p, name, chs):
    regs, rng, ap, desc = controls()[name]
    out = {}
    for ch in chs:
        orig = [p.r(ch, ps, rg) for ps, rg in regs]
        o_cal = p.r(ch, 1, 0x7F)
        p.log(f"sweep {name} ch{ch} orig={orig} cal_mode(8F7F)={o_cal:02x} # {desc}")
        res = {}
        try:
            if name.startswith("rd_dly"):
                p.w(ch, 1, 0x7F, (o_cal & 0xCF) | 0x30)  # disable auto 3-point cal so taps stay put
            for v in rng:
                for ps, rg in regs:
                    p.w(ch, ps, rg, v)
                if ap:
                    p.w(ch, 1, ap[0] & 0xFF, ap[1])
                m = worst([p.measure(ch), p.measure(ch, clear=False)])
                res[v] = m
                p.log(f"  {name} ch{ch} v={v:02x} {fmt(m)}")
        finally:
            for (ps, rg), v in zip(regs, orig):
                if v is not None:
                    p.w(ch, ps, rg, v)
            if ap:
                p.w(ch, 1, ap[0] & 0xFF, ap[1])
            p.w(ch, 1, 0x7F, o_cal)
            p.log(f"  restored ch{ch}: {fmt(p.measure(ch))}")
        out[ch] = {format(k, "02x"): {kk: vv for kk, vv in m.items() if kk != "vwb"} for k, m in res.items()}
        passing = [format(k, "02x") for k, m in res.items() if m["vw"] == 0 and m["calint"] == 0]
        p.log(f"PASS-MAP {name} ch{ch}: clean at {passing if passing else 'none'}")
    d = ROOT / "tmp/ddr_sweep"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"sweep-{name}-{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(out, indent=1))
    return 0


def cmd_trig(p, name):
    seq = {
        "cal_range": lambda ch: p.w(ch, 1, *(APPLY_CAL_RANGE[0] & 0xFF, APPLY_CAL_RANGE[1])),
        "rd_det": lambda ch: p.w(ch, 1, *(APPLY_RD_DET[0] & 0xFF, APPLY_RD_DET[1])),
        "rd_dly": lambda ch: p.w(ch, 1, *(APPLY_RD_DLY[0] & 0xFF, APPLY_RD_DLY[1])),
        "all": lambda ch: [p.w(ch, 1, 0x83, v) for v in (0x30, 0xC0, 0x0C)],
        "cal_imm": lambda ch: (p.w(ch, 1, 0x7F, 0x65), p.w(ch, 1, 0x83, 0x30), p.w(ch, 1, 0x7F, 0x55)),
        "cal_off_on": lambda ch: (p.w(ch, 1, 0x7F, 0x75), p.w(ch, 1, 0x7F, 0x55)),
    }[name]
    for ch in "AB":
        p.log(f"trig {name} ch{ch} before {fmt(p.measure(ch))}")
        seq(ch)
        p.log(f"trig {name} ch{ch} after  {fmt(p.measure(ch))}")
        p.log(f"trig {name} ch{ch} after2 {fmt(p.measure(ch, settle=1.0))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", type=int, required=True)
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--serial", required=True)
    ap.add_argument("cmd", choices=["state", "base", "sweep", "trig"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--ch", default="AB")
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/ddr_sweep.log").open("a")
    i2cbus.require_unit(a.bus, a.serial)
    p = Phy(Real(a.bus, allow_write=True), lf)
    if a.cmd == "state":
        return cmd_state(p)
    if a.cmd == "base":
        return cmd_base(p, a.n)
    if a.cmd == "sweep":
        return cmd_sweep(p, a.name, a.ch)
    return cmd_trig(p, a.name)


if __name__ == "__main__":
    sys.exit(main())
