#!/usr/bin/env python3
"""MCU / flash clock sweep on the test unit or in the firmware sim (docs/clock-sweep.md).

usage: clk_sweep.py --bus B --serial S --map MAP [--bin BIN] [--sim] [--set NAME ...] [--hold-s S] STEP [STEP ...]
  Image built with -D _AWTO_OSD_HWTEST (fw/test/testcmd.c: g_stAwtoClk, AwtoClkApply). Per step the firmware sets the dividers
  (FFED / FFEE / FFE9) at run time, redoes Timer2, delay counts and the DDC debounce as the SDK speed-up mode does, runs its own
  checks, then holds the step while the host measures; revert from the host, at the hold limit, or by the WDT reset (586 ms stall).
  MCU = M2PLL / F / M, SPI = M2PLL / F / F2. STEP = a name from STEPS, or `all-mcu`, `all-flash`, `stock`.
  M2PLL steps: pmNN (M = NN, N 2, O 1; F 1, M-divider 1, F2 = smallest keeping the SPI <= 70.2 MHz), pmNNL = + 200 CRC passes, aliases p372 p401 p430 p487.
  The firmware moves the M2PLL (MCU / flash on the crystal meanwhile), retunes every derived divider to the nearest integer and reverts at the hold limit.
  --max-m2pll-mhz N (default 490): steps above are refused by the tool and the firmware; raising it is an explicit, logged decision.
  --keep NAMES leaves derived dividers at stock (bisect), --override NAME=VAL sets one, --retry repeats a failed step once, --stop-after N stops after N consecutive reproducible failures.
  Pass / fail per check, one line per check; log ./tmp/logs/clk_sweep.log, TSV ./tmp/logs/clk_sweep.tsv.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_hw_test as H  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/clk_sweep.log"
TSV = ROOT / "tmp/logs/clk_sweep.tsv"

# StAwtoClk (fw/test/testcmd.c), big endian
(C_GO, C_SEQ, C_STATE, C_F, C_F2, C_M, C_CKCON, C_FLAGS, C_HOLD, C_RCAP, C_D5, C_DX, C_D5P, C_DXP, C_TICK, C_CRC, C_CRCBAD, _R0,
 C_XDBAD, C_ALU, C_MISS, C_CRCMS, C_FFED, C_FFE9, C_FFEE, C_FF6C, C_FDA1, C_CKNOW, C_FORM, C_REFUSE, C_PLL, C_DEB, C_REF, C_MISSN,
 C_RST, C_NOW) = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 16, 18, 20, 24, 25, 26, 28, 30, 32, 34, 35, 36, 37, 38, 39, 40, 41, 42, 46, 48, 52, 56, 60)
C_DRIVE, C_SLEW, C_CHIP, C_DRNOW, C_SLNOW = 62, 63, 64, 65, 66
C_AST = 67
C_TUNE, C_PASSES = 69, 70
C_SC = 71
C_SIZE = 73
(C_PLLM, C_PLLN, C_PLLO, C_MAXMHZ, C_KEEP, C_OVIDX, C_OVVAL, C_WDOS, C_WDON, C_MOVED, C_PTMO, C_E0, C_E1, C_E7, C_DIVOLD, C_DIVNEW, C_PWMOLD, C_PWMNEW) = \
    (73, 74, 75, 76, 78, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 100, 111, 123)
C_SIZE2 = 135
N_DIV, N_PWM = 11, 6
DIV_NAMES = ["m22", "sync", "meas", "gdi", "aphy0", "aphy1", "amac0", "amac1", "cbus0", "cbus1", "adc", "pwm"]      # bit k of --keep; pwm = bit 11 (all PWM dividers)
DIV_REGS = ["0x0022[6:3]", "0x4006[3:0]", "0x4007[3:0]", "0x8006[3:0]", "0xB773", "0xBA73", "0xB7B0", "0xBAB0", "0x2AA1[7:5]", "0x68A1[7:5]", "0xFF0D[6:0]"]
SYNC_CAP_MHZ = 33.0                       # regdb 0x4006 sync_clk_div_m2pll: "The clock should be less than 33M after this divider" (no cap stated for 0x4007 / 0x8006)
XTAL_KHZ = 14318
MAX_M2PLL_DEF_MHZ = 490                   # unattended default of --max-m2pll-mhz: a tool guard, not a chip limit
SPI_TARGET_MHZ = 70.2
OP_APPLY, OP_REVERT = 1, 2
ST_HELD, ST_REVERTED, ST_REFUSED, ST_AUTO = 1, 2, 3, 4
REFUSE = {0: "none", 1: "divider range", 2: "step already held", 3: "SPI above rating", 4: "no safe write order", 5: "MCU slower than SPI",
          6: "M2PLL above --max-m2pll-mhz", 7: "M / N / O out of range", 8: "M2PLL did not lock (watchdog flag / bounded wait): stock M2PLL put back"}
FL_DUAL, FL_CKCON, FL_NOWRAP, FL_PLL = 1, 2, 4, 8

STOCK_MHZ = 87.75
RATED_FAST_MHZ, RATED_DUAL_MHZ, RATED_READ_MHZ = 86.0, 80.0, 33.0       # MX25L8006E Table 13: fSCLK (0x0B), fTSCLK (0x3B), fRSCLK (0x03)
FFED_STOCK = 4

# name: (F, F2, M, flags). MCU = pll / (F x M), SPI = pll / (F x F2); M <= F2 (MCU not slower than the SPI), F x F2 >= 5 (SPI <= 86 MHz)
STEPS = {
    "stock":    (4, 2, 1, 0),      # 87.75 / 43.9
    "m44":      (8, 1, 1, 0),      # 43.9 / 43.9
    "m58":      (6, 2, 1, 0),      # 58.5 / 29.3
    "m70":      (5, 2, 1, 0),      # 70.2 / 35.1
    "m117":     (3, 3, 1, 0),      # 117 / 39.0
    "m175":     (2, 4, 1, 0),      # 175.5 / 43.9 = SDK speed-up mode
    "m351":     (1, 5, 1, 0),
    "m351S":    (1, 5, 1, 0),      # + 40 CRC passes
    "m351L":    (1, 5, 1, 0),      # + 200 CRC passes (~16 s of flash reads)
    "f175_70L": (1, 5, 2, 0),      # 350.8 / 70.2: the only divider step above 175 (no SDK evidence; tests the limit)
    "s22":      (4, 4, 1, 0),      # 87.75 / 21.9
    "s29":      (4, 3, 1, 0),      # 87.75 / 29.3
    "s58":      (2, 3, 2, 0),      # 87.75 / 58.5
    "s70":      (1, 5, 4, 0),      # 87.75 / 70.2
    "s44d":     (4, 2, 1, FL_DUAL),
    "s58d":     (2, 3, 2, FL_DUAL),
    "s70d":     (1, 5, 4, FL_DUAL),
    "f175_58":  (2, 3, 1, 0),      # 175.5 / 58.5
    "f175_70":  (1, 5, 2, 0),      # 175.5 / 70.2
    "f175_44d": (2, 4, 1, FL_DUAL),
    "f175_58d": (2, 3, 1, FL_DUAL),
    "f175_70d": (1, 5, 2, FL_DUAL),
    "f175_44dn": (2, 4, 1, FL_DUAL | FL_NOWRAP),   # dual read, FF6C written with the default MOVX cycle
    "s44dn":   (4, 2, 1, FL_DUAL | FL_NOWRAP),
    "m175S":   (2, 4, 1, 0),                    # 40 CRC passes (flash-read stress)
    "f175_58S": (2, 3, 1, 0),
    "f175_70S": (1, 5, 2, 0),
    "s70S":    (1, 5, 4, 0),
    "s44S":    (4, 2, 1, 0),                    # stock clocks, 40 CRC passes: the stress baseline
    "s44dS":   (4, 2, 1, FL_DUAL),              # dual read, 40 passes
    "s44d_l1": (4, 2, 1, FL_DUAL),              # + latch SO on the other edge
    "s44d_d1": (4, 2, 1, FL_DUAL),              # + si_dly 2 ns / 4 / 6
    "s44d_d2": (4, 2, 1, FL_DUAL),
    "s44d_d3": (4, 2, 1, FL_DUAL),
    "s44d_f1": (4, 2, 1, FL_DUAL),
    "s44_l1":  (4, 2, 1, 0),                    # single read, latch on the other edge
    "s58p":    (2, 3, 2, 0),      # pad drive 5.5 mA (PADS)
    "s70p":    (1, 5, 4, 0),
    "s70dp":   (1, 5, 4, FL_DUAL),
    "f175_58p": (2, 3, 1, 0),
    "f175_70p": (1, 5, 2, 0),
    "f175_70dp": (1, 5, 2, FL_DUAL),
}
PADS = {"s58p": (7, 0xFF), "s70p": (7, 0xFF), "s70dp": (7, 0xFF), "f175_58p": (7, 0xFF), "f175_70p": (7, 0xFF), "f175_70dp": (7, 0xFF)}   # (drive 0..7 = 2 + 0.5 x n mA, slew 0/1); 0xFF = keep
KEEP = 0xFF
# FF6C[5:2] = latch_so_rise (bit 5), drive_si_fall (4), si_dly_sel (3:2) while the step is held; PASSES = CRC passes (stress; 0 = 3)
TUNE = {"s44d_l1": 0x20, "s44d_d1": 0x04, "s44d_d2": 0x08, "s44d_d3": 0x0C, "s44d_f1": 0x10, "s44_l1": 0x20}
PASSES = {"m351S": 40, "m351L": 200, "f175_70L": 200, "m175S": 40, "f175_58S": 40, "f175_70S": 40, "s70S": 40, "s44dS": 40, "s44d_l1": 40, "s44d_d1": 40, "s44d_d2": 40, "s44d_d3": 40, "s44d_f1": 40, "s44S": 40, "s44_l1": 40}
PLL = {}                                  # name -> (M, N, O)


def pll_khz(m: int, n: int = 2, o: int = 1) -> float:
    return XTAL_KHZ * m / (n * o)


def _pll_steps() -> None:
    for m in range(40, 131):
        k = pll_khz(m)
        f2 = -(-int(k) // int(SPI_TARGET_MHZ * 1000))       # ceil: SPI = M2PLL / F2 <= 70.2 MHz
        for suffix, passes in (("", 0), ("L", 200)):
            nm = f"pm{m}{suffix}"
            STEPS[nm] = (1, f2, 1, FL_PLL)
            PLL[nm] = (m, 2, 1)
            if passes:
                PASSES[nm] = passes
    for alias, m in (("p372", 52), ("p401", 56), ("p430", 60), ("p487", 68)):
        STEPS[alias] = STEPS[f"pm{m}"]
        PLL[alias] = PLL[f"pm{m}"]


GROUPS = {"all-mcu": ["stock", "m44", "m58", "m70", "m117", "m175"],
          "all-flash": ["stock", "s22", "s29", "s58", "s70", "s44d", "s58d", "s70d"],
          "all-175": ["m175", "f175_58", "f175_70", "f175_44d", "f175_58d", "f175_70d"],
          "all-pad": ["s58p", "s70p", "s70dp", "f175_58p", "f175_70p", "f175_70dp"]}

_pll_steps()
GROUPS["all-pll"] = ["p372", "p401", "p430", "p487"]
GROUPS["pll-fine"] = [f"pm{m}" for m in range(52, 81, 2)]          # +14.3 MHz per step

CRC_FROM, CRC_TO = 0x0100, 0x4000
TICK_REL_PM = 5                           # per mille of the stock step's value; window 100 ticks, resolution 1 clock in 1.4 M
DELAY_PCT_MIN, DELAY_PCT_MAX = 97, 150    # unit_health.py delay-cal limits
RT_READS = 300                            # debug-link block reads per step (24 B each, the ISR + main loop at the step clock)
WALL_S = 2.0                              # heartbeat vs host clock window
WALL_TOL_PCT = 1.5                        # usNowMs is refreshed once per main pass (~3 ms): 2 s window, +- 0.2 % plus I2C jitter
FPS_SETTLE_S = 2.5                        # Scope 2 first frame hidden (docs/saver-fps-hw.md baseline)
FPS_WINDOW_S = 6.0
APPLY_LIMIT_S = 3.0                       # apply op at stock ~1.2 s (calibrated by the first stock run, --cal); x (stock MCU / step MCU)
HOLD_S = 25.0                             # fw-side revert: apply + host checks (~10 s) x 2.5; the WDT reset is the backstop
SAVER_SCOPE2, SAVER_AST, SAVER_OFF = H.SAVER_SCOPE2, H.SAVER_AST, H.SAVER_OFF
SAVER_SCOPE1 = 3
SCOPE1_FRAME_ARGS = (0x76, 0x77)
SCOPE1_WINDOW_S = 6.0
SYNC_EV_ODEMO = 0xE9


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


class Ctx:
    def __init__(self, dev, ck, rdabs, sync_addr, expect_crc):
        self.dev, self.ck, self.rdabs, self.sync_addr, self.expect_crc = dev, ck, rdabs, sync_addr, expect_crc
        self.stock_crc = None
        self.stock_tick = None
        self.sim = False
        self.pll_khz = None
        self.base = None                      # registers before the first step: what a revert must restore
        self.stock_pll = None
        self.stock_e = None
        self.max_mhz = MAX_M2PLL_DEF_MHZ
        self.keep = 0
        self.override = (0xFF, 0)


def be(raw: bytes, o: int, n: int) -> int:
    return int.from_bytes(raw[o:o + n], "big")


def wait(dev, s: float) -> None:
    t0 = dev.now()
    while dev.now() - t0 < s:
        dev.idle()


POLL_PACE_S = 0.05                        # between polls of a long fw op: back-to-back I2C polls load the DDC ISRs (unit 3, m44: WDT bite in ScalerSyncDdcDetect_EXINT1)


def pace(ck) -> None:
    if isinstance(ck, H.Unit):
        t0 = time.monotonic()
        while time.monotonic() - t0 < POLL_PACE_S:
            pass
    else:
        ck.idle()


def crd(ck, tries: int = 40) -> bytes:
    return ck.rd(0, C_SIZE)


def mcu_mhz(pll_khz: float, f: int, m: int) -> float:
    return pll_khz / 1000.0 / (f * m)


def spi_mhz(pll_khz: float, f: int, f2: int) -> float:
    return pll_khz / 1000.0 / (f * f2)


def send(ctx, go: int, limit_s: float, f=0, f2=0, m=0, flags=0, hold_s=HOLD_S, label="", pad=(0xFF, 0xFF), name_="") -> bytes | None:
    """Write the request, go; poll until the firmware clears go (the main loop serves it; reads fail while it is busy)."""
    ck = ctx.ck
    if go == OP_APPLY:
        ck.wr(C_F, bytes([f, f2, m, 0, flags]))
        ck.wr(C_DRIVE, bytes(pad))
        ck.wr(C_TUNE, bytes([TUNE.get(name_, 0xFF), PASSES.get(name_, 0)]))
        ck.wr(C_HOLD, int(hold_s * 1000).to_bytes(2, "big"))
        pm, pn, po = PLL.get(name_, (0, 0, 0))
        ck.wr(C_PLLM, bytes([pm, pn, po]) + ctx.max_mhz.to_bytes(2, "big") + ctx.keep.to_bytes(2, "big") + bytes(ctx.override))
    seq0 = ck.rd(C_SEQ, 1)[0]
    ck.wr(C_GO, bytes([go]))
    t0 = ck.now()
    while True:
        pace(ck)
        try:
            h = ck.rd(C_GO, 2)
        except RuntimeError:
            h = None
        if h is not None and h[0] == 0 and h[1] != seq0:
            return crd(ck)
        if ck.now() - t0 > limit_s:
            say(f"  FAIL {label}: no answer after {ck.now() - t0:.2f} s (limit {limit_s:.2f} s)")
            return None


def fps_scope2(ctx) -> tuple[float, int]:
    dev = ctx.dev
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_SCOPE2, label="scope2 on")
    H.wait_scope2(dev)
    wait(dev, FPS_SETTLE_S)
    r0 = H.op(dev, H.OP_REGS, H.lim_read(0), label="frame0")
    t0 = dev.now()
    wait(dev, FPS_WINDOW_S)
    r1 = H.op(dev, H.OP_REGS, H.lim_read(0), label="frame1")
    t1 = dev.now()
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
    n = (r1["frame"] - r0["frame"]) & 0xFFFF
    return n / (t1 - t0), n


def fps_ast(ctx) -> tuple[float, int]:
    """Asteroids frames drawn: the fw counts the wraps of the column counter (its sync line is a game tick, not a frame)."""
    dev, ck = ctx.dev, ctx.ck
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_AST, label="asteroids on")
    wait(dev, FPS_SETTLE_S)
    a0, t0 = be(ck.rd(C_AST, 2), 0, 2), ck.now()
    wait(dev, FPS_WINDOW_S)
    a1, t1 = be(ck.rd(C_AST, 2), 0, 2), ck.now()
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
    n = (a1 - a0) & 0xFFFF
    return n / (t1 - t0), n


def fps_scope1(ctx) -> tuple[float, int]:
    """Scope 1 frames drawn: the fw counts them (g_usAwtoScFrames, HWTEST build)."""
    dev, ck = ctx.dev, ctx.ck
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_SCOPE1, label="scope1 on")
    wait(dev, FPS_SETTLE_S)
    a0, t0 = be(ck.rd(C_SC, 2), 0, 2), ck.now()
    wait(dev, FPS_WINDOW_S)
    a1, t1 = be(ck.rd(C_SC, 2), 0, 2), ck.now()
    H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
    n = (a1 - a0) & 0xFFFF
    return n / (t1 - t0), n


def pll_checks(ctx, name: str, t: bytes, pll: int, chk) -> None:
    """M2PLL step: register read-back, lock flag, derived-clock table (stock div -> new div, MHz vs stock)."""
    m, n, o = PLL[name]
    e0, e1, e7 = t[C_E0 - C_PLLM], t[C_E1 - C_PLLM], t[C_E7 - C_PLLM]
    want = ((m - 2) & 0xFF, (ctx.stock_e[1] & 0xC0 if ctx.stock_e else 0) | {1: 0, 2: 1, 4: 2, 8: 3}[o] << 4 | (n - 2), (ctx.stock_e[2] & 0xC0) if ctx.stock_e else 0)
    chk("pll", (e0, e1, e7) == want and not t[C_PTMO - C_PLLM] and not (t[C_WDON - C_PLLM] and not t[C_WDOS - C_PLLM]),
        f"M {m} N {n} O {o} -> {pll / 1000:.2f} MHz; 0x01E0/E1/E7 = {e0:02X}/{e1:02X}/{e7:02X} want {want[0]:02X}/{want[1]:02X}/{want[2]:02X}; WD flag stock {t[C_WDOS - C_PLLM]} now {t[C_WDON - C_PLLM]}; bounded wait expired {t[C_PTMO - C_PLLM]}")
    spll = ctx.stock_pll or 350791
    old, new = t[C_DIVOLD - C_PLLM:C_DIVOLD - C_PLLM + N_DIV], t[C_DIVNEW - C_PLLM:C_DIVNEW - C_PLLM + N_DIV]
    say(f"  derived clocks (stock M2PLL {spll / 1000:.1f} MHz -> {pll / 1000:.1f} MHz): register, stock div, new div, MHz stock -> new, error")
    for k in range(N_DIV):
        if old[k] == 0:
            say(f"    {DIV_NAMES[k]:6s} {DIV_REGS[k]:12s} not on the M2PLL / no clock: left alone")
            continue
        a, b = spll / 1000 / old[k], pll / 1000 / new[k]
        say(f"    {DIV_NAMES[k]:6s} {DIV_REGS[k]:12s} {old[k]:3d} -> {new[k]:3d}   {a:7.2f} -> {b:7.2f} MHz  {100 * (b / a - 1):+5.1f} %{'  (kept at stock)' if (ctx.keep >> k) & 1 else ''}")
    for k in range(N_PWM):
        a, b = be(t, C_PWMOLD - C_PLLM + 2 * k, 2), be(t, C_PWMNEW - C_PLLM + 2 * k, 2)
        if a:
            say(f"    pwm{k}   N+1 {a} -> {b}   frequency {100 * ((pll / b) / (spll / a) - 1):+5.1f} %")
    if old[1]:
        c = pll / 1000 / new[1]
        say(f"  {'!!!! sync processor clock OVER the regdb 0x4006 cap' if c > SYNC_CAP_MHZ else 'info sync processor clock under the regdb 0x4006 cap'}: {c:.2f} MHz vs {SYNC_CAP_MHZ} MHz (divider 4 bit, max 15: above {SYNC_CAP_MHZ * 15:.0f} MHz M2PLL the cap cannot be kept; a documented 'should', not a check)")


def run_step(ctx, name: str, ck_checks: bool = True) -> dict | None:
    f, f2, m, fl = STEPS[name]
    dev, ck = ctx.dev, ctx.ck
    res = {"step": name, "F": f, "F2": f2, "M": m, "dual": int(bool(fl & FL_DUAL))}
    pllk = pll_khz(*PLL[name]) if name in PLL else 350.8e3
    pll_step = name in PLL
    if pll_step and pllk > ctx.max_mhz * 1000:
        say(f"== {name}: M2PLL {pllk / 1000:.1f} MHz is above --max-m2pll-mhz {ctx.max_mhz}: NOT RUN (tool guard; raise the flag to go beyond)")
        res["fail"] = "refused by tool: above --max-m2pll-mhz"
        return res
    if pll_step and pllk > MAX_M2PLL_DEF_MHZ * 1000:
        say(f"!!!! {name}: M2PLL {pllk / 1000:.1f} MHz is OUTSIDE the default envelope ({MAX_M2PLL_DEF_MHZ} MHz): explicit --max-m2pll-mhz {ctx.max_mhz}")
    scale = max(1.0, STOCK_MHZ / (pllk / 1000 / (f * m)), 43.85 / (pllk / 1000 / (f * f2)))     # op times follow the MCU clock and the SPI clock (stock 43.85)
    r = send(ctx, OP_APPLY, (APPLY_LIMIT_S + PASSES.get(name, 0) * 0.45) * scale, f, f2, m, fl, label=f"apply {name}", pad=PADS.get(name, (KEEP, KEEP)), name_=name, hold_s=min(65.0, HOLD_S + PASSES.get(name, 0) * 0.4 * scale))
    if r is None:
        res["fail"] = "no answer to apply (hung or reset)"
        return res
    st, refuse = r[C_STATE], r[C_REFUSE]
    pll = be(r, C_PLL, 4)
    ctx.pll_khz = pll
    mhz, shz = mcu_mhz(pll, f, m), spi_mhz(pll, f, f2)
    res.update(mcu=mhz, spi=shz, pll_mhz=pll / 1000)
    if name == "stock" and ctx.stock_pll is None:
        ctx.stock_pll = pll
        ctx.stock_e = tuple(ck.rd(C_E0, 1) + ck.rd(C_E1, 1) + ck.rd(C_E7, 1))
    say(f"== {name}: F {f} F2 {f2} M {m}{' dual-read' if fl & FL_DUAL else ''} -> MCU {mhz:.2f} MHz, SPI {shz:.2f} MHz (M2PLL {pll} kHz)")
    if st != ST_HELD:
        say(f"  REFUSED by the firmware: {REFUSE.get(refuse, refuse)}")
        res["fail"] = "refused: " + REFUSE.get(refuse, str(refuse))
        return res
    checks = []

    def chk(label, ok, detail, sim_info=False):
        if sim_info and ctx.sim:                     # the sim's host clock / OSD read-back are not the unit's: report only
            say(f"  info {label} (sim, not a check): {detail}")
            return
        checks.append((label, bool(ok)))
        say(f"  {'PASS' if ok else 'FAIL'} {label}: {detail}")
        res[label] = bool(ok)

    crc = r[C_CRC:C_CRC + 4].hex()
    if name == "stock" and ctx.stock_crc is None:
        ctx.stock_crc = crc
    want = ctx.expect_crc
    if pll_step:
        t = ck.rd(C_PLLM, C_SIZE2 - C_PLLM)
        pll_checks(ctx, name, t, pll, chk)
    chk("regs", (r[C_FFED] >> 2) & 15 == f and r[C_FFE9] & 15 == f2 and (r[C_FFEE] >> 2) & 15 == m,
        f"FFED {r[C_FFED]:02X} FFE9 {r[C_FFE9]:02X} FFEE {r[C_FFEE]:02X} FF6C {r[C_FF6C]:02X} FDA1 {r[C_FDA1]:02X} CKCON {r[C_CKNOW]:02X}; chip ID 0x{r[C_CHIP]:02X}; FFEE[6] mcu_peri_non_stop {(r[C_FFEE] >> 6) & 1}; pad drive P10_C2 {r[C_DRNOW]:02X} slew P10_81 {r[C_SLNOW]:02X}")
    chk("formula", r[C_FORM] == 1, f"stock Timer2 reload equals the reload formula; RCAP2 now 0x{be(r, C_RCAP, 2):04X}")
    chk("crc32", crc == ctx.stock_crc and r[C_CRCBAD] == 0,
        f"code 0x{CRC_FROM:04X}..0x{CRC_TO:04X} via MOVC 3 passes: {crc} want {ctx.stock_crc} (stock step), file {want}, passes differing {r[C_CRCBAD]}, {be(r, C_CRCMS, 2)} ms/pass")
    chk("xdata", be(r, C_XDBAD, 2) == 0, f"4 patterns x 8 rounds, {be(r, C_XDBAD, 2)} bad bytes")
    tick = be(r, C_TICK, 2)
    if name == "stock" and ctx.stock_tick is None:
        ctx.stock_tick = tick                       # the WDT counter is not the crystal 1:1 (unit 3 stock: 1.082): the reference is the stock step, the host clock is the heartbeat check
    st0 = ctx.stock_tick or tick
    say(f"  info tick: Timer2 ms per WDT-counter ms x 1000 = {tick} (stock step {st0}); the WDT counter is no fixed reference (unit 3: 1000 / 1082 / 1068 in three runs), the heartbeat check below is against the host clock")
    d5, dx = be(r, C_D5P, 2), be(r, C_DXP, 2)
    chk("delay", DELAY_PCT_MIN <= d5 <= DELAY_PCT_MAX and DELAY_PCT_MIN <= dx <= DELAY_PCT_MAX,
        f"counts {r[C_D5]}/{r[C_DX]}: DELAY_5US {d5} %, DELAY_XUS(100) {dx} % of nominal (limit {DELAY_PCT_MIN}..{DELAY_PCT_MAX})")
    alu, miss = be(r, C_ALU, 2), be(r, C_MISS, 2)
    ref, mis, rst = be(r, C_REF, 4), be(r, C_MISSN, 4), be(r, C_RST, 4)
    say(f"  info cpu loop {alu} ms (196608 it) = {196608 / max(alu, 1):.0f} kit/s; cache-miss reads {miss} ms for 16384 = {miss * 1000 / 16.384:.0f} ns each; "
        f"cache meter over the CRC pass: {ref} reads, {mis} misses ({100 * mis / max(ref, 1):.1f} %), {rst} memory restarts; DDC debounce {be(r, C_DEB, 2)}")
    res.update(alu_ms=alu, miss_ms=miss, ref=ref, misses=mis, crc_ms=be(r, C_CRCMS, 2))
    # host side, at the step clock
    n_bad, ref_blk = 0, None
    t0 = ck.now()
    for _ in range(RT_READS):
        try:
            b = ck.rd(C_CRC, 24)
        except RuntimeError:
            n_bad += 1
            continue
        ref_blk = ref_blk or b
        n_bad += b != ref_blk
    chk("link", n_bad == 0, f"{RT_READS} block reads of 24 B in {ck.now() - t0:.2f} s, {n_bad} failed / differing")
    a0, t0 = be(ck.rd(C_NOW, 2), 0, 2), ck.now()
    wait(ck, WALL_S)
    a1, t1 = be(ck.rd(C_NOW, 2), 0, 2), ck.now()
    ratio = ((a1 - a0) & 0xFFFF) / 1000.0 / (t1 - t0)
    chk("heartbeat", abs(ratio - 1) * 100 <= WALL_TOL_PCT, f"fw ms {((a1 - a0) & 0xFFFF)} per host {1000 * (t1 - t0):.0f} ms = {ratio:.4f} (limit +-{WALL_TOL_PCT} %)", sim_info=True)
    try:
        H.set_flags(dev, 0)
        H.op(dev, H.OP_SAVER, H.lim_saver(), flags=0, n=SAVER_OFF, label="saver off")
        bad = 0
        for nm, mode in (("s2map", H.M_TRIPLE), ("s2map", H.M_SDK)):
            w = H.op(dev, H.OP_WRITE, H.lim_write(mode, 616 * 3) * scale, mode=mode, flags=H.F_REPEAT, seed=0x3C, addr=0, n=616 * 3, label="osd write")
            for fl in (0, H.F_M2):
                v = H.op(dev, H.OP_VERIFY, H.lim_read(616 * 3) * scale, flags=H.F_REPEAT | fl, seed=0x3C, addr=0, n=616 * 3, label="osd verify")
                bad += v["bad"]
            say(f"    osd write {H.MODE_NAMES[mode]}: {w['ms']} ms for 1848 B = {w['ms'] * 1000 / 1848:.2f} us/B")
        chk("osd-port", bad == 0, f"616 words written (direct triples, ScalerOsdDataPort) and read back M1 + M2: {bad} bad bytes", sim_info=True)
    except (TimeoutError, RuntimeError) as e:
        chk("osd-port", False, str(e))
    try:
        fps2, n2 = fps_scope2(ctx)
        say(f"  info Scope 2: {n2} frames in {FPS_WINDOW_S:.0f} s = {fps2:.2f} frames/s ({1000 / max(fps2, 1e-9):.0f} ms/frame)")
        res["scope2_fps"] = fps2
        fpsa, na = fps_ast(ctx)
        say(f"  info Asteroids: {na} frames in {FPS_WINDOW_S:.0f} s = {fpsa:.2f} frames/s ({1000 / max(fpsa, 1e-9):.0f} ms/frame)")
        res["ast_fps"] = fpsa
        fps1, n1 = fps_scope1(ctx)
        say(f"  info Scope 1: {n1} frames in {FPS_WINDOW_S:.0f} s = {fps1:.2f} frames/s ({1000 / max(fps1, 1e-9):.0f} ms/frame)")
        res["scope1_fps"] = fps1
    except (TimeoutError, RuntimeError) as e:
        chk("saver", False, str(e))
    r = send(ctx, OP_REVERT, 2.0, label=f"revert {name}")
    if r is None or r[C_STATE] not in (ST_REVERTED, ST_AUTO):
        chk("revert", False, "no answer / not reverted")
    else:
        b = ctx.base or {}
        stock_ok = (r[C_FFED], r[C_FFE9] & 15, r[C_FFEE]) == (b.get("ffed", r[C_FFED]), b.get("ffe9", r[C_FFE9] & 15), b.get("ffee", r[C_FFEE]))
        e = ck.rd(C_E0, 3)
        stock_ok = stock_ok and (e[0], e[1], e[2]) == (b.get("e0", e[0]), b.get("e1", e[1]), b.get("e7", e[2])) and be(r, C_RCAP, 2) == b.get("rcap", be(r, C_RCAP, 2))
        chk("revert", stock_ok, f"FFED {r[C_FFED]:02X} FFE9 {r[C_FFE9]:02X} FFEE {r[C_FFEE]:02X} FF6C {r[C_FF6C]:02X} M2PLL E0/E1/E7 {e[0]:02X}/{e[1]:02X}/{e[2]:02X} RCAP2 0x{be(r, C_RCAP, 2):04X} state {r[C_STATE]}; "
                       f"baseline {', '.join(f'{k} {v:X}' for k, v in b.items())}")
    res["pass"] = all(ok for _, ok in checks)
    say(f"  {'STEP PASS' if res['pass'] else 'STEP FAIL'} {name}")
    return res


def tsv(row: dict) -> None:
    keys = ["step", "pll_mhz", "mcu", "spi", "dual", "pass", "crc_ms", "alu_ms", "miss_ms", "ref", "misses", "scope2_fps", "ast_fps", "scope1_fps", "fail"]
    TSV.parent.mkdir(parents=True, exist_ok=True)
    new = not TSV.exists()
    with TSV.open("a") as f:
        if new:
            f.write("\t".join(["time"] + keys) + "\n")
        f.write("\t".join([isostamp.now()] + [("%.4g" % row[k]) if isinstance(row.get(k), float) else str(row.get(k, "")) for k in keys]) + "\n")


def make_sim(binp: Path, map_path: Path):
    import osd_render as R
    import ddc_sim as D
    eng = D.DdcEngine()
    sess = R.Session(binp, map_path, "2160p60", devs=[eng])
    sess.boot()
    m = sess.bus.m
    dev = H.Sim.__new__(H.Sim)
    dev.eng, dev.sess, dev.m = eng, sess, m
    dev.base = m.addr("g_stAwtoOsdHw")
    ck = copy.copy(dev)
    ck.base = m.addr("g_stAwtoClk")
    return dev, ck, (lambda a, n: bytes(m.rd(a, n))), m.addr("g_stAwtoSync")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--serial")
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--continue-on-fail", action="store_true", help="go on to the next step after a failed one (default: stop, the rest is slower-to-faster)")
    ap.add_argument("--max-m2pll-mhz", type=int, default=MAX_M2PLL_DEF_MHZ, help="M2PLL ceiling of this run (default 490: unattended); a step above is refused; a higher value is an explicit decision")
    ap.add_argument("--keep", default="", help="comma list of derived dividers left at stock: " + ",".join(DIV_NAMES))
    ap.add_argument("--override", default="", help="NAME=VAL: set one derived divider field to VAL instead of the nearest integer")
    ap.add_argument("--retry", action="store_true", help="repeat a failed step once with the same settings; only a repeated failure counts")
    ap.add_argument("--stop-after", type=int, default=1, help="stop after N consecutive reproducible failed steps (default 1)")
    ap.add_argument("steps", nargs="+")
    a = ap.parse_args()
    keep = 0
    for nm in [x for x in a.keep.split(",") if x]:
        if nm not in DIV_NAMES:
            raise SystemExit(f"--keep: unknown divider {nm}; known {DIV_NAMES}")
        keep |= 1 << DIV_NAMES.index(nm)
    ov = (0xFF, 0)
    if a.override:
        nm, _, v = a.override.partition("=")
        if nm not in DIV_NAMES[:N_DIV] or not v.isdigit():
            raise SystemExit(f"--override: NAME=VAL with NAME in {DIV_NAMES[:N_DIV]}")
        ov = (DIV_NAMES.index(nm), int(v))
    a.ctx_opts = (a.max_m2pll_mhz, keep, ov)
    names = []
    for s in a.steps:
        names += GROUPS.get(s, [s])
    names = ["stock"] + [n for n in names if n != "stock"]       # the stock step is the CRC reference of the session
    bad = [s for s in names if s not in STEPS]
    if bad:
        raise SystemExit(f"unknown step {bad}; known {sorted(STEPS)} {sorted(GROUPS)}")
    binp = a.bin or a.map.with_suffix(".bin")
    img = binp.read_bytes() if binp.exists() else b""
    want = f"{zlib.crc32(img[CRC_FROM:CRC_TO]):08x}" if img else None
    import sync_log as S
    fails = 0
    if a.sim:
        dev, ck, rdabs, sync_addr = make_sim(binp, a.map)
        ctx = Ctx(dev, ck, rdabs, sync_addr, want)
        ctx.sim = True
        ctx.max_mhz, ctx.keep, ctx.override = a.ctx_opts
        run(ctx, names, a)
        return 0
    import dbg_link
    import i2cbus
    import dbg_xdata
    i2cbus.require_unit(a.bus, a.serial)
    with dbg_link.linked(a.bus, 10):
        dev = H.Unit(a.bus, a.map)
        ck = copy.copy(dev)
        ck.base = S.sym(a.map, "g_stAwtoClk")
        sync_addr = S.sym(a.map, "g_stAwtoSync")

        def rdabs(addr, n):
            for _ in range(dev.RD_TRIES):
                r = dbg_xdata.read_blocks(dev.io, addr, n)
                if r is not None:
                    return r
            return None
        ctx = Ctx(dev, ck, rdabs, sync_addr, want)
        ctx.max_mhz, ctx.keep, ctx.override = a.ctx_opts
        ctx.relink = lambda: relink(a.bus)
        try:
            fails = run(ctx, names, a)
        finally:
            try:
                send(ctx, OP_REVERT, 2.0, label="final revert")
            except Exception as e:  # noqa: BLE001
                say(f"final revert: {e}")
            dev.close()
    return 1 if fails else 0


RELINK_S = 5.0                            # unit back after a reset: EDID in ~2 s (docs / memory monitor-wait-5s); expiry = abort the sweep


def relink(bus: int) -> bool:
    """After a fw reset the debug slave is off (the link window ends with the reset): switch it on again, up to RELINK_S."""
    import dbg_link
    t0 = time.monotonic()
    while time.monotonic() - t0 < RELINK_S:
        try:
            dbg_link.on(bus, 10)
            if dbg_link.dbg_ok(bus):
                say(f"  relinked after {time.monotonic() - t0:.1f} s (fw had reset: step failed, unit back on the stock clock)")
                return True
        except (Exception, SystemExit):  # noqa: BLE001  dbg_link.on exits when neither slave answers (unit still booting)
            pass
    say(f"  RELINK FAIL: no debug slave after {RELINK_S:.0f} s")
    return False


def one_step(ctx, n: str) -> dict:
    say(f"##### step {n}")
    try:
        row = run_step(ctx, n)
    except (TimeoutError, RuntimeError) as e:
        row = {"step": n, "pass": False, "fail": f"comm: {e}"}
        say(f"  FAIL comm lost at step {n}: {e}")
    tsv(row)
    return row


def baseline(ctx) -> None:
    """Registers before any step (the build's own clock): what every revert must restore. A revert with nothing saved only reads them."""
    r = send(ctx, OP_REVERT, 2.0, label="baseline")
    if r is None:
        raise SystemExit("no answer to the baseline read: nothing done")
    e = ctx.ck.rd(C_E0, 3)
    ctx.base = {"ffed": r[C_FFED], "ffe9": r[C_FFE9] & 15, "ffee": r[C_FFEE], "e0": e[0], "e1": e[1], "e7": e[2], "rcap": be(r, C_RCAP, 2)}
    say(f"baseline: FFED {r[C_FFED]:02X} FFE9 {r[C_FFE9]:02X} FFEE {r[C_FFEE]:02X} M2PLL E0/E1/E7 {e[0]:02X}/{e[1]:02X}/{e[2]:02X} RCAP2 0x{be(r, C_RCAP, 2):04X}")


def run(ctx, names, a) -> int:
    fails = consec = 0
    stop_after = max(1, a.stop_after)
    baseline(ctx)
    for n in names:
        row = one_step(ctx, n)
        if not row.get("pass") and a.retry and not str(row.get("fail", "")).startswith("refused"):
            lost = str(row.get("fail", "")).startswith(("comm", "no answer"))
            if lost and getattr(ctx, "relink", None) and not ctx.relink():
                say("unit did not come back: sweep aborted")
                fails += 1
                break
            say(f"  retry {n} once with the same settings (a repeated failure counts, a single one is a flake)")
            row = one_step(ctx, n)
            say(f"  retry of {n}: {'PASS (flake, not counted)' if row.get('pass') else 'FAIL again: reproducible'}")
        if not row.get("pass"):
            fails += 1
            consec += 1
            lost = str(row.get("fail", "")).startswith(("comm", "no answer"))
            if lost and getattr(ctx, "relink", None) and not ctx.relink():
                say("unit did not come back: sweep aborted")
                break
            if not a.continue_on_fail and consec >= stop_after:
                say(f"stop after {consec} consecutive failed step(s) (last {n}); the fw reverts by itself at the hold limit, the WDT resets a stalled main loop")
                break
        else:
            consec = 0
    say(f"sweep done: {len(names)} requested, {fails} failed")
    return fails


if __name__ == "__main__":
    sys.exit(main())
