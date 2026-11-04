# RTDCustomerTool: firmware-relevant contents (mining result)

- Mined: 2026-11-04T14:00+10:00. Method: static only (unzip into a fresh dir, `file`/`strings`/`wrestool`/byte scans). Nothing run.
- Packages: V3.8_20221101 (26 MB zip, 72 MB extracted), V3.7_20190114 (16 MB zip, 31 MB extracted).
- Scratch extract (vendor data, outside git): `~/vendors/realtek/analysis/rtdtool-mine/{v38,v37}/`.
- Related: [db-bin-format](reversing/realtek-rtd/db-bin-format.md), [rtdtool-gui-map](rtdtool-gui-map.md), [rtdtool-headless-feasibility](rtdtool-headless-feasibility.md), [rtdtool-debug-notes](rtdtool-debug-notes.md).

## Verdict

- No firmware source, no 8051 code, no image template, no golden RTD2795T image, no OSD font, no splash/logo bitmap, no EDID template, no caps string, no panel-timing table.
- The tool is a PC-side register/ISP debugger. It writes a user-supplied `.bin` (finds it in the exe dir) and never carries one.
- File inventory by type, both versions: 0 x `.c`/`.a51`/`.asm`/`.uvproj*`/`.hex`/`.omf`/`.lib`/`.a`. Only `.h` = 2 debug-message headers (x2 versions).

## Inventory (V3.8)

| Item | What it is | Firmware use |
|---|---|---|
| `RTDTool.exe`, `Comm.dll`, `Comm/*.dll`, `PlugIn/*.dll`, `RSGrid.ocx` | MFC PC code (x86). Resources = cursors/icons/dialogs/strings/PNG skins/toolbar defs | none |
| `PlugIn/PlugIn_NewEDID.dll` | EDID/CEA/DisplayID editor dialogs only (class names, no embedded EDID blobs; custom resources are 129-915 B toolbar defs) | none; editor UI only |
| `PlugIn/PlugIn_ISP.dll` | ISP engine (bank erase/write, boot flag). Already decompiled: `~/vendors/realtek/analysis/PlugIn_ISP.c` | protocol only |
| `RTDScaler/<chip>/DB.bin` | register database (names, fields, reset values, DPCD text) | register map, not image |
| `RTDScaler/<chip>/GPIO.bin` | pin database | pin map |
| `RTDScaler/<chip>/ReadAll.txt`, `version.txt` | page list, per-page type arrays, DB spec revision | register map |
| `PlugIn/Flash.dat`, `FlashSet.dat`, `SWREN.dat` | SPI-flash chip table with command scripts (84 chips) | ISP opcodes only |
| `DefaultDebugMsgFile/DebugCode.h`, `DebugString.h` | 56 firmware debug-message IDs `0x8901..0x893F` + text | see below |
| `IspDebugLog.txt` (V3.8, 1.8 MB) | real ISP session log from a customer, 2019-12..2022-11 | see below |
| `Comm/Comm_RealtekUSB.dll` | refers to `realsil.bin` (Realtek USB script file, not shipped) | n/a |

- V3.7 differs: empty `RTDScaler/` (no chips), no `Flash.dat`, `FlashSet.dat` is 6270 B vs 6558 B. Nothing extra over V3.8.
- No PE overlay / appended blob / big RCDATA found in any DLL; the large DLL sizes are static MFC + PNG skins (485 PNG in `PlugIn_GPIO.dll`).

## Chip support (RTD2795T explicit)

- `RTDScaler/RTD2795T-CG/`: `DB.bin` 4.1 MB, `GPIO.bin` 36 KB, `ReadAll.txt`, `version.txt`. ScalerID 49 (the "Read scaler type: 49" in the ISP log), IcType 1, PageCount 256, PageSelect 0x9F, DB SpecRevision 1092.
- Shipped chips (ScalerID): RTD2776B-CG 42, RTD2537T-CG 44, RTD2797PM-VDL-CG / 2797UPM-CG 45, RTD2775TM-CG / 2785TM-CG 47, RTD2795T-CG 49, RTD2525AR-CG 50, RTD2172 54, RTD2186 56.
- Parameters given per chip: register pages, field maps, pin list, DPCD register text. NOT given: flash layout, bank map, register init sequences, panel config, clock tree.
- Already extracted: `DB.bin` + `GPIO.bin` (parsers in `scripts/`), `FlashSet.dat`.
- Not yet extracted, none is image-like:
  - `DB.bin` post-pool region (RTD2795T: 0x3c66b4..EOF, 147 KB). Sampled: NUL-padded DPCD register description text (DPCD_REV, MAX_LINK_RATE ...). Documentation text, not data the tool writes to a scaler.
  - `ReadAll.txt` `PGxx_TypeArry` per-register type arrays: already cross-checked against `DB.bin` (9,209/9,209).
  - `IPDB.bin`/`DPCDDB.bin`: only exist for RTD2172/RTD2186, not RTD2795T.
  - `PTPG_PageSelect` keys in ReadAll.txt: pattern-generator page selectors (values 106, 152, 1991 on 2795T). Only potential lead; PG = pattern generator, relevant to issue 4 in [firmware-proposal](firmware-proposal.md) (no-signal test pattern).

## Useful structure leaks (small, no image)

### ISP log: bank/flash behaviour of the real tool [fw, log]

- Slave addr in log: 0x94 (8-bit; 7-bit 0x4A, matches our ISP addr).
- Per-flash sequence on 49-type scalers (RTD2795T, 190 sessions): chip erase, then write banks in order 11, 8, 7, 6, 5, 4, 3, 2, 1, 0 (banks 9 and 10 never written). Each bank write = 64 KB class unit, ~8-9 s per bank on a 1 MiB part.
- Bank 11 first, bank 0 last: bank 0 holds the boot vector, so it is committed last.
- Type 51 and 37 sessions (other chips) use "Auto Set Flash Partition" -> `Set Flash Partition, addr: 0x7000`, erase banks 12..0, and write an "isp boot flag" at bank 0 addr 0x7000: bytes `55 AA` then the first 14 bytes of what follows (flag is cleared on erase, rewritten at the end).
- Log truncates the flag line to 16 bytes. Sampled payload after `55 AA` is 8051-looking code, varies per image. Only ~16 bytes per line; reassembly into code is not possible.
- Flash types seen: P25Q40H, P25Q80H, FM25Q08A, MD25D80D, FM25Q04, FM25F04, MX/KH25L20XX. Third-party boards, not our MX25L8006E (already noted in [flash-unprotect](flash-unprotect.md)).
- Scaler type ids seen in log: 33, 37, 39, 41, 47, 49, 50, 51 (plus 0 = read failure); 51, 37, 39, 41, 33 are not in the shipped chip list.

### DebugCode.h / DebugString.h [fw-ish]

- 56 message IDs 0x8901..0x893F with display strings: source-unstable, measured-input HV changed, input timing H/V/interlace/total/start/width, memory check failed, sys mode reset state, source judge / switch port / no-cable search, eeprom fix port.
- These are the debug-channel message codes the firmware emits (tool decodes them, see rtdtool-debug-notes). Identical in V3.7 and V3.8.
- Value to us: names for firmware state machine (source search, timing measure, no-signal handling) when labelling Ghidra functions; a firmware `printf`/debug-send call site with a 0x89xx constant is identifiable. Strings contain vendor-developer chatter ("wuanne test") - confirms they are lifted from source `DebugMessage` calls.
- Not firmware source; no code, no addresses.

### FlashSet.dat / Flash.dat

- 84 chip entries each: name, JEDEC id bytes, sizes/opcodes, and comma-separated hex scripts of ISP-engine register writes (reg 0x60 ctl, 0x61 opcode, 0x64-0x66 addr, 0x6F ISP ctl, 0x70 data): per-chip unprotect/status sequences.
- Decoder already exists (`scripts/rtd_flashdb_parse.py`). `Flash.dat` is a different, wider record set with UTF-16 names + same scripts as text; not yet separately decoded (worth a diff vs `FlashSet.dat`, low value).

## Gaps (what is NOT in the tool, so must come from elsewhere)

- Any firmware image or code for RTD2795T (only our own dumps: `~/vendors/realtek/analysis/dumps/`).
- Default OSD font / glyph RAM contents, boot logo/splash bitmap (the tool's `CSplashScreenEx` = PC GUI splash only; see [boot-logo](boot-logo.md)).
- Panel config / timing tables, eDP link settings, gamma/OD tables (the tool has Gamma/OD plug-in DLLs but they edit live scaler registers; no default tables shipped).
- EDID templates (editor only), DDC/CI caps string.
- Build artefacts: no Keil project, map, hex or OMF; no SDK headers (`.h` only debug messages).
- Flash layout / bank map beyond what the ISP log shows (bank write order, 0x7000 boot-flag).

## Worth pulling into the build effort

1. Debug-message IDs (`DebugCode.h`/`DebugString.h`): label firmware debug/state call sites in Ghidra. Cheap, concrete.
2. ISP log bank order for scaler type 49 (11, 8..0, bank 0 last, no 9/10) as the write-order template for our own flasher (matches our dumps: banks 0-6 used, rest 0xFF).
3. `PTPG_*` pattern-generator entries in ReadAll.txt + regdb: target for the no-signal test-pattern fix (not a build input).
4. Everything else (DB/GPIO/FlashSet) is already consumed. Image/font/splash/panel data must come from our own dumps or the open-source prior art ([README](reversing/realtek-rtd/README.md)), not this tool.
