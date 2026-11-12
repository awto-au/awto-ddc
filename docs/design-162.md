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
