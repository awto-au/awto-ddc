# Sync log: DONE / FAILED / link health lines

Issue draft: `tmp/scratch/issue-sync-done.md`. Related: #257, #253, #139, #144. Log texts: `fw/awto/sync.tsv`; ring: `fw/log/sync.c`; decoders: `scripts/sync_log.py`, `fw/osd/console.c`.
Existing sync lines stay (C1 / C6 / C2 / F0..F4 / FC / system machine); the new lines summarise them and are not repeated by them.

## Goal
- One line per sync episode and port that says the sync is DONE, with the step times and the retry evidence.
- One line when a sync cannot complete (FAILED), one when the picture is lost after ACTIVE. Never silent.
- One link-health line shortly after ACTIVE (HDMI: SCDC ratio, scrambling, character errors; DP: rate, lanes, lane status).

## Lines (examples from the sim image, `sync_sim`)
- `sync DONE D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok 120ms, timing 380ms, ACTIVE 452ms`
- `sync DONE D2 HDMI 2.0 (1:40), after 1 retry: PHY 31ms (2 set-ups), scan ok 640ms, timing 700ms, ACTIVE 810ms`
- `sync DONE D1 DP, first try: link trained 120ms (1 training), scan ok 150ms, timing 380ms, ACTIVE 452ms`
- `sync link D2 HDMI 2.0 (1:40): SCDC ratio 1:40, scrambling on, scrambled data seen, errors 0/0/0, 100ms after ACTIVE`
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
- A new episode (switch, wake, power key) clears everything.

## Ring layout (8 B entry: id, arg, ms16, value32)
- `EF` sdone: arg = port idx (0 = D1) | kind << 2 (0 DVI, 1 HDMI 1.4, 2 HDMI 2.0, 3 DP) | scan retries << 4 | set-ups / trainings << 6 (each 0..3). Value = scan ok ms << 20 | timing ms << 8 | PHY / link ms (0xFF none); stamps 12-bit, 0xFFF = unseen.
- `FF` slink: arg = port idx | kind << 2 | flags << 4 | 0x80 n/a. HDMI flags: bit 0 scrambling on (SCDC 20h), bit 1 ratio 1:40 (SCDC 20h), bit 2 scrambled data seen. DP flags: lane count. Value = ms after ACTIVE << 24 | HDMI errors ch0 / 1 / 2 (255 max each) or DP rate << 16 | DPCD 202h << 8 | 203h.
- `FE` sfail: arg = reason (F2 scan code, 0x00, 0x40, 0x41), value = port << 16 | ms (fmt `pms`; rows per reason in `sync.tsv`; texts duplicate the F2 reason phrases once).
- Fmts `sdone` / `slink` (31 / 32): `scripts/gen_awto_sync.py` (width check: 2 console rows), `fw/osd/console.c` `AwtoPutSdone` / `AwtoPutSlink`, `scripts/sync_log.py` `sync_done` / `sync_link`. Class: DONE normal, link timing, FAILED error.

## Link health registers (regdb `re/regdb/RTD2795T-CG.tsv.gz`; D2 = page 71, D3 = page 72)
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
