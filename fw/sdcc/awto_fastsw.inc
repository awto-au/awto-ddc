// #60 cached fast input switch, system half. Inserted into SysSource.c by keil2sdcc.py; RL6449_Project.h _AWTO_FAST_SWITCH.
// - Cache per port D1..D3 (scaler half: fw/sdcc/awto_fastsw_scaler.inc), stored at each full-path first ACTIVE.
// - Taken only in ACTIVE, target timing + colour = what is on screen, target receiver stable; I/M/D-domain set-up kept.
// - Unblank once the new port's off-line measure matches the cache; mismatch / timeout = full path (reset to SEARCH).
#if(_AWTO_FAST_SWITCH == _ON)
typedef struct
{
    BYTE ucValid;
    BYTE ucSourceType;
    BYTE pucScaler[AWTO_FAST_SCALER_BYTES];
} StAwtoSwCache;

extern bit SysJudgeCheckStatus(void);           // SysJudge.c, no header prototype
static __xdata StAwtoSwCache s_pstAwtoSwCache[3];
__xdata BYTE g_ucAwtoFastPending;
static __xdata WORD s_usAwtoFastT0;
static __xdata BYTE s_ucAwtoFastFrameMs;
static __xdata BYTE s_ucAwtoFastWatch;          // diagnostic: after a fast unblank, log the first M-domain error flags once
static __xdata WORD s_usAwtoFastNextMs;         // next check, ms after the switch; 0 = flags not cleared yet

static WORD AwtoFastNow(void)
{
    WORD usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

void AwtoSwCacheStore(void)
{
    BYTE ucI = SysSourceGetInputPort() - _D1_INPUT_PORT;

    if(ucI >= 3)
    {
        return;
    }
    s_pstAwtoSwCache[ucI].ucSourceType = GET_SOURCE_TYPE(g_ucSearchIndex);
    AwtoFastScalerSave(s_pstAwtoSwCache[ucI].pucScaler);
    s_pstAwtoSwCache[ucI].ucValid = 1;
}

unsigned char AwtoSwFast(unsigned char ucPort)  // _TRUE = fast path taken, no mode reset
{
    BYTE ucI = ucPort - _D1_INPUT_PORT;
    BYTE ucType;
    bit bStable = _FALSE;

    ucType = ((ucI >= 3) || (s_pstAwtoSwCache[ucI].ucValid == 0)) ? 1 : (GET_MODE_STATE() != _MODE_STATUS_ACTIVE) ? 6 :
             (g_ucAwtoFastPending != 0) ? 7 : (ucPort == SysSourceGetInputPort()) ? 8 :
             (GET_MODE_RESET_TARGET() != _MODE_ACTION_NO_RESET_MODE) ? 9 : 0;
    if(ucType != 0)
    {
        AwtoSwEvent(AWTO_SW_EV_FAST, ucType);
        return _FALSE;
    }
    ucType = AwtoFastScalerMatch(s_pstAwtoSwCache[ucI].pucScaler);
    if(ucType != 0)
    {
        AwtoSwEvent(AWTO_SW_EV_FAST, 0x20 | ucType);
        return _FALSE;
    }
    ucType = s_pstAwtoSwCache[ucI].ucSourceType;
#if(_DP_SUPPORT == _ON)
    if(ucType == _SOURCE_DP)
    {
        bStable = ScalerDpStableDetect(ucPort);
    }
#endif
#if((_DVI_SUPPORT == _ON) || (_HDMI_SUPPORT == _ON))
    if((ucType == _SOURCE_HDMI) || (ucType == _SOURCE_DVI))
    {
        bStable = ScalerTMDSStableDetect(ucPort, ucType);
    }
#endif
    if(bStable == _FALSE)
    {
        AwtoSwEvent(AWTO_SW_EV_FAST, 3);
        return _FALSE;
    }

    ScalerDDomainBackgroundEnable(_ENABLE);
    SET_SOURCE_JUDGE(g_ucSearchIndex, _FALSE);
    g_ucSearchIndex = SysSourceConvertSearchPort(ucPort);
    SET_SOURCE_TYPE(g_ucSearchIndex, ucType);
    SET_SOURCE_JUDGE(g_ucSearchIndex, _TRUE);
    s_ucAwtoFastFrameMs = AwtoFastScalerApply(s_pstAwtoSwCache[ucI].pucScaler, ucType, ucPort);
    s_usAwtoFastT0 = AwtoFastNow();
    s_usAwtoFastNextMs = 0;
    s_ucAwtoFastWatch = 0;
    g_ucAwtoFastPending = ucPort;
    AwtoSwEvent(AWTO_SW_EV_FAST, 0);
    return _TRUE;
}

void AwtoSwFastPoll(void)                       // once per main-loop pass: finish (unblank) or abandon a fast switch
{
    WORD usDt;
    BYTE ucWhy;

    if(g_ucAwtoFastPending == 0)
    {
#if(_AWTO_SW_MARKS == _ON)
        if((s_ucAwtoFastWatch != 0) && (AwtoFastScalerStatus() != 0))
        {
            s_ucAwtoFastWatch = 0;
            AwtoSwEvent(AWTO_SW_EV_FAST_FLAGS, AwtoFastScalerStatus());
        }
#endif
        return;
    }
    if((GET_MODE_STATE() != _MODE_STATUS_ACTIVE) || (SysSourceGetInputPort() != g_ucAwtoFastPending))
    {
        g_ucAwtoFastPending = 0;                // the SDK reset the mode itself: its full path unblanks
        AwtoSwEvent(AWTO_SW_EV_FAST, 4);
        return;
    }
    usDt = AwtoFastNow() - s_usAwtoFastT0;
    if(usDt < (WORD)s_ucAwtoFastFrameMs * 3)    // 3 frames: the frame-sync phase jump (one short / long frame) is over
    {
        return;
    }
    if(s_usAwtoFastNextMs == 0)
    {
        AwtoFastScalerClearStatus(_TRUE);
        s_usAwtoFastNextMs = usDt + s_ucAwtoFastFrameMs;
        return;
    }
    if(usDt < s_usAwtoFastNextMs)               // one frame after each clear: clean flags and an off-line measure result
    {
        return;
    }
    ucWhy = AwtoFastScalerMeasureOk();
    if(SysSourceStableCheck() == _FALSE)
    {
        ucWhy |= 0x08;
    }
    if((ucWhy == 0) && (ScalerMeasureTimingChange(GET_SOURCE_TYPE(g_ucSearchIndex), g_ucAwtoFastPending) == _TRUE))
    {
        ucWhy |= 0x10;
    }
    if((ucWhy == 0) && (SysJudgeCheckStatus() == _FALSE))      // the judge's own check, held off until now
    {
        ucWhy |= 0x20;
    }
    if(ucWhy == 0)
    {
        g_ucAwtoFastPending = 0;
        ScalerGlobalFirstActiveProc(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort());
        UserCommonInterfaceOsdActiveProc();     // NVRAM search port, DDC/CI (debug slave) to the new port, info pop-up, unblank
        s_ucAwtoFastWatch = 1;
        return;
    }
    if(usDt >= (WORD)s_ucAwtoFastFrameMs * 8)   // still failing 8 frames after the switch: full path
    {
        g_ucAwtoFastPending = 0;
        AwtoSwEvent(AWTO_SW_EV_FAST, 5);
        AwtoSwEvent(AWTO_SW_EV_FAST_WHY, ucWhy);
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
        return;
    }
    AwtoFastScalerClearStatus(_FALSE);          // re-lock still settling: clear the flags again, check one frame later
    s_usAwtoFastNextMs = usDt + s_ucAwtoFastFrameMs;
}
#endif
