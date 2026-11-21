/* (a) conflict: main polls a plain flag the T0 ISR sets; g_guarded is only touched with EA=0 in main */
#include <8051.h>
#include "san.h"
__xdata unsigned char g_flag, g_guarded, g_sink;
void t0_isr(void) __interrupt(1) { g_flag = 1; g_guarded = 3; RELOAD(); }
void main(void)
{
    TMOD = 0x01; TH0 = 0xFF; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (;;) {
        if (g_flag) g_sink = g_flag;
        EA = 0; g_guarded = 1; EA = 1;
    }
}
