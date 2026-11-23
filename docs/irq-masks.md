# Interrupt-masked sections (#281)

- Inventory of every place the firmware holds an interrupt off, with worst cases.
- Data: `docs/irq-masks.tsv` (one row per masked section; hand columns `sim_us hw_us budget_us action reason`).
- Generator + gate: `scripts/irq_masks.py` (`--write`, `--check`, `--sim-merge`); the gate runs inside `scripts/delay_audit.py --check` (the fw_gates `delays` gate).
- Dynamic: `scripts/stall_sim.py --scenario all` (sim, `tmp/logs/stall_sim.tsv`), `scripts/irq_masks_hw.py` (unit).

## What counts as a mask
- `clr EA / EX0 / EX1 / ET0-2 / ES / EX2` (`EIE.0` = WDT warning), `jbc ea` (SDCC `__critical`), `mov/anl IE`, ScalerGlobalIRQControl(_DISABLE) (P0_04[7]: all scaler IRQs into EXINT0).
- `mov IP,#v` swaps priority; listed, no masking.
- Source of truth: the SDCC listing of the build (`tmp/sdcc-port/asm_bank/*.rst`), so only linked code is counted. 64 sections in the default image (2026-11-21, commit 4063de57):
  - EX0 43, EA 13, IP 3, scaler-IRQ gate 2, ET2 1, EX2 1, IE-byte 1.
- Not linked in the default image (source present, compiled out): `FlashWrite.c` EA off/on (`_XDATA_MAP_ACCESS` only), `ScalerCommonTimerFunction.c` ET0/ET1 pairs, `ScalerGlobal.c:441` / `RL6449_Series_Global.c:449` `EX0 = 1`, DPRx0 macros.
- Interrupt sources and how long they may be held:
  - WDT warning: margin 146 ms (docs/watchdog.md).
  - Timer2 tick: 1 ms.
  - EXINT0 DP AUX reply: 300 us.

## Length measures
- static: longest forward path in the CFG (a loop body counts once) at 350.8 MHz, 12 clocks per machine cycle, + callees' longest path + delay rows at their bound (docs/delay-budget.tsv, docs/delay-audit.tsv). MOVX wait states are not modelled.
- sim: `clr` -> next enable, wall time of the sim clock model. Includes ISRs that run inside the section. Per function, not per site. Many PHY / DP steps are stubbed in the sim (HLE), so it under-reads long sections.
- hw: only the TMDS PHY span (see below).

## Ranked sections (longest first)
| id | site | masks | static | sim | hw | starves | action |
|---|---|---|---|---|---|---|---|
| M057 | `ScalerTMDSRxPhySetDeferred` RL6449_Series_TMDSRx2.c:2047 | EX0 | 1578 us (static under-reads; sim 3138 us at 4K60, #331) | 140 us (PHY stubbed) | 3-4 ms | EXINT0 AUX reply | restructure |
| M043 | `ScalerDpRx1PhyCTS` RL6449_Series_DPRx1.c:3660 | EX0, open | 742 us | - | - | AUX reply | ok: PHY compliance mode only |
| M056 | `ScalerMcuInitial` ScalerMcu.c:153 | IE = 0 | 391 us | - | - | nothing running | ok: boot |
| M006 | `AwtoSdTick` sync.c:600 | EX0 | 30 us | 60 us | - | no | ok |
| M005 | `AwtoPsTmdsClk` sync.c:980 | EX0 | 11 us | 150 us | - | no | ok (sim includes ISRs in the window) |
| M011 | `AwtoTmdsIdleKhz` sync.c:1440 | EX0 | 10 us | - | - | no | ok |
| M001 | `AwtoWdtBite` wdt.c:217 | EA, never restored | 11 us | - | - | n/a | ok: reset follows |
| M007 | `AwtoT0EvClock` t0ev.c:191 | EA (`__critical`) | 6 us | - | - | no | ok |
| M063, M064 | `SysPowerMcuClock`, `SysPowerSystemClockSelect` SysPower.c | scaler IRQs (P0_04[7]) | 4 us | - | - | no | ok |
| rest (46) | DP Rx1 AUX-mode macros, T0 event ISR, timer events, wdt probes | EX0 / EA / ET2 | <= 3 us each | <= 15 us | - | no | ok |

## Halts that are not masks (not in the TSV)
- Flash writes and erases halt the MCU in hardware (`ScalerFlashErasePage`: "8051 will halt when common instruction executes"): sector erase up to 200 ms, WRSR 40 ms, page program 3 ms (datasheet maxima, docs/delays.md row "SPI-flash halts").
- Interrupts stay pending for the whole halt; WDT counter freezes (`FFEA[5]`), so no bite (docs/watchdog.md).
- Starved: EXINT0 DP AUX reply (300 us) and every Timer2 tick for up to 200 ms.
- Not measured: the sim does not model the halt; hardware probe not built (finding filed).

## Hardware measurement (unit 3, 2026-11-21, image 30b070a0, HDMI D2 4K60)
- `scripts/irq_masks_hw.py 10`: 10 DDC/CI sleep + wake locks, `sync DONE ... PHY N ms (1 set-up)` = PhySetDeferred span: 3 ms x 9, 4 ms x 1 (ms resolution).
- Health `monitor` row before and after: longest watchdog gap 45.1 ms (main pass); unchanged by the locks. The gap includes every ISR and mask inside it (docs/monitoring.md).
- Not covered: input switch locks (kvm over DDC/CI: D2 bus silent while D1 shows, run abandoned, unit reset), DP AUX / training, flash erase halt, panel sequences, per-site masked time of the other 63 sections (no probe), 0.1 ms resolution of the PHY span.

## Nesting
- Unconditional enables in linked code (`setb EX0/EX1/EA/ET0` with no save or clear before it in the function): `ScalerDpRx1AuxIntInitial` (DPRx1.c:284), `ScalerTMDSRxInterruptInitial` (TMDSRx2.c:436), `SysPowerInitial` (SysPower.c:146), `ScalerMcuDdcciInitial` EX1, `ScalerMcuInitial` EA, `ScalerTimerWDInitial` ET0.
- All are init functions. No masked section in the default image reaches one through its calls except `ScalerMcuInitial` itself (`IE = 0` then `ScalerMcuDdcciInitial` -> `EX1 = 1`: intended, boot).
- Unconditional restores `EX0 = 1` in the DP Rx1 AUX-mode macros are single register writes (0.4 us), no section calls into another.
- Sections that save and restore (`mov EX0,c`): sync.c (3), TMDS PhySetDeferred, T0 event `__critical`: nest correctly.
- Stale flag: `AwtoPsTmdsClk` shows "escapes" (a CFG path to `ret` without a restore found); not confirmed in the source.

## Gate
- `delay_audit.py --check` runs `irq_masks.py --check`: fails on a masked section not in `docs/irq-masks.tsv`, a static worst case over its budget, a raised `budget_us` without `reason`.
- Default budget 100 us. Raised rows: PhySetDeferred 9000, PhyCTS 800, ScalerMcuInitial 400 (reasons in the TSV).
- Tests: `tests/test_irq_masks.py`.
- Refresh after a build: `python3 scripts/irq_masks.py --write`, then fill `action` for new rows.
