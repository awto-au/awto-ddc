# RTDCustomerTool 3.8 - headless host feasibility

Static analysis only (Ghidra headless decompile, PE export parse). Nothing was run, installed or wine-run.
Tags: [fw] read in decompiled code, [str] from strings, [guess] inference, [?] unknown.
Tool tree: `tmp/rtdtool/rtdtool-3.8/RTDCustomerTool_V3.8_20221101/`.
Decompiles (not in git): `tmp/rtdtool/{PlugIn_ISP.c,tmp_dbg/RTDTool.c,tmp_hdl/*.c}` (gitignored); layout dump `tmp/rtdtool/tmp_hdl/commobj_layout.txt`.
Related: `rtdtool-debug-notes.md` (debug slave, stream), `rtdtool-gui-map.md` (control IDs).

## Verdict
- **Feasible for ISP only, and only for the version-read exports.** `PlugIn_ISP.dll` is the one plugin with a real non-GUI API (`InitialComm`, `ReadVersionExport`, ...). Those run without a window and write result files.
- **All other plugins (NewEDID, McuReg, I2C, Measure, DebugMessage, ...) are MFC dialogs.** The logic lives in dialog handlers, not in exports. `SetCmd` is a no-op there. A host can load them and click their buttons via window messages, but cannot call "the read function".
- **RTDTool.exe contains no extraction logic of its own** beyond hosting plugins and the Comm object (`CRTDToolComm`); no command line (see debug-notes §1).
- **Recommendation:** use the ISP exports for the version/ID read; for registers, EDID, scaler info, debug stream reimplement the read sequences directly against our I2C backend (we already do ISP/flash). The `CRsComm` object in `host.c` gives a way to call Comm.dll's register layer (`ReadRegEx`, `ReadMcuReg`, ...) without any plugin.

## 1. Plugin host contract [fw]
Resolved by `GetProcAddress` in `FUN_0041c260` / `FUN_004043a0` (RTDTool.exe). All plugins export exactly these 10, all `__cdecl`:

| Export | Signature | Semantics |
|---|---|---|
| `Initinal` | `int(HWND parent)` | Once: `CWnd::FromHandle(parent)`, `new CDialog`, `Create(1000, parent)`, `ShowWindow(SW_HIDE)`. `OnInitDialog` runs inside this call. Returns 0. Default setting path = `<exedir>\Setting.ini` if `SetSettingFilePath` never called (ISP) |
| `SetCommInterface` | `void(CRsComm* obj)` | Stores the pointer in a plugin global. RTDTool passes `&DAT_005b9b08` = its `CRTDToolComm` |
| `SetSettingFilePath` | `void(const wchar_t* path)` | `wcscpy_s(g, 0x104, path)`; ini the plugin keeps its keys in (RTDTool passes `NewRTDCustomerToolSetting.ini` [guess]) |
| `SetScalerFilePath` | `void(const wchar_t* path)` | `wcscpy_s(g, 0x104, path)`; per-scaler file from `RTDScaler\` [guess] |
| `SetCmd` | `void(const wchar_t* s)` | Stores string in a global. ISP: consumed (below). NewEDID/McuReg/I2C: stored, never read (only the static destructor touches it) [fw]. Measure/DPCD/NewCtrlReg/others: not checked [?]. RTDTool.exe never calls it (loaded into the table, no call site) [fw] |
| `GetPIHWnd` | `HWND()` | `dialog->m_hWnd`, or 0 before `Initinal` |
| `GetPIName` | `void(wchar_t* buf, ushort n)` | e.g. "ISP" |
| `GetPIID` | `int()` | ISP 0x0C, NewEDID 0x28, McuReg 0x03, I2C 0x1F |
| `GetPIICON` | `HICON()` | `LoadIcon(res 0x3fc)` |
| `ReleasePI` | `void()` | No-op in NewEDID/McuReg/I2C |

- Plugin table in RTDTool (struct of fn ptrs): +0 Initinal, +4 SetCommInterface, +8 GetPIName, +0xC GetPIHWnd, +0x10 GetPIID, +0x14 SetSettingFilePath, +0x18 ReleasePI, +0x1C GetPIICON, +0x20 SetScalerFilePath, +0x24 SetCmd [fw].
- Load order in the GUI: `LoadLibrary` -> `SetSettingFilePath` -> `SetCommInterface` -> `GetPIName`/`GetPIICON`; later on selection `Initinal(mainhwnd)` -> `GetPIHWnd` -> reposition/show [fw].
- **Window:** `GetPIHWnd` is the plugin's own dialog. A real parent HWND is needed (ISP dereferences `parent->m_hWnd` when it posts WM_CLOSE in command mode; others only pass it to `Create`) [fw]. A hidden never-shown popup window satisfies it [guess]. The dialog is created hidden, so no visible UI is needed; message pumping is needed for anything the dialog posts to itself.
- **GUI -> plugin command channel is window messages, not exports** [fw]: RTDTool does `SendMessageW/PostMessageW(GetPIHWnd(), WM_USER+n, ...)`: 0x464, 0x466 (select item, wParam=id), 0x470 (deactivate/stop), 0x478 (init data, wParam=ptr into main object), 0x4F3, 0x54C. Reads then happen in button handlers (`WM_COMMAND`/`BN_CLICKED`) and results are drawn into controls. Control IDs: `rtdtool-gui-map.md`.

## 2. Comm interface (`CRsComm`) [fw]
- `SetCommInterface` takes a pointer to a C++ object, **not** a flat table:
  - `+0x000` vtable pointer (9 slots, below)
  - `+0x004` `HMODULE` of `Comm.dll`
  - `+0x008 .. +0x1F8` 125 function pointers, `GetProcAddress` order, one per `Comm.dll` export, all `__cdecl`. Offset = 4 x slot. Canonical name list: `COMM_FN[]` in `scripts/rtd_headless/host.c` (copied from `PlugIn_ISP` `FUN_10001000`).
  - `+0x1FC ..` `CRTDToolComm` extension fields. Plugins touch at least `+0x21C` (byte) and `+0x220` (flag) (McuReg) [fw]; `+0x22C` = main dialog ptr and `+0x238` = state, used only by RTDTool's own overrides [fw]. A zeroed 0x400-byte block is enough for plugin code that does not use the overrides [guess].
- Member offsets seen in use: 0x08 GetI2CPageLength, 0x0C GetNativePageLength, 0x10 I2CWrite, 0x14 I2CRead, 0x18 I2CWriteByte, 0x50 SetI2CSpeed, 0x5C SetWaitingMode, 0x64 Initiallize, 0x68 GetCommCount, 0x6C GetCommID, 0x7C SetCommByID, 0x98 SetDebugMode, 0x9C GetDebugMode, 0xA0 ReadReg, 0xA4 WriteReg, 0xB8 ReadRegEx, 0xBC WriteRegEx, 0xE0 ScalerStop, 0xE4 ScalerRun, 0xE8 WriteMcuReg, 0xF0 ReadMcuReg, 0xF4 WriteMcuRegBit, 0x104 ReleaseDev, 0x110 SetSettingFilePath, 0x11C EnterIspMode, 0x130 AutoDetectSlaveAddr, 0x134 DDCCIWrite, 0x198-0x1AC DebugMessage* (EventStart, EventFinish, Start, End, GetValue, GetString), 0x1B0 SetCmdLine.
- Argument conventions seen: `ReadReg/ReadRegEx(reg, byte* out)`, `WriteReg(reg, val)`, `WriteMcuRegBit(reg, mask, val)`, `SetDebugMode(mode)`, `SetWaitingMode(a, b)` [fw]; `ReadFlashData(addr, ushort len, byte* buf)` chunks by `GetNativePageLength` [fw]; others [guess]/[?].
- **vtable (`CRsComm` base, 9 slots, `__thiscall`)**: each forwards to a member, returns **6** if the member is NULL:

| vt | thunk -> member | args |
|---|---|---|
| 0 | ReadReg (+0xA0) | 2 |
| 1 | WriteReg (+0xA4) | 2 |
| 2 | ReadRegEx (+0xB8) | 2 |
| 3 | WriteRegEx (+0xBC) | 2 |
| 4 | ScalerStop (+0xE0) | 0 |
| 5 | ScalerRun (+0xE4) | 0 |
| 6 | EnterIspMode (+0x11C) | 1 |
| 7 | AutoDetectSlaveAddr (+0x130) | 0 |
| 8 | DDCCIWrite (+0x134) | 4 |

- `CRTDToolComm` (RTDTool) overrides vt4-vt7 with wrappers that `SendMessage(plugin, 0x4DC/0x46E/0x47A)` and the main dialog, plus retry loops (`FUN_004096e0`, `FUN_0040a6c0`, `FUN_00409ac0`, `FUN_004095c0`). A host needs only the base behaviour; `PlugIn_ISP` itself runs on a base `CRsComm` [fw].
- **Comm.dll is a dispatcher** [fw]: `Initiallize()` enumerates `Comm\Comm_*.dll`, `GetCommID()` of each; `SetCommByID(id)` / `SetCommByIndex` pick one; every export forwards to the picked DLL's pointer, 6 if absent. Same `Comm.dll` instance is shared in-process, so selection made by the host is seen by a plugin's own loader.
- Transport IDs (first bytes of each `GetCommID`, `mov eax,imm; ret`) [fw]: Aux 1, Smbus 2, RealtekUSB 3, FTDIUsb 4, GFXI2C 5, UsbHubI2C 6, TypeCUsb 8, UsbHubHidI2C 0x0B. Free: 7, 9, 10.
- **Our `Comm_LinuxI2C.dll` returns `GetCommID` = 0xAB0BB.** Consequences [fw]: ISP `InitialComm` only calls `SetCommByID` for ini `[EXE] CommID` in 1..10, so it cannot select our shim; RTDTool's `switch(GetCommID())` (cases 1-6) falls to default. Change the shim to return 7, 9 or 10 (nothing else uses them) [guess].

## 3. `PlugIn_ISP.dll` exports [fw]

| Export | Does | Output |
|---|---|---|
| `InitialComm()` | Sets plugin-global comm to its **own** static `CRsComm`, `LoadLibrary(<exedir>\Comm.dll)` and fills it (`FUN_10001000`), `Initiallize()`, reads `<exedir>\ISPToolSetting.ini` `[EXE] CommID` (default 6) -> `SetCommByID` if in 1..10, `SetSettingFilePath(ini)`. Throws (AtlThrow 0x80004005) if `Comm.dll` will not load. Does not use `SetCommInterface` | none |
| `ReadVersionExport()` | `ReleaseDev`; `SetDebugMode`; `EnterIspMode`; `ReadRegEx` x3; writes ini. Returns void, status only in the file | `<exedir>\VersionResult.txt`: `[InstalledFWVersion] FWReadResult=Success\|Fail, ProjectID, FWVersion, FWSubVersion` (hex) |
| `ReadCopyBankVersionExport()` | Dual-bank "copy bank" firmware flow: sets "factory mode" (`FUN_1002c2e0(1)`), polls, reads banks, restores | `HPVersion.txt` `[Current FW Version]` `CurrentBank`, `Bank<n>FWVer/FWSubVer/Year/...` |
| `SaveCombineVersionExport()` | Same flow, reads combined version | `HPVersion.txt` `[Combine FW Version]` `Major/Minor/Build/Revison`, also issues `DDCCIWrite(0x6E,0x71,...)` |
| `UpdateCombineVersionExport(wchar* "a.b.c.d")` | Parses 4 bytes, writes combined version | writes to device [guess] |
| `ExecuteIsp()` | Finds a `.bin` in the exe dir, runs the programming flow selected by `ISPToolSetting.ini`/`DAT_10093cb8` | **flash write**; logs `IspDebugLog.txt`, `IspResult.txt` |
| `SetCmd(wchar* cmd)` | Command line for the dialog's `OnInitDialog` (`FUN_100326c0` -> `FUN_10036ba0`). Words: `ReadVersion`, `ReadBootVersion`, `ReadCombineVer`, `ReadVerCopyBank`, `UpdateCombineVer a.b.c.d`, `ReadKey [file]`, `ISP`, `ISPWithVerify`, `ISPWithVerifyQHD`, `ISPWithVerifyQHDOneUser`, `ISPCopyBank`, `ISPCopyBankSw`, `/silent`, `/fw <file>`, `Ignore_Auto`, `NoSaveSetting`, `VerifyFail`, `setcomm`, `InstallDriver`, `UninstallDriver` | dialog posts WM_CLOSE to its parent when done |

- Path root is `GetModuleFileNameW(NULL)`'s directory [guess: the HMODULE arg is optimised out], so the host exe must sit in the tool root.
- `ReadKey` writes `PublicKey.txt` [str]; `ReadBootVersion` target file not traced [?].
- `ReadVersionExport` is non-destructive in intent but enters ISP mode and writes MCU reg 0xEE [fw: `(*[0x3d])(0xee)`], i.e. it pauses the scaler MCU while it runs [guess]. The copy-bank/combine reads toggle factory mode: gated behind `RTD_HOST_ALLOW_WRITE=1` in `host.c`.
- Whether the JXC firmware answers the copy-bank/combine flows is [?]; `ReadVersionExport` is the one expected to work.

## 4. Per-plugin verdict

| Plugin | Headless callable? | Reason |
|---|---|---|
| ISP | Yes: `ReadVersionExport` (+ copy-bank/combine reads, gated). `ExecuteIsp` = write, do not use for reads | Real exports, own comm object, file outputs |
| NewEDID | No (GUI only) | Export set = boilerplate; ~900 comm refs inside dialog code, mostly `WriteMcuReg` (+0xE8, 95x), `WriteMcuRegBit` (+0xF4), `I2CWrite`; EDID is read by driving an MCU-register window [guess]; result goes to dialog controls/save-file handlers |
| McuReg | No | Dialog; uses `SetDebugMode`, `GetCommID`, `ReadMcuReg*`; posts own 0x46x messages; touches obj `+0x21C/+0x220` |
| I2C | No | Dialog; `I2CWrite`/`I2CRead` raw (+0xF4 `WriteMcuRegBit` 23x) |
| Measure | No | Dialog; installs a `SetWindowsHookEx(3 = WH_GETMESSAGE)` hook on the calling thread in `Initinal` |
| DPCD, NewCtrlReg, DebugMessage, others | No | Same 7-10 boilerplate exports only (DebugMessage 7: GetPIHWnd, GetPIID, GetPIName, Initinal, ReleasePI, SetCommInterface, SetSettingFilePath) |

- Driving a GUI plugin from a host (what `host.c plugin` does): `SetSettingFilePath` -> `SetScalerFilePath` -> `SetCommInterface(obj)` -> `Initinal(hidden HWND)` -> `PostMessage(WM_COMMAND, BN_CLICKED)` on the "Read" button IDs -> pump -> scrape child control text. This automates the GUI in-process; it does not call the underlying read function, and each plugin may need the 0x464/0x466/0x478 state messages first [?]. Expect trial and error per plugin.
- **Debug stream:** `DebugMessage.dll` runs a worker thread over Comm members 0x198-0x1AC (EventStart handshake up to 6 tries, then loop Start -> GetValue -> GetString -> EventFinish; frame magics 0xFA 0xF5 / 0xE7 0xEC) [fw]. In 7 of 8 `Comm_*.dll` those exports are one shared stub returning a constant error (`mov eax,imm; ret`; Aux 0x804, FTDI/Smbus 0x1C13, GFXI2C 0x2201, RealtekUSB 0xB01, UsbHubHidI2C 0x3F00, UsbHubI2C 0x2B00) [fw]. Only `Comm_TypeCUsb` has a body (`cmp [g],0; jnz ...`). An I2C transport therefore gives no debug stream through Comm; it has to be read host-side (debug slave 0x6A, `rtdtool-debug-notes.md` §2-3).
- Same for `ReadFlashData`/`WriteFlashData`/`IspEnable`/`SectorErase`: stubs in I2C-class transports, so flash access is done by ISP-mode register writes in our own code, not via Comm.

## 5. Easy wins (files written regardless of GUI)
- `VersionResult.txt` (ISP `ReadVersionExport`) - project ID, FW version, sub-version.
- `HPVersion.txt` (ISP copy-bank / combine reads) - only on dual-bank firmware [?].
- `IspDebugLog.txt` (ISP, when debug flag `DAT_100901d0` set) - Comm trace.
- `PublicKey.txt` (ISP `ReadKey` via SetCmd path, GUI dialog route).
- Nothing else found: ReadAll/EDID/register dumps are produced by GUI handlers (save dialogs), not exports.

## 6. Open
- [?] Does `GetModuleFileNameW` in ISP use `NULL` (host exe dir) or the DLL handle (PlugIn\)? If the DLL dir, `Comm.dll` is looked up in `PlugIn\`; copy it there or symlink.
- [?] Exact argument/return types of `ReadMcuReg` (+0xF0) and `ReadRegEx` index base; `host.c rdreg/rdmcu` assume `(addr, byte*)`.
- [?] Whether a plugin crashes on the zeroed `CRTDToolComm` extension fields.
- [?] SetCmd for Measure/DPCD/NewCtrlReg/GPIO/Flash/Gamma etc. (only ISP, NewEDID, McuReg, I2C checked).
- Draft host: `scripts/rtd_headless/host.c` (compiles with i686 mingw; never run).
