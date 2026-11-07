# Firmware diag block (boot stage + timing), #23

- Switch: `_AWTO_DIAG` in `fw/overlay/Project/Header/RL6449_Project.h` (`_ON` now). Off = every call site compiles to nothing.
- Block: 48 B XDATA at `0xF6D0..0xF6FF`, `volatile __xdata __at(0xF6D0)`. `fw_build.py` `XRAM` end = `0xF6D0` so the linker never uses it.
- Reader: `scripts/rtd_diag.py <bus> [--watch N]` over debug slave 0x35 (reads + staging only, no other writes). Sim: `fw_sim.py` prints it from sim XRAM.
- Zeroed by `AwtoDiagInit()` at start of `main`; code in `fw/sdcc/awto_diag.inc` (inserted into `SysMain.c` by `keil2sdcc.py`).

## Layout (SDCC little-endian: low byte at the lower address)
| off | size | field |
|---|---|---|
| 0x00 | 2 | magic `'A' 'D'` |
| 0x02 | 1 | version (1) |
| 0x03 | 1 | stage, last reached (monotonic) |
| 0x04 | 16 | 8 x u16 `g_usTimerCounter` (1 ms) at first entry of stage 1..8 |
| 0x14 | 2 | main-loop heartbeat |
| 0x16 | 2 | Timer2 ISR count |
| 0x18 | 2 | EXINT1 (DDC-CI/debug) ISR count |
| 0x1A | 1 | `g_ucDelay5usN_Base` (set by `ScalerMcu5usDelayCalc`) at the calibration; 0 before it ran |
| 0x1B | 2 | 10 ticks of `ScalerTimerDelayXms` (started on a tick edge), Timer2 counts / 4 |
| 0x1D | 2 | 10 x `DELAY_5US()` (= `ScalerDelay5us`), raw Timer2 counts, EA off |
| 0x1F | 1 | `RCAP2H` at the calibration |
| 0x20 | 2 | `DELAY_XUS(100)`, raw counts |
| 0x22 | 2 | `DELAY_XUS_EXINT(100)`, raw counts |
| 0x24 | 2 | 10 x `DELAY_5US_EXINT()`, raw counts |
| 0x26 | 2 | whole panel T3 wait (calibration included), Timer2 counts / 64 |
| 0x28 | 8 | spare |

## Stages (temporal order; timestamp 0 before Timer2 runs)
1 BOOT start of main | 2 GPIO init done (inside `ScalerMcuInitial`) | 3 `ScalerMcuInitial` done | 4 pin-share done | 5 main loop first pass | 6 panel power on | 7 DPTx link start | 8 DPTx link done.
- 6..8 are marked in both the `_PANEL_ON` and `_BACKLIGHT_ON` paths of `UserCommonInterfacePanelPowerAction`; stage 8 comes BEFORE the T3 wait (backlight path).

## Delay calibration (`_AWTO_DIAG_DELAYCAL`, default `_ON`; #53.6, #54)
- Runs once per boot inside the panel T3 wait: `UserInterfaceAdjustWaitPanelT3` -> `AwtoDiagPanelT3Wait(550)` (keil2sdcc rule; code `fw/sdcc/awto_delaycal.inc`, inserted into `ScalerCommonMcu.c` because only scaler files see `DELAY_XUS`).
- The wait ends at the same tick as `ScalerTimerDelayXms(550)`: tick counter at entry + 550, polled; the test time is part of it, so boot time is unchanged. Whole wait measured with Timer2 (0x26).
- Interrupts live (as the SDK has them at T3); EA off only inside each measured body (<= ~100 us), Timer2 TF2 holds the overflow. Overhead of an empty snapshot pair subtracted. Bodies are unrolled x10 where a loop would add overhead.
- 10 ticks are measured from a tick edge (`ScalerTimerDelayXms(1)` first): exact vs the reload period.
- Host: `rtd_diag.cal_eval` (limits and reasons in its `CAL_ROWS`), `unit_health.py` row "delay cal" (sim: tick and T3 rows only; ucsim Timer2 counts machine cycles, busy loops not timed).
- Offline guard (cycle counts of every delay loop in the image vs Keil): `scripts/delay_cal_check.py`, known deviations `re/delay_cal_known.tsv`.

## Timer2 constants (SDK `ScalerCommonTimerFunction.c`; M2PLL 351 MHz, flash div 4, MCU div 1, xtal 14.318 MHz)
- M2PLL mode: 701582 / 96 = 7308, reload `0xE373`, 7309 counts per 1 ms tick.
- Xtal (initial) mode: 14318 / 12 = 1193, reload `0xFB56`, 1194 counts per tick.
- Host picks the row by `RCAP2H` (0xE3 / 0xFB). Counts = whole ticks x (0x10000 - RCAP2) + TH2:TL2 offset, EA off; 0x1B stores counts / 4, 0x26 counts / 64.

## Hardware reference (removed self-test + micro-bench, #53.6)
- Measured 2026-11-06, unit AWT26110003, image wb-fw53 step 2, M2PLL clock, Timer2 7309 counts/ms, interrupts live.
- `ScalerTimerDelayXms(10)` = 9.847 ms (started at an arbitrary phase); 200 x `ScalerDelay5us()` (N=26) = 1094 us = 5.47 us per call incl. Timer2 ISR time.
- Micro-bench, 1000 iterations, EA off (empty `djnz` loop 1216 raw counts): `mov a,dir` 2.11 cycles, `movx a,@dptr` 2.00, `mov a,@r0` 1.00, `djnz` 3.65 (cycles at the expected 87.7 MHz, 4 clocks per cycle).
- Cycle model of `delay_cal_check.py` runs ~20 % fast against this (N=26 loop: 81 cycles = 3.7 us model, 5.5 us measured with ISR).
