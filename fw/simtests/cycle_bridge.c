/* probe: outer (locals live) -> recursive fn -> leaf with locals; leaf only reachable through the cycle */
#include "sim.h"
volatile unsigned char seed = 9;

unsigned int leaf(unsigned char x)
{
    unsigned char t[8]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 8; i++) t[i] = x + i;
    for (i = 0; i < 8; i++) s += t[i];
    return s;
}
unsigned int rec(unsigned char n) __reentrant
{
    if (n == 0) return leaf(3);
    return rec(n - 1) + 1;
}
unsigned int outer(unsigned char x)
{
    unsigned char mine[8]; unsigned char i; unsigned int r, s = 0;
    for (i = 0; i < 8; i++) mine[i] = x * 3 + i;
    r = rec(2);
    for (i = 0; i < 8; i++) s += mine[i];
    return r + s;
}
void main(void)
{
    sim_val("outer", outer(seed));
    sim_done();
}
