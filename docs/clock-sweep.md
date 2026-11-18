# MCU and flash clock sweep (unit 3, RTD2795T)

Measured 2026-11-18 on unit 3 (AWT26110003, chip ID reads 0x23, M2PLL 350.79 MHz = 14318 kHz x 49 / 2), image = commit 465cb97 + `-D _AWTO_OSD_HWTEST` (tag clk10), 4K60 DP input, Rotate 180, ambient temperature not logged.
Tags: `[hw]` measured on the unit, `[ds]` MX25L8006E datasheet (`/vendors/macronix/MX25L8006E_v1.6.pdf`, 57 pages, Table 13), `[regdb]` `re/regdb/RTD2795T-CG.tsv.gz`, `[sdk-hypothesis]` Realtek SDK claim, `[sim]` fw_sim only.

Register roles, stock values and per-register results: `re/regmap/regs.tsv` (keys `01E0..01E7 FFED FFEE FFE9 FFBD FF6B FF6C FDA0 FDA1 FDB3..FDC6 FDCC 4006 4007 8006 0022`; tests `T-L`, `T-M`, `C-PLLHW`, `C-NVWR`, `C-SOAK` in `re/regmap/tests.tsv`); query: `python scripts/regmap_query.py FFED`.

## Status (2026-11-19)
- Chosen default: MCU 350.8 MHz, flash 70.2 MHz (Dan, 2026-11-19); built in as `AWTO_CLOCK_MHZ` (`docs/delay-audit.md`). Boot input detection failed ~1 boot in 2 at 350.8 MHz on unit 3: eDP AUX read over-run, fixed (section "Default image at 350.8 MHz").
- Flash overclock: ceiling 116.9 MHz at this PLL (section "Flash overclock"); not adopted, only measured.
- Measured in session 2 (2026-11-18/19): NVRAM / flash write at speed (wrapper mandatory at 350.8), cache meter, 30 min soak, flash overclock grid, temperature proxies. Open: M2PLL steps above 350.8 (Phase B), other units; list in "Not yet measured".
- Sections: Method, Clock tree, Rated limits, Results, Flash write / erase, Cache meter, Delay check, Flash overclock, Soak, Temperature proxy and probes, Default image boot, Chosen default, M2PLL steps, Not yet measured, External evidence, Links.

## Method
- `./dev.py clk-sweep --unit 3 [--sim] [--continue-on-fail] STEP...` -> `scripts/clk_sweep.py`; firmware op `AwtoClkApply` in `fw/test/testcmd.c` (struct `g_stAwtoClk`, HWTEST builds only). Logs `tmp/logs/clk_sweep.log` / `.tsv`.
- Runtime step = dividers `FFED[5:2]` F, `FFEE[5:2]` M, `FFE9[3:0]` F2 (MCU = M2PLL / F / M, SPI = M2PLL / F / F2), written in an order whose every transient keeps SPI <= rating and MCU <= the faster end; then Timer2 reload (same formula as `_TIMER2_COUNT_NUM`; formula checked against the stock `RCAP2` = 0xE373 on every run), `DELAY_5US` / `DELAY_XUS` counts (scaled, then secant-calibrated to 105 % +-5 against Timer2), DDC debounce counter scaled with the clock, pad drive / slew optional.
- Safe by construction: the step reverts from the main loop at the hold limit (host revert normally); a stalled main loop = WDT reset (586 ms) = stock clock again. Measured: every failed dual-read step ended in a reset back to stock, unit came back each time (relink < 5 s).
- Refused by the firmware: dividers outside 1..15, SPI above 86 MHz (80 MHz in dual mode), MCU slower than the SPI.
- Checks per step (pass / fail line each): registers read back; Timer2 formula; CRC-32 of code 0x0100..0x3FFF read with MOVC, 3 passes (stock CRC = the file's CRC); XDATA patterns; delay accuracy 97..150 %; 300 debug-link block reads; heartbeat vs host clock +-1.5 %; OSD port write + read-back M1 / M2; revert. Info: cache-miss read time, cache meter (FDB3..FDC6: reads, misses, restarts), Scope 2 / Scope 1 / Asteroids frames drawn per second (fw frame counters, `g_usAwtoScFrames`, `g_usAwtoAstFrames`, `g_usAwtoS2Frame`).
- Session 2 additions (2026-11-18, HWTEST image `-D _AWTO_OSD_HWTEST -D AWTO_CLOCK_MHZ=87`, build `--fw-args=--xdata-floor 0`; the default image boots at 350.8 MHz since b15e45f):
  - Flash write / erase test, steps `<base>_fl0` / `<base>_fl7` (`base` = stock, f175_70, m351; `m351_fl0s` / `m351_fl7s` = 3 cycles): `AwtoClkFlashTest`, spare sector 0xFE000 only (constants in the firmware, never host-set; refuses unless blank or carrying its own 0xA5 0x5A signature; ends blank). Per cycle: `UserCommonFlashErasePage` + blank check, 4096 B programmed with `UserCommonFlashWrite` in 128 B calls, read back; MOVX cycles around the FF60 writes = `g_ucAwtoFlCk` (0 default, 7 = SDK wrapper), read by `_CKCON_MCU_SLOW_CYCLE` in HWTEST builds.
  - Whole-image read (`<base>_img`, every oc step): CRC-32 of banks 0..13 through the flash data port FF7B (`UserCommonFlashRead`), one reference pass at the stock clock per boot, N passes at the step; compares per bank.
  - Overclock: `--allow-overclock-flash` (host) + firmware flag `AWTO_CLK_F_OVERCLOCK` (SPI cap 180 MHz, sweep op only; flash write / erase refused above 86 MHz; firmware flags 0x20 overclock, 0x40 tune-first). Steps `oc88_l<latch>_f<drive_si_fall>_d<si_dly>` / `oc117_...` (+ suffix `L` = 200 CRC passes + 5 image passes); FF6C[5:2] = latch_so_rise, drive_si_fall, si_dly_sel; `--tune-first` writes it before the dividers change.
  - `./dev.py clk-soak [--nvram 0|7] STEP MINUTES` (`scripts/clk_soak.py`): ops KEEP (restart the hold timer; host silence = revert after 20 s) and CHECK (checks again); savers 3 / 4 / 8 / 2 cycling, checks every 30 s, IOSC trim counter logged; `--nvram` = settings write through the firmware mailbox at the held step with the wrapper selected.
  - `./dev.py dss-probe` (`scripts/dss_probe.py`): DDR PHY speed sensor read next to the IOSC counter; the CTRL_3 byte is restored.
  - Scope 2 runs read the flash-cache meter (FDB3 control, FDB9 reads, FDBD misses, FDC1 restarts) from the host over the debug link.
- Sim (`--sim`, `scripts/fw_sim.py`) ran the same sweep first: logic, timer rescale, revert proven; the sim has no flash-cache meter and no real flash timing.

## Clock tree
- MCU = M2PLL / `FFED[5:2]` / `FFEE[5:2]`; flash / SPI = M2PLL / `FFED[5:2]` / `FFE9[3:0]`; each divider 4 bit, 1..15 (registers `[FFED] [FFEE] [FFE9]` in `re/regmap/regs.tsv`).
- M2PLL 350.79 MHz = 14.318 MHz x M49 / N2, O 1 [hw 2026-11-18]. Stock: MCU 87.7, flash 43.85 MHz.
- SDK `_MCU_SPEED_UP_SUPPORT` = `_LOCAL_DIMMING_SUPPORT == _ON` (`Project_Option.h:349`): FFED 2, FFE9 4 -> MCU 175.4, flash 43.9; the SDK states no reason against it with dimming off; it also doubles the DDC debounce and halves the Timer0/1 step [sdk-hypothesis].
- DW8051 databook v3.2a (`/vendors/realtek/analysis/rl6449-dw8051/`): core '0 to greater than 120 MHz', > 100 MHz needs 0.25 um or smaller; this die: rating unknown. MOVX = 2 + CKCON[2:0] cycles (Table 2-5), 4 clocks per instruction cycle; XDATA access (MOV DPTR + MOVX) 5 cycles / 4 code bytes vs IRAM 2 / 2 [databook].
- IOSC (power saving, kept slow by decision): 28 MHz nominal, trim `[06A4] [06A5] [06A2] [06A3]`; regdb target count 1956, live reads 1998..2000 [spec][hw].

## Rated limits
| item | rated | what we run (stock) | tested |
|---|---|---|---|
| SPI FAST_READ 0x0B [ds] | 86 MHz | 43.85 MHz | 21.9 .. 70.2 MHz, all pass |
| SPI READ 0x03 [ds] | 33 MHz | not used | - |
| SPI DREAD 0x3B [ds] | 80 MHz (x1 / x2 part: no dual-I/O, no quad) | not used | see dual read |
| SPI 87.7 / 116.9 / 175.4 MHz (F x F2 = 4 / 3 / 2) | above rating (+2 / +36 / +104 %) | - | 87.7 and 116.9 pass with the right latch settings, 175.4 fails (section Flash overclock); sweep-only flag |
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
- CPU loop (196608 iterations) [hw]: 531 ms stock, 263 ms at 175.4, 131 ms at 350.8 (4x; MCU-bound work scales with the clock).
- Cache miss cost per 16-byte line falls with both clocks; the cache meter counts ~0.6-0.9 % misses of ~6.4 M program reads per 15.6 KB CRC pass (code of the loop itself).

## Flash overclock (MCU 350.8 MHz, flash above the 86 MHz rating) [hw, 2026-11-18/19]
- Step name `ocNN_l<L>_f<F>_d<D>`: NN = flash MHz, L = `FF6C[5]` latch_so_rise, F = `FF6C[4]` drive_si_fall, D = `FF6C[3:2]` si_dly_sel 0..3 (`scripts/clk_sweep.py`); suffix `L` = soak variant. Registers: `[FF6C] [FF6B]`.
- Ceiling at this PLL = 116.9 MHz (+36 %); there is no integer divider between 116.9 and 175.4.

| flash MHz | over rating | `FF6C[5]` = 0 | `FF6C[5]` = 1 (stock value 0x60) pass | `FF6C[5]` = 1 fail | soak `L` |
|---|---|---|---|---|---|
| 87.7 | +2 % | fails every combination (no answer, reset to stock; all 8) | F0: D0, D1; F1: D0..D2 | l1_f0_d2, l1_f0_d3, l1_f1_d3 | pass |
| 116.9 | +36 % | fails | l1_f0_d0, l1_f0_d1; l1_f1_d0..d2 | l1_f0_d2, l1_f0_d3 (and f1_d3) | pass |
| 175.4 | +104 % | fails | none | every combination | - |

- Stock `FF6C` reads 0x60: bit 5 = 1 passes at every speed that passes at all, bit 5 = 0 fails everywhere. Polarity unresolved: the field is named latch_so_rise but the regdb text says 1 = falling edge; recorded by bit value only.
- P = every check + phase 2 pass (5 combos x 2 speeds x 200 CRC passes + 5 whole-image reads through FF7B, 0 bank CRC differences, 0 resets). F = reset / hang at the clock write; `l1_f1_d3` at 87.7 passed the apply but failed the link check (80 of 300 block reads) = marginal.
- Window (bit 5 = 1): SO delay <= 2 ns with drive_si_fall 0, <= 4 ns with drive_si_fall 1; same at 87.7 and 116.9 MHz. Centre: `l1_f1_d1`. 175.4: `l1_f1_d1` retried once, failed again.
- Gains at `l1_f1_d1` (Scope 2 / Scope 1 / Asteroids fps, miss ns): 70.2 MHz 20.9 / 10.3 / 25.0, 1404 ns; 87.7 MHz 25.5 / 25.0 / 25.0, 1343 ns (`l1_f0_d0` 1221 ns); 116.9 MHz 31.1 / 25.0 / 25.0, 1099 ns. Scope 1 and Asteroids reach their 40 ms schedule from 87.7 MHz.
- [datasheet] fSCLK 86 MHz, tCLQV 8 ns @ 30 pF: at 116.9 MHz the half period is 4.3 ns, so the margin rests on this unit's board and die. Not tried: FF76 CS# timing counts. Not tested warm or on another unit.
- Margin rule (recommended, not applied): ~10 % below the highest passing clock, centre of the passing delay window; test hot and cold; boot-time CRC (section "External evidence"). Writes / erases stay at an in-spec flash clock.
- Dual-output read (`FF6C[7:6]` = 10): unusable, cause unknown (SIO1 board wiring not documented here).
  - With `FF6B` left 0x0B: immediate reset, 3 of 3 tries at stock clocks. `FF6B` = 0x3B (DREAD [ds]) is needed with it [regdb: "fast read op code, include fast dual read"].
  - `FF6B` = 0x3B at 87.7 / 43.85: short checks pass (300 link reads, CRC 3 passes, OSD, Scope 2 5.70 / s vs 5.2 single), then reset in the savers (once) and in the 40-pass CRC stress (twice) while single read passes the same stress.
  - Latch flip: immediate reset; `si_dly_sel` 2 / 4 / 6 ns, `drive_si_fall`: apply hung > 21 s, reset.
- Every failed step ended in a WDT reset back to stock; unit came back each time (relink < 5 s).

## Other failures and flakes
- First runs at 43.85 MHz: WDT bite in `ScalerSyncDdcDetect_EXINT1` when the host polled the debug link back-to-back during the 2 s apply op; host polls are now 50 ms apart. Not seen at stock or faster.
- Delay calibration at a step needed warm-up + shortest of 5 runs (cold cache: 85 % one run, 116 % the next); f175_70S read 96 % against the 97 % limit once: calibration flake, not instability. Superseded by compile-time counts (`docs/delay-audit.md`).
- No failure inside the divider steps up to 350.8 MHz and the rated SPI range.

## Soak [hw]
- CRC-32 of code, 15.6 KB through the cache per pass, 0 differing passes: stock 40, s70 40, m175 40, f175_70 40 and 200 (3.1 MB), m351 40 and 200 (3.1 MB), m351 repeated twice more.
- 30-minute soak at m351: 60 checks, 0 failures, 0 resets; stock 10-minute control 0 failures; IOSC trim count 1999 constant through both (no drift visible at this resolution). Overclock `L` variants: see table above.
| run | duration | checks | failures | resets | IOSC trim_cnt |
|---|---|---|---|---|---|
| stock (control) | 10 min | 20 | 0 | 0 | 1999 throughout |
| m351 | 30 min | 60 | 0 | 0 | 1999 throughout |
- Savers 3 / 4 / 8 / 2 cycling every 30 s; per check: CRC-32 of code (3 passes) = stock value, XDATA patterns, delay 103-107 % / 104-105 %, 100 / 100 link reads, heartbeat 0.998-1.005.
- One unit, minutes to 30 min, no temperature measurement (`docs/temperature.md`).

## SDK claims checked ([sdk-hypothesis] -> measurement)
- Speed-up needs `_CKCON_MOVX_9_CYCLE` for scaler / flash registers: scaler registers and the OSD data port at 175.4 and 350.8 MHz with the default 2-cycle MOVX: OSD write / read-back 0 bad bytes, link, heartbeat all pass -> not needed for those. `FF6C` / `FF6B` writes were done with the 9-cycle wrapper; the no-wrapper variant was not reached (dual read unusable). NVRAM flash writes / erases above 87.7 MHz: section "Flash write / erase" (wrapper needed at 350.8 MHz, not at 175.4 MHz).
- Timer2 reload = compile-time product of the dividers: runtime formula reproduces the stock reload (check "formula" pass on every run); heartbeat vs host clock 0.9997 .. 1.0012 at every step.
- Delay counts 26 / 21 -> 53 / 44 at 175.5 (SDK): our calibrated stock counts differ (28 / 24 here), the calibrated counts scale ~1 / clock (e.g. 36 / 39 at 175.4, 116 / 90 at 350.8).
- Timer0 / 1 step 8 -> 4 ms: Timer0 / 1 events are off in our build (`_INSTANT_TIMER_EVENT_0/1 = _OFF`), `t0ev.c` ticks from `RCAP2`; no step needed.
- "WDT counts crystal time": the WDT counter / Timer2 ratio read 1.000, 1.082, 1.068 on different runs: not a fixed reference; the host clock is the reference.
- `FFEE[6]` mcu_peri_non_stop: `re/regmap/fields.tsv` key `FFEE[6:6]`. Chip-ID register read returned 0x23 (rev E) mostly, 0x02 once: unreliable read, not used.
- Pad drive (`P10_C2` 5.5 mA vs 4 mA) and slew: no failure without it at 70.2 MHz, so no effect measurable.

## Flash write / erase on the spare sector 0xFE000 (`<base>_fl0` = no wrapper, `_fl7` = 9-cycle MOVX wrapper) [hw, 2026-11-18]
Per run: 14 x (erase + 4096 B program in 128 B calls + read-back) + 1 closing erase, sector left blank. Wear: about 140 erases in total on 0xFE000 (limit asked ~100; endurance 100 k).
| clock (MCU / SPI) | no wrapper | wrapper |
|---|---|---|
| stock 87.7 / 43.85 | pass (2 runs), 0 bad bytes | pass |
| f175_70: 175.4 / 70.2 | pass (2 runs), 0 bad bytes | pass |
| m351: 350.8 / 70.2 | **unit reset / hang, 3 of 3** (15 cycles once, 3 cycles twice); first time the WDT reset it, the second time the debug and DDC/CI slaves stayed NAK > 25 s until an ISP reset (`dev.py reset`) | pass, 15 cycles, 0 bad bytes |
- `[sdk-hypothesis]` "FF60..FF6F need the 9-cycle MOVX wrapper when the MCU is sped up" is confirmed at 350.8 MHz and not needed at 175.4 MHz (measured, MOVX 2 cycles). Where it hangs inside the cycle is not known (stage markers are unreadable: the debug slave is silent while the op runs).
- The SDK macro `MCU_SET_BYTE_WITH_CKCON` sits around every FF60 write in `ScalerCommonNVRam.c`; with `_CKCON_MCU_SLOW_CYCLE` = default (`_MCU_SPEED_UP_SUPPORT` off) it is a no-op, so a 350.8 MHz build without `_MCU_SPEED_UP_SUPPORT` kills the unit at the first NVRAM write. b15e45f keeps the wrapper (AWTO_CLOCK_MHZ 350 > 87).
- Halt times: `AwtoMs` (Timer2 ISR ticks) under-counts during flash halts (erase "3 ms", program "1.4 s"); host wall time for the whole run 7-11 s. Not a measurement of the flash.
- Production settings write path (`settings set sharpness` + save through the firmware mailbox, flush gate): stock without wrapper pass; m351 with wrapper pass (change + restore, 1 flush, 1 item programmed, 16 B each, no erase needed). The production path at m351 without wrapper was not run (same FF60 sequence as the spare-sector test, which resets).
- Link block reads failed for ~2 s right after the flash test once of 11 flash runs (261 of 300 reads, no data error); not reproduced.

## Cache meter during Scope 2 (FDB3..FDC6 read from the host, 6 s window) [hw, 2026-11-18]
| step | MCU / SPI | Scope 2 fps | program reads / frame | misses / frame | restarts / frame | fills / frame (calibrated) |
|---|---|---|---|---|---|---|
| stock | 87.7 / 43.85 | 6.8 - 6.9 | 1.51 - 1.55 M | 300 - 307 k | 25 k | 8.4 k |
| f175_70 | 175.4 / 70.2 | 14.70 | 1.40 M | 225 k | 18 k | 8.1 k |
| m351 | 350.8 / 70.2 | 20.86 | 1.37 M | 194 k | 15 k | 7.6 k |
| oc88_l1_f1_d1 | 350.8 / 87.7 | 25.46 | 1.34 M | 181 k | 14 k | |
| oc117_l1_f1_d1 | 350.8 / 116.9 | 31.12 | 1.33 M | 174 k | 14 k | |
- Calibration: the CRC pass (15.6 KB of MOVC data = 976 lines) counts 25 k - 35 k meter misses per pass, so the meter counts about 26 - 36 misses per 16 B line fill; dividing by that gives 7.6 - 8.4 k fills / frame at every clock (consistent across clocks, which supports the calibration).
- Model A (2 KB shared common, sim 24.6 k fills / frame) vs B (4 KB per-bank common, sim 15 k): the measured 8 k lies below both, closer to B; the calibration assumes code and data misses count alike, so A vs B is NOT settled. Raw meter counts per frame are 8 - 12 x the sim's fills.
- Miss time per 16 B line (fw loop, ns): stock 3601, f175_70 2014, m351 1465 / 1404, 87.7 MHz SPI 1221 (FF6C[5] = 1, no extra delay), 116.9 MHz 1099.

## Delay check at m351 and on the default image [hw, 2026-11-18/19]
- 8 runs (5 in one session, plus the cache run and two soak starts): counts 116 / 90 every time (DELAY_5US / DELAY_XUS(100)); 107 % / 104 - 105 % of nominal; spread 0 counts, 1 % in the percentages. Stock 27 / 21 (28 / 22 earlier build), 103 - 107 % / 105 - 110 %; f175_70 57 / 44.
- Timer2 reload at runtime 0x8DCE (formula check passes); the compile-time default is 0x8DCF (b15e45f). DDC debounce 920 (scaled), heartbeat 0.9967 - 1.0027 over 30 min.
- Default image (compile-time counts 109 / 87) on the unit: diag row `delay cal`: DELAY_5US 5.73 us = 115 %, DELAY_XUS(100) 107 %, DELAY_XUS_EXINT 104 %, DELAY_5US_EXINT 115 % (limit 97..150 %: pass). The row `tick` FAILS (10 ticks = 1.011 ms, wants 10): the diag counts Timer2 counts / 4 in a u16, 10 ms x 29233 / 4 = 73 k wraps at 350.8 MHz (175.4 MHz default build passes all 11 health checks). A diag artifact, not a timing fault; `rtd_diag.cal_eval` and the firmware counter need a wider field.
- Gates on the default image in this worktree: `delays` fails in `delay_audit.py --check` only ("564 linked sites none missing": `docs/delay-audit.tsv` keys carry the absolute path of the audit agent's worktree), `h1080` / `h2160` fail the `delay cal` row in the sim (same u16 wrap); everything else passes.

## Temperature proxy and probes (read-only) [hw, 2026-11-19]
- IOSC trim block 0x06A0..0x06A6 over the debug slave (xdata-mapped): `dc a4 9d 9d cf 77 83` (or `ce` in byte 4): trim_cnt = 0x06A5[7:4] x 256 + 0x06A4 = 1998 / 1999, vc 3, mos 5, trim_done 1, trim code 0x9D. Sampled at every step boundary (stock clock) and every 30 s of both soaks: 1998 / 1999 only, no drift with soak time at stock or at 350.8 MHz [hw]. Sensitivity is one count (0.05 %); the counter is not shown to track die temperature. Cold-start sample not possible (unit on for hours).
- Existence probe (ISP dump, `rtd_reg_dump.py --pages 24,5F,66,41,0A`, 2026-11-19 00:00): pages 24 (0xA0..B5), 5F (0x20..70), 41 (0x00..19) read all zero; page 66 zero except the page-select echo 0x9F; page 0A: 36 non-zero bytes (control page, 0x30..0x4F, 0x80.., 0xA0..0xC7), no sensor-like layout identified.
- DDR PHY speed sensor (DSS, 0xA753 / 0xAF53 CTRL_3, Dan approved the write): one-write enable (0x43 / 0x53 / 0x45 / 0x47 / 0x63 / 0x73) and Realtek's 3-step sequence (rst_n 0 + speed_en 0, rst_n 1, speed_en 1; ro_sel 1..5 x wire_sel long / short) on both channels, 0.5 - 1 s poll: STATUS_3 stays 0x00, `ready` never asserts, no count. CTRL_3 restored to 0x01 and read back each time; picture, DDC/CI, health unaffected. regdb has no dss_clk enable (only the A7 / AF CTRL / STATUS fields): the sensor needs the DDR PHY clock, which is probably not running (frame-sync frame buffer) [?]. Counts at m351 therefore not available.
- I2C probe (`./dev.py i2c-probe`, 2026-11-19, HDMI-A-2 bus 11, 4K59.940 active): `i2cdetect -r` ACK at 0x37, 0x4A, 0x4B, 0x50, 0x54 (SCDC); 0x30 does not ACK here. **0x4B ACKs on the HDMI bus** (not DP-AUX only). Firmware running: 0x4A and 0x4B read 0x00 everywhere (regs 0x00..0x0F and 16-byte reads at 0x00 / 0x40 / 0x6F). MCU halted by the ISP link (0x6F bit 7): 0x4B regs 0x00..0x0F = `11 00 00 48 00 00 00 00 b0 f8 f8 f8 f8 04 00 00`, identical on two reads; 0x4A skipped (ISP). The content follows the MCU state and is static: a scaler-side hardware slave (second ISP-style slave), not a board temperature sensor [guess]. 0x54 SCDC regs 0x00..0x0F = `00 01 00 ...` both states.
- SCDC read-only (input 4K59.940 HDMI active): 01=01 02=00 10=03 20=00 21=01 40=03 50..55=ff 56..5A=00.

## Default image at 350.8 MHz on unit 3: boot input detection fails [hw, 2026-11-19]
Status: cause found and fixed (eDP AUX read over-run); the `AWTO_CLOCK_MHZ=350` default boots 40 / 40 on unit 3. `scripts/boot_loop.py` = `./dev.py reset` + sync log per boot (logs `tmp/logs/boot_loop/`), 6 s verdict; excluded: one window (01:57 - 02:16) in which the host HDMI output had not started video (every image failed).
- Root cause: `ScalerDisplayDPTx1AuxRead` (`ScalerDisplayDPTx.c`, SDK code, also the Tx2 copy) copied `FIFO_WR_PTR[4:0]` bytes (up to 31) into the caller's buffer without checking them against the request.
  - Callers pass `pData` (XDATA 0xF63D, 16 B): a reply longer than the request overran it into 0xF64D.. (`g_ucDpRx0LTStatus` ... `g_pucSourceSearchPriority`, 0xF65B). The search priority table then read `04 00 00 ..`, so `SysSourceDetectPort` stopped calling `ScalerTMDSRx2TMDSNormalPreDetect` for D2 (2 calls instead of 3): "no TMDS clock measured", NO SIGNAL after 4.3 s.
  - A partial reply made the loop subtract the running offset from an already reduced `ucLength` (underflow -> 16-byte request again), also feeding wrong lane status to link training (the eDP "link training FAIL" line, retry succeeds).
- Evidence (DDCDBG temp build, not committed):
  - Canary on `g_pucSourceSearchPriority[1]` checked at every Timer2 / EXINT0 / EXINT1 entry and exit: first detection always at a Timer2 entry (never an ISR exit), main-loop mark = `UserCommonInterfacePanelPowerTick` (link training), 270 - 390 ms after `main()`.
  - Priority table correct at `main()` entry and in the first loop pass in every boot (not a startup / flash-read fault).
  - AUX read counters at 350.8 MHz: reply length > remaining request in 28 / 32 boots (up to 9 per boot, e.g. FIFO 5 for a 1-byte remainder, 4 for 2); right after the FIFO reset the pointer reads 0, the flags at done read `0x20`, reply cmd 0. At 175.4 MHz: 0 of 160 reads (16 boots x 10).
- Fix (production, no build option): remaining request = total - offset; a reply longer than the remaining request is retried like a NACK; done = offset == total. Speed cost: none measured (only the link-training AUX reads).
- Why the FIFO pointer is wrong at 350.8 MHz only: not found [?]. Not scaler write pacing (FFF1 sel 7 leaves the over-reads), not the start-bit pulse width (5 us between the two start-bit writes leaves them).
- Boots with a picture (unit 3, same cable and host, 16 - 40 boots per row):
| image | picture | eDP "link training FAIL" |
|---|---|---|
| default 350.8 / 70.2 (before) | 6 / 12 .. 11 / 16 (40 - 70 %) | about 90 % |
| `AWTO_CLOCK_MHZ=175` | 20 / 20, 16 / 16 | 0 |
| 350.8 + global MOVX stretch 7 (`CKCON[2:0]` = 7 at `main()`) | 9 / 16 | all |
| 350.8 + wait pump off (`AWTO_WAIT_PUMP` empty) | 30 / 40 | all |
| 350.8 + over-run clamp only | 32 / 32, 24 / 24 | all |
| 350.8 + clamp + 5 us between the AUX start-bit writes | 24 / 24 | all |
| 350.8 + clamp + `FFF1` sel 7 | 24 / 24 | 0 |
| 350.8 + retry of over-long replies (instrumented) | 24 / 24 | 2 / 24 |
| 350.8 + retry of over-long replies (the fix, default build) | 40 / 40 | 19 / 40 |
- Hypotheses: H1 (MOVX stretch for the whole firmware): no effect, costs loop rate (485 vs 586 passes/s, different unit state); H2 (DDC/CI ISR overrun): the DDC detect ISR ran with the D2 port flag set in every boot, bad boots included, and a quiet loop (one DDC read per boot, 7 / 16) failed as often: ruled out; H3 (scaler write pacing): `FFF1` changes the FAIL line only, not the over-reads; H4 (EXINT order): predetect was not called a third time because the search index port type changed, not an ordering race.
- Open: why the AUX FIFO reports a longer / stale reply at 350.8 MHz (needs the AUX lines on a scope); the FAIL line in about half of the boots (retry succeeds; `FFF1` sel 7 clears it, costs scaler write rate: Dan decides); the stale read data of the retried replies is dropped, not examined.
- DDC/CI on the default 350.8 image when it came up: 20 x getvcp 0x10 0 failures (0.49 - 0.58 s each), 20 x setvcp 0x10 + getvcp 0 mismatches, brightness 1 / 50 / 100 / 50 accepted, VCP 0xEB 3 / 4 / 8 / 2 / 0 accepted, alert tone sent. Audio and PWM clocks derive from the M2PLL (350791 kHz in every step log). Front keys need a person. Only HDMI D2 is cabled.
- Diag `delay cal` row: the u16 fields held counts >> 2 / >> 6 and wrapped at 350.8 MHz; now `AWTO_DIAG_XMS_SHIFT` 4 / `AWTO_DIAG_T3_SHIFT` 10 (`RL6449_Project.h`, `rtd_diag.XMS_SHIFT / T3_SHIFT`).
- `AWTO_CLOCK_MHZ=175` default: 20 / 20 boots, 20 / 20 wakes from power saving (`ddc sleep` / `wake`), health 11 / 11.

## Chosen default
- Dan chose 350.8 MHz MCU / 70.2 MHz flash as the fixed default (2026-11-19): 17.55 Scope 2 frames / s (3.1x stock), every check and soak above passed. The runtime sweep could not see the boot-time failure (input already locked when the clock rose); boot statistics: section "Default image at 350.8 MHz" (40 / 40 after the fix).
- Without the 9-cycle MOVX wrapper the unit resets at the first flash write at 350.8 MHz (section Flash write / erase): the wrapper stays.
- Earlier candidate 175.4 / 70.2 (2.2x) stays as `AWTO_CLOCK_MHZ=175`; 87 = stock.
- Adoption in code = compile-time constants (`_FLASH_CLK_DIV`, `_FLASH_2_CLK_DIV`, `_MCU_CLK_DIV`, Timer2 / delay / debounce): `docs/delay-audit.md`.
- Power saving stays on the slow IOSC clock (Dan).

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
- Measured on hardware: nothing yet. Phase B (hardware) not run: Dan approved going past 487 MHz in small steps, stop after about 3 failures.
- Derived-divider retune table (integer divider of the stock divider x new / stock M2PLL; stock 13 unless noted; the tool prints it per step): 13 -> 14 at 372 MHz (-1.5 % off the stock clock), 15 at 401 (-0.9 %), 15 at 430 (+6.1 %), 15 at 487 (+20.3 %); no divider set keeps every derived clock within +-3 % above 401.
- PLL register detail (`[01E0] [01E1] [01E4] [01E5] [01E6] [01E7]`, derived dividers `[4006] [4007] [8006] [0022]` in `re/regmap/regs.tsv`); `0x01E5[7]` as lock indicator untested. RL6463 family uses a 372 MHz N.F PLL (page 41): not this die.
- Derived dividers are 4 bit, so above ~495 MHz the sync clock rises with the M2PLL (cap 33 MHz x 15).

## Recommendation (session 2, 2026-11-19)
- 350.8 MHz default: boot failure fixed (section above, 40 / 40); `AWTO_CLOCK_MHZ=175` boots 20 / 20.
- 87.7 / 116.9 MHz flash pass with `FF6C[5]` = 1 and delay <= 2 ns on this unit: not a default without a warm / multi-unit window measurement (Dan decides). Flash writes only at the in-spec clock (the sweep op refuses otherwise).
- Checks left for a person: front keys (SOURCE MENU DOWN UP AUTO POWER) at the fast clock, audio tone by ear, picture by eye during a soak, other inputs.

## Not yet measured
- Temperature (no known sensor: `docs/temperature.md`), other units / die revisions, soaks of hours.
- Front keys and audio by ear at the fast clock (need a person); other inputs (only HDMI D2 cabled); audio / PWM clocks derive from the M2PLL (unchanged by the divider sweep, M2PLL 350791 kHz in every step log).
- M2PLL steps (Phase B), IOSC tolerance (`docs/delay-audit.md`), Scope 1 plateau 6.3 fps up to 175.4 (not CPU-bound, cause not investigated).
- Flash overclock hot / cold and on other units; flash clock above 116.9 needs a different PLL (not run).
- Power-saving IOSC period vs host clock, 20 wakes, nv_test flushlog at 350.8 (delay-audit hardware items).
- Pending phases: M2PLL Phase B (`pmNN`, `p372..p487`), `C-SOAK` hours, `C-PLLHW`; list `re/regmap/tests.tsv`.

## External evidence on flash overclocking (web research 2026-11-19; no vendor app note found)
- ESP-IDF flash / PSRAM docs (https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/flash_psram_config.html): 120 MHz DDR mode crashes randomly after a > 20 C drift from the boot temperature (tuning done at boot).
- pico-sdk issue #1304 (https://github.com/raspberrypi/pico-sdk/issues/1304): flash over its rating worked after flashing, failed after a cold restart on 2 of 3 boards; a larger divider fixed it.
- Arithmetic [derived]: rising-edge half period 5.8 ns at 86 MHz vs tCLQV 6..8 ns (8 / 6 ns at 30 / 15 pF) on this flash.
- Rule taken from it: margin ~10 % below the highest passing clock, centre of the passing delay window, hot and cold tests, boot-time CRC. Macronix / Winbond publish nothing above the datasheet clock.
- Flash datasheet limits [ds] (`/vendors/macronix/MX25L8006E_v1.6.pdf`): FAST_READ 0x0B 86 MHz, READ 0x03 33 MHz, DREAD 0x3B 80 MHz (no dual I/O, no quad), tCLQV 8 / 6 ns, tCH / tCL 5.5 ns, tCLQX 0.

## Links
- Delay constants at the default clock: `docs/delay-audit.md`; OSD / saver costs: `docs/saver-fps-hw.md`, `docs/osd/path-cost.md`; registers: `re/regmap/`; log `tmp/logs/clk_sweep.log` / `.tsv`.
