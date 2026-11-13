// #138: WD-timer protocol events (DP rebuild PHY, HDMI RR retry) on Timer0, so the WD counter is only a watchdog (docs/watchdog.md).
// Appended to ScalerCommonTimerFunction.c (fw/awto/wdt/rules.py); the SDK's WD-timer block there is #if 0. Same function names
// (ScalerTimerWDEventProc_WDINT gone: the WD IRQ is the watchdog warning, SysTimerWDIntProc -> AwtoWdtIrq).
// 1 ms ticks while an event is pending. Timer0 counts what Timer2 counts (same MCU clock, both /12: SDK _TIMER01_* = _TIMER2_*).
#if((_SYSTEM_LOW_POWER_IDLE_SUPPORT == _ON) || (_SYSTEM_TIMER_QUARTER_RESOLUTION == _ON))
#error "awto_t0ev: RCAP2 is not one 1 ms Timer2 period in this configuration"
#endif
#if((_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON) && (_PORT_CONTROLLER_EMBEDDED_SUPPORT == _ON))
#error "awto_t0ev: Type-C PD WD events (re-armed from their handler) are not ported"
#endif

static __xdata WORD s_pusAwtoT0Ms[_SCALER_WD_TIMER_EVENT_COUNT];   // ms left per event ID (0 = idle; ID 0 is INVALID)
static __xdata WORD s_usAwtoT0Rl;                                   // reload (RCAP2) of the running tick
__xdata BYTE g_ucAwtoT0Pos;                                         // 0 = Timer0 ISR not running; else the next ID it decrements

// Timer0 = one 1 ms tick from now at the current clock (Timer2's reload)
#define AWTO_T0EV_START()               do { TR0 = 0; TL0 = RCAP2L; TH0 = RCAP2H; TF0 = 0; TR0 = 1; \
                                             s_usAwtoT0Rl = (((WORD)RCAP2H) << 8) | RCAP2L; } while(0)
// Re-arm restarts. Timer0 running: +1 tick when the current tick is past half -> fires within +-0.5 ms of usMs.
// Preempting the Timer0 ISR (EXINT0 high in power saving): +1 if the ISR has yet to decrement this ID in its tick.
#define AWTO_T0EV_ARM(usMs, ucId)       do { if(g_ucAwtoT0Pos != 0) { s_pusAwtoT0Ms[(ucId)] = (usMs) + ((ucId) >= g_ucAwtoT0Pos); } \
                                             else if(TR0 == 0) { AWTO_T0EV_START(); s_pusAwtoT0Ms[(ucId)] = (usMs); } \
                                             else { s_pusAwtoT0Ms[(ucId)] = (usMs) + ((((WORD)(BYTE)(TH0 - RCAP2H)) << 1) >= (WORD)(0x100 - RCAP2H)); } } while(0)

// ScalerMcuInitial end (TMOD 0x11: Timer0 16 bit; PT0 = 0: low priority, as the WD IRQ was) and AwtoWdtProbe.
// The WD counter is the watchdog only (#138 task 3, RL6449_Project.h AWTO_WDT_*): warning IRQ on int2 at high priority.
void ScalerTimerWDInitial(void)
{
    TR0 = 0;
    TF0 = 0;
    ET0 = 1;

    EX2 = 0;
    MCU_FFC4_IRQ_PRIORITY_3 = (MCU_FFC4_IRQ_PRIORITY_3 & ~(_BIT5 | _BIT4 | _BIT3)) | _BIT4;  // wdt_irq_pri = int2
    PX2 = 1;                                    // high: interrupts a hung main loop or a low-priority ISR
    MCU_FFAF_WATCHDOG_TIMER_THRESHOLD_MASK = 0x00;
    MCU_FFB0_WATCHDOG_TIMER_H_THRESHOLD_MASK = (AWTO_WDT_THR >> 4) & 0xF0;
    MCU_FFAE_WATCHDOG_TIMER_THRESHOLD = (BYTE)AWTO_WDT_THR;
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~(_BIT7 | _BIT4 | _BIT2)) | _BIT7 | ((AWTO_WDT_MODE == AWTO_WDT_TIMER_IRQ) ? _BIT4 : 0);
    MCU_FFEA_WATCHDOG_TIMER = (MCU_FFEA_WATCHDOG_TIMER & ~(_BIT5 | _BIT2 | _BIT1 | _BIT0)) | _BIT7 | _BIT6 | (AWTO_WDT_N - 1) |
                              ((AWTO_WDT_HALT_FLASH != 0) ? _BIT5 : 0);
    EXIF &= ~_BIT4;
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT2;
    EX2 = 1;
    AwtoSyncPush(AWTO_SYNC_EV_INIT, 3, (AWTO_WDT_WARN_MS << 16) | AWTO_WDT_RESET_MS);
}

void ScalerTimerWDActivateTimerEvent_EXINT0(WORD usTime, EnumScalerWDTimerEventID enumEventID)
{
    // EXINT0: Timer0 (same or lower priority) cannot preempt; Timer2 does not touch the table
    if((enumEventID != _SCALER_WD_TIMER_EVENT_INVALID) && (enumEventID < _SCALER_WD_TIMER_EVENT_COUNT))
    {
        AWTO_T0EV_ARM((usTime != 0) ? usTime : 1, enumEventID);
    }
}

void ScalerTimerWDCancelTimerEvent(EnumScalerWDTimerEventID enumEventID)
{
    if(enumEventID < _SCALER_WD_TIMER_EVENT_COUNT)
    {
        __critical
        {
            s_pusAwtoT0Ms[enumEventID] = 0;     // 2-byte write: EXINT0 / Timer0 must not see half of it
        }
    }
}

#if((_DP_SUPPORT == _ON) || ((_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON) && (_PORT_CONTROLLER_EMBEDDED_SUPPORT == _ON)))
void ScalerTimerWDCancelTimerEvent_EXINT0(EnumScalerWDTimerEventID enumEventID)
{
    if(enumEventID < _SCALER_WD_TIMER_EVENT_COUNT)
    {
        s_pusAwtoT0Ms[enumEventID] = 0;
    }
}
#endif

#if(_D1_DP_EXIST == _ON)
extern volatile __xdata BYTE g_ucAwtoT0Test;
#endif

void AwtoT0EvFire(EnumScalerWDTimerEventID enumEventID)     // the SDK's WD event switch; Timer0 ISR context
{
#if(_D1_DP_EXIST == _ON)
    while((g_ucAwtoT0Test == 4) && (enumEventID == _SCALER_WD_TIMER_EVENT_RX5_HDMI_RR_RETRY))
    {
    }                                           // test 9: stuck Timer0 handler (RX5 is never armed otherwise)
#endif
    switch(enumEventID)
    {
#if(_D0_DP_EXIST == _ON)
        case _SCALER_WD_TIMER_EVENT_RX0_DP_LINK_TRAINING_REBUILD_PHY:
            ScalerDpWDTimerEventProc_WDINT(enumEventID);
            break;
#endif
#if(_D1_DP_EXIST == _ON)
        case _SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY:
            ScalerDpWDTimerEventProc_WDINT(enumEventID);
            break;
#endif
#if(_HDMI_2_0_SUPPORT == _ON)
        case _SCALER_WD_TIMER_EVENT_RX0_HDMI_RR_RETRY:
        case _SCALER_WD_TIMER_EVENT_RX1_HDMI_RR_RETRY:
        case _SCALER_WD_TIMER_EVENT_RX2_HDMI_RR_RETRY:
        case _SCALER_WD_TIMER_EVENT_RX3_HDMI_RR_RETRY:
        case _SCALER_WD_TIMER_EVENT_RX4_HDMI_RR_RETRY:
        case _SCALER_WD_TIMER_EVENT_RX5_HDMI_RR_RETRY:
            ScalerTMDSHdmiReadRequestTimerEnable_WDINT(_ENABLE);
            break;
#endif
#if((_DP_HDCP_2_2_SUPPORT == _ON) && (_D0_DP_EXIST == _ON))
        case _SCALER_WD_TIMER_EVENT_DP_RX0_HDCP2_SKE:
            ScalerDpRx0Hdcp2SkeProc_WDINT();
            break;
#endif
#if((_DP_HDCP_2_2_SUPPORT == _ON) && (_D1_DP_EXIST == _ON))
        case _SCALER_WD_TIMER_EVENT_DP_RX1_HDCP2_SKE:
            ScalerDpRx1Hdcp2SkeProc_WDINT();
            break;
#endif
        default:
            break;
    }
}

void AwtoT0EvIsr(void)                          // SysTimerIntProc0: one 1 ms tick
{
    BYTE ucId;
    BYTE ucDue;
    WORD usT;

    EA = 0;                                     // EXINT0 is high priority in power saving (IP 0x81) and arms: reload atomic
    TR0 = 0;                                    // next tick 1 ms after the overflow: keep the counts since it (ISR latency)
    s_usAwtoT0Rl = (((WORD)RCAP2H) << 8) | RCAP2L;
    usT = ((((WORD)TH0) << 8) | TL0) + s_usAwtoT0Rl;
    if(usT < s_usAwtoT0Rl)
    {
        usT = 0xFFFF;                           // more than a tick late (a long EXINT0 handler): the next tick at once
    }
    TL0 = (BYTE)usT;
    TH0 = (BYTE)(usT >> 8);
    TR0 = 1;
    g_ucAwtoT0Pos = 1;
    EA = 1;
    for(ucId = 1; ucId < _SCALER_WD_TIMER_EVENT_COUNT; ucId++)
    {
        EA = 0;
        ucDue = (s_pusAwtoT0Ms[ucId] != 0) && (--s_pusAwtoT0Ms[ucId] == 0);
        g_ucAwtoT0Pos = ucId + 1;
        EA = 1;
        if(ucDue != 0)
        {
            AwtoT0EvFire(ucId);                 // handlers run with interrupts on (rebuild PHY ~1 ms)
        }
    }
    EA = 0;
    for(ucId = 1; (ucId < _SCALER_WD_TIMER_EVENT_COUNT) && (s_pusAwtoT0Ms[ucId] == 0); ucId++)
    {
    }
    if(ucId == _SCALER_WD_TIMER_EVENT_COUNT)
    {
        TR0 = 0;                                // nothing pending: no ticks
    }
    g_ucAwtoT0Pos = 0;
    EA = 1;
}

void AwtoT0EvClock(void)                        // end of ScalerTimerSetTimerCount (every MCU clock switch)
{
    WORD usNew;
    WORD usLeft;

    AwtoSyncT2Start();                          // #29: the first reload starts the 1 ms tick (boot log time base)

    __critical
    {
        usNew = (((WORD)RCAP2H) << 8) | RCAP2L;
        if((TR0 != 0) && (usNew != s_usAwtoT0Rl))
        {
            TR0 = 0;                            // rest of the tick: same fraction of a period at the new clock
            usLeft = 0 - ((((WORD)TH0) << 8) | TL0);
            usLeft = (WORD)(((DWORD)usLeft * (WORD)(0 - usNew)) / (WORD)(0 - s_usAwtoT0Rl));
            usLeft = 0 - ((usLeft != 0) ? usLeft : 1);
            TL0 = (BYTE)usLeft;
            TH0 = (BYTE)(usLeft >> 8);
            s_usAwtoT0Rl = usNew;
            TR0 = 1;
        }
    }
}

#if(_D1_DP_EXIST == _ON)
// Tests (sim: wdt_test.py t0_* / prio_*; unit 2 where it can): test cmd 0x2A + n -> n 0..5, 0x5A..0x5C -> 6..8, 0x24 -> 9.
// 0 DP rebuild 30 ms, 1 / 2 HDMI RR D2 / D3 10 ms, 3 = 0 + 1 together, 4 / 5 = 0 / 1 with a forced PS reload and back while pending,
// 6 / 7 = 0 / 1 armed and fired at the PS reload, 8 = RR D3 10, rebuild 30, RR D2 5 out of order, then RR D3 cancelled,
// 9 = RX5 RR 1 ms whose handler spins (a stuck Timer0 handler: the WDT warning must preempt it).
volatile __xdata BYTE g_ucAwtoT0Test;           // EXINT0 test mode (test cmds 0x5D..0x5F, 0x25 off): 1 arm once, 2 spin 2 ms once, 3 spin
volatile __xdata BYTE g_ucAwtoT0Arms;           // arms done by the EXINT0 test hook

void AwtoT0EvTest(BYTE ucHow)
{
    EnumScalerWDTimerEventID enumId = ((ucHow == 0) || (ucHow == 4) || (ucHow == 6)) ? _SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY :
                                      (ucHow == 2) ? _SCALER_WD_TIMER_EVENT_RX3_HDMI_RR_RETRY : _SCALER_WD_TIMER_EVENT_RX2_HDMI_RR_RETRY;
    BYTE ucMs = (enumId == _SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY) ? 30 : 10;

    if(ucHow > 9)
    {
        return;
    }
    if((ucHow == 6) || (ucHow == 7))
    {
        ScalerTimerSetTimerCount(_TIMER_OPERATION_POWER_SAVING_MODE);
    }
    __critical
    {
        if(ucHow == 8)
        {
            AWTO_T0EV_ARM(10, _SCALER_WD_TIMER_EVENT_RX3_HDMI_RR_RETRY);
            AWTO_T0EV_ARM(30, _SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY);
            AWTO_T0EV_ARM(5, _SCALER_WD_TIMER_EVENT_RX2_HDMI_RR_RETRY);
        }
        else if(ucHow == 9)
        {
            g_ucAwtoT0Test = 4;
            AWTO_T0EV_ARM(1, _SCALER_WD_TIMER_EVENT_RX5_HDMI_RR_RETRY);
        }
        else
        {
            AWTO_T0EV_ARM(ucMs, enumId);
            if(ucHow == 3)
            {
                AWTO_T0EV_ARM(30, _SCALER_WD_TIMER_EVENT_RX1_DP_LINK_TRAINING_REBUILD_PHY);
            }
        }
    }
    if(ucHow == 8)
    {
        ScalerTimerDelayXms(2);
        ScalerTimerWDCancelTimerEvent(_SCALER_WD_TIMER_EVENT_RX3_HDMI_RR_RETRY);
    }
    else if((ucHow == 4) || (ucHow == 5))
    {
        ScalerTimerDelayXms(ucMs / 6);
        ScalerTimerSetTimerCount(_TIMER_OPERATION_POWER_SAVING_MODE);
        ScalerTimerDelayXms(ucMs / 3);
        ScalerTimerSetTimerCount(_TIMER_OPERATION_POWER_NORMAL_MODE);
    }
    else if((ucHow == 6) || (ucHow == 7))
    {
        ScalerTimerDelayXms(ucMs + (ucMs >> 2));            // the event fires inside (x1.25), still at the PS reload
        ScalerTimerSetTimerCount(_TIMER_OPERATION_POWER_NORMAL_MODE);
    }
}

void AwtoT0EvTestIsr(void)                      // SysEXINT0 entry while g_ucAwtoT0Test != 0 (EXINT0 context)
{
    WORD usT0;

    if(g_ucAwtoT0Test == 1)
    {
        g_ucAwtoT0Test = 0;                     // one shot: other EXINT0 sources must not re-arm it
        AWTO_T0EV_ARM(10, _SCALER_WD_TIMER_EVENT_RX2_HDMI_RR_RETRY);
        g_ucAwtoT0Arms++;
    }
    else if(g_ucAwtoT0Test == 2)
    {
        g_ucAwtoT0Test = 0;
        usT0 = d_g_usTimerCounter;                // Timer2 (high) keeps ticking: spin 2..3 ms
        while((WORD)(d_g_usTimerCounter - usT0) < 3)
        {
        }
    }
    else if(g_ucAwtoT0Test == 3)
    {
        while(_TRUE)                            // stuck EXINT0 handler: no pokes; the WDT warning (high) must preempt
        {
        }
    }
}
#endif
