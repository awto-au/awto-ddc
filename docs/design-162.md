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
