/* probe: fn `calc` has local `sum_acc` -> label _calc_sum_acc_*, owner guessed as fn `calc_sum` */
#include "sim.h"
volatile unsigned char seed = 2;

unsigned int calc_sum(unsigned char x)
{
    unsigned char t[10]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 10; i++) t[i] = x + i;
    for (i = 0; i < 10; i++) s += t[i];
    return s;
}
unsigned int aux(unsigned char x)
{
    unsigned char t[40]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 40; i++) t[i] = 0xA5 ^ x ^ i;
    for (i = 0; i < 40; i++) s += t[i];
    return s;
}
unsigned int calc(unsigned char x)
{
    unsigned char sum_acc[4] = { 1, 2, 3, 4 };      /* array: always gets XSEG storage */
    sum_acc[0] = x + seed;
    unsigned int r = calc_sum(x);       /* sum_acc live across calls to calc_sum and aux */
    r += aux(x);
    return r + sum_acc[0] + sum_acc[1] + sum_acc[2] + sum_acc[3];
}
void main(void)
{
    sim_val("calc", calc(seed));
    sim_done();
}
