// #139 sync / power-on log: a small I2C-readable ring of stage events (RL6449_Project.h StAwtoSync), one episode per
// power-on / input switch / wake. Texts: fw/awto/sync.tsv (scripts/gen_awto_sync.py); host decoder: scripts/sync_log.py.
// Also the port getters the selector rows read (stage, DDC activity, idle TMDS clock). Inserted into SysMain.c after awto_sw.inc.
extern WORD g_usTmdsOffLineMeasureClk;              // ScalerCommonSync.c: SDK TMDS clock at freq-stable, 0.1 MHz
__xdata StAwtoSync g_stAwtoSync;
static __xdata BYTE s_pucAwtoSyncDet[3];          // D1..D3: last predetect (bit0) | source type << 1 seen by the port detect
static __xdata BYTE s_pucAwtoDdcAge[3];           // D1..D3: DDC polls left in which the port counts as live

// GENERATED-BEGIN awto_sync_rows
#define AWTO_SYNC_ROWS 151
static const __code BYTE tAwtoSyncRowId[151] = {
    0xD0, 0xD0, 0xD0, 0xD0, 0xD0, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD2, 0xD2, 0xD2, 0xD4, 0xD4, 0xD4,
    0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD8, 0xD9,
    0xC0, 0xC0, 0xC0, 0xC0, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x11,
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12,
    0x12, 0x13, 0x14, 0x1C, 0x1C, 0x1C, 0x90, 0x90, 0x90, 0x90, 0xA0, 0xA0, 0xA0, 0xA0, 0xA8, 0xB0,
    0xB1, 0xC1, 0xC6, 0xC2, 0xC3, 0xC4, 0xC5, 0xC7, 0xC8, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xD3, 0xDC,
    0xDD, 0xDA, 0xDB, 0xDE, 0xDF, 0xDF, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0,
    0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE2, 0xE2, 0xE2, 0xE2, 0xE2,
    0xE2, 0xCF, 0xCF, 0xCF, 0xCF, 0xCF, 0xCF};
static const __code BYTE tAwtoSyncRowArg[151] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x01, 0x02, 0x03, 0x04, 0x06, 0x01, 0x02, 0x03, 0x01, 0x02, 0x03,
    0x04, 0x05, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x0C, 0xFF, 0xFF, 0xFF, 0x01, 0x02, 0xFF,
    0x01, 0x02, 0x03, 0x04, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0E, 0x0F, 0x01,
    0x12, 0x1B, 0x23, 0x2B, 0x34, 0x45, 0x49, 0x54, 0x56, 0x67, 0x68, 0x78, 0x84, 0x89, 0x94, 0x9A,
    0xA4, 0xAB, 0xB0, 0x0B, 0x4A, 0xFF, 0x00, 0x01, 0x02, 0x12, 0x22, 0x32, 0x03, 0x13, 0x23, 0x33,
    0x04, 0xFF, 0xFF, 0x00, 0x01, 0x02, 0x14, 0x15, 0x16, 0x17, 0x01, 0x03, 0x04, 0xFF, 0x10, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x02, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x01, 0x09, 0x0B, 0x0D, 0x20,
    0xFF, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
static const __code BYTE tAwtoSyncIdRow[256] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 37, 48, 71, 82, 83, 0, 0, 0, 0, 0, 0, 0, 84, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 87, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    91, 0, 0, 0, 0, 0, 0, 0, 95, 0, 0, 0, 0, 0, 0, 0, 96, 97, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    33, 98, 100, 101, 102, 103, 99, 104, 105, 0, 106, 107, 108, 109, 110, 146, 1, 6, 11, 111, 14, 27, 28, 29, 30, 32, 114, 115, 112, 113, 116, 117,
    119, 129, 140, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
BYTE AwtoSyncRow(BYTE ucId, BYTE ucArg)           // row + 1 of the first match (arg 0xFF = any), 0 = not logged
{
    BYTE ucI = tAwtoSyncIdRow[ucId];

    if(ucI == 0)
    {
        return 0;
    }
    for(ucI--; (ucI < AWTO_SYNC_ROWS) && (tAwtoSyncRowId[ucI] == ucId); ucI++)
    {
        if((tAwtoSyncRowArg[ucI] == 0xFF) || (tAwtoSyncRowArg[ucI] == ucArg))
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
    usC3 = (((WORD)(AWTO_XFR(AWTO_R_WATCHDOG_CNT3_VALUE) & AWTO_F_WATCHDOG_CNT3_VALUE_WDT_CNT3_H_VALUE)) << 5) | (AWTO_XFR(AWTO_R_WATCHDOG_CNT23_VALUE) >> 3);
    return s_usAwtoBootMs + (WORD)(((DWORD)usC3 * 9375) >> 16) + (WORD)(AWTO_XFR(AWTO_R_WATCHDOG_CNT1_VALUE) & AWTO_F_WATCHDOG_CNT1_VALUE_WDT_CNT1_VALUE) * 586;
}

#if(_AWTO_FLASH_ALL == _ON)
extern BYTE g_ucFlashType;                          // ScalerCommonNVRam.c: the SDK detects it at its first flash write
static __xdata BYTE s_ucAwtoFlashLogged = 0xFF;     // type last logged (0xFF: none yet; no table entry has it)
#endif

void AwtoNvEv(BYTE ucStep)                          // #150 NVRAM save step; value = WDT ms since the last poke (crystal: counts a halt)
{
    WORD usC3;

#ifdef _AWTO_NEW_SETTINGS
    if(ucStep == 3)                                 // #151 counter: a sector erase (programs: AwtoWdtLibPoke)
    {
        AWTO_NV_OP();
        g_stAwtoNv.usErase++;
    }
#endif
    if(g_stAwtoDiag.ucStage < 8)
    {
        return;                                     // boot-time flash ops would push the boot lines out of the 32-line ring
    }
#if(_AWTO_FLASH_ALL == _ON)
    if(g_ucFlashType != s_ucAwtoFlashLogged)        // first NVRAM step after the SDK's detection: the type it found, once
    {
        s_ucAwtoFlashLogged = g_ucFlashType;
        AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_FLASH_TYPE, g_ucFlashType);
    }
#endif
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT3;     // latch, no clear
    usC3 = (((WORD)(AWTO_XFR(AWTO_R_WATCHDOG_CNT3_VALUE) & AWTO_F_WATCHDOG_CNT3_VALUE_WDT_CNT3_H_VALUE)) << 5) | (AWTO_XFR(AWTO_R_WATCHDOG_CNT23_VALUE) >> 3);
    AwtoSyncPush(AWTO_SYNC_EV_NV, ucStep, (WORD)(((DWORD)usC3 * 9375) >> 16) + (WORD)(AWTO_XFR(AWTO_R_WATCHDOG_CNT1_VALUE) & AWTO_F_WATCHDOG_CNT1_VALUE_WDT_CNT1_VALUE) * 586);
}

void AwtoSyncMark(void)                             // ScalerMcuInitial, just before it clears the WDT
{
    WORD usNow = AwtoSyncWdtMs();

    AwtoSyncPush(AWTO_SYNC_EV_INIT, 1, AWTO_WDT_N_BOOT_FIELD + 1);
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
    WORD usNow = (WORD)AwtoMs();

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
// #165 the first M-domain set-up of a boot, step by step (was the _AWTO_MEAS4K event table): AWTO_MSTEP call sites
__xdata BYTE g_ucAwtoMstepN;
__xdata BYTE g_ucAwtoMemForce;                   // test cmds 0x0C / 0x0D (#165 step 2)

void AwtoMstep(BYTE ucId, BYTE ucArg, WORD usVal)
{
    if(g_ucAwtoMstepN >= AWTO_MSTEP_MAX)
    {
        return;                                     // first set-up logged (or the cap line written)
    }
    g_ucAwtoMstepN++;
    if((g_ucAwtoMstepN == AWTO_MSTEP_MAX) && (ucId != AWTO_MSTEP_LAST))
    {
        AwtoSyncPush(AWTO_SYNC_EV_MSTEP, 0xFF, AWTO_MSTEP_MAX);
        return;
    }
    AwtoSyncPush(AWTO_SYNC_EV_MSTEP, ucId, ((DWORD)ucArg << 16) | usVal);
    if(ucId == AWTO_MSTEP_LAST)
    {
        g_ucAwtoMstepN = AWTO_MSTEP_MAX;
    }
}

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

// One time base for all our code: Timer2 ISR count (usT2Isr = low word, g_stAwtoHt.usUpHi = high word, both bumped in the ISR).
// Before Timer2 runs it is the WDT-counter time (ring lines are re-based at the Timer2 start). SDK event table (g_usTimerCounter) is separate.
__xdata StAwtoHt g_stAwtoHt;

unsigned long AwtoMs(void)
{
    bit bEa;
    WORD usHi;
    WORD usLo;

    if(s_usAwtoT2Base == 0xFFFF)
    {
        return AwtoSyncWdtMs();
    }
    bEa = EA;
    EA = 0;                                         // ISR bumps lo then hi: a read between them would be 65536 ms short
    usLo = g_stAwtoDiag.usT2Isr;
    usHi = g_stAwtoHt.usUpHi;
    EA = bEa;
    return ((DWORD)usHi << 16) | usLo;
}

// #157 DDC/CI host time (awto_ddcci.inc): RAM only. Ring lines at the first sync of this boot and on a drift over AWTO_HT_DRIFT_MS.
void AwtoHtSync(BYTE *puc)                          // unix s BE x4, ms BE x2, UTC offset (15 min, signed)
{
    DWORD ulNow = AwtoMs();
    DWORD ulE = ((DWORD)puc[0] << 24) | ((DWORD)puc[1] << 16) | ((DWORD)puc[2] << 8) | puc[3];
    WORD usF = ((WORD)puc[4] << 8) | puc[5];
    long lS;
    long lD = 0;
    BYTE ucWhy = 1;

    if(usF > 999)
    {
        return;                                     // not a ms field: not ours
    }
    if(g_stAwtoHt.ucSyncs != 0)
    {
        lS = (long)(ulE - g_stAwtoHt.ulEpoch);
        lD = ((lS > AWTO_HT_GAP_S) || (lS < -AWTO_HT_GAP_S)) ? 0x7FFFFFFFL :
             (lS * 1000 + (long)usF - (long)g_stAwtoHt.usFrac - (long)(ulNow - g_stAwtoHt.ulFwMs));
        ucWhy = ((lD > AWTO_HT_DRIFT_MS) || (lD < -AWTO_HT_DRIFT_MS)) ? 2 : 0;
        if(g_stAwtoHt.ucSyncs != 0xFF)
        {
            g_stAwtoHt.ucSyncs++;
        }
    }
    else
    {
        g_stAwtoHt.ucSyncs = 1;
    }
    g_stAwtoHt.ulEpoch = ulE;
    g_stAwtoHt.usFrac = usF;
    g_stAwtoHt.cOfs = (signed char)puc[6];
    g_stAwtoHt.ulFwMs = ulNow;
    g_stAwtoHt.iDrift = (lD > 32767) ? 32767 : ((lD < -32767) ? -32767 : (int)lD);
    if(ucWhy != 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_HOST, puc[6], ulE);
        AwtoSyncPush(AWTO_SYNC_EV_HOSTFW, ucWhy, ulNow);
        if(ucWhy == 2)
        {
            AwtoSyncPush(AWTO_SYNC_EV_DRIFT, 0, (DWORD)lD);
        }
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
    usNow = (WORD)AwtoMs();
    g_stAwtoSync.ucT0Hi = (BYTE)(usNow >> 8);
    g_stAwtoSync.ucT0Lo = (BYTE)usNow;
    g_stAwtoSync.ucKind = ucKind;
    g_stAwtoSync.ucPort = ucPort;
    g_stAwtoSync.ucDone = 0;
    if(g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY)
    {
        g_stAwtoSync.ucOpenReq = 1;
    }
    for(ucI = 0; ucI < 3; ucI++)
    {
        s_pucAwtoSyncDet[ucI] = _SOURCE_NONE << 1;
    }
    if(ucKind == AWTO_SYNC_K_POWER_ON)
    {
        AwtoSyncPush(AWTO_SYNC_EV_BOOT, AwtoBootReason(), AwtoBootValue());     // first line: why it is running (#29)
        AwtoSyncPush(AWTO_SYNC_EV_STAGE, 1, 0);
    }
    AwtoSyncPush(AWTO_SYNC_EV_BEGIN, ucKind, ((AwtoMs() >> 16) << 8) | ucPort);   // #157 anchor: fw ms bits 31..16 above the port
}

void AwtoSyncInit(void)                             // boot (before SysMainSystemInitial): the power-on episode
{
    g_stAwtoSync.ucMagic0 = 'S';
    g_stAwtoSync.ucMagic1 = 'Y';
    g_stAwtoSync.ucVersion = 3;
    g_stAwtoSync.ucN = AWTO_SYNC_N;
    g_stAwtoSync.ucWrap = AWTO_SYNC_WRAP;
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

#if(_AWTO_PS_WAKE == _ON)
static BYTE AwtoPsTmdsStable(BYTE ucPage);
static WORD AwtoPsTmdsClk(WORD usBase);
#endif
static __xdata BYTE s_ucTmdsPend;                   // bit i: HDMI port Di+1 predetect logged, clock not yet measured stable

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
#if(_AWTO_PS_WAKE == _ON)
    if(((s_ucTmdsPend & ((BYTE)1 << ucI)) != 0) && (AwtoPsTmdsStable(0x70 + ucI) != 0))
    {
        s_ucTmdsPend &= ~((BYTE)1 << ucI);
        AwtoSyncPush(AWTO_SYNC_EV_TMDS_CLK, ucPort, AwtoPsTmdsClk((WORD)(0x70 + ucI) << 8));
    }
#endif
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
            AwtoSyncPush(AWTO_SYNC_EV_TMDS, ucPort, 0);
            s_ucTmdsPend |= (BYTE)1 << ucI;
        }
    }
    else if(((ucNew & 1) == 0) && ((ucOld & 1) != 0))
    {
        AwtoSyncPush(AWTO_SYNC_EV_LOST, ucPort, 0);
        s_ucTmdsPend &= ~((BYTE)1 << ucI);
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
    BYTE ucPort = SysSourceGetInputPort();

    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_VFREQ, ucPort, g_stAwtoFreq.ulVFreqmHz);
        AwtoSyncPush(AWTO_SYNC_EV_PCLK, ucPort, g_stAwtoFreq.ulPclkHz / 1000);
    }
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

static const __code WORD tAwtoWakeAux[2] = {AWTO_R_PB7_AUX_IRQ_STATUS, AWTO_R_PBA_AUX_IRQ_STATUS};

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
__xdata WORD g_usAwtoPsGap;                         // longest ms between two wake polls this episode (test readout)
static __xdata WORD s_usWakeAt;                     // usT2Isr of the last wake poll
static __xdata BYTE s_ucWakeArmed;                  // 1 = AwtoPsWakeArm ran: the freq detectors are ours

// HDMI freq detector, SDK sequence of ScalerTMDSRx2TMDSPSPreDetect (regdb HDMI_FREQDET_CTRL / ERROR_TH, P71 = D2, P72 = D3):
// start E6[7] on the TMDS clock (E6[5:4] 0), W1C stable EF[6] and unstable E6[2]. Read back >= AWTO_PS_POLL_MS later.
static void AwtoPsTmdsStart(WORD usBase)
{
    ScalerSetBit(usBase | 0xE6, ~(_BIT7 | _BIT5 | _BIT4), 0x00);
    ScalerSetBit(usBase | 0xE6, ~_BIT7, _BIT7);
    ScalerSetBit(usBase | 0xEF, ~_BIT6, _BIT6);
    ScalerSetBit(usBase | 0xE6, ~_BIT2, _BIT2);
}

// The SDK's freq-detect criterion: started, first result done, no unstable since the start, stable at least once.
static BYTE AwtoPsTmdsStable(BYTE ucPage)
{
    WORD usBase = (WORD)ucPage << 8;

    return ((ScalerGetBit(usBase | 0xE6, (_BIT7 | _BIT6 | _BIT2)) == (_BIT7 | _BIT6)) &&
            (ScalerGetBit(usBase | 0xEF, _BIT6) == _BIT6)) ? 1 : 0;
}

// Power-saving wake criterion: our detector armed, cable required.
BYTE AwtoPsTmdsLive(BYTE ucPage)
{
    if((s_ucWakeArmed == 0) || (SysSourceGetCableDetect((ucPage == 0x71) ? _D2_INPUT_PORT : _D3_INPUT_PORT) != _TRUE))
    {
        return 0;
    }
    return AwtoPsTmdsStable(ucPage);
}

static WORD AwtoPsTmdsClk(WORD usBase)              // 0.1 MHz: count x (E7[6] ? 2 : 1) x IOSC / (1000 << F6[1:0]) ref cycles
{
    WORD usCount;
    bit bEx0 = EX0;

    EX0 = 0;                                        // the TMDS ISR pops this detector too
    ScalerSetBit(usBase | 0xEC, ~_BIT7, _BIT7);
    usCount = ((WORD)ScalerGetByte(usBase | 0xED) << 8) | ScalerGetByte(usBase | 0xEE);
    EX0 = bEx0;
    return (WORD)((DWORD)usCount * ((ScalerGetBit(usBase | 0xE7, _BIT6) != 0) ? 2 : 1) * (AWTO_IOSC_KHZ / 100) /
                  ((WORD)1000 << (ScalerGetByte(usBase | 0xF6) & 0x03)));
}

// #150: state of our wake poll when the SDK woke the monitor itself: cable bits 2:0 (D1..D3 now), EDID latches 5:3, AUX 6,
// DPCD 600h = D0 7, polls since power saving 23:8, TMDS live D2 24 / D3 25
static DWORD AwtoPsWakeState(void)
{
    BYTE ucI, ucB = AwtoPsWakeCables();
    DWORD ulT = ((DWORD)AwtoPsTmdsLive(0x71) << 24) | ((DWORD)AwtoPsTmdsLive(0x72) << 25);

    for(ucI = 0; ucI < 3; ucI++)
    {
        if((AWTO_XB(tAwtoWakeDdc[ucI]) & _BIT0) != 0)
        {
            ucB |= (BYTE)8 << ucI;
        }
    }
    if((ScalerGetBit(AWTO_R_PB7_AUX_IRQ_STATUS, AWTO_F_PB7_AUX_IRQ_STATUS_AUX_RX_INT) != 0) || (ScalerGetBit(AWTO_R_PBA_AUX_IRQ_STATUS, AWTO_F_PBA_AUX_IRQ_STATUS_AUX_RX_INT) != 0))
    {
        ucB |= _BIT6;
    }
    if(ScalerDpRx1GetDpcdInfo(0x00, 0x06, 0x00) == 0x01)
    {
        ucB |= _BIT7;
    }
    return ulT | ((DWORD)g_usAwtoPsPolls << 8) | ucB;
}

bit AwtoPsWakeFire(BYTE ucT, BYTE ucI, WORD usVal);
__xdata DWORD g_ulAwtoPsMs;                         // #144 ms in power status SAVING this episode (sum of poll gaps; test readout)
__xdata BYTE g_ucAwtoPsWakes;                       // wakes from SAVING since boot, any path (test readout)
__xdata WORD g_usAwtoPsTmdsLive;                    // polls with a TMDS clock live this episode, D2 + D3 (test readout)
__xdata WORD g_usAwtoPsTmdsRun;                     // longest TMDS live run this episode, ms (test readout)
__xdata WORD g_usAwtoPsDdc;                         // SDK DDC handshakes (SCL toggle) seen in SAVING since boot, gated (test readout)
__xdata WORD g_usAwtoPsAux;                         // SDK DP AUX toggles seen in SAVING since boot, gated (test readout)
static __xdata WORD s_pusTmdsFirst[2];              // D2 / D3: AwtoMs of the first live poll of the current run
static __xdata WORD s_pusTmdsLast[2];               // D2 / D3: last live poll
static __xdata BYTE s_ucTmdsRun;                    // bit i - 1: a run is open on port D1 + i
static __xdata BYTE s_ucPsSaid;                     // lines logged this sleep: bit 0 AUX cmd, bit i burst (D1 + i), bit 4 + i DDC, bit 7 SDK AUX

// SDK TMDS PS predetect (keil2sdcc sub): a DDC handshake (any SCL toggle on the port's DDC, e.g. a DDC/CI or 0x35 access)
// is counted, never a wake; an EDID read still wakes through AWTO_WAKE_T_EDID. Line once per sleep.
void AwtoPsDdcSeen(BYTE ucPort)
{
    BYTE ucBit = (BYTE)0x10 << (ucPort - _D1_INPUT_PORT);

    if(g_usAwtoPsDdc != 0xFFFF)
    {
        g_usAwtoPsDdc++;
    }
    if((s_ucPsSaid & ucBit) == 0)
    {
        s_ucPsSaid |= ucBit;
        AwtoSyncPush(AWTO_SYNC_EV_PS_DDC, ucPort, 0);
    }
}

#if(_AWTO_PS_AUX_WAKE == _OFF)
__xdata BYTE g_ucAwtoPsAuxWakeOff;                  // marker in the map (D:) for wake_sim: no AUX-command wake
#endif
void AwtoPsAuxSeen(BYTE ucPort)                     // SDK DP PS predetect: AUX toggle counted, no wake; line once per sleep
{
    if(g_usAwtoPsAux != 0xFFFF)
    {
        g_usAwtoPsAux++;
    }
    if((s_ucPsSaid & _BIT7) == 0)
    {
        s_ucPsSaid |= _BIT7;
        AwtoSyncPush(AWTO_SYNC_EV_PS_AUX, ucPort, 0);
    }
}

// TMDS wake: live at every restarted measurement for AWTO_PS_TMDS_HOLD_MS, no gap > AWTO_PS_TMDS_GAP_MS; 1 = woke
static BYTE AwtoPsTmdsHold(BYTE ucI, WORD usNow)
{
    BYTE ucB = (BYTE)1 << (ucI - 1);
    WORD usBase = (WORD)(0x70 + ucI) << 8;
    WORD usRun;

    if(AwtoPsTmdsLive(0x70 + ucI) != 0)
    {
        if(g_usAwtoPsTmdsLive != 0xFFFF)
        {
            g_usAwtoPsTmdsLive++;
        }
        if((s_ucTmdsRun & ucB) == 0)
        {
            s_ucTmdsRun |= ucB;
            s_pusTmdsFirst[ucI - 1] = usNow;
        }
        s_pusTmdsLast[ucI - 1] = usNow;
        usRun = usNow - s_pusTmdsFirst[ucI - 1];
        if(usRun > g_usAwtoPsTmdsRun)
        {
            g_usAwtoPsTmdsRun = usRun;
        }
        if(usRun >= AWTO_PS_TMDS_HOLD_MS)
        {
            s_ucTmdsRun &= ~ucB;
            return (AwtoPsWakeFire(AWTO_WAKE_T_TMDS, ucI, AwtoPsTmdsClk(usBase)) != 0) ? 1 : 0;
        }
        AwtoPsTmdsStart(usBase);                    // measure again: the next poll sees only a clock that is still there
        return 0;
    }
    if(((s_ucTmdsRun & ucB) != 0) && ((WORD)(usNow - s_pusTmdsLast[ucI - 1]) > AWTO_PS_TMDS_GAP_MS))
    {
        s_ucTmdsRun &= ~ucB;                        // the clock went away before the hold: a burst, no wake
        if((s_ucPsSaid & ((BYTE)1 << ucI)) == 0)
        {
            s_ucPsSaid |= (BYTE)1 << ucI;
            AwtoSyncPush(AWTO_SYNC_EV_PS_BURST, _D1_INPUT_PORT + ucI, s_pusTmdsLast[ucI - 1] - s_pusTmdsFirst[ucI - 1]);
        }
    }
    if(((s_ucWakeCable & ((BYTE)1 << ucI)) != 0) && ((s_ucTmdsRun & ucB) == 0) &&
       (ScalerGetBit(usBase | 0xE6, (_BIT7 | _BIT2)) != _BIT7))
    {
        AwtoPsTmdsStart(usBase);                    // stopped, or unstable since the start (no clock): measure again
    }
    return 0;
}

void AwtoPsWakeArm(void)                              // power saving entered: baselines, latches cleared
{
    BYTE ucI;

    g_usAwtoPsPolls = 0;
    g_usAwtoPsGap = 0;
    g_ulAwtoPsMs = 0;
    g_usAwtoPsTmdsLive = 0;
    g_usAwtoPsTmdsRun = 0;
    s_ucTmdsRun = 0;
    s_ucPsSaid = 0;
    s_usWakeAt = (WORD)AwtoMs();
    AwtoPsTmdsStart(0x7100);                        // pre-PS stable latches must not count (SDK PS bounds are set by now)
    AwtoPsTmdsStart(0x7200);
    s_ucWakeArmed = 1;
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

bit AwtoPsWakeFire(BYTE ucT, BYTE ucI, WORD usVal)   // trigger AWTO_WAKE_T_*, port index, line value; 1 = woke
{
    BYTE ucBit = (BYTE)1 << ucI;
    BYTE ucId = (ucT == AWTO_WAKE_T_UNPLUG) ? AWTO_SYNC_EV_UNPLUG : ((ucT == AWTO_WAKE_T_TMDS) ? AWTO_SYNC_EV_WAKE_TMDS : (AWTO_SYNC_EV_WAKE + ucT));

    if(AWTO_PORT_OFF(_D1_INPUT_PORT + ucI))     // #81: a disabled port never wakes the monitor (one line per trigger per sleep)
    {
        if((s_pucWakeSaid[ucT] & ucBit) == 0)
        {
            s_pucWakeSaid[ucT] |= ucBit;
            AwtoSyncPush(AWTO_SYNC_EV_PORT, AWTO_PORT_WHY_WAKE, _D1_INPUT_PORT + ucI);
        }
        return 0;
    }

    if(((s_pucWakeUsed[ucT] & ucBit) != 0) && (ucT != AWTO_WAKE_T_TMDS))     // TMDS: the hold is the gate
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
    AwtoSyncPush(ucId, _D1_INPUT_PORT + ucI, usVal);
    g_ucAwtoPsWakeCon = 1;
    s_ucWakeArmed = 0;
    SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_WAKEPOLL);
    return 1;
}

void AwtoPsPollSite(void)                           // AWTO_PS_POLL_SITE: armed (AwtoSyncPoll saw SAVING) and still SAVING
{
    if((g_ucAwtoSyncPwr == _POWER_STATUS_SAVING) && (GET_POWER_STATUS() == _POWER_STATUS_SAVING))
    {
        AwtoPsWakePoll();
    }
}

void AwtoPsWakePoll(void)                           // AWTO_SYNC_POLL + AWTO_PS_POLL_SITE (between handlers); works every AWTO_PS_POLL_MS
{
    BYTE ucI, ucNow, ucR, ucU;
    WORD usNow = (WORD)AwtoMs();
    WORD usGap = usNow - s_usWakeAt;

    if((g_ucAwtoPsWakeCon != 0) || (usGap < AWTO_PS_POLL_MS))
    {
        return;                                     // woken (the SDK powers up on its next pass), or not due
    }
    s_usWakeAt = usNow;
    g_ulAwtoPsMs += usGap;
    if((g_usAwtoPsPolls != 0) && (usGap > g_usAwtoPsGap))    // poll to poll: the arm -> first poll pass is PS entry work
    {
        g_usAwtoPsGap = usGap;
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
        if(((ucR & ((BYTE)1 << ucI)) != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_CABLE, ucI, 0) != 0))
        {
            return;
        }
        if(((ucU & ((BYTE)1 << ucI)) != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_UNPLUG, ucI, 0) != 0))
        {
            return;
        }
        ucNow = AWTO_XB(tAwtoWakeDdc[ucI]);
        if((ucNow & _BIT0) != 0)
        {
            AWTO_XB(tAwtoWakeDdc[ucI]) = (ucNow & ~(_BIT2 | _BIT0)) | _BIT0;
            if(AwtoPsWakeFire(AWTO_WAKE_T_EDID, ucI, 0) != 0)
            {
                return;
            }
        }
    }
    for(ucI = 1; ucI < 3; ucI++)                    // TMDS clock, HDMI D2 (P71) / D3 (P72): wakes only when held AWTO_PS_TMDS_HOLD_MS
    {
        if(AwtoPsTmdsHold(ucI, usNow) != 0)
        {
            return;
        }
    }
#if(_AWTO_PS_AUX_WAKE == _ON)
    if((AwtoPsWakeAux() != 0) && (AwtoPsWakeFire(AWTO_WAKE_T_AUX, 0, 0) != 0))          // index 0 = D1, the DP port
    {
        return;
    }
#else
    if((AwtoPsWakeAux() != 0) && ((s_ucPsSaid & _BIT0) == 0))    // logged once per sleep; DPCD 600h = D0 still wakes
    {
        s_ucPsSaid |= _BIT0;
        AwtoSyncPush(AWTO_SYNC_EV_PS_AUXCMD, _D1_INPUT_PORT, 0);
    }
#endif
    ucNow = ScalerDpRx1GetDpcdInfo(0x00, 0x06, 0x00);
    ucR = s_ucWakeDpcd;
    s_ucWakeDpcd = ucNow;
    if(((ucNow & 0x07) == 0x01) && ((ucR & 0x07) != 0x01))
    {
        AwtoPsWakeFire(AWTO_WAKE_T_DPCD, 0, 0);
    }
}
#endif

void AwtoSyncPoll(void)                             // power status changed (AWTO_SYNC_POLL in AwtoSwPoll)
{
    BYTE ucP = GET_POWER_STATUS();

#if(_AWTO_PS_WAKE == _ON)
    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_SAVING))
    {
        g_ucAwtoPsWakes++;
    }
    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoPsWakeCon != 0))
    {
        g_ucAwtoPsWakeCon = 0;                        // episode begun by AwtoPsWakeFire: console + backlight (as at power-on)
        AwtoBootConsole();
        UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_WAKE_POLL));     // the panel machine runs T1 .. T3 meanwhile
    }
    else
#endif
    if((ucP == _POWER_STATUS_NORMAL) && (g_ucAwtoSyncPwr == _POWER_STATUS_SAVING))
    {
        AwtoSyncBegin(AWTO_SYNC_K_WAKE, SysSourceGetInputPort());
#if(_AWTO_PS_WAKE == _ON)
        AwtoSyncPush(AWTO_SYNC_EV_SDKWAKE, SysSourceGetInputPort(), AwtoPsWakeState());   // not our poll: the SDK's detect
#endif
        if(g_stAwtoSync.ucOpenReq == AWTO_SYNC_OPEN_KEY)
        {
            AwtoBootConsole();                          // #132 UP+DOWN wake: the console at power NORMAL, as a source-event wake
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_KEY_CONSOLE));
        }
    }
    else if((ucP == _POWER_STATUS_OFF) || (ucP == _POWER_STATUS_SAVING))
    {
        g_stAwtoSync.ucOpenReq = 0;                 // #162 s3b: no 'power off / saving' line, the system transition states it
#if(_AWTO_PS_WAKE == _ON)
        if(ucP == _POWER_STATUS_SAVING)
        {
            AwtoPsWakeArm();
        }
#endif
    }
#if(_AWTO_PS_WAKE == _ON)
    if(ucP != _POWER_STATUS_SAVING)
    {
        s_ucWakeArmed = 0;                          // the SDK owns the freq detectors until power saving is armed again
    }
#endif
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
