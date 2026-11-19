#include "ScalerCommonFunctionInclude.h"

// The one routine every main-context micro-delay runs (DELAY_5US / DELAY_XUS in ScalerCommonMcuInclude.h call these), so the
// simulator hooks one place and delay_sim / delay_audit see one function instead of ~190 inline loop copies.
// Loop shape kept as the inline macros had it: `djnz` on a direct IRAM byte = 16 clk per count (AWTO_DELAY_CLK_PER_CNT, unit 3 sweep);
// the counts are the unchanged AWTO_DELAY_CNT values. Pinned to common (fw_build --pin-common): a call from any bank, no trampoline.
// Not for ISRs: the EXINT macros stay inline (an ISR that calls a function pays SDCC's register-save prologue). The callers use an inline `lcall` (the macros): the compiler then spills nothing around the call, so both routines touch only the IRAM counters, no register, no flag.

// DELAY_5US: loops = d_isr_g_ucDelay5usN_Call = Base - AWTO_DELAY_CALL_CNT. The call (lcall + ret = 32 clk) costs exactly two loop counts
// (16 clk each) more than the inline entry, so the same wait comes out with two counts less; the entry is the same `mov d,d` (3 cycles).
// Base >= 3 at every clock state (AWTO_DELAY_CNT of the 5 us loop is >= 4: delay_audit.py --counts, the delays gate).
void AwtoDelayLoops(void) __naked
{
    __asm
        mov     _d_isr_g_ucDelay5usI, _d_isr_g_ucDelay5usN_Call
    00001$:
        djnz    _d_isr_g_ucDelay5usI, 00001$
        ret
    __endasm;
}

// DELAY_XUS: d_isr_g_ucDelayXus_Counter = N >> 2 is set by the caller (as the inline macro did); the outer passes of the 4 us base loop
// (count = d_isr_g_ucDelayXusN_Base). The call adds lcall + ret = 32 clk to a wait of 50 us and more: longer, never shorter.
void AwtoDelayXus(void) __naked
{
    __asm
    00001$:
        mov     _d_isr_g_ucDelay5usI, _d_isr_g_ucDelayXusN_Base
    00002$:
        djnz    _d_isr_g_ucDelay5usI, 00002$
        djnz    _d_isr_g_ucDelayXus_Counter, 00001$
        ret
    __endasm;
}
