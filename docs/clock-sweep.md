# MCU and flash clock sweep (unit 3, RTD2795T)

Measured 2026-11-18 on unit 3 (AWT26110003, chip ID reads 0x23, M2PLL 350.79 MHz = 14318 kHz x 49 / 2), image = commit 465cb97 + `-D _AWTO_OSD_HWTEST` (tag clk10), 4K60 DP input, Rotate 180, ambient temperature not logged.
Tags: `[hw]` measured on the unit, `[ds]` MX25L8006E datasheet (`/vendors/macronix/MX25L8006E_v1.6.pdf`, 57 pages, Table 13), `[regdb]` `re/regdb/RTD2795T-CG.tsv.gz`, `[sdk-hypothesis]` Realtek SDK claim, `[sim]` fw_sim only.

## Tool
- `./dev.py clk-sweep --unit 3 [--sim] [--continue-on-fail] STEP...` -> `scripts/clk_sweep.py`; firmware op `AwtoClkApply` in `fw/test/testcmd.c` (struct `g_stAwtoClk`, HWTEST builds only). Logs `tmp/logs/clk_sweep.log` / `.tsv`.
- Runtime step = dividers `FFED[5:2]` F, `FFEE[5:2]` M, `FFE9[3:0]` F2 (MCU = M2PLL / F / M, SPI = M2PLL / F / F2), written in an order whose every transient keeps SPI <= rating and MCU <= the faster end; then Timer2 reload (same formula as `_TIMER2_COUNT_NUM`; formula checked against the stock `RCAP2` = 0xE373 on every run), `DELAY_5US` / `DELAY_XUS` counts (scaled, then secant-calibrated to 105 % +-5 against Timer2), DDC debounce counter scaled with the clock, pad drive / slew optional.
- Safe by construction: the step reverts from the main loop at the hold limit (host revert normally); a stalled main loop = WDT reset (586 ms) = stock clock again. Measured: every failed dual-read step ended in a reset back to stock, unit came back each time (relink < 5 s).
- Refused by the firmware: dividers outside 1..15, SPI above 86 MHz (80 MHz in dual mode), MCU slower than the SPI.
- Checks per step (pass / fail line each): registers read back; Timer2 formula; CRC-32 of code 0x0100..0x3FFF read with MOVC, 3 passes (stock CRC = the file's CRC); XDATA patterns; delay accuracy 97..150 %; 300 debug-link block reads; heartbeat vs host clock +-1.5 %; OSD port write + read-back M1 / M2; revert. Info: cache-miss read time, cache meter (FDB3..FDC6: reads, misses, restarts), Scope 2 / Scope 1 / Asteroids frames drawn per second (fw frame counters, `g_usAwtoScFrames`, `g_usAwtoAstFrames`, `g_usAwtoS2Frame`).
- Sim (`--sim`, `scripts/fw_sim.py`) ran the same sweep first: logic, timer rescale, revert proven; the sim has no flash-cache meter and no real flash timing.

## Rated limits
| item | rated | what we run (stock) | tested |
|---|---|---|---|
| SPI FAST_READ 0x0B [ds] | 86 MHz | 43.85 MHz | 21.9 .. 70.2 MHz, all pass |
| SPI READ 0x03 [ds] | 33 MHz | not used | - |
| SPI DREAD 0x3B [ds] | 80 MHz (x1 / x2 part: no dual-I/O, no quad) | not used | see dual read |
| SPI 87.7 MHz (F x F2 = 4) | above rating (2 %) | - | not run (firmware refuses) |
| MCU [ds DW8051 databook] | no rating for this die (> 120 MHz only <= 0.25 um) | 87.7 MHz | 43.9 .. 350.8 MHz, all pass |

## Results (one image, clk10, commit 465cb97)
Frames per second drawn; Scope 2 has no frame schedule, Scope 1 / Asteroids are scheduled at 40 ms (25 / s).

| step | F F2 M | MCU MHz | SPI MHz | checks | Scope 2 | Scope 1 | Asteroids | miss ns | OSD direct us/B |
|---|---|---|---|---|---|---|---|---|---|
| m44 | 8 1 1 | 43.85 | 43.85 | all pass | 3.31 | 6.17 | 14.3 | 5615 | 7.03 |
| stock | 4 2 1 | 87.70 | 43.85 | all pass | 5.63 | 6.17 | 23.5 | 3601 | 3.79 |
| m117 | 3 3 1 | 116.93 | 38.98 | all pass | 6.12 | 6.17 | 22.5 | 3296 | 2.71 |
| s58 | 2 3 2 | 87.70 | 58.47 | all pass | 6.96 | 6.33 | 23.2 | 3113 | 3.25 |
| s70 | 1 5 4 | 87.70 | 70.16 | all pass | 7.62 | 6.33 | 22.8 | 2930 | 2.71 |
| m175 | 2 4 1 | 175.40 | 43.85 | all pass | 8.28 | 6.33 | 25.0 | 2563 | 2.16 |
| f175_58 | 2 3 1 | 175.40 | 58.47 | all pass | 10.78 | 6.50 | 25.0 | 2197 | 1.62 |
| f175_70 | 1 5 2 | 175.40 | 70.16 | all pass | 12.42 | 6.66 | 25.0 | 1892 | 1.08 |
| m351 | 1 5 1 | 350.79 | 70.16 | all pass | 17.55 | 8.16 | 24.8 | 1404 | 1.08 |

Other steps (earlier images, same checks, pass): m58 (58.5 / 29.2), m70 (70.2 / 35.1), s22 (87.7 / 21.9), s29 (87.7 / 29.2), pad drive 5.5 mA on s58 / s70 / f175_58 / f175_70 (no difference seen).
Stress (CRC passes of 15.6 KB through the cache, 0 passes differing): stock 40, s70 40, m175 40, f175_70 40 and 200 (3.1 MB), m351 40 and 200 (3.1 MB), m351 repeated twice more; a run is minutes, not hours, one unit, no temperature measurement.

- Scope 2 is compute-bound: gain follows both clocks (MCU alone 1.47x at 175.4, SPI alone 1.35x at 70.2, both 2.2x; 3.1x at 350.8). Sim predicted 1.57x for the MCU step.
- Scope 1 and Asteroids already sit at their 40 ms / 160 ms schedule at stock (Scope 1 is a 6.2 / s plateau at every clock up to 175.4: not CPU-bound there, cause not looked at; 8.2 / s only at 350.8).
- Cache miss cost per 16-byte line falls with both clocks; the cache meter counts ~0.6-0.9 % misses of ~6.4 M program reads per 15.6 KB CRC pass (code of the loop itself).

## What failed
- Nothing failed inside the divider steps and the rated SPI range. The MCU limit is not reached with dividers: A x B = 1 (350.8 MHz) passes every check and the 200-pass soak. Beyond that only an M2PLL change exists (372 MHz = M 52 per the SDK RL6463 value `[sdk-hypothesis]`); not run: it moves other clock domains and needs Dan's go.
- Dual-output read (`FF6C[7:6]` = 10):
  - `FF6C` alone (opcode register `FF6B` left at 0x0B): firmware resets at once, 3 of 3 tries at stock clocks [hw]. `FF6B` = 0x3B (DREAD opcode [ds]) is needed with it [regdb: "fast read op code, include fast dual read"].
  - With `FF6B` = 0x3B at 87.7 / 43.85: all checks pass incl. 300 link reads, CRC (3 passes), OSD, Scope 2 5.70 / s (single read 5.2 on that image), then the unit reset within seconds in the savers (once) and within the 40-pass CRC stress (twice: 40 passes single read pass, dual read reset). Symptom: no answer from the debug slave, WDT reset, stock clock afterwards.
  - Latch / delay variants (`latch_so_rise` flipped: immediate reset; `si_dly_sel` 2 / 4 / 6 ns, `drive_si_fall`: apply hung > 21 s, reset) did not help. Dual read is not usable as set up; cause unknown (board wiring of SIO1 is not documented here). It does not change the table above; flash gain comes from the clock.
- First hardware runs at 43.85 MHz: WDT bite in `ScalerSyncDdcDetect_EXINT1` when the host polled the debug link back-to-back during the 2 s apply op (ISR load at a slow MCU). Host polls are now 50 ms apart. Not seen at stock or faster.
- Delay calibration at a step needs warm-up + shortest of 5 runs (cold flash cache made 5 us measure 85 % one run, 116 % the next); one step (f175_70S) reported 96 % against the 97 % limit once: a calibration flake, not an instability.

## SDK claims checked ([sdk-hypothesis] -> measurement)
- Speed-up needs `_CKCON_MOVX_9_CYCLE` for scaler / flash registers: scaler registers and the OSD data port at 175.4 and 350.8 MHz with the default 2-cycle MOVX: OSD write / read-back 0 bad bytes, link, heartbeat all pass -> not needed for those. `FF6C` / `FF6B` writes were done with the 9-cycle wrapper; the no-wrapper variant was not reached (dual read unusable). NVRAM flash writes / erases (`FF60..FF6F` common instruction) were NOT exercised above 87.7 MHz: untested, keep the SDK wrapper until measured.
- Timer2 reload = compile-time product of the dividers: runtime formula reproduces the stock reload (check "formula" pass on every run); heartbeat vs host clock 0.9997 .. 1.0012 at every step.
- Delay counts 26 / 21 -> 53 / 44 at 175.5 (SDK): our calibrated stock counts differ (28 / 24 here), the calibrated counts scale ~1 / clock (e.g. 36 / 39 at 175.4, 116 / 90 at 350.8).
- Timer0 / 1 step 8 -> 4 ms: Timer0 / 1 events are off in our build (`_INSTANT_TIMER_EVENT_0/1 = _OFF`), `t0ev.c` ticks from `RCAP2`; no step needed.
- "WDT counts crystal time": the WDT counter / Timer2 ratio read 1.000, 1.082, 1.068 on different runs: not a fixed reference; the host clock is the reference.
- `FFEE[6]` mcu_peri_non_stop reads 1 at every step. Chip-ID register read returned 0x23 (rev E) mostly, 0x02 once: unreliable read, not used.
- Pad drive (`P10_C2` 5.5 mA vs 4 mA) and slew: no failure without it at 70.2 MHz, so no effect measurable.

## Recommendation
- Default candidate: MCU 175.4 MHz + SPI 70.2 MHz (F 1, F2 5, M 2): Scope 2 5.6 -> 12.4 / s (2.2x), Scope 1 / Asteroids unchanged (already scheduled), every check + 200-pass soak pass; SPI 18 % under the 86 MHz rating.
- 350.8 MHz passes everything tried (17.6 Scope 2 frames / s) but there is no margin knowledge: needs temperature, longer soak, other units, flash write path before it is a default.
- Not yet measured, risks: NVRAM flash write / erase at the new clock (`FF60..FF6F`, CKCON), temperature drift, other units / die revisions, long soak (hours), DP / HDMI source handling at the new clock (the sweep ran on a DP input, savers on), audio / PWM clocks (derive from M2PLL, unchanged here).
- Adoption in production code = compile-time constants: `_FLASH_CLK_DIV`, `_FLASH_2_CLK_DIV`, `_MCU_CLK_DIV`, Timer2 / delay / debounce constants must follow (they are the products the runtime step recomputes); SDK `_MCU_SPEED_UP_SUPPORT` only gives (F 2, F2 4, M 1) = the m175 step with SPI 43.85.

## M2PLL steps (above 350.8 MHz)
Phase A (code + sim, no hardware): `./dev.py clk-sweep --unit 3 [--sim] pmNN | p372 p401 p430 p487 | all-pll | pll-fine`. Tags as above; `[sdk-hypothesis]` = Realtek SDK claim.
- Step `pmNN` = M2PLL M = NN, N 2, O 1 (14.318 MHz x NN / 2): MCU = M2PLL (F 1, M 1), flash F2 = smallest keeping the SPI <= 70.2 MHz. `pmNNL` = + 200 CRC passes. p372 = M52, p401 = M56, p430 = M60, p487 = M68 (a 487 MHz VCO is the SDK's 243 MHz setting M68 N2 O2 `[sdk-hypothesis]`).
- Firmware sequence (`AwtoClkPllMove`, `fw/test/testcmd.c`, EA off): derived dividers to the new values (M2PLL still low: slower than final) -> MCU / flash source = crystal, dividers 1 (regdb FFED) -> M2PLL power off, `0x01E0`, `0x01E7`, `0x01E1` (latches M / N), power on, >= 1 ms (Timer2 at the crystal) -> clear `0x01E5[7]` (W1C), PFD / LPF reset pulse, >= 1 ms -> lock = `0x01E5[7]` clear and no bounded wait expired -> F / F2 / M dividers, source = M2PLL -> Timer2 reload, delay counts, DDC debounce scaled by (new M2PLL x stock MCU div) / (stock M2PLL x new MCU div). Loop filter `0x01E4`, LDO `0x01E6`, `vcomd` untouched (no measured need).
- Revert (host, hold limit from the main loop, WDT backstop): same move back with the derived dividers written last. No lock -> stock M2PLL put back at once, step refused ("did not lock").
- Guards: `--max-m2pll-mhz` (default 490, a tool guard not a chip limit; host and firmware both refuse above; beyond 490 logged with `!!!!`), SPI <= 86 MHz, MCU >= flash, M / N / O range, hold-limit revert, WDT reset.
- Derived clocks retuned to the nearest integer divider of `stock div x new / stock M2PLL` (table printed per step; `--keep NAMES` leaves some at stock, `--override NAME=VAL` sets one, for bisecting): 0x0022[6:3], 0x4006 sync, 0x4007 measure, 0x8006 GDI, 0xB773 / 0xBA73 AUX PHY, 0xB7B0 / 0xBAB0 AUX MAC, 0x2AA1 / 0x68A1 CBUS, 0xFF0D ADC (only if on the M2PLL), PWM second stage N (FF3D..FF45, only PWMs on the M2PLL). Dividers are 4 bit (CBUS 3 bit): at M2PLL > 15 x stock-div-limit the clock rises with the M2PLL.
- Regdb limits on the derived dividers: only 0x4006 states a cap: "The clock should be less than 33M after this divider" (sync processor, APLL, DDS, VGA auto) -> the 4-bit divider (max 15) keeps it up to 495 MHz M2PLL; above, the tool logs `!!!!` (not a check). 0x4007 measure and 0x8006 GDI: no limit stated (GDI: GDI Tx / Rx, CBUS, HDMI measure, DP, audio DAC, depop, DP Tx AUX; measure: all on-line and off-line measure). Not retuned: 0x6392[7] rsa_clk_div (1 bit), 0x37A0 M-domain gate.
- Sim (`--sim`): `sim_clock.py` follows `0x01E0` / `0x01E1` / `0x01E7` (M[9:8], N[7:4]) and clears `0x01E5[7]` on write (W1C); the sim has no lock timing, no flash cache. Sim run p372 / p487 / pm72: lock, retune table, timer / delay / debounce rescale and revert to the baseline registers pass (sim cell values for the AUX / CBUS dividers are reset values, not the unit's).
- Revert check compares with the registers read before the first step (the build's own clock), not a fixed 87.7 MHz.
- Measured on hardware: nothing yet (Phase B).
