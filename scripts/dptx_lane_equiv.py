#!/usr/bin/env python3
"""Host proof for #295: the merged eDP lane Adjust functions == the 8 per-lane originals.

usage: dptx_lane_equiv.py [--old-ref REF]
  Extracts the OLD per-lane functions + macros + struct from git REF (default: last commit before the merge)
  and the NEW ones from the working tree, compiles each with gcc and runs both over the state space:
    lane 0..3 x own lane byte (256) x request byte of the lane's pair (256) x own SameVolCnt 0..4
    x background of the other lanes (cur bytes, other request byte, other counts).
  Every call: return value + all lane bytes + request bytes + counts into a CRC; OLD CRC must equal NEW CRC.
  SameVolCnt stays 0..4: the function clears it at 5 (3-bit field never wraps).
Log: ./tmp/logs/dptx_lane_equiv.log
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from _log import shared

ROOT = Path(
    os.environ.get("AWTO_DDC_REPO")
    or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    or Path(__file__).resolve().parents[1]
)
LOG = ROOT / "tmp/logs/dptx_lane_equiv.log"
SCRATCH = ROOT / "tmp/scratch/dptx_lane"
SRC = "fw/sdk/Kernel/Scaler/ScalerFunction/Code/ScalerDisplayDPTx.c"
HDR = "fw/sdk/Kernel/Scaler/ScalerFunction/Header/ScalerDisplayDPTxInclude.h"
TYP = "fw/sdk/Kernel/Scaler/ScalerFunction/Header/ScalerGDIPhyTxInclude.h"
DEFAULT_OLD = "2949ca69"

PRE = r"""
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
typedef uint8_t BYTE; typedef uint16_t WORD; typedef unsigned char bit;
#define __xdata
#define _BIT0 0x01
#define _BIT1 0x02
#define _BIT2 0x04
#define _BIT3 0x08
#define _BIT4 0x10
#define _BIT5 0x20
#define _BIT6 0x40
#define _BIT7 0x80
#define _SUCCESS 1
#define _FAIL 0
#define _TRUE 1
#define _DISPLAY_DP_TX_LEVEL_3 3
"""


def say(s):
    shared(LOG, stamp_echo=False).say(s)


def git_show(ref, path):
    if ref == "WORK":
        return (ROOT / path).read_text()
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout


def func(text, name):
    m = re.search(
        r"^(?:static )?(?:bit|void|BYTE) " + name + r"\([^)]*\)\n\{.*?\n\}\n",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        raise SystemExit(f"function {name} not found")
    return m.group(0)


def build(ref, new):
    src, hdr, typ = git_show(ref, SRC), git_show(ref, HDR), git_show(ref, TYP)
    st = re.search(
        r"typedef struct\s*\{[^}]*ucLane0Adjust[^}]*\}\s*StructDPTxLTInfo;",
        typ,
        re.DOTALL,
    ).group(0)
    macros = [
        ln
        for ln in hdr.splitlines()
        if re.match(r"#define (GET|SET|ADD|CLR)_DISPLAY_DP_TX1_(TP1_)?LANE\d_", ln)
        and "STATUS" not in ln
        and "CR_DONE" not in ln
        and "EQ_DONE" not in ln
    ]
    body = ""
    if new:
        body += "\n".join(
            ln
            for ln in src.splitlines()
            if ln.startswith(("#define DPTX_LANE_CHK", "DPTX_LANE_CHK("))
        )
        body += (
            "\n"
            + func(src, "ScalerDisplayDPTx1TP1SameVolCnt")
            + func(src, "ScalerDisplayDPTxLaneSetCurrent")
            + func(src, "ScalerDisplayDPTx1TP1LaneAdjust")
            + func(src, "ScalerDisplayDPTx1TP2LaneAdjust")
        )
        call1, call2 = (
            "ScalerDisplayDPTx1TP1LaneAdjust(L)",
            "ScalerDisplayDPTx1TP2LaneAdjust(L)",
        )
        body = (
            "static void ScalerDisplayDPTxLaneSetCurrent(BYTE __xdata *, BYTE, BYTE);\n"
            "static BYTE ScalerDisplayDPTx1TP1SameVolCnt(BYTE, bit);\n" + body
        )
    else:
        for n in range(4):
            body += func(src, f"ScalerDisplayDPTx1TP1Lane{n}Adjust") + func(
                src, f"ScalerDisplayDPTx1TP2Lane{n}Adjust"
            )
        call1 = "(BYTE)(L==0?ScalerDisplayDPTx1TP1Lane0Adjust():L==1?ScalerDisplayDPTx1TP1Lane1Adjust():L==2?ScalerDisplayDPTx1TP1Lane2Adjust():ScalerDisplayDPTx1TP1Lane3Adjust())"
    drv = r"""
#define CNT(n) GET_DISPLAY_DP_TX1_TP1_LANE##n##_SAME_VOL_CNT()
static uint32_t crc = 0xFFFFFFFFu; static unsigned long calls;
static void feed(BYTE b) { crc ^= b; for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1)); }
static void setcnt(int l, int v) {
    switch (l) { case 0: g_stDisplayDPTx1LTInfo.@c0@ = v; break; case 1: g_stDisplayDPTx1LTInfo.@c1@ = v; break;
                 case 2: g_stDisplayDPTx1LTInfo.@c2@ = v; break; default: g_stDisplayDPTx1LTInfo.@c3@ = v; }
}
static void dump(int r) {
    feed(r); feed(g_stDisplayDPTx1LTInfo.ucLane0Adjust); feed(g_stDisplayDPTx1LTInfo.ucLane1Adjust);
    feed(g_stDisplayDPTx1LTInfo.ucLane2Adjust); feed(g_stDisplayDPTx1LTInfo.ucLane3Adjust);
    feed(g_stDisplayDPTx1LTInfo.ucAdjustReqLane01); feed(g_stDisplayDPTx1LTInfo.ucAdjustReqLane23);
    feed(CNT(0)); feed(CNT(1)); feed(CNT(2)); feed(CNT(3)); calls++;
}
@fn@
int main(void) {
    static const BYTE bg[] = {0x00, 0xFF, 0xA5, 0x5A, 0x1B, 0xE4};
    static const int bc[] = {0, 2, 4};
    for (int fnsel = 1; fnsel <= 2; fnsel++)
    for (int L = 0; L < 4; L++)
    for (unsigned b = 0; b < sizeof bg; b++)
    for (int ci = 0; ci < 3; ci++)
    for (int cur = 0; cur < 256; cur++)
    for (int req = 0; req < 256; req++)
    for (int cnt = 0; cnt <= 4; cnt++) {
        BYTE *lane[4] = {&g_stDisplayDPTx1LTInfo.ucLane0Adjust, &g_stDisplayDPTx1LTInfo.ucLane1Adjust,
                         &g_stDisplayDPTx1LTInfo.ucLane2Adjust, &g_stDisplayDPTx1LTInfo.ucLane3Adjust};
        for (int k = 0; k < 4; k++) { *lane[k] = bg[(b + k) % sizeof bg]; setcnt(k, bc[(ci + k) % 3]); }
        g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 = g_stDisplayDPTx1LTInfo.ucAdjustReqLane23 = bg[(b + 3) % sizeof bg];
        *lane[L] = cur; setcnt(L, cnt);
        if (L < 2) g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 = req; else g_stDisplayDPTx1LTInfo.ucAdjustReqLane23 = req;
        int r = 0;
        if (fnsel == 1) r = @call1@; else { @call2@; }
        dump(r);
    }
    printf("calls=%lu crc=%08X\n", calls, ~crc);
    return 0;
}
"""
    if new:
        cnt = [f"b3TP1Lane{i}SameVolCnt" for i in range(4)]
        call2 = "ScalerDisplayDPTx1TP2LaneAdjust(L)"
    else:
        cnt = [f"b3TP1Lane{i}SameVolCnt" for i in range(4)]
        call2 = "switch (L) { case 0: ScalerDisplayDPTx1TP2Lane0Adjust(); break; case 1: ScalerDisplayDPTx1TP2Lane1Adjust(); break; case 2: ScalerDisplayDPTx1TP2Lane2Adjust(); break; default: ScalerDisplayDPTx1TP2Lane3Adjust(); }"
    # the old/new SameVolCnt GET macros differ only by field name; the driver reads through them
    subst = {
        "c0": cnt[0],
        "c1": cnt[1],
        "c2": cnt[2],
        "c3": cnt[3],
        "fn": "",
        "call1": call1,
        "call2": call2,
    }
    for k, v in subst.items():
        drv = drv.replace(f"@{k}@", v)
    text = (
        PRE
        + st
        + "\nStructDPTxLTInfo g_stDisplayDPTx1LTInfo;\n"
        + "\n".join(macros)
        + "\n"
        + body
        + drv
    )
    # prototypes: old functions are defined before use; the new statics too (helper declared above)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-ref", default=DEFAULT_OLD)
    a = ap.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out = {}
    for tag, ref, new in (("old", a.old_ref, False), ("new", "WORK", True)):
        c = SCRATCH / f"{tag}.c"
        c.write_text(build(ref, new))
        exe = SCRATCH / tag
        r = subprocess.run(
            ["gcc", "-O1", "-w", "-o", str(exe), str(c)],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode:
            say(f"{tag}: gcc failed\n{r.stderr[:3000]}")
            return 2
        res = subprocess.run(
            [str(exe)], capture_output=True, text=True, check=False
        ).stdout.strip()
        say(f"{tag}: {res}")
        out[tag] = res
    ok = out["old"] == out["new"]
    say("EQUIVALENT" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
