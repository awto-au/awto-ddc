# Delays, waits and timeouts in the firmware (#54)

- Review 2026-11-13 by two read-only agents. Code = main 722e32d / image wb-p14ui-amp2. Panel T6 since then: 900 ms, run at power-down (b70095c).
- Rule (Dan, 2026-11-13): every delay = **datasheet / spec value - 10 %**, never an added margin. Timeouts (event waits that fail on expiry) = 1.25 x expected worst case. Rule text: awto-dan `docs/agents/agent-rules.md`.
- Columns: what it waits for, value, where defined, **what decided it**, source value, ratio code/source.
- Superseded: the older `re/delays.tsv` / `re/delays_reasons.tsv` (image wb-stepB 1100f24; cite a BOE panel datasheet).

# Part 1: inventory

## How I decided what is compiled, and what the snapshot is

- **Build chain.** `scripts/wb_build.py` calls `scripts/fw_build.py`, which calls `scripts/fw_compile.py`.
  - `fw_compile.py` compiles the C files listed in `fw/sdk/STD_FW_1P.Uv2` (target `RL6449_Project`) plus the Lib Uv2.
  - `fw_compile.py awto` compiles every `awto-rtdfw/awto/*/**.c` module (arith, dataport, gamma, nvram, reg, settings) plus the shim `fw/awto/awto_shim/sdk_boundary.c`, with `-D_AWTO_NEW_<MOD>`.
  - `fw/sdcc/*.inc` are our code, pulled into the SDK translation units.
- **How "linked" was decided.** I re-ran `scripts/delay_inventory.py` against the worktree `/mnt/2tb/git/awto-ddc-audio3` (722e32d) and the map `tmp/fw/AWT26110003-wb-p14ui-amp2-be.map`.
  - 722e32d is the code of main. main HEAD c83d618 differs only in docs.
  - A site counts as linked only if the final SDCC listing contains code for that file:line.
- **Where the run output is.** The re-run wrote to `/tmp/claude-1000/-mnt-2tb-git-awto-ddc/f7982fc5-907c-4500-a6ef-8f90f4ceaa15/scratchpad/root/out/delays.tsv`: 1014 rows, 547 linked.
  - Its `value` column says "variable" because sdcccall 3 broke the argument decode. I resolved the values from the statement text instead.
- **The committed inventory is stale.** `re/delays.tsv` and `docs/delays.md` come from an older image (wb-stepB, 1100f24). They still list blocking T1..T5 waits that #162 removed, and they cite a BOE panel datasheet. Do not use them.
- **The working tree is moving.** While I worked, uncommitted edits appeared in main:
  - `AWTO_M280DCA_E3B.h` T6 1100 -> 900.
  - `UserCommonInterfacePanelBoot()` changed.
  - `RL6449_Series_Mcu.c` now turns panel VDD on at GPIO init.
  - `docs/monitors/panel-innolux-m280dca-e3b.md` and `docs/settings.md` were edited.
  - awto-rtdfw commit 50d9c65 (20:06 today) set the registry `panel_t6` default to 900.
  - Treat the T6 row as "HEAD says 1100, working tree and registry say 900".
- **Rules I measured ratios against.** From `~/.claude/CLAUDE.md` and the memory file `delays-datasheet-minus-10.md`:
  - Delay = datasheet value minus 10 % (expected ratio 0.90, never padded).
  - Timeout = 1.25x the expected worst case.
- **Tick granularity.** `ScalerTimerDelayXms(n)` counts n Timer2 tick events from a random phase, so the real wait is between n-1 and n ms.
  - `ScalerTimerPollingFlagProc(n)` and `ScalerTimerWaitForEvent` use `<=` bounds, so they run n+1 ticks.
  - The wait-event bound is 91 ticks; the poll bound is n+1 ticks.
- **Dahua firmware RE.** I found no delay value in the code whose cited source is the Dahua firmware. The only Dahua-derived numbers in the scope are panel timing registers.
- **Not delays.** The djnz loops in `crt_xinit.asm` and `crt_divulong.c` are data-copy loops.

Abbreviations in the table:
- **SDK-lit** = a literal in Realtek source with no stated reason.
- **n/a** = no source value exists, so no ratio.
- Unless stated, the file path is under `fw/sdk/Kernel/...` (SDK) or `fw/sdcc/` (ours).

## Table

| file:line | what it waits for | value | where defined | what decided it | source value | ratio code/source | on expiry |
|---|---|---|---|---|---|---|---|
| **PANEL STATE MACHINE (ours, #162)** | | | | | | | |
| User Common Function/Code/UserCommonInterface.c:874 | T1: VDD on -> eDP PHY / AUX. Also waits, with no time bound, for power status NORMAL. | 10 ms | `fw/sdk/Panel/AWTO_M280DCA_E3B.h:47`. With `_AWTO_NEW_SETTINGS`, `AWTO_SET(PANEL_T1)` at :61; registry row 67 default 10, range 0..100. | Datasheet Innolux M280DCA-E3B v0.0 sec 4.8 T1, VDD rise 0.5..10 ms (panel doc, power-sequence table). The registry note says "vendor example value, no datasheet" and `docs/settings.md` says [sdk-value], so the notes disagree with the panel doc. | max 10 ms | 1.00 | PHY on, HPD read |
| UserCommonInterface.c:892 | T2: eDP HPD high, read once per tick | 250 ms | header :48, registry row 68 | Panel doc: bound = 1.25 x datasheet T3 (VDD->HPD 15..200 ms). Measured 115 ms (unit 3, #78), 78 ms (unit 2). | 200 ms max | 1.25 | logs sync 12 00, trains anyway |
| UserCommonInterface.c:952 and :806 | T3: stream valid -> backlight pin on, used when there is no own frame | 550 ms | header :49 (comment cites datasheet T8 >= 200), registry row 69 (range 300..2000) | Registry note: ">= 500 ms per 27-inch 4K eDP datasheets" (those datasheets are not cited). The panel doc maps it to datasheet T8 (valid video -> LED on, >= 200 ms). | 200 ms (panel datasheet), 500 ms (registry note) | 2.75 vs datasheet, 1.10 vs the registry note | backlight pin on |
| UserCommonInterface.c:775 (T3 use at :952) | T3 with own black frame | 20 ms | `RL6449_Project.h:1276` -> registry row 70 (default 20, min 17); :1278 fallback 20 | Comment: "one 60 Hz frame (16.7 ms) + margin". Panel doc marks it below datasheet T8 min 200; deliberately not followed (Dan, 2026-11-13). Measured stream->backlight pin 37 ms on unit 2. | 16.7 ms (frame), 200 ms (datasheet) | 1.20 vs frame, 0.10 vs datasheet | backlight pin on |
| UserCommonInterface.c:971 | backlight pin on -> PWM duty (`_PANEL_POWER_ON_BL_TO_PWM`) | 50 ms | `Kernel/Common/Panel_Default.h:330` (the panel header does not override it) | SDK default. The panel doc says it is not in the datasheet. | n/a | n/a | user duty applied |
| UserCommonInterface.c:992 | PWM dark -> backlight pin off (`_PANEL_POWER_OFF_PWM_TO_BL`) | 50 ms | `Panel_Default.h:334` | SDK default, not in the datasheet | n/a | n/a | pin off |
| UserCommonInterface.c:1011 | T4: backlight off -> stream idle | 250 ms (effective >= 251 ms, `<=` compare) | header :51, registry row 71 | Panel doc maps it to datasheet T9 (LED off -> video idle, >= 200 ms). Registry note [vendor-value]. | 200 ms min | 1.25 | stream to idle pattern |
| UserCommonInterface.c:1028 | T5: stream idle -> SSC / PHY / VDD off | 20 ms (+1 tick) | header :52, registry row 72 | Panel doc maps it to datasheet T10 (video end -> VDD off, 0..500 ms max) | 500 ms max | 0.04 | SSC, PHY and VDD off |
| UserCommonInterface.c:1038 | T6: VDD off -> VDD on, minimum | 900 ms in working tree and registry (HEAD header: 1100) (+1 tick) | header :53 (working tree), registry row 73 (rtdfw 50d9c65) | Datasheet T11 (VDD off at 10 % -> on, >= 1000 ms), minus 10 % per the delay rule (Dan, 2026-11-13). VDD decay is not measured. | 1000 ms min | 0.90 working tree / registry; 1.10 for the 1100 in HEAD's header | state OFF, VDD may come on |
| registry row 74 `bl_pwm_ms` (awto-rtdfw `settings/registry.tsv`) | planned enable-pin -> PWM wait | 0 ms, inert | registry | no reader in firmware | n/a | n/a | n/a |
| **BOOT / POWER (SDK, our board header)** | | | | | | | |
| RL6449_Series_Mcu.c:1762 | VCCK_OFF flag poll at GPIO init: up to 20 x `DelayXms(1)`, then always +10 ms (`ScalerPowerInclude.h:23-32`) | bound 20 ms (+10 ms fixed) | `Kernel/Common/RL6449_Pcb_Default.h:1004` (the AWTO_JXC4K PCB header does not define it) | SDK default; SDK comment "Wait for VCCK_OFF Power On Stable"; the pin is a no-op on our board (`RL6449_AWTO_JXC4K.h:279-285`) | n/a | n/a | continues |
| RL6449_Series_Power.c:267 | same macro, group A isolation off | 20 + 10 ms | same | same | n/a | n/a | continues |
| RL6449_Series_Power.c:428, :438, :446 | DDR power release 200 ms; DDR stable 10 ms; 1.1 V stable 10 ms | 200 / 10 / 10 ms **compiled out** | `_AWTO_FAST_BOOT == _ON`, `RL6449_Project.h:1159`; `_DDR_POWER_OFF_TIME` 200 at `RL6449_Pcb_Default.h:1032` | our board never switches these rails (comment :1156) | n/a | n/a | n/a |
| ScalerGlobal.c:140 | whole-chip reset settle | 10 ms | SDK-lit | SDK comment "For Delay 10 ms"; no spec cited -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonPower.c:68 | xtal stable | 6 ms | SDK-lit | SDK comment "Waiting for xtal stable"; no datasheet value -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonIOSC.c:68, :104, :136 | IOSC enable settle 2 ms; IOSC trim poll 10 ms; trim finished poll 10 ms | 2 / 10 / 10 ms | SDK-lit | SDK comments ("Polling trimming finished, time-consuming"); no spec -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerPLL.c:2802 | "Wait for Mpll stable (Must!)" | 2 ms | SDK-lit | SDK comment -> UNKNOWN value | UNKNOWN | UNKNOWN | continues |
| ScalerPLL.c:3731 | DDR2 PLL lock flag poll | 40 ms bound | SDK-lit | SDK; no stated reason -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_PLL.c:322, :328, :348 | CMU stable 2 ms; DPLL watchdog poll 2 ms; SSC-off stable 2 ms | 2 / 2 / 2 ms | SDK-lit | SDK comments "Wait for CMU Stable", "SSC Off stable"; no spec -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_Measure.c:311, ScalerMeasure.c:660 | measure reset | `_MEASURE_RESET_TIME` = 2 ms at the xtal clock (`ScalerMeasureInclude.h:38`; depends on the runtime measure clock) | SDK | SDK comment "Delay for measure reset" | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_Measure.c:155 | offline measure done poll | `_MEASURE_TIMEOUT` = 512*10/CLK + 10 ms (650 ms at the 14.318 MHz xtal; M2PLL value depends on a runtime divider -> UNKNOWN) | `ScalerMeasureInclude.h:37` | SDK arithmetic | formula | n/a | returns _FALSE |
| ScalerGlobal / MDomain / VGIP double-buffer polls: RL6449_Series_Global.c:308, RL6449_Series_MDomain.c:258, ScalerVGIP.c:734 | double-buffer apply flag | 168 ms | `ScalerGlobalCommonInclude.h:31` | SDK comment: "4 frames at 24 Hz" = 166.7 ms | 166.7 ms | 1.008 | returns _FALSE |
| ScalerTimerFunction.c:56-105 `ScalerTimerWaitForEvent`; **106 call sites**: fw/osd/console.c; fw/settings/settings_glue.c set_ap_volume / set_ap_mute; RL6449_Series_FRC.c:154,169,262,341-343,359,372,373,382,433,964,1075,1324,1364,1367; FormatConversion.c:174,276-279; MDomain.c:77-146 (13 sites); Measure.c:442-1080 (about 19 sites); Osd.c:179; Rotation.c:114,115; ColorOutputGammaAdjust.c:60,78; OsdPosition.c:62; ScalerDisplayDPTx.c:1685,1705,1706; ScalerGlobal.c:260; ScalerMDomain.c:392,427,1541,1542; ScalerMeasure.c:750,751,788,789,867; ScalerMemory.c:391-461,714-716; ScalerPLL.c:1330,1382,1930,2262-2297; ColorIDitherEnable.c:70; OsdCircuitActivated.c:79; OsdFontLibraryRotation.c:61; OsdDrawWindow.c:118; UserCommonInterface.c:1257; RTDFactoryFunction.c:2762; RTD2014UserAdjust.c:555; RTD2014OsdDisplay.c:557; RTD2014OsdWindow.c:131; plus the awto-rtdfw gamma.c:31,49 via `sdk_boundary.c:91-98` | IVS / DVS / IEN / DEN edge | 90 ms bound (91 ticks) | `ScalerCommonTimerFunctionInclude.h:48` | SDK-lit, no reason stated -> UNKNOWN | UNKNOWN | UNKNOWN | returns _FALSE; callers mostly ignore it |
| **DP RX / TX (SDK, linked)** | | | | | | | |
| ScalerCommonSyncInclude.h:161,162 and sites: ScalerDisplayDPTx.c:579; ScalerCommonDPRx1.c:746,1133,2860; ScalerDPRx1_SeptPhy.c:4883,5061; RL6449_Series_DPRx1.c:2511 | one / two DP frames | 45 / 90 ms | `ScalerCommonSyncInclude.h:161` | SDK comment "in ms @ 23 Hz" | 43.5 ms (1/23 Hz) | 1.035 | continues |
| ScalerDPRx1_SeptPhy.c:4068 and :4312 (`AWTO_DP_TWO_FRAMES()`) | two frames from the measured frame | 2 x measured frame ms + 1, capped at 90 | `awto_dpframe.inc:5-17`, `_AWTO_DP_FRAME_WAIT` `RL6449_Project.h:829` | measured at runtime (#60) | 2 frames | (2n+1)/(2n) | continues |
| RL6449_Series_DPRx1.c:2421, :2479, :2505 (via ucFrameTime) | 1 frame | measured frame ms + 1 (:2403) | computed | computed from the measured stream clock; SDK comment "Delay 1 Frame" | 1 frame | (f+1)/f | continues |
| RL6449_Series_DPRx1.c:1982,2283,2293,2298; ScalerCommonDPRx1.c:949; ScalerDPRx1_SeptPhy.c:381(3 ms),443,4499,4979; ScalerDP_SeptPhy.c:1009 | measure done, VBID, scramble, lane alignment, low-power settle | 2 ms (3 ms at :381) | SDK-lit | SDK comments ("Waiting for Measure Done", "Delay 2ms for Scramble"); no spec -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonDPRx1.c:955 | 1 frame from VBID | `(count/_GDI_CLK_KHZ)+2` ms | computed | SDK comment "Delay 1 frame" | 1 frame | (f+2)/f | continues |
| ScalerCommonDPRx1.c:2856; ScalerDPRx1_SeptPhy.c:4954 | MAC reset pulse | 30 ms | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerDPRx1_SeptPhy.c:4318 | FIFO check settle | 10 ms | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| `_DP_MEASURE_POLLING_TIMEOUT` sites: RL6449_Series_DPRx1.c:2037; ScalerCommonDPRx1.c:937; ScalerDPRx1_SeptPhy.c:607,3980,4535 | M/N measure done | 100 ms | `ScalerCommonSyncInclude.h:145` | SDK-lit -> UNKNOWN | UNKNOWN | UNKNOWN | returns _FALSE |
| RL6449_Series_DPRx1.c:2499; ScalerDPRx1_SeptPhy.c:338 | VBID bit0 poll | 50 ms | SDK-lit | SDK comment "Polling Vertical BS" -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_DPRx1.c:2425,2483 | PE flag loop | up to 10 passes of 1 frame | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | exits |
| RL6449_Series_DPRx1.c:3872-3972 (5x 2 ms), :4133 (1000 ms), :4187,:4261 (10 ms), :4238 (2 ms); ScalerDPRx1_SeptPhy.c:5153,5159,5218,5259 (10/2/10/2 ms) | PHY compliance test (lab only, `_AWTO_DP_PHYCTS` `RL6449_Project.h:~300`, kept by Dan) | as listed | SDK-lit | VESA PHY CTS flow in the SDK -> UNKNOWN per value | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_DPRx1.c:3665,3966,4050 `ScalerDpRx1PhyCTS` | until the DP source ends the CTS test | **no bound** (pokes the watchdog) | SDK | `docs/watchdog.md` row 113: "unbounded, bug class, lab-only, decision for Dan" | n/a | n/a | never (until the source ends the test) |
| RL6449_Series_DisplayDPTx.c:284 | after every link-training attempt, including the passing one | 5 ms x up to 5 attempts | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | next attempt |
| RL6449_Series_DisplayDPTx.c:495 | "Waiting for PHY initial" | 10 ms | SDK-lit | SDK comment; no spec -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerDisplayDPTx.c:206 | after the DPCD 600h power-up write | 10 ms | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerDisplayDPTx.c:828,924,1929,1934,2084,2089 | AUX / training-pattern wait | `DELAY_XUS(400)` | SDK | SDK comment "Delay Time us [400,x]" | UNKNOWN beyond the comment (DP AUX timing is likely but not cited) | UNKNOWN | continues |
| ScalerDisplayDPTx.c:1929-1940 and 2084-2095 | AUX done poll | 25 x `DELAY_5US` (125 us); 7 retries (:2004) | SDK | SDK comment "Delay Time us [5,175]" | n/a | n/a | retry then fail |
| ScalerDisplayDPTx.c:652 `LinkTraining` | until LT_RESULT is PASS or FAIL | state machine, no timer | SDK | n/a | n/a | n/a | n/a |
| **HDMI / TMDS (SDK, linked)** | | | | | | | |
| RL6449_Series_TMDSRx2.c:3342 and RL6449_Series_TMDSRx3.c:3345 | blind wait "at least 3 frames" for the HW colour-depth update | 130 ms | SDK-lit | SDK comment | 3 frames (rate not stated; 130 ms = 3 frames at 23 Hz) | UNKNOWN | continues |
| TMDSRx2.c:3385, TMDSRx3.c:3388; ScalerCommonSync.c:8733, 9341; ScalerTMDSRx2_SeptPhy.c:101, ScalerTMDSRx3_SeptPhy.c:101 | "down sampling effect" | 20 ms | SDK-lit | SDK comment -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| TMDSRx2.c:3264,3279,3294,3975 and TMDSRx3.c:3267,3282,3297,3978 | packet / format polls | 130 / 180 / 180 / 130 ms | SDK-lit | SDK comments "3 frames", "more time to wait GCP/AVI" | UNKNOWN | UNKNOWN | falls through |
| TMDSRx2.c:4060,4062 and TMDSRx3.c:4063,4065; ScalerTMDSRx2_SeptPhy.c:141,144 and TMDSRx3_SeptPhy.c:141,144 | HDCP-enabled / video detect | 45 / 20 ms | SDK-lit | SDK comment "at least 1 frame" | UNKNOWN | UNKNOWN | falls through |
| ScalerTMDSRx2_SeptPhy.c:677 and ScalerTMDSRx3_SeptPhy.c:677 | pre-detect settle | 6 ms | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerTMDSRx2_SeptPhy.c:632-636 and ScalerTMDSRx3_SeptPhy.c:632-636 | deep-colour PLL lock | 2 ms x up to 16 | SDK-lit | SDK comment "Delay for PLL Phase Lock" | UNKNOWN | UNKNOWN | returns _FALSE |
| TMDSRx2.c:3183,3192,3197 and TMDSRx3.c:3186,3195,3200; ScalerTMDSRx2_SeptPhy.c:3630 and TMDSRx3_SeptPhy.c:3633 | deep-colour PLL set / PHY stable | 2 ms each | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerTMDSRx2_SeptPhy.c:815 and ScalerTMDSRx3_SeptPhy.c:815 `HotPlugHighProc` | HDMI HPD low time | user setting x 100 ms; SDK NVRAM default 5 = 500 ms (`UserCommonNVRamSystem.c:52`). **Skipped:** `_AWTO_HDMI_HPD_TOGGLE == _OFF` (`RL6449_Project.h:1164`). | NVRAM | SDK default | n/a | n/a | continues |
| ScalerCommonSyncInclude.h:118-120 | HDMI HPD times when toggling: HDCP 2.2 1000 / Acer 130 / EDID switch 600 ms | as listed | SDK | SDK constants | n/a | n/a | n/a |
| `ScalerTMDS*FLD / SetPhy_EXINT0` (interrupt context): ScalerTMDSRx2.c:1362-1920 and Rx3.c:1365-1923 | EXINT0 PHY set blind steps | **5545 us per call** (50 + 3x360 + 5x150 + 2x290 + 2x1000 + 900 + 25 + 2x80 us) | SDK | SDK numbers, no stated reason -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| `*MeasureClk`, `FLDBandFineTune_EXINT0`: TMDSRx2.c:691,728,2850,2906 and Rx3.c:694,731,2853,2909 | 5 us steps | 5 us each | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| TMDS timer events: TMDSRx2.c:3994,4200 and Rx3.c:3997,4203 | format reset wait | 130 ms | SDK-lit | UNKNOWN | UNKNOWN | UNKNOWN | event fires |
| ScalerTMDSRx2_SeptPhy.c:191 and ScalerTMDSRx3_SeptPhy.c:191 | video-detect re-arm | 45 ms | SDK | "1 frame" comment | UNKNOWN | UNKNOWN | re-poll |
| `ScalerTMDSRx2_SeptPhy.c:562` (and Rx3 :562) | HDMI read-request retry on Timer0 | 10 ms | SDK; `awto_t0ev.inc:218` | SDK | n/a | n/a | retry event |
| **busy-wait macros (main context)** | | | | | | | |
| `ScalerCommonMcuInclude.h:40-215`; counts set at `ScalerCommonMcu.c:1844-1849`; our calibration `awto_delaycal.inc:88-99` | `DELAY_5US`, `DELAY_XUS(n)` and relatives | loop counts set so the shorter copy of each pair lands at 105 % of nominal | `AWTO_DELAY_TARGET_PCT` `RL6449_Project.h:188`, valid only at `AWTO_DELAY_CAL_RCAP2H 0xE3` | measured (T3 measurement, #54, diag block). Realtek's own count is 112..127 % depending on code placement. Health limit 90..125 %. | nominal us | 1.05 | n/a |
| RL6449_Series_DPRx1.c:1201-1759 `RebuildPhy` | PHY rebuild steps | 905 us total (5x85 + 300 + 3x25 + 3x5 + 2x45) | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| DPRx1.c:2832-2954 `PhyCtsTp1SetPhy` / :3060-3609 `Tp2SetPhy` / :3920-4230 `PhyCTS` | CTS PHY steps | 370 / 815 / 165 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerPLL.c:309-317, 1406-1410, 2761-2765, 3689-3706, 3727-3743, 3769, 3843 | PLL power-up and reset steps | M2PLL 150 + 5 + 1000 us; DPLL cascade 155 us; MPLL 2x150 + 2x5 us; DDR2 ctrl 2x150 + 2x85 us; DDR2 output 3x85 us; DDR2 freq 2x150 us | SDK | "Wait for M2PLL Stable (1ms)" comment at :317; others UNKNOWN | 1000 us (:317) | 1.00 (:317) | continues |
| RL6449_Series_DDR2.c:337; GDIPhy.c:213 | DDR2 DCPHY / bandgap | 5 us / 85 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_Power.c:482-495,527-540,572-585,617-630,662-675 | power-cut flag polls | 50 x `DELAY_5US` per flag (about 250 us each), 10 loops | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonDPRx1.c:560; TMDS MeasureClk; ScalerDPRx1_SeptPhy.c:3418,3888(150 us),4686 | small settles | 5 us / 150 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerDisplayDPTx.c:338 | video stream output | 5 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonDebug.c:343,744 | debug message gap | 30 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| **INTERRUPT-CONTEXT BLIND WAITS** | | | | | | | |
| RL6449_Series_DPRx1_INT.c:485-599 `Tp1SetPhy_EXINT0` | PHY | 260 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| DPRx1_INT.c:731-950 `Tp2SetPhy_EXINT0` | PHY | 710 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| DPRx1_INT.c:1065-1454 `RebuildPhy_WDINT` | PHY | 845 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_DP_INT.c:994 `WDTimerEventProc_WDINT` | AUX | 150 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerDPRx1_INT_SeptPhy.c:1170,1196,1819 | Tp2 check, FLD band | 2x25 us + 5 us | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonSync.c:3669,3712 `DdcDetect_EXINT1` | DDC detect | 2 x 30 us (60 us); debounce loop `g_usDDCDebounceCnt` (:3559) | SDK | SDK comment "Debounce 300us" | 300 us | UNKNOWN (count is a runtime value) | continues |
| `awto_dbgisr.inc:21,142`; DELAY_30US_EXINT calls | debug slave reply tail | 2 x 30 us | our code | copied from the SDK debug handler -> UNKNOWN | UNKNOWN | UNKNOWN | continues |
| ScalerCommonDebug.c:213-606 | debug DDC out-FIFO loops | bounded by `_DATA_OUT_COUNT` 5 passes | `ScalerCommonDebug.c:27` | SDK | n/a | n/a | exits |
| ScalerCommonDebug.c:403; awto_dbgisr.inc:129 | IIC status wait inside the interrupt | no time bound (status bit only) | SDK / ours | n/a | n/a | n/a | unbounded in principle |
| **OTHER SDK WAITS (linked)** | | | | | | | |
| ScalerAudio.c:770-773 | DVC mute: `DelayXms(1)` loop until gain done | bound 400 | `_DVC_VOLUME_MUTE_TIMER` `RL6449_Project_Default.h:1985` | SDK default | UNKNOWN | UNKNOWN | continues |
| RL6449_Series_Audio.c:837,1384 and ScalerAudio_SeptPhy.c:1358 | audio PLL | 2 ms, comment "Delay 2000us" | SDK | SDK comment | 2 ms | 1.00 | continues |
| RL6449_Series_Audio.c:843,849,1390,1396 and ScalerAudio_SeptPhy.c:1364,1370 | audio PLL | 2 ms, comment "Delay 1000us" | SDK | SDK comment; rounded up for the tick | 1 ms | 2.00 | continues |
| RL6449_Series_Audio.c:1598,1614 | audio detect | 3 ms, comment "Waiting for 2ms" | SDK | SDK comment | 2 ms | 1.50 | continues |
| RL6449_Series_Audio.c:1513, ScalerAudio_SeptPhy.c:736,985 | dynamic I-code reload event | 100 ms | `ScalerAudioInclude.h:29` | SDK | UNKNOWN | UNKNOWN | event fires |
| RL6449_Series_OsdHardwareVLC.c:99; fw/osd/text_layer.c (`osd_tc_vlc_end`) | OSD HW decoder flush | 2 ms | SDK / ours | fw/osd/text_layer.c comment: "Realtek's loader waits 2 ms here for the same reason". The OSD busy flag exists as an alternative. | 2 ms (Realtek loader) | 1.00 | continues |
| RTDFactoryFunction.c:2155,2161 | OSD HW | 1 ms x 2 | SDK | SDK comment as above | UNKNOWN | UNKNOWN | continues |
| ScalerColorIDitherEnable.c:69 | dither | 2 ms | SDK | UNKNOWN | UNKNOWN | UNKNOWN | continues |
| SysSource.c:3982,4093,4203 | cable-pin debounce, only after a status change | 10 ms | SDK-lit | UNKNOWN. `AWTO_SLOW_MS` 10 samples the same check. | UNKNOWN | UNKNOWN | continues |
| ScalerTimerFunction.c / ScalerCommonTimerFunction.c:2586 | the Timer2 spin itself; no-op when TR2 off | n | SDK; poked every ms by `AWTO_WDT_FEED` | n/a | n/a | n/a | n/a |
| **TIMER EVENTS (SDK, linked)** | | | | | | | |
| SysJudge.c:553, :707 | no-signal judge | 1 s | SDK | SDK | UNKNOWN | UNKNOWN | request no-signal |
| SysJudge.c:569,593,630,712 | no-support judge | 0.5 s; 2 s in DISPLAY (:603, :712) | SDK | SDK | UNKNOWN | UNKNOWN | request no-support |
| SysJudge.c:597, :878-893 | wait to active | VGA 50 ms; DVI / HDMI / DP 100 ms | `RL6449_Project.h:1814-1817` | SDK defaults (re-stated in the project header) | UNKNOWN | UNKNOWN | request active |
| SysSource.c:636,690 etc.; consts `RL6449_Project.h:1800-1803` | source search window | ALL_PORT 2000 ms (the polling style used here, :931); VGA 500, HDMI 2000, DVI 2000, DP 3000 ms in the per-port branches | project header, `RL6449_Project_Default.h:1011-1052` | SDK defaults. Registry rows 40-43 (`search_*_ms`, `nocable_*_ms`) feed the per-port variables via `glue.inc:711-728`. | UNKNOWN | UNKNOWN | search ends -> no signal |
| SysSource.c:698 | double-check search | 0.5 s | `_SOURCE_DOUBLE_CHECK_SEARCH_TIME_NVRAM_PORT` | SDK | UNKNOWN | UNKNOWN | search ends |
| SysDP.c:257,304 and ScalerDPRx1_SeptPhy.c:4925 | DP hotplug / link-status IRQ | 100 ms | SDK | SDK | UNKNOWN | UNKNOWN | event fires |
| ScalerDP_SeptPhy.c:594 | DP HPD sequence | table | SDK | SDK | UNKNOWN | UNKNOWN | event fires |
| ScalerDPRx1_SeptPhy.c:5391 | HDCP long hotplug | 1 s | SDK | SDK | UNKNOWN | UNKNOWN | event fires |
| RL6449_Series_DP_INT.c:822 | DP rebuild PHY on Timer0 | 30 ms | SDK; `awto_t0ev.inc:219` | SDK | UNKNOWN | UNKNOWN | event fires |
| SysAudio.c:358,377,394 | DAC VCM initial 0.1 s; charge 0.5 s; depop 0.1 s | | SysAudio.c:30-31; `RL6449_Project_Default.h:1880` | SDK | UNKNOWN | UNKNOWN | state step |
| RTD2014Osd.c:138-243 | no-signal / no-cable pop-up | 2 s | SDK | SDK | UNKNOWN | UNKNOWN | pop-up |
| RTD2014Osd.c:204,210,220 | power-saving pop-up | 3 s | SDK | SDK | UNKNOWN | UNKNOWN | pop-up |
| RTD2014Osd.c:243 | go to power saving | 2 s | SDK | SDK | UNKNOWN | UNKNOWN | request power saving |
| RTD2014Osd.c:282 | input-info pop-up | 6 s | `RL6449_Project.h:1433` | our change; SDK value was 3 s; no reason given | 3 s | 2.00 | OSD off |
| RTDFactoryFunction.c:3436, `RL6449_AWTO_JXC4K.h:331` | panel-used hour counter | 60 s | SDK | SDK | UNKNOWN | UNKNOWN | event fires |
| **WATCHDOG** | | | | | | | |
| `RL6449_Project.h:325,326,311-324` `AWTO_WDT_THR 0x577`, `AWTO_WDT_N 1` | warning IRQ | 200.1 ms (1399 x 143.0 us) | project header | measured: worst poke gap 160 ms (host_sleep, power saving), x 1.25 (`docs/watchdog.md` wd8) | 160 ms | 1.25 | capture, then soft reset |
| same | hardware reset (CNT1 = N = 1) | 585.9 ms | project header | register arithmetic: 4096 x 2048 / 14.318 MHz | n/a | n/a | chip reset |
| same | early match marker | 439.4 ms (CNT3 0xC00) | doc | register arithmetic | n/a | n/a | marker only |
| `AWTO_WDT_N_BOOT_FIELD` | boot reset period until `ScalerTimerWDInitial` | N = 8 x 585.9 = 4687 ms | `RL6449_Project.h:~316` | SDK boot value | n/a | n/a | chip reset |
| `AWTO_WDT_PROBE_THR/MS` `RL6449_Project.h:328-329`; `fw/diag/wdt.c:222-229` | test probes 0x49 / 0x4F | 36.6 ms threshold, spin 1500 ms | project header | comment: N+1 wraps (1172 ms) x 1.25 -> 1.5 s | 1172 ms | 1.28 | test ends |
| `AWTO_WDT_SHOW_MS` `RL6449_Project.h:377`; `fw/diag/wdt.c:255` | console opens after a bite | 1000 ms | project header | comment: sim max pass 800 ms x 1.25 | 800 ms | 1.25 | console opens |
| SPI-flash halts (not code) | erase 200 ms, WRSR 40 ms, page program 3 ms | n/a | MX25L8006E datasheet, `docs/watchdog.md` | datasheet maxima | n/a | n/a | CPU halted; `FFEA[5]` freezes the counter |
| **OUR OWN TIMED LOGIC (fw/sdcc, project header)** | | | | | | | |
| `RL6449_Project.h:462` `AWTO_KEY_SAMPLE_MS`; `fw/keys/keys.c:382` | key debounce: two equal samples | 10 ms | project header | SDK key scan SEC(0.01) | 10 ms | 1.00 | sample accepted |
| `RL6449_Project.h:463`; `fw/keys/keys.c:308` | UP / DOWN wait for combo partner | 80 ms | project header | our choice: "two-finger press skew; longer feels slow"; no measurement cited -> UNKNOWN | UNKNOWN | UNKNOWN | sends PRESS |
| `RL6449_Project.h:464`; `fw/keys/keys.c:315` | first key repeat | 500 ms | project header | SDK SEC(0.5) | 500 ms | 1.00 | repeat |
| `RL6449_Project.h:465`; `fw/keys/keys.c:314` | key repeat rate | 100 ms | project header | our choice: 10 steps/s so a 0..100 slider takes 10 s | n/a | n/a | repeat |
| `fw/keys/keyinject.c:30` `s_usAwtoKeyHoldMs` | injected key hold | host value | host | host command | n/a | n/a | key released |
| `RL6449_Project.h:834` `AWTO_SLOW_MS`; `fw/diag/loopsplit.c:18` | slow main-loop checks | 10 ms | project header | "latency <= 10 ms + 1 pass (limit 50 ms, #75)" | 50 ms limit | 0.20 | next pass |
| `RL6449_Project.h:871` `AWTO_SW_SLOW_MS`; `fw/log/swlog.c:66` | stall log threshold | 20 ms | project header | "7x a 4K60 pass (2.7 ms)" | 2.7 ms | 7.4 | logs a slow-mark line |
| `RL6449_Project.h:1175` `AWTO_TMDS_HPD_LOW_MS`; `fw/log/swlog.c:162` | HDMI HPD low pulse (non-blocking) | 110 ms | project header | comment: HDMI 1.4b, a source reads HPD low >= 100 ms as unplug | 100 ms | 1.10 | HPD high again |
| `RL6449_Project.h:1067` `AWTO_PS_POLL_MS`; `fw/log/sync.c:754` | power-saving wake poll | 5 ms | project header | SDK's own freq-measure wait (5 ms) | 5 ms | 1.00 | next poll |
| `AWTO_PS_TMDS_HOLD_MS`; `fw/log/sync.c:644` | TMDS wake hold | 50 ms | project header | "about 10 SDK stable windows" | UNKNOWN | UNKNOWN | wake |
| `AWTO_PS_TMDS_GAP_MS`; `fw/log/sync.c:652` | gap ends a TMDS run | 15 ms (3 x poll) | project header | derived | 15 ms | 1.00 | run ends |
| `AWTO_HOLD_CHECK_MS`; `awto_fastsw.inc:173` | receiver check while held | 10 ms | project header | wake latency <= 10 ms + 1 pass; UNKNOWN reason | UNKNOWN | UNKNOWN | next check |
| `AWTO_REHOLD_MS`; `awto_fastsw.inc:133` | no new hold after a fast wake | 3000 ms | project header | no source stated -> UNKNOWN | UNKNOWN | UNKNOWN | hold allowed |
| `AWTO_L2_SEC`; `AWTO_HOLD_AUTO_SEC`; `AWTO_HOLD_TRIES` (`RL6449_Project.h:1230-1234`) | hold levels | 60 s; 5 s; 4 tries | project header | L2 = Dan 2026-11-08; the others are our choice, no reason cited | UNKNOWN | UNKNOWN | to SDK search |
| `awto_fastsw.inc:280` `AWTO_FAST_SETTLE_FRAMES` (`RL6449_Project.h:1249-1252`) | fast switch settle | 3 frames; 1 for a wake | project header | comment "frame-sync phase jump is over" | n/a | n/a | unblank |
| `awto_fastsw.inc:321` | fast path gives up | 8 frames | code literal | UNKNOWN | UNKNOWN | UNKNOWN | full path |
| `AWTO_SRC_POLL_MS` 250; `AWTO_SRC_DDC_POLLS` 12; `AWTO_SRC_SLEEP_SEC` 60; `AWTO_SRC_IDLE_COMMIT_MS` 2000 (`RL6449_Project.h:691-692,1095,1097`) | selector refresh; DDC "live"; sleep; idle commit | 250 ms; 3 s (12 polls); 60 s; 2000 ms | project header | refresh = human reading (4 Hz); DDC: HDCP Ri every 2 s x 1.25 = 2.5 s rounded up to 3 s; sleep = L2 60 s; idle commit = Dan 2026-11-12 (#132) | 2.5 s (DDC) | 1.20 (DDC) | field compare / sleep / commit |
| `AWTO_KEY_REFRESH_MS` 80; `AWTO_KEY_RETRY_MS` 250; `AWTO_GPIO_REFRESH_MS` 20; `AWTO_DBG_REFRESH_MS` 500; `AWTO_TITLE_MS` 1000 | screen redraw periods | as listed | project header | 80 = 100 ms (10 Hz floor) / 1.25; 250 = one draw about 175 ms in the sim; 1000 = Dan | 100 ms (key refresh) | 0.80 | redraw |
| `AWTO_MSG_HOST_MS` (`AwtoMsg.h:5`), `AwtoMsgWait` | host-silence limit for the debug wait | 100 ms | `AwtoMsg.h:5` | comment: poll gap 2 ms + fetch about 5 ms, x20 | 5 ms | 20.0 | channel off, message stays in the ring |
| `AWTO_HT_STALE_MS` 180000; `AWTO_HT_DRIFT_MS` 1000; `AWTO_HT_GAP_S` | host-time stale / drift | as listed | project header | Dan: 3 minutes without a sync (host sends every 60 s); drift 1 s | 60 s period | 3.0 | marks the host time stale |
| `AWTO_SET_LOOP_MS` 20; `AWTO_NV_EL_MAX_MS` 100 | settings service period; gate aging cap | 20 ms; 100 ms | `RL6449_Project.h:104,150` | derived: below key repeat 0.5 s; 5 x 20 | n/a | n/a | service call |
| `AWTO_MEAS_PERIOD_MS` 25; `AWTO_MEAS_WINDOW_MS` 1000 (`awto_meas4k.inc:29,52`) | 4K measurement sampling | 25 ms; 1000 ms | project header | UNKNOWN reason | UNKNOWN | UNKNOWN | window ends |
| `fw/ddcci/ddcci.c:86` | debug-link minute countdown | 1000 ms steps | code | n/a | n/a | n/a | link back to DDC/CI |
| `awto_diag.inc:12,49`; `awto_meas4k.inc:70,85`; `fw/diag/wdt.c:224` | spin to the next 1 ms tick | up to 1 ms | code | tick alignment | 1 tick | 1.00 | continues |
| `awto_delaycal.inc:68,70` | calibration: align 1 tick, then `DelayXms(10)` | about 11 ms once per boot, after the first stream start | code | measurement method | n/a | n/a | continues |
| `awto_t0ev.inc:238-269` | Timer0 event test commands | `DelayXms(2)`, `ucMs/6`, `ucMs/3`, `ucMs*1.25`, 2..3 ms spin | code | test-only, host-triggered | n/a | n/a | test ends |
| `fw/settings/settings_glue.c` `set_wait_ms`; `awto-rtdfw settings.c:271-273` | boot recovery hold | `DelayXms(10)` loop for up to 1000 ms | `settings.h:74` `SET_RECOVERY_MS` | derived: "longer than a key bounce, short enough to hold at power-on" | n/a | n/a | defaults restored if held |
| **NVRAM GATE (`RL6449_Project.h:146-150`; `fw/nvram/nv_gate.c` `AwtoNvService`)** | | | | | | | |
| `AWTO_NV_STABLE_MS` | ACTIVE with no switch / sync / training | 3000 ms | project header | Dan | n/a | n/a | write allowed |
| `AWTO_NV_DDC_IDLE_MS` | since the last DDC/CI request | 500 ms | project header | Dan | n/a | n/a | write allowed |
| `AWTO_NV_SAVE_MS` | after the last change | 2000 ms | project header | derived: one write per slider drag | n/a | n/a | write |
| `AWTO_NV_FORCE_MS` | dirty -> written at the latest | 30000 ms | project header | Dan | n/a | n/a | forced write |
| `AWTO_SAVE_CARD_MS` (`fw/osd/console.c`) | "Saving to memory" card | 1000 ms | project header | derived: "one glance" | n/a | n/a | card off |
| **AWTO-RTDFW (settings / menu)** | | | | | | | |
| `awto/include/settings.h:49` `SET_CONFIRM_MS`; `settings.c:259` | risky row auto-revert | 15000 ms | settings.h | derived: our UI choice | n/a | n/a | value reverts |
| `settings.h:50` `SET_SAVE_MS`; `settings.c:261` | settings save debounce | 2000 ms | settings.h | derived: one save per slider drag | n/a | n/a | save |
| `awto/settings/menu.c:610-616` | menu timeout, counted per second | registry `osd_timeout` (row 57) default 30 s, 0 = never | registry | vendor menu 10..60 s [vendor-ui]; default 30 is ours (no reason cited) | n/a | n/a | menu closes |
| `menu.c:487` `key_hold` | host key hold | arg x 50 ms | menu.c | protocol unit | n/a | n/a | key released |
| registry rows 40-43 (`awto-rtdfw settings/registry.tsv`) | source search windows | HDMI 2000 / DP 3000 ms (min 500 / 1000, max 10000) | registry | [vendor-value] = SDK defaults | 2000 / 3000 ms | 1.00 | search ends |
| registry rows 76, 78, 80 | L1 delay 0 ms, L2 60 s, L3 600 s | as listed | registry | inert, stored only. The firmware uses `AWTO_L2_SEC` 60. | n/a | n/a | n/a |
| registry row 66 `logo_ms` | boot logo time | 3000 ms | registry | no reader in the firmware (`RL6449_Project.h:1028` calls the VCP code retired) | n/a | n/a | none |

## (a) Added margin: the code value exceeds its source

- **Panel T3**: 550 ms against the datasheet T8 min 200 ms (2.75x). Against the registry note "500 ms per 27-inch 4K eDP datasheets" it is +10 %.
- **Panel T4**: 250 ms against datasheet T9 min 200 ms (1.25x, plus 1 tick).
- **Panel T2**: 250 ms against datasheet T3 max 200 ms (1.25x). This one is a timeout, so the 1.25 rule applies.
- **Panel T6 in HEAD's header**: 1100 against 1000 (+10 %). The working tree and registry now say 900.
- **`AWTO_TMDS_HPD_LOW_MS`**: 110 ms against the HDMI 1.4b 100 ms (+10 %).
- **`AWTO_DELAY_TARGET_PCT`**: all the `DELAY_*US` loops are calibrated to 105 % of nominal.
- **Audio PLL waits**: six sites coded 2 ms for a "Delay 1000us" comment (2.0x). The two audio-detect waits are 3 ms for "2 ms" (1.5x).
- **`_AWTO_INFO_POPUP_SEC`**: 6 s against the SDK 3 s (2.0x).
- **`AWTO_MSG_HOST_MS`**: 100 ms against about 5 ms (20x, far above the 1.25 timeout rule).
- **`AWTO_WDT_PROBE_MS`**: 1.28x.
- **`AWTO_SRC_DDC_POLLS`**: 3 s against 2.5 s (1.2x).
- **`AWTO_SW_SLOW_MS`**: 7.4x (a logging threshold, not a wait).
- **DP frame waits**: 45 / 90 ms against 43.5 / 87 ms (1.035x). `_DOUBLE_BUFFER_WAIT_TIME` 168 against 166.7 ms (1.008x).
- **`ScalerTimerDelayXms`**: always has up to 1 tick of extra wait. `T4..T6` are `<=` compares, so +1 tick.

## (b) Source UNKNOWN

- **Our own values with no reason cited**:
  - `AWTO_KEY_COMBO_MS` 80
  - `AWTO_REHOLD_MS` 3000
  - `AWTO_HOLD_CHECK_MS` 10
  - `AWTO_HOLD_AUTO_SEC` 5
  - `AWTO_HOLD_TRIES` 4
  - fast-path 8 frames
  - `AWTO_PS_TMDS_HOLD_MS` 50
  - `AWTO_MEAS_PERIOD_MS` 25
  - `osd_timeout` default 30 s
  - the `DELAY_30US_EXINT` steps in `awto_dbgisr.inc`
- **SDK literals with no datasheet or spec cited**, effectively all of these:
  - the `ScalerTimerDelayXms` constants (2 / 3 / 6 / 10 / 20 / 30 / 45 / 130 ms)
  - the poll bounds (10 / 20 / 40 / 45 / 50 / 100 / 130 / 180 ms)
  - the 90 ms wait-event bound
  - all `DELAY_*US` and `DELAY_XUS` steps
  - SDK timer-event periods
  - SDK search times and wait-to-active times
- **Panel T1 / T4 / T5 provenance is contradictory**:
  - the panel doc maps them to datasheet T1 / T9 / T10
  - registry says [vendor-value]
  - `docs/settings.md` says [sdk-value]
- **`_MEASURE_TIMEOUT` and `_MEASURE_RESET_TIME`**: depend on a runtime measure clock divider. I did not derive the M2PLL value.
- **`ucFrameTime`, `AWTO_DP_TWO_FRAMES`**: computed from the measured frame period at runtime.

## (c) Blocking busy-waits over 1 ms

All of these are `ScalerTimerDelayXms` or a poll, which spin and poke the watchdog each ms. Worst case:

- **Boot, once**
  - VCCK_OFF poll plus 10 ms: `RL6449_Series_Mcu.c:1762` (up to 30 ms) and `RL6449_Series_Power.c:267`.
  - `ScalerGlobal.c:140` 10 ms.
  - `ScalerCommonPower.c:68` 6 ms.
  - `ScalerCommonIOSC.c:68,104,136`: 2 ms plus two polls of up to 10 ms.
  - `ScalerPLL.c:2802` 2 ms.
  - `ScalerPLL.c:3731` DDR2 poll, up to 40 ms.
  - `RL6449_Series_PLL.c:322,328,348` 2 ms each.
  - `awto_delaycal.inc:68,70` about 11 ms, plus the loop calibration after the first stream start.
- **Display / DPTx bring-up**
  - `RL6449_Series_DisplayDPTx.c:284` 5 ms x 5 attempts.
  - `RL6449_Series_DisplayDPTx.c:495` 10 ms.
  - `ScalerDisplayDPTx.c:206` 10 ms.
  - `ScalerDisplayDPTx.c:579` 45 ms.
- **Source search and cable**
  - `SysSource.c:3982,4093,4203` 10 ms (only after a status change).
  - TMDS `ScalerTMDSRx2` / `Rx3` waits: 130 ms (`TMDSRx2.c:3342`, `Rx3.c:3345`); 20 ms (`TMDSRx2.c:3385`, `Rx3.c:3388`; `ScalerCommonSync.c:8733,9341`; `ScalerTMDSRx2_SeptPhy.c:101`, `Rx3_SeptPhy.c:101`); polls up to 130 / 180 ms; 6 ms pre-detect (`ScalerTMDSRx2_SeptPhy.c:677`, `Rx3_SeptPhy.c:677`).
  - DP RX: 45 / 90 ms frame waits, 30 ms resets, 100 ms measure polls.
  - HDMI HPD toggle: `ScalerTMDSRx2_SeptPhy.c:815` and `Rx3_SeptPhy.c:815`, 500 ms by default. Skipped while `_AWTO_HDMI_HPD_TOGGLE` is `_OFF`.
  - DP PHY compliance test: `RL6449_Series_DPRx1.c:4133` 1000 ms, plus unbounded loops at :3665, :3966 and :4050 (lab only).
- **Per mode change or measure**
  - `ScalerTimerWaitForEvent` waits of up to 90 ms each (106 sites, many in `ScalerMDomain` and `FRC`).
  - Double-buffer polls up to 168 ms.
  - `ScalerMeasureGetOfflineMeasureResult` poll of 650 ms at the xtal clock.
- **Rare or maintenance**
  - Audio PLL 2 / 3 ms, DVC mute poll up to 400 ms.
  - Settings boot-recovery hold up to 1000 ms (`awto-rtdfw settings.c:271`).
  - Watchdog probe spin 1500 ms (test command only, `fw/diag/wdt.c:222-229`).
  - `awto_t0ev.inc:238-269` test delays.
- **Non-blocking since #162**: the panel T1..T6 machine, the HDMI HPD recovery pulse, and the source/judge timer events. None of these block.
- **Interrupt-context blind spins over 1 ms**
  - `ScalerTMDSRx2SetPhy_EXINT0` and `ScalerTMDSRx3SetPhy_EXINT0`: 5.5 ms per call.
  - `ScalerDpRx1RebuildPhy_WDINT`: 0.85 ms.
  - `ScalerDpRx1Tp2SetPhy_EXINT0`: 0.71 ms.


# Part 2: added-margin review (firmware and host)


Scope note: awto-ddc has uncommitted changes (docs/nvram-settings.md, docs/speed-bench.tsv); values below are from the working tree. awto-rtdfw/settings/registry.tsv generates awto-rtdfw/awto/settings/set_table.c. Margin % = (code value / source value - 1) x 100. "Source" is the spec, the measured worst case, or the stated derivation, whichever the code or comment names.

## A. Firmware, registry defaults and firmware-facing docs (owner policy 2026-11-13: no added margin)

| file:line | value in code | source value + where it comes from | margin (%) | comment / justification quoted | firmware or host |
|---|---|---|---|---|---|
| /mnt/2tb/git/awto-ddc/fw/sdk/Project/Header/RL6449_Project.h:188 and /mnt/2tb/git/awto-ddc/fw/sdcc/awto_delaycal.inc:85-98 | AWTO_DELAY_TARGET_PCT 105 (busy-loop counts recalculated so delays land at 105 % of nominal) | nominal Timer2-derived delay (10 x 5 us, 100 us) from the Timer2 tick | +5 | "shorter copy of each pair; health limit 90..125 %" / "lands at AWTO_DELAY_TARGET_PCT of nominal" | firmware |
| /mnt/2tb/git/awto-ddc/fw/sdk/Project/Header/RL6449_Project.h:316, 321, 325 | AWTO_WDT_THR 0x577, warning at 200.1 ms | measured worst poke gap 160 ms (wd8, unit 2, /mnt/2tb/git/awto-ddc/docs/watchdog.md:215). The earlier 133 ms gives 166.25 ms (docs/watchdog.md:198), also x1.25 | +25 | "Warning = 1.25 x the measured worst poke gap" / "warning at 1399 x 0.143 = 200.1 ms" | firmware |
| RL6449_Project.h:329 | AWTO_WDT_PROBE_MS 1500 | N+1 wraps = 1172 ms (CNT1 wrap, docs/watchdog.md:56) | +28 | "probe: reset expected by 586 ms; N + 1 wraps (1172) x 1.25 -> 1.5 s" (1172 x 1.25 = 1465, rounded up to 1500) | firmware |
| RL6449_Project.h:377 (comment at 376) | AWTO_WDT_SHOW_MS 1000 | sim max main-loop pass 800 ms (sim, <4 checks) | +25 | "sim max pass < 4 checks = 800 ms) x 1.25" | firmware |
| RL6449_Project.h:418 (#else branch) | AWTO_KEY_REFRESH_MS 80 | 100 ms (10 Hz floor, stated) | -20 (refresh period 20 % shorter than the source) | "screen redraw period: 100 ms (10 Hz floor) / 1.25" | firmware (key test screen #39) |
| RL6449_Project.h:1175 | AWTO_TMDS_HPD_LOW_MS 110 | HDMI 1.4b >= 100 ms HPD low = unplug | +10 | "HDMI 1.4b: a source reads HPD low >= 100 ms as unplug" | firmware |
| RL6449_Project.h:1096-1097 | AWTO_SRC_DDC_POLLS 12 (= 3 s at 250 ms) | HDCP 1.4 Ri check every 2 s (the slowest regular DDC traffic) | +50 (3 s vs 2 s; the comment's own step is 2 s x 1.25 = 2.5 s, rounded up to 3 s) | "HDCP 1.4 Ri checks run every 2 s (the slowest regular DDC traffic) x 1.25 = 2.5 s -> 3 s = 12 polls" | firmware |
| RL6449_Project.h:1029 | AWTO_HT_STALE_MS 180000 | host sync period 60 s | +200 (3x) | "Dan: HOST marked stale after 3 min without a sync (host sends every 60 s)" | firmware |
| RL6449_Project.h:1278 (fallback when no registry; registry at 1276) | AWTO_T3_OWN_PATTERN_MS 20 | one 60 Hz frame = 16.7 ms | +20 | "one 60 Hz frame (16.7 ms) + margin before backlight on" | firmware |
| /mnt/2tb/git/awto-rtdfw/settings/registry.tsv:92 and /mnt/2tb/git/awto-rtdfw/awto/settings/set_table.c:85 | panel_t3_own default 20 (range min 17) | one 60 Hz frame, 16.7 ms (min 17 is the rounded frame) | +20 (+18 vs the 17 minimum) | "logo / background frame: one 60 Hz frame minimum" (no margin text; the margin wording is only in RL6449_Project.h:1278) | firmware (registry default) |
| /mnt/2tb/git/awto-ddc/fw/sdcc/awto_dpframe.inc:8, 11, 13 | two-frame wait = 2 x (floor(frame ms) + 1) + 1 ms, capped at SDK _DP_TWO_FRAME_TIME_MAX (2 x 45 ms) | 2 x measured frame period (VBs2Bs) | +5.0 at 60 Hz (35 ms vs 33.3 ms); +2.3 at 23 Hz (89 ms vs 87.0 ms, cap 90) | "2 frames + 1 ms tick margin, never above the SDK's 23 Hz worst case"; line 4 "ms per frame (rounded up)"; line 2 "The SDK waits _DP_TWO_FRAME_TIME_MAX (2 x 45 ms, sized for 23 Hz)" | firmware |
| /mnt/2tb/git/awto-ddc/fw/sdcc/awto_t0ev.inc:250 | ScalerTimerDelayXms(ucMs + (ucMs >> 2)) | requested event time ucMs | +25 | "the event fires inside (x1.25), still at the PS reload" (test hook, ucHow 6/7) | firmware (test code) |
| RL6449_Project.h:568 | AWTO_MSTEP_MAX 7 (a count of log lines, not time) | 5 lines for the first set-up | +40 (count) | "first set-up 5 lines x1.25" | firmware |
| RL6449_Project.h:928 | AWTO_SYNC_N 60 (ring slots, not time) | 50 lines on the console (con_wrap_sim); 38 lines x 1.25 = 47.5 (boot_sim) | +20 vs 50 | ">= cold boot 38 lines x1.25 (boot_sim, #165) and cold boot + power off 50 lines on the console" | firmware |
| RL6449_Project.h:1433 | _AWTO_INFO_POPUP_SEC 6 | SDK value 3 s | +100 (deviation, no margin wording) | "input-info pop-up on-screen time (SDK: 3)" | firmware |
| /mnt/2tb/git/awto-ddc/fw/sdk/Panel/AWTO_M280DCA_E3B.h:49 (overridden by AWTO_SET at :61-66 when the registry is used) | _PANEL_POWER_ON_T3 550 | datasheet T8 >= 200 ms (header's own citation, docs/monitors/panel-innolux-m280dca-e3b.md) | +175 | "video valid -> backlight on; datasheet T8 >= 200 ms (panel-innolux-m280dca-e3b.md)" | firmware |
| /mnt/2tb/git/awto-ddc/fw/sdk/Panel/AWTO_M280DCA_E3B.h:48 | _PANEL_POWER_ON_T2 250 | HPD bound: datasheet T2 max 200 ms (docs/monitors/panel-edid.md:47) | +25 | no comment in header; docs/monitors/panel-innolux-m280dca-e3b.md:41 "ok: bound = 1.25 x 200"; re/delays_reasons.tsv:65 "datasheet T2 max 200 ms, value 250" | firmware |
| /mnt/2tb/git/awto-rtdfw/settings/registry.tsv:95 and set_table.c:88 (docs/nvram-settings.md:223) | panel_t6 default 1100 (range 500..5000) | BOE MV270QUM-N50 spec T8 >= 1000 ms (docs/monitors/panel-edid.md:47; re/delays.tsv:1025) | +10 | registry "minimum VDD off time [vendor-value]"; re/delays_reasons.tsv "datasheet T8 >= 1000 ms, value 1100" | firmware (registry default) |
| registry.tsv:91 and set_table.c:84 (docs/nvram-settings.md:219) | panel_t3 default 550 (range 300..2000) | ">= 500 ms per 27-inch 4K eDP datasheets" (registry) = BOE T4 >= 500 ms (panel-edid.md:47). Conflicts with M280DCA header's T8 >= 200 (+175) | +10 | "host video; >= 500 ms per 27-inch 4K eDP datasheets" | firmware (registry default) |
| registry.tsv:93 and set_table.c:86 (docs/nvram-settings.md:221) | panel_t4 default 250 (labelled "T4 BL to link off") | BOE T5 >= 100 ms (panel-edid.md:47) | +150 | registry "[vendor-value]"; re/delays_reasons.tsv:21 "datasheet T5 needs >= 100 ms, so ~150 ms is margin"; re/delays.tsv:1022 "value 250 (150 ms margin)". Label mismatch: registry calls it T4, datasheet number is T5 | firmware (registry default) |
| registry.tsv:94 and set_table.c:87 (docs/nvram-settings.md:222) | panel_t5 default 20 (labelled "T5 link to VDD off") | BOE T6 0..50 ms, "recommend 0" (panel-edid.md:47) | +20 ms over the recommended 0 (no %) | registry "[vendor-value]"; re/delays_reasons.tsv:68 "datasheet T6 0-50 ms (recommend 0), value 20" | firmware (registry default) |
| registry.tsv:89 and set_table.c:82 (docs/nvram-settings.md:217) | panel_t1 default 10 | BOE T1 0.5..10 ms, so 10 = the max | 0 | registry "vendor example value, no datasheet [vendor-value]"; re/delays_reasons.tsv:19 cites the BOE spec. The two sources conflict | firmware (registry default) |
| registry.tsv:90 and set_table.c:83 (docs/nvram-settings.md:218) | panel_t2 default 250 | BOE T2 0..200 ms | +25 | registry "[vendor-value]"; the margin wording is in docs/monitors/panel-innolux-m280dca-e3b.md:41 "bound = 1.25 x 200" | firmware (registry default) |
| registry.tsv:40-43 and set_table.c:47-50 (search_hdmi_ms 2000, search_dp_ms 3000, nocable_hdmi_ms 2000, nocable_dp_ms 3000) | no source value | none (SDK defaults; re/delays_notes.md:12 "SDK defaults, no spec") | not computable | "[vendor-value]" / "per-port search time" | firmware (registry default) |

Docs that state a margin (docs/**/*.md):
- docs/monitors/panel-innolux-m280dca-e3b.md:41: T2 HPD bound 250 = 1.25 x 200, +25.
- docs/watchdog.md:198, 215: warning = 1.25 x measured gap (133 then 160), +25.
- docs/watchdog.md:58: longest legit gap < 1025.3 / 1.25 = 820 ms (a criterion, not a timer). docs/watchdog.md:200: "2x rule" (criterion).
- docs/design-162.md:24: sync ring "sized for a full cold boot x 1.25" (count, +25).
- docs/nvram-settings.md:219 "host video; >= 500 ms per 27-inch 4K eDP datasheets" with def 550 (+10), and :220 "one 60 Hz frame minimum" (no margin word).
- docs/input-status.md:25: DDC live "seen in the last 12 polls (3 s ...)" (the margin is in RL6449_Project.h:1096).
- The re/ notes (outside docs/**): re/delays_reasons.tsv:21 and re/delays.tsv:1022 "150 ms margin"; re/delays.tsv:1024 "value 20" for T6 0..50 recommend 0.

Also noted, not margins: /mnt/2tb/git/awto-ddc/fw/sdk/Project/Header/RL6449_Project.h:1062 (the 2x wait notes) and docs/sdk-model-inventory.md:646 ("within 1.1 s") are thresholds, not padding. The panel header fw/sdk/Panel/21_AU_LVDS_21_5_WUXGA_FREESYNC.h:97-103 carries T1..T6 = 100/40/300/20/40/600, which does not match the BOE values the registry and docs cite. I did not establish which panel header the AWTO build compiles.

## B. Host scripts (separate rule: 1.25 x measured worst for interface timeouts; stall backstops for host processes)

Interface timeouts (DDC/CI, ddcutil, MCCS, gdctl, SPI-flash engine, firmware-facing waits from host):

| file:line | value | measured worst / source | factor | vs 1.25x rule | comment quoted |
|---|---|---|---|---|---|
| scripts/ddc_ctl.py:20 | TIMEOUT_S 4.5 | worst 1.37 s (docs/ddc-control.md:33, 2026-11-04) | 3.3x | violates | "Limit 4.5 s = ~3x worst" |
| scripts/ddc_idle.py:16 | CTL_TIMEOUT_S 20.0 | 3-6 s worst (sleep/wake) | 3.3x of 6 s | violates | "Limit 3x = 20 s" |
| scripts/kvm.py:44 | RAW_LIMIT_S 0.17 | 130 ms worst derived (line 43) | 1.31x (1.25x = 162.5 ms) | ~ok (rounded up 4.6 %) | "x1.25 -> per-unit limit below" |
| scripts/kvm.py:46 | DDCUTIL_LIMIT_S 1.7 | worst 1.37 s | 1.24x | ok | "x1.25" |
| scripts/led_unit.py:31 | HOST_GUARD_S 15 | ~8 s derived | 1.9x | violates; additive "+ margin" | "x1.25 + margin for ddcutil" |
| scripts/led_unit.py:30 | WAIT_PS_S 3.75, WAIT_OFF_S 1.9, WAIT_ON_S 3.75, WAIT_WAKE_S 6.9 | sysm_sim 3, 1.5, 3, 5.5 s (line 29) | 1.25x (rounded) | ok | "State waits = sysm_sim bounds x1.25" |
| scripts/audio_test.py:80 | AMP_WAIT_S 1.5 | <= 400 ms (DVC ramp) | 3.75x; "+ ddc" term unquantified | cannot verify | "x1.25 + ddc" |
| scripts/audio_test.py:50 | APLAY_LIMIT_S 1.25 | tone length | 1.25x (multiplier on tone length) | ok | "x tone length: aplay runs the tone + ~0.2 s open/drain" |
| scripts/wake_time.py:24, 105 | WAKE_LIMIT_S 6.0; guard = 1.25 x (off + 6) + 10 | 1.0-1.2 s ACTIVE + 3 s search = 4.2 s | 1.43x (no 1.25 stated) | violates; additive +10 s | "+10: arm + decode reads" |
| scripts/cold_boot.py:27 | OFF_S 8 | PSU hold-up ~6 s (#27) | 1.33x (1.25x = 7.5 s, rounded up) | ~ok | "x1.25" |
| scripts/cold_boot.py:28 | LIMIT_S 15.0 | sim boot 5.7 s | 2.6x | violates | "x~2.5" |
| scripts/panel_unit.py:31 | BOOT_WAIT_S 6.0 | 2.47 s worst | 2.4x | violates | "x2.4 = 6 s" |
| scripts/panel_unit.py:32 | KEY_WAIT_S 6.0 | < 2.5 s | 2.4x | violates | "x2.4" |
| scripts/panel_unit.py:33 | SWITCH_WAIT_S 4.0 | 3 s worst | 1.33x (3.75 rounded) | ~ok | "x1.25 ~ 4 s" |
| scripts/boot_variance.py:16 | BOOT_WAIT_S 6.0 | 2.4 s | 2.5x | violates | "x2.5 = 6 s" |
| scripts/con_blank_probe.py:27 | SETTLE_S 6.0 | 1.8 s | 3.3x | violates | "x3 margin" |
| scripts/key_sim_test.py:314 | SWITCH_S 6.0 | DP search 3 s + display setting ~1 s | 1.2x of 5 s; "+ key time" unquantified | ~ok | "x1.25 + key time" |
| scripts/keymap_unit.py:28-31 | KEY_S 0.25, IDLE_COMMIT_S 2.5, SEARCH_S 5.0 | 0.2 s; 2 s; (1 + 3) s | 1.25x | ok | "x1.25" |
| scripts/osdt_unit.py:30 | SHOW_LIMIT_S 1.5 | 1.2 s unmeasured | 1.25x | ok | "1.2 s if unmeasured x1.25" |
| scripts/wdt_test.py:36 | NV_IDLE_MS 4200 | 3.3 s | 1.27x | ok | "x1.25" |
| scripts/wdt_test.py:37 | ARM_WAIT_MS 1400 | 1.1 s | 1.27x | ok | "x1.25" |
| scripts/wdt_test.py:43 | SETTLE_S 17.0 | 13.7 s | 1.24x | ok | "x 1.25 -> 17 s" |
| scripts/wdt_test.py:50 | PS_S 29.0 | 23 s | 1.26x | ok | "= 23 s x 1.25 -> 29 s" |
| scripts/wdt_test.py:53 | PS_STATUS_S 9.0 | 7 s | 1.29x | ok | "7 s x 1.25" |
| scripts/wdt_test.py:58 | HOLD_LIMIT_S 146.0 | 117 s | 1.25x | ok | "x1.25 -> 146 s" |
| scripts/wdt_test.py:64 | WAKE_S 9.0 | 3 s x 1.25 + 5 s rule | 1.25x + 5 s additive | additive term | "3 s x 1.25 -> 4 s, plus the 5 s monitor-return rule -> 9 s" |
| scripts/wdt_test.py:68 | FLASH_OP_MS 360 | 288 ms | 1.25x | ok | "288 ms x 1.25" |
| scripts/wdt_test.py:48 | DPMS_S 3.0 | < 1 s | 3x | violates | "x3" |
| scripts/wdt_test.py:94-102, 1115 | sim checks at 1.1 x and +-10 % | n/a | +10 % tolerances | tolerance, not a timeout | "+-10 %" |
| scripts/dev.py:1192 | RECOVER_BUS_WAIT_S 5.0 | EDID 1-2 s after relay | 2.5x | violates | "5 s = 2.5x" |
| scripts/rtd_diag.py:292 | HOLD_WAIT_S 5.0 | 2 s safe window | 2.5x | violates | "2.5x the 2 s safe window" |
| scripts/rtd_flash_sector.py:76 | T_WRSR_LIMIT 0.05, T_ERASE_LIMIT 0.25 | tW 40 ms, tSE 200 ms (MX25L8006E) | 1.25x | ok | "Limits = 1.25x max" |
| scripts/rtd_flash_sector.py:81-82 | T_PROG_LIMIT 0.05, T_BUFRDY_LIMIT 0.05 | tPP 3 ms | 13x (floor) | floor, not 1.25x | "floor at ~5 polls" |
| scripts/rtd_flash_sector.py:264 | flash CRC poll limit n x 8 us x 1.25 + 0.02 | derived | 1.25x + 20 ms additive | additive term | "+ 20 ms for the poll granularity" |
| scripts/dbg_link.py:139 | expiry = minutes x 60 x 1.25 | firmware timeout | 1.25x | ok | (no comment) |
| docs/flash-unprotect.md:21-23 | same as rtd_flash_sector.py | MX25L8006E | 1.25x | ok | "1.25 x tW max 40 ms" |

Host-process stall backstops (not interface timeouts; ratios shown for the record):
- scripts/nv_test.py:160 timeout 10 (one ddcutil call ~0.2 s, 50x); scripts/audio_test.py:66 and scripts/led_unit.py:32 DDC_LIMIT_S 10 (~1 s, 10x); scripts/osd_test.py:96 timeout 5 (0.4 s, 12x); scripts/rtd_identify.py:22 DDC_TIMEOUT 15 ("few s worst", 15 s backstop).
- scripts/wdt_test.py:47 GDBUS_S 5 (~0.1 s, 50x).
- scripts/kvm_demo.py:15 STEP_LIMIT_S 15 (~0.7 s, 21x); scripts/fastmachine.py:55 GCC_TIMEOUT_S 60 (< 2 s, 30x, "project host-process stall limit"); scripts/sdcc_bank.py:49 ASM_TIMEOUT 30 (< 2 s); scripts/sdcc_isr_libs.py:33 CC_TIMEOUT 60 (< 2 s); scripts/sdk_option_audit.py:28 PP_TIMEOUT 60 (~2 s); scripts/sdcc_link.py:17 LINK_TIMEOUT 120 (~20 s, 6x); scripts/rtd_extract_all.py:38 PARSER_LIMIT_S 120 ("capped generously").
- Multiplier-labelled build and sim budgets: scripts/fw_gates.py:42-43 (3x cold run: keys 150, wdt 60, rules 30, LIMIT_S 30); scripts/fw_build.py:33-34 (3x cold); scripts/fw_compile.py:42 COMPILE_TIMEOUT 200 ("3x worst-case rule"); scripts/sdcc_size_probe.py:19 (3x); scripts/flash_layout_measure.py:21 BUILD_TIMEOUT 600 ("3x + margin"); scripts/fastcore_check.py:39 TOOL_LIMIT_S 460 (3x); scripts/osd_catalog.py:40-42 RUN_LIMIT_S 650 ("3x cold worst case"); scripts/sdk_option_audit.py:141 BUILD_TIMEOUT 240 (x3 backstop); scripts/fw_variants.py:27 BUILD_TIMEOUT 300 (x3 cold); scripts/fw_stage.py:14 GATES_LIMIT_S 90 ("15x margin is the backstop only"); scripts/sim_timelines.py:19 SIM_LIMIT_S 300 ("12x margin"); scripts/boot_sim.py:32 BUDGET_INSTR 160 M ("75 M x2 margin", 2.1x); scripts/sim_test.py:10 CAP 20 M (">=5x margin"); scripts/wdt_sim.py:87 EVENT_BUDGET 20 M ("x10"); scripts/desk_layout.py:54 ("3x cold worst case").
- Additive or wording-only margins in host code: scripts/wake_time.py:105 (+10 s), scripts/rtd_flash_sector.py:264 (+20 ms), scripts/led_unit.py:31 ("+ margin"), scripts/audio_test.py:80 ("+ ddc"), scripts/ps_probe.py:133 (7 s x 1.25 -> 9 s, OK), scripts/power_cycle.py:22 ("1.25x" on OFF).

Host items not checked line-by-line (medium breadth): the remaining keys_sim.py, wake_sim.py, host_time_sim.py, ddr_sweep.py and kvm.py / host_time.py paths were checked only by grep; their comments state x1.25 or a measured worst, consistent with the host rule.

No file was modified.
