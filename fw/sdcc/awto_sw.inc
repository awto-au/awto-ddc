// #60 input-switch timeline (RL6449_Project.h StAwtoSw): events in Timer2 ms ticks; test cmd 0x31..0x33 arms it
// (fixed port D1..D3), 0x30 = auto search again. Host: scripts/sw_timeline.py. Inserted into SysMain.c by keil2sdcc.py.
#if(_AWTO_SW_LOG == _ON)
__xdata StAwtoSw g_stAwtoSw;

static unsigned int AwtoSwNow(void)             // Timer2 ISR count = 1 per ms tick; g_usTimerCounter is rebased to 0
{                                               // by ScalerTimerCheckTimerEvent near _EVENT_TIME_MAX (log showed the jumps)
    unsigned int usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

void AwtoSwEvent(unsigned char ucId, unsigned char ucArg)
{
    unsigned char ucN = g_stAwtoSw.ucN;

    if(ucN < AWTO_SW_EVENTS)
    {
        g_stAwtoSw.stEv[ucN].ucId = ucId;
        g_stAwtoSw.stEv[ucN].ucArg = ucArg;
        g_stAwtoSw.stEv[ucN].usMs = AwtoSwNow();
        g_stAwtoSw.ucN = ucN + 1;
    }
}

void AwtoSwArm(unsigned char ucPort)
{
    g_stAwtoSw.ucMagic = 'S';
    g_stAwtoSw.ucSeq++;
    g_stAwtoSw.ucPort = ucPort;
    g_stAwtoSw.ucN = 0;
    g_stAwtoSw.usT0 = AwtoSwNow();
}

#if(_AWTO_FAST_BOOT == _ON)
void AwtoPanelVddEarly(void)                    // #63: right after pin-share; eDP lanes stay off until the SDK's _PANEL_ON (T1 later)
{
    PCB_PANEL_POWER(_PANEL_CONTROL_ON);
    AwtoSwEvent(AWTO_SW_EV_VDD, 1);
}
#endif

void AwtoSwPoll(void)                           // once per main-loop pass: mode-state changes
{
    unsigned char ucMode = GET_MODE_STATE();

    if(ucMode != g_stAwtoSw.ucLastMode)
    {
        g_stAwtoSw.ucLastMode = ucMode;
        AwtoSwEvent(AWTO_SW_EV_MODE, ucMode);
    }
}
#endif
