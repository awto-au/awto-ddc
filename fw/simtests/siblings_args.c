/* calls inside argument lists: f(a, g(x), h(y)); g/h have params + locals (PARM overlay question) */
#include "sim.h"
volatile unsigned char seed = 5;

unsigned int g(unsigned int p, unsigned char q, unsigned long r)
{
    unsigned int loc[3]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 3; i++) loc[i] = p + q * i + (unsigned int)r;
    for (i = 0; i < 3; i++) s += loc[i];
    return s;
}
unsigned int h(unsigned int p, unsigned char q, unsigned long r)
{
    unsigned int loc[3]; unsigned char i; unsigned int s = 1;
    for (i = 0; i < 3; i++) loc[i] = (p ^ q) + r + i;
    for (i = 0; i < 3; i++) s ^= loc[i] << i;
    return s;
}
unsigned int f(unsigned int a, unsigned int b, unsigned int c, unsigned long d, unsigned char e)
{
    unsigned int mine[4]; unsigned char i; unsigned int s = a + e;
    for (i = 0; i < 4; i++) mine[i] = b + c + i;
    for (i = 0; i < 4; i++) s += mine[i];
    return s + (unsigned int)d;
}
void main(void)
{
    unsigned char x = seed, y = seed + 1;
    unsigned int r;
    r = f(1000 + x, g(x, y, 70000UL), h(y, x, 123456UL), 99UL, g(1, 2, 3UL) & 0xFF);
    sim_val("f1", r);
    r = f(g(1, 2, 3UL), g(4, 5, 6UL), g(7, 8, 9UL), h(1, 2, 3UL), h(4, 5, 6UL) & 0xFF);
    sim_val("f2", r);
    r = g(h(x, y, 1UL), g(y, x, 2UL), h(g(1, 1, 1UL), 2, 3UL));
    sim_val("f3", r);
    sim_done();
}
