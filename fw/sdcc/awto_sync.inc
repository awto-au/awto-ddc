// #139 sync / power-on log: a small I2C-readable ring of stage events (RL6449_Project.h StAwtoSync), one episode per
// power-on / input switch / wake. Texts: fw/awto/sync.tsv (scripts/gen_awto_sync.py); host decoder: scripts/sync_log.py.
// Also the port getters the selector rows read (stage, DDC activity, idle TMDS clock). Inserted into SysMain.c after awto_sw.inc.
#if(_AWTO_SYNC_LOG == _ON)
extern WORD g_usTmdsOffLineMeasureClk;              // ScalerCommonSync.c: SDK TMDS clock at freq-stable, 0.1 MHz
__xdata StAwtoSync g_stAwtoSync;
static __xdata BYTE s_pucAwtoSyncDet[3];          // D1..D3: last predetect (bit0) | source type << 1 seen by the port detect
static __xdata BYTE s_pucAwtoDdcAge[3];           // D1..D3: DDC polls left in which the port counts as live

// GENERATED-BEGIN awto_sync_rows
#define AWTO_SYNC_ROWS 52
static const __code BYTE tAwtoSyncRowId[52] = {
    0xC0, 0xC0, 0xC0, 0xC0, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x10, 0x10, 0x10, 0x10,
    0x70, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0,
    0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xB0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC7,
    0xC8, 0xC9, 0xC9, 0xCA};
static const __code BYTE tAwtoSyncRowArg[52] = {
    0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x00, 0x01, 0x02, 0x03,
    0xFF, 0x01, 0x0E, 0x14, 0x15, 0x16, 0x17, 0x1A, 0x1B, 0x1C, 0x00, 0x01, 0x03, 0x04, 0x05, 0xFF,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x10, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0x01, 0x03, 0xFF};
BYTE AwtoSyncRow(BYTE ucId, BYTE ucArg)           // row + 1 of the first match (arg 0xFF = any), 0 = not logged
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_SYNC_ROWS; ucI++)
    {
        if((tAwtoSyncRowId[ucI] == ucId) && ((tAwtoSyncRowArg[ucI] == 0xFF) || (tAwtoSyncRowArg[ucI] == ucArg)))
        {
            return ucI + 1;
        }
    }
    return 0;
}
// GENERATED-END awto_sync_rows

static WORD AwtoSyncNow(void)                       // Timer2 ISR ms count (diag usT2Isr), read until stable
{
    WORD usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

void AwtoSyncPush(BYTE ucId, BYTE ucArg, DWORD ulVal)
{
    BYTE ucN = g_stAwtoSync.ucSeq;
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(ucN, 1))];
    WORD usNow = AwtoSyncNow();

    if((ucN != g_stAwtoSync.ucEpSeq) && (puc[0] == ucId) && (puc[1] == ucArg) && (puc[4] == (BYTE)(ulVal >> 24)) &&
       (puc[5] == (BYTE)(ulVal >> 16)) && (puc[6] == (BYTE)(ulVal >> 8)) && (puc[7] == (BYTE)ulVal))
    {
        return;                                     // a repeat of the last line (probes in retry loops)
    }
    puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(ucN)];
    puc[0] = ucId;
    puc[1] = ucArg;
    puc[2] = (BYTE)(usNow >> 8);
    puc[3] = (BYTE)usNow;
    puc[4] = (BYTE)(ulVal >> 24);
    puc[5] = (BYTE)(ulVal >> 16);
    puc[6] = (BYTE)(ulVal >> 8);
    puc[7] = (BYTE)ulVal;
    g_stAwtoSync.ucSeq = AWTO_SYNC_NEXT(ucN);
}

// New episode: time base, per-port detect state, console request. A switch inside a power-on / wake that has not settled
// is one more line of that episode (the SDK switches to the stored port during boot).
void AwtoSyncBegin(BYTE ucKind, BYTE ucPort)
{
    BYTE ucI;
    WORD usNow;

    if((ucKind == AWTO_SYNC_K_SWITCH) && (g_stAwtoSync.ucKind != AWTO_SYNC_K_SWITCH) && (g_stAwtoSync.ucDone == 0))
    {
        AwtoSyncPush(AWTO_SYNC_EV_BEGIN, ucKind, ucPort);
        return;
    }
    if((AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, g_stAwtoSync.ucEpSeq) == 1) && (g_stAwtoSync.ucKind == ucKind) && (g_stAwtoSync.ucPort == ucPort))
    {
        return;                                     // the same start again (DDC/CI select, then SysSourceSwitchInputPort)
    }
    g_stAwtoSync.ucEpSeq = g_stAwtoSync.ucSeq;
    usNow = AwtoSyncNow();
    g_stAwtoSync.ucT0Hi = (BYTE)(usNow >> 8);
    g_stAwtoSync.ucT0Lo = (BYTE)usNow;
    g_stAwtoSync.ucKind = ucKind;
    g_stAwtoSync.ucPort = ucPort;
    g_stAwtoSync.ucDone = 0;
    g_stAwtoSync.ucOpenReq = 1;
    for(ucI = 0; ucI < 3; ucI++)
    {
        s_pucAwtoSyncDet[ucI] = _SOURCE_NONE << 1;
    }
    AwtoSyncPush(AWTO_SYNC_EV_BEGIN, ucKind, ucPort);
}

void AwtoSyncInit(void)                             // boot (before SysMainSystemInitial): the power-on episode
{
    g_stAwtoSync.ucMagic0 = 'S';
    g_stAwtoSync.ucMagic1 = 'Y';
    g_stAwtoSync.ucVersion = 1;
    g_stAwtoSync.ucKind = 0;
    g_ucAwtoSyncPwr = _POWER_STATUS_AC_ON;
    AwtoSyncBegin(AWTO_SYNC_K_POWER_ON, 0xFF);
}

// Switch-log events (awto_sw.inc AwtoSwEvent) that have a sync.tsv row go into the ring too.
void AwtoSyncSw(BYTE ucId, BYTE ucArg)
{
    if((ucId == AWTO_SW_EV_HOLD) && (ucArg == 5))
    {
        AwtoSyncBegin(AWTO_SYNC_K_WAKE, SysSourceGetInputPort());     // #78 held port has its signal back
    }
    if((ucId == AWTO_SW_EV_MODE) && ((ucArg == _MODE_STATUS_ACTIVE) || (ucArg == _MODE_STATUS_NOSIGNAL) ||
       (ucArg == _MODE_STATUS_NOSUPPORT) || (ucArg == _MODE_STATUS_POWER_SAVING)))
    {
        g_stAwtoSync.ucDone = 1;
    }
    if(AwtoSyncRow(ucId, ucArg) != 0)
    {
        AwtoSyncPush(ucId, ucArg, 0);
    }
}

// End of SysSourceDetectPort (one search index per call): predetect / scan result changes of a board port.
void AwtoSyncDetect(BYTE ucPort, BYTE ucKind, BYTE ucPre, BYTE ucType)
{
    BYTE ucI = ucPort - _D1_INPUT_PORT;
    BYTE ucNew = (ucPre & 1) | (ucType << 1);
    BYTE ucOld;

    if(ucI > 2)
    {
        return;
    }
    ucOld = s_pucAwtoSyncDet[ucI];
    if(ucNew == ucOld)
    {
        return;
    }
    s_pucAwtoSyncDet[ucI] = ucNew;
    if(((ucNew & 1) != 0) && ((ucOld & 1) == 0))
    {
#if(_DP_SUPPORT == _ON)
        if(ucKind == _PORT_DP)
        {
            AwtoSyncPush(AWTO_SYNC_EV_DP, ucPort, ((DWORD)ScalerDpGetLinkRate(ucPort) << 8) | ScalerDpGetLaneCount(ucPort));
        }
        else
#endif
        {
            AwtoSyncPush(AWTO_SYNC_EV_TMDS, ucPort, g_usTmdsOffLineMeasureClk);    // SDK freq-stable value, 0.1 MHz
        }
    }
    else if(((ucNew & 1) == 0) && ((ucOld & 1) != 0))
    {
        AwtoSyncPush(AWTO_SYNC_EV_LOST, ucPort, 0);
    }
    if(((ucNew >> 1) != _SOURCE_NONE) && ((ucNew >> 1) != (ucOld >> 1)))
    {
        AwtoSyncPush(AWTO_SYNC_EV_SCAN, ucPort, ucNew >> 1);
    }
}

void AwtoSyncTiming(void)                           // SysModeHandler: timing confirmed (measure done)
{
    BYTE ucPort = SysSourceGetInputPort();

    AwtoSyncPush(AWTO_SYNC_EV_TIMING, ucPort, ((DWORD)GET_INPUT_TIMING_HWIDTH() << 16) | GET_INPUT_TIMING_VHEIGHT());
}

void AwtoSyncFreq(void)                             // SysModeHandler: display setting done; exact values (#34) when counted
{
#if(_AWTO_FREQ == _ON)
    BYTE ucPort = SysSourceGetInputPort();

    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_VFREQ, ucPort, g_stAwtoFreq.ulVFreqmHz);
        AwtoSyncPush(AWTO_SYNC_EV_PCLK, ucPort, g_stAwtoFreq.ulPclkHz / 1000);
    }
#endif
}

__xdata BYTE g_ucAwtoSyncPwr;                       // power status the log last saw (AWTO_SYNC_POLL compares per pass)

void AwtoSyncPoll(void)                             // power status changed (AWTO_SYNC_POLL in AwtoSwPoll)
{
    BYTE ucP = GET_POWER_STATUS();

    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_SAVING))
    {
        AwtoSyncBegin(AWTO_SYNC_K_WAKE, SysSourceGetInputPort());
    }
    else if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_OFF))
    {
        AwtoSyncBegin(AWTO_SYNC_K_POWER_KEY, SysSourceGetInputPort());
    }
    else if((ucP == _POWER_STATUS_OFF) || (ucP == _POWER_STATUS_SAVING))
    {
        AwtoSyncPush(AWTO_SYNC_EV_POWER, ucP, 0);
        g_stAwtoSync.ucOpenReq = 0;
    }
    g_ucAwtoSyncPwr = ucP;
}

// Selector row getters (#139 task 2) ----
// Sync stage of a port: AWTO_SYNC_ST_*. Only the port the SDK works on has one; the others are idle.
BYTE AwtoSyncStage(BYTE ucPort)
{
    BYTE ucIdx;

    if(ucPort != SysSourceGetInputPort())
    {
        return AWTO_SYNC_ST_IDLE;
    }
#if(_AWTO_FAST_SWITCH == _ON)
    if(g_ucAwtoFastPending == ucPort)
    {
        return AWTO_SYNC_ST_FAST;
    }
#endif
    switch(GET_MODE_STATE())
    {
        case _MODE_STATUS_ACTIVE:           return AWTO_SYNC_ST_ACTIVE;
        case _MODE_STATUS_DISPLAY_SETTING:  return AWTO_SYNC_ST_DISPLAY;
        case _MODE_STATUS_NOSUPPORT:        return AWTO_SYNC_ST_NOSUPPORT;
        case _MODE_STATUS_POWER_SAVING:     return AWTO_SYNC_ST_SLEEP;
        case _MODE_STATUS_POWER_OFF:        return AWTO_SYNC_ST_OFF;
        case _MODE_STATUS_SEARCH:
        case _MODE_STATUS_NOSIGNAL:
            break;
        default:                            return AWTO_SYNC_ST_INIT;
    }
    ucIdx = SysSourceConvertSearchPort(ucPort);
    if(GET_SOURCE_JUDGE(ucIdx) == _TRUE)
    {
        return (GET_MODE_TIMING_CONFIRM() == _TRUE) ? AWTO_SYNC_ST_TIMING : AWTO_SYNC_ST_MEASURE;
    }
    if(GET_SOURCE_TYPE(ucIdx) != _SOURCE_NONE)
    {
        return AWTO_SYNC_ST_STABLE;
    }
    if(GET_SOURCE_PREDETECT(ucIdx) == _TRUE)
    {
        return AWTO_SYNC_ST_SCAN;
    }
    return (GET_MODE_STATE() == _MODE_STATUS_NOSIGNAL) ? AWTO_SYNC_ST_NOSIGNAL : AWTO_SYNC_ST_SEARCH;
}

// DDC activity per port: DDCn_EDID_IRQ bit2 SCL toggle / bit0 EDID read since clear (regdb FFE5 / FE69 / FE72, write 1 =
// clear). Bit2 is cleared only while its IRQ (bit3) is off: with it on, the SDK's EXINT1 DDC wake detect owns the flag.
static const __code WORD tAwtoDdcReg[3] = {AWTO_DDC_IRQ_D1, AWTO_DDC_IRQ_D2, AWTO_DDC_IRQ_D3};
BYTE AwtoDdcLive(BYTE ucI)                          // ucI = port - D1; called every AWTO_SRC_POLL_MS: 1 = traffic seen lately
{
    BYTE ucR = AWTO_XB(tAwtoDdcReg[ucI]);
    BYTE ucClr = ucR & _BIT0;

    if((ucR & _BIT3) == 0)
    {
        ucClr |= ucR & _BIT2;
    }
    if((ucR & (_BIT2 | _BIT0)) != 0)
    {
        s_pucAwtoDdcAge[ucI] = AWTO_SRC_DDC_POLLS;
        if(ucClr != 0)
        {
            AWTO_XB(tAwtoDdcReg[ucI]) = (ucR & ~(_BIT2 | _BIT0)) | ucClr;
        }
    }
    else if(s_pucAwtoDdcAge[ucI] != 0)
    {
        s_pucAwtoDdcAge[ucI]--;
    }
    return (s_pucAwtoDdcAge[ucI] != 0) ? 1 : 0;
}

// Idle HDMI port: TMDS clock from its free-running frequency detector, no switch (HDMI_FREQDET_*, P71 = Rx2 / D2, P72 = Rx3 /
// D3). kHz = count x (E7[6] ? 2 : 1) x crystal / reference cycles (F6[1:0]: 1000 << n), crystal reference (E6[3] = 0).
// 0 = no result (detector not started E6[7], no first result E6[6], or a TMDS reference E6[3]). Result popped by EC[7].
DWORD AwtoTmdsIdleKhz(BYTE ucPage)                  // ucPage = 0x71 / 0x72
{
    WORD usBase = (WORD)ucPage << 8;
    BYTE ucCtl = ScalerGetByte(usBase | 0xE6);
    WORD usCount;
    bit bEx0 = EX0;

    if((ucCtl & (_BIT7 | _BIT6 | _BIT3 | _BIT5 | _BIT4)) != (_BIT7 | _BIT6))
    {
        return 0;                                   // E6[5:4] != 0: the TMDS ISR is measuring a data lane right now
    }
    EX0 = 0;                                        // the TMDS ISR pops / re-programs this detector too
    ScalerSetBit(usBase | 0xEC, ~_BIT7, _BIT7);
    usCount = ((WORD)ScalerGetByte(usBase | 0xED) << 8) | ScalerGetByte(usBase | 0xEE);
    EX0 = bEx0;
    return (DWORD)usCount * ((ScalerGetBit(usBase | 0xE7, _BIT6) != 0) ? 2 : 1) * (AWTO_XTAL_HZ / 1000) /
           ((WORD)1000 << (ScalerGetByte(usBase | 0xF6) & 0x03));
}
#endif
