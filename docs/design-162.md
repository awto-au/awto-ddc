# #162 design: one owner per resource (draft for Dan, 2026-11-12)

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
| Power status (OFF / NORMAL / SAVING) | SDK `SysPower` (kept); every caller uses `SysPowerSetTargetPowerStatus` | direct target writes in fastsw / wake poll / testcmd | **B** |
| Mode (search … active) | SDK `SysMode`/`SysJudge` (kept); our code uses its API only | hold-judge sub, `AwtoSwPoll` mode polling (machine logs itself) | **B** |
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

## Order (each step: gates + sim + unit-2 cold-boot / POWER / switch timelines before → after, posted on #162)
1. Time base (low risk, enables the rest).
2. Panel machine (C1, C2) + M2PLL early. Biggest gain; highest risk (panel T-timings re-proven on unit 2).
3. OSD owner (C3): console up through switches and wakes.
4. Power-saving wake single decider (C4, C5): Timer0-driven poll, poll sites removed.
5. Source model + hold decision (C10, C11).
6. NVRAM finish (C7), log ring / formatter (C13).

## Decisions for Dan
1. Panel: **A** own non-blocking machine (recommended) / B thin wrapper / C reorder only.
2. OSD: **A** single owner, console survives input changes (recommended) / B pin flag inside the SDK model.
3. Mode / power: **B** keep the SDK machines, ours via their API only (recommended) / A rewrite as one table machine.
4. Signal-loss hold: keep L1 (backlight off, ~270-300 ms back) and fold L2 / L3 into the SDK's NOSIGNAL → power-saving timers (recommended) / keep L1-L3 as today / drop the hold (SDK path only, ~2.5 s back).
5. Wake poll driven by Timer0 every 5 ms instead of main-loop sites (recommended) / keep sites.
6. Order as above, or another first step.
