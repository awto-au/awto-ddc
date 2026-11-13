#include "SysInclude.h"

// Watchdog + crash canary (#131, #138, docs/watchdog.md). Record: RL6449_Project.h StAwtoWdt.
// One hardware watchdog: pokes in the main-loop pass and bounded loops; the WDT threshold IRQ (int2, high priority) captures.
#if(_AWTO_WDT == _ON)
__sfr __at(0xD8) AWTO_EICON;                    // DW8051 EICON: bit 3 WDTI = core watchdog interrupt input flag (databook)
bit AwtoWdtValid(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&isr_g_stAwtoWdt)[ucI];
    }
    return (isr_g_stAwtoWdt.ucMagic0 == 'W') && (isr_g_stAwtoWdt.ucMagic1 == 'D') && (isr_g_stAwtoWdt.ucVersion == 2) && (isr_g_stAwtoWdt.ucCheck == ucS);
}

static void AwtoWdtSeal(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&isr_g_stAwtoWdt)[ucI];
    }
    isr_g_stAwtoWdt.ucCheck = ucS;
}

static void AwtoWdtFresh(void)                  // empty record: cold RAM, a host clear, or another layout
{
    BYTE ucI;

    for(ucI = 0; ucI < 32; ucI++)
    {
        ((volatile __xdata BYTE *)&isr_g_stAwtoWdt)[ucI] = 0;
    }
    isr_g_stAwtoWdt.ucMagic0 = 'W';
    isr_g_stAwtoWdt.ucMagic1 = 'D';
    isr_g_stAwtoWdt.ucVersion = 2;
}

volatile __xdata BYTE g_ucAwtoPokeSite;         // AWTO_WDT_S_* that ended the longest poke gap this boot (#150)
volatile __xdata BYTE g_ucAwtoPokeFrom;         // ... and the site that started it
volatile __xdata BYTE g_ucAwtoPokeLast;

void AwtoWdtLibPoke(BYTE ucSite)                // the FunctionLib flash read / write loops (no project header there)
{
    AWTO_WDT_POKE(ucSite);
#ifdef _AWTO_NEW_SETTINGS
    if(ucSite == 10)                                // one flash program (#151 counter; a CPU halt)
    {
        AWTO_NV_OP();
    }
#endif
}

// Once per reset, before EA: classify the boot, keep the record, reset the live counters.
volatile __xdata unsigned char g_ucAwtoStackHigh;
volatile __xdata unsigned char g_ucAwtoStackFatal;

void AwtoStackPaint(void)                      // main entry, EA still off: every byte above SP gets the paint
{
    __idata BYTE *pucP = (__idata BYTE *)(BYTE)(SP + 1);

    g_ucAwtoStackHigh = SP;
    g_ucAwtoStackFatal = 0;
    do
    {
        *pucP = AWTO_STACK_PAINT;
    }
    while(pucP++ != (__idata BYTE *)AWTO_STACK_TOP);
}

void AwtoStackCheck(void)                      // every main pass: O(1) normally (the mark only moves up)
{
    BYTE ucH = g_ucAwtoStackHigh;

    while((ucH < AWTO_STACK_TOP) && ((ucH < SP) || (*(__idata BYTE *)(BYTE)(ucH + 1) != AWTO_STACK_PAINT)))
    {
        ucH++;
    }
    g_ucAwtoStackHigh = ucH;
    if(ucH >= AWTO_STACK_GUARD)
    {
        g_ucAwtoStackFatal = 1;
        AwtoStackFatal(ucH);                    // drawn from the top of the main loop: the stack is shallow here
        for(;;)
        {
            AWTO_WDT_FEED(AWTO_WDT_S_STACK);    // the message stays up; ISRs (debug link) keep running
        }
    }
}

void AwtoStackDeepTest(void)                   // test cmd AWTO_TC_STACK_DEEP: zero bytes pushed into the guard zone, SP restored
{
    BYTE ucSave = SP;

    while(SP < AWTO_STACK_GUARD)
    {
        __asm
            clr a
            push acc
        __endasm;
    }
    SP = ucSave;
}

void AwtoWdtInit(void)
{
    BYTE ucOld = isr_g_stAwtoWdt.ucBoot;
    BYTE ucNew = 0;

    ScalerSetBit(AWTO_R_HOST_CTRL, ~(AWTO_F_HOST_CTRL_RESET_CHK | AWTO_F_HOST_CTRL_SOFT_RESET), AWTO_F_HOST_CTRL_RESET_CHK);   // reset_chk set again (any reset clears it; raw in the snapshot)
    // cold = no valid record; warm = valid record (P0_01[6] reads 0 after every reset on unit 2, #131: not used)
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
        ucOld = 0;
        ucNew |= AWTO_WDT_B_COLD;
    }
    else if((ucOld & AWTO_WDT_B_BITE) != 0)
    {
        ucNew |= AWTO_WDT_B_NEW | AWTO_WDT_B_AFTER;
    }
    else
    {
        ucNew |= AWTO_WDT_B_WARM | (((isr_g_stAwtoWdt.ucProbe & AWTO_WDT_P_EARLY) != 0) ? AWTO_WDT_B_HWWDT : 0);
        if(isr_g_stAwtoWdt.ucWarm != 0xFF)
        {
            isr_g_stAwtoWdt.ucWarm++;
        }
    }
    isr_g_stAwtoWdt.ucProbe &= ~AWTO_WDT_P_EARLY;
    ucNew |= ucOld & AWTO_WDT_B_NEW;            // not yet shown: keep it over another reset
    if((isr_g_stAwtoWdt.ucProbe & AWTO_WDT_P_ARMED) != 0)
    {
        isr_g_stAwtoWdt.ucProbe = (isr_g_stAwtoWdt.ucProbe & ~AWTO_WDT_P_ARMED) | AWTO_WDT_P_RESET;    // the probe's reset
        ucNew |= AWTO_WDT_B_PROBE;
    }
    AwtoWdtSeal();
    isr_g_stAwtoWdt.ucBoot = ucNew;
    isr_g_stAwtoWdt.ucPassHi = 0;                   // d_isr_g_usTimerCounter starts at 0 with Timer2 (ScalerMcuInitial)
    isr_g_stAwtoWdt.ucPassLo = 0;
    isr_g_stAwtoWdt.ucMaxPass = 0;
    isr_g_stAwtoWdt.ucMaxPoke = 0;
}

// Why this boot (#29). Inputs: the canary only (no reset-cause flag in DW8051 or RL6449; a found one goes in here first).
BYTE AwtoBootReason(void)
{
    BYTE ucB = isr_g_stAwtoWdt.ucBoot;

    return ((ucB & AWTO_WDT_B_COLD) != 0) ? AWTO_BOOT_COLD : ((ucB & AWTO_WDT_B_AFTER) != 0) ? AWTO_BOOT_BITE :
           ((ucB & AWTO_WDT_B_PROBE) != 0) ? AWTO_BOOT_PROBE : ((ucB & AWTO_WDT_B_HWWDT) != 0) ? AWTO_BOOT_HWWDT : AWTO_BOOT_WARM;
}

DWORD AwtoBootValue(void)                       // bite: cause << 24 | bank << 16 | PC (sync.tsv fmt pc)
{
    return ((DWORD)isr_g_stAwtoWdt.ucCause << 24) | ((DWORD)isr_g_stAwtoWdt.ucBank << 16) | ((WORD)isr_g_stAwtoWdt.ucPcHi << 8) | isr_g_stAwtoWdt.ucPcLo;
}

// WDT IRQ context (SysTimerWDIntProc), never returns. Frame at entry: SP0 + 1 PCL, + 2 PCH, then the ISR prologue pushes
// (acc, psw, r7..r0, bits, dpl, dph, b). No poke: the reset follows; sof_rst only shortens the wait.
static void AwtoWdtBite(BYTE ucSp, BYTE ucBank, BYTE ucCause)
{
    __idata BYTE *pucF = (__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME);
    WORD usAge = d_isr_g_usTimerCounter - AWTO_WDT_PASS_AT();

    EA = 0;
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
    }
    isr_g_stAwtoWdt.ucCause = ucCause | (((isr_g_stAwtoWdt.ucBoot & AWTO_WDT_B_TEST) != 0) ? AWTO_WDT_C_TEST : 0) |
                          ((AWTO_WDT_MODE == AWTO_WDT_TIMER_IRQ) ? AWTO_WDT_C_TMODE : 0);
    if(isr_g_stAwtoWdt.ucBites != 0xFF)
    {
        isr_g_stAwtoWdt.ucBites++;
    }
    isr_g_stAwtoWdt.ucPcHi = pucF[2];
    isr_g_stAwtoWdt.ucPcLo = pucF[1];
    isr_g_stAwtoWdt.ucBank = ucBank;
    isr_g_stAwtoWdt.ucSp = (BYTE)(ucSp - AWTO_WDT_FRAME);
    isr_g_stAwtoWdt.ucAcc = pucF[3];
    isr_g_stAwtoWdt.ucPsw = pucF[4];
    isr_g_stAwtoWdt.ucDpl = pucF[14];
    isr_g_stAwtoWdt.ucDph = pucF[15];
    isr_g_stAwtoWdt.ucB = pucF[16];
    isr_g_stAwtoWdt.ucRetHi = pucF[0];
    isr_g_stAwtoWdt.ucRetLo = *(__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME - 1);
    isr_g_stAwtoWdt.ucStage = isr_g_stAwtoDiag.ucStage;
    isr_g_stAwtoWdt.ucMode = GET_MODE_STATE();
    isr_g_stAwtoWdt.ucHbHi = (BYTE)(isr_g_stAwtoDiag.usHeartbeat >> 8);
    isr_g_stAwtoWdt.ucHbLo = (BYTE)isr_g_stAwtoDiag.usHeartbeat;
    isr_g_stAwtoWdt.ucUpHi = (BYTE)(d_isr_g_usTimerCounter >> 8);
    isr_g_stAwtoWdt.ucUpLo = (BYTE)d_isr_g_usTimerCounter;
    isr_g_stAwtoWdt.ucPassAgeHi = (BYTE)(usAge >> 8);
    isr_g_stAwtoWdt.ucPassAgeLo = (BYTE)usAge;
    AwtoWdtSeal();
    isr_g_stAwtoWdt.ucBoot |= AWTO_WDT_B_BITE;
    MCU_FFEE_MCU_CLOCK_CONTROL |= _BIT1;          // sof_rst now (as the host's ISP 0xEE <- 0x02); else CNT1 = N resets
    while(_TRUE)
    {
    }
}

// SysTimerWDIntProc (int2, PX2 = 1): CNT3 matched the threshold. Warning only at CNT1 = N - 1; earlier wraps' matches return.
void AwtoWdtIrq(BYTE ucSp, BYTE ucBank)
{
    BYTE ucCnt1;

    if((MCU_FFEB_WDT_TEST & _BIT7) == 0)
    {
        return;
    }
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT3;     // latch the counters (no clear)
    ucCnt1 = AWTO_XFR(AWTO_R_WATCHDOG_CNT1_VALUE) & AWTO_F_WATCHDOG_CNT1_VALUE_WDT_CNT1_VALUE;
    if((isr_g_stAwtoWdt.ucProbe & AWTO_WDT_P_ARMED) != 0)
    {
        isr_g_stAwtoWdt.ucProbe |= AWTO_WDT_P_IRQ | (((AWTO_EICON & _BIT3) != 0) ? AWTO_WDT_P_WDTI : 0);
        MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT2) | _BIT7;  // flag cleared, IRQ off; counting goes on to the reset
        return;
    }
#if(AWTO_WDT_N > 1)
    if(ucCnt1 < (AWTO_WDT_N - 1))
    {
        isr_g_stAwtoWdt.ucProbe |= AWTO_WDT_P_EARLY;    // evidence for the next boot if the warning never captures
        MCU_FFEB_WDT_TEST |= _BIT7;             // flag cleared (W1C); counting goes on
        return;
    }
#else
    ucCnt1 = ucCnt1;                            // N = 1: the first match is the warning (no early match, no P_EARLY)
#endif
    AwtoWdtBite(ucSp, ucBank, AWTO_WDT_C_STALL);
}

// Test cmd 0x4C + n (#131): 0 spin (STALL), 2 spin with EA off (hardware reset only, no capture). 1 (spin in a poking wait)
// is gone (#138): an unbounded loop around a poking wait is a bug the audit forbids (docs/watchdog.md), not a run-time case.
void AwtoWdtHang(BYTE ucHow)
{
    if(ucHow == 1)
    {
        return;
    }
    isr_g_stAwtoWdt.ucBoot |= AWTO_WDT_B_TEST;
    if(ucHow == 2)
    {
        EA = 0;
    }
    while(_TRUE)
    {
    }
}

// Test cmd 0x49 (normal mode) / 0x4F (timer mode), for unit 2: no pokes, threshold PROBE_THR, N = 1; does the IRQ come, does
// the chip reset? Result in ucProbe (kept over the reset; rtd_crash.py, console). Back to the configured watchdog if no reset.
void AwtoWdtProbe(BYTE ucTimer)
{
    WORD usT0;
    WORD usNow;

    isr_g_stAwtoWdt.ucProbe = AWTO_WDT_P_ARMED | ((ucTimer != 0) ? AWTO_WDT_P_TIMER : 0);
    EA = 0;
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~(_BIT7 | _BIT4 | _BIT2)) | _BIT7 | ((ucTimer != 0) ? _BIT4 : 0);
    AWTO_XFR(AWTO_R_WATCHDOG_TIMER_H_THRESHOLD_MASK) = (AWTO_XFR(AWTO_R_WATCHDOG_TIMER_H_THRESHOLD_MASK) & AWTO_F_WATCHDOG_TIMER_H_THRESHOLD_MASK_WDT_CNT_THRESHOLD_H_MASK) | ((AWTO_WDT_PROBE_THR >> 4) & AWTO_F_WATCHDOG_TIMER_H_THRESHOLD_MASK_WDT_CNT_THRESHOLD_H_VALUE);
    AWTO_XFR(AWTO_R_WATCHDOG_TIMER_THRESHOLD) = (BYTE)AWTO_WDT_PROBE_THR;
    MCU_FFEA_WATCHDOG_TIMER = (MCU_FFEA_WATCHDOG_TIMER & ~(_BIT2 | _BIT1 | _BIT0)) | _BIT6;       // N = 1, clear
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT2;
    EA = 1;
    do
    {
        usT0 = d_isr_g_usTimerCounter;
    }
    while(usT0 != d_isr_g_usTimerCounter);
    do
    {
        usNow = d_isr_g_usTimerCounter;
    }
    while((WORD)(usNow - usT0) < AWTO_WDT_PROBE_MS);
    isr_g_stAwtoWdt.ucProbe = (isr_g_stAwtoWdt.ucProbe & ~AWTO_WDT_P_ARMED) | AWTO_WDT_P_NORESET | (((AWTO_EICON & _BIT3) != 0) ? AWTO_WDT_P_WDTI : 0);
    ScalerTimerWDInitial();                     // the configured watchdog again (clears the counters)
}

// Main loop while AWTO_WDT_B_NEW: open the console (watchdog panel) once picture / no-signal state has settled AWTO_WDT_SHOW_MS.
// Not through the info pop-up (ucDbgPopup): the pop-up repositions the OSD after the console opened (sim render, #131).
static __xdata WORD s_usAwtoWdtSettled;         // 0 = not settled; else AwtoMs low word | 1 when it settled

void AwtoWdtShow(void)
{
    BYTE ucMode = GET_MODE_STATE();
    WORD usNow;

    usNow = (WORD)AwtoMs();
    if((isr_g_stAwtoDiag.ucStage < 8) || (SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) ||
       ((ucMode != _MODE_STATUS_ACTIVE) && (ucMode != _MODE_STATUS_NOSIGNAL) && (ucMode != _MODE_STATUS_NOSUPPORT)))
    {
        s_usAwtoWdtSettled = 0;
        return;
    }
    if(s_usAwtoWdtSettled == 0)
    {
        s_usAwtoWdtSettled = usNow | 1;
        return;
    }
    if((WORD)(usNow - s_usAwtoWdtSettled) >= AWTO_WDT_SHOW_MS)
    {
        AwtoDiagConsole(1);                     // its first log line is the bite ("boot: watchdog bite, PC ...")
        isr_g_stAwtoWdt.ucBoot &= ~AWTO_WDT_B_NEW;  // shown: stops this poll reopening it every boot
    }
}
#endif
