#!/usr/bin/env python3
"""Clean 8051 disassembler (module + CLI), annotates MOV DPTR,#imm with regdb register names.

  from d8051 import disasm, load_regnames
  for ins in disasm(code_bytes, base=0x1234, names=load_regnames(), reloc={offsets}): ...
Insn fields: addr, off, n, raw, text, target (branch/call dest or None), dptr (imm16 or None),
reloc (True if any byte is a link-time fixup site), note (register name for DPTR, else "").
CLI: d8051.py <file> <start-hex> <len-hex> [--base 0xNNNN]   (linear sweep; data decodes as garbage)
Scaler registers are XDATA at (page<<8)|reg; names from re/regdb/RTD2795T-CG.tsv.gz.
"""
import csv, gzip, os, sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)

SFR = {0x80: "P0", 0x81: "SP", 0x82: "DPL", 0x83: "DPH", 0x87: "PCON", 0x88: "TCON", 0x89: "TMOD", 0x8A: "TL0",
       0x8B: "TL1", 0x8C: "TH0", 0x8D: "TH1", 0x90: "P1", 0x98: "SCON", 0x99: "SBUF", 0xA0: "P2", 0xA8: "IE",
       0xB0: "P3", 0xB8: "IP", 0xD0: "PSW", 0xE0: "ACC", 0xF0: "B"}

# opcodes whose low nibble is not the generic operand column: (text template, length)
# tokens: {d} direct  {i} imm8  {I} imm16  {r} rel8  {a} addr16  {b} bit  {d2} second direct (MOV d,d)
_FIXED = {
    0x00: ("NOP", 1), 0x02: ("LJMP {a}", 3), 0x03: ("RR A", 1), 0x04: ("INC A", 1), 0x05: ("INC {d}", 2),
    0x10: ("JBC {b},{r}", 3), 0x12: ("LCALL {a}", 3), 0x13: ("RRC A", 1), 0x14: ("DEC A", 1), 0x15: ("DEC {d}", 2),
    0x20: ("JB {b},{r}", 3), 0x22: ("RET", 1), 0x23: ("RL A", 1), 0x24: ("ADD A,#{i}", 2), 0x25: ("ADD A,{d}", 2),
    0x30: ("JNB {b},{r}", 3), 0x32: ("RETI", 1), 0x33: ("RLC A", 1), 0x34: ("ADDC A,#{i}", 2), 0x35: ("ADDC A,{d}", 2),
    0x40: ("JC {r}", 2), 0x42: ("ORL {d},A", 2), 0x43: ("ORL {d},#{i}", 3), 0x44: ("ORL A,#{i}", 2), 0x45: ("ORL A,{d}", 2),
    0x50: ("JNC {r}", 2), 0x52: ("ANL {d},A", 2), 0x53: ("ANL {d},#{i}", 3), 0x54: ("ANL A,#{i}", 2), 0x55: ("ANL A,{d}", 2),
    0x60: ("JZ {r}", 2), 0x62: ("XRL {d},A", 2), 0x63: ("XRL {d},#{i}", 3), 0x64: ("XRL A,#{i}", 2), 0x65: ("XRL A,{d}", 2),
    0x70: ("JNZ {r}", 2), 0x72: ("ORL C,{b}", 2), 0x73: ("JMP @A+DPTR", 1), 0x74: ("MOV A,#{i}", 2), 0x75: ("MOV {d},#{i}", 3),
    0x80: ("SJMP {r}", 2), 0x82: ("ANL C,{b}", 2), 0x83: ("MOVC A,@A+PC", 1), 0x84: ("DIV AB", 1), 0x85: ("MOV {d2},{d}", 3),
    0x90: ("MOV DPTR,#{I}", 3), 0x92: ("MOV {b},C", 2), 0x93: ("MOVC A,@A+DPTR", 1), 0x94: ("SUBB A,#{i}", 2), 0x95: ("SUBB A,{d}", 2),
    0xA0: ("ORL C,/{b}", 2), 0xA2: ("MOV C,{b}", 2), 0xA3: ("INC DPTR", 1), 0xA4: ("MUL AB", 1), 0xA5: ("DB 0A5h", 1),
    0xB0: ("ANL C,/{b}", 2), 0xB2: ("CPL {b}", 2), 0xB3: ("CPL C", 1), 0xB4: ("CJNE A,#{i},{r}", 3), 0xB5: ("CJNE A,{d},{r}", 3),
    0xC0: ("PUSH {d}", 2), 0xC2: ("CLR {b}", 2), 0xC3: ("CLR C", 1), 0xC4: ("SWAP A", 1), 0xC5: ("XCH A,{d}", 2),
    0xD0: ("POP {d}", 2), 0xD2: ("SETB {b}", 2), 0xD3: ("SETB C", 1), 0xD4: ("DA A", 1), 0xD5: ("DJNZ {d},{r}", 3),
    0xE0: ("MOVX A,@DPTR", 1), 0xE4: ("CLR A", 1), 0xE5: ("MOV A,{d}", 2),
    0xF0: ("MOVX @DPTR,A", 1), 0xF4: ("CPL A", 1), 0xF5: ("MOV {d},A", 2),
    0xE2: ("MOVX A,@R0", 1), 0xE3: ("MOVX A,@R1", 1), 0xF2: ("MOVX @R0,A", 1), 0xF3: ("MOVX @R1,A", 1),
}
# row (high nibble) -> template with {x} = Rn / @Ri operand, for low nibbles 6-F (not in _FIXED)
_ROW = {0x0: ("INC {x}", 1), 0x1: ("DEC {x}", 1), 0x2: ("ADD A,{x}", 1), 0x3: ("ADDC A,{x}", 1), 0x4: ("ORL A,{x}", 1),
        0x5: ("ANL A,{x}", 1), 0x6: ("XRL A,{x}", 1), 0x7: ("MOV {x},#{i}", 2), 0x8: ("MOV {d},{x}", 2),
        0x9: ("SUBB A,{x}", 1), 0xA: ("MOV {x},{d}", 2), 0xB: ("CJNE {x},#{i},{r}", 3), 0xC: ("XCH A,{x}", 1),
        0xD: ("DJNZ {x},{r}", 2), 0xE: ("MOV A,{x}", 1), 0xF: ("MOV {x},A", 1)}


def _table():
    t = dict(_FIXED)
    for p in range(8):
        t[0x01 + p * 0x20] = ("AJMP {p}", 2); t[0x11 + p * 0x20] = ("ACALL {p}", 2)
    for op in range(256):
        if op in t:
            continue
        lo, hi = op & 15, op >> 4
        if lo in (6, 7) or lo >= 8:
            x = f"@R{lo - 6}" if lo < 8 else f"R{lo - 8}"
            fmt, n = _ROW[hi]
            if hi == 0xD and lo < 8:   # D6/D7 are XCHD
                fmt, n = "XCHD A,{x}", 1
            t[op] = (fmt.replace("{x}", x), n)
    # lengths: recompute from the placeholders so the row table stays declarative
    for op, (fmt, n) in list(t.items()):
        if op in _FIXED:
            continue
        t[op] = (fmt, 1 + sum(fmt.count(k) for k in ("{i}", "{d}", "{r}", "{p}")))
    return t


_T = _table()


@dataclass
class Insn:
    addr: int
    off: int
    n: int
    raw: bytes
    text: str
    target: int = None
    dptr: int = None
    reloc: bool = False
    note: str = ""


def _dir(v):
    return SFR.get(v, f"{v:02X}h") if v >= 0x80 else f"{v:02X}h"


def _bit(v):
    if v < 0x80:
        return f"{0x20 + (v >> 3):02X}h.{v & 7}"
    return f"{SFR.get(v & 0xF8, f'{v & 0xF8:02X}h')}.{v & 7}"


def decode(code, off, base=0):
    op = code[off]
    fmt, n = _T[op]
    b = code[off:off + n]
    if len(b) < n:
        return Insn(base + off, off, len(b), bytes(b), "DB " + ",".join(f"{x:02X}h" for x in b))
    a = base + off
    tgt = dptr = None
    vals = list(b[1:])
    k = 0
    out = fmt
    if "{p}" in out:
        tgt = ((a + 2) & 0xF800) | ((op >> 5) << 8) | b[1]
        out = out.replace("{p}", f"{tgt:04X}h")
    # operand order of appearance in the encoding: MOV d2,d is encoded src,dst
    if "{d2}" in out:
        out = out.replace("{d2}", _dir(vals[1])).replace("{d}", _dir(vals[0])); k = 2
    else:
        while True:
            i = min((out.find(t) for t in ("{i}", "{I}", "{d}", "{a}", "{b}", "{r}") if t in out), default=-1)
            if i < 0:
                break
            t = out[i:i + 3]
            if t == "{i}":
                s = f"{vals[k]:02X}h"; k += 1
            elif t == "{I}":
                dptr = vals[k] << 8 | vals[k + 1]; s = f"{dptr:04X}h"; k += 2
            elif t == "{d}":
                s = _dir(vals[k]); k += 1
            elif t == "{a}":
                tgt = vals[k] << 8 | vals[k + 1]; s = f"{tgt:04X}h"; k += 2
            elif t == "{b}":
                s = _bit(vals[k]); k += 1
            else:
                r = vals[k] - 256 if vals[k] > 127 else vals[k]; k += 1
                tgt = (a + n + r) & 0xFFFF; s = f"{tgt:04X}h"
            out = out[:i] + s + out[i + 3:]
    return Insn(a, off, n, bytes(b), out, tgt, dptr)


def disasm(code, base=0, names=None, reloc=frozenset(), start=0, end=None):
    off, end = start, len(code) if end is None else end
    while off < end:
        ins = decode(code, off, base)
        ins.reloc = any((off + j) in reloc for j in range(ins.n))
        if ins.dptr is not None and names and not ins.reloc:
            ins.note = names.get(ins.dptr, "")
        yield ins
        off += ins.n


def load_regnames(chip="RTD2795T-CG"):
    """{xdata addr: REGNAME} from the regdb REG rows (page<<8|reg)."""
    names = {}
    for d in (REPO / "re/regdb", Path.home() / "vendors/realtek/analysis/regdb"):
        p = d / f"{chip}.tsv.gz"
        if p.exists():
            for r in csv.DictReader(gzip.open(p, "rt", newline=""), delimiter="\t"):
                if r["kind"] == "REG":
                    names[int(r["address"], 16)] = r["register"]
            return names
    return names


def main():
    if len(sys.argv) < 4:
        print(__doc__); return 2
    buf = open(sys.argv[1], "rb").read()
    base = int(sys.argv[sys.argv.index("--base") + 1], 16) if "--base" in sys.argv else 0
    s, ln = int(sys.argv[2], 16), int(sys.argv[3], 16)
    for i in disasm(buf, base, load_regnames(), start=s, end=min(len(buf), s + ln)):
        print(f"{i.addr:04X}: {i.raw.hex():8s} {i.text}" + (f"   ; {i.note}" if i.note else ""))


if __name__ == "__main__":
    sys.exit(main())
