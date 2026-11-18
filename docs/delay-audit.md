# Delay audit: every wait at 350.8 MHz (default) and 87.7 MHz

- Decision (Dan 2026-11-18): fixed clock MCU 350.8 MHz, flash 70.2 MHz (F 1, F2 5, M 1, M2PLL 350.79 MHz), [hw] stable on unit 3 (`docs/clock-sweep.md`). Every delay is a compile-time constant from that clock; no run-time calibration, no division at run time.
- Rule (Dan 2026-11-13): delay = datasheet / spec value minus 10 %, never a margin. Timeouts: global timeout rule (what, expected + source, multiplier, expiry).
- Evidence tags: [hw] unit 3, [emu] sim with the clock model (`scripts/sim_clock.py`), [databook], [spec], [sdk-hypothesis], [?].
- Inventory (typed): `docs/delay-audit.tsv`, 564 linked sites + our `..._MS` constants. Sources and value rationale of the SDK constants: `docs/delays.md`. Generated from the post-link listing (`scripts/delay_inventory.py`).

## One clock switch: `AWTO_CLOCK_MHZ`
- `fw/sdk/Kernel/Common/Project_Option.h`: `350` (default) | `175` | `87` (stock). Build: `./dev.py build -D AWTO_CLOCK_MHZ=87 --tag <tag>-clk87`.
- Dividers (`Scaler_Option.h`): 350 = F 1 / F2 5 / M 1; 175 = F 2 / F2 4 / M 1; 87 = F 4 / F2 2 / M 1. MCU = M2PLL / F / M, SPI = M2PLL / F / F2.
- Derived at build time from `_FLASH_CLK_DIV * _MCU_CLK_DIV`: Timer2 / Timer0 / UART reloads (`ScalerCommonTimerFunction.c`; Timer2 reload 0x8DCF = 29233 counts per ms at 350.8, 0xC6E7 at 175.4, 0xE373 at 87.7), delay loop counts and DDC debounce (below).
- `_MCU_SPEED_UP_SUPPORT` = clock above 87: keeps the SDK 9-cycle MOVX wrapper (`_CKCON_MCU_SLOW_CYCLE`) around the NVRAM flash-controller writes (FF60..FF6F); scaler registers and the OSD port need no wrapper at 350.8 MHz [hw]. `_TIMER01_STEP_TIME_MS` is not linked (`t0ev.c` ticks from RCAP2).
- Not clock-derived and unchanged: power-saving (IOSC 28 MHz) and boot (crystal 14.318 MHz) states; their loop counts come from the same formula with their own clock (below).

## Loop counts (class B): `AWTO_DELAY_CNT` in `ScalerCommonPLLInclude.h`
- `count = ceil((T us x kHz / 1000 - ovh clk) / 16)`. DELAY_5US `while(--n)` = 16 clk per count + 15 clk entry; 4 us base of DELAY_XUS = 16 clk per count + 22 clk per outer pass. 16 clk per count [hw]: sweep 87.7 MHz 27/22 counts read 102 / 108 %; 175.4 MHz 57/44 read 103..106 / 105 %; 350.8 MHz 116/90 read 107 / 105 %.
- The variable `d_isr_g_ucDelay5usN_Base` stays (DATA, 2 B): the clock state changes at run time and the EXINT copies read it. `ScalerMcu5usDelayCalc(clk)` only selects a constant pair.

| state | kHz | DELAY_5US | 4 us base | formula wall 5 us / 4 us | sim hot (5 us loop / DELAY_XUS) | was |
|---|---|---|---|---|---|---|
| M2PLL 350.8 (default) | 350791 | 109 | 87 | 5.00 / 4.00 | 100 % / 101..104 % | boot calibration skipped above RCAP2H 0xE3: SDK counts 26 / 21 = 24 % of nominal |
| M2PLL 175.4 | 175395 | 54 | 43 | 5.01 / 4.05 | 100 % / 102..107 % | SDK 53 / 44 [sdk-hypothesis] |
| M2PLL 87.7 (stock) | 87697 | 27 | 21 | 5.10 / 4.08 | 101 % / 104..108 % | calibrated 23 (sim, 87 % of nominal) .. 28 [hw] |
| XTAL 14.318 (boot) | 14318 | 4 | 3 | 5.52 / 4.89 | not run in the scenario | SDK 2 / 2 = 3.3 us / 3.8 us (formula) |
| IOSC 28 (power saving) | 28000 | 8 | 6 | 5.11 / 4.21 | 100 % | SDK 3 / 6: 5 us loop = 2.14 us = 43 % [emu, old image] |

- The SDK 26 / 21 at 350.8 MHz is what the old code would have run if the calibration had been skipped (it was calibrated to 105 % only at the stock reload); 4x faster loops, the case Dan flagged.
- Tolerance: ceil() makes the hot loop >= nominal; upper = nominal + one count (0.9 % at 350.8 MHz, 3.7 % at 87.7 MHz for 5 us) + entry. [emu] hot loops 100..108 %; cold (first fetch, ISR) up to 175 %.
- Hardware limit (clk_sweep `delay` check, `rtd_diag.CAL_ROWS`): lower 97 %, upper 150 %. The 96 % run came from a calibration count that was not the formula's; with compile-time counts expect 100..107 % (the diag runs 10 unrolled cold DELAY_5US: 103..138 % cold in the sim).
- IOSC (power saving): formula uses the 28 MHz nominal. The RC oscillator is trimmed, not crystal exact, tolerance not measured [?]; a delay is short by that tolerance. Only `ScalerPLLM2PLLPower` (M2PLL power-up) and the DDC debounce (`_TMDS_DDC_DEBOUNCE_PS` = 55, SDK value kept: 197 us at 100.5 clk per pass, the normal value is 263 us) run timed loops there. Decision for Dan after the one-off IOSC period measurement below.

## Timer waits (class A), our constants (E), spec minimums (D)
- `ScalerTimerDelayXms`, `ScalerTimerPollingFlagProc`, `ScalerTimerWaitForEvent`, timer events, panel T1..T6, backlight, saver frame schedules, key / sound / pump timing count Timer2 ms (`AwtoMs()` deadlines): same wall time at every clock by construction. [emu] Timer2 ms per wall ms 1.00020 (350.8), 0.99996 (175.4), 0.99976 (87.7) in a 2 s steady window.
- Clock switches lose Timer2 time (24 changes in the panel scenario, about 4 ms each on the 7 MHz crystal step): whole-scenario Timer2 / wall = 0.995 [emu]; not a wait error.
- Delay = spec - 10 % rows (panel T-values etc.): `docs/delays.md`; unchanged.

## Findings and open decisions (2026-11-18/19)
- Decision: delays are build-time constants from `AWTO_CLOCK_MHZ` (above); boot-time calibration deleted. Freed: code -1135 B, XDATA -2 B (map before / after).
- Error found: SDK counts 26 / 21 (`_M2PLL_DELAY*_CNT`) at 350.8 MHz would have run at ~24 % of nominal; boot calibration was skipped above `RCAP2H` 0xE3 [sdk-hypothesis wrong at this clock, derived from the count arithmetic and the sim]. IOSC old counts 3 / 6 gave 43 % of nominal.
- Inventory: 564 linked sites, 0 FIX / UNKNOWN; classes A 303 (timer), B 154 (micro-delay), C 44 (loop count: 29 NOCLOCK, 14 SCALES-BENIGN, 1 OK), D 13, E 50.
- Finding, not fixed (Dan's call): `AwtoMs()` / Timer2 loses ticks while a high-priority EXINT0 handler runs >= ~1 ms (power-saving priority swap). Sim: 2.0 ms wall = 1.14 ms firmware ms. Timer0 events are unaffected.
  - Gate `wdt` case `t0_arm_from_isr` now judges the EXINT0-armed Timer0 event in wall ms with derived bounds 8.0..12.0 ms: not a firmware regression.
- Gate fixes: `delays` inventory keys were absolute worktree paths (now repo-relative); gates `inputrate` and canary timeouts 90 s.
- Open decisions (listed with ids in `docs/open-decisions.md`):
  - IOSC tolerance: measure the PS Timer2 period vs host clock once; sets the IOSC counts 8 / 6 and `_TMDS_DDC_DEBOUNCE_PS`.
  - `_TMDS_DDC_DEBOUNCE_PS` = 55 gives 197 us vs 263 us normal (SDK comment says 300 us) [sdk-hypothesis].
  - Delete the 807 B diag delay measurement after hardware confirmation of the compile-time counts.
  - DPS17 pass-row pulse counted in only 45 % of phases (existing, #110).
  - 9-cycle MOVX wrapper around `FF60..FF6F` kept; NVRAM write / erase above 87.7 MHz untested.

## Spin loops (class C): 44 rows
- DDC debounce (`ScalerSyncDdcDetectDebounce_EXINT1`): 100.2..100.5 clk per pass [emu]; count = `AWTO_CPU_KHZ_M2PLL / 381` = 920 (350.8) / 460 (175.4) / 230 (87.7) = 262.7 / 263.0 / 263.5 us. SDK comment says 300 us [sdk-hypothesis]; the stock count never gave 300. Sweep [hw]: debounce 920 at 350.8.
- `ScalerDebugMessage` / `ScalerDebug`: 5 FIFO reads, about 5 us at 87.7 MHz, 1.3 us at 350.8: a give-up not a wait (the host drains at I2C rate). Not our log path. SCALES-BENIGN.
- Other C rows: hardware-bound state loops (NOCLOCK) or loops whose pass contains a class A / B wait (power-cut polls = 50 x DELAY_5US).
- No pass-count waits (main-loop passes as time) in our code (grep of `Pass|Cnt|Count` against constants).
- Pulse detection that depends on pass time, not a wait: the DPS17 edge counter misses 4 ms pulses in 55 % of phases at every clock [emu, `input_rate_sim.py` informational line, #110]; the gate's calibration now includes the pulse-triggered long pass (worst gap 12.2 ms at 350.8, 19.8 at 87.7).

## Changes (wrong or unproven at the fast clock)
| file | was | now |
|---|---|---|
| `fw/diag/delaycal.c` boot calibration, `g_ucAwtoCal5/X` (2 B XDATA), `RCAP2H == 0xE3` gate, `AWTO_DELAY_TARGET_PCT` / `AWTO_DELAY_CAL_RCAP2H` | run-time calibration, only at the stock reload | removed (-1135 B code with `ScalerMcu5usDelayCalc`); the diag measurement stays as the hardware check |
| `ScalerCommonMcu.c` `ScalerMcu5usDelayCalc` | M2PLL: calibrated override; IOSC 3 / 6; XTAL 2 / 2 | `AWTO_DELAY_CNT` per state |
| `Scaler_Option.h` `_M2PLL_DELAY*_CNT` enum | SDK counts 26 / 21, 53 / 44 | removed |
| `ScalerCommonPLLInclude.h` | - | `AWTO_DELAY_CNT`, `AWTO_CPU_KHZ_M2PLL / XTAL / IOSC` |
| `Project_Option.h`, `Scaler_Option.h` | `_MCU_SPEED_UP_SUPPORT` from local dimming; F 4, F2 2 | `AWTO_CLOCK_MHZ`; F / F2 per clock |
| `RL6449_Gen_Option.h` `_TMDS_DDC_DEBOUNCE_NORMAL` | `230 * 2` | `AWTO_CPU_KHZ_M2PLL / 381` |
| `rtd_diag.PERIOD` | no 350.8 / 175.4 MHz row: health "RCAP2H not in the Timer2 table" | 0x8D: 29233, 0xC6: 14617 |
| `fw/test/testcmd.c` | sweep target `AWTO_DELAY_TARGET_PCT` from `RL6449_Project.h` | local define (sweep op only; image counts are compile time) |
| `delay_cal_check.var_addrs` | failed on the 32-char truncated map name of the `_EXINT` counters | prefix match |
| `wdt_test.py`, `fw_gates.py` | wdt on the 8052 model (no clock model: the 350.8 MHz boot never reached stage 8) | dw8051; two Timer0 cases judged in wall ms (bounds 12.5 / 15.5 ms) |
| `input_rate_sim.py` | calibration window without pulses (missed the pulse-triggered pass at 350.8) | 6 s with one DPS17 pulse per second |

## Run
- Gate: `scripts/fw_gates.py <stem> --only delays` (about 55 s with both images): panel_sim scenario (cold boot, POWER off / on, signal loss, power saving = IOSC, wake) at the image's clock, class A wall time vs argument, Timer2 / wall, every executed loop site >= 99 % of nominal, image counts = formula, DDC debounce, `delay_audit.py --check`. A sibling image `<stem minus -be>-clk87-be` (`-D AWTO_CLOCK_MHZ=87`) is measured too and compared.
- Manual: `scripts/delay_sim.py BIN MAP --other BIN87 MAP87 --audit`; regenerate the inventory after a build: `scripts/delay_audit.py --write`; counts: `scripts/delay_audit.py --counts`. Logs `tmp/logs/delay_sim.log`, `tmp/logs/delay_audit.log`.
- Sim coverage: 27 of 379 compiled loop sites run in the panel scenario (the rest are in paths the sim does not reach: DP RX, HDCP, DDR training variants); the others rest on the formula and `scripts/delay_cal_check.py`. `ScalerTimerDelayXms` is not called in the scenario (0 calls).

## Add a delay
- Use a Timer2 wait (`ScalerTimerDelayXms`, timer event, `AwtoMs()` deadline), or `DELAY_5US` / `DELAY_XUS` for <= 1 ms: never a counted loop of your own.
- Build, run `scripts/delay_audit.py --write`, set the new row's verdict (OK / NOCLOCK / SCALES-BENIGN with the reason), commit the TSV. The gate fails on a linked site that is not in it.
- Spec minimum: value = datasheet - 10 %, source in the row `spec`; timeout: 1.25 x expected worst case (host processes: stall rule), expiry logged.

## Hardware verification plan (unit 3, one session at the default 350.8 MHz image, not run)
| check | how | expect | tolerance | tests which change |
|---|---|---|---|---|
| loop counts 109 / 87 | `clk_sweep.py` `delay` check (diag `usDelay5us10` etc. read at boot) | DELAY_5US 100..107 %, DELAY_XUS(100) 100..107 % | 97..150 % | `AWTO_DELAY_CNT`, `ScalerMcu5usDelayCalc` |
| Timer2 reload 0x8DCF | `tick` + `formula` checks vs crystal | 1.000 | +-0.5 % | `AWTO_CLOCK_MHZ` dividers |
| fw ms vs host ms | `heartbeat` check | 1.000 | +-1.5 % | same |
| DDC debounce count | sweep info line | 920 | exact | `_TMDS_DDC_DEBOUNCE_NORMAL` |
| DDC/CI reply latency, sync-log ms stamps, boot to first picture | `./dev.py health`, `sync_log` stamps vs host clock, `boot_profile.py` | stock spread | +-10 % | timer constants |
| panel VDD / backlight pin timing T4..T6, key debounce / repeat | `dev.py health` pins, `key_hold` + ring stamps | as `panel_sim` (T4+T5 >= 270 ms, T6 >= 900 ms) | +-3 ms | timer constants |
| NVRAM write / erase at 350.8 MHz, soak | `nv_test.py` flushlog + read back, settings save / reload | wrote N B, read back identical | exact | kept 9-cycle MOVX wrapper (FF60..FF6F untested above 87.7 MHz [hw]) |
| IOSC period (power saving) | read Timer2 period in power saving vs host clock (PS reload 0xFB) | 1.000 | measure: sets the IOSC tolerance | IOSC counts 8 / 6, `_TMDS_DDC_DEBOUNCE_PS` |
| M2PLL power-up (`ScalerPLLM2PLLPower` 5 us at IOSC) | wake from power saving x20, HDMI lock | no failed wake | 0 failures | IOSC counts 3 -> 8 |
| `ScalerTimerDelayXms` | not called in the sim scenario: boot with the wait log ring (`AwtoWaitLog`) | arg - 1 .. arg ms | +-1 tick | timer constants |
| HDMI / DP link, audio | soak with source, audio test tone | no drop | - | whole clock change |
- Not observable without a scope / logic analyser: each DELAY_5US / DELAY_XUS site against its datasheet (PHY settle, AUX 30 us, I2C bit times). The diag measures them against Timer2, which shares the PLL: it proves the ratio; the absolute time rests on the Timer2 / host heartbeat check.
