/* Clean-room C reference of the data-port helper semantics (spec: register access order), ref_ prefix. */
typedef unsigned char BYTE;
typedef unsigned int WORD;
#define R(a) (*(volatile BYTE __xdata *)(WORD)(a))

void ref_ScalerSetDataPortByte(WORD a, BYTE v1, BYTE v2)
{
    R(a) = v1;
    R(a + 1) = v2;
}

/* bAutoInc == 0 -> index auto-increments (Realtek _AUTOINC = 0) */
void ref_ScalerGetDataPortByte(WORD a, BYTE v, WORD len, BYTE *p, __bit nonauto)
{
    WORD i;
    if (len) {
        for (i = 0; i < len; i++) {
            R(a) = nonauto ? v : (BYTE)(v + i);
            p[i] = R(a + 1);
        }
    }
}

void ref_ScalerSetDataPortBit(WORD a, BYTE v, BYTE and, BYTE or)
{
    BYTE t;
    R(a) = v;
    t = R(a + 1);
    t = (t & and) | or;
    R(a) = v;
    R(a + 1) = t;
}

BYTE ref_ScalerGetDataPortBit(WORD a, BYTE v, BYTE and)
{
    R(a) = v;
    return R(a + 1) & and;
}
