#!/usr/bin/env python3
"""Host proof for #300: DpRx1 DFECheck (main) and DFECheck_EXINT0 (ISR) after the lane-helper merge == the originals.

usage: dfe_check_equiv.py [--old-ref REF]
  OLD functions from git REF (default: the commit before the merge), NEW from the working tree; both compiled with gcc
  against one register model: every access (set bit / get byte: address, mask, value) goes into a CRC, plus the return value.
  State space per function: link rate (HBR2 / other) x lane-count byte (1, 2, 4, 0x84 / 0x82 / 0x81 with the framing bit,
  3, 0, 8) x lane mapping (4^4) x per physical lane one of 5 (Vth, Tap0) read pairs, incl. the invalid (0x00, 0x15) pair.
  The debug message call is stubbed out (text changed on purpose: one message, lane as value).
Log: ./tmp/logs/dfe_check_equiv.log
"""

import argparse
import re
import subprocess
import sys

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/dfe_check_equiv.log"
SCRATCH = ROOT / "tmp/scratch/dfe_equiv"
MAIN = "fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c"
ISR = "fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_INT_SeptPhy.c"

PRE = r"""
#include <stdio.h>
#include <stdint.h>
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
#define _DP_LINK_HBR2 0x14
#define _DP_FOUR_LANE 0x04
#define _DP_TWO_LANE 0x02
#define _DP_ONE_LANE 0x01
#define P7A_F0_COEF_1 0x7AF0
#define P7A_F1_COEF_2 0x7AF1
#define P7A_F2_COEF_3 0x7AF2
static uint32_t crc = 0xFFFFFFFFu; static unsigned long calls;
static void feed(unsigned b) { crc ^= b & 0xFF; for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1)); }
static BYTE g_map[4], g_rate, g_lanes, rdv[4][2], reg_f0, reg_f2, pData[8];
static BYTE regs_get(unsigned a) {
    if (a == P7A_F1_COEF_2) return rdv[(reg_f2 >> 6) & 3][reg_f0 & 1];
    return 0;
}
#define ScalerSetBit(a, an, o) do { BYTE m_ = (BYTE)(an), v_ = (BYTE)(o); feed('S'); feed((a) >> 8); feed(a); feed(m_); feed(v_); \
    if ((a) == P7A_F0_COEF_1) reg_f0 = (reg_f0 & m_) | v_; if ((a) == P7A_F2_COEF_3) reg_f2 = (reg_f2 & m_) | v_; } while (0)
static BYTE getbyte(unsigned a) { BYTE v = regs_get(a); feed('G'); feed(a >> 8); feed(a); feed(v); return v; }
#define ScalerGetByte(a) getbyte(a)
#define ScalerSetBit_EXINT ScalerSetBit
#define ScalerGetByte_EXINT getbyte
#define PDATA_WORD(x) ((WORD)(((WORD)pData[2 * (x)] << 8) | pData[2 * (x) + 1]))
#define PDATA_WORD_EXINT(x) PDATA_WORD(x)
#define pData_EXINT pData
#define _D1_DP_LANE0 (g_map[0])
#define _D1_DP_LANE1 (g_map[1])
#define _D1_DP_LANE2 (g_map[2])
#define _D1_DP_LANE3 (g_map[3])
#define g_ucDpRx1LinkRate g_rate
#define g_ucDpRx1LaneCount g_lanes
#define DebugMessageRx1(x, y) ((void)(y))
static BYTE ScalerDpRx1GetDpcdInfo(BYTE h, BYTE m, BYTE l) { feed('D'); feed(l); return l == 0 ? g_rate : g_lanes; }
"""

DRV = r"""
int main(void) {
    static const BYTE rates[] = {0x14, 0x0A, 0x06};
    static const BYTE lanes[] = {1, 2, 4, 0x84, 0x82, 0x81, 3, 0, 8};
    static const BYTE vt[5][2] = {{0, 0x15}, {0, 0x14}, {1, 0x15}, {0x0F, 0x1F}, {0, 0}};
    for (unsigned ri = 0; ri < 3; ri++)
    for (unsigned li = 0; li < sizeof lanes; li++)
    for (unsigned mp = 0; mp < 256; mp++)
    for (unsigned c = 0; c < 625; c++) {
        g_rate = rates[ri]; g_lanes = lanes[li];
        for (int k = 0; k < 4; k++) g_map[k] = (mp >> (2 * k)) & 3;
        unsigned cc = c;
        for (int k = 0; k < 4; k++) { rdv[k][0] = vt[cc % 5][0] | 0xE0 * (k & 1); rdv[k][1] = vt[cc % 5][1] | 0xE0 * (k & 1); cc /= 5; }
        reg_f0 = reg_f2 = 0; pData[0] = pData[1] = 0xAA;
        feed(@CALL@); calls++;
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
    m = re.search(r"^(?:static )?(?:bit|BYTE) " + name + r"\([^)]*\)\n\{.*?\n\}\n", text, re.DOTALL | re.MULTILINE)
    if not m:
        raise SystemExit(f"function {name} not found")
    return m.group(0)


def run(ref, path, names, call, tag):
    src = git_show(ref, path)
    body = "".join(func(src, n) for n in names)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    c = SCRATCH / f"{tag}.c"
    c.write_text(PRE + body + DRV.replace("@CALL@", call))
    exe = SCRATCH / tag
    subprocess.run(["gcc", "-O1", "-w", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()
    say(f"{tag}: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-ref", default="021f3788")
    a = ap.parse_args()
    bad = 0
    for label, path, helper, fn in (
        ("main", MAIN, "ScalerDpRx1DFELaneCheck", "ScalerDpRx1DFECheck"),
        ("isr", ISR, "ScalerDpRx1DFELaneCheck_EXINT0", "ScalerDpRx1DFECheck_EXINT0"),
    ):
        old = run(a.old_ref, path, [fn], f"{fn}()", f"{label}_old")
        new = run("WORK", path, [helper, fn], f"{fn}()", f"{label}_new")
        ok = old == new
        say(f"{label}: {'EQUAL' if ok else 'MISMATCH'}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
