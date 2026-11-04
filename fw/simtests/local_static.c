/* probe: function-local statics (persist across calls) share the _fn_name_N label shape of autos */
#include "sim.h"
volatile unsigned char seed = 1;

unsigned int counter(unsigned char step)
{
    static unsigned int total;
    static unsigned char calls = 3;
    total += step;
    calls++;
    return total + calls;
}
unsigned int other(unsigned char x)
{
    unsigned char t[6]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 6; i++) t[i] = x + i;
    for (i = 0; i < 6; i++) s += t[i];
    return s;
}
void main(void)
{
    unsigned int r = 0; unsigned char i;
    for (i = 0; i < 4; i++) { r += counter(seed + i); r += other(i); }
    sim_val("r", r);
    sim_val("c", counter(0));
    sim_done();
}
