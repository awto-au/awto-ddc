#include "ScalerCommonFunctionInclude.h"

// The routines every micro-delay runs, main and ISR (DELAY_5US / DELAY_XUS / AWTO_GAP_RUN in ScalerCommonMcuInclude.h): one djnz shape, 12 clk
// per count (AWTO_DELAY_CLK_PER_CNT), so delay_sim / delay_audit see one place. R6 / R7 are bank 0 direct (push 0x07 here, the caller's
// inline asm pushes R6 around the call): an ISR delay cannot corrupt an interrupted one, no shared counter. Pinned to common (fw_build --pin-common).
// DELAY_5US loops d_isr_g_ucDelay5usN_Call = Base - AWTO_DELAY_CALL_CNT (lcall + ret + push + pop = 48 clk = 4 counts): same wait as an inline loop.
void AwtoDelayLoops(void) __naked
{
    __asm
        push    0x07
        mov     r7, _d_isr_g_ucDelay5usN_Call
    00001$:
        djnz    r7, 00001$
        pop     0x07
        ret
    __endasm;
}

// DELAY_XUS: R6 = N >> 2 outer passes of the 4 us base loop (count = Base).
void AwtoDelayXus(void) __naked
{
    __asm
        push    0x07
    00001$:
        mov     r7, _d_isr_g_ucDelayXusN_Base
    00002$:
        djnz    r7, 00002$
        djnz    0x06, 00001$
        pop     0x07
        ret
    __endasm;
}

// AWTO_GAP_RUN: R6 = loop count (the caller subtracts AWTO_GAP_CALL_CNT).
void AwtoDelayCnt(void) __naked
{
    __asm
    00001$:
        djnz    0x06, 00001$
        ret
    __endasm;
}
