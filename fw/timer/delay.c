#include "ScalerCommonFunctionInclude.h"

// The routines every micro-delay runs, main and ISR (DELAY_5US / DELAY_XUS / AWTO_GAP_RUN in ScalerCommonMcuInclude.h): one djnz shape, 12 clk
// per count (AWTO_DELAY_CLK_PER_CNT), so delay_sim / delay_audit see one place. R6 / R7 are bank 0 direct (push 0x07 here, the caller's
// inline asm pushes R6 around the call): an ISR delay cannot corrupt an interrupted one, no shared counter. Pinned to common (fw_build --pin-common).
// DELAY_5US loops d_isr_g_ucDelay5usN_Call = Base - AWTO_DELAY_CALL_CNT (lcall + ret + push + pop = 48 clk = 4 counts): same wait as an inline loop.
// Long-block check (AwtoDelayXus only: a 5 us wait is too short to matter; the check's ~12 counts would exceed it at the slow clocks) (docs/delays.md): TH2 (256 Timer2 counts = 256 loop counts) at entry and exit; elapsed > expected + AWTO_DLY_SLACK_TICKS
// -> AwtoDelayLong stores the caller PC, bank and ticks in isr_g_stAwtoDlyLong; AwtoDelayLongPoll (main) writes the sync line.
// SFR: 0xCD TH2, 0xCB RCAP2H. Saved around the check: PSW, ACC, B, R7 (no ISR prologue sees this code).
__xdata StAwtoDlyLong isr_g_stAwtoDlyLong;

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

// DELAY_XUS: R6 = N >> 2 outer passes of the 4 us base loop (count = Base); expected ticks = R6 x (Base + AWTO_DLY_PASS_CNT) >> 8.
void AwtoDelayXus(void) __naked
{
    __asm
        push    psw
        push    acc
        push    b
        push    0x07
        mov     b, 0x06
        mov     a, 0xCD
    00001$:
        mov     r7, _d_isr_g_ucDelayXusN_Base
    00002$:
        djnz    r7, 00002$
        djnz    0x06, 00001$
        mov     r7, a
        mov     a, _d_isr_g_ucDelayXusN_Base
        add     a, #AWTO_DLY_PASS_CNT
        xch     a, b
        mul     ab
        mov     a, r7
        mov     r7, b
        ljmp    _AwtoDelayEnd
    __endasm;
}

// A = TH2 at entry, R7 = expected ticks; pops what the routine pushed and returns to the caller.
void AwtoDelayEnd(void) __naked
{
    __asm
        mov     b, a
        mov     a, 0xCD
        clr     c
        subb    a, b
        jnc     00001$
        clr     c
        subb    a, 0xCB
    00001$:
        mov     b, a
        clr     c
        subb    a, r7
        jc      00002$
        add     a, #(255 - AWTO_DLY_SLACK_TICKS)
        jnc     00002$
        lcall   _AwtoDelayLong
    00002$:
        pop     0x07
        pop     b
        pop     acc
        pop     psw
        ret
    __endasm;
}

// AWTO_GAP_RUN: R6 = loop count (the caller subtracts AWTO_GAP_CALL_CNT). No check: a gap is a few counts.
void AwtoDelayCnt(void) __naked
{
    __asm
    00001$:
        djnz    0x06, 00001$
        ret
    __endasm;
}

// B = elapsed ticks, R7 = expected. Stack from SP: AwtoDelayEnd ret (2), R7, B, ACC, PSW, caller PC (hi above lo).
void AwtoDelayLong(void) __naked
{
    __asm
        push    dpl
        push    dph
        push    0x00
        mov     a, sp
        clr     c
        subb    a, #9
        mov     r0, a
        mov     dptr, #_isr_g_stAwtoDlyLong
        movx    a, @dptr
        cjne    a, #0xFF, 00001$
        sjmp    00002$
    00001$:
        inc     a
        movx    @dptr, a
    00002$:
        inc     dptr
        mov     a, @r0
        movx    @dptr, a
        dec     r0
        inc     dptr
        mov     a, @r0
        movx    @dptr, a
        inc     dptr
        mov     a, _d_isr_bs_cur
        movx    @dptr, a
        inc     dptr
        mov     a, b
        movx    @dptr, a
        inc     dptr
        mov     a, r7
        movx    @dptr, a
        pop     0x00
        pop     dph
        pop     dpl
        ret
    __endasm;
}

// Main loop, once per pass: one sync line for the blocks since the last pass (the last one, +N more); the counter restarts.
void AwtoDelayLongPoll(void)
{
    StAwtoDlyLong stRec;
    DWORD ulUs;

    if(isr_g_stAwtoDlyLong.ucN == 0)
    {
        return;
    }
    EA = 0;
    stRec = isr_g_stAwtoDlyLong;
    isr_g_stAwtoDlyLong.ucN = 0;
    EA = 1;
    ulUs = ((DWORD)stRec.ucTicks * 256UL * 1000UL) / (0x10000UL - (((WORD)RCAP2H << 8) | RCAP2L));
    AwtoSyncPush(AWTO_SYNC_EV_DLYLONG, (stRec.ucBank & 0x0F) | ((stRec.ucN > 16 ? 15 : (stRec.ucN - 1)) << 4),
                 ((DWORD)(((WORD)stRec.ucPcHi << 8) | stRec.ucPcLo) << 16) | (ulUs > 0xFFFF ? 0xFFFF : ulUs));
}
