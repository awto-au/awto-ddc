#!/usr/bin/env python3
"""Minimal linear 8051 disassembler for a flash dump / bank file (static analysis helper).

usage: dis51.py <file> <start-hex> <len-hex> [--base <hex>]   -> stdout (redirect to ./tmp/logs/dis51.log if long)
       dis51.py <file> --find-dptr <hex16> [--base <hex>]      -> offsets of MOV DPTR,#imm16
Linear sweep only; data in code will decode as garbage.
"""
import sys

R = ["R%d" % i for i in range(8)]
# (mnemonic template, length); operand kinds: d=direct, i=imm8, I=imm16, r=rel8, a=addr16, b=bit
T = {}
def op(code, fmt, n): T[code] = (fmt, n)
for i in range(8):
    op(0x08+i, f"INC R{i}", 1); op(0x18+i, f"DEC R{i}", 1)
    op(0x28+i, f"ADD A,R{i}", 1); op(0x38+i, f"ADDC A,R{i}", 1); op(0x48+i, f"ORL A,R{i}", 1)
    op(0x58+i, f"ANL A,R{i}", 1); op(0x68+i, f"XRL A,R{i}", 1); op(0x78+i, f"MOV R{i},#i", 2)
    op(0x88+i, f"MOV d,R{i}", 2); op(0x98+i, f"SUBB A,R{i}", 1); op(0xA8+i, f"MOV R{i},d", 2)
    op(0xB8+i, f"CJNE R{i},#i,r", 3); op(0xC8+i, f"XCH A,R{i}", 1); op(0xD8+i, f"DJNZ R{i},r", 2)
    op(0xE8+i, f"MOV A,R{i}", 1); op(0xF8+i, f"MOV R{i},A", 1)
for i in range(2):
    op(0x06+i, f"INC @R{i}", 1); op(0x16+i, f"DEC @R{i}", 1); op(0x26+i, f"ADD A,@R{i}", 1)
    op(0x36+i, f"ADDC A,@R{i}", 1); op(0x46+i, f"ORL A,@R{i}", 1); op(0x56+i, f"ANL A,@R{i}", 1)
    op(0x66+i, f"XRL A,@R{i}", 1); op(0x76+i, f"MOV @R{i},#i", 2); op(0x86+i, f"MOV d,@R{i}", 2)
    op(0x96+i, f"SUBB A,@R{i}", 1); op(0xA6+i, f"MOV @R{i},d", 2); op(0xB6+i, f"CJNE @R{i},#i,r", 3)
    op(0xC6+i, f"XCH A,@R{i}", 1); op(0xD6+i, f"XCHD A,@R{i}", 1); op(0xE2+i, f"MOVX A,@R{i}", 1)
    op(0xE6+i, f"MOV A,@R{i}", 1); op(0xF2+i, f"MOVX @R{i},A", 1); op(0xF6+i, f"MOV @R{i},A", 1)
for c, f, n in [(0x00,"NOP",1),(0x02,"LJMP a",3),(0x03,"RR A",1),(0x04,"INC A",1),(0x05,"INC d",2),(0x10,"JBC b,r",3),
 (0x12,"LCALL a",3),(0x13,"RRC A",1),(0x14,"DEC A",1),(0x15,"DEC d",2),(0x20,"JB b,r",3),(0x22,"RET",1),(0x23,"RL A",1),
 (0x24,"ADD A,#i",2),(0x25,"ADD A,d",2),(0x30,"JNB b,r",3),(0x32,"RETI",1),(0x33,"RLC A",1),(0x34,"ADDC A,#i",2),
 (0x35,"ADDC A,d",2),(0x40,"JC r",2),(0x42,"ORL d,A",2),(0x43,"ORL d,#i",3),(0x44,"ORL A,#i",2),(0x45,"ORL A,d",2),
 (0x50,"JNC r",2),(0x52,"ANL d,A",2),(0x53,"ANL d,#i",3),(0x54,"ANL A,#i",2),(0x55,"ANL A,d",2),(0x60,"JZ r",2),
 (0x62,"XRL d,A",2),(0x63,"XRL d,#i",3),(0x64,"XRL A,#i",2),(0x65,"XRL A,d",2),(0x70,"JNZ r",2),(0x72,"ORL C,b",2),
 (0x73,"JMP @A+DPTR",1),(0x74,"MOV A,#i",2),(0x75,"MOV d,#i",3),(0x80,"SJMP r",2),(0x82,"ANL C,b",2),
 (0x83,"MOVC A,@A+PC",1),(0x84,"DIV AB",1),(0x85,"MOV d2,d",3),(0x90,"MOV DPTR,#I",3),(0x92,"MOV b,C",2),
 (0x93,"MOVC A,@A+DPTR",1),(0x94,"SUBB A,#i",2),(0x95,"SUBB A,d",2),(0xA0,"ORL C,/b",2),(0xA2,"MOV C,b",2),
 (0xA3,"INC DPTR",1),(0xA4,"MUL AB",1),(0xA5,"DB 0A5h",1),(0xB0,"ANL C,/b",2),(0xB2,"CPL b",2),(0xB3,"CPL C",1),
 (0xB4,"CJNE A,#i,r",3),(0xB5,"CJNE A,d,r",3),(0xC0,"PUSH d",2),(0xC2,"CLR b",2),(0xC3,"CLR C",1),(0xC4,"SWAP A",1),
 (0xC5,"XCH A,d",2),(0xD0,"POP d",2),(0xD2,"SETB b",2),(0xD3,"SETB C",1),(0xD4,"DA A",1),(0xD5,"DJNZ d,r",3),
 (0xE0,"MOVX A,@DPTR",1),(0xE4,"CLR A",1),(0xE5,"MOV A,d",2),(0xF0,"MOVX @DPTR,A",1),(0xF4,"CPL A",1),
 (0xF5,"MOV d,A",2)]:
    op(c, f, n)
for p in range(8):
    op(0x01+p*0x20, "AJMP p", 2); op(0x11+p*0x20, "ACALL p", 2)
op(0x42,"ORL d,A",2)


def dis(buf, pc, base=0):
    code = buf[pc]
    f, n = T[code]
    b = buf[pc:pc+n]
    a = base + pc
    if f.startswith(("AJMP", "ACALL")):
        tgt = ((a + 2) & 0xF800) | ((code >> 5) << 8) | b[1]
        return f"{f.split()[0]} {tgt:04X}", n
    out = f
    # operand substitution in order of appearance
    vals = list(b[1:])
    if f.startswith("MOV d2,d"):          # MOV dst,src : encoded src then dst
        return f"MOV {vals[1]:02X}h,{vals[0]:02X}h", n
    res, k, i = "", 0, 0
    while i < len(out):
        c = out[i]
        nxt = out[i+1] if i+1 < len(out) else ""
        if c in "di" and (i == 0 or out[i-1] in " ,#@/") and not nxt.isalpha() and not (c == "d" and False):
            if c == "i" and i > 0 and out[i-1] == "#" or c == "d" and (i == 0 or out[i-1] in " ,"):
                res += f"{vals[k]:02X}h" if c == "d" else f"{vals[k]:02X}h"; k += 1; i += 1; continue
        if c == "I" and out[i-1] == "#":
            res += f"{(vals[k] << 8 | vals[k+1]):04X}h"; k += 2; i += 1; continue
        if c == "a" and out[i-1] == " ":
            res += f"{(vals[0] << 8 | vals[1]):04X}"; k += 2; i += 1; continue
        if c == "r" and out[i-1] == ",":
            r = vals[k] - 256 if vals[k] > 127 else vals[k]; res += f"{(a + n + r) & 0xFFFF:04X}"; k += 1; i += 1; continue
        if c == "r" and out[i-1] == " ":
            r = vals[k] - 256 if vals[k] > 127 else vals[k]; res += f"{(a + n + r) & 0xFFFF:04X}"; k += 1; i += 1; continue
        if c == "b" and out[i-1] in " ,/":
            res += f"bit{vals[k]:02X}h"; k += 1; i += 1; continue
        res += c; i += 1
    return res, n


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 2
    buf = open(sys.argv[1], "rb").read()
    base = int(sys.argv[sys.argv.index("--base")+1], 16) if "--base" in sys.argv else 0
    if sys.argv[2] == "--find-dptr":
        v = int(sys.argv[3], 16)
        pat = bytes([0x90, v >> 8, v & 255])
        i = buf.find(pat)
        while i >= 0:
            print(f"{base+i:06X}"); i = buf.find(pat, i+1)
        return 0
    start, ln = int(sys.argv[2], 16), int(sys.argv[3], 16)
    pc = start
    while pc < start + ln and pc < len(buf):
        try:
            s, n = dis(buf, pc, base)
        except Exception:
            s, n = "??", 1
        print(f"{base+pc:06X}: {buf[pc:pc+n].hex():8s} {s}")
        pc += n
    return 0


if __name__ == "__main__":
    sys.exit(main())
