# RTD2795T SDK / source / debug-firmware hunt

Date: 2026-11-04T13:30:00+10:00. Read-only research; nothing committed; only 4 small test bins fetched to the session scratchpad (not vendor store).

## Verdict

- **SDK for RTD2795T found: PARTIAL, strongly positive.** A leaked Realtek Keil-C51 SDK for the **RL64xx family** is public; the RL6449 series is register-compatible with the RTD2795T (see "Chip mapping").
- Not labelled "RTD2795" anywhere in the source (internal names only: `RL6449`, `RL6432`, `RL6410`, ...).
- Buildable in principle: user/app layer + scaler function C source, prebuilt kernel `.LIB`, Keil project files, link scripts, build tooling. Needs commercial Keil C51 + BL51 (banked linker) on Windows/Wine.
- Corrects the earlier assumption: `Kingdomwhisky/RTD-Scaler-TEST` is **NOT 266x**; it is the 2024-02 RL64xx (27xx-era) SDK.
- Confidence: chip mapping 85% (register-set overlap, not a chip-ID match); buildability 60% (never built; Keil licence + RL6449 `.Uv2` completeness unverified).

## Chip mapping (RL64xx -> RTD)

Method: set of register addresses from SDK `RL64xx_Series_Common_RegCommonInclude.h` vs our `re/regdb/*.tsv.gz` (REG rows, Wine-free, 2026-11-04).

| SDK series | SDK regs | vs RTD2795T-CG (9209) | vs RTD2785TM (5700) | vs RTD2797UPM (11380) | Reading |
|---|---|---|---|---|---|
| RL6449 | 10789 | **8870 (96%)** | 4981 | 6784 | = RTD2795T family |
| RL6432 | 6129 | 4284 | **5332 (94%)** | 5029 | = RTD2785/2775 family (Kingdomwhisky's other repo says "based on the RTD2785 solution") |
| RL6410 | 12531 | 5984 | 5092 | **10944 (96%)** | = RTD2797 family (linsn_2796 / avita_rtd2776 projects are RL6410) |
| RL6492 | 4208 | 2443 | 2466 | 2468 | smaller part, not ours |

- Page 0x3A OSD names match our regdb (`P3A_07_FRAME_CTRL_07` = 0x3A07).
- Not proven: exact RL6449 <-> 2795T-CG suffix mapping. Verify by diffing field-level names and `ID_REG`/product code (0xCF2) handling in `RL6449_Series_McuInterface.h`.

## Candidates

| URL | chip (RL / RTD) | type | licence / leak status | relevance |
|---|---|---|---|---|
| https://github.com/Kingdomwhisky/RTD-Scaler-TEST (3791 files, 19 MB, pushed 2024-02-22) | RL6369/6410/**6432**/**6449**/6463/6492 (+6193); 6432 build output present | **SDK-source** (Keil .Uv2, C51 user+kernel C, `L51_bank.a51`, per-series prebuilt `*_FunctionLib.LIB`, `Tool/build/auto_link.exe`, `HexToBin.exe`); also prebuilt `Output/RL6432_BEACON/*.bin` (393216 B), 3.4 MB `.m51` link map, `.H00-H05` bank hex | Realtek-confidential header ("proprietary, confidential ... c 2003-2012"), no licence file, leaked/uploaded by a customer FAE (history: "FW_UNITED_C23", Typical OSD) | **PRIMARY.** RL6449 = our chip family. Includes `Pcb/RL6449/LQFP_216,156`, `RL6449_Project.h`, `RL6449_Project_Link.lin`, `Bin/RL6449_Project.cmd` |
| https://github.com/Kingdomwhisky/Ambient-Sensor-Explore | RL6432 ("RTD2785 solution") | SDK-source (same tree as above) | same | duplicate; RTD2785 label confirms RL6432 mapping |
| https://github.com/Llong1/avita_rtd2776 (67 MB, 2019-12) | RL6193 + **RL6410** (RTD2776/2796 class) | SDK-source (svn `trunk`, `doc`, `tool`), RL6410 + RL6193 `.LIB`, `.lin`, hex outputs | same Realtek header; no licence | older 27xx-era SDK, different series (RL6410), 4K/BGA; useful as 2nd reference |
| https://github.com/weimuxing/linsn_2796Code (6.8 MB, 2018-06) | RL6193/**RL6410** (RTD2796) | SDK-source (`source/`) | same | RL6410 reference; smaller |
| forks of Kingdomwhisky: iBolot/RTD-Scaler-TEST, fu709691151/rtd-scaler-test, yu1741588584/RTD-Scaler-TEST; forks of avita: ~12 (weiquan886, rayPopo, skylerwang1, Kreedb, haivilwu, jutyy5, JSssssss, ahhz-create, ganhailin, laijainGui, Kiloland, Zackeryyc) ; xtxbruin/linsn_2796Code | as parents | SDK-source mirrors | same | survivability if originals are DMCA'd |
| https://github.com/balika011/realtek_display (docs pushed 2026-01-04) | RTD2795T-CG..2797 (CustomerTool V3.6 data), R1811D/RTD2797UPM boards | **tool + docs + binaries** | community mirror, vendor docs | `rtd_docs/RTD2796-CG_confidential_specification.pdf` (27.5 MB), `RTD2797P-CG_confidential_specification.pdf` (3.6 MB), `RTD2785T-CG_Brief_Spec_20160727.pdf`, `rtd27x6_4k2k_v8_20160713.pdf`, `2796OSD菜单说明文档综合V1.0.pdf`, `2556-2796...OSD-v3.1.pdf`, `RTD2786-CG_Brief_Specification.pdf`, OSD/logo/RTDTool manuals; Dell/Razer/R1811D firmware (below) |
| https://github.com/roufsweb/portable-display | RTD2556/2550 (+V3.8 tool with RTD2795T-CG scaler dir) | tool + binary | community | origin of V3.8 tool; `02_RTDCustomerTool_V3.8/IspDebugLog.txt` 1.84 MB; no 279x firmware, no source |
| https://github.com/Dizi0/RTD-Firmwares | RTD2556/JG2555TB (`RTD-Firmware-Studio.exe` 19.6 MB, `rtd-cli.exe`, rtd-gui Rust source) | tool + 100+ binaries; `docs/memory_map.md`, `flashing_guide.md`, `pinouts_edp.md` | community | 2556-class only (851968 B = 13x64 KB banks). Banked-call doc: `?B_SWITCH` at 0x02C1 (2556). Template bins, checksum = 16-bit byte sum |
| https://github.com/wbcbz7/RTDTool-Comm-CH341A | n/a | tool (CH341A Comm DLL) | community | flasher only; other repos of this uploader not combed |
| https://github.com/naorunaoru/rtdflash | RTD2795-family | flasher | open | already used in awto-ddc |
| https://github.com/KerJoe/ORTD2662, KunYi/RTD266x, floppes/RTD266xFlash, KerJoe/RTDMultiProg | RTD266x | open firmware/flashers | open | wrong chip (confirmed) |
| https://gitcode.com/open-source-toolkit/c27d65 (mirror of CSDN download 88628144, vendor "rtddisplay", WeChat rtddisplay) | titled "RTD2795T/UT source" but contents are **RL6336 (RTD2383-class)**, RTD2011 OSD, 692 files, 3.08 MB 7z | SDK-source (wrong chip) | paid download; commenters: "not 2795" | MISLABELLED. Do not fetch |
| https://www.rtddisplay.com (vendor; sells "RTD2775QT/RTD2795T eDP 4K60 firmware/driver/upgrade tool") | RTD2795T | binary (768 KB firmware) | commercial | unvisited; possible source of 2795T eDP reference images |
| NStevenU/UPerfect-QSL02-Custom-Firmware | RTD2775QT (2795T-class regs) | custom firmware binary/patch | public | niche; 2795T-architecture claim |
| searches: GitLab, Codeberg, sr.ht, Bitbucket, SourceForge, grep.app | - | not run to completion | - | `gh search code` + DuckDuckGo(playwrong) only this pass; widen before declaring exhaustive |

## What is in the primary SDK (Kingdomwhisky/RTD-Scaler-TEST)

- Files: `STD_FW_1P.Uv2` / `STD_FW_1P_BEACON.Uv2` (Keil v2 project), `Kernel/Common/{C_STARTUP,STARTUP,L51_bank}.a51`, `Kernel/Common/RL6432_Gen_Option.h` (and per-series), `Project/Header/RL6449_Project*.h|.lin`, `Pcb/RL6449/...`, `Panel/*.h` (100+ panels incl. eDP), `Kernel/Scaler/RL6449_Series_Scaler/Lib/{RL6449_Series_Lib.Uv2, Output/RL6449_FunctionLib.LIB 438 KB}`.
- Register map header: `Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h` (paths follow the RL6432 pattern; fetched RL6449 copy 1 MB).
- Build chain (Keil C51/BL51, uVision batch): awto-sdcc `docs/keil-c51.md` ("SDK toolchain as shipped").
- Not verified: that the RL6449 `.Uv2` + all libs are present (only RL6432 Beacon has an `Output/` tree); whether the `.LIB` kernel is source-less (ScalerFunction/Lib/Code C sources are present for OSD, so partial).
- Fetch plan if proceeding: `~/vendors/realtek/sources/rtd-scaler-sdk-rl64xx/` (own directory, manifest + SHA-256, EULA/confidentiality note: leaked, "shall not be disclosed"). `git clone` is fine here (3791 files, 19 MB); also mirror Llong1/avita_rtd2776 (67 MB) for RL6410. Repo stays out of public repos/issues (vendor-binary/commercial rule: analysis OK, publishing the content or conclusions not).

## Debug / engineering / un-stripped firmware images

No true debug build (assertions / verbose log strings) found. Closest items:

| Item | URL | Chip | Size | Stripped? | Notes |
|---|---|---|---|---|---|
| **RL6432 Beacon link map `RL6432_Beacon_Project.m51`** | Kingdomwhisky/RTD-Scaler-TEST `Output/` | RL6432 (RTD2785 gen) | 3.4 MB | **has symbols**: ~13.9k PUBLIC/SYMBOL lines, bank:address (e.g. `C5:CA4AH _ScalerOsdWriteByte`, `C4:FB1EH UserCommonDdcciHandler`) | Not a debug image, but real function names + bank addresses for a Realtek banked build. Best naming source for Ghidra; different chip gen, so match by function body, not address |
| RL6432 Beacon `.bin` + `.H00-H05` bank hex | same | RL6432 | 393216 B (bins 154-183 KB each) | unstripped hex banks only per-bank; image itself has no debug strings | Pair with `.m51` to label every function (same build, 2024-02-20 18:41) |
| Razer Raptor 27 144Hz V1.01 | balika011/realtek_display `firmwares/` | **RTD2797UPM** (string present) | 2,097,152 B | production; ~1.3k strings (len>=6), no assert/debug/.c names | 279x sibling; closest *production* binary to compare against our 2795T dump |
| Dell G3223D M3C101/104/105 | same | 27xx (chip suffix not in strings) | 1,638,400 B | production; ~2.9k strings, 1 debug-ish hit | Dell build, likely richer OSD/strings; chip unconfirmed |
| R1811D LM270QQ2-SPA3 / R9A18 / LE550PQL V2-V5(IIS) | same | R1811D board (27xx-class) | 1.5-2.0 MB | production; ~1.4k strings | board fw dumps |
| `IspDebugLog.txt` | roufsweb V3.8 | tool log, not firmware | 1.84 MB | n/a | ISP command trace, useful for protocol, not code |
| `DebugCode.h`, `DebugString.h`, `PlugIn/DebugMessage` | CustomerTool dirs | tool-side | 4.8-6 KB, DLL 3 MB | n/a | host-side firmware debug-message table (UART/DDC debug message IDs) -- the *firmware* emits numbered debug codes, which this table decodes. Worth checking whether our image emits them |
| Dizi0 / roufsweb 2556/2550 images (100+) | see above | RTD2556/2550 | 320-850 KB | production | wrong chip |

- Strings counts are from `strings -n 6` on the fetched files (2026-11-04); "no assert/debug/.c" = no match for `assert|debug|*.c:|Scaler[A-Z]`.
- A "FACTORY" file exists: `PCB800869_FACTORY_FULL_BACKUP_512KB.bin` (RTD2556). Factory-mode is a compile option in this SDK (`RTDFactoryMode.c`, `RTDFactoryFunction.c` in the RL6336 tree), not a separate image.
- Practical path to a debug build: compile the SDK with its debug/UART-message options (`_DEBUG_MESSAGE_SUPPORT`-style flags in Gen/Project options; names unverified) -- gives our own symbols + `.m51`.

## Next steps

- Clone Kingdomwhisky/RTD-Scaler-TEST into `~/vendors/realtek/sources/` with manifest (own dir); diff `RL6449_Series_McuInterface.h` against our regdb for `ID_REG` 0xCF / product code 0xCF2.
- Check whether `Project/Header/RL6449_Project.h` + `.lin` link with the shipped libs; identify Keil version (BL51 V6.11 used here, 2024-02-20).
- Use the RL6432 `.m51` + our regdb to seed Ghidra names (awto-2000 pipeline per memory).
- Search remaining hosts (GitLab, Codeberg, sr.ht, Bitbucket, SourceForge, grep.app) for `RL6449`, `_RL6449_SERIES`, `RtdDseries`, `UserCommonDdcci`, `STD_FW_1P`; check www.rtddisplay.com.
- File as issue in awto-ddc (not done here: research-only brief; coordinator to file).
