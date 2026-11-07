#!/usr/bin/env python3
"""Port the Realtek RL64xx Keil C51 SDK to SDCC: mechanical source rewrite + per-file compile harness.

usage: keil2sdcc.py port                     SDK -> tmp/sdcc-port/src (rewritten; regenerable)
       keil2sdcc.py compile <uv2> [--target T] [--jobs N] [--only SUBSTR]
                                             compile ONE target's C files (multi-target projects need
                                             --target, e.g. RL6449_Project), bucket errors
       keil2sdcc.py report                   print the last compile's error histogram

- Source of truth = SDK mirror (read-only) + the rules here + fw/sdcc/*.h. Never hand-edit tmp/sdcc-port/src:
  fix a rule or the compat header and re-run `port` (the tree is a derived artifact).
- <uv2> is SDK-relative, e.g. Kernel/Scaler/RL6449_Series_Scaler/Lib/RL6449_Series_Lib.Uv2
- Output: tmp/sdcc-port/{src,obj,logs}, tmp/sdcc-port/report.json. Log: tmp/logs/keil2sdcc.log
- `port` also tokenises DebugMessage<Cat>("text", v) -> AwtoMsg0(id)/AwtoMsgV(id, v), drops sites not in
  fw/msg_enable.txt, and writes fw/msgids.tsv (awto-ddc#25, #26).
- Repo is private (Realtek code), see CLAUDE.md. Tracking: awto-ddc#8.
"""
import fnmatch, hashlib, json, os, re, shutil, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_tools as T  # noqa: E402


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
WORK = ROOT / "tmp" / "sdcc-port"
SRC = WORK / "src"
SHIM = ROOT / "fw" / "sdcc"                    # keil_compat.h, intrins.h (committed)
OVERLAY = ROOT / "fw" / "overlay"              # our board/project files, SDK-relative paths, replace SDK copies
SDCC = str(T.BIN / "sdcc")                     # awto-sdcc (scripts/sdcc_tools.py)
# Per-file backstop (sdcc prints nothing while working, so no stall guard). Worst measured: RL6449_Series_DPRx0.c
# 64 s under full parallel load (#8). 3x worst-case rule (awto-dan#53). Expiry -> logged TIMEOUT fail.
COMPILE_TIMEOUT = 200
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


# ---------------- rewrite rules ----------------
SRC_EXT = {".c", ".h"}
# IRAM is the binding limit (#8): drop ISR register banks 1-3 (SDCC ISRs then push regs; +~1-2 us/IRQ);
# pData scratch arrays and all Keil `idata` go to XDATA (keil_compat.h) so 0x80-0xFF is left to the stack.
DROP_USING = True
RULES = [
    # OSD default D1 DP version: _AWTO_DP_D1_VERSION (RL6449_Project.h; SDK 0 = DP 1.1) (#28)
    (re.compile(r"^(\s*)0,(\s*// b1OsdDpD1PortVersion\b)", re.M), r"\1_AWTO_DP_D1_VERSION,\2"),
    (re.compile(r"\bdata(\s+pData(?:_EXINT)?\s*\[)"), r"xdata\1"),
    # Storage-first pointer decls: Keil `code BYTE *t[]` places t in code; SDCC reads it as pointer-to-code
    # and puts t in RAM (and `xdata BYTE *p` would become a 2-byte xdata pointer). Move the qualifier next
    # to the name. Variables only (name followed by [ = ; ,); functions returning pointers untouched.
    # Pointee keeps the same space unless the type names one (SDCC's old reading + Keil's storage).
    (re.compile(r"^(\s*(?:extern\s+|static\s+)*)(code|xdata|idata|data|pdata)\s+([A-Za-z_][\w ]*?)\s*(\*+)\s*"
                r"([A-Za-z_]\w*)(?=\s*[\[=;,])", re.M),
     lambda m: (f"{m.group(1)}{m.group(3)} {m.group(4)} {m.group(2)} {m.group(5)}"
                if re.search(r"\b(code|xdata|idata|data|pdata)\b", m.group(3)) else
                f"{m.group(1)}{m.group(3)} {m.group(2)} {m.group(4)} {m.group(2)} {m.group(5)}")),
    (re.compile(r"^(\s*(?:extern\s+|static\s+)*)(code|xdata|idata|data|pdata)\s+([A-Za-z_][\w ]*?)\s*\(\s*\*\s*"
                r"([A-Za-z_]\w*)", re.M), r"\1\3 (* \2 \4"),
    # CheckMDomain messages call ScalerMDomainGetFRCMemoryBW, which the SDK builds only with FRC+OD (OD is cut, #37)
    (re.compile(r"^#if\(\(\(_FRC_SUPPORT == _ON\) && \(_OD_SUPPORT == _ON\)\) \|\| \(_DISP_LATENCY_ADJUST_SUPPORT == _ON\)\)", re.M),
     "#if((((_FRC_SUPPORT == _ON) && (_OD_SUPPORT == _ON)) || (_DISP_LATENCY_ADJUST_SUPPORT == _ON)) || "
     "((_FRC_SUPPORT == _ON) && (_DEBUG_MESSAGE_CHECK_MDOMAIN == _ON)))"),
    # input-info pop-up after mode ACTIVE (_OSDEVENT_ACTIVE_DO_ONE_TIME_MSG): SDK 3 s -> _AWTO_INFO_POPUP_SEC
    (re.compile(r"ScalerTimerActiveTimerEvent\(SEC\(3\), (_USER_TIMER_EVENT_OSD_DISABLE\);)"),
     r"ScalerTimerActiveTimerEvent(SEC(_AWTO_INFO_POPUP_SEC), \1"),
    # panel T3 (video valid -> backlight on, 550 ms blind): the delay calibration runs inside it, same end tick (#53.6)
    (re.compile(r"\bScalerTimerDelayXms\(_PANEL_POWER_ON_T3\)"), "AwtoDiagPanelT3Wait(_PANEL_POWER_ON_T3)"),
    # host-wait loop of ScalerDebugMessage: host-silence timeout (fw/overlay AwtoMsg.h, #56)
    (re.compile(r"^(\s*)while\(g_bFwHalt != 0\);", re.M), r"\1while((g_bFwHalt != 0) && (AwtoMsgWait() != 0));"),
    # ISR-written flags polled in main code: non-volatile -> SDCC folds the re-check (warning 110/126, #26)
    (re.compile(r"\bbit(\s+g_b(?:NotifyTimer2Int|WDTimer2Update)\b)"), r"volatile bit\1"),
    # Keil memory qualifiers that can also be identifiers: only in declarator position
    (re.compile(r"\bcode(?=\s+[\*A-Za-z_])"), "__code"),
    (re.compile(r"\bdata(?=\s+[\*A-Za-z_])"), "__data"),
    # sfr NAME = 0xNN;  ->  __sfr __at(0xNN) NAME;
    (re.compile(r"\bsfr\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr __at(\2) \1;"),
    (re.compile(r"\bsfr16\s+(\w+)\s*=\s*([0-9A-Fa-fxX]+)\s*;"), r"__sfr16 __at(\2) \1;"),
    # ISR / register bank, only right after a parameter list: `) interrupt N [using M]`, `) using M`
    (re.compile(r"\)\s*interrupt\s+(\w+)\s+using\s+(\w+)"),
     r") __interrupt(\1)" if DROP_USING else r") __interrupt(\1) __using(\2)"),
    (re.compile(r"\)\s*interrupt\s+(\w+)(?=\s*[{;\n])"), r") __interrupt(\1)"),
    (re.compile(r"\)\s*using\s+(\d)(?=\s*[{;\n])"), r")" if DROP_USING else r") __using(\1)"),
    # TYPE QUAL NAME _at_ ADDR;  ->  __at(ADDR) TYPE QUAL NAME;
    (re.compile(r"^(\s*)([^;\n]*?)\b(\w+(?:\s*\[[^\]\n]*\])?)\s+_at_\s+([^;]+);", re.M), r"\1__at(\4) \2\3;"),
    # Keil-only pragmas (optimiser level, register banks) -> dropped; save/restore are kept (SDCC has them)
    (re.compile(r"^\s*#\s*pragma\s+(OT|OPTIMIZE|NOAREGS|AREGS|REGPARMS|NOREGPARMS|SRC|ASM|ENDASM|"
                r"LARGE|SMALL|COMPACT|ROM|CODE|DEBUG|OBJECTEXTEND|SYMBOLS|NOINTVECTOR|INTVECTOR)\b.*$",
                re.M | re.I), r"// [keil2sdcc] dropped pragma"),
]
# Compile-out rules for SDK code we don't use: (SDK-relative file, start-line regex, end-line regex, switch).
# Lines start..end (first end match after start) get wrapped in #if(switch == _ON). Switches default _OFF
# in fw/overlay/Project/Header/RL6449_Project.h. SDCC's linker keeps unreferenced code, so this saves flash.
OSD = "User/RTD Series/RTD2014Osd/Code/"
LOGO_SDK_DATA = "(_AWTO_DEMO_LOGO == _ON) && (_AWTO_LOGO_SDK == _ON)"   # Realtek logo consts; _OFF = ours (fw/sdcc/awto_logo_*.inc)
WRAPS = [
    # Realtek demo boot logo (call, draw fn, char maps, VLC glyph blobs + loader cases); ours replaces it
    # two single-line wraps: the backlight-on call between them must stay
    (OSD + "RTD2014Osd.c", r"^\s*OsdDispShowLogo\(\);", r"^\s*OsdDispShowLogo\(\);", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014Osd.c", r"ActiveTimerEvent\(SEC\(3\), _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO\);",
     r"_USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO\);", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdDisplay.c", r"^void OsdDispShowLogo\(void\)$", r"^\}", "_AWTO_DEMO_LOGO"),
    (OSD + "RTD2014OsdFontTable.c", r"^BYTE __code tiOSD_REALTEK_1BIT_LOGO0\[\]", r"^\};", LOGO_SDK_DATA),
    (OSD + "RTD2014OsdFontTable.c", r"^BYTE __code tiOSD_REALTEK_1BIT_LOGO1\[\]", r"^\};", LOGO_SDK_DATA),
    (OSD + "RTD2014OsdFontVLC.c", r"^BYTE __code tICON_REALTEK_1BIT_LOGO0\[\]", r"^\};", LOGO_SDK_DATA),
    (OSD + "RTD2014OsdFontVLC.c", r"^BYTE __code tICON_REALTEK_1BIT_LOGO1\[\]", r"^\};", LOGO_SDK_DATA),
    (OSD + "RTD2014OsdFontVLC.c", r"^\s*case _REALTEK_1BIT_LOGO0:", r"^\s*default:", "_AWTO_DEMO_LOGO", "before-end"),
    # input-info + debug pop-up: speech-bubble "i" icon at the left (tFONT1_ICON_INFORMATION), blank when _AWTO_POPUP_ICON is _OFF (#46)
    (OSD + "RTD2014OsdDisplay.c", r"OsdFontVLCDynamicLoadIcon\(_ICON_POS_UP_0, _MENU_INFORMATION\);",
     r"OsdFontPut1BitMainMenuIcon\(ROW\(_OSD_MESSAGE_ROW_START\), COL\(3\)", "_AWTO_POPUP_ICON"),
    # awto mark replaces the SDK info bubble consts when _AWTO_POPUP_ICON_AWTO is _ON (scripts/osd_icon_encode.py, #46)
    (OSD + "RTD2014OsdFontDynamicIcon_1.c", r"^BYTE __code tFONT1_ICON_INFORMATION\[\]", r"^\};", "_AWTO_POPUP_ICON_AWTO == _OFF"),
    # _AWTO_DEBUG_PORT: RL6449_Project.h forces GET_OSD_DDCCI_STATUS() off -> DDC port in Realtek debug mode (#13)
    ("User/RTD Series/RTD2014Osd/Header/RTD2014Include.h", r"^#define GET_OSD_DDCCI_STATUS\(\)",
     r"^#define GET_OSD_DDCCI_STATUS\(\)", "_AWTO_DEBUG_PORT == _OFF"),
    # NVRAM checksum: ours (RL6449_Project.h) so data left by the old fw / older builds reloads defaults (#8)
    (OSD + "RTD2014NVRamOsd.c", r"^#define _CHECKSUM\s", r"^#define _CHECKSUM\s", "!defined(_CHECKSUM)"),
    # DDC RAM arrays: address differs per chip/DDC channel, so the header extern can't get a single __at;
    # hide it from the defining file (SDCC rejects extern-without-__at + __at definition in one TU)
    ("Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonMcuInclude.h",
     r"^#if\(_D0_EMBEDDED_DDCRAM_MAX_SIZE", r"^extern BYTE xdata MCU_DDCRAM_D5\[", "!defined(_AWTO_DDCRAM_DEFINER)"),
    ("Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonMcuInclude.h",
     r"^#if\(_D0_MHL_EMBEDDED_DDCRAM_SIZE", r"^extern BYTE xdata MCU_DDCRAM_MHL_D2\[", "!defined(_AWTO_DDCRAM_DEFINER)"),
]
def fw_tag(root) -> str:
    """No --dirty, fixed abbrev: rebuilding one commit gives identical bytes (#51.5); AWTO_FW_TAG overrides."""
    return os.environ.get("AWTO_FW_TAG") or subprocess.run(
        ["git", "describe", "--always", "--abbrev=7"], cwd=root, capture_output=True, text=True).stdout.strip() or "nogit"


FW_TAG = fw_tag(ROOT)
LOGO_INC = "#if((_AWTO_DEMO_LOGO == _ON) && (_AWTO_LOGO_SDK == _OFF))\n%s\n#endif"
# Lines inserted before the first line matching anchor: (SDK-relative file, anchor regex, text)
INSERTS = [
    # awto boot logo consts, generated by scripts/osd_logo_encode.py (#46)
    (OSD + "RTD2014OsdFontVLC.c", r"^#if\(_OSD_TYPE == _REALTEK_2014_OSD\)", LOGO_INC % (SHIM / "awto_logo_icons.inc").read_text().rstrip("\n")),
    (OSD + "RTD2014OsdFontTable.c", r"^#if\(_OSD_TYPE == _REALTEK_2014_OSD\)", LOGO_INC % (SHIM / "awto_logo_maps.inc").read_text().rstrip("\n")),
    (OSD + "RTD2014OsdFontDynamicIcon_1.c", r"^BYTE __code \* __code tFONT1_MAIN_ICON_TABLE_1\[\]",
     "#if(_AWTO_POPUP_ICON_AWTO == _ON)\n%s\n#endif" % (SHIM / "awto_icon_info.inc").read_text().rstrip("\n")),
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c", r"^#include", "#define _AWTO_DDCRAM_DEFINER"),
    # #28: debug IIC engine follows the active port (fw/sdcc/awto_dbgport.inc; SUBS below route the debug branch to it)
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c",
     r"^void ScalerMcuDdcciSwitchPort\(EnumDDCCIDebugMode enumMode, BYTE ucInputPort\)$", (SHIM / "awto_dbgport.inc").read_text().rstrip("\n")),
    # our board (fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h); id 0x4F is unused in Pcb_List.h
    ("Kernel/Common/Pcb_List.h", r"^#define _RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP\s",
     "#define _RL6449_AWTO_JXC4K                                          0x4F"),
    ("Pcb/User_Pcb_Include.h", r'^#include "\./RL6449/LQFP_216/RL6449_QA_B_',
     '#include "./RL6449/LQFP_216/RL6449_AWTO_JXC4K.h"'),
    # our panel (fw/overlay/Panel/AWTO_LTM270FL01.h); id 0x3D is unused in User_Panel_List.h (#7)
    ("Panel/User_Panel_List.h", r"^#define _AUO_EDP_27_UHD_LOCAL_DIMMING\s",
     "#define _AWTO_LTM270FL01                        0x3D    // 3840 x 2160"),
    ("Panel/User_Panel_Include.h", r'^#include "30_AUO_eDP_27_UHD\.h"', '#include "AWTO_LTM270FL01.h"'),
    # awto-ddc#26: vendor FineTuneFrameSyncLineBuffer has no DHtotal debounce loop: one pass
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r"^\s*while\(ucDebounceCnt > 0\)", "    ucDebounceCnt = 1;"),
    # ... and no last-line block (no IVS2DVS rewrite after FrameSyncSetDt): off for this function only
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r"^#if\(_LAST_LINE_FINETUNE_ENABLE == _ENABLE\)",
     "#undef _LAST_LINE_FINETUNE_ENABLE\n#define _LAST_LINE_FINETUNE_ENABLE _DISABLE", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r'^\s*// Switch to "input active region"',
     "#undef _LAST_LINE_FINETUNE_ENABLE\n#define _LAST_LINE_FINETUNE_ENABLE _ENABLE", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    # awto-ddc#26: AwtoMsg0/AwtoMsgV (overlay AwtoMsg.h) live in the debug module, beside ScalerDebugMessage
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c",
     r"^void ScalerDebugSelectDDCCIDebugMode\(EnumDDCCIDebugMode enumMode\)$", '#include "AwtoMsg.h"'),
    # boot-stage / timing diag block (RL6449_Project.h StAwtoDiag; functions in fw/sdcc/awto_diag.inc; no-op when off)
    # awto-ddc#38: debug slave answers 0x3A / block read 0x3C inside the EXINT1 ISR (fw/sdcc/awto_dbgisr.inc, docs/diag-block.md)
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c", r"^\s*MCU_FF2A_IIC_IRQ_CONTROL2 \|= 0x20;",
     (SHIM / "awto_dbgisr.inc").read_text().rstrip("\n"), r"^void ScalerDebugIntProc_EXINT1\(void\)$"),
    ("Kernel/System/Code/SysMain.c", r"^#include", "#define _AWTO_DIAG_DEFINER"),
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (SHIM / "awto_diag.inc").read_text().rstrip("\n")),
    # #60 input-switch timeline (fw/sdcc/awto_sw.inc): mode-state poll per pass, panel power actions; #28 hold guards
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (SHIM / "awto_sw.inc").read_text().rstrip("\n")),
    ("Kernel/System/Code/SysMain.c", r"^\s*UserInterfaceKeyHandler\(\);", "            AwtoSwPoll();"),
    ("Kernel/System/Code/SysMain.c", r"^\s*UserCommonInterfaceOsdHandler\(\);", "            AwtoHoldOsdGuard();"),
    ("Kernel/User Common Function/Code/UserCommonInterface.c", r"^\s*switch\(ucEvent\)", "    AwtoSwEvent(AWTO_SW_EV_POWER, ucEvent);",
     r"^void UserCommonInterfacePanelPowerAction\(BYTE ucEvent\)$"),
    (OSD + "RTD2014OsdDisplay.c", r"^\s*SET_OSD_STATE\(_MENU_NONE\);", "    if(AwtoHoldBlocksDisable() == _TRUE)\n    {\n        return;\n    }",
     r"^void OsdDispDisableOsd\(void\)$"),
    ("Kernel/System/Code/SysMain.c", r"^\s*SysMainSystemInitial\(\);", "        AwtoDiagInit();"),                 # stage 1
    # delay calibration (#53.6) needs the DELAY_XUS macros, which only scaler files see
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c", r"^void ScalerMcu5usDelayCalc\(EnumClkSel enumClock\)$",
     (SHIM / "awto_delaycal.inc").read_text().rstrip("\n")),
    # awto-ddc#26 4K60 measurement ring: functions (fw/sdcc/awto_meas4k.inc), Timer2 sampler, M-domain / DPLL fine-tune call events
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (SHIM / "awto_meas4k.inc").read_text().rstrip("\n")),
    ("Kernel/System/Code/SysMain.c", r"^\s*SysMainSystemInitial\(\);", "        AwtoMeasInit();"),
    ("Kernel/System/Code/SysTimer.c", r"^\s*// Reload Backup for Burst Write Bug", "    AWTO_MEAS_T2ISR();", r"^void SysTimerIntProc2\(void\) __interrupt\(5\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMDomainMemorySettings\(&stFIFOScaling\);", "    AwtoMeasEvent(1, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMemoryInitial\(\);", "    AwtoMeasEvent(2, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMemoryFrameSyncSetDt\(_DT_TARGET_PERCENTAGE\);", "    AwtoMeasEvent(3, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMDomainSetDisplayFormat\(_FRAME_SYNC_LINE_BUFFER\);", "    AwtoMeasEvent(4, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerDPLLFineTuneFrameSyncLineBuffer\(\);", "    AwtoMeasEvent(5, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerIDomainVgipAdjustIHVDelay\(\);", "    AwtoMeasEvent(6, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMDomainControlDBApply\(\);", "    AwtoMeasEvent(7, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerPLLSetDPLLSSC\(GET_DCLK", "    AwtoMeasEvent(8, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerTimerWaitForEvent\(_EVENT_IVS\);", "    AwtoMeasEvent(9, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMemoryReset\(\);", "    AwtoMeasEvent(10, 0, 0);", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerSetByte\(P0_02_STATUS0, 0xFF\);", "    AwtoMeasEvent(14, 0, AWTO_MEAS_P0_02_0C());", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*if\(\(ScalerMDomainMemoryCheck\(\) == _FALSE\)", "    AwtoMeasEvent(11, 0, AWTO_MEAS_P0_02_0C());", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerGlobalIDDomainDBSetTriggerEvent\(\);", "    AwtoMeasEvent(13, 0, AWTO_MEAS_P0_02_0C());", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r"^\s*// Temporary Enable Frame Sync Fine Tune for Interlace", "    AwtoMeasEvent(30, 0, 0);", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r"^\s*stDHtotalFTStatus = ScalerMDomainDHtotalFinetune", "    AwtoMeasEvent(31, ucDebounceCnt, (unsigned int)ulDiffOffsetNew);", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r"^\s*SET_D_CLK_FREQ\(ScalerPLLGetNewCount\(ulDiffOffsetNew", "    AwtoMeasEvent(32, 0, (unsigned int)ulDiffOffsetNew);", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c", r'^\s*// Switch to "input active region"', "    AwtoMeasEvent(33, 0, 0);", r"^void ScalerDPLLFineTuneFrameSyncLineBuffer\(void\)$"),
    # #60 switch-path probes (AWTO_SW_EV_PROBE; fire only on a mode reset)
    ("Kernel/System/Code/SysJudge.c", r"^\s*SysModeResetState\(_MODE_ACTION_RESET_TO_SEARCH\);", "                AwtoSwEvent(AWTO_SW_EV_PROBE, 1);",
     r"^void SysJudgeModeResetProc\(void\)$"),
    ("Kernel/System/Code/SysJudge.c", r"^\s*if\(SysJudgeStateChangeEvent\(_MODE_STATUS_SEARCH\) == _FALSE\)", "                AwtoSwEvent(AWTO_SW_EV_PROBE, 2);",
     r"^void SysJudgeModeResetProc\(void\)$"),
    ("Kernel/System/Code/SysJudge.c", r"^\s*SET_MODE_RESET_TARGET\(_MODE_ACTION_RESET_TO_SEARCH\);", "                    AwtoSwEvent(AWTO_SW_EV_PROBE, 3);",
     r"^void SysJudgeModeResetProc\(void\)$"),
    ("Kernel/System/Code/SysMode.c", r"^\s*SysSourceInfoReset\(\);", "            AwtoSwEvent(AWTO_SW_EV_PROBE, 4);", r"^void SysModeResetState\(BYTE ucResetTarget\)$"),
    ("Kernel/System/Code/SysMode.c", r"^\s*ScalerTimerCancelTimerEvent\(_SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE\);", "            AwtoSwEvent(AWTO_SW_EV_PROBE, 5);",
     r"^void SysModeResetState\(BYTE ucResetTarget\)$"),
    # exact input frequencies (#34, #26): fw/sdcc/awto_freq.inc after each active-region count, 3-decimal pop-up strings
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMeasure.c", r"^void ScalerMeasureUpdateInputTimingData\(.*\)$", (SHIM / "awto_freq.inc").read_text().rstrip("\n")),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMDomainMemorySettings\(&stFIFOScaling\);", "    AwtoFreqInvalidate();", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerIDomainVgipAdjustIHVDelay\(\);", "            AwtoFreqUpdate();", r"^bit ScalerMDomainControl\(void\)$"),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c", r"^\s*ScalerMemorySetFIFOFreq\(_FIFO_FREQ_FRAME_BUFFER_SEL\);", "            AwtoFreqUpdate();", r"^bit ScalerMDomainControl\(void\)$"),
    (OSD + "RTD2014OsdFontProp.c", r"^void OsdPropGetShowVFreqStringAddress\(void\)$", (SHIM / "awto_freqstr.inc").read_text().rstrip("\n")),
] + [(OSD + "RTD2014OsdFontProp.c", anchor, "#if(_AWTO_FREQ == _ON)\n    if(AwtoFreqModeStr(%s) == _TRUE)\n    {\n        return;\n    }\n#endif" % which, rf"^void {fn}\(void\)$")
     for fn, anchor, which in (("OsdPropGetShowVFreqStringAddress", r"^\s*usTemp = GET_INPUT_TIMING_VFREQ\(\);", "AWTO_STR_VFREQ"),
                               ("OsdPropGetShowHFreqPClkStringAddress", r"^\s*g_pucModeInfoData\[0\] = _H_;", "AWTO_STR_HFREQ_PCLK"),
                               ("OsdPropGetShowResolutionStringAddress", r"^\s*if\(ucI != 0\)", "AWTO_STR_RES"))] + [
    ("Kernel/Scaler/ScalerFunction/Code/ScalerMcu.c", r"^\s*ScalerMcuIspInitial\(\);", "    AwtoDiagStage(2);",
     r"^\s*ScalerMcuGpioInitial\(\);"),                                                                   # after GPIO init
    ("Kernel/System/Code/SysMain.c", r"^\s*ScalerPinshareInitial\(\);", "    AwtoDiagStage(3);"),          # after McuInitial
    # #63 logo draw timestamps (switch log)
    (OSD + "RTD2014OsdDisplay.c", r"^\s*g_ucLogoTimerCounter = 0;", "    AwtoSwEvent(AWTO_SW_EV_LOGO, 0);", r"^void OsdDispShowLogo\(void\)$"),
    (OSD + "RTD2014OsdDisplay.c", r"^\s*SET_OSD_LOGO_ON\(_ON\);", "    AwtoSwEvent(AWTO_SW_EV_LOGO, 1);", r"^void OsdDispShowLogo\(void\)$"),
    ("Kernel/System/Code/SysMain.c", r"^\s*ScalerTimerInitialTimerEvent\(\);", "    AwtoDiagStage(4);"),  # after pin-share
    ("Kernel/System/Code/SysMain.c", r"^\s*ScalerTimerInitialTimerEvent\(\);", "#if(_AWTO_FAST_BOOT == _ON)\n    AwtoPanelVddEarly();\n#endif"),  # after stage 4: inserts stack, the later rule lands nearer the anchor
    ("Kernel/System/Code/SysMain.c", r"^\s*UserInterfaceKeyHandler\(\);", "            AwtoDiagMainPass();"),  # 5
    ("Kernel/System/Code/SysMain.c", r"^\s*SysPowerHandler\(\);", "            AwtoDiagTestCmd();"),  # after key scan (#33)
    (OSD + "RTD2014Key.c", r"^void UserInterfaceKeyHandler\(void\)$", (SHIM / "awto_testcmd.inc").read_text().rstrip("\n")),
    (OSD + "RTD2014OsdDisplay.c", r"^void OsdDispOsdMessage\(EnumOSDDispMsg enumMessage\)$",
     '#define AWTO_FW_TAG "%s"\n' % FW_TAG + (SHIM / "awto_dbgpop.inc").read_text().rstrip("\n")),
    (OSD + "RTD2014OsdDisplay.c", r"OsdPropPutStringCenter\(.*OsdDisplayGetSourcePortString\(\)",
     "            if(g_stAwtoDiag.ucDbgPopup == 1)\n            {\n                AwtoOsdDebugLines();\n                break;\n            }"),
    ("Kernel/System/Code/SysTimer.c", r"^\s*TF2 = 0;", "    AWTO_DIAG_T2ISR();"),
    ("Kernel/System/Code/SysInt.c", r"^\s*g_ucBackup_EXINT1 = MCU_FFF4", "    AWTO_DIAG_EX1ISR();"),
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (SHIM / "awto_loopsplit.inc").read_text().rstrip("\n")),   # #75
    ("Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c", r"^bit ScalerDpRx1DisplayFormatSetting\(void\)$",
     (SHIM / "awto_dpframe.inc").read_text().rstrip("\n")),   # #60
] + [   # main-loop cost per handler (fw/sdcc/awto_loopprof.inc, -D_AWTO_LOOP_PROF=_ON); AWTO_LP(k) lands just before handler k
    ("Kernel/System/Code/SysMain.c", r"^void main\(void\)$", (SHIM / "awto_loopprof.inc").read_text().rstrip("\n")),
] + [("Kernel/System/Code/SysMain.c", rf"^\s*{fn}\(\);", f"            AWTO_LP({k});", r"^void main\(void\)$")
     for k, fn in enumerate(("AwtoSwPoll", "SysPowerHandler", "SysJudgeHandler", "SysTimerHandler", "SysSourceHandler",
                             "SysModeHandler", "SysDpRxHandler", "SysTMDSRxHandler", "ScalerHdcp2Handler", "AwtoHoldOsdGuard",
                             "UserCommonDdcciHandler"))] + [
    ("Kernel/System/Code/SysMain.c", rf"^\s*{fn}\(\);", f"            AWTO_SW_MARK({k});", r"^void main\(void\)$")     # #60 slow segments
    for k, fn in enumerate(("AwtoSwPoll", "SysPowerHandler", "SysJudgeHandler", "SysTimerHandler", "SysSourceHandler",
                            "SysModeHandler", "SysDpRxHandler", "SysTMDSRxHandler", "ScalerHdcp2Handler", "AwtoHoldOsdGuard",
                            "UserCommonDdcciHandler"))] + [
    ("Kernel/System/Code/SysSource.c", rf"^\s*{fn}\(g_ucSearchIndex\);", f"            AWTO_SW_MARK({k});", r"^void SysSourceHandler\(void\)$")
    for k, fn in ((20, "SysSourceScanPortInitial"), (21, "SysSourceSearchTimeInitial"), (22, "SysSourceDetectPort"))] + [
    ("Kernel/System/Code/SysSource.c", r"^\s*SysSourceJudge\(\);", "            AWTO_SW_MARK(23);", r"^void SysSourceHandler\(void\)$"),
] + [("Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c", rf"^\s*if\({fn}\(", f"    AWTO_SW_MARK({k});",
      r"^BYTE ScalerDpRx1ScanInputPort\(void\)$")      # #60: DP Rx1 scan steps (marks 30..36)
     for k, fn in ((30, "ScalerDpRx1HdcpCheck"), (31, "ScalerDpRx1GetVideoStream"), (32, "ScalerDpRx1MSACheck"),
                   (33, "ScalerDpRx1GetVideoInfo"), (34, "ScalerDpRx1DisplayFormatSetting"),
                   (35, "ScalerDpRx1StreamClkRegenerate"), (36, "ScalerDpRx1FifoCheck"))] + [
    ("Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c", r"^\s*ScalerTimerCancelTimerEvent\(_SCALER_TIMER_EVENT_DP_RX1_HDCP_LONG_HOTPLUG_EVENT\);",
     "    AWTO_SW_MARK(37);", r"^BYTE ScalerDpRx1ScanInputPort\(void\)$"),
] + [   # panel power-up in UserCommonInterfacePanelPowerAction: _PANEL_ON path, then the _BACKLIGHT_ON path
    ("Kernel/User Common Function/Code/UserCommonInterface.c", rx, txt, rf"^\s*case {case}:")
    for case, tail in (("_PANEL_ON", r"^\s*if\(GET_PANELPOWERSTATUS\(\) != _BACKLIGHT_ON_ALREADY\)"),
                       ("_BACKLIGHT_ON", r"^\s*// Set Video Stream parameter"))
    for rx, txt in ((r"^\s*PCB_PANEL_POWER\(_PANEL_CONTROL_ON\);", "    AwtoDiagStage(5);"),     # panel VDD (#63 order)
                    (tail, "    AwtoDiagStage(7);"))                                                 # eDP link done
] + [   # stage 8 = backlight on: the DPTx branch of _BACKLIGHT_ON (first PCB_BACKLIGHT_POWER after the stream set-up)
    ("Kernel/User Common Function/Code/UserCommonInterface.c", r"^\s*PCB_BACKLIGHT_POWER\(_LIGHT_CONTROL_ON\);",
     "    AwtoDiagStage(8);", r"^\s*// Set Video Stream parameter")
]

# Block substitutions: (SDK-relative file, regex (DOTALL), replacement fn(match) -> text, expected count).
# #28: SCL hold/release of the debug protocol and the debug-mode channel select, fixed to _DEBUG_DDC_CHANNEL_SEL in
# the SDK, go to the DDC FF22 selects (_AWTO_DBG_FOLLOW); the SDK block stays in the #else.
SCL_BLOCK = r"#if\(_DEBUG_DDC_CHANNEL_SEL == _DDC5\)\s*\n\s*MCU_FE81_DDC5_DDC_CONTROL_2 (\|= _BIT0|&= ~_BIT0);.*?#endif"
SUBS = [
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c", SCL_BLOCK,
     lambda m: "#if(_AWTO_DBG_FOLLOW == _ON)  // [keil2sdcc] sub\n    AWTO_DBG_SCL(%s);\n#else\n%s\n#endif" % (m.group(1), m.group(0)), 4),
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c",
     r"#if\(_DEBUG_DDC_CHANNEL_SEL == _DDC3\)\s*\n {8}// DDC from DDC3 channel.*?#endif",   # SwitchPort (8 sp), not DdcciInitial (4)
     lambda m: "#if(_AWTO_DBG_FOLLOW == _ON)  // [keil2sdcc] sub\n        AwtoDbgSelectChannel(ucInputPort);\n#else\n%s\n#endif" % m.group(0), 1),
    # #63 fast boot: no waits for rails our board never switches (PCB_DDR_POWER / PCB_VCCK_OFF_POWER are no-ops)
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Power.c", r"PCB_DDR_POWER_RELEASE_TIME\(_DDR_POWER_OFF_TIME\);",
     lambda m: "#if(_AWTO_FAST_BOOT == _OFF)  // [keil2sdcc] sub\n" + m.group(0) + "\n#endif", 1),
    ("Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Power.c", r"(// Wait for (DDR|1\.1V) stable, can't delete\s*\n\s*)(ScalerTimerDelayXms\(10\);)",
     lambda m: m.group(1) + "\n#if(_AWTO_FAST_BOOT == _OFF)  // [keil2sdcc] sub\n            " + m.group(3) + "\n#endif", 2),
    # #60 step 2: the three backlight-offs of an input change / display setting become a blank (AWTO_BL_OFF_OR_BLANK)
    ("Kernel/System/Code/SysMode.c", r"(// Turn off backlight to prevent garbage\s*\n\s*)UserCommonInterfacePanelPowerAction\(_BACKLIGHT_OFF\);",
     lambda m: m.group(1) + "AWTO_BL_OFF_OR_BLANK(1);  // [keil2sdcc] sub", 2),
    ("Kernel/User Common Function/Code/UserCommonInterface.c", r"UserCommonInterfacePanelPowerAction\(_BACKLIGHT_OFF\);",
     lambda m: "AWTO_BL_OFF_OR_BLANK(2);  // [keil2sdcc] sub", 1),
    # #60 step 3: no HDMI hot-plug pulse on an input switch (the host then re-reads the EDID and re-lays out): toggle off
    ("Kernel/System/Code/SysSource.c", r"if\(UserCommonNVRamGetSystemData\(_HDMI_HOT_PLUG_SUPPORT\) == _TRUE\)",
     lambda m: "if((_AWTO_HDMI_HPD_TOGGLE == _ON) && (UserCommonNVRamGetSystemData(_HDMI_HOT_PLUG_SUPPORT) == _TRUE))  // [keil2sdcc] sub", 1),
    ("Kernel/User Common Function/Code/UserCommonNVRamSystem.c", r"if\(g_stSystemData\.b1HDMIHotPlugSupport == _TRUE\)",
     lambda m: "if((_AWTO_HDMI_HPD_TOGGLE == _ON) && (g_stSystemData.b1HDMIHotPlugSupport == _TRUE))  // [keil2sdcc] sub", 1),
    # #74 debug-messages switch in NVRAM: a spare bit of the last OSD-user byte (sizeof and record layout unchanged, default 0)
    ("User/RTD Series/RTD2014Osd/Header/RTD2014NVRamOsd.h",r"BYTE b3OsdDpMST : 3;",
     lambda m: m.group(0) + "\n    BYTE b1AwtoMsgOn : 1;  // [keil2sdcc] sub", 1),
    ("User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c", r"(void UserInterfaceInitial\(void\)\n\{\n    PCB_PWM_SETTING\(\);\n    RTDNVRamStartup\(\);)",
     lambda m: m.group(1) + "\n#if(_AWTO_DIAG == _ON)  // [keil2sdcc] sub\n    AwtoMsgLoad();\n#endif", 1),
    # #54: an M2PLL re-entry (power saving -> on) keeps the self-calibrated loop counts
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c", r"g_ucDelay5usN_Base = _M2PLL_DELAY6US_CNT;",
     lambda m: "g_ucDelay5usN_Base = (g_ucAwtoCal5 != 0) ? g_ucAwtoCal5 : _M2PLL_DELAY6US_CNT;  // [keil2sdcc] sub", 1),
    ("Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c", r"g_ucDelayXusN_Base = _M2PLL_DELAY4US_CNT;",
     lambda m: "g_ucDelayXusN_Base = (g_ucAwtoCalX != 0) ? g_ucAwtoCalX : _M2PLL_DELAY4US_CNT;  // [keil2sdcc] sub", 1),
    # #75 main-loop split (fw/sdcc/awto_loopsplit.inc): the stable/timing watchdog every AWTO_SLOW_MS in ACTIVE (other
    # states: every pass, a short glitch while locking still resets the search), cable detection every AWTO_SLOW_MS
    ("Kernel/System/Code/SysJudge.c", r"if\(SysJudgeCheckStatus\(\) == _FALSE\)",
     lambda m: "if(((AWTO_SLOW_DUE_JUDGE() == _TRUE) || (GET_MODE_STATE() != _MODE_STATUS_ACTIVE)) && (SysJudgeCheckStatus() == _FALSE))  // [keil2sdcc] sub", 1),
    ("Kernel/System/Code/SysSource.c", r"(void SysSourceHandler\(void\)\n\{\n)    SysSourceCableDetection\(\);",
     lambda m: m.group(1) + "    if(AWTO_SLOW_DUE_CABLE() == _TRUE)  // [keil2sdcc] sub\n    {\n        SysSourceCableDetection();\n    }", 1),
    # #60: DP Rx1 SST two-frame waits = 2 x the measured frame (fw/sdcc/awto_dpframe.inc), not 2 x 45 ms
    ("Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c",
     r"(bit ScalerDpRx1DisplayFormatSetting\(void\)\n\{.*?)ScalerTimerDelayXms\(_DP_TWO_FRAME_TIME_MAX\);",
     lambda m: m.group(1) + "AWTO_DP_FRAME_SET(ulVBs2BsCount);  // [keil2sdcc] sub\n        ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());", 1),
    ("Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c",
     r"(bit ScalerDpRx1FifoCheck\(EnumDpFifoCheckCondition enumFifoCheckCondition\)\n\{.*?)ScalerTimerDelayXms\(_DP_TWO_FRAME_TIME_MAX\);",
     lambda m: m.group(1) + "ScalerTimerDelayXms(AWTO_DP_TWO_FRAMES());  // [keil2sdcc] sub", 1),
    # boot / held logo artwork = window 0 colour (osd_logo_encode.py: artwork transparent): _AWTO_LOGO_COLOR, SDK _LOGO_CP_BLUE
    (OSD + "RTD2014OsdDisplay.c", r"(XEND\(_LOGO_WINDOW_SIZE_X\), YEND\(_LOGO_WINDOW_SIZE_Y\), )_LOGO_CP_BLUE\);",
     lambda m: m.group(1) + "_AWTO_LOGO_COLOR);  // [keil2sdcc] sub", 1),
    # #63 big logo: 2x OSD scale for the logo only (flag restored after the draw), our grid size, run-length map draw, window = grid
    (OSD + "RTD2014OsdDisplay.c", r"    OsdFuncApplyMap\(WIDTH\(70\), HEIGHT\(10\),",
     lambda m: "    SET_OSD_DOUBLE_SIZE(_ON);  // [keil2sdcc] sub\n    OsdFuncApplyMap(WIDTH(AWTO_LOGO_COLS), HEIGHT(AWTO_LOGO_ROWS),", 1),
    (OSD + "RTD2014OsdDisplay.c", r"    OsdFontPut1BitTable\(ROW\(0\), COL\(0\), tiOSD_REALTEK_1BIT_LOGO0.*?LOGO1, COLOR\(_LOGO_CP_BG, _LOGO_CP_BG\)\);",
     lambda m: "    {  // [keil2sdcc] sub\n        extern void AwtoLogoDraw(void);\n        AwtoLogoDraw();\n    }", 1),
    (OSD + "RTD2014OsdDisplay.c", r"XEND\(_LOGO_WINDOW_SIZE_X\), YEND\(_LOGO_WINDOW_SIZE_Y\)",
     lambda m: "XEND(AWTO_LOGO_COLS * 12 - 1), YEND(AWTO_LOGO_ROWS * 18 - 1)", 1),
    (OSD + "RTD2014OsdDisplay.c", r"(OsdWindowDrawing\(_OSD_WINDOW_0, [^\n]*\n    OsdFuncEnableOsd\(\);)",
     lambda m: m.group(1) + "\n    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());  // [keil2sdcc] sub", 1),
]

from keil2sdcc_drops import DROP_WRAPS, DROP_SUBS  # noqa: E402  (#65 step 1)
WRAPS += DROP_WRAPS
SUBS += DROP_SUBS

# Per-module rules (#65, docs/cleanroom.md): fw/awto/<mod>/rules.py may define WRAPS, INSERTS and SUBS (formats above).

def _resolve_clean():
    """Clean tree for the mixed build: $AWTO_RTDFW_REPO as is (live dir), else the commit in fw/awto/clean_ref.txt exported
    to tmp/clean-pin (HEAD of awto-rtdfw may be ahead of what links; the pin moves by an explicit edit of the file)."""
    env = os.environ.get("AWTO_RTDFW_REPO")
    if env:
        return Path(env)
    repo = Path("/mnt/2tb/git/awto-rtdfw")
    refp = ROOT / "fw" / "awto" / "clean_ref.txt"
    if not refp.exists() or not repo.is_dir():
        return repo
    ref = refp.read_text().split("#")[0].strip()
    dst = ROOT / "tmp" / "clean-pin"
    if not (dst / ".ref").exists() or (dst / ".ref").read_text() != ref:
        import shutil
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        tar = subprocess.run(["git", "-C", str(repo), "archive", ref, "awto", "facts"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dst)], input=tar, check=True)
        (dst / ".ref").write_text(ref)
    return dst


CLEAN = _resolve_clean()
os.environ["AWTO_RTDFW_REPO"] = str(CLEAN)         # module rules.py files test for their clean directory
ALIASES, PIN_COMMON = [], []                       # from rules.py: (sdk name, clean name) macros for SDK files; fns kept in common


def load_module_rules(base=ROOT / "fw" / "awto"):
    import importlib.util
    for p in sorted(base.glob("*/rules.py")):
        spec = importlib.util.spec_from_file_location(f"awto_rules_{p.parent.name}", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for name, dst in (("WRAPS", WRAPS), ("INSERTS", INSERTS), ("SUBS", SUBS), ("ALIASES", ALIASES), ("PIN_COMMON", PIN_COMMON)):
            dst.extend(getattr(m, name, []))


load_module_rules()


def apply_subs(rel: str, text: str, stats) -> str:
    for f, rx, fn, want in SUBS:
        if f != rel:
            continue
        text, n = re.subn(rx, fn, text, flags=re.S)
        if n != want:
            sys.exit(f"sub rule matched {n}x, want {want}: {f} {rx[:60]!r}")
        stats[f"sub {f.rsplit('/', 1)[-1]}"] += n
    return text


def apply_inserts(rel: str, text: str, stats) -> str:
    for rule in INSERTS:
        f, anchor, add = rule[:3]
        if f != rel:
            continue
        lines = text.split("\n")
        start = 0
        if len(rule) > 3:      # optional: first anchor match after the first line matching rule[3]
            start = next((k for k, l in enumerate(lines) if re.search(rule[3], l)), None)
            if start is None:
                sys.exit(f"insert rule did not match: {f} after {rule[3]!r}")
        i = next((k for k in range(start, len(lines)) if re.search(anchor, lines[k])), None)
        if i is None:
            sys.exit(f"insert rule did not match: {f} {anchor!r}")
        lines.insert(i, add + "  // [keil2sdcc] insert")
        text = "\n".join(lines)
        stats["insert"] += 1
    return text


def apply_wraps(rel: str, text: str, stats) -> str:
    lines = text.split("\n")
    for w in WRAPS:
        f, start, end, sw = w[:4]
        if f != rel:
            continue
        before_end = len(w) > 4 and w[4] == "before-end"      # end line itself stays outside the #if
        s = next((i for i, l in enumerate(lines) if re.search(start, l)), None)
        e = None if s is None else next((i for i in range(s, len(lines)) if re.search(end, lines[i])), None)
        if s is None or e is None:
            sys.exit(f"wrap rule did not match: {f} {start!r}..{end!r} (SDK changed? fix the rule)")
        e = e - 1 if before_end else e
        cond = sw if re.search(r"[()!=<> ]", sw) else f"{sw} == _ON"     # switch name or raw condition
        lines[s:e + 1] = [f"#if({cond})  // [keil2sdcc] wrap"] + lines[s:e + 1] + ["#endif"]
        stats[f"wrap {sw}"] += 1
    return "\n".join(lines)


SBIT = re.compile(r"\bsbit\s+(\w+)\s*=\s*([\w]+)\s*\^\s*(\d)\s*;")
INCLUDE = re.compile(r'^(\s*#\s*include\s*[<"])([^>"]+)([>"])', re.M)


def build_name_index():
    """lower-case basename -> list of SDK-relative paths (Windows includes are case-insensitive)."""
    idx = {}
    for p in SDK.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            idx.setdefault(p.name.lower(), []).append(p.relative_to(SDK))
    return idx


def ci_resolve(base: Path, rel: str):
    """Resolve `rel` under `base` matching each path component case-insensitively (Windows semantics)."""
    p = base
    for part in rel.split("/"):
        if part in (".", ""):
            continue
        if part == "..":
            p = p.parent
            continue
        if (p / part).exists():
            p = p / part
            continue
        hit = next((c for c in p.iterdir() if c.name.lower() == part.lower()), None) if p.is_dir() else None
        if hit is None:
            return None
        p = hit
    return p


def fix_includes(text, here: Path, idx):
    def sub(m):
        inc = m.group(2).replace("\\", "/")
        cand = (here / inc)
        if cand.exists():
            return m.group(1) + inc + m.group(3)
        hit = ci_resolve(here, inc)                          # same path, wrong case in some component
        if hit is not None:
            fixed = os.path.relpath(hit, here).replace(os.sep, "/")
            return m.group(1) + fixed + m.group(3)
        hits = idx.get(Path(inc).name.lower())
        if hits and len(hits) == 1:                         # basename unique -> correct the case
            fixed = str(Path(inc).parent / hits[0].name) if "/" in inc else hits[0].name
            return m.group(1) + fixed + m.group(3)
        return m.group(1) + inc + m.group(3)
    return INCLUDE.sub(sub, text)


USING_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*using\s+(\d)\s*\n?\s*\{")
INT_DEF = re.compile(r"\b(\w+)\s*\([^;{)]*\)\s*interrupt\s+(\w+)(?:\s+using\s+(\d))?\s*\n?\s*\{")


def add_using_to_protos(text, using, stats):
    """SDCC needs the prototype's __interrupt/__using to match the definition (Keil does not).
    Dropping __using is unsafe: the fn runs on an ISR register bank. `using` maps name -> attr string."""
    def sub(m):
        attrs = using.get(m.group(2))
        if attrs is None or "__using" in m.group(0) or "__interrupt" in m.group(0) \
                or re.search(r"\breturn\b", m.group(1)):
            return m.group(0)
        stats["proto attrs added"] += 1
        return f"{m.group(1)}{m.group(2)}({m.group(3)}){attrs};"
    # declaration line: [extern] <type words> [*] name(params);  (a call has no type words before it)
    return re.sub(r"^(\s*(?:extern\s+)?(?:\w+\s+)+\**\s*)(\w+)\s*\(([^;{()]*)\)\s*;", sub, text, flags=re.M)


AT_DEF = re.compile(r"\b(\w+)(?:\s*\[[^\]\n]*\])?\s+_at_\s+([^;]+);")
AT_ADDR = {}                                   # name -> address expr, filled in port pass 1


def add_at_to_externs(text, stats):
    """SDCC needs `extern` decls to carry the definition's __at(addr) (Keil does not)."""
    def sub(m):
        addr = AT_ADDR.get(m.group(2))
        if addr is None or "__at" in m.group(0):
            return m.group(0)
        stats["extern __at added"] += 1
        return f"__at({addr}) {m.group(0)}"
    return re.sub(r"\bextern\b[^;\n(]*?\b(?:\w+\s+)+\**\s*()(\w+)\s*(?:\[[^\]\n]*\])?\s*;", sub, text)


# ---------------- tokenised debug messages (#25, #26) ----------------
# DebugMessage<Cat>("text", v) -> AwtoMsg0(0xHHLL) / AwtoMsgV(0xHHLL, v) (overlay AwtoMsg.h); wire bytes {0x01, HH, LL, 0},
# HH/LL in 1..255 so the NUL-terminated protocol never sees a 0. Text lives in fw/msgids.tsv.
# Sites not matched by fw/msg_enable.txt (or whose category flag is _OFF in Debug.h) are dropped.
MSG_TSV = ROOT / "fw" / "msgids.tsv"
MSG_ENABLE = ROOT / "fw" / "msg_enable.txt"
MSG_CATS = None                                # category -> Debug.h flag name, read from the overlay Debug.h
MSG_FLAG_ON = {}                               # flag name -> bool
MSG_RULES = []                                 # (kind, value) from msg_enable.txt
MSG_IDS = {}                                   # (category, text) -> id, filled by collect_messages
_STR = r'"(?:[^"\\\n]|\\.)*"'
MSG_CALL = re.compile(r"\bDebugMessage(\w+)\s*\(")
MSG_LIT = re.compile(rf"\s*((?:{_STR}\s*)+),")
COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"', re.S)
ESC = {"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11, "\\": 92, '"': 34, "'": 39, "?": 63}
# side effects: a call to a mixed-case function, ++/--, assignment (ALL-CAPS macros are the SDK's GET_*/PDATA_* reads)
SIDE_EFFECT = re.compile(r"\b\w*[a-z]\w*\s*\(|\+\+|--|(?<![=!<>])=(?!=)")


def c_unescape(lit: str) -> str:
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c != "\\":
            out.append(c); i += 1; continue
        m = re.match(r"\\(x[0-9A-Fa-f]+|[0-7]{1,3}|.)", lit[i:], re.S)
        e = m.group(1)
        out.append(chr((int(e[1:], 16) if e[0] == "x" else int(e, 8) if e[0] in "01234567" else ESC.get(e, ord(e))) & 0xFF))
        i += len(m.group(0))
    return "".join(out)


def mask_comments(text: str) -> str:
    """Blank out comments (same length, newlines kept) so offsets match the original; strings stay."""
    return COMMENT.sub(lambda m: m.group(0) if m.group(0)[0] == '"' else re.sub(r"[^\n]", " ", m.group(0)), text)


def call_end(masked: str, i: int) -> int:
    """Index of the ')' closing the call whose '(' precedes i (strings and char literals skipped), or -1."""
    depth = 1
    while i < len(masked):
        c = masked[i]
        if c in "\"'":
            m = re.compile(rf"{c}(?:[^{c}\\\n]|\\.)*{c}").match(masked, i)
            i = m.end() if m else i + 1
            continue
        depth += (c == "(") - (c == ")")
        if depth == 0:
            return i
        i += 1
    return -1


def msg_sites(text: str, full=False):
    """Yield (start, end, category, text) per DebugMessage<Cat>(<literals>, ...) call; text[start:end] is the
    literal run. A call whose first argument is not purely string literals yields (None, None, category, head).
    full=True: literal calls only, yields (call_start, call_end, category, text, value_expr)."""
    masked = mask_comments(text)
    for m in MSG_CALL.finditer(masked):
        if m.group(1) not in MSG_CATS:
            continue
        ls = masked.rfind("\n", 0, m.start()) + 1
        if re.match(r"\s*#\s*define", masked[ls:m.start()]):
            continue
        lit = MSG_LIT.match(masked, m.end())
        if lit is None:
            if not full:
                yield None, None, m.group(1), masked[m.end():m.end() + 60].split("\n")[0]
            continue
        val = "".join(c_unescape(x[1:-1]) for x in re.findall(_STR, lit.group(1)))
        if full:
            e = call_end(masked, lit.end())
            if e >= 0:
                yield m.start(), e + 1, m.group(1), val, text[lit.end():e].strip()
        else:
            yield m.end(), lit.end() - 1, m.group(1), val


def assign_msg_ids(keys):
    """Stable 16-bit id per (category, text): sha1 of category+text, each byte folded into 1..255; collisions
    re-salted deterministically, keys processed in sorted order."""
    import hashlib
    ids, used, collisions = {}, {}, 0
    for key in sorted(keys):
        for salt in range(1000):
            d = hashlib.sha1(f"{key[0]}\0{key[1]}\0{salt}".encode("latin-1")).digest()
            v = ((d[0] % 255 + 1) << 8) | (d[1] % 255 + 1)
            if v not in used:
                break
            collisions += 1
        else:
            sys.exit(f"msg id: no free id for {key!r}")
        used[v] = key; ids[key] = v
    return ids, collisions


def load_msg_rules():
    MSG_RULES.clear()
    for n, line in enumerate(MSG_ENABLE.read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, val = line.partition(":")
        if kind not in ("cat", "file", "id") or not val.strip():
            sys.exit(f"{MSG_ENABLE}:{n}: bad rule {line!r}")
        MSG_RULES.append((kind, int(val, 16) if kind == "id" else val.strip()))


def msg_enabled(cat: str, rel: str, mid: int) -> bool:
    """Category flag ON in Debug.h (else the SDK already dropped the call) and some allowlist rule matches (cat / file glob / id)."""
    import fnmatch
    if not MSG_FLAG_ON.get(MSG_CATS[cat], False):
        return False
    return any((k == "cat" and v == cat) or (k == "id" and v == mid) or (k == "file" and fnmatch.fnmatch(rel, v))
               for k, v in MSG_RULES)


def collect_messages(files, overlay):
    """Pre-pass over SDK + overlay sources: assign ids, write fw/msgids.tsv. Returns stats."""
    global MSG_CATS
    dbg = (OVERLAY / "Kernel/Common/Debug.h").read_text(errors="replace")
    MSG_CATS = {c: f for f, c in re.findall(
        r"#if\(\s*(\w+)\s*==\s*_ON\)\s*\n#define\s+DebugMessage(\w+)\(x,\s*y\)", dbg)}
    MSG_FLAG_ON.clear()
    MSG_FLAG_ON.update({f: v == "_ON" for f, v in re.findall(r"#define\s+(_DEBUG_MESSAGE_\w+)\s+(_ON|_OFF)\b", dbg)})
    load_msg_rules()
    srcs = {}
    for p in files:
        if p.suffix.lower() in SRC_EXT:
            srcs[str(p.relative_to(SDK))] = p
    for p in overlay:
        if p.suffix.lower() in SRC_EXT:
            srcs[str(p.relative_to(OVERLAY))] = p      # overlay replaces the SDK file
    sites, skipped, skip_sample = [], 0, []
    for rel, p in srcs.items():
        t = p.read_bytes().decode("latin-1").replace("\r\n", "\n")
        for a, b, cat, txt in msg_sites(t):
            if a is None:
                skipped += 1; skip_sample.append(f"{rel}: DebugMessage{cat}({txt}"); continue
            sites.append((cat, rel, t.count("\n", 0, a) + 1, txt))
    keys = {(c, x) for c, _, _, x in sites}
    MSG_IDS.clear()
    ids, coll = assign_msg_ids(keys)
    MSG_IDS.update(ids)
    rows = sorted((ids[(c, x)], c, f"{r}:{ln}", x, int(msg_enabled(c, r, ids[(c, x)]))) for c, r, ln, x in sites)
    esc = lambda s: s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    MSG_TSV.write_text("".join(f"{i:04x}\t{c}\t{f}\t{esc(x)}\t{en}\n" for i, c, f, x, en in rows),
                       encoding="utf-8", errors="replace")
    log(f"msgids: {len(sites)} call sites, {len(keys)} unique ids, {coll} collisions re-salted, "
        f"{skipped} skipped (not a single literal), {sum(r[4] for r in rows)} enabled -> {MSG_TSV}")
    for s_ in skip_sample[:8]:
        log(f"  msg skipped: {s_}")
    return len(sites), skipped


def tokenise_messages(text: str, stats, rel: str) -> str:
    out, last = [], 0
    for a, b, cat, txt, val in msg_sites(text, full=True):
        mid = MSG_IDS[(cat, txt)]
        if msg_enabled(cat, rel, mid):
            zero = re.fullmatch(r"0[xX]?0*[uUlL]*", val) is not None
            new = f"AwtoMsg0(0x{mid:04X})" if zero else f"AwtoMsgV(0x{mid:04X}, {val})"
            stats["msg enabled"] += 1
        elif MSG_FLAG_ON.get(MSG_CATS[cat], False) and SIDE_EFFECT.search(val):
            new = f"(void)({val})"                           # may have side effects: keep it evaluated
            stats["msg dropped, value kept"] += 1
            log(f"  msg dropped, value expr kept: {rel}:{text.count(chr(10), 0, a) + 1} DebugMessage{cat}: {val}")
        else:
            new = "((void)0)"
            stats["msg dropped"] += 1
        out.append(text[last:a]); out.append(new); last = b
    out.append(text[last:])
    return "".join(out)


def rewrite(text, here, idx, sfr_addr, using, stats, rel):
    text = text.replace("\r\n", "\n")
    # cpp splices `\ <spaces>\n` anyway (warns "backslash and newline separated by space"): drop the spaces, same splice
    text, n = re.subn(r"\\[ \t]+\n", "\\\n", text)
    stats["backslash-space"] += n
    # "/*" inside a block comment (cpp warns): the comment still ends at the first */; "/ *" keeps the text, no warning
    text = COMMENT.sub(lambda m: "/*" + m.group(0)[2:-2].replace("/*", "/ *") + "*/"
                       if m.group(0).startswith("/*") else m.group(0), text)
    text = tokenise_messages(text, stats, rel)
    text = fix_includes(text, here, idx)
    text = add_using_to_protos(text, using, stats)
    text = add_at_to_externs(text, stats)
    for rx, rep in RULES:
        text, n = rx.subn(rep, text)
        if n:
            stats[rx.pattern[:40]] += n

    def sbit(m):
        name, reg, bitn = m.group(1), m.group(2), int(m.group(3))
        base = int(reg, 0) if re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", reg) else sfr_addr.get(reg)
        if base is None:
            stats["sbit unresolved"] += 1
            return m.group(0)
        stats["sbit"] += 1
        return f"__sbit __at(0x{base + bitn:02X}) {name};"
    return SBIT.sub(sbit, text)


def cmd_port():
    if SRC.exists():
        shutil.rmtree(SRC)
    idx = build_name_index()
    sfr_addr, using_all, at_all = {}, {}, {}
    files = [p for p in SDK.rglob("*") if p.is_file() and ".git" not in p.parts]
    for p in files:                                          # pass 1: sfr addresses, `using`/`_at_` defs
        if p.suffix.lower() in SRC_EXT:
            t = p.read_text(errors="replace")
            for m in re.finditer(r"\bsfr\s+(\w+)\s*=\s*(0[xX][0-9A-Fa-f]+|\d+)\s*;", t):
                sfr_addr[m.group(1)] = int(m.group(2), 0)
            if not DROP_USING:
                for m in USING_DEF.finditer(t):
                    using_all.setdefault(m.group(1), set()).add(f" __using({m.group(2)})")
            for m in AT_DEF.finditer(t):
                at_all.setdefault(m.group(1), set()).add(m.group(2).strip())
            for m in INT_DEF.finditer(t):
                using_all.setdefault(m.group(1), set()).add(
                    f" __interrupt({m.group(2)})" + (f" __using({m.group(3)})" if m.group(3) and not DROP_USING else ""))
    # 7 chips share names: a name defined differently across files is NOT auto-propagated (wrong-chip risk)
    using = {k: next(iter(v)) for k, v in using_all.items() if len(v) == 1}
    AT_ADDR.clear()
    # numeric addresses only: a macro address (e.g. _EMBEDDED_DDCRAM_DDC3_ADDRESS) may be defined in one .c only
    AT_ADDR.update({k: next(iter(v)) for k, v in at_all.items()
                    if len(v) == 1 and re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", next(iter(v)))})
    for kind, d in (("using/interrupt", using_all), ("_at_", at_all)):
        conflicts = sorted(k for k, v in d.items() if len(v) > 1)
        if conflicts:
            log(f"{kind}: {len(conflicts)} names with conflicting definitions not propagated: "
                f"{', '.join(conflicts[:12])}{' ...' if len(conflicts) > 12 else ''}")
    stats = Counter()
    n = 0
    ov = [p for p in OVERLAY.rglob("*") if p.is_file()] if OVERLAY.exists() else []
    collect_messages(files, ov)
    for p in files:
        rel = p.relative_to(SDK)
        dst = SRC / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in SRC_EXT:
            raw = p.read_bytes().decode("latin-1")           # byte-preserving; comments are GBK/Big5
            out = rewrite(raw, p.parent, idx, sfr_addr, using, stats, str(rel))
            out = apply_wraps(str(rel), out, stats)
            out = apply_inserts(str(rel), out, stats)
            out = apply_subs(str(rel), out, stats)
            dst.write_bytes(out.encode("latin-1"))
            n += 1
        elif p.suffix.lower() in {".uv2", ".lin", ".a51", ".inc"}:
            shutil.copy2(p, dst)
    for p in ov:                                             # our files win over the SDK's
        dst = SRC / p.relative_to(OVERLAY)
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes().decode("latin-1")
        dst.write_bytes(rewrite(raw, (SDK / p.relative_to(OVERLAY)).parent, idx, sfr_addr, using, stats,
                                str(p.relative_to(OVERLAY)))
                        .encode("latin-1"))
        log(f"overlay: {p.relative_to(OVERLAY)}")
    log(f"port: {n} C/H files rewritten into {SRC}; sfr map {len(sfr_addr)} names; "
        f"{len(using)} fns with `using`; {len(ov)} overlay files")
    for k, v in stats.most_common():
        log(f"  rule {v:6d}  {k}")
    return 0


# ---------------- uVision2 project ----------------
def parse_uv2(uv2: Path, target=None):
    """C files + C51DEF + INCC5 + memory model of ONE target. Multi-target projects: groups/files whose
    `Options T,G,F` block has IncBld=0 are excluded for target T (only that target is ever built)."""
    txt = uv2.read_bytes().decode("latin-1")
    blocks = {(int(m.group(1)), int(m.group(2)), int(m.group(3))): m.group(5)
              for m in re.finditer(r"^Options (\d+),(\d+),(\d+)\s*// (Target|Group|File)[^\n]*\n(.*?)^EndOpt",
                                   txt, re.M | re.S)}
    tnames = {int(m.group(1)): m.group(2) for m in re.finditer(r"^Options (\d+),0,0\s*// Target '([^']+)'", txt, re.M)}
    if target is None:
        if len(tnames) > 1:
            sys.exit(f"{uv2.name} has targets {sorted(tnames.values())}: pass --target")
        t = next(iter(tnames), 1)
    else:
        t = next((k for k, v in tnames.items() if v == target), None)
        if t is None:
            sys.exit(f"target {target!r} not in {sorted(tnames.values())}")
    tb = blocks.get((t, 0, 0), txt)

    def excluded(g, f):
        for key in ((t, g, 0), (t, g, f)):
            b = blocks.get(key)
            if b and re.search(r"^\s*IncBld=0", b, re.M):
                return True
        return False
    files, nth = [], Counter()
    for m in re.finditer(r"^File (\d+),(\d+),<([^>]+)>", txt, re.M):
        g = int(m.group(1)); nth[g] += 1
        if m.group(2) == "1" and not excluded(g, nth[g]):
            files.append(m.group(3).replace("\\", "/"))
    defs = re.search(r"C51DEF \((.*)\)", tb)
    incs = re.search(r"INCC5 \((.*)\)", tb)
    defines = [d.replace(" ", "") for d in defs.group(1).split(",")] if defs and defs.group(1) else []
    inc = [i.replace("\\", "/") for i in incs.group(1).split(";")] if incs and incs.group(1) else []
    model = re.search(r"MODEL5=(\d)", tb)
    return files, defines, inc, int(model.group(1)) if model else 2


def norm_err(line):
    """Strip location/identifiers so equal problems bucket together."""
    s = re.sub(r"^.*?:\d+:\s*", "", line)
    s = re.sub(r"'[^']*'", "'X'", s)
    s = re.sub(r"\b0x[0-9a-fA-F]+\b|\b\d+\b", "N", s)
    return s.strip()[:120]


# Per-file compiler workarounds (basename -> extra flags); each one names its awto-sdcc issue
FILE_FLAGS = {
    "ScalerCommonIOSC.c": ["--noinduction"],   # trunk r17139 ICE validateOpType @ SDCCopt.c (awto-sdcc#3)
    # GCSE temps of the WD-ISR handlers spill to DATA (sloc, 23 B); direct RAM is the binding limit (#8)
    "ScalerCommonTimerFunction.c": ["--nogcse"],
}


_KC = None


def keil_compat():
    """--keil-compat, refusing a compiler without it: sdcc only warns on an unknown option, and the ~bit rule is gone."""
    global _KC
    if _KC is None:
        r = subprocess.run([SDCC, "--help"], capture_output=True, text=True, timeout=30)
        if "--keil-compat" not in r.stdout + r.stderr:
            sys.exit(f"{SDCC} has no --keil-compat (awto-sdcc#25): Keil ~bit semantics would be lost")
        _KC = ["--keil-compat"]
    return _KC


def sdcc_cmd(c: Path, uv2dir: Path, defines, incs, model):
    cmd = [SDCC, "-mmcs51", {0: "--model-small", 1: "--model-medium", 2: "--model-large"}.get(model, "--model-large"),
           "--std-sdcc11", "--opt-code-size",                 # flash is the constraint (Dan: smallest)
           "--fsigned-char",                                  # Keil: plain char signed; SDK SBYTE = char (awto-sdcc#3)
           "--norestartseqatomics",                           # trunk: else every ISR exits via sdcc_atomic_maybe_rollback
           "--nooverlay",                                     # `data` locals -> DSEG for sdcc_overlay (call-graph aware), not OSEG
           "--noinvariant",                                   # hoisted loop invariants become DATA spill slots (#8)
           "--nogenconstprop",                                # SDK polls ISR-set non-volatile flags; trunk folded the delay loop away (#23)
           *keil_compat(),                                    # Keil ~bit (replaces the ~bX -> !bX rule, #26), /0, loop re-read, eval order (awto-sdcc#25)
           f"-Wp-include,{SHIM / 'keil_compat.h'}", f"-I{SHIM}"]
    if awto_alias_header():
        cmd.append(f"-Wp-include,{awto_alias_header()}")
    cmd += [f"-I{(uv2dir / i).resolve()}" for i in incs]
    cmd += [f"-I{c.parent}"]
    cmd += [f"-D{d}" for d in defines]
    cmd += FILE_FLAGS.get(c.name, [])
    cmd += [f"-D_AWTO_NEW_{m.upper()}" for m in awto_modules()]   # per-module WRAPS compile-out (#68)
    cmd += T.CFLAGS_EXTRA                                      # --big-endian when AWTO_SDCC_BE=1
    cmd += os.environ.get("K2S_SDCC_EXTRA", "").split()      # experiments, e.g. --max-allocs-per-node N
    return cmd


ASM_MODE = False                               # compile --asm: emit .asm (-S) for the XDATA overlay pass


def _run_stage(cmd, **kw):
    """One compiler stage; returns (stdout + stderr, rc). Stages never share a stderr pipe, so lines never interleave."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=COMPILE_TIMEOUT, **kw)
        return r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return f"TIMEOUT after {COMPILE_TIMEOUT}s", 124


def _cache_dir() -> Path | None:
    """Compile cache shared by every worktree (one-file change = one compile): $AWTO_SDCC_CACHE, else the main checkout's
    tmp/sdcc-cache (git common dir's parent); AWTO_SDCC_CACHE=off disables it."""
    env = os.environ.get("AWTO_SDCC_CACHE")
    if env == "off":
        return None
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    return Path(r.stdout.strip()).parent / "tmp/sdcc-cache" if r.returncode == 0 else ROOT / "tmp/sdcc-cache"


CACHE = _cache_dir()
_COMPILER_ID = None
STATS = Counter()                              # cache_hit / cache_miss per compile run


def _compiler_id() -> str:
    """Compiler identity in the cache key: size + mtime of every file in the install's bin and libexec dirs."""
    global _COMPILER_ID
    if _COMPILER_ID is None:
        inst = Path(SDCC).resolve().parent.parent
        parts = [f"{p.relative_to(inst)}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
                 for d in ("bin", "libexec") for p in sorted((inst / d).rglob("*")) if p.is_file()]
        _COMPILER_ID = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return _COMPILER_ID


def _cache_key(pp: bytes, args: list) -> str:
    """Preprocessed source (worktree root replaced, so all worktrees share entries) + compiler flags (paths stripped) +
    compiler identity + output kind/name."""
    root = str(ROOT).encode()
    h = hashlib.sha256(pp.replace(root, b"@ROOT@"))
    h.update("\0".join(a.replace(str(ROOT), "@ROOT@") for a in args).encode())
    h.update(_compiler_id().encode())
    return h.hexdigest()


def compile_one(c: Path, uv2dir: Path, defines, incs, model):
    """Two stages: cpp (-E to a .i file), then the compiler proper on that file (--c1mode). In one `sdcc` run the cpp
    and the compiler write the same stderr concurrently and their lines interleave, splitting warning text (#51.7, #47).
    Message = cpp output, then compiler output. Stage 2 runs in the output dir with a bare -o: --c1mode names the
    .module from the -o path (bare = same name as a normal run)."""
    rel_dir = uv2dir.relative_to(SRC)
    out = WORK / ("asm" if ASM_MODE else "obj") / rel_dir / (c.stem + (".asm" if ASM_MODE else ".rel"))
    out.parent.mkdir(parents=True, exist_ok=True)
    pp = out.with_suffix(".i")
    base = sdcc_cmd(c, uv2dir, defines, incs, model)
    msg, rc = _run_stage(base + ["-E", "-o", str(pp), str(c)])
    if rc == 0:
        c1 = base + ["--c1mode"] + ([] if ASM_MODE else ["-c"]) + ["-o", out.name]
        key = _cache_key(pp.read_bytes(), c1) if CACHE else None
        hit = CACHE / f"{key}{out.suffix}" if key else None
        if hit and hit.exists() and hit.with_suffix(".msg").exists():
            root = str(ROOT).encode()
            out.write_bytes(hit.read_bytes().replace(b"@ROOT@", root))
            msg += hit.with_suffix(".msg").read_text(errors="replace").replace("@ROOT@", str(ROOT))
            STATS["cache_hit"] += 1
        else:
            with open(pp, "rb") as fh:
                m2, rc = _run_stage(c1, stdin=fh, cwd=out.parent)
            msg += m2
            if hit and rc == 0:                              # only successful compiles are cached (msg = c1 stage)
                CACHE.mkdir(parents=True, exist_ok=True)
                tmp = hit.with_name(hit.name + f".{os.getpid()}")
                tmp.write_bytes(out.read_bytes().replace(str(ROOT).encode(), b"@ROOT@"))
                hit.with_suffix(".msg").write_text(m2.replace(str(ROOT), "@ROOT@"))
                tmp.replace(hit)                             # entry visible only when complete (.msg first)
            STATS["cache_miss"] += 1
    pp.unlink(missing_ok=True)
    return str(c.relative_to(SRC)), rc, msg


# ---------------- clean-room mixed build (#65, #68) ----------------
SHIM_C = ROOT / "fw" / "awto" / "awto_shim" / "sdk_boundary.c"   # integrator-owned SDK<->clean bridge


def awto_sources():
    """{module: [.c]} of the clean tree: awto/<mod>/**/*.c (awto/include excluded). Empty = SDK-only build."""
    out = {}
    for p in sorted((CLEAN / "awto").glob("*/**/*.c")) + sorted((CLEAN / "awto").glob("*.c")):
        mod = p.relative_to(CLEAN / "awto").parts[0] if p.parent != CLEAN / "awto" else "core"
        if mod != "include":
            out.setdefault(mod, []).append(p)
    return out


def awto_alias_header():
    """SDK name -> clean symbol as a macro (thin boundary: callers reach the clean function directly, no wrapper hop).
    Only for modules present in the clean tree. Returns the header path or None."""
    mods = set(awto_modules())
    lines = [f"#define {a} {b}" for a, b, m in ALIASES if m in mods]
    if not lines:
        return None
    h = WORK / "awto_alias.h"
    h.parent.mkdir(parents=True, exist_ok=True)
    text = "/* generated by keil2sdcc.py from the ALIASES of fw/awto rules files */\n" + "\n".join(lines) + "\n"
    if not h.exists() or h.read_text() != text:
        h.write_text(text)
    return h


def awto_modules():
    return sorted(awto_sources())


def cmd_awto(jobs):
    """Compile clean sources (only awto/include + facts visible, SDK flags) and the shim (SDK includes) to asm in
    tmp/sdcc-port/asm/awto_<mod>_<file>.asm, where fw_build's select_lib picks them up as project modules."""
    (WORK / "asm").mkdir(parents=True, exist_ok=True)
    for old in (WORK / "asm").glob("awto_*.asm"):
        old.unlink()
    srcs = awto_sources()
    (WORK / "pin_common.txt").write_text("")
    if not srcs:
        log("awto: no clean sources (SDK-only build)"); return 0
    uv2 = SRC / "STD_FW_1P.Uv2"
    _, defines, incs, model = parse_uv2(uv2, "RL6449_Project")
    jobs_l = []                                              # (src, out, cmd)
    for mod, cs in srcs.items():
        for c in cs:
            cmd = [x for x in sdcc_cmd(c, uv2.parent, [], [], model) if not x.startswith(("-Wp-include", "-I"))]   # no Keil shim
            cmd += [f"-I{CLEAN / 'awto' / 'include'}", f"-I{CLEAN / 'facts'}", f"-I{c.parent}"]
            cmd += ["-D__data=__xdata"]            # direct RAM is full on this board (#8): clean DATA working sets live in XDATA
            jobs_l.append((c, WORK / "asm" / f"awto_{mod}_{c.stem}.asm", cmd))
    if SHIM_C.exists():                                      # may name SDK symbols: full project flags
        cmd = sdcc_cmd(SHIM_C, uv2.parent, defines, incs, model) + [f"-I{CLEAN / 'awto' / 'include'}", f"-I{SHIM_C.parent}"] \
            + [f"-I{CLEAN / 'awto' / m}" for m in srcs]
        jobs_l.append((SHIM_C, WORK / "asm" / "awto_shim_sdk_boundary.asm", cmd))

    def one(j):
        c, out, cmd = j
        try:
            r = subprocess.run(cmd + ["-S", "-o", str(out), str(c)], capture_output=True, text=True, errors="replace",
                               timeout=COMPILE_TIMEOUT)
            return c, r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return c, 124, f"TIMEOUT after {COMPILE_TIMEOUT}s"
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(one, jobs_l))
    for c, rc, msg in res:
        for l in msg.splitlines():
            log(f"awto {c.name}: {l}")
    # fw_build passes this to sdcc_bank --pin-common: names defined in the shim or in a clean module (#68: aliased hot leaves)
    sh = "\n".join(p.read_text(errors="replace") for p in sorted((WORK / "asm").glob("awto_*.asm")))
    (WORK / "pin_common.txt").write_text(",".join("_" + n for n in PIN_COMMON if re.search(rf"^_{n}:", sh, re.M)))
    bad = [c for c, rc, _ in res if rc]
    log(f"awto: modules {', '.join(awto_modules())}; {len(res) - len(bad)}/{len(res)} files ok")
    return 1 if bad else 0


def cmd_compile(uv2_rel, jobs, only, target):
    uv2 = SRC / uv2_rel
    files, defines, incs, model = parse_uv2(uv2, target)
    cs = [(uv2.parent / f).resolve() for f in files]
    if only:
        cs = [c for c in cs if only.lower() in str(c).lower()]
    missing = [c for c in cs if not c.exists()]
    cs = [c for c in cs if c.exists()]
    log(f"compile {uv2_rel}: {len(cs)} C files ({len(missing)} missing), defines {defines}, model {model}")
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda c: compile_one(c, uv2.parent, defines, incs, model), cs))
    ok = [r for r in res if r[1] == 0]
    bad = [r for r in res if r[1] != 0]
    hist, per_file = Counter(), {}
    for f, rc, msg in bad:
        errs = [l for l in msg.splitlines() if "error" in l.lower() or "TIMEOUT" in l]
        per_file[f] = errs[:20]
        for e in set(norm_err(l) for l in errs):
            hist[e] += 1
    (WORK / "logs").mkdir(parents=True, exist_ok=True)
    whist, wfile = Counter(), {}                             # warnings of every file, ok or not (#26)
    for f, _, msg in res:
        ws = [l for l in msg.splitlines() if "warning" in l.lower()]
        if ws:
            wfile[f] = ws
            for w in set(norm_err(l) for l in ws):
                whist[w] += 1
    wtxt = "".join(f"== {f}\n" + "\n".join(ws) + "\n" for f, ws in sorted(wfile.items()))
    (WORK / "warnings.txt").write_text(wtxt)
    (WORK / f"warnings-{Path(uv2_rel).stem}.txt").write_text(wtxt)    # per compile: scripts/warn_policy_check.py
    unreviewed = warn_gate(res)
    seg = Counter()                                          # area sizes summed over ok files
    for f, _, _ in ok:
        if ASM_MODE:                                         # XSEG split: globals vs fn locals/params
            asm = WORK / "asm" / uv2.parent.relative_to(SRC) / (Path(f).stem + ".asm")
            area, label = None, None
            for line in asm.read_text(errors="replace").splitlines():
                if line.startswith("\t.area"):
                    area = line.split()[1]
                elif area in ("XSEG", "DSEG", "OSEG", "ISEG") and re.match(r"^\w+::?$", line):
                    label = line
                elif area in ("XSEG", "DSEG", "OSEG", "ISEG") and line.strip().startswith(".ds") and label:
                    kind = ("global" if label.endswith("::") else
                            "sloc" if "sloc" in label else "local")
                    seg[f"{area}_{kind}"] += int(line.split()[1], 0)
            continue
        rel = WORK / "obj" / uv2.parent.relative_to(SRC) / (Path(f).stem + ".rel")
        for m in re.finditer(r"^A (\w+) size (\w+)", rel.read_text(errors="replace"), re.M):
            seg[m.group(1)] += int(m.group(2), 16)
    rep = {"uv2": uv2_rel, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ok": len(ok), "fail": len(bad),
           "missing": [str(m) for m in missing], "segments": dict(seg), "hist": hist.most_common(),
           "per_file": per_file, "warn_hist": whist.most_common(), "warn_files": len(wfile),
           "warn_unreviewed": unreviewed}
    log("segment bytes: " + ", ".join(f"{k}={v}" for k, v in seg.most_common() if v))
    (WORK / "report.json").write_text(json.dumps(rep, indent=1))
    log(f"compiled in {time.time() - t0:.0f}s: ok {len(ok)} fail {len(bad)}; cache {STATS['cache_hit']} hit / {STATS['cache_miss']} miss ({CACHE or 'off'})")
    print_hist(rep)
    for u in unreviewed:
        log(f"WARN-GATE unreviewed: {u}")
    if unreviewed:
        log(f"WARN-GATE: {len(unreviewed)} warning site(s) not in fw/warn_policy.tsv -> build fails (#26)")
    return 0 if not bad and not unreviewed else 1


WARN_RE = re.compile(r"^(.+?):(\d+)(?::\d+)?: warning(?: (\d+))?: (.*)$")


def warn_gate(res):
    """Every compiler/cpp warning must match a fw/warn_policy.tsv rule; returns the unmatched ones.
    Rule columns: pattern (regex on text) | file glob (src-relative) | line (* or N) | verdict | reason."""
    rules = []
    for ln in (ROOT / "fw" / "warn_policy.tsv").read_text().splitlines():
        if ln.strip() and not ln.startswith("#"):
            pat, glob, line, verdict, _reason = (ln.split("\t") + [""] * 5)[:5]
            if verdict == "ok":
                rules.append((re.compile(pat), glob, line))
    out = set()
    for _f, _rc, msg in res:
        for l in msg.splitlines():
            m = WARN_RE.match(l)
            if not m:
                continue
            path, line, text = m.group(1), m.group(2), m.group(4)
            rel = os.path.relpath(path, SRC) if path.startswith(str(SRC)) else path
            if not any(p.search(text) and fnmatch.fnmatch(rel, g) and lr in ("*", line) for p, g, lr in rules):
                out.add(f"{rel}:{line}: {text}")
    return sorted(out)


def print_hist(rep, n=25):
    log(f"top errors (files affected) for {rep['uv2']}: ok {rep['ok']} fail {rep['fail']}")
    for e, k in rep["hist"][:n]:
        log(f"  {k:5d}  {e}")
    log(f"warnings (files affected) in {rep.get('warn_files', 0)} files; full list tmp/sdcc-port/warnings.txt")
    for e, k in rep.get("warn_hist", [])[:n]:
        log(f"  {k:5d}  {e}")


def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "keil2sdcc.log").open("a")
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    if a[0] == "port":
        return cmd_port()
    if a[0] == "compile":
        jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count()
        only = a[a.index("--only") + 1] if "--only" in a else None
        target = a[a.index("--target") + 1] if "--target" in a else None
        global ASM_MODE, COMPILE_TIMEOUT
        ASM_MODE = "--asm" in a
        if "--timeout" in a:                                 # for measuring a slow file once
            COMPILE_TIMEOUT = int(a[a.index("--timeout") + 1])
        return cmd_compile(a[1], jobs, only, target)
    if a[0] == "awto":
        return cmd_awto(int(a[a.index("--jobs") + 1]) if "--jobs" in a else os.cpu_count())
    if a[0] == "pp":                                         # preprocess one file with a target's flags
        target = a[a.index("--target") + 1] if "--target" in a else None
        uv2 = SRC / a[1]
        files, defines, incs, model = parse_uv2(uv2, target)
        c = next((uv2.parent / f).resolve() for f in files if a[a.index("--only") + 1].lower() in f.lower())
        out = WORK / "pp" / (c.stem + ".i")
        out.parent.mkdir(parents=True, exist_ok=True)
        extra = ["-Wp-dM"] if "--macros" in a else []           # --macros: dump #defines instead
        r = subprocess.run(sdcc_cmd(c, uv2.parent, defines, incs, model) + extra + ["-E", str(c)],
                           capture_output=True, text=True, errors="replace", timeout=COMPILE_TIMEOUT)
        out.write_text(r.stdout)
        log(f"pp {c.name} -> {out} ({len(r.stdout)} chars) {r.stderr[-300:]}"); return r.returncode
    if a[0] == "report":
        print_hist(json.loads((WORK / "report.json").read_text()), 60); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
