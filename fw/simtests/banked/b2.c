#include "bk.h"
WORD g2(WORD a, WORD b) { return a * 5 + b; }
WORD g3(WORD a, WORD b, WORD c) { return a * 11 + b * 13 + c * 17; }
WORD back(WORD a, WORD b, WORD c) { return f3(c, b, a) + f2(a, c); }
DWORD lsum3(WORD a, WORD b, WORD c) { return (DWORD)a * 65536UL + b + c; }
static const BYTE __code ctab[4] = {10, 20, 30, 40};
static BYTE __xdata xtab[4] = {1, 2, 3, 4};
static BYTE __data dvar;
const BYTE *gret(BYTE which)
{
    const BYTE *p;
    if (which == 0) p = ctab;
    else if (which == 1) p = xtab;
    else p = &dvar;
    return p;
}
BYTE __xdata *xret(void) { return xtab; }
BYTE __data *dret(void) { return &dvar; }
float fret(WORD n) { return n * 0.5f; }
char cret(char a) { return a + 1; }
void vset(BYTE v) { dvar = v; }
BYTE vget(void) { return dvar; }
WORD gnest(const BYTE *p, WORD n, BYTE k) { return gsum(p, n) + k; }
