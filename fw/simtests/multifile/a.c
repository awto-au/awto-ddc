#include "mf.h"
static unsigned int helper(unsigned char v)
{
    unsigned char t[5]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 5; i++) t[i] = v + i;
    for (i = 0; i < 5; i++) s += t[i];
    return s + 1000;
}
unsigned int a_entry(unsigned char x)
{
    unsigned char counter = x * 2;
    unsigned int r = helper(counter);
    shared_g += 1;
    return r + counter;
}
