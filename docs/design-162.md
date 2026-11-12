# #162 design: one owner per resource (decided by Dan, 2026-11-12)

Input: `docs/sdk-model-inventory.md` (state machines, hooks, collisions C1-C16, transitions T1-T9), boot profile (#144, unit 2 fb4), SDK now our source in `fw/sdk` (`git diff sdk-import-3d38340 -- fw/sdk` = our edits).

## Principles (Dan)
- One code path per resource. Every other caller *requests*; only the owner drives the hardware.
- State machines first: each owner is a machine with named states; transitions are the only place hardware changes.
- No blocking waits in a transition (T1-T6, HPD, link, flash): a step arms a timer and returns; the main loop / Timer0 runs the next step.
- Logging only grows: each transition logs itself (`<owner>: <old> -> <new> (<why>)`), each request logs its outcome (`... requested (already on)`).

## Owners (recommended option in bold; letters = inventory §8)

| Resource | Owner (new) | Replaces | Option |
|---|---|---|---|
| Panel VDD / eDP-1 link / backlight / PWM | `PanelPowerAction` rewritten as a non-blocking machine: OFF → VDD (T1) → HPD (≤T2) → LINK → VIDEO → T3 → BL_ON, and back (T4, T5, T6) | early raw VDD, INITIAL `_BACKLIGHT_ON`, display-setting `_PANEL_ON`, ACTIVE `_BACKLIGHT_ON`, OSD-event BL on, L1 pin, L2 link, `AWTO_BL_OFF_OR_BLANK`, T3 sub | **A** |
| Output timing (free-run / frame-sync, DCLK) | SDK `SysModeSetFreeRun` + `ScalerMDomainControl` (unchanged) | — | keep |
| OSD (console, cards, selector, menu, GPIO page) | one OSD owner: screen stack + `show/hide/replace`; mode resets no longer call `OsdDispDisableOsd`; console survives input changes (output stays free-run) | m4-m6 redraw patches, `AwtoConLost`, `AwtoMenuForget`, `AwtoHoldBlocksDisable`, SDK OSD timers/hot-key menus | **A** |
| Power status + mode (OFF / NORMAL / SAVING; INITIAL … ACTIVE, NO SIGNAL, PS) | one machine of ours replacing SysPower + SysMode + SysJudge (decision 3); scaler functions are its actions | SDK SysPower/SysMode/SysJudge, direct target writes in fastsw / wake poll / testcmd, hold-judge sub, `AwtoSwPoll` mode polling | **A** |
| Input selection / KVM / search order / cache / fast path | one source model; `AwtoInputSelect` the only entry; #84 = invariant (no uncabled target) | fixed-port workarounds, selector fragments, deadport poll | **A** |
| Signal-loss hold (L1 backlight off / L2 link off / L3 PS) | decision 4 | | — |
| Power-saving wake | our poll is the only decider (SDK predetects removed); poll runs from a Timer0 event every 5 ms, not 14 main-loop sites; triggers: cable, EDID read, DPCD 600h / link training, TMDS clock (AUX logged only, #163) | SDK PS predetect paths, `AWTO_PS_POLL_SITE` x14 | **A** |
| NVRAM | SDK store behind the flush gate (#151, kept); boot-time writes through the gate; legacy `nvram.c` and inert rows removed | | **A** |
| Time | one 32-bit ms counter (Timer2 ISR) for all our code; SDK event table keeps its own | `AwtoSwNow/AwtoFastNow/AwtoSrcNow/AwtoSyncNow` | **A** |
| Log | one sync ring sized for a full cold boot × 1.25; one console formatter (#146); new lines: OSD owner changes, "console lost"→ gone (owner keeps it), panel machine states | probe inserts (≈45) once the machines log the same facts | — |

## Boot (from the profile, 1955 ms mains → ACTIVE)
- M2PLL switch first in `SysMainSystemInitial`: ~390 ms of init runs on the 14.318 MHz crystal today.
- Profile and cut `UserInterfaceInitial` (219 ms) and HDCP key + DP init (121 ms).
- Panel machine starts at power-on and runs alongside the SDK's power-on, INITIAL and SEARCH; console drawn while the link trains; backlight at T3 after link up. No step blocks the main pass.
- Expected (to be measured, not promised): picture-ready path no longer waits ~0.5 s for the panel; init ~2-3x faster on M2PLL.

## Order (each step: sim first, then unit 2)
- Sim: build, all gates, sim timelines per transition (cold boot, POWER on / off, switch, signal lost / back, sleep / wake) before → after; VLC view (`sim_live.py`) for Dan.
- Unit 2 only after the sim is clean: same timelines, posted on #162.
- Step 1 includes the sim clock model: fw_sim counts fixed instructions per ms, so it shows the ~390 ms crystal-phase init as 148 ms and cannot show an M2PLL-early gain. Model the MCU clock (crystal before the M2PLL switch, M2PLL, IOSC in power saving) so sim times match unit 2.
1. Time base (low risk, enables the rest).
2. Panel machine (C1, C2) + M2PLL early. Biggest gain; highest risk (panel T-timings re-proven on unit 2).
3. OSD owner (C3): console up through switches and wakes.
4. Power-saving wake single decider (C4, C5): Timer0-driven poll, poll sites removed.
5. Source model + hold decision (C10, C11).
6. NVRAM finish (C7), log ring / formatter (C13).

## Decisions (Dan, 2026-11-12)
1. Panel: own non-blocking machine (A).
2. OSD: one owner; console survives input changes (A).
3. Mode + power: **rewrite SysPower + SysMode + SysJudge as one machine of ours** (A; not the recommended B). Scaler functions (`ScalerGlobalResetProc`, measure, M-domain, free-run) stay as the machine's actions.
4. Signal-loss hold: keep L1 (backlight off, fast return) inside the new owners; L2 / L3 fold into the machine's NO SIGNAL → power-saving timers.
5. Wake poll: Timer0 event every 5 ms; the 14 main-loop sites go.
6. Order: time base → panel machine + M2PLL early → mode/power machine → OSD owner → wake → source model → NVRAM / log.

## Step 2: panel machine (wb-p14ui-s2, 2026-11-12)
- Owner: `UserCommonInterfacePanelPowerAction(event)` = request (idempotent, returns at once, logs 10 04..0B); `UserCommonInterfacePanelPowerTick()` = the only driver (UserCommonInterface.c). Ticks: main loop after `SysPowerHandler` and before the OSD handler, console open (map clear, font load, log init), each request.
- States (`AWTO_PNL_*`, RL6449_Project.h); each wait is an `AwtoMs()` due check from the step's action time:

| state | entry action | leaves when | wait from |
|---|---|---|---|
| OFF | - | target > off | - |
| VDD | VDD pin on | T1 and power status NORMAL | registry PANEL_T1 |
| HPD | DPTx power seq, PHY on | HPD high (one read per tick), or T2 (line 12 00, train anyway) | PANEL_T2 |
| LINK | link training, background on, stream on | one step | - |
| VIDEO | - | target BL (-> T3) / off (-> T4) | - |
| T3 | - | T3 since the stream start | PANEL_T3_OWN with own frame, else PANEL_T3 |
| BL_PWM | backlight pin on | backlight-to-PWM | `_PANEL_POWER_ON_BL_TO_PWM` |
| BL_ON | PWM = user duty | target < BL | - |
| BL_OFF | PWM dark | PWM-to-backlight, then pin off -> VIDEO (stream kept) or T4 | `_PANEL_POWER_OFF_PWM_TO_BL` |
| T4 | DPTx BL-off seq | T4, then stream idle | PANEL_T4 |
| T5 | - | T5, then SSC / PHY / VDD off | PANEL_T5 |
| T6 | - | T6 | PANEL_T6 |

- SDK status (READY / ALREADY for `UserCommonInterfaceReadyForActive`) derived from the state; ReadyForActive requests video when the target is off (replaces the display-setting `_PANEL_ON`).
- Power: `SysPowerHandler` waits (non-blocking) for the panel down before NORMAL/AC_ON -> OFF/SAVING; up-requests meanwhile are deferred (line 12 05) and the level restored if the target is withdrawn. Requests at OFF_TO_NORMAL (BL) and PS_TO_NORMAL (video); boot request after pin-share.
- Removed second drivers: `AwtoPanelVddEarly`, INITIAL `AWTO_BOOT_PANEL_ON`, display-setting `_PANEL_ON`, L1 pin writes, L2 `AwtoL2LinkOff/On` + `AwtoHoldBacklightSdk`, `AWTO_BL_OFF_OR_BLANK`, `AwtoDiagPanelT3Wait`, blocking HPD poll, `UserInterfaceAdjustWaitPanelT1..T5`, panel SDK timer events; `UserAdjustBacklight` writes PWM through the machine.
- Hidden blink: SDK `_BACKLIGHT_ON` held `#if(_USER_PROJECT_TYPE == UNITED_RTD2785_C23_LG_LM240WU8_SLE1_2LVDS_PWM)`; both undefined, so `0 == 0`: pin off, 10 ms, on, on every backlight-on call (the m15 / s1 blinks).
- Hold: L1 = BL_OFF / BL_ON requests; after `usL2Sec` the SDK no-signal -> power-saving path (L3 gone).
- M2PLL early: `SysPowerMcuClock` after `ScalerMcuInitial`; crystal around the whole-chip reset (regdb HOST_CTRL soft_reset resets all registers but HOST_CTRL, incl. M2PLL); M2PLL again after IOSC trimming.
- Gate `panel` (scripts/panel_sim.py): writes to VDD / backlight pins / PWM4 and DPTx link / stream / PHY calls only with `g_ucAwtoPanelOwn`; no blink; one link training per bring-up; T3 / T4+T5 / T6 kept; power off during display setting. Sim panel model: `fw_sim.EdpPanel` (HPD 115 ms after VDD, #78).
- Measurements: #162 comment of 2026-11-12 (sim and unit 2 tables).

## Step 3: system machine (wb-p14ui-s3, 2026-11-12)
- Owner: `SysJudge.c` = one machine for power status + mode (decision 3). `SysMachineHandler` (requests, power transitions, the judge's transitions, pending mode reset, state check) at the old `SysPowerHandler` slot; `SysMachineWork` (measure, display setting, first-ACTIVE work) at the `SysModeHandler` slot. `SysPowerSwitch`, `SysModeResetState`, `SysModeDisplaySetting`, `SysModeSetFreeRun` stay as its actions.
- One state `s_ucSysState` (`AWTO_SYS_*`, RL6449_Project.h). The SDK views (power status / target, mode state / reset target) follow it and are written only in `SysJudge.c` with `g_ucAwtoSysOwn` = 1.

| state | SDK power / mode | leaves when |
|---|---|---|
| AC_ON | AC_ON / POWER OFF | NVRAM power request: on -> INITIAL (`AC_ON_TO_NORMAL`), off -> DOWN |
| OFF | OFF / POWER OFF | power-on request -> INITIAL (`OFF_TO_NORMAL`) |
| INITIAL | NORMAL / INITIAL | next pass -> SEARCH |
| SEARCH | NORMAL / SEARCH | timing confirmed + supported -> DISPLAY; search done -> NOSIGNAL |
| DISPLAY | NORMAL / DISPLAY SETTING | display set + panel video ready + active wait -> ACTIVE |
| ACTIVE | NORMAL / ACTIVE | check fails -> HOLD (L1, `AwtoWakeHold`) or SEARCH; fast path -> FAST |
| FAST | NORMAL / ACTIVE | unblank -> ACTIVE; timeout -> SEARCH; fast wake retry -> HOLD |
| HOLD | NORMAL / ACTIVE | signal back -> FAST; released (L2 time, other cable, tries) -> SEARCH |
| NOSUPPORT | NORMAL / NO SUPPORT | a reset or a failed check |
| NOSIGNAL | NORMAL / NO SIGNAL | timing confirmed -> DISPLAY; cable reset -> SEARCH; OSD power-saving timer -> DOWN |
| SAVING | SAVING / POWER SAVING | power-on request -> WAKE (`PS_TO_NORMAL`, or `FAKE_PS_TO_NORMAL`); off -> OFF |
| WAKE | NORMAL / POWER SAVING | timing confirmed -> DISPLAY; search finds nothing -> power-saving request |
| DOWN | kept | panel machine down (T4, T5) -> OFF (`NORMAL_TO_OFF`) / SAVING (`NORMAL_TO_PS`); power-on request -> back |

- Requests: `SysMachineRequest(request, who)` only. Requesters: POWER key, front key in power saving, test cmd 0x3E, VCP D6 (glue and SDK DDC/CI), input select, selector, dead port, wake poll, SDK power-saving predetect, SDK cable reset, OSD power-saving timer, settings, SDK OSD, hold, fast path, judge timers, NVRAM at boot. `SysPowerSetTargetPowerStatus` / `SysModeSetResetTarget` are request wrappers. Outcomes: accepted, already, replaces, refused, kept (power saving / down / hold).
- Power targets and mode resets wait in the SDK target fields until the handler takes them. Fast path / hold requests change the state at once: they do no scaler work.
- SDK rule kept: a mode change waits while an SDK handler has not seen the last one (change flags). The state check after a failure forces the change, as in the SDK.
- Logs (sync.tsv): 13 = `system: <old> -> <new>: <why> (N ms in <old>)`, 14 = `system: <request> requested by <who> (<outcome>)`. Name tables 15..19 use a direct row index. Mode lines (01) are logged at the transition. Power lines (C0, C9) are logged at the power transition. Row lookup is indexed by id (`tAwtoSyncIdRow`).
- Removed: `SysPowerHandler`, `SysJudgeHandler`, `SysModeHandler`, `SysJudgeStateChangeEvent`, `SysJudgeModeResetProc`, `AwtoSwPoll` mode polling, the per-pass power compare, the judge-hold sub (`AWTO_FAST_JUDGE_HOLD`, `AWTO_WAKE_HOLD`), the direct target writes (keys, testcmd, VCP, wake poll, dead port, fastsw, hold, selector, settings, SysTimer, SysSource), and `g_ucSignalUnstable` / `g_ucIssueState`.
- POWER off during display setting: DOWN runs no judge, so display setting no longer restarts during the power-down. POWER pressed again during DOWN calls it off.
- POWER-key-on block (~700 ms, step 2 open item): the DP DC-on HPD toggle in `_DP_LONG_HPD_DELAY_MODE` = `ScalerTimerDelayXms(_DP_LONG_HPD_TIME)` (700 ms) with a cable on D1. Not in the sim (no D1 cable). `Scaler_Option.h`: timer-event mode always.
- HDMI HPD recovery: the 110 ms low pulse no longer waits in the judge (`AwtoTmdsHpdTick`).
- Panel machine (step 2 items 6, 7): a warm reset starts in T6, counted after the registry load. Off from VIDEO / T3 with the backlight never on skips T4. T6 counts from the VDD-off edge.
- Hidden SDK branch (corrected 2026-11-12): `_CUS_*` are defined (Project_List.h, ISO-8859: plain grep misses it); only `_CUSTOMER` is undefined = 0 = `_CUS_DEFAULT`, so every customer body was compiled out. Step 3 had switched the no-support timer to SEARCH on the wrong premise (search loop, no NO SUPPORT); restored to the SDK NO SUPPORT path (gate `sysm` no-support case). The NOSUPPORT 1 s delay was Mindray-only, never compiled. Customer branches deleted; audit + gate `scripts/pp_audit.py` (wb-p14ui-cus).
- XDATA: 2 B free (17 before). Locals in the machine are cut to one per function.
- Console: no live log draw while a fast switch settles (`AWTO_CON_LIVE`); the lines stay in the ring and the OSD poll draws them after the unblank.
- Gate `sysm` (scripts/sysm_sim.py): power / mode view changes only with `g_ucAwtoSysOwn`, unbroken transition chain, named states / requesters, each mode line after its transition, no request-less target; `--tree` lint (view setters only in SysJudge.c, actions only from the machine's files, old handlers gone).
- Measurements: #162 comment of 2026-11-12 (step 3, sim and unit 2 tables).

## Step 3b: one fact = one line (wb-p14ui-s3b, 2026-11-12)
- Machine lines are the record of pin / link / stream / power / mode changes; no second line restates them (Dan: three backlight-on lines).
- Gone (rows removed; switch log keeps the events): pin edges 10 00..03 for machine writes, stage lines D1 05 / 07 / 08, mode lines 01, C9 power off / saving, probes 90 01 / 0E, A0 00 / 05, A8 01..09.
- Folded: mode text appended to the system transition that changes the SDK mode (why bit 7, table 1A); boot `RESET -> AC ON` (ms since reset) replaces the init mode line; `LINK -> VIDEO` carries the training time (fmt ms2); a pin write outside the machine is one line 12 02..33 (level, edge).
- Requests say who: panel `UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(event, AWTO_PNL_BY_*))` (who in bits 7..2, table 1B), deferred is an outcome (was 12 05); hold release reasons are requesters (16 0E / 1A / 1B).
- Times: a line's ring time = its transition. Panel: line before the action (LINK -> VIDEO after training + stream, `-> T6` at the VDD-off edge). System: `SYS_AT` logs before the action, `SysMachineGo` applies after. Console draw held during the panel tick / a system line (`AWTO_CON_LIVE`).
- Gates: panel_sim (each machine pin edge has its line within 3 ms), boot_sim (line time = previous line + `N ms in`, +-3 ms), sysm_sim (mode text exactly on mode changes, RESET first, requesters named).
