// Diag block functions (#23), inserted into SysMain.c by keil2sdcc.py. Layout: RL6449_Project.h StAwtoDiag.
#if(_AWTO_DIAG == _ON)
void AwtoDiagStage(unsigned char ucStage)
{
    unsigned int usNow;

    if(ucStage > g_stAwtoDiag.ucStage)
    {
        do
        {
            usNow = g_usTimerCounter;
        }
        while(usNow != g_usTimerCounter);
        g_stAwtoDiag.usStageMs[ucStage - 1] = usNow;
        g_stAwtoDiag.ucStage = ucStage;
    }
}

void AwtoDiagInit(void)
{
    unsigned char ucI;
    unsigned char ucWdt = MCU_FFEB_WDT_TEST;

    MCU_FFEB_WDT_TEST |= _BIT7;                  // write 1 to clear
    // warm reset: keep the previous boot's trace + pass times before the diag block is wiped
    g_stAwtoSafe.ucFlags = 0;
    g_stAwtoSafe.ucWdtTest = ucWdt;
    if(g_stAwtoSafe.usMarker == _AWTO_SAFE_MARKER)
    {
        g_stAwtoSafe.ucPrevTraceSeq = g_stAwtoDiag.ucTraceSeq;
        for(ucI = 0; ucI < 3; ucI++)
        {
            g_stAwtoSafe.usPrevTrace[ucI] = g_stAwtoDiag.usTrace[ucI];
        }
        g_stAwtoSafe.usPrevLastPassMs = g_stAwtoSafe.usLastPassMs;
        g_stAwtoSafe.usPrevMaxPassMs = g_stAwtoSafe.usMaxPassMs;
        g_stAwtoSafe.ucPrevForceReset = g_stAwtoSafe.ucForceReset;
        g_stAwtoSafe.ucPrevBusResets = g_stAwtoSafe.ucBusResets;
        g_stAwtoSafe.ucFlags = _AWTO_SAFE_F_WARM;
    }
    g_stAwtoSafe.ucForceReset = 0;
    g_stAwtoSafe.usKeyStartMs = 0xFFFF;
    g_stAwtoSafe.usBusStuckMs = 0xFFFF;
    g_stAwtoSafe.ucBusResets = 0;
    // never carry a hold across a reset: the front-panel power key is a warm reset (RAM kept), and a held
    // window left unit 3 with a dead DDC bus on every boot (#26, 2026-11-06). Host re-arms it per boot.
    g_stAwtoSafe.usHold = 0;
    g_stAwtoSafe.usMarker = _AWTO_SAFE_MARKER;
    g_stAwtoSafe.usLastPassMs = g_usTimerCounter;
    g_stAwtoSafe.usMaxPassMs = 0;

    for(ucI = 0; ucI < sizeof(StAwtoDiag); ucI++)
    {
        ((volatile __xdata unsigned char *)0xF6D0)[ucI] = 0;
    }
    g_stAwtoDiag.ucMagic0 = 'A';
    g_stAwtoDiag.ucMagic1 = 'D';
    g_stAwtoDiag.ucVersion = 1;
    g_stAwtoDiag.ucSpare = ucWdt;               // bit7 = WDT overflow: last reset was the watchdog (#26)
    AwtoDiagStage(1);
}

// main-loop canary: the Timer2 ISR kicks the WDT only while this ran within _AWTO_WD_STALE_MS (AWTO_MAIN_ALIVE)
static void AwtoCanary(void)
{
    unsigned int usNow;
    unsigned int usPass;

    do
    {
        usNow = g_usTimerCounter;
    }
    while(usNow != g_usTimerCounter);
    usPass = usNow - g_stAwtoSafe.usLastPassMs;
    if(usPass > g_stAwtoSafe.usMaxPassMs)
    {
        g_stAwtoSafe.usMaxPassMs = usPass;
    }
    g_stAwtoSafe.usLastPassMs = usNow;
}

void AwtoDiagMainPass(void)
{
    g_stAwtoDiag.usHeartbeat++;
    AwtoCanary();
    AwtoDiagStage(5);
}

// Safe window before inputs + display start: ISP, EDID and debug 0x35 are up. Stays while usHold == magic
// (host: rtd_diag.py --hold; fw: after a WDT reset). Recovery path for an image that wedges on an input (#26).
void AwtoSafeBoot(void)
{
    unsigned int usStart = g_usTimerCounter;

    // warm reset (WDT / key / ISP) leaves the DDC + IIC slave state of the dead run: clear it before the window
    AWTO_BUS_RELEASE();
    g_stAwtoSafe.ucFlags |= _AWTO_SAFE_F_ACTIVE;
    while(((unsigned int)(g_usTimerCounter - usStart) < _AWTO_SAFE_BOOT_MS) || (g_stAwtoSafe.usHold == _AWTO_SAFE_HOLD_MAGIC))
    {
        AwtoCanary();
    }
    g_stAwtoSafe.ucFlags &= ~_AWTO_SAFE_F_ACTIVE;
    g_stAwtoSafe.usMaxPassMs = 0;               // the window is not a main-loop pass
}

// Timer2 counts since an arbitrary origin: whole 1 ms ticks x reload period + TH2:TL2 offset.
// EA off so the ISR cannot move g_usTimerCounter; a pending TF2 is an overflow whose tick is not yet counted.
static unsigned long AwtoDiagT2Now(void)
{
    unsigned char ucEa, ucF, ucH, ucL;
    unsigned int usTick, usRcap;

    ucEa = EA;
    EA = 0;
    do
    {
        ucF = TF2;
        usTick = g_usTimerCounter;
        do
        {
            ucH = TH2;
            ucL = TL2;
        }
        while(ucH != TH2);
    }
    while(ucF != TF2);
    usRcap = ((unsigned int)RCAP2H << 8) | RCAP2L;
    EA = ucEa;

    return ((unsigned long)(usTick + ucF) * (0x10000UL - usRcap)) + (((unsigned int)ucH << 8) | ucL) - usRcap;
}

// 1000 x one instruction (4 x 250 djnz), exact counts; EA off so the Timer2 ISR cannot add time.
static void AwtoDiagBench(void)
{
    unsigned long ulT;
    unsigned char ucEa;

    ucEa = EA;
    EA = 0;
    ulT = AwtoDiagT2Now();
    __asm
        push ar6
        push ar7
        push ar0
        push dpl
        push dph
        push acc
        mov dptr,#0xF6D0
        mov r0,#0xFF
        mov r6,#4
    10$:
        mov r7,#250
    11$:
        mov a,0x7f
        djnz r7,11$
        djnz r6,10$
        pop acc
        pop dph
        pop dpl
        pop ar0
        pop ar7
        pop ar6
    __endasm;
    g_stAwtoDiag.usBenchDirect = (unsigned int)(AwtoDiagT2Now() - ulT);
    ulT = AwtoDiagT2Now();
    __asm
        push ar6
        push ar7
        push ar0
        push dpl
        push dph
        push acc
        mov dptr,#0xF6D0
        mov r0,#0xFF
        mov r6,#4
    20$:
        mov r7,#250
    21$:
        movx a,@dptr
        djnz r7,21$
        djnz r6,20$
        pop acc
        pop dph
        pop dpl
        pop ar0
        pop ar7
        pop ar6
    __endasm;
    g_stAwtoDiag.usBenchXdata = (unsigned int)(AwtoDiagT2Now() - ulT);
    ulT = AwtoDiagT2Now();
    __asm
        push ar6
        push ar7
        push ar0
        push dpl
        push dph
        push acc
        mov dptr,#0xF6D0
        mov r0,#0xFF
        mov r6,#4
    30$:
        mov r7,#250
    31$:
        mov a,@r0
        djnz r7,31$
        djnz r6,30$
        pop acc
        pop dph
        pop dpl
        pop ar0
        pop ar7
        pop ar6
    __endasm;
    g_stAwtoDiag.usBenchIdata = (unsigned int)(AwtoDiagT2Now() - ulT);
    ulT = AwtoDiagT2Now();
    __asm
        push ar6
        push ar7
        push ar0
        push dpl
        push dph
        push acc
        mov dptr,#0xF6D0
        mov r0,#0xFF
        mov r6,#4
    40$:
        mov r7,#250
    41$:
        djnz r7,41$
        djnz r6,40$
        pop acc
        pop dph
        pop dpl
        pop ar0
        pop ar7
        pop ar6
    __endasm;
    g_stAwtoDiag.usBenchEmpty = (unsigned int)(AwtoDiagT2Now() - ulT);
    EA = ucEa;
}

void AwtoDiagSelfTest(void)
{
    unsigned long ulT;
    unsigned char ucI;

    if(g_stAwtoDiag.usDelayXms10 != 0)
    {
        return;
    }

    g_stAwtoDiag.ucDelay5usN = g_ucDelay5usN_Base;
    g_stAwtoDiag.ucRcap2h = RCAP2H;

    ulT = AwtoDiagT2Now();
    ScalerTimerDelayXms(10);
    g_stAwtoDiag.usDelayXms10 = (unsigned int)((AwtoDiagT2Now() - ulT) >> 2);

    ulT = AwtoDiagT2Now();
    for(ucI = 0; ucI < 200; ucI++)
    {
        ScalerDelay5us();
    }
    g_stAwtoDiag.usBusy1ms = (unsigned int)((AwtoDiagT2Now() - ulT) >> 2);

    AwtoDiagBench();
}
#endif
