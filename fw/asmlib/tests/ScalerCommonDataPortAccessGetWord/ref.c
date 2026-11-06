/* Clean-room reference of ScalerGetDataPortWord semantics (Realtek _AUTOINC = 0), ref_ prefix. */
typedef unsigned char BYTE;
typedef unsigned int WORD;
#define R(a) (*(volatile BYTE __xdata *)(WORD)(a))

WORD ref_ScalerGetDataPortWord(WORD a, BYTE v, __bit nonauto)
{
    BYTE hi, lo;
    R(a) = v;
    hi = R(a + 1);
    R(a) = nonauto ? v : (BYTE)(v + 1);
    lo = R(a + 1);
    return ((WORD)hi << 8) | lo;
}
