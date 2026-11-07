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
extern void SysPowerSetTargetPowerStatus(EnumPowerStatus enumPorStatus);   // SysPower.c, no header prototype
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
#if(_AWTO_WAKE_HOLD == _ON)
    g_ucAwtoNoHold = 0;
#endif
}

static void AwtoSwFastGo(BYTE ucI, BYTE ucPort, BYTE ucType)
{
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
}

static bit AwtoRxStable(BYTE ucPort, BYTE ucType)
{
#if(_DP_SUPPORT == _ON)
    if(ucType == _SOURCE_DP)
    {
        return ScalerDpStableDetect(ucPort);
    }
#endif
#if((_DVI_SUPPORT == _ON) || (_HDMI_SUPPORT == _ON))
    if((ucType == _SOURCE_HDMI) || (ucType == _SOURCE_DVI))
    {
        return ScalerTMDSStableDetect(ucPort, ucType);
    }
#endif
    return _FALSE;
}

#if(_AWTO_WAKE_HOLD == _ON)
static __xdata BYTE s_ucAwtoHoldLevel;          // 1 L1, 2 L2, 0 = backlight / panel already back on

static bit AwtoRxPreDetect(BYTE ucPort, BYTE ucType)
{
#if(_DP_SUPPORT == _ON)
    if(ucType == _SOURCE_DP)
    {
        return ScalerDpNormalPreDetect(ucPort);
    }
#endif
#if((_DVI_SUPPORT == _ON) || (_HDMI_SUPPORT == _ON))
    if((ucType == _SOURCE_HDMI) || (ucType == _SOURCE_DVI))
    {
        return ScalerTMDSNormalPreDetect(ucPort);
    }
#endif
    return _FALSE;
}

static bit AwtoRxRescan(BYTE ucPort, BYTE ucType)  // held port: receiver set up again by the SDK's own pre-detect + scan
{
    if(AwtoRxStable(ucPort, ucType) == _TRUE)
    {
        return _TRUE;
    }
    if(AwtoRxPreDetect(ucPort, ucType) == _FALSE)
    {
        return _FALSE;
    }
    AwtoSwEvent(AWTO_SW_EV_HOLD, 8);
    if(s_ucAwtoHoldLevel == 2)                  // L2: panel up (T1, eDP HPD, T3; black) before the scan, not after it
    {
        UserCommonInterfacePanelPowerAction(_BACKLIGHT_ON);
        AwtoSwEvent(AWTO_SW_EV_HOLD, 6);
        s_ucAwtoHoldLevel = 0;
    }
#if(_DP_SUPPORT == _ON)
    if(ucType == _SOURCE_DP)
    {
        return (ScalerDpScanInputPort(ucPort) == ucType);
    }
#endif
    return (ScalerTMDSScanInputPort(ucPort, GET_INPUTPORT_TYPE(g_ucSearchIndex)) == ucType);
}

// #78 power levels: signal lost in ACTIVE = hold the set-up (judge held, mode stays ACTIVE), L1 backlight off at once,
// L2 panel off after usL2Sec, L3 = the SDK path (search, no signal, power saving) after usL3Sec. Signal back on the
// held port = the fast path (cache) with a backlight-on before the unblank. Settings: g_stAwtoPower (test cmds 0x36..0x3A).
__xdata StAwtoPower g_stAwtoPower = {1, 1, 1, AWTO_L2_SEC, AWTO_L3_SEC};
__xdata BYTE g_ucAwtoHold;                      // port held, 0 = none
static __xdata WORD s_usAwtoHoldSec;
static __xdata WORD s_usAwtoHoldMs;             // ms into the current second / last 10 ms check
static __xdata BYTE s_ucAwtoHoldTries;
static __xdata BYTE s_ucAwtoHoldOther;
__xdata BYTE g_ucAwtoWakePending;               // a fast wake is in flight (its unblank stamps s_usAwtoWokeMs)
static __xdata WORD s_usAwtoWokeMs;
static __xdata BYTE s_ucAwtoWoke;
__xdata BYTE g_ucAwtoNoHold;                    // released to the SDK: no new hold until a full-path ACTIVE (AwtoSwCacheStore)

bit AwtoWakeHold(void)                          // judge check failed in ACTIVE: _TRUE = held here, no SDK mode reset
{
    BYTE ucI = SysSourceGetInputPort() - _D1_INPUT_PORT;

    if((g_stAwtoPower.ucL1 == 0) || (g_ucAwtoNoHold != 0) || (GET_MODE_STATE() != _MODE_STATUS_ACTIVE) || (g_ucAwtoFastPending != 0) ||
       (ucI >= 3) || (s_pstAwtoSwCache[ucI].ucValid == 0) || (AwtoFastScalerMatch(s_pstAwtoSwCache[ucI].pucScaler) != 0) ||
       ((s_ucAwtoWoke != 0) && ((WORD)(AwtoFastNow() - s_usAwtoWokeMs) < AWTO_REHOLD_MS)))     // judge failed right after a fast wake: full path, no blink loop
    {
        return _FALSE;
    }
    ScalerDDomainBackgroundEnable(_ENABLE);
    ScalerGlobalWatchDog(_DISABLE);             // no free run: the display stays set up for the same timing
    PCB_BACKLIGHT_POWER_PIN(_LIGHT_CONTROL_OFF);    // L1: enable pin only; eDP stream + SDK panel state stay (SDK BACKLIGHT_OFF: 300 ms)
    g_ucAwtoHold = SysSourceGetInputPort();
    s_ucAwtoHoldLevel = 1;
    s_usAwtoHoldSec = 0;
    s_usAwtoHoldMs = AwtoFastNow();
    s_ucAwtoHoldTries = 0;
    AwtoSwEvent(AWTO_SW_EV_HOLD, 1);
    return _TRUE;
}

static void AwtoHoldBacklightSdk(void)          // leaving an L1 hold to the SDK: its own backlight-off, so its state is right
{
    if(s_ucAwtoHoldLevel == 1)
    {
        PCB_BACKLIGHT_POWER_PIN(_LIGHT_CONTROL_ON);
        UserCommonInterfacePanelPowerAction(_BACKLIGHT_OFF);
    }
    s_ucAwtoHoldLevel = 0;
}

static void AwtoWakeRelease(BYTE ucWhy)         // 3: L3 = SDK power saving now (no search, no lit no-signal OSD); else search
{
    AwtoHoldBacklightSdk();
    g_ucAwtoHold = 0;
    g_ucAwtoNoHold = 1;
    g_ucAwtoWakePending = 0;
    AwtoSwEvent(AWTO_SW_EV_HOLD, ucWhy);
    if(ucWhy == 3)
    {
        SysPowerSetTargetPowerStatus(_POWER_STATUS_SAVING);    // not forced: a signal still wakes it (PS pre-detect)
    }
    else
    {
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
    }
}

void AwtoWakePoll(void)                         // every pass while held
{
    BYTE ucI;
    WORD usNow;

    if(GET_MODE_STATE() != _MODE_STATUS_ACTIVE)
    {
        AwtoHoldBacklightSdk();
        g_ucAwtoHold = 0;                       // the SDK reset the mode itself
        AwtoSwEvent(AWTO_SW_EV_HOLD, 0x10);
        return;
    }
    usNow = AwtoFastNow();
    if((WORD)(usNow - s_usAwtoHoldMs) < AWTO_HOLD_CHECK_MS)
    {
        return;
    }
    s_usAwtoHoldMs += AWTO_HOLD_CHECK_MS;
    if((s_usAwtoHoldMs % 1000) < AWTO_HOLD_CHECK_MS)
    {
        s_usAwtoHoldSec++;
    }
    if((g_stAwtoPower.ucL3 != 0) && (s_usAwtoHoldSec >= g_stAwtoPower.usL3Sec))
    {
        AwtoWakeRelease(3);
        return;
    }
    if((s_ucAwtoHoldLevel == 1) && (g_stAwtoPower.ucL2 != 0) && (s_usAwtoHoldSec >= g_stAwtoPower.usL2Sec))
    {
        s_ucAwtoHoldLevel = 2;
        UserCommonInterfacePanelPowerAction(_PANEL_OFF);
        AwtoSwEvent(AWTO_SW_EV_HOLD, 2);
    }
    if((GET_SOURCE_SCAN_TYPE() != _SOURCE_SWITCH_FIXED_PORT) && ((s_usAwtoHoldMs % AWTO_HOLD_OTHER_MS) < AWTO_HOLD_CHECK_MS))
    {                                           // auto search: another port with a signal ends the hold (one port per check)
        s_ucAwtoHoldOther = (s_ucAwtoHoldOther >= 2) ? 0 : (s_ucAwtoHoldOther + 1);
        ucI = _D1_INPUT_PORT + s_ucAwtoHoldOther;
        if((ucI != g_ucAwtoHold) && (((ucI == _D1_INPUT_PORT) ? AwtoRxStable(ucI, _SOURCE_DP) : AwtoRxPreDetect(ucI, _SOURCE_HDMI)) == _TRUE))   // DP pre-detect is true on an idle cable: trained link only
        {
            AwtoWakeRelease(9);
            return;
        }
    }
    ucI = g_ucAwtoHold - _D1_INPUT_PORT;
    if(AwtoRxRescan(g_ucAwtoHold, s_pstAwtoSwCache[ucI].ucSourceType) == _FALSE)
    {
        return;
    }
    if(++s_ucAwtoHoldTries > AWTO_HOLD_TRIES)   // signal back but the cached set-up keeps failing: full path
    {
        AwtoWakeRelease(4);
        return;
    }
    AwtoSwEvent(AWTO_SW_EV_HOLD, 5);            // receiver stable again: fast path on the held port
    g_ucAwtoHold = 0;
    g_ucAwtoWakePending = 1;
    AwtoSwFastGo(ucI, SysSourceGetInputPort(), s_pstAwtoSwCache[ucI].ucSourceType);
    if(s_ucAwtoHoldLevel == 2)                  // L2: SDK panel on (T1, eDP link, T3) while the fast path's 3 frames pass; still
    {                                           // blanked (black) and before its flag clear, so its checks see the result
        UserCommonInterfacePanelPowerAction(_BACKLIGHT_ON);
    }
    else if(s_ucAwtoHoldLevel == 1)
    {
        PCB_BACKLIGHT_POWER_PIN(_LIGHT_CONTROL_ON);
    }
    if(s_ucAwtoHoldLevel != 0)
    {
        AwtoSwEvent(AWTO_SW_EV_HOLD, 6);
        s_ucAwtoHoldLevel = 0;
    }
}
#endif

unsigned char AwtoSwFast(unsigned char ucPort)  // _TRUE = fast path taken, no mode reset
{
    BYTE ucI = ucPort - _D1_INPUT_PORT;
    BYTE ucType;

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
    if(AwtoRxStable(ucPort, ucType) == _FALSE)
    {
        AwtoSwEvent(AWTO_SW_EV_FAST, 3);
        return _FALSE;
    }
    AwtoSwFastGo(ucI, ucPort, ucType);
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
    if(usDt < (WORD)s_ucAwtoFastFrameMs * AWTO_FAST_SETTLE_FRAMES)   // switch: 3 frames, the frame-sync phase jump is over
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
#if(_AWTO_WAKE_HOLD == _ON)
        s_ucAwtoWoke = g_ucAwtoWakePending;
        s_usAwtoWokeMs = AwtoFastNow();
        g_ucAwtoWakePending = 0;
#endif
        ScalerGlobalFirstActiveProc(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort());
        UserCommonInterfaceOsdActiveProc();     // NVRAM search port, DDC/CI (debug slave) to the new port, info pop-up, unblank
        s_ucAwtoFastWatch = 1;
        return;
    }
    if(usDt >= (WORD)s_ucAwtoFastFrameMs * 8)   // still failing 8 frames after the switch: full path
    {
        g_ucAwtoFastPending = 0;
#if(_AWTO_WAKE_HOLD == _ON)
        if(g_ucAwtoWakePending != 0)            // wake: back to the hold, the receiver may still be training (tries counted)
        {
            g_ucAwtoHold = SysSourceGetInputPort();
            s_ucAwtoHoldLevel = 0;              // backlight / panel already back on
            g_ucAwtoWakePending = 0;
            ScalerGlobalWatchDog(_DISABLE);
            ScalerDDomainBackgroundEnable(_ENABLE);
            AwtoSwEvent(AWTO_SW_EV_FAST_WHY, ucWhy);
            AwtoSwEvent(AWTO_SW_EV_HOLD, 7);
            return;
        }
#endif
        AwtoSwEvent(AWTO_SW_EV_FAST, 5);
        AwtoSwEvent(AWTO_SW_EV_FAST_WHY, ucWhy);
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
        return;
    }
    AwtoFastScalerClearStatus(_FALSE);          // re-lock still settling: clear the flags again, check one frame later
    s_usAwtoFastNextMs = usDt + s_ucAwtoFastFrameMs;
}
#endif
