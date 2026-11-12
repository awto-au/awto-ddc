# Firmware diag block (boot stage + timing), #23

- Switch: `_AWTO_DIAG` in `fw/sdk/Project/Header/RL6449_Project.h` (`_ON` now). Off = every call site compiles to nothing.
- Block: 48 B XDATA at `0xF6D0..0xF6FF`, `volatile __xdata __at(0xF6D0)`. `fw_build.py` `XRAM` end = `0xF6D0` so the linker never uses it.
- Reader: `scripts/rtd_diag.py <bus> [--watch N]` over debug slave 0x35 (reads + staging only, no other writes). Sim: `fw_sim.py` prints it from sim XRAM.
- Zeroed by `AwtoDiagInit()` at start of `main`; code in `fw/sdcc/awto_diag.inc` (`#include`d in `SysMain.c`, fw/sdk).

## Layout (SDCC little-endian: low byte at the lower address)
| off | size | field |
|---|---|---|
| 0x00 | 2 | magic `'A' 'D'` |
| 0x02 | 1 | version: 1 = byte reads only; 2 = debug slave also answers 0x3C block read (`_AWTO_DBGISR`) |
| 0x03 | 1 | stage, last reached (monotonic) |
| 0x04 | 16 | 8 x u16 `g_usTimerCounter` (1 ms) at first entry of stage 1..8 |
| 0x14 | 2 | main-loop heartbeat |
| 0x16 | 2 | Timer2 ISR count |
| 0x18 | 2 | EXINT1 (DDC-CI/debug) ISR count |
| 0x1A | 1 | `g_ucDelay5usN_Base` (set by `ScalerMcu5usDelayCalc`) at self-test; 0 with the self-test off |
| 0x1B | 2 | `ScalerTimerDelayXms(10)` in Timer2 counts / 4; 0 with the self-test off |
| 0x1D | 2 | 200 x `ScalerDelay5us()` in Timer2 counts / 4; 0 with the self-test off |
| 0x1F | 1 | `RCAP2H` at self-test; 0 with the self-test off |
| 0x20 | 8 | reserved (was the micro-bench, removed in #53.6); 0 |
| 0x28 | 1 | test command (#33): 0x01-0x05 key messages: menu role (AUTO key) / UP / DOWN / exit role (MENU key) / SOURCE, 0x10+n OSD event n, 0x20 debug pop-up, 0x41/0x42 key test screen open/close (#39); cleared when applied |
| 0x29 | 1 | debug pop-up pending (#34): 1 = next input-info pop-up draws the debug lines; test cmd 0x20 sets it + raises event 10 |
| 0x2A | 2 | main-loop passes in the last ~1 s (u16, target byte order) |
| 0x2C | 3 | `g_stOsdInfo` byte offsets of `usOsdState`, `ucOsdEventMsg`, `ucOsdKeyMessage` (`offsetof`, set at boot by `AwtoOsdOfsInit`; #37). `_DP_DEBUG_MSG` on = 4, 6, 7; off = 3, 5, 6; 0 = image without the report. Host: `rtd_proto.osd_offsets_from_diag` |
| 0x2F | 1 | spare |

## Stages (temporal order; timestamp 0 before Timer2 runs)
1 BOOT start of main | 2 GPIO init done (inside `ScalerMcuInitial`) | 3 `ScalerMcuInitial` done | 4 pin-share done | 5 main loop first pass | 6 panel power on | 7 DPTx link start | 8 DPTx link done.
- 6..8 are marked in both the `_PANEL_ON` and `_BACKLIGHT_ON` paths of `UserCommonInterfacePanelPowerAction`.
- Self-test: switch `_AWTO_DIAG_SELFTEST` (`_OFF` default, #53.6). When on it runs once, just before stage 6 (final clock, interrupts live). Both counts stay 0 if `ScalerTimerDelayXms` never returns (#23).

## Timer2 constants (SDK `ScalerCommonTimerFunction.c`; M2PLL 351 MHz, flash div 4, MCU div 1, xtal 14.318 MHz)
- M2PLL mode: 701582 / 96 = 7308, reload `0xE373`, 7309 counts per 1 ms tick.
- Xtal (initial) mode: 14318 / 12 = 1193, reload `0xFB56`, 1194 counts per tick.
- Counts = whole ticks x (0x10000 - RCAP2) + TH2:TL2 offset, read with EA off; stored value is counts >> 2.
- Host picks the row by `RCAP2H` (0xE3 / 0xFB). Nominal: `DelayXms(10)` = 10 ms, 200 x 5 us = 1000 us.

## Measured numbers (self-test + micro-bench, removed from the firmware in #53.6)
- Measured 2026-11-06 on unit AWT26110003, image wb-fw53 step 2 (working-base + #53.2/17/18), M2PLL clock, Timer2 7309 counts/ms.
- Self-test: `ScalerTimerDelayXms(10)` = 9.847 ms (98.5 %); 200 x `ScalerDelay5us()` (N=26) = 1094 us (109.4 %).
- Micro-bench, 1000 iterations each, EA off, raw Timer2 counts (empty `djnz` loop 1216):

| instruction | raw counts | cycles at the expected 87.7 MHz |
|---|---|---|
| `mov a,dir` | 1919 | 2.11 (expect 2) |
| `movx a,@dptr` | 1883 | 2.00 |
| `mov a,@r0` | 1550 | 1.00 |
| `djnz` | 1216 (empty loop) | 3.65 (expect 2-3) |

- Boot cost of bench + self-test (stage times of one boot each, same unit, 2026-11-06): stage 6 at 566 ms vs 554 ms, stage 8 at 711 ms vs 699 ms after removal = 12 ms. Stage 5 is 424 ms in both.

## Debug slave 0x35 read protocol (#38)
- Reference: `scripts/dbg_xdata.py` (host), `fw/sdcc/awto_dbgisr.inc` (ISR block, `#include`d in `ScalerDebugIntProc_EXINT1`), switch `_AWTO_DBGISR` in `RL6449_Project.h`.
- Cause of the old design's 1 MHz failures: the ISR only latched the command and held SCL (FE66 bit0); `ScalerDebug()` loaded FF26 one main-loop pass later (#12).
- Now the ISR, at the STOP of the command write, resets the IIC data FIFO (FF2A bit6), loads FF26 and releases SCL, with no main-loop step.
- Byte read (all versions): write `0x01 [hi]` (main loop, staging), write `0x3A [lo]`, read sub `0x08` x1.
- Block read (version >= 2): write `0x3C [lo, hi, len, seq]`, then ONE read transaction `[0x08]` + repeated start + `len + 1` bytes: data, then checksum `(seq + lo + hi + sum(data)) & 0xFF`.
  - The host verifies the checksum and retries (3 tries): at 1 MHz a reply raced by the ISR returns the previous reply (stale, wrong seq) or garbage.
  - `len` clamped to `_AWTO_DBGISR_BLK_MAX` (24 data + 1 checksum in the IIC data FIFO; the SDK 0xBB reply fills 27); the ISR also stops filling at FF29 bit2 (FIFO full).
  - Host chunks reads at `dbg_xdata.BLK_MAX` = 24. 48 B diag block = 4 transfers (byte path: 97).
  - 0x3C overwrites the staged hi byte (g_pucDdcciData[2]); byte-path callers stage `0x01` themselves each time.
  - Unused by the SDK: main-loop `ScalerDebug()` has no 0x3C case (low nibble 0xC matches no default case).
  - Tried and dropped: FF29 bit7 (iic_force_scl_l, stretch SCL while the FIFO is empty in a read) wedged the DDC bus (EDID silent, power cycle needed) (#38).
- Host picks the path from the version byte: `dbg_xdata.probe` (rtd_diag), `check_diag` (unit_health); version 1 or unreadable -> byte path.
