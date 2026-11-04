# RTDCustomerTool 3.8 GUI map (static, from PE resources)

- Source: `tmp/rtdtool/rtdtool-3.8/RTDCustomerTool_V3.8_20221101/` (read-only, never executed)
- Full table: `tmp/rtdtool/rtdtool-res/gui_resources.tsv` (not in git; 7631 rows; `source<TAB>restype<TAB>id<TAB>class<TAB>text`)
- Generator: `scripts/pe_resources.py <root> <out.tsv>` (stdlib PE resource-tree parser; dialogs, DLGTEMPLATEEX, menus, string tables, accelerators, DLGINIT, version)
- Tags: [res] resource, [str] strings, [guess]
- ID format in TSV: `dlg:<dlgid>/<ctrlid>` (ctrlid -1 = static label with no ID), `menu:<id>/<cmdid>`, bare number = string-table id

## Findings

- [res] Every plugin is an MFC dialog shell. Plugin string tables contain only the 81 stock MFC strings (no app labels). Labels live in dialog control captions.
- [res] Register names, field names, scaler specifics are NOT in resources. Grids/lists are filled at runtime (SysListView32 / RSGrid.ocx `{1C095413-...}`) from `RTDScaler/` data files and `PlugIn/*.dat` [guess].
- [res] Many data-readout fields are `Edit` controls with empty caption; the label is the preceding `Static` (ID -1), so the pairing is by dialog order, not ID. Edit IDs are real and usable.
- [res] Menu command IDs are only in RTDTool.exe and PlugIn_NewEDID (New/Delete). DebugMessage/GPIO menus are MFC toolbar-customise popups (16910-16917), no tool actions.
- [str] All plugins export `GetPIHWnd GetPIICON GetPIID GetPIName Initinal SetCmd SetCommInterface`. PlugIn_ISP additionally `SetCmdLine SetCommByID SetCommByIndex InitialComm Initiallize`. DebugMessage exports no `SetCmd` (and no `GetPIICON`).
- [guess] Control IDs (BN_CLICKED) are likely what `SetCmd(command_id)` dispatches on; exact mapping needs disassembly of each plugin's `SetCmd`. GetPIName/GetPIID return values are not visible as strings (computed in code).

## Counts (dialogs / controls / strings)

| file | dlg | ctl | str | file | dlg | ctl | str |
|---|---|---|---|---|---|---|---|
| RTDTool.exe | 13 | 99 | 82 | PlugIn_ISP | 7 | 103 | 81 |
| DebugMessage | 26 | 278 | 193 | PlugIn_NewEDID | 56 | 1488 | 81 |
| PlugIn_CTS | 6 | 34 | 81 | PlugIn_NewCtrlReg | 15 | 253 | 81 |
| PlugIn_DPCD | 6 | 45 | 81 | PlugIn_Measure | 5 | 232 | 81 |
| PlugIn_DPTxCtrl | 7 | 132 | 81 | PlugIn_OD | 8 | 92 | 81 |
| PlugIn_Dither | 18 | 153 | 81 | PlugIn_McuReg | 4 | 19 | 81 |
| PlugIn_Flash | 4 | 32 | 81 | PlugIn_LastLine | 4 | 14 | 81 |
| PlugIn_GPIO | 24 | 217 | 193 | PlugIn_HsDelay | 3 | 44 | 81 |
| PlugIn_GT | 5 | 57 | 81 | PlugIn_I2C | 4 | 55 | 81 |
| PlugIn_Gamma | 6 | 48 | 81 | PlugIn_HDCP | 9 | 64 | 81 |
| Option/ISPOption | 12 | 247 | 81 | Option/DeviceSelectOption | 5 | 100 | 81 |
| Comm_* (8 DLLs) | 3-4 each | 10-36 | 81 | RHubLib | 2 | 5 | 88 |

(Comm.dll, RtHub_USB2I2C.dll, RtHIDlib.dll: no usable dialogs.)

## RTDTool.exe (main shell)

- [res] Main dlg:102 "RTDTool 3.8.2": 1010 SysListView32 (plugin list), 1011 ComboBox (access method, label "Access method:"), 1012 `>` (comm option), 1031 ComboBox (Scaler:), 1032 ComboBox, 1030 button (no caption), 1049 Stop, 1050 Run, 1051 Reset, 1062 "Del registry code".
- [res] Menu 133: 32771 Option>PlugIn management, 32774 Option>Setting, 32772 Debug message, 32773 Communication Option, 32779 Flash Support List, 32775 Update. Menu 148: 32778 Delete. Sys menu string 101 "&About RTDTool...".
- [res] dlg:100 About ("RTDTool, Version 3.6" string stale vs 3.8.2 title): 3801102 / 3801251 Edit (Plugin's version / Comm's version readouts).
- [res] dlg:134 Plugin Management (>>, <<, Up, Down; wanted/spare lists). dlg:142 Setting: ISP Addr / Debug Addr / ISP Continuous Addr edits, "Auto Detect Slave Address", "Enable Debug Mode", "Access Scaler Mode". dlg:144 Update (server, Flash Support List download). dlg:146 Login, 149 New version, 150 Tips ("Current IC has warnings or it is forbidden").

## Plugins: dialogs and readout/action control IDs

Dialog 1000 is each plugin's main page unless noted.

- **NewEDID**: [res] 1075 Load, 1076 Save, 1079 Read, 1080 Write, 1081 Option, 1466 Vendor SN Setting; labels Device/Port Sel. Dlg 1003 = parsed General Information (ID Manufacturer Name, Product Code, Serial, Week/Year, EDID Version/Revision, Number of Extension, Check Sum). 56 dialogs = per-block parsers (detailed timing, CEA etc.). Menus 1026 New (32774), 1027 Delete (32775). EDID read target: 1079.
- **Measure**: [res] 1015 Measure, 1106 Off-Line M2, 1107 Get Result, 1033/1034/1035/1079 = M2/S1/S2/S3 source, 1042 Hex / 1043 Dec. Readout Edits (in order after labels): 1011-1013, 1022-1031, 1036-1041, 1045-1078. Labels: HSync/VSync Polarity/Period/Pulse Width (A=analog,D=digital), IH/IV Capture Start/Width, IHS/IVS Delay, Pixel Rate (MHz), Phase Select, FIFO Win H/V, D Clock (MHz), DH/DV Total Pixels/Lines, Active/BK Start/End, IH Freq (KHz), IV Freq (Hz), Free Run D Clock. Dlg 1006 "Measure Window", 1011 "Off-Line Measure M2" repeat the set. Best timing readout.
- **ISP**: [res] 1004 ISP, 1005 Create Flash Dat, 1007 ISP Option, 1014 Auto, 1015 Erase, 1016 1 To 1, 1017 1 To 4. Dlg 1003 FW Update Progress, 1004 Flash Dat File editor (ID Code, ID Type, Flash Name, Bank Count, SWREN, SR bytes, SafeGuard; 1094 Auto detect), 1030 "ISP result" (1107 "FW Version:" label, 1106 Re ISP).
- **Flash**: [res] dlg:4000 Total Bank / Current Bank, 4007 Read Total, 4008 Save Total, 4009 Read, 4010 Save, 4011 Compare, 4016 Read, 4017 Save (page), 4019 Page of Current Bank, 4023 Auto; File CRC / Read Code CRC / Total CheckSum edits.
- **I2C**: [res] Slave/Sub/Length edits, 1005 Word Sub Address, 1006 Write, 1008 Read, 1009 Sub Addr Increase, 1012 Direct, 1013 Through IC; second block 1018-1037 (1024 Write, 1025 Read, 1026-1029 Save/Load, 1032/1033 Checksum, 1036/1037 Segment access).
- **McuReg**: [res] 1018 Embedded MCU, 1019 Through FW, 1007 Read, 1008 Write, 1009 Open, 1010 Save, 1016 Run, 1020 Stop.
- **DPCD**: [res] 1008 Read, 1009 Write, 1010 Open, 1011 Save, 1007 Acess DPCD Port Window, 1029 Hide Reserved, 1030 Read scaler register only; dlg 1005 port window (1016 length, 1017/1018 Addr/Val edits, Read 1008, Write 1009; DPCD reg 0x003F0/0x003F1 access port).
- **CTS** (DP PHY): [res] dlg:1006 1003 CTS, 1004 Enable PHY CTS, 1007 Test Rate, 1011 Test Lane, 1016 Freq. Test, 1017 Symbol Test, 1018 Clear Counter, 1019 Get Counter, 1020 Clear Registers, 1021 Test Port, 1037 Register Result, 1038 Delay Time(ms), 1047 Error Counter. Dlg 1007: 1041 CTS Mode Enable, 1045 EXECUT.
- **HDCP**: [res] 1042 HDCP 2.2, 1048 HDCP 1.4, 1046 HDCP Setting, 1047 Advance Option, 1021 Device Option; labels HDCP Key Length, Bksv Length, Access Place, Port Sel. Dlg 1012 "HDCP Result".
- **Gamma**: [res] 1010 Read, 1011 Save, 1012 Write, 1008 Load, 1029/1030 Enable/Disable Gamma, 1034/1035 RGB gamma, 1014-1017 R/G/B/All, 1020/1021 Gen0/Gen1, 1043/1044 M1/M2.
- **GPIO**: [res] 1010 Read Port Ctrl, 1011 By Register, 1012 By Bus, 1013 Pinshare Setting, 1044 Apply Setting, 1046 Low, 1047 High, 1048 Read, 1007 Check All.
- **HsDelay**: [res] 1003 Search, 1004 Update status, 1012/1037 -/+, 1013-1015 latch/clock invert. Readouts: H total, pixel rate, meta-stable phase, current/default HS delay, V height.
- **LastLine**: [res] 1003 Last line Analysis, 1004 Last Line Bar, 1010/1011 SSCG On/Off, 1012/1013 D-Pattern Gen On/Off.
- **GT**: [res] dlg:6001 6005 New, 6017 Run Step, 6018 Run All, 6022 Clear, 6023 Load, 6024 Save, 6026 Save To Default, 6029 Cmd, 6007 Insert, 6035 Stop before run. "Old GT supports 256 byte at most". Scripted cmd list: closest to headless batch driving.
- **NewCtrlReg**: [res] 15 dialogs (Field Edit 143, Page select 1007, Access Port 1008/1022, Compare 1015, Option 1017, OSD 1018, Check 1020, USB 1021). Register grid; labels not in resources [guess: from RTDScaler data].
- **OD, Dither, DPTxCtrl**: [res] controls mostly unlabelled in resources (OD export option 1016, progress 1019); see TSV.
- **DebugMessage**: [res] dlg:1000 1014 Start, 1015 Stop, 1016 Clear, 1017 Pause, 1018 RUN, 1019/1020 Filter Message, 1024 Auto Clear Items, 1025 Auto Start After ISP, 1027 Save, 1028 Search, 1055/1061 Save Message To File, 1058 Split File, 1059 file size ComboBox, 1062 Edit Debug String, 1073 Unsigned, 1074 Enable save eye table, 1033-1054 bit-selector buttons 0..9/Other (8 filter bits). List control is custom (`{1C095413-B7A4-4B71-A4FB-3006EA716AE1}`, id 1013 = RSGrid.ocx) [guess]. Dlg 1006: 1063 SysListView32 (code/string file table), 1064-1069 Code File/String File paths. Column names for debug message are not in resources; see `DefaultDebugMsgFile/*.h` [guess].
- **ISPOption** (Option/): [res] 12 dialogs (1002 ISP Option, 1010 Conflict Flash). **DeviceSelectOption**: 15000 Device Select Option, 15002/15003 GPIO Simulate I2C Pin Setting.
- **Comm_***: [res] one option dialog each (Aux 3000 AUX Adjust, FTDIUsb 3000, GFXI2C 3000, RealtekUSB 3000 + 3018 Install Usb Driver, Smbus 3002, TypeCUsb 3000, UsbHubHidI2C 1000, UsbHubI2C 3000); Aux/GFXI2C also 3001 Multi RT Monitor Select.

## Gaps

- No "ReadAll" or "scaler info" control exists in resources [res]; likely a runtime-built list in RTDTool main (1010) or comes from `RTDScaler/` data [guess].
- Plugin display names / IDs (GetPIName / GetPIID) need disassembly.
- Control ID -> SetCmd command-id mapping not established; next step is Ghidra on `SetCmd` in PlugIn_Measure / NewEDID / I2C.
