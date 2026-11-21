/* (d) clobbered scratch: main writes a scratch byte, uses it later; the ISR reuses the same byte in between */
#include <8051.h>
#include "san.h"
__xdata volatile unsigned char g_scratch;
__xdata unsigned char g_out;
void t0_isr(void) __interrupt(1) { g_scratch = 0x55; RELOAD(); }
void main(void)
{
    unsigned char i;
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (;;) {
        g_scratch = 7;
        for (i = 0; i < 20; i++) g_out ^= i;
        g_out += g_scratch;
    }
}
