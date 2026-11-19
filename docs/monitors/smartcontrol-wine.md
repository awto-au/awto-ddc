# Philips SmartControl under Wine, emulated 288E2

Goal (Dan, 2026-11-19): see which DDC/CI / VCP codes SmartControl sends and expects, without touching the real Philips (read-only probe only until Dan's word). Status 2026-11-19: app runs under Wine, finds the emulated monitor, requests the capabilities string; VCP get/set stage blocked (section 6).

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
- Gap: transport 1 is where TPV-extend commands (and raw DDC/CI bytes) go. Capturing them needs a fake NVAPI (`nvapi.dll`, I2C read/write via `NvAPI_QueryInterface`) plus the registry/PCI facts the helper checks (`EnumPCI`, `EnumNV: skip checking`). Next step (section 6).
- EDID: Wine rewrites `Enum\DISPLAY\Default_Monitor\*\Device Parameters` on the first display enumeration, so the EDID is injected after the first `Rescan` and a second `Rescan` reads it (`scripts/smartcontrol_wine.py edid`).

## 4. Scripts

| script | job |
|---|---|
| `scripts/smartcontrol_profile.py [--model NAME]` | build `tmp/wine/monitor_profile.txt` (caps, EDID, VCP table) from the probe files; `--model` renames EDID name + caps `model()` |
| `tools/smartcontrol_dxva2/build.py` | build the shim with `i686-w64-mingw32-gcc`, copy next to the backend |
| `scripts/smartcontrol_wine.py` | `prepare` (unpack zip, profile, shim), `run` (Electron UI), `backend`, `edid`, `wine ...` |
| `scripts/smartcontrol_probe.py CALL...` | start backend, Rescan, inject EDID, Rescan, run REST calls (5 s limit each), copy logs |

- Needs: `wine` 11 (wow64), `7z`, `i686-w64-mingw32-gcc`, all present on this host; no `winetricks` step was required.
- Env gotchas: unset `ELECTRON_RUN_AS_NODE` (VS Code sets it; Electron then behaves as node), `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` (no ICU), leave `mscoree` enabled (wine-mono loads IL-only images), shim linked `-static-libgcc` (else the P/Invoke load fails with "module not found").

## 5. What ran (2026-11-19)

- Electron UI starts under Wine (no window inspected; the UI does not start the backend without a user action, so the backend is run directly).
- Backend starts, REST answers, 4 Wine monitors enumerated, shim loaded by the .NET side (`GetNumberOfPhysicalMonitorsFromHMONITOR` x4, `GetPhysicalMonitorsFromHMONITOR` x4).
- With the injected EDID the app names the monitor `0-PHLC231_PHL 288E2` (also with `--model 288E2UAE`).
- Codes the app sent over the shim so far (the deliverable table, current content):

| call | code | seen | note |
|---|---|---|---|
| `GetCapabilitiesStringLength` | - | yes | after 3 failed raw-I2C caps attempts (500 ms apart) |
| `CapabilitiesRequestAndCapabilitiesReply` | - | yes | accepted the 576-char string, parsed it (`GetMonitorCapabilites CapString:`) |
| `GetVCPFeatureAndVCPFeatureReply` | none yet | no | blocked, section 6 |
| `SetVCPFeature` | none yet | no | blocked |
| TPV-extend (pre2, acode1, extCode) | none yet | no | raw-I2C transport only (section 3) |

- Undocumented codes the app uses: none captured yet. Candidates from the real monitor, to test once the get stage works: readable manufacturer-specific codes E0 E6 E7 E9 EB EC EF F0 F7 FA FB FC FD FE and 68 A8 (see README Philips section).

## 6. Open issues / next steps

- App marks the emulated monitor unsupported (`DDCCISupport` false); `GetStandardDDC` then spins at 100 % CPU logging `CheckSupport false` (backend bug without a supported monitor; the probe script times out after 5 s and kills Wine). Not the model name: `288E2UAE` (in the app's list) behaves the same. Suspect `DDCSupportJudge_C` needs a raw-I2C answer. Next: fake NVAPI I2C (+ PCI/driver facts), or find the judge's inputs by decompiling the .NET libs (obfuscated; `ikdasm` fails, no ILSpy on host, nuget download is denied here).
- Raw-I2C transport emulation (fake `nvapi.dll`, DDC/CI responder with the 288E2 profile): needed for TPV-extend capture. Larger job, own issue.
- Read the SmartControl EULA (installer licence page) and note restrictions in `/vendors/philips/sources/smartcontrol/README.md`.
- Repo is public: this page holds protocol-level facts only; Dan to confirm it may be merged (vendor-software notes rule in `~/.claude/CLAUDE.md`).
- Real-monitor test of any code the app sends: only with Dan's word, unit 3 first.
