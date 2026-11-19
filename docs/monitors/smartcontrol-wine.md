# Philips SmartControl under Wine, emulated 288E2

Goal (Dan, 2026-11-19): see which DDC/CI / VCP codes SmartControl sends and expects, without touching the real Philips (read-only probe only until Dan's word). Status 2026-11-19: app runs under Wine against an emulated monitor (dxva2 + nvapi/I2C shims) and its DDC/CI traffic is logged (section 5).

## 1. Source and files

- Installer: Philips download via the winget manifest `Philips.SmartControl` 7.2.0 (2026-04-21); stored in `/vendors/philips/sources/smartcontrol/` (manifest README there: URL, date, size, SHA-256, EULA status).
- EULA: not read, not accepted (text is inside the NSIS script, not extracted). Open: read it and note restrictions (section 6).
- Run tree: payload unpacked with `7z` (installer never executed), prefix + tree in `tmp/wine/` (untracked). Per vendor rules this repo holds no binaries, hashes or extracted material; section 2 is protocol-level.

## 2. How SmartControl 7.2 talks to a monitor

- Electron UI -> local REST (Kestrel, `bin/SmartControl.exe --urls http://*:PORT`, Swagger on) -> .NET libs -> native `DDCHelperLib.dll` (i386).
- REST DDC surface (whole list): `Main/Start`, `Rescan`, `SwitchDisplay?name`, `GetStandardDDC?eVCPOpCode_e`, `SetStandardDDC?eVCPOpCode_e&i32Value`, `GetTPVExtendDDC?pre2&acode1&extCode`, `SetTPVExtendDDC?pre2&acode1&extCode&i32Value`, `GetTaskResult?parm`.
  - Standard = MCCS VCP by opcode. TPV extend = vendor-specific commands addressed by 3 bytes (pre2, acode1, extCode): the undocumented-code surface.
- Native exports: `getStandardDDCCIValue_C`, `setStandardDDCCIValue_C`, `getTPVExternDDCCIValue_C`, `setTPVExternDDCCIValue_C`, `DDCSupportJudge_C`, `EnumMonitorCapabilitesStr`, `MonitorGetFactorySN_C`, `SwitchGetCommandChecksum`.
- Transports inside `DDCHelperLib`, tried in this order (from its own log strings):
  1. raw DDC/CI I2C write/read: via NVAPI I2C, AMD ADL I2C (`atiadlxx`, `atiddc`), Intel CUI/SDVO/i9xx register access, Matrox; on Win7+ without these it logs `DDCCIWrite Failed: ERROR_NOTSUPPORTEDBYVISTAAPI`.
  2. Windows "Vista API" = `dxva2.dll`: `GetNumberOfPhysicalMonitorsFromHMONITOR`, `GetPhysicalMonitorsFromHMONITOR`, `GetCapabilitiesStringLength`, `CapabilitiesRequestAndCapabilitiesReply`, `GetVCPFeatureAndVCPFeatureReply`, `SetVCPFeature`, `DestroyPhysicalMonitor`.
- EDID: from registry `Enum\DISPLAY\*\*\Device Parameters\EDID` (and NVAPI/ADL when present).
- USB path (`SupUsbDDC` per model in the app's model list): Genesys `GL_SDK.dll`, Realtek `RhHidAPI.dll`, VIA hubs, for monitors with a USB-hub DDC bridge. Not the 288E2 route.
- The app ships a supported-model list (138 names); `288E2UAE` is listed, plain `288E2` is not.
- Its own log: `%APPDATA%\SmartControlData\backserver\logs\<date>.log` (DDCHelper prints each step, DDC errors included).

## 3. Emulation design (chosen: dxva2 shim, bridge and i2c-stub rejected)

- Route (a): `tools/smartcontrol_dxva2/` = i386 `dxva2.dll` placed next to the backend (`WINEDLLOVERRIDES=dxva2=n`). One fake physical monitor; capabilities string, VCP values from the real 288E2 probe (`tmp/philips/<date>-*`, via `scripts/smartcontrol_profile.py`); every call logged with ISO timestamp to `tmp/logs/smartcontrol_ddc.log`; sets change RAM only.
  - Why: the app's transport 2 is exactly this API, no real I2C device, no hardware risk, call-level log for free.
- Route (b) bridge to unit 3 (bus 11): not needed for logging; only useful later to check real replies to a code the app sends. Needs Dan's go for any write.
- Route (c) i2c-stub / userspace responder: only helps transport 1 (raw I2C), which the app reaches via GPU-vendor libraries, not `/dev/i2c`. Superseded by the next item.
- Transport 1 (raw I2C) is emulated too: `nvapi_shim.c` = i386 `nvapi.dll` (`nvapi_QueryInterface`: Initialize, EnumPhysicalGPUs, GPU_GetConnectedDisplayIds, GPU_GetEDID, I2CRead, I2CWrite) with a DDC/CI responder at 0x6E/0x6F (Get VCP, Set VCP (RAM only), caps fragments, timing) and EDID at 0xA0/0xA1 from the profile. Every I2C transaction is logged in hex. With it the helper takes the NVIDIA branch and the app treats the monitor as supported.
- EDID: Wine rewrites `Enum\DISPLAY\Default_Monitor\*\Device Parameters` on the first display enumeration, so the EDID is injected after the first `Rescan` and a second `Rescan` reads it (`scripts/smartcontrol_wine.py edid`).

## 4. Scripts

| script | job |
|---|---|
| `scripts/smartcontrol_profile.py [--model NAME]` | build `tmp/wine/monitor_profile.txt` (caps, EDID, VCP table) from the probe files; `--model` renames EDID name + caps `model()` |
| `tools/smartcontrol_dxva2/build.py` | build the dxva2 + nvapi shims with `i686-w64-mingw32-gcc`, copy next to the backend |
| `scripts/smartcontrol_wine.py` | `prepare` (unpack zip, profile, shim), `run` (Electron UI), `backend`, `edid`, `wine ...` |
| `scripts/smartcontrol_probe.py CALL...` | start backend, Rescan, inject EDID, Rescan, run REST calls (5 s limit each), copy logs |

- Needs: `wine` 11 (wow64), `7z`, `i686-w64-mingw32-gcc`, all present on this host; no `winetricks` step was required.
- Env gotchas: unset `ELECTRON_RUN_AS_NODE` (VS Code sets it; Electron then behaves as node), `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` (no ICU), leave `mscoree` enabled (wine-mono loads IL-only images), shim linked `-static-libgcc` (else the P/Invoke load fails with "module not found").

## 5. What ran (2026-11-19) and the code list

- Backend under Wine, REST answers, emulated monitor named `0-PHLC231_PHL 288E2UAE`; `Rescan` reads every feature in the capabilities string, `Start` returns the feature skeleton.
- Frame format observed on the I2C wire (host to monitor, dest 0x6E, then `51 <0x80|len> <opcode> ... <chk>`):
  - Get VCP: `51 82 01 <code> <chk>`; caps: `51 83 F3 <off hi> <off lo> <chk>` (offsets step 0x20).
  - TPV-extend Get = Get-VCP opcode 01 with a 3-byte code: `GetTPVExtendDDC(pre2,acode1,extCode)` sends `51 84 01 <pre2> <acode1> <extCode> <chk>` (e.g. `01 E0 01 00`).
  - Support probe sent on every Rescan: `51 87 01 FE EF 13 00 00 20 <chk>`, reply expected up to 35 bytes (our 11-byte reply was accepted). Real reply format unknown, needs a trace from a real unit.
  - Before any of it the app reads EDID at 0xA0/0xA1 and tries VCP 0x14 as a support test.
- Standard codes the app queries at Rescan (`GetVCP`, from the log): 04 10 12 14 16 18 1A 60 62 72 86 8D A5 C0 C9 CC D6 DC E9 EC F6 F7 FE. Note 04 ("restore factory defaults") is only read, as a support probe; the 288E2 reports it not readable, so on the real unit a read of 04 is the unknown to check first.
- Code names the UI uses (OP_xx table in the app): 10 Luminance, 12 Contrast, 14 SelectColorPreset, 16/18/1A VideoGainDrive R/G/B, 60 InputSource, 62 AudioSpeakerVolume, 72 Gamma, 86 DisplayScaling, 8D AudioMute, 92 TVBlackLevelLuminance, A5 WindowSelect, AA ScreenOrientation, CC OSDLanguage, D6 PowerMode, DC DisplayApplication, E9 ResolutionNotifier, EC PIPPBPSizeLocation, ED InputAuto, F2 PowerLED.
  - Not in the 288E2 scan / caps: 92 AA ED F2 (app features the monitor does not advertise). E9 EC F6 F7 FE are manufacturer-specific codes the 288E2 does answer.
- Set side: the app issues `SetVCPFeature` / `03 <code> <hi> <lo>` only on user actions (brightness stepping seen via `SetStandardDDC`); none sent at Rescan.
- Undocumented-code candidates for a read-only real-unit check (reads only, Dan's word for anything else): E9 EC F6 F7 FE plus the TPV-extend 3-byte form and the `FE EF 13 00 00 20` probe.

## 6. Open issues / next steps

- TPV-extend codes the UI sends for its features (SmartImage, LowBlue, ECO, PIP/PBP...) are not enumerated: the UI talks to the backend over SignalR; drive it (or call `GetTPVExtendDDC` per feature once the feature to (pre2,acode1,extCode) mapping is found; .NET libs are obfuscated, `ikdasm` fails, decompiler needs approval).
- Reply format of the 35-byte TPV probe: needs a real-monitor trace (unit 3 firmware, or Dan's word for the Philips, read only).
- `SwitchDisplay` spins the backend; `Start` skeleton has no opcodes.
- Read the SmartControl EULA (installer licence page) and note restrictions in `/vendors/philips/sources/smartcontrol/README.md`.
- This page and the shim notes stay on the branch, not merged, until Dan confirms (vendor-software design-notes rule).
