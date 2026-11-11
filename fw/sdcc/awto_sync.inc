// #139 sync / power-on log: a small I2C-readable ring of stage events (RL6449_Project.h StAwtoSync), one episode per
// power-on / input switch / wake. Texts: fw/awto/sync.tsv (scripts/gen_awto_sync.py); host decoder: scripts/sync_log.py.
// Also the port getters the selector rows read (stage, DDC activity, idle TMDS clock). Inserted into SysMain.c after awto_sw.inc.
#if(_AWTO_SYNC_LOG == _ON)
extern WORD g_usTmdsOffLineMeasureClk;              // ScalerCommonSync.c: SDK TMDS clock at freq-stable, 0.1 MHz
__xdata StAwtoSync g_stAwtoSync;
static __xdata BYTE s_pucAwtoSyncDet[3];          // D1..D3: last predetect (bit0) | source type << 1 seen by the port detect
static __xdata BYTE s_pucAwtoDdcAge[3];           // D1..D3: DDC polls left in which the port counts as live

// GENERATED-BEGIN awto_sync_rows
#define AWTO_SYNC_ROWS 85
static const __code BYTE tAwtoSyncRowId[85] = {
    0xD0, 0xD0, 0xD0, 0xD0, 0xD0, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD2, 0xD2, 0xD2,
    0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD5, 0xD6, 0xC0, 0xC0, 0xC0, 0xC0, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x10, 0x10, 0x10, 0x10, 0x70, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90,
    0x90, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA0, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8, 0xA8,
    0xB0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC7, 0xC8, 0xC9, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xD3,
    0xCF, 0xCF, 0xCF, 0xCF, 0xCF};
static const __code BYTE tAwtoSyncRowArg[85] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x01, 0x02, 0x03,
    0x01, 0x02, 0x03, 0x04, 0x05, 0xFF, 0xFF, 0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x00, 0x01, 0x02, 0x03, 0xFF, 0x01, 0x0E, 0x14, 0x15, 0x16, 0x17, 0x1A, 0x1B,
    0x1C, 0x00, 0x01, 0x03, 0x04, 0x05, 0xFF, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x10,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x03, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0x01, 0x02, 0x03, 0x04, 0x05};
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

// #29: ring time = usT2Isr (as before). Before Timer2 runs: the WDT counter (cleared by the first instruction, crt_rtd_startup;
// 143 us per CNT3 count, crystal), carried over the ScalerMcuInitial clear (AwtoSyncMark); at the Timer2 start those lines
// are moved to usT2Isr time and the power-on T0 set to -(ms since reset at usT2Isr = 0): the episode prints ms since reset.
static __xdata WORD s_usAwtoBootMs;                 // WDT ms at the ScalerMcuInitial clear
static __xdata WORD s_usAwtoT2Base;                 // 0xFFFF = Timer2 not started, else 0

static WORD AwtoSyncWdtMs(void)                     // ms on the WDT counter since its last clear (+ the carried part)
{
    WORD usC3;

    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT3;     // latch, no clear
    usC3 = (((WORD)(AWTO_XFR(0xFFAC) & 0x7F)) << 5) | (AWTO_XFR(0xFFAB) >> 3);
    return s_usAwtoBootMs + (WORD)(((DWORD)usC3 * 9375) >> 16) + (WORD)(AWTO_XFR(0xFFAD) & 0x07) * 586;
}

static WORD AwtoSyncNow(void)
{
    WORD usNow;

    if(s_usAwtoT2Base == 0xFFFF)
    {
        return AwtoSyncWdtMs();
    }
    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

void AwtoNvEv(BYTE ucStep)                          // #150 NVRAM save step; value = WDT ms since the last poke (crystal: counts a halt)
{
    WORD usC3;

#ifdef _AWTO_NEW_SETTINGS
    if(ucStep == 3)                                 // #151 counter: a sector erase (programs: AwtoWdtLibPoke)
    {
        AWTO_NV_OP();
    }
#endif
    if(g_stAwtoDiag.ucStage < 8)
    {
        return;                                     // boot-time flash ops would push the boot lines out of the 32-line ring
    }
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT3;     // latch, no clear
    usC3 = (((WORD)(AWTO_XFR(0xFFAC) & 0x7F)) << 5) | (AWTO_XFR(0xFFAB) >> 3);
    AwtoSyncPush(AWTO_SYNC_EV_NV, ucStep, (WORD)(((DWORD)usC3 * 9375) >> 16) + (WORD)(AWTO_XFR(0xFFAD) & 0x07) * 586);
}

void AwtoSyncMark(void)                             // ScalerMcuInitial, just before it clears the WDT
{
    WORD usNow = AwtoSyncWdtMs();

    AwtoSyncPush(AWTO_SYNC_EV_INIT, 1, 0);
    s_usAwtoBootMs = usNow;                         // carried over the clear that follows
}

void AwtoSyncT2Start(void)                          // every Timer2 reload (AwtoT0EvClock); the first starts the tick
{
    BYTE ucS;
    WORD usBase;
    WORD usMs;
    BYTE __xdata *puc;

    if(s_usAwtoT2Base != 0xFFFF)
    {
        return;
    }
    usBase = AwtoSyncWdtMs() - g_stAwtoDiag.usT2Isr;  // ms since reset at usT2Isr = 0
    s_usAwtoT2Base = 0;
    for(ucS = g_stAwtoSync.ucEpSeq; ucS != g_stAwtoSync.ucSeq; ucS = AWTO_SYNC_NEXT(ucS))
    {
        puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(ucS)];
        usMs = ((((WORD)puc[2]) << 8) | puc[3]) - usBase;      // lines so far: WDT time -> usT2Isr time
        puc[2] = (BYTE)(usMs >> 8);
        puc[3] = (BYTE)usMs;
    }
    g_stAwtoSync.ucT0Hi = (BYTE)((0 - usBase) >> 8);
    g_stAwtoSync.ucT0Lo = (BYTE)(0 - usBase);
    AwtoSyncPush(AWTO_SYNC_EV_INIT, 2, 0);
}

__xdata StAwtoSyncEv g_stAwtoSyncPin;               // #150: copy of this boot's reason line (the ring may lose it)

static bit AwtoSyncSame(BYTE ucBack, BYTE ucId, BYTE ucArg, DWORD ulVal)    // entry ucBack lines back = this event (time aside)
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, ucBack))];

    return (puc[0] == ucId) && (puc[1] == ucArg) && (puc[4] == (BYTE)(ulVal >> 24)) && (puc[5] == (BYTE)(ulVal >> 16)) &&
           (puc[6] == (BYTE)(ulVal >> 8)) && (puc[7] == (BYTE)ulVal);
}

static void AwtoSyncPut(BYTE ucId, BYTE ucArg, DWORD ulVal)
{
    BYTE ucN = g_stAwtoSync.ucSeq;
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(ucN)];
    WORD usNow = AwtoSyncNow();

    puc[0] = ucId;
    puc[1] = ucArg;
    puc[2] = (BYTE)(usNow >> 8);
    puc[3] = (BYTE)usNow;
    puc[4] = (BYTE)(ulVal >> 24);
    puc[5] = (BYTE)(ulVal >> 16);
    puc[6] = (BYTE)(ulVal >> 8);
    puc[7] = (BYTE)ulVal;
    g_stAwtoSync.ucSeq = AWTO_SYNC_NEXT(ucN);
    if(g_stAwtoGpio.ucOpen != 0)
    {
        AwtoConLogSync();                           // #144 live: the line shows now, also inside a blocking SDK step (panel on)
    }
}

// Repeats collapse (#150): the last line again is dropped (probes in retry loops); a pair repeating (A B A B, e.g. an idle
// port's predetect flapping in NO SIGNAL) is counted in ucSpare and written once as "the 2 lines above x N".
void AwtoSyncPush(BYTE ucId, BYTE ucArg, DWORD ulVal)
{
    BYTE ucK = AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, g_stAwtoSync.ucEpSeq);      // lines in this episode

    if((ucK >= 1) && (AwtoSyncSame(1, ucId, ucArg, ulVal) != 0))
    {
        return;
    }
    if(ucK >= 3)
    {
        BYTE __xdata *puc1 = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, 1))];
        DWORD ulV1 = ((DWORD)puc1[4] << 24) | ((DWORD)puc1[5] << 16) | ((WORD)puc1[6] << 8) | puc1[7];

        if((AwtoSyncSame(2, ucId, ucArg, ulVal) != 0) && (AwtoSyncSame(3, puc1[0], puc1[1], ulV1) != 0))
        {
            if(g_stAwtoSync.ucSpare != 0xFF)
            {
                g_stAwtoSync.ucSpare++;
            }
            return;
        }
    }
    if(g_stAwtoSync.ucSpare != 0)
    {
        BYTE ucR = g_stAwtoSync.ucSpare;

        g_stAwtoSync.ucSpare = 0;
        AwtoSyncPut(AWTO_SYNC_EV_REPEAT, 0, ucR);
    }
    AwtoSyncPut(ucId, ucArg, ulVal);
    if(ucId == AWTO_SYNC_EV_BOOT)
    {
        g_stAwtoSyncPin = g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, 1))];
    }
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
    if(ucKind == AWTO_SYNC_K_POWER_ON)
    {
        AwtoSyncPush(AWTO_SYNC_EV_BOOT, AwtoBootReason(), AwtoBootValue());     // first line: why it is running (#29)
        AwtoSyncPush(AWTO_SYNC_EV_STAGE, 1, 0);
    }
    AwtoSyncPush(AWTO_SYNC_EV_BEGIN, ucKind, ucPort);
}

void AwtoSyncInit(void)                             // boot (before SysMainSystemInitial): the power-on episode
{
    g_stAwtoSync.ucMagic0 = 'S';
    g_stAwtoSync.ucMagic1 = 'Y';
    g_stAwtoSync.ucVersion = 2;                     // 2: AWTO_SYNC_N 32, ms since reset in the power-on episode (#29)
    g_stAwtoSync.ucKind = 0;
    g_ucAwtoSyncPwr = _POWER_STATUS_AC_ON;
    s_usAwtoT2Base = 0xFFFF;
    AwtoSyncBegin(AWTO_SYNC_K_POWER_ON, 0xFF);
    g_stAwtoSync.ucT0Hi = 0;                        // power-on lines print ms since reset
    g_stAwtoSync.ucT0Lo = 0;
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
#if(_AWTO_PS_WAKE == _ON)
        if(ucArg == _MODE_STATUS_ACTIVE)
        {
            AwtoPsWakeReset();
        }
#endif
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

#if(_AWTO_PS_WAKE == _ON)
// #144 wake from power saving on a source event, any port, every main-loop pass (the SDK predetects one search port per
// pass with a 2-3 s dwell). Edge / event based; each trigger wakes once per port per sleep episode (until a picture):
// a source that polls DDC / AUX while off wakes the monitor once, then is logged as suppressed.
__xdata BYTE g_ucAwtoPsWakeCon;                       // 1 = our trigger woke it: console + panel at power NORMAL
static __xdata BYTE s_ucWakeCable;                  // bit i = port D1 + i cable at the last poll
static __xdata BYTE s_ucWakeDpcd;                   // DPCD 600h at the last poll (1 = D0, 2 = D3)
static __xdata BYTE s_pucWakeUsed[AWTO_WAKE_T_N];   // per trigger: bit i = port D1 + i woke the monitor this sleep episode
static __xdata BYTE s_pucWakeSaid[AWTO_WAKE_T_N];   // per trigger: suppression already logged since the sleep began
extern BYTE ScalerDpRx1GetDpcdInfo(BYTE ucH, BYTE ucM, BYTE ucL);
extern bit SysSourceGetCableDetect(BYTE ucInputPort);           // SysInterface.h (not in this translation unit)
extern void SysPowerSetTargetPowerStatus(EnumPowerStatus enumPorStatus);
static const __code WORD tAwtoWakeDdc[3] = {AWTO_DDC_IRQ_D1, AWTO_DDC_IRQ_D2, AWTO_DDC_IRQ_D3};

static BYTE AwtoPsWakeCables(void)
{
    BYTE ucI, ucB = 0;

    for(ucI = 0; ucI < 3; ucI++)
    {
        if(SysSourceGetCableDetect(_D1_INPUT_PORT + ucI) == _TRUE)   // SDK debounced cable status, as the selector shows it
        {
            ucB |= (BYTE)1 << ucI;
        }
    }
    return ucB;
}

static const __code WORD tAwtoWakeAux[2] = {0xB7DC, 0xBADC};

static BYTE AwtoPsWakeAux(void)                       // DP AUX command received (aux_rx_int, W1C); Rx0 B7 / Rx1 BA: both watched
{
    BYTE ucI, ucHit = 0;

    for(ucI = 0; ucI < 2; ucI++)
    {
        if(ScalerGetBit(tAwtoWakeAux[ucI], _BIT0) != 0)
        {
            ucHit = 1;                              // clear only a seen flag: a command between read and clear stays
            ScalerSetBit(tAwtoWakeAux[ucI], (_BIT5 | _BIT3 | _BIT2), _BIT0);    // enables kept, other W1C flags untouched
        }
    }
    return ucHit;
}

__xdata WORD g_usAwtoPsPolls;                       // #150: wake polls since power saving began (test readout)

// #150: state of our wake poll when the SDK woke the monitor itself: cable bits 2:0 (D1..D3 now), EDID latches 5:3, AUX 6,
// DPCD 600h = D0 7, polls since power saving 23:8
static DWORD AwtoPsWakeState(void)
{
    BYTE ucI, ucB = AwtoPsWakeCables();

    for(ucI = 0; ucI < 3; ucI++)
    {
        if((AWTO_XB(tAwtoWakeDdc[ucI]) & _BIT0) != 0)
        {
            ucB |= (BYTE)8 << ucI;
        }
    }
    if((ScalerGetBit(0xB7DC, _BIT0) != 0) || (ScalerGetBit(0xBADC, _BIT0) != 0))
    {
        ucB |= _BIT6;
    }
    if(ScalerDpRx1GetDpcdInfo(0x00, 0x06, 0x00) == 0x01)
    {
        ucB |= _BIT7;
    }
    return ((DWORD)g_usAwtoPsPolls << 8) | ucB;
}

void AwtoPsWakeArm(void)                              // power saving entered: baselines, latches cleared
{
    BYTE ucI;

    g_usAwtoPsPolls = 0;
    s_ucWakeCable = AwtoPsWakeCables();
    s_ucWakeDpcd = ScalerDpRx1GetDpcdInfo(0x00, 0x06, 0x00);
    for(ucI = 0; ucI < 3; ucI++)
    {
        AWTO_XB(tAwtoWakeDdc[ucI]) = (AWTO_XB(tAwtoWakeDdc[ucI]) & ~(_BIT2 | _BIT0)) | _BIT0;  // EDID-read latch only
    }
    AwtoPsWakeAux();
    for(ucI = 0; ucI < AWTO_WAKE_T_N; ucI++)
    {
        s_pucWakeSaid[ucI] = 0;
    }
}

void AwtoPsWakeReset(void)                            // a picture: every trigger may wake again
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_WAKE_T_N; ucI++)
    {
        s_pucWakeUsed[ucI] = 0;
    }
}

bit AwtoPsWakeFire(BYTE ucT, BYTE ucI)                 // trigger AWTO_WAKE_T_*, port index; 1 = woke
{
    BYTE ucBit = (BYTE)1 << ucI;

    if((s_pucWakeUsed[ucT] & ucBit) != 0)
    {
        if((s_pucWakeSaid[ucT] & ucBit) == 0)
        {
            s_pucWakeSaid[ucT] |= ucBit;
            AwtoSyncPush(AWTO_SYNC_EV_WAKE_OFF, ucT + 1, _D1_INPUT_PORT + ucI);
        }
        return 0;
    }
    s_pucWakeUsed[ucT] |= ucBit;
    AwtoSyncBegin(AWTO_SYNC_K_WAKE, _D1_INPUT_PORT + ucI);
    AwtoSyncPush((ucT == AWTO_WAKE_T_UNPLUG) ? AWTO_SYNC_EV_UNPLUG : (AWTO_SYNC_EV_WAKE + ucT), _D1_INPUT_PORT + ucI, 0);
    g_ucAwtoPsWakeCon = 1;
    SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
    return 1;
}

void AwtoPsWakePoll(void)                           // AWTO_SYNC_POLL: power saving, every pass
{
    BYTE ucI, ucNow, ucR, ucU;

    if(g_ucAwtoPsWakeCon != 0)
    {
        return;                                     // woken; the SDK powers up on its next pass
    }
    if(g_usAwtoPsPolls != 0xFFFF)
    {
        g_usAwtoPsPolls++;
    }
    ucNow = AwtoPsWakeCables();
    ucR = ucNow & ~s_ucWakeCable;                   // plug edges (not connected -> connected)
    ucU = s_ucWakeCable & ~ucNow;                   // unplug edges: a trigger of their own (once per port per episode)
    s_ucWakeCable = ucNow;
    for(ucI = 0; ucI < 3; ucI++)
    {
        if(((ucR & ((BYTE)1 << ucI)) != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_CABLE, ucI) != 0))
        {
            return;
        }
        if(((ucU & ((BYTE)1 << ucI)) != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_UNPLUG, ucI) != 0))
        {
            return;
        }
        ucNow = AWTO_XB(tAwtoWakeDdc[ucI]);
        if((ucNow & _BIT0) != 0)
        {
            AWTO_XB(tAwtoWakeDdc[ucI]) = (ucNow & ~(_BIT2 | _BIT0)) | _BIT0;
            if(AwtoPsWakeFire(AWTO_WAKE_T_EDID, ucI) != 0)
            {
                return;
            }
        }
    }
    if((AwtoPsWakeAux() != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_AUX, 0) != 0))             // index 0 = D1, the DP port
    {
        return;
    }
    ucNow = ScalerDpRx1GetDpcdInfo(0x00, 0x06, 0x00);
    ucR = s_ucWakeDpcd;
    s_ucWakeDpcd = ucNow;
    if(((ucNow & 0x07) == 0x01) && ((ucR & 0x07) != 0x01))
    {
        AwtoPsWakeFire(AWTO_WAKE_T_DPCD, 0);
    }
}
#endif

void AwtoSyncPoll(void)                             // power status changed (AWTO_SYNC_POLL in AwtoSwPoll)
{
    BYTE ucP = GET_POWER_STATUS();

#if(_AWTO_PS_WAKE == _ON)
    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoPsWakeCon != 0))
    {
        g_ucAwtoPsWakeCon = 0;                        // episode begun by AwtoPsWakeFire: console + panel now (as at power-on)
        AwtoBootConsole();
        AWTO_BOOT_PANEL_ON();
    }
    else
#endif
    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_SAVING))
    {
        AwtoSyncBegin(AWTO_SYNC_K_WAKE, SysSourceGetInputPort());
#if(_AWTO_PS_WAKE == _ON)
        AwtoSyncPush(AWTO_SYNC_EV_SDKWAKE, SysSourceGetInputPort(), AwtoPsWakeState());   // not our poll: the SDK's detect
#endif
    }
    else if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_OFF))
    {
        AwtoSyncBegin(AWTO_SYNC_K_POWER_KEY, SysSourceGetInputPort());
    }
    else if((ucP == _POWER_STATUS_OFF) || (ucP == _POWER_STATUS_SAVING))
    {
        AwtoSyncPush(AWTO_SYNC_EV_POWER, ucP, 0);
        g_stAwtoSync.ucOpenReq = 0;
#if(_AWTO_PS_WAKE == _ON)
        if(ucP == _POWER_STATUS_SAVING)
        {
            AwtoPsWakeArm();
        }
#endif
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
