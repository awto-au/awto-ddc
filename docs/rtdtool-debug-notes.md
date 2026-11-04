# RTDCustomerTool V3.8 - command line, debug mode, debug-message stream

Static analysis only (Ghidra headless decompile + strings). Nothing was run.
Tags: [fw] read in decompiled code, [str] from strings, [oss] open source, [guess] inference, [?] unknown.
Tool tree: `~/vendors/realtek/analysis/rtdtool-3.8/RTDCustomerTool_V3.8_20221101/`.
Decompile dumps (not in git): `~/vendors/realtek/analysis/tmp_dbg/{RTDTool.c,DebugMessage.c}`, throwaway project `tmp_dbg/proj`.

## 1. Command-line arguments of RTDTool.exe
- None. [fw] `InitInstance` (0x00408xxx) calls `InitCommonControlsEx`, `CWinApp::InitInstance`, `SetRegistryKey`, creates mutex `NewRTDCustomerTool`, `AfxSocketInit`, then runs the main dialog modally. It never calls `ParseCommandLine` / `ProcessShellCommand`.
- [fw] `CCommandLineInfo` / `ParseParam` exist in the binary only as statically linked MFC library code; no caller in app code.
- [str] No `/x` or `-x` switch strings, no `GetCommandLine` use in app code.
- [fw] Second instance: mutex `NewRTDCustomerTool` already held -> `AfxMessageBox("Already running!")` and exit.
- [fw] "Socket init fail!" if Winsock init fails (network comm backend).
- So: no switch for access method, scaler, auto-run, batch/ISP, log file, or debug. All of those are GUI + INI.

## 2. Debug mode / debug slave
- Comm-DLL interface (exported by `Comm.dll`, resolved by `GetProcAddress` in RTDTool and forwarded to plugins as a function table) [fw]:
  `SetDebugMode`, `GetDebugMode`, `SetDebugSlave`, `GetDebugSlave`, `SetIspSlave`, `GetIspSlave`, `SetIspContinuousSlave`, `AutoDetectSlaveAddr`, `DebugMessageEventStart/EventFinish/Start/End/GetValue/GetString`, `SetCmdLine`, `SetCmd`.
- Debug slave address: default 0x6A [fw]; ISP slave 0x94, ISP-continuous 0x96. Source of truth, in order:
  - per-scaler file `RTDScaler/<chip>/...` section `[ScalerInfor]` keys `IspSlaveAddr`, `IspContinuousAddr`, `DebugSlaveAddr` (also per `SpecialType` section) [fw]
  - `NewRTDCustomerToolSetting.ini` section `[RTDTool]`: `IspSlaveAddr`, `IspContinuousSlaveAddr`, `DebugSlaveAddr`, `bAutoDetectSlaveAddr`, `bDefaultAddr` [fw]
  - GUI settings dialog (hex edit boxes 0x439/0x43b/0x43d, `%02X`) writes these back [fw]
- Debug mode (`DAT_005b9aa4`, checkbox ctrl 0x418 in the connection/settings dialog) [fw]:
  - After a successful connect, if set (and status != 0x34): message box "Debug mode enabled, it will diasble double buffer and watch dog!" (sic), then the tool continues.
  - Effect on the scaler: disables double-buffer and watchdog [str] so the firmware can be debugged.
  - Not persisted to the INI (no key written) [fw].
  - Plugins can request it via window message 0x46A -> `SetDebugMode` wrapper (0x00401F10) [fw].
- `GetDebugMode()` returns 2 when the scaler is in ISP mode; DebugMessage plugin then shows "ISP Mode" and refuses to start [fw].
- Debug mode does NOT add logging to `IspDebugLog.txt` [fw]; that file is written by PlugIn_ISP (see 4).
- [str] `ISPOption.dll`: "Set debug mode fail!", "Set debug ISP fail!", "Read Machine ID fail, Set Debug Mode faile!" - ISP path also enters the scaler's debug mode.

## 3. DebugMessage plugin and the debug stream
- `PlugIn/DebugMessage/DebugMessage.dll` is a normal GUI plugin (exports `SetCommInterface`, `GetPIName`, `GetPIHWnd`, `GetPIID`, `SetSettingFilePath`), loaded unconditionally at startup ("Load DebugMessage...") [fw].
  - The six `DebugMessage*` names in its string table are the host-side names; the implementations live in `Comm.dll` and each `Comm/Comm_*.dll` [str: all of them carry the six names].
  - So there is no standalone "decode a UART log" entry point; the plugin is a poller driven by a host function table (`DAT_1018a130`).
- Transport = same bus as everything else (I2C/DDC/USB-bridge), NOT a UART [fw]:
  - Polling thread `FUN_10007af0`: if comm type (host table +0x6c) == 8 -> `FUN_1000ba60` (Type-C/USB path, [str] "Type-C Usb Get DebugMessage String/Value Fail!"), else `FUN_1000c4c0` (I2C path).
  - I2C path: host I2C-transfer (+0x30) with slave = `GetDebugSlave` (+0x8c) reads command/register 0x25 repeatedly.
  - Frame header bytes 0xFA 0xF5, then length byte (1..0xEE), 4 code bytes (+ a byte), checksum seeded 0x0F summed over fields; mismatch logs "Check sum error".
  - Payload > 15 bytes is fetched in 0x0F-byte chunks (`FUN_10007b30`, command bytes start 0x01 and increment, per-chunk checksum).
  - [guess] 4 code bytes = 0x89xx event code + argument; length 3 with first payload byte 0x40 is a special record.
- Code -> text mapping is done in the plugin at runtime [str]/[fw]:
  - reads `DefaultDebugMsgFile\DebugCode.h` (`#define NAME 0x89xx`) and `DebugString.h` (`#define NAME "text"`), joined by NAME; "No Code Define!!!" if missing [str].
  - Editor dialogs (CDebugCodeStringDlg, CDebugMsgNewCodeStringDlg) let the user add/edit pairs and save to `.h` [str].
  - Value shown in hex or decimal (checkbox `+0x200`) via `__ultow_s` [fw].
- Output [fw]/[str]:
  - GUI list control with columns Time / Code Value / Message String.
  - Checkbox "Save Message To File" (member +0x1fc) + path box; default `MessageLog.txt`, resolved against the plugin DLL's directory (`GetModuleFileName`) [fw]. Exact resulting path not confirmed [?] - expect `PlugIn/DebugMessage/MessageLog.txt` or `<tool dir>/MessageLog.txt`.
  - "Split File" + "File Size:" options rotate the log; `.txt` extension enforced via `wcsstr`.
  - "Open Log File Fail" if the log cannot be created; "Message Start" / "Message Stop" / "Force to Stop" markers.
  - "Auto Clear Items" and "Auto Start After ISP" checkboxes; "Start" / "Stop" / "Clear" / "Save" buttons.
- Serial/COM: only [str] "Instrumnet no ack from COM port!", "COM port initial fail!" (Comm_Aux = bench instrument, not scaler debug) and FTDI baud-rate call in `Comm_FTDIUsb.dll` (FT_SetBaudRate; FTDI used as an I2C/MPSSE bridge). No scaler-UART debug channel found [?]. The firmware debug codes reach the host via the I2C debug slave (0x6A), same as the 0x89xx table.

## 4. INI / registry switches
- `NewRTDCustomerToolSetting.ini` (next to RTDTool.exe, created at runtime; not shipped) [fw]:
  - `[RTDTool]` `bEnableHotKey`, `bAutoDetectSlaveAddr`, `IspSlaveAddr`, `IspContinuousSlaveAddr`, `DebugSlaveAddr`, `bDefaultAddr`, `ucIPAddr0..3`, `bShowNewVersionMsg`, `bNeverPopupIDCodeMsg`, `bBigIcon`, `bTopCommonPlugIn`, `CommID`, `LastPluginName`, `PluginCountShowByName/HideByName`.
  - No debug/verbose key.
- ISP plugin INI `[ISP_Basic]`: `bAutoSlaveAddr`, `enumCheckType`, `ucSlaveAddress`, `bFileLenIncludeFF`, `bAutoISP`, `bSaveLog` [fw]. `bSaveLog=1` ("Save log file" in the ISP option dialog) enables `IspDebugLog.txt` (ISP steps: mode entry, slave addr, scaler type, flash type, bank erase/write codes) in the working dir [fw]/[str]. This log is ISP events only, not scaler reads.
  - `bAutoISP` = auto-run ISP; GUI-set, not a CLI.
- `PlugIn_HDCP.dll`, `PlugIn_NewEDID.dll` also read `bSaveLog` [str].
- Registry: only MFC `SetRegistryKey("Local AppWizard-Generated Applications")` MRU/UI state [fw]. No debug keys.

## 5. Recipe: dump everything the tool reads
No CLI route. Options, in order of effort:
1. GUI, Realtek tool (needs the real comm backend, Windows):
   - Start RTDTool, pick the Comm interface (CommID persists in INI), connect; tick debug mode (ctrl 0x418) if the firmware needs double-buffer/watchdog off.
   - Open the DebugMessage tab: tick "Save Message To File", set path/"Split File", press "Start". Raw events land in the file as Time / Code / decoded string via `DefaultDebugMsgFile\*.h`.
   - Plain register reads (McuReg/NewCtrlReg plugins) have no dump-to-file option found in strings; ISP plugin only logs ISP steps (`bSaveLog`).
2. Direct DLL call: not practical. The plugin DLLs are GUI/MFC objects needing the host function table; the `DebugMessage*` exports live in Comm DLLs and take no file argument.
3. Reimplement the poll [guess, best fit for awto-ddc]:
   - On the scaler's I2C debug slave (default 7-bit 0x35 = 8-bit 0x6A; confirm per chip in `RTDScaler/<chip>/` scaler info), read command 0x25, expect `FA F5 <len> ...` + checksum; fetch extra 15-byte chunks; map `0x89xx` through `DebugCode.h`/`DebugString.h`.
   - Needs the debug-capable firmware on the scaler (debug slave must be enabled; ISP mode returns "ISP Mode").
   - Frame layout above is partial; validate on a bus capture before relying on it.

## Open
- [?] Exact `MessageLog.txt` location and whether Start can be triggered by a window message from outside (no CLI hook found).
- [?] Whether the JXC 4K firmware (`bank0/5`) ships the debug-slave/0x25 handler; check for 0xFA 0xF5 header constants in the 8051 dump.
- [?] `FUN_1000ba60` (Type-C path) not decoded.
