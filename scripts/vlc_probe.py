#!/usr/bin/env python3
"""Decode a Realtek OSD VLC stream (4 bit/symbol, codes from regdb page 3A 0x0F-0x16) to nibbles (static analysis).

usage: vlc_probe.py <dump> <start-hex> <nbytes-hex> [--map identity|rev] -> prints glyph streams split at END (1111_1111)
Code table [spec from regdb]: 0,100,1010,1011,1100,11010,11011,11100,111010,111011,111100,111101,1111100,1111101,1111110,11111110; END=11111111.
Symbol value for each code is programmable (vlc_0..vlc_f); the identity map here is a guess [?].
"""
import sys
CODES = ["0","100","1010","1011","1100","11010","11011","11100","111010","111011","111100","111101","1111100","1111101","1111110","11111110"]
DEC = {c: i for i, c in enumerate(CODES)}

def decode(buf):
    bits = "".join(f"{b:08b}" for b in buf)
    out, cur, i = [], [], 0
    code = ""
    for ch in bits:
        code += ch
        if code == "11111111":
            out.append(cur); cur = []; code = ""
        elif code in DEC:
            cur.append(DEC[code]); code = ""
    if cur: out.append(cur)
    return out

if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    s, n = int(sys.argv[2], 16), int(sys.argv[3], 16)
    for k, g in enumerate(decode(d[s:s+n])):
        print(k, len(g), "".join("%x" % v for v in g))
