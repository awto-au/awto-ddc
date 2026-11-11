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


def _feed(m):
    return m.group(1) + " AWTO_WDT_FEED();  // [keil2sdcc] sub #131"


SUBS = [
    # #138: a watchdog is never off. Compiled out here (_FLASH_PARTITION_NONE); kept safe if the boot partition is ever used
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c",
     r"// Disable watchdog timer\n    MCU_FFEA_WATCHDOG_TIMER &= ~\(_BIT7\);",
     "// awto #138: watchdog stays on: clear, longest period (N = 8)\n"
     "    MCU_FFEA_WATCHDOG_TIMER |= _BIT7 | _BIT6 | _BIT2 | _BIT1 | _BIT0;  // [keil2sdcc] sub #138", 1),
    # one feed per elapsed ms inside each bounded wait: the wait itself is not a hang (its bound is the SDK's)
    (TMR, r"(void ScalerTimerDelayXms\(WORD usNum\)\n\{.*?g_bNotifyTimer2Int = _FALSE;\n.*?g_bNotifyTimer2Int = _FALSE;)", _feed, 1),
    (TMR, r"(bit ScalerTimerPollingFlagProc\(WORD usTimeout, WORD usRegister, BYTE ucBit, bit bSuccess\)\n\{.*?usTimeElapsed\+\+;)", _feed, 1),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerTimerFunction.c",
     r"(bit ScalerTimerWaitForEvent\(EnumWaitEventType enumEvent\)\n\{.*?usTimeElapsed\+\+;)", _feed, 1),
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
]
