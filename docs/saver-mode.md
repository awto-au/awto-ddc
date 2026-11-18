# Saver mode: what it is, what the main loop does under it (Dan's question 2026-11-18)

Status 2026-11-18. D1, D4, D5 decided (Dan, 2026-11-18) and implemented (below); D2, D3, D6, D7 open. Code: `fw/test/saver.c`, main loop `fw/sdk/Kernel/System/Code/SysMain.c` `main()`. Design: `docs/screensaver.md`.
Tools: `scripts/saver_loop_cost.py` (per-pass cost by handler, saver rates), `scripts/saver_mode_sim.py` (exit paths).
Numbers below: sim, fast core, dw8051 timing, image `AWT26110003-smb-be` (main 4b25631 + `-D _AWTO_AUDIO_TEST`), 3 s fw windows.

## Answer in short

- Saver mode today = `g_ucAwtoSaverRun != AWTO_SAVER_OFF` (`saver.c:44`). One owner (`saver.c`), but exits are partial: see defects.
- The main loop outside the saver costs ~3.1 ms per pass (8.6 k instr). Nothing in it is worth skipping for speed:
  - Pac-Man is timer-paced (31 ms sub-step): pass time does not change its rate.
  - Scopes: the saver itself is 23-30 ms of a 27-34 ms pass (85-89 %). Everything skippable is < 0.2 ms per pass (< 1 %).
- Interference is real and is the reason to act, not speed: SDK no-signal card over a running saver (fixed for idle and for no signal: D1).
- Implemented: idle saver ends when the picture is lost; any mode exit restarts the idle time. No main-loop short path.
- Gates on the changed image (`AWT26110003-smj-be`): `fw_gates.py` all PASS but `pump` (fails the same on the unchanged smb image: pre-existing, main 714cf6a), health `delay cal` (pre-existing); `saver_sim.py` 12 PASS; `pytest` 305 passed.

## Saver state today

| var | file:line | values |
|---|---|---|
| `g_ucAwtoSaverRun` | `saver.c:44` | 0 off, 1 Pac-Man, 2 Scope, 3 Scope 2, 5 flash warning, 6 boot splash |
| `g_ucAwtoSaverWhy` | `saver.c:45` | 0 none, 1 no signal, 2 idle, 3 now (VCP 0xEB / test), 4 boot; bit 7 = Alternate |
| `g_ucAwtoSaverMode` / `g_usAwtoSaverIdleS` | `saver.c:42-43` | settings rows 119 / 120 |
| `s_ucReq` | `saver.c:47` | VCP 0xEB request, served by the next `AwtoSaverPoll` |
| `isr_g_stAwtoDiag.ucHold` bit `AWTO_HOLD_POPUP` | `saver.c:224`, `console.c:556-643` | boot splash and console: blocks `OsdDispDisableOsd` (`testcmd.c:18`) |

- Poll: `AwtoSaverPoll` once per pass from `AwtoDiagTestCmd` (`testcmd.c:250`), slot 0 of the pass (after keys).
- Test cmds 0xB7-0xB9 / 0xBA.. draw Pac-Man / Scope directly: not saver mode (no state, no exits).

### Entries

| who | why | file:line | condition |
|---|---|---|---|
| power-on | boot (splash) | `saver.c:165-175` | first pass, `boot_splash` on, cold boot; drawn at mode INITIAL (`:218`) |
| no signal | nosig | `AwtoSaverPoll` | mode NOSIGNAL for `AWTO_SAVER_NOSIG_MS` 1.8 s, row 119 != Off, `pwr_l3_s` != 0, not ended earlier in this no-signal episode |
| idle | idle | `saver.c:282` | mode ACTIVE, row 120 != 0, no key / DDC/CI for row 120 s |
| VCP 0xEB 1-5, 7 | now | `saver.c:177-203`, `set_ap_screensaver_now` | any mode |

### Exits

| event | ends | file:line |
|---|---|---|
| front key press | all | `keys.c:321` -> `AwtoSaverKey` (`saver.c:63`); the key also does its normal action |
| DDC/CI command (not VCP 0xEB) | nosig, idle. Not now (plain or Alternate: D4), not boot | `ddcci.c:244` -> `AwtoSaverActivity` |
| `pwr_l3_s` s after the start | nosig: then the SDK chain resumes (D1) | `AwtoSaverPoll` |
| VCP 0xEB = 0 | all but boot | `saver.c:182-188` |
| mode != NOSIGNAL | nosig | `saver.c:228-234` |
| mode != ACTIVE | idle (**new**, this change) | `saver.c:229` |
| mode ACTIVE or 3 s (`AWTO_SPLASH_MAX_MS`) | boot | `saver.c:214` |
| `OsdDispDisableOsd` past the hold (console, menu, SDK reset) | boot only | `RTD2014OsdDisplay.c:265` -> `AwtoSaverTaken` (`saver.c:137`) |
| power saving / POWER off | nosig (mode leaves NOSIGNAL); idle (mode leaves ACTIVE); **now: never** | - |

### What is under the saver

- Idle: live picture; the saver is an OSD over it. Host audio keeps playing (`SysAudioHandler` runs).
- No signal: background only. The saver starts at the card time and replaces the card (D1).
- Now: whatever is up, any mode; it survives signal loss, power saving and input switches.
- Boot: power-on, mode INITIAL..ACTIVE.

## Defects found in the sim (`saver_mode_sim.py`)

| case | before (smb) | after (smj) |
|---|---|---|
| `idle_loss`: idle Pac-Man, input -> D3 without source (signal-loss proxy) | saver keeps running; 2 s after NOSIGNAL the SDK no-signal card draws into the Pac-Man OSD: garbled glyphs, double scale (PNG `tmp/saver_mode_sim/idle_loss_after.png`) | saver off at the first non-ACTIVE sample; clean no-signal card |
| `nosig_lock`: no-signal saver, then D2 locks, row 120 = 10 s | the idle saver starts over the new picture 2 s after ACTIVE | stays off (idle time restarts at the exit) |
| `nosig_default`: defaults, no signal | saver never started: NOSIGNAL +2 s card, +3 s power-saving card, +2 s power saving (mode 6 at +8.25 s) < 10 s | saver at +1.5 s after NOSIGNAL (sample 0.5 s), runs N, ends, power saving 8 s later; no card over it (D1) |
| `nosig_l3off`, `nosig_lock` with `pwr_l3_en` 0 | saver starts at +10 s; its own start (`osd_tc_close`, `text_layer.c:356`) re-arms the no-signal card 2 s; card wipes the saver at +12 s, saver keeps uploading into it (black screen) | saver keeps the OSD for N; after N the card returns and stays (power saving ignored), no restart |

## Per-pass inventory (sim)

Slot = from the call's entry to the next hooked call (macro polls like `AWTO_PS_POLL_SITE` and ISRs landing there are included).

| slot (SysMain.c order) | ACTIVE idle pass instr / us | NOSIGNAL instr / us | in a Scope 2 pass instr / us | class | why |
|---|---|---|---|---|---|
| `AwtoStackCheck` | 41 / 24 | 43 / 26 | 41 / 25 | must | stack canary (crash record) |
| `AwtoSwPoll` (x2) | 179 / 66 | 177 / 65 | 185 / 70 | must | wake poll, mode-change log lines (never dropped) |
| `AwtoDiagMainPass` | 222 / 104 | 219 / 103 | 227 / 107 | must | watchdog pass poke, heartbeat |
| `AwtoGpioPoll` | 3108 / 475 | 3103 / 474 | 3099 / 470 | must | key ADC incl. POWER, 44-input scan + logs, console auto-open |
| `AwtoKeyPoll` | 277 / 145 | 277 / 145 | 338 / 184 | must | keys end the saver |
| `AwtoDiagTestCmd` | 98 / 62 | 94 / 60 | 94 / 60 | must | test cmds, pop-up hold timer, Pac-Man sound poll |
| `AwtoSaverPoll` | 168 / 62 | 171 / 62 | 163118 / 30200 | - | the saver |
| `SysMachineHandler` | 860 / 390 | 284 / 177 | 1894 / 830 | must | power + mode transitions: signal loss (ends idle), lock (ends nosig) |
| `UserCommonInterfacePanelPowerTick` (x2) | 588 / 284 | 678 / 336 | 589 / 291 | must | panel power sequencing |
| `SysAudioHandler` | 1131 / 620 | 848 / 482 | 1135 / 629 | must (idle) | host audio under an idle saver; 110 / 59 while the Pac-Man generator runs |
| `SysTimerHandler` | 463 / 114 | 528 / 121 | 466 / 120 | must | SDK timer events (judge, OSD, power saving) |
| `SysSourceHandler` | 318 / 176 | 694 / 409 | 311 / 171 | must | source search: what ends the nosig saver |
| `SysMachineWork` | 185 / 107 | 237 / 142 | 189 / 110 | must | measure / display setting |
| `SysDpRxHandler` | 170 / 106 | 184 / 113 | 174 / 109 | must | DP Rx link / AUX |
| `SysTMDSRxHandler` | 151 / 64 | 149 / 59 | 126 / 61 | must | HDMI / HPD |
| `AwtoSetLoop` (every 20 ms) | 258 / 83 | 136 / 66 | 2341 / 656 | must | VCP mailbox (0xEB = 0 stop), settings, NV gate flush |
| `UserCommonInterfaceOsdHandler` | 255 / 155 | 407 / 180 | 246 / 151 | gate, not skip | SDK OSD: mode-change pop-ups (the collision source) + `SysModeClrModeStateChange` (must) |
| `UserCommonDdcciHandler` (+ `AwtoDdcciPoll` when flagged) | 58 / 18 | 61 / 20 | 64 / 22 | must | DDC/CI |
| `SysColorHandler` | 27 / 11 | 28 / 12 | 27 / 11 | can skip | ACTIVE-only colour handlers; 11 us: not worth a branch |
| `ScalerDebug` | 48 / 28 | 51 / 30 | 50 / 30 | must | debug link 0x35 (tools, sims) |
| **pass** | 8604 / 3091 | 8368 / 3083 | 174714 / 34307 | | worst pass: 19.6 / 21.4 / 71.1 ms |

- Can delete: none.
- Can skip: `SysColorHandler` (11 us), and at most the SDK pop-up part of the OSD handler (~0.15 ms): < 0.2 ms per pass.
- Bound on the gain: Scope 2 frame = 28 passes; 28 x 0.17 ms = 5 ms of 1510 ms (0.3 %). Pac-Man: 0. Not implemented.

## Saver rates (sim, before = after)

| saver | rate | per pass |
|---|---|---|
| Pac-Man | 32.00 sub-steps/s = 7.999 game steps/s over 62 s fw (D5; was 7.78: the schedule restarted from 'now'); sub-step 31, 31, 31, 32 ms, 5..95 % of intervals 29.3..33.7 ms (pass jitter), worst 22.6..38.5 | 3.1 ms |
| Scope | 0.90 frames/s: 32 column passes x 27.3 ms + 100 ms pause = 1115 ms | saver 23.1 of 27.3 ms |
| Scope 2 | 0.66 frames/s: 28 column passes x 34.3 ms + 100 ms pause = 1510 ms | saver 30.2 of 34.3 ms |
| `pacman_speed.py` (test cmd step) | 4.17 (smb) -> 4.19 (smj) ms per step, 240 -> 239 steps/s: unchanged | - |

- Where the scope time goes (PC samples, Scope 2): `cursor_init` 13 %, `cursor_plot` 12 %, `S2Char` 10 %, banked-call trampoline (`__bs_call`, shown as `__mcs51_genXRAMCLEAR`) 8 %, `osd_line` 6 %, `__mulint` 5 %, `S2Trace` 5 %, `__gptrget` 5 %.
- Idle pass (PC samples): `AwtoInScan` + `AwtoInRead` 30 %, banked-call trampoline 16 %.
- DDC/CI under a scope: the engine is polled once per pass; Get-VCP reply latency up to a pass (mean 34 ms, worst 71 ms vs 3 / 20 ms idle). Watchdog: 71 ms worst gap of the 820 ms budget.

## Design: one saver-mode predicate

- One definition, owner `saver.c`: `AwtoSaverOwnsOsd()` = `g_ucAwtoSaverRun != AWTO_SAVER_OFF`. Every OSD user asks it; nobody else reads `g_ucAwtoSaverRun`.
- Consumers (instead of a main-loop short path; the main loop stays as is):
  - `AwtoHoldBlocksDisable` (`testcmd.c:18`): blocks `OsdDispDisableOsd` while the saver owns the OSD, as for the awto menu (`g_ucAwtoMenuOn`). Replaces the splash's `AWTO_HOLD_POPUP` use.
  - SDK pop-up events (`RTDOsdEventMsgProc`): dropped while the saver owns the OSD, as `AwtoSetLoop` does for the menu (`settings_glue.c:559-570`). Power-saving events: per D1.
  - Console / menu / test screen opening: call `AwtoSaverStop()` first (explicit take-over), not via the disable hook.
- Exits, one table in `AwtoSaverPoll` (by why):
  - nosig: mode != NOSIGNAL (exists); power status != NORMAL.
  - idle: mode != ACTIVE (done); power status != NORMAL.
  - now: power status != NORMAL (new: D3).
  - boot: mode ACTIVE, 3 s cap, key (exists).
  - all: key, DDC/CI command (not 0xEB), VCP 0xEB = 0, console / menu take-over.
  - after any exit: idle time restarts (done for mode exits; key / DDC already do).
- Not in the design: skipping handlers per pass (measured gain < 1 %). Speed work belongs in the saver draws and the column budget.

## Decisions (Dan, 2026-11-18)

- **D1 no-signal saver vs power saving: decided, implemented.** Start at the card time, replace the card, run N, then the SDK chain.
  - Start: 1.8 s into NOSIGNAL (`AWTO_SAVER_NOSIG_MS`, 90 % of the SDK card timer `SEC(2)`, so the saver is up before the card event). The start requests backlight on (`AWTO_PNL_BY_OSD_NOSIGNAL`, as the card does) and cancels the SDK card / power-saving timers.
  - N = registry row 80 `pwr_l3_s` ("L3 delay", default 600 s = 10 min, step 30, was inert). Reason: it is the existing "time before deep sleep" row and the same 600 s as `AWTO_L3_SEC` (the hold's L3); 0 = no no-signal saver (SDK chain as without a saver). Measured from NOSIGNAL + 1.8 s.
  - While it runs: `AwtoSaverGuard` (`RTDOsdEventMsgProc` cases NOSIGNAL, NOCABLE, NOSUPPORT, POWER_SAVING_EVENT, GO_TO_POWER_SAVING) drops the pop-up and cancels the four timers.
  - End by N: `AwtoSaverStop` -> the OSD close re-arms the card (2 s) -> card, power-saving card (+3 s), power saving (+2 s): power saving at N + ~8 s. `pwr_l3_en` = 0: card stays, power saving ignored.
  - End by key / DDC/CI command: same chain. `s_ucNoSigDone` latches until the mode leaves NOSIGNAL: no saver -> card -> saver loop.
  - Signal back (mode != NOSIGNAL): saver off, idle time restarts (idle saver not over the new picture before `screensaver_s`).
- **D4 Alternate flag: decided, implemented as: a DDC/CI command ends neither "now" saver** (plain 0x03 and Alternate 0x83 behave the same). Reason: the code excluded now savers on purpose (explicit host request; `scope2_ddc_latency.py` and the sims talk DDC/CI to a running now saver); the bug was only the unmasked bit 7. Not read as "end both": it would break those tools. Open and unchanged: a front key does not end a plain "now" saver either (`AwtoSaverKey` -> `AwtoSaverActivity`), although the table above says "all".
- **D5 Pac-Man pacing: decided, implemented.** Fixed-rate schedule: `s_usTick += period`, 31 / 31 / 31 / 32 ms = 125 ms per game step; resync to now when more than a game step behind (no catch-up burst). `saver_loop_cost.py --case pacman --window 62` prints rate and interval spread.

## Open decisions

- **D2 the key that ends a saver:** also does its action today (MENU opens the menu, SOURCE the selector). Swallow it?
- **D3 VCP 0xEB "now" savers** survive signal loss, input switch and power saving (by design for tests). End them on power status != NORMAL?
- **D6 scope column budget:** a column pass is 23-30 ms (worst 71 ms) and delays DDC/CI replies by as much. Split a column into bands per pass (< 10 ms) or pump DDC/CI between bands? (Scope 2 now draws in <= 8 ms bands.)
- **D7 `AwtoGpioPoll`:** 44 inputs scanned every pass = 15 % of an idle pass (0.47 ms). Scan keys every pass, the rest every N ms? Selector pulse counts (`AWTO_PS_COUNT`) would need a check.

## Unit 3 tests (hardware; nothing here was run on a unit)

- Real signal loss (host output drop, `scripts/host_output_drop.py 3`) under an idle saver: with `pwr_l1_en` on the mode stays ACTIVE (L1 hold, backlight off): the saver runs on in the dark until L2 (60 s), then ends. Check that and the clean no-signal card after it.
- Idle saver, picture returns (host wake): saver stays off for row 120 s.
- No-signal saver (D1), host output dropped (`host_output_drop.py 3 --hold-s 15` or longer; a short drop may wake before NOSIGNAL):
  - Backlight on at ~2 s after NOSIGNAL with the saver up (the card's backlight request is made by the saver start): confirm no dark gap and no card flash.
  - Panel / backlight sequencing: `pwr_l1_en` / `pwr_l2_en` hold runs first (ACTIVE, 60 s) when the loss was in ACTIVE; the saver only starts in NOSIGNAL after it.
  - Set `pwr_l3_s` = 30: saver ends at ~32 s, card, power saving at ~40 s; wake by host output back.
  - `pwr_l3_en` = 0: after N the card returns and stays; a key during the saver gives the card, no saver again until the signal returns.
