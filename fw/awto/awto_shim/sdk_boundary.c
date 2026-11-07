/* SDK <-> clean boundary (integrator-owned, private; never enters awto-rtdfw). docs/cleanroom.md, awto-ddc#68.
 * One block per module; each block is deleted with the module's rules.py at step 15.
 * Compiled with the project flags + clean awto/include + awto/<mod>; skipped when the clean tree has no sources. */

#ifdef _AWTO_NEW_ARITH            /* set by keil2sdcc for every clean module directory */
#include "arith.h"

/* arith: FunctionLib ScalerCommonComputeDwordMulDiv.c defines both; defining them here drops that module from the link. */
unsigned long ScalerComputeDwordMulDiv(unsigned long a, unsigned long b, unsigned long c)
{
    return ar_muldiv(a, b, c);
}

/* (a * 2^pow) / b, rounded half up = ar_shldiv(a, pow, b) */
unsigned long ScalerComputeDwordPowDiv(unsigned long a, unsigned char pow, unsigned long b)
{
    return ar_shldiv(a, pow, b);
}
#endif
