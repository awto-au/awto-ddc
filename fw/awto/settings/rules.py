# settings (#67): the registry, our menu, DDC/CI VCP and the NVRAM record (awto-rtdfw awto/settings, awto/nvram).
# Glue (SDK side): glue.inc (RTD2014Osd.c), glue_key.inc (RTD2014Key.c); ids: fw/overlay/Project/Header/AwtoSetIds.h
# (scripts/settings_gen.py), included by RL6449_Project.h (with the hook prototypes). Glue goes at the end of
# each file and every hook is one line, so SDK line numbers (fw/warn_policy.tsv keys) move as little as possible.
# DDC/CI: the #60 spare-engine 0x37 handler (fw/sdcc/awto_ddcci.inc) calls the registry (AwtoDdcRegistry); the SDK
# DDC/CI handler stays off. Overlay readers use AWTO_SET(NAME) under #ifdef _AWTO_NEW_SETTINGS: panel T1-T6 (AWTO_LTM270FL01.h), T3 own pattern,
# DDC/CI / debug link, keep idle inputs (RL6449_Project.h), fast switch (fw/sdcc/awto_fastsw.inc).
import os
from pathlib import Path

_CLEAN = Path(os.environ.get("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw"))
_HERE = Path(__file__).resolve().parent
OSD = "User/RTD Series/RTD2014Osd/Code/"
WRAPS = []
INSERTS = []
SUBS = []


def _txt(name):
    return (_HERE / name).read_text().rstrip("\n")


if (_CLEAN / "awto" / "settings").is_dir():
    INSERTS = [
        (OSD + "RTD2014Osd.c", r"^#endif//#if\(_OSD_TYPE == _REALTEK_2014_OSD\)$",
         _txt("glue.inc").replace('#include "glue_nv.inc"', _txt("glue_nv.inc"))),      # at the end: no SDK line moves
        (OSD + "RTD2014OsdDisplay.c", r"^\s*SET_OSD_IN_FACTORY_MENU_STATUS\(_FALSE\);",
         "    AwtoMenuForget();", r"^void OsdDispDisableOsd\(void\)$"),
        (OSD + "RTD2014Key.c", r"^#endif//#if\(_OSD_TYPE == _REALTEK_2014_OSD\)$", _txt("glue_key.inc")),
        ("Kernel/System/Code/SysMain.c", r"^\s*UserCommonInterfaceOsdHandler\(\);",
         "            AWTO_SET_LOOP();"),       # inline time check: no banked call on most passes
        ("User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c",
         r"^\s*UserCommonInterfaceDdcciSwitch\(GET_OSD_DDCCI_STATUS\(\), UserCommonNVRamGetSystemData\(_SEARCH_PORT\)\);",
         "    AwtoSetInit();"),
    ]

# #151 one store (glue_nv.inc): every SDK item save is deferred to the flush gate; same-line subs (no SDK line moves).
UI = "User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c"
NVS = "Kernel/User Common Function/Code/UserCommonNVRamSystem.c"
if (_CLEAN / "awto" / "settings").is_dir():
    SUBS = [
        # audio (docs/audio.md): volume % -> DVC gain through our dB table; muted while the mode is not ACTIVE / DISPLAY_SETTING
        ("User/RTD Series/RTD2014Function/Code/RTD2014UserAdjust.c",
         r"(WORD UserAdjustAudioVolumeMapping\(BYTE ucVolume\)\n\{).*?\n\}\n",
         lambda m: m.group(1) + "\n    return AwtoAudioGain(ucVolume);  // [keil2sdcc] sub\n}\n", 1),
        ("User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c",
         r"(bit UserInterfaceGetAudioMuteStatus\(void\)\n\{\n    )return GET_OSD_VOLUME_MUTE\(\);",
         lambda m: m.group(1) + "return (GET_OSD_VOLUME_MUTE() || AWTO_AUDIO_HOLD());  // [keil2sdcc] sub", 1),
        # audio: the Dahua firmware enables the headphone output only (06C0 = DF after OutputSwitch in its trace); SDK default = both
        ("User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c",
         r"(EnumAudioDACOutput UserInterfaceGetAudioDACOutput\(void\)\n\{\n).*?\n\}\n",
         lambda m: m.group(1) + "    return _AUDIO_DAC_OUTPUT_HEADPHONE;  // [keil2sdcc] sub\n}\n", 1),
        (NVS, r"(bit UserCommonFlashSaveItem\(EnumFlashItemIDType enumItemID, BYTE \*pucData, BYTE ucLength\)\n\{.*?"
              r"    if\(ucLength > \(_DATA_ITEM_LENGTH - 2\)\)\n    \{\n        return _FALSE;\n    \})",
         lambda m: m.group(1) + " { extern bit AwtoNvDefer(BYTE ucId, BYTE *pucData); if(AwtoNvDefer(LOBYTE(enumItemID), pucData) == _TRUE) "
                                "{ return _TRUE; } }  // [keil2sdcc] sub #151: the flush gate writes it", 1),
        (NVS, r"(    // Write __data\n    UserCommonFlashWrite\(_SYSTEM_EEPROM_EMULATION_FLASH_BANK, usPageAddr \+ g_pusFlashAddrArr\[ucPageID\] \* "
              r"_DATA_ITEM_LENGTH, _DATA_ITEM_LENGTH, pucWholeItem\);)",
         lambda m: m.group(1) + " AWTO_NV_ITEM_WR();  // [keil2sdcc] sub #151", 1),
        (NVS, r"(            RTDFlashMoveData\(ucPageID, pucWholeItem\);)", lambda m: m.group(1) + " AWTO_NV_ITEM_WR();  // [keil2sdcc] sub #151", 1),
        # F: the first ACTIVE after a switch keeps the live port in RAM only; the selector stores the input (AwtoNvCommitSel)
        (UI, r"(        AwtoSwEvent\(AWTO_SW_EV_PROBE, 7\);  // \[keil2sdcc\] insert\n)        UserCommonNVRamSaveSystemData\(\);",
         lambda m: m.group(1) + "        // awto #151: no save here (KVM / search switch)  // [keil2sdcc] sub", 1),
        # power off (key, PS -> off) and power-saving entry (panel off): every dirty item now, panel time with them
        (UI, r"(_MONITOR_POWER_STATUS, _OFF\);\n\n            // Save System Power Status Data.\n            UserCommonNVRamSaveSystemData\(\);)",
         lambda m: m.group(1) + " AwtoNvFlush();  // [keil2sdcc] sub #151", 2),
        (UI, r"(            UserInterfaceKeyPadLedControl\(_LED_POWER_SAVING\);\n\n            // Panel pown down.\n"
             r"            UserCommonInterfacePanelPowerAction\(_PANEL_OFF\);)",
         lambda m: m.group(1) + " AwtoNvFlush();  // [keil2sdcc] sub #151", 1),
    ]
