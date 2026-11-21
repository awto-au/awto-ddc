# Input sync timeline and SDK source-setup decisions

Log: sync ring (`fw/log/sync.c`), texts `fw/awto/sync.tsv` rows F0..FC, decoders `scripts/sync_log.py`, `rtd_diag.py --sync`; same line on the diag console.
Issues: #78 (wake time), #139 (sync log), #239 (350.8 MHz boot), #256 / #147 / #197 (TMDS).

## New log events (one line per stage / decision)

| id | arg | value | text (example) |
|---|---|---|---|
| F0 | why: 0 fixed, 1 auto + last used, 2 auto + other, 3 other | port, source | `input taken:D2 HDMI (fixed port: selector / VCP 0x60 / menu / setting)` |
| F1 | stage 1 measure, 2 display setting, 3 colour, 4 first-active | ms | `stage:display setting took 117ms` |
| F2 | scan outcome (below) | port, ms in the scan call | `scan fail:CDR not locked at 1:10, retry 1:40 (D2, 3ms)` |
| F3 | 0 | port left, ms on it | `search left the port:D3, 2012ms` |
| F4 | link kind << 3 or colour space | bit depth | `format:HDMI 2.0 (1:40), RGB, 8 bit` |
| F5 | frame buffer rule, +0x10 = SDK and register disagree | buffers the register holds | `frame buffers:SDK 1 (default); register says 1` |
| F6 | select / config | bits per pixel | `memory:work mode (FRC), frame sync frame buffer, 24 bit per pixel` |
| F7 | SDK `_x_IVF` select | display rate, 0.1 Hz | `display frame rate:1 IVF, display = input rate, 60.0Hz` |
| F8 | H * 3 + V scale (none / up / down) | display W x H | `scaling:H none, V none, display 3840x2160` |
| F9 | 0 none, 1 DDR bandwidth, 2 DDR space | FIFO width, limit | `FRC width:3840 of 4096 px (not limited)` |
| FB | wait kind (+0x10 expired) | register or event, ms | `EXPIRED poll (register) + took:71A4 45ms` |
| FC | 1 | port, ms | `DP link trained:D1, 120ms after the loop first saw it training` |
| FA | 0 / 1 HPD pin low / high, 2 EDID channels enabled | port / pin mask (bit0 = D1) | `D2 HPD high`, `EDID channels on:HPD pin mask 6 (bit0 = D1)` |

HPD lines: pins polled once per main-loop pass (`AwtoEdidPoll`, <= 2.5 ms), the first pass logs all three levels; `E7` (`Dn EDID read`) is the DDC / AUX read latch, same poll.

Scan outcome codes (F2 arg, set by `AWTO_SCAN_STAGE` at the SDK step, one line per change of outcome per port, 12 lines per episode):
- 01 ok; 02 the PHY set-up took 1:40 from the per-port memory (line before the outcome); 10 HPD event running; 11 PHY not set / freq detect not stable; 12..14 CDR / DFE / video detect failed at 1:10 (retry 1:40); 15..17 same at 1:40 (retry 1:10)
- 20 no RGBHV; 21 DE only; 22 deep colour PLL; 24 timing measure failed
- 30 DP link not trained; 31 HDCP; 32 video stream; 33 MSA; 34 video info; 35 display format; 36 stream clock; 37 FIFO delay

Cost (build 2026-11-20, unit 2 image, rebased on 42b5373):
- ring 48 -> 80 entries (+256 B XDATA, the panel_sim ring-read gate needs it): XDATA free 400 B -> 212 B of 7324 B
- code: 14 new functions, ~1.5 KB in banks with free space (bank_layout.tsv updated); text rows 124 in bank 11
- idle cost: speed_bench cycles per pass 163228 -> 163240 (12 passes, +1 cycle per pass); hooks run only on a predetect, a search-port change, a stage end
- DATA overlay path unchanged (70 B): slow-wait lines use `AwtoSyncPushQuiet` (no live console draw in the deepest call chain; the console catches up next pass)

## SDK source-scan / sync path (stage list, `fw/sdk/Kernel`)

SDK reading = hypothesis; the log lines are the measurement.

| stage | where | note |
|---|---|---|
| cable / 5 V / HPD detect | `System/Code/SysSource.c` `SysSourceCableDetection` (3694 before edits) | cable change resets the search |
| search port switch | `SysSource.c:1547` `SysSourceSwitchPort`; visit line in `SysSourceHandler` :252 | dwell per port `_SOURCE_DEFAULT_SEARCH_TIME_HDMI` 2 s, `_DP` 3 s (`Project/Header/RL6449_Project.h:2160-2162`) |
| predetect | `SysSource.c:412` `SysSourceDetectPort` -> `ScalerTMDSNormalPreDetect` / `ScalerDpNormalPreDetect` | one search port per pass |
| TMDS scan | `RL6449_Series_TMDSRx2.c:3601` (Rx3 same, `RL6449_Series_TMDSRx3.c`) | 2 ms PHY settle; CDR / DFE / video-detect chain; 1:10 / 1:40 retry toggle `:3684` |
| TMDS video detect | `ScalerTMDSRx2_SeptPhy.c:134` | polls 45 ms (RGBHV) + 20 ms (DE) |
| TMDS packet detect | `RL6449_Series_TMDSRx2.c:3438` | polls 130 ms (AVI + GCP), 180 ms each; the colour depth is read once after them (no 130 ms wait; re-checked in `TMDSStableDetect`, #216) |
| TMDS format detect | `RL6449_Series_TMDSRx2.c:4210` | poll 130 ms |
| DP scan | `ScalerDPRx1_SeptPhy.c` `ScalerDpRx1ScanInputPort`: HDCP, stream, MSA, video info, display format, stream clock, FIFO delay (`AWTO_SW_MARK` 30..36) | link training itself runs in the ISR (`ScalerDPRx1_INT_SeptPhy.c`) |
| judge | `SysSource.c:1278` `SysSourceJudge` (probe 19, F0 line) | |
| measure | `System/Code/SysJudge.c` `SysMachineWork` (probes 17 / 18, F1 stage 1) | `ScalerMeasureInputInfo` |
| display setting | `SysJudge.c` probes 14 / 15, `SysMode.c:129` `SysModeDisplaySetting` -> `ScalerMDomainControl` (F1 stage 2, F5..F9) | |
| colour | `UserCommonInterfaceAdjustColorProc` (F1 stage 3) | |
| first active, backlight | `SysJudge.c` probes 11 / 12 (F1 stage 4), panel machine lines | |

### SDK choices made during source setup (all logged at display-setting done)

| choice | made in | what it is | log |
|---|---|---|---|
| frame buffer count | `RL6449_Series_Scaling.c` `ScalerScalingUpdateFIFOScalingSize`: default 1; rotation CW180 / vertical mirror with DVF != 1 IVF gives 2 or 3; not frame-sync + `ScalerFRCCheckDoubleFrameBuffer` gives 2 | `GET_MEMORY_FRAME_BUFFER`, registers P5_27 / P5_29 (read back by `AwtoFbRegCount`) | F5, mismatch flagged |
| memory config / select | `ScalerMDomain.c` `ScalerMDomainMemorySettings`: `GET_MEMORY_CONFIG` (line buffer vs work mode), `GET_MEMORY_SELECT` (frame sync line buffer / frame buffer / free run / M-N) | decides FRC use | F6 (also E3 on change) |
| display frame rate | `ScalerDisplaySelectDVFMode` | `GET_MEMORY_DVF_SELECT` 1 / 2 / 3 / 2.5 / 5/4 / 6/5 IVF, `g_usDVFreq` | F7 |
| scaling up / down | `ScalerMDomainSetScaling` | `GET_H_SCALE_UP/DOWN`, `GET_V_SCALE_UP/DOWN` | F8 |
| FRC width clamp | `Scaling.c` `ulHSDBW` (DDR bandwidth) and `ulHSDSpace` (DDR rows) | FIFO input width limited to the smaller | F9 |
| rotation | `ScalerRotationCheckStatus`, `GET_ROT_TYPE` | E4 lines on change; rule rows of F5 name the rotation cases | E4, F5 |
| colour space / depth | scan functions, `GET_COLOR_SPACE`, `GET_COLOR_DEPTH` | | F4 |
| HDMI 1.4 / 2.0 | `GET_TMDS_RXn_HIGH_SPEED_MODE` (1:40 PHY mode) | | F4, F2 retry rows |
| OD, FreeSync, VRR | `_OD_SUPPORT`, `_DP_FREESYNC_SUPPORT`, `_HDMI_FREESYNC_SUPPORT` all `_OFF` in this build | not built: nothing to log; `usFRCBW` is only computed by the OD path | none |

## Measured timelines


Conditions: 2026-11-20, image = branch sync-log-inputs (42b5373 + sync log), MCU 350.8 MHz default clock, panel eDP 4K, host Intel DP-1 (unit 2) / NVIDIA HDMI (unit 1) at 3840x2160 60 Hz RGB 8 bit; console_mode Always; ring read over the debug link after each episode (`scripts/sync_log.py`).
Power-on = warm reset (ISP identify): VDD stays on; the relay power cycle is disabled (#339), so a cold boot was not measured.
Input switch was not measurable: each unit has one cable, a switch to an uncabled port is refused (`refused:no cable on D2`); switching to the same port logs nothing.
Times: ms since the episode start (first boot line 113 ms after the timer starts), 2 runs per unit agree within 20 ms (unit 1 runs a / b), unit 2 one run plus the earlier sl3 runs.

### Power-on to picture (stage x ms, from the first main-loop pass)

| stage | unit 2 DP D1 | unit 1 HDMI D2 (2.0, 1:40) | what the time is |
|---|---|---|---|
| boot to first pass | 168 | 167 | MCU / GPIO / pin set-up |
| INITIAL (panel VDD T1 + eDP HPD + link) | 104 (to SEARCH at 277) | 303 (SEARCH at 475) | panel T1 76 ms, HPD 77 to 90, link 76 to 83 (45 ms delay inside) |
| SEARCH start to predetect on | ~480 (277 to 757, source side: Intel trains after its EDID read at 402) | 2 (477 to 478) | host / source speed |
| scan call (predetect true to port found) | 330 | 69 failed at 1:10 + 65 to 73 ok at 1:40 | DP: 242 ms are 7 waits (below); HDMI: 2 expired video-detect polls (71A4, 46 + 21 ms) then the 1:40 try |
| measure | 160 | 181 to 198 | `ScalerMeasureInputInfo` |
| search total (SEARCH state) | 848 to 972 | 356 to 434 | |
| display setting | 230 to 249 | 230 to 248 | M-domain set-up 190 ms to DCLK fine tune final offset, IVS wait 30 ms, check |
| colour set-up | 30 | 29 | |
| wait to ACTIVE after colour | 103 | 107 to 110 | DISPLAY SETTING state total 375 to 389 vs 261 of work |
| first-active work | 1 | 1 | audio unmute delay 20 ms follows |
| **picture (ACTIVE) at** | **~1510** | **1206 to 1378** | from the first boot line |

DP scan waits (unit 2, all in `ScalerDpRx1ScanInputPort` and what it calls): delay 45, MN meas poll `PB8_58` bit 6 (22 to 32 ms) x3, delay 35, delay 45, delay 35 = 242 of 330 ms. HDMI: poll `P71_A4` (TMDS_CTRL) RGBHV 45 ms + DE 20 ms both expire at 1:10 (the 4K60 source needs 1:40), then `P71_CB` / `71CB` poll 50 to 66 ms at 1:40.

### Wake (unit 2, DDC/CI power on, DP link already up), request to picture

| stage | ms |
|---|---|
| request to scan call start | ~100 (30 + 45 + 35 delays in front of the DP waits) |
| scan call | 325 |
| measure | 141 |
| display setting + colour | 244 + 32 |
| wait to ACTIVE | 103 |
| total, request to picture | 945 |

### Findings

- The DP wake after a DDC/CI sleep stayed in WAKE SEARCH for 102 s with no scan line (state `in WAKE SEARCH for 102104ms`, host DPMS unchanged); the scan started the moment the DDC/CI power-on request came. Candidate for #78: the wake search does not scan D1 until another system request arrives. Evidence: ring `tmp/scratch_u2_wake2.txt` (not kept in git; sequence reproduced from the ring dump of 2026-11-20T19:52).
- `scaling:H up, V none` at 3840x2160 input on a 3840x2160 panel: the SDK sets the H scale-up flag with equal sizes (both units, all runs). Not explained yet.
- `frame buffers: SDK 1, register 1`, memory = line buffer mode, no FRC at 4K60: the frame-buffer rules never fire in this configuration; F9 (FRC limit) is only logged in work mode.
- Display frame rate decision `60.1 Hz` (`g_usDVFreq`) against measured 59.991 / 59.995 Hz: the SDK target, not the measurement.

### Top slow stages and proposed fixes (1 and 5 implemented, see below)

1. [done, see above: 330 -> 302 ms] DP scan call, 330 ms (unit 2): frame-time delays are `_DP_ONE_FRAME_TIME_MAX` 45 ms (a 23 Hz frame, `ScalerCommonSyncInclude.h:161`) x4 plus 35 ms x2 and three 22 to 32 ms `MN_MEAS` polls. At 60 Hz one frame is 16.7 ms. Fix: derive the delay from the measured frame period (MSA / `PB8_58` count), expected saving 100 to 150 ms. Needs a hardware check that the DP receiver locks with the shorter waits.
2. DISPLAY SETTING to ACTIVE: 375 to 389 ms for 261 ms of work; 103 to 110 ms between colour done and ACTIVE (panel video ready gate, `SysJudge.c` DISPLAY -> ACTIVE). Fix: find what the machine waits for (panel machine VIDEO state or a pass period) and release it at the colour step.
3. M-domain set-up / DCLK fine tune, 190 ms of the 230 to 249 ms display setting (final offset stable at 34808 to 34810 on every run, both units). Fix: cache the final offset per timing and start the fine tune from it.
4. Measure, 141 to 198 ms (`ScalerMeasureInputInfo`): for DP the MSA already gives H/V totals. Fix: skip the full re-measure when the MSA timing is stable (fast path exists only for a cached input switch).
5. [done for switches only: memory is RAM, boot unchanged] HDMI 2.0 first try at 1:10, 69 ms lost per boot and per switch: the HDMI port expires two polls (46 + 21 ms) before the 1:40 retry. Fix: remember the last mode per port (`GET_TMDS_RXn_HIGH_SPEED_MODE`) and start there, or use the SCDC scrambling flag the source writes.
6. DP source start, ~480 ms from SEARCH to the first DP scan: the source trains after it reads the EDID (402 to 474 ms after the start). Fix: raise HPD earlier (during INITIAL, before the panel sequence ends); the HPD edge is not logged yet, so the gain is unmeasured: add the pin edge row first.
7. Search dwell: `_SOURCE_DEFAULT_SEARCH_TIME_HDMI` 2 s / `_DP` 3 s (`RL6449_Project.h:2160-2162`) apply to every port without a signal in an auto search; they are SDK defaults (not measured values). Not seen in these runs (single cabled port); the F3 visit lines will show it on a multi-cable setup.

Hooks not measured here: eDP link training detail (one panel line, 76 to 83 ms with a 45 ms delay), VideoDetect timeouts beyond the polls above, #239 (350.8 MHz boot loses the picture 1 in 3): none of the 8 boots in this session failed, so the new lines have no failing case yet. Next step for #239: run boots until a failure and read the F2 / FB lines.

## Fixes 1 and 5 (branch sync-speed, 2026-11-20)

Conditions: warm reset (ISP), n = 5 per image, median, console_mode Always, 4K60 RGB 8 bit; images built from origin/main b494ac8 ("before") and the branch tip ("after"); `./dev.py syncbench` rows in `tmp/logs/sync_bench.log`.

### 1. DP frame waits from the measured frame (`fw/dp/dpframe.c`, `AWTO_DP_ONE_FRAME()` / `AWTO_DP_TWO_FRAMES()`)

- Period = VBs2Bs count / GDI clock + 1 ms, set by `ScalerDpRx1DisplayFormatSetting`; cleared on a failed scan and on an HPD toggle; < 4 ms (bad count) or > 45 ms = the SDK worst case.
- Sites switched: `RL6449_Series_DPRx1.c` PG-stable wait (45 ms, in the scan), `ScalerDPRx1_SeptPhy.c` post-link wait and vsync adjust, `ScalerCommonDPRx1.c` MSA reset / video info / interlace / HDR waits (error and rare paths too). The 2-frame waits in display format and FIFO check were already derived (#60).
- Not shortened: the 45 ms wait after link training (no stream to measure yet; a measure-poll variant made the first scan fail MSA and retry, no net gain: dropped); three `PB8_58` measure polls (23 / 32 / 28 ms, hardware needs one frame each); the 6 x 10 ms FIFO watch (60 ms, SDK window, not a frame time).

| unit 2 DP D1, ms | before | after |
|---|---|---|
| scan call (n = 5: 330 330 330 331 331 / 302 301 302 301 302) | 330 | 302 |
| scan start (source-driven, 795..876 / 665..802) | 808 | 783 |
| picture (ACTIVE) at (1691 1688 1693 1674 1758 / 1655 1545 1665 1662 1539) | 1691 | 1655 |
| sim cycles per pass | 163222 | 163219 |

- Saving 28 ms in the scan call (45 -> 17 ms measured frame + 1); the picture time moves with the Intel source (HPD high at 478 ms, EDID read +24, link training after that: 120 ms spread between runs), so the picture median gain (36 ms) is not separable from source noise. Expected 100 to 150 ms was not reachable: one wait of the seven was a frame-time wait that could change; the rest are hardware measure polls and a fixed FIFO window.

### 5. HDMI mode memory (`isr_g_ucAwtoTmdsMem`, `AWTO_TMDS_MEM_*` in `RL6449_Project.h`)

- One XDATA byte: bit n = port Dn+2 worked at 1:40 last. Set / cleared after every successful scan (mode in use); the clock-stable ISR takes 1:40 from it when SCDC does not say so and the clock is in the SDK's 85..150 MHz window; a lock failure drops the bit (the SDK toggle then tries the other mode); cable change on the port clears it. RAM only, no NVRAM.
- Not cleared when the search leaves the port: the gain is on a later switch back to it.
- Log: F2 02 `scan:tried the remembered mode 1:40 first (D2, 48ms)` before the outcome line.
- Cold boot / warm reset: the byte is empty, the 69 ms failed 1:10 try stays (unit 1 and unit 3, 5 of 5 runs). The gain is on an input switch or a re-scan on the same cable.
- SCDC 0x20 read again in the scan (instead of memory) was tried and dropped: the sources (Intel on unit 3) leave TMDS_Bit_Clock_Ratio 0 (`./dev.py scdc`: cfg 0x00, scrambler status 1), the SDK's own SCDC test fails the same way, so no failed try was avoided (5 of 5 unchanged).

| unit 3 HDMI D2, switch D1 -> D2, ms from the switch | before | after |
|---|---|---|
| first scan call (per run 33..43 / 39..41) | 43 | 40 |
| failed 1:10 try (23 ms poll + retry) | every run | none |
| picture (ACTIVE): 833 851 853 850 857 / 780 811 792 787 784 | 851 | 787 |

| boot (warm reset), n = 5 | before | after |
|---|---|---|
| unit 3 picture, ms (1420 median / 1428) | 1420 | 1428 |
| unit 1 picture, ms (1049 / 1039) | 1049 | 1039 |
| failed 1:10 try, ms | 69 | 69 |

### Cost

- XDATA: +2 B (memory byte in `ports`, HPD edge state in `sync`); free 212 B -> 210 B. The ring-read gate layout re-homed a few 1..2 B slots.
- Code: about +0.6 KB (HPD / EDID log 220 B, scan memory line 170 B, TMDS wrapper 76 B, ISR hooks, dpframe), banks with free space; no DATA change.
- Idle: speed_bench cycles per pass 163222 -> 163219.

## EDID read versus video bring-up (2026-11-20, FA / E7 lines, warm reset, n = 5 per unit, ms from the episode start)

| event | unit 2 DP D1 (Intel) | unit 3 HDMI D2 (Intel) | unit 1 HDMI D2 (NVIDIA) |
|---|---|---|---|
| backlight pin on (panel machine, "as early as possible") | 133 | 133 | 133 |
| EDID channels enabled (`ScalerMcuDdcRamEnable`) | 142 | 142 | 140 |
| HPD pin high | D1 low until 478..494 | D2 / D3 high at the first poll (168) | D2 / D3 high at 167 |
| eDP link trained, panel stream on | 382 | 376 | 445 |
| EDID read by the source | 502 (24 after HPD) | 475 | 669, again 1014 |
| TMDS predetect / DP link trained | 673 (link), scan ok 977 | 566 predetect, scan ok 708 | 359 predetect, scan ok 468 |
| picture (ACTIVE) | 1655 | 1428 | 1039 |

- DP: HPD is raised after the EDID channel is on (350 ms later, at the end of INITIAL), the source reads 24 ms after HPD and trains about 170 ms after that. Order correct; no video path starts before the read.
- HDMI: the EDID channel is enabled at 140..142 ms, HPD is already high at the first poll (168); the GPIO init that raises HPD is at 129, so HPD is high about 13 ms before the DDC channel answers. No source read inside that window in these runs (first reads at 475 / 669).
- Unit 1 (NVIDIA): the TMDS scan completes (468) and timing is confirmed (670) before the source reads the EDID (669, 1014). Cause: the warm reset keeps HPD high, the source keeps transmitting and re-reads the EDID after its DDC reads failed during the reset; a cold power-up (HPD low first) was not measurable (relay disabled, #339).
- Before any EDID read: the backlight (133) and the eDP panel stream (376..445, background colour) on every unit; no input video path (TMDS predetect, DP link training, display setting) except the warm-reset case above.
- Proposal, not done (needs a measurement of the DP Rx readiness): DP HPD at 142 ms instead of 478..494 would move the whole source chain about 340 ms earlier. HDMI: drive HPD low in GPIO init and raise it after `ScalerMcuDdcRamEnable` to close the 13 ms window; EDID content untouched.

## Input switch timeline (unit 3, both cables: HDMI D2 Intel, DP D1 NVIDIA DP-4 output switched off on the host on purpose)

Host side of D1 is off: the DP input has no stream (the NVIDIA source still trains the link and reads the EDID in some runs). Switch by `./dev.py kvm` (VCP 0x60); times in ms from the switch.

| step | D2 -> D1 (no picture source) | D1 -> D2 (before / after the memory) |
|---|---|---|
| request accepted, reset to search | 0..3 | 0..1 |
| first scan | `DP link not trained` at 127, link seen trained at 128, `signal lost` 133 (run 1) | scan ok 58..135 (fails 1:10 first / 1:40 first) |
| search ends | NO SIGNAL after 2091 (run 2) and 4133 (run 1, after the link came and went) | n/a |
| picture | none | 851 / 787 |
| `kvm D3` | `refused:no cable on D3`, input stays | |

- The fixed-port search on a port without signal ends in NO SIGNAL after 2.1 s (no stream) or 4.1 s (link trained, stream lost): the SDK dwell (`_SOURCE_DEFAULT_SEARCH_TIME_DP`); not shortened here.
