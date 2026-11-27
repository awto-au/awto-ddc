Triage of the 110 open issues in awto-au/awto-ddc (read-only; nothing written anywhere). I read every issue body and comments, then checked the git history and code. The CLOSE rows below are the ones with concrete evidence. Commits are in /mnt/2tb/git/awto-ddc unless marked (ui) = awto-ddc-ui on wb-p14ui.

## CLOSE-DONE
| # | Evidence | Comment to post |
|---|---|---|
| 1 | This was a status/alternatives survey. The scaler is identified (RTD2795T), the flash is dumped and flashed over I2C ISP (no programmer needed), and own firmware runs (#7). | 🤖 Superseded by #7. Part is identified, ISP flashing works, own firmware runs on all 3 units; the survey is in docs/monitors/README.md. |
| 4 | da24a2f "production EDID": DTD1 4K60.000, deduped VIC list, CVT-RB DTDs, `edid-decode -c` PASS on all tables. Higher refresh is ruled out (panel ceiling 60 Hz, comment on #4). | 🤖 Done in da24a2f: production EDID with the mode list cleaned up, `edid-decode -c` PASS, 4K60.000 preferred. Higher refresh is ruled out by the 60 Hz panel. |
| 7 | The umbrella has all five steps done. Toolchain exists, board and panel headers exist, first flash was 2026-11-06, the awto menu exists, and DDC/CI MCCS 2.2 runs from the registry (8df4372 VCP 0x60, a6275dc). Units 1-3 run it. | 🤖 Done. Own RL6449 firmware builds and runs on units 1-3 with the awto OSD and registry-driven DDC/CI (a6275dc). Follow-ups live in their own issues. |
| 25 | a72d779 tokenised debug messages (8507 sites to 3611 ids, `fw/msgids.tsv`, cost about 2.6 KB). Host reader: `rtd_diag.py --messages` (a3ef79b). In-image text is in #56. | 🤖 Done: a72d779 (AWTO_MSG ids + msgids.tsv, about 2.6 KB) and a3ef79b (`rtd_diag --messages` decoder). |
| 26 | Root cause was `~bit` Keil semantics breaking the DCLK fine-tune. Fixed (wb-vfreq, then 92e4233 / 323b342 `--keil-compat`). 4K60.000 confirmed by Dan on unit 3. DP-1 47-mode sweep had no failures. Unit 2 locks 4K60 now (#109). | 🤖 Root cause: Keil `~bit` semantics (comment 2026-11-07T01:53). Fixed in the compiler (92e4233, 323b342). 4K60.000 ACTIVE on all units, sweep 47/47 on DP. |
| 28 | Unit 2 runs our firmware on D1 DP: 3840x2160@59.994, health 11/11 over DP AUX, HBR2 (comment 2026-11-07T16:03, 650301c). The #26 DP-1 sweep passed 47 modes. | 🤖 DP input works: unit 2 on D1 DP, health 11/11 at 4K60 (650301c); DP-1 sweep 47/47 (#26). |
| 38 | Dan's stated scope: "only 4K60 + 1080p60 on DP and HDMI; when they work, close out the rest". HDMI is done (#26), DP is done (#28), and the sticky-layout / diag / trace / asm queue items are merged. | 🤖 Scope reached (4K60 + 1080p60 on DP and HDMI, #26/#28). Queue items are merged; closing per the rule in this issue. |
| 39 | Key test screen built (5dcc66e, d8a364b). Dan confirmed it on unit 2 (keys5). Live ADC and decoded key now sit in the console key panel (ui 11f56fc). | 🤖 Done: key test screen with live ADC + decoded key (d8a364b), confirmed on unit 2; now a panel of the console (11f56fc). |
| 40 | bd94b56 fast boot: panel VDD at 11 ms (was about 591), first main-loop pass at 209 ms (was 409), measured by cold_boot.py. | 🤖 Done in bd94b56: panel VDD at 11 ms, first main-loop pass 409 to 209 ms. The remaining DDR2PLL deferral is not needed for the ask. |
| 48 | 0b133dd: `scripts/i2cbus.py` is the only opener of /dev/i2c-N, all callers migrated. `tests/test_i2c_single_layer.py` fails on any other opener. 2ff51f8 adds fast_bus and dev.py. | 🤖 Done in 0b133dd + 2ff51f8: `i2cbus.py` is the single I2C layer; a test enforces it. |
| 60 | fe9a8d7: same-timing switch in 80-95 ms (was 0.9-1.0 s), 0 drm uevents, VCP 0x60, source selector. Measured 10/10 on unit 2. The uncached first switch is tracked in #83. | 🤖 Done: cached input switch is 80-95 ms with no hot-plug (fe9a8d7). First switch to an uncached port is tracked in #83. |
| 61 | The feasibility answer was "yes", and #80 built it: `ddcnet.py stack` 13/13 PASS and a Linux TAP ping work on units 2 and 3. | 🤖 Superseded by #80; feasibility proven and built (Busorra, ddcnet.py stack PASS). |
| 67 | Registry built and flashed. Menu, DDC/CI VCPs and NVRAM generated from it. Health 11/11 on 3 units (bb0dbd8). Inert rows are tracked in #81. | 🤖 Done: one settings registry drives the menu, DDC/CI and NVRAM (a6275dc, bb0dbd8, health 11/11 on all units). Inert rows are in #81. |
| 68 | The mixed clean-room build is in every image. Clean tree pinned f4063ad (bf9373d / 513ac52). At `--sdcccall 3` it is in image wb-p14kc2 on all 3 units. It beat SDK-only in the A/B. | 🤖 Done: awto-rtdfw modules compile into the SDK image (pinned f4063ad) and run on all 3 units. |
| 71 | Per-sector erase + program + verify with boot/common sectors last (7c96c91, 762d62c "default every unit to boot-last per-sector"). Read gate before any erase (8478e6b). Link off before ISP (762d62c). Burst on NVIDIA (comment 17:22). | 🤖 Done: 7c96c91, 8478e6b, 762d62c cover per-sector boot-last flashing, the read gate and link-off, plus the NVIDIA burst fix. |
| 75 | 97a037b: SysJudgeCheckStatus every 10 ms in ACTIVE, `g_stAwtoLoop` fast/slow counters. Main loop 375.7 to 875.7 per second, rolled to all 3 units. | 🤖 Done in 97a037b: fast/slow path split, main loop +133 % (376 to 876 per second), health 11/11. |
| 79 | VCP 0xE3 runtime swap (5ce1d85). Proven on units 1 and 2 on swap7: 0x35 up after 58 ms, 0x37 back after 462 ms, 11/11. | 🤖 Decision made and built: runtime DDC swap by VCP 0xE3 (5ce1d85), proven on all 3 units. |
| 80 | All hardware tests PASS on unit 3 (transports A/B) and unit 2 (13/13 stack, TAP ping 5/5). Open items (a) and (b) were answered in the comments. | 🤖 Done: Busorra (IP over DDC) passes loopback, stack and ping on hardware (de074ad). |
| 82 | 5bf8a15 tolerates storage failures (#82, #96). Boot/common sectors last (7c96c91, 762d62c). disk_guard f83b589. | 🤖 Done: 5bf8a15 (ENOSPC tolerant) + 7c96c91/762d62c (boot sectors last). |
| 85 | Decode fixed on the JXC ladder (6a27866, 5dcc66e). A 13-press hardware log on unit 2 shows all six keys decode, release to idle, and wake from soft-off works. Role swap (keys6) is now in #129. | 🤖 Done: the real JXC key decode (SOURCE/MENU/DOWN/UP/AUTO/POWER) is in (6a27866), verified by a 13-press log on unit 2. Key roles continue in #129. |
| 55 | Hypothesis refuted. Its own last comment proposes closing; the truth is in #26. | 🤖 Refuted (see comment 2026-11-07T01:13); root cause was the `~bit` compiler issue, fixed under #26. |
| 30 | `rtk_libsig.py` plus `omf51_lib.py` (622f97e). Used on the vendor image and other firmware (7 comments). | 🤖 Done in 622f97e: library signature matcher is a standard tool and has run on the vendor image and the other images. |
| 32 | The chip-level answer is no. There are no HEC registers in the RTD2795T regdb, no HEC symbols in the SDK, and none in FunctionLib/AdvancedLib. Board wiring is moot without the MAC. | 🤖 Answered: no HEC support in the chip (regdb, SDK source and libs have no HEC/Ethernet registers or code). |

## UNSURE
| # | What is missing |
|---|---|
| 20 | Item 1 done (e98c8b1) and item 4 covered by the delay-cal test (f023f71). Bit-field order and the storage-first pointer rewrite have no verification evidence. |
| 24 | Mitigated (free direct IRAM 9 to 23 B, ab697cc / 7fd165f; options 1-3 done) but I have no current figure on sc3. Option 5 (the DATA to XDATA fallback) was deprioritised. |
| 31 | The review is written (re/lib-review/README.md). Still open is the follow-up to verify which register gates output gamma when gamma is brought up. |
| 49 | Probably superseded by #65/#68 (clean-room mixed build), but the ask differs: pick functions by measurement, hand asm. |
| 56 | Phase 1 (block + ring) merged (36cf775). Phase 2 (overlay) is "NOT done". Confirm the in-image text block is in the current line. |
| 69 | The OSD oracle via vendor key injection has no commit. It may be obsolete now that the Realtek menu is built out (#120). Dan to decide. |
| 76 | Fix landed (fa99bd6). Open item remains: unit_health should refuse a bus where the magic is not "AD". |
| 87 | Strip and legend are implemented (awto-rtdfw ba25304, 3-line strip). The colours are blue, not "red like the logo", and #125/#128 will rework them. |
| 88 | The gate now runs with video (43dad5d). The no-signal hang on hardware is untested. |
| 104 | Evidence only (OCR of photos), no cause. It is likely moot since the console replaced the diagnostic screen. Confirm with Dan. |
| 105 | The GPIO screen is now a panel of the console, and UP+DOWN toggles the console (`AWTO_KEY_TOGGLE` / `AwtoKeyTestSet(2)` in ui HEAD). Not confirmed on unit 2 after txt3. |
| 107 | Descriptions exist for 44 of 50 rows (88dd6cd, `fw/awto/inputs.tsv` desc column). The key rows are "-". The page-1 "live meaning" values are not verified on screen. |
| 120 | Step 1 done (ui 6bd79ce): image 523624 to 462348 B, health 11/11. Still in: 48.8 KB of icons via the shared icon table. Not checked by eye (MENU opens the menu, source selector, card on signal loss). |

## KEEP (still open work or open hardware/research question)
- **Hardware / research:**
  - #3: OEM, board and panel identity is unresolved; the panel candidates conflict.
  - #6: the Windows flasher is not started (decided to build all three vendor paths).
  - #9, #64: USB; these overlap, so consider merging #64 into #9.
  - #21: FreeSync is deferred.
  - #22, #94: audio. #94 is built offline but never flashed, and whether the board has a jack is unknown.
  - #44: HDCP is parked.
  - #59: 10 bpc at 4K60.
  - #93, #95: the owner commented "Steil need conpletion".
  - #100, #101, #109 (4K30 no sync), #110 (DPS17).
  - #41: reversal is ongoing.
- **Hardware not met:**
  - #78: wake target is under 300 ms. HDMI L1/L2 is 269-372 ms and DP L1/L2 is 509-635 ms.
  - #83: pre-fill is 0 of 2 working.
- **Build / flash tooling:**
  - #13: CLI replacement; measure/edid/dpcd/gamma/od/gpio subcommands are not done.
  - #50-#53: reviews with items listed "not done".
  - #54: the delay-calibration residual is still open (126-132 % drift).
  - #58: wait_wip still busy-polls (rtd_flash_sector.py:237).
  - #66: warn_policy rows still exist.
  - #73: the 6 stale tests are untouched since 11-07.
  - #92: awto-sdcc#18 is open and the asm is unchanged.
  - #102: the recovery stub is not built.
  - #106, #108, #111 (on hold, awto-sdcc#39 open), #130, #131.
- **Firmware work:**
  - #29: no boot-log OSD or reset-cause screen exists.
  - #35: self-recovery is off (54efb39).
  - #37: docs/realtek-debug.md exists only on a branch (38fa9bd), not on main.
  - #45: the cleanup meta issue; firmware is not finished.
  - #46: `fw_ours.py` was never built.
- **Clean-room / design:**
  - #65, #81 (inert rows), #89, #90 (no editor in scripts/), #91 (`facts_lint` not built).
- **OSD cleanup:** #112-#119 (stubs confirmed present in HEAD, e.g. `tiOSD_REALTEK_1BIT_LOGO0/1` in `awto_logo_maps.inc:2,6`), #121-#129. #121-#129 are all open and nothing in HEAD shows them done.

Summary:
- 22 CLOSE-DONE (the evidence list above), 13 UNSURE, the rest KEEP. No CLOSE-OBSOLETE or other CLOSE-SUPERSEDED beyond #1, #55 and #61.
- Biggest clean wins are the finished flasher and KVM line (#71, #82, #48, #60, #79, #75, #80) and the 4K60 fix (#26, #55, #28, #38).
- The osd-cleanup issues #112-#129 are all genuinely open, apart from the partial #120.
