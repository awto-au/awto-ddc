// Diag block functions (#23), inserted into SysMain.c by keil2sdcc.py. Layout: RL6449_Project.h StAwtoDiag.
#if(_AWTO_DIAG == _ON)
void AwtoDiagStage(unsigned char ucStage)
{
    unsigned int usNow;

    if((ucStage > g_stAwtoDiag.ucStage) && (ucStage <= 8))      // awto: #53.17 usStageMs[7] is the last
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
        ((volatile __xdata unsigned char *)&g_stAwtoDiag)[ucI] = 0;      // awto: #53.18
    }
    g_stAwtoDiag.ucMagic0 = 'A';
    g_stAwtoDiag.ucMagic1 = 'D';
    g_stAwtoDiag.ucVersion = (_AWTO_DBGISR == _ON) ? 2 : 1;
    AwtoOsdOfsInit();
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

#if(_AWTO_DIAG_SELFTEST == _ON)      // awto: #53.6 off by default (boot time), numbers in docs/diag-block.md
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

}
#endif
#endif
