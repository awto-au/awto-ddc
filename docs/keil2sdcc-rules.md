# keil2sdcc rules: what each removed rule did (awto-ddc#162)

- Until `wb-p14ui-ownbase`, `scripts/keil2sdcc.py` rewrote the Realtek SDK mirror on every build: a mechanical Keil->SDCC port, then INSERT / SUB / WRAP rules that changed what the firmware does (plus `fw/awto/*/rules.py` and `keil2sdcc_drops.py`).
- Now `fw/sdk/` is the SDK as our source, in SDCC form. Every row below is a plain edit there, marked `// awto: <what> (#issue)`; `git log -- fw/sdk` shows import, overlay merge, then the edits.
- The build only tokenises DebugMessage (`scripts/msg_tokenise.py`, ids pinned in `fw/msgids.tsv`) and compiles (`scripts/fw_compile.py`). Gate `rules` (`scripts/sdk_rules_lint.py`) fails if a patch path comes back.
- Kind: `behaviour` = adds or changes what the firmware does (probes, awto calls, removed features, board/panel registration, config). `mechanical` = size switch or SDCC-only fix (defaults leave the SDK code in place).
- Rows are the `// awto:` spots of a file with the same note (`spots` = how many). Tool of the migration: `scripts/sdk_own.py` (deleted after the migration, in git history; rules read from tag `wb-p14ui-ownbase`).

## Mechanical import (kept in `scripts/sdk_import.py`, one-off, not part of the build)

| rule | does |
|---|---|
| `code`/`data`/`idata`/`xdata` qualifiers | `__code`/`__data`; storage-first pointer declarations; `data pData[]` scratch to xdata (IRAM is the binding limit, #8) |
| `sfr`, `sfr16`, `sbit`, `_at_`, `interrupt`, `using` | `__sfr __at`, `__sbit __at`, `__at(addr)`, `__interrupt(n)`; register banks dropped |
| `__at` on externs, interrupt prototypes | SDCC needs the definition's attributes on the declaration |
| pragmas (OT, OPTIMIZE, REGPARMS, ...) | dropped |
| ISR flags `g_bNotifyTimer2Int`, `g_bWDTimer2Update` | `volatile bit` (SDCC folds the poll otherwise, #26) |
| include case fixing, `\\ ` + spaces, nested `/*` | Windows case-insensitive includes; cpp warnings |

## Behaviour and size-switch edits (now plain edits in `fw/sdk`)

| file | class | what | issue | spots |
|---|---|---|---|---|
| `Kernel/Common/Pcb_List.h` | behaviour | our board id 0x4F | #7 | 1 |
| `Kernel/Common/Project.h` | behaviour | customer (Beacon/RL6432) layer redefined _PCB_TYPE/_PANEL_TYPE for every target -> Beacon only | #8 | 1 |
| `Kernel/Common/Scaler_Test_Function.h` | behaviour | audio test build (-D_AWTO_AUDIO_TEST) |  | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Audio.c` | behaviour | RL6449 has no D1 internal-generator implementation |  | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Audio.c` | behaviour | audio test build (-D_AWTO_AUDIO_TEST) |  | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_DPRx1.c` | mechanical | size switch: DP PHY compliance test code | #65 | 4 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_DisplayDPTx.c` | behaviour | watchdog feed per ms in the eDP HPD poll | #150 | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c` | behaviour | debug IIC engine follows the active port | #28 | 2 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Mcu.c` | mechanical | DDC RAM arrays defined here, extern hidden (one __at per array) | #8 | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Power.c` | behaviour | fast boot: no waits for rails this board never switches | #63 | 3 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_TMDSRx2.c` | behaviour | keep SCDC 0x20 across a TMDS initial (host 1/40 ratio) | #78 | 1 |
| `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_TMDSRx3.c` | behaviour | keep SCDC 0x20 across a TMDS initial (host 1/40 ratio) | #78 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c` | behaviour | debug IIC engine follows the active port | #28 | 4 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c` | behaviour | debug slave answers in the EXINT1 ISR | #38 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c` | behaviour | host-silence timeout of the debug wait | #56 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonDebug.c` | mechanical | tokenised message functions live in the debug module | #26 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c` | behaviour | M2PLL re-entry keeps the calibrated delay counts | #54 | 2 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c` | behaviour | delay calibration | #53 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonMcu.c` | behaviour | no watchdog disable (three ORed enables; never cleared) | #138 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c` | behaviour | NVRAM save timing in the sync log | #150 | 2 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c` | behaviour | watchdog feed instead of the SDK flash poke | #138 | 3 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c` | mechanical | size switch: one flash chip, detection and table dropped | #65 | 3 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonSync.c` | behaviour | idle TMDS MAC stays powered | #60 | 2 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonSync.c` | behaviour | idle receivers stay powered (AWTO_IDLE_RX_OFF) | #60 | 60 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonTimerFunction.c` | behaviour | WD-timer event table replaced by the Timer0 scheduler | #138 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonTimerFunction.c` | behaviour | WD-timer functions in fw/sdcc/awto_t0ev.inc | #138 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonTimerFunction.c` | behaviour | restart the pending Timer0 tick at the new clock | #138 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonTimerFunction.c` | behaviour | watchdog feed per ms in a bounded wait | #131 | 2 |
| `Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonMcuInclude.h` | mechanical | DDC RAM arrays defined here, extern hidden (one __at per array) | #8 | 2 |
| `Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonNVRamCommonInclude.h` | mechanical | size switch: one flash chip, detection and table dropped | #65 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Lib/Code/ScalerCommonNVRam/ScalerCommonFlashRead.c` | behaviour | watchdog poke in a flash loop | #150 | 1 |
| `Kernel/Scaler/ScalerCommonFunction/Lib/Code/ScalerCommonNVRam/ScalerCommonFlashWrite.c` | behaviour | watchdog poke in a flash loop | #150 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c` | behaviour | DP Rx1 scan step mark | #60 | 8 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c` | behaviour | DP Rx1 two-frame waits = 2 x the measured frame | #60 | 3 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c` | behaviour | power-saving wake: counted, not returned | #144 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerDPRx1_SeptPhy.c` | mechanical | size switch: DP PHY compliance test code | #65 | 3 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerDisplay.c` | behaviour | T3 wait with the delay calibration inside (#53) */; |  | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c` | behaviour | 4K60 measurement ring | #26 | 13 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c` | behaviour | FRC memory BW also with the CheckMDomain debug messages | #37 | 2 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c` | behaviour | exact input frequencies | #34 | 3 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMcu.c` | behaviour | boot log clock carried over the WDT counter clear | #29 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMcu.c` | behaviour | boot stage 2 | #34 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMeasure.c` | behaviour | exact input frequencies | #34 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerMeasure.c` | behaviour | fast switch: scaler side | #60 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c` | behaviour | 4K60 measurement ring | #26 | 4 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c` | behaviour | DHtotal fine-tune: one pass, no debounce loop | #26 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerPLL.c` | behaviour | last-line fine-tune off for this function only | #26 | 2 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerTMDSRx2_SeptPhy.c` | behaviour | power-saving wake: SDK predetect wait kept only without _AWTO_PS_WAKE | #144 | 2 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerTMDSRx2_SeptPhy.c` | behaviour | power-saving wake: counted, not returned | #144 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerTMDSRx3_SeptPhy.c` | behaviour | power-saving wake: SDK predetect wait kept only without _AWTO_PS_WAKE | #144 | 2 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerTMDSRx3_SeptPhy.c` | behaviour | power-saving wake: counted, not returned | #144 | 1 |
| `Kernel/Scaler/ScalerFunction/Code/ScalerTimerFunction.c` | behaviour | watchdog feed per ms in a bounded wait | #131 | 1 |
| `Kernel/Scaler/ScalerFunction/Header/ScalerMDomainInclude.h` | behaviour | FRC memory BW also with the CheckMDomain debug messages | #37 | 1 |
| `Kernel/System/Code/SysInt.c` | behaviour | Timer0 event flag test in EXINT0 | #138 | 1 |
| `Kernel/System/Code/SysInt.c` | behaviour | diag hook in the ISR | #23 | 1 |
| `Kernel/System/Code/SysJudge.c` | behaviour | main-loop split + L1/L2 hold in the judge check | #78 | 1 |
| `Kernel/System/Code/SysJudge.c` | behaviour | pulse the HDMI HPD of a stuck TMDS port | #78 | 1 |
| `Kernel/System/Code/SysJudge.c` | behaviour | switch-log probe | #60 | 3 |
| `Kernel/System/Code/SysJudge.c` | behaviour | switch-log probe: which SysJudgeCheckStatus check failed | #60 | 4 |
| `Kernel/System/Code/SysMain.c` | behaviour | 4K60 measurement ring | #26 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | 4K60 measurement ring init | #26 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | GPIO change poll | #39 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | IP over DDC | #80 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | KVM input select + DDC/CI engines | #60 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | boot stage | #63 | 2 |
| `Kernel/System/Code/SysMain.c` | behaviour | boot-stage / timing diagnostics | #23 | 4 |
| `Kernel/System/Code/SysMain.c` | behaviour | diag block defined in SysMain.c, extern elsewhere | #23 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | early panel VDD (AwtoPanelVddEarly) | #63 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | main-loop cost profile | #75 | 12 |
| `Kernel/System/Code/SysMain.c` | behaviour | main-loop split: cable detection every AWTO_SLOW_MS | #75 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | main-loop watchdog | #131 | 2 |
| `Kernel/System/Code/SysMain.c` | behaviour | one key path | #129 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | power LED | #23 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | power-saving wake poll between handlers | #144 | 14 |
| `Kernel/System/Code/SysMain.c` | behaviour | settings registry / menu glue | #67 | 1 |
| `Kernel/System/Code/SysMain.c` | behaviour | slow-segment mark | #60 | 11 |
| `Kernel/System/Code/SysMain.c` | behaviour | switch timeline poll | #60 | 5 |
| `Kernel/System/Code/SysMain.c` | behaviour | sync / power-on log | #139 | 2 |
| `Kernel/System/Code/SysMode.c` | behaviour | backlight off becomes a blank | #60 | 2 |
| `Kernel/System/Code/SysMode.c` | behaviour | store the fast-switch cache at the first ACTIVE | #60 | 1 |
| `Kernel/System/Code/SysMode.c` | behaviour | switch-log probe | #60 | 9 |
| `Kernel/System/Code/SysMode.c` | behaviour | sync / power-on log | #139 | 2 |
| `Kernel/System/Code/SysSource.c` | behaviour | cached fast input switch | #60 | 1 |
| `Kernel/System/Code/SysSource.c` | behaviour | main-loop split: cable detection every AWTO_SLOW_MS | #75 | 1 |
| `Kernel/System/Code/SysSource.c` | behaviour | no HDMI hot-plug pulse on an input switch | #60 | 1 |
| `Kernel/System/Code/SysSource.c` | behaviour | slow-segment mark | #60 | 4 |
| `Kernel/System/Code/SysSource.c` | behaviour | switch-log probe | #60 | 1 |
| `Kernel/System/Code/SysSource.c` | behaviour | sync / power-on log | #139 | 2 |
| `Kernel/System/Code/SysTimer.c` | behaviour | 4K60 measurement ring | #26 | 1 |
| `Kernel/System/Code/SysTimer.c` | behaviour | Timer0 event scheduler tick | #138 | 1 |
| `Kernel/System/Code/SysTimer.c` | behaviour | diag hook in the ISR | #23 | 1 |
| `Kernel/System/Code/SysTimer.c` | behaviour | no watchdog work in the 1 ms tick | #138 | 1 |
| `Kernel/System/Code/SysTimer.c` | behaviour | watchdog warning (capture + reset) | #138 | 1 |
| `Kernel/User Common Function/Code/UserCommonInterface.c` | behaviour | backlight off becomes a blank | #60 | 1 |
| `Kernel/User Common Function/Code/UserCommonInterface.c` | behaviour | eDP power-up stage | #63 | 5 |
| `Kernel/User Common Function/Code/UserCommonInterface.c` | behaviour | key panels follow an OSD reset | #129 | 1 |
| `Kernel/User Common Function/Code/UserCommonInterface.c` | behaviour | switch-log probe: eDP panel-on phase | #78 | 6 |
| `Kernel/User Common Function/Code/UserCommonInterface.c` | behaviour | switch-log: panel power action | #60 | 1 |
| `Kernel/User Common Function/Code/UserCommonNVRamSystem.c` | behaviour | NVRAM item write notes the flush gate | #151 | 2 |
| `Kernel/User Common Function/Code/UserCommonNVRamSystem.c` | behaviour | no HDMI hot-plug pulse on an input switch | #60 | 1 |
| `Kernel/User Common Function/Code/UserCommonNVRamSystem.c` | behaviour | the flush gate writes it | #151 | 1 |
| `Kernel/User Common Function/Header/EDID/EdidTableD1.h` | behaviour | D1 EDID = scripts/fw_edid_tables.py output (make_edid.py, per-unit serial); docs/edid-fix.md |  | 1 |
| `Kernel/User Common Function/Header/EDID/EdidTableD2.h` | behaviour | D2 EDID = scripts/fw_edid_tables.py output (make_edid.py, per-unit serial); docs/edid-fix.md |  | 1 |
| `Kernel/User Common Function/Header/EDID/EdidTableD3.h` | behaviour | D3 EDID = scripts/fw_edid_tables.py output (make_edid.py, per-unit serial); docs/edid-fix.md |  | 1 |
| `Panel/RTDColorDefaultTable/ColorTableInclude.h` | mechanical | size switch: demo gamma tables alias the 2.2 table | #65 | 4 |
| `Panel/User_Panel_Include.h` | behaviour | include our panel | #7 | 1 |
| `Panel/User_Panel_List.h` | behaviour | our panel id 0x3D | #7 | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | A0/D0 are not wired; PRI_0 is also the NVRAM default port, i.e. the boot DDC-CI channel | #8 | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | AUX0 pins are GPIO in old fw |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | P8.2 role unproven, not driven (#53.4) |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | P8.4 is a board power-state enable, not an LED. LED2..5 remain unproven/no-op. |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | no EEPROM / IIC device on the HW IIC pins 210/211 (GPIO here), #53.3 |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | no EEPROM, PA.6 is not driven (#53.3) |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | no VGA |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | no amp-mute pin in the Dahua fw access table (docs/audio.md) [fw] |  | 1 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | old fw serves all 3 EDIDs from code (docs/edid-fix.md) |  | 3 |
| `Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` | behaviour | settings are flash-emulated (#53.3) |  | 1 |
| `Pcb/User_Pcb_Include.h` | behaviour | include our board | #7 | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | DP-out port only; eDP panel uses ScalerDisplayDPTx (independent) |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | Samsung LTM270FL01, eDP HBR2 x4 on TX1 (fw/sdk/Panel/AWTO_LTM270FL01.h, #7) |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | board = 1 DP + 2 HDMI + eDP panel (Dan, awto-ddc#7). Placeholder until our own PCB header. |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | cut (Dan 2026-11-04, #8) |  | 8 |
| `Project/Header/RL6449_Project.h` | behaviour | needed by EEPROM emulation |  | 2 |
| `Project/Header/RL6449_Project.h` | behaviour | no DP-out/daisy chain (demo _ON; ~0.9 KB XDATA) |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | no EEPROM (EEIIC pins GPIO); old fw records at bank 15 p11-12 |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | no VGA port (A0 none); demo default was _ON |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | old fw gamma __data at bank 14 pages 0-2 (1 MiB flash) |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | unused (FreeSync II off); kept inside 1 MiB |  | 1 |
| `Project/Header/RL6449_Project.h` | behaviour | unused on this board | #7 | 11 |
| `User/RTD Factory/Code/RTDFactoryFunction.c` | mechanical | size switch: factory menu | #65 | 1 |
| `User/RTD Factory/Code/RTDFactoryMode.c` | mechanical | size switch: factory menu | #65 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserAdjust.c` | behaviour | volume through our dB table | #93 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | T3 wait with the delay calibration inside (#53) */; |  | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | flush every dirty NVRAM item now | #151 | 3 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | headphone output only | #93 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | load the debug-message switch from NVRAM | #74 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | mute while the mode is not ACTIVE / DISPLAY_SETTING | #93 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | no NVRAM save at the first ACTIVE after a switch | #151 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | settings registry / menu glue | #67 | 1 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | switch-log probe | #60 | 2 |
| `User/RTD Series/RTD2014Function/Code/RTD2014UserInterface.c` | behaviour | switch-log: blank | #60 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Ddcci.c` | behaviour | IP over DDC | #80 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Ddcci.c` | behaviour | KVM input select + DDC/CI engines | #60 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Ddcci.c` | behaviour | input select through the fast path | #60 | 7 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Ddcci.c` | behaviour | our ports: D1 DP, D2 / D3 HDMI | #60 | 3 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Key.c` | behaviour | key / test / GPIO code | #129 | 4 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Key.c` | behaviour | removed; keys: fw/sdcc/awto_keys.inc | #129 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Key.c` | behaviour | settings registry / menu glue | #67 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014NVRamOsd.c` | behaviour | D1 DP version default _AWTO_DP_D1_VERSION (#28) */ : 1; |  | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014NVRamOsd.c` | behaviour | NVRAM checksum from RL6449_Project.h (old data reloads defaults) | #8 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014NVRamOsd.c` | behaviour | NVRAM save timing in the sync log | #150 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | Realtek menu built out | #120 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | boot console instead of the logo | #144 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | boot logo removed | #144 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | boot panel power-on | #144 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | info pop-up time _AWTO_INFO_POPUP_SEC |  | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | our source selector | #134 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | removed; keys: fw/sdcc/awto_keys.inc | #129 | 4 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | settings registry / menu glue | #67 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | sleep rule in AwtoSourceOpen (AwtoSrcSleepArm) | #139 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014Osd.c` | behaviour | switch-log probe | #60 | 2 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | OSD text layer, cards and panels | #134 | 4 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | an OSD hold (debug pop-up) blocks the disable | #28 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | boot logo removed | #144 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | main-loop watchdog | #131 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | menu forgets a closed OSD | #67 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | removed; message cards: fw/sdcc/awto_osdcard.inc | #124 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c` | behaviour | removed; source selector: fw/sdcc/awto_osdcard.inc | #134 | 3 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_1.c` | behaviour | early panel VDD (AwtoPanelVddEarly) | #63 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_1.c` | behaviour | no input icons (the selector is text) | #134 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontDynamicIcon_1.c` | behaviour | our info mark replaces the SDK bubble | #46 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontProp.c` | behaviour | info pop-up string, no reader | #124 | 7 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFontProp.c` | behaviour | per character (string terminator bound) | #150 | 1 |
| `User/RTD Series/RTD2014Osd/Code/RTD2014OsdFunc.c` | behaviour | Realtek menu built out | #120 | 1 |
| `User/RTD Series/RTD2014Osd/Header/RTD2014Include.h` | behaviour | DDC port in Realtek debug mode / spare engines | #13 | 1 |
| `User/RTD Series/RTD2014Osd/Header/RTD2014NVRamOsd.h` | behaviour | spare bit: debug messages switch | #74 | 1 |
| `User/RTD Series/RTD2014Osd/Header/RTD2014Project.h` | behaviour | no panel/OSD rotation |  | 1 |

## Rules before the change (INSERTS / SUBS / WRAPS / global regexes, counted from tag `wb-p14ui-ownbase`)

| kind | behaviour | mechanical |
|---|---|---|
| insert | 170 | 2 |
| sub | 98 | 8 |
| wrap | 3 | 14 |
| global | 7 | 0 |

## Moved out of the rule files

- `fw/awto/{arith,dataport,gamma,reg,settings,wdt}/rules.py` deleted. ALIASES / PIN_COMMON (dataport, reg) -> `fw/awto/boundary.py`. gamma / settings / wdt inserts and subs -> edits in `fw/sdk`; their `.inc` glue -> `fw/sdcc/glue*.inc`.
- `scripts/keil2sdcc_drops.py` (size switches `_AWTO_DP_PHYCTS`, `_AWTO_FACTORY`, `_AWTO_GAMMA_ALL`, `_AWTO_FLASH_ALL`, #65) -> edits in `fw/sdk`.
- Big inserted blocks (`fw/sdcc/awto_*.inc`) are `#include` lines in the SDK file; the build tag is `@FW_TAG@` in `fw/sdk/User/RTD Series/RTD2014Osd/Code/RTD2014OsdDisplay.c`, substituted by `msg_tokenise.py port`.
- `fw/overlay/**` (board, panel, project headers, debug/msg headers, EDID) merged into `fw/sdk` at the same relative paths.
