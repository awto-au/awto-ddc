"""Compile-outs for SDK code our monitor never reaches (awto-ddc#65 step 1). Imported by keil2sdcc.py.

Switches (fw/overlay/Project/Header/RL6449_Project.h) default _OFF = code dropped; _ON restores the SDK code.
Sizes per item: issue #65 comment.
"""
FACTORY = "User/RTD Factory/Code/"
DPRX1 = "Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_DPRx1.c"
SEPT = "Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c"
NVRAM = "Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c"
NVRAM_H = "Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonNVRamCommonInclude.h"
GAMMA_H = "Panel/RTDColorDefaultTable/ColorTableInclude.h"
FN_END = r"^\}"
MX25L8006E_ROW = "{0x9F, 0xC2, 0x20, 0x14, 0x90, 0xC2, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},"   # JEDEC c22014 (MXIC)


def body_sub(stub: str):
    """Keep everything after the include under _AWTO_FACTORY; the #else part holds the stubs for the callers."""
    return lambda m: (m.group(1) + "#if(_AWTO_FACTORY == _ON)  // [keil2sdcc] sub\n" + m.group(2)
                      + "\n#else\n" + stub + "\n#endif\n")


DROP_WRAPS = [
    # DP PHY CTS (compliance tester only): the whole process, its PHY setup and the TP checks
    (DPRX1, r"^void ScalerDpRx1PhyCtsTp1SetPhy\(EnumDpNFCodeRef enumDpNFCodeRef\)$", FN_END, "_AWTO_DP_PHYCTS"),
    (DPRX1, r"^void ScalerDpRx1PhyCtsTp2SetPhy\(void\)$", FN_END, "_AWTO_DP_PHYCTS"),
    (DPRX1, r"^void ScalerDpRx1PhyCTS\(void\)$", FN_END, "_AWTO_DP_PHYCTS"),
    (DPRX1, r"^WORD ScalerDpRx1PhyCtsAction\(void\)$", FN_END, "_AWTO_DP_PHYCTS"),
    (SEPT, r"^bit ScalerDpRx1PhyCtsTp1Check\(void\)$", FN_END, "_AWTO_DP_PHYCTS"),
    (SEPT, r"^bit ScalerDpRx1PhyCtsTp2Check\(void\)$", FN_END, "_AWTO_DP_PHYCTS"),
    # NormalPreDetect: first match is the PHY CTS entry (the later one is a DFE init branch)
    (SEPT, r"^\s+if\(\(GET_DP_RX1_PHY_CTS_FLG\(\) == _TRUE\) \|\| \(ScalerDpRx1GetDpcdBitInfo\(0x00, 0x02, 0x70, _BIT7\) == _BIT7\)\)$",
     r"^    \}$", "_AWTO_DP_PHYCTS"),
    # flash: one chip (MX25L8006E); detection and the 77-row table go, the type becomes a constant (header SUB)
    (NVRAM, r"^BYTE g_ucFlashType = _FLASH_UNDETECT;", r"^BYTE g_ucFlashType = _FLASH_UNDETECT;", "_AWTO_FLASH_ALL"),
    (NVRAM, r"^void ScalerFlashDetectFlashType\(void\)$", FN_END, "_AWTO_FLASH_ALL"),
    # demo gamma LUTs: 1.8 / 2.0 / 2.4 alias the 2.2 table (SUB below)
    (GAMMA_H, r"^BYTE __code tLUTGAMMA_18_TABLE\[\] =", r"^\};", "_AWTO_GAMMA_ALL"),
    (GAMMA_H, r"^BYTE __code tLUTGAMMA_20_TABLE\[\] =", r"^\};", "_AWTO_GAMMA_ALL"),
    (GAMMA_H, r"^BYTE __code tLUTGAMMA_24_TABLE\[\] =", r"^\};", "_AWTO_GAMMA_ALL"),
]

DROP_SUBS = [
    (FACTORY + "RTDFactoryMode.c", r'(#include "UserCommonInclude.h"\n)(.*)\Z',
     body_sub("void RTDFactoryMenuOperation(void) {}\nvoid RTDFactoryMainMenu(void) {}"), 1),
    (FACTORY + "RTDFactoryFunction.c", r'(#include "UserCommonInclude.h"\n)(.*)\Z',
     body_sub("void RTDFactoryPanelUsedTimer(void) {}"), 1),
    (NVRAM, r"tFlashInformation\[g_ucFlashType\]", lambda m: "tFlashInformation[_AWTO_FLASH_IDX]", 37),
    (NVRAM, r"StructFlashInformation __code tFlashInformation\[\] =\n\{.*?\n\};",
     lambda m: ("#if(_AWTO_FLASH_ALL == _ON)  // [keil2sdcc] sub\n%s\n#else\nStructFlashInformation __code tFlashInformation[] =\n{\n    %s\n};\n#endif"
                % (m.group(0), MX25L8006E_ROW)), 1),
    (NVRAM_H, r"extern BYTE g_ucFlashType;",
     lambda m: "#if(_AWTO_FLASH_ALL == _ON)  // [keil2sdcc] sub\nextern BYTE g_ucFlashType;\n#else\n#define g_ucFlashType (_FLASH_MX25L8006E)\n#endif", 1),
    (GAMMA_H, r"(BYTE __code \* __code tGAMMA_TABLE\[\] =\n\{\n    tLUTGAMMA_18_TABLE,)",
     lambda m: ("#if(_AWTO_GAMMA_ALL == _OFF)  // [keil2sdcc] sub\n#define tLUTGAMMA_18_TABLE tLUTGAMMA_22_TABLE\n"
                "#define tLUTGAMMA_20_TABLE tLUTGAMMA_22_TABLE\n#define tLUTGAMMA_24_TABLE tLUTGAMMA_22_TABLE\n#endif\n" + m.group(1)), 1),
]
