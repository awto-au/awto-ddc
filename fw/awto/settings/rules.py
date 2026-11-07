# settings (#67): the registry, our menu, DDC/CI VCP and the NVRAM record (awto-rtdfw awto/settings, awto/nvram).
# Glue (SDK side): glue.inc (RTD2014Osd.c), glue_ddcci.inc (RTD2014Ddcci.c), glue_key.inc (RTD2014Key.c); ids: fw/overlay/Project/Header/AwtoSetIds.h
# (scripts/settings_gen.py), included by RL6449_Project.h (with the hook prototypes). Glue goes at the end of
# each file and every hook is one line, so SDK line numbers (fw/warn_policy.tsv keys) move as little as possible.
# Overlay readers use AWTO_SET(NAME) under #ifdef _AWTO_NEW_SETTINGS: panel T1-T6 (AWTO_LTM270FL01.h), T3 own pattern,
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
        (OSD + "RTD2014Osd.c", r"^#endif//#if\(_OSD_TYPE == _REALTEK_2014_OSD\)$", _txt("glue.inc")),      # at the end: no SDK line moves
        (OSD + "RTD2014Osd.c", r"^\s*if\(GET_OSD_IN_FACTORY_MENU_STATUS\(\) == _TRUE\)$",
         "        if(AwtoMenuKeyHook() == _TRUE) { return; }", r"^void RTDOsdSystemFlowProc\(void\)$"),
        (OSD + "RTD2014OsdDisplay.c", r"^\s*SET_OSD_IN_FACTORY_MENU_STATUS\(_FALSE\);",
         "    AwtoMenuForget();", r"^void OsdDispDisableOsd\(void\)$"),
        (OSD + "RTD2014Ddcci.c", r"^#endif // End of #if\(_OSD_TYPE == _REALTEK_2014_OSD\)$", _txt("glue_ddcci.inc")),
        (OSD + "RTD2014Key.c", r"^#endif//#if\(_OSD_TYPE == _REALTEK_2014_OSD\)$", _txt("glue_key.inc")),
        ("Kernel/System/Code/SysMain.c", r"^\s*UserCommonInterfaceOsdHandler\(\);",
         "            AWTO_SET_LOOP();"),       # inline time check: no banked call on most passes
        ("User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c",
         r"^\s*UserCommonInterfaceDdcciSwitch\(GET_OSD_DDCCI_STATUS\(\), UserCommonNVRamGetSystemData\(_SEARCH_PORT\)\);",
         "    AwtoSetInit();"),
    ]
    SUBS = [
        # #67 host key hold (glue_key.inc): ORed into the scanned key state, both PCB_KEY_STATE branches of RTDKeyScan
        (OSD + "RTD2014Key.c", r"PCB_KEY_STATE\(ucVoltage0, ucVoltage1, ucVoltage2, ucVoltage3, ucKeyState\);",
         lambda m: m.group(0) + " ucKeyState |= AWTO_KEY_HOLD();  // [keil2sdcc] sub", 2),
        # boot logo row + its time (was SEC(3)); logo off = the logo-end event right away
        (OSD + "RTD2014Osd.c", r"ScalerTimerActiveTimerEvent\(SEC\(3\), _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO\);",
         lambda m: "ScalerTimerActiveTimerEvent((AWTO_SET(LOGO) != 0) ? AWTO_SET(LOGO_MS) : 0, _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO);  // [keil2sdcc] sub", 1),
        (OSD + "RTD2014Osd.c", r"(\n\s*)OsdDispShowLogo\(\);",
         lambda m: m.group(1) + "if(AWTO_SET(LOGO) != 0) { OsdDispShowLogo(); }  // [keil2sdcc] sub", 1),
        (OSD + "RTD2014Ddcci.c", r"(void RTDDdcciGetVCPFeature\(void\)\n\{.*?)\n    switch\(g_pucDdcciRxBuf\[_DDCCI_SOURCE_OPCODE\]\)",
         lambda m: m.group(1) + "\n    if(AwtoVcpGetHook() == _FALSE)  // [keil2sdcc] sub\n    switch(g_pucDdcciRxBuf[_DDCCI_SOURCE_OPCODE])", 1),
        (OSD + "RTD2014Ddcci.c", r"    if\(RTDDdcciSetVCPFeatureCheck\(\) == _FAIL\)",
         lambda m: "    if(AwtoVcpSetHook() == _TRUE)  // [keil2sdcc] sub\n    {\n        UserCommonDdcciInitTx();\n    }\n"
                   "    else if(RTDDdcciSetVCPFeatureCheck() == _FAIL)", 1),
    ]
