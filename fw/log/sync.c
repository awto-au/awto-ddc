#include "SysInclude.h"

// #139 sync / power-on log: a small I2C-readable ring of stage events (RL6449_Project.h StAwtoSync), one episode per
// power-on / input switch / wake. Texts: fw/awto/sync.tsv (scripts/gen_awto_sync.py); host decoder: scripts/sync_log.py.
// Also the port getters the selector rows read (stage, DDC activity, idle TMDS clock).
extern WORD isr_g_usTmdsOffLineMeasureClk;              // ScalerCommonSync.c: SDK TMDS clock at freq-stable, 0.1 MHz
__xdata __at(AWTO_SYNC_ADDR) StAwtoSync g_stAwtoSync;
static __xdata BYTE s_pucAwtoSyncDet[3];          // D1..D3: last predetect (bit0) | source type << 1 seen by the port detect
__xdata BYTE g_ucAwtoScanStage;                     // input-sync timeline: step a scan stopped at (AWTO_SCAN_STAGE sites in the SDK)
__xdata WORD g_usAwtoScanT0;
__xdata BYTE g_ucAwtoFbRule;                        // ScalerScalingUpdateFIFOScalingSize: which frame buffer rule fired
__xdata WORD g_usAwtoHsdBw;                         // FRC width limits (pixels) from DDR bandwidth / space, 0xFFFF = not limited
__xdata WORD g_usAwtoHsdSp;
static __xdata WORD s_usAwtoDpLtT0;                 // DP: AwtoMs low word when the main loop first saw link training under way (0 = not)
static __xdata BYTE s_pucAwtoScanWhy[3];            // D1..D3: last scan line written (repeats are not logged)
static __xdata BYTE s_ucAwtoScanN;                  // scan / visit / slow-wait lines this episode (caps AWTO_SCAN_LOG_MAX / AWTO_WAIT_SYNC_MAX)
static __xdata BYTE s_ucAwtoVisitN;
static __xdata BYTE s_ucAwtoWaitN;
static __xdata WORD s_usAwtoVisitT0;
static __xdata WORD s_usAwtoStageT0;
static bit d_s_bAwtoStageOn;
static __xdata BYTE s_pucAwtoDdcAge[3];           // D1..D3: DDC polls left in which the port counts as live

// GENERATED-BEGIN awto_sync_rows
#define AWTO_SYNC_ROWS 365
#pragma place bank(11)
static const __code BYTE tAwtoSyncRowId[365] = {
    0xD0, 0xD0, 0xD0, 0xD0, 0xD0, 0xD1, 0xD1, 0xD1, 0xD1, 0xD1, 0xD2, 0xD2, 0xD2, 0xD4, 0xD4, 0xD4,
    0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
    0xD8, 0xD9, 0xC0, 0xC0, 0xC0, 0xC0, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10,
    0x10, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x12, 0x12, 0x12,
    0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x13, 0x14, 0x1C, 0x1C, 0x1C, 0x90, 0x90, 0x90,
    0x90, 0xA0, 0xA0, 0xA0, 0xA0, 0xA8, 0xB0, 0xB1, 0xC1, 0xC6, 0xC2, 0xC3, 0xC4, 0xC5, 0xC7, 0xC8,
    0xCA, 0xCB, 0xCC, 0xE7, 0xFA, 0xFA, 0xFA, 0xE8, 0xE8, 0xEA, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9,
    0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9,
    0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9, 0xE9,
    0xE9, 0xCD, 0xCE, 0xD3, 0xDC, 0xDD, 0xDA, 0xDB, 0xDE, 0xDF, 0xDF, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0,
    0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE0, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1, 0xE1,
    0xE1, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5,
    0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE5, 0xE2, 0xE2, 0xE2, 0xE2, 0xE2, 0xE2, 0xE2, 0xE3, 0xE3,
    0xE3, 0xE3, 0xE3, 0xE3, 0xE3, 0xE3, 0xE3, 0xE3, 0xE3, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4,
    0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xE4, 0xCF, 0xCF, 0xCF, 0xCF, 0xCF,
    0xCF, 0xF0, 0xF0, 0xF0, 0xF0, 0xF1, 0xF1, 0xF1, 0xF1, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2,
    0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2,
    0xF3, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF4, 0xF5,
    0xF5, 0xF5, 0xF5, 0xF5, 0xF5, 0xF5, 0xF5, 0xF5, 0xF5, 0xF6, 0xF6, 0xF6, 0xF6, 0xF6, 0xF6, 0xF7,
    0xF7, 0xF7, 0xF7, 0xF7, 0xF7, 0xF7, 0xF8, 0xF8, 0xF8, 0xF8, 0xF8, 0xF8, 0xF8, 0xF8, 0xF8, 0xF9,
    0xF9, 0xF9, 0xFB, 0xFB, 0xFB, 0xFB, 0xFB, 0xFB, 0xFC, 0xE6, 0xE6, 0xE6, 0xEB, 0xED, 0xED, 0xED,
    0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xED, 0xEE};
#pragma place bank(11)
static const __code BYTE tAwtoSyncRowArg[365] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x01, 0x02, 0x03, 0x04, 0x06, 0x01, 0x02, 0x03, 0x01, 0x02, 0x03,
    0x04, 0x05, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x21, 0x17, 0x20, 0x0C, 0xFF, 0xFF, 0xFF, 0x01,
    0x02, 0xFF, 0x01, 0x02, 0x03, 0x04, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0E,
    0x0F, 0x01, 0x12, 0x1B, 0x23, 0x2B, 0x34, 0x49, 0x94, 0x9A, 0xA4, 0xAB, 0xB0, 0x4A, 0xC1, 0xC2,
    0xCA, 0xD1, 0xE1, 0xE2, 0xE4, 0xE5, 0xE6, 0xE3, 0xC6, 0xC7, 0xCB, 0xCC, 0xFF, 0x00, 0x01, 0x02,
    0x12, 0x22, 0x32, 0x03, 0x13, 0x23, 0x33, 0x04, 0xFF, 0xFF, 0x00, 0x01, 0x02, 0x14, 0x15, 0x16,
    0x17, 0x01, 0x03, 0x04, 0xFF, 0x10, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x01, 0x02, 0x01, 0x03, 0xFF, 0x01, 0x11, 0x15, 0x16, 0x20, 0x21,
    0x22, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x41, 0x42, 0x43, 0x44, 0x50, 0x51, 0x60,
    0x61, 0x73, 0x74, 0x75, 0x79, 0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x87, 0x88, 0x89, 0x8A, 0x8B,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x01, 0x02, 0x01, 0x02, 0x03, 0x04, 0x05,
    0x06, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A,
    0x0B, 0x01, 0x02, 0x05, 0x06, 0x07, 0x04, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x30, 0x40, 0x41,
    0x42, 0x43, 0x44, 0x45, 0x46, 0x50, 0x51, 0x01, 0x09, 0x0B, 0x0D, 0x20, 0xFF, 0xFE, 0x01, 0x02,
    0x03, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12, 0x13, 0x14, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
    0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x21, 0x01, 0x02, 0x03, 0x04, 0x05,
    0x06, 0x00, 0x01, 0x02, 0x03, 0x01, 0x02, 0x03, 0x04, 0x01, 0x02, 0x10, 0x11, 0x12, 0x13, 0x14,
    0x15, 0x16, 0x17, 0x20, 0x21, 0x22, 0x24, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0xFF,
    0x00, 0x00, 0x08, 0x09, 0x0A, 0x0B, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1A, 0x1B, 0xFF, 0x00,
    0x01, 0x02, 0x03, 0x04, 0x10, 0x11, 0x12, 0x13, 0x14, 0x00, 0x11, 0x12, 0x13, 0x14, 0xFF, 0x00,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x00,
    0x01, 0x02, 0x00, 0x10, 0x01, 0x11, 0x02, 0x12, 0x01, 0x01, 0x02, 0x03, 0xFF, 0x00, 0x14, 0x3A,
    0x3C, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x39, 0x81, 0x82, 0xFF};
#pragma place bank(11)
static const __code WORD tAwtoSyncIdRow[256] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    39, 50, 78, 89, 90, 0, 0, 0, 0, 0, 0, 0, 91, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    94, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    98, 0, 0, 0, 0, 0, 0, 0, 102, 0, 0, 0, 0, 0, 0, 0,
    103, 104, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    35, 105, 107, 108, 109, 110, 106, 111, 112, 0, 113, 114, 115, 162, 163, 252,
    1, 6, 11, 164, 14, 29, 30, 31, 32, 34, 167, 168, 165, 166, 169, 170,
    172, 183, 216, 223, 234, 194, 346, 116, 120, 123, 122, 349, 0, 350, 365, 0,
    258, 262, 266, 289, 290, 304, 314, 320, 327, 336, 117, 339, 345, 0, 0, 0};
#pragma place bank(11)
WORD AwtoSyncRow(BYTE ucId, BYTE ucArg)           // row + 1 of the first match (arg 0xFF = any), 0 = not logged
{
    WORD usI = tAwtoSyncIdRow[ucId];

    if(usI == 0)
    {
        return 0;
    }
    for(usI--; (usI < AWTO_SYNC_ROWS) && (tAwtoSyncRowId[usI] == ucId); usI++)
    {
        if((tAwtoSyncRowArg[usI] == 0xFF) || (tAwtoSyncRowArg[usI] == ucArg))
        {
            return usI + 1;
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
    if(isr_g_stAwtoDiag.ucStage < 8)
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
    usBase = AwtoSyncWdtMs() - isr_g_stAwtoDiag.usT2Isr;  // ms since reset at usT2Isr = 0
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

static void AwtoSyncPutRaw(BYTE ucId, BYTE ucArg, DWORD ulVal)
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
}


static void AwtoSyncPut(BYTE ucId, BYTE ucArg, DWORD ulVal)
{
    AwtoSyncPutRaw(ucId, ucArg, ulVal);
    if(g_stAwtoGpio.ucOpen != 0)
    {
        AwtoConLogSync();                           // #144 live: the line shows now, also inside a blocking SDK step (panel on)
    }
}

// Ring line without the live console draw (AwtoWaitLog runs inside the deepest DATA path; the console catches up next pass) and without repeat collapse.
static void AwtoSyncPushQuiet(BYTE ucId, BYTE ucArg, DWORD ulVal)
{
    AwtoSyncPutRaw(ucId, ucArg, ulVal);
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
        AwtoSyncPush(AWTO_SYNC_EV_MSTEP, 0xFE, 0);              // its second line (Dan: two lines, not one wrapped)
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
        BYTE ucP;

        for(ucP = 0; ucP < sizeof(StAwtoSyncEv); ucP++)
        {
            ((BYTE __xdata *)&g_stAwtoSyncPin)[ucP] = ((BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, 1))])[ucP];
        }
    }
}

// One time base for all our code: Timer2 ISR count (usT2Isr = low word, isr_g_stAwtoHt.usUpHi = high word, both bumped in the ISR).
// Before Timer2 runs it is the WDT-counter time (ring lines are re-based at the Timer2 start). SDK event table (d_isr_g_usTimerCounter) is separate.
__xdata StAwtoHt isr_g_stAwtoHt;

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
    usLo = isr_g_stAwtoDiag.usT2Isr;
    usHi = isr_g_stAwtoHt.usUpHi;
    EA = bEa;
    return ((DWORD)usHi << 16) | usLo;
}

__xdata StAwtoWait g_stAwtoWait;

void AwtoWaitLog(unsigned char ucKind, unsigned int usArg, unsigned int usT0, unsigned int usPc)      // #216: one entry per blocking wait, written when it ends
{
    unsigned int usNow = (WORD)AwtoMs();
    unsigned int usDur = usNow - usT0;
    unsigned char ucI = g_stAwtoWait.ucTotal % AWTO_WAIT_N;

    if(SP > g_stAwtoWait.ucSpMax)
    {
        g_stAwtoWait.ucSpMax = SP;
    }

    if((usDur < 2) && ((ucKind & AWTO_WAIT_TIMEOUT) == 0))
    {
        g_stAwtoWait.ucQuick++;                 // under 2 ms (a 1 ms measure poll every ~100 ms floods the ring): counted, not logged
        return;
    }
    if(((usDur >= AWTO_WAIT_SYNC_MS) || ((ucKind & AWTO_WAIT_TIMEOUT) != 0)) && (s_ucAwtoWaitN < AWTO_WAIT_SYNC_MAX))
    {
        s_ucAwtoWaitN++;
        AwtoSyncPushQuiet(AWTO_SYNC_EV_WAITSLOW, (ucKind & 3) | (((ucKind & AWTO_WAIT_TIMEOUT) != 0) ? 0x10 : 0), ((DWORD)usArg << 16) | usDur);
    }
    g_stAwtoWait.stEv[ucI].usMs = usNow;
    g_stAwtoWait.stEv[ucI].ucKind = ucKind;
    g_stAwtoWait.stEv[ucI].usArg = usArg;
    g_stAwtoWait.stEv[ucI].usPc = usPc;
    g_stAwtoWait.stEv[ucI].ucDur = (usDur > 255) ? 255 : (unsigned char)usDur;
    g_stAwtoWait.ucTotal = (g_stAwtoWait.ucTotal + 1 == 2 * AWTO_WAIT_N) ? AWTO_WAIT_N : g_stAwtoWait.ucTotal + 1;   // >= N = ring full, index stays total % N
}

// #157 DDC/CI host time (fw/ddcci/ddcci.c): RAM only. Ring lines at the first sync of this boot and on a drift over AWTO_HT_DRIFT_MS.
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
    if(isr_g_stAwtoHt.ucSyncs != 0)
    {
        lS = (long)(ulE - isr_g_stAwtoHt.ulEpoch);
        lD = ((lS > AWTO_HT_GAP_S) || (lS < -AWTO_HT_GAP_S)) ? 0x7FFFFFFFL :
             (lS * 1000 + (long)usF - (long)isr_g_stAwtoHt.usFrac - (long)(ulNow - isr_g_stAwtoHt.ulFwMs));
        ucWhy = ((lD > AWTO_HT_DRIFT_MS) || (lD < -AWTO_HT_DRIFT_MS)) ? 2 : 0;
        if(isr_g_stAwtoHt.ucSyncs != 0xFF)
        {
            isr_g_stAwtoHt.ucSyncs++;
        }
    }
    else
    {
        isr_g_stAwtoHt.ucSyncs = 1;
    }
    isr_g_stAwtoHt.ulEpoch = ulE;
    isr_g_stAwtoHt.usFrac = usF;
    isr_g_stAwtoHt.cOfs = (signed char)puc[6];
    isr_g_stAwtoHt.ulFwMs = ulNow;
    isr_g_stAwtoHt.iDrift = (lD > 32767) ? 32767 : ((lD < -32767) ? -32767 : (int)lD);
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
        s_pucAwtoScanWhy[ucI] = 0;
    }
    s_ucAwtoScanN = 0;
    s_ucAwtoVisitN = 0;
    s_ucAwtoWaitN = 0;
    s_usAwtoVisitT0 = usNow;
    if(ucKind == AWTO_SYNC_K_POWER_ON)
    {
        AwtoSyncPush(AWTO_SYNC_EV_BOOT, AwtoBootReason(), AwtoBootValue());     // first line: why it is running (#29)
        AwtoSyncPush(AWTO_SYNC_EV_STAGE, 1, 0);
    }
    AwtoSyncPush(AWTO_SYNC_EV_BEGIN, ucKind, ((AwtoMs() >> 16) << 8) | ucPort);   // #157 anchor: fw ms bits 31..16 above the port
}

static __xdata BYTE s_ucAwtoSyncRan;                // 0 until this boot's first AwtoSyncInit (the main loop may re-enter it)

void AwtoSyncInit(void)                             // boot (before SysMainSystemInitial): the power-on episode
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync;
    WORD usI;

    if(((s_ucAwtoSyncRan == 0) && (AwtoBootReason() == AWTO_BOOT_COLD)) || (g_stAwtoSync.ucMagic0 != 'S') || (g_stAwtoSync.ucMagic1 != 'Y') || (g_stAwtoSync.ucVersion != 3) ||
       (g_stAwtoSync.ucN != AWTO_SYNC_N) || (g_stAwtoSync.ucWrap != AWTO_SYNC_WRAP) || (g_stAwtoSync.ucSeq >= AWTO_SYNC_WRAP) || (g_stAwtoSync.ucEpSeq >= AWTO_SYNC_WRAP))
    {
        for(usI = 0; usI < sizeof(StAwtoSync); usI++)
        {
            puc[usI] = 0;                           // cold power-up (RAM not ours) or a ring that fails its header: an empty ring
        }
    }
    g_stAwtoSync.ucMagic0 = 'S';
    g_stAwtoSync.ucMagic1 = 'Y';
    g_stAwtoSync.ucVersion = 3;
    g_stAwtoSync.ucN = AWTO_SYNC_N;
    g_stAwtoSync.ucWrap = AWTO_SYNC_WRAP;
    g_stAwtoSync.ucKind = 0;
    g_stAwtoSync.ucSpare = 0;
    g_stAwtoSync.ucOpenReq = 0;
    s_ucAwtoSyncRan = 1;
    for(usI = 1; usI <= AWTO_SYNC_N; usI++)         // a kept ring: the note numbers go on (the DDR lines are keyed by them)
    {
        puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, usI))];
        if(puc[0] == AWTO_SYNC_EV_NOTE)
        {
            g_usAwtoNoteN = ((WORD)puc[6] << 8) | puc[7];
            break;
        }
    }
    g_ucAwtoSyncPwr = _POWER_STATUS_AC_ON;
    s_usAwtoT2Base = 0xFFFF;
    AwtoSyncBegin(AWTO_SYNC_K_POWER_ON, 0xFF);
    g_stAwtoSync.ucT0Hi = 0;                        // power-on lines print ms since reset
    g_stAwtoSync.ucT0Lo = 0;
}

// Switch-log events (fw/log/swlog.c AwtoSwEvent) that have a sync.tsv row go into the ring too.
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
#if(_DP_SUPPORT == _ON)
    if((ucKind == _PORT_DP) && (s_usAwtoDpLtT0 == 0) && ((ucPre & 1) == 0) && (AwtoDpRx1LtBusy() != 0))
    {
        s_usAwtoDpLtT0 = (WORD)AwtoMs() | 1;
    }
#endif
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
            AwtoSyncPush(AWTO_SYNC_EV_DPLT, 1, ((DWORD)ucPort << 16) | ((s_usAwtoDpLtT0 == 0) ? 0 : (WORD)((WORD)AwtoMs() - s_usAwtoDpLtT0)));   // 0: training finished before the loop saw it
            s_usAwtoDpLtT0 = 0;
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
        s_pucAwtoScanWhy[ucI] = 0;
        s_ucTmdsPend &= ~((BYTE)1 << ucI);
    }
    if(((ucNew >> 1) != _SOURCE_NONE) && ((ucNew >> 1) != (ucOld >> 1)))
    {
        AwtoSyncPush(AWTO_SYNC_EV_SCAN, ucPort, ucNew >> 1);
    }
}

void AwtoSyncScan(BYTE ucPort, BYTE ucType)         // SysSourceDetectPort: a predetected port was scanned; one line per change of the outcome
{
    BYTE ucI = ucPort - _D1_INPUT_PORT;
    BYTE ucWhy = (ucType != _SOURCE_NONE) ? AWTO_SCAN_OK : g_ucAwtoScanStage;

#if(_AWTO_TMDS_MODE_MEM == _ON)
    BYTE ucMem = (ucPort == _D2_INPUT_PORT) ? AWTO_TMDS_MEM_D2 : ((ucPort == _D3_INPUT_PORT) ? AWTO_TMDS_MEM_D3 : 0);

    if(((isr_g_ucAwtoTmdsMem & (ucMem << 4)) != 0) && (s_ucAwtoScanN < AWTO_SCAN_LOG_MAX))     // the PHY set-up took 1:40 from the memory
    {
        isr_g_ucAwtoTmdsMem &= ~(ucMem << 4);
        s_ucAwtoScanN++;
        AwtoSyncPush(AWTO_SYNC_EV_SCANW, AWTO_SCAN_MEM, ((DWORD)ucPort << 16) | (WORD)((WORD)AwtoMs() - g_usAwtoScanT0));
    }
#endif
    if((ucI > 2) || (s_pucAwtoScanWhy[ucI] == ucWhy))
    {
        return;
    }
    s_pucAwtoScanWhy[ucI] = ucWhy;
    if(s_ucAwtoScanN >= AWTO_SCAN_LOG_MAX)
    {
        if(s_ucAwtoScanN == AWTO_SCAN_LOG_MAX)
        {
            s_ucAwtoScanN++;
            AwtoSyncPush(AWTO_SYNC_EV_SCANW, 0xFF, 0);
        }
        return;
    }
    s_ucAwtoScanN++;
    AwtoSyncPush(AWTO_SYNC_EV_SCANW, ucWhy, ((DWORD)ucPort << 16) | (WORD)((WORD)AwtoMs() - g_usAwtoScanT0));
}

void AwtoSyncVisit(BYTE ucOldPort)                  // SysSourceHandler: the search moved on from ucOldPort
{
    WORD usNow = (WORD)AwtoMs();

    if(s_ucAwtoVisitN < AWTO_SCAN_LOG_MAX)
    {
        s_ucAwtoVisitN++;
        AwtoSyncPush(AWTO_SYNC_EV_VISIT, 0, ((DWORD)ucOldPort << 16) | (WORD)(usNow - s_usAwtoVisitT0));
    }
    s_usAwtoVisitT0 = usNow;
}

void AwtoStageMs(BYTE ucStg)                        // SysMachineWork probes: 0 = a stage starts (once, the SDK retries the call); else it took ms
{
    WORD usNow = (WORD)AwtoMs();

    if(ucStg == 0)
    {
        if(d_s_bAwtoStageOn == 0)
        {
            d_s_bAwtoStageOn = 1;
            s_usAwtoStageT0 = usNow;
        }
        return;
    }
    AwtoSyncPush(AWTO_SYNC_EV_STAGE_MS, ucStg, (WORD)(usNow - s_usAwtoStageT0));
    s_usAwtoStageT0 = usNow;                        // display setting ends where the colour proc starts
    d_s_bAwtoStageOn = (ucStg == AWTO_STG_DISPLAY);
}

void AwtoSyncTiming(void)                           // SysModeHandler: timing confirmed (measure done)
{
    BYTE ucPort = SysSourceGetInputPort();

    BYTE ucKind = 0;                                  // 0 DVI, 1 HDMI 1.4 (TMDS 1:10), 2 HDMI 2.0 (1:40), 3 DP

    AwtoSyncPush(AWTO_SYNC_EV_TIMING, ucPort, ((DWORD)GET_INPUT_TIMING_HWIDTH() << 16) | GET_INPUT_TIMING_VHEIGHT());
    if(SysSourceGetSourceType() == _SOURCE_DP)
    {
        ucKind = 3;
    }
    else if(SysSourceGetSourceType() == _SOURCE_HDMI)
    {
        ucKind = 1;
#if(_D2_HDMI_2_0_SUPPORT == _ON)
        if((ucPort == _D2_INPUT_PORT) && (AwtoTmdsRx2Hs() != 0))
        {
            ucKind = 2;
        }
#endif
#if(_D3_HDMI_2_0_SUPPORT == _ON)
        if((ucPort == _D3_INPUT_PORT) && (AwtoTmdsRx3Hs() != 0))
        {
            ucKind = 2;
        }
#endif
    }
    AwtoSyncFormat(ucKind);
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

#if(_AWTO_PS_WAKE == _ON)
static BYTE AwtoHpdPins(void)                       // bit n = HPD pin of D(n+1) high
{
    return (PCB_D1_HOTPLUG_DETECT() ? 1 : 0) | (PCB_D2_HOTPLUG_DETECT() ? 2 : 0) | (PCB_D3_HOTPLUG_DETECT() ? 4 : 0);
}

void AwtoSyncEdidOn(void)                           // ScalerMcuDdcRamEnable: the EDID channels answer from here (HPD level at that moment)
{
    AwtoSyncPushQuiet(AWTO_SYNC_EV_HPD, 2, AwtoHpdPins());
}

void AwtoEdidPoll(void)                             // awake: every EDID read by a source is a log line (power saving: the wake lines)
{
    static __xdata BYTE s_ucSeen;                   // bit n = port n's read flag was already logged and has not read 0 since
    static __xdata BYTE s_ucHpd;                    // HPD pins as last logged; bit 3 = first poll done (it logs all three levels)
    BYTE ucI, ucV, ucH;

    if(g_ucAwtoSyncPwr == _POWER_STATUS_SAVING)
    {
        return;
    }
    ucH = AwtoHpdPins();
    ucV = ((s_ucHpd & 8) == 0) ? 7 : ((ucH ^ s_ucHpd) & 7);
    s_ucHpd = ucH | 8;
    for(ucI = 0; ucI < 3; ucI++)
    {
        if((ucV & ((BYTE)1 << ucI)) != 0)
        {
            AwtoSyncPushQuiet(AWTO_SYNC_EV_HPD, (ucH >> ucI) & 1, _D1_INPUT_PORT + ucI);      // no live console draw: its ms would delay the boot it measures
        }
    }
    for(ucI = 0; ucI < 3; ucI++)
    {
        ucV = AWTO_XB(tAwtoWakeDdc[ucI]);
        if((ucV & _BIT0) == 0)
        {
            s_ucSeen &= ~((BYTE)1 << ucI);
        }
        else if((s_ucSeen & ((BYTE)1 << ucI)) == 0)
        {
            s_ucSeen |= (BYTE)1 << ucI;
            AWTO_XB(tAwtoWakeDdc[ucI]) = (ucV & ~(_BIT2 | _BIT0)) | _BIT0;      // W1C the read flag only
            AwtoSyncPush(AWTO_SYNC_EV_EDID, _D1_INPUT_PORT + ucI, 0);
        }
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
