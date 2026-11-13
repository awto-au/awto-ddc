# Watchdog, crash canary and boot reason (#131, #138, #29)

- Firmware: `awto-ddc-wdt2` branch `wb-p14ui-wdt2` (from wb-p14ui 1c82a51). Files: `fw/diag/wdt.c`, `fw/timer/t0ev.c`, `fw/osd/console.c`,
  `crt_rtd_startup.asm`, `fw/awto/wdt/rules.py`, `RL6449_Project.h` (`StAwtoWdt`, `AWTO_WDT_*`).
- Host: `scripts/wdt_test.py` (sim + unit 2 runner), `wdt_sim.py` (boot gaps, Timer0 events, loop rate), `crash_sim_test.py`, `poke_loops.py`
  (static loop check, table `re/poke_loops.tsv`), `rtd_crash.py` (record v2, `--snap`), `sync_log.py` (boot reason line), `fw_sim.py` `ChipReset`.
- Superseded design (#131 software watchdog in the 1 ms tick, record v1): git history of this file.

## Hardware (regdb `re/regdb/RTD2795T-CG.tsv.gz`, unit 2 2026-11-11 wb-p14ui-wd4)

| reg | bits | fact |
|---|---|---|
| FFEA | 7 wdt_en, 6 clr_wdt (strobe: clear all counters, latch them into FFAA-FFAD), 5 / 4 halt on SPI flash / burst write, 2:0 N-1 | reset 0x80 (on, N = 1) |
| FFE9 [7], FF3A [6] | wdt_en_3, wdt_en_2 | ORed with FFEA[7]; reset 1; unit 2 FFE9 0x82, FF3A 0x50: never cleared by our code (whole-byte writes checked: all RMW) |
| FFEB | 7 flag (W1C), 4 timer mode, 3 latch, 2 IRQ enable, 1 / 0 bypass CNT2 / CNT3 | |
| FFAE / FFB0[7:4] | threshold, compared with CNT3 | |
| FFC4 [5:3] | wdt_irq_pri: 2 = int2 (EXINT2, vector 43h, EIE.0 / EXIF.4 / EIP.0) | |

- Chain: CNT2 (2048 XTAL) -> CNT3 12 bit (143.0 us, wraps 585.9 ms) -> CNT1. Reset when CNT1 reaches N.
### One counter, two outputs (unit 2, 2026-11-11, image wb-p14ui-wd4, probes 0x49 / 0x4F: threshold 36.6 ms, N = 1, no pokes)

- Reset output: CNT1 reaching N resets the chip in **both** modes. Normal mode: reset at 605 ms (586 expected); timer mode: reset too.
- Compare output, timer mode only: count >= threshold sets the flag and raises the IRQ. 0x4F = TIMER-MODE | IRQ | RESET (0x0D);
  normal mode never raises it, 0x49 = RESET only (0x08).
- Realtek's use: its event scheduler moved the threshold per event, so it had to keep clearing the counter (WD ISR + the tick's
  'Prevent INT Lock Reset' clear) to keep the always-live reset away.
- Our use: a fixed threshold (the warning), pokes only from main-loop progress and bounded loops, events on Timer0.
- So the build uses timer mode: `AWTO_WDT_MODE = AWTO_WDT_TIMER_IRQ` (default; `AWTO_WDT_NORMAL_IRQ` stays selectable).
- fw_sim `ChipReset` models exactly this: reset at CNT1 = N in both modes, compare flag / IRQ in timer mode only.
- No reset-cause register: DW8051 has no watchdog and no POR / WTRF flag (databook v3.2a; SFRs reset on por_n and rst_in_n). P0_01[6]
  reset_chk reads 0 after every reset on unit 2 (#131): not used for cold / warm.
- MX25L8006E (`/vendors/macronix/MX25L8006E_v1.6.pdf` p. 49): tSE 4 KB sector 200 ms max, tPP 3 ms, tW (WRSR) 40 ms. The CPU halts
  during a flash command (SDK comment); the WDT keeps counting (FFEA[5] off: "stop by SPI-FLASH access" would also stop it on code fetch).

## Design: one hardware watchdog

- Poke = FFEA[6] (`AWTO_WDT_POKE`), only:
  - once per main-loop pass (`AWTO_WDT_PASS` in `AwtoDiagMainPass`);
  - inside bounded loops (`AWTO_WDT_FEED`): `ScalerTimerDelayXms`, `ScalerTimerPollingFlagProc`, `ScalerTimerWaitForEvent`, `AwtoMsgWait`,
    the SDK flash `ScalerFlashWREN` / `ScalerFlashWRDis` (were the SDK's own unconditional pokes).
- Rule (Dan): only the main loop is unbounded; any loop around a poking wait must be bounded (audit below, `poke_loops.py`). No gating.
- The 1 ms tick does no watchdog work: #131 check, the SDK latch and its CNT1 > 4 'Prevent INT Lock Reset' clear removed.
- Every FFEA write in the link (asm check): pokes above, `ScalerMcuInitial` (boot clear + enable), `ScalerTimerWDInitial`, `AwtoWdtProbe`.
- `ScalerTimerWDInitial`: timer mode, threshold 0xC00, IRQ on int2 at high priority (PX2), N = 2.
- Warning (`SysTimerWDIntProc` -> `AwtoWdtIrq`): a match with CNT1 < N-1 sets `AWTO_WDT_P_EARLY` and returns; at CNT1 = N-1: capture the
  stacked PC, SP, regs, bank, stage, pass age, seal, then sof_rst. No poke.
  - sof_rst right away is safe: the record is sealed before it, XDATA 0xF6B0 survives it (unit 2, #131), and it is the reset the host's
    ISP 0xEE does. If it did nothing, CNT1 = N resets 146 ms later.

### Arithmetic (N, threshold)

| point | from the last poke | |
|---|---|---|
| early match (CNT1 0, CNT3 = 0xC00) | 3072 x 0.143 = 439.4 ms | IRQ, marker only |
| warning + capture (CNT1 1, CNT3 = 0xC00) | 585.9 + 439.4 = 1025.3 ms | AWTO_WDT_THR, N-1 |
| hardware reset (CNT1 = 2) | 2 x 585.9 = 1171.8 ms | AWTO_WDT_N; covers EA off / high-priority hangs |

- Longest legit gap must be < 1025.3 / 1.25 = 820 ms. Measured: sim 311 ms (boot + workload + NVRAM save), unit 2 188 ms (wd4 baseline).
  Plus a sector erase halt 200 ms + WRSR 40 ms (not in the sim) -> 551 ms worst estimate.
- Warning -> reset margin 146 ms (capture takes < 1 ms). Today's old backstop was 4.69 s (N = 8).

## Boot (task 1)

- The SDK's boot 'disable' (`ScalerMcuBootInitial`, FFEA[7] only) is not linked (`_FLASH_PARTITION_NONE`) and would be a no-op (FFE9[7] /
  FF3A[6]); the line is removed by a rule anyway.
- `crt_rtd_startup`: XFR on, reset snapshot, then FFEA |= 0xC7 (clear, N = 8) at once. `ScalerMcuInitial` clears again, then
  `ScalerTimerWDInitial` sets the run-time mode.
- Sim (`wdt_sim.py boot`, wd5): clears at 0 (startup), 39.6 ms (ScalerMcuInitial), 51 ms (WDInitial), then pokes; worst gap before the first
  main-loop pass 39.6 ms of the 4687 ms period in force. Times before Timer2 are the ucsim 12-clock model (DW8051: 4): upper bounds.

## Timer0 event scheduler (task 2, `fw/timer/t0ev.c`)

- The SDK's WD-timer jobs (DP Rx1 rebuild PHY 30 ms, HDMI read-request retry D2 / D3 10 ms; HDCP2 SKE and Type-C PD compiled out) on Timer0.
  Same function names (`ScalerTimerWDActivateTimerEvent_EXINT0`, `ScalerTimerWDCancelTimerEvent[_EXINT0]`): no SDK call site changes.
- One ms counter per event ID; re-arm restarts; Timer0 ticks 1 ms only while one is pending. Reload = RCAP2: Timer0 and Timer2 count the same
  MCU clock /12 (SDK `_TIMER01_TEMP_COUNT_*` = `_TIMER2_COUNT_*`); the ISR adds the counts since the overflow; more than a tick late (a long
  EXINT0 handler) -> the next tick at once.
- Arm: Timer0 running -> +1 tick when the current tick is past half (+-0.5 ms); preempting the Timer0 ISR (EXINT0 high in power saving) ->
  +1 if the ISR has yet to decrement that ID (`s_ucAwtoT0Pos`).
- Clock switch: `ScalerTimerSetTimerCount` ends with `AwtoT0EvClock`: the rest of the current tick scaled to the new reload.
- Priority: Timer0 low (PT0 = 0), as the WD IRQ was; handlers run with interrupts on.

| shared data | contexts | guard |
|---|---|---|
| `s_pusAwtoT0Ms[]` | Timer0 ISR, EXINT0 (arm / cancel), main (cancel, tests) | Timer0: EA off per element; main: `__critical`; EXINT0: Timer0 cannot preempt it at the same / lower level |
| TR0 / TH0 / TL0, `s_usAwtoT0Rl`, `s_ucAwtoT0Pos` | Timer0 ISR, EXINT0 (start), main (rescale) | ISR reload and idle check under EA off; main under `__critical` |
| `g_stAwtoWdt` live bytes | main pass, pokes, WDT IRQ | single bytes; the capture runs with EA off and never returns |

- EA-off windows are a few instructions (no spin inside): no low-priority path can hold off a higher one.

## Interrupt model (DW8051 databook v3.2a pp. 3-43..3-48)

- Two levels (IP / EIP); same level by natural order EX0, T0, EX1, T1, serial 0, T2, serial 1, int2..int5, wdti; only a higher level preempts;
  after RETI or an IE / IP / EIE / EIP write one more instruction runs before an IRQ.
- fw_sim fast core (`mcs51_core.c`): all of the above for EX0..T2 + int2 (43h); serial 1, int3..5, wdti, pfi not modelled (unused). ucsim
  core: no DW8051 extended interrupts (no 43h): WDT warning tests need `AWTO_SIM_CORE=fast`. SFR reset values are ucsim's (not DW8051's
  EICON 0x40, EIE / EIP 0xE0, IP 0x80): kept for lockstep with ucsim.
- fw_sim `ChipReset` hardware WDT: per unit 2: reset at CNT1 = N in both modes; threshold flag / IRQ in timer mode only; clr_wdt latch.
  ASSUMED: CNT1 counts CNT3 wraps in timer mode as in normal mode.
- Power-saving IP = 0x81: EXINT0 high. A stuck EXINT0 is then not preempted by the WDT IRQ (same level): hardware reset at 1171.8 ms, no
  capture (sim: prio_wdt_preempts).

## Bounded-loop audit (task 4)

- `poke_loops.py TREE`: 66 loops reach a poking helper (linked call graph): 43 bounded by form, 1 main, 22 read by hand (below), 0 unbounded.
- Waits over ~0.5 s and how they poke (wake: `wake_sim` cable unplug / plug wake 20 ms after the edge, bound 35 ms): panel T3 550 ms, HDMI HPD low 500 ms, panel T6 1100 ms (all `ScalerTimerDelayXms`: poke per ms);
  `ScalerMDomainControlDBApply` up to pData[15] frames of `ScalerTimerWaitForEvent` (90 ms bound each, poke per ms); DDR2 PLL lock poll
  (`PollingFlagProc`, 40 ms); DPTx link sequence (5 retries); NVRAM save: `ScalerFlashWrite` page loop pokes in WREN / WRDis per page,
  sector erase is one CPU halt <= 200 ms (no poke possible; inside the margin above).

| site | loop | bound | verdict |
|---|---|---|---|
| RL6449_Series_DPRx1.c:3662 / 3963 / 4047 `ScalerDpRx1PhyCTS` | while CTS auto mode / error report / CTS flag | none: ends when the DP source ends the PHY CTS test (DPCD 0x270) | **unbounded, pokes (DelayXms)**: bug class; lab-only mode (`_AWTO_DP_PHYCTS`), decision for Dan |
| ScalerCommonDebug.c:656 `ScalerDebug` | do while host halt (0x80) | none: until the host releases | unbounded; no poke inside -> WDT resets a host halt after 1.03 s (same as #131) |
| ScalerCommonDebug.c:194 `ScalerDebugMessage` | host wait | `AwtoMsgWait` host-silence timeout (#56) | bounded |
| RL6449_Series_DisplayDPTx.c:221 | DPTx link sequence | 5 retries | bounded |
| ScalerDisplayDPTx.c:652 | DPTx training state machine | TP1 / TP2 internal retry counts -> FAIL | bounded [likely] |
| RL6449_Series_MDomain.c:106 / 135 | pData[15]-- frames | frame count byte | bounded |
| ScalerCommonDPRx1.c:300 / 731 | lane count step-down, scramble seed toggle | 4 lanes; 2 seeds | bounded [likely] |
| ScalerAudio.c:768 | DVC mute | PDATA_WORD(1) < limit | bounded |
| ScalerIDomain.c:222, UserCommonAdjust.c:962 | V delay step | ucSettingCounter / ucTimeoutCounter | bounded |
| ScalerMemory.c:320 / 361 / 411 | IVS2DVS fine tune | remaining delay / step limit | bounded |
| RTD2014OsdFontProp.c:1290 / 1373, RTDFactoryFunction.c:1994 | string to the OSD | string terminator (code tables) | bounded |
| RTD2014Key.c:1164 `AwtoKeyPoll` | key queue drain | queue size | bounded |
| SysMain.c:1295 `main` | inner power-detect loop | main loop | main |

- No unbounded wait-forever other than the main loop pokes, except the PHY CTS loops (reported).

## Boot reason and early log (task 5)

- First power-on sync line (`AwtoBootReason`, canary only; one function to swap in a hardware flag if the snapshot finds one):
  `boot: cold power-up` (no valid record) | `boot: watchdog bite, STALL[ TEST], PC bb:pppp fn+off` | `boot: hardware watchdog reset, no capture
  (an early warning IRQ came)` | `boot: warm reset, no capture (host ISP 0xEE, or a hardware watchdog reset with interrupts off)` |
  `boot: watchdog probe reset`. A host-cleared record boots as cold.
- Then stage 1..8, MCU init, Timer2 start, watchdog run-time lines. Times = ms since reset: before Timer2 the WDT counter (cleared by the
  first instruction; 143 us counts on the crystal), carried over the ScalerMcuInitial clear; at the Timer2 start those lines move to Timer2
  time and the episode's T0 becomes -(ms since reset at Timer2 0).
- XDATA: ring 24 -> 32 entries +64 B, time base +4 B, Timer0 position +1 B, snapshot 20 B (linker XDATA end 0xF6B0 -> 0xF69C).
- Power on from soft-off (POWER key / DDC/CI D6) and wake lines were already there (`power key on, Dn`, `Dn cable plugged in: wake`, ...).
- Reset-vector snapshot (`crt_rtd_startup`, 20 B at 0xF69C, `rtd_crash.py --snap`): 'RS', EICON PCON EXIF CKCON IE EIE IP EIP, FFEA FFEB
  FFAA-FFAD FFE0 FFED FFEE, P0_01. A byte that differs between cold / WDT / ISP resets on unit 2 is a reset-cause candidate.

## Record v2 (`g_stAwtoWdt`, 32 B at XDATA 0xF6B0, bytes only)

| off | field |
|---|---|
| 0-2 | 'W' 'D' 2 |
| 3 | cause: 1 STALL; 0x40 timer-mode build; 0x80 test hang |
| 4 / 5 | bites / other warm resets |
| 6-16 | PC hi lo, bank, SP, PSW, ACC, B, DPH, DPL, stack top hi lo |
| 17-22 | stage, mode, heartbeat, uptime ms |
| 23-24 | ms since the last main-loop pass at the warning |
| 25 | check (0xA5 ^ bytes 0..24) |
| 26 | boot: 01 HW-WDT, 02 bite pending, 04 test, 08 not shown, 10 warm, 20 cold, 40 after bite, 80 after probe |
| 27-28 | g_usTimerCounter at the last pass (live) |
| 29 / 30 | max pass x32 ms / max poke gap x4.58 ms (clr_wdt latch FFAC) this boot |
| 31 | probe: 01 timer mode, 02 armed, 04 IRQ, 08 reset, 10 no reset in 1.5 s, 20 EICON WDTI, 40 early match since the last pass |

## Test commands

- 0x4C spin (warning capture), 0x4E spin with EA off (hardware reset, no capture), 0x4D gone (loop around a poking wait = audit rule).
- 0x49 / 0x4F probe normal / timer mode: threshold 36.6 ms, N = 1, no pokes for 1.5 s.
- Timer0: 0x2A rebuild 30, 0x2B / 0x2C RR D2 / D3 10, 0x2D two, 0x2E / 0x2F across a forced PS reload, 0x5A / 0x5B at the PS reload, 0x5C three
  out of order + cancel, 0x24 stuck Timer0 handler; EXINT0 hook 0x5D arm once, 0x5E 2-3 ms spin once, 0x5F stuck, 0x25 off.

## Measured (sim, fast core, 2026-11-11; image wb-p14ui-wd5 unless stated)

- `wdt_test.py --sim`: all cases PASS (list: `wdt_test.py --list`). Warning capture 1025 ms after the last poke, PC `AwtoWdtHang+0x10`;
  EA off: hardware reset 1171.8 ms, no capture, `boot: warm reset, no capture`.
- Timer0 events: 10 ms -> 10.03-10.05, 30 ms -> 30.07; at the PS reload 9.73 / 29.86; across a PS reload and back 9.85 / 31.05; arm from
  EXINT0 alone / during a Timer0 ISR / with TF0 pending / IP 0x81 preempting: 10.05 / 10.02 / 10.53 / 9.04 ms; 2-3 ms EXINT0 spin -> 13.04 ms.
- Timer2 ISR: 219 -> 173 machine cycles mean (wd0 -> wd5). Timer0 ISR 629 cycles a tick (893 on a fire tick), only while an event is pending.
  Main pass bookkeeping + poke: `AwtoDiagMainPass` 105 -> 219 cycles.
- Loop rate (`wdt_sim.py rate`, ACTIVE 1080p60): 2617 -> 2586 passes/s.
- Code +1498 B (wd0 -> wd6, map_size_diff); XDATA free 149 -> 102 B (wd5).
- Unit 2 (wd4): baseline 10 s no reset, max pass 544 ms, max poke gap 188 ms; probes as above.

## NVRAM save bite (#150, unit 2 2026-11-11, wb-p14ui-wd5)

- Record: STALL, PC C:32B2 SysEXINT1+0x5e (the warning interrupted the debug-slave ISR), stack top OsdPropPutString+0xb1a, up 24305 ms,
  stage 8, mode 3, pass age 1028 ms, during the baseline NVRAM save (test cmd 0x29).
- SPI-flash common instructions (FF60 start bit: erase, program, WRSR) halt the MCU for the whole op (SDK `ScalerFlashErasePage`: "8051
  will halt"); no code, no pokes, no interrupts; with FFEA[5] off the WDT counted the halts. Datasheet max: tSE 200 ms, tW 40 ms, tPP 3 ms.
- wb-p14ui-wd6: FFEA[5] sf_hlt_wdt_en on (`AWTO_WDT_HALT_FLASH`, default 1); pokes added in `ScalerFlashRead` (per call), `ScalerFlashWrite`
  (per sector part) and `OsdPropPutString` (per character); `poke_loops.py` lists the 6 functions that start a common instruction (halt rows).
- Unit 2 decides: 0x4C must still bite with bit 5 on (else bit 5 also stops the counter on code fetch: fall back to
  `-D AWTO_WDT_HALT_FLASH=0` = image wb-p14ui-wd6n, whose save lines then measure each halt).
- Sync lines after boot: `NVRAM save start / end`, `flash erase start / done`, `NVRAM page move`, each with WDT ms since the last poke.
- Live `g_ucAwtoPokeSite`: which poke site (AWTO_WDT_S_*, `rtd_crash.SITES`) ended the longest gap; console `POKE n MS AT s`.
- Sim: `FlashHalt` (fw_sim) adds the halt to the WDT model (typ, or datasheet max in wdt_test nvsave); wd6: 40 ops 1600 ms, 0 counted.
- Unit 2 wd6 (2026-11-11): 0x4C still bites with bit 5 on (first failed 0x35 read 1056 ms after the cmd); 5 saves, no bite, max
  poke gap 133 ms; ea_off hardware-only reset, warm 1 -> 2.

### wd7 threshold (2026-11-12, from unit 2 wb-p14ui-wd6 stress, 2026-11-11)

- Measurement: one `wdt_test --unit 2 --cases stress` run (5 saves, menu open / close, D3 no cable, D2, D1 without a DP source, D2):
  max poke gap 133 ms, ended by the main pass. **No DP traffic** (host DP-1 output off): a DP stress run is still owed.
- Warning = 1.25 x 133 = 166.25 ms -> threshold 0x48B = 1163 CNT3 counts x 143.0 us = 166.4 ms (the next count up). N = 1: reset
  585.9 ms after the last poke; warning -> reset margin 419.5 ms (>= 100 ms for the capture).
- 2x rule: the poking waits poke every ms (DelayXms, PollingFlagProc, WaitForEvent, HPD poll, T3 wait) or per call / character;
  the longest single step between pokes inside them is ~1 ms, far under 166.4 / 2 = 83 ms. Not below 150 ms.
- With N = 1 the first threshold match is the warning: no early match, so no `AWTO_WDT_P_EARLY` hardware-WDT evidence.
- Sim before wd7 found two waits without pokes, now poked per ms: the eDP HPD poll (`ScalerDisplayDPTxPollingHotPlug`, panel T2,
  bound 250 ms: the sim's 255 ms gap, HPD not modelled) and `AwtoDiagPanelT3Wait`. Sim max poke gap after: 92 ms.
- wd7 sim (gates): 0x4C capture 166.2 ms, 0x4E hardware reset 585.9 ms, probes as unit 2.

### wd8 threshold: power saving (2026-11-12, from unit 2 wb-p14ui-wd7, 2026-11-11)

- wd7 on unit 2: wdt_test 5/5 PASS (stall capture 173 ms, PC AwtoWdtHang+0x10; ea_off hardware reset 700 ms), but host_sleep
  measured a max poke gap of **160 ms** in power saving (ended by the main pass) against the 166.4 ms warning.
- In power saving the MCU runs on IOSC with the PS flash divider: a main pass without a poking wait is long in real time. The sim
  does not show it (PS passes there <= 37 ms: no SPI-flash fetch latency, sim max PS poke gap 37 ms), so the long stretch is not
  identified yet. wd8 records the site that started the longest gap too (`g_ucAwtoPokeFrom`, `wdt_test` "from ...").
  A loop-profile build (`-D _AWTO_LOOP_PROF=_ON`, `scripts/loop_prof.py`) in power saving gives the per-handler pass cost.
- wd8: warning = 1.25 x 160 = 200 ms -> threshold 0x577 = 1399 counts = 200.1 ms; N = 1 (reset 585.9 ms, margin 385.8 ms).
- stress now holds the D3 (no cable) step into power saving (up to 29 s), so its max gap covers the power-saving passes.

### SDK wake vs our wake poll (#150, #144)

- host_sleep on wd7: no wake line: the host's DPMS on brings TMDS back; our poll has no TMDS-clock trigger (cable / EDID read /
  AUX / DPCD 600h only) and the SDK's own power-saving source detect woke the monitor ('wake on D2' only).
- wd8: such a wake logs 'Dn wake by the SDK source detect, not our poll (poll state ...)': cable, EDID latches, AUX, DPCD 600h
  and the number of wake polls since power saving (`g_usAwtoPsPolls`, also read by host_sleep while in power saving).
- Sim (wd8, D2 source, forced power saving): woke after 905 ms, 'D1 wake by the SDK source detect, not our poll (poll state
  0x00C803: polls 200, cable 011, EDID 000, AUX 0, DPCD D0 0)': the poll ran, no trigger set.

### TMDS-clock wake and the PS poll period (tmds1, #144 q7, Dan 2026-11-12)

- Branch `wb-p14ui-tmds` (worktree `awto-ddc-tmds`), image `AWT26110002-wb-p14ui-tmds1-be`. Build: `AWTO_RTDFW_REPO=/mnt/2tb/git/awto-rtdfw-ui`
  `wb_build.py ... -D _AWTO_AUDIO_TEST` (the pinned clean ref lacks the ui font symbols; layout = `fw/bank_layout.tsv`, was wdt2 `tmp/layout_sync3.tsv`).
- Why the poll ran 3 times on unit 2 (wd8): the only wait in a power-saving pass was the SDK's TMDS PS predetect (`ScalerTMDSRx2/3TMDSPSPreDetect`:
  reset the freq detector, `ScalerTimerDelayXms(5)`, read, disable). Sim wd8: PS pass 24 k instr / 6 ms, 5 of them that wait; console redraws
  (`AwtoGpioPoll` 93 k instr every 500 ms, `AwtoKeyShow`) the other long passes. Unit 2 PS pass length itself not measured (host_sleep now reads it).
- tmds1:
  - SDK TMDS PS predetect without its reset / wait / disable: it reads `AwtoPsTmdsLive` (same criterion); the wake poll owns the detectors in PS.
  - Wake poll every `AWTO_PS_POLL_MS` 5 ms (rate | why: 200/s | the SDK's own 5 ms freq-measure wait = restart -> read interval; cable debounce 10 ms sampled 2x).
  - No console / key-panel redraws in power saving (panel off).
  - TMDS trigger: per HDMI port with a cable: live (E6[7] start, E6[6] done, E6[2] unstable 0, EF[6] stable latched; regdb HDMI_FREQDET_CTRL / ERROR_TH)
    -> wake `Dn wake by TMDS clock, about x MHz (IOSC reference)` (sync D7; count x 28 MHz IOSC / 1000 ref cycles, +-10 %); else stopped / unstable
    -> restart (SDK sequence). Once per port per sleep (`wake suppressed (TMDS clock, once per sleep)`, CF 06). Armed at PS entry (restart clears pre-PS latches).
  - Readouts: `g_usAwtoPsPolls`, `g_usAwtoPsGap` (longest poll-to-poll gap; the arm -> first poll pass is PS entry work, not counted); SDK-wake state bits 25:24 = TMDS live D3 D2.
- Sim (wake_sim, fast core, 2026-11-12, tmds1): PS pass 1.47..1.56 ms (no waits); poll 84 in 500 ms (5.95 ms), longest gap 6 ms (bound 10);
  TMDS on D2 -> wake line 15 ms (bound 22: clock up after a restart = 2 polls); D3 clock without a cable: no wake; repeat suppressed.
  Event -> wake line vs wd8: cable 16 / 22 ms (18 / 29), EDID 9 (13), AUX 6 (9), DPCD 7 (12).
- Unit 2 open: freq detector of the non-search port in PS (both PHYs keep the clock lane on: `P7B/P7C_1A = 0x80` at NORMAL_TO_PS), the real poll
  period (host_sleep `wake polls in PS`: host ms vs fw ms shows the PS Timer2 rate), which trigger fires first on host DPMS on.

### Sync ring in NO SIGNAL (#150)

- Unit 2 wd6, host output off: the ring filled with alternating 'D2 TMDS clock 0.0 MHz detected' / 'D2 signal lost' (every
  15-100 ms) and lost the reason and save lines.
- The lines follow `GET_SOURCE_PREDETECT` of the SDK's per-pass port detect (`AwtoSyncDetect`): the SDK's predetect really flips,
  the logger only reports it. Why the D2 TMDS predetect reads true with no clock (HDMI +5 V present, DPMS off) is not established:
  needs a trace of the TMDS clock-detect register on unit 2.
- wd7: a repeating pair is written once as 'the 2 lines above repeated N more times'; the boot reason has a pinned copy
  (`g_stAwtoSyncPin`, read first by `wdt_test` and `rtd_diag --sync`).
- Uptimes are 16-bit ms (wrap at 65.5 s): `wdt_test` compares them modulo 65536 (64779 -> 247 = +1004 ms, same boot).

### host_sleep case (unit only, approved autonomous test)

- Host outputs off (Mutter `PowerSaveMode` 3, checked on `/sys/class/drm/card1-HDMI-A-2/dpms`), test cmd 0x39 (#78 short levels:
  L3 = SDK power saving at 20 s) -> NOSIGNAL -> power saving (bound 29 s: 20 + 1 s judge + 2 s go-to-PS = 23 s x 1.25), host on:
  #144 wake line, ms to ACTIVE (bound 9 s), no bite, max poke gap. Host always woken (also on an exception / Ctrl-C), 0x36 restores
  the levels; the runner holds `gnome-session-inhibit --inhibit idle` for the case.
- Measured 2026-11-11 (wd6, by hand): host DPMS on -> unit 2 ACTIVE in 863 ms from NOSIGNAL (not from power saving).

## Sim notes

- fw_sim time dilation: a firmware RCAP2 write (and its matching TL2/TH2 load) is dilated at once (fastmachine): Timer0 reads RCAP2.
- An IP change inside EXINT0 (harness only) flips `ScalerTimerPollingFlagProc_EXINT0` to its g_usTimerCounter branch while Timer2
  cannot preempt: endless poll. The SDK changes IP in main context only; wdt_test restores IP outside interrupts.

## Needs hardware (unit 2, image wb-p14ui-wd5)

- 0x4C: warning capture in timer mode (link drop ~1025 ms + cmd latency; record STALL TEST, PC AwtoWdtHang, first line `boot: watchdog bite`).
- 0x4E: hardware reset ~1172 ms, warm + 1, `boot: warm reset, no capture`.
- Snapshot diffs cold / WDT / ISP; EICON WDTI bit in the probe; DP link training with the rebuild on Timer0.
