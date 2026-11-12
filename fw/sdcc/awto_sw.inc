// #60 input-switch timeline (RL6449_Project.h StAwtoSw): events in Timer2 ms ticks; test cmd 0x31..0x33 arms it
// (fixed port D1..D3), 0x30 = auto search again. Host: scripts/sw_timeline.py. Inserted into SysMain.c by keil2sdcc.py.
#if(_AWTO_SW_LOG == _ON)
__xdata StAwtoSw g_stAwtoSw;
#if(_AWTO_TMDS_HPD_RECOVER == _ON)
static __xdata unsigned char s_ucAwtoUnstable;  // "source unstable" judge fails since the last ACTIVE (TMDS ports)
static __xdata unsigned char s_ucAwtoHpdPulses;
#endif

static void AwtoSwRec(unsigned char ucId, unsigned char ucArg)
{
    unsigned char ucN = g_stAwtoSw.ucN;

    if((ucN != 0) && (g_stAwtoSw.stEv[ucN - 1].ucId == ucId) && (g_stAwtoSw.stEv[ucN - 1].ucArg == ucArg))
    {
        return;                                 // #78: measure-retry probes repeat every ~8 ms; the first one carries the time
    }
    if(ucN < AWTO_SW_EVENTS)
    {
        g_stAwtoSw.stEv[ucN].ucId = ucId;
        g_stAwtoSw.stEv[ucN].ucArg = ucArg;
        g_stAwtoSw.stEv[ucN].usMs = ((WORD)AwtoMs());
        g_stAwtoSw.ucN = ucN + 1;
    }
}

void AwtoSwEvent(unsigned char ucId, unsigned char ucArg)
{
    AWTO_SYNC_SW(ucId, ucArg);                  // #139 sync log: its own ring, kept when this log is full
    AwtoSwRec(ucId, ucArg);
}

// #162 panel machine transition: switch log (no value) + ring line with the ms spent in the old state.
void AwtoPanelLog(unsigned char ucArg, unsigned int usMs)
{
    AwtoSwRec(AWTO_SW_EV_PANEL, ucArg);
    AwtoSyncPush(AWTO_SW_EV_PANEL, ucArg, usMs);
}

// #63 own frame: pattern generator or forced background on, so the panel's short T3 applies (AWTO_T3_OWN_PATTERN_MS)
unsigned char AwtoOwnFrame(void)
{
    return ((ScalerGetByte(AWTO_R_DISP_PG_R_CTRL) & AWTO_F_DISP_PG_R_CTRL_PG_ENABLE) != 0) ||
           ((ScalerGetByte(AWTO_R_VIDEO_DISPLAY_CONTROL_REG) & AWTO_F_VIDEO_DISPLAY_CONTROL_REG_FORCE_BG_EN) != 0);
}

// A panel pin or the backlight PWM written outside the panel machine (after boot pin init): logged, for the sim gate too.
void AwtoPanelForeign(unsigned char ucWhat)
{
    if((g_ucAwtoPanelOwn == 0) && (g_stAwtoDiag.ucStage >= 5))
    {
        AwtoSwEvent(AWTO_SW_EV_PANEL_X, ucWhat);
    }
}

#if(_AWTO_SW_MARKS == _ON)
static unsigned int s_usAwtoSwMark;

static unsigned char s_ucAwtoSwReset;

void AwtoSwMark(unsigned char ucK)      // logs AWTO_SW_EV_SLOW(k) when the code since the previous mark took >= AWTO_SW_SLOW_MS
{
    unsigned int usNow = ((WORD)AwtoMs());

    if(GET_MODE_RESET_TARGET() != s_ucAwtoSwReset)    // which segment set a mode reset (#60)
    {
        s_ucAwtoSwReset = GET_MODE_RESET_TARGET();
        if(s_ucAwtoSwReset != _MODE_ACTION_NO_RESET_MODE)
        {
            AwtoSwEvent(AWTO_SW_EV_RESET_AT, ucK);
        }
    }

    if((unsigned int)(usNow - s_usAwtoSwMark) >= AWTO_SW_SLOW_MS)
    {
        AwtoSwEvent(AWTO_SW_EV_SLOW, ucK);
    }
    s_usAwtoSwMark = usNow;
}
#endif

void AwtoSwArm(unsigned char ucPort)
{
    g_stAwtoSw.ucMagic = 'S';
    g_stAwtoSw.ucSeq++;
    g_stAwtoSw.ucPort = ucPort;
    g_stAwtoSw.ucN = 0;
    g_stAwtoSw.usT0 = ((WORD)AwtoMs());
}

#if(_AWTO_PANEL_LOG == _ON)
// #144 panel log: a real pin change logs the event (0..3) from the PCB macros; requests log in the panel machine.
static __xdata unsigned char s_ucAwtoPins;       // last written level: bit0 panel VDD, bit1 backlight (every write goes through the PCB macros)

void AwtoPanelPinLog(unsigned char ucBacklight, unsigned char ucOn)    // before the pin is written
{
    unsigned char ucBit = (ucBacklight != 0) ? 2 : 1;
    unsigned char ucWas = ((s_ucAwtoPins & ucBit) != 0);

    AwtoPanelForeign(AWTO_PNL_X_VDD + ucBacklight);
    if(ucOn != 0)
    {
        s_ucAwtoPins |= ucBit;
    }
    else
    {
        s_ucAwtoPins &= ~ucBit;
    }
    if((g_stAwtoDiag.ucStage >= 5) && (ucWas != (ucOn != 0)))      // boot-time pin init is not a panel change
    {
        AwtoSwEvent(AWTO_SW_EV_POWER, (ucBacklight != 0) ? ((ucOn != 0) ? _BACKLIGHT_ON : _BACKLIGHT_OFF) : ((ucOn != 0) ? _PANEL_ON : _PANEL_OFF));
    }
}
#endif

// #162 step 3 system machine transition: switch log (no value) + ring line (why << 24 | ms in the old state, 24 bits).
void AwtoSysLog(unsigned char ucArg, unsigned char ucWhy, unsigned long ulMs)
{
    AwtoSwRec(AWTO_SW_EV_SYS, ucArg);
    AwtoSyncPush(AWTO_SW_EV_SYS, ucArg, ((DWORD)ucWhy << 24) | ((ulMs > AWTO_SYS_MS_MAX) ? AWTO_SYS_MS_MAX : ulMs));
}

void AwtoSwMode(unsigned char ucMode)           // the system machine changed the SDK mode state (at the transition)
{
    g_stAwtoSw.ucLastMode = ucMode;
    AwtoSwEvent(AWTO_SW_EV_MODE, ucMode);
#if(_AWTO_TMDS_HPD_RECOVER == _ON)
    if(ucMode == _MODE_STATUS_ACTIVE)
    {
        s_ucAwtoUnstable = 0;
        s_ucAwtoHpdPulses = 0;
    }
#endif
}

void AwtoSwPoll(void)                           // once per main-loop pass: the power-saving wake poll (#144)
{
    AWTO_SYNC_POLL();
}

#if(_AWTO_TMDS_HPD_RECOVER == _ON)
static __xdata unsigned char s_ucAwtoHpdLow;    // port whose HPD is held low by the recovery, 0 = none
static __xdata unsigned int s_usAwtoHpdLowAt;

static void AwtoTmdsHpd(BYTE ucPort, BYTE ucHigh)
{
    if(ucPort == _D2_INPUT_PORT)
    {
        PCB_D2_HOTPLUG((ucHigh != 0) ? _D2_HOT_PLUG_HIGH : _D2_HOT_PLUG_LOW);
    }
    else
    {
        PCB_D3_HOTPLUG((ucHigh != 0) ? _D3_HOT_PLUG_HIGH : _D3_HOT_PLUG_LOW);
    }
}

void AwtoTmdsStuck(void)                        // judge: source unstable. Host lost its SCDC set-up (chip reset, #78): one HPD pulse
{
    BYTE ucPort = SysSourceGetInputPort();

    if((s_ucAwtoHpdLow != 0) || ((ucPort != _D2_INPUT_PORT) && (ucPort != _D3_INPUT_PORT)) || (++s_ucAwtoUnstable < AWTO_TMDS_STUCK_N))
    {
        return;
    }
    s_ucAwtoUnstable = 0;
    if(s_ucAwtoHpdPulses >= AWTO_TMDS_HPD_MAX)  // no hot-plug storm: the counters reset at ACTIVE
    {
        return;
    }
    s_ucAwtoHpdPulses++;
    AwtoSwEvent(AWTO_SW_EV_HPD_RECOVER, ucPort);
    AwtoTmdsHpd(ucPort, 0);                     // #162: no wait here; AwtoTmdsHpdTick raises it after AWTO_TMDS_HPD_LOW_MS
    s_ucAwtoHpdLow = ucPort;
    s_usAwtoHpdLowAt = (WORD)AwtoMs();
}

void AwtoTmdsHpdTick(void)                      // system machine, each pass
{
    if((s_ucAwtoHpdLow != 0) && ((WORD)((WORD)AwtoMs() - s_usAwtoHpdLowAt) >= AWTO_TMDS_HPD_LOW_MS))
    {
        AwtoTmdsHpd(s_ucAwtoHpdLow, 1);
        AwtoSwEvent(AWTO_SW_EV_HPD_RECOVER_UP, s_ucAwtoHpdLow);
        s_ucAwtoHpdLow = 0;
    }
}
#endif
#endif
