# Main-loop pacing and headroom (Dan 2026-11-19)

Status 2026-11-19. Decision (Dan 2026-11-19): 4 ms paced loop is the DEFAULT; felt on unit 3, "fine". `-D AWTO_LOOP_PACING=0` builds the free-running loop.
Tags: [measured] sim / repo scan, [databook], [sdk-hypothesis], [guess]. Decision: Dan.

## 0. Implemented 2026-11-19 (Dan: GO, pop-up 2026-11-19)

`AWTO_LOOP_PACING` = N ms, default 4; 0 = free-run (`./dev.py build -D AWTO_LOOP_PACING=0`). Sleep = `AwtoLoopPace()` at the end of every pass (`fw/diag/diag.c`).
- Wakes at the first of:
  - N ms since the previous pass.
  - A wake bit: `d_isr_g_bWkEx0 / Ex1 / T0` set by the EXINT0, EXINT1, Timer0 ISRs; `d_g_bWkSw` for software (`AWTO_WAKE_SW()`). Timer1 / serial ISRs are empty / unused: no bit.
  - The earliest valid timer event: `SysTimerNextEventMs()` (`SysTimer.c`; fires at counter > time as `SysTimerHandler`): event resolution stays 1 ms.
  - The next key sample (`AwtoKeyDueMs()`, 10 ms) and the next settings-loop service (`AWTO_SET_LOOP_MS`, 20 ms).
- Lost wake: a wake bit set between the flag check and the IDL write sleeps until the next IRQ. Worst case 1 Timer2 tick (1 ms). No EA trick: a halted 8051 cannot run `EA = 1`, databook says wake needs an enabled IRQ. Test `race`: next pass 1 tick after the injection.
- Busy hook `AwtoLoopBusy()` (`fw/keys/keys.c`, the one list): no sleep while any of
  - mode state initial / search / display setting, power status AC on (source scan, link training, boot / power steps);
  - a saver runs (`g_ucAwtoSaverRun`), key test / GPIO page open, console log with lines to draw (`AwtoConBusy`: an open idle console sleeps; awto-ddc pacing-stuck), console auto-open pending, our menu on, any OSD state other than none (selector, backlight bar, cards: they also count pulses per pass, DPS17), a key down or injected key queued, a deferred DDC/CI reply.
  - NVRAM flush and panel / power steps run from timer events or the 20 ms settings loop: deadlines, not listed.
- Keys: decisions were already time-based (`AwtoMs` compares: 10 ms sample, 2 equal samples, 80 ms combo, 500 ms repeat, 100 ms rate, 10 s reset). Added: pass-count prefilter `AWTO_KEY_PASS_N = floor(10 / N)` (4 ms: 2, 8 ms: 1) in front of the tick compare. Tick compare stays the exact gate (early wake passes, free-run busy passes at 2300 /s); floor (not round) because the sleep also wakes at the sample deadline, so at least N passes fit in 10 ms.
- Headroom (last 1 s window, `g_stAwtoHead`, 12 B, read by symbol: the 48 B diag block is full): passes, sleep per mille, worst busy pass (1/16 ms), passes with the busy hook on (per mille), IDL exits, passes ended by a wake bit.
  - Shown in: monitor sync row `headroom N passes/s, busy P %, worst pass X ms` (arg 5, on the heartbeat), console LOOP row ` busy P%`, `./dev.py health` row `headroom`, `docs/speed-bench.tsv` columns `pacing_ms passes_s_idle busy_pct_idle worst_ms_idle` (`loop_pacing_sim.py --bench LABEL`).
  - Health rule: idle ACTIVE (busy hook < 10 % of passes, re-read up to 4 windows while it is on): busy < 50 % x (350 / image clock MHz), capped at 95 % (Dan 2026-11-20; clock from the image's build.json), worst pass < 10 ms; busy hook still on after 4.8 s = FAIL (stuck producer).

Sim numbers (350.8 MHz, ACTIVE 1080p60, idle, 5 s after ACTIVE, `scripts/loop_pacing_sim.py`; dw8051 core with exact idle):

| image | passes/s | busy % (not asleep) | CPU duty % | worst pass | IRQ/s | key press -> mask |
|---|---|---|---|---|---|---|
| free run (0) | 2436 | 100 | 100 | n/a | n/a | 18 / 16 / 12 ms |
| 4 ms | 300 | 15.4 | 18.8 | 0.69 ms | 1000 | 13 / 12 / 17 ms |
| 8 ms | 200 | 11.0 | 13.5 | 0.62 ms | 1000 | 18 / 13 / 13 ms |

- Passes are 300 / 200, not 250 / 125: the key-sample deadline (10 ms) adds a pass per sample. Dropping that wake at 4 ms gives ~250 /s and a key sample at 12 ms (debounce window 12 instead of 10 ms): not done, debounce window kept.
- Key latency = three presses at different phases against the 10 ms grid; limit 2 samples + a pass (21-28 ms). Free run and paced agree: key timing no longer depends on the pass period, 8 ms is as good as 4 ms for keys. Sampling code cost per pass not measured separately (a byte increment + compare per pass at N > 1).
- 1000 IRQ/s in idle = the Timer2 tick (1 per ms); EXINT0 / EXINT1 / Timer0 add none in idle ACTIVE with nothing connected moving (passes ended by a wake bit: 0 per window).
- Timer2 tick ISR (`SysTimerIntProc2`): about 173 machine cycles = 2.0 us at 350.8 MHz [measured: `clock-scaling-review.md`] x 1000 = 0.2 % CPU. Runs per tick: ms counter (`d_isr_g_usTimerCounter`), diag count, LED / measure hooks, watchdog clear (`CLR_MCU_WATCH_DOG` when the WD timer interrupt is off), DP HPD IRQ timer hook; timer events and key debounce run in the pass, not in the ISR. Tickless judgement: not worth it (0.2 % CPU; the IDL wake per tick costs 5-13 cycles of IRQ entry); not investigated further (Dan).
- Power: DW8051 does not gate the clock in idle (databook 3-54..3-56): the saving is CPU duty, sim speed (sim / host 26.6 at 4 ms, 36.3 at 8 ms, 5.6 free run) and headroom, not a clock-gated current drop. Expected power change unknown until measured on the unit power meter (`docs/power-levels.md`); the flash fetch / cache fill traffic that stops with the CPU is the likely part [guess].
- Gates on the 4 ms image: all PASS except `delays` (same FAIL on the free-run image) and the `delay cal` row inside `h1080` / `h2160` (accepted by `fw_gates.py`, needs the wb-delaycal image). 8 ms: `sysm`, `wake`, `sync`, `keys` PASS since `SimBus.wait` sizes its chunk by the instructions per ms of the last chunk (a paced loop executes 10x fewer per ms, the old fixed 4200 per ms overshot).
- Tests (`scripts/loop_pacing_test.py BIN --period N`, ~1 s of sim each): `headroom` (pacing engages, no long pass), `race` (Timer0 IRQ between the flag check and the IDL: <= 1 tick), `keys` (press -> mask within 2 samples + a pass), `stuck` (AwtoLoopBusy forced on: hook 100 %, health row FAIL).
- ISR diet step 1 (TMDS `SetPhy_EXINT0` out of EXINT0): NOT implemented, no change to the HDMI lock path without the unit.
  - Where: `ScalerTMDSRx2IntHandler_EXINT0` / `Rx3` (`RL6449_Series_TMDSRx2.c:1966`), branch "Freq. Stable Into IRQ": the block after the pixel clock read (divider, measure + `SetPhy_EXINT0` + `CheckCDRStable_EXINT0`, freq bounds, HDMI 2.0 CED set-up) is the 5.5 ms part.
  - Why not blind: the main loop reads `GET_TMDS_RX2_PHY_SET()` in `ScalerTMDSRx2TMDSScanInputPort` and `FreqDetectDisable`; the "Freq. Unstable" ISR branch compares against `isr_g_usTMDSRx2ClkCount` that the block writes. A deferred block needs: a pending flag per port set by the ISR (stable IRQ already acknowledged, unstable IRQ held off until the block ran), the block run from `SysTMDSRxHandler` before the scan, the scan treating "pending" as not locked yet. The TMDS PHY / freq-detect IRQs are not modelled in the sim (lock time before / after cannot be measured there).
  - Needs from the unit (HDMI, unit 3): lock time before / after, Timer2 tick loss (AwtoMs vs wall) across a lock, no re-lock loop.

## 1. What stock does

- Realtek SDK `SysMain.c main()`: `while(SysMainSytemPowerDetect())` runs every handler then `SysTimerHandler()`; no pacing in the loop [measured: source].
- Idle exists only for power saving / off: `_SYSTEM_LOW_POWER_IDLE_SUPPORT` -> `SysMachineHandler` calls `SysPowerIdleProc()` when status is SAVING or OFF and no DDC/CI command runs: Timer2 count set to 100 ms (reload stays 1 ms), `PCON |= 1`, then `ScalerTimerAddTimerCounter()` adds the elapsed ticks [measured: `SysPower.c:697`, `SysJudge.c:733`].
- RL6449 `_FW_SYSTEM_LOW_POWER_IDLE_SUPPORT = _OFF` (RL6463 / RL6369: `_ON`). Stock RL6449 never idles; NORMAL state free-runs on every chip [measured: `RL6449_Gen_Option.h:658`].
- Dahua firmware (banks 0-6): no `orl PCON,#1` / `mov PCON,#1/#3/#2` byte pattern [measured: byte scan `/vendors/realtek/analysis/banks`, other encodings not excluded]. Loop rate of the Dahua image: not measured.
- Our free-running rate: 87.7 MHz builds 120-586 passes/s by state; 350.8 MHz unit ~1057/s (Dan); sim idle ACTIVE 2323/s [measured, `docs/speed-bench.tsv`, below].
- DW8051 idle [databook v3.2a 3-54..3-56]: `PCON.0` set -> CPU stops after that instruction; `clk` is NOT gated internally (unlike 8051); exit on any enabled interrupt, por_n or rst_in_n; RETI returns to the instruction after the IDL write. STOP exits only on por_n (unusable).
- Timer2 1 ms tick (`SysTimerIntProc2`, ~173 machine cycles, 2.0 us at 350.8 MHz) keeps running in idle, so idle is bounded to 1 ms [measured: `clock-scaling-review.md`].
- `SysTimerHandler` compares every valid event against the ms counter once per pass: event resolution = max(1 ms tick, pass period) [measured: source].

## 2. Deadlines of the pass consumers

| consumer | deadline | min passes/s | note |
|---|---|---|---|
| watchdog poke (per pass) | warn 200.1 ms, reset 585.9 ms | 5 | bound = longest pass (OSD draw ~150 ms), not the rate |
| DDC/CI engine (`AWTO_DDCCI_POLL`) | polled per pass; host waits 40 ms+ [guess: DDC/CI spec] | 25 | EXINT1 sets the wake flag: latency = one pass, not the period |
| key sample (`AWTO_KEY_SAMPLE_MS` 10) + debounce 2 samples, combo 80 ms | 10 ms | 100 | **binding at idle**: sample interval = ceil to the period (4 ms -> 12 ms, 8 ms -> 16 ms) |
| source / port scan, system machine, panel tick | timer events 1 ms ticks, +-10 % on class A waits [`delay-audit.md`] | 100 for 10 ms events | lateness <= period; fix = wake at the earliest event (below) |
| DP / HDMI link | ISR (EXINT0), no pass | 0 | only state steps run per pass |
| OSD / console draw, NVRAM flush | long passes by design | none | work, not a deadline |
| savers (Scope 2 / Asteroids / Pac-Man) | 25 fps target = >= 25 draw passes/s + draw time | 25 x passes per frame (15 / 18 / 10) | pacing must be off while a saver draws (work-pending flag) |
| sync log / monitor | windows of 1 s / 10 s | 1 | not binding |

- Binding deadline in idle ACTIVE: key sampling (100/s). Everything else needs <= 25/s. 4 ms (250/s) keeps the key rate within 2.5 passes per sample; 120/s (8 ms) stretches the sample to 16 ms [guess: 60 % slower keys].
- Binding with a saver running: passes per frame x fps; the saver is work, so it keeps `busy` and the loop free-runs.

## 3. Design

Sleep gate = "work pending" flag + tick. `AwtoLoopPace()` at the end of every pass (`SysMain.c`):
- wait until `AWTO_LOOP_PACING` ms since the previous pass, or `d_isr_g_bAwtoWake` (set by EXINT0, EXINT1, Timer0 ISRs);
- wait = `PCON |= 1` in a loop; every IRQ (Timer2 at the latest, 1 ms) re-checks.
- Lost wakeup: an ISR setting the flag between the check and the IDL write is seen at the next IRQ (<= 1 ms). The classic EA-off trick does not work on the 8051 (CPU halted, cannot run `EA = 1`); bounded 1 ms is the fix [databook: wake needs an enabled interrupt, EA semantics not stated: [guess]].
- Watchdog still poked once per pass (`AwtoDiagMainPass`); sleep cannot starve it (<= period).
- Wake sources today: EXINT0 (DP AUX, TMDS, CEC), EXINT1 (DDC/CI, debug slave), Timer0 events. Key ADC, scan state machines: polled (no ISR) -> wait for the period. Work-pending hook (`AWTO_LOOP_BUSY()`, NOT in the prototype): saver draw, OSD draw in progress, NVRAM flush, console redraw, panel sequence with an event due -> skip the idle.
- Refinement (not built): wake at min(period, earliest timer-event deadline) so events keep 1 ms resolution.

| option | rate | CPU duty | latency added | savers | code / XDATA | risk |
|---|---|---|---|---|---|---|
| (c) status quo | 2323/s sim, ~1057/s unit | 100 % | 0 | as today | 0 | none |
| (a) tick-paced + wake flag, 4 ms | 250/s | 14.5 % (core idle 85.5 %) | key sample +2 ms, event <= 4 ms, DDC/CI 0 (ISR wake) | need busy hook | 79 B code, +8 B XDATA (`g_stAwtoHead` 6 B + 2) | lost wakeup <= 1 ms |
| (a) 8 ms (120/s, Dan) | 125/s | 8.2 % | key sample +6 ms, event <= 8 ms | same | same | harness breaks (below) |
| (b) fixed rate, no flag | = (a) without early wake | = (a) | DDC/CI +period | same | smaller | DDC/CI latency up to a period: rejected |

[measured: sim, 350.8 MHz default clock, ACTIVE 1080p60, 3 s window after 2 s settle, `scripts/loop_pacing_sim.py`, dw8051 core with exact idle].

| image | passes/s | CPU duty | firmware sleep (1 s window) | worst busy pass | instr per 3 s | sim / host speed |
|---|---|---|---|---|---|---|
| lp0 free run | 2323 | 100 % | n/a | n/a | 38.4 M | 5.8 |
| lp4 (4 ms) | 249.5 | 14.5 % | 87.3 % (busy 12.7 %) | 0.69 ms | 6.5 M | 34.3 |
| lp8 (8 ms) | 125.0 | 8.2 % | 92.9 % (busy 7.1 %) | 0.69 ms | 4.1 M | 56.6 |

- Firmware sleep includes ISR time inside the wait (+1.1 point vs the core's exact idle); worst pass is idle ACTIVE only (no OSD draw, no saver).
- Power: DW8051 does not gate `clk` in idle; the saving is switching in the CPU core and, larger [guess], the SPI flash fetch / cache fills that stop with the CPU. Not measured; needs the unit power meter (`docs/power-levels.md`).
- Gates at the default clock, lp4 (`fw_gates --only boot,isr,h1080,h2160,menu,ddc,keys,wdt,sync,wake,panel,sysm,htime,crash,delays`): all PASS except `delays` (same FAIL on lp0: pre-existing) and, in the first run only, `sync`.
  - `sync` first run: console already auto-closed (3 s timer) at the check; `SimBus.wait` runs 200 k instr chunks = up to 100 ms fw when paced (16 ms free-run): harness overshoot [guess]; second build PASS.
- Gates lp8: `sysm` 13 failed (ring overwritten: it reads after an instruction budget that is 6x more fw time), `wake` (crash record decode None), `delays` (pre-existing): harness assumes the free-run rate [guess]. Needs time-based waits in `sync_sim` / `sysm_sim` / `wake_sim` before 8 ms is judged.
- Savers not run: the prototype has no busy hook; fps would fall to passes/s.

## 4. Sim impact (exact)

- Idle is modelled in `scripts/mcs51_core.c` (dw8051 only): `PCON.0` write -> loop: accepted IRQ? else advance clk to the next timer deadline (`tnext`, cap 65536 clk) -> nothing is skipped, timers and WDT see real time; `p.idle_clk`, `p.nidle` public.
- Cost-free for existing images (they never write PCON.IDL). Not cross-checked against ucsim (8052 mode has no idle).
- Free-run firmware cannot skip exactly (the loop is code). Equivalent estimate from the paced images: 85 % of idle-ACTIVE instructions are spin passes (38.4 M -> 6.5 M per 3 s at 4 ms); gate sim speed in idle ACTIVE up to 5.9x (4 ms) / 9.8x (8 ms). Gates dominated by real work (OSD draw, savers, NVRAM) gain nothing.

## 5. ISR diet (Dan: do less in interrupts)

Inventory (`SysInt.c`, `SysTimer.c`, `fw/diag/dbgisr.c`; cycles [measured: `clock-scaling-review.md`, `delays.md`] or [guess]):

| ISR | does | cost | must be ISR | can defer to a pass via event flag |
|---|---|---|---|---|
| EXINT0 DP AUX judge (`DP_INT.c:61`) | manual-mode defer, flag clear | entry 5.5-10.7 us + ~3 line fills | yes: AUX reply deadline 300 us (spec), ~400 us source timeout | no |
| EXINT0 DP training (`DPRx1_INT_SeptPhy.c:2030`, TP1/TP2 check, `Tp1SetPhy` 260 us, `Tp2SetPhy` 710 us, 85/150/300 us waits) | CR / EQ lock, lane status 0x202-0x204 | up to ~1 ms | yes: source reads lane status 100 us (CR) / 400 us (EQ) after the TP write | PHY tuning beyond the status write: no |
| EXINT0 DP sink status, 0x600 power, HDCP KSV, MST auto switch, audio freq, VB-ID | state flags, DPCD copies | us-scale each | status write: yes | KSV fifo, MST switch, audio, hot-plug events: yes |
| EXINT0 TMDS `SetPhy_EXINT0` / FLD | PHY / CDR set-up | **5545 us per call** (blind steps) | no hard us deadline [guess] | yes: biggest diet item; also causes Timer2 tick loss >= ~1 ms (#197) |
| EXINT0 CEC | RX frame into struct | ~300 instr / frame | yes (bit timing) | decode already in a pass |
| EXINT1 DDC/CI + debug slave (`dbgisr.c`) | I2C slave byte, 2 x 30 us tail, SDK DDC detect 300 us debounce | tens of us per byte | byte handling: yes | DDC/CI command execution: already in a pass |
| Timer2 | 1 ms counter, flag | 173 mc = 2.0 us at 350.8 | yes | no |
| Timer0 | `AwtoT0EvIsr`: WD-event table, 1 ms | us-scale | yes | no |
| Timer1, serial | empty (instant event / UART off) | entry only | n/a | could be unvectored |
| WDT int2 | warning capture, sof_rst | rare | yes | no |

- Diet effect on speed and memory: the worst ISR path is the DP training path through `SysEXINT0`: 32 B of stack; `fw_stack` total 100 B of 128, margin 11 B [measured: `cec.md`, `saver-code-placement.md`]. A thin ISR (flag + status write) would need ~12-15 B [guess], freeing ~17-20 B, margin ~30 B. Overlay / `__data` saving not quantified.
- Removing the 5.5 ms TMDS PHY block from EXINT0 removes the longest tick-loss source (#197) and the longest stretch with EA effectively off for lower priority work.
- Unit-2 DP lock bug (Dan: at 350.8 MHz the training ISR reads DPCD 0x100 / 0x202 before the host's AUX write landed; ring: stale 00/01/82/84 vs host 14/06). Not found in the repo issues by my search; evidence is Dan's.
  - Moving the DPCD config read to the main loop is NOT the fix: the status must be in place within CR 100 us / EQ 400 us of the TP write; a pass is 0.4-1 ms free-run, 4-8 ms paced. Holding the source with AUX defer is bounded (source retries defer a limited number of times [guess: spec 7]) and shorter than one paced pass.
  - Same exposure as S2 in `clock-scaling-review.md` (flag read then pointer read closer than the AUX clock domain sync): fix inside the ISR = re-read until the AUX write-done flag / value is stable (`T4: DELAY_XUS(1)` or re-read of the IRQ event). Independent of pacing: idle wake adds only the databook IRQ entry (5-13 instr cycles).
  - Flag-released loop + diet is the right frame for everything EXCEPT this: the AUX reply and the lane-status write stay in hardware / ISR.

## 6. Headroom instrumentation

Prototype (`fw/diag/diag.c`, only with `AWTO_LOOP_PACING > 0`): `g_stAwtoHead` (6 B XDATA, last 1 s window), read by symbol over debug slave 0x35.
- Time base `AwtoQ8Now()` = Timer2 ms tick + TH2:TL2 phase / reload, 1/256 ms; read-only, never wakes the CPU or touches a timer.
- busy = previous pace exit -> this pace entry; sleep = entry -> exit (includes ISR time inside the wait).
- Fields: `usPasses`, `usSleepPm` (per mille), `usWorstQ4` (worst busy pass, 1/16 ms). Sim read-out: `scripts/loop_pacing_sim.py` (`headroom (last 1 s): 250 passes, sleep 87.3 %, worst busy pass 0.69 ms`).
- Not built (proposal, all read the same 3 fields):
  - Monitor row 3 (`docs/monitoring.md`): `monitor: main loop 250 passes/s, busy 12.7 %, worst pass 0.7 ms, longest watchdog gap 18ms` (new arg fields in `AWTO_MON_EV_LOOP`, decoders `mon_decode.py`, `sync_log.py`, `console.c AwtoPutMon`).
  - Diag block (`docs/diag-block.md`): +4 B after `usLoopRate`: sleep per mille, worst Q4 (layout version bump, `rtd_diag.decode`).
  - `./dev.py health` row `headroom`: PASS if busy < 50 % idle ACTIVE and worst pass < 10 ms (idle numbers above: 12.7 % / 0.69 ms).
  - Console title row (CPU / PLL / SPI line): append ` busy 13 %`; position decided with the console layout owner.
- Regression metric (measure-speed-every-change): `busy %` and `worst pass ms` in idle ACTIVE and in each saver, new columns in `docs/speed-bench.tsv`; a change that raises busy beyond +10 % relative or worst pass beyond the pass period fails. Meaningful only on a paced image; on a free-running image the existing `cycles_pass` column stays the metric.

## 7. Recommendation

- Adopt (a): tick-paced loop with a wake flag and a busy hook, 4 ms (250/s) as the first target (key sampling is the binding deadline; 120/s needs key sampling off the pass first). Add the earliest-event wake so timer events keep 1 ms resolution, and wake on key ADC activity if it ever gets an ISR.
- Do the ISR diet in order: TMDS PHY block, DP non-status work, then the DPCD race fix inside the ISR.
- Default 4 ms decided (Dan 2026-11-19). Still open: 8 ms vs 4 ms power measurement, savers busy-hook design, time-based `SimBus.wait` in the harness.
- Files: `fw/diag/diag.c`, `fw/sdk/Kernel/System/Code/{SysMain,SysInt,SysTimer}.c`, `fw/sdk/Project/Header/RL6449_Project.h`, `scripts/mcs51_core.c`, `scripts/fastmachine.py`, `scripts/loop_pacing_sim.py`. Build: `./dev.py build` (default 4), `-D AWTO_LOOP_PACING=0` free-run.
