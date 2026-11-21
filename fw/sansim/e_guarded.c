/* negative: every main access to g_cnt is inside EA=0 (and a __critical function); no could / did finding */
#include <8051.h>
#include "san.h"
__xdata unsigned char g_cnt, g_two;
void t0_isr(void) __interrupt(1) { g_cnt++; g_two = 1; RELOAD(); }
void bump(void) __critical { g_two = 0; g_two++; }
void main(void)
{
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (;;) { EA = 0; g_cnt++; EA = 1; bump(); }
}
