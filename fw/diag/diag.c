#include "SysInclude.h"

// Diag block functions (#23). Layout: RL6449_Project.h StAwtoDiag.
void AwtoDiagStage(unsigned char ucStage)
{
    unsigned int usNow;

    if((ucStage > isr_g_stAwtoDiag.ucStage) && (ucStage <= 8))      // awto: #53.17 usStageMs[7] is the last
    {
        do
        {
            usNow = d_isr_g_usTimerCounter;
        }
        while(usNow != d_isr_g_usTimerCounter);
        isr_g_stAwtoDiag.usStageMs[ucStage - 1] = usNow;
        isr_g_stAwtoDiag.ucStage = ucStage;
        // stage 1 = AwtoSyncInit's line; stages without a sync.tsv row (5 / 7 / 8: the panel machine's lines state them) no line
        if((ucStage >= 2) && (AwtoSyncRow(AWTO_SYNC_EV_STAGE, ucStage) != 0))
        {
            AwtoSyncPush(AWTO_SYNC_EV_STAGE, ucStage, 0);
        }
    }
}

void AwtoDiagInit(void)
{
    unsigned char ucI;

    for(ucI = 0; ucI < sizeof(StAwtoDiag); ucI++)
    {
        ((volatile __xdata unsigned char *)&isr_g_stAwtoDiag)[ucI] = 0;      // awto: #53.18
    }
    isr_g_stAwtoDiag.ucMagic0 = 'A';
    isr_g_stAwtoDiag.ucMagic1 = 'D';
    isr_g_stAwtoDiag.ucVersion = (_AWTO_DBGISR == _ON) ? 2 : 1;
    AwtoOsdOfsInit();
    AwtoDiagStage(1);
}

void AwtoDiagMainPass(void)
{
    static unsigned int usLastMs;
    static unsigned int usLastHb;
    static unsigned int usLastMon;
    unsigned int usNow;

    isr_g_stAwtoDiag.usHeartbeat++;
    do
    {
        usNow = d_isr_g_usTimerCounter;
    }
    while(usNow != d_isr_g_usTimerCounter);
    AWTO_WDT_PASS(usNow);
    if((unsigned int)(usNow - usLastMs) >= 1000)
    {
        isr_g_stAwtoDiag.usLoopRate = isr_g_stAwtoDiag.usHeartbeat - usLastHb;
        usLastHb = isr_g_stAwtoDiag.usHeartbeat;
        usLastMs = usNow;
    }
#if(_AWTO_WDT == _ON)
    if((unsigned int)(usNow - usLastMon) >= AWTO_MON_MS)       // monitor: one subtract + compare per pass, the sample every AWTO_MON_MS
    {
        usLastMon = usNow;
        AwtoMonSample();
    }
#endif
    AwtoDiagStage(6);                                  // first main-loop pass (#63 order: 5 = panel VDD comes first)
    AWTO_WDT_SHOW();
}


#if(AWTO_LOOP_PACING > 0)
volatile bit d_isr_g_bWkEx0;
volatile bit d_isr_g_bWkEx1;
volatile bit d_isr_g_bWkT0;
volatile bit d_g_bWkSw;
__xdata StAwtoHead g_stAwtoHead;                // last 1 s window, read over the debug slave by symbol (docs/main-loop-pacing.md)
extern __xdata unsigned char g_ucAwtoSaverRun;

// Time in 1/256 ms: Timer2 ms ticks + the phase of TH2:TL2 inside the tick (reload RCAP2). Read-only, does not wake or stop anything.
static unsigned long AwtoQ8Now(void)
{
    unsigned int usT1;
    unsigned int usT2;
    unsigned int usCnt;
    unsigned int usRl;

    do
    {
        usT1 = d_isr_g_usTimerCounter;
        usCnt = ((unsigned int)TH2 << 8) | TL2;
        usT2 = d_isr_g_usTimerCounter;
    }
    while(usT1 != usT2);
    usRl = ((unsigned int)RCAP2H << 8) | RCAP2L;
    return ((unsigned long)usT1 << 8) + (((unsigned long)(unsigned int)(usCnt - usRl) << 8) / (unsigned int)(0u - usRl));
}

static unsigned int AwtoTick(void)
{
    return ScalerTimerGetTimerCounter();
}

static unsigned int AwtoMinMs(unsigned int usA, unsigned int usB)
{
    return (usA < usB) ? usA : usB;
}

void AwtoLoopIdle(void)                         // own function: the sim test (scripts/loop_pacing_test.py) sets a wake bit here, between the check and the IDL write
{
    PCON |= 0x01;
}

// End of every pass. Sleep (IDL) until the first of: AWTO_LOOP_PACING ms since the previous pass, a wake bit, the earliest timer-event deadline,
// the next key sample, the next settings-loop service. Lost wake: a wake bit set between the check and the IDL write is seen at the next IRQ,
// Timer2 at the latest = 1 ms. The EA-off trick does not apply (a halted 8051 cannot run EA = 1; databook: wake needs an enabled IRQ).
// Headroom (per 1 s window, g_stAwtoHead): busy = previous exit -> this entry, sleep = entry -> exit, worst busy pass.
void AwtoLoopPace(void)
{
    static unsigned int usStart;
    static unsigned long ulExit;
    static unsigned long ulWin;
    static unsigned long ulSleep;
    static unsigned int usPasses;
    static unsigned int usHold;
    static unsigned int usIdles;
    static unsigned int usWkIsr;
    static unsigned int usWorst;
    unsigned long ulEntry = AwtoQ8Now();
    unsigned long ulBusy = (ulEntry - ulExit) & 0xFFFFFFul;
    unsigned int usNow = AwtoTick();
    unsigned int usDue = usStart + AWTO_LOOP_PACING;
    unsigned int usD;
    unsigned int usRem;

    AwtoDelayLongPoll();
    if(AwtoLoopBusy() != 0)
    {
        usHold++;
    }
    else
    {
        usD = (unsigned int)(isr_g_stAwtoDiag.usT2Isr - g_usAwtoSetLast);
        usD = (usD >= AWTO_SET_LOOP_MS) ? 0 : (AWTO_SET_LOOP_MS - usD);
        usD = AwtoMinMs(usD, AwtoMinMs(SysTimerNextEventMs(), AwtoKeyDueMs()));
        usRem = usDue - usNow;
        if((int)usRem < 0)
        {
            usRem = 0;
        }
        if(usD < usRem)
        {
            usDue = usNow + usD;
        }
        for(;;)
        {
            usNow = AwtoTick();
            if((d_isr_g_bWkEx0 != 0) || (d_isr_g_bWkEx1 != 0) || (d_isr_g_bWkT0 != 0) || (d_g_bWkSw != 0))
            {
                usWkIsr++;
                break;
            }
            if((int)(usNow - usDue) >= 0)
            {
                break;
            }
            usIdles++;
            AwtoLoopIdle();
        }
    }
    d_isr_g_bWkEx0 = 0;
    d_isr_g_bWkEx1 = 0;
    d_isr_g_bWkT0 = 0;
    d_g_bWkSw = 0;
    usStart = AwtoTick();
    ulExit = AwtoQ8Now();
    ulSleep += (ulExit - ulEntry) & 0xFFFFFFul;
    usPasses++;
    if((ulBusy >> 4) > usWorst)
    {
        usWorst = (ulBusy >> 4 > 0xFFFF) ? 0xFFFF : (unsigned int)(ulBusy >> 4);
    }
    if(((ulExit - ulWin) & 0xFFFFFFul) >= (1000ul << 8))
    {
        g_stAwtoHead.usPasses = usPasses;
        g_stAwtoHead.usSleepPm = (unsigned int)((ulSleep * 1000ul) / ((ulExit - ulWin) & 0xFFFFFFul));
        g_stAwtoHead.usWorstQ4 = usWorst;
        g_stAwtoHead.usHoldPm = (unsigned int)(((unsigned long)usHold * 1000ul) / usPasses);
        g_stAwtoHead.usIdles = usIdles;
        g_stAwtoHead.usWkIsr = usWkIsr;
        ulWin = ulExit;
        ulSleep = 0;
        usPasses = 0;
        usHold = 0;
        usIdles = 0;
        usWkIsr = 0;
        usWorst = 0;
    }
}
#endif
