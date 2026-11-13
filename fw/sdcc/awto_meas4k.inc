// 4K60 measurement ring (awto-ddc#26), inserted into SysMain.c by keil2sdcc.py. Layout: RL6449_Project.h StAwtoMeas.
#if(_AWTO_MEAS4K == _ON)
__xdata StAwtoMeas g_stAwtoMeas;

void AwtoMeasInit(void)
{
    g_stAwtoMeas.ucMagic0 = 'M';
    g_stAwtoMeas.ucMagic1 = 'K';
    g_stAwtoMeas.ucVersion = 2;                 // 2: ucSampMax in the header
    g_stAwtoMeas.ucSampMax = AWTO_MEAS_SAMPLES;
    g_stAwtoMeas.ucArms = 0;
    g_stAwtoMeas.ucNSamp = 0;
    g_stAwtoMeas.ucNEv = 0;
    g_stAwtoMeas.pSampWr = &g_stAwtoMeas.stSamp[0];
    g_stAwtoMeas.ucState = 0;
}

// Timer2 ISR, state 1 only: one sample per AWTO_MEAS_PERIOD_MS from the arm, ends at +1000 ms or mode ACTIVE. No locals that need helpers.
void AwtoMeasT2Sample(void)
{
    __xdata StAwtoMeasRec *pR;
    unsigned int usNow;

    usNow = d_g_usTimerCounter;
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
        pR->ucP0_02 = AWTO_MEAS_RD(AWTO_R_STATUS0);
        pR->ucP0_0C = AWTO_MEAS_RD(AWTO_R_WATCH_DOG_CTRL0);
        pR->ucP5_B0 = AWTO_MEAS_RD(AWTO_R_DISP_M1_FIFO_STATUS);
        pR->ucP45_B0 = AWTO_MEAS_RD(AWTO_R_DISP_M2_FIFO_STATUS);
        pR->ucP5_2B = AWTO_MEAS_RD(AWTO_R_CAP_M1_FIFO_STATUS);
        pR->ucP45_2B = AWTO_MEAS_RD(AWTO_R_CAP_M2_FIFO_STATUS);
        pR->ucP0_3D = AWTO_MEAS_RD(AWTO_R_IV_DV_DELAY_CLK_FINE);
        pR->ucP0_3E = AWTO_MEAS_RD(AWTO_R_IVS2DVS_DLY_LINE_H);
        pR->ucP0_40 = AWTO_MEAS_RD(AWTO_R_IVS2DVS_DLY_LINE_L);
        pR->ucP0_41 = AWTO_MEAS_RD(AWTO_R_IVS2DVS_DLY_TUNE_ODD);
        pR->ucP0_45 = AWTO_MEAS_RD(AWTO_R_LAST_LINE_L);
        pR->ucP1_C4 = AWTO_MEAS_RD(AWTO_R_DCLK_FINE_TUNE_OFFSET_MSB);
        pR->ucP1_C5 = AWTO_MEAS_RD(AWTO_R_DCLK_FINE_TUNE_OFFSET_LSB);
        pR->ucP0_28 = AWTO_MEAS_RD(AWTO_R_VIDEO_DISPLAY_CONTROL_REG);
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
            usNow = d_g_usTimerCounter;
        }
        while(usNow != d_g_usTimerCounter);
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
            usNow = d_g_usTimerCounter;
        }
        while(usNow != d_g_usTimerCounter);
        pE = &g_stAwtoMeas.stEv[g_stAwtoMeas.ucNEv];
        pE->usMs = usNow;
        pE->ucId = ucId;
        pE->ucArg = ucArg;
        pE->usVal = usVal;
        g_stAwtoMeas.ucNEv++;
    }
}
#endif
