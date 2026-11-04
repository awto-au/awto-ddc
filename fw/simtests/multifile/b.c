#include "mf.h"
static unsigned int helper(unsigned char v)
{
    unsigned int t[3]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 3; i++) t[i] = v * (i + 2);
    for (i = 0; i < 3; i++) s ^= t[i];
    return s + 2000;
}
unsigned int b_entry(unsigned char x)
{
    unsigned char counter = x * 3;
    unsigned int r = helper(counter);
    shared_g += 2;
    return r + counter;
}
