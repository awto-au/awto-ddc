# Clock scaling review: what depends on the MCU / flash / timer clock at 350.8 / 116.9 MHz (2026-11-19)

- Scope: `fw/` (own code), `fw/sdk` active tree, host tools. No hardware used (units busy); everything below is code reading, the existing sim / hardware records, and arithmetic. Tags: `[hw]` measured on a unit (cited doc), `[sim]`, `[derived]` arithmetic from code / databook, `[?]` not measured.
- Default now: MCU 350.8 MHz (stock 87.7), flash 116.9 MHz (stock 43.85), M2PLL 350.79 MHz, IOSC 28 MHz power saving, crystal 14.318 MHz boot. One machine cycle (mc) = 4 clocks: 11.4 ns at 350.8, 22.8 at 175.4, 45.6 at 87.7 (databook, `docs/clock-sweep.md` "Clock tree").
- Verdicts: OK = correct at every clock, wrong = defect, wasted = correct but slower / looser than needed, unknown = no measurement. Priority P1 (blocks a known failure) .. P4.
- Premise corrections (checked in code):
  - The production watchdog is NOT fed by the Timer2 ISR. `SysTimerIntProc2` clears it only under `_WD_TIMER_INT_SUPPORT == _OFF` (`fw/sdk/Kernel/System/Code/SysTimer.c:437`); `Scaler_Option.h:453-457` forces it `_ON` (DP / HDMI 2.0 on). Feeds are main-loop passes and bounded loops only (`docs/watchdog.md`). A main-loop-fed WDT is already the design.
  - `fw/sdk-parked/cpu-suite/docs/cpu-suite.md` (branch a0ae6fa) lines 20 / 27 / 134 ("Timer2 keeps clearing the hardware watchdog") are wrong for the same reason: the suite loop's `AWTO_WDT_PASS` is the only feed. `docs/saver-mode.md:112` "820 ms budget" is the superseded N = 2 design (warning 1025 ms); current warning 200.1 ms, reset 585.9 ms.

## 1. Watchdog
- Time base: CNT2 counts 2048 crystal clocks, CNT3 12 bit (143.0 us per count, wraps 585.9 ms), CNT1 counts wraps (`docs/watchdog.md`, `RL6449_Project.h:327-332`). Not the MCU clock, not M2PLL: the timeout in wall time is identical at 87 / 175 / 350.
- Registers: FFEA (7 en, 6 clr, 5 halt-on-flash, 2:0 N-1), FFEB (timer mode, IRQ), FFAE + FFB0[7:4] threshold (`fw/timer/t0ev.c:37-43`). Warning = `AWTO_WDT_THR` 0x577 = 1399 x 143.0 us = 200.1 ms; reset at N = 1 = 585.9 ms (N = 1 is the hardware minimum: the reset cannot be tightened).
- Feed sites: `fw/diag/diag.c:53` `AWTO_WDT_PASS` (main pass); `ScalerCommonTimerFunction.c:2576 / 2597 / 2632` (`ScalerTimerDelayXms`, `PollingFlagProc`), `ScalerTimerFunction.c:110` (`WaitForEvent`), `AwtoMsg.h:18`, `ScalerCommonNVRam.c:614 / 3884 / 4336` (WREN / WRDIS / WRPROT), flash read / write per call, `OsdPropPutString` per character, `fw/osd/console.c:2871`, `fw/diag/wdt.c:91`.

| item | clock dependency | verdict | evidence | fix / test | prio |
|---|---|---|---|---|---|
| WDT time base | crystal 14.318 MHz (CNT2 / 2048) | unknown (assumed crystal) | `docs/watchdog.md` chain; unit 2 probe reset 605 ms vs 586 expected (+3 %); `clk_sweep.py:468` + `clock-sweep.md` "WDT counts crystal time": WDT / Timer2 ratio read 1.000, 1.082, 1.068 on three runs | test W2: probe 0x4F reset time vs host clock x6, active and power saving; if the ratio is not 1.00 +-0.03 the WDT counts IOSC or a divided clock and every ms figure in `watchdog.md` moves | P2 |
| warning threshold 200.1 ms | wall time; gaps measured at stock 87.7 (active 133 ms, PS 160 ms, 2026-11-11 unit 2) | wasted (active), unknown at 350 | `watchdog.md` wd7 / wd8 sections; `RL6449_Project.h:327` | test W1: read `g_stAwtoWdt.ucMaxPoke` + `g_ucAwtoPokeSite` after 10 min of savers / menu / DDC / wake on the default image; compute-bound gaps shrink about 3-4x, flash-halt and ms waits do not. Then threshold = 1.25 x measured, per state: FFAE / FFB0 are run-time registers, write at power-state change (active tight, PS keeps 200 ms: IOSC unchanged). Reset stays 585.9 ms | P3 |
| 585.9 ms reset (N = 1) | wall | OK | hardware minimum; global rule "1.25 x worst case" met only by the warning, not the reset | none; faster-than-586 ms bite would need a software deadline in the 1 ms tick (superseded #131 design); not recommended: EA-off hangs would still need the hardware path | - |
| main-loop-fed (not ISR-fed) | n/a | OK, already so | `SysTimer.c:437`, feed list above | none | - |
| FFEA[5] halt-on-flash with flash 116.9 MHz, cache fills | flash clock | unknown | `watchdog.md` "NVRAM save bite": bit 5 on, 0x4C still bites, checked at 87.7 / 43.85 only; a fill is a flash read, may be counted as a halt | test W3: 0x4C variant spinning through cache-missing code, bite time vs 1.0x | P3 |
| direct pokes bypass site accounting | none | wrong (minor) | `fw/test/scope_saver.c:280`, `fw/test/asteroids.c:1429` write FFEA[6] directly: `ucMaxPoke` / `g_ucAwtoPokeSite` never see those gaps, so W1 under-reports during savers | use `AWTO_WDT_FEED(site)` with new site ids | P3 |
| `wdt_test.py` default N / THR | none | wrong default, OK in gate | `wdt_test.py:35` `N, THR = 2, 0xC00` vs header 1 / 0x577; gate passes `--header` (`fw_gates.py:120`) | read the header by default or fail without `--header` | P4 |
| PS: WDT IRQ vs EXINT0 priority | IOSC unchanged | OK | `watchdog.md` interrupt model: IP 0x81 PS, stuck EXINT0 not preempted, hardware reset 585.9 ms | none | - |
| cpu-suite idle self-reset 30 s | none | OK (suite only) | branch a0ae6fa `AwtoWdtHang` after `AWTO_CPU_IDLE_MS`; not for the production image | wrong sentence in `fw/sdk-parked/cpu-suite/docs/cpu-suite.md` fixed in the next edit of that file | P4 |

## 2. Timers, serial, I2C, keys, CEC, PWM, audio, power-saving clocks

| item | clock dependency | verdict | evidence | fix / test | prio |
|---|---|---|---|---|---|
| Timer2 reload (1 ms tick) | `_TIMER2_COUNT_NUM` = 0xFFFF - 29233 at 350.8, 14617 at 175, 7309 at 87 | OK | `ScalerCommonTimerFunction.c:123-131`; 16 bit holds 2.24 ms at 350.8; heartbeat 0.9967-1.0027 over 30 min [hw] `clock-sweep.md` | none | - |
| Timer0 events (`t0ev.c`) | RCAP2 shared with Timer2 | OK | `watchdog.md` Timer0 section; gate wdt bounds 8.0-12.0 ms wall (`wdt_test.py:40`) | none | - |
| Timer0/1 instant events, `_TIMER01_STEP_TIME_MS` | MCU clock | OK, not linked | `_INSTANT_TIMER_EVENT_0/1 = _OFF` | none | - |
| UART baud (Timer1, 8 bit) | `_TIMER1_UART_COUNT_BYTE` = clk_kHz / 614 for 9600 baud | wrong if ever enabled | `ScalerCommonTimerFunction.c:84-87`: 571 at 350.8 and 285 at 175.4 overflow the BYTE cast (limit 255 = 157 MHz); `_UART_SUPPORT _OFF` | `#error` when `_UART_SUPPORT == _ON` and count > 255 | P4 |
| `AwtoMs()` / Timer2 tick loss in long EXINT0 | MCU clock (ISR length) | OK / known | open #197: loss >= ~1 ms ISR; ISRs are shorter at 350.8, PS unchanged | none | - |
| DDC debounce `_TMDS_DDC_DEBOUNCE_NORMAL` 920 | MCU clock, empty C loop reading an XDATA word | unknown on hardware | `RL6449_Gen_Option.h:604` = `AWTO_CPU_KHZ_M2PLL / 381`; 100.2-100.5 clk per pass is [sim]; only the count 920 is [hw]; loop runs from flash cache in an ISR (`ScalerCommonSync.c:3548`) | test D1: time EXINT1 debounce on the unit (GPIO / cycle counter). Option: replace the loop by `DELAY_XUS_EXINT(263)` (audited class B, formula + hw check) | P3 |
| DDC debounce PS 55 | IOSC 28 MHz | unknown | #243: 197 us vs 263 us, IOSC tolerance not measured | IOSC period test (below, T6) | P3 |
| Debug slave / DDC-CI engine (IIC_1), EXINT1 `DELAY_30US_EXINT` waits | host I2C rate, wall-time delays | OK | `dbgisr.c:26 / 110 / 147`; delay audit NOCLOCK rows; DDC/CI is polled per main pass (`RL6449_Project.h:790`), latency falls with pass time | none | - |
| DDC/CI on the default image: 20 getvcp read-backs / setvcp mismatches | unknown | unknown | `clock-sweep.md:184` lists "20 x getvcp 0x10 failures (0.49-0.58 s each), 20 x setvcp mismatches" without a verdict | test D2: ddcutil getvcp / setvcp x20 on default vs `-D AWTO_CLOCK_MHZ=175`, same unit | P2 |
| Key scan / ADC | `AWTO_KEY_SAMPLE_MS` 10, combo 80, repeat 500, rate 100 | OK | `keys.c` uses `AwtoMs()` deadlines; ADC clock from M2PLL (unchanged) | none | - |
| CEC | block clock M2PLL / 117 = 3.0 MHz (IOSC branch 1 MHz) | OK | `ScalerCec.c:158-167` constants from M2PLL 351 (0.06 % off), independent of the MCU clock; pad not proven (`cec.md`) | none | - |
| IR | `_IR_SUPPORT _IR_OFF` | OK, n/a | `RL6449_Project.h:2302` | none | - |
| PWM / backlight | M2PLL divider | OK | `ScalerCommonMcu.c:1278-1609` use `_M2PLL_CLK_KHZ`, not the CPU clock | none | - |
| Audio | M2PLL-derived | OK | `clock-sweep.md:184`; depop / mute waits are Timer2 ms | none | - |
| Power saving / wake clocks | IOSC 28 MHz, crystal 14.318; unchanged | OK, one open item | `ScalerMcuFlashClockGroupSetting` restores the fast tune with every return to M2PLL (`clock-sweep.md` default flash clock); `DP_INT.c:74 / 116 / 485` write FFE9 F2 only while FFED[1] mcu_clk_sel = 0 (CPU on crystal / IOSC) | test T6 IOSC period; wake failures 2-3 / 20 at every clock (not clock dependent) | P3 |
| Mixed clocks in the source state machine (crystal 4 / 3 counts) | 14.318 MHz | OK | `delay-audit.md` table: 5.52 / 4.89 us (10 % long) | none | - |

## 3. Delay loops, DELAY_*, hardware timeouts in MCU cycles

| item | clock dependency | verdict | evidence | fix / test | prio |
|---|---|---|---|---|---|
| `DELAY_5US` / `DELAY_XUS` counts 109 / 87 (350), 54 / 43 (175), 27 / 21 (87), IOSC 8 / 6, XTAL 4 / 3 | `AWTO_DELAY_CNT(khz, t, ovh)` = floor((khz x t + 1000 x (15 - ovh)) / 16000), ovh 15 / 22 | OK | recomputed here: 350791 x 5 -> 109, x 4 -> 87; hw 115 % / 107 % / 104 % (limit 97-150 %) `clock-sweep.md:149`; gate `delays` | none | - |
| Class A (timer waits, 303 rows), B (154), D (13), E (60) | Timer2 ms or formula | OK | `delay-audit.tsv` verdicts; 0 FIX / UNKNOWN | none | - |
| Class C NOCLOCK (29): `ScalerDpRx1PhyCTS` (lab mode), debug slave, `DPTx1AuxRead` retries | none (hardware-bound) | OK | audit rows; `DPTx.c:1930-2007` 400 us + 25 x 5 us per attempt, 7 attempts | none | - |
| SDK spin loops with a pass-count bound and no wait (grep `for(... < N)` over the active tree) | would shrink 4x | OK, none found | the only hits are retry / iteration counts (`DPTx` 25 / 7 / 5, `UserCommonInterface.c:3246-3348` power-sequence steps with `ScalerTimerDelayXms` inside, `ScalerCommonSync.c:10476 / 10502` 1500 x `DELAY_30US`, `ScalerPLL.c:2036` debounce count) | none | - |
| ISR delay copies (`d_isr_g_ucDelay*N_Base`) | run-time clock state | OK | `ScalerCommonMcu.c:1746-1757` one constant per state | none | - |
| Diag delay measurement 807 B | n/a | wasted | #243 row 3 | delete after the hw check (test D3 below) | P4 |
| Boot / 175 / 87 consistency | all constants derive from `_FLASH_CLK_DIV x _MCU_CLK_DIV` | OK by construction, 175 not gated | gate `delays` builds the default and `-clk87-be` only (`delay-audit.md` Run); 175 row rests on the formula + sim | add `-D AWTO_CLOCK_MHZ=175` to the gate sibling list | P4 |
| Unsupported `AWTO_CLOCK_MHZ` / `AWTO_FLASH_MHZ` values | n/a | wrong (silent) | `Project_Option.h:352-365`, `Scaler_Option.h:643-660`: any value > 87 other than 350 compiles as 175; any `AWTO_FLASH_MHZ` other than 117 / 87 as 70; `Project_Config_Check.h` has no check | `#error` for values outside {87, 175, 350} / {70, 87, 117} | P4 |

## 4. Interrupt latency and ISR time vs deadlines
- Sim (dw8051, `fw/sdk-parked/cpu-suite/docs/cpu-suite.md`): EXINT0 / Timer0 entry mean latency 78 / 138 / 162 counts = 10.7 / 9.4 / 5.5 us at 87 / 175 / 350: cache-cold entry, falls only 2x for a 4x clock. Timer1 (cache hit) 23 counts = 0.8 us at 350. Not measured on the unit (Phase B of the suite).
- Cache fill on the unit: 1099 ns per 16 B line at 116.9 MHz flash, 3601 ns at stock (`clock-sweep.md` cache meter).

| item | clock dependency | verdict | evidence | fix / test | prio |
|---|---|---|---|---|---|
| Timer2 ISR (1 ms) | 173 mc (sim) = 2.0 us at 350.8, 7.9 us at 87.7 | OK | `watchdog.md` Measured | none | - |
| DP AUX RX reply deadline (300 us spec, ~400 us source timeout) in EXINT0 manual-mode defer (`DP_INT.c:100-140`) | ISR entry latency + cold lines | OK | worst 3 line fills x 1.1 us + 5.5 us entry << 300 us; margin about 40x [derived] | cpu-suite Phase B latency on the unit | P4 |
| EXINT0 DP handlers with 85 / 150 / 300 us waits (`DPRx1_INT.c:485-773`) | wall-time delays | OK | class B rows, hot 100-107 % | none | - |
| EXINT1 debug slave / DDC debounce 263 us + 30 us | wall time | OK | stock had the same wall time; I2C slave stretch not relied on | D1 above | P3 |
| HDCP handlers | none clock-bound | unknown | not exercised in the sim scenario (27 of 379 loop sites run, `delay-audit.md`) | HDCP source soak at 350 | P3 |
| Timer0 event ISR 629 mc per tick (893 on fire) | MCU clock | OK | `watchdog.md` | none | - |

## 5. DP RX link training: timing suspects (unit 2 default image never locks, DPCD 0x202 = 01 00 00 00)
- Signature: lane 0 CR_DONE only (0x202 bit 0), lanes 1-3 never; per-lane PHY sequences are programmed lane by lane (`DPRx1_INT.c:109-267` `P7A_1A_CMU_00` four-step chains per lane, `P7A_A1 / B1 / C1 / D1` DFE enables 507-510). Another agent debugs the lock: this lists suspects only.
- Read-behind (stale first read of a dword) is NOT a suspect for DP RX: the SDK DP RX code reads pages 7A / B0 / B8 / B9 / BA (`grep` over `RL6449_Series_DPRx1*.c`: 114 / 55 / 17 / 6 / 1 reads) and `re/regmap/read_behind.tsv` shows those pages clean; the affected pages (88 8A 8B 8E 8F 90 A0 A3 A4 A6 A7 A8 AB AC AE AF C8 CA CB CE CF D0) are read by SDK code only in `ScalerRotation.c` (fixed 13af8f5).

| # | suspect | clock dependency | verdict | evidence | test | prio |
|---|---|---|---|---|---|---|
| S1 | PHY reset / toggle pulses are two back-to-back scaler stores: `P7A_3A_TMDS_RESET` 0x00 then 0xF0 (`DPRx1_INT.c:397 / 691 / 1007`), `P7A_24_KOFFSET_00` en_fore_offset 1,0,1 (477-481 / 751-756 / 1057-1062), `PB0_01` MAC reset, `PB0_0E` deskew, `PB8_00` SEC reset (`ScalerCommonDPRx1.c:721-730`), `P7A_2D` rstb_fsm. Pulse width = time between the two stores = max(RMW time, FFF1 floor 4 + 4 x sel mc) | MCU clock | wrong (probable) | [derived] RMW about 12 mc: 550 ns at 87.7, 137 ns at 350.8 with FFF1 sel 0; sel 7 floor 32 mc = 365 ns (-34 % vs stock); sel 11 = 48 mc = 547 ns restores stock width; the eDP Tx link-training FAIL line only cleared with FFF1 sel 7 (`clock-sweep.md:179`) = evidence that scaler write spacing matters for DP training | T3: FFF1 sel 11 / 15 on the Rx lock; `fw_sim` count of mc between the paired stores at 350 vs 87 (exact numbers); `DELAY_5US` between the toggle writes | P1 |
| S2 | AUX Tx FIFO pointer read stale / over-long after the done flag (28 / 32 boots at 350.8, 0 / 160 at 175.4); clamp added in `ScalerDisplayDPTx.c:1942` (Tx2 copy 3997); root cause "not found" `clock-sweep.md:169` | MCU clock | wrong (hidden) | two flag / pointer reads closer than the AUX-clock domain sync: H1 (MOVX stretch 7) adds only ~9 mc = 100 ns, and FFF1 paces writes not reads, so neither covers it | T4: `DELAY_XUS(1)` or re-read of IRQ_EVENT between flag and pointer; same pattern: `ScalerDpAuxJudgeHandler_EXINT0` (`DP_INT.c:61-140`) reads PB7_7A / PB7_79 flags then clears: Rx has the same exposure | P1 |
| S3 | `en_fore_offset` calibration 85 us wait then adaptation | wall time | OK | `DELAY_XUS_EXINT(85)` hot 104 % | none | - |
| S4 | Rebuild PHY event 30 ms on Timer0 (`DP_INT.c:431 / 822`) | Timer0 / RCAP2 | OK | `watchdog.md` 30 -> 30.07 ms [sim] | cancel / arm order on hw | P3 |
| S5 | Cold flash lines inside EXINT0 training handlers (about 1.1 us per 16 B) | flash clock | OK | handlers contain 85-300 us waits | none | - |
| S6 | Lane-by-lane sequence timing: lane 0 gets the full settle, later lanes less | MCU clock | unknown | signature above | T3 variant: 10 us between per-lane enables | P2 |

## 6. DDR / OSD / display dividers from M2PLL
- All unchanged (M2PLL fixed): DDR, OSD clock, display PLL, AUX PHY / MAC dividers (0xB773 / 0xB7B0), CBUS, ADC. OK. The only MCU-side coupling is bus timing (section 7).

## 7. Things that now run too fast (minimum setup / interval between accesses)

| item | clock dependency | verdict | evidence | fix / test | prio |
|---|---|---|---|---|---|
| Flash controller FF60 / FF6F start bits | MOVX cycles | OK with wrapper | `ScalerCommonNVRam.c:504-4438` `MCU_SET_BYTE_WITH_CKCON`; unwrapped hangs at 350.8 3 / 3, fine at 175.4 [hw] `clock-sweep.md:127` | none; wrapper kept for every build > 87 (`Project_Option.h:389-395`), not needed at 175 (cost negligible) | - |
| Flash controller FF61..FF66, FF71, FF7B data port stores (not wrapped) | MOVX cycles | unknown | only FF60 / FF6F are wrapped in the SDK; production flush at 350.8 passes 20 / 20 with the wrapper on those two [hw] | `nv_test.py` flushlog soak at 350.8 (existing item) | P3 |
| OSD data port `AWTO_OSD_PORT` (was store + 24 nops; nops dropped 2026-11-19, spacing = FFF1 sel 12, `osd-port-loss.md`) | hardware pace | done | `RL6449_Project.h:1178`; need = 16 nops = 182 ns at 350.8, fix 1.5x `scope-corruption.md`; at 87.7 a store + 24 nops = 29 mc = 1.3 us per byte, 7x the 182 ns need | derive from the clock: nops = ceil(1.5 x 182 ns / mc), 24 / 12 / 6 at 350 / 175 / 87; bisect 12..16 again after S1 | P3 |
| Scaler write pacing FFF1 sel (default now 12 = 52 mc, same at all clocks, `osd-port-loss.md`) | fixed sel, cycles | wasted at 175 / 87 (every scaler write paced to 730 ns / 1.46 us) | `RL6449_Project.h:27-28`, `ScalerMcu.c:92-93`; value found at 350 only, sel 0..6 not bisected | sel as a function of the clock (time-based: 365 ns: 7 / 3 / 1); bisect 4..7 at 350. Side effect: stock-clock benchmark builds (`-clk87`) are slower than true stock | P3 |
| SDK `ScalerOsdHardwareCompression` sets FFF1[3:0] = 2 and restores | cycles | unknown | `RL6449_Series_OsdHardwareCompression.c:100` (mask 0x8F, bits 7 and 1): during the rotate-180 font load (used on unit 3) pacing drops from sel 7 to 2 for the 2 ms window; ISRs (Timer2 touches FFF4 each ms) write scaler registers in it | font read-back after a rotated load at 350 (T7-style); else keep max(sel, 7) | P3 |
| Palette port 0x6E / 0x6F, window regs, CBUS | write interval | OK (SDK path paced) | `sc-hw350sdk` 0 diffs [hw] `scope-corruption.md`; only the OSD data port is stored directly in `fw/` (`grep AWTO_XFR`: tests, sync.c) | none | - |
| EEPROM, GPIO bit-bang | n/a | OK, n/a | `_SW_IIC_SUPPORT` / `_HW_IIC_SUPPORT _OFF`, `_PCB_SYS_EEPROM_IIC _NO_IIC_PIN` (`RL6449_AWTO_JXC4K.h:204-220`); NVRAM = flash | none | - |
| Register read right after write / flag (read-behind class) | MCU clock | partly fixed | rotation PA0_05 double read; AUX Tx clamp; FFBC lowering hazard (never below 0x0F) | S2 test | P2 |

## 8. Host tools
| tool | bound | verdict | evidence | fix | prio |
|---|---|---|---|---|---|
| `clk_sweep.py` | `HOLD_S` 25 s, apply limit scaled by clock / SPI ratio, tick check vs stock step | OK | `clk_sweep.py:190 / 418`; `scale = max(1, 87.7 / mcu, 43.85 / spi)` is >= 1 only: fast steps get no tighter bound | none | - |
| `boot_loop.py` | `VERDICT_S` 7 s (4.3 s no-signal x 1.25 + link) | OK | boot to ACTIVE ~1.3 s, wall-dominated | none | - |
| `wake_sim.py` | wake bounds 45 / 24 / 94 ms, poll gap 10 ms | OK | PS on IOSC, unchanged | none | - |
| `wdt_test.py` | Timer0 8.0-12.0 ms wall, probes 1500 ms, SETTLE 17 s | OK; defaults stale | see section 1 | read header | P4 |
| `rtd_diag.py` `PERIOD`, `XMS_SHIFT` 4 / `T3_SHIFT` 10 | counts per ms 29233 | OK | fixed after the u16 wrap (`clock-sweep.md:185`) | none | - |
| `delay_audit.py --check`, `delay_sim.py`, `inputrate` gate | formula, sim fill 68 clk | OK | `clock-sweep.md:252` | none | - |

## Ranked hardware tests (when a unit is free; default image 350.8 / 116.9 unless stated)
1. T3 DP RX lock vs write pacing: FFF1 sel 7 / 11 / 15 (build constant or runtime op), read DPCD 0x202..0x205 from the host; then 1 us between the P7A toggle writes. Decides S1 / S6. Needs a DP source on unit 2 or 3.
2. T4 AUX read-after-flag: `DELAY_XUS(1)` before the pointer read in `DPTx1AuxRead`, boots x 40 with the clamp removed (instrumented build): over-reads 28 / 32 -> expect 0.
3. W1 watchdog active budget: `ucMaxPoke` + site after 10 min mixed load (savers, menu, DDC/CI, wake); sets the active warning threshold.
4. W2 WDT period vs host clock, active and PS (probe 0x4F x 6): identity of the time base.
5. D2 DDC/CI getvcp / setvcp x 20 on default vs `AWTO_CLOCK_MHZ=175`.
6. D1 EXINT1 debounce duration; then T6 IOSC period (existing, sets IOSC counts and `_TMDS_DDC_DEBOUNCE_PS`).
7. W3 FFEA[5] with a cache-thrashing spin (bite time).
8. FFF1 sel bisect 3..7 and OSD nop bisect 8..16 (needs S1 result first).
9. `nv_test.py` flush soak at 350.8, cpu-suite Phase B, HDCP soak (existing).

## Draft issues (not posted; public repo): `tmp/scratch/issue-clock-*.md`
- `issue-clock-dp-rx-pulse-width.md` (S1, S6), `issue-clock-aux-read-sync.md` (S2), `issue-clock-wdt-budget.md` (W1-W3, direct pokes, stale doc lines), `issue-clock-fixed-spacing.md` (OSD nops, FFF1 sel, HW compression), `issue-clock-config-guards.md` (UART, `#error`, gate 175, wdt_test default).
