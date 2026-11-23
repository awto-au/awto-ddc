# Self-flashing: can the MCU update its own flash? (#232 part 2)

Status 2026-11-18, research only (code, docs, regdb, SDK source; no hardware run, nothing flashed).
Tags (awto-dan `docs/embedded/reversing/README.md`): [confirmed] read in our source / regdb / datasheet, [likely] inferred, [guess] unverified, [measure] needs a hardware run.

## Verdict: GO-IF

- Technically feasible: the firmware already erases / programs banks 14-15 itself (NVRAM), the SDK write path takes any bank 0-15, WP# is a firmware GPIO.
- GO now: prototype steps T0-T2 below (read-back, erase + program of retired / spare sectors, identical-content rewrite of one non-running bank). No code sector at risk.
- GO-IF for a real update of code banks, all of:
  - immutable boot / recovery sector first (#102), so a half-written image never leaves a dark unit with a dead reset vector;
  - updater pinned at a fixed address and never moved by the sticky layout;
  - per-page CRC + whole-image CRC + a valid-marker written last;
  - `boot_last` order (as the host flasher), running bank and bank 0 common via a second hop.
- NO-GO: A/B full images (no space: image = 14 of 16 banks, 15 with bank 14 code; rest is NVRAM / spare; relocation needs 2 MiB, see section 5).
- Value check: host ISP flash is 26 s at 1 MHz and already works on a blank flash; self-update only pays for units with no HDMI DDC access to ISP (DP-only, #177) or remote update.
- Part 1 (warning screen during the host flash) is done and seen on unit 3 (`docs/flash-screen.md`).

## 1. How the firmware writes flash today

- Path: `AwtoFlIo` (`fw/nvram/flash_io.c`) -> `UserCommonFlashWrite / ErasePage` -> `ScalerFlashWrite / ScalerFlashErasePage` [confirmed].
- Access method `_HW_FLASH_ACCESS_METHOD = _FLASH_PORT_ACCESS` (`RL6449_Gen_Option.h:123`) [confirmed]:
  - address FF78-FF7A (bank, hi, lo), data byte to FF7B, FF7C bit0 access_flash_en, bit1 auto-increment [regdb].
  - The xdata-mapped write path (FFF0[0] enable, FFFE bank select) is compiled out.
- Erase: `FF60` common instruction (com_inst 101 = erase), op code FF61, sector address FF64-FF66 (bank, addr hi, lo), start = FF60 bit0 [confirmed, `ScalerCommonNVRam.c:4268`].
- Every op is wrapped: `ScalerFlashWREN(bank, page)` -> WRSR unprotect (+ WREN), op, `ScalerFlashWRDis` -> WRSR re-protect [confirmed].
  - `ScalerFlashWrite` repeats WREN / WRDis per page: ~3 halts per call, ~83 ms max (#151).
  - Unit's flash MX25L8006E: WREN case sets block protect so only banks above the target stay protected (target 0-7 -> protect 8-15 = SR 0x12; 8-11 -> 0x0E; 12-13 -> 0x0A; 14 -> 0x06) [confirmed, `ScalerCommonNVRam.c:1671`]. Every bank 0-15 is covered by the switch.
- WP#: `PCB_FLASH_WRITE_PROTECT(x)` = P8.6 = `MCU_FE26_PORT86_PIN_REG` on the awto board header (`RL6449_AWTO_JXC4K.h:366`); `ScalerFlashSetWRSR` releases it around each WRSR and re-asserts [confirmed]. Same pin the host flasher releases (`docs/flash-unprotect.md`, sys[0xFE26]) [confirmed]. So WP# is controllable from firmware.
- Bank guard: `ucBank < MCU_FFFD_XDATA_BANK_START` returns false; we set FFFD = 0 (`ScalerMcu.c:87`) so no bank is excluded [confirmed].
- Our NVRAM sits in bank 15 pages 11-12 (0xFB000-0xFCFFF); retired registry record 0xFD000-0xFEFFF (never written now) [`docs/nvram-settings.md`]; since 2026-11-18 `0xFD000` holds the host flasher's device manifest (CRC32 per image sector, valid word last), `0xFE000` stays the spare [`docs/flash-registry.md`].
- Watchdog pokes are inside WREN / WRDis (`AWTO_WDT_FEED`) and the page loop (`AwtoWdtLibPoke(10)`) [confirmed].
- Writes through the debug slave (0x3A / 0x3B) are `ScalerGetByte / SetByte` on xdata, not flash programming [confirmed, `ScalerCommonDebug.c:619`].

## 2. What the 8051 executes from during an erase / program

- The MCU fetches code from the same SPI flash [confirmed: all 64 KB code space is banked flash, `mcu-8051.md`; no other code memory].
- A common instruction (erase, WRSR, WREN) halts the 8051 in hardware: "No need to polling, 8051 will halt when common instruction executes" (SDK comments, `ScalerCommonNVRam.c:4293`) [confirmed]. The CPU resumes after the SPI command ends and fetches again from flash.
  - Consequence: no code runs and no interrupt is served for erase <= 200 ms, WRSR <= 40 ms, page program <= 3 ms (datasheet maxima, `docs/delays.md`) [confirmed]; measured halt lengths not recorded [measure].
- Not a "code runs from RAM" design: the halt is a stall, not a fault. Code in the sector being erased is what breaks: after the stall the next fetch reads 0xFF [likely].
- Halt side effects, regdb page FF [confirmed]:
  - FFEE[6] `mcu_peri_non_stop`: peripherals keep running while the MCU is stopped; SDK sets it in `ScalerMcuIspInitial` (`ScalerMcu.c:235`).
  - FFF0[4,3,1]: stop serial / timer2 / timer0-1 on halt (default 0 = run).
  - FFEA[5] `sf_hlt_wdt_en`: stop the watchdog on flash access; off in our build (would also stop it on code fetch, `docs/watchdog.md`).
  - FFEA[6] clear-watchdog works only while code runs; hardware reset at CNT1 = 2 = 1171.8 ms regardless of EA (`docs/watchdog.md`).
- OSD, scaler pipeline, panel and PWM are independent hardware and keep running during a halt (the OSD already survives the host ISP halt, `docs/flash-screen.md`) [confirmed].
- Flash cache: FDA0 `cache_en`, CACHE_LOAD (FDCC) can preload a range and release the MCU by interrupt [regdb]. Cache SRAM is not exposed as code RAM (only the debug port FDC7-FDC9, `mcu-8051.md`) [confirmed]. Do not rely on cache to keep code alive across an erase.
- No SRAM / XRAM code-execution path found: XRAM is 0xD700-0xF6FF xdata only; 8051 Harvard, code space = flash [confirmed absence in regdb + SDK; no vendor doc found stating otherwise].
- No flash-controller mode that frees the MCU found: the ISP mode (FF6F[7] isp_en) gates the 8051 clock entirely ("gating 8051 clock") [regdb]; it is the host path. SPI command completes in hardware but the MCU is stalled for its duration [confirmed]. Host-side page SRAM (256 B, FF70, `docs/flash-burst.md`) is the only buffered program path; whether the MCU can start a page program from it and run on while it completes is [guess] (SDK never does; FF6F is documented usable "in ISP mode"; SDK page program for this build uses the FF7B port).

## 3. Bank / boot layout

- 1 MiB MX25L8006E = 16 banks x 64 KB; code space 64 KB, bank select = XDATA 0xFFFF (reset value 0), bank_en FFFC[0] [regdb, `mcu-8051.md`].
- Our image: common area 0x0000-0x4FFF (vectors, startup, bank stubs, hot code) physically copied into every bank 0-13; banked code from 0x5000 [confirmed, `docs/flash-layout.md`].
  - So running in bank N executes bank N's own common copy. Erasing common of the bank you run in kills the CPU; erasing it in another bank does not.
  - Sticky layout pins chunks to slots (`fw/bank_layout.tsv`); full image 224 sectors = banks 0-13, bank 14 is the 15th code bank (240 sectors when used, #44), bank 15 = NVRAM / manifest / spare (never written by the host image flasher).
- Reset: vector at 0x0000 of bank 0 (LJMP to startup) [confirmed, Dahua dump notes; same for ours, bank reset value 0]. There is no mask boot ROM that validates flash: the chip fetches from flash at reset [likely; the ISP slave 0x4A is hardware and answers on blank flash, #167 / #177 recoveries].
- All interrupt vectors (EXINT0/1, T0, T2, WDT 0x43) are in the current bank's common copy and call banked code (EXINT0: 537 callees) [confirmed, `mcu-8051.md`]. During an update every ISR path may bank-switch into a bank being rewritten: interrupts must be off (EA = 0) while any code bank is incomplete.
- Realtek's own partition scheme: `_FLASH_PARTITION_TYPE` NONE / BOOT / USER, optional digital signature, `_FLASH_PARTITION_RELOCATABLE_SUPPORT` (`g_ucBankOffset` at IRAM 0x30), `ScalerMcuBootInitial`; USER partition needs `_FLASH_PARTITION_TOTAL_BANKS = 0x20` = 2 MiB [confirmed, `Project_Asm_Option.h`]. Ours is NONE and the flash is 1 MiB: not usable as is. The Realtek boot code itself is not in our SDK tree (BOOT project sources absent) [confirmed absence].
- Free flash: banks 10-13 have 4-30 KiB free each (`docs/flash-layout.md`); bank 14 (unused) and the NVRAM bank hold a few free sectors (retired registry 0xFD000-0xFEFFF = 2 sectors). No room for a second image or a staging area for a whole one.

## 4. What the host flasher does that firmware must copy

(`scripts/rtd_flash_image.py`, `docs/flash-crc.md`, `docs/flash-burst.md`)

- Order `boot_last`: banked sectors banks 1.., bank 0 banked, common of banks 1.., bank 0 common last.
- Per sector: erase (<= 200 ms), 16 pages, verify by hardware CRC-8 (FF64-66 / FF72-74, FF6F bit2, result FF75; ISP only) or readback; manifest of per-sector SHA-256, "write-in-progress" state; never resets onto a mixed image (#177).
- Firmware has no hardware CRC (crc_start works in ISP mode only) [regdb]: software CRC-16 / CRC-32 over the received page + a readback via FF7B / flash read (`ScalerFlashRead`, `_FLASH_READ_FUNCTION_SUPPORT` on).

## 5. Design (minimal safe)

Layers, in build order. None exists today.

1. Immutable boot / recovery sector (#102, prerequisite).
   - Reset path: bank 0 sector 0 (vector + startup) must never be erased by a normal update (host: opt-in flag only).
   - Content: reset vector -> check valid-marker + CRC of the image manifest -> jump to the app; else stay in a stub: scaler / panel safe, keep DDC/CI + debug slave answering, minimal OSD "RECOVERY".
   - Open: all 14 bank copies of the common area carry vectors; the vector table must LJMP to fixed addresses (pinned ISR trampolines) or the stub must run with EA = 0 and not use bank switching [guess; needs a map of what the reset path needs, #102 first step].
   - Even without the stub the chip's ISP slave recovers any state (blank flash included) over an HDMI DDC cable [confirmed: #167, #156]; the stub removes the "dark until a cable is moved" cost, it is not the last line of defence.
2. Updater routine.
   - Placed in a pinned region of common (`-a` area in the sticky layout), same address in old and new image, so its own sector content is identical before and after.
   - Runs with EA = 0, no bank switch, polls the I2C buffer itself (or a main-loop step), pokes FFEA[6] between every erase / page (hardware reset at 1171.8 ms; one erase <= 200 ms).
   - One unprotect for a whole bank group (SDK WREN covers banks 0-7 in one SR value), raw FF7B page writes, one re-protect at the end; not `ScalerFlashWrite` per page (83 ms x 3584 pages worst = 300 s).
   - Never rewrite the sector holding its own running copy: run from bank X, rewrite banks != X; then switch to an already updated bank Y (updater at the same address there) and rewrite X; bank 0 common last from bank Y's copy.
3. Transport (host-driven, resumable).
   - Candidates: DDC/CI 0x37 command set (`docs/ddcci.md`), debug slave 0x35 (1 MHz NAKs, 100 kHz only), IP over DDC (#61, MTU 286, UDP service). A new small VCP-style block command is the least code.
   - Unit of transfer = one 256 B flash page with its address and CRC-16; ack per page; the host resends from the last acked page (same seq / ack idea as `ddcnet`).
   - Sector open on the first page of a sector (erase), sector close after page 16 (readback CRC compared with the host's), manifest row updated.
4. State machine and markers.
   - Image-valid marker: a flash word in a protected sector, cleared at update start, set last after full-image CRC (pairs with the recovery stub check).
   - Session record in flash (sector list done, target image CRC) so an interrupted update resumes after reboot; written in an erase-friendly slot (NVRAM style, 16 B items).
5. Screen: draw the existing flash screen (`fw/test/flash_screen.c`, `AwtoFlashScreen`) at update start; hold it with `AWTO_HOLD_POPUP` so SDK OSD resets do not wipe it; step the Pac-Man mouth per sector from the updater loop; show phase / sector n of N / "DO NOT POWER OFF"; OSD survives every halt (section 2). Clear on boot of the new image.
6. Exit: only reset (0xFFEE sof_rst) after final CRC OK + marker set; on any failure stay in the updater with the screen showing the error and DDC/CI alive for a retry, never reset onto a mixed image (same rule as #177).

Rejected:
- A/B images in flash: 14 of 16 banks used, 2 MiB needed for the Realtek USER partition + relocatable banks [section 3].
- Staging the whole image in XRAM: 8 KB XRAM total, 1541 B free.
- Running the updater from XRAM: no code path (section 2).

## 6. Risks

| risk | effect | mitigation |
|---|---|---|
| power cut during erase / program of a code sector | mixed image, dark unit (the #156 / #167 / #177 pattern) | boot stub + valid marker; `boot_last`; ISP over HDMI DDC recovers every case |
| power cut while bank 0 sector 0 (reset vector) is erased: window <= 200 ms + 16 x 3 ms | no code runs at all | sector 0 immutable (layer 1); else ISP recovery |
| erased sector holds code that is running or an ISR target | CPU reads 0xFF, runaway | EA = 0, updater pinned, never erase own bank's common while running from it |
| WDT reset mid-update | partial image | pokes between ops; erase 200 ms < 1171.8 ms hard reset; resume from the session record |
| unprotect state left on after failure | stray writes | re-protect in every exit path; SR check (0x9C) in the T tests |
| SR write endurance (2 WRSR per SDK call) | wear | one WRSR pair per bank group, not per page (#151) |
| DDC/CI slave unresponsive during a halt | host NAK / timeout | page protocol with ack + resend [guess: slave NAKs during halt; measure] |
| DP AUX units: bus dies on reset into a mixed image (#177) | needs an HDMI cable | never reset on a mixed image; recovery stub keeps AUX alive |
| host and firmware disagree on image layout (bank / stub addresses move) | wrong sector rewritten | manifest from `fw_build` (sector list + CRC) is the only input; firmware refuses sectors outside 0-13 and the protected list |
| code growth | XDATA / code budget | section 7 |

## 7. Size / XDATA estimate [guess until built]

- XDATA: 1541 B free.
  - page buffer 256 B + header / seq / state ~24 B + CRC-16 state ~4 B + session cursor ~8 B = ~300 B.
  - Leaves ~1240 B of the free XDATA. Do not buffer a 4 KiB sector (impossible: free XDATA 1541 B).
- IRAM: ~10 B direct (22 B free, `mcu-8051.md`); stack: updater is a leaf loop, one extra frame.
- Code: updater (erase, page program via FF7B, readback, CRC-16 table-less ~100 B, state machine) ~1.5-2.5 KB; transport command ~0.5 KB; recovery stub 2-4 KB (target well under 16 KiB, #102). Updater in common = 14 bank copies of the same sector content only when it lands in a sector; pinned slot costs one common sector per bank (host flasher writes it only when it changes).
- Time (firmware side, datasheet maxima): full image 224 erases x 200 ms = 44.8 s + 3584 pages x 3 ms = 10.8 s ~ 56 s, plus transfer (rate unknown; ~2 KB/s over DDC/CI would be ~7.5 min) [measure]. Incremental sticky edits are 1-14 sectors (`docs/flash-layout.md`).

## 8. Test plan (unit 3 only, `scripts/devices.json` test unit)

Preconditions: debug link off (`scripts/dbg_link.py off 11`); known-good image archived (`build-debris/images/`) and its manifest; HDMI DDC cable + `./dev.py flash --unit 3 --bus 11` (burst, 1 MHz) ready as ISP recovery; relay does not feed unit 3 (`hass_power.py cycle`); rest mode after each step (unit 3 at 4K60). Hardware flashes of the test image through the normal gated path.

- T0 read-only: firmware reads a code sector through FF7B and returns CRC over DDC/CI; compare with the ISP dump CRC. Measures read path and CRC-16 speed.
- T1 spare sector: erase + program + verify the retired sector 0xFE000 with a pattern (0xFD000 is the device manifest, do not touch); check SR = 0x9C afterwards; time each halt (Timer2 ticks, FFEA pokes); screen shown and animated during the loop; DDC/CI behaviour during halts (NAK pattern).
- T2 non-running code bank, identical content: rewrite one banked sector (bank != running, e.g. 12) with the bytes already there; boot, gates, health 11/11. Repeat for a common sector of a non-running bank.
- Follow-up (not built): firmware boot self-check of its own sectors against the device manifest (`docs/flash-registry.md`: CRC-32/ISO-HDLC, 16-entry table); a self-flash update rewrites the manifest the same way (body pages, commit page last).
- T3 changed content: one-sector edit via a sticky build (1 sector changes, `flash_layout_measure.py`); update by the firmware; reboot; verify against the host manifest.
- T4 hop: update the running bank through the second hop (run from bank Y); updater at the pinned address in both images.
- T5 interruption: after erasing a sector, force `sof_rst` (0xFFEE[1]) from a test command; expect the stub / resume path (needs layer 1); then recover with the host flasher. Real power-cut tests only with Dan's go (no relay on unit 3).
- T6 full image over the transport, bank 0 common last, 5 runs, 0 failures, flash screen visible for the whole run.
- Stop at the first failure; recovery by host ISP; findings to the issue.

## 9. Open questions (for Dan)

1. Is DP-only / remote update a real need, or is the host ISP flow (26 s) enough? Decides whether layers 2-4 are worth building after the T0-T2 prototype.
2. Immutable boot sector (#102): accept sector 0 of bank 0 (and the vector tables in the other 13 bank copies) as never-updated, which pins the ISR trampoline addresses?
3. Which transport: new DDC/CI command block, debug slave 0x35 (100 kHz limit), or IP over DDC (MTU 286, hardware untested)?
4. Real power-cut tests: allowed on unit 3, with the mains switch available?
5. Measure in T1: does the MCU halt for a whole page program through FF7B, or can a page start from the 256 B SRAM and let the MCU run (would halve the stall)? Also whether the 8051 stalls in hardware for every FF7B byte write.

## Sources

- Our code: `fw/nvram/flash_io.c`, `fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/ScalerCommonNVRam.c` (WREN 604, erase 4268, WRSR 4044), `.../Lib/Code/ScalerCommonNVRam/ScalerCommonFlashWrite.c`, `ScalerCommonMcu.c:2680`, `Project_Asm_Option.h`, `RL6449_AWTO_JXC4K.h:366`.
- Docs: `docs/flash-layout.md`, `flash-burst.md`, `flash-crc.md`, `flash-unprotect.md`, `flash-screen.md`, `nvram-settings.md`, `watchdog.md`, `delays.md`, `ip-over-ddc.md`, `reversing/realtek-rtd/mcu-8051.md`, `history.md` 4.4.
- regdb `re/regdb/RTD2795T-CG.tsv.gz` page FF (FF60-FF7C, FFE9-FFF0, FFFC-FFFF) and FD (cache).
- Issues: #232, #151, #156, #167, #177, #102.
- Vendor notes `~/vendors/realtek/analysis/NOTES.md` (bank layout of the Dahua image); no vendor bytes copied. Web search (playwrong, RTD2795 MCU self-flash / ISP) returned no Realtek document on in-system update beyond the SDK partition options above.
