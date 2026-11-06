/* Reference of the MulDiv / PowDiv semantics (see fw/asmlib/ScalerCommonComputeDwordMulDiv.asm header), ref_ prefix.
   Divisor 0 not supported here (stock SDCC % never returns); the driver checks it for the asm only. */
typedef unsigned char BYTE;
typedef unsigned int WORD;
typedef unsigned long DWORD;

DWORD ref_ScalerComputeDwordPowDiv(DWORD a, BYTE pow, DWORD b)
{
    DWORD r = 0;
    do {
        r <<= 1;
        if (a >= b) { r += a / b; a %= b; }
        a <<= 1;
    } while (pow-- != 0);
    return (a >= b) ? r + 1 : r;
}

DWORD ref_ScalerComputeDwordMulDiv(DWORD a, DWORD b, DWORD c)
{
    if (a == 0 || b == 0 || a < (0xFFFFFFFFUL / b))
        return a * b / c;
    {
        WORD x1 = a >> 16, x2 = (WORD)a, x3 = b >> 16, x4 = (WORD)b;
        DWORD p0 = (DWORD)x1 * x4, p1 = (DWORD)x2 * x3, lo = (DWORD)x2 * x4, hi = (DWORD)x1 * x3;
        DWORD buf = (DWORD)(WORD)p0 + (WORD)p1 + (WORD)(lo >> 16);
        lo = ((DWORD)(WORD)buf << 16) | (WORD)lo;
        hi += (DWORD)(WORD)(p0 >> 16) + (WORD)(p1 >> 16) + (WORD)(buf >> 16);
        return ref_ScalerComputeDwordPowDiv(hi, 32, c) + ref_ScalerComputeDwordPowDiv(lo, 0, c);
    }
}
