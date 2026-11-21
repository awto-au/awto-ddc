#include "ScalerCommonFunctionInclude.h"

// The one routine every main-context micro-delay runs (DELAY_5US / DELAY_XUS in ScalerCommonMcuInclude.h), so the simulator hooks
// one place and delay_sim / delay_audit see one function. Loop = `mov R7,base; djnz R7,$`, 12 clk per count (AWTO_DELAY_CLK_PER_CNT);
// R7 (direct 0x07, bank 0) is saved (push / pop), the callers use an inline `lcall` so SDCC spills nothing. Pinned to common (fw_build --pin-common).
// Not for ISRs: the EXINT macros stay inline (an ISR that calls a function pays SDCC's register-save prologue).
// DELAY_5US loops d_g_ucDelay5usN_Call = Base - AWTO_DELAY_CALL_CNT (lcall + ret + push + pop = 48 clk = 4 counts): same wait as inline.
void AwtoDelayLoops(void) __naked
{
    __asm
        push    0x07
        mov     r7, _d_g_ucDelay5usN_Call
    00001$:
        djnz    r7, 00001$
        pop     0x07
        ret
    __endasm;
}

// DELAY_XUS: the caller sets d_g_ucDelayXus_Counter = N >> 2 (outer passes of the 4 us base loop, count = Base).
void AwtoDelayXus(void) __naked
{
    __asm
        push    0x07
    00001$:
        mov     r7, _d_isr_g_ucDelayXusN_Base
    00002$:
        djnz    r7, 00002$
        djnz    _d_g_ucDelayXus_Counter, 00001$
        pop     0x07
        ret
    __endasm;
}
