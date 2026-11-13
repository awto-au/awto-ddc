/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2012>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : RL6449_Project.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#if(_PROJECT == _RL6449_PROJECT)

#include "AwtoRegs.h"                                         // generated register / field names (scripts/gen_regnames.py)

// IIC engine status: sub-address or data-in event pending = DDC/CI traffic to service (same layout for IIC_1..3)
#define AWTO_IIC_ATTN                                           (AWTO_F_IIC_1_STATUS_IIC_1_SUB_I | AWTO_F_IIC_1_STATUS_IIC_1_D_IN_I)
#define AWTO_DDCCI_WR_ADDR                                      0x6E    // DDC/CI slave 0x37 as the 8-bit write address
//--------------------------------------------------
// OSD palette: indices (1-based, ScalerOsdSetColorPalette) and RGB triples (R, G, B)
//--------------------------------------------------
#define AWTO_PAL_N                                              12
#define AWTO_PAL_FIRST                                          1
#define AWTO_PAL_ACCENT                                         1       // Realtek 2014 blue
#define AWTO_PAL_GREY                                           2
#define AWTO_PAL_SURFACE                                        3       // white
#define AWTO_PAL_ALERT                                          4       // diagnostic console only
#define AWTO_PAL_DIAG_TEXT                                      1       // diagnostic look re-uses indices 1..4
#define AWTO_PAL_DIAG_DIM                                       2
#define AWTO_PAL_DIAG_BG                                        3
#define AWTO_PAL_DIAG_ALERT                                     4
#define AWTO_RGB_REALTEK_BLUE                                   0, 68, 166
#define AWTO_RGB_GREY_AA                                        170, 170, 170
#define AWTO_RGB_WHITE                                          255, 255, 255
#define AWTO_RGB_GREY_49                                        73, 73, 73
#define AWTO_RGB_GREY_6E                                        110, 110, 110
#define AWTO_RGB_BLUE_PALE                                      170, 193, 225
#define AWTO_RGB_BLUE_DEEP                                      0, 45, 111
#define AWTO_RGB_GREY_55                                        85, 85, 85
#define AWTO_RGB_GREY_25                                        37, 37, 37
#define AWTO_RGB_BLUE_STEEL                                     85, 130, 196
#define AWTO_RGB_BLUE_NAVY                                      0, 23, 55
#define AWTO_RGB_BLACK                                          0, 0, 0
#define AWTO_RGB_PHOSPHOR_GREEN                                 0, 255, 65
#define AWTO_RGB_PHOSPHOR_DIM                                   0, 140, 40
#define AWTO_RGB_ALERT_RED                                      255, 50, 50

//--------------------------------------------------
// awto two-colour power LED (bLED_ON = P3.5 on colour, bLED_STANDBY = P3.6 standby colour; awto-ddc#95)
// One owner: the system machine (SysJudge.c SysMachineLed) per state; line "LED: <colour> (<state>)" per change (sync.tsv 1C).
//--------------------------------------------------
#define AWTO_LED_OFF                                            0       // also the sync.tsv 1C arg
#define AWTO_LED_ON                                             1
#define AWTO_LED_BREATHE                                        2
#define AWTO_SW_EV_LED                                          0x1C    // LED change: arg AWTO_LED_*, ring value = system state (AWTO_SYS_*)
extern volatile __xdata unsigned char g_ucAwtoLedMode;
extern volatile __xdata unsigned char g_ucAwtoLedPhase;
extern volatile __xdata unsigned char g_ucAwtoLedLevel;
extern volatile __xdata unsigned char g_ucAwtoLedTick;
extern volatile __xdata unsigned char g_ucAwtoLedUp;
extern volatile __xdata unsigned char g_ucAwtoLedPins;  // P3 pin levels (MCU_FFE3, bus value) once per main-loop pass: debug-readable
extern void AwtoLedSet(unsigned char ucMode, unsigned char ucState);    // SysMachineLed only
extern void SysMachineLedBoot(void);
// Timer2 ticks each millisecond.  The accumulator produces 1 kHz pulse-density PWM;
// brightness moves one step every 16 ms for an approximately 8.2 s breathe cycle.
#define AWTO_LED_T2ISR()                                        do { \
                                                                    if(g_ucAwtoLedMode == AWTO_LED_BREATHE) { \
                                                                        g_ucAwtoLedPhase += g_ucAwtoLedLevel; \
                                                                        bLED_ON = 0; \
                                                                        bLED_STANDBY = (g_ucAwtoLedPhase < g_ucAwtoLedLevel); \
                                                                        if(++g_ucAwtoLedTick >= 16) { \
                                                                            g_ucAwtoLedTick = 0; \
                                                                            if(g_ucAwtoLedUp != 0) { \
                                                                                if(g_ucAwtoLedLevel >= 254) { g_ucAwtoLedLevel = 255; g_ucAwtoLedUp = 0; } \
                                                                                else { ++g_ucAwtoLedLevel; } \
                                                                            } else { \
                                                                                if(g_ucAwtoLedLevel <= 1) { g_ucAwtoLedLevel = 0; g_ucAwtoLedUp = 1; } \
                                                                                else { --g_ucAwtoLedLevel; } \
                                                                            } \
                                                                        } \
                                                                    } \
                                                                } while(0)

//--------------------------------------------------
// awto switches for SDK __code compiled out by scripts/keil2sdcc.py WRAPS (#8)
//--------------------------------------------------
#ifdef _AWTO_NEW_SETTINGS                                       // #67 settings registry (awto-rtdfw): ids + reader
#include "AwtoSetIds.h"
extern int set_get(unsigned char ucId);
#define AWTO_SET(n)                                             set_get(AWTO_SET_##n)
extern void AwtoSetInit(void);                                  // hooks: fw/awto/settings/glue*.inc
extern void AwtoSetLoop(void);
extern __xdata unsigned char g_ucAwtoMenuOn;                    // our menu on screen: service every pass
extern void menu_close(void);                                   // awto-rtdfw menu.c: closes it (saves an edit in progress)
extern __xdata unsigned int g_usAwtoSetLast;
#define AWTO_SET_LOOP_MS                                        20      // settings / mailbox service period (derived: below key-repeat 0.5 s and host polling)
#define AWTO_SET_LOOP()                                         { if((g_ucAwtoMenuOn != 0) || ((unsigned int)(g_stAwtoDiag.usT2Isr - g_usAwtoSetLast) >= AWTO_SET_LOOP_MS)) { AwtoSetLoop(); } }
extern unsigned int AwtoAudioGain(unsigned char ucV);          // volume % -> DVC gain (glue.inc)
#define AWTO_AUDIO_HOLD()                                       ((SysModeGetModeState() != _MODE_STATUS_ACTIVE) && (SysModeGetModeState() != _MODE_STATUS_DISPLAY_SETTING))
extern void AwtoMenuForget(void);
// #151 one store: the SDK EEPROM emulation. SDK saves are deferred (item dirty) and written by the flush gate (glue.inc)
typedef struct
{
    unsigned char ucMagic;                                      // 'N' once AwtoSetInit ran
    unsigned char ucMask;                                       // dirty items (AWTO_NV_*)
    unsigned char ucWhy;                                        // last flush: AWTO_NV_WHY_*
    unsigned char ucInDdc;                                      // flash ops seen inside a DDC/CI handler (must stay 0)
    unsigned int usDefer;                                       // SDK item saves deferred
    unsigned int usFlush;                                       // flushes
    unsigned int usItemWr;                                      // items programmed (after the SDK's unchanged check)
    unsigned int usOps;                                         // flash halt ops: page programs + sector erases
    unsigned int usStable;                                      // gate inputs at the last service: stable ms, DDC/CI idle ms
    unsigned int usDdcIdle;
    unsigned int usErase;                                       // sector erases (of usOps)
    unsigned int usBytes;                                       // bytes programmed (UserCommonFlashWrite lengths)
} StAwtoNv;
extern __xdata StAwtoNv g_stAwtoNv;
extern __xdata unsigned char g_ucAwtoNvDdc;                     // a DDC/CI request since the last service
extern __xdata unsigned char g_ucAwtoNvInDdc;                   // inside the DDC/CI handler now
extern __xdata unsigned char g_ucAwtoNvSwitch;                  // an input switch since the last service
extern void AwtoNvFlush(void);                                  // power-off / saving entry: write all dirty items now
extern void AwtoNvCommitSel(void);                              // source selector choice: input saved at the gate, card
#define AWTO_NV_SYS                                             0x01
#define AWTO_NV_OSD                                             0x02
#define AWTO_NV_BRI                                             0x04
#define AWTO_NV_CT                                              0x08
#define AWTO_NV_SIX                                             0x10
#define AWTO_NV_PANEL                                           0x20    // never opens the gate: rides along, power-down
#define AWTO_NV_AUX                                             0x40
#define AWTO_SAVE_CARD_MS                                       1000    // "Saving to memory" readable once (derived: one glance)
#define AWTO_NV_ITEM_WR()                                       { g_stAwtoNv.usItemWr++; AWTO_NV_IN_DDC(); }
#define AWTO_NV_OP()                                            { g_stAwtoNv.usOps++; AWTO_NV_IN_DDC(); }
#define AWTO_NV_BYTES(n)                                        { g_stAwtoNv.usBytes += (n); }
#define AWTO_NV_IN_DDC()                                        { if(g_ucAwtoNvInDdc != 0) { g_stAwtoNv.ucInDdc++; } }   // must stay 0
#define AWTO_NV_AUX_ID                                          0x40    // SDK item ids of the aux block (registry rows without an SDK field)
#define AWTO_NV_AUX_ITEMS                                       ((AWTO_SET_AUX_MAX + 13) / 14)
// Gate (Dan, #151): a flash op halts the CPU (no DDC/CI, AUX, tick), so writes wait for a settled picture
#define AWTO_NV_STABLE_MS                                       3000    // ACTIVE, no switch / sync / link training (Dan)
#define AWTO_NV_DDC_IDLE_MS                                     500     // since the last DDC/CI request (Dan)
#define AWTO_NV_FORCE_MS                                        30000   // dirty -> written at the latest (Dan)
#define AWTO_NV_SAVE_MS                                         2000    // after the last change: one write per slider drag (derived)
#define AWTO_NV_EL_MAX_MS                                       100     // gate ages per service call at most this (5 x AWTO_SET_LOOP_MS)
#define AWTO_NV_WHY_GATE                                        1
#define AWTO_NV_WHY_FORCED                                      2
#define AWTO_NV_WHY_POWER                                       3
#define AWTO_NV_WHY_CLOSE                                       4
#define AWTO_NV_WHY_TEST                                        5
#define AWTO_NV_WHY_SNAP                                        6       // a second BriCon / ColorProc item while one waited
#define AWTO_NV_WHY_DDC                                         7       // DDC/CI save current settings (MCCS 0x0C, VCP 0xE3 = 2)
// Flush result line (AWTO_SYNC_EV_NV, arg AWTO_NV_LOG_ARG(why), fmt nvw): value = deltas across the flush, saturating
// [31:27] items written by group (AWTO_NV_LOG_G_*) | [26:25] erases | [24:19] programs | [18:9] bytes | [8:0] ms (AwtoMs tick)
#define AWTO_NV_LOG_ARG(why)                                    (0x10 + (why))
#define AWTO_NV_LOG_G_SYS                                       0x01    // SDK system data
#define AWTO_NV_LOG_G_OSD                                       0x02    // SDK OSD user data (2 items)
#define AWTO_NV_LOG_G_COLOUR                                    0x04    // SDK BriCon / ColorProc / SixColor items
#define AWTO_NV_LOG_G_PANEL                                     0x08    // SDK panel used time
#define AWTO_NV_LOG_G_AUX                                       0x10    // awto aux block (items AWTO_NV_AUX_ID..)
#define AWTO_NV_LOG_ER_MAX                                      3
#define AWTO_NV_LOG_PR_MAX                                      63
#define AWTO_NV_LOG_B_MAX                                       1023
#define AWTO_NV_LOG_MS_MAX                                      511
extern void menu_key(unsigned char ucKey);                      // awto-rtdfw menu.h: key numbers = SDK key messages 0..3
extern void menu_open(void);
extern unsigned char menu_active(void);
extern __xdata unsigned char g_ucAwtoKeyHold;
extern unsigned char AwtoKeyHold(void);
#define AWTO_KEY_HOLD()                                         ((g_ucAwtoKeyHold != 0) ? AwtoKeyHold() : 0)
#endif
// #65 step 1 drops: _OFF = SDK __code compiled out (scripts/keil2sdcc_drops.py)
#define _AWTO_FACTORY                                           _ON     // RTD factory menu (RTDFactoryMode/Function); Dan: kept (needed), port to open __code later
#define _AWTO_GAMMA_ALL                                         _ON     // _OFF = 1.8/2.0/2.4 OSD gamma options alias the 2.2 LUT; Dan: all kept
#ifndef _AWTO_TMDS_MEASURE_ACCEPT                                // build -D overrides (A/B)
#define _AWTO_TMDS_MEASURE_ACCEPT                               _OFF    // _ON = HDMI search accepts a port only once its timing measures (A/B for the predetect flaps, #162)
#endif
#define _AWTO_DP_PHYCTS                                         _ON     // DP PHY compliance (CTS) process; Dan: kept
// _AWTO_FLASH_ALL: RL6449_Gen_Option.h (the Lib flash code sees it there too)
// Boot-stage + timing diag block (#23): 48 B at 0xF6D0, outside the linker's XDATA range (fw_build.py XRAM end).
// Layout (SDCC little-endian: low byte first): docs/diag-block.md, scripts/rtd_diag.py. Read over debug slave 0x35.
// #54: busy-loop counts from the T3 measurement (the SDK constants are 112..127 % depending on __code placement)
#define AWTO_DELAY_TARGET_PCT                                   105     // shorter copy of each pair; health limit 90..125 %
#define AWTO_DELAY_CAL_RCAP2H                                   0xE3    // M2PLL Timer2 reload (rtd_diag PERIOD); others keep the SDK counts
extern unsigned char g_ucAwtoCal5;
extern unsigned char g_ucAwtoCalX;
typedef struct
{
    unsigned char ucMagic0;                     // 'A'
    unsigned char ucMagic1;                     // 'D'
    unsigned char ucVersion;                    // 1; 2 = debug slave block read 0x3C (#38)
    unsigned char ucStage;                      // last stage reached (1..8, monotonic)
    unsigned int usStageMs[8];                  // g_usTimerCounter (1 ms) at first entry of stage n
    unsigned int usHeartbeat;                   // main-loop passes
    unsigned int usT2Isr;                       // Timer2 ISR entries
    unsigned int usEx1Isr;                      // EXINT1 (DDC-CI/debug) ISR entries
    unsigned char ucDelay5usN;                  // g_ucDelay5usN_Base seen by the self-test
    unsigned int usDelayXms10;                  // 10 ticks of ScalerTimerDelayXms, Timer2 counts / 4
    unsigned int usDelay5us10;                  // 10 x ScalerDelay5us(), raw Timer2 counts, EA off
    unsigned char ucRcap2h;                     // RCAP2H at the test: tells XTAL from M2PLL reload
    unsigned int usDelayXus100;                 // DELAY_XUS(100), raw Timer2 counts, EA off
    unsigned int usDelayXusIsr100;              // DELAY_XUS_EXINT(100), raw counts
    unsigned int usDelay5usIsr10;               // 10 x DELAY_5US_EXINT(), raw counts
    unsigned int usT3Wait64;                    // whole panel T3 wait (test included), Timer2 counts / 64
    unsigned char ucTestCmd;                    // OSD test command, written over I2C, applied + cleared in main loop (#33)
    unsigned char ucDbgPopup;                   // unused since #124 (the menu opens the console directly); kept: diag block layout
    unsigned int usLoopRate;                    // main-loop passes in the last ~1 s (#34)
    unsigned char ucOsdOfsState;                // offsetof(StructOsdInfo, usOsdState): g_stOsdInfo layout moves with _DP_DEBUG_MSG (#37)
    unsigned char ucOsdOfsEvent;                // offsetof(StructOsdInfo, ucOsdEventMsg)
    unsigned char ucOsdOfsKey;                  // offsetof(StructOsdInfo, ucOsdKeyMessage)
    unsigned char ucHold;                       // #28 held test visuals: bit1 debug pop-up / console (0x26); 0x27 clears; bit0 free (was the logo)
} StAwtoDiag;
typedef char AwtoDiagSizeCheck[(sizeof(StAwtoDiag) == 48) ? 1 : -1];
#ifdef _AWTO_DIAG_DEFINER
volatile __xdata __at(0xF6D0) StAwtoDiag g_stAwtoDiag;
#else
extern volatile __xdata __at(0xF6D0) StAwtoDiag g_stAwtoDiag;
#endif
// Watchdog + crash canary (#131, #138, docs/watchdog.md): 32 B at 0xF6B0, outside the linker XDATA range (fw_build.py XRAM end),
// so neither the crt nor AwtoDiagInit clears it. Bytes only: same layout in LE and BE images (host: scripts/rtd_crash.py).
#define _AWTO_WDT                                               _ON
typedef struct
{
    unsigned char ucMagic0;                     // 'W'; host clear = write 0 here
    unsigned char ucMagic1;                     // 'D'
    unsigned char ucVersion;                    // 2 (#138: hardware watchdog only)
    unsigned char ucCause;                      // AWTO_WDT_C_* of the last bite
    unsigned char ucBites;                      // watchdog warnings captured since the record was cleared (stops at 255)
    unsigned char ucWarm;                       // other warm resets (no capture: hardware reset, ISP 0xEE), stops at 255
    unsigned char ucPcHi;                       // interrupted PC = return address stacked by the WDT warning interrupt
    unsigned char ucPcLo;
    unsigned char ucBank;                       // __bs_cur at the interrupt: __code bank of a PC >= 0x5000
    unsigned char ucSp;                         // SP before the interrupt
    unsigned char ucPsw;
    unsigned char ucAcc;
    unsigned char ucB;
    unsigned char ucDph;
    unsigned char ucDpl;
    unsigned char ucRetHi;                      // top word of the interrupted stack (a caller's return address, if any)
    unsigned char ucRetLo;
    unsigned char ucStage;                      // g_stAwtoDiag.ucStage
    unsigned char ucMode;                       // mode state (_MODE_STATUS_*)
    unsigned char ucHbHi;                       // g_stAwtoDiag.usHeartbeat
    unsigned char ucHbLo;
    unsigned char ucUpHi;                       // g_usTimerCounter, ms (wraps at 65.5 s)
    unsigned char ucUpLo;
    unsigned char ucPassAgeHi;                  // ms since the last main-loop pass, at the warning (wraps at 65.5 s)
    unsigned char ucPassAgeLo;
    unsigned char ucCheck;                      // AWTO_WDT_SEED ^ bytes 0..24: record valid
    unsigned char ucBoot;                       // live from here (not in ucCheck): AWTO_WDT_B_*
    unsigned char ucPassHi;                     // g_usTimerCounter at the last main-loop pass
    unsigned char ucPassLo;
    unsigned char ucMaxPass;                    // longest main-loop pass this boot, x32 ms (255 = 8.1 s or more)
    unsigned char ucMaxPoke;                    // longest gap between watchdog pokes this boot, x32 CNT3 = 4.58 ms (255: >= 586 ms)
    unsigned char ucProbe;                      // AWTO_WDT_P_*: test cmd 0x49 / 0x4F result (kept over resets)
} StAwtoWdt;
typedef char AwtoWdtSizeCheck[(sizeof(StAwtoWdt) == 32) ? 1 : -1];
#ifdef _AWTO_DIAG_DEFINER
volatile __xdata __at(0xF6B0) StAwtoWdt g_stAwtoWdt;
#else
extern volatile __xdata __at(0xF6B0) StAwtoWdt g_stAwtoWdt;
#endif
// Reset-vector snapshot (#29 / #138): crt_rtd_startup copies these before any init, 20 B no-init at 0xF69C (rtd_crash.py --snap).
// 'R' 'S', SFRs EICON PCON EXIF CKCON IE EIE IP EIP, XFRs FFEA FFEB FFAA FFAB FFAC FFAD FFE0 FFED FFEE, P0_01. Reset-cause search.
#ifdef _AWTO_DIAG_DEFINER
volatile __xdata __at(0xF69C) unsigned char g_stAwtoSnap[20];
#else
extern volatile __xdata __at(0xF69C) unsigned char g_stAwtoSnap[20];
#endif
#define AWTO_WDT_REC_N                                          25      // bytes under ucCheck
#define AWTO_WDT_SEED                                           0xA5
#define AWTO_WDT_C_STALL                                        1       // pokes stopped: no main-loop pass and no bounded loop
#define AWTO_WDT_C_TMODE                                        0x40    // or-ed: built with AWTO_WDT_MODE = AWTO_WDT_TIMER_IRQ
#define AWTO_WDT_C_TEST                                         0x80    // or-ed: hang requested by test cmd 0x4C..0x4E
#define AWTO_WDT_B_BITE                                         0x02    // set by the bite, read by the next boot
#define AWTO_WDT_B_TEST                                         0x04    // test hang armed
#define AWTO_WDT_B_NEW                                          0x08    // record from a bite not yet shown on the console
#define AWTO_WDT_B_WARM                                         0x10    // this boot: warm reset without a capture
#define AWTO_WDT_B_COLD                                         0x20    // this boot: no valid record in RAM (power-up / brown-out)
#define AWTO_WDT_B_AFTER                                        0x40    // this boot follows a captured bite
#define AWTO_WDT_B_PROBE                                        0x80    // this boot follows a probe reset (test cmd 0x49 / 0x4F)
#define AWTO_WDT_B_HWWDT                                        0x01    // this boot: warm, AWTO_WDT_P_EARLY was set (was LVR: P0_01[6] reads 0
                                                                        // after every reset, #131 unit 2; raw value in the snapshot)
// Boot reason (#29): AwtoBootReason, the first sync-log line. Canary only: no reset-cause flag in DW8051 or RL6449 (docs/watchdog.md)
#define AWTO_BOOT_COLD                                          1
#define AWTO_BOOT_BITE                                          2       // value: cause << 24 | bank << 16 | PC
#define AWTO_BOOT_WARM                                          3       // no capture, no evidence: host ISP 0xEE, or a WDT reset with interrupts dead
#define AWTO_BOOT_PROBE                                         4
#define AWTO_BOOT_HWWDT                                         5       // no capture, but an early threshold IRQ came: hardware watchdog
#define AWTO_WDT_P_TIMER                                        0x01    // probe in timer mode (0x4F); else normal mode (0x49)
#define AWTO_WDT_P_ARMED                                        0x02    // probe running (a reset while set = the probe's reset)
#define AWTO_WDT_P_IRQ                                          0x04    // the threshold IRQ came (no pokes, CNT3 = AWTO_WDT_PROBE_THR)
#define AWTO_WDT_P_RESET                                        0x08    // the chip reset (CNT1 = 1) during the probe
#define AWTO_WDT_P_NORESET                                      0x10    // no reset within AWTO_WDT_PROBE_MS
#define AWTO_WDT_P_WDTI                                         0x20    // DW8051 EICON[3] WDTI set: Realtek's WDT also drives the core wdti
#define AWTO_WDT_P_EARLY                                        0x40    // a threshold IRQ before the warning since the last main pass (pokes
                                                                        // stopped > 439 ms); kept over the reset: hardware-WDT evidence
// One hardware watchdog (#138). Counters: CNT2 / 2048 XTAL -> CNT3 (143.0 us, wraps 585.9 ms) -> CNT1 (wraps).
// Poke = FFEA[6] clr_wdt: every main-loop pass and inside bounded loops only (rule: no unbounded loop around a poking wait).
// Warning = threshold IRQ at CNT1 = N - 1, CNT3 = THR (earlier matches return): capture, then sof_rst. Reset = CNT1 = N.
#define AWTO_WDT_NORMAL_IRQ                                     1       // normal mode: unit 2 (2026-11-11, probe 0x49): NO threshold IRQ
#define AWTO_WDT_TIMER_IRQ                                      2       // timer mode: unit 2 (probe 0x4F): IRQ fires, CNT1 overflow resets
#ifndef AWTO_WDT_MODE
#define AWTO_WDT_MODE                                           AWTO_WDT_TIMER_IRQ
#endif
// #150: FFEA[5] sf_hlt_wdt_en stops the counter while the MCU is halted on an SPI-flash common instruction (erase, program,
// WRSR: up to 200 ms each, no __code runs, no pokes). 0 = off (diagnostic build: AWTO_NV_EV then measures the halts)
#ifndef AWTO_WDT_HALT_FLASH
#define AWTO_WDT_HALT_FLASH                                     1
#endif
// Warning = 1.25 x the measured worst poke gap (wd8: power saving), reset at N = 1 (docs/watchdog.md, #150)
#ifndef AWTO_WDT_N
#define AWTO_WDT_N                                              1       // reset at 585.9 ms without a poke
#endif
#ifndef AWTO_WDT_THR
#define AWTO_WDT_THR                                            0x577   // warning at 1399 x 0.143 = 200.1 ms
#endif
#define AWTO_WDT_CNT3_XTAL                                      2048    // crystal clocks per CNT3 count (CNT2 / 2048 = 143 us)
#define AWTO_WDT_CNT3_WRAP                                      4096    // CNT3 is 12 bit
#define AWTO_WDT_WARN_MS                                        (((unsigned long)AWTO_WDT_THR * AWTO_WDT_CNT3_XTAL + _EXT_XTAL / 2) / _EXT_XTAL)
#define AWTO_WDT_RESET_MS                                       (((unsigned long)AWTO_WDT_N * AWTO_WDT_CNT3_WRAP * AWTO_WDT_CNT3_XTAL + _EXT_XTAL / 2) / _EXT_XTAL)
#define AWTO_WDT_N_BOOT_FIELD                                   (_BIT2 | _BIT1 | _BIT0)   // CNT1 N field at ScalerMcuInitial: N = 8 until ScalerTimerWDInitial
#define AWTO_WDT_PROBE_THR                                      0x100   // probe: IRQ expected 36.6 ms after the clear, reset at 585.9 ms (N = 1)
#define AWTO_WDT_PROBE_MS                                       1500    // probe: reset expected by 586 ms; N + 1 wraps (1172) x 1.25 -> 1.5 s
#define AWTO_WDT_FRAME                                          16      // WDT / Timer2 ISR: 2 B PC + 14 pushes (crash_sim_test checks)
#define AWTO_XFR(a)                                             (*(volatile __xdata unsigned char *)(a))
#if(_AWTO_WDT == _ON)
extern __data unsigned char _bs_cur;           // fw/sdcc/bank.asm bank shadow
extern void AwtoWdtInit(void);
extern unsigned char AwtoBootReason(void);
extern unsigned long AwtoBootValue(void);
extern void AwtoWdtIrq(unsigned char ucSp, unsigned char ucBank);
extern void AwtoWdtHang(unsigned char ucHow);
extern void AwtoWdtProbe(unsigned char ucTimer);
extern bit AwtoWdtValid(void);
extern void AwtoOsdWdtLines(void);
extern void ScalerTimerWDInitial(void);
#define AWTO_WDT_IRQ()                                          AwtoWdtIrq(SP, _bs_cur)
// clr_wdt latches the old counters: FFAC = CNT3[11:5], FFAD = CNT1 -> the gap this poke ended, for ucMaxPoke + the site (#150)
#define AWTO_WDT_POKE(site)                                     do { unsigned char ucG_; AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT; \
                                                                     ucG_ = ((AWTO_XFR(AWTO_R_WATCHDOG_CNT1_VALUE) & AWTO_F_WATCHDOG_CNT1_VALUE_WDT_CNT1_VALUE) != 0) ? 0xFF : (AWTO_XFR(AWTO_R_WATCHDOG_CNT3_VALUE) & AWTO_F_WATCHDOG_CNT3_VALUE_WDT_CNT3_H_VALUE); \
                                                                     if(ucG_ > g_stAwtoWdt.ucMaxPoke) { g_stAwtoWdt.ucMaxPoke = ucG_; g_ucAwtoPokeSite = (site); \
                                                                         g_ucAwtoPokeFrom = g_ucAwtoPokeLast; } g_ucAwtoPokeLast = (site); } while(0)
// poke sites (g_ucAwtoPokeSite: which one ended the longest gap; rtd_crash.py SITES)
#define AWTO_WDT_S_PASS                                         1       // main-loop pass
#define AWTO_WDT_S_DELAY                                        2       // ScalerTimerDelayXms
#define AWTO_WDT_S_POLL                                         3       // ScalerTimerPollingFlagProc
#define AWTO_WDT_S_EVENT                                        4       // ScalerTimerWaitForEvent
#define AWTO_WDT_S_MSG                                          5       // AwtoMsgWait
#define AWTO_WDT_S_WREN                                         6       // ScalerFlashWREN
#define AWTO_WDT_S_WRDIS                                        7       // ScalerFlashWRDis
#define AWTO_WDT_S_WRPROT                                       8       // ScalerFlashWRProtect
#define AWTO_WDT_S_FREAD                                        9       // ScalerFlashRead
#define AWTO_WDT_S_FWRITE                                       10      // ScalerFlashWrite sector part
#define AWTO_WDT_S_OSDSTR                                       11      // OsdPropPutString character
#define AWTO_WDT_S_T3                                           12      // retired #162 (was the blocking panel T3 wait); id kept for old crash records
#define AWTO_WDT_S_HPD                                          13      // retired #162 (was the blocking eDP HPD poll); id kept for old crash records
#define AWTO_WDT_S_CONLINE                                      14      // AwtoConLogSync console log line (#165)
extern volatile __xdata unsigned char g_ucAwtoPokeSite;
extern volatile __xdata unsigned char g_ucAwtoPokeFrom;    // site of the poke that started that gap (#150)
extern volatile __xdata unsigned char g_ucAwtoPokeLast;    // site of the last poke
// g_usTimerCounter steps back to 0 when ScalerTimerCheckTimerEvent rebases its event table: a negative gap counts 0
#define AWTO_WDT_PASS_AT()                                      ((((unsigned int)g_stAwtoWdt.ucPassHi) << 8) | g_stAwtoWdt.ucPassLo)
#define AWTO_WDT_FEED(site)                                     AWTO_WDT_POKE(site) // inside a bounded loop (docs/watchdog.md table)
#define AWTO_WDT_PASS(usNow)                                    do { unsigned int usG_ = (usNow) - AWTO_WDT_PASS_AT(); \
                                                                     usG_ = (usG_ >= 0x8000) ? 0 : (((usG_ >> 5) > 0xFF) ? 0xFF : (usG_ >> 5)); \
                                                                     if((unsigned char)usG_ > g_stAwtoWdt.ucMaxPass) { g_stAwtoWdt.ucMaxPass = (unsigned char)usG_; } \
                                                                     g_stAwtoWdt.ucPassHi = (unsigned char)((usNow) >> 8); g_stAwtoWdt.ucPassLo = (unsigned char)(usNow); \
                                                                     g_stAwtoWdt.ucProbe &= ~AWTO_WDT_P_EARLY; AWTO_WDT_POKE(AWTO_WDT_S_PASS); } while(0)
// After a bite the console opens by itself once the screen has been settled this long: the SDK's mode pop-up is drawn within
// one main-loop pass of the mode change (sim max pass < 4 checks = 800 ms) x 1.25; expiry = open the console (AwtoWdtShow)
#define AWTO_WDT_SHOW_MS                                        1000
extern void AwtoWdtShow(void);
#define AWTO_WDT_SHOW()                                         do { if((g_stAwtoWdt.ucBoot & AWTO_WDT_B_NEW) != 0) { AwtoWdtShow(); } } while(0)
#else
#define AWTO_WDT_IRQ()
#define AWTO_WDT_POKE(site)
#define AWTO_WDT_FEED(site)
#define AWTO_WDT_PASS(usNow)
#define AWTO_WDT_SHOW()
#define AwtoOsdWdtLines()
#endif
// #138: WD-timer protocol events on Timer0 (fw/sdcc/awto_t0ev.inc, appended to ScalerCommonTimerFunction.c)
extern void AwtoT0EvIsr(void);
extern void AwtoT0EvClock(void);
extern void AwtoT0EvTest(unsigned char ucHow);
extern void AwtoT0EvTestIsr(void);
extern volatile __xdata unsigned char g_ucAwtoT0Test;
#define AWTO_T0EV_EXINT0()                                      do { if(g_ucAwtoT0Test != 0) { AwtoT0EvTestIsr(); } } while(0)
#define AWTO_MSG_RING                                           40      // on-screen message log entries (#56)
typedef struct
{
    unsigned int usId;
    unsigned long ulValue;
} StAwtoMsg;
extern __xdata StAwtoMsg g_pstAwtoMsgRing[AWTO_MSG_RING];
extern __xdata unsigned char g_ucAwtoMsgHead;
extern __xdata unsigned int g_usAwtoMsgSeq;
extern __xdata unsigned char g_ucAwtoMsgLog;
extern __xdata unsigned char g_ucAwtoMsgOn;     // #74 runtime switch, 0 = off (default): AwtoMsgV returns at once; NVRAM b1AwtoMsgOn
extern unsigned char AwtoMsgWait(void);
extern void AwtoMsgLoad(void);
extern void AwtoDiagInit(void);
extern void AwtoDiagStage(unsigned char ucStage);
extern void AwtoDiagMainPass(void);
extern void AwtoDiagTestCmd(void);
extern bit AwtoHoldBlocksDisable(void);
extern void AwtoOsdDebugLines(void);
extern void AwtoOsdOfsInit(void);
// #39 key test screen + press log (fw/sdcc/awto_keytest.inc, awto_keypop.inc): read over debug slave 0x35 at map symbol _g_stAwtoKey
// (host: scripts/rtd_keywatch.py --log). Bytes only, so the layout is the same in LE and BE images.
#define AWTO_KEY_LOG_N                                          16      // press-log entries (ring, newest at index (ucCount - 1) % 16)
#define AWTO_KEY_REFRESH_MS                                     80      // screen redraw period: 100 ms (10 Hz floor) / 1.25
#define AWTO_KEY_RETRY_MS                                       250     // open but never drawn: draw again after this (one draw ~175 ms in the sim)
#define AWTO_KM_POWER                                           0x01    // = SDK masks of RTD2014Key.c (checked there); the Key.c names are not visible in OsdDisplay.c
#define AWTO_KM_MENU                                            0x10    // physical MENU = _EXIT_KEY_MASK (roles swapped, PCB_KEY_STATE)
#define AWTO_KM_UP                                              0x04    // _RIGHT_KEY_MASK
#define AWTO_KM_DOWN                                            0x08    // _LEFT_KEY_MASK
#define AWTO_KM_AUTO                                            0x02    // physical AUTO = _MENU_KEY_MASK
#define AWTO_KM_SOURCE                                          0x20    // _KEY5_MASK
#define AWTO_KEY_LAST_N                                         8       // keys in the screen's LAST row
#define AWTO_KEY_MSG_NONE                                       0xFF    // log entry: no key message came with the press (combo, POWER)
#define AWTO_KEY_MSG_SOURCE                                     4       // our SOURCE message (SDK messages 0..3 = menu role = AUTO key, RIGHT = UP, LEFT = DOWN, exit role = MENU key)
#define AWTO_KEY_F_INJ                                          0x80    // flags: injected (I2C test cmd, key_inject, key_hold)
#define AWTO_KEY_F_P30                                          0x01    // flags: P3.0 level (live and log entries)
typedef struct                                  // 8 B
{
    unsigned char ucSeq;                        // = ucCount at the time
    unsigned char ucTickHi;                     // g_stAwtoDiag.usT2Isr (1 ms), high byte first
    unsigned char ucTickLo;
    unsigned char ucA0;                         // raw ADC_A0 (0xFF09)
    unsigned char ucA1;                         // raw ADC_A1 (0xFF0A)
    unsigned char ucFlags;                      // bit0 = P3.0 level, bit7 = AWTO_KEY_F_INJ
    unsigned char ucMask;                       // SDK key mask (0 = injected message only)
    unsigned char ucMsg;                        // key message 0..4 or AWTO_KEY_MSG_NONE
} StAwtoKeyEntry;
typedef struct
{
    unsigned char ucMagic0;                     // 'K'
    unsigned char ucMagic1;                     // 'Y'
    unsigned char ucVersion;                    // 1
    unsigned char ucOpen;                       // test screen open
    unsigned char ucDrawn;                      // screen has been drawn (redraw allowed)
    unsigned char ucCount;                      // presses logged, wraps at 256; also the next seq
    unsigned char ucA0;
    unsigned char ucA1;
    unsigned char ucP30;
    unsigned char ucMask;
    unsigned char ucMsg;                        // last key message (0..4) or AWTO_KEY_MSG_NONE
    unsigned char ucFlags;                      // bit0 repeating, bit1 combo latch, bit7 key_hold mask on (live; #129)
    unsigned char ucRedraws;                    // screen redraws (wraps): keys_sim checks an idle open screen does not redraw
    unsigned char ucReserved[3];
    StAwtoKeyEntry pstLog[AWTO_KEY_LOG_N];
} StAwtoKey;
extern __xdata StAwtoKey g_stAwtoKey;
// #129 keys (fw/sdcc/awto_keys.inc): input monitor values -> AwtoKeyPoll (debounce, combos, repeat) -> AwtoKeyRoute (one dispatcher)
#define AWTO_KEY_SAMPLE_MS                                      10      // debounce: a change counts after two equal samples this far apart (SDK key scan: SEC(0.01))
#define AWTO_KEY_COMBO_MS                                       80      // UP / DOWN wait this long for a combo partner (UP+DOWN) before PRESS (two-finger press skew; longer feels slow)
#define AWTO_KEY_REPEAT_MS                                      500     // first REPEAT of a held key (SDK: SEC(0.5))
#define AWTO_KEY_RATE_MS                                        100     // then one REPEAT per this: 10 steps / s, a 0..100 slider in 10 s; the SDK repeated every main pass
#define AWTO_KEY_Q_N                                            4       // injected keys waiting for the next AwtoKeyPoll (one per host write; power of 2)
extern void AwtoKeyPoll(void);
extern void AwtoKeyInject(unsigned char ucMsg);
extern void AwtoSourceKey(unsigned char ucKey);
extern void AwtoKeyTestSet(unsigned char ucOn);
extern void AwtoKeyOsdReset(void);
extern void AwtoOsdKeyLines(void);
#define AWTO_KEY_TEST_ON()                                      ((g_stAwtoKey.ucOpen != 0) || (g_stAwtoGpio.ucOpen != 0))
#define AWTO_KEY_OSD_RESET()                                    AwtoKeyOsdReset()

// Realtek SDK demo menu (awto-ddc#120): built out; its OSD state table went with the SDK key path (#129).
#if(defined(_AWTO_REALTEK_MENU) && (_AWTO_REALTEK_MENU == _ON))
#error "_AWTO_REALTEK_MENU: the OperationTable dispatch is gone (#129)"
#endif
#define AWTO_REALTEK_MENU_OPEN()                                SET_OSD_STATE(_MENU_NONE)
#define AWTO_REALTEK_KEYINFO(k, s)
// Input monitor (fw/awto/inputs.tsv -> scripts/gen_awto_inputs.py): one poller keeps the value of every input; a change updates the transition ring
// (debug I2C slave 0x35, map symbol _g_stAwtoGpio, layout in scripts/gpio_diag.py) and marks that input for the console, which writes only that field.
// GENERATED-BEGIN awto_inputs
#define AWTO_IN_N                                               44      // inputs in fw/awto/inputs.tsv; also the transition ring id range
#define AWTO_IN_ROWS                                            39      // inputs shown on the diagnostic console (the first AWTO_IN_ROWS)
#define AWTO_IN_ADC0                                            8
#define AWTO_IN_ADC1                                            9
#define AWTO_IN_SOURCE                                          39
#define AWTO_IN_MENU                                            40
#define AWTO_IN_DOWN                                            41
#define AWTO_IN_UP                                              42
#define AWTO_IN_AUTO                                            43
#define AWTO_IN_POWER                                           11
// GENERATED-END awto_inputs
#define AWTO_GPIO_LOG_N                                         32
#define AWTO_GPIO_REFRESH_MS                                    20
#define AWTO_ADC_DEADBAND                                       2       // analog inputs: a change smaller than this is noise, not logged
typedef struct                                  // 5 B, byte-only so LE/BE layout is identical
{
    unsigned char ucSeq;
    unsigned char ucTickHi;
    unsigned char ucTickLo;
    unsigned char ucId;                         // input index in inputs.tsv
    unsigned char ucVal;                        // new value (0/1 for bits)
} StAwtoInEntry;
typedef struct
{
    unsigned char ucMagic0;                     // 'G'
    unsigned char ucMagic1;                     // 'P'
    unsigned char ucVersion;                    // 4: value table + 5 B ring
    unsigned char ucOpen;                       // console page (0 closed, AWTO_CON_*); VGA front end on for AWTO_CON_GPIO
    unsigned char ucDrawn;
    unsigned char ucSeq;                        // next transition sequence; ring index = seq & 31
    unsigned char ucRedraws;
    unsigned char ucN;                          // AWTO_IN_N
    unsigned char ucAny;                        // some input changed since the console drew
    unsigned char ucDirty[(AWTO_IN_N + 7) / 8]; // inputs changed since drawn
    unsigned char ucPad[16 - 9 - (AWTO_IN_N + 7) / 8];
    unsigned char ucIn[AWTO_IN_N];              // current value of every input
    StAwtoInEntry pstLog[AWTO_GPIO_LOG_N];
} StAwtoGpio;
extern __xdata StAwtoGpio g_stAwtoGpio;
extern void AwtoGpioPoll(void);
extern void AwtoGpioTestSet(unsigned char ucOn);
extern void AwtoOsdGpioLines(void);
extern __xdata unsigned char g_ucAwtoDiagFont;
extern __xdata unsigned char g_ucAwtoDiagSmall;
extern __xdata unsigned char g_ucAwtoProbeLines;
extern __xdata unsigned char g_ucAwtoProbeCols;
extern void AwtoProbeScroll(unsigned char ucReset);
extern void AwtoProbeSet(unsigned char ucLines);
extern void AwtoDiagConsole(unsigned char ucOn);
#define AWTO_CON_MAIN                                           1       // AwtoDiagConsole page: event log (2 = toggle main)
#define AWTO_CON_GPIO                                           3       // AwtoDiagConsole page: GPIO input table + its changes
extern void AwtoConScroll(signed char cD);
extern void AwtoConLogInit(void);
extern void AwtoConLogEvent(unsigned char ucId, unsigned char ucVal, unsigned int usTick);
extern void AwtoGpioConSet(unsigned char ucOn);
extern void AwtoKeyConSet(unsigned char ucOn);
#define AWTO_GPIO_TEST_ON()                                     (g_stAwtoGpio.ucOpen != 0)
extern void AwtoDiagT3Mark(unsigned char ucEnd);
#define AWTO_DIAG_T2ISR()                                       do { if(++g_stAwtoDiag.usT2Isr == 0) { g_stAwtoHt.usUpHi++; } AWTO_LED_T2ISR(); } while(0)
#define AWTO_DIAG_EX1ISR()                                      (g_stAwtoDiag.usEx1Isr++)
// Debug slave 0x35 answers 0x3A / 0x3C in the EXINT1 ISR (#38, docs/diag-block.md); diag version 2 = this is on.
#define _AWTO_DBGISR                                            _ON
#define _AWTO_DBGISR_BLK_MAX                                    24      // max bytes per 0x3C read: IIC __data FIFO fill, as the SDK 0xBB reply
// Debug slave 0x35 on the DDC of the active port, not fixed _PCB_DEBUG_DDC (#28): D1 -> DDC1 (DP AUX), D2 -> DDC2, D3 -> DDC3.
// SCL hold/release of the debug protocol follow FF22 (fw/sdcc/awto_dbgport.inc, keil2sdcc SUBS).
#ifndef _AWTO_DBG_FOLLOW
#define _AWTO_DBG_FOLLOW                                        _ON
#endif
#if(_AWTO_DBG_FOLLOW == _ON)
#define AWTO_DBG_SCL(op)                                        do { BYTE ucAwtoCh = MCU_FF22_IIC_CH_SEL & 0x07; \
    if(ucAwtoCh == 0x03) { MCU_FE66_DDC2_DDC_CONTROL_2 op; } else if(ucAwtoCh == 0x04) { MCU_FE6F_DDC3_DDC_CONTROL_2 op; } \
    else if(ucAwtoCh == 0x02) { MCU_FF2E_DDC1_DDC_CONTROL_2 op; } else if(ucAwtoCh == 0x01) { MCU_FF20_DDC0_DDC_CONTROL_2 op; } } while(0)
#endif
// M-domain set-up phases of the first set-up per boot (start, IVS wait 1, DCLK final offset, memory check, check OK): one sync log
// line each (AWTO_SYNC_EV_MSTEP, value = arg << 16 | val), every build; the other steps only in the ring below (#165).
// -D_AWTO_MEAS4K=_ON adds the 4K60 measurement ring (awto-ddc#26): Timer2 ISR samples scaler regs every AWTO_MEAS_PERIOD_MS from the
// first M-domain setup, layout in scripts/meas4k_dump.py; re-arm: write state byte (g_stAwtoMeas+3) = 0 over the debug slave, change mode.
#ifndef _AWTO_MEAS4K
#define _AWTO_MEAS4K                                            _OFF    // opt-in (Dan 2026-11-12, #165): 974 B XDATA
#endif
#define AWTO_MEAS_RD(a)                                         (*((volatile __xdata unsigned char *)(a)))
#define AWTO_MEAS_P0_02_0C()                                    (((unsigned int)AWTO_MEAS_RD(AWTO_R_WATCH_DOG_CTRL0) << 8) | AWTO_MEAS_RD(AWTO_R_STATUS0))
#define AWTO_MSTEP_LAST                                         13      // step id of the last line of a set-up (memory + timing gen check OK)
#define AWTO_MSTEP_MAX                                          7       // first set-up 5 lines x1.25: a set-up that never reaches LAST stops here, said in the log
#define AWTO_MSTEP(id, arg, val)                                { AwtoMstep((id), (arg), (val)); AwtoMeasEvent((id), (arg), (val)); }
extern void AwtoMstep(unsigned char ucId, unsigned char ucArg, unsigned int usVal);
extern __xdata unsigned char g_ucAwtoMstepN;   // step lines logged this boot; AWTO_MSTEP_MAX = done (write 0 over the debug slave to log the next set-up)
#if(_AWTO_MEAS4K == _ON)
#define AWTO_MEAS_PERIOD_MS                                     25
#define AWTO_MEAS_WINDOW_MS                                     1000
#define AWTO_MEAS_SAMPLES                                       42      // 1000 / 25 + 1 + 1 spare
#define AWTO_MEAS_EVENTS                                        40
typedef struct
{
    unsigned int usMs;
    unsigned char ucMode;
    unsigned char ucP0_02, ucP0_0C, ucP5_B0, ucP45_B0, ucP5_2B, ucP45_2B;
    unsigned char ucP0_3D, ucP0_3E, ucP0_40, ucP0_41, ucP0_45, ucP1_C4, ucP1_C5, ucP0_28;
} StAwtoMeasRec;                                // 17 B
typedef struct
{
    unsigned int usMs;
    unsigned char ucId;
    unsigned char ucArg;
    unsigned int usVal;
} StAwtoMeasEv;                                 // 6 B
typedef struct
{
    unsigned char ucMagic0;                     // 'M'
    unsigned char ucMagic1;                     // 'K'
    unsigned char ucVersion;                    // 1
    unsigned char ucState;                      // 0 idle (armable), 1 sampling, 2 done
    unsigned char ucArms;
    unsigned char ucNSamp;
    unsigned char ucNEv;
    unsigned char ucSampMax;                    // AWTO_MEAS_SAMPLES: the event table starts after this many samples
    unsigned int usStartMs;
    unsigned int usNextMs;
    unsigned int usEndMs;
    __xdata StAwtoMeasRec *pSampWr;
    StAwtoMeasRec stSamp[AWTO_MEAS_SAMPLES];
    StAwtoMeasEv stEv[AWTO_MEAS_EVENTS];
} StAwtoMeas;
extern __xdata StAwtoMeas g_stAwtoMeas;
extern void AwtoMeasInit(void);
extern void AwtoMeasEvent(unsigned char ucId, unsigned char ucArg, unsigned int usVal);
extern void AwtoMeasT2Sample(void);
#define AWTO_MEAS_T2ISR()                                       do { if(g_stAwtoMeas.ucState == 1) { AwtoMeasT2Sample(); } } while(0)
#else
#define AwtoMeasInit()
#define AwtoMeasEvent(a, b, c)
#define AWTO_MEAS_T2ISR()
#endif
// Exact input frequencies (#34, #26) from the input active-region count the M-domain set-up took (fw/sdcc/awto_freq.inc);
// pop-ups show 3 decimals from these. The SDK's own 0.1 Hz / 0.1 kHz values and decisions are untouched.
#define AWTO_XTAL_HZ                                            14318180UL      // board crystal, 4x NTSC colour burst; SDK _XTAL14318K = 14318 kHz
typedef struct
{
    unsigned long ulCount;                      // g_ulInputActiveRegionBackUp: measure clocks, first to last active pixel
    unsigned long ulMeasHz;                     // measure clock: crystal or M2PLL / P40_07 divider
    unsigned long ulPclkHz;                     // ulMeasHz * (IHtotal * (IVheight - 1 + extra) + IHwidth) / ulCount
    unsigned long ulHFreqHz;                    // ulPclkHz / IHtotal
    unsigned long ulVFreqmHz;                   // ulPclkHz * 1000 / (IHtotal * IVtotal)
    unsigned int usIHTotal;
    unsigned int usIVTotal;
    unsigned int usIHWidth;
    unsigned int usIVHeight;
    unsigned char ucExtraLines;                 // count spans extra lines with V scale-down (SDK fine-tune: 1, F-to-P 2)
    unsigned char ucValid;                      // 1 = fields above are from the current count
} StAwtoFreq;                                   // 30 B, big-endian in -be images
extern __xdata StAwtoFreq g_stAwtoFreq;
extern void AwtoFreqUpdate(void);
#define AwtoFreqInvalidate()                                    (g_stAwtoFreq.ucValid = 0)
// Debug port: DDC on the active port speaks the Realtek debug protocol (slave 0x35) instead of DDC/CI (0x37),
// so RTDCustomerTool / our CLI get live register access (#13). DDC/CI (ddcutil) is off while this is _ON.
#define _AWTO_DEBUG_PORT                                        _ON
// #60 KVM: DDC/CI 0x37 on the spare IIC engines, polled (fw/sdcc/awto_ddcci.inc); 0 = off, 1 = IIC_1 following the active
// port, 3 = IIC_1..3 fixed on DDC1/2/3 (every host can switch). The main engine then never enters DDC/CI mode (both would ACK 0x6E)
#ifndef _AWTO_DDCCI_PARK
#define _AWTO_DDCCI_PARK                                        0       // bisect (kvm1 dead on unit 3): 1 = IIC_1 polled but parked on channel 7 (no DDC)
#endif
#ifndef _AWTO_DDCCI_FIXCH
#define _AWTO_DDCCI_FIXCH                                       0       // bisect: IIC_1 fixed on this DDC channel (2 = DDC1 / D1 DP AUX), no follow
#endif
#ifndef _AWTO_DDCCI_NOPOLL
#define _AWTO_DDCCI_NOPOLL                                      0
#endif
#ifndef _AWTO_DDCCI_ENGINES
#define _AWTO_DDCCI_ENGINES                                     1       // RL6449 has one working spare IIC engine; IIC_2/3 register aliases do not answer on hardware
#endif
#define AWTO_XB(a)                                              (*(volatile __xdata unsigned char *)(a))
extern void AwtoInputSelect(unsigned char ucPort, unsigned char ucWhy);
// awto: dead-port guard hook, called from AWTO_SW_FAST_POLL (#84); fw/sdcc/awto_ddcci.inc. Switch-log arg 1 = port with no cable refused (VCP 0x60, menu row, selector),
// 3 = fixed port without cable in NOSIGNAL / PS while another port is cabled -> auto search, normal, SEARCH
#define AWTO_SW_EV_DEADPORT                                     0xB8
extern unsigned char AwtoPortCable(unsigned char ucPort);
// #81 per-port settings block (fw/sdcc/awto_port.inc): one bit per port per field, bit n = Dn (AWTO_PORT_BIT). Field today: enable.
// Disabled port: HPD held low (PCB_Dn_HOTPLUG), EDID channel off (ScalerMcuDdcRamEnable), receiver off (ScalerGDIPhyPowerProc),
// skipped by the search / AUTO (SysSourceHandler, SysSourceSwitchPort), the fast-switch cache and the wake poll.
extern __xdata unsigned char g_ucAwtoPortOff;
#define AWTO_PORT_BIT(port)                                     ((unsigned char)(1 << ((port) - _D0_INPUT_PORT)))
#define AWTO_PORT_OFF(port)                                     ((g_ucAwtoPortOff & AWTO_PORT_BIT(port)) != 0)
#define AWTO_PORT_HPD(n, x)                                     ((x) & (~g_ucAwtoPortOff >> (n)) & 1)   // PCB_Dn_HOTPLUG (x = 0 / 1): high only when on; no branch
#define AWTO_PORT_RX_ACTION(port, a)                            ((AWTO_PORT_OFF(port) && ((a) != _POWER_ACTION_NORMAL_TO_OFF) && ((a) != _POWER_ACTION_AC_ON_TO_OFF) && \
                                                                  ((a) != _POWER_ACTION_PS_TO_OFF)) ? _POWER_ACTION_SWITCH_INTERFACE_TO_OFF : (a))
#define AWTO_PORT_WHY_BOOT                                      0x01    // sync.tsv E1 rows: why a port changed (arg)
#define AWTO_PORT_WHY_OFF                                       0x02
#define AWTO_PORT_WHY_ON                                        0x03
#define AWTO_PORT_WHY_SELECTOR                                  0x04
#define AWTO_PORT_WHY_SELECT                                    0x05
#define AWTO_PORT_WHY_ON_SCREEN                                 0x06    // refusals
#define AWTO_PORT_WHY_LAST                                      0x07
#define AWTO_PORT_WHY_WAKE                                      0x08    // wake trigger on a disabled port (once per sleep)
#define AWTO_PORT_WHY_ALREADY_OFF                               0x09
#define AWTO_PORT_WHY_ALREADY_ON                                0x0A
#define AWTO_PORT_WHY_FIXED                                     0x0B    // fixed search on a disabled port -> auto
#define AWTO_SYNC_EV_PORT                                       0xE1    // #81 port settings line: arg = AWTO_PORT_WHY_*, value = port
extern void AwtoPortSelect(unsigned char ucPort, unsigned char ucWhy);   // a selection enables a disabled port first
extern void AwtoPortSkipSearch(void);
extern void AwtoPortBoot(void);                                 // AwtoSetInit: stored enables -> mask, boot lines
#define AWTO_PORT_SEARCH_GATE(idx)                              { if(AWTO_PORT_OFF(GET_INPUT_PORT(GET_INPUTPORT_TYPE(idx)))) { AwtoPortSkipSearch(); } }
extern void AwtoDeadPortPoll(void);
#define AWTO_DEAD_PORT_POLL()                                   { if((GET_SOURCE_SCAN_TYPE() == _SOURCE_SWITCH_FIXED_PORT) && \
                                                                     (GET_MODE_STATE() >= _MODE_STATUS_NOSIGNAL)) { AwtoDeadPortPoll(); } }   // NOSIGNAL / PS / OFF
extern void AwtoSourceOpen(unsigned char ucWhy);                // ucWhy = AWTO_SEL_EV_OPEN_KEY / _OPEN_CARD (its ring line)
// #139 selector, no picture: waits for a key; same 60 s as AWTO_L2_SEC (Dan's panel-off default), x1; expiry = SDK power-saving card, sleep
#define AWTO_SRC_SLEEP_SEC                                      60
#define AWTO_SRC_IDLE_COMMIT_MS                                 2000    // selector: highlighted input taken after this long with no key (Dan, 2026-11-12, #132)
extern void AwtoSourceAuto(unsigned char ucWho);                // auto source select: the selector's Auto row, the AUTO key (#132)
extern void AwtoSourceIdle(void);                               // OSD_DISABLE timer with the selector open: idle commit
extern void AwtoSourceReset(void);                              // SDK OSD reset (UserInterfaceAdjustOsdResetProc): the open selector's choice
#define AWTO_BL_KEY_STEP                                        1       // UP / DOWN backlight change per press / repeat, % (= registry brightness step)
#define AWTO_BL_VPOS_PCT                                        85      // backlight bar card: vertical position, % (lower screen, off the picture centre)
extern void AwtoBlKey(unsigned char ucKey);                     // backlight bar (#132): open on UP / DOWN, step
extern void AwtoBlClose(void);                                  // close it; the value is stored at the NVRAM gate
extern void set_nv_commit(unsigned char ucShow);
extern unsigned char AwtoSwCacheValid(unsigned char ucPort);
// #79 runtime swap: DDC/CI (IIC_1) owns the active port's DDC; VCP E3 = A5 NN (test cmd 0x3C) moves the
// debug slave 0x35 there for NN minutes (FF = until told back); test cmd 0x3B = back to DDC/CI now. Parked engine: DDC0.
#if(((_AWTO_DDCCI_ENGINES == 1) || (_AWTO_DDCCI_ENGINES == 3)) && (_AWTO_DDCCI_PARK == 0) && (_AWTO_DDCCI_FIXCH == 0) && (_AWTO_DDCCI_NOPOLL == 0) && (_AWTO_DBG_FOLLOW == _ON))
#define _AWTO_DBG_SWAP                                          _ON
#else
#define _AWTO_DBG_SWAP                                          _OFF
#endif
#define AWTO_DBG_PARK_CH                                        0x01    // DDC0: no D0 port here (7 = reserved: 0x35 then ACKed on DDC2, dead)
#define AWTO_DBG_LINK_VCP                                       0xE3    // not a registry code (0xE8 is, #67)
#define AWTO_DBG_LINK_MAGIC                                     0xA5
#if(_AWTO_DBG_SWAP == _ON)
extern __xdata unsigned char g_ucAwtoDbgLink;
extern __xdata unsigned int g_usAwtoDbgLinkSec;
extern __xdata unsigned char g_ucAwtoDdcciCh;
extern void AwtoDbgLinkSet(unsigned char ucMin);
extern void AwtoDbgLinkStart(unsigned char ucMin);
extern void AwtoDbgLinkPoll(void);
#if(_AWTO_DDCCI_ENGINES == 3)
extern void AwtoDdcciDebugLink(unsigned char ucPort, unsigned char ucOn);
#endif
#define AWTO_DBG_LINK_POLL()                                    { if(g_ucAwtoDbgLink != 0) { AwtoDbgLinkPoll(); } }
#else
#define AWTO_DBG_LINK_POLL()
#endif
#if(_AWTO_DDCCI_ENGINES != 0)
extern void AwtoDdcciPoll(void);
#if(_AWTO_DDCCI_NOPOLL == 1)
#define AWTO_DDCCI_POLL()                                       // bisect: engine __code linked, never called
#define AWTO_DDCCI_FOLLOW(ch)
#elif(_AWTO_DDCCI_ENGINES == 3)
#define AWTO_DDCCI_POLL()                                       { if((AWTO_XB(AWTO_R_IIC_1_SET_SLAVE) != AWTO_DDCCI_WR_ADDR) || ((AWTO_XB(AWTO_R_IIC_1_STATUS) | AWTO_XB(AWTO_R_IIC_2_STATUS) | AWTO_XB(AWTO_R_IIC_3_STATUS)) & AWTO_IIC_ATTN)) { AwtoDdcciPoll(); } AWTO_DBG_LINK_POLL(); }
#define AWTO_DDCCI_FOLLOW(ch)
#else
#define AWTO_DDCCI_POLL()                                       { if((AWTO_XB(AWTO_R_IIC_1_SET_SLAVE) != AWTO_DDCCI_WR_ADDR) || (AWTO_XB(AWTO_R_IIC_1_STATUS) & AWTO_IIC_ATTN)) { AwtoDdcciPoll(); } AWTO_DBG_LINK_POLL(); }
#if((_AWTO_DDCCI_PARK == 1) || (_AWTO_DDCCI_FIXCH != 0))
#define AWTO_DDCCI_FOLLOW(ch)
#else
#define AWTO_DDCCI_FOLLOW(ch)                                   { AWTO_XB(AWTO_R_IIC_1_CH_SEL) = (AWTO_XB(AWTO_R_IIC_1_CH_SEL) & ~AWTO_F_IIC_1_CH_SEL_IIC_1_CH_SEL) | (ch); }
#endif
#endif
#else
#define AWTO_DDCCI_POLL()
#define AWTO_DDCCI_FOLLOW(ch)
#endif
#if((_AWTO_DEBUG_PORT == _ON) || (_AWTO_DDCCI_ENGINES != 0))
#define GET_OSD_DDCCI_STATUS()                                  (_OFF)
#endif
#if(defined(_AWTO_NEW_SETTINGS) && (_AWTO_DDCCI_ENGINES != 0))   // #67 DDC/CI row: the spare-engine 0x37 path on/off, fixed at boot
extern __xdata unsigned char g_ucAwtoDdcciOn;
#define AWTO_DDCCI_POLL_ON()                                    (g_ucAwtoDdcciOn != 0)
#else
#define AWTO_DDCCI_POLL_ON()                                    (1)
#endif
// #80 IP over DDC (fw/sdcc/awto_net.inc, docs/ip-over-ddc.md): byte rings fed by DDC/CI op 0xD0 (Transport A, polled engine)
// and debug cmd 0x3D (Transport B, EXINT1 ISR); SLIP-framed Ethernet; ARP, ICMP echo, UDP echo + service. Work only when a
// transport raised g_ucAwtoNetRun (a host exchange): an idle link costs one XDATA byte test per pass.
#ifndef _AWTO_NET
#define _AWTO_NET                                               _OFF    // opt-in -D_AWTO_NET=_ON (Dan 2026-11-12, #165): 706 B XDATA, 4.8 KB code
#endif
#if(_AWTO_NET == _ON)
#define AWTO_NET_RING                                           128     // bytes per direction; divides 256 (BYTE indices wrap)
#define AWTO_NET_MASK                                           (AWTO_NET_RING - 1)
#define AWTO_NET_BUF                                            300     // one Ethernet frame (IP MTU 286), RX decode + TX encode
#define AWTO_NET_B_MAX                                          20      // 0x3D reply data: 4 hdr + 20 + chk = 25 FIFO bytes (as 0x3C)
#define AWTO_NET_A_MAX                                          9       // D1 reply data: 16-byte engine buffer - 6E len D1 seq flags free chk
#define AWTO_NET_A_IN                                           10      // D0 request data: len + D0 seq ctl ack + 10 + chk = 16
#define AWTO_NET_F_ACC                                          0x01    // reply flags: request __data taken
#define AWTO_NET_F_FULL                                         0x02    // not taken, RX ring full: resend with a new seq
#define AWTO_NET_F_BAD                                          0x04    // request checksum bad (B): nothing applied
#define AWTO_NET_F_RESET                                        0x08    // reset pending: no __data taken, none sent
#define AWTO_NET_F_ECHO                                         0x10    // raw loopback mode (ctl bit0)
#define AWTO_NET_F_MORE                                         0x20    // TX bytes beyond this reply
#define AWTO_NET_F_UP                                           0x80    // always set: a net firmware answered
#define AWTO_NET_CTL_ECHO                                       0x01
#define AWTO_NET_CTL_RESET                                      0x80
typedef struct
{
    unsigned char ucRxHead;                     // host -> fw ring: written by the transport (ISR for B)
    unsigned char ucRxTail;                     // read by AwtoNetPoll
    unsigned char ucTxHead;                     // fw -> host ring: written by AwtoNetPoll
    unsigned char ucTxTail;                     // advanced by the transport on the host's ack
    unsigned char ucBSeq;                       // 0x3D: last host seq (a repeat = retry: nothing re-applied)
    unsigned char ucBFlags;                     // its ACC / FULL result
    unsigned char ucASeq;                       // DDC/CI 0xD0: same
    unsigned char ucAFlags;
    unsigned char ucCtl;                        // host ctl of the last new exchange (bit0 echo)
    unsigned char ucReset;                      // 1 = AwtoNetPoll empties rings + frame state (transports pause)
    unsigned char pucRx[AWTO_NET_RING];
    unsigned char pucTx[AWTO_NET_RING];
} StAwtoNetLink;
extern __xdata StAwtoNetLink g_stAwtoNet;
extern __xdata unsigned char g_ucAwtoNetRun;
extern void AwtoNetPoll(void);
extern unsigned char AwtoNetXchgA(unsigned char *pucQ, unsigned char ucN, unsigned char *pucR);
#define AWTO_NET_POLL()                                         { if(g_ucAwtoNetRun != 0) { AwtoNetPoll(); } }
#else
#define AWTO_NET_POLL()
#endif
// #60 input-switch timeline (fw/sdcc/awto_sw.inc): mode-state changes, panel power actions, T3 wait in ms; HPD-low counters.
#define AWTO_SW_EVENTS                                          64      // #78: a wake logs ~45; repeats of the last event are dropped
#define AWTO_SW_EV_MODE                                         0x01    // arg = new g_stModeInfo mode state
#define AWTO_SW_EV_POWER                                        0x10    // arg = UserCommonInterfacePanelPowerAction event
#define AWTO_SW_EV_T3                                           0x20    // arg 0 = T3 wait start, 1 = end
#define AWTO_SW_EV_CMD                                          0x40    // arg = switch command (test cmd 0x30..0x33)
#define AWTO_SW_EV_HOLD_BLOCK                                   0x50    // OsdDispDisableOsd blocked by a hold (#28); arg = mode state
#define AWTO_SW_EV_PANEL                                        0x11    // #162 panel machine: arg = old state << 4 | new state; ring value = ms in the old state
#define AWTO_SW_EV_PANEL_X                                      0x12    // #162 arg AWTO_PNL_X_*: HPD timeout, link fail, a pin / PWM write outside the machine
#define AWTO_SW_EV_BLANK                                        0x80    // backlight kept on, picture blanked instead (#60 step 2); arg = site
#ifndef _AWTO_LOOP_PROF
#define _AWTO_LOOP_PROF                                         _OFF    // -D_AWTO_LOOP_PROF=_ON: per-handler main-loop cost (fw/sdcc/awto_loopprof.inc)
#endif
#define AWTO_LP_SLOTS                                           12
typedef struct
{
    unsigned char ucReset;                      // host writes 1: zeroed at the next pass start
    unsigned int usPer;                         // Timer2 counts per 1 ms tick
    unsigned long ulPasses;
    unsigned long pulT2[AWTO_LP_SLOTS];         // Timer2 counts per segment (scripts/loop_prof.py SLOTS)
    unsigned char ucPsOnly;                     // host writes 1: count only passes in power status SAVING (#144)
} StAwtoLoopProf;
#if(_AWTO_LOOP_PROF == _ON)
extern void AwtoLpMark(unsigned char ucK);
#define AWTO_LP(k)                                              AwtoLpMark(k)
#else
#define AWTO_LP(k)
#endif
#ifndef _AWTO_DP_FRAME_WAIT
#define _AWTO_DP_FRAME_WAIT                                     _ON     // #60: DP Rx1 two-frame waits from the measured frame (fw/sdcc/awto_dpframe.inc)
#endif
#ifndef _AWTO_LOOP_SPLIT
#define _AWTO_LOOP_SPLIT                                        _ON     // #75: slow checks every AWTO_SLOW_MS, not every pass (fw/sdcc/awto_loopsplit.inc)
#endif
#define AWTO_SLOW_MS                                            10      // detection latency <= 10 ms + 1 pass (limit 50 ms, #75)
#define AWTO_SLOW_JUDGE                                         0       // SysJudgeCheckStatus (48.6 % of an ACTIVE pass, #75)
#define AWTO_SLOW_CABLE                                         1       // SysSourceCableDetection
#define AWTO_SLOW_SLOTS                                         2
typedef struct
{
    unsigned int usFastRate;                    // main-loop passes in the last ~1 s (= g_stAwtoDiag.usLoopRate)
    unsigned int usSlowRate;                    // AWTO_SLOW_JUDGE runs in the last ~1 s (~1000 / AWTO_SLOW_MS)
    unsigned int usSlowRuns;                    // AWTO_SLOW_JUDGE runs, free-running
    unsigned int usMaxGapMs;                    // longest gap between two AWTO_SLOW_JUDGE runs in the last ~1 s
} StAwtoLoop;
#if(_AWTO_LOOP_SPLIT == _ON)
extern __xdata StAwtoLoop g_stAwtoLoop;
extern bit AwtoSlowDue(unsigned char ucSlot);
#define AWTO_SLOW_DUE(k)                                        AwtoSlowDue(k)
#else
#define AWTO_SLOW_DUE(k)                                        _TRUE
#endif
#ifndef _AWTO_SPLIT_CABLE
#define _AWTO_SPLIT_CABLE                                       _OFF    // _ON: cable detection on the slow path too: +6 % loop, but ACTIVE ~50 ms later at cold boot (#75)
#endif
#if(_AWTO_SPLIT_CABLE == _ON)
#define AWTO_SLOW_DUE_CABLE()                                   AWTO_SLOW_DUE(AWTO_SLOW_CABLE)
#else
#define AWTO_SLOW_DUE_CABLE()                                   _TRUE
#endif
#ifndef _AWTO_SPLIT_JUDGE
#define _AWTO_SPLIT_JUDGE                                       _ON     // SysJudgeCheckStatus on the slow path (#75)
#endif
#if(_AWTO_SPLIT_JUDGE == _ON)
#define AWTO_SLOW_DUE_JUDGE()                                   AWTO_SLOW_DUE(AWTO_SLOW_JUDGE)
#else
#define AWTO_SLOW_DUE_JUDGE()                                   _TRUE
#endif
#ifndef _AWTO_SW_MARKS
#define _AWTO_SW_MARKS                                          _OFF    // -D_AWTO_SW_MARKS=_ON: log main-loop segments >= AWTO_SW_SLOW_MS (#60)
#endif
#define AWTO_SW_SLOW_MS                                         20      // 7x a 4K60 pass (2.7 ms): only real stalls get logged
#define AWTO_SW_EV_SLOW                                         0x91    // arg = mark k: the __code before mark k took >= AWTO_SW_SLOW_MS
#define AWTO_SW_EV_RESET_AT                                     0x92    // arg = mark k: a mode reset target was set in the __code before mark k
#if(_AWTO_SW_MARKS == _ON)
extern void AwtoSwMark(unsigned char ucK);
#define AWTO_SW_MARK(k)                                         AwtoSwMark(k)
#define AWTO_SW_POLL_MARKS()                                    AwtoSwPoll()   // mode change logged right after judge / mode handler
#else
#define AWTO_SW_MARK(k)
#define AWTO_SW_POLL_MARKS()
#endif
#define AWTO_SW_EV_PROBE                                      0x90    // switch-path probe (#60); arg = site, names in scripts/sw_timeline.py
typedef struct
{
    unsigned char ucId;
    unsigned char ucArg;
    unsigned int usMs;
} StAwtoSwEv;
typedef struct
{
    unsigned char ucMagic;                      // 'S'
    unsigned char ucSeq;                        // +1 per arm
    unsigned char ucPort;                       // armed for this port (_Dn_INPUT_PORT)
    unsigned char ucN;                          // events recorded since the arm (max AWTO_SW_EVENTS)
    unsigned int usT0;                          // g_usTimerCounter at the arm
    unsigned char ucLastMode;
    unsigned char ucHpdLow[4];                  // HPD-low writes per port D0..D3 since boot (wraps)
    unsigned char ucHoldBlocks;                 // SDK OSD paths stopped by a held visual (#28), wraps
    StAwtoSwEv stEv[AWTO_SW_EVENTS];
} StAwtoSw;
extern __xdata StAwtoSw g_stAwtoSw;
extern void AwtoSwEvent(unsigned char ucId, unsigned char ucArg);
extern void AwtoSwArm(unsigned char ucPort);
extern void AwtoSwPoll(void);
#ifndef _AWTO_PANEL_LOG
#define _AWTO_PANEL_LOG                                         _ON     // every panel / backlight call with its outcome, real pin changes (#144)
#endif
#if(_AWTO_PANEL_LOG == _ON)
extern void AwtoPanelPinLog(unsigned char ucWhat);       // bit 1 = backlight pin (else VDD), bit 0 = the level written
#else
#define AwtoPanelPinLog(w)
#endif
extern void AwtoSwRec(unsigned char ucId, unsigned char ucArg);
// #162 panel machine line (UserCommonInterface.c): ring line + switch log. Transition (11): value = ms in the old state;
// request (10): who. No function of its own: its params would cost XDATA / DATA overlay (both full, #162 s3b).
#define AWTO_PNL_LOG(id, arg, val)                              { AwtoSyncPush((id), (arg), (val)); AwtoSwRec((id), (arg)); }
extern void AwtoSysLog(unsigned char ucArg, unsigned char ucWhy, unsigned long ulMs);
extern void AwtoSwMode(unsigned char ucMode);
#define AWTO_BPROF(k)                                           AwtoSwEvent(AWTO_SW_EV_PROBE, (k))   // #144 boot profile sites
#define AWTO_SW_HPD(port, x)                                    (g_stAwtoSw.ucHpdLow[port] += ((x) == 0))   // counter only (ISRs too); no branch (constant x)
// #139 sync / power-on log (fw/sdcc/awto_sync.inc): ring of stage events per episode (power on, switch, wake), on the console /
// selector and over I2C at map symbol _g_stAwtoSync (host: scripts/sync_log.py, rtd_diag.py --sync). Bytes only (LE = BE layout).
// GENERATED-BEGIN awto_port_cnt
#define AWTO_PS_CNT_N                                           1       // inputs whose rising edges are counted (fw/awto/portsig.tsv cnt rows)
#define AWTO_PS_COUNT(i, v)                                     { if((v) != 0) { if(i == 28) { g_pucAwtoInCnt[0]++; } } }
// GENERATED-END awto_port_cnt
extern __xdata unsigned char g_pucAwtoInCnt[];   // awto_gpio.inc: rising edges per counted input (wraps), read by the selector
#define AWTO_SYNC_N                                             60      // >= cold boot 38 lines x1.25 (boot_sim, #165) and cold boot + power off 50 lines on the console (con_wrap_sim); divides WRAP
#define AWTO_SYNC_WRAP                                          240     // seq counts 0..239 (a multiple of AWTO_SYNC_N): entry = seq % N
#define AWTO_SYNC_IDX(s)                                        ((unsigned char)((s) % AWTO_SYNC_N))
#define AWTO_SYNC_NEXT(s)                                       ((unsigned char)((((s) + 1) >= AWTO_SYNC_WRAP) ? 0 : ((s) + 1)))
#define AWTO_SYNC_BACK(s, n)                                    ((unsigned char)(((s) >= (n)) ? ((s) - (n)) : ((s) + AWTO_SYNC_WRAP - (n))))
typedef struct                                  // 8 B
{
    unsigned char ucId;                         // AWTO_SW_EV_* (mirrored) or AWTO_SYNC_EV_*
    unsigned char ucArg;                        // port byte for port events
    unsigned char ucMsHi;                       // g_stAwtoDiag.usT2Isr (1 ms) at the event
    unsigned char ucMsLo;
    unsigned char pucVal[4];                    // value, high byte first (fw/awto/sync.tsv fmt)
} StAwtoSyncEv;
typedef struct
{
    unsigned char ucMagic0;                     // 'S'
    unsigned char ucMagic1;                     // 'Y'
    unsigned char ucVersion;                    // 3: ucN / ucWrap in the header
    unsigned char ucSeq;                        // next event's seq, 0..AWTO_SYNC_WRAP-1; entry = stEv[seq % AWTO_SYNC_N]
    unsigned char ucEpSeq;                      // seq of the current episode's first event
    unsigned char ucKind;                       // AWTO_SYNC_K_* of the current episode
    unsigned char ucPort;                       // its port (0xFF = auto / unknown)
    unsigned char ucT0Hi;                       // usT2Isr at its start
    unsigned char ucT0Lo;
    unsigned char ucDone;                       // mode reached ACTIVE / NOSIGNAL / NOSUPPORT / POWER SAVING since the start
    unsigned char ucOpenReq;                    // console auto-open pending (awto_osdcard.inc AwtoSyncConPoll); AWTO_SYNC_OPEN_KEY = by UP+DOWN
    unsigned char ucSpare;                      // #150: repeats of the last line pair not yet written (AwtoSyncPush)
    unsigned char ucN;                          // AWTO_SYNC_N: entries in the ring (hosts size the read from this)
    unsigned char ucWrap;                       // AWTO_SYNC_WRAP
    StAwtoSyncEv stEv[AWTO_SYNC_N];
} StAwtoSync;
extern __xdata StAwtoSync g_stAwtoSync;
extern __xdata StAwtoSyncEv g_stAwtoSyncPin;  // #150: this boot's reason line, kept out of the ring
#define AWTO_SYNC_K_POWER_ON                                    1
#define AWTO_SYNC_K_SWITCH                                      2
#define AWTO_SYNC_K_WAKE                                        3
#define AWTO_SYNC_K_POWER_KEY                                   4
#define AWTO_SYNC_EV_BEGIN                                      0xC0    // arg kind, value port
#define AWTO_SYNC_EV_TMDS                                       0xC1    // predetect on, HDMI (clock not measured yet)
#define AWTO_SYNC_EV_TMDS_CLK                                   0xC6    // HDMI freq detector stable: value = measured TMDS clock, 0.1 MHz
#define AWTO_SYNC_EV_DP                                         0xC2    // predetect on, DP: value = link rate << 8 | lanes (DPCD 100h / 101h)
#define AWTO_SYNC_EV_SCAN                                       0xC3    // scan found a source: value = SDK source type
#define AWTO_SYNC_EV_LOST                                       0xC4    // predetect off
#define AWTO_SYNC_EV_TIMING                                     0xC5    // timing confirmed: value = H << 16 | V
#define AWTO_SYNC_EV_VFREQ                                      0xC7    // display setting done: exact V freq, mHz (#34)
#define AWTO_SYNC_EV_PCLK                                       0xC8    // exact pixel clock, kHz
#define AWTO_SYNC_EV_CONSOLE                                    0xCA    // the console opened by itself
#define AWTO_SYNC_EV_WAKE                                       0xCB    // + AWTO_WAKE_T_*: a trigger woke the monitor, arg = port
#define AWTO_SYNC_EV_DEADPORT                                   0xDF    // #84: arg 1 = port with no cable refused, 2 = fixed port without cable -> auto search; value = port
#define AWTO_SYNC_EV_SEL                                        0xE0    // input selector (#132): arg AWTO_SEL_EV_*, value = port of the item (0xFF = Auto)
#define AWTO_SEL_EV_OPEN_KEY                                    0x01    // opened by SOURCE, highlight on the value
#define AWTO_SEL_EV_OPEN_CARD                                   0x02    // opened by the SDK no-signal / power-saving wake event
#define AWTO_SEL_EV_KEPT_IDLE                                   0x03    // idle commit on the input it opened on: closed, no switch
#define AWTO_SEL_EV_KEPT_AUTO                                   0x04    // AUTO on the input it opened on: closed, no switch
#define AWTO_SEL_EV_CANCEL                                      0x05    // MENU: closed, the input it opened on kept
#define AWTO_SEL_EV_NOCABLE                                     0x06    // #84 take refused: no cable on the item; stays open
#define AWTO_SEL_EV_DPVER                                       0x07    // take ignored: DP version pop-up up
#define AWTO_SEL_EV_NOPORT                                      0x08    // take ignored: the item is no port of this board (value = item)
#define AWTO_SEL_EV_RESET                                       0x09    // closed by the SDK OSD reset (mode reset / signal back), nothing to take
#define AWTO_SEL_EV_CON_CLOSE                                   0x0A    // SOURCE closed a console that opened by itself, for the selector
#define AWTO_SYNC_EV_WAKE_OFF                                   0xCF    // arg = trigger + 1, value = port: wake suppressed
#define AWTO_SYNC_EV_BOOT                                       0xD0    // arg = AWTO_BOOT_* (first line of the power-on episode)
#define AWTO_SYNC_EV_STAGE                                      0xD1    // arg = diag stage 1..8
#define AWTO_SYNC_EV_INIT                                       0xD2    // arg 1 MCU init, 2 Timer2 tick, 3 watchdog run-time mode
#define AWTO_SYNC_EV_UNPLUG                                     0xD3    // arg = port: a cable unplug woke the monitor (AWTO_WAKE_T_UNPLUG)
#define AWTO_SYNC_EV_NV                                         0xD4    // #150 NVRAM save timing: arg 1..5 (sync.tsv), value = ms since the last poke
#define AWTO_NV_LOG_FLASH_TYPE                                  0x0C    // AWTO_SYNC_EV_NV arg: flash type the SDK detected (tFlashInformation index), at the first NVRAM step after it
#define AWTO_SYNC_REPEAT_LINES                                  2       // lines the repeat collapse compares (AwtoSyncSame back 2 and 3)
#define AWTO_SYNC_EV_REPEAT                                     0xD5    // #150 the 2 lines above repeated value times (collapsed)
#define AWTO_SYNC_EV_SDKWAKE                                    0xD6    // #150 wake from power saving not by our poll: arg port, value poll state
#define AWTO_SYNC_EV_MSTEP                                      0xE2    // #165 M-domain / DCLK fine-tune step: arg = step (AWTO_MSTEP), value = arg << 16 | val
#define AWTO_SYNC_EV_WAKE_TMDS                                  0xDC    // arg = port: a TMDS clock woke the monitor, value = clock 0.1 MHz (IOSC ref)
#define AWTO_SYNC_EV_PS_DDC                                     0xDD    // arg = port: SDK DDC handshake in power saving, gated (once per sleep)
#define AWTO_SYNC_EV_PS_AUX                                     0xDA    // arg = port: SDK DP AUX toggle in power saving, gated (once per sleep)
#define AWTO_SYNC_EV_PS_AUXCMD                                  0xDB    // arg = port: AUX command in power saving, no wake
#define AWTO_SYNC_EV_PS_BURST                                   0xDE    // arg = port: TMDS clock live shorter than the hold, value ms (once per sleep)
#define AWTO_SYNC_EV_HOST                                       0xD7    // #157 host time: arg = UTC offset (15 min, signed), value = unix s
#define AWTO_SYNC_EV_HOSTFW                                     0xD8    // #157 arg 1 first sync / 2 drift, value = fw ms (AwtoMs) at the sync
#define AWTO_SYNC_EV_DRIFT                                      0xD9    // #157 value = host - local tick, ms (signed)
// #157 host time: DDC/CI table write (0xE7) to this VCP, offset 0: unix s BE x4, ms BE x2, UTC offset (15 min, signed)
#define AWTO_HT_VCP                                             0xE9    // retired registry code (logo_ms, #144); get: max = syncs, cur = drift ms
#define AWTO_HT_STALE_MS                                        180000  // Dan: HOST marked stale after 3 min without a sync (host sends every 60 s)
#define AWTO_HT_DRIFT_MS                                        1000    // Dan: a ring line when the local tick and the host differ by more
#define AWTO_HT_GAP_S                                           2000000 // syncs further apart (23 days): drift not computed (ms must fit a long)
#define AWTO_TITLE_MS                                           1000    // Dan: title row live fields about 1/s; expiry = redraw changed cells
typedef struct                                  // host-read (sync_log.py): native words, BE images
{
    unsigned char ucSyncs;                      // syncs since boot (stops at 255), 0 = none yet
    signed char cOfs;                           // UTC offset, 15 min units
    unsigned int usFrac;                        // host ms within the second
    unsigned long ulEpoch;                      // host unix s at the sync
    unsigned long ulFwMs;                       // AwtoMs() at the sync
    int iDrift;                                 // host - local tick at the last sync, ms (clamped)
    unsigned int usUpHi;                        // AwtoMs bits 31..16, bumped by the Timer2 ISR (bits 15..0 = g_stAwtoDiag.usT2Isr)
} StAwtoHt;
extern __xdata StAwtoHt g_stAwtoHt;
extern unsigned long AwtoMs(void);
extern void AwtoHtSync(unsigned char *puc);
// #144 power-saving wake triggers (awto_sync.inc AwtoPsWakePoll), each once per port per sleep episode
#ifndef _AWTO_PS_WAKE
#define _AWTO_PS_WAKE                                           _ON
#endif
// AUX command alone: logged, no wake (_OFF, awto-ddc#163: host DP idle AUX ends every sleep); DPCD 600h = D0 / link training wake
#ifndef _AWTO_PS_AUX_WAKE
#define _AWTO_PS_AUX_WAKE                                       _OFF
#endif
#define AWTO_WAKE_T_CABLE                                       0       // cable status not connected -> connected
#define AWTO_WAKE_T_EDID                                        1       // DDCn_EDID_IRQ bit0: the source read the EDID
#define AWTO_WAKE_T_AUX                                         2       // DP AUX_IRQ_STATUS bit0: an AUX command arrived
#define AWTO_WAKE_T_DPCD                                        3       // DPCD 600h went to D0
#define AWTO_WAKE_T_UNPLUG                                      4       // cable status connected -> not connected (task 6)
#define AWTO_WAKE_T_TMDS                                        5       // HDMI freq detector stable on a port with a cable (#144 q7)
#define AWTO_WAKE_T_N                                           6
// Wake poll period in power saving: 200/s. = the SDK's own freq-measure wait (TMDS PS predetect: 5 ms "for measure 5
// times"), the TMDS check's restart -> read interval; cable debounce (AWTO_SLOW_MS 10) sampled 2x. Not met = max gap readout.
#define AWTO_PS_POLL_MS                                         5
// TMDS wake hold: SDK-stable (FREQDET_STABLE 63 in-bound measurements) at every restarted measurement for 50 ms: ~10 SDK
// stable windows, outlasts the host's short TMDS bursts (#144); expiry = wake, line D7. Gap > 3 polls ends a run (burst, line D9).
#define AWTO_PS_TMDS_HOLD_MS                                    50
#define AWTO_PS_TMDS_GAP_MS                                     (3 * AWTO_PS_POLL_MS)
#define AWTO_IOSC_KHZ                                           28000UL // _INTERNAL_OSC_XTAL: freq-detect reference in power saving
#if(_AWTO_PS_WAKE == _ON)
#define AWTO_PS_CABLE_SDK()                                     (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL)
#else
#define AWTO_PS_CABLE_SDK()                                     _TRUE
#endif
// selector stage codes (AwtoSyncStage): texts in awto_osdcard.inc tAwtoCardS from AWTO_CT_STAGE
#define AWTO_SYNC_ST_IDLE                                       0
#define AWTO_SYNC_ST_SEARCH                                     1
#define AWTO_SYNC_ST_SCAN                                       2
#define AWTO_SYNC_ST_STABLE                                     3
#define AWTO_SYNC_ST_MEASURE                                    4
#define AWTO_SYNC_ST_TIMING                                     5
#define AWTO_SYNC_ST_DISPLAY                                    6
#define AWTO_SYNC_ST_ACTIVE                                     7
#define AWTO_SYNC_ST_NOSIGNAL                                   8
#define AWTO_SYNC_ST_NOSUPPORT                                  9
#define AWTO_SYNC_ST_SLEEP                                      10
#define AWTO_SYNC_ST_OFF                                        11
#define AWTO_SYNC_ST_FAST                                       12
#define AWTO_SYNC_ST_INIT                                       13
// DDCn_EDID_IRQ of the port's DDC channel (regdb: DDC1 FFE5, DDC2 FE69, DDC3 FE72; bit2 SCL toggle, bit0 EDID read, W1C)
#define AWTO_DDC_IRQ_REG(sel)                                   (((sel) == _DDC1) ? AWTO_R_DDC1_EDID_IRQ : (((sel) == _DDC2) ? AWTO_R_DDC2_EDID_IRQ : AWTO_R_DDC3_EDID_IRQ))
#define AWTO_DDC_IRQ_D1                                         AWTO_DDC_IRQ_REG(_D1_DDC_CHANNEL_SEL)
#define AWTO_DDC_IRQ_D2                                         AWTO_DDC_IRQ_REG(_D2_DDC_CHANNEL_SEL)
#define AWTO_DDC_IRQ_D3                                         AWTO_DDC_IRQ_REG(_D3_DDC_CHANNEL_SEL)
// Selector rows refresh: a human reads them; 4 Hz (250 ms) shows a switch's stages; expiry = one field compare per port
#define AWTO_SRC_POLL_MS                                        250
// DDC live: HDCP 1.4 Ri checks run every 2 s (the slowest regular DDC traffic) x 1.25 = 2.5 s -> 3 s = 12 polls; expiry = "ddc-"
#define AWTO_SRC_DDC_POLLS                                      12
extern void AwtoSyncInit(void);
extern void AwtoSyncMark(void);
extern void AwtoNvEv(unsigned char ucStep);
#define AWTO_NV_EV(k)                                           AwtoNvEv(k)
extern void AwtoSyncT2Start(void);
#define AWTO_SYNC_MARK()                                        AwtoSyncMark()
extern void AwtoSyncBegin(unsigned char ucKind, unsigned char ucPort);
extern void AwtoSyncPush(unsigned char ucId, unsigned char ucArg, unsigned long ulVal);
extern void AwtoSyncSw(unsigned char ucId, unsigned char ucArg);
extern void AwtoSyncDetect(unsigned char ucPort, unsigned char ucKind, unsigned char ucPre, unsigned char ucType);
extern void AwtoSyncTiming(void);
extern void AwtoSyncFreq(void);
extern void AwtoSyncPoll(void);
extern unsigned char AwtoSyncRow(unsigned char ucId, unsigned char ucArg);
extern unsigned char AwtoSyncStage(unsigned char ucPort);
extern unsigned char AwtoDdcLive(unsigned char ucI);
extern unsigned long AwtoTmdsIdleKhz(unsigned char ucPage);
#define AWTO_SYNC_SW(id, arg)                                   AwtoSyncSw((id), (arg))
extern __xdata unsigned char g_ucAwtoSyncPwr;
#if(_AWTO_PS_WAKE == _ON)
extern __xdata unsigned char g_ucAwtoPsWakeCon;
extern void AwtoPsWakePoll(void);
extern void AwtoPsWakeArm(void);
extern void AwtoPsWakeReset(void);
extern unsigned char AwtoPsTmdsLive(unsigned char ucPage);    // TMDS freq detector live (our wake poll)
extern void AwtoPsDdcSeen(unsigned char ucPort);
extern void AwtoPsAuxSeen(unsigned char ucPort);              // SDK DP PS predetect: AUX toggle counted, no wake (keil2sdcc sub)              // SDK TMDS PS predetect: DDC handshake counted, no wake (keil2sdcc sub)
// #162 step 3: power status changes are logged by the system machine (AwtoSyncPoll at the transition); per pass only the wake poll
#define AWTO_SYNC_POLL()                                        { if(g_ucAwtoSyncPwr == _POWER_STATUS_SAVING) { AwtoPsWakePoll(); } }
// between main-loop handlers (keil2sdcc): armed (AwtoSyncPoll saw SAVING) and still SAVING; the poll returns unless due
// one call per site, the compares in AwtoPsPollSite: 14 sites in main, which is in the full common area (#157 merge)
extern void AwtoPsPollSite(void);
#define AWTO_PS_POLL_SITE()                                     AwtoPsPollSite()
#else
#define AWTO_SYNC_POLL()
#define AWTO_PS_POLL_SITE()
#endif
extern __xdata unsigned char g_ucAwtoConAuto;  // the open console opened itself: SOURCE closes it for the selector (#132)
extern __xdata unsigned char g_ucAwtoSyncCon;  // 0 = no console auto-open (sim / tests); the setting is registry sync_console
#define AWTO_SYNC_OPEN_KEY                                      2       // ucOpenReq: UP+DOWN in power saving (#132): opens once awake, whatever the setting
extern void AwtoOsdSyncPoll(void);
extern void AwtoConLogSync(void);
// per pass: call only with work to do (console open, auto-open pending, selector open); a call every pass costs loop rate (#139)
#define AWTO_OSD_SYNC_POLL()                                    { if((g_stAwtoSync.ucOpenReq != 0) || AWTO_KEY_TEST_ON() || \
                                                                     (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE)) { AwtoOsdSyncPoll(); } }
// #144 power-on: mode INITIAL opens the console with the live power-on log (awto_osdcard.inc AwtoBootConsole), then
// panel + backlight on so it shows while the input syncs. _OFF: the panel comes on at display setting (no boot console).
#ifndef AWTO_PS_CABLE_SDK
#define AWTO_PS_CABLE_SDK()                                     _TRUE   // no #144 wake poll (sync log off)
#endif
#ifndef _AWTO_BOOT_PANEL_EARLY
#define _AWTO_BOOT_PANEL_EARLY                                  _ON
#endif
#if(_AWTO_BOOT_PANEL_EARLY == _ON)
extern void AwtoBootConsole(void);
#else
#define AwtoBootConsole()
#endif
// Fast boot (#63, Dan's panel policy 2026-11-07): no waits for the DDR / VCCK rails our board never switches (D026 200 ms,
// D027 2 x 10 ms; PCB_DDR_POWER / PCB_VCCK_OFF_POWER are no-ops), panel VDD right after pin-share, T3 = one frame while the
// scaler shows its own pattern (black background): no host video can glitch, the panel only needs a valid frame.
#define _AWTO_FAST_BOOT                                         _ON
// #60 step 2 (Dan's panel policy 4): no backlight off on mode reset / display setting / DCLK change; the picture is blanked
// (forced background) instead and the active proc unblanks it. Real power saving still turns the backlight off.
#define AWTO_BLANK(site)                                        { ScalerDDomainBackgroundEnable(_ENABLE); AwtoSwEvent(AWTO_SW_EV_BLANK, (site)); }
// #60 step 3: _OFF = the SDK never pulses HDMI HPD low on a switch / timing change (host saw 2 drm uevents per switch to D2)
#define _AWTO_HDMI_HPD_TOGGLE                                   _OFF
// #78: _ON = TMDS Initial keeps the SCDC module (host-written 1/40 ratio, scrambling) after a no-signal power-off; the
// HPD-low IRQ still clears it (SDK). With no HPD pulse the host never rewrites SCDC: DPMS wake searched forever
#ifndef _AWTO_SCDC_KEEP
#define _AWTO_SCDC_KEEP                                         _ON
#endif
// #78: _ON = AWTO_TMDS_STUCK_N "source unstable" judges in a row on HDMI = one HPD pulse (host re-links, rewrites SCDC);
// at most AWTO_TMDS_HPD_MAX per episode. Case: chip reset (flash, watchdog) under a live 4K60 link, no host hot-plug seen
#define _AWTO_TMDS_HPD_RECOVER                                  _ON
#define AWTO_TMDS_STUCK_N                                       3       // one search round ~180 ms: pulse ~0.55 s into a stuck link
#define AWTO_TMDS_HPD_MAX                                       2
#define AWTO_TMDS_HPD_LOW_MS                                    110     // HDMI 1.4b: a source reads HPD low >= 100 ms as unplug
#define AWTO_SW_EV_HPD_RECOVER                                  0xB0    // arg = port pulled low
#define AWTO_SW_EV_HPD_RECOVER_UP                               0xB1    // arg = port high again (AWTO_TMDS_HPD_LOW_MS later, no wait)
#if(_AWTO_TMDS_HPD_RECOVER == _ON)
extern void AwtoTmdsStuck(void);
extern void AwtoTmdsHpdTick(void);
#define AWTO_TMDS_STUCK()                                       AwtoTmdsStuck()
#define AWTO_TMDS_HPD_TICK()                                    AwtoTmdsHpdTick()
#else
#define AWTO_TMDS_STUCK()
#define AWTO_TMDS_HPD_TICK()
#endif
// #60: _ON = ScalerSyncInterfaceSwitch leaves the other ports powered (PHY, Z0, TMDS MAC): the idle receiver stays locked
#ifndef _AWTO_KEEP_IDLE_RX
#define _AWTO_KEEP_IDLE_RX                                      _ON
#endif
#if(_AWTO_KEEP_IDLE_RX == _ON)
#define AWTO_IDLE_RX_OFF(port)
// idle TMDS: freq-detect / clock IRQs off (their ISR forces the shared display to background on a clock mismatch),
// MAC power and the clock count kept (the SDK's ScalerTMDSFreqDetectDisable also cut those)
#define AWTO_IDLE_TMDS_OFF()                                    { ScalerSetBit(P71_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00); ScalerSetBit(P71_EF_HDMI_ERROR_TH, ~_BIT7, 0x00);\
                                                                  ScalerSetBit(P72_E6_HDMI_FREQDET_CTRL, ~_BIT1, 0x00); ScalerSetBit(P72_EF_HDMI_ERROR_TH, ~_BIT7, 0x00); }
#else
#define AWTO_IDLE_TMDS_OFF()                                    ScalerTMDSFreqDetectDisable()
#define AWTO_IDLE_RX_OFF(port)                                  ScalerGDIPhyPowerProc((port), _POWER_ACTION_SWITCH_INTERFACE_TO_OFF)
#endif
#if((_AWTO_KEEP_IDLE_RX == _ON) && defined(_AWTO_NEW_SETTINGS))   // #67: Keep idle inputs row, fixed at boot
extern __xdata unsigned char g_ucAwtoKeepIdle;
#undef AWTO_IDLE_RX_OFF
#define AWTO_IDLE_RX_OFF(port)                                  { if(g_ucAwtoKeepIdle == 0) { ScalerGDIPhyPowerProc((port), _POWER_ACTION_SWITCH_INTERFACE_TO_OFF); } }
#endif
// #60: _ON = a switch to a port whose cached timing matches the screen skips search / measure / display setting
// (fw/sdcc/awto_fastsw.inc); needs the switch log (timer) and idle receivers kept powered
#ifndef _AWTO_FAST_SWITCH
#define _AWTO_FAST_SWITCH                                       _ON
#endif
#if(_AWTO_KEEP_IDLE_RX == _OFF)
#undef _AWTO_FAST_SWITCH
#define _AWTO_FAST_SWITCH                                       _OFF
#endif
#define AWTO_SW_EV_FAST                                         0xA0    // arg 0 = taken, 1 = refused (state / no cache), 0x21..0x28 = timing field differs, 3 = receiver unstable, 4 = SDK reset meanwhile, 5 = timeout -> full path
#if(_AWTO_FAST_SWITCH == _ON)
extern void AwtoSwCacheStore(void);
extern unsigned char AwtoSwFast(unsigned char ucPort);
extern void AwtoSwFastPoll(void);
extern __xdata unsigned char g_ucAwtoFastPending;      // port being brought up by the fast path, 0 = none
// #162 s3: console lines wait while a fast switch settles; s3b: and inside a panel machine tick / a system transition line (line
// time = transition time; the OSD poll or the next line draws them)
#define AWTO_CON_LIVE()                                         ((g_ucAwtoFastPending == 0) && (g_ucAwtoPanelOwn == 0) && (g_ucAwtoSysOwn == 0))
#define AWTO_SW_EV_FAST_WHY                                     0xA1    // at a fast-path timeout: 1 measure busy, 2 watchdog, 4 FIFO / HV error, 8 receiver unstable, 0x10 timing change, 0x20 judge check
#define AWTO_SW_EV_FAST_FLAGS                                   0xA2    // first M-domain error after a fast unblank: P0_02 bits 6,5,1,0, bit7 = watchdog P0_0C.0
// #78 power levels (fw/sdcc/awto_fastsw.inc AwtoWakeHold): L1 backlight off at signal loss, L2 panel off, L3 SDK power saving
#ifndef _AWTO_WAKE_HOLD
#define _AWTO_WAKE_HOLD                                         _ON
#endif
#define AWTO_L2_SEC                                             60      // Dan 2026-11-08: 1 min; #162 (Dan 2026-11-12): then the no-signal -> power-saving timers
#define AWTO_HOLD_CHECK_MS                                      10      // receiver check while held: wake latency <= 10 ms + 1 pass
#define AWTO_HOLD_AUTO_SEC                                      5       // auto search + a 2nd cable: hold this long, then SDK search
#define AWTO_REHOLD_MS                                          3000    // no new hold this soon after a fast wake (a post-wake judge fail = full path)
#define AWTO_HOLD_TRIES                                         4       // fast wakes that time out (8 frames each) before the full path
#define AWTO_SW_EV_HOLD                                         0xA8    // 1 L1 entered, 2 L2 released to no signal, 4 tries used up, 5 signal back, 6 backlight on, 7 retry, 9 auto search, another cable, 0x10 SDK reset
typedef struct
{
    unsigned char ucL1;                         // per-level enable (0/1); settings registry / test cmds 0x36..0x39
    unsigned char ucL2;
    unsigned int usL2Sec;                       // s in hold before L2 (released to the no-signal path)
} StAwtoPower;
#if(_AWTO_WAKE_HOLD == _ON)
extern __xdata StAwtoPower g_stAwtoPower;
extern __xdata unsigned char g_ucAwtoHold;
extern __xdata unsigned char g_ucAwtoWakePending;
extern __xdata unsigned char g_ucAwtoNoHold;
extern bit AwtoWakeHold(void);
extern void AwtoWakePoll(void);
#define AWTO_FAST_SETTLE_FRAMES                                 ((g_ucAwtoWakePending != 0) ? 1 : 3)   // wake: same port, no mux jump
#define AWTO_WAKE_POLL()                                        { if(g_ucAwtoHold != 0) { AwtoWakePoll(); } }
#else
#define AWTO_FAST_SETTLE_FRAMES                                 3
#define AWTO_WAKE_POLL()
#endif
#if(_AWTO_SW_MARKS == _ON)
#define AWTO_SW_FAST_POLL()                                     { AwtoSwFastPoll(); AWTO_WAKE_POLL(); AWTO_DEAD_PORT_POLL(); }    // also runs the post-unblank flag watch
#else
#define AWTO_SW_FAST_POLL()                                     { if(g_ucAwtoFastPending != 0) { AwtoSwFastPoll(); } AWTO_WAKE_POLL(); AWTO_DEAD_PORT_POLL(); }
#endif
#define AWTO_FAST_SCALER_BYTES                                  48      // >= sizeof(StAwtoFastScaler), checked at compile time
extern void AwtoFastScalerSave(unsigned char __xdata *pucBuf);
extern unsigned char AwtoFastScalerMatch(unsigned char __xdata *pucBuf);
extern void AwtoFastScalerClearStatus(unsigned char ucFirst);
extern unsigned char AwtoFastScalerApply(unsigned char __xdata *pucBuf, unsigned char ucSourceType, unsigned char ucPort);
extern unsigned char AwtoFastScalerMeasureOk(void);
extern unsigned char AwtoFastScalerStatus(void);
#else
#define AwtoSwCacheStore()
#define AwtoSwFastPoll()
#define AWTO_CON_LIVE()                                         ((g_ucAwtoPanelOwn == 0) && (g_ucAwtoSysOwn == 0))
#define AWTO_SW_FAST_POLL()                                     AWTO_DEAD_PORT_POLL()
#undef _AWTO_WAKE_HOLD
#define _AWTO_WAKE_HOLD                                         _OFF
#endif
// Backlight on (Dan 2026-11-13): wanted -> pin on after bl_on_delay, pin -> PWM duty after bl_pwm_ms; defaults 0 = at once
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_BL_ON_DELAY_MS                                     AWTO_SET(BL_ON_DELAY)       // #67 registry, default 0
#define AWTO_BL_TO_PWM_MS                                       AWTO_SET(BL_PWM_MS)         // #67 registry, default 0
#else
#define AWTO_BL_ON_DELAY_MS                                     0
#define AWTO_BL_TO_PWM_MS                                       0
#endif
// #162 panel machine (UserCommonInterface.c): the one driver of panel VDD, eDP-1 PHY / link / stream, backlight pin and PWM.
// Callers request (UserCommonInterfacePanelPowerAction); UserCommonInterfacePanelPowerTick() steps it, never waits. docs/design-162.md.
#define AWTO_PNL_OFF                                            0       // VDD off, T6 done
#define AWTO_PNL_VDD                                            1       // VDD on: T1, then the PHY once power status is NORMAL
#define AWTO_PNL_HPD                                            2       // PHY on: HPD read each tick, bound T2
#define AWTO_PNL_LINK                                           3       // link training (one step)
#define AWTO_PNL_VIDEO                                          4       // stream on (backlight: its own sub-state)
#define AWTO_PNL_T4                                             9       // backlight off: T4, then the stream idle (5..8 retired: T3 / BL states)
#define AWTO_PNL_T5                                             10      // stream idle: T5, then link / PHY / VDD off
#define AWTO_PNL_T6                                             11      // VDD off: T6 before VDD may come on again
#define AWTO_PNL_BL_DARK                                        0       // backlight sub-state (beside VDD .. VIDEO): pin off
#define AWTO_PNL_BL_PIN                                         1       // pin on: bl_pwm_ms, then the PWM duty
#define AWTO_PNL_BL_LIT                                         2       // PWM duty set
#define AWTO_PNL_BL_DIM                                         3       // PWM dark: PWM-to-backlight time, then the pin off
#define AWTO_PNL_BL_ARG(o, n)                                   (0xC0 | ((o) << 2) | (n))   // line 11 arg of a backlight change
#define AWTO_PNL_BL_DELAYED                                     0x10    // + arg: pin on after a non-zero bl_on_delay
#define AWTO_PNL_TGT_OFF                                        0       // request levels: panel off
#define AWTO_PNL_TGT_VIDEO                                      1       // VDD + link + stream, backlight off
#define AWTO_PNL_TGT_BL                                         2       // all on
#define AWTO_PNL_X_HPD                                          0       // AWTO_SW_EV_PANEL_X args
#define AWTO_PNL_X_LINK                                         1
#define AWTO_PNL_X_VDD                                          2       // 2 + resource: written outside the machine
#define AWTO_PNL_X_BL                                           3
#define AWTO_PNL_X_PWM                                          4
#define AWTO_PNL_X_ON                                           0x10    // pin args (X_VDD / X_BL): + level on
#define AWTO_PNL_X_SAME                                         0x20    // pin args: + no edge (written to the level it had)
// #162 s3b panel requests: UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(event, AWTO_PNL_BY_*)), who in bits 7..2
#define AWTO_PNL_REQ(ev, by)                                    ((unsigned char)(((by) << 2) | (ev)))
#define AWTO_PNL_EV(req)                                        ((req) & 0x03)      // _PANEL_ON / _PANEL_OFF / _BACKLIGHT_ON / _BACKLIGHT_OFF
#define AWTO_PNL_REQ_DEFER                                      0x0C    // request line arg 0C + event: deferred (power switch waits for the panel)
#define AWTO_PNL_BY_BOOT_COLD                                   0x01    // who codes: texts in fw/awto/sync.tsv id 1B
#define AWTO_PNL_BY_BOOT_WARM                                   0x02
#define AWTO_PNL_BY_PWR_ON                                      0x03    // SysPowerSwitch OFF_TO_NORMAL
#define AWTO_PNL_BY_PWR_WAKE                                    0x04    // SysPowerSwitch PS_TO_NORMAL
#define AWTO_PNL_BY_WAKE_POLL                                   0x05
#define AWTO_PNL_BY_PWR_DOWN                                    0x06
#define AWTO_PNL_BY_PWR_BACK                                    0x07
#define AWTO_PNL_BY_VIDEO_WANTED                                0x08
#define AWTO_PNL_BY_DS_BL_OFF                                   0x09
#define AWTO_PNL_BY_DS_DCLK                                     0x0A
#define AWTO_PNL_BY_OSD_RESET                                   0x0B
#define AWTO_PNL_BY_FIRST_ACTIVE                                0x0C
#define AWTO_PNL_BY_HOLD_L1                                     0x0D
#define AWTO_PNL_BY_HOLD_BACK                                   0x0E
#define AWTO_PNL_BY_SELECTOR                                    0x0F
#define AWTO_PNL_BY_OSD_NOSIGNAL                                0x10
#define AWTO_PNL_BY_OSD_NOCABLE                                 0x11
#define AWTO_PNL_BY_OSD_NOSUPPORT                               0x12
#define AWTO_PNL_BY_OSD_SOURCE                                  0x13
#define AWTO_PNL_BY_OSD_PS                                      0x14
#define AWTO_PNL_BY_OSD_DPINFO                                  0x15
#define AWTO_PNL_BY_FREESYNC_OD                                 0x16
#define AWTO_PNL_BY_USER_AC_OFF                                 0x17    // RTD2014UserInterface power switch
#define AWTO_PNL_BY_USER_OFF                                    0x18
#define AWTO_PNL_BY_USER_PS                                     0x19
#define AWTO_PNL_BY_KEY_CONSOLE                                 0x1A    // UP+DOWN wake into the console (#132)
#define AWTO_PWM_DARK                                           ((_BACKLIGHT_PWM_INVERSE == _ON) ? 0xFF : 0x00)    // 8-bit duty (_PWM_DUT_RESOLUTION) with the backlight dark
extern __xdata unsigned char g_ucAwtoPanelOwn;     // 1 while the panel machine drives its pins (AwtoPanelPinLog flags other writers)
extern void UserCommonInterfacePanelPowerTick(void);
extern bit UserCommonInterfacePanelPowerDown(bit bDown, bit bUp);
extern void UserCommonInterfacePanelPwm(unsigned int usDuty);
extern void AwtoPanelForeign(unsigned char ucWhat);
extern void UserCommonInterfacePanelBoot(unsigned char ucWarm);
// #162 step 3 system machine (SysJudge.c): one state for power status + mode, one request entry (SysMachineRequest), one driver.
// The SDK views (power status / target, mode state / reset target) are written there only (gate sysm). docs/design-162.md.
#define AWTO_SYS_AC_ON                                          0       // boot: power AC_ON, mode POWER OFF
#define AWTO_SYS_OFF                                            1
#define AWTO_SYS_INITIAL                                        2       // power NORMAL, one pass before the search
#define AWTO_SYS_SEARCH                                         3
#define AWTO_SYS_DISPLAY                                        4       // display setting
#define AWTO_SYS_ACTIVE                                         5
#define AWTO_SYS_FAST                                           6       // mode ACTIVE: cached switch / fast wake in flight (AwtoSwFastPoll)
#define AWTO_SYS_HOLD                                           7       // mode ACTIVE: signal lost, L1 hold (backlight off, set-up kept)
#define AWTO_SYS_NOSUPPORT                                      8
#define AWTO_SYS_NOSIGNAL                                       9
#define AWTO_SYS_SAVING                                         10      // power SAVING (or fake saving), mode POWER SAVING
#define AWTO_SYS_WAKE                                           11      // power NORMAL after a wake, mode still POWER SAVING: search
#define AWTO_SYS_DOWN                                           12      // OFF / SAVING requested: panel down first (T4, T5), mode kept
#define AWTO_SYS_STATES                                         13      // state count (and "no state")
#define AWTO_SYS_REQ_MODE                                       0x10    // request = AWTO_SYS_REQ_MODE | EnumModeAction; power = EnumPowerStatus
#define AWTO_SYS_REQ_FAST                                       0x20    // fast path taken (ACTIVE / HOLD -> FAST)
#define AWTO_SYS_REQ_HOLD                                       0x21    // fast wake failed (FAST -> HOLD)
#define AWTO_SYS_REQ_ACTIVE                                     0x22    // fast path unblanked (FAST -> ACTIVE)
#define AWTO_SYS_BY_KEY                                         0x01    // who / why codes: texts in fw/awto/sync.tsv id 16
#define AWTO_SYS_BY_KEY_WAKE                                    0x02
#define AWTO_SYS_BY_TESTCMD                                     0x03
#define AWTO_SYS_BY_VCP                                         0x04
#define AWTO_SYS_BY_INPUT                                       0x05
#define AWTO_SYS_BY_SELECTOR                                    0x06
#define AWTO_SYS_BY_DEADPORT                                    0x07
#define AWTO_SYS_BY_WAKEPOLL                                    0x08
#define AWTO_SYS_BY_SDK_DETECT                                  0x09
#define AWTO_SYS_BY_CABLE                                       0x0A
#define AWTO_SYS_BY_OSD_PS                                      0x0B
#define AWTO_SYS_BY_SETTINGS                                    0x0C
#define AWTO_SYS_BY_SDK_OSD                                     0x0D
#define AWTO_SYS_BY_HOLD                                        0x0E
#define AWTO_SYS_BY_HOLD_BACK                                   0x0F
#define AWTO_SYS_BY_FAST                                        0x10
#define AWTO_SYS_BY_FAST_DONE                                   0x11
#define AWTO_SYS_BY_FAST_FAIL                                   0x12
#define AWTO_SYS_BY_FAST_RETRY                                  0x13
#define AWTO_SYS_BY_TIMER_NOSIGNAL                              0x14
#define AWTO_SYS_BY_TIMER_NOSUPPORT                             0x15
#define AWTO_SYS_BY_NVRAM                                       0x16
#define AWTO_SYS_BY_SDK                                         0x17
#define AWTO_SYS_BY_WAKE_EMPTY                                  0x18
#define AWTO_SYS_BY_DIRECT                                      0x19    // power target found without a request (host / sim poke)
#define AWTO_SYS_BY_HOLD_TRIES                                  0x1A    // hold released: fast wakes used up (BY_HOLD = L2 time)
#define AWTO_SYS_BY_HOLD_AUTO                                   0x1B    // hold released: auto search, another cable
#define AWTO_SYS_BY_KEY_AUTO                                    0x1C    // AUTO with nothing open: auto source select (#132)
#define AWTO_SYS_BY_KEY_CONSOLE                                 0x1D    // UP+DOWN in power saving: wake into the console (#132)
#define AWTO_SYS_BY_SELECTOR_IDLE                               0x1E    // selector: highlighted input taken after AWTO_SRC_IDLE_COMMIT_MS (#132)
#define AWTO_SYS_BY_SELECTOR_RESET                              0x1F    // selector closed by the SDK OSD reset: its highlighted choice taken (#132)
#define AWTO_SYS_WHY_INITIAL                                    0x21
#define AWTO_SYS_WHY_TIMING                                     0x22
#define AWTO_SYS_WHY_NO_SOURCE                                  0x24
#define AWTO_SYS_WHY_READY                                      0x25
#define AWTO_SYS_WHY_UNSTABLE                                   0x26    // 0x26..0x2A: SysMachineCheck reasons, in its order
#define AWTO_SYS_WHY_HV                                         0x27
#define AWTO_SYS_WHY_INTERLACE                                  0x28
#define AWTO_SYS_WHY_MEMORY                                     0x29
#define AWTO_SYS_WHY_EDP                                        0x2A
#define AWTO_SYS_WHY_HOLD                                       0x2B
#define AWTO_SYS_WHY_PANEL_DOWN                                 0x2C
#define AWTO_SYS_WHY_CALLED_OFF                                 0x2D
#define AWTO_SYS_WHY_BOOT                                       0x2E    // SysMachineInit: the RESET -> AC ON line
#define AWTO_SYS_WHY_CODE                                       0x3F    // why byte: code bits; 0x40 / 0x80 flags
#define AWTO_SYS_WHY_AT                                         0x40    // SysMachineGo: line only, before the action; the next Go applies it
#define AWTO_SYS_WHY_MODE                                       0x80    // in the ring: the SDK mode changed (line gets the mode text, sync.tsv 1A)
#define AWTO_SYS_OK                                             0       // request outcomes (sync.tsv id 18)
#define AWTO_SYS_ALREADY                                        1
#define AWTO_SYS_REPLACES                                       2
#define AWTO_SYS_REFUSED                                        3
#define AWTO_SYS_KEPT                                           4       // kept until the state can take it
#define AWTO_SYS_DROPPED                                        5       // pending search reset dropped: the no-signal search confirmed a timing first (#132)
#define AWTO_SYS_MS_MAX                                         0xFFFFFFUL     // transition line: ms in the old state, 24 bits (4.6 h)
#define AWTO_SW_EV_SYS                                          0x13    // transition: arg old << 4 | new; ring value why << 24 | ms in old
#define AWTO_SW_EV_SYS_REQ                                      0x14    // request: arg request; ring value who << 8 | outcome
#define AWTO_SYNC_EV_SYS_STATE                                  0x15    // sync.tsv name tables for the sys / sysreq fmts (never pushed)
#define AWTO_SYNC_EV_SYS_WHY                                    0x16
#define AWTO_SYNC_EV_SYS_REQNAME                                0x17
#define AWTO_SYNC_EV_SYS_OUTCOME                                0x18
#define AWTO_SYNC_EV_SYS_SEP                                    0x19    // separators of the two line formats (no string literals in that TU)
#define AWTO_SYNC_EV_SYS_MODE                                   0x1A    // mode text per system state (sys fmt, why bit 7)
#define AWTO_SYNC_EV_PNL_BY                                     0x1B    // panel requester names (pby fmt)
extern volatile __xdata unsigned char g_ucAwtoSysOwn;       // 1 while the machine writes the SDK power / mode views (gate sysm) or pushes a transition line
extern void SysMachineInit(void);
extern void SysMachineHandler(void);
extern void SysMachineWork(void);
extern void SysMachineRequest(unsigned char ucReq, unsigned char ucBy);
// D1 DPCD default: SDK OSD default is DP 1.1 = HBR max (4K60 pruned by the host); vendor runs 4K60 over DP = HBR2 (#28)
#define _AWTO_DP_D1_VERSION                                     _DP_VER_1_DOT_2
#define _AWTO_INFO_POPUP_SEC                                    6       // input-info pop-up on-screen time (SDK: 3)
#define _CHECKSUM                                               0xA3    // awto NVRAM layout id; change = defaults reload (SDK 0x1A)


/////////////
// General //
/////////////

//--------------------------------------------------
// Pcb Option
//--------------------------------------------------
#define _PCB_TYPE                                               _RL6449_AWTO_JXC4K  // 216-pin; live pinshare (#7)

//--------------------------------------------------
// Panel Option
//--------------------------------------------------
#define _PANEL_TYPE                                             _AWTO_M280DCA_E3B
#define _PANEL_POW_SEQ_FAST_MODE                                _ON

//--------------------------------------------------
// Osd Option
//--------------------------------------------------
#define _OSD_TYPE                                               _REALTEK_2014_OSD

#define _OSD_INCLUDE                                            "RTD2014Include.h"
#define _USER_FUNCTION_INCLUDE                                  "RTD2014UserInclude.h"
#define _USER_TIMER_INCLUDE                                     "RTD2014TimerInclude.h"
#define _FACTORY_INCLUDE                                        "RTDFactoryInclude.h"
#define _USER_HWIIC_INCLUDE                                     "RTD2014HWIICInclude.h"

//--------------------------------------------------
// OSD Window & Font Align to DEN Option
//--------------------------------------------------
#define _OSD_POSITION_OFFSET_CORRECTION                         _ON

//--------------------------------------------------
// OSD Position Align Option
//--------------------------------------------------
#define _OSD_POSITION_SELF_ALIGNMENT                            _ON


///////////
// DDCCI //
///////////

//-------------------------------------------------
// DDCCI Option
//-------------------------------------------------
#define _DDCCI_RXBUF_LENGTH                                     16
#define _DDCCI_TXBUF_LENGTH                                     16
#define _DDCCI_TIMEOUT_LIMIT                                    50 // 0~65535ms

#define _CAPABILITIES_STRING_VGA                                "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 0E 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 1E 1F 20 30 3E 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_DVI                                "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_HDMI                               "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"
#define _CAPABILITIES_STRING_DP                                 "(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02 04 05 06 08 0B 0C 10 12 14(01 02 04 05 06 08 0B) 16 18 1A 52 60(01 03 04 0F 10 11 12) 87 AC AE B2 B6 C6 C8 CA CC(01 02 03 04 06 0A 0D) D6(01 04 05) DF FD FF)mswhql(1)asset_eep(40)mccs_ver(2.2))"


/////////////////////
// Display Setting //
/////////////////////

//-------------------------------------------------
// Embedded Memory Size Option
//-------------------------------------------------
#define _EMBEDDED_MEMORY_SIZE_CONFIG                            _16M_16BIT_DDR2_2PCS
#define _DDR2_MEMORY_CLK_1200M_SUPPORT                          _ON     // vendor fw: DDR PLL 1200000 kHz (bank2 F9B7) + 1200M PHY timings (#26)

//-------------------------------------------------
// OD Option
//-------------------------------------------------
#define _OD_SUPPORT                                             _OFF

//-------------------------------------------------
// FRC Option
//-------------------------------------------------
// FRC: off by default (#8); K2S_SDCC_EXTRA=-D_AWTO_FRC turns it on (4K60 work, #26)
#ifdef _AWTO_FRC
#define _FRC_SUPPORT                                            _ON
#else
#define _FRC_SUPPORT                                            _OFF
#endif

//-------------------------------------------------
// Display Rotation Option
//-------------------------------------------------
#define _DISPLAY_ROTATION_SUPPORT                               _OFF

//--------------------------------------------------
// Aspect Ratio Option
//--------------------------------------------------
#define _ASPECT_RATIO_SUPPORT                                   _ON
#define _ASPECT_ORIGINAL_MODE_SUPPORT                           _ON

//--------------------------------------------------
// Overscan Option
//--------------------------------------------------
#define _OVERSCAN_VGA_SUPPORT                                   _OFF
#define _OVERSCAN_DVI_SUPPORT                                   _ON
#define _OVERSCAN_HDMI_SUPPORT                                  _ON
#define _OVERSCAN_DP_SUPPORT                                    _ON

#define _OVERSCAN_H_RATIO                                       30
#define _OVERSCAN_V_RATIO                                       30

//-------------------------------------------------
// Adjust H & V Position Max Range Option
//-------------------------------------------------
#define _MAX_H_POSITION_RANGE                                   100 // Pixel
#define _MAX_V_POSITION_RANGE                                   100 // Line


////////////////////
// Color Function //
////////////////////

//--------------------------------------------------
// Digital Functional Option
//--------------------------------------------------
#define _I_DITHER_SUPPORT                                       _ON
#define _D_DITHER_SUPPORT                                       _ON
#define _GAMMA_FUNCTION                                         _ON
#define _COLOR_FORMAT_CONVERT                                   _ON
#define _RGB_QUANTIZATION_RANGE_SUPPORT                         _ON
#define _YCC_QUANTIZATION_RANGE_SUPPORT                         _ON
#define _ULTRA_VIVID_SUPPORT                                    _OFF
#define _DCR_SUPPORT                                            _OFF
#define _DCC_FUNCTION                                           _OFF
#define _DCC_HISTOGRM_INFO                                      _OFF
#define _ICM_SUPPORT                                            _OFF
#define _ICM_BRI_SUPPORT                                        _OFF
#define _SCM_SUPPORT                                            _OFF
#define _SIX_COLOR_SUPPORT                                      _OFF
#define _HIGHLIGHT_WINDOW_SUPPORT                               _OFF
#define _RINGING_FILTER_SUPPORT                                 _OFF
#define _SHARPNESS_SUPPORT                                      _OFF
#define _CONTRAST_SUPPORT                                       _ON
#define _BRIGHTNESS_SUPPORT                                     _ON

//-------------------------------------------------
// Hue and Saturation Option
//-------------------------------------------------
#define _GLOBAL_HUE_SATURATION                                  _OFF

#define _HUE_MAX                                                230
#define _HUE_MIN                                                30
#define _SATURATION_MAX                                         200
#define _SATURATION_MIN                                         0

//-------------------------------------------------
// IAPS Option
//-------------------------------------------------
#define _IAPS_SUPPORT                                           _OFF


////////////////////////////////////////
// Off-Line Display Color Calibration //
////////////////////////////////////////

//-------------------------------------------------
// PCM (Load Code Table) Option
//-------------------------------------------------
#define _PCM_FUNCTION                                           _OFF

//-------------------------------------------------
// 3D Gamma (Load Code Table) Option
//-------------------------------------------------
#define _RGB_3D_GAMMA                                           _OFF

////////////////////////////////////////
// On-Line Display Color Calibration //
////////////////////////////////////////

//-------------------------------------------------
// OGC and OCC (On-Line Calibration) Option
//-------------------------------------------------
#define _OCC_SUPPORT                                            _OFF
#define _OGC_SUPPORT                                            _OFF
#define _OGC_DICOM_SUPPORT                                      _OFF
#define _TWO_BRI_CALIBRATION_TYPE                               _TWO_BRI_CALIBRATION_NONE

#define _OGC_TOTAL_GAMMA                                        5 // 1/2/3/4/5/6
#define _OGC_TOTAL_CT                                           6
#define _OGC_FLASH_BANK                                         14

//-------------------------------------------------
// FreesyncII Option
//-------------------------------------------------
#define _FREESYNC_II_FLASH_BANK                                 13
#define _FREESYNC_II_FLASH_PAGE                                 0

//-------------------------------------------------
// Uniformity (On-Line Calibration) Option
//-------------------------------------------------
#define _UNIFORMITY_SUPPORT                                     _OFF

#define _UNIFORMITY_FLASH_BANK0                                 29

#define _UNIFORMITY_1ST_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_2ND_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_3RD_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_4TH_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_5TH_TABLE_LEVEL                             _UNIFORMITY_NONE
#define _UNIFORMITY_6TH_TABLE_LEVEL                             _UNIFORMITY_NONE

//-------------------------------------------------
// Dimming Option
//-------------------------------------------------
#define _LOCAL_DIMMING_SUPPORT                                  _OFF
#define _GLOBAL_DIMMING_SUPPORT                                 _OFF

#define _DISPLAY_HDR_VERSION                                    _DISPLAY_HDR_VERSION_1_0

////////////
// Eeprom //
////////////

//-------------------------------------------------
// Eeprom Access Function Option
//-------------------------------------------------

//-------------------------------------------------
// System Eeprom Start Address for Kernel Data Option
//-------------------------------------------------
#define _EEPROM_KERNEL_START_ADDRESS                            (_EEPROM_PAGE0_BANK0)


///////////
// Flash //
///////////

//-------------------------------------------------
// Flash Clock Option
//-------------------------------------------------
#define _FLASH_CLK_SPEED                                        _FLASH_FAST_SPEED

//-------------------------------------------------
// Flash Access Function Option
//-------------------------------------------------
#define _FLASH_WRITE_FUNCTION_SUPPORT                           _ON
#define _FLASH_READ_FUNCTION_SUPPORT                            _ON

#define _FLASH_TYPE_W25X20A_OR_W25X21CL                         _FLASH_W25X20A
#define _FLASH_TYPE_W25X40CL_OR_W25X41CL                        _FLASH_W25X40CL
#define _FLASH_TYPE_GD25Q16C_OR_GD25Q16                         _FLASH_GD25Q16C
#define _FLASH_TYPE_MX25L3206E_OR_MX25L3233F_OR_KH25L3236F      _FLASH_MX25L3233F
#define _FLASH_TYPE_GD25Q40B_OR_GD25Q41B                        _FLASH_GD25Q41B
#define _FLASH_TYPE_W25Q16DV_OR_W25Q16JVSIQ                     _FLASH_W25Q16JVSIQ
#define _FLASH_TYPE_FM25Q08_OR_FM25Q08A                         _FLASH_FM25Q08A
#define _FLASH_TYPE_BY25D40C_OR_BY25D40ASTIG                    _FLASH_BY25D40C
#define _FLASH_TYPE_W25Q32F_OR_W25Q32JVSSIQ                     _FLASH_W25Q32F
#define _FLASH_TYPE_BY25D80ASTIG_OR_BY25Q80BSTIG                _FLASH_BY25D80ASTIG

#define _FLASH_EWSR_FUNCTION_SUPPORT                            _OFF

//-------------------------------------------------
// EEPROM Emulation Option
//-------------------------------------------------
#define _SYSTEM_EEPROM_EMULATION_SUPPORT                        _ON

#define _SYSTEM_EEPROM_EMULATION_FLASH_BANK                     15
#define _SYSTEM_EEPROM_EMULATION_START_PAGE                     11
#define _SYSTEM_EEPROM_EMULATION_END_PAGE                       12
#define _START_OF_PAGEID                                        _PAGEID_0
#define _END_OF_PAGEID                                          _PAGEID_0
#define _CHECKSUM_VERSIONCODE_ID                                _PAGEID_0


//////////
// EDID //
//////////

//-------------------------------------------------
// EDID Location Option
//-------------------------------------------------
#define _EDID_ADDRESS_EEPROM                                    (_EEPROM_PAGE7_BANK0)
#define _EDID_ADDRESS_FLASH                                     0
#define _EDID_FLASH_BANK                                        9
#define _EDID_HDR10_AUTO_SWITCH                                 _OFF


//////////////
// HDCP Key //
//////////////

// awto: HDCP parked (#44). _OFF = no key tables in the image, no key load, HDCP DDC slave / DPCD Bcaps not advertised
#ifndef _AWTO_HDCP
#define _AWTO_HDCP                                              _OFF
#endif

//-------------------------------------------------
// HDCP Key Location Option
//-------------------------------------------------
#define _HDCP_1_4_KEY_LOCATION                                  _TABLE_LOCATION_CODE
#define _HDCP_2_2_KEY_LOCATION                                  _TABLE_LOCATION_CODE

//-------------------------------------------------
// For HDCP 1.4 Rx Key (FW Size : 325 Bytes ; Tool Size : 376 Bytes)
//-------------------------------------------------
#define _RX_HDCP_1_4_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE2_BANK1)
#define _RX_HDCP_1_4_KEY_ADDRESS_FLASH                          0
#define _RX_HDCP_1_4_KEY_FLASH_BANK                             8

//-------------------------------------------------
// For HDCP 2.2 Rx Key (FW Size : 1118 Bytes ; Tool Size : 1120 Bytes)
//-------------------------------------------------
#define _RX_HDCP_2_2_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE6_BANK0)
#define _RX_HDCP_2_2_KEY_ADDRESS_FLASH                          0
#define _RX_HDCP_2_2_KEY_FLASH_BANK                             15

//-------------------------------------------------
// For HDCP 1.4 Tx Key (FW Size : 325 Bytes ; Tool Size : 376 Bytes)
//-------------------------------------------------
#define _TX_HDCP_1_4_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE4_BANK0)
#define _TX_HDCP_1_4_KEY_ADDRESS_FLASH                          0x180
#define _TX_HDCP_1_4_KEY_FLASH_BANK                             8

//-------------------------------------------------
// For HDCP 2.2 Tx Key (FW Size : 900 Bytes ; Tool Size : 935 Bytes)
//-------------------------------------------------
#define _TX_HDCP_2_2_KEY_ADDRESS_EEPROM                         (_EEPROM_PAGE8_BANK0)
#define _TX_HDCP_2_2_KEY_ADDRESS_FLASH                          0x180
#define _TX_HDCP_2_2_KEY_FLASH_BANK                             15


///////////////////
// System Source //
///////////////////

//-------------------------------------------------
// System Auto Search Style Option
//-------------------------------------------------
#define _SOURCE_AUTO_SEARCH_STYLE                               _SOURCE_POLLING_IN_SEARCH_STATE

//-------------------------------------------------
// System Source Search Time Option
//-------------------------------------------------
#define _SOURCE_DEFAULT_SEARCH_TIME_VGA                         SEC(0.5)
#define _SOURCE_DEFAULT_SEARCH_TIME_HDMI                        SEC(2)
#define _SOURCE_DEFAULT_SEARCH_TIME_DVI                         SEC(2)
#define _SOURCE_DEFAULT_SEARCH_TIME_DP                          SEC(3)
#define _SOURCE_DEFAULT_SEARCH_TIME_TYPE_C                      SEC(4.5)


//////////////////
// System Judge //
//////////////////

//-------------------------------------------------
// System Display Setting Check Time Option
//-------------------------------------------------
#define _WAIT_TIME_TO_ACTIVE_VGA                                SEC(0.05)
#define _WAIT_TIME_TO_ACTIVE_DVI                                SEC(0.1)
#define _WAIT_TIME_TO_ACTIVE_HDMI                               SEC(0.1)
#define _WAIT_TIME_TO_ACTIVE_DP                                 SEC(0.1)

//--------------------------------------------------
// System Support Timing Option
//--------------------------------------------------
#define _OOR_H_FREQ_UPPER_BOUND                                 2200 // Unit in 0.1 kHZ
#define _OOR_H_FREQ_LOWER_BOUND                                 100  // Unit in 0.1 kHZ
#define _OOR_V_FREQ_UPPER_BOUND                                 1500 // Unit in 0.1 HZ
#define _OOR_V_FREQ_LOWER_BOUND                                 230  // Unit in 0.1 HZ
#define _OOR_H_WIDTH_UPPER_BOUND                                4096 // Unit in pixel
#define _OOR_V_HEIGHT_LOWER_BOUND                               240  // Unit in line

#define _FAIL_SAVE_H_FREQ_UPPER_BOUND                           2200 // Unit in 0.1 kHZ
#define _FAIL_SAVE_H_FREQ_LOWER_BOUND                           110  // Unit in 0.1 kHZ
#define _FAIL_SAVE_V_FREQ_UPPER_BOUND                           1500 // Unit in 0.1 HZ
#define _FAIL_SAVE_V_FREQ_LOWER_BOUND                           230  // Unit in 0.1 HZ

#define _INPUTCLOCK_RANG_VGA                                    2100 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_DVI                                    6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_HDMI                                   6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_DP                                     6000 // Unit in 0.1 MHz
#define _INPUTCLOCK_RANG_USBC                                   6000 // Unit in 0.1 MHz


/////////
// VGA //
/////////

//--------------------------------------------------
// VGA YPBPR Option
//--------------------------------------------------
#define _YPBPR_SUPPORT                                          _OFF
#define _SOG_SUPPORT                                            _OFF
#define _VGA_COMPOSITE_SUPPORT                                  _OFF

//--------------------------------------------------
// VGA Mode Search condition reference by picture width Option
//--------------------------------------------------
#define _MODE_SEARCH_BY_ACTIVE_MEASURE_SUPPORT                  _OFF

//--------------------------------------------------
// VGA Auto Adjust Clock Setup Option
//--------------------------------------------------
#define _AUTO_CLOCK_STEP                                        2  // 1 or 2
#define _AUTO_CLOCK_RANGE                                       95 // Set Clock Non-adjusting Range (%) by the active region
#define _AUTO_TOLERANCE_PIXEL                                   2  // Definitions Of tolerance pixel for Auto Clock
#define _AUTO_CLOCK_SAVE_VALUE_OPTION                           _CLOCK_SAVE_PERCENT_VALUE

//--------------------------------------------------
// VGA Gain & Offset Defualt Option
//--------------------------------------------------
#define _ADC_RGB_DEFAULT_RED_GAIN                               128
#define _ADC_RGB_DEFAULT_GREEN_GAIN                             128
#define _ADC_RGB_DEFAULT_BLUE_GAIN                              128
#define _ADC_RGB_DEFAULT_RED_OFFSET                             128
#define _ADC_RGB_DEFAULT_GREEN_OFFSET                           128
#define _ADC_RGB_DEFAULT_BLUE_OFFSET                            128

#define _ADC_YPBPR_DEFAULT_Y_GAIN                               159
#define _ADC_YPBPR_DEFAULT_PB_GAIN                              154
#define _ADC_YPBPR_DEFAULT_PR_GAIN                              154
#define _ADC_YPBPR_DEFAULT_Y_OFFSET                             112
#define _ADC_YPBPR_DEFAULT_PB_OFFSET                            128
#define _ADC_YPBPR_DEFAULT_PR_OFFSET                            128

//--------------------------------------------------
// VGA Self-Calibration Option
//--------------------------------------------------
#define _ADC_SELF_CALIBRATION                                   _OFF

#define _CALIBRATION_R_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_G_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_B_GAIN_BIAS                                (0)  // Needs modification for EVERY single source
#define _CALIBRATION_R_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source
#define _CALIBRATION_G_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source
#define _CALIBRATION_B_OFFSET_BIAS                              (-3) // Needs modification for EVERY single source

//--------------------------------------------------
// VGA YPBPR Auto Color Method Option
//--------------------------------------------------
#define _YPBPR_AUTO_METHOD                                      _YPBPR_AUTO_BY_SOURCE

#define _AUTO_PB_GAIN_BIAS                                      (5)
#define _AUTO_PR_GAIN_BIAS                                      (5)
#define _AUTO_Y_GAIN_BIAS                                       (0)
#define _AUTO_PB_OFFSET_BIAS                                    (-8)
#define _AUTO_PR_OFFSET_BIAS                                    (-8)
#define _AUTO_Y_OFFSET_BIAS                                     (-16)

//--------------------------------------------------
// VGA Digital Filter Option
//--------------------------------------------------
#define _DIG_FILTER_NSMEAR_ENABLE                               _ENABLE
#define _DIG_FILTER_PSMEAR_ENABLE                               _ENABLE
#define _DIG_FILTER_NRING_ENABLE                                _ENABLE
#define _DIG_FILTER_PRING_ENABLE                                _ENABLE
#define _DIG_FILTER_EXTENSION_ENABLE                            _ENABLE
#define _DIG_FILTER_ENHANCE_PHASE_ENABLE                        _ENABLE


////////////////
// DVI & HDMI //
////////////////

//--------------------------------------------------
// DVI & HDMI Option
//--------------------------------------------------
#define _DVI_DE_ONLY_SUPPORT                                    _OFF
#define _HDMI_FROM_DVI_CONNECT                                  _ON
#define _HDMI_FREESYNC_SUPPORT                                  _OFF
#define _HDMI_HDR10_SUPPORT                                     _OFF
#define _HDMI_FREESYNC_II_SUPPORT                               _OFF
#define _TMDS_HDCP_2_2_SUPPORT                                  _OFF

//--------------------------------------------------
// HDMI CTS Option
//--------------------------------------------------
#define _TMDS_HDCP_FEATURE                                      _HDCP_FEATURE_BY_INPUT
#define _TMDS_Z0_POWER_SAVING_OPTION                            _ALL_CHANNEL_CONNECTED_FOR_CTS


////////
// DP //
////////

//-------------------------------------------------
// DP Capability Option
//-------------------------------------------------
#define _DP_MST_SUPPORT                                         _OFF
#define _DP_TX_SUPPORT                                          _OFF
#define _DP_FREESYNC_SUPPORT                                    _OFF
#define _DP_FREESYNC_II_SUPPORT                                 _OFF
#define _DP_HDR10_SUPPORT                                       _OFF
#define _DP_HDCP_2_2_SUPPORT                                    _OFF

#if((_AWTO_HDCP == _OFF) && ((_TMDS_HDCP_2_2_SUPPORT == _ON) || (_DP_HDCP_2_2_SUPPORT == _ON)))
#error "HDCP 2.2 needs _AWTO_HDCP _ON (#44)"
#endif


/////////
// MHL //
/////////

//--------------------------------------------------
// MHL2.x Option
//--------------------------------------------------
#define _MHL_CBUS_CTS_MODE                                      _OFF
#define _MHL2_UCP_SUPPORT                                       _OFF
#define _MHL2_AUD_CHANNEL                                       _MHL_AUD_2CH
#define _MHL2_ADOPTER_ID                                        0x0000
#define _MHL2_DEVICE_ID                                         0x0000
#define _MHL2_PP_MODE_SUPPORT                                   _OFF


///////////
// Audio //
///////////

//-------------------------------------------------
// Audio Option
//-------------------------------------------------
#define _AUDIO_SUPPORT                                          _ON  // digital HDMI/DP audio -> embedded DAC (docs/audio.md, #93); _AWTO_AUDIO_TEST adds the sine

//-------------------------------------------------
// Audio DAC Option
//-------------------------------------------------
#define _EMBEDDED_DAC_SUPPORT                                   _ON
#define _DAC_SPEAKER_OUTPUT_SWAP                                _ON  // Dahua fw: REG_MUX_ANA_OUT = 0x50 (aout L/R swapped), docs/audio.md [fw]

//-------------------------------------------------
// Audio Line In Option
//-------------------------------------------------
#define _LINE_IN_SUPPORT                                        _OFF

#define _LINE_IN_DAC_AOUT_GAIN_DB                               _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _LINE_IN_DAC_HPOUT_GAIN_DB                              _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _LINE_IN_BOOST_GAIN_DB                                  0x17                        // 0dB, 1.5dB for each step, Max Gain: 0x3F(30dB)
#define _LINE_IN_VOLUME_MAX                                     0x3FFF                      // MAX: 0x3FFF
#define _LINE_IN_VOLUME_MIN                                     0x0000

//-------------------------------------------------
// Audio Digital Option
//-------------------------------------------------
#define _DIGITAL_DAC_AOUT_GAIN_DB                               _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _DIGITAL_DAC_HPOUT_GAIN_DB                              _AUDIO_DAC_OUTPUT_GAIN_0_DB // 0dB, 1.5dB for each step, Max Gain: 'b111(10.5dB)
#define _DIGITAL_VOLUME_MAX                                     0x3FFF                      // MAX: 0x3FFF
#define _DIGITAL_VOLUME_MIN                                     0x0000

//-------------------------------------------------
// Audio PS Option
//-------------------------------------------------
#define _SLEEP_AUDIO_SUPPORT                                    _OFF

#define _PS_AUDIO_INPUT                                         _PS_AUDIO_LINE_IN


///////////////////
// Misc Function //
///////////////////

//-------------------------------------------------
// Instant Timer Events Option
//-------------------------------------------------
#define _INSTANT_TIMER_EVENT_0                                  _OFF    // awto #144: Timer0 only faded the boot logo in
#define _INSTANT_TIMER_EVENT_1                                  _OFF

//--------------------------------------------------
// IRDA Option
//--------------------------------------------------
#define _IR_SUPPORT                                             _IR_OFF

#endif // End of #if(_PROJECT == _RL6410_PROJECT)

