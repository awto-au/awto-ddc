#include "bk.h"
WORD f2(WORD a, WORD b) { return a * 3 + b; }
WORD f3(WORD a, WORD b, WORD c) { return a * 3 + b * 5 + c * 7; }
BYTE fb(BYTE a, BYTE b, BYTE c) { return a * 9 + b * 3 + c; }
DWORD fl(DWORD a, WORD b) { return a + b; }
__bit fbit(WORD a, WORD b) { return a > b; }
WORD chain1(WORD a, WORD b, WORD c)
{
    WORD t = g3(c, a, b);              /* a, b, c live across the crossing */
    WORD u = back(b, c, a);
    return t + u + f3(a, b, c);
}
WORD gsum(const BYTE *p, WORD n)
{
    WORD s = 0;
    while (n--)
        s += *p++;
    return s;
}
BYTE gpick(BYTE a, WORD b, const BYTE *p) { return p[a] + (BYTE)b; }
BYTE gp2(BYTE a, const BYTE *p, BYTE c) { return p[a] * 2 + c; }
DWORD lmix(DWORD a, BYTE b, BYTE c) { return a * 3 + b + c; }
float fmul(float a, WORD n) { return a * n; }
signed char scr(signed char a, signed char b) { return a - b; }
