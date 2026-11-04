/* direct + mutual recursion (__reentrant: plain SDCC statics can't recurse); pass must keep cycles static */
#include "sim.h"
volatile unsigned char seed = 6;

unsigned int fact(unsigned char n) __reentrant
{
    unsigned int r;
    if (n <= 1) return 1;
    r = fact(n - 1);
    return r * n;
}
unsigned int is_odd(unsigned char n) __reentrant;
unsigned int is_even(unsigned char n) __reentrant
{
    unsigned int pad = n * 3;
    if (n == 0) return 1;
    return is_odd(n - 1) + (pad & 0);
}
unsigned int is_odd(unsigned char n) __reentrant
{
    unsigned int pad = n * 5;
    if (n == 0) return 0;
    return is_even(n - 1) + (pad & 0);
}
unsigned int fib(unsigned char n) __reentrant
{
    unsigned int a, b;
    if (n < 2) return n;
    a = fib(n - 1);
    b = fib(n - 2);
    return a + b;
}
unsigned int leaf(unsigned char x)       /* plain function called from main and between recursive calls */
{
    unsigned char t[5]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 5; i++) t[i] = x + i;
    for (i = 0; i < 5; i++) s += t[i];
    return s;
}
void main(void)
{
    unsigned int keep = leaf(seed);
    sim_val("fact", fact(7));
    sim_val("even", is_even(9 + seed));
    sim_val("odd", is_odd(9 + seed));
    sim_val("fib", fib(12));
    sim_val("keep", keep + leaf(1));
    sim_done();
}
