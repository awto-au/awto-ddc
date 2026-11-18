# MCU and flash clock sweep (unit 3, RTD2795T)

Measured 2026-11-18 on unit 3 (AWT26110003, chip ID reads 0x23, M2PLL 350.79 MHz = 14318 kHz x 49 / 2), image = commit 465cb97 + `-D _AWTO_OSD_HWTEST` (tag clk10), 4K60 DP input, Rotate 180, ambient temperature not logged.
Tags: `[hw]` measured on the unit, `[ds]` MX25L8006E datasheet (`/vendors/macronix/MX25L8006E_v1.6.pdf`, 57 pages, Table 13), `[regdb]` `re/regdb/RTD2795T-CG.tsv.gz`, `[sdk-hypothesis]` Realtek SDK claim, `[sim]` fw_sim only.

## Tool
- `./dev.py clk-sweep --unit 3 [--sim] [--continue-on-fail] STEP...` -> `scripts/clk_sweep.py`; firmware op `AwtoClkApply` in `fw/test/testcmd.c` (struct `g_stAwtoClk`, HWTEST builds only). Logs `tmp/logs/clk_sweep.log` / `.tsv`.
- Runtime step = dividers `FFED[5:2]` F, `FFEE[5:2]` M, `FFE9[3:0]` F2 (MCU = M2PLL / F / M, SPI = M2PLL / F / F2), written in an order whose every transient keeps SPI <= rating and MCU <= the faster end; then Timer2 reload (same formula as `_TIMER2_COUNT_NUM`; formula checked against the stock `RCAP2` = 0xE373 on every run), `DELAY_5US` / `DELAY_XUS` counts (scaled, then secant-calibrated to 105 % +-5 against Timer2), DDC debounce counter scaled with the clock, pad drive / slew optional.
- Safe by construction: the step reverts from the main loop at the hold limit (host revert normally); a stalled main loop = WDT reset (586 ms) = stock clock again. Measured: every failed dual-read step ended in a reset back to stock, unit came back each time (relink < 5 s).
- Refused by the firmware: dividers outside 1..15, SPI above 86 MHz (80 MHz in dual mode), MCU slower than the SPI.
- Checks per step (pass / fail line each): registers read back; Timer2 formula; CRC-32 of code 0x0100..0x3FFF read with MOVC, 3 passes (stock CRC = the file's CRC); XDATA patterns; delay accuracy 97..150 %; 300 debug-link block reads; heartbeat vs host clock +-1.5 %; OSD port write + read-back M1 / M2; revert. Info: cache-miss read time, cache meter (FDB3..FDC6: reads, misses, restarts), Scope 2 / Scope 1 / Asteroids frames drawn per second (fw frame counters, `g_usAwtoScFrames`, `g_usAwtoAstFrames`, `g_usAwtoS2Frame`).
- Session 2 additions (2026-11-18, HWTEST image `-D _AWTO_OSD_HWTEST -D AWTO_CLOCK_MHZ=87`, build `--fw-args=--xdata-floor 0`; the default image boots at 350.8 MHz since b15e45f):
  - Flash write / erase test, steps `<base>_fl0` / `<base>_fl7` (`base` = stock, f175_70, m351; `m351_fl0s` / `m351_fl7s` = 3 cycles): `AwtoClkFlashTest`, spare sector 0xFE000 only (constants in the firmware, never host-set; refuses unless blank or carrying its own 0xA5 0x5A signature; ends blank). Per cycle: `UserCommonFlashErasePage` + blank check, 4096 B programmed with `UserCommonFlashWrite` in 128 B calls, read back; MOVX cycles around the FF60 writes = `g_ucAwtoFlCk` (0 default, 7 = SDK wrapper), read by `_CKCON_MCU_SLOW_CYCLE` in HWTEST builds.
  - Whole-image read (`<base>_img`, every oc step): CRC-32 of banks 0..13 through the flash data port FF7B (`UserCommonFlashRead`), one reference pass at the stock clock per boot, N passes at the step; compares per bank.
  - Overclock: `--allow-overclock-flash` (host) + firmware flag `AWTO_CLK_F_OVERCLOCK` (SPI cap 120 MHz, sweep op only; flash write / erase refused above 86 MHz). Steps `oc88_l<latch>_f<drive_si_fall>_d<si_dly>` / `oc117_...` (+ suffix `L` = 200 CRC passes + 5 image passes); FF6C[5:2] = latch_so_rise, drive_si_fall, si_dly_sel; `--tune-first` writes it before the dividers change.
  - `./dev.py clk-soak [--nvram 0|7] STEP MINUTES` (`scripts/clk_soak.py`): ops KEEP (restart the hold timer; host silence = revert after 20 s) and CHECK (checks again); savers 3 / 4 / 8 / 2 cycling, checks every 30 s, IOSC trim counter logged; `--nvram` = settings write through the firmware mailbox at the held step with the wrapper selected.
  - `./dev.py dss-probe` (`scripts/dss_probe.py`): DDR PHY speed sensor read next to the IOSC counter; the CTRL_3 byte is restored.
  - Scope 2 runs read the flash-cache meter (FDB3 control, FDB9 reads, FDBD misses, FDC1 restarts) from the host over the debug link.
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
- Speed-up needs `_CKCON_MOVX_9_CYCLE` for scaler / flash registers: scaler registers and the OSD data port at 175.4 and 350.8 MHz with the default 2-cycle MOVX: OSD write / read-back 0 bad bytes, link, heartbeat all pass -> not needed for those. `FF6C` / `FF6B` writes were done with the 9-cycle wrapper; the no-wrapper variant was not reached (dual read unusable). NVRAM flash writes / erases above 87.7 MHz: measured in session 2 below (wrapper needed at 350.8 MHz, not at 175.4 MHz).
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

## Session 2 results (2026-11-18 / 19, unit 3, HWTEST images clk20..clk25 = merge of origin/main b15e45f + this branch, `AWTO_CLOCK_MHZ=87`; HDMI D2 4K59.940 input, Rotate 180)
Scope: ambient temperature not logged; the unit had been powered for hours (no cold start possible: no relay on unit 3). Logs `tmp/logs/run_*.log`, `soak_*.log`, `clk_sweep.tsv`.

### Flash write / erase on the spare sector 0xFE000 (`<base>_fl0` = no wrapper, `_fl7` = 9-cycle MOVX wrapper)
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

### Cache meter during Scope 2 (FDB3..FDC6 read from the host over the debug link, 6 s window)
| step | MCU / SPI | Scope 2 fps | program reads / frame | misses / frame | restarts / frame | fills / frame (calibrated) |
|---|---|---|---|---|---|---|
| stock | 87.7 / 43.85 | 6.8 - 6.9 | 1.51 - 1.55 M | 300 - 307 k | 25 k | 8.4 k |
| f175_70 | 175.4 / 70.2 | 14.70 | 1.40 M | 225 k | 18 k | 8.1 k |
| m351 | 350.8 / 70.2 | 20.86 | 1.37 M | 194 k | 15 k | 7.6 k |
| oc88_l1_f1_d1 | 350.8 / 87.7 | 25.46 | 1.34 M | 181 k | 14 k | |
| oc117_l1_f1_d1 | 350.8 / 116.9 | 31.12 | 1.33 M | 174 k | 14 k | |
- Calibration: the CRC pass (15.6 KB of MOVC data = 976 lines) counts 25 k - 35 k meter misses per pass, so the meter counts about 26 - 36 misses per 16 B line fill; dividing by that gives 7.6 - 8.4 k fills / frame at every clock (consistent across clocks, which supports the calibration).
- Model A (2 KB shared common, sim 24.6 k fills / frame) vs B (4 KB per-bank common, sim 15 k): the measured 8 k lies below both, closer to B; the calibration assumes code and data misses count alike, so A vs B is NOT settled. Raw meter counts per frame are 8 - 12 x the sim's fills.
- Miss time per 16 B line (fw loop, ns): stock 3601, f175_70 2014, m351 1465 / 1404, 87.7 MHz SPI 1221 (rising-edge latch, no extra delay), 116.9 MHz 1099.

### Delay check at m351 (`delay` check, secant-calibrated by the sweep op)
- 8 runs (5 in one session, plus the cache run and two soak starts): counts 116 / 90 every time (DELAY_5US / DELAY_XUS(100)); 107 % / 104 - 105 % of nominal; spread 0 counts, 1 % in the percentages. Stock 27 / 21 (28 / 22 earlier build), 103 - 107 % / 105 - 110 %; f175_70 57 / 44.
- Timer2 reload at runtime 0x8DCE (formula check passes); the compile-time default is 0x8DCF (b15e45f). DDC debounce 920 (scaled), heartbeat 0.9967 - 1.0027 over 30 min.
- Default image (compile-time counts 109 / 87) on the unit: diag row `delay cal`: DELAY_5US 5.73 us = 115 %, DELAY_XUS(100) 107 %, DELAY_XUS_EXINT 104 %, DELAY_5US_EXINT 115 % (limit 97..150 %: pass). The row `tick` FAILS (10 ticks = 1.011 ms, wants 10): the diag counts Timer2 counts / 4 in a u16, 10 ms x 29233 / 4 = 73 k wraps at 350.8 MHz (175.4 MHz default build passes all 11 health checks). A diag artifact, not a timing fault; `rtd_diag.cal_eval` and the firmware counter need a wider field.
- Gates on the default image in this worktree: `delays` fails in `delay_audit.py --check` only ("564 linked sites none missing": `docs/delay-audit.tsv` keys carry the absolute path of the audit agent's worktree), `h1080` / `h2160` fail the `delay cal` row in the sim (same u16 wrap); everything else passes.

### Flash overclock (Dan 2026-11-18; MCU 350.8 MHz, fast read 0x0B single bit only, flash writes never above 86 MHz)
- Stock FF6C reads 0x60 = read_mode 01, **latch_so_rise = 1** (rising-edge latch), si_dly 0, drive_si_fall 0 (the brief assumed falling). Steps `oc<MHz>_l<latch_so_rise>_f<drive_si_fall>_d<si_dly_sel 0/2/4/6 ns>`; phase 1 = 3 CRC passes + XDATA + link + heartbeat + OSD + 1 whole-image read (banks 0..13 through FF7B, per-bank CRC-32 vs a stock-clock pass); phase 2 (`L`) = 200 CRC passes + 5 image passes.
| SPI MHz | latch 1 (rising) f0: d0 d1 d2 d3 | latch 1 f1: d0 d1 d2 d3 | latch 0 (falling) |
|---|---|---|---|
| 87.7 (F2 4, +2 % over rating) | P P F F | P P P F | F (all 8 combos) |
| 116.9 (F2 3, +36 %) | P P F F | P P P F | F (f0 d0 tried) |
| 175.4 (F2 2, +104 %) | F F F F | F F F F | F (f0 d0 tried), l1 f1 d1 retried: F |
- P = every check and phase 2 pass (5 combos x 2 speeds x 200 CRC passes + 5 whole-image passes, 0 bank CRC differences, 0 resets). F = unit reset / hang at the clock write (debug slave silent, relink needed); l1 f1 d3 at 87.7 passed the apply but failed the link check (80 of 300 block reads) = marginal.
- Passing window is the same at 87.7 and 116.9 MHz: rising-edge latch, SO delay <= 2 ns (f0) / <= 4 ns (f1). Centre of the window: latch 1, drive_si_fall 1, si_dly 2 ns. Highest passing flash clock: 116.9 MHz. 140 MHz is not reachable with integer dividers (SPI = 350.8 / (F x F2): 175.4, 116.9, 87.7, 70.2, 58.5, 50.1, 43.85 ...); between 116.9 and 175.4 only an M2PLL change.
- Gains (Scope 2 / Scope 1 / Asteroids fps, miss ns): 70.2 MHz 20.9 / 10.3 / 25.0, 1404 ns; 87.7 MHz (l1 f1 d1) 25.5 / 25.0 / 25.0, 1343 ns (l1 f0 d0 1221 ns); 116.9 MHz (l1 f1 d1) 31.1 / 25.0 / 25.0, 1099 ns. Scope 1 and Asteroids sit at their 40 ms schedule from 87.7 MHz.
- No margin test across temperature: IOSC trim counter flat (below); the passing window should be re-measured warm and on other units before anything above 86 MHz is a default. [datasheet] fSCLK 86 MHz (MX25L8006E_v1.6, Table 13); tCLQV 8 ns @ 30 pF: at 116.9 MHz the half period is 4.3 ns, so the margin is not the datasheet's, it rests on this unit's board and die.
- Not tried: FF76 CS# timing counts (not needed at the passing steps); dual read stays off (resets, see above).

### Soak (savers 3 / 4 / 8 / 2 cycling every 30 s, firmware checks + 100 link reads + heartbeat + IOSC every 30 s)
| run | duration | checks | failures | resets | IOSC trim_cnt |
|---|---|---|---|---|---|
| stock (control) | 10 min | 20 | 0 | 0 | 1999 at start, end and every check |
| m351 | 30 min | 60 | 0 | 0 | 1999 at start, end and every check |
- Each check: CRC-32 of code 0x0100..0x3FFF (3 passes) = stock value, XDATA patterns, delay 103 - 107 % / 104 - 105 %, 100 / 100 link reads, heartbeat 0.998 - 1.005 vs the host clock.
- No temperature sensor on the RTD2795T (docs #206): case warmth is not measurable; 30 min at 350.8 MHz is the longest run, one unit.

### Temperature proxy (read-only)
- IOSC trim block 0x06A0..0x06A6 over the debug slave (xdata-mapped): `dc a4 9d 9d cf 77 83` (or `ce` in byte 4): trim_cnt = 0x06A5[7:4] x 256 + 0x06A4 = 1998 / 1999, vc 3, mos 5, trim_done 1, trim code 0x9D. Sampled at every step boundary (stock clock) and every 30 s of both soaks: 1998 / 1999 only, no drift with soak time at stock or at 350.8 MHz [hw]. Sensitivity is one count (0.05 %); the counter is not shown to track die temperature. Cold-start sample not possible (unit on for hours).
- Existence probe (ISP dump, `rtd_reg_dump.py --pages 24,5F,66,41,0A`, 2026-11-19 00:00): pages 24 (0xA0..B5), 5F (0x20..70), 41 (0x00..19) read all zero; page 66 zero except the page-select echo 0x9F; page 0A: 36 non-zero bytes (control page, 0x30..0x4F, 0x80.., 0xA0..0xC7), no sensor-like layout identified.
- DDR PHY speed sensor (DSS, 0xA753 / 0xAF53 CTRL_3, Dan approved the write): one-write enable (0x43 / 0x53 / 0x45 / 0x47 / 0x63 / 0x73) and Realtek's 3-step sequence (rst_n 0 + speed_en 0, rst_n 1, speed_en 1; ro_sel 1..5 x wire_sel long / short) on both channels, 0.5 - 1 s poll: STATUS_3 stays 0x00, `ready` never asserts, no count. CTRL_3 restored to 0x01 and read back each time; picture, DDC/CI, health unaffected. regdb has no dss_clk enable (only the A7 / AF CTRL / STATUS fields): the sensor needs the DDR PHY clock, which is probably not running (frame-sync frame buffer) [?]. Counts at m351 therefore not available.
- I2C probe (`./dev.py i2c-probe`, 2026-11-19, HDMI-A-2 bus 11, 4K59.940 active): `i2cdetect -r` ACK at 0x37, 0x4A, 0x4B, 0x50, 0x54 (SCDC); 0x30 does not ACK here. **0x4B ACKs on the HDMI bus** (not DP-AUX only). Firmware running: 0x4A and 0x4B read 0x00 everywhere (regs 0x00..0x0F and 16-byte reads at 0x00 / 0x40 / 0x6F). MCU halted by the ISP link (0x6F bit 7): 0x4B regs 0x00..0x0F = `11 00 00 48 00 00 00 00 b0 f8 f8 f8 f8 04 00 00`, identical on two reads; 0x4A skipped (ISP). The content follows the MCU state and is static: a scaler-side hardware slave (second ISP-style slave), not a board temperature sensor [guess]. 0x54 SCDC regs 0x00..0x0F = `00 01 00 ...` both states.
- SCDC read-only (input 4K59.940 HDMI active): 01=01 02=00 10=03 20=00 21=01 40=03 50..55=ff 56..5A=00.

### Default image at 350.8 MHz (origin/main b15e45f) on unit 3: boot input detection is unreliable
- Boots after `dev.py reset` (6 s later, synclog), same unit and cable (`tmp/scratch/boots.py`):
| image | MCU / SPI | boots with picture | eDP-1 "link training FAIL" lines |
|---|---|---|---|
| `-D AWTO_CLOCK_MHZ=87` | 87.7 / 43.85 | 8 / 8 | 0 |
| `-D AWTO_CLOCK_MHZ=175` | 175.4 / 43.85 | 8 / 8 | 0 |
| bisect: MCU 175.4 / SPI 70.2 (temporary divider override, not committed) | 175.4 / 70.2 | 8 / 8 | 0 |
| bisect: MCU 350.8 / SPI 43.85 (temporary override) | 350.8 / 43.85 | 5 / 8 | every boot |
| default 350 | 350.8 / 70.2 | 4 / 6 (the first boot after the flash failed too) | most boots |
- Failing boot: `D2 TMDS predetect on (clock not measured yet)`, no `TMDS clock measured`, `SEARCH ... NO SIGNAL: search found no source` after 4.3 s, then power saving; host display on and source present (host DPMS On). Health at 350.8: `mode state POWER_SAVING`, `input timing` 0x0.
- Cause is the MCU clock (350.8 MHz), not the 70.2 MHz flash. The runtime sweep never saw it because the input was already locked when the clock was raised. Some wait in eDP link training / TMDS clock measurement is still too short at 350.8 MHz (not in the DELAY_* constants). Not found yet.
- DDC/CI on the default 350.8 image when it did come up: 20 x getvcp 0x10 0 failures (0.49 - 0.58 s each), 20 x setvcp 0x10 + getvcp 0 mismatches, brightness 1 / 50 / 100 / 50 accepted, VCP 0xEB 3 / 4 / 8 / 2 / 0 accepted, alert tone (VCP 0xEB 6) sent. Audio and PWM clocks derive from M2PLL, unchanged at every step (M2PLL 350791 kHz in each step's log). Front keys: not testable without a person. Other inputs: only HDMI D2 is cabled.

## Recommendation (session 2)
- Do not ship 350.8 MHz as the default yet: boot input detection fails 3 of 8 boots at that MCU clock, independent of the flash clock. 175.4 MHz MCU + 70.2 MHz flash (F 1, F2 5, M 2) boots 8 / 8, passes the sweep, 200-pass soak and the NVRAM write path without the wrapper; keep the wrapper in the build anyway.
- If 350.8 MHz is kept: the 9-cycle MOVX wrapper around FF60..FF6F is mandatory (spare-sector test resets without it), the eDP / TMDS wait must be found, the diag `tick` field widened.
- Flash clock: 70.2 MHz in spec stays the default. 87.7 / 116.9 MHz pass with rising-edge latch and delay <= 2 ns on this unit (200 CRC passes + 5 whole-image reads each; Scope 2 +22 % / +49 % over 70.2 MHz at 350.8 MHz); not a default without a warm / multi-unit window measurement (Dan decides). Flash writes only at the in-spec clock (the sweep op refuses otherwise).
- Checks left for Dan: front keys (SOURCE MENU DOWN UP AUTO POWER) at the fast clock; audio tone by ear; picture by eye during a soak (savers on screen); other inputs (only HDMI cabled).
