/* big local arrays + many 32-bit temporaries (forces XSEG locals and DSEG sloc spills) */
#include "sim.h"
volatile unsigned char seed = 1;

unsigned long mix(unsigned long a, unsigned long b)
{
    unsigned long x = a * b + (a >> 3) + (b << 5);
    unsigned long y = (a ^ b) * 3 + (x >> 7);
    return x + y * (a | 1);
}
unsigned long inner(unsigned char n)
{
    unsigned char arr[64]; unsigned char i; unsigned long s = 0;
    for (i = 0; i < 64; i++) arr[i] = (unsigned char)(i * n + seed);
    for (i = 0; i < 64; i++) s = mix(s, arr[i]);
    return s;
}
unsigned long outer(unsigned char n)
{
    unsigned int wide[40]; unsigned char i;
    unsigned long a = n, b = n * 3UL, c = n * 5UL, d = n * 7UL, e = n * 11UL, s;
    for (i = 0; i < 40; i++) wide[i] = (unsigned int)(a * i + b);
    s = inner(n + 1);
    for (i = 0; i < 40; i++) s += wide[i];
    return mix(s, a + b + c) ^ mix(d, e);
}
void main(void)
{
    unsigned char n; unsigned long sum = 0;
    for (n = 1; n <= 4; n++) { sum += outer(n); sim_val("outer", sum); }
    sim_done();
}
