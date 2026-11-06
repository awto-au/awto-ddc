// 4K60 measurement ring (awto-ddc#26), inserted into SysMain.c by keil2sdcc.py. Layout: RL6449_Project.h StAwtoMeas.
#if(_AWTO_MEAS4K == _ON)
__xdata StAwtoMeas g_stAwtoMeas;

void AwtoMeasInit(void)
{
    g_stAwtoMeas.ucMagic0 = 'M';
    g_stAwtoMeas.ucMagic1 = 'K';
    g_stAwtoMeas.ucVersion = 1;
    g_stAwtoMeas.ucArms = 0;
    g_stAwtoMeas.ucNSamp = 0;
    g_stAwtoMeas.ucNEv = 0;
    g_stAwtoMeas.pSampWr = &g_stAwtoMeas.stSamp[0];
    g_stAwtoMeas.ucState = 0;
}

// Timer2 ISR, state 1 only: one sample per 20 ms from the arm, ends at +1000 ms or mode ACTIVE. No locals that need helpers.
void AwtoMeasT2Sample(void)
{
    __xdata StAwtoMeasRec *pR;
    unsigned int usNow;

    usNow = g_usTimerCounter;
    if((signed int)(usNow - g_stAwtoMeas.usNextMs) < 0)
    {
        return;
    }
    g_stAwtoMeas.usNextMs = usNow + AWTO_MEAS_PERIOD_MS;
    if(g_stAwtoMeas.ucNSamp < AWTO_MEAS_SAMPLES)
    {
        pR = g_stAwtoMeas.pSampWr;
        pR->usMs = usNow;
        pR->ucMode = GET_MODE_STATE();
        pR->ucP0_02 = AWTO_MEAS_RD(0x0002);
        pR->ucP0_0C = AWTO_MEAS_RD(0x000C);
        pR->ucP5_B0 = AWTO_MEAS_RD(0x05B0);
        pR->ucP45_B0 = AWTO_MEAS_RD(0x45B0);
        pR->ucP5_2B = AWTO_MEAS_RD(0x052B);
        pR->ucP45_2B = AWTO_MEAS_RD(0x452B);
        pR->ucP0_3D = AWTO_MEAS_RD(0x003D);
        pR->ucP0_3E = AWTO_MEAS_RD(0x003E);
        pR->ucP0_40 = AWTO_MEAS_RD(0x0040);
        pR->ucP0_41 = AWTO_MEAS_RD(0x0041);
        pR->ucP0_45 = AWTO_MEAS_RD(0x0045);
        pR->ucP1_C4 = AWTO_MEAS_RD(0x01C4);
        pR->ucP1_C5 = AWTO_MEAS_RD(0x01C5);
        pR->ucP0_28 = AWTO_MEAS_RD(0x0028);
        g_stAwtoMeas.pSampWr = pR + 1;
        g_stAwtoMeas.ucNSamp++;
    }
    if(((unsigned int)(usNow - g_stAwtoMeas.usStartMs) >= AWTO_MEAS_WINDOW_MS) || (GET_MODE_STATE() == _MODE_STATUS_ACTIVE) ||
       (g_stAwtoMeas.ucNSamp >= AWTO_MEAS_SAMPLES))
    {
        g_stAwtoMeas.usEndMs = usNow;
        g_stAwtoMeas.ucState = 2;
    }
}

// Main context. Id 1 (MDomainControl entry) arms when idle (state 0); later ids log while state != 0.
void AwtoMeasEvent(unsigned char ucId, unsigned char ucArg, unsigned int usVal)
{
    unsigned int usNow;
    __xdata StAwtoMeasEv *pE;

    if((ucId == 1) && (g_stAwtoMeas.ucState == 0))
    {
        do
        {
            usNow = g_usTimerCounter;
        }
        while(usNow != g_usTimerCounter);
        g_stAwtoMeas.ucNSamp = 0;
        g_stAwtoMeas.ucNEv = 0;
        g_stAwtoMeas.pSampWr = &g_stAwtoMeas.stSamp[0];
        g_stAwtoMeas.usStartMs = usNow;
        g_stAwtoMeas.usNextMs = usNow;
        g_stAwtoMeas.ucArms++;
        g_stAwtoMeas.ucState = 1;
    }
    if((g_stAwtoMeas.ucState != 0) && (g_stAwtoMeas.ucNEv < AWTO_MEAS_EVENTS))
    {
        do
        {
            usNow = g_usTimerCounter;
        }
        while(usNow != g_usTimerCounter);
        pE = &g_stAwtoMeas.stEv[g_stAwtoMeas.ucNEv];
        pE->usMs = usNow;
        pE->ucId = ucId;
        pE->ucArg = ucArg;
        pE->usVal = usVal;
        g_stAwtoMeas.ucNEv++;
    }
}
#endif
