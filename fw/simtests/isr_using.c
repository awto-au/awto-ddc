/* ISR on register bank 1 calling a __using(2) fn and a plain helper that main also calls (EA=0 sections) */
#include <8051.h>
#include "sim.h"
volatile unsigned char seed = 7;
volatile unsigned int isr_n, isr_bad;

unsigned int plain(unsigned char x)
{
    unsigned char t[4]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 4; i++) t[i] = x ^ (i * 17);
    for (i = 0; i < 4; i++) s += t[i];
    return s;
}
unsigned int banked(unsigned char x) __using(2)
{
    unsigned char t[3]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 3; i++) t[i] = x + i;
    for (i = 0; i < 3; i++) s += t[i];
    return s;
}
unsigned int want_plain(unsigned char x)
{
    unsigned int s = 0; unsigned char i;
    for (i = 0; i < 4; i++) s += (unsigned char)(x ^ (i * 17));
    return s;
}
void t0_isr(void) __interrupt(1) __using(1)
{
    unsigned char v = (unsigned char)isr_n;
    if (banked(v) != (unsigned int)(3 * v + 3)) isr_bad++;
    if (plain(v) != want_plain(v)) isr_bad++;
    TH0 = 0xF8; TL0 = 0;
    isr_n++;
}
void main(void)
{
    unsigned int k, bad = 0; unsigned long sum = 0; unsigned int r;
    TMOD = 0x01; TH0 = 0xF8; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (k = 0; k < 300; k++) {
        unsigned char x = (unsigned char)k + seed;
        EA = 0; r = plain(x); if (r != want_plain(x)) bad++; EA = 1;
        sum += r;
    }
    while (isr_n < 20) { }
    for (k = 0; k < 40; k++) { sim_val("main_sum", sum + k); sim_val("main_bad", bad); }
    EA = 0; TR0 = 0;
    sim_val("isr_bad", isr_bad);
    sim_done();
}
