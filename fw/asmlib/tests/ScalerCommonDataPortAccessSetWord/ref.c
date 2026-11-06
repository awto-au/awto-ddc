/* Clean-room reference of ScalerSetDataPortWord semantics, ref_ prefix. */
typedef unsigned char BYTE;
typedef unsigned int WORD;
#define R(a) (*(volatile BYTE __xdata *)(WORD)(a))

void ref_ScalerSetDataPortWord(WORD a, BYTE v1, WORD v2)
{
    R(a) = v1;
    R(a + 1) = (BYTE)(v2 >> 8);
    R(a) = (BYTE)(v1 + 1);
    R(a + 1) = (BYTE)v2;
}
