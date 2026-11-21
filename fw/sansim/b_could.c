/* (b) could only: the T0 ISR runs once (then stops its timer) before main starts the g_cnt++ loop, so nothing interleaves */
#include <8051.h>
__xdata unsigned char g_cnt;
__xdata volatile unsigned char g_ran;
void t0_isr(void) __interrupt(1) { g_cnt++; TR0 = 0; g_ran = 1; }
void main(void)
{
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    while (!g_ran) { }
    for (;;) { g_cnt++; }
}
