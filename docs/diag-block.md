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
| 0x1A | 1 | `g_ucDelay5usN_Base` (set by `ScalerMcu5usDelayCalc`) at self-test |
| 0x1B | 2 | `ScalerTimerDelayXms(10)` in Timer2 counts / 4 |
| 0x1D | 2 | 200 x `ScalerDelay5us()` in Timer2 counts / 4 |
| 0x1F | 1 | `RCAP2H` at self-test |
| 0x20 | 2 | micro-bench: 1000 x `mov a,0x7f`, raw Timer2 counts |
| 0x22 | 2 | 1000 x `movx a,@dptr` (DPTR = block base) |
| 0x24 | 2 | 1000 x `mov a,@r0` (R0 = 0xFF) |
| 0x26 | 2 | 1000 x empty `djnz` loop (baseline) |
| 0x28 | 8 | spare |

## Stages (temporal order; timestamp 0 before Timer2 runs)
1 BOOT start of main | 2 GPIO init done (inside `ScalerMcuInitial`) | 3 `ScalerMcuInitial` done | 4 pin-share done | 5 main loop first pass | 6 panel power on | 7 DPTx link start | 8 DPTx link done.
- 6..8 are marked in both the `_PANEL_ON` and `_BACKLIGHT_ON` paths of `UserCommonInterfacePanelPowerAction`.
- The self-test runs once, just before stage 6 (final clock, interrupts live). Both counts stay 0 if `ScalerTimerDelayXms` never returns (#23).

## Timer2 constants (SDK `ScalerCommonTimerFunction.c`; M2PLL 351 MHz, flash div 4, MCU div 1, xtal 14.318 MHz)
- M2PLL mode: 701582 / 96 = 7308, reload `0xE373`, 7309 counts per 1 ms tick.
- Xtal (initial) mode: 14318 / 12 = 1193, reload `0xFB56`, 1194 counts per tick.
- Counts = whole ticks x (0x10000 - RCAP2) + TH2:TL2 offset, read with EA off; stored value is counts >> 2.
- Host picks the row by `RCAP2H` (0xE3 / 0xFB). Nominal: `DelayXms(10)` = 10 ms, 200 x 5 us = 1000 us.

## Micro-bench (self-test, after the delays)
- Inline asm, 4 x 250 `djnz` nest, EA off; R6/R7/R0/DPTR/ACC saved. Raw counts (not shifted), host: (x - empty) / 1000 = Timer2 counts per instruction.
- Host assumes DW8051 cycles: `mov a,dir` 2, `movx` 2, `mov a,@r0` 1, `djnz` 2-3; 4 clocks per cycle; expected MCU clock 87.7 MHz (M2PLL 350.8 / 4).
