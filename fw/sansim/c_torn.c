/* (c) torn: the ISR stores a 16-bit value as two bytes, main reads it as two bytes */
#include <8051.h>
#include "san.h"
__xdata unsigned int g_v;
__xdata unsigned int g_sink;
void t0_isr(void) __interrupt(1) { g_v += 0x0101; RELOAD(); }
void main(void)
{
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (;;) { g_sink = g_v; }
}
