/* Clean-room reference of ScalerRead semantics (Realtek _AUTOINC = 0), ref_ prefix. */
typedef unsigned char BYTE;
typedef unsigned int WORD;

void ref_ScalerRead(WORD a, WORD len, BYTE *p, __bit nonauto)
{
    WORD i;
    for (i = 0; i < len; i++)
        p[i] = *(volatile BYTE __xdata *)(nonauto ? a : (WORD)(a + i));
}
