#!/usr/bin/env python3
"""Register names and static access candidates for the RL6449 firmware simulator (fw_sim.py, #38).
names(): XDATA address -> register name, from the SDK headers (tmp/sdcc-port/src; scaler regs are plain XDATA 0x0000..,
MCU regs 0xFE00..). candidates(img): addresses loaded with MOV DPTR,#imm16 that are followed (<= 6 B) by MOVX A,@DPTR
(read) or MOVX @DPTR,A (write): the registers the code touches by constant address. Computed addresses are not found."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "tmp/sdcc-port/src/Kernel/Scaler"

def _lens() -> list[int]:
    """MCS-51 instruction length by opcode."""
    L = [1] * 256
    for op in range(256):
        lo = op & 15
        if lo == 1:
            L[op] = 2                                              # AJMP / ACALL
        elif lo >= 8:
            L[op] = {0x78: 2, 0x88: 2, 0xA8: 2, 0xB8: 3, 0xD8: 2}.get(op & 0xF8, 1)   # Rn forms
        elif lo in (6, 7):
            L[op] = {0x76: 2, 0x86: 2, 0xA6: 2, 0xB6: 3}.get(op & 0xFE, 1)              # @Ri forms
        elif lo == 4:
            L[op] = 3 if op == 0xB4 else 2 if op in (0x24, 0x34, 0x44, 0x54, 0x64, 0x74, 0x94) else 1
        elif lo == 5:
            L[op] = 3 if op in (0x75, 0x85, 0xB5, 0xD5) else 1 if op == 0xA5 else 2
    for op in (0x43, 0x53, 0x63, 0x02, 0x12, 0x10, 0x20, 0x30, 0x90):
        L[op] = 3
    for op in (0x42, 0x52, 0x62, 0x72, 0x82, 0x92, 0xA2, 0xB2, 0xC2, 0xD2, 0x40, 0x50, 0x60, 0x70, 0x80, 0xA0, 0xB0, 0xC0,
               0xD0):
        L[op] = 2
    return L


LEN = _lens()


def names(root: Path = SDK) -> dict[int, str]:
    out: dict[int, str] = {}
    for f in (root / "RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h",
              root / "RL6449_Series_Scaler/Header/RL6449_Series_McuInterface.h"):
        if not f.exists():
            continue
        t = f.read_text(errors="replace")
        for m in re.finditer(r"#define\s+(P[0-9A-F]+_[0-9A-F]{2}_\w+)\s+0x([0-9A-Fa-f]{4})\b", t):
            out.setdefault(int(m.group(2), 16), m.group(1))
        for m in re.finditer(r"__at\(0x([0-9A-Fa-f]{4})\)\s+extern volatile BYTE xdata (\w+);", t):
            out.setdefault(int(m.group(1), 16), m.group(2))
    return out


def candidates(img: bytes, bank: int = 0x10000) -> tuple[set[int], set[int]]:
    """(read addrs, write addrs) from a linear sweep of every bank."""
    rd, wr = set(), set()
    for b in range(len(img) // bank):
        code = img[b * bank:(b + 1) * bank]
        i, n = 0, len(code)
        while i < n - 3:
            op = code[i]
            if op == 0x90:
                a = code[i + 1] << 8 | code[i + 2]
                j = i + 3
                for _ in range(3):                      # MOVX within a few instructions (inc dptr / mov a,.. between)
                    if j >= n:
                        break
                    if code[j] == 0xE0:
                        rd.add(a); break
                    if code[j] == 0xF0:
                        wr.add(a); break
                    j += LEN[code[j]]
            i += LEN[op]
    return rd, wr


def regdb_reset(chip: str = "RTD2795T-CG") -> dict[int, int]:
    """XDATA address -> reset value of every REG row in re/regdb/<chip>.tsv.gz (RL6449 = RTD2795T family; page << 8 | reg)."""
    import csv
    import gzip
    out: dict[int, int] = {}
    with gzip.open(ROOT / "re/regdb" / f"{chip}.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["kind"] == "REG" and r["reset"].startswith("0x") and r["address"].startswith("0x"):
                out[int(r["address"], 16)] = int(r["reset"], 16) & 0xFF
    return out
