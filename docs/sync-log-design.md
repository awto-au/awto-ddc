# Sync log: DONE / FAILED / link health lines

Issue draft: `tmp/scratch/issue-sync-done.md`. Related: #257, #253, #139, #144. Log texts: `fw/awto/sync.tsv`; ring: `fw/log/sync.c`; decoders: `scripts/sync_log.py`, `fw/osd/console.c`.
Existing sync lines stay (C1 / C6 / C2 / F0..F4 / FC / system machine); the new lines summarise them and are not repeated by them.

## Goal
- One line per sync episode and port that says the sync is DONE, with the step times and the retry evidence.
- One line when a sync cannot complete (FAILED), one when the picture is lost after ACTIVE. Never silent.
- One link-health line shortly after ACTIVE (HDMI: PHY mode, scrambled data seen, raw SCDC 20h bits, character errors; DP: rate, lanes, lane status).

## Lines (examples from the sim image, `sync_sim`)
- `sync DONE D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok 120ms, timing 380ms, ACTIVE 452ms`
- `sync DONE D2 HDMI 2.0 (1:40), after 1 retry: PHY 31ms (2 set-ups), scan ok 640ms, timing 700ms, ACTIVE 810ms`
- `sync DONE D1 DP, first try: link trained 120ms (1 training), scan ok 150ms, timing 380ms, ACTIVE 452ms`
- `sync link D2 HDMI 2.0 (1:40): scrambled data seen, SCDC 20h as the source left it: ratio bit 0 scrambling bit 0, errors 0/0/0, 147ms after ACTIVE`
- `sync link D1 DP HBR2 x4: lanes CR 4/4, EQ 4/4, symbol lock 4/4, 100ms after ACTIVE`
- `sync FAILED:CDR not locked at 1:10, retry 1:40 not done (D2, 3012ms)`
- `sync FAILED:signal lost, the picture was up; time = since ACTIVE (D2, 5000ms)`

## Fields
- Times: `scan ok` and `timing` are `+N ms` since the search reached the port (the episode start for a fixed port; the F3 `search left the port` line shows the dwell on earlier ports). `ACTIVE` is ms since the episode start (the console time column), FAILED ms too.
- `first try` / `after N retries`: N = failed scan calls this port visit (F2 fail codes 12..17, 20..24, 31..37; waits 10 / 11 / 30 not counted). 0 = the first ratio worked (1:10 vs 1:40 retry shown by the F2 fail lines above).
- `PHY N ms (M set-ups)`: span of `ScalerTMDSPhySetDeferred` calls that had work (last span; M counts them, 3+ saturates). `-` = no PHY set-up in this sync (fast path / wake hold).
- DP: `link trained N ms (M trainings)`: N = the FC line's ms; M = training-pattern-1 starts counted in the DP EXINT (`isr_g_ucAwtoDpLtN`), per episode / visit.
- `scan ok`: first `scan ok` (F2 01) after the port visit started = CDR locked + DFE + video detect, the SDK scan order. The CDR lock itself has no cheap production stamp (the test probe `fw/diag/phyprobe.c` stamps inside the TMDS files that `rx-share` rewrites).
- `timing`: first timing-confirm (C5 / F4) of the visit. Unseen stamp prints `-`; a 12-bit stamp saturates at 4094 ("4094+ms").
- Clock detect (C1 / C6) is not repeated: its own line carries its time.

## Hooks (no edit of RL6449_Series_TMDSRx2/Rx3 / SeptPhy)
- PHY span: `ScalerTMDSPhySetDeferred` in `RL6449_Series_TMDS.c` (the dispatcher every caller goes through, also the AWTO_TMDS_PHY_PUMP): `AWTO_SD_PHY_BEGIN()` only when a Rx2 / Rx3 `PhyPend` is set, `AWTO_SD_PHY_END()` after.
- Scan ok / retries / last reason: `AwtoSyncScan` (sync.c, already called per scan). Timing: `AwtoSyncTiming`. Port visit reset: `AwtoSyncVisit`. Episode reset: `AwtoSyncBegin`.
- DONE / FAILED: `AwtoSyncSw` mode events ACTIVE / NO SIGNAL / NO SUPPORT (POWER SAVING is by design: no line).
- DP trainings: one `isr_g_ucAwtoDpLtN++` at the TP1 case of `RL6449_Series_DP_INT.c` (EXINT0; byte counter only, no ring write in the ISR).
- Link health: `AwtoSdTick` from `AwtoSwPoll` (every pass, a single flag test while nothing is pending). Non-blocking: reads once `AWTO_SD_HEALTH_MS` (100 ms ~ 6 frames at 60 Hz, a sampling time not a wait) after ACTIVE. No delay is added; `docs/delay-budget.tsv` unchanged.

## State machine (g_ucAwtoSdFlags)
- ACTIVE and no DONE since the last ACTIVE: write DONE, arm the health read, clear FAIL.
- NO SIGNAL / NO SUPPORT with DONE set: write `FAILED:signal lost` (ms since ACTIVE), clear all stamps and flags: the next ACTIVE writes a new DONE (re-sync inside one episode).
- NO SIGNAL / NO SUPPORT without DONE: FAILED once per episode (reason = last scan outcome code, `0x00` nothing detected, `0x40` no support). Search cycles in NO SIGNAL do not repeat it.
- A new episode (switch, wake, power key) clears everything; picture lost (`K_LOST`) keeps it.

## Ring layout (8 B entry: id, arg, ms16, value32)
- `EF` sdone: arg = port idx (0 = D1) | kind << 2 (0 DVI, 1 HDMI 1.4, 2 HDMI 2.0, 3 DP) | scan retries << 4 | set-ups / trainings << 6 (each 0..3). Value = scan ok ms << 20 | timing ms << 8 | PHY / link ms (0xFF none); stamps 12-bit, 0xFFF = unseen.
- `FF` slink: arg = port idx | kind << 2 | flags << 4 | 0x80 n/a. HDMI flags: bit 0 scrambling on (SCDC 20h), bit 1 ratio 1:40 (SCDC 20h), bit 2 scrambled data seen. DP flags: lane count. Value = ms after ACTIVE << 24 | HDMI errors ch0 / 1 / 2 (255 max each) or DP rate << 16 | DPCD 202h << 8 | 203h.
- `FE` sfail: arg = reason (F2 scan code, 0x00, 0x40, 0x41), value = port << 16 | ms (fmt `pms`; rows per reason in `sync.tsv`; texts duplicate the F2 reason phrases once).
- Fmts `sdone` / `slink` (31 / 32): `scripts/gen_awto_sync.py` (width check: 2 console rows), `fw/osd/console.c` `AwtoPutSdone` / `AwtoPutSlink`, `scripts/sync_log.py` `sync_done` / `sync_link`. Class: DONE normal, link timing, FAILED error.

## Link health registers (regdb `re/regdb/RTD2795T-CG.tsv.gz`; D2 = page 71, D3 = page 72)
- SCDC 20h is printed as raw evidence only: sources (Intel / NVIDIA) leave `TMDS_Bit_Clock_Ratio` 0 while the PHY runs 1:40 (docs/input-sync-timeline.md section 5; unit 1 4K60: PHY 1:40, scrambled data seen, SCDC bits 0). The PHY mode in the line head (1:10 / 1:40) and `scrambled data seen` are the authority.
- SCDC 20h via the SCDC data port (`HDMI_CTRL_39` index `PORT_PAGE71_HDMI_SCDC_20`): `tmds_clk_ratio` bit 1, `scram_en` bit 0 (what the source wrote).
- `HDMI_CTRL_01.scram_det` bit 3: sink detected scrambled control codes.
- CED: `HDMI_CTRL_0C.err_popup` bit 7 latches, then `err_cnt_ch0 / 1 / 2` = `HDMI_CTRL_0C..11` (15-bit each, MSB regs bit 6..0). Counter source is `HDMI_CTRL_0B.err_cnt_sel` as the SDK leaves it (0, lock / unlock counter).
- Read with EX0 off for the whole access (the TMDS ISR uses the same SCDC / CED ports): 1 data-port read + 1 popup + 6 byte reads.
- HDMI on a port without SCDC / CED (DVI): the line says `no link health on this input`.
- DP: `ScalerDpGetLinkRate` / `ScalerDpGetLaneCount`, DPCD 202h / 203h (sink-held lane status of the last training, bit 0 CR, 1 EQ, 2 symbol lock per lane).
- Not readable: the CDR lock instant, and BER beyond the CED counters (no register for symbol errors on DP in the regdb names used here).

## Cost
- XDATA: 14 B (stamps 8 B, counters 4 B, flags 1 B, DP trainings 1 B); numbers in the issue draft.
- Idle cost per pass: one flag test in `AwtoSwPoll`; PHY dispatcher: one OR + branch.

## Limits
- Per episode a re-sync without a mode change through NO SIGNAL (receiver glitch inside ACTIVE) writes no second DONE.
- `PHY` time and `scan ok` belong to the port the search visited last before ACTIVE.
- DP trainings count TP1 starts: a source that retrains with a new TP1 write counts each; one counted by the EXINT even before the main loop saw it.
- A wake search that ends in POWER SAVING writes no FAILED line: the system line `wake search found no source` states it (a FAILED line there splits the system transition from its LED line: panel_sim LED gate).

## Console time columns and episode starts (Dan 2026-11-27, awto-ddc#354)
- Columns, 22 cells + ':' (`AWTO_LOG_TIME_W`, text at `AWTO_LOG_TXT0` = 23): real time, space, delta (`fw/osd/console.c` `AwtoPutReal` / `AwtoPutDelta`, host `sync_log.real_col` / `fmt_delta`):
  - real time, 13 cells: ` HH:MM:SS.mmm` = host clock (line of this boot, a host sync known); `uHH:MM:SS.mmm` = uptime of the line's boot; `u-0:00:00.ddd` = a line re-based before the Timer2 start; from 100 h `uhhhh:mm:ss.t`.
  - this boot: the line's absolute ring index >= `g_ulAwtoBootAbs` (index of this boot's `D0` line, set at the push, moved by `AwtoDlInit`); older lines keep their boot's uptime.
  - delta, 7 cells: ms since the ring line above. Up to 999 ms `+xxx ms`; up to 99.9 s `+xx.x s`; up to 9999 s `+xxxx s`; then `+xxxx h`; `-` = a step back (Timer2 re-base). Blank = no line above.
- Full times: DRAM log images carry 32-bit fw ms per line (tail entry bytes 8..9, DDR entry): deltas and real time are exact over any gap; no wrap row is needed there.
- `_AWTO_DRAM_LOG` off (16-bit ring, no gate builds it): real-time column blank, delta = 16-bit step (a gap of 65.5 s or more wraps unseen).
- Host decoders (`sync_log.py`, `dram_log.py`): the same columns, then `[fw <32-bit ms> ms, ring <ms16>]`. A version 3 (16-bit) delta is used only between full times it lands on exactly (C0 / D8 anchors, now); otherwise a red row `-- relative time reset: counter wrap --`, blank delta and real time on the next line (Dan 2026-11-27).
- Joined rows (`AWTO_LN_PAIR`, host `JOIN_PAIRS`): a listed next line within `AWTO_LN_JOIN_MS` (3 ms: pushes of one call) shares the row after ` | `; the live draw leaves a newest group leader for one call (the next push or the OSD poll), no time wait.
  - monitor heartbeat rows (not an ADC move): `monitor: IOSC 2001 | 300/s gap 12.6ms | free 301/s busy 39% worst 1.937ms | up 1150s stk D4`;
  - `frame buffers` + `memory`; `display frame rate` + `scaling` + `FRC width`.
  - Delta / real time of a joined row = its first line; the next row's delta counts from the last joined line.
  - Not joined: the backlight on / pin / PWM lines (joined they still take two rows), an ADC move.
- Episode start row is never lost at the top (Dan 2026-11-27): `g_ulAwtoEpAbs` = absolute index of the current episode's start row (boot line / start BEGIN). A console open / redraw whose backfill starts after it draws that row first, from the DDR (`g_ucAwtoAtLaps` past a seq wrap), with `(N lines not shown)` before the rule; the backfill follows. Cost: XDATA 9 B (EpAbs 4, laps 2, hidden count 2, jump 1), no pass cost when the console is closed.
- Host one-episode read (DRAM log): every line of the episode from the DDR, up to 175 (seq window; a unit 3 boot is ~127), not the newest 88; `--dram` reads any length.
- Episode start = a red row `-- text ---` to the row end (`AWTO_T_STYLE_EPOCH` = the alert style, palette `AWTO_PAL_DIAG_ALERT`). Coloured text row: the font is ASCII (no box-drawing glyph), and an OSD window per row is not available.
- Starts and their zero (the delta on the red row):
  - boot line (`D0`, first of the power-on episode): MCU reset = fw ms 0; lines logged before Timer2 starts are re-based and can be a few ms below 0.
  - `C0` BEGIN switch / wake / power key / picture lost: the BEGIN itself (0). Each is pushed where the trigger is seen: VCP 0x60 / key / selector (switch), the wake poll's trigger pass or the SDK power-status change (wake), the judge pass (picture lost).
  - Not a start: the power-on BEGIN (inside the boot episode), a switch inside an unsettled power-on / wake (value bits 31..24 = `AWTO_SYNC_BEGIN_IN`).
- Picture lost (`AWTO_SYNC_K_LOST`, `C0 05`): `SysJudge.c` when the judge check resets ACTIVE (any cause) or DISPLAY SETTING (source unstable) to SEARCH. No console auto-open; the sync-done state stays (its `FAILED:signal lost` line comes at NO SIGNAL). The L1 hold path is unchanged (signal back = a wake episode).

## Gap lines (#284: where the time goes; no behaviour change)
- `INITIAL:first exit check at Nms` / `longest gap between checks Nms` / `SDK <source|mode|OSD|other> flag set until Nms` (id 93, ms since INITIAL began, 4 ms steps): INITIAL ends when no SDK change flag is set at a judge pass; a flag line is written only for a flag seen set; a long gap = the main loop was blocked between passes (see the slow-wait / long-block lines).
- `search reached Dn: predetect on|off, cable detected|no cable` and `search left Dn after Nms: no signal|predetect seen, N edges[, dwell re-armed]|port disabled, skipped` (F3, fmt `visit`): the edge count is a per-visit counter (the repeated C1 / C4 lines collapse in the ring). Visit lines stop after `AWTO_SCAN_LOG_MAX` visits per episode (counted at reached).
- `Dn search dwell re-armed, N after reaching` (id 95, warning): predetect on a searched port cancelled the SDK dwell and armed the reactive time (SDK: 4.5 s TMDS, 4 s DP, `SysSourceSearchTimeInitial`), written from `SysSourceJudge`. This is the #290 mechanism.
- `ACTIVE wait:timer Nms, panel ready Nms` (id 94, both since the display setting ended): the SDK ACTIVE timer (`_WAIT_TIME_TO_ACTIVE_*`, 100 ms) and the first pass the panel video was ready; written before `sync DONE`.
- `EDID load start:HPD mask N` / `EDID load end:took Nms` (FA 03 / 04, around `UserCommonInterfaceLoadEmbeddedEdidData` at boot, #289) next to `EDID channels on` and the HPD lines.
- HPD edges (FA 00 / 01) are sampled every main-loop pass, now also in power saving; they are written without repeat collapse and carry the ring ms.
- Host join (#284): `synclog --json` carries `fw_now` and per entry `fw` / `poll_wall` (read time of the fw clock minus the ms since the entry); `unit_log` lines without a host sync use it (marked `~`). A warm reset restarts the fw clock, so host-synced time needs `host_time.py` after the reset.
- Cost: XDATA 18 B (visit 3, INITIAL 8, tail 5, EDID 2), no new delay; per pass: one compare in `AwtoSyncDetect`, one call in the INITIAL judge pass.

## Main-loop stage timing (#311: where a slow pass goes; no behaviour change)
- `AWTO_PSTG(id)` (RL6449_Project.h) after each stage of `SysMainPass` (SysMain.c; the pass body moved out of `main()`: common bank full) and after the sub-calls of the console open (`AwtoDiagConsole`, `osd_tc_open`, `AwtoTextOpen`). `AwtoPassStamp` (sync.c, pinned common) reads the Timer2 ms counter (`usT2Isr`, re-read when torn); under `AWTO_PSTG_NOTE_MS` (4 ms) it only stores the stamp.
- A segment >= `AWTO_PSTG_SLOW_MS` (20 ms, `#ifndef` constant, `-D` overrides; no registry row: XDATA / NVRAM) writes `slow pass stage <name> took Nms in <STATE> (#C)` (id 96, arg = stage id, value = state << 24 | per-boot count << 16 | ms). The count makes every line unique: it never collapses. State = system state when the segment ended.
- Longest pass per state (INITIAL, SEARCH, DISPLAY SETTING, ACTIVE; passes >= 4 ms, 4 ms units) and its longest segment: `boot passes:<STATE> longest Nms in stage <name>` (id 97), once per boot before the first `sync DONE` (ACTIVE row not yet filled then).
- Names and line words: `AWTO_PSTG_NAMES` (RL6449_Project.h, ids < `AWTO_PSTG_WORD0`, then the words); firmware table `tAwtoPassName` + reader in bank 6 (bank 11 sync text and common are full), host `sync_log.pass_names()`, fmt `pass` (34, `AwtoPutPass` / `pass_value`).
- A pass is attributed to its state at the end: the pass that moves AC ON -> INITIAL is an INITIAL pass.
- Cost: XDATA 15 B (+4 B layout), flash common -185 B (main shrank), cycles/pass +25 (sim, `./dev.py stats`). Findings and boot table: awto-ddc#311.

## DRAM log (#284 / #291: history in the DDR)
- `_AWTO_DRAM_LOG` (default ON): ring = 32-line XDATA tail + DDR ring (docs/dram-log-design.md). Collapse, episodes, console and host decoders unchanged (`AwtoSyncAt`, `sync_log.read_ring` version 4).
