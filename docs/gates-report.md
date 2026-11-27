# Gate report: where we were -> where we are

Measured 2026-11-19 13:38-13:55 on a fresh build of the merged tree (origin/main + this branch), image `AWT26110003-r1`, load average 15-17 (not quiet; the box does not get quieter).
- CPU s = user + sys of the gate's process tree, one gate at a time.
- Wall s is the same single run.
- Tier totals come from `fw_gates.py` with the tier's gates in parallel.
- OLD = the full-set run of 2026-11-19 12:24 under load 35 (`gates_main_full.log`): result and wall s. OLD CPU is my own measurement on the old scripts, where I took one; `~` = not re-measured, taken from the new scripts' value.

## Pipeline time (edit -> on the unit)

| stage | OLD (12:24 situation) | NOW warm cache | NOW changed tree / cold-ish | options (not applied) |
|---|---|---|---|---|
| pre-build (generators, `pp_audit --check`, EDID tables, lint) | 27 s | 25-27 s (pp_audit 24 s, generators 2 s) | 32-34 s (pp_audit 32 s at load 20) | cache `pp_audit --check` by source hash: saves 24-32 s on an unchanged-source build. Run it only on changed TUs: about the same saving on a small edit. Run it in parallel with the asm compile: about 25 s wall. A `--fast` build for the dev loop that skips it |
| BUILD (compile + assemble + link) | 13 s warm | 13 s (compile 3 s ccache hit, assemble 5 s, link 3 s) | 58-60 s (ccache miss after a merge: compile 47-51 s) | cold ccache (empty): about 2.5 min |
| pre-build + build (what `dev.py build` prints) | 40 s warm | 40 s | 88-93 s; cold ~2.5 min | |
| TEST (pytest, `./dev.py test`) | not measured (same suite, no gate involved) | 75 s wall, 73 s CPU, 527 pass, 1 fail (see below) | | |
| GATE normal | 136 s wall, 9 killed by the old guard | 14 s wall, 51 s CPU (24 gates, all PASS) | | |
| GATE extensive | not separate (same 136 s run) | 129 s wall, 626 s CPU (37 gates, all PASS) | | |
| FLASH | unit 3 HDMI DDC 24 s, unit 2 DP AUX 116 s (Dan) | same | | incremental vs full: not measured (no hardware here) |

| path | OLD | NOW warm | NOW changed tree |
|---|---|---|---|
| daily loop: build + normal gate + flash unit 3 | 40 + 136 + 24 = 200 s | 40 + 14 + 24 = 78 s | 90 + 14 + 24 = 128 s |
| merge path: build + pytest + extensive gate (includes normal) + merge-check (<1 s), without flash | 40 + 75 (assumed) + 136 = 251 s | 40 + 75 + 129 = 244 s | 90 + 75 + 129 = 294 s |

Notes:
- Gate times exclude the build. Wall = tier in parallel; CPU = sum of the gates.
- `pytest` has 1 failure that is not a gate and not caused by the gate work: `tests/test_pump_budget.py` takes the first `AWT26110003-*-clk87-be.bin` in `tmp/fw` (alphabetical), and on this tree's other clk87 images the old-check assertion does not flip. It needs to pick the newest image.
- OLD gate wall 136 s = the whole run from 12:24:41 to 12:26:57; the guard killed 9 gates (sync, sysm, wake, conmode, conwrap, crash, wdt, monitor, delays), so OLD was not a complete record.

## Per gate

NORMAL/EXTENSIVE columns: the variant that runs in that tier (wall s / CPU s, single run). `-` = not in the tier. Dan's comment is verbatim from `debris/docs/tmp-notes-20261127/scratch/gates-report.md`.

| gate | what it checks | failure it catches | OLD result, wall s | OLD CPU s | NORMAL wall / CPU | EXTENSIVE wall / CPU | tier today | Dan's comment | action / status |
|---|---|---|---|---|---|---|---|---|---|
| boot | firmware boots to stage 8, heartbeat advances | firmware that never starts / traps / restarts | PASS 1 | ~0.4 | 0.4 / 0.4 | same | normal | ok | none |
| isr | 1500 interrupts return to the interrupted bank | an ISR that returns to the wrong code bank or leaks stack | PASS 7 | ~0.4 | 4.5 / 0.4 (ucsim) | same | normal | why 1500 ? can we just do minium to sweep all vaues | open: minimal sweep (all banks x all vectors seen, stop there) not done |
| link | linker findings | overlap, missing symbol, banking error | PASS 3 | ~2 | 2.0 / 2.0 | same | normal | | none |
| h1080 | health in the sim at 1080p60 (12 checks) | broken input timing, pins, OSD event, monitor, delay calibration | PASS (11/12) 4 | ~1.4 | 1.4 / 1.4 | same | normal | more info | all 12 checks real now: 'delay cal' is judged in the dw8051 sim like on the unit (was marked "sim, not timed" and failed by construction); 12/12 at 350 / 175 / 87 MHz |
| h2160 | same at 2160p60 | same | PASS (11/12) 6 | ~1.4 | 1.4 / 1.4 | same | normal | more info | as h1080 |
| menu | walks 16 menu pages; normal: per page the first / last entry + one per class (46 of 133 entries); extensive `menu_full`: all 133 + a PNG per page | a menu entry that crashes or draws wrong | PASS 27 | ~10 | 3.1 / 5.0 | 7.9 / 9.4 (menu_full) | normal (quick) + extensive (full) | to long - extended gate only | PNG renders were 6 of the 9 CPU s: normal has none. Fault proof: `menu_open` RET'd fails it |
| ddc | DDC/CI protocol sim (MCCS get/set) | a wrong VCP reply, a lost request | PASS 8 | ~1.8 | 1.8 / 1.8 | same | normal | too longg - can we reduce to sesssential vlaues only | now 1.8 s; value reduction not done |
| pump | message pump sim | a DDC/CI request lost inside a blocking wait | PASS 3 | ~0.9 | 0.9 / 0.9 | same | normal | | none |
| keys | key dispatcher: every screen, 80 checks (full); selector section only (quick) | wrong key band, missing debounce, hold / repeat / reset wrong, selector wrong | PASS 126 | 90 | not in normal | quick 21.7 / 23.6; full 123 / 124 | extensive | why so long ? | moved. Cost = ~250 simulated s of OSD timeouts and holds: the test-timing scale is the cut (in progress) |
| wdt | watchdog cases: bite, no false reset, reason line, Timer0 timing (4) normal; 21 in full | a hang not detected, a spurious reset, wrong reset cause | KILLED 60 | ~33 | 3.0 / 3.0 | full 40.6 / 40.3 | normal (4 cases) + extensive (21) | why do long ? | cut from 33 s to 3 s in normal |
| sync | sync-log sim (ring format, lines) | a log line lost or garbled | KILLED 30 | ~11 | - | 12.3 / 14.2 | extensive | why so long ? | moved; pure-logic split not done |
| bootsim | boot with console after the picture | console missing or wrong after boot | PASS 11 | ~6 | 5.6 / 7.5 | same | normal | why 10x realtimed when sim runs 10 times quicket than realtime | boot = 16.5 M instr, 0.66 simulated s, 0.67 s CPU = 1x real time (event-heavy: flash reads, register hooks); the 5x of the idle loop is the sim's best |
| bootsim_always | boot with console at power-on | console not drawn at power-on | PASS 14 | ~6 | - | 5.0 / 7.0 | extensive | | moved |
| wake | wake from power saving (cable, EDID, AUX, DPCD, keys, TMDS clock) | a wake missed or spurious, a wake line missing | KILLED 30 | ~15 | - | quick 9.4 / 11.3; full 17.2 / 19.2 | extensive | why do long | moved; quick variant kept for `--only` |
| panel | panel power, backlight and DP link sequencing | wrong T-times, backlight before VDD, link out of order | PASS 17 | ~6 | 6.1 / 6.0 | same | normal | why | none |
| sysm | system state machine (power / mode chain) | a transition out of order, a request without its line | KILLED 30 | ~10 | - | 11.0 / 11.0 | extensive | whot sol ong | moved |
| delays | every linked delay site is in the audit TSV, no FIX / UNKNOWN row (normal); + the panel scenario at the image clock (delays_sim); + the sibling -clk87 image (delays_full) | a new delay with no audit row, a loop under its nominal, Timer2 not 1:1 with wall, loop counts not AWTO_DELAY_CNT, DDC debounce differing between clocks | KILLED 93 | 49 | audit 1.7 / 1.7 | sim 12.0 / 11.9; full 29.0 / 26.8 | normal (audit) + extensive (sim) | huh  are there check ing what ? | what it checks, in words: (1) every timed wait in the panel power sequence took its intended wall ms (class A, DelayXms / poll / wait-for-event); (2) Timer2 ms per wall ms within 0.5 %; (3) every executed DELAY_5US / DELAY_XUS loop at least nominal; (4) loop counts equal AWTO_DELAY_CNT of the running clock; (5) DDC debounce the same wall time at both clocks; (6) the audit TSV lists every linked delay site. 49 s -> 14 s: the audit's regex compiles (39 of 49 s) |
| nvlog | NVRAM flush log lines | a flush with no line, wrong byte count | PASS 11 | ~4 | 5.1 / 5.1 | same | normal | ? | none |
| flashclk | flash clock order at boot, write sessions | wrong F2 / tune order | PASS 3 | ~1 | 1.1 / 1.1 | same | normal | | none |
| deadport | dead-port search: VCP 0x60 / selector refuse a port with no cable | a switch to a port with no cable that sticks | PASS 75 | 35 | - | 24.6 / 24.5 | extensive | why so long | 4 cases from one boot snapshot; cmd case asserts at 16 s |
| portcfg | disabled port: HPD low, never searched | a disabled port still searched | PASS 12 | ~3 | 4.1 / 4.1 | same | normal | ? | none |
| inputrate | input-monitor scan rates: a pulse of 1.25 x the worst read gap is seen at every phase | a scan too slow to see a key spike or a source pulse | PASS 85 | 55 | - | 16.9 / 18.9 | extensive | ? | 55 -> 19 s: big idle steps, informational sweeps opt-in (`--info`) |
| monitor | health monitor: sample period, rows, change thresholds, registry switch, heartbeat | a sample missed, a row dropped or repeated, heartbeat not sent | KILLED 90 | 95 | 4 / 5.2 (period / 10, no heartbeat) | monitor_full (period / 10, heartbeat) ~ 11 CPU; monitor_real (production period) 75 / 77 | normal + extensive | ? | sim-only period scale (`sim_time_scale.py`), same 9 checks at scale 1 and 10 (`tests/test_time_scale.py`); production image untouched |
| htime | host time over DDC/CI, console title row | wrong time in the title | PASS 13 | ~6 | 4.8 / 6.6 | same | normal | for one line on the osd | 13 s was load: 4.8 s now; one boot + the title draw is the floor |
| conmode | console off / until signal / always | the console closing at the wrong time or on the wrong key | KILLED 30 | ~9 | - | 8.8 / 8.8 | extensive | ? | moved |
| canary | stack canary quiet at ACTIVE, fatal + halt on 0x3F | stack overflow not caught | PASS 44 | ~24 | - | 25.0 / 24.5 | extensive | 44s to chek thsa ? | long boot + fatal path; direct check not done |
| conwrap | console lines whole, a wide line on two rows, no watchdog bite. Normal `conhost`: the real break decision (`fw/osd/conwrap.c`, split out of console.c) compiled on the host; extensive: the sim phases (`conwrap_full`) | a clipped line, a break in the wrong place, a 3-row group, a missing line | KILLED 30 | 13.6 | 0.0 / 0.04 (conhost, 7613 rows) | full 13.5 / 14.8 | normal (host) + extensive (sim) | shoule less .1s ? | done: 0.05 s wall cached. 5 injected faults in the C source each FAIL it (`tests/test_con_wrap_host.py`); the sim gates still pass on the refactored image. Code size +35 B (WrapLine 282 -> 230, Break 78 + 8) |
| crash | crash and watchdog-bite handling | a hang that leaves no crash record | KILLED 30 | ~21 | - | stall 6.3 / 8.3; full 15.8 / 17.7 | extensive | seem wring | tests the 0x4C stall -> bite -> record chain; needs a boot to ACTIVE then a deliberate hang |
| pokes | watchdog poking loops are bounded | an unbounded loop around a poke | PASS 4 | ~1 | 0.9 / 0.9 | same | normal | seem long | 4 s was load; 0.9 s CPU (static) |
| magic | no raw register / palette numbers in our code | a raw 0x3Axx in a Scaler call | PASS 0 | 0.1 | 0.1 / 0.1 | same | normal | | none |
| regs | register-name header current | stale AwtoRegs.h | PASS 2 | 0.7 | 0.7 / 0.7 | same | normal | | none |
| regmap | register database current | stale regmap | PASS 10 | 3.6 | 3.6 / 3.6 | same | normal | | none |
| iram | IRAM names and placement | a variable in the wrong IRAM space | PASS 4 | 1.4 | 1.4 / 1.3 | same | normal | | none |
| rules | SDK is not patched by the build | a build step editing SDK source | PASS 0 | 0.1 | 0.1 / 0.1 | same | normal | | none |
| edid | the 3 EDID tables pass `edid-decode -c`, warnings only from the allow-list | a new edid-decode warning or failure | not yet run | ~0.3 | | | normal | | static (#321) |
| gensync, geninputs, gensavers, dwmodel | generated tables / model current | a stale generated table | PASS 0-2 | 0-0.6 | 0-0.6 | same | normal | | none |

## Totals per tier (gates only, build and flash excluded)

| tier | gates | wall s (parallel) | CPU s (sum) | load | when |
|---|---|---|---|---|---|
| OLD full set | 40 | 136 (9 killed) | ~570 (est.) | 35 | 2026-11-19 12:24 |
| NORMAL | 24 | 14 | 51 | 15 | every build / flash (a complete normal record is the flash gate) |
| EXTENSIVE (includes normal's gates) | 37 | 129 | 626 | 15-17 | on request, before a merge to main (`./dev.py merge-check`), nightly |

Build (separate): warm 40 s, changed tree 90 s, cold ~2.5 min. Flash (separate): unit 3 HDMI DDC 24 s, unit 2 DP AUX 116 s.
Clock matrix (350 / 175 / 87 MHz, timing gates, extensive): 0 FAIL cells, 176 s wall with the images built (`scripts/gate_matrix.py`).

## Where we were -> where we are
- Were: one gate set, 136 s wall under load 35, 9 gates killed by the stall guard, 'delay cal' counted PASS while failing, each gate's time dominated by simulated seconds.
- Now: two tiers. NORMAL is 24 gates, 14 s wall, 51 s CPU. EXTENSIVE is 37 gates, 129 s wall, 626 s CPU, all PASS at three clocks.
- Measured why gates are slow: the sim runs about 5x real time idle and about 1x during boot (25 M instr/s, 29 clk per instruction); gates cost their simulated seconds, not Python or boot.
- Cuts that keep every assertion: deadport one boot snapshot (35 -> 19 s CPU), inputrate big idle steps (55 -> 15 s), delays audit regex compile (49 -> 14 s CPU; normal = audit only, 1.7 s).
- Cuts that lose normal-tier coverage (Dan approved): keys, monitor, wake, crash, conwrap, conmode, sysm, sync, canary, menu, deadport, inputrate, bootsim_always and the long wdt cases are extensive-only.
- 'delay cal' is a real check now; the sim result is judged like the unit's.
- Open: test-timing scale (shorter OSD timeouts / holds / sample periods in test images) to bring the moved gates back into normal at ~1 s each; isr / ddc / menu minimal sweeps; delay choke point (design in the report, firmware timing change: branch + unit 3 check); pre-build cut (`pp_audit --check`, 24-32 s of every build); firmware pacing (separate agent) for exact fast-forward; `tests/test_pump_budget.py` image selection.

## Variant images (-D _AWTO_OSD_HWTEST, -D AWTO_CLOCK_MHZ=N)
- `dev.py build` writes `tmp/fw/<stem>.build.json` (defines) and `<stem>.xdata_layout.tsv` (the XDATA layout the image linked with); `scripts/image_variant.py` reads them (no file: map symbol `_g_stAwtoOsdHw` = hwtest, default clock).
- Variant = hwtest or clock != 350: the build never promotes the tracked bank / XDATA layouts (#268).
- Expectation per variant:
  - `xlayout`: the map is checked against the image's own layout file, not the tracked `fw/xdata_layout.tsv`.
  - `delays`: sites must be in `docs/delay-audit.tsv` or, for hwtest, `docs/delay-audit-hwtest.tsv`; a site in neither fails; FIX / UNKNOWN verdicts fail.
  - Every other gate: same thresholds as the default image.
- HWTEST XDATA is full (#268): `AWTO_MSG_RING` 32 (default 40) in HWTEST, OSD / Osw / flash-clk test ops share `g_stAwtoOsdHw.aucBuf`.
- Tests: `tests/test_gate_variants.py`.
