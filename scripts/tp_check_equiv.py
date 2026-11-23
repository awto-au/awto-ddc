#!/usr/bin/env python3
"""Host proof for #299: DpRx1 Tp1Check_EXINT0 / Tp2Check_EXINT0 after the lane-loop merge == the originals.

usage: tp_check_equiv.py [--fn tp1|tp2|both] [--old-ref REF] [--n N]
  OLD function from git REF (default: the commit before the merge), NEW (+ its static helper) from the working tree, gcc, one
  stub model: DPCD memory, scaler registers, lane mapping, margin bits, link state globals.
  Every side effect (register set / get with mask and value, DPCD set / get / bit-get, return value) goes into a CRC, plus a
  hash of the final state (status / request bytes, margin bits, EQ-CRC byte, TP1-initial flag).
  Inputs: N random cells (xorshift, fixed seed): training type, link rate, lane count (4 / 2 / 1 / invalid), lane mapping (2-bit
  per lane), EQ-CRC and Vth readbacks, DPCD level / request bytes, start state of every global.
  Options as in the build: swing-0 OUI off, forced marginal link on, direct swing-2 request on, MI dongle off.
Log: ./tmp/logs/tp_check_equiv.log
"""

import argparse
import re
import subprocess
import sys

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/tp_check_equiv.log"
SCRATCH = ROOT / "tmp/scratch/tp_equiv"
SRC = "fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_INT_SeptPhy.c"

PRE = r"""
#include <stdio.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t BYTE; typedef uint16_t WORD; typedef unsigned char bit;
#define _BIT0 0x01
#define _BIT1 0x02
#define _BIT2 0x04
#define _BIT3 0x08
#define _BIT4 0x10
#define _BIT5 0x20
#define _BIT6 0x40
#define _BIT7 0x80
#define _TRUE 1
#define _FALSE 0
#define _ON 1
#define _OFF 0
#define _DP_LT_TP1_PERMIT_SWING_LEVEL_0_FOR_SPECIFIC_SOURCE_OUI _OFF
#define _DP_HBR_RBR_LT_FORCE_MARGINAL_LINK _ON
#define _DP_LT_DIRECT_REQUEST_SWING_LEVEL_2 _ON
#define _DP_RX_MI_DONGLE_SUPPORT _OFF
#define _DP_LINK_RBR 0x06
#define _DP_LINK_HBR 0x0A
#define _DP_LINK_HBR2 0x14
#define _DP_FOUR_LANE 4
#define _DP_TWO_LANE 2
#define _DP_ONE_LANE 1
#define _DP_SCALER_LANE0 0
#define _DP_SCALER_LANE1 1
#define _DP_SCALER_LANE2 2
#define _DP_SCALER_LANE3 3
typedef enum { _DP_NORMAL_LT, _DP_FAKE_LT } EnumDpLinkTrainingType;
#define _DP_NORMAL_TRAINING_PATTERN_1_FAIL 5
#define _DP_FAKE_TRAINING_PATTERN_1_FAIL 6
#define PB0_14_EQ_CRC_3 0xB014
#define PB0_12_EQ_CRC_1 0xB012
#define P7A_F0_COEF_1 0x7AF0
#define P7A_F1_COEF_2 0x7AF1
#define P7A_F2_COEF_3 0x7AF2
#define AWTO_TP1_WAIT()
#define DELAY_25US_EXINT() feed('W')
static uint32_t crc = 0xFFFFFFFFu; static unsigned long calls;
static void feed(unsigned b) { crc ^= b & 0xFF; for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1)); }
static BYTE g_map[4], g_rate, g_lanes, g_status01, g_status23, g_req01, g_req23, g_eqcrc_state, g_lt_status, g_tp1init, g_permit;
static BYTE margin[4], pData[8], dpcd[0x400], reg_f0, reg_f2, vth[4], eqcrc_rd, eq1_rd[8]; static unsigned eq1_i;
#define g_ucDpRx1LinkRate g_rate
#define g_ucDpRx1LaneCount g_lanes
#define g_ucDpRx1LinkStatus01 g_status01
#define g_ucDpRx1LinkStatus23 g_status23
#define g_ucDpRx1LinkRequest01 g_req01
#define g_ucDpRx1LinkRequest23 g_req23
#define g_ucDpRx1EQCRC g_eqcrc_state
#define g_ucDpRx1Tp1PermitSwingLevel0 g_permit
#define d_g_bDpRx1Tp1Initial g_tp1init
#define GET_DP_RX1_LINK_TRAINING_STATUS() (g_lt_status)
#define pData_EXINT pData
#define GET_DP_RX1_PCB_LANE0_MAPPING() (g_map[0])
#define GET_DP_RX1_PCB_LANE1_MAPPING() (g_map[1])
#define GET_DP_RX1_PCB_LANE2_MAPPING() (g_map[2])
#define GET_DP_RX1_PCB_LANE3_MAPPING() (g_map[3])
#define _D1_DP_LANE0 (g_map[0])
#define _D1_DP_LANE1 (g_map[1])
#define _D1_DP_LANE2 (g_map[2])
#define _D1_DP_LANE3 (g_map[3])
#define GET_DP_RX_D1_LANE0_MARGIN_LINK_HBR_RBR() (margin[0])
#define GET_DP_RX_D1_LANE1_MARGIN_LINK_HBR_RBR() (margin[1])
#define GET_DP_RX_D1_LANE2_MARGIN_LINK_HBR_RBR() (margin[2])
#define GET_DP_RX_D1_LANE3_MARGIN_LINK_HBR_RBR() (margin[3])
#define SET_DP_RX_D1_LANE0_MARGIN_LINK_HBR_RBR() (margin[0] = 1)
#define SET_DP_RX_D1_LANE1_MARGIN_LINK_HBR_RBR() (margin[1] = 1)
#define SET_DP_RX_D1_LANE2_MARGIN_LINK_HBR_RBR() (margin[2] = 1)
#define SET_DP_RX_D1_LANE3_MARGIN_LINK_HBR_RBR() (margin[3] = 1)
#define CLR_DP_RX_D1_LANE0_MARGIN_LINK_HBR_RBR() (margin[0] = 0)
#define CLR_DP_RX_D1_LANE1_MARGIN_LINK_HBR_RBR() (margin[1] = 0)
#define CLR_DP_RX_D1_LANE2_MARGIN_LINK_HBR_RBR() (margin[2] = 0)
#define CLR_DP_RX_D1_LANE3_MARGIN_LINK_HBR_RBR() (margin[3] = 0)
static BYTE regget(unsigned a) {
    if (a == P7A_F1_COEF_2) return vth[(reg_f2 >> 6) & 3];
    if (a == PB0_14_EQ_CRC_3) return eqcrc_rd;
    if (a == PB0_12_EQ_CRC_1) return eq1_rd[eq1_i++ & 7];
    return 0;
}
#define ScalerSetBit_EXINT(a, an, o) do { BYTE m_ = (BYTE)(an), v_ = (BYTE)(o); feed('S'); feed((a) >> 8); feed(a); feed(m_); feed(v_); \
    if ((a) == P7A_F0_COEF_1) reg_f0 = (reg_f0 & m_) | v_; if ((a) == P7A_F2_COEF_3) reg_f2 = (reg_f2 & m_) | v_; } while (0)
static BYTE getbit(unsigned a, BYTE m) { BYTE v = regget(a) & m; feed('B'); feed(a >> 8); feed(a); feed(m); feed(v); return v; }
static BYTE getbyte(unsigned a) { BYTE v = regget(a); feed('G'); feed(a >> 8); feed(a); feed(v); return v; }
#define ScalerGetBit_EXINT(a, m) getbit(a, m)
#define ScalerGetByte_EXINT(a) getbyte(a)
static void ScalerDpRx1SetDpcdValue_EXINT0(BYTE h, BYTE m, BYTE l, BYTE v) { feed('s'); feed(m); feed(l); feed(v); dpcd[(m << 8 | l) & 0x3FF] = v; }
static BYTE ScalerDpRx1GetDpcdInfo_EXINT0(BYTE h, BYTE m, BYTE l) { BYTE v = dpcd[(m << 8 | l) & 0x3FF]; feed('g'); feed(m); feed(l); feed(v); return v; }
static BYTE ScalerDpRx1GetDpcdBitInfo_EXINT0(BYTE h, BYTE m, BYTE l, BYTE b) { BYTE v = dpcd[(m << 8 | l) & 0x3FF] & b; feed('b'); feed(m); feed(l); feed(b); feed(v); return v; }
"""

DRV = r"""
static uint64_t rs = 0x9E3779B97F4A7C15ull;
static unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)(rs >> 11); }
int main(void) {
    static const BYTE rates[] = {0x06, 0x0A, 0x14};
    static const BYTE lanes[] = {4, 4, 2, 1, 4, 2, 3, 0};
    static const BYTE sts[] = {0, 1, 5, 6, 7};
    for (unsigned long n = 0; n < NCELLS; n++) {
        g_rate = rates[rnd() % 3]; g_lanes = lanes[rnd() % sizeof lanes]; g_lt_status = sts[rnd() % sizeof sts];
        for (int k = 0; k < 4; k++) { g_map[k] = rnd() & 3; margin[k] = rnd() & 1; vth[k] = rnd(); }
        g_status01 = rnd(); g_status23 = rnd(); g_req01 = rnd(); g_req23 = rnd(); g_eqcrc_state = rnd();
        g_tp1init = rnd() & 1; g_permit = rnd() & 1; eqcrc_rd = rnd(); reg_f0 = reg_f2 = 0; eq1_i = 0;
        for (int k = 0; k < 8; k++) eq1_rd[k] = (rnd() & 3) == 0 ? 0xFF : rnd();
        for (unsigned k = 0; k < sizeof dpcd; k++) dpcd[k] = rnd();
        for (int k = 0x103; k <= 0x106; k++) dpcd[k] = (rnd() & 1) ? (rnd() & 0x07) : rnd();
        for (int k = 0; k < 8; k++) pData[k] = rnd();
        EnumDpLinkTrainingType t = (rnd() & 3) ? _DP_NORMAL_LT : _DP_FAKE_LT;
        BYTE r = @CALL@(t);
        feed(r); feed(g_status01); feed(g_status23); feed(g_req01); feed(g_req23); feed(g_eqcrc_state); feed(g_tp1init);
        for (int k = 0; k < 4; k++) feed(margin[k]);
        for (unsigned k = 0x200; k < 0x210; k++) feed(dpcd[k]);
        for (unsigned k = 0x100; k < 0x108; k++) feed(dpcd[k]);
        calls++;
    }
    printf("calls=%lu crc=%08X\n", calls, ~crc);
    return 0;
}
"""


def say(s):
    log_line(s, LOG, stamp_stdout=False)


def git_show(ref, path):
    if ref == "WORK":
        return (ROOT / path).read_text()
    return subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True, cwd=ROOT).stdout


def func(text, name):
    m = re.search(r"^(?:static )?(?:bit|BYTE|void) " + name + r"\([^)]*\)\n\{.*?\n\}\n", text, re.DOTALL | re.MULTILINE)
    if not m:
        raise SystemExit(f"function {name} not found")
    return m.group(0)


def run(ref, names, call, tag, n):
    src = git_show(ref, SRC)
    body = "".join(func(src, x) for x in names)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    c = SCRATCH / f"{tag}.c"
    c.write_text(PRE + body + DRV.replace("@CALL@", call).replace("NCELLS", str(n)))
    exe = SCRATCH / tag
    subprocess.run(["gcc", "-O1", "-w", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()
    say(f"{tag}: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fn", default="both")
    ap.add_argument("--old-ref", default="03f6ef81")
    ap.add_argument("--n", type=int, default=3000000)
    a = ap.parse_args()
    cases = {
        "tp1": ("ScalerDpRx1Tp1Check_EXINT0", ["ScalerDpRx1Tp1LaneCheck_EXINT0"]),
        "tp2": ("ScalerDpRx1Tp2Check_EXINT0", ["ScalerDpRx1Tp2LaneCheck_EXINT0"]),
    }
    bad = 0
    for k, (fn, helpers) in cases.items():
        if a.fn not in (k, "both"):
            continue
        old = run(a.old_ref, [fn], fn, f"{k}_old", a.n)
        src = git_show("WORK", SRC)
        hs = [h for h in helpers if re.search(r"^static \w+ " + h + r"\(", src, re.MULTILINE)]
        new = run("WORK", hs + [fn], fn, f"{k}_new", a.n)
        ok = old == new
        say(f"{k}: {'EQUAL' if ok else 'MISMATCH'}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
