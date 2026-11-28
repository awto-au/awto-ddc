# Philips SmartControl under Wine, emulated 288E2

Goal (Dan, 2026-11-19): see which DDC/CI / VCP codes SmartControl sends and expects, without touching the real Philips (read-only probe only until Dan's word). Status 2026-11-19: app runs under Wine against an emulated monitor (dxva2 + nvapi/I2C shims) and its DDC/CI traffic is logged (section 5).

## 1. Source and files

- Installer: Philips download via the winget manifest `Philips.SmartControl` 7.2.0 (2026-04-21); stored in `/vendors/philips/sources/smartcontrol/` (manifest README there: URL, date, size, SHA-256, EULA status).
- EULA: not read, not accepted. Dan 2026-11-28: not a constraint (compatibility RE).
- Decompile output: `/vendors/philips/smartcontrol/analysis/` (section 7); 2026-11-28 unpack in `tmp/philips_re/` (untracked).
- Run tree: payload unpacked with `7z` (installer never executed), prefix + tree in `tmp/wine/` (untracked). Per vendor rules this repo holds no binaries, hashes or extracted material; section 2 is protocol-level.

## 2. How SmartControl 7.2 talks to a monitor

- Electron UI -> local REST (Kestrel, `bin/SmartControl.exe --urls http://*:PORT`, Swagger on) -> .NET libs -> native `DDCHelperLib.dll` (i386).
- REST DDC surface (whole list): `Main/Start`, `Rescan`, `SwitchDisplay?name`, `GetStandardDDC?eVCPOpCode_e`, `SetStandardDDC?eVCPOpCode_e&i32Value`, `GetTPVExtendDDC?pre2&acode1&extCode`, `SetTPVExtendDDC?pre2&acode1&extCode&i32Value`, `GetTaskResult?parm`.
  - Standard = MCCS VCP by opcode. TPV extend = vendor-specific commands addressed by 3 bytes (pre2, acode1, extCode): the undocumented-code surface.
- Transports inside `DDCHelperLib`, tried in this order (from its own log strings):
  1. raw DDC/CI I2C write/read: via NVAPI I2C, AMD ADL I2C (`atiadlxx`, `atiddc`), Intel CUI/SDVO/i9xx register access, Matrox; on Win7+ without these it logs `DDCCIWrite Failed: ERROR_NOTSUPPORTEDBYVISTAAPI`.
  2. Windows "Vista API" = `dxva2.dll`: `GetNumberOfPhysicalMonitorsFromHMONITOR`, `GetPhysicalMonitorsFromHMONITOR`, `GetCapabilitiesStringLength`, `CapabilitiesRequestAndCapabilitiesReply`, `GetVCPFeatureAndVCPFeatureReply`, `SetVCPFeature`, `DestroyPhysicalMonitor`.
- EDID: from registry `Enum\DISPLAY\*\*\Device Parameters\EDID` (and NVAPI/ADL when present).

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
  - Support probe sent on every Rescan: `51 87 01 FE EF 13 00 00 20 <chk>`. It reads the factory serial: real 288E2 reply `6E 8D <13 ASCII bytes> 98` (no opcode byte, len 0x8D = 13, text = the EDID serial; chk = XOR of 0x50 and all reply bytes). The responder now answers it the same way.
  - Before any of it the app reads EDID at 0xA0/0xA1 and tries VCP 0x14 as a support test.
- Standard codes the app queries at Rescan (`GetVCP`, from the log): 04 10 12 14 16 18 1A 60 62 72 86 8D A5 C0 C9 CC D6 DC E9 EC F6 F7 FE. Note 04 ("restore factory defaults") is only read, as a support probe; the 288E2 reports it not readable, so on the real unit a read of 04 is the unknown to check first.
- Code names the UI uses (OP_xx table in the app): 10 Luminance, 12 Contrast, 14 SelectColorPreset, 16/18/1A VideoGainDrive R/G/B, 60 InputSource, 62 AudioSpeakerVolume, 72 Gamma, 86 DisplayScaling, 8D AudioMute, 92 TVBlackLevelLuminance, A5 WindowSelect, AA ScreenOrientation, CC OSDLanguage, D6 PowerMode, DC DisplayApplication, E9 ResolutionNotifier, EC PIPPBPSizeLocation, ED InputAuto, F2 PowerLED.
  - Not in the 288E2 scan / caps: 92 AA ED F2 (app features the monitor does not advertise). E9 EC F6 F7 FE are manufacturer-specific codes the 288E2 does answer.
- Set side: `SetVCPFeature` / `03 <code> <hi> <lo>` only on user actions (brightness stepping seen via `SetStandardDDC`); none sent at Rescan.
- TPV-extend (`pre2, acode1, extCode`): the extended-DDC call path exists in the backend and REST (`GetTPVExtendDDC` / `SetTPVExtendDDC`), but the UI never calls it for this model: the extern opcode enum in the app has a single `Null` entry and the OP table below is all standard-form VCP. TPV-extend table for the 288E2: empty. The only vendor-form frame the app sends on its own is the serial probe above. Full decode: section 7.
- Value enums: section 8.
- Real 288E2 replies (read-only, `scripts/philips_raw_ddc.py`, raw in `tmp/philips/20261119-rawddc.txt`; reply = `6E 88 02 <result> <code> <type> <mh> <ml> <sh> <sl> <chk>`):
  - E9: result 00, type 01, mh 00 ml 02, sh 00 sl 02. EC: 00, 01, 04 03, 00 00. F7: 00, 01, 00 42, 00 42. FE: 00, 01, FF FF, 00 00.
  - F6: result 01 (unsupported) although F6 is in the capabilities string (`01 F6 01 FF FF 00 00`).
  - Reply buffer from the NVIDIA I2C-over-AUX read carries stale bytes after the checksum (read 40, frame is 11); ignore past len.
  - Real replies match the emulated ones (E9 EC F7 FE from the same scan); only F6's result code differs: the profile has F6 absent, so the responder also answers unsupported.

## 6. Open issues / next steps

- No TPV-extend codes are used by the app for the 288E2 (sections 5, 7).
- `SwitchDisplay` spins the backend; `Start` skeleton has no opcodes.
- EULA: Dan 2026-11-28: not a constraint for this compatibility work.
- Open: meanings of E0 E7 EB EF F0 FA FB FC FD FF (not in the app; section 8). Read-only probes and write tests need Dan's OK: awto-ddc#381.

## 7. Decompile results (2026-11-28, SmartControl 7.2.0)

- What: all 15 .NET assemblies (ILSpy; .NET Reactor-style obfuscation, strings decrypted by running each assembly's own decryptor), native `DDCHelperLib.dll` + `RhHidAPI.dll` (Ghidra), `app.asar` (Electron UI). Output, tool versions, file map: `/vendors/philips/smartcontrol/analysis/README.md`. Facts below are protocol-level only.
- Confidence tags: [app] = read from the app's enums/builders; [scan] = 288E2 reply (#381); [prior] = public work (section 9).

### 7.1 Frames (host -> 0x6E, reply from 0x6F) [app]
- Write: `51 <0x80|n> <payload n bytes> <chk>`, chk = XOR of 0x6E, 0x51, len byte and payload. Native sleeps 100 ms after every write; retries 3x, 5/10 ms between retries.
- The .NET layer builds the payload; native only frames it. Payload forms:

| call | payload | reply used |
|---|---|---|
| Get VCP | `01 <code>` | 8 bytes `02 <rc> <code> <type> <mh> <ml> <ch> <cl>` |
| Set VCP | `03 <code> <hi> <lo>` | none |
| TPV-extend Get | `01 <pre2> <acode1> <ext>` | 8 bytes; max = bytes 4-5, cur = bytes 6-7 (standard reply layout) |
| TPV-extend Set | `03 <pre2> <acode1> <ext> <hi> <lo>` | none |
| raw Get (`GetExternDDCCIValue`) | `01 <n bytes>` | caller-defined length |
| raw Set (`SetExternDDCCIValue`) | `03 <n bytes>` | none |
| factory read | `01 FE EF <sel> 00 00 <len>` | `<len>` bytes, no opcode byte |
| firmware version string | `01 FE E1 E6 06 00` | 32 bytes; ASCII from offset 4 (offset 3 if byte 3 = 0) |

- Factory read selectors accepted by native: 00-07, 10-14. The app only uses `13` (serial, len 0x20; reply = 13 ASCII bytes on the 288E2 [scan]). Others: meaning unknown.
- `FE E1 E6 06 00` (`GetDisplayFWVersion`): never sent at Rescan for the 288E2 in the 2026-11-19 log; not yet sent to the real unit.
- Internal opcode numbering: `VCPOpCode > 0xFF` = `pre2<<16 | acode1<<8 | ext` (extended), else standard.
- dxva2 cannot carry multi-byte codes; extended/raw forms need the raw-I2C transports (NVAPI/ADL/Intel). [app, prior]

### 7.2 TPV-extend tables [app, prior]
- SmartControl 7.2.0: `E2A0_ExternVCPOpCode_E` = `Null` only. No model uses TPV-extend.
- `MonitorInfo.json` (app.asar, refreshed from `deviceportal.zeasn.tv`): 138 models, fields `Name`, `SupUsbDDC`, `SupOTA` only; no per-model feature/code list. 288E2UAE: `SupUsbDDC false`, `SupOTA true`.
- Known TPV groups on AOC G-Menu (same DDCHelperLib family): `F8 E1` (11 Eco, 12 gamma, 13 DCR, 51 overdrive, 52 HDR, 55-59, 5A dial, 5B FPS, 60-68 Light FX; `F8 E1 00` = support bitmask), `E2 A0` (06 Sniper, 13 USB standby, 18 local dimming, 20 gamut, 36 pixel clean, ...). Untested on the 288E2.

### 7.3 Firmware update path [app]
- Monitor scaler OTA runs only through a USB-hub I2C bridge, never over GPU DDC: VIA hub (VID 2109, functions A3 / A7A9), Realtek hub (0BDA, `RhHidAPI` HID-I2C), Genesys hub (05E3, `GL_SDK`). Also camera, audio, USB hub, PD controller, Ambiglow, LightFX updaters.
- Image: downloaded from `deviceportal.zeasn.tv/direct/component/update` (zip/rar with `.bin`), matched on ModelName.
- Scaler families with ISP flows: MTK (MStar: MST9U, TSUMxxx{G,C,D,2,V,B,U}, MST8556, MT9700/9701/9800/9810), RTK (RTD25xxAR/BR, RTD2525CR, RTD2711, RTD2718/19, RTD2721/22, RTD2723, RTD2738/39, RTD2775/85, RTD27x8R, RTD2795QT, RTD2797/98/99, RTD2727Q/LQ, RTD2788M), NTK (Novatek), HVW (6315, 7315).
  - MTK flow: enter serial debug + GPIO config, enter ISP, flash ID, per-series write-protect disable, SR read/0x00 write, erase, program, verify, WP restore, exit ISP.
  - RTK flow: SetDefaultValue, DetectFlashType, disable HW WP (per-series reg F5 / E3 writes), disable SW WP, erase + CRC check per block, write + CRC, boot-flag sector, reset.
  - Per-model OTA script language: sections of `S - <bytes> - P` lines; `RTKWrite`/`RTKRead` on 8-bit address 0x94/0x95 (7-bit 0x4A, Realtek ISP), `MTKWrite`/`MTKRead` on 0xB2/0xB3 (7-bit 0x59, MStar SERDB); variables with `&=` / `|=`.
- 288E2: no USB upstream port (spec; to confirm on the unit) -> no transport -> SmartControl cannot update its firmware despite `SupOTA true`.

## 8. Code table (288E2)

Columns: code | name | values | R/W | source | confidence. "caps" = in the 288E2 capabilities string.

| code | name | values | R/W | source | conf |
|---|---|---|---|---|---|
| 02 | New control value | MCCS | R/W | caps | high |
| 04 | Restore factory defaults | write any non-zero | W | caps, app (Reset) | high |
| 05 / 08 | Restore lum-contrast / colour defaults | MCCS | W | caps | high |
| 0B / 0C | Colour temp increment / request | MCCS | R/W | caps | high |
| 10 / 12 | Brightness / contrast | 0-100 | R/W | caps, app, scan | high |
| 14 | Colour preset | 01 sRGB, 02 native, 04 5000K, 05 6500K, 06 7500K, 07 8200K, 08 9300K, 0A 11500K, 0B user1 (288E2 caps: 01 04 05 06 07 08 0A 0B) | R/W | caps, app enum | high |
| 16 / 18 / 1A | Gain R / G / B | 0-100 | R/W | caps, app | high |
| 52 / 54 | Active control / performance preservation | MCCS | R | caps | med |
| 60 | Input source | low byte main: 01 VGA, 03 DVI, 0F DP1, 10 DP2, 11 HDMI1, 12 HDMI2, 13 HDMI3, 15/16 USB-C; high byte PIP/PBP sub-input: 21 HDMI1, 22 HDMI2, 23 HDMI3, 24 DVI, 2F DP1, 30 DP2, 31 VGA1, 32 VGA2, 35/36 USB-C. caps `60(00 01 11 12 0F 21 22 2F 31)` mixes both | R/W | caps, app enum | high (main), med (sub) |
| 62 | Speaker volume | 0-100 | R/W | caps, app | high |
| 6C / 6E / 70 | Black level R / G / B | MCCS | R/W | caps | high |
| 72 | Gamma | 0x50 1.8, 0x64 2.0, 0x78 2.2, 0x8C 2.4, 0xA0 2.6 | R/W | caps, app enum | high |
| 86 | Display scaling (picture format) | two app tables: {01 1:1, 02 4:3, 04 16:9, 08 wide, 21 movie1, 22 movie2} and {01 1:1, 02 wide, 05 4:3, 21, 22}; 288E2 reads 08/00/02 (#381) | R/W | caps, app enum | med |
| 8D | Mute | 1 on, 2 off | R/W | caps, app | high |
| 95-98 | Window position TL/BR | MCCS | R/W | caps | med |
| A5 | Window select = PIP/PBP mode | 0x000 off, 0x100 PIP, 0x200 PBP1, 0x400 PBP2, 0x800 PBP3 (allowed set from F7) | R/W | caps, app | high |
| AC / AE | H / V frequency | MCCS | R | caps | high |
| B6 | Display technology | MCCS | R | caps | high |
| C0 | Usage time | hours | R | caps, app, scan | high |
| C6 / C8 / C9 / CA | App enable key / controller (MStar) / FW level / OSD | MCCS | R | caps, scan | high |
| CC | OSD language | 01 T-Chinese, 02 English, 03 French, 04 German, 05 Italian, 06 Japanese, 07 Korean, 08 Portuguese, 09 Russian, 0A Spanish, 0B Swedish, 0C Turkish, 0D S-Chinese, 0E BR-Portuguese, 0F Arabic ... 25 Vietnamese, EF Indonesian (app `Language_E`) | R/W | caps, app enum | high |
| D6 | Power mode | app: 1 on, 4 off with recovery, 5 off; caps 01 04 05 | R/W | caps, app enum | high |
| DC | SmartImage | table E1: 00 off, 01 office, 02 photo, 03 movie, 05 game, 08 economy, 0B LowBlue, 0E EasyRead, 1F SmartUniformity, 50 D-mode. Table picked by the last caps value E1-E4; 288E2 caps `DC` has no list -> E1 | R/W | caps, app enum | high (map), med (288E2 subset) |
| DF | VCP version | MCCS 2.2 | R | caps, scan | high |
| E0 | ? | reads max 4 / cur 3 | R | caps, scan | unknown |
| E6 | PBP state | bit0 = 1 single input, 0 PBP (499P9) | R | scan (not in caps), prior | low |
| E7 | ? (sharpness?) | max 100 / cur 50 | R | caps, scan | unknown |
| E9 | Resolution notifier | 0 off, 2 on | R/W | caps, app, scan | high |
| EB | ? (SmartResponse?) | max 3 / cur 0 | R | caps, scan | unknown |
| EC | PIP/PBP size + location | low byte size 1 small / 2 medium / 3 large; high byte location 1 UR / 2 DR / 3 UL / 4 DL; 288E2 max 0x0403 | R/W | caps, app, scan | high |
| ED | Auto input | on/off | R/W | app (not in caps) | med |
| EF | ? | max FF / cur FF | R | caps, scan | unknown |
| F0 | ? | max 1 / cur 0 | R | caps, scan | unknown |
| F2 | Power LED | 0-4 | R/W | app (not in caps), prior (221P6Q) | med |
| F6 | PIP/PBP swap | write 1 = swap; read = unsupported on 288E2 | W | caps, app, scan | high |
| F7 | PIP/PBP supported type | 02/03/04 = PBP 1-3 windows, 40 = PIP, 42/43/44 = PIP + PBP 1-3; 288E2 = 0x42 (off, PIP, PBP1) | R | caps, app, scan | high |
| F8 | HDR | app enum only | R/W | app (not in caps) | low |
| FA FB FC FD FF | ? | FA FFFF/0, FB FF/5, FC FD FF/2 | R | caps, scan | unknown |
| FE | ? (app reads it at Rescan) | max FFFF / cur 0 | R | caps, app, scan | unknown |
| 68 / A8 | ? | max 5 / max 3 | R | scan (not in caps) | unknown |

## 9. Prior work (search 2026-11-28)

| source | adds |
|---|---|
| github.com/zhzh2001/aoc-osd | AOC TPV-extend `51 84 01 F8 E1 <sel>` / `51 86 03 F8 E1 <sel> hi lo`, reply `6E 88 02 00 F8 <sel> mh ml ch cl`; tested on AOC 22B2HM2B (ADL) |
| github.com/Skyzenfr/gear-control `docs/AGON-PROTOCOL.md` | G-Menu (same TPV DDCHelperLib) enums: groups `F8 E1`, `E2 A0` |
| github.com/Juancjc/signalrgb-aoc-lightfx | TPV write pacing: >= 110-120 ms between writes, ~0.4 s after mode change |
| github.com/edsuuu/monitorctl | `F8 E1 00` = support bitmask; dxva2 cannot send 3-byte codes |
| github.com/rockowitz/ddcutil discussion 642, issues 163/162/385/314/580, wiki "Phillips" | Philips E/F codes undocumented by TPV; E6 bit0 PBP; MStar Philips DF=3.0 quirk; 60=00/15 USB-C on some models |
| github.com/ddccontrol/ddccontrol-db (PHL08DC, AOC3279) | F2 power LED 0-4 (Philips); F8 FreeSync (AOC MStar) |
| github.com/xanderfrangos/twinkle-tray issue 1367 | Philips 60 = 0x15 USB-C |
| flashrom `mstarddc_spi`, `mediatek_i2c_spi`, `realtek_mst_i2c_spi` | MStar ISP 0x49 ("MSTAR", 10/11/12/24), SERDB 0x59; Realtek ISP 0x4A |
| github.com/franc1sc0sv/monitor-firmware | MST9U ISP over HDMI DDC (ADL), flash layout; NVAPI I2C limited to 0x37/0x50 |
| github.com/LA777/philips-display-controller | uses SmartControl DLL names, standard VCP only |
| ddcutil.com/sniffing | DDC bus sniffing method (HDMI only) |

- None public: `FE EF` factory group, `FE E1 E6` firmware string, Philips E0/E7/EB/EF/F0/FA-FF meanings, 288E2 scaler part / service manual.
