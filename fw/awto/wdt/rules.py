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
]
