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

    for(ucI = 0; ucI < sizeof(StAwtoDiag); ucI++)
    {
        ((volatile __xdata unsigned char *)0xF6D0)[ucI] = 0;
    }
    g_stAwtoDiag.ucMagic0 = 'A';
    g_stAwtoDiag.ucMagic1 = 'D';
    g_stAwtoDiag.ucVersion = (_AWTO_DBGISR == _ON) ? 2 : 1;
    AwtoDiagStage(1);
}

void AwtoDiagMainPass(void)
{
    static unsigned int usLastMs;
    static unsigned int usLastHb;
    unsigned int usNow;

    g_stAwtoDiag.usHeartbeat++;
    do
    {
        usNow = g_usTimerCounter;
    }
    while(usNow != g_usTimerCounter);
    if((unsigned int)(usNow - usLastMs) >= 1000)
    {
        g_stAwtoDiag.usLoopRate = g_stAwtoDiag.usHeartbeat - usLastHb;
        usLastHb = g_stAwtoDiag.usHeartbeat;
        usLastMs = usNow;
    }
    AwtoDiagStage(5);
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
