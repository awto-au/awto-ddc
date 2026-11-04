/* function-pointer table; one table entry calls other functions; callbacks have locals */
#include "sim.h"
volatile unsigned char seed = 2;

unsigned int helper(unsigned int v)
{
    unsigned int t[4]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 4; i++) t[i] = v + i * 5;
    for (i = 0; i < 4; i++) s ^= t[i] * 3;
    return s;
}
unsigned int cb_a(unsigned int v)
{
    unsigned int a = v * 2, b = v + 17;
    return a + helper(b) + b;
}
unsigned int cb_b(unsigned int v)
{
    unsigned char buf[9]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 9; i++) buf[i] = v + i;
    for (i = 0; i < 9; i++) s += buf[i];
    return s;
}
unsigned int cb_c(unsigned int v)     /* table fn calling another table fn + helper */
{
    unsigned int keep = v ^ 0x55AA, r;
    r = cb_b(v + 1);
    r += helper(keep);
    return r + keep;
}
typedef unsigned int (*cb_t)(unsigned int);
static const cb_t table[3] = { cb_a, cb_b, cb_c };

unsigned int dispatch(unsigned char idx, unsigned int v)
{
    unsigned int pre = v * 3, r;
    r = table[idx](v);
    return r + pre;
}
void main(void)
{
    unsigned char i; unsigned long sum = 0; cb_t direct = cb_a;
    for (i = 0; i < 3; i++) { sum += dispatch(i, 100 + i + seed); sim_val("disp", sum); }
    sum += direct(7); sim_val("direct", sum);
    sim_done();
}
