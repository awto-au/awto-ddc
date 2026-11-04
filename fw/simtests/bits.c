/* __bit params + bit locals live across nested calls; bit args computed by nested calls (BSEG overlay) */
#include "sim.h"
volatile unsigned char seed = 6;
__bit g_flag;

unsigned char leafb(__bit a, __bit b, unsigned char x)
{
    __bit t = a ^ b;
    __bit u = (x & 1);
    return (t ? 3 : 1) + (u ? 10 : 20) + x;
}
__bit pick(unsigned char x)
{
    __bit q = (x & 2);
    return q ^ g_flag;
}
unsigned int midb(__bit en, unsigned char x)
{
    __bit keep = !en;
    __bit k2 = (x & 4);
    unsigned int r = leafb(pick(x), pick(x + 1), x);
    r += leafb(keep, k2, x + 2);
    r += (keep ? 100 : 0) + (k2 ? 1000 : 0) + (en ? 7 : 0);
    return r;
}
void main(void)
{
    unsigned long s = 0; unsigned char i;
    for (i = 0; i < 12; i++) {
        g_flag = (i & 1);
        s += midb(pick(i + seed), i + seed);
        sim_val("bits", s);
    }
    sim_done();
}
