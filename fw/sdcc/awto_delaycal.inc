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
#if(_AWTO_DELAY_SELFCAL == _ON)
unsigned char g_ucAwtoCal5;                                        // calibrated DELAY_5US / DELAY_XUS base counts, 0 = none yet
unsigned char g_ucAwtoCalX;
unsigned char g_ucAwtoCal5X;                                       // DELAY_5US_EXINT's own count (#54: copies differ by layout)

// N for 10 x 5 us at AWTO_DELAY_TARGET_PCT, from (n0, t0) and (n1, t1) on the line t = a + b*n; rounded up (never short)
static unsigned char AwtoCalSecant(unsigned char ucN0, unsigned int usT0, unsigned char ucN1, unsigned int usT1, unsigned int usNom)
{
    long lTgt = (long)usNom * AWTO_DELAY_TARGET_PCT / 100;
    long lDn = (long)ucN0 - ucN1, lDt = (long)usT0 - usT1, lNum, lQ, lN;

    if((lDn == 0) || (lDt == 0) || ((lDn > 0) != (lDt > 0)))
    {
        return ucN1;                                               // no slope: keep the proportional result
    }
    lNum = (lTgt - (long)usT1) * lDn;
    if(lDt < 0)
    {
        lNum = -lNum;
        lDt = -lDt;
    }
    lQ = lNum / lDt;                                               // truncates toward 0
    if(lQ * lDt < lNum)
    {
        lQ++;                                                      // ceil
    }
    lN = ucN1 + lQ;
    return (lN < 1) ? 1 : ((lN > 255) ? 255 : (unsigned char)lN);
}
#endif

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
#if(_AWTO_DELAY_SELFCAL == _ON)
    // #54: set the loop counts from this measurement: each 5 us copy (main / _EXINT, own counts) and the shorter XUS copy
    // land at AWTO_DELAY_TARGET_PCT of nominal; then measure again, so the diag (and health's 90..125 % check) sees the result.
    {
        unsigned long ulPer = 0x10000UL - usRcap;                 // Timer2 counts per 1 ms tick
        unsigned int usNom5 = (unsigned int)(ulPer * 50 / 1000);  // 10 x 5 us
        unsigned int usNomX = (unsigned int)(ulPer * 100 / 1000); // 100 us
        unsigned int usM5 = g_stAwtoDiag.usDelay5us10;
        unsigned int usI5 = g_stAwtoDiag.usDelay5usIsr10;
        unsigned int usMinX = (g_stAwtoDiag.usDelayXus100 < g_stAwtoDiag.usDelayXusIsr100) ? g_stAwtoDiag.usDelayXus100 : g_stAwtoDiag.usDelayXusIsr100;
        unsigned long ulN;

        if((RCAP2H == AWTO_DELAY_CAL_RCAP2H) && (usM5 != 0) && (usI5 != 0) && (usMinX != 0))      // M2PLL clock only (counts are per clock)
        {
            unsigned char ucN0 = g_ucDelay5usN_Base, ucN0X = g_ucAwtoDelay5usNX;

            ulN = ((unsigned long)g_ucDelay5usN_Base * AWTO_DELAY_TARGET_PCT * usNom5 + (100UL * usM5) - 1) / (100UL * usM5);
            g_ucAwtoCal5 = (ulN < 1) ? 1 : ((ulN > 255) ? 255 : (unsigned char)ulN);
            ulN = ((unsigned long)g_ucAwtoDelay5usNX * AWTO_DELAY_TARGET_PCT * usNom5 + (100UL * usI5) - 1) / (100UL * usI5);
            g_ucAwtoCal5X = (ulN < 1) ? 1 : ((ulN > 255) ? 255 : (unsigned char)ulN);
            g_ucAwtoDelay5usNX = g_ucAwtoCal5X;
            ulN = ((unsigned long)g_ucDelayXusN_Base * AWTO_DELAY_TARGET_PCT * usNomX + (100UL * usMinX) - 1) / (100UL * usMinX);
            g_ucAwtoCalX = (ulN < 1) ? 1 : ((ulN > 255) ? 255 : (unsigned char)ulN);
            g_ucDelay5usN_Base = g_ucAwtoCal5;
            g_ucDelayXusN_Base = g_ucAwtoCalX;
            g_stAwtoDiag.ucDelay5usN = g_ucDelay5usN_Base;
            AWTO_CAL_RUN(g_stAwtoDiag.usDelay5us10, AWTO_X10(DELAY_5US()));
            AWTO_CAL_RUN(g_stAwtoDiag.usDelayXus100, DELAY_XUS(100));
            AWTO_CAL_RUN(g_stAwtoDiag.usDelayXusIsr100, DELAY_XUS_EXINT(100));
            AWTO_CAL_RUN(g_stAwtoDiag.usDelay5usIsr10, AWTO_X10(DELAY_5US_EXINT()));
            // 5 us copies: time = fixed + N x step, so the proportional N above overshoots; one secant step from both points
            g_ucDelay5usN_Base = g_ucAwtoCal5 = AwtoCalSecant(ucN0, usM5, g_ucAwtoCal5, g_stAwtoDiag.usDelay5us10, usNom5);
            g_ucAwtoDelay5usNX = g_ucAwtoCal5X = AwtoCalSecant(ucN0X, usI5, g_ucAwtoCal5X, g_stAwtoDiag.usDelay5usIsr10, usNom5);
            g_stAwtoDiag.ucDelay5usN = g_ucDelay5usN_Base;
            AWTO_CAL_RUN(g_stAwtoDiag.usDelay5us10, AWTO_X10(DELAY_5US()));
            AWTO_CAL_RUN(g_stAwtoDiag.usDelay5usIsr10, AWTO_X10(DELAY_5US_EXINT()));
        }
    }
#endif
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
#if(_AWTO_FAST_BOOT == _ON)
    if(((ScalerGetByte(P7_F0_DISP_PG_R_CTRL) & _BIT7) != 0) || ((ScalerGetByte(P0_28_VIDEO_DISPLAY_CONTROL_REG) & _BIT5) != 0))
    {
        usMs = AWTO_T3_OWN_PATTERN_MS;                             // pattern gen or forced background: our own frame
    }
#endif
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
