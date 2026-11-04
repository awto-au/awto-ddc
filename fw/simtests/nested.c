/* deep call chain; each level keeps locals + an array live across the callee */
#include "sim.h"
volatile unsigned char seed = 3;

unsigned int lvl4(unsigned char x)
{
    unsigned char t[6]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 6; i++) t[i] = x * (i + 1) + seed;
    for (i = 0; i < 6; i++) s += t[i];
    return s;
}
unsigned int lvl3(unsigned char x)
{
    unsigned int a = x * 7 + seed, b = 0x1234 ^ x, c;
    unsigned char k[4] = {1, 2, 3, 4};
    c = lvl4(x + 1);
    return a + b + c + k[0] + k[3];
}
unsigned int lvl2(unsigned char x)
{
    unsigned long big = 0x01020304UL * x;
    unsigned int m = x * 11, r;
    unsigned char pad[8]; unsigned char i;
    for (i = 0; i < 8; i++) pad[i] = x + i;
    r = lvl3(x + 2);
    r += lvl3(x + 3);
    for (i = 0; i < 8; i++) r += pad[i];
    return r + (unsigned int)(big >> 8) + m;
}
unsigned int lvl1(unsigned char x)
{
    unsigned int keep1 = x * 100, keep2 = 0xBEEF, r;
    unsigned char buf[12]; unsigned char i;
    for (i = 0; i < 12; i++) buf[i] = i ^ x;
    r = lvl2(x + 1);
    for (i = 0; i < 12; i++) r += buf[i];
    return r + keep1 + keep2;
}
void main(void)
{
    unsigned long sum = 0; unsigned char n;
    for (n = 0; n < 5; n++) { sum += lvl1(n + seed); sim_val("lvl1", sum); }
    sim_done();
}
