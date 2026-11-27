🤖 Rotation study, phase A (findings + plan, no firmware change). Dan, 2026-11-13: the monitor rotates the picture for sources that can't.

Tags: [fw] our tree, [sdk] Realtek SDK source in fw/sdk / fw/sdk-parked, [regdb] `re/regdb/RTD2795T-CG.tsv.gz`, [hw] measured on unit 2, [ds] panel datasheet, [guess] unverified.

## 1. 180° without frame memory: not possible

**Panel (Innolux M280DCA-E3B rev C1)**
- [ds] Spec v0.0 (2019-03-11), 51-pin JAE FI-RXE51S-HF: power, GND, 4 eDP lanes, AUX, HPD. No scan-direction / LR / UD pin.
  - Pins 7-11, 13-15, 35, 37, 38, 40, 41, 43, 44, 46, 47, 49, 50 = N.C., "reserved for internal use, leave open". Any hidden TCON strap there is undocumented [guess] and would be a board change anyway.
- [ds] No DPCD / TCON register for scan direction in the spec.
- [hw] Panel DPCD (unit 1 AUX read, 2026-11-05): rev 1.4, sink OUI / device ID at 0x400 all zero, so no identified TCON vendor register set to try.

**Scaler**
- [regdb] No mirror / flip / reverse-scan field in the D-domain, display timing gen or DPTX pages. The only picture-reversal hardware:
  - P20_F0..F2 rotation block (`rotation_en` "replace main/sub capture client", `rotation_in_wid` <= 4096): reverses pixels within a line in front of the capture client.
  - P5_49 / P45_49 `rotation_cw180_en` (capture M1 / M2): reverses the line order written to memory.
  - P37_B0 client mux: display clients read the other DDR channel (M1 shows what M2 captured).
- [sdk] RL6449 = `_DISPLAY_ROTATION_GEN_II` (RL6449_Gen_Option.h): 180° only; 90 / 270 `_OFF`. 180° = P20 line block + capture cw180 + P37_B0 crossed mux, frame buffer read back reversed.
- [sdk] `ScalerMDomainMemoryConfig`: rotation on forces `_MEMORY_WORK_MODE` (frame buffer) in every mode. `Project_Config_Check.h` flags rotation / H mirror / V mirror without memory and rotation without `_FRC_SUPPORT`.
- Vertical flip needs the last input line before the first output line, i.e. a whole frame stored. With no panel-side reverse scan, 180° needs the DDR frame buffer.

**Live poke, unit 2** (2026-11-13T11:14-11:15+11:00; image wb-p14ui-osdt2, DP-1 4K60.000, line-buffer mode P5_27 = 82 / P5_AC = 05 / P0_28 = 0B; debug link over bus 15, unit lock held, every write restored)
| test | write | P0_02 after clear | firmware |
|---|---|---|---|
| A | P5_49 = P45_49 = 01 (cw180) | 00 | no reaction; no effect expected (nothing written to DDR in line-buffer mode) |
| B | P20_F1/F2 = 3840, P20_F0 = 81 | 02 (M1 overflow) | P0_28 0B -> 23 -> 2B: display setting re-run |
| B2 | P20_F1/F2 = 1920, P20_F0 = 81 | 01 (M1 underflow) | P0_28 -> 23 -> A3: re-run |
- [hw] The P20 line block sits in the capture path even in line-buffer mode: enabling it changes the M-domain FIFO balance. Width 3840 overflows, 1920 underflows.
- Picture not seen (no camera, nobody watching). Possible lead: horizontal mirror without memory, if a correct set-up exists [guess]. That is mirror, not 180°.
- Restored: P20_F0 = 01 (reset value), F1 / F2 = 00, P5_49 / P45_49 = 00, P0_02 cleared. `dev.py health --unit 2` 10/11 after each (delay cal, known): ACTIVE, 3840x2160@59.991, loop 321/s. Debug link off, lock released.

## 2. Full rotation via frame memory

**What exists**
- [sdk][regdb] 180° (and H / V mirror) only. 90 / 270 are GEN_I chips (RL6410: separate rotation display block, P20_A*/C* registers); RTD2795T's page 20 has only F0-FF. Portrait (90 / 270) stays with the host OS.
- No size question for 180°: 3840x2160 in, 3840x2160 out, same scaling as today.

**Bringing it back**
- `git mv` from fw/sdk-parked to fw/sdk: `Kernel/Scaler/ScalerFunction/Code/ScalerRotation.c`, `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Rotation.c`, `Kernel/Scaler/ScalerFunction/Code/ScalerFRC.c` (FRC is parked too).
- `RL6449_Project.h`: `_FRC_SUPPORT` `_ON` (today only with `-D_AWTO_FRC`), `_DISPLAY_ROTATION_SUPPORT` `_ON`; `_DISPLAY_ROTATION_180_SUPPORT` is already ON in the Gen option.
  - Already set: `_EMBEDDED_MEMORY_SIZE_CONFIG _16M_16BIT_DDR2_2PCS` (enables `ScalerDDR2RotationSetClientMux`, called from SysMode), `_DDR2_MEMORY_CLK_1200M_SUPPORT _ON`.
  - H / V mirror: optional, 0 extra hardware; `_DISPLAY_HOR_MIRROR_SUPPORT` / `_VER_` are `_OFF` (QC_Option / Default).
- Then: warn-policy / pp_audit rows for the new sites, `~bit`-class keil2sdcc rules over the new files (#26), stack + XDATA (2209 B free after the audit; FRC + rotation cost not measured yet), all sim gates.
- [sdk] Conflict: GEN_II forbids `_FREEZE_SUPPORT` together with rotation (`Project_Config_Check.h`). #165 lists both, so Dan picks one, or freeze is greyed out while rotated.
- [sdk] Rotation forces display latency ratio 0 and the frame buffer: +1 frame of input lag while rotated (~16.7 ms at 60 Hz) [guess on the exact figure].
- Vendor reference: the Dahua firmware has `_DISPLAY_ROTATION_SUPPORT` on (P37_B0 = 22 at DS init, P20_F0 / P5_49 / ShiftOneLine writes; #26 trace diff).

**Memory: size and bandwidth** (SDK model: `ScalerMDomainGetFRCMemoryBW`, budget `_MEMORY_TOTAL_BW` = data rate x 85 %)
- DDR2 2 x 16M x16 = 32-bit bus, 512 Mbit (64 MB), 1200 MT/s (600 MHz clock): 4.8 GB/s raw, 1020 M words/s SDK budget.
  - DDR2-1200 is above JEDEC DDR2-1066; the Dahua firmware runs 1200 too (#26). DRAM part not identified [guess: possible margin issue, test after code causes].
- 4K60 input is 8 bpc on both links (HDMI 594 MHz = 24 bpp; DP HBR2 x4 cannot carry 4K60 at 30 bpp) -> memory data bit 24 (`ScalerMDomainSetMemoryDataBit`).
| case | write (M words/s) | read | total | of SDK budget |
|---|---|---|---|---|
| 4K60, 24 bit (Vtotal 2250 in, ~2250 out) | 389 | ~389 + SSC margin | ~780 | ~76 % |
| 4K60, 30 bit | 486 | ~486 + margin | ~975 | ~96 % |
| 1080p60, 24 bit | 97 | ~97 | ~195 | ~19 % |
- Bytes: 4K60 24 bit ≈ 1.5 GB/s each way, 3.0 GB/s of 4.8 raw. Each DDR channel carries one capture and one display client (crossed mux), so the load splits evenly.
- Size: one 4K frame = 199 Mbit (24 bit) / 249 Mbit (30 bit). Two buffers fit (398 / 498 of 512 Mbit); three do not (`_FRC_HW_AUTO_3BLOCK_TOGGLE_SUPPORT` is `_OFF` on RL6449 anyway).
- Tiled / block writes: not needed for 180° (whole lines, reversed order), only for GEN_I 90 / 270.

**DDR read-error bug (#26 / #36): the blocker**
- Measured 2026-11-07, unit 3, pre-`~bit` fix: every frame-buffer mode garbled (4K24-50, 1080p24-50, 720p); DDR PHY read-window flags (pages 8F / CF `VALID_WIN_DET_SLIC*`, `INT_STATUS1`) set continuously with DDR traffic, 0 with line buffer. DDR config, PHY taps, pads, ODT, Vref, PLL and init order equal the Dahua firmware; no reachable read-path control cleared it (PAD_DQ pull-down only blanked the data).
- Last hypothesis: SDCC runs the DDR init ~4x faster than Keil after the DRAM init trigger (sim instruction counts), so FIFO / SYS2 set-up lands while the DRAM init FSM still runs. Test image `wb-ddrinit` (088a07d, DELAY_XUS(500) at both points) was built, never flashed.
- After the `~bit` fix (2026-11-07 17:31) those modes run in line buffer (frc = 0), so the frame buffer has not run on hardware since. Only 1080p24 HDMI still chose it (NOSIGNAL). State: unknown, not fixed.
- Retest needs: an FRC image (`-D_AWTO_FRC` + ScalerFRC.c back), a mode that uses memory, `mode_sweep.py` / `ddr_flags_probe.py` for the 8F / CF flags, then Dan's eye. Then `wb-ddrinit` rebased onto current main if the flags are still set.

## 3. Menu: registry row 32 `disp_rotate`
- Today: 0 / 90 / 180 / 270, `inert`, stored in `OSD.b3OsdDispRotate` (3 bits). Change to options 0 / 180 (plus H / V mirror if wanted); 90 / 270 cannot be built on this chip.
- One owner: setting apply `rotate`, same pattern as `set_ap_aspect` (fw/sdcc/glue.inc): store the field, then in ACTIVE `SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_DISPLAY_SETTING, AWTO_SYS_BY_SETTINGS)`.
  - The SDK reads it in one place: SysMode display-setting entry `SET_ROT_TYPE(UserInterfaceGetRotationDegree())`; `SysModeCheckToDisableGlobalDoubleBuffer` already handles a change.
  - `UserInterfaceGetRotationDisplayType` (`b2DispRotationSizeType`): fix to FULL for 180° (same size).
- Sync log: one line per rotation change (requested / already / applied); VCP: none in MCCS, an awto VCP only if wanted.
- OSD: menu orientation is a separate row (63 `osd_rotate`, OSD engine auto-rotate); no change needed for picture 180°.

## Step plan (each step: sim gates, speed row, unit 2 only, restore)
1. **FRC back, no rotation.** Unpark ScalerFRC.c, `_FRC_SUPPORT` on by default. Measure XDATA / code. Unit 2 at 4K60 (line buffer, unchanged): health 10/11, loop rate.
2. **DDR frame-buffer check.** Force memory work mode at the current mode with a debug test cmd (no host mode change). Read 8F / CF flags; Dan looks.
   - Flags set / garbled: flash `wb-ddrinit` rebased; then DDR init order vs Dahua with real delays.
3. **Rotation 180° at 1080p60**, if Dan allows a mode change on DP-1 (it is on his desktop). Otherwise go straight to 4K60.
4. **Rotation 180° at 4K60**: P0_02, DDR flags, loop rate, Dan's eye; then menu row 32 wired and `inert` dropped.

## Risks
- DDR read errors persist: no frame buffer, so no rotation and no FRC modes. Rotation depends on #26 being fixed.
- 4K60 at 76 % of the SDK bandwidth budget (24 bit) is fine on paper; 30 bit (future 10 bpc input) is at 96 %.
- XDATA / code: FRC + rotation unmeasured; budget floor is 700 B free.
- Freeze and rotation exclusive (GEN_II).
- +1 frame lag while rotated; mode changes take a full display setting (no fast path while rotated) [guess].
- Line-block poke showed FIFO balance changes in line-buffer mode: wrong set-up re-runs display setting (seen live, self-recovered).

## Open for Dan (needs-dan)
- Freeze or rotation, given they cannot both be on?
- May step 3 change unit 2's host mode on DP-1 (1080p60, then back to 4K60)?
- Want H / V mirror in the menu too (same hardware, no extra cost)?
