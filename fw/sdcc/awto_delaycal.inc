#if((_AWTO_DIAG == _ON) && (_AWTO_DIAG_DELAYCAL == _ON))      // awto: #53.6/#54 delay calibration inside the panel T3 wait; docs/diag-block.md
// Timer2 snapshot (EA off) and counts since an arbitrary origin: whole ticks x reload period + TH2:TL2 offset.
// A pending TF2 is an overflow whose tick the ISR has not counted yet.
typedef struct
{
    unsigned int usTick;
    unsigned char ucF, ucH, ucL;
} StAwtoT2Snap;

static void AwtoDiagT2Snap(__xdata StAwtoT2Snap *p)
{
    unsigned char ucEa = EA;

    EA = 0;
    do
    {
        p->ucF = TF2;
        p->usTick = g_usTimerCounter;
        do
        {
            p->ucH = TH2;
            p->ucL = TL2;
        }
        while(p->ucH != TH2);
    }
    while(p->ucF != TF2);
    EA = ucEa;
}

// Counts from snapshot a to b (tick difference mod 65536, so a g_usTimerCounter wrap is harmless).
static unsigned long AwtoDiagT2Diff(__xdata StAwtoT2Snap *a, __xdata StAwtoT2Snap *b, unsigned int usRcap)
{
    unsigned int usTicks = (unsigned int)((b->usTick + b->ucF) - (a->usTick + a->ucF));

    return ((unsigned long)usTicks * (0x10000UL - usRcap)) + (((unsigned int)b->ucH << 8) | b->ucL) - (((unsigned int)a->ucH << 8) | a->ucL);
}

static __xdata StAwtoT2Snap s_stSnapA, s_stSnapB, s_stT3A, s_stT3B;

// Snapshot pair around a body, EA off for the body (<= 100 us: the Timer2 ISR only runs later, TF2 holds one overflow);
// result = raw counts minus the empty snapshot pair, never below 0. Bodies are unrolled: loop overhead would not cancel.
#define AWTO_CAL_RUN(dst, body)                                  \
    do                                                            \
    {                                                             \
        EA = 0;                                                   \
        AwtoDiagT2Snap(&s_stSnapA);                               \
        body;                                                     \
        AwtoDiagT2Snap(&s_stSnapB);                               \
        EA = ucEa;                                                \
        ulD = AwtoDiagT2Diff(&s_stSnapA, &s_stSnapB, usRcap);   \
        (dst) = (ulD > ulOvh) ? (unsigned int)(ulD - ulOvh) : 0;  \
    }                                                             \
    while(0)

#define AWTO_X10(op)    op; op; op; op; op; op; op; op; op; op

static void AwtoDiagDelayCal(void)
{
    unsigned long ulD, ulOvh;
    unsigned int usRcap;
    unsigned char ucEa = EA;

    g_stAwtoDiag.ucDelay5usN = g_ucDelay5usN_Base;
    g_stAwtoDiag.ucRcap2h = RCAP2H;
    usRcap = ((unsigned int)RCAP2H << 8) | RCAP2L;

    ScalerTimerDelayXms(1);                                       // align to a tick edge: the next 10 ticks are exact
    AwtoDiagT2Snap(&s_stSnapA);
    ScalerTimerDelayXms(10);
    AwtoDiagT2Snap(&s_stSnapB);
    g_stAwtoDiag.usDelayXms10 = (unsigned int)((AwtoDiagT2Diff(&s_stSnapA, &s_stSnapB, usRcap)) >> 2);

    EA = 0;
    AwtoDiagT2Snap(&s_stSnapA);
    AwtoDiagT2Snap(&s_stSnapB);
    EA = ucEa;
    ulOvh = AwtoDiagT2Diff(&s_stSnapA, &s_stSnapB, usRcap);

    AWTO_CAL_RUN(g_stAwtoDiag.usDelay5us10, AWTO_X10(DELAY_5US()));
    AWTO_CAL_RUN(g_stAwtoDiag.usDelayXus100, DELAY_XUS(100));
    AWTO_CAL_RUN(g_stAwtoDiag.usDelayXusIsr100, DELAY_XUS_EXINT(100));
    AWTO_CAL_RUN(g_stAwtoDiag.usDelay5usIsr10, AWTO_X10(DELAY_5US_EXINT()));
}

// ScalerTimerDelayXms(usMs) for the panel T3 wait with the calibration run inside it (once per boot): the wait ends at
// the same Timer2 tick as before (tick count taken at entry + usMs), so the test costs no boot time.
void AwtoDiagPanelT3Wait(unsigned int usMs)
{
    unsigned int usN0, usNow;
    unsigned int usRcap = ((unsigned int)RCAP2H << 8) | RCAP2L;

    if(TR2 == _OFF)                                               // as ScalerTimerDelayXms: no tick, no wait
    {
        return;
    }
    do
    {
        usN0 = g_usTimerCounter;
    }
    while(usN0 != g_usTimerCounter);
    AwtoSwEvent(AWTO_SW_EV_T3, 0);
    AwtoDiagT2Snap(&s_stT3A);
    if(g_stAwtoDiag.usDelayXms10 == 0)
    {
        AwtoDiagDelayCal();
    }
    do
    {
        do
        {
            usNow = g_usTimerCounter;
        }
        while(usNow != g_usTimerCounter);
    }
    while((unsigned int)(usNow - usN0) < usMs);
    AwtoDiagT2Snap(&s_stT3B);
    AwtoSwEvent(AWTO_SW_EV_T3, 1);
    g_stAwtoDiag.usT3Wait64 = (unsigned int)(AwtoDiagT2Diff(&s_stT3A, &s_stT3B, usRcap) >> 6);
}
#endif
