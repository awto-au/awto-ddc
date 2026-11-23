#!/usr/bin/env python3
"""Host proof for #44: the DP Rx1 HDCP 1.4 functions gated out under _AWTO_HDCP == _OFF behave as before.

usage: hdcp_off_equiv.py [--old-ref REF] [--n N] [--violate none|aksv|vprime|mode|auth]
  OLD = function bodies from git REF (default: HDCP off, before the gating); NEW = working tree with _AWTO_HDCP = _OFF plus the
  OFF macros of ScalerDPRx1_SeptPhyInclude.h. gcc, one stub model: scaler registers (get / set with mask), DPCD memory.
  Compared per call: return value, every register set (address, mask, value), final registers, final DPCD memory.
  DPCD sets / register gets are not in the trace (reads have no side effect; a zero over a zero DPCD cell changes nothing).
  Precondition P (HDCP idle, true without HDCP): HDCP mode 1.4 (PB0_1A bit1 = 0), no authentication (PB0_20 bit7 = 0), Aksv
  DPCD 0x68007-B zero, V' / RxStatus / KSV FIFO cells (0x68014-27, 29-2B, 2C-3A) zero, HDCP2 answer regs not 0x53 0x1F.
  --violate breaks one part of P (control: must report MISMATCH).
Log: ./tmp/logs/hdcp_off_equiv.log
"""

import argparse
import re
import subprocess
import sys

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/hdcp_off_equiv.log"
SCRATCH = ROOT / "tmp/scratch/hdcp_off_equiv"
SRC = "fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c"
SRC_DPRX1 = "fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_DPRx1.c"
HDR = "fw/sdk/Kernel/Scaler/ScalerFunction/Header/ScalerDPRx1_SeptPhyInclude.h"
HDR_AUX = "fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Header/RL6449_Series_DPRx1Include.h"

PRE = r"""
#include <stdio.h>
#include <stdint.h>
typedef uint8_t BYTE; typedef unsigned char bit;
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
#define _ENABLE 1
#define _DISABLE 0
#define _AWTO_HDCP @HDCP@
#define _DP_HDCP_2_2_SUPPORT _OFF
#define _DP_TX_SUPPORT _OFF
#define _DP_MST_SUPPORT _OFF
#define _D1_DP_MST_PORT_SUPPORT _OFF
#define _EIZO_CUSTOMIZED_VALUE_OF_DPCD_SUPPORT _OFF
enum { _HDCP_14 = 1, _HDCP_22 = 2 };
enum { PB0_01_PHY_DIG_RESET_CTRL, PB0_1A_HDCP_IRQ, PB0_1E_HDCP_INTGT_VRF_ANS_MSB, PB0_1F_HDCP_INTGT_VRF_ANS_LSB, PB0_20_HDCP_DEBUG,
       PBA_D0_AUX_MODE_SET, PBA_DA_AUX_FIFO_RST, PBA_A5_AUX_RESERVE5, NREG };
static uint32_t crc = 0xFFFFFFFFu;
static void feed(unsigned b) { crc ^= b & 0xFF; for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1)); }
static BYTE regs[NREG], pData[32], dpcd[1 << 20], EX0;
static BYTE ScalerGetBit(unsigned a, BYTE m) { return regs[a] & m; }
static BYTE ScalerGetByte(unsigned a) { return regs[a]; }
static void ScalerSetBit(unsigned a, unsigned an, BYTE o) { BYTE m = (BYTE)an; feed('S'); feed(EX0); feed(a); feed(m); feed(o); regs[a] = (regs[a] & m) | o; }
static void ScalerDpRx1SetDpcdValue(BYTE h, BYTE m, BYTE l, BYTE v) { dpcd[(h << 16) | (m << 8) | l] = v; }
static BYTE ScalerDpRx1GetDpcdInfo(BYTE h, BYTE m, BYTE l) { return dpcd[(h << 16) | (m << 8) | l]; }
#define GET_DP_RX1_HDCP_MODE() ((ScalerGetBit(PB0_1A_HDCP_IRQ, _BIT1) == _BIT1) ? _HDCP_22 : _HDCP_14)
static unsigned mrs = 1;
static bit ScalerDpRx1HdcpMeasureCheck(void) { feed('M'); return (mrs++ & 1); }
"""

DRV = r"""
static uint64_t rs = 0x9E3779B97F4A7C15ull;
static unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)(rs >> 11); }
static BYTE rb(void) { return (BYTE)rnd(); }
static BYTE run(int fn) {
    switch (fn) {
    case 0: ScalerDpRx1ChangeHdcpDpcdCapability(_DISABLE); return 0;
    case 1: ScalerDpRx1HDCPBlockReset(); return 0;
    case 2: return ScalerDpRx1HdcpCheckValid();
    case 3: return ScalerDpRx1HdcpCheckEnabled();
    case 4: return ScalerDpRx1HdcpReAuthStatusCheck();
    case 5: ScalerDpRx1CheckHdcpCpirqStatus(); return 0;
    default: return ScalerDpRx1HdcpCheck();
    }
}
int main(void) {
    static BYTE sregs[NREG], sdpcd[1 << 20];
    unsigned long calls = 0;
    for (unsigned long n = 0; n < NCELLS; n++) {
        for (int k = 0; k < NREG; k++) regs[k] = rb();
        for (unsigned k = 0x68000; k < 0x69300; k++) dpcd[k] = rb();
        for (unsigned k = 0x00000; k < 0x00400; k++) dpcd[k] = rb();
        regs[PB0_1A_HDCP_IRQ] &= ~_BIT1;
        regs[PB0_20_HDCP_DEBUG] &= ~_BIT7;
        if (regs[PB0_1E_HDCP_INTGT_VRF_ANS_MSB] == 0x53 && regs[PB0_1F_HDCP_INTGT_VRF_ANS_LSB] == 0x1F) regs[PB0_1F_HDCP_INTGT_VRF_ANS_LSB] = 0;
        for (unsigned k = 0x68007; k <= 0x6800B; k++) dpcd[k] = 0;
        for (unsigned k = 0x68014; k <= 0x6803A; k++) if (k != 0x68028) dpcd[k] = 0;
        VIOLATE
        for (unsigned k = 0; k < NREG; k++) sregs[k] = regs[k];
        for (unsigned k = 0x68000; k < 0x69300; k++) sdpcd[k] = dpcd[k];
        for (unsigned k = 0; k < 0x400; k++) sdpcd[k] = dpcd[k];
        for (int fn = 0; fn < 7; fn++) {
            for (unsigned k = 0; k < NREG; k++) regs[k] = sregs[k];
            for (unsigned k = 0x68000; k < 0x69300; k++) dpcd[k] = sdpcd[k];
            for (unsigned k = 0; k < 0x400; k++) dpcd[k] = sdpcd[k];
            BYTE r = run(fn);
            feed('R'); feed(fn); feed(r);
            for (int k = 0; k < NREG; k++) feed(regs[k]);
            for (unsigned k = 0x68000; k < 0x69300; k++) feed(dpcd[k]);
            calls++;
        }
    }
    printf("calls=%lu crc=%08X\n", calls, ~crc);
    return 0;
}
"""

VIOLATIONS = {
    "none": "",
    "aksv": "if (rnd() & 1) dpcd[0x68007 + rnd() % 5] = 1 + rnd() % 255;",
    "vprime": "if (rnd() & 1) dpcd[0x68014 + rnd() % 20] = 1 + rnd() % 255;",
    "mode": "if (rnd() & 1) regs[PB0_1A_HDCP_IRQ] |= _BIT1;",
    "auth": "if (rnd() & 1) regs[PB0_20_HDCP_DEBUG] |= _BIT7 | _BIT5 | _BIT6;",
}


def say(s):
    log_line(s, LOG, stamp_stdout=False)


def text(ref, path):
    if ref == "WORK":
        return (ROOT / path).read_text()
    return subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True, cwd=ROOT).stdout


def func(src, name):
    m = re.search(r"^(?:static )?(?:bit|BYTE|void) " + name + r"\([^)]*\)\n\{.*?\n\}\n", src, re.DOTALL | re.MULTILINE)
    if not m:
        raise SystemExit(f"function {name} not found")
    return m.group(0)


def aux_macros(ref):
    h = text(ref, HDR_AUX)
    ms = re.findall(r"#define SET_DP_RX1_AUX_(?:MANUAL|AUTO)_MODE\(\)\s+\{\\\n(?:.*\\\n)*.*\}\n", h)
    if len(ms) != 2:
        raise SystemExit("aux mode macros not found")
    return "".join(ms)


def off_macros(ref):
    h = text(ref, HDR)
    out = ""
    for m in re.finditer(r"#if\(_AWTO_HDCP == _ON\)\n(?:extern[^\n]*\n)+#else\n((?:[^\n]*\n)*?)#endif\n", h):
        out += m.group(1)
    return out


def build(ref, tag, n, violate):
    src = text(ref, SRC)
    names = ["ScalerDpRx1ChangeHdcpDpcdCapability", "ScalerDpRx1HDCPBlockReset"]
    new = ref == "WORK"
    body = aux_macros(ref) + (off_macros(ref) if new else "")
    if not new:
        names += ["ScalerDpRx1HdcpCheckValid", "ScalerDpRx1HdcpCheckEnabled", "ScalerDpRx1HdcpReAuthStatusCheck", "ScalerDpRx1CheckHdcpCpirqStatus"]
    body += "".join(func(src, x) + "\n" for x in names)
    body += func(text(ref, SRC_DPRX1), "ScalerDpRx1HdcpCheck")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    c = SCRATCH / f"{tag}.c"
    c.write_text(PRE.replace("@HDCP@", "_OFF") + body + DRV.replace("NCELLS", str(n)).replace("VIOLATE", VIOLATIONS[violate]))
    exe = SCRATCH / tag
    subprocess.run(["gcc", "-O1", "-w", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()
    say(f"{tag}: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-ref", default="a74fefa5")
    ap.add_argument("--n", type=int, default=300000)
    ap.add_argument("--violate", default="none", choices=sorted(VIOLATIONS))
    a = ap.parse_args()
    old = build(a.old_ref, "old", a.n, a.violate)
    new = build("WORK", "new", a.n, a.violate)
    ok = old == new
    say(f"violate={a.violate}: {'EQUAL' if ok else 'MISMATCH'}")
    return 0 if ok == (a.violate == "none") else 1


if __name__ == "__main__":
    sys.exit(main())
