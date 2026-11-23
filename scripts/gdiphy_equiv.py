#!/usr/bin/env python3
"""Host proof for #298: shared ScalerGDIPhyRxPower / RxPowerProc / RxZ0Switch(port) == the old Rx2 / Rx3 copies, per port.

usage: gdiphy_equiv.py [--old-ref REF] [--n N] [--mutate]
  OLD = ScalerGDIPhyRx{2,3}{Power,PowerProc,Z0Switch} + the ScalerGDIPhyZ0Switch dispatcher from git REF (default origin/main
  at the start of #298); NEW = the shared functions in the working tree. gcc, stub register model (64 KiB, random start).
  Every register access (get / set with address, mask, value), every state macro, every ScalerTMDS* call and the final register
  file go into a CRC, one CRC per port; old Rx2 must equal new port 0, old Rx3 new port 1.
  Inputs: all power actions x select x N random register files / state; build variants: Z0 power-saving option, background
  detect, per-port LG 90 ohm, Acer toggle, HDCP 2.2.
  --mutate: swap the Rx2 / Rx3 ABC0 constants in NEW and require a MISMATCH (proves the trace sees the quirk).
Log: ./tmp/logs/gdiphy_equiv.log
"""

import argparse
import itertools
import re
import subprocess
import sys

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/gdiphy_equiv.log"
SCRATCH = ROOT / "tmp/scratch/gdiphy_equiv"
SRC = "fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_GDIPhy.c"
REGS = ROOT / "fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h"

PRE = r"""
#include <stdio.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t BYTE; typedef uintptr_t WORD; typedef unsigned char bit;
#define xdata
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
#define _D0_NO_PORT 0
#define _D1_NO_PORT 0
#define _D2_NO_PORT 0
#define _D3_NO_PORT 0
#define _D2_HDMI_PORT 1
#define _D3_HDMI_PORT 1
#define _D2_MHL_PORT 2
#define _D3_MHL_PORT 2
#define _D0_INPUT_PORT_TYPE 0
#define _D1_INPUT_PORT_TYPE 0
#define _D2_INPUT_PORT_TYPE _D2_HDMI_PORT
#define _D3_INPUT_PORT_TYPE _D3_HDMI_PORT
#define _D2_TMDS_SUPPORT _ON
#define _D3_TMDS_SUPPORT _ON
#define _D0_INPUT_PORT 0
#define _D1_INPUT_PORT 1
#define _D2_INPUT_PORT 2
#define _D3_INPUT_PORT 3
#define _LG_90_OHM 1
#define _BY_CONNECTOR 0
#define _ALL_CHANNEL_CONNECTED_FOR_CTS 1
#define _ONLY_CLK_CHANNEL_CONNECTED_FOR_PS 2
#ifndef ZPS
#define ZPS 1
#endif
#define _TMDS_Z0_POWER_SAVING_OPTION ZPS
#ifndef BGD
#define BGD 0
#endif
#define _SOURCE_BACKGROUND_DETECT_SUPPORT BGD
#ifndef Z2
#define Z2 0
#endif
#define _D2_TMDS_Z0_IMPEDANCE_OPTION Z2
#ifndef Z3
#define Z3 0
#endif
#define _D3_TMDS_Z0_IMPEDANCE_OPTION Z3
#ifndef ACER
#define ACER 0
#endif
#define _TMDS_TOGGLE_HPD_Z0_FOR_ACER ACER
#ifndef H22
#define H22 0
#endif
#define _TMDS_HDCP_2_2_SUPPORT H22
#define _HDCP_2_2_SUPPORT H22
typedef enum { _POWER_ACTION_OFF_TO_NORMAL = 0, _POWER_ACTION_OFF_TO_FAKE_OFF, _POWER_ACTION_AC_ON_TO_NORMAL, _POWER_ACTION_AC_ON_TO_OFF,
    _POWER_ACTION_AC_ON_INITIAL, _POWER_ACTION_PS_TO_NORMAL, _POWER_ACTION_PS_TO_OFF, _POWER_ACTION_NORMAL_TO_PS, _POWER_ACTION_NORMAL_TO_OFF,
    _POWER_ACTION_NORMAL_TO_FAKE_OFF, _POWER_ACTION_SWITCH_INTERFACE_TO_OFF, _POWER_ACTION_NORMAL_TO_FAKE_PS, _POWER_ACTION_FAKE_PS_TO_NORMAL,
    _POWER_ACTION_FAKE_OFF_TO_NORMAL, _POWER_ACTION_NONE = 0xFF } EnumPowerAction;
#include "@REGS@"
static uint32_t crc[2] = {0xFFFFFFFFu, 0xFFFFFFFFu}; static int cur;
static void feed(unsigned b) { uint32_t *c = &crc[cur]; *c ^= b & 0xFF; for (int i = 0; i < 8; i++) *c = (*c >> 1) ^ (0xEDB88320u & -(*c & 1)); }
static BYTE reg[65536], xreg[65536], isr_g_ucDigitalSwitch, z0[2], ddc[2];
#define MCU_FE69_DDC2_EDID_IRQ (*(volatile BYTE *)(xreg + 0xFE69))
#define MCU_FE72_DDC3_EDID_IRQ (*(volatile BYTE *)(xreg + 0xFE72))
static BYTE d_isr_g_ucTMDSRxPort;
@SHAREMACROS@
static void RxSetBit(WORD a, BYTE an, BYTE o) { a += (WORD)RX_CUR << 8; feed('S'); feed(a >> 8); feed(a); feed(an); feed(o); reg[a] = (reg[a] & an) | o; }
static BYTE RxGetBit(WORD a, BYTE m) { a += (WORD)RX_CUR << 8; BYTE v = reg[a] & m; feed('B'); feed(a >> 8); feed(a); feed(m); feed(v); return v; }
static void RxSetByte(WORD a, BYTE v) { a += (WORD)RX_CUR << 8; feed('W'); feed(a >> 8); feed(a); feed(v); reg[a] = v; }
static void ScalerSetBit(WORD a, BYTE an, BYTE o) { feed('S'); feed(a >> 8); feed(a); feed(an); feed(o); reg[a] = (reg[a] & an) | o; }
static BYTE ScalerGetBit(WORD a, BYTE m) { BYTE v = reg[a] & m; feed('B'); feed(a >> 8); feed(a); feed(m); feed(v); return v; }
static void ScalerSetByte(WORD a, BYTE v) { feed('W'); feed(a >> 8); feed(a); feed(v); reg[a] = v; }
#define SET_DIGITAL_PORT_SWITCH_TO_D2() (feed('2'), isr_g_ucDigitalSwitch |= _BIT3)
#define CLR_DIGITAL_PORT_SWITCH_TO_D2() (feed('3'), isr_g_ucDigitalSwitch &= ~_BIT3)
#define SET_DIGITAL_PORT_SWITCH_TO_D3() (feed('4'), isr_g_ucDigitalSwitch |= _BIT2)
#define CLR_DIGITAL_PORT_SWITCH_TO_D3() (feed('5'), isr_g_ucDigitalSwitch &= ~_BIT2)
#define SET_TMDS_RX2_Z0_ASSERTED() (feed('a'), z0[0] = 1)
#define SET_TMDS_RX3_Z0_ASSERTED() (feed('A'), z0[1] = 1)
#define CLR_TMDS_RX2_DDC_DETECTED() (feed('d'), ddc[0] = 0)
#define CLR_TMDS_RX3_DDC_DETECTED() (feed('D'), ddc[1] = 0)
#define CLR_TMDS_RX2_TOGGLE_Z0() feed('t')
#define CLR_TMDS_RX3_TOGGLE_Z0() feed('T')
#define CLR_TMDS_RX2_TOGGLE_Z0_EVENT() feed('e')
#define CLR_TMDS_RX3_TOGGLE_Z0_EVENT() feed('E')
static void ScalerTMDSRx2PowerSavingProc(void) { feed('p'); }
static void ScalerTMDSRx3PowerSavingProc(void) { feed('P'); }
static void ScalerTMDSRx2PowerOffProc(void) { feed('o'); }
static void ScalerTMDSRx3PowerOffProc(void) { feed('O'); }
static void ScalerHdcp2ResetTMDSProc(BYTE p) { feed('h'); feed(p); }
static void ScalerGDIPhyZ0Switch(BYTE ucPortSelect, bit bSelect);
@FUNCS@
static uint64_t rs = 0x9E3779B97F4A7C15ull;
static unsigned rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (unsigned)(rs >> 11); }
static const EnumPowerAction acts[] = {_POWER_ACTION_OFF_TO_NORMAL, _POWER_ACTION_AC_ON_TO_NORMAL, _POWER_ACTION_AC_ON_TO_OFF, _POWER_ACTION_PS_TO_NORMAL,
    _POWER_ACTION_PS_TO_OFF, _POWER_ACTION_NORMAL_TO_PS, _POWER_ACTION_NORMAL_TO_OFF, _POWER_ACTION_SWITCH_INTERFACE_TO_OFF, _POWER_ACTION_AC_ON_INITIAL,
    _POWER_ACTION_NONE};
int main(void) {
    unsigned long cells = 0;
    for (unsigned long n = 0; n < NCELLS; n++) {
        for (unsigned k = 0x7000; k < 0x7E00; k++) reg[k] = rnd();
        for (unsigned k = 0xFE00; k < 0xFF00; k++) xreg[k] = rnd();
        BYTE sw = rnd(), z0a = rnd() & 1, ddca = rnd() & 1;
        for (unsigned a = 0; a < sizeof acts / sizeof acts[0]; a++) for (int sel = 0; sel < 2; sel++) for (int kind = 0; kind < 3; kind++) {
            for (int p = 0; p < 2; p++) {
                cur = p; d_isr_g_ucTMDSRxPort = sw & 1; isr_g_ucDigitalSwitch = sw; z0[0] = z0[1] = z0a; ddc[0] = ddc[1] = ddca;
                static BYTE sreg[0xE00], sx[0x100];
                memcpy(sreg, reg + 0x7000, 0xE00); memcpy(sx, xreg + 0xFE00, 0x100);
                CALL(kind, p, acts[a], sel);
                feed(d_isr_g_ucTMDSRxPort); feed(isr_g_ucDigitalSwitch); feed(z0[p]); feed(ddc[p]); feed(z0[p ^ 1]); feed(ddc[p ^ 1]);
                for (unsigned k = 0x7000; k < 0x7E00; k++) feed(reg[k]);
                feed(xreg[0xFE69]); feed(xreg[0xFE72]);
                memcpy(reg + 0x7000, sreg, 0xE00); memcpy(xreg + 0xFE00, sx, 0x100);
            }
            cells++;
        }
    }
    printf("cells=%lu rx2=%08X rx3=%08X\n", cells, ~crc[0], ~crc[1]);
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


def proto(f):
    return re.sub(r"\n\{.*", ";", f, flags=re.DOTALL).replace("void ", "static void ", 1)


def share_macros():
    h = (ROOT / "fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Header/RL6449_Series_TMDSRxShareInclude.h").read_text()
    return "\n".join(l for l in h.split("\n") if re.match(r"#define (RX_CUR|RXSEL|RXSTMT|RXREG)\b", l))


def old_funcs(ref):
    src = git_show(ref, SRC)
    names = [f"ScalerGDIPhyRx{p}{k}" for p in (2, 3) for k in ("Power", "PowerProc", "Z0Switch")] + ["ScalerGDIPhyZ0Switch"]
    fs = [func(src, n).replace("void ", "static void ", 1) for n in names]
    pro = "".join(proto(func(src, n)) + "\n" for n in names)
    call = r"""
#define CALL(kind, p, a, s) do { if (kind == 0) { if (p) ScalerGDIPhyRx3Power(a); else ScalerGDIPhyRx2Power(a); } \
    else if (kind == 1) { if (p) ScalerGDIPhyRx3PowerProc(a); else ScalerGDIPhyRx2PowerProc(a); } \
    else { if (p) ScalerGDIPhyRx3Z0Switch(s); else ScalerGDIPhyRx2Z0Switch(s); } } while (0)
"""
    return pro + "".join(fs) + call


def new_funcs(mutate):
    src = git_show("WORK", SRC)
    pre = src[src.index("#define GDI_EDID_IRQ"):src.index("//--------------------------------------------------\n// Description  : GDI Rx2 / Rx3 Power Process")]
    if mutate:
        for k in ("AND", "OR"):
            d2, d3 = f"GDI_ABC0_HDCP_CLR_{k}_D2    ", f"GDI_ABC0_HDCP_CLR_{k}_D3    "
            pre = pre.replace(d2, "@X@    ").replace(d3, d2).replace("@X@    ", d3)
    names = ["ScalerGDIPhyRxPower", "ScalerGDIPhyRxPowerProc", "ScalerGDIPhyRxZ0Switch"]
    fs = [func(src, n).replace("void ", "static void ", 1) for n in names]
    pro = "".join(proto(func(src, n)) + "\n" for n in names)
    call = r"""
#define CALL(kind, p, a, s) do { if (kind == 0) ScalerGDIPhyRxPower(p, a); else if (kind == 1) ScalerGDIPhyRxPowerProc(p, a); \
    else ScalerGDIPhyRxZ0Switch(p, s); } while (0)
"""
    return pre + pro + "".join(fs) + call


def build_run(tag, funcs, defs, n):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    c = SCRATCH / f"{tag}.c"
    c.write_text(PRE.replace("@SHAREMACROS@", share_macros()).replace("@REGS@", str(REGS)).replace("@FUNCS@", funcs).replace("NCELLS", str(n)))
    exe = SCRATCH / tag
    subprocess.run(["gcc", "-O1", "-w", *[f"-D{d}" for d in defs], "-o", str(exe), str(c)], check=True)
    return subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-ref", default="4ab8550c")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args()
    old = old_funcs(a.old_ref)
    new = new_funcs(a.mutate)
    bad = 0
    variants = list(itertools.product((1, 2), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)))
    for zps, bgd, z2, z3, acer, h22 in variants:
        defs = [f"ZPS={zps}", f"BGD={bgd}", f"Z2={z2}", f"Z3={z3}", f"ACER={acer}", f"H22={h22}"]
        tag = f"zps{zps}_bgd{bgd}_z{z2}{z3}_acer{acer}_h22{h22}"
        o = build_run(tag + "_old", old, defs, a.n)
        w = build_run(tag + "_new", new, defs, a.n)
        ok = o == w
        say(f"{tag}: old [{o}] new [{w}] {'EQUAL' if ok else 'MISMATCH'}")
        bad += not ok
    if a.mutate:
        say(f"mutation (ABC0 values swapped in NEW): {bad}/{len(variants)} variants MISMATCH (all must)")
        return 0 if bad == len(variants) else 1
    say(f"{len(variants) - bad}/{len(variants)} variants EQUAL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
