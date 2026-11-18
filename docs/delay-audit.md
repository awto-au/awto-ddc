# Delay audit: every wait at 87.7 and 175.4 MHz

- Rule (Dan 2026-11-18): the CPU runs at ONE fixed clock; every delay is a compile-time constant from that clock, no run-time calibration, no division at run time.
- Rule (Dan 2026-11-13): delay = datasheet / spec value minus 10 %; never a margin. Timeouts: global timeout rule (what, expected + source, multiplier, expiry).
- Evidence tags: [hw] unit 3 measurement, [emu] sim with the clock model (`scripts/sim_clock.py`), [databook], [spec], [sdk-hypothesis], [?].
- Inventory (typed): `docs/delay-audit.tsv`, 564 linked sites. Value / source columns of the SDK constants: `docs/delays.md` (Part 1). Sources: `docs/delay-audit.tsv` is generated from the post-link listing (`scripts/delay_inventory.py`), plus our own `..._MS` constants.

## One clock switch
- Build: `./dev.py build -D AWTO_FAST_CLOCK=1 --tag <tag>-fast` = MCU 175.4 MHz (`_MCU_SPEED_UP_SUPPORT`, `fw/sdk/Kernel/Common/Project_Option.h`). No flag = stock 87.7 MHz. Default stays stock until Dan switches it.
- Derived from `_FLASH_CLK_DIV * _MCU_CLK_DIV` at build time: Timer2 / Timer0 / UART reloads (`ScalerCommonTimerFunction.c`), loop counts and the DDC debounce (below). Nothing is calibrated at run time.
- Not changed by the flag: flash clock (FLASH_2 divider 4 in both = 43.85 MHz; 58.5 / 70.2 MHz flash is a separate decision after the sweep).
- Side effects of the SDK speed-up block (`_MCU_SPEED_UP_SUPPORT`) that this audit does not clear: `_CKCON_MCU_SLOW_CYCLE` = 9-cycle MOVX in the NVRAM flash command sequences [sdk-hypothesis], `_TIMER01_STEP_TIME_MS` (not linked: t0ev.c replaces it).

## Loop counts (class B): `AWTO_DELAY_CNT` in `ScalerCommonPLLInclude.h`
- `count = ceil((T us x kHz / 1000 - ovh clk) / 16)`. DELAY_5US: `while(--n)` = 16 clk per count, 15 clk entry. DELAY_XUS base (4 us): 22 clk per outer pass. 16 clk per count [hw]: unit 3 sweep 2026-11-18 27/22 counts at 87.7 MHz read 102 / 108 %, 57/44 at 175.4 MHz 103..106 / 105 %. [emu] hot loop 5 us = 101 % at 27, 100 % at 54.
- Per clock state (`ScalerMcu5usDelayCalc(clk)` selects the constant pair; the variable `d_isr_g_ucDelay5usN_Base` stays because the clock state changes at run time and the EXINT copies read it):

| state | kHz | DELAY_5US count | 4 us base count | wall 5 us / 4 us (formula) | was |
|---|---|---|---|---|---|
| M2PLL stock 87.7 | 87699 | 27 | 21 | 5.10 / 4.08 | boot-calibrated 23 (sim) .. 28 [hw]; SDK 26 / 21 |
| M2PLL fast 175.4 | 175398 | 54 | 43 | 5.01 / 4.05 | calibration skipped (RCAP2H hard-coded 0xE3), SDK 53 / 44 [sdk-hypothesis] |
| XTAL 14.318 (boot, before M2PLL) | 14318 | 4 | 3 | 5.52 / 4.89 | 2 / 2 = 3.3 us / 3.8 us (formula) |
| IOSC 28 (power saving) | 28000 | 8 | 6 | 5.11 / 4.21 | 3 / 6: 5 us loop = 2.14 us = 43 % [emu, old image] |

- Tolerance: ceil() makes the hot loop >= nominal; upper = nominal + one count (1.9 % at 175.4 MHz, 3.7 % at 87.7 MHz, 5 us) + entry. [emu] hot loops 100..108 %; cold (first fetch / ISR) up to 175 %.
- Hardware limit (`delay` check in clk_sweep.py / `rtd_diag.CAL_ROWS`): lower 97 %, upper 150 % stays right: the 96 % run came from a count that was not the formula's (sweep calibration); with compile-time counts expect >= 100 % hot, cold x10-unrolled 5 us reads 103..138 %.
- IOSC (power saving): the formula uses the 28 MHz nominal. The RC oscillator is trimmed, not crystal exact, tolerance not measured [?]; a delay is short by that tolerance. Decision for Dan: measure the IOSC period against the crystal once ([hw] test below), then either accept the tolerance or move the IOSC counts (never a blind margin). In power saving only the M2PLL power-up sequence (`ScalerPLLM2PLLPower`) and the DDC debounce (`_TMDS_DDC_DEBOUNCE_PS` = 55, SDK value kept: 197 us at 100.5 clk per pass, the stock value is 263 us) run timed loops.

## Timer waits (class A), our constants (E), spec minimums (D)
- Timer2 reload is compile time: 14617 counts per ms at 175.4 MHz (0xC6E7), 7309 at 87.7 (0xE373). [emu] Timer2 ms per wall ms 0.99996 / 0.99976 in a 2 s steady window; `rtd_diag.PERIOD` has the 0xC6 row.
- `ScalerTimerDelayXms`, `ScalerTimerPollingFlagProc`, `ScalerTimerWaitForEvent`, timer events, panel T1..T6, backlight, saver frame schedules, key / sound / pump timing all count Timer2 ms (`AwtoMs()` deadlines): same wall time at both clocks by construction.
- Clock switches lose Timer2 time: whole panel scenario Timer2 / wall = 0.995 (24 clock changes, about 4 ms each on the 7 MHz crystal step) [emu]; not a wait error.
- Delay = spec - 10 % rows (panel T-values etc.): `docs/delays.md`; unchanged by this audit.

## Spin loops (class C): 44 rows
- Duration depends on the clock only where a count is not tied to a timer: DDC debounce (`ScalerSyncDdcDetectDebounce_EXINT1`), debug FIFO reads (`ScalerDebugMessage`).
- DDC debounce: 100.5 clk per pass [emu]; count = `AWTO_CPU_KHZ_M2PLL / 381` = 230 (87.7) / 460 (175.4) = 263.5 / 263.0 us [emu] (same as the SDK x2, now derived). SDK comment says 300 us [sdk-hypothesis]; the stock count never gave 300.
- `ScalerDebugMessage` / `ScalerDebug`: 5 FIFO reads, about 5 us at 87.7 MHz, half at 175.4: a give-up not a wait (the host drains at I2C rate). Not our log path. SCALES-BENIGN.
- All other C rows: hardware-bound state loops (NOCLOCK) or loops whose pass contains a class A / B wait (power-cut polls = 50 x DELAY_5US).
- No pass-count waits (main-loop passes as time) found in our code (grep of `Pass|Cnt|Count` against constants).

## Findings (wrong or unproven at 175.4 MHz)
| where | was | now |
|---|---|---|
| `fw/diag/delaycal.c` boot calibration: `RCAP2H == 0xE3` gate (stock reload only) | at 175.4 MHz no calibration, SDK counts 53/44 | calibration removed, formula counts 54/43 |
| `ScalerCommonMcu.c` `ScalerMcu5usDelayCalc`: M2PLL used `g_ucAwtoCal5/X` (2 B XDATA) | boot-measured, stock sim 5 us loop 87 % of nominal | compile-time 27/21, sim 101 % / 104 % |
| IOSC count 3 / 6 (SDK) | 5 us loop 2.14 us in power saving [emu] | 8 / 6: 5.00 us |
| XTAL count 2 / 2 (SDK) | 5 us loop 3.3 us at boot before M2PLL [formula] | 4 / 3 |
| `RL6449_Gen_Option.h` `_TMDS_DDC_DEBOUNCE_NORMAL` `230 * 2` | equal values | `AWTO_CPU_KHZ_M2PLL / 381` |
| `rtd_diag.PERIOD` | no 175.4 MHz row: health "RCAP2H not in the Timer2 table" | 0xC6: 14617 |
| `delay_cal_check.var_addrs` | failed on the 32-char truncated map name of `_EXINT` counters | prefix match |

## Run
- Gate: `scripts/fw_gates.py <stem> --only delays` (about 10 s): panel_sim scenario (cold boot, POWER off / on, signal loss, power saving = IOSC, wake) at the image's clock, class A wall time vs argument, Timer2 / wall, every executed loop site >= 99 % of nominal, image counts = formula, DDC debounce, `delay_audit.py --check`. A sibling image `<stem minus -be>-fast-be` (`-D AWTO_FAST_CLOCK=1`) is measured too and compared.
- Manual: `scripts/delay_sim.py BIN MAP --fast FASTBIN FASTMAP --audit`; regenerate the inventory after a build: `scripts/delay_audit.py --write`; counts: `scripts/delay_audit.py --counts`. Logs `tmp/logs/delay_sim.log`, `tmp/logs/delay_audit.log`.
- Sim coverage: 27 of 379 compiled loop sites run in the panel scenario (the rest are in paths the sim does not reach: DP RX, HDCP, DDR training variants). Those are covered by the count formula and the shape check `scripts/delay_cal_check.py`. `ScalerTimerDelayXms` itself is not called in the scenario (0 calls): hardware list below.

## Add a delay
- Use a Timer2 wait (`ScalerTimerDelayXms`, timer event, `AwtoMs()` deadline), or `DELAY_5US` / `DELAY_XUS` for <= 1 ms: never a counted loop of your own.
- Build, run `scripts/delay_audit.py --write`, set the new row's verdict (OK / NOCLOCK / SCALES-BENIGN with the reason), commit the TSV. The gate fails on a linked site that is not in it.
- Spec minimum: value = datasheet - 10 %, source in the row `spec`; timeout: 1.25 x expected worst case (host processes: stall rule), expiry logged.

## Hardware verification plan (unit 3, ONE session at the fast clock, not run)
| what | how | expect | tolerance |
|---|---|---|---|
| loop counts 54 / 43 | `clk_sweep.py` `delay` check on the `-fast` image (diag `usDelay5us10` etc.) | DELAY_5US 100..106 %, DELAY_XUS(100) 100..106 % | 97..150 % |
| Timer2 reload | `tick` check vs crystal | 1.000 | +-0.5 % |
| fw ms vs host ms | `heartbeat` check | 1.000 | +-1.5 % |
| DDC debounce count | sweep info line (`DDC debounce`) | 460 | exact |
| DDC/CI reply latency, sync-log ms stamps, boot to first picture | `./dev.py health`, `sync_log` stamps vs host clock, `boot_profile.py` | equal to the stock image within the stock spread | +-10 % |
| panel VDD / backlight pin timing T4..T6, key debounce / repeat | `dev.py health` pins, `key_hold` + ring stamps | as `panel_sim` (T4+T5 >= 270 ms, T6 >= 900 ms) | +-3 ms |
| NVRAM flush at the 9-cycle MOVX CKCON | `nv_test.py` flushlog + read back | wrote N B, read back identical | exact |
| IOSC period (power saving) | read Timer2 period in power saving against the host clock (PS reload 0xFB) | 1.000 | measure; sets the IOSC tolerance |
| `ScalerTimerDelayXms` | not called in the sim scenario: a boot with `-D` wait log (`AwtoWaitLog` ring) | arg - 1 .. arg ms | +-1 tick |
- Not observable without a scope / logic analyser: each DELAY_5US / DELAY_XUS site against its datasheet (PHY settle, AUX 30 us, I2C bit times). The diag measures them against Timer2, which shares the PLL: it proves the ratio, the absolute time rests on the Timer2 / host heartbeat check.
