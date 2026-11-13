/* % and / written as C operators (compiler-generated helper calls) through fw/sdcc/crt_mod0.c (%) and the library (/) at the
 * current AWTO_SDCCCALL level (0/1/2): unsigned + signed 16/32-bit, * too (library), edge cases, divisor 0, constant divisors.
 * Vectors: scripts/crt_ops_vec.py -> vec.h. Self-checking: bad != 0 hangs before the sentinel (harness: TIMEOUT). Operands volatile. */
#include "sim.h"
#include "vec.h"

volatile unsigned long va, vb;
volatile unsigned int ua, ub;
volatile long sa, sb;
volatile int ia, ib;

void main(void)
{
    unsigned int i, bad = 0;
    for (i = 0; i < sizeof V32 / sizeof V32[0]; i++) {
        va = V32[i].a; vb = V32[i].b; sa = (long)V32[i].a; sb = (long)V32[i].b;
        if (va * vb != V32[i].mul) { bad++; sim_val("m32", i); }
        if (va / vb != V32[i].divu) { bad++; sim_val("d32", i); }
        if (va % vb != V32[i].modu) { bad++; sim_val("r32", i); }
        if ((unsigned long)(sa / sb) != V32[i].divs) { bad++; sim_val("sd32", i); }
        if ((unsigned long)(sa % sb) != V32[i].mods) { bad++; sim_val("sr32", i); }
    }
    for (i = 0; i < sizeof V16 / sizeof V16[0]; i++) {
        ua = V16[i].a; ub = V16[i].b; ia = (int)V16[i].a; ib = (int)V16[i].b;
        if ((unsigned int)(ua * ub) != V16[i].mul) { bad++; sim_val("m16", i); }
        if (ua / ub != V16[i].divu) { bad++; sim_val("d16", i); }
        if (ua % ub != V16[i].modu) { bad++; sim_val("r16", i); }
        if ((unsigned int)(ia / ib) != V16[i].divs) { bad++; sim_val("sd16", i); }
        if ((unsigned int)(ia % ib) != V16[i].mods) { bad++; sim_val("sr16", i); }
    }
    /* divisor 0: x % 0 = x (SDK hits it after a failed eDP link), x / 0 = all ones (library behaviour) */
    va = 0xDEADBEEFUL; vb = 0; ua = 0xBEEF; ub = 0;
    if (va % vb != 0xDEADBEEFUL || ua % ub != 0xBEEF) bad++;
    if (va / vb != 0xFFFFFFFFUL || ua / ub != 0xFFFF) bad++;
    va = 0x1234UL; ua = 0x56;
    if (va % vb != 0x1234UL || ua % ub != 0x56 || va / vb != 0xFFFFFFFFUL || ua / ub != 0xFFFF) bad++;
    /* constant divisors */
    va = 0xFFFFFFFFUL; ua = 0xFFFF;
    if (va % 10UL != 5 || va / 1000UL != 0x00418937UL || ua % 10U != 5 || ua / 1000U != 65) bad++;
    sim_val("bad", bad);
    sim_val("n", sizeof V32 / sizeof V32[0] + sizeof V16 / sizeof V16[0]);
    if (bad) for (;;) ;
    sim_done();
}
