# wdt (#131, docs/watchdog.md): main-loop watchdog + crash canary. Check in the Timer2 ISR (AWTO_DIAG_T2ISR, RL6449_Project.h),
# record g_stAwtoWdt at 0xF6B0, functions fw/sdcc/awto_wdt.inc (SysMain.c), console panel fw/sdcc/awto_wdtpop.inc.
# Feeds in the SDK's bounded waits are same-line SUBS: no SDK line moves (fw/warn_policy.tsv is keyed by line).
from pathlib import Path

_SHIM = Path(__file__).resolve().parents[2] / "sdcc"
OSD = "User/RTD Series/RTD2014Osd/Code/"
TMR = "Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonTimerFunction.c"
WRAPS = []
INSERTS = [
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (_SHIM / "awto_wdt.inc").read_text().rstrip("\n")),
    ("Kernel/System/Code/SysMain.c", r"^\s*do$", "    AwtoWdtInit();", r"^void main\(void\)$"),     # once per reset, before EA
    (OSD + "RTD2014OsdDisplay.c", r"^#endif//#if\(_OSD_TYPE == _REALTEK_2014_OSD\)$", (_SHIM / "awto_wdtpop.inc").read_text().rstrip("\n")),
]


def _feed(site):
    return lambda m: m.group(1) + f" AWTO_WDT_FEED({site});  // [keil2sdcc] sub #131"


_NV_SITES = iter(("AWTO_WDT_S_WREN", "AWTO_WDT_S_WRDIS", "AWTO_WDT_S_WRPROT"))   # file order of the SDK's flash pokes


SUBS = [
    # #138: a watchdog is never off. The SDK's boot 'disable' clears FFEA[7] only, a no-op: FFE9[7] and FF3A[6] (ORed enables,
    # reset 1) keep it on. Line removed (compiled out here anyway, _FLASH_PARTITION_NONE); N is set at startup (crt_rtd_startup)
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c",
     r"// Disable watchdog timer\n    MCU_FFEA_WATCHDOG_TIMER &= ~\(_BIT7\);",
     "// awto #138: no watchdog disable (three ORed enables; never cleared)\n"
     "  // [keil2sdcc] sub #138", 1),
    # one feed per elapsed ms inside each bounded wait: the wait itself is not a hang (its bound is the SDK's)
    (TMR, r"(void ScalerTimerDelayXms\(WORD usNum\)\n\{.*?g_bNotifyTimer2Int = _FALSE;\n.*?g_bNotifyTimer2Int = _FALSE;)", _feed("AWTO_WDT_S_DELAY"), 1),
    (TMR, r"(bit ScalerTimerPollingFlagProc\(WORD usTimeout, WORD usRegister, BYTE ucBit, bit bSuccess\)\n\{.*?usTimeElapsed\+\+;)", _feed("AWTO_WDT_S_POLL"), 1),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerTimerFunction.c",
     r"(bit ScalerTimerWaitForEvent\(EnumWaitEventType enumEvent\)\n\{.*?usTimeElapsed\+\+;)", _feed("AWTO_WDT_S_EVENT"), 1),
    # #138: WD-timer events -> Timer0 (fw/sdcc/awto_t0ev.inc, same function names; call sites unchanged). SDK block off,
    # its table gone, ours appended at the end of the file: no line before it moves.
    (TMR, r"#if\(_WD_TIMER_INT_SUPPORT == _ON\)(\n//-+\n// Description  : Watch Dog Timer Initial)",
     r"#if 0  // [keil2sdcc] sub #138: WD-timer functions in fw/sdcc/awto_t0ev.inc\1", 1),
    (TMR, r"StructWDTimerEventType g_pstWDTimerEvent\[_WD_TIMER_EVENT_COUNT\];",
     "// awto #138: event table in awto_t0ev.inc  // [keil2sdcc] sub", 1),
    (TMR, r"(    ScalerTimerDelayXms\(ScalerTimerGetEventRemainTime\(enumEventID\)\);\n    ScalerTimerCancelTimerEvent\(enumEventID\);\n\}\n)",
     lambda m: m.group(1) + (_SHIM / "awto_t0ev.inc").read_text(), 1),
    # every Timer2 reload (MCU clock switch): restart the pending Timer0 tick at the new clock
    (TMR, r"(    // Run Timer2\n    TR2 = _ON;)", lambda m: m.group(1) + " AwtoT0EvClock();  // [keil2sdcc] sub #138", 1),
    ("Kernel/System/Code/SysTimer.c",
     r"(void SysTimerIntProc0\(void\)[^\n]*\n\{\n    // Backup for Burst Write Bug\n    g_ucBackup_TIMER0 = MCU_FFF4_SCA_INF_ADDR;)",
     lambda m: m.group(1) + " AwtoT0EvIsr();  // [keil2sdcc] sub #138", 1),
    # #138 task 3: one hardware watchdog. The 1 ms tick does no watchdog work (latch + 'Prevent INT Lock Reset' clear gone);
    # the WD IRQ is the warning (capture); the SDK's flash-op pokes become ours. Blank lines keep the SDK line numbers.
    ("Kernel/System/Code/SysTimer.c",
     r"    // Latch Current Counter and not clear any WD timer counter\n.*?\n        CLR_MCU_WATCH_DOG\(\);\n    \}\n",
     lambda m: "    // [keil2sdcc] sub #138: no watchdog work in the 1 ms tick" + "\n" * m.group(0).count("\n"), 1),
    ("Kernel/System/Code/SysTimer.c", r"    ScalerTimerWDEventProc_WDINT\(\);",
     "    AWTO_WDT_IRQ();  // [keil2sdcc] sub #138: watchdog warning (capture + reset)", 1),
    # #29 boot log: the WDT counter is the clock before Timer2; carry it over ScalerMcuInitial's clear
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMcu.c", r"    MCU_FFEA_WATCHDOG_TIMER \|= _BIT6 \| _BIT2 \| _BIT1 \| _BIT0;",
     "    AWTO_SYNC_MARK(); MCU_FFEA_WATCHDOG_TIMER |= _BIT6 | _BIT2 | _BIT1 | _BIT0;  // [keil2sdcc] sub #29", 1),
    # #150: NVRAM save timing in the sync log (start / end, erase start / done, page move): value = ms since the last poke
    (OSD + "RTD2014Osd.c", r"(        case _OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG:\n)            RTDNVRamSaveOSDData\(\);",
     lambda m: m.group(1) + "            AWTO_NV_EV(1); RTDNVRamSaveOSDData(); AWTO_NV_EV(2);  // [keil2sdcc] sub #150", 1),
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c",
     r"(bit ScalerFlashErasePage\(BYTE ucBank, BYTE ucPage\)\n\{.*?    ScalerFlashWREN\(ucBank, ucPage\);)",
     lambda m: m.group(1) + " AWTO_NV_EV(3);  // [keil2sdcc] sub #150", 1),
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c",
     r"(    // No need to polling, 8051 will halt when common instruction executes\n\n    MCU_FF61_COMMON_OP_CODE = 0xFF;)",
     lambda m: m.group(1) + " AWTO_NV_EV(4);  // [keil2sdcc] sub #150", 1),
    (OSD + "RTD2014NVRamOsd.c", r"(bit RTDFlashMoveData\(BYTE ucPageID, BYTE \*pucData\)\n\{\n    BYTE ucPrevPage = g_pucFlashPageArr\[ucPageID\];)",
     lambda m: m.group(1) + " AWTO_NV_EV(5);  // [keil2sdcc] sub #150", 1),
    # #150: bounded loops that ran without a poke on unit 2 (flash port reads, page programs, prop-font strings): one poke each.
    # The FunctionLib files do not see RL6449_Project.h: a call (9 = AWTO_WDT_S_FREAD, 10 = AWTO_WDT_S_FWRITE)
    ("Kernel/Scaler/ScalerCommonFunction/Lib/Code/ScalerCommonNVRam/ScalerCommonFlashRead.c",
     r"(    MCU_FF78_ACCESS_FLASH_ADDR_0 = ucBank;)", lambda m: m.group(1) + " { extern void AwtoWdtLibPoke(unsigned char ucSite); AwtoWdtLibPoke(9); }  // [keil2sdcc] sub #150", 1),
    ("Kernel/Scaler/ScalerCommonFunction/Lib/Code/ScalerCommonNVRam/ScalerCommonFlashWrite.c",
     r"(    for\(ucPage = ucStartPage; ucPage <= ucEndPage; ucPage\+\+\)\n    \{)",
     lambda m: m.group(1) + " { extern void AwtoWdtLibPoke(unsigned char ucSite); AwtoWdtLibPoke(10); }  // [keil2sdcc] sub #150: per 4 KB sector part", 1),
    (OSD + "RTD2014OsdFontProp.c",
     r"(        while\(\(\*\(pucArray \+ ucElementCount\) != _END_\) &&\n              \(\*\(pucArray \+ ucElementCount\) != _NEXT_LINE\)\)\n        \{)",
     lambda m: m.group(1) + " AWTO_WDT_FEED(AWTO_WDT_S_OSDSTR);  // [keil2sdcc] sub #150: per character (string terminator bound)", 1),
    # #150: eDP HPD poll (panel T2, bound _PANEL_POWER_ON_T2 = 250 ms): per ms, as the SDK's other polls
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_DisplayDPTx.c", r"(            usTimeElapsed\+\+;)",
     lambda m: m.group(1) + " AWTO_WDT_FEED(AWTO_WDT_S_HPD);  // [keil2sdcc] sub #150", 1),
    # interrupt tests (wdt_test.py prio_*, t0_arm_from_isr): one XDATA flag test per EXINT0
    ("Kernel/System/Code/SysInt.c", r"(void SysEXINT0\(void\)[^\n]*\n\{\n    // Backup for Burst Write Bug\n    g_ucBackup_EXINT0 = MCU_FFF4_SCA_INF_ADDR;)",
     lambda m: m.group(1) + " AWTO_T0EV_EXINT0();  // [keil2sdcc] sub #138", 1),
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c", r"MCU_FFEA_WATCHDOG_TIMER \|= 0x40;",
     lambda m: f"AWTO_WDT_FEED({next(_NV_SITES)});  // [keil2sdcc] sub #138", 3),
]
