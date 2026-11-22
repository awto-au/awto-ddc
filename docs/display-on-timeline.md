# Display-on timeline: SEARCH (measure) -> DISPLAY SETTING -> ACTIVE

Scope: the "machine work" after INITIAL and the scan, units 1 (HDMI D2, line buffer) and 3 (HDMI D2, FRC, rotate 180), 4K59.99.
Issue: display-on-time item (d) (#284, #290). Sources: wait ring `g_stAwtoWait` (`scripts/wait_log.py`: every wait >= 2 ms with the caller's return address), sync log stage lines, `./dev.py ontime`.
Method: ISP reset x5 per unit, `wait_log.py` read right after `sync DONE`; image 582f4b27+ (= d2e991b0 for these paths). Times = MCU ms since boot in the ring, per-wait ms = ring `waited`.

## Result in one line

- Every ms of the measure stage and of display setting is a frame-event wait (`ScalerTimerWaitForEvent` IVS / DVS / DEN / IEN, 1 frame = 16.7 ms at 59.99 Hz); no blind `DelayXms` and no `PollingFlagProc` sits in either stage.
- All the bounds (90 ms per event, 168 ms DB apply) are never reached: every wait exits at its event. The cost is the NUMBER of frame waits the SDK strings together (12 in measure, 17 on unit 3 / 17 on unit 1 in display setting).
- The waits are SDK-lit counts ("wait 4 IVS", "2 IVS for measure"); none states a spec reason.

## SEARCH: measure stage (stage:measure 189..200 ms, 12 IVS waits)

| # | caller | wait | ms (U3 mean, 5 boots) | ms (U1) | kind | source of the number | shorten? |
|---|---|---|---|---|---|---|---|
| 1-2 | `ScalerMeasureInputInfo` :442 | 2 IVS, then pop the off-line measure | 7.6 + 16.8 | 16.4 + 16.8 | frame wait | SDK "wait for 2 raw IVS" (1 to start, 1 full frame measured) | no: 1 full frame is the hardware minimum |
| 3-4 | `ScalerMeasureInputInfo` :478 | 2 IVS, then pop auto-function | 16.4 + 16.6 | 16.5 + 16.8 | frame wait | SDK "2 latched IVS" | no (same) |
| 5-6 | `ScalerMeasureInterlaceCheck` :1079 | 2 IVS, V start of two consecutive frames compared | 16.8 + 16.6 | 16.5 + 16.6 | frame wait | SDK "delay until field stable" | no: two samples needed to see a field toggle |
| 7-10 | `ScalerFmtCnvFinalSetting` :276-279 | 4 IVS after F-to-P enable | 4 x 16.5 | 4 x 16.6 | frame wait | SDK "wait 4 IVS", no reason | YES: 4 -> 2 (commit mw2): the re-check below waits 2 more before its result is read |
| 11-12 | `ScalerMeasureInputInfo` :593 | 2 IVS, pop the auto-function re-check | 16.8 + 16.8 | 16.5 + 16.8 | frame wait | SDK "double-check auto-function" | no: verification of the F-to-P result |

Before the measure (scan, in the F-to-P-free part of the path, listed for completeness; not changed):

| caller | wait | ms | kind | note |
|---|---|---|---|---|
| `ScalerTMDSRxTMDSNormalPreDetect` | `DelayXms(6)` x3 | 6 each | blind SDK | SDK-lit; one per pre-detect try |
| `ScalerTMDSRxTMDSScanInputPort` | `DelayXms(2)` | 2 | blind SDK | PHY settle |
| `ScalerTMDSRxTMDSVideoDetect` | poll 0x71A4, bound 45 + 20 ms | 46 + 21 EXPIRED on the first try after reset, 2 ms after | bounded poll | the expiry is the first scan failing (no stream yet), not a wait to shorten |
| `ScalerTMDSRxFormatDetect` | poll 0x71CB, bound 130 ms | 30..33 | bounded poll, exits early | 25 % of the bound; follows the source |
| `ScalerMeasureSetOfflineMeasure` | `DelayXms(2)` (`_MEASURE_RESET_TIME`) | 2 | blind SDK | measure reset |

## DISPLAY SETTING

Unit 3 (FRC, rotate 180), `stage:display setting` 278..311 ms (the spread = frame phase at the first wait):

| # | caller | wait | ms mean | kind | source | shorten? |
|---|---|---|---|---|---|---|
| 1 | `_bs_call_sw` (scaler timing set) | DVS | 7.6 (2..15) | frame wait | SDK | no (phase alignment) |
| 2 | `ScalerMDomainControl` | DVS (DB apply) | 14.0 | frame wait | SDK | no: double-buffer apply |
| 3-4 | `ScalerMeasureGetInputRegionCountResult(_WAIT)` | 2 IVS | 4.8 + 16.8 | frame wait | SDK "wait for additional frames" | needed (value read by `ScalerFRCCompareIHFandDHF` next) |
| 5 | `ScalerFRCCompareIHFandDHF` | DEN_STOP | 10.2 | frame wait | SDK | no |
| 6 | `ScalerFRCControl` | DVS | 20.8 | frame wait | SDK | candidate (a) |
| 7-9 | `ScalerFRCControl` | 3 IVS "I-domain stable before FRC enable" | 3 x 16.7 | frame wait | SDK-lit | candidate: 3 -> 1..2, needs a capture-start proof (#issue) |
| 10 | `ScalerFRCControl` | DEN_START "FRC display enable together" | 16.6 | frame wait | SDK | no |
| 11-12 | `ScalerFRCControl` | 2 IVS "FRC run in single frame buffer" | 2 x 16.6 | frame wait | SDK-lit | candidate: 2 -> 1 (issue) |
| 13 | `ScalerFRCControl` | DVS "double buffer" | 16.0 | frame wait | SDK | no: DB apply |
| 14-15 | `ScalerDPLLFineTuneFrameSyncFrameBuffer` | 2 DVS | 16.6 + 16.3 | frame wait | SDK | needs the fine tune design (issue) |
| 16 | `ScalerMDomainControl` :"IVS wait 1" | IVS | 13.0 | frame wait | SDK | no |
| 17-18 | `ScalerRotationReset` | 2 IVS (rotation CW180 reset) | 16.6 + 16.7 | frame wait | SDK-lit | candidate: 2 -> 1 (issue); rotate 180 only |
| 19 | `ScalerMDomainControl` | IVS before the memory check | 16.3 | frame wait | SDK | no: the memory check reads the status after it |
| 20 | `ScalerMeasureUpdateOnlineMeasureResult` | `DelayXms(2)` | 2.0 | blind SDK | SDK | tiny |

Sum of the waits above: ~277 ms of the 278..311 ms stage; non-wait compute is ~5 ms.

Unit 1 (line buffer), `stage:display setting` 232..248 ms before the change:

| # | caller | wait | ms mean | note |
|---|---|---|---|---|
| 1 | `_bs_call_sw` | DVS | 8.0 | as unit 3 |
| 2 | `ScalerFRCEn` | IEN_STOP | 24.8 (18..31) | frame wait, SDK |
| 3 | `_bs_call_sw` | DVS | 8.2 | |
| 4 | `ScalerMDomainControl` | DVS | 16.4 | |
| 5 | `ScalerPLLSetDPLLFreqNfCascade` | DEN_STOP | 10.2 | |
| 6 | `ScalerDPLLFineTuneFrameSyncLineBuffer` | IVS | 15.6 | |
| 7-13 | `ScalerMDomainGetDisplayActiveRegion` + `ScalerMeasureGetDisplayRegionCountResult` | 7 DVS (first call 3, loop call 4) | 7 x 16.7 | the first call's result was overwritten: CUT (commit mw1) |
| 14-15 | `ScalerMDomainControl` | IVS + IVS | 13.0 + 16.8 | memory check path |
| 16 | `ScalerMeasureUpdateOnlineMeasureResult` | `DelayXms(2)` | 2.0 | |

Unit 3 vs unit 1 (~80 ms): FRC path = FRC control 8 waits (~134 ms) + rotation 2 (33 ms) + input count 2 (21 ms) + DEN_STOP; line buffer = IEN_STOP + 7 DVS of the active region measure.
No timeout expired in either stage (0 `EXPIRED` lines in 10 boots); the 100 ms bounds / 168 ms DB-apply bound are never close.

## ACTIVE tail (after display setting)

| what | ms | kind | note |
|---|---|---|---|
| colour set-up (`UserCommonInterfaceAdjustColorP...` DEN_STOP 9..14, `UserAdjustContrast` DEN_STOP 15..16) | 30..32 (`stage:colour set-up`) | 2 frame waits | SDK colour path: candidate (issue) |
| SDK ACTIVE timer | 100..115 ms, `ACTIVE wait:timer` | timer | closed: the picture is already up in the same ms (nothing visible waits for it) |
| panel video ready | 115 ms | panel T-chain | not shortened (panel sequence timings are out of scope) |
| backlight on delay | 100 ms from power-up | registry 127, by design | camera-measured, docs/camera-lcd-timing.md |

## Changes made (one commit each)

| commit | change | unit 1 (line buffer, ISP reset x5) | unit 3 (FRC, 25 DDC/CI locks + 5 resets) | unit 2 (DP, flash boot) |
|---|---|---|---|---|
| 8635cd4f | `ScalerDPLLFineTuneFrameSyncLineBuffer`: first display active region measure dropped (result overwritten in the loop), input count popped with `_WAIT` (2 IVS) | display setting 232..248 -> 182..199 ms; ACTIVE 1052..1056 -> 985..1006 ms | not on the path | line buffer: display setting 188 ms |
| 3662aa82 | `ScalerFmtCnvFinalSetting` 4 -> 2 IVS | timing 668 -> 633 ms; ACTIVE ~990 -> ~950 ms | stage:measure median 195 -> 161 ms (n = 25, 179..196 -> 144..164); ISP reset ACTIVE 1356..1393 -> 1299..1345 ms | measure 133 ms |

- Checks per commit: gates normal ALL PASS (includes irq-masks + delay budget gates, magic 0, xlayout), `./dev.py test` 758 passed; health 13/13 (unit 3: 25/25 locks, 0 `sync FAILED`); unit 1 and 2: `memory + timing gen check OK` in every episode.
- Unit 3 ISP resets 1-3 showed health 11/13 / FAIL once: the unit was in POWER SAVING (mode state 6) while another stream drove unit 3 (flash + host display); the scan before the changed code was identical to baseline ("after 1 retry"); health 13/13 on the re-check and in all 25 locks.
- Units 1 and 3 baseline = image 582f4b27+ (same code on these paths as d2e991b0).

## Left, and why

- FRC waits on unit 3 (3 IVS before FRC enable, 2 IVS single-frame-buffer, DVS waits, rotation reset 2 IVS, fine tune 2 DVS): no status bit proven, only the SDK count; measurement plan in #314.
- Colour set-up 2 DEN_STOP (31 ms) and the interlace check 2 IVS: #314.
- Auto-function pops (3 pairs of IVS): a done-bit poll would save ~half a frame each; regdb name + bound needed (#314).
- ACTIVE tail 100 ms SDK timer: closed (the picture is already on screen in the same ms); panel video ready 115 ms, backlight delay 100 ms (registry 127), panel T1..T6: not touched (spec / by design).
- TMDS scan waits (DelayXms 6 / 2, video detect 45 + 20 ms polls, format detect 130 ms poll exits at 30..33 ms): scan, outside this task; the 46 + 21 ms EXPIRED video-detect polls are the first scan failing right after reset.
- Unit 1 DDC/CI sleep trigger does not work (ddcutil sees no monitor on bus 18), so unit 1 was measured with ISP resets only.
