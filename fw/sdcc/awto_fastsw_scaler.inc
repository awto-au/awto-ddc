// #60 fast switch, scaler half: per-port snapshot of timing, sync reference, colour info, path0 source, pixel clock as an
// opaque AWTO_FAST_SCALER_BYTES buffer (system half: fw/sdcc/awto_fastsw.inc). Inserted into ScalerMeasure.c by keil2sdcc.py.
#if(_AWTO_FAST_SWITCH == _ON)
typedef struct
{
    StructTimingInfo stTiming;
    StructMeasureSyncData stSync;
    StructColorInfo stColor;
    WORD usPixelClk;
    BYTE ucFcSrc;                               // P31_00 path0 input select [7:4]
    BYTE pucIvs2Dvs[6];                         // P0_3D..P0_42 IVS-to-DVS delay (P0_3F: bits 5,4,1,0 only); per port, vstart differs
} StAwtoFastScaler;
typedef char AwtoFastScalerSizeCheck[(sizeof(StAwtoFastScaler) <= AWTO_FAST_SCALER_BYTES) ? 1 : -1];

void AwtoFastScalerSave(BYTE __xdata *pucBuf)
{
    __xdata StAwtoFastScaler *pstS = (__xdata StAwtoFastScaler *)pucBuf;

    memcpy(&pstS->stTiming, &g_stInputTimingData, sizeof(StructTimingInfo));
    memcpy(&pstS->stSync, &g_stMeasureSyncHV, sizeof(StructMeasureSyncData));
    memcpy(&pstS->stColor, &isr_g_stColorInfo, sizeof(StructColorInfo));
    pstS->usPixelClk = GET_INPUT_PIXEL_CLK();
    pstS->ucFcSrc = ScalerGetByte(P31_00_FC_INPUT_SEL_P01) & 0xF0;
    pstS->pucIvs2Dvs[0] = ScalerGetByte(P0_3D_IV_DV_DELAY_CLK_FINE);
    pstS->pucIvs2Dvs[1] = ScalerGetByte(P0_3E_IVS2DVS_DLY_LINE_H);
    pstS->pucIvs2Dvs[2] = ScalerGetByte(P0_3F_DISPLAY_ALIGN_CONTROL) & (_BIT5 | _BIT4 | _BIT1 | _BIT0);
    pstS->pucIvs2Dvs[3] = ScalerGetByte(P0_40_IVS2DVS_DLY_LINE_L);
    pstS->pucIvs2Dvs[4] = ScalerGetByte(P0_41_IVS2DVS_DLY_TUNE_ODD);
    pstS->pucIvs2Dvs[5] = ScalerGetByte(P0_42_IVS2DVS_DLY_TUNE_EVEN);
}

static bit AwtoFastSameBytes(BYTE __xdata *pucA, BYTE __xdata *pucB, BYTE ucN)     // no lib memcmp: it would grow the residual area
{
    while(ucN-- != 0)
    {
        if(*pucA++ != *pucB++)
        {
            return _FALSE;
        }
    }
    return _TRUE;
}

static bit AwtoFastNear(WORD usA, WORD usB, WORD usTol)
{
    return (((usA > usB) ? (usA - usB) : (usB - usA)) <= usTol);
}

BYTE AwtoFastScalerMatch(BYTE __xdata *pucBuf) // 0 = same geometry, rate and colour as on screen (display set-up stays valid), else field 1..9
{
    __xdata StAwtoFastScaler *pstS = (__xdata StAwtoFastScaler *)pucBuf;

    if((pstS->stTiming.usHWidth != g_stInputTimingData.usHWidth) || (pstS->stTiming.usVHeight != g_stInputTimingData.usVHeight))
    {
        return 1;
    }
    if((AwtoFastNear(pstS->stTiming.usHTotal, g_stInputTimingData.usHTotal, 2) == _FALSE) ||
       (AwtoFastNear(pstS->stTiming.usVTotal, g_stInputTimingData.usVTotal, 2) == _FALSE))         // SDK timing-change tolerance
    {
        return 2;
    }
    // H/V start: DP (MSA) and TMDS (sync measure) differ by a few lines; digital capture is DE-relative,
    // a FIFO / watchdog error from the IVS-to-DVS phase is caught before the unblank
    if(AwtoFastNear(pstS->stTiming.usHStart, g_stInputTimingData.usHStart, 8) == _FALSE)
    {
        return 3;
    }
    if(AwtoFastNear(pstS->stTiming.usVStart, g_stInputTimingData.usVStart, 4) == _FALSE)
    {
        return 4;
    }
    if(pstS->stTiming.b1Interlace != g_stInputTimingData.b1Interlace)
    {
        return 5;
    }
    if(AwtoFastNear(pstS->stTiming.usVFreq, g_stInputTimingData.usVFreq, 5) == _FALSE)                        // 0.5 Hz
    {
        return 6;
    }
    if(AwtoFastNear(pstS->usPixelClk, GET_INPUT_PIXEL_CLK(), GET_INPUT_PIXEL_CLK() / 100) == _FALSE)          // 1 %
    {
        return 7;
    }
    if(AwtoFastSameBytes((BYTE __xdata *)&pstS->stColor, (BYTE __xdata *)&isr_g_stColorInfo, sizeof(StructColorInfo)) == _FALSE)
    {
        return 8;
    }
    return 0;
}

BYTE AwtoFastScalerApply(BYTE __xdata *pucBuf, BYTE ucSourceType, BYTE ucPort)    // returns the frame period, ms
{
    __xdata StAwtoFastScaler *pstS = (__xdata StAwtoFastScaler *)pucBuf;

    ScalerGlobalWatchDog(_DISABLE);             // else the IVS phase jump fires the watchdog: free run + forced background
    if(ucSourceType == _SOURCE_DP)
    {
        AWTO_IDLE_TMDS_OFF();                   // as ScalerSyncInterfaceSwitch does for a non-TMDS port
    }
    ScalerSetBit(P31_00_FC_INPUT_SEL_P01, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), pstS->ucFcSrc);
    ScalerSetByte(P0_3D_IV_DV_DELAY_CLK_FINE, pstS->pucIvs2Dvs[0]);
    ScalerSetByte(P0_3E_IVS2DVS_DLY_LINE_H, pstS->pucIvs2Dvs[1]);
    ScalerSetBit(P0_3F_DISPLAY_ALIGN_CONTROL, ~(_BIT5 | _BIT4 | _BIT1 | _BIT0), pstS->pucIvs2Dvs[2]);
    ScalerSetByte(P0_40_IVS2DVS_DLY_LINE_L, pstS->pucIvs2Dvs[3]);
    ScalerSetByte(P0_41_IVS2DVS_DLY_TUNE_ODD, pstS->pucIvs2Dvs[4]);
    ScalerSetByte(P0_42_IVS2DVS_DLY_TUNE_EVEN, pstS->pucIvs2Dvs[5]);
    memcpy(&g_stInputTimingData, &pstS->stTiming, sizeof(StructTimingInfo));
    memcpy(&g_stMeasureSyncHV, &pstS->stSync, sizeof(StructMeasureSyncData));
    SET_INPUT_PIXEL_CLK(pstS->usPixelClk);
    ScalerMeasureSetOfflineMeasure(ucSourceType, ucPort);
    ScalerMeasureInterlaceInitial(ucSourceType, ucPort);       // the judge's interlace double check reads this port's detector
#if(_D2_TMDS_SUPPORT == _ON)
    if(ucPort == _D2_INPUT_PORT)
    {
        ScalerSetBit(P71_E6_HDMI_FREQDET_CTRL, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));     // freq-detect IRQ back on (flag cleared)
    }
#endif
#if(_D3_TMDS_SUPPORT == _ON)
    if(ucPort == _D3_INPUT_PORT)
    {
        ScalerSetBit(P72_E6_HDMI_FREQDET_CTRL, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
    }
#endif
    return (BYTE)((10000 + pstS->stTiming.usVFreq - 1) / pstS->stTiming.usVFreq);
}

void AwtoFastScalerClearStatus(BYTE ucFirst)    // after the switch: first call re-arms the watchdogs (clears all flags), later ones clear flags only
{
    if(ucFirst == _TRUE)
    {
        ScalerMeasureUpdateOnlineMeasureResult();   // on-line measure restarted on the new input (its over-range WD tracks frame-to-frame deltas)
        ScalerGlobalWatchDog(_ENABLE);
        return;
    }
    ScalerSetByte(P0_02_STATUS0, 0xFF);
    ScalerSetBit(P16_16_MEAS_HS_VS_DELTA_IRQ, ~(_BIT6 | _BIT5 | _BIT4), (_BIT6 | _BIT5 | _BIT4));
    ScalerSetByte(P16_03_MEAS_ERROR_FLG0, 0xFF);
}

BYTE AwtoFastScalerStatus(void)                // P0_02 HV-sync error / FIFO bits and the watchdog flag P0_0C bit0
{
    return (ScalerGetBit(P0_02_STATUS0, (_BIT6 | _BIT5 | _BIT1 | _BIT0)) | ScalerGetBit(P0_0C_WATCH_DOG_CTRL0, _BIT0) << 7);
}

BYTE AwtoFastScalerMeasureOk(void)             // 0 = off-line measure done, no on-line watchdog, no FIFO / HV-sync error since the clear
{
    BYTE ucWhy = 0;

    if(ScalerGetBit(P30_02_MEAS_CTL1, _BIT7) != 0x00)
    {
        ucWhy |= 0x01;
    }
    if(ScalerMeasureWatchdogStatus() == _TRUE)
    {
        ucWhy |= 0x02;
    }
    if(ScalerMDomainMemoryCheck() == _FALSE)
    {
        ucWhy |= 0x04;
    }
    return ucWhy;
}
#endif
