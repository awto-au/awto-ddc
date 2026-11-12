// #60 input-switch timeline (RL6449_Project.h StAwtoSw): events in Timer2 ms ticks; test cmd 0x31..0x33 arms it
// (fixed port D1..D3), 0x30 = auto search again. Host: scripts/sw_timeline.py. Inserted into SysMain.c by keil2sdcc.py.
#if(_AWTO_SW_LOG == _ON)
__xdata StAwtoSw g_stAwtoSw;
#if(_AWTO_TMDS_HPD_RECOVER == _ON)
static __xdata unsigned char s_ucAwtoUnstable;  // "source unstable" judge fails since the last ACTIVE (TMDS ports)
static __xdata unsigned char s_ucAwtoHpdPulses;
#endif

void AwtoSwEvent(unsigned char ucId, unsigned char ucArg)
{
    unsigned char ucN = g_stAwtoSw.ucN;

    AWTO_SYNC_SW(ucId, ucArg);                  // #139 sync log: its own ring, kept when this log is full
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
// #144 panel log: a call logs 4 + 2 * event + already-in-that-state; a real pin change logs the event (0..3) from the PCB macros.
unsigned char AwtoPanelReqArg(unsigned char ucEvent, unsigned char ucStatus)
{
    unsigned char ucSame;

    switch(ucEvent)
    {
        case _PANEL_ON:
            ucSame = (ucStatus != _PANEL_POWER_OFF_STATE);
            break;
        case _PANEL_OFF:
            ucSame = (ucStatus == _PANEL_POWER_OFF_STATE);
            break;
        case _BACKLIGHT_ON:
            ucSame = (ucStatus == _BACKLIGHT_ON_ALREADY);
            break;
        default:
            ucSame = (ucStatus != _BACKLIGHT_ON_ALREADY);
            break;
    }
    return 4 + 2 * ucEvent + ucSame;
}

static __xdata unsigned char s_ucAwtoPins;       // last written level: bit0 panel VDD, bit1 backlight (every write goes through the PCB macros)

void AwtoPanelPinLog(unsigned char ucBacklight, unsigned char ucOn)    // before the pin is written
{
    unsigned char ucBit = (ucBacklight != 0) ? 2 : 1;
    unsigned char ucWas = ((s_ucAwtoPins & ucBit) != 0);

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

#if(_AWTO_FAST_BOOT == _ON)
void AwtoPanelVddEarly(void)                    // #63: right after pin-share; eDP lanes stay off until the SDK's _PANEL_ON (T1 later)
{
    PCB_PANEL_POWER(_PANEL_CONTROL_ON);
    AwtoDiagStage(5);
    AwtoSwEvent(AWTO_SW_EV_VDD, 1);
}
#endif

void AwtoSwPoll(void)                           // once per main-loop pass: mode-state changes
{
    unsigned char ucMode = GET_MODE_STATE();

    AWTO_SYNC_POLL();
    if(ucMode != g_stAwtoSw.ucLastMode)
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
}

#if(_AWTO_TMDS_HPD_RECOVER == _ON)
void AwtoTmdsStuck(void)                        // judge: source unstable. Host lost its SCDC set-up (chip reset, #78): one HPD pulse
{
    BYTE ucPort = SysSourceGetInputPort();

    if(((ucPort != _D2_INPUT_PORT) && (ucPort != _D3_INPUT_PORT)) || (++s_ucAwtoUnstable < AWTO_TMDS_STUCK_N))
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
    if(ucPort == _D2_INPUT_PORT)
    {
        PCB_D2_HOTPLUG(_D2_HOT_PLUG_LOW);
        ScalerTimerDelayXms(AWTO_TMDS_HPD_LOW_MS);
        PCB_D2_HOTPLUG(_D2_HOT_PLUG_HIGH);
    }
    else
    {
        PCB_D3_HOTPLUG(_D3_HOT_PLUG_LOW);
        ScalerTimerDelayXms(AWTO_TMDS_HPD_LOW_MS);
        PCB_D3_HOTPLUG(_D3_HOT_PLUG_HIGH);
    }
}
#endif
#endif
