/* (b) lost update: main and the T0 ISR both do cnt++ (movx / inc / movx); g_quiet: ISR enabled but the timer never runs */
#include <8051.h>
#include "san.h"
__xdata unsigned char g_cnt, g_quiet_cnt;
void t0_isr(void) __interrupt(1) { g_cnt++; g_quiet_cnt++; RELOAD(); }
void main(void)
{
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (;;) { g_cnt++; }
}
