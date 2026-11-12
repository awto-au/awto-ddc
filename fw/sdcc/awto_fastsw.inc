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

static __xdata StAwtoSwCache s_pstAwtoSwCache[3];
__xdata BYTE g_ucAwtoFastPending;
static __xdata WORD s_usAwtoFastT0;
static __xdata BYTE s_ucAwtoFastFrameMs;
static __xdata BYTE s_ucAwtoFastWatch;          // diagnostic: after a fast unblank, log the first M-domain error flags once
static __xdata WORD s_usAwtoFastNextMs;         // next check, ms after the switch; 0 = flags not cleared yet

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

unsigned char AwtoSwCacheValid(unsigned char ucPort)
{
    BYTE ucI = ucPort - _D1_INPUT_PORT;

    return (ucI < 3) ? s_pstAwtoSwCache[ucI].ucValid : 0;
}

static void AwtoSwFastGo(BYTE ucI, BYTE ucPort, BYTE ucType)
{
    ScalerDDomainBackgroundEnable(_ENABLE);
    SET_SOURCE_JUDGE(g_ucSearchIndex, _FALSE);
    g_ucSearchIndex = SysSourceConvertSearchPort(ucPort);
    SET_SOURCE_TYPE(g_ucSearchIndex, ucType);
    SET_SOURCE_JUDGE(g_ucSearchIndex, _TRUE);
    s_ucAwtoFastFrameMs = AwtoFastScalerApply(s_pstAwtoSwCache[ucI].pucScaler, ucType, ucPort);
    s_usAwtoFastT0 = ((WORD)AwtoMs());
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
static __xdata BYTE s_ucAwtoHoldLevel;          // 1 = this hold asked the panel machine for backlight off, 0 = backlight on

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
#if(_DP_SUPPORT == _ON)
    if(ucType == _SOURCE_DP)
    {
        return (ScalerDpScanInputPort(ucPort) == ucType);
    }
#endif
    return (ScalerTMDSScanInputPort(ucPort, GET_INPUTPORT_TYPE(g_ucSearchIndex)) == ucType);
}

// #78 signal lost in ACTIVE = hold the set-up (system machine state HOLD, mode stays ACTIVE), L1 backlight off (panel request);
// after usL2Sec the SDK path takes over (search, no signal, power-saving timers; #162 Dan 2026-11-12). Signal back on the
// held port = the fast path (cache) with a backlight-on request before the unblank. Settings: g_stAwtoPower (test cmds 0x36..0x39).
__xdata StAwtoPower g_stAwtoPower = {1, 1, AWTO_L2_SEC};
__xdata BYTE g_ucAwtoHold;                      // port held, 0 = none
static __xdata WORD s_usAwtoHoldSec;
static __xdata WORD s_usAwtoHoldMs;             // ms into the current second / last 10 ms check
static __xdata BYTE s_ucAwtoHoldTries;
__xdata BYTE g_ucAwtoWakePending;               // a fast wake is in flight (its unblank stamps s_usAwtoWokeMs)
static __xdata WORD s_usAwtoWokeMs;
static __xdata BYTE s_ucAwtoWoke;
__xdata BYTE g_ucAwtoNoHold;                    // released to the SDK: no new hold until a full-path ACTIVE (AwtoSwCacheStore)

bit AwtoWakeHold(void)                          // judge check failed in ACTIVE: _TRUE = held here, no SDK mode reset
{
    BYTE ucI = SysSourceGetInputPort() - _D1_INPUT_PORT;

    if((g_stAwtoPower.ucL1 == 0) || (g_ucAwtoNoHold != 0) || (GET_MODE_STATE() != _MODE_STATUS_ACTIVE) || (g_ucAwtoFastPending != 0) ||
       (ucI >= 3) || (s_pstAwtoSwCache[ucI].ucValid == 0) || (AwtoFastScalerMatch(s_pstAwtoSwCache[ucI].pucScaler) != 0) ||
       ((s_ucAwtoWoke != 0) && ((WORD)(((WORD)AwtoMs()) - s_usAwtoWokeMs) < AWTO_REHOLD_MS)))     // judge failed right after a fast wake: full path, no blink loop
    {
        return _FALSE;
    }
    ScalerDDomainBackgroundEnable(_ENABLE);
    ScalerGlobalWatchDog(_DISABLE);             // no free run: the display stays set up for the same timing
    UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_OFF, AWTO_PNL_BY_HOLD_L1));    // L1: returns at once; the machine keeps the eDP stream
    g_ucAwtoHold = SysSourceGetInputPort();
    s_ucAwtoHoldLevel = 1;
    s_usAwtoHoldSec = 0;
    s_usAwtoHoldMs = ((WORD)AwtoMs());
    s_ucAwtoHoldTries = 0;
    AwtoSwEvent(AWTO_SW_EV_HOLD, 1);
    return _TRUE;
}

static void AwtoWakeRelease(BYTE ucWhy)         // to the SDK search; the panel machine already holds the backlight state
{
    s_ucAwtoHoldLevel = 0;
    g_ucAwtoHold = 0;
    g_ucAwtoNoHold = 1;
    g_ucAwtoWakePending = 0;
    AwtoSwEvent(AWTO_SW_EV_HOLD, ucWhy);       // switch log; the ring line is the request's (who = the reason)
    SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH,
                      (ucWhy == 2) ? AWTO_SYS_BY_HOLD : ((ucWhy == 4) ? AWTO_SYS_BY_HOLD_TRIES : AWTO_SYS_BY_HOLD_AUTO));
}

void AwtoWakePoll(void)                         // every pass while held
{
    BYTE ucI;
    WORD usNow;

    if(GET_MODE_STATE() != _MODE_STATUS_ACTIVE)
    {
        s_ucAwtoHoldLevel = 0;
        g_ucAwtoHold = 0;                       // the SDK reset the mode itself
        AwtoSwEvent(AWTO_SW_EV_HOLD, 0x10);
        return;
    }
    usNow = ((WORD)AwtoMs());
    if((WORD)(usNow - s_usAwtoHoldMs) < AWTO_HOLD_CHECK_MS)
    {
        return;
    }
    s_usAwtoHoldMs += AWTO_HOLD_CHECK_MS;
    if((s_usAwtoHoldMs % 1000) < AWTO_HOLD_CHECK_MS)
    {
        s_usAwtoHoldSec++;
    }
    if((g_stAwtoPower.ucL2 != 0) && (s_usAwtoHoldSec >= g_stAwtoPower.usL2Sec))
    {
        AwtoWakeRelease(2);                     // L2: the SDK's no-signal -> power-saving timers from here
        return;
    }
    if((GET_SOURCE_SCAN_TYPE() != _SOURCE_SWITCH_FIXED_PORT) && (s_usAwtoHoldSec >= AWTO_HOLD_AUTO_SEC) &&
       (((g_ucAwtoHold != _D1_INPUT_PORT) && (GET_D1_CABLE_STATUS() == _TRUE) && (s_pstAwtoSwCache[0].ucValid != 0)) ||
        ((g_ucAwtoHold != _D2_INPUT_PORT) && (GET_D2_CABLE_STATUS() == _TRUE) && (s_pstAwtoSwCache[1].ucValid != 0)) ||
        ((g_ucAwtoHold != _D3_INPUT_PORT) && (GET_D3_CABLE_STATUS() == _TRUE) && (s_pstAwtoSwCache[2].ucValid != 0))))
    {                                           // auto search + another cable that has carried a picture (cache): the SDK
                                                // search may find it live. A cable that never did (idle DP) keeps the fast wake.
        AwtoWakeRelease(9);                     // (idle ports have no clock detection: their freq-detect IRQ is off, #60)
        return;
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
    SysMachineRequest(AWTO_SYS_REQ_FAST, AWTO_SYS_BY_HOLD_BACK);
    if(s_ucAwtoHoldLevel != 0)                  // still blanked: the backlight is back before the unblank
    {
        UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_HOLD_BACK));
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
#ifdef _AWTO_NEW_SETTINGS
    if((ucType == 0) && (AWTO_SET(FAST_SWITCH) == 0))      // #67 Fast switch row off: always the full path
    {
        ucType = 10;
    }
#endif
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
    SysMachineRequest(AWTO_SYS_REQ_FAST, AWTO_SYS_BY_FAST);
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
    usDt = ((WORD)AwtoMs()) - s_usAwtoFastT0;
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
        s_usAwtoWokeMs = ((WORD)AwtoMs());
        g_ucAwtoWakePending = 0;
#endif
        ScalerGlobalFirstActiveProc(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort());
        UserCommonInterfaceOsdActiveProc();     // NVRAM search port, DDC/CI (debug slave) to the new port, info pop-up, unblank
        s_ucAwtoFastWatch = 1;
        SysMachineRequest(AWTO_SYS_REQ_ACTIVE, AWTO_SYS_BY_FAST_DONE);
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
            SysMachineRequest(AWTO_SYS_REQ_HOLD, AWTO_SYS_BY_FAST_RETRY);
            return;
        }
#endif
        AwtoSwEvent(AWTO_SW_EV_FAST, 5);
        AwtoSwEvent(AWTO_SW_EV_FAST_WHY, ucWhy);
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_FAST_FAIL);
        return;
    }
    AwtoFastScalerClearStatus(_FALSE);          // re-lock still settling: clear the flags again, check one frame later
    s_usAwtoFastNextMs = usDt + s_ucAwtoFastFrameMs;
}
#endif
