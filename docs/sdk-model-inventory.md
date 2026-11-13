# SDK model inventory (for #162) - 2026-11-12


Sources read:
- Tree: awto-ddc-ui (`wb-p14ui`, head 41d860f), `tmp/sdcc-port/src`, `scripts/keil2sdcc.py` and `keil2sdcc_drops.py`.
- Overlay, `fw/sdcc/*.inc`, `fw/awto/**`, `/mnt/2tb/git/awto-rtdfw-ui/awto`.
- Docs: handover (dated 11-09), watchdog.
- Issues: #78 #81 #83 #84 #129 #132 #144 #145 #146 #150 #151 #157 #162.
- docs/nvram-settings.md and docs/osd.md: headings and a skim only; the NVRAM and OSD facts below come from the issues.

Tags: [code] read in source. [issue] taken from an issue or comment. [inferred] my reading, unverified. Line refs are keil2sdcc OUTPUT lines unless a file is named.

---
## 0. Findings that change the picture
- **The #84 dead-port guard and the #83 D1 pre-fill are NOT in wb-p14ui.** They live on `wb-p14swap` (194116a) and `wb-p14pf`. Commit b721714 says "its base #84 dead-port guard 194116a not taken". [code: no `AwtoDeadPortPoll` or `AwtoPrefillPoll` anywhere in fw/ or the port; branch --contains]
  - Today `AwtoInputSelect` (fw/ddcci/ddcci.c:12) accepts a port with no cable. EXIT/UP "next input" and VCP 0x60 therefore have the #84 failure again: fixed port, no cable, NOSIGNAL, power saving, never back.
  - The registry row `kvm_prefill` is inert (only toggled by test cmd 0x3D).
- **Early panel bring-up is two separate SDK-path calls plus one raw GPIO** [code]:
  - (a) `AwtoPanelVddEarly()` is inserted in `SysMainSystemInitial` after stage 4. It does a raw `PCB_PANEL_POWER(ON)` plus logging, with no wait and **no SDK panel-state change**. The SDK panel status stays `_PANEL_POWER_OFF_STATE`.
  - (b) At mode INITIAL, `RTDOsdSystemFlowProc` (RTD2014Osd.c:96-97) runs `AwtoBootConsole()` then `AWTO_BOOT_PANEL_ON()` = `UserCommonInterfacePanelPowerAction(_BACKLIGHT_ON)`.
    - This blocks inside the OSD handler for T1 10 + HPD poll up to T2 250 + link + T3 + PWM.
    - Because it is called from `UserCommonInterfaceOsdHandler`, it blocks that main pass.
    - `AwtoSwPoll` logs mode changes once per pass, so the mode stays "POWER OFF" in the log until the pass returns. This is why #162 sees POWER OFF from +492 to +989 ms [inferred, matches the evidence].
  - (c) Display setting then runs `_PANEL_ON` again (`_PANEL_POW_SEQ_FAST_MODE == _ON`, SysMode.c DISPLAY_SETTING case), and ACTIVE runs `_BACKLIGHT_ON` again.
    - By code, both are no-ops when the panel status is `_BACKLIGHT_ON_ALREADY`. The only extra effects are the probe/stage log lines (24/26/27, `AwtoDiagStage(5/7)` re-fire).
    - So the eDP retrain at +1609 and the second backlight-on at +1758 in #162 are NOT explained by the SDK `_PANEL_ON`/`_BACKLIGHT_ON` code alone. Candidates: a DPTx stream/format re-enable inside `SysModeSetUpDisplayCapture` or `ScalerDisplay*`, or the status not being ALREADY at that moment. Open until #162 step 2 (boot profile).
- **Hidden drivers of resources outside the obvious modules:**
  - `AwtoTmdsStuck` (fw/log/swlog.c:104) pulses the D2/D3 HDMI HPD pins with a blocking `ScalerTimerDelayXms(110)`, called from the SysJudge hook.
  - `AwtoL2LinkOn/Off`, `PCB_BACKLIGHT_POWER_PIN` and `ScalerGlobalWatchDog` are called straight from awto_fastsw.inc.
  - fw/log/sync.c's `AwtoPsWakePoll` makes power-status wake decisions.
  - fw/test/testcmd.c can drive input, power, NVRAM and keys.
- **Time bases: at least six.** `g_usTimerCounter` (SDK, rebased near `_EVENT_TIME_MAX`), `usT2Isr` (g_stAwtoDiag), `AwtoUpMs` (32-bit), `AwtoSyncNow`, `AwtoFastNow`, `AwtoSrcNow`, plus Timer0 event ms. [code]
- **Logs: at least four parallel rings/streams.** `g_stAwtoSw` (switch events), `AwtoSync` ring (+ `AwtoSyncPush` stage lines), `g_stAwtoDiag` stages, tokenised `AwtoMsg`/`DebugMessage`, and the GPIO change ring. #146: two line formats on the console. [code, issue]
- Power saving: the "~2 s main pass" on tmds1 was a measurement error (sampled before power status SAVING). Real pass 15.6 ms on IOSC (~3.1x slower MCU clock); poll every 5.9-6.0 ms with the 14 poll sites (#144 comments, tmds3). [issue]

---
## 1. The SDK's own state machines as built

### 1.1 SysPower (SysPower.c:`SysPowerHandler` 271, `SysPowerSwitch` 440)
- The handler is a 2-level switch on `GET_TARGET_POWER_STATUS()` x `GET_POWER_STATUS()`. It runs once per main pass.
- Status values: AC_ON (boot only), OFF, NORMAL, SAVING.
- Boot: `SysMainSystemInitial` sets AC_ON, the target from NVRAM `_MONITOR_POWER_STATUS` (NORMAL or OFF), and mode POWER_OFF.
- Transitions (`SysPowerSwitch` action → what it does):

| from → to | action | notable work (blocking) |
|---|---|---|
| AC_ON → NORMAL | `AC_ON_TO_NORMAL` | LDO NORMAL, `ScalerSyncPowerProc`, `UserInterfacePowerSwitch` (LED on), `UserCommonInterfaceOsdPowerOnInitial`, memory power on, `SysSourceInfoReset`, `SysModeSetFreeRun` |
| OFF → NORMAL | `OFF_TO_NORMAL` (or `OFF_TO_FAKE_OFF` when `SysPowerCheckNormal` false) | same + NVRAM `_MONITOR_POWER_STATUS`=ON, **SaveSystemData** |
| SAVING → NORMAL | `PS_TO_NORMAL` | same, no NVRAM write |
| NORMAL → SAVING | `NORMAL_TO_PS` | `UserInterfacePowerSwitch`: LED breathe, **`PanelPowerAction(_PANEL_OFF)` (T4 250 + T5 20 blocking)** + our `AwtoNvFlush()`; then `SysModeResetState(RESET_TO_POWER_SAVING)`, memory off, `ScalerSyncPowerProc`, LDO SAVING |
| NORMAL → OFF | `NORMAL_TO_OFF` | LED off, panel off, NVRAM power=OFF + Save + `AwtoNvFlush()`, `SysSourcePowerOffProc`, `SysModeResetState(RESET_TO_POWER_OFF)` |
| SAVING → OFF, AC_ON → OFF | `PS_TO_OFF`, `AC_ON_TO_OFF` | similar |
| FAKE_OFF / FAKE_PS | `NORMAL_TO_FAKE_*`, `FAKE_*_TO_NORMAL` | DP MST / Type-C only; effectively unused on this board (`SysPowerCheckFakeSaving` true only for NOSUPPORT mode or user force) |

- Triggers (who sets the target power status):
  - SDK: SysMode `SET_TARGET_POWER_STATUS(SAVING)` when `SOURCE_SWITCH_FINISH && UserInterfaceGetIntoPSStatus` in mode POWER_SAVING; and `(NORMAL)` on `UserInterfaceGetCableResetStatus`.
  - SDK: `SysSourceDetectPort` PS predetect true → NORMAL (SysSource.c ~1418/1486).
  - Ours: the key POWER edge (fw/keys/keys.c → power-target calls); `AwtoPsWakeFire` (fw/log/sync.c); `AwtoWakeRelease(3)` L3 → SAVING; VCP 0xD6 `set_ap_power_mode`; `AwtoSourceOpen` sleep rule (#139); test cmd 0x3E; the debug link/KVM clears `FORCE_POW_SAV`.
- LED: `PCB_LED_*` macros → `AwtoLedSetMode` (awto_led.inc: ON/OFF/BREATHE on P3.5/P3.6).

### 1.2 SysMode / SysJudge (SysJudge.c:`SysJudgeHandler`, SysMode.c:`SysModeHandler`/`SysModeResetState`)
- Mode state is set ONLY by `SysJudgeStateChangeEvent(mode)`. It refuses while `GET_MODE_RESET_TARGET != NO_RESET`, or while any `MODE_STATE_CHANGE_*` flag is pending.
- Mode work (`SysModeHandler`) runs after SysJudge in the same pass. `SysModeHandler` clears `MODE_STATE_CHANGE_MODE` at its end.
- Judge transitions (`SysJudgeHandler`; the first switch is the power status):

| judge sees | mode now | → next | condition |
|---|---|---|---|
| power OFF | any ≠ POWER_OFF | POWER_OFF | |
| power SAVING | any ≠ POWER_SAVING | POWER_SAVING | |
| NORMAL | POWER_OFF | INITIAL | |
| NORMAL | INITIAL | SEARCH | next pass |
| NORMAL | SEARCH | DISPLAY_SETTING | `SOURCE_JUDGE` && `ModeGetTimingConfirm` && `!CheckNoSupport`; starts the NOSIGNAL timer SEC(1) (judge-true), NOSUPPORT timer 0.5 s if unsupported. Also gated by `UserInterfaceGetLogoStatus` (logo gone now) |
| NORMAL | SEARCH | NOSIGNAL | `SOURCE_SWITCH_FINISH` (all searched) |
| NORMAL | DISPLAY_SETTING | ACTIVE | `ModeGetActiveReady && UserCommonInterfaceReadyForActive`; else (re)arm `JUDGE_ACTIVE_STATE` timer = `SysJudgeGetActiveWaitTime` (VGA 50 / DVI,HDMI,DP 100 ms) or NOSUPPORT timer 2 s |
| NORMAL | NOSIGNAL / POWER_SAVING | DISPLAY_SETTING | timing confirm again |
| ACTIVE | | any | `SysJudgeCheckStatus()==FALSE` (our hook `if((AWTO_FAST_JUDGE_HOLD()==FALSE) && ((AWTO_SLOW_DUE_JUDGE()) \|\| mode≠ACTIVE) && CheckStatus()==FALSE && AWTO_WAKE_HOLD()==FALSE)`) → `SysJudgeModeResetProc` → reset target |

- Reset actions (`SysModeResetState`): `RESET_TO_SEARCH`, `…DISPLAY_SETTING(_WITHOUT_FORCETOBG)`, `…NOSUPPORT`, `…POWER_SAVING`, `…POWER_OFF`.
  - Each calls `UserCommonInterfaceOsdResetProc` (→ `UserInterfaceAdjustOsdResetProc` → `OsdDispDisableOsd`) and `ScalerGlobalResetProc`. Cancels the judge timers.
- Per-mode work (`SysModeHandler`):
  - POWER_OFF / INITIAL: nothing.
  - SEARCH / NOSIGNAL / POWER_SAVING:
    - timing measure → `SET_MODE_TIMING_CONFIRM`;
    - in POWER_SAVING: target power SAVING when `SOURCE_SWITCH_FINISH && IntoPSStatus`;
    - `UserInterfaceGetCableResetStatus` → target NORMAL, reset to SEARCH, `SysSourceCableResetProc`.
  - DISPLAY_SETTING: `SysModeDisplaySetting()` (blocking, heavy; ~1450 ms in the log). With `_PANEL_POW_SEQ_FAST_MODE` it calls `PanelPowerAction(_PANEL_ON)`, then `AdjustColorProc`, then `SET_MODE_DISPLAY_SETTING_READY`.
    - Inside, `SysModeSetUpDisplayInitialization` has the "backlight action" which our sub turns into `AWTO_BL_OFF_OR_BLANK(1)`: forced background (blank) instead of backlight off (`_AWTO_KEEP_BACKLIGHT`).
  - ACTIVE, on the change-mode flag: `ScalerGlobalFirstActiveProc`, `UserCommonInterfaceOsdActiveProc`, **`PanelPowerAction(_BACKLIGHT_ON)`**, `AwtoSwCacheStore` (our), `SysSourceFirstActiveProc`; then `ScalerSyncActiveProc` each pass.
  - NOSUPPORT / FACTORY: nothing (Mindray-only branch).
- Dwell timers: NOSIGNAL SEC(1) after judge true; NOSUPPORT 0.5 s / 2 s; ACTIVE wait 50-100 ms; source search per-type times (HDMI 2 s, DP 3 s, VGA 0.5 s, Type-C 4.5 s; registry `search_*` / `nocable_*` call `SysSourceSetDefaultSearchTime`/`SetNoCableSearchTime` via `set_ap_search_time`). [code RL6449_Project.h:1564-1568]

### 1.3 SysSource (SysSource.c:`SysSourceHandler`, `SysSourceSwitchPort`, `SysSourceDetectPort`, `SysSourceJudge`, `SysSourceCableDetection`, `SysSourceSwitchInputPort`)
- Per pass: `SysSourceCableDetection` (our `AWTO_SLOW_DUE_CABLE`, currently every pass because `_AWTO_SPLIT_CABLE` = OFF).
- Then, unless mode is POWER_OFF/INITIAL or force-PS:
  - if `!SOURCE_JUDGE(searchIndex)`: `SysSourceSwitchPort` (next port by scan type), `ScanPortInitial`, `SearchTimeInitial`, `DetectPort` (PS predetect or normal predetect + scan), `SysSourceJudge`.
- Scan types: auto-in-group, auto-without-group, fixed port (`_SOURCE_SWITCH_FIXED_PORT`, set by `AwtoInputSelect` and by the selector).
- Switch: `SysSourceSwitchInputPort` (HDMI HPD toggle suppressed by `_AWTO_HDMI_HPD_TOGGLE == _OFF`; idle receivers kept by `AWTO_IDLE_RX_OFF`); then `SysModeSetResetTarget(RESET_TO_SEARCH)` (full path). Our fast path replaces both for a cached port.
- Cable status: `g_stPortCableStatus` from `SysSourceCableDetection`; `UserInterfaceGetCableResetStatus` (RTD2014UserInterface.c:1843) compares against the NVRAM search port only; our sub gates it with `AWTO_PS_CABLE_SDK()` (power NORMAL only) when `_AWTO_PS_WAKE`.
- Blocking waits in detection: TMDS PS predetect reset+`ScalerTimerDelayXms(5)` (removed by sub when `_AWTO_PS_WAKE == _ON`); `ScalerTMDSScanInputPort` ~180 ms; DP Rx1 scan 0.3-0.5 s (`ScalerDpRx1DisplayFormatSetting`/`FifoCheck` two-frame wait: SDK 2x45 ms → our measured `AWTO_DP_TWO_FRAMES()`); HDMI `ScalerTimerPollingFlagProc` bounded loops.

### 1.4 Panel power (UserCommonInterface.c:`UserCommonInterfacePanelPowerAction` 761; `_PANEL_STYLE == _PANEL_DPTX`, T6 timer mode OFF)
Status var: `GET_PANELPOWERSTATUS()` ∈ {`_PANEL_POWER_OFF_STATE`, `_WAITING_FOR_BACKLIGHT`, `_BACKLIGHT_ON_ALREADY`, `_PANEL_BACKLIGHT_OFF`}.

| event | from | steps (blocking) | to |
|---|---|---|---|
| `_PANEL_ON` | OFF_STATE | `ScalerTimerWaitForActiveTimerEvent(PANEL_POWER_OFF)` (T6 wait if still running) → VDD on (probe 24, **stage 5**) → **T1 10** → DPTx power seq PANEL_ON, PHY init → **T2: HPD poll ≤ 250** (feeds WDT per ms) → probe 26 → `DPTxLinkSequence` (~33 ms) → **stage 7**/probe 27 → (if ≠ ALREADY) stream enable, power seq → timer **T3** (`_PANEL_POWER_ON_T3`, `USER_TIMER_EVENT_PANEL_BACKLIGHT_ON`) | WAITING_FOR_BACKLIGHT (backlight on from the timer event) |
| `_PANEL_ON` | ALREADY | nothing (probes only) | |
| `_BACKLIGHT_ON` | OFF_STATE | same VDD/T1/T2/link, then **T3 blocking** (`AwtoDiagPanelT3Wait`: delay calibration runs inside it), PWM, `PCB_BACKLIGHT_POWER(ON)` (**stage 8**), power seq BACKLIGHT_ON, then `UserAdjustBacklight` | ALREADY |
| `_BACKLIGHT_ON` | `_PANEL_BACKLIGHT_OFF` | stream enable, backlight on | ALREADY |
| `_BACKLIGHT_ON` | ALREADY | nothing | |
| `_BACKLIGHT_OFF` | any | PWM 0, backlight off (SDK ~300 ms) | `_PANEL_BACKLIGHT_OFF` |
| `_PANEL_OFF` | ≠ OFF_STATE | PWM 0, BL off, DPTx BL-off seq, **T4 250**, stream disable, idle pattern, **T5 20**, SSC off, PHY off, VDD off, timer **T6 1100** | OFF_STATE |

- Values (registry `PANEL_T1..T6`, defaults AWTO_M280DCA_E3B.h:47-53): T1 10, T2 250, T3 550, T4 250, T5 20, T6 1100; plus `PANEL_T3_OWN` default 20 ms (T3 when the scaler shows its own black pattern, fast boot) - this is `AWTO_T3_OWN_PATTERN_MS`, used in `AwtoDiagPanelT3Wait` [code RL6449_Project.h]. Measured on unit 3: VDD→HPD 115 ms, HPD→link 33 ms [issue #78].
- Entry points today (see §3): SysMode (DISPLAY_SETTING, ACTIVE), `UserInterfacePowerSwitch`, RTDOsd (INITIAL boot, lines 200/235/241/251), RTD2014UserAdjust:857, SysSource via `SysModeSetUpDisplayInitialization`, `UserCommonInterface.c` (the `_BACKLIGHT_OFF` sub), our L1/L2 hold, the AWTO wake paths.

### 1.5 OSD ownership
- The SDK path runs: `UserCommonInterfaceOsdHandler` → `UserOsdHandler` = `RTDOsdSystemFlowProc` (per-mode: INITIAL → our boot console + panel; SEARCH/ACTIVE → LED) + `RTDOsdEventMsgProc` (timer-event driven: no-signal, no-cable, power-saving cards, info pop-up at ACTIVE `_OSDEVENT_ACTIVE_DO_ONE_TIME_MSG`, 6 s `_AWTO_INFO_POPUP_SEC`).
- Resets: every `SysModeResetState` and `UserInterfaceAdjustOsdResetProc` → `OsdDispDisableOsd`. Our hook `AwtoHoldBlocksDisable` (fw/test/testcmd.c) blocks it only for the #28 debug pop-up holds, not for the console. [code]
- Ours on the OSD engine: the text layer `osd_tc_*` (fw/osd/text_layer.c) used by console (dbgpop, osdcard `AwtoDiagConsole`), cards (`OsdDispOsdMessage` SDK body removed), source selector (`AwtoSourceOpen/Key`), key/GPIO/WDT panels, awto menu (rtdfw settings/menu.c, osd/ui.c).
- Console release rule: "owns the OSD only while its map is in place: an SDK pop-up or mode reset releases it (`AwtoConLost`)" [docs/osd.md]. Each time the SDK mode path resets the OSD (display setting → `OsdDispDisableOsd`), the console is lost → m4/m5/m6 patches (re-apply view registers, redraw once settled, view at row 0).
- Remaining SDK OSD pieces: input-info card flows (`_OSDEVENT_*`), OSD timeout timers (`_USER_TIMER_EVENT_OSD_DISABLE` etc.), `OsdDispDisableOsd`, hot-key menus (DDC/CI, DP version), factory menu (`_AWTO_FACTORY`), `GET_OSD_STATE()` machine (partly; `OperationTable` removed #129).

### 1.6 Timers
- SDK: Timer2, 1 ms tick → `g_usTimerCounter` (16-bit, rebased) and the event table (`ScalerTimerActive/Reactive/Cancel/SearchTimerEvent`, `SysTimerHandler` runs events in main). Blocking: `ScalerTimerDelayXms` (waits on `g_bNotifyTimer2Int`), `ScalerTimerPollingFlagProc`, `ScalerTimerWaitForEvent`, `ScalerTimerWaitForActiveTimerEvent`. All three delay/poll/wait loops now feed the WDT per ms (SUBS #131).
- SDK WD-timer events (DP rebuild PHY, HDMI RR) were on the WD counter; replaced by our Timer0 scheduler (`awto_t0ev.inc`, same function names; `_INSTANT_TIMER_EVENT_0` is OFF: Timer0 boot-logo fade gone). 1 ms ticks while an event is pending.
- Our pollers (non-SDK-event): `AwtoSlowDue` (10 ms), `AwtoWakePoll` (10 ms hold check), `AwtoPsWakePoll` (5 ms), key debounce/repeat, NV flush gate, console refresh, selector poll `AWTO_SRC_POLL_MS`, host-time clock. Each uses its own time base (§0).
- Watchdog: one hardware WDT (FFEA/FFE9/FF3A). The SDK "disable" line is removed (it never worked). Warning IRQ (int2) 200.1 ms, reset 585.9 ms. SPI-flash ops halt the CPU and stop the counter (FFEA bit5). ~15 feed sites (`AWTO_WDT_FEED(site)`), `AWTO_WDT_PASS` in `AwtoDiagMainPass`. [docs/watchdog.md, #150]

### 1.7 NVRAM
- SDK: EEPROM emulation in flash bank 15 pages 11-12 (`UserCommonFlashSaveItem`, `RTDFlashMoveData`, page erase every ~239 writes). 95 fields in 6 structs (System 27, OSD 49, BriCon 2, ColorProc 3, SixColor 12, PanelUsedTime 2). `_CHECKSUM` 0xA3 (ours; change = defaults reload). SDK `RTDNVRamStartup` loads/recovers at boot; `AwtoMsgLoad` is added after it.
- SDK save call sites: `UserCommonNVRamSaveSystemData()` in `UserInterfacePowerSwitch`, `UserInterfaceAdjustOsdActiveProc` (search port at ACTIVE: now no-save sub), OSD adjusts.
- Now (#151, nv2): all SDK item saves deferred by hook (`AwtoNvDefer`); flush gate in fw/nvram/nv_gate.c: ACTIVE stable 3 s + DDC/CI idle 500 ms + 2 s since last change; forced after 30 s; immediate on power off / power-saving entry (`AwtoNvFlush()` subs in `UserInterfacePowerSwitch`). Registry (rtdfw settings) = RAM view of SDK fields; 36 awto-only rows in an aux block (SDK items 0x40-0x43); legacy rtdfw record (nvram.c) read once for import. Input saved only on selector/menu close.
- Flash ops halt the CPU (> 1 s for chained erase+program: the #150 bite).

---
## 2. Hook inventory (every place our code changes SDK behaviour)
Rule sources in `scripts/keil2sdcc.py` (RULES 62-115, WRAPS 120-133, INSERTS 143-336, SUBS 341-532), `keil2sdcc_drops.py` (56 lines), `fw/awto/*/rules.py`.

### 2.1 Global regex RULES (keil2sdcc.py:62-115)
| rule | does | area | issue |
|---|---|---|---|
| `_INTERNAL_AUDIO_TEST_SUPPORT` ifdef + D1 internal-gen `if 0` | audio test builds | audio | - |
| `b1OsdDpD1PortVersion` default → `_AWTO_DP_D1_VERSION` | DP 1.2 default | NVRAM/DP | #28 |
| `data pData[` → xdata; storage-first pointer decls; `code`/`data` → `__code`/`__data`; `sfr`, `interrupt`, `using` (dropped, DROP_USING), `_at_`, pragmas | Keil → SDCC port | toolchain | #8 |
| CheckMDomain FRC condition widened | debug msgs build | debug | #37 |
| `ScalerTimerActiveTimerEvent(SEC(3), …OSD_DISABLE)` → `SEC(_AWTO_INFO_POPUP_SEC)` | info pop-up 6 s | OSD/timers | - |
| `ScalerTimerDelayXms(_PANEL_POWER_ON_T3)` → `AwtoDiagPanelT3Wait` | delay calibration inside T3 | panel | #53.6 |
| `while(g_bFwHalt != 0);` → `&& AwtoMsgWait()` | debug host-silence timeout | debug | #56 |
| `bit g_bNotifyTimer2Int / g_bWDTimer2Update` → volatile | ISR flags | timers | #26 |

### 2.2 WRAPS (compile-out / conditional) 
- Info bubble const when `_AWTO_POPUP_ICON_AWTO` ON; `GET_OSD_DDCCI_STATUS()` forced by `_AWTO_DEBUG_PORT` / `_AWTO_DDCCI_ENGINES`; `_CHECKSUM` override; DDC RAM array externs.
- DROP_WRAPS (keil2sdcc_drops.py): DP PHY CTS (`_AWTO_DP_PHYCTS`, ON), factory menu (`_AWTO_FACTORY`, ON), gamma tables (`_AWTO_GAMMA_ALL`), flash table (`_AWTO_FLASH_ALL`). All defaults ON = nothing dropped; they are size switches (#65).

### 2.3 INSERTS (line before anchor), grouped. Anchors in keil2sdcc.py:143-336.
| # | where (SDK file:function) | inserted | area | issue |
|---|---|---|---|---|
| 1 | RTD2014OsdFontDynamicIcon_1.c | `fw/osd/mark_icon.c` | OSD icon | #46 |
| 2 | RL6449_Series_Mcu.c | `_AWTO_DDCRAM_DEFINER`; `awto_dbgport.inc` before `ScalerMcuDdcciSwitchPort` | DDC/CI | #28 |
| 3 | Pcb_List.h, User_Pcb_Include.h, User_Panel_List.h, User_Panel_Include.h | our board id 0x4F, panel id 0x3D includes | board/panel | #7 |
| 4 | ScalerPLL.c (3), ScalerMDomain.c (14 `AwtoMeasEvent`), ScalerMeasure.c, SysTimer.c T2 ISR `AWTO_MEAS_T2ISR` | 4K60 measurement ring; DHtotal debounce forced one pass; last-line finetune off | measure | #26 |
| 5 | ScalerCommonDebug.c | `AwtoMsg.h` include; `awto_dbgisr.inc` in EXINT1 ISR | debug link | #26 #38 |
| 6 | SysMain.c (before `main`) | `awto_led`, `awto_diag`, `awto_sw`, `awto_sync`, `awto_meas4k`, `awto_loopsplit`, `awto_loopprof`, `awto_wdt` | all | various |
| 7 | SysMain.c `SysMainSystemInitial` / `main` | `AwtoDiagInit`, `AwtoMeasInit`, `AwtoSyncInit`, `AwtoWdtInit`; stage 3, 4; **`AwtoPanelVddEarly()`** (after stage 4) | boot/panel | #23 #63 #139 |
| 8 | SysMain.c main loop | `AwtoSwPoll`, `AwtoDiagMainPass`, `AwtoGpioPoll`, `AwtoDiagTestCmd`, `AWTO_SW_FAST_POLL`, `AWTO_SW_POLL_MARKS` (x2), `AWTO_SET_LOOP`, DDCCI poll, `AWTO_NET_POLL`, `AWTO_LP(0..10)`, `AWTO_SW_MARK(0..10)` | poll sites | #60 #67 #75 #80 |
| 9 | SysMain.c main loop | **`AWTO_PS_POLL_SITE()` x 14** before each of: AwtoGpioPoll, KeyHandler(AwtoKeyPoll), AwtoDiagTestCmd, SysPowerHandler, SysJudge, SysTimer, SysSource, SysMode, SysDpRx, SysTMDSRx, Hdcp2, OsdHandler, DdcciHandler, SysColor | wake poll between handlers | #144 |
| 10 | SysSource.c | `AwtoSyncBegin` in `SysSourceSwitchInputPort`; `AwtoSyncDetect` end of `SysSourceDetectPort`; `awto_fastsw.inc` before `SysSourceSwitchInputPort`; `AWTO_SW_MARK(20-23)`; probe 19 | input | #60 #139 |
| 11 | SysMode.c | `AwtoSyncTiming`, `AwtoSyncFreq`, probes 4,5,11,12,14-18, `AwtoSwCacheStore` at ACTIVE | mode | #60 #139 |
| 12 | SysJudge.c | probes 1,2,3,20-23; `AWTO_TMDS_STUCK()` | judge | #60 #78 |
| 13 | UserCommonInterface.c `PanelPowerAction` | `AwtoSwEvent(POWER)` at switch; probes 24/26/27; stages 5,7,8 (both `_PANEL_ON` and `_BACKLIGHT_ON` paths); `AWTO_KEY_OSD_RESET()` in `OsdResetProc` | panel/log | #63 #78 |
| 14 | RTD2014UserInterface.c | `AwtoSwEvent` probes 7,8, BLANK before `ScalerDDomainBackgroundEnable(DISABLE)` in `AdjustOsdActiveProc`; `AwtoSetInit` | OSD/ACTIVE | #60 #67 |
| 15 | RTD2014Osd.c | probes 9, 10 in the one-time message | OSD | #60 |
| 16 | RTD2014OsdDisplay.c | `AwtoHoldBlocksDisable` guard in `OsdDispDisableOsd`; `AwtoMenuForget`; `AWTO_FW_TAG` + dbgpop, osdcard, keypop, gpiopop, wdtpop, settings glue | OSD | #28 #34 #124 #134 |
| 17 | RTD2014Key.c | code in fw/test/testcmd.c, fw/keys/keytest.c + keys.c + keyinject.c, fw/input/inputs.c | keys | #129 |
| 18 | RTD2014Ddcci.c | code in fw/input/ports.c, fw/ddcci/ddcci.c, fw/net/net.c | DDC/CI | #60 #80 |
| 19 | ScalerCommonMcu.c | `awto_delaycal.inc`; M2PLL re-entry keeps calibrated counts (sub) | timers | #53 #54 |
| 20 | SysTimer.c / SysInt.c | `AWTO_DIAG_T2ISR`, `AWTO_DIAG_EX1ISR`, `AWTO_MEAS_T2ISR` | ISRs | #23 #26 |
| 21 | ScalerDPRx1_SeptPhy.c | `awto_dpframe.inc`; `AWTO_SW_MARK(30-37)` | DP | #60 |
| 22 | ScalerMcu.c, ScalerMDomain.c, ScalerMeasure.c | `AwtoDiagStage(2)`, `awto_freq` calls | log | #34 |
| 23 | rtdfw glue: `fw/settings/settings_glue.c`, `fw/osd/text_layer.c`, `fw/nvram/flash_io.c`, `fw/nvram/nv_gate.c`, `fw/keys/keyinject.c` | settings glue | settings | #67 |
| 24 | wdt rules.py | `fw/diag/wdt.c` (SysMain.c), `AwtoWdtInit` before EA, `fw/osd/console.c` | watchdog | #131 |
| 25 | ScalerCommonTimerFunction.c end | `awto_t0ev.inc` | timers | #138 |

### 2.4 SUBS (keil2sdcc.py:341-532 + wdt/settings rules.py)
| area | substitution | issue |
|---|---|---|
| KVM / DDC | RTD2014Ddcci.c port defines → D1 DP / D2 / D3; `SysSourceSwitchInputPort(x)` at DDCCI VCP 0x60 → `AwtoInputSelect(x, 0x60)` (7 sites) | #60 |
| HDMI | TMDSRx2/3 `_AWTO_SCDC_KEEP` guard; `AWTO_IDLE_RX_OFF` replaces `ScalerGDIPhyPowerProc(..OFF)` x60; `AWTO_IDLE_TMDS_OFF` x2; HPD toggle gated `_AWTO_HDMI_HPD_TOGGLE` (SysSource.c, UserCommonNVRamSystem.c) | #60 #78 |
| Debug | `_DEBUG_DDC_CHANNEL_SEL` x4 + `ScalerMcuDdcciSwitchPort` → `_AWTO_DBG_FOLLOW` | #28 |
| Boot | RL6449_Power.c: DDR/1.1 V waits `_AWTO_FAST_BOOT == OFF` only (200 ms + 2x10 ms) | #63 |
| Panel/blank | SysMode.c x2 and UserCommonInterface.c x1: `PanelPowerAction(_BACKLIGHT_OFF)` → `AWTO_BL_OFF_OR_BLANK(site)` | #60 |
| Settings | NVRamOsd.h `b1AwtoMsgOn`; `UserInterfaceInitial` + `AwtoMsgLoad` | #74 |
| Loop | SysJudge CheckStatus condition (hold + slow due); SysSource `SysSourceCableDetection` gated | #75 #78 |
| DP | DPRx1 two-frame waits ×2 → `AWTO_DP_TWO_FRAMES()` | #60 |
| **Wake (#144)** | TMDSRx2/3 PS predetect: reset/5 ms wait/disable removed → `AwtoPsTmdsLive`; `TMDSPSPreDetect` body → counts DDC detect only (`AwtoPsDdcSeen`); DPRx1 PS predetect: AUX toggle counted (`AwtoPsAuxSeen`) not returned; `UserInterfaceGetCableResetStatus()` ANDed with `AWTO_PS_CABLE_SDK()` | #144 #145 |
| Boot logo (#144) | `OsdDispShowLogo()+BACKLIGHT_ON+3 s timer` → `AwtoBootConsole(); AWTO_BOOT_PANEL_ON();`; logo functions, tables, VLC cases, externs, timer case removed (13 subs) | #144 |
| Menu | `OsdDispMainMenu*` → `AWTO_REALTEK_MENU_OPEN` / `AWTO_REALTEK_KEYINFO` (4 subs) | #120 |
| Keys (#129) | `UserInterfaceKeyHandler()` call → `AwtoKeyPoll()`; SDK key scan, key-message block, `MenuNone`, `MenuHotKeySource`, `OperationTable`, repeat timer cases, `RTDKeyInitial()` removed (8 subs) | #129 |
| Selector (#134/#139) | hot-key source menu x3 removed, `OsdDispHotKeySourceMenu()` → `AwtoSourceOpen()`, input icon load removed, 3 s PS-close timer removed | #134 #139 |
| Cards (#124) | `OsdDispOsdMessage` body removed; 7 info string builders stubbed | #124 |
| Icons | icon tables → shared stub (`AWTO_ICON`), 2 tables | #117 #118 #120 |
| NVRAM (#151) | `UserCommonFlashSaveItem` → `AwtoNvDefer`; item-write/move → `AWTO_NV_ITEM_WR`; `UserInterfaceAdjustOsdActiveProc` no save; `AwtoNvFlush()` at power-off ×2 and PS entry | #151 |
| NVRAM timing (#150) | `AWTO_NV_EV(3,4,5)` in erase/WREN/Move; `AwtoWdtLibPoke(9,10)` in flash read/write | #150 |
| Watchdog | disable line removed; feeds at delay/poll/event loops, flash pokes ×3 (`MCU_FFEA |= 0x40` → feed), OSD string loop, HPD poll; SysTimer 1 ms tick WD work removed; WD IRQ → `AWTO_WDT_IRQ`; Timer0 events (`AwtoT0EvIsr`, `AwtoT0EvClock`, `AWTO_T0EV_EXINT0`); WD-timer functions `#if 0` | #131 #138 #150 |
| Audio | `UserAdjustAudioVolumeMapping` → `AwtoAudioGain`; mute `|| AWTO_AUDIO_HOLD()`; DAC output = headphone | #93 |
| gamma | `UserCommonAdjustGamma` → `AwtoGammaLoad` (clean) | #65 |
| `MCU_FFEA` init | `AWTO_SYNC_MARK()` before WDT counter clear | #29 |

### 2.5 Overlay replacements (`fw/overlay`)
| file | lines | delta vs SDK |
|---|---|---|
| Project/Header/RL6449_Project.h | 1790 | the central macro file (see 2.6) |
| Project/Header/AwtoSetIds.h, AwtoRegs.h | 117, 87 | generated ids / reg names |
| Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h (+_PINSHARE.h) | 600 + 374 | our board; `PCB_LED_*`, `PCB_KEY_STATE` bands (A0/A1/P3.0), `PCB_PANEL_POWER`, backlight pin |
| Panel/AWTO_M280DCA_E3B.h | 74 | eDP HBR2 x4 TX1; T1-T6 `AWTO_SET(PANEL_Tn)` |
| Kernel/Common/Project.h | 3 | Beacon-only PCB/panel redefinition guard |
| Kernel/Common/Debug.h | ~43 | all debug categories ON |
| User/RTD Series/RTD2014Osd/Header/RTD2014Project.h | 2 | `_OSD_ROTATE_OFF`; `_DP_DEBUG_MSG` ON |
| EDID tables D1/D2/D3 | - | production EDID |
| Kernel/Scaler/ScalerCommonFunction/Code/AwtoMsg.h | 59 | tokenised message macros |

### 2.6 Macros redefined / policy in RL6449_Project.h
`_AWTO_BOOT_PANEL_EARLY`+`AWTO_BOOT_PANEL_ON` (1084-1090); `_AWTO_FAST_BOOT` 1100; `_AWTO_KEEP_BACKLIGHT`/`AWTO_BL_OFF_OR_BLANK` 1103; `_AWTO_HDMI_HPD_TOGGLE` OFF; `_AWTO_SCDC_KEEP` ON; `_AWTO_TMDS_HPD_RECOVER` ON (N=3, max 2 pulses, 110 ms low); `_AWTO_KEEP_IDLE_RX` + `g_ucAwtoKeepIdle` (registry `keep_idle_rx`, fixed at boot); `_AWTO_FAST_SWITCH` (forced OFF without sw log or keep-idle); `_AWTO_WAKE_HOLD` + `AWTO_L2_SEC` 60 / `AWTO_L3_SEC` 600 / `AWTO_HOLD_*` / `AWTO_REHOLD_MS` 3000 / `AWTO_HOLD_TRIES` 4; `_AWTO_PS_WAKE` ON / `_AWTO_PS_AUX_WAKE` OFF (#163), `AWTO_PS_POLL_MS` 5, `AWTO_PS_CABLE_SDK()`; `_AWTO_LOOP_SPLIT`, `AWTO_SLOW_MS` 10, `_AWTO_SPLIT_JUDGE` ON / `_AWTO_SPLIT_CABLE` OFF; `_PANEL_POW_SEQ_FAST_MODE` ON; `_INSTANT_TIMER_EVENT_0` OFF; `_CHECKSUM` 0xA3; `_SOURCE_DEFAULT_SEARCH_TIME_*`, `_WAIT_TIME_TO_ACTIVE_*`; `_AWTO_DIAG`/`_AWTO_SYNC_LOG` ON (error if DIAG off: keys depend on it); `_AWTO_DBGISR`, `_AWTO_DBG_SWAP`, `_AWTO_NET`, `_AWTO_MEAS4K`, `_AWTO_FREQ`, `_AWTO_SW_LOG` ON; `_AWTO_LOOP_PROF`, `_AWTO_SW_MARKS` OFF.

### 2.7 Poll sites
Main loop (SysMain.c): 14 `AWTO_PS_POLL_SITE` + `AWTO_SYNC_POLL()` (inside `AwtoSwPoll`) + `AWTO_SW_FAST_POLL` (fast path + `AWTO_WAKE_POLL`) + `AWTO_SW_POLL_MARKS` + `AWTO_SET_LOOP` + `AWTO_DDCCI_POLL` + `AWTO_NET_POLL` + `AWTO_OSD_SYNC_POLL` (inside `AwtoGpioPoll` and key handler) + `AwtoGpioPoll` + `AwtoKeyPoll` + `AwtoDiagTestCmd` + `AwtoDiagMainPass`. ISR hooks: T2 (diag/meas/WDT check), EX1 (debug slave answers), EX0 (T0EV flag test), Timer0, WD int2.

---
## 3. Resource → every code path that drives it today
(For Dan's principle 1; "SDK" = SDK-original path, "ours" = awto code.)

### 3.1 Panel power / eDP link / backlight
| path | file:function | drives | trigger |
|---|---|---|---|
| SDK full power-up | UserCommonInterface.c:`PanelPowerAction(_PANEL_ON/_BACKLIGHT_ON/_BACKLIGHT_OFF/_PANEL_OFF)` | VDD, T1-T6, HPD, link, stream, BL | callers below |
| SysMode DISPLAY_SETTING | SysMode.c:`SysModeHandler` (`_PANEL_ON` under FAST_MODE); `SysModeSetUpDisplayInitialization` | `_PANEL_ON` again; blank (our sub) | mode state |
| SysMode ACTIVE | SysMode.c:`SysModeHandler` | `_BACKLIGHT_ON` | first active |
| SDK power actions | UserInterface.c:`UserInterfacePowerSwitch` | `_PANEL_OFF` | power status change |
| SDK OSD | RTD2014Osd.c:200/235/241/251, RTD2014UserAdjust.c:857 | `_BACKLIGHT_ON` | key/OSD events |
| **ours: raw early VDD** | fw/log/swlog.c:`AwtoPanelVddEarly` (SysMainSystemInitial) | `PCB_PANEL_POWER` only, no SDK state | boot |
| **ours: boot panel** | RTD2014Osd.c:96 `AWTO_BOOT_PANEL_ON` | full `_BACKLIGHT_ON` at INITIAL | mode INITIAL |
| ours: blank instead of BL off | `AWTO_BL_OFF_OR_BLANK` x3 | `ScalerDDomainBackgroundEnable` | mode reset / display setting |
| **ours: L1/L2 hold** | awto_fastsw.inc:`AwtoWakeHold/AwtoWakePoll/AwtoL2LinkOff/On/AwtoHoldBacklightSdk` | `PCB_BACKLIGHT_POWER_PIN` direct, eDP stream/SSC/PHY off/on direct, SDK `_BACKLIGHT_OFF` at release | judge failure in ACTIVE |
| ours: fast unblank | `AwtoSwFastPoll` | `ScalerDDomainBackgroundEnable`, `UserCommonInterfaceOsdActiveProc` | fast switch |
| ours: LED | awto_led.inc | power LED P3.5/P3.6 (through PCB_LED_*) | power status |
| ours: T3 wait | awto_delaycal.inc:`AwtoDiagPanelT3Wait` | blocking inside T3 | panel on |
| ours: PWM/backlight level | fw/settings/settings_glue.c:`set_ap_backlight` | PWM | menu / VCP |
| ours: probes | `AwtoSwEvent(24/26/27)`, `AwtoDiagStage(5/7/8)` | log only | |

Duplicates: boot INITIAL `_BACKLIGHT_ON` + early raw VDD + display-setting `_PANEL_ON` + ACTIVE `_BACKLIGHT_ON` = four entry points for one bring-up; three different "backlight off" ways (SDK BL_OFF 300 ms, blank, pin-only L1).

### 3.2 OSD
| path | what | owner |
|---|---|---|
| SDK message/state machine | `RTDOsdSystemFlowProc/EventMsgProc`, `_USER_TIMER_EVENT_OSD_*`, `OsdDispDisableOsd` | SDK |
| cards | fw/osd/console.c:`OsdDispOsdMessage` (SDK body removed) | ours, called by SDK events |
| source selector | `AwtoSourceOpen/Key/Step`, `AwtoOsdSyncPoll` | ours, opened by SDK no-signal/wake event and keys |
| console (boot/diag) | `AwtoBootConsole` (SDK INITIAL hook), `AwtoDiagConsole`, `AwtoSyncConPoll` auto-open, test cmds, UP+DOWN | ours |
| key/GPIO/WDT panels | fw/osd/console.c | ours |
| awto menu | rtdfw settings/menu.c + ui.c; `AwtoMenuForget`, `AwtoSetLoop` | ours |
| SDK hot-key DDC/CI + DP-version menus, factory menu, `AWTO_REALTEK_MENU_OPEN` | RTD2014Osd.c | SDK (reachable by test cmd only) |
| OSD teardown | every mode reset → `OsdDispDisableOsd` | SDK, takes the console (`AwtoConLost`) |

### 3.3 Input search / switch
| path | file:function | trigger |
|---|---|---|
| SDK auto/fixed search | SysSource.c:`SysSourceHandler/SwitchPort/DetectPort/Judge` | mode SEARCH/NOSIGNAL |
| SDK switch + reset | `SysSourceSwitchInputPort` + `SysModeSetResetTarget(RESET_TO_SEARCH)` | OSD selector, SDK hot-key |
| **ours: `AwtoInputSelect`** | fw/ddcci/ddcci.c:12 (VCP 0x60, menu input row, test cmds 0x31-0x33, selector) | fixed port; fast path first |
| ours: fast path | `AwtoSwFast/Go/Poll` | cached switch (§5) |
| ours: hold wake | `AwtoWakePoll` → `AwtoRxRescan`, `AwtoSwFastGo`, `AwtoWakeRelease` → `SysModeSetResetTarget(SEARCH)` | L1/L2 |
| ours: selector | `AwtoSourceKey` | keys |
| ours: key next-input | `AwtoKeyNextInput` / UP opens selector | keys |
| ours: HDMI HPD recovery | `AwtoTmdsStuck` | judge fails ×3 |
| SDK cable reset → SEARCH | `UserInterfaceGetCableResetStatus` | cable change (gated in PS) |
| ours: wake search | `AwtoPsWakeFire` / `AwtoSwEvent` | PS wake |
| config: idle rx kept, HPD toggle off | project macros | |

### 3.4 Power status
| path | trigger |
|---|---|
| SDK: `SysPowerHandler` | target ≠ status |
| SDK sets target: SysMode (PS entry/cable reset), SysSource PS predetect, `UserInterfacePowerSwitch` |
| ours: key POWER (fw/keys/keys.c), `AwtoPsWakeFire`, `AwtoWakeRelease(3)`, VCP 0xD6 `set_ap_power_mode`, selector sleep rule, test cmd 0x3E, debug link / KVM `SET_FORCE_POW_SAV_STATUS(FALSE)`, `AwtoInputSelect` |

### 3.5 NVRAM
| path | note |
|---|---|
| SDK `UserCommonNVRamSaveSystemData`, `RTDFlashSaveOSDData`, `UserCommonFlashSaveItem` | now deferred by hook |
| ours: `AwtoNvDefer` / flush gate (fw/nvram/nv_gate.c), `AwtoNvFlush()` at power transitions, `AwtoNvCommitSel`, `AwtoSaveCard` | |
| ours: registry `set_sdk_put` / aux items 0x40-0x43; legacy record read (`set_load_legacy`) | |
| SDK boot/recovery writes still allowed (`s_ucNvOn == 0`) | |
| `AwtoMsgLoad`/`b1AwtoMsgOn` debug flag in OSD struct (#74) | |

### 3.6 Cross-cutting
- Timers/WDT: SDK event table + ours (§1.6); WDT feeds from SDK waits (subs) and ours.
- DDC/CI: SDK `UserCommonDdcciHandler` (engine 0), our spare-engine poll (fw/ddcci/ddcci.c), debug slave in EXINT1 (awto_dbgisr), IP-over-DDC (fw/net/net.c), debug-port follow (awto_dbgport). KVM/debug cannot share a channel (#79).
- Keys: one reader and dispatcher after #129.

---
## 4. State machines with the second driver marked
Notation: [SDK] original driver, [AWTO+] our second driver.

### 4.1 Power status
```
AC_ON --target NORMAL [SDK: NVRAM power status; AWTO+: none]--> NORMAL   (action AC_ON_TO_NORMAL)
AC_ON --target OFF-->      OFF
OFF   --target NORMAL-->   NORMAL   [SDK: key POWER via UserInterface? AWTO+: AwtoKeyRoute power target]
NORMAL --target SAVING-->  SAVING   [SDK: SysMode when switch finished; AWTO+: AwtoWakeRelease(3), VCP D6, sleep rule 0x3E]
SAVING --target NORMAL-->  NORMAL   [SDK: PS predetect (SysSourceDetectPort), UserInterfaceGetCableResetStatus (gated);
                                     AWTO+: AwtoPsWakeFire (cable edges, EDID, AUX, DPCD 600h, TMDS clock), key wake]
NORMAL --target OFF--> OFF          [SDK: POWER key; AWTO+: AwtoKeyRoute]
```
Second driver: the wake. In SAVING there are two wake paths (SDK predetect + AwtoPsWakePoll). SDK predetect bodies are cut down so they only count; but the SDK predetect on the current search port still wakes (observed: wd8/tmds1 wakes were "by the SDK source detect, not our poll").

### 4.2 Mode
```
POWER_OFF --(power NORMAL)--> INITIAL --(next pass)--> SEARCH
SEARCH --(judge+timing confirm, supported)--> DISPLAY_SETTING --(active ready)--> ACTIVE
SEARCH --(all ports searched)--> NOSIGNAL --(timing confirm)--> DISPLAY_SETTING
ACTIVE --(CheckStatus fail)--> [reset target SEARCH/DISPLAY_SETTING] --> SEARCH ...   [AWTO+: hold L1/L2/L3 intercepts here (no reset); AWTO+: fast path skips SEARCH+DISPLAY_SETTING]
any --(power SAVING)--> POWER_SAVING --(timing/cable/PS predetect)--> DISPLAY_SETTING
any --(unsupported timing)--> NOSUPPORT
```
Second drivers per transition:
- INITIAL: AWTO+ boot console + panel (blocking 0.5 s).
- DISPLAY_SETTING: AWTO+ blank sub, fast mode `_PANEL_ON` [SDK], `AwtoSyncFreq`.
- ACTIVE: `AwtoSwCacheStore` and fast path (the fast path does its own `ScalerGlobalFirstActiveProc` + `UserCommonInterfaceOsdActiveProc` from `AwtoSwFastPoll`, skipping the SysMode ACTIVE entry and its `_BACKLIGHT_ON`).
- Logging: `AwtoSwPoll` logs mode changes once per pass (not at the transition), so durations in blocking passes show the old mode.

### 4.3 Panel
Table in §1.4. Second drivers marked in §3.1.

### 4.4 Source search
`SEARCH_PORT_INITIAL → SEARCH_TIME_INITIAL → DetectPort (predetect, scan) → Judge → (timing) → next port when time elapsed → SOURCE_SWITCH_FINISH`. AWTO+: fixed-port scan type set by `AwtoInputSelect`/selector, which makes "all ports searched" mean one port; no cable guard in this tree (#84 branch only).

---
## 5. Fast switch / KVM / hold model (awto_fastsw.inc, awto_fastsw_scaler.inc, fw/log/swlog.c, fw/ddcci/ddcci.c)
State machine (as coded, `_AWTO_FAST_SWITCH` and `_AWTO_WAKE_HOLD` ON, `_AWTO_KEEP_IDLE_RX` ON):
```
ACTIVE(port P, cache[P] valid)
  |-- KVM/VCP 0x60/menu/selector to port Q ---> AwtoInputSelect: skip if Q==current ACTIVE
  |      AwtoSwFast(Q): refuse codes (event 0xA0): 1 no cache / bad port, 6 mode≠ACTIVE, 7 fast pending, 8 same port, 9 mode reset pending,
  |                     10 registry fast_switch off, 0x21..0x28 timing field differs (AwtoFastScalerMatch), 3 receiver unstable (AwtoRxStable)
  |      refused --> SysSourceSwitchInputPort + RESET_TO_SEARCH   (full path)
  |      taken --> AwtoSwFastGo: blank, search index=Q, scaler snapshot applied, g_ucAwtoFastPending=Q
  |           AwtoSwFastPoll (each pass): wait N frames (3 switch, 1 wake) -> clear flags -> +1 frame -> check M-domain/watchdog flags,
  |           SysSourceStableCheck, ScalerMeasureTimingChange, SysJudgeCheckStatus -> ok: FirstActiveProc + OsdActiveProc (unblank)
  |           fail up to 8 frames -> SEARCH reset (event 5, why 0xA1) ; mode left ACTIVE meanwhile -> abandon (event 4)
  |-- judge fails in ACTIVE (signal lost): AwtoWakeHold (L1) if cache valid & not NoHold & not 3 s after a fast wake
  |      L1: blank, free-run WD off, backlight PIN off, g_ucAwtoHold=P (judge held: AWTO_FAST_JUDGE_HOLD / AWTO_WAKE_HOLD)
  |      every 10 ms (AwtoWakePoll): AwtoRxRescan(P) = StableDetect | NormalPreDetect + scan
  |      L2 after usL2Sec(60): eDP stream/SSC/PHY off, VDD kept   (AwtoL2LinkOff)
  |      L3 after usL3Sec(600): AwtoWakeRelease(3) -> SysPowerSetTargetPowerStatus(SAVING)
  |      auto-search + another cabled port with cache after 5 s: AwtoWakeRelease(9) -> RESET_TO_SEARCH
  |      signal back: AwtoSwFastGo(P) (+ L2 link on + backlight pin on, probe 25/27/28) ; tries>4 -> release(4)
  |      fast wake fails 8 frames -> back to hold (event 7)
  '-- mode leaves ACTIVE by the SDK meanwhile: AwtoHoldBacklightSdk (SDK _BACKLIGHT_OFF to fix its state), hold cleared (event 0x10)
```
Resources it drives: panel/backlight pin and eDP link (direct, bypassing `PanelPowerAction` state); the D-domain blank; input index/search state (`g_ucSearchIndex`, `SET_SOURCE_JUDGE/TYPE`); power status (L3); scaler I/M/D registers (snapshot apply); WD enable (`ScalerGlobalWatchDog(DISABLE)`); mode reset target.

Known misbehaviour and gaps:
- SDK panel state is not updated by L1/L2 (SDK still thinks "backlight on"); `AwtoHoldBacklightSdk` repairs it when leaving to the SDK path by calling the SDK `_BACKLIGHT_OFF` (~300 ms). [code, #78]
- Wake-hold: wk4 backlight blink (fixed with pin + 3 s re-hold guard); wk8 L3 re-held (fixed with NoHold flag); wk10 auto-escape on idle DP cable (fixed by requiring a trained link). [issue #78]
- Auto search with a second live HDMI: idle HDMI has no clock detect (freq-detect IRQ off), so the hold only leaves via the 5 s "cached cable" rule; `kvm_prefill` for idle ports is NOT built in this tree; first switch to a never-shown port always takes the full path (~1 s). [#83, #78]
- First switch after deep sleep back to HDMI takes the full path (idle receiver powered down; not investigated). [handover 4.3]
- #84: dead-port switch (EXIT/next input/VCP 0x60 to a port without a cable) leaves the unit in POWER_SAVING on a fixed port. Fixed on wb-p14swap10 (`AwtoInputSelect` refuses; `AwtoDeadPortPoll`), **absent in wb-p14ui**.
- L2 target 100-150 ms is not reachable (floor ~200 ms: VDD→HPD 115 ms + T1/PHY + link + 60 ms SDK backlight on). [#78]
- Fast path unconfirmed on hardware for pre-filled ports (#83 not on a real second input); "odd behaviour" reports have no issue yet [no 'fast path' issue found beyond #60 #78 #83 #84 #75 #79 #81].
- Registry rows `fast_switch` (read by `AwtoSwFast`), `keep_idle_rx` (boot-fixed `g_ucAwtoKeepIdle`), `pwr_l1_en/l2_en/l3_en/ms/s` (written into `g_stAwtoPower` via `set_ap_power`?), `search_*`/`nocable_*` (live via `set_ap_search_time`), `d1/d2/d3_enable`, `search_order`: **#81 lists input enables, search order, power levels as inert**; their current state needs checking per row (`set_ap_power` is a "placeholder store (see StAwtoPwrCfg)" at glue.inc:745). `kvm_prefill` inert.
- Resource duplicates specific to this model: three ways to blank/backlight-off; two ways to start a switch (SDK reset vs fast); `AwtoWakeRelease` also restarts search/power in competition with SDK power handler; `AWTO_FAST_JUDGE_HOLD` disables the SDK judge while ours runs the same checks (`AwtoSwFastPoll` calls `SysJudgeCheckStatus` itself).

---
## 6. Collisions (our model vs SDK model)
| # | collision | evidence |
|---|---|---|
| C1 | Early panel bring-up blocks inside the OSD handler while SDK is in POWER OFF/INITIAL; input SEARCH starts only after | #162: SDK mode POWER OFF +492..+989, SEARCH +996, ACTIVE 1822 (unit 2, m4). Code: RTD2014Osd.c:96-97 sub; `AwtoPanelVddEarly` SysMain; `_PANEL_ON` blocks T1+HPD(≤250)+link+T3 |
| C2 | Panel brought up 3-4 times (raw VDD, INITIAL, display setting `_PANEL_ON`, ACTIVE `_BACKLIGHT_ON`); retrain at +1609 and second backlight call at +1758 | #162; by code only logging is re-run when status ALREADY → cause unconfirmed (see §0) |
| C3 | Console blanked/lost by display setting: SDK `OsdDispDisableOsd` on every mode reset; console redrawn/re-applied (m4, m5, m6) | commits 72150d8, 49a83c3, d7343ae; docs/osd.md `AwtoConLost`; osdcard.inc:872 "display setting took the OSD" |
| C4 | SDK self-wake vs our wake poll (two wake paths in power saving) | #144: wd8 "wake by the SDK source detect, not our poll (polls 3)"; tmds1: poll never ran; Dan 11-12 "fix the PS wake poll". Subs gating the SDK predetect (SeptPhy x4, `UserInterfaceGetCableResetStatus`). #145 q9: SDK no longer wakes on search-port unplug |
| C5 | PS main pass 15.6 ms on IOSC; 14 poll sites wedged into the main loop to reach a 5 ms wake poll (-5.5 % loop rate) | #144 tmds3 comments (the earlier ~2 s was a measurement error) |
| C6 | Keys: two readers/dispatchers (SDK scan + OperationTable vs input monitor) | #129 (resolved: one reader, `AwtoKeyPoll/Route`); remaining open items #132 (combo window, injected keys skip wake rule, HOLD unused, two ways into selector, MENU+DOWN at boot toggles debug link too) |
| C7 | NVRAM two stores (SDK items vs registry record) with 52 duplicated fields, diverged on unit 2 (input, osd_timeout, hue) | #151 listing; resolved by SDK-as-owner (nv2) but: boot-time SDK writes still immediate, input store semantics bolted on (selector only), power status `_MONITOR_POWER_STATUS` write only flushed at transitions, SDK MST default-order bug, legacy record import cause of wiped values unknown |
| C8 | NVRAM flash ops halt the CPU > 1 s: watchdog bite | #150 (fixed with FFEA bit5; stall test 216 ms) |
| C9 | Watchdog vs SDK WD-timer events: SDK used the WD counter for protocol events and cleared it in the 1 ms tick | #138; replaced by Timer0 scheduler |
| C10 | Fast path / hold bypass SDK judge, power and panel state (see §5) | #78/#60 |
| C11 | KVM input select vs search: fixed port without cable | #84 (absent from this tree) |
| C12 | Debug slave vs DDC/CI on one DDC channel | #79 (resolved by park/swap; still `_AWTO_DDCCI_ENGINES`/FIXCH config) |
| C13 | Log formats/time bases differ (GPIO ring vs sync ring, `ms` vs `MS`); crash record 16-bit ms not convertible | #146, #157 |
| C14 | Time bases: SDK `g_usTimerCounter` rebases near max (jumps seen) → we count `usT2Isr`; PS Timer2 rate unknown on IOSC | fw/log/swlog.c:`AwtoSwNow` comment; #144 |
| C15 | `kvm_prefill`, `d*_enable`, `search_order`, `power levels` rows inert vs UI shows them | #81, #151 listing (48 nv rows inert) |
| C16 | Key press in ACTIVE re-arms OSD disable timer (SDK) → info pop-up never closes with timeout ≤ 10 s | #132 q6 |

---
## 7. Module table (whole awto layer)
Verdicts are suggestions for the review, not decisions. "R#162" = redesign under #162.

### 7.1 `fw/sdcc/awto_*.inc` (28 modules)
| module | lines | issues | entry points | drives | state | overlap / dead | verdict |
|---|---|---|---|---|---|---|---|
| dbgisr | 152 | #28 #38 #80 | ISR: `ScalerDebugIntProc_EXINT1` insert | debug slave (0x35) DDC/CI | XDATA | SDK debug slave; #147 large call trees in ISRs | keep (review ISR cost) |
| dbgpop | 631 | #34 #131 #144 #157 | `OsdDispOsdMessage` hook, console open, test cmds | OSD text layer, console | `s_ucConOpen`, row buf | shares helpers with osdcard; name misleads (it is the text layer) | merge into one "console/OSD" module; R#162 (OSD ownership) |
| dbgport | 107 | #28 #60 #67 #79 | `ScalerMcuDdcciSwitchPort` hook | DDC channel select | `g_ucAwtoDbgLink` | overlaps ddcci engines | keep with ddcci |
| ddcci | 459 | #28 #60 #67 #79 #80 #139 #151 #157 | main loop `AWTO_DDCCI_POLL`; VCP 0x60/0x37; key combo; test cmds | DDC/CI engines, **input switch (`AwtoInputSelect`)**, debug link, NV flush gate flag | switch log, link timer | input-switch logic belongs to source model; lacks #84 guard | split: DDC/CI transport keep; `AwtoInputSelect` → R#162 source model |
| delaycal | 158 | #53 #54 #150 | `AwtoDiagPanelT3Wait` (T3), `ScalerMcu5usDelayCalc` | timers, blocking inside panel T3 | cal counts | known health fail 10/11; panel T3 dependency | R#162 (panel) + keep calibration |
| diag | 64 | #23 #53 #63 #157 | main + stage hooks | stage log | `g_stAwtoDiag` | stages duplicate sync-ring STAGE lines | merge into sync/log |
| dpframe | 22 | #60 | DPRx1 sub | DP waits | frame ms | - | keep |
| fastsw | 417 | #60 #67 #78 | main `AWTO_SW_FAST_POLL`, `AwtoInputSelect`, SysMode ACTIVE | panel pin, eDP link, input index, power target, WD, blank | cache[3], hold L, tries, pending | duplicates SDK panel/power/judge paths | R#162 (hold + fast path as part of mode/panel model) |
| fastsw_scaler | 163 | #60 | called by fastsw | scaler regs snapshot/apply | 3×48 B cache | fragile (48 B opaque) | keep, move with fastsw |
| freq | 49 | #26 #34 | ScalerMeasure/MDomain hooks | none (measurement) | `StAwtoFreq` | - | keep |
| gpio | 242 | #139 #144 | main `AwtoGpioPoll`; generated from inputs.tsv | input reader, key mask | ring, values | single reader | keep |
| gpiopop | 452 | #139 #144 #157 | menu/test cmd 0x43 | OSD GPIO page | row cache | OSD helpers duplicates | merge into console module |
| icon_info | 28 | #46 | SDK icon table | OSD icon | const | likely dead (cards on text layer, `_AWTO_POPUP_ICON_AWTO`) | check, probably delete |
| keypop | 161 | #34 #39 | key test screen | OSD | - | - | merge into console module |
| keys | 400 | #85 #120 #129 #132 #139 | main `AwtoKeyPoll` | key events → power, menu, selector, console, debug link | combo/repeat state | done model (#129); open #132 | keep (single dispatcher); route targets change with R#162 |
| keytest | 162 | #39 #67 #85 #129 #144 | `AwtoKeyMsg`, source key | key log | `g_stAwtoKey` | partly duplicates keys | merge into keys |
| led | 37 | - | PCB_LED_* macros, tick | LED P3.5/P3.6 | mode/phase | #95 other power GPIOs not driven | keep (move into power model) |
| loopprof | 67 | #60 | main (`_AWTO_LOOP_PROF` OFF) | none | - | OFF by default | delete or keep as tool |
| loopsplit | 48 | #75 | SysJudge/SysSource subs | judge/cable cadence | slow timers | interacts with hold/fast judge conditions | R#162 (judge cadence) |
| meas4k | 95 | #26 | T2 ISR + 14 MDomain/PLL inserts | none | ring | research tool, ON by default, costs ISR + 18 inserts | candidate: build-time off / delete |
| net | 610 | #56 #67 #80 | main `AWTO_NET_POLL`, EXINT1, DDC/CI op D0 | DDC/CI | rings | XDATA free 9 B | keep optional |
| osdcard | 1122 | #29 #34 #39 #114 #124 #129 #134 #139 #144 #150 #151 #157 | SDK OSD events, keys, main (`AWTO_OSD_SYNC_POLL`), boot INITIAL | OSD, **input selector sleep rule**, console auto-open, NV save card | selector, console open req | overlaps SDK OSD event machine, console lost on resets | R#162 (OSD ownership) |
| sw | 133 | #60 #63 #78 #139 | panel/probe hooks, `AwtoSwPoll`, `AwtoPanelVddEarly` | **VDD raw early**, **HDMI HPD pulses**, switch log | `g_stAwtoSw`, ucLastMode | one of 4 logs; HPD recovery is a hidden driver | split: log → sync; early VDD + HPD recovery → R#162 |
| sync | 882 | #29 #34 #78 #139 #144 #150 #151 #157 | main (poll + PS sites), SDK hooks, host-time | **PS wake decisions**, log, console | ring, wake flags | PS wake = second wake path | split: log keep; wake poll → R#162 power model |
| t0ev | 280 | #138 #29 | Timer0 ISR, ScalerCommonTimerFunction | protocol events (DP rebuild, HDMI RR), WDT | event ms table | replaces SDK WD events | keep |
| testcmd | 224 | many | `AwtoDiagTestCmd` main | input switch, power, NV, keys, holds | - | duplicates VCP/mailbox entry | keep as test API; route through the new model |
| wdt | 265 | #29 #131 #138 #150 #151 | `AwtoWdtInit`, T2 ISR, WD IRQ, feeds | watchdog | `g_stAwtoWdt` | SDK disable removed | keep |
| wdtpop | 99 | #131 #144 #150 | console panel | OSD | - | - | merge into console module |

### 7.2 `fw/awto/**` and glue
| item | lines | purpose / entry | notes | verdict |
|---|---|---|---|---|
| fw/settings/settings_glue.c + fw/osd/text_layer.c + fw/nvram/flash_io.c | 820 | rtdfw settings platform: flash shim (`fl_*`), `osd_tc_*` text layer, `ui_port_state/timing`, `set_ap_*` appliers (backlight, volume, input_mode, search, dp, power_mode, osd…), `AwtoSetLoop` | text layer lives here but is used by the console (dbgpop); `set_ap_power` placeholder (inert power rows) | R#162: split text layer out; appliers keep |
| fw/nvram/nv_gate.c | 474 | #151 SDK-store hook, flush gate, aux block, commit/card | `AwtoNvDefer/Flush/Commit`; flags from DDC/CI/switch | keep; NVRAM owner per Dan 11-12 |
| fw/keys/keyinject.c | 34 | key hook for menu | duplicates routing in keys | merge into keys |
| settings/rules.py | 70 | inserts+subs (audio, NV, ACTIVE no-save) | | keep |
| wdt/rules.py | 86 | WDT/Timer0/NV poke subs | | keep |
| gamma/arith/dataport/reg rules.py | 12/5/5/2 | clean-room module hooks | | keep (#65) |
| awto_shim/sdk_boundary.c | 112 | clean↔SDK glue (muldiv, gamma, reg) | | keep |
| inputs.tsv, portsig.tsv, sync.tsv, clean_ref.txt | - | generator tables | sync.tsv = log texts (logging rule) | keep |
| keil2sdcc_drops.py | 56 | size switches | all defaults ON (nothing dropped) | review: remove dead switches |
| fw/sdcc crt_*.asm, bank.asm, keil_compat.h, intrins.h | - | startup, banking, compat | `crt_rtd_startup.asm` sets WDT N | keep |

### 7.3 awto-rtdfw-ui (`/mnt/2tb/git/awto-rtdfw-ui/awto`, branch `ui`, e7c597f)
| module | lines | purpose | verdict |
|---|---|---|---|
| settings/settings.c | 349 | registry values, clamp, risky auto-revert, recovery, aux pack/unpack; SDK rows via `set_sdk_*` | keep; registry = RAM view of SDK fields |
| settings/set_table.c + set_gen.h | 479 + 205 | generated page/row tables (101-104 rows; 48 nv rows inert) | keep; prune inert rows (#81) |
| settings/menu.c | 659 | menu engine, key dispatch (`mn_key`) | keep; routes under new key/OSD model |
| settings/vcp.c | 172 | DDC/CI VCP get/set + host mailbox | keep |
| nvram/nvram.c | 187 | old record log; **read once** (`set_load_legacy`), never written | delete after migration window |
| osd/ui.c | 305 | components, key roles per context | keep; merge key-role table with keys |
| osd/font.c + font_data.inc + hex | 58 + 571 + 7×98 | fixed-cell fonts | keep |
| reg/ (reg.c, burst.c), dataport/, arith/ | 54+87, 65, 69 | clean-room SDK replacements | keep |
| include/*.h | ~15 files | interfaces | keep |

---
## 8. Options per area (trade-offs, no decision)
**Panel / eDP / backlight**
- A. Change SDK `PanelPowerAction` into one owned state machine (states OFF / VDD / LINK / VIDEO / BL_ON; events request, no blocking inline; steps run from the main loop with timers). Deletes: `AwtoPanelVddEarly`, `AWTO_BOOT_PANEL_ON`, `AWTO_BL_OFF_OR_BLANK`, panel probes/stage inserts (replaced by transition logging inside the machine), L1/L2 direct pin/link code, `AwtoDiagPanelT3Wait` sub, subs in SysMode/UserCommonInterface (6). Cost: biggest rewrite of the highest-risk code; T1-T6 and HPD timing must be re-proven on the panel (datasheet NDA, T values measured not specified). Gain: removes C1/C2 and the SDK-state/pin mismatch.
- B. Keep hooking, add a single "panel request" function that SDK calls and hold/fast path also use (thin wrapper, idempotent). Deletes: duplicate calls only. Cost: small; the SDK blocking sequence remains (1 pass blocks ~0.5 s); the INITIAL stall remains unless the call moves out of the OSD handler.
- C. Keep as is and fix by ordering (move boot panel call, drop the `_PANEL_ON` under FAST_MODE). Smallest; leaves three backlight-off mechanisms.

**Mode / power / source**
- A. Own SysPower+SysMode+SysJudge as one table-driven machine (events: power key, signal found/lost, timing confirmed, wake). The SDK keeps scalers (`ScalerGlobalResetProc`, etc.). Deletes: hold-judge condition sub, loopsplit cadence subs, `AwtoSwPoll` mode polling (transitions log themselves), `AwtoWakeRelease`'s direct resets, 14 PS poll sites (power saving gets one place). Cost: SysJudge/SysMode touch every scaler flow (DP MST/Type-C compile paths can be cut); regression risk on search/NOSIGNAL timers.
- B. Keep SDK machine, make our extensions go through its API only (`SysModeSetResetTarget`, `SET_TARGET_POWER_STATUS`) and move L1/L2/L3 into the SDK's NOSIGNAL/PS states (hold = a NOSIGNAL variant with the receiver kept). Deletes: direct pin/link calls in fastsw. Cost: L1 latency (SDK BL off 300 ms) unless the panel machine (above) removes it.
- C. Leave SDK as is; accept two wake paths but make one the sole decider (AwtoPsWakePoll) and disable SDK predetect completely. Deletes: 4 PS-predetect subs become `return FALSE`; keeps `SysSourceDetectPort` PS handling dead.

**Power-saving wake**
- A. One poll (ours), SDK predetects removed entirely; poll cadence from a hardware timer or inside the idle loop. Needs the PS-pass slowness explained first (C5).
- B. SDK predetect remains the single wake; our triggers (cable edge, EDID, AUX, TMDS clock) are put into the predetect functions. Fewer paths but modifies SDK per-PHY code (3 files) and loses the all-ports-every-pass property.

**OSD**
- A. Make the OSD engine ours: single owner object (console, cards, selector, menu, panels), SDK message/timer state machine removed; mode changes ask the owner to show/hide (no `OsdDispDisableOsd` on reset). Deletes: m4/m5/m6 redraw patches, `AwtoConLost`, `AwtoHoldBlocksDisable`, `AwtoMenuForget`, SDK hot-key menus, `OsdDispDisableOsd` sub, ~6 OSD subs. Cost: input-info/no-signal flows (timer events) re-implemented; factory menu / DDC/CI hot-key pop-ups need dropping (#122).
- B. Keep SDK event machine, give the console a priority flag SDK honours (`OsdDispDisableOsd` returns when console pinned). Smaller; keeps two timers/state machines.

**Input search / switch / KVM**
- A. One source model owning: scan type, ports enabled, cable status, cache, search, fast path, hold. `AwtoInputSelect` is its only entry (cable-less ports refused, as on wb-p14swap10). Deletes: fixed-port workarounds, the SDK reset path for switches, hot-key selector fragments, #84 guard becomes an invariant.
- B. Keep fast path as an optimisation layered on the SDK switch (cache-hit shortcuts only), and drop holds L1-L3 (replace by SDK NOSIGNAL → PS timers at tuned values). Deletes ~250 lines of hold code. Cost: loses 270-300 ms L1 wake (vs 1.4 s L3 path / ~2.5 s SDK).
- C. Leave; merge the #84 guard and decide prefill (#83) separately.

**NVRAM**
- A. Accept #151 (SDK store owner) and finish: route boot-time writes through the gate, remove legacy `nvram.c`, prune inert registry rows, document the 52 duplicates as views.
- B. Replace SDK store by registry-only record (the original plan, dropped 11-12): deletes the 95 SDK fields' write paths and the deferral hook; Dan decided against.

**Timers / time bases**
- A. One monotonic ms time source (32-bit, from Timer2 ISR) used by all pollers; SDK event table kept for its own events. Deletes `AwtoSwNow/AwtoFastNow/AwtoSrcNow/AwtoSyncNow` copies. Low risk.
- B. Leave.

**Logging (Dan's rule: never reduced, explicit texts)**
- Whatever model is chosen, each transition logs itself (state change function, text such as "backlight on requested (already on)"). One formatter for the console (#146). Probe inserts (≈45) and mode polling can be deleted ONLY because the transition function logs; the log content must stay at least the same.

---
## 9. Summary (15 lines)
1. Report content above; the file could not be written (no write tool): save it as `/mnt/2tb/git/awto-ddc/tmp/sdk_model_inventory.md`.
2. wb-p14ui lacks the #84 dead-port guard and the #83 pre-fill; they live on wb-p14swap/wb-p14pf, so KVM to an uncabled port is exposed again.
3. Panel bring-up has four entry points (raw early VDD, INITIAL `_BACKLIGHT_ON`, display-setting `_PANEL_ON`, ACTIVE `_BACKLIGHT_ON`) plus L1/L2 pin and link calls that bypass the SDK panel state.
4. The INITIAL panel call blocks the OSD handler (T1 10 + HPD ≤250 + link + T3) while `AwtoSwPoll` still shows POWER OFF; that matches #162's POWER OFF +492..+989 ms.
5. By code, `_PANEL_ON`/`_BACKLIGHT_ON` are no-ops when the status is ALREADY, so the +1609 retrain and +1758 backlight call in #162 are unexplained here; they need the boot profile (#162 step 2).
6. Console loss comes from SDK `OsdDispDisableOsd` on every mode reset; m4/m5/m6 are patches on top, not a model.
7. Power saving has two wake paths (SDK predetect + `AwtoPsWakePoll`); the PS pass is 15.6 ms on IOSC, so the poll needs 14 sites in the main loop.
8. Hidden resource drivers: `AwtoTmdsStuck` pulses HDMI HPD (blocking 110 ms); fastsw writes backlight pin/eDP link/WDT directly; testcmd reaches input, power, NV and keys.
9. At least six time bases and four log streams (switch, sync, diag stage, tokenised messages) with two console formats (#146).
10. NVRAM: SDK store is now the owner behind a flush gate; leftovers are boot-time immediate writes, selector-only input store, legacy `nvram.c` (read-once), inert registry rows (#81, 48 nv rows).
11. Hook count: ~150 keil2sdcc inserts, ~110 subs, 14 PS poll sites, 14 main-loop handler slots with marks, 6 overlay files plus the 1790-line RL6449_Project.h; roughly 45 of the inserts are log probes.
12. Module map (§7): 28 `.inc` modules, ~8300 lines; big ones are osdcard 1122, sync 882, dbgpop 631, net 610, ddcci 459, gpiopop 452, fastsw 417, keys 400.
13. Redesign candidates under #162: fastsw, sw (early VDD, HPD), sync (wake), osdcard, dbgpop (OSD ownership), loopsplit (judge cadence), `AwtoInputSelect`; keep: wdt, t0ev, gpio, keys, dbgisr, net, freq, dpframe, delaycal (move T3).
14. Likely dead or optional: icon_info, loopprof, meas4k (ON by default), `nvram.c` after migration, size switches in keil2sdcc_drops.py (all ON), `kvm_prefill`/inert registry rows.
15. §8 lists options per area (own the machine vs thin wrapper vs reorder) with what each deletes; no decision taken.

### Critical Files for Implementation
- /mnt/2tb/git/awto-ddc-ui/scripts/keil2sdcc.py
- /mnt/2tb/git/awto-ddc-ui/fw/overlay/Project/Header/RL6449_Project.h
- /mnt/2tb/git/awto-ddc-ui/fw/sdcc/awto_fastsw.inc
- /mnt/2tb/git/awto-ddc-ui/fw/log/sync.c
- /mnt/2tb/git/awto-ddc-ui/tmp/sdcc-port/src/Kernel/User Common Function/Code/UserCommonInterface.c


---
# Addendum: transitions + OSD / output timing (2026-11-12)

## 10.0 Corrections to my earlier report (panel state model)
- The panel status values are: 0 `_PANEL_POWER_OFF_STATE`, 1 `_WAITING_FOR_BACKLIGHT`, 2 `_READY_FOR_BACKLIGHT`, 3 `_BACKLIGHT_ON_ALREADY`, 4 `_PANEL_BACKLIGHT_OFF`, 5 `_WAITING_FOR_PANEL_OFF`. [code, Global.h:900-905]
- The T3 timer event (`_USER_TIMER_EVENT_PANEL_BACKLIGHT_ON`) sets status 2 READY. It does not switch the backlight on (RTD2014UserInterface.c:665). The backlight pin goes on in a later `_BACKLIGHT_ON` call. I had this wrong earlier.
- The T6 timer event (`_USER_TIMER_EVENT_PANEL_POWER_OFF`) sets status 0 OFF_STATE unconditionally (UserInterface.c:669).
  - If any `_PANEL_OFF` ran about T6 (1100 ms) before a moment when the panel is on, that timer drops the status to OFF_STATE even though VDD and link are up.
  - The next `_PANEL_ON` or `_BACKLIGHT_ON` then repeats the full VDD, T1, HPD poll, link training and T3.
  - I could not find a `_PANEL_OFF` call at cold boot, so this is only a candidate for the +1609 retrain in #162. Check it in the boot profile.
- **The SDK's own model with `_PANEL_POW_SEQ_FAST_MODE == _ON`** [code]:
  - `_PANEL_ON` at DISPLAY_SETTING brings up VDD and link and starts the T3 timer, overlapped with the scaler set-up.
  - `UserCommonInterfaceReadyForActive` (UserCommonInterface.c:1893) blocks DISPLAY_SETTING → ACTIVE until the status is READY or ALREADY.
  - The backlight pin goes on at ACTIVE (`_BACKLIGHT_ON`).
  - Our boot call (`_BACKLIGHT_ON` at INITIAL) therefore runs the SDK's ACTIVE step early and inline, and brings up VDD, link and backlight before display setting. That is the second driver.
- `UserInterfaceGetIntoPSStatus()` returns FALSE while the OSD is enabled (RTD2014UserInterface.c:1859). An open console, selector or card blocks the SDK from entering power saving. [code]
- `AwtoDiagPanelT3Wait` cuts T3 to `AWTO_T3_OWN_PATTERN_MS` (registry `PANEL_T3_OWN`, default 20 ms) when the pattern generator (P7_F0 bit7) or forced background (P0_28 bit5) is on. Otherwise T3 is the registry value (default 550 ms). [code, awto_delaycal.inc:118]
  - The boot console enables the background first, so the boot T3 is about 20 ms.
  - A wake does the same (`AwtoBootConsole` → background on).

## 10.1 The question: OSD vs output timing / DCLK / eDP-1 link

**Facts**
- The OSD is drawn by the display side from on-chip OSD SRAM, on the scaler's display clock. It uses neither the input clock nor the DDR. [docs/reversing/realtek-rtd/osd.md §"OSD vs the picture path": [guess], consistent with the no-signal screen] [issue #26 #36: faults on the input→display crossing do not affect the OSD or the panel link]
- So the OSD depends on: D-domain timing generator + DCLK (DPLL), the DPTx stream/link, and panel power. It does not depend on the input receiver or the I/M domain.
- The eDP link is not touched by any mode-flow step. [code]
  - Every caller of `ScalerDisplayDPTx*` (link sequence, PHY init, stream enable, SSC set, analog PHY) is in `UserCommonInterfacePanelPowerAction` or in our `AwtoL2LinkOff/On` (awto_fastsw.inc). I grepped the port: there are no other callers.
  - `ScalerPLLSetDPLLRefPLL` (the DPTx link CMU, RL6449_Series_PLL.c) returns at once when the DPTx PHY is already powered (P38_A0 bit4). It uses the fixed link rate (`_PANEL_DPTX_LINK_RATE` HBR2), never the pixel clock.
  - `ScalerPLLSetDPLLReset`, which can power down the DPTx PLL, is called only from RL6449_Series_Power.c:709 (power-up). So a DCLK change does not touch the link.
  - Conclusion [code]: by the SDK's own design, a change of timing or DCLK needs **no eDP retrain**. The DPLL (pixel clock) relocks on its own.
- The DPLL change type [code, ScalerPLL.c, `ScalerPLLSetDPLLFreqNf*`]:
  - Under 10 %: `_DPLL_FREQ_CHG_UNDER_10PER`, VCO band and divider kept, only M/offset set. No unlock expected. This covers 60 / 59.94 Hz sources against the panel's 4000x2222x60 = 533.3 MHz.
  - Over 10 % (a 50 Hz source is -17 %, 24/30 Hz sources too): band, divider and N/F are reselected and the DPLL relocks. The output pixel clock is unstable for that moment. [inferred: glitch while relocking]
  - Whether the panel tolerates a changing DHtotal/DVtotal/MSA without a relink is unmeasured. The panel datasheet is NDA. [guess]

**Output-touching steps of an input change, in order** [code]

| step | function | output effect |
|---|---|---|
| 1 | `SysModeResetState(RESET_TO_SEARCH)` → `ScalerGlobalResetProc` (ScalerGlobal.c:199) | D-domain background ON (black), watchdog off, double buffer off, FRC off, `ScalerFRCSetDDomainSourceSelect(FRAME_SYNC)`, OD off. Timing generator keeps running. |
| 2 | `SysModeSetFreeRun()` (SysMode.c, from `SysModeResetState`) | `SysModeDisplayTimingInitial`, then `ScalerMDomainSetDisplayFormat(_FREE_RUN_NO_INPUT)`: DHtotal, DVtotal, free-run DVtotal and last line set, DCLK = panel typical, `ScalerPLLSetDPLLFreq`, `ScalerPLLSetDPLLSSC`. If DCLK changed → our sub blanks (SDK DPTX: nothing). |
| 3 | search / measure (`SysSourceHandler`, `ScalerMeasure*`) | input side only (receivers, I-domain). No output change. |
| 4 | DISPLAY_SETTING: `SysModeSetUpDisplayInitialization` (blank sub, `SysModeSetupIDomainIniValue`, FRC/DB disable), `SysModeSetUpInputCapture` (VGIP window), `SysModeSetUpDisplayCapture` (`SysModeDisplayTimingInitial`, `UserCommonInterfaceAdjustDisplayTiming`, `ScalerMDomainCheckDisplayFormat`) | I/D-domain set-up, mostly input side. |
| 5 | `SysModeSetUpMDomain` = `ScalerMDomainControl` (ScalerMDomain.c) | `ScalerMemoryFrameSyncSetDt`, **`ScalerMDomainSetDisplayFormat(_FRAME_SYNC_LINE_BUFFER)`** (DHtotal/DVtotal/DCLK for frame sync → `ScalerPLLSetDPLLFreq`), **`ScalerDPLLFineTuneFrameSyncLineBuffer`** (iterates DCLK offset and DHtotal; waits for IVS events), `ScalerMDomainControlDBApply`, **`ScalerPLLSetDPLLSSC`**, `ScalerTimerWaitForEvent(_EVENT_IVS)` x2 (bounded by the WDT; hangs while the input has no vsync), `ScalerMemoryReset`, double-buffer trigger. |
| 6 | `UserCommonInterfaceAdjustColorProc` | colour pipe; output side but not timing. |
| 7 | ACTIVE first pass: `ScalerGlobalFirstActiveProc`, `UserCommonInterfaceOsdActiveProc` → `UserInterfaceAdjustOsdActiveProc` | background OFF (unblank). OSD event for the info card. |

**Answer**
- The SDK already has a fixed-timing state with no input: `_FREE_RUN_NO_INPUT` (step 2). No-signal and power-saving cards are drawn on it with the background on. Search and measure (step 3) do not touch the output.
- The output timing is changed in two places only: step 2 (a no-op if the unit was already free-running at typical) and **step 5, the frame-sync format + DPLL fine-tune + SSC + DB apply**.
  - With the frame-sync line buffer (what 4K60 / 1080p60 use here) the output frame rate must follow the input, so the DPLL and DHtotal necessarily change at step 5. A "touch the output only at the final frame-sync step" design matches what the SDK does, provided the earlier steps (reset, blank) do not stop the output.
  - With frame-buffer FRC the output could stay at the panel's fixed timing, but FRC is off here: #26/#36 report bad data at 4K30 and 1080p50 with FRC. [issue; I did not check `_FRC_SUPPORT` in the build]
- The retrain question: **no retrain is required** at step 5. The link functions are not in that path.
- What actually kills the OSD in today's flow is software, not hardware [code, docs/osd.md]:
  - `UserInterfaceAdjustOsdResetProc` → `OsdDispDisableOsd` runs on every `SysModeResetState`, and again on the SDK events `_OSDEVENT_SHOW_POWER_SAVING_EVENT_MSG` and `_OSDEVENT_GO_TO_POWER_SAVING_EVENT_MSG`.
  - The m4/m5/m6 console patches repair that.
  - Display setting also changes OSD-related D-domain registers (the "view registers" re-applied in m4). I did not trace which.
- Not traced: whether step 4 or 5 resets the OSD engine registers (position, enable, scroll). m4 says the console went blank after display setting although the background was on, so something there does.
- Honest limits: the panel's tolerance of timing changes without a relink is unmeasured. The +1609 retrain in #162 is therefore NOT explained by step 5. Candidates: the status-0 timer (§10.0), `_PANEL_ON` called with status 0 for another reason, or `AwtoSwEvent` probes misleading the log.

## 10.2 Transition blocks (in execution order)

Blocking waits are listed with their durations. "Log:" lists every line that reaches the sync ring or console (text from `sync.tsv`), in order. SDK-internal debug messages (`AwtoMsg*`) are not listed.

### T1. Mains power-up (cold boot)
1. `crt_rtd_startup.asm` (RAM init, WDT N set) → `main()`: `AwtoWdtInit` (SysMain.c). LOG: boot reason line (written later by `AwtoSyncBegin`).
2. `AwtoDiagInit` (stage 1), `AwtoMeasInit`, `AwtoSyncInit` → `AwtoSyncBegin(POWER_ON)`. LOG: `boot: cold power-up…` (or the watchdog/warm cause), `boot: main() entered` (D1 01), `power on` (C0 01).
3. `SysMainSystemInitial` (SysMain.c):
   - `ScalerMcuInitial`: M2PLL clock, flash clock, code banks, Timer2 tick, GPIO init, WDT counter cleared after `AWTO_SYNC_MARK`. LOG: D1 02 GPIO set up, D2 01 MCU init, D2 02 Timer2 tick running, D1 03 MCU set up, D2 03 watchdog run-time.
   - `ScalerPinshareInitial`. LOG: D1 04 pin functions set.
   - **`AwtoPanelVddEarly`**: PNL VDD ON by raw `PCB_PANEL_POWER`, no wait, SDK panel status stays 0. LOG: D1 05 `panel VDD switched on`, 70 `panel VDD on (early)`.
   - `ScalerTimerInitialTimerEvent`, `UserCommonInterfaceInitial` (→ `UserInterfaceInitial`: `PCB_PWM_SETTING`, `RTDNVRamStartup` [NV load and recovery, may write flash, CPU halted], `AwtoMsgLoad`, `AwtoSetInit` [registry load, legacy import]), `ScalerMcuDdcRamEnable`, `SysSourceInitial`.
   - `SysPowerInitial`: whole-chip reset, IOSC trim, LDO, EDID/HDCP load from flash, `ScalerDpInitial` per DP port, memory power off, isolation (blocking waits not individually traced).
   - Power status = AC_ON, target = NORMAL (NVRAM `_MONITOR_POWER_STATUS` ON) or OFF, mode POWER_OFF.
4. Main-loop pass 1: `AwtoSwPoll` (LOG: `mode POWER OFF` when it differs from the init value), `AwtoDiagMainPass` (LOG: D1 06 first main-loop pass), `SysPowerHandler` → `SysPowerSwitch(AC_ON_TO_NORMAL)`:
   - powerboard low-power off, LDO NORMAL, `ScalerSyncPowerProc`, `UserInterfacePowerSwitch` (LED on).
   - `UserCommonInterfaceOsdPowerOnInitial` (OSD engine init, font load: OSD).
   - `ScalerMemoryPowerControl(ON)`, `SysSourceInfoReset`.
   - `SysModeSetFreeRun`: DOM free-run, DCLK typical, DPLL started (PHY off → full start), SSC. RX: `ScalerSyncPowerProc` powers the receivers (not traced).
   - Waits: DDR/1.1 V rail waits (200 ms + 2x10 ms) skipped by the `_AWTO_FAST_BOOT` sub. Other waits not traced. No LOG line for this transition.
   - PWR = NORMAL.
5. `SysJudgeHandler`: POWER_OFF → INITIAL. LOG: `mode INITIAL` (01 00).
6. `RTDOsdSystemFlowProc` (mode INITIAL, change flag set):
   - `AwtoBootConsole`: D-domain background ON, console opened (OSD map written, enable, position). LOG: `console opened (sync log)` (CA).
   - `AWTO_BOOT_PANEL_ON` = `PanelPowerAction(_BACKLIGHT_ON)`, status 0 → full inline sequence: probe 24, stage 5, T1 10 ms, DPTx power seq, PHY init, T2 `ScalerDisplayDPTxPollingHotPlug` (returns on HPD; measured ~115 ms from VDD on, bound 250 ms), probe 26, `ScalerDisplayDPTxLinkSequence` (~33 ms), stage 7 / probe 27, stream enable, video pattern, T3 (about 20 ms with the background on), `PCB_BACKLIGHT_POWER` ON (stage 8), BL PWM after `_PANEL_POWER_ON_BL_TO_PWM`, status 3.
   - PNL, LNK, BL and OSD all come up here.
   - LOG: `panel on` / `backlight on` (10 xx via `AwtoSwEvent(POWER)`), `eDP-1: panel HPD high` (90 1A), `eDP-1: link trained` (90 1B) or `link training FAIL` (90 1C), D1 07 `eDP-1 panel link trained`, D1 08 `eDP-1 video stream to the panel running`.
   - This is the blocking call that holds the main pass for ~0.4-0.5 s while the log still shows POWER OFF (#162: +492..+989 ms).
7. `SysJudgeHandler` (next pass): INITIAL → SEARCH. LOG: `mode SEARCH` (01 01). LED: search.
8. SEARCH: continues as T6 (source change): `SysSourceHandler` search; `AwtoSyncDetect` lines; display setting (T7 steps), then ACTIVE. Cold boot ends at `mode ACTIVE` (01 03) at ~1.8-1.9 s on unit 2 [issue #162 m4: 1822 ms].

### T2. POWER key on (from POWER OFF)
1. `AwtoKeyPoll` (fw/keys/keys.c, SysMain.c): debounce → `AwtoKeyRoute(POWER, PRESS)`. Console is closed first if open (`AwtoKeyTestSet(0)`). `SysPowerGetPowerStatus() == OFF` → `SysPowerSetTargetPowerStatus(NORMAL)`.
2. Next pass: `AwtoSwPoll` → `AWTO_SYNC_POLL` → `AwtoSyncPoll`: NORMAL after OFF → `AwtoSyncBegin(POWER_KEY, port)`. LOG: `power key on, <port>` (C0 04).
3. `SysPowerHandler`: target NORMAL, status OFF → `SysPowerSwitch(OFF_TO_NORMAL)`: same work as T1 step 4 (powerboard, LDO, `ScalerSyncPowerProc`, LED on, `OsdPowerOnInitial`, memory on, `SysSourceInfoReset`, `SysModeSetFreeRun`), plus `UserCommonNVRamSetSystemData(_MONITOR_POWER_STATUS, ON)` and `UserCommonNVRamSaveSystemData()`. The save is deferred by the `AwtoNvDefer` hook (NV: dirty; written by the flush gate, not at the key press).
4. `SysJudgeHandler`: POWER_OFF → INITIAL (LOG: `mode INITIAL`). `RTDOsdSystemFlowProc`: `AwtoBootConsole` + `AWTO_BOOT_PANEL_ON` exactly as T1 step 6 (panel status was set to OFF_STATE by the power-off panel-off; if the T6 timer (1100 ms) from the power-off is still running, `_BACKLIGHT_ON` first blocks in `ScalerTimerWaitForActiveTimerEvent(PANEL_POWER_OFF)` for the remainder).
5. INITIAL → SEARCH → … → ACTIVE as in T1. Not traced: whether `RTDOsdSystemFlowProc POWER_OFF` clears `FORCE_POW_SAV`. It does (`SET_FORCE_POW_SAV_STATUS(_FALSE)` on POWER_OFF change).
- The console auto-open request is also set by `AwtoSyncBegin` (`ucOpenReq = 1`), so a second path (`AwtoSyncConPoll`) can open the console again at the settled mode.

### T3. POWER key off
1. `AwtoKeyRoute(POWER, PRESS)`: console closed first; status ≠ OFF → `SysPowerSetTargetPowerStatus(OFF)`.
2. `SysPowerHandler`: target OFF, status NORMAL, not fake-off → `SysPowerSwitch(NORMAL_TO_OFF)`:
   - `UserInterfacePowerSwitch`: LED off; **`PanelPowerAction(_PANEL_OFF)`**: PWM 0 + `_PANEL_POWER_OFF_PWM_TO_BL`, BL off, DPTx BL-off power seq, **T4 250 ms**, stream disable, idle pattern, **T5 20 ms**, SSC off, analog PHY off, VDD off, T6 timer 1100 ms armed, status 0 (LNK, BL, PNL off). LOG: `panel off` (10 01) via `AwtoSwEvent(POWER)`.
   - NV: `_MONITOR_POWER_STATUS` = OFF, `UserCommonNVRamSaveSystemData(); AwtoNvFlush()`: **the flush writes every dirty item now; flash ops halt the CPU for tens to hundreds of ms** (stall test 216 ms; chained erase+program can exceed 1 s without FFEA bit5). LOG: `NVRAM flush (power off / saving entry): wrote N B (...) in M programs, E erases, T ms` or `nothing changed, no flash write` (D4 13, after the flush), `NVRAM save start/end`, `flash erase start/done`, `NVRAM page move` (D4 01-05).
   - `SysSourcePowerOffProc`, `SysModeResetState(RESET_TO_POWER_OFF)` (`UserCommonInterfaceOsdResetProc` → blank sub; `SysSourceInfoReset`; `ScalerGlobalResetProc`), `ScalerMemoryPowerControl(OFF)`, `ScalerSyncPowerProc` x2, `ScalerLDOPowerControl(OFF)`, powerboard low-power.
   - OSD: lost with the display (`OsdDispDisableOsd` through the reset).
3. `SysJudgeHandler`: status OFF → mode POWER_OFF. `AwtoSyncPoll`: OFF → `AwtoSyncPush(POWER, 1)`. LOG: `power off` (C9 01), `mode POWER OFF` (01 07).

### T4. Power-saving entry (no-signal timeout)
SDK chain, with our changes marked:
1. Search finds nothing: `SysJudgeHandler` SEARCH → NOSIGNAL when `SOURCE_SWITCH_FINISH`. LOG: `mode NO SIGNAL` (01 05). (In the hold model the judge-failed-in-ACTIVE case goes to the L1/L2/L3 path instead; see T8.)
2. `RTDOsdSystemFlowProc` (NOSIGNAL change): `ScalerTimerActiveTimerEvent(SEC(2), …SHOW_NO_SIGNAL or SHOW_NO_CABLE)` depending on the cable of the NVRAM search port.
3. After 2 s: `_OSDEVENT_SHOW_NOSIGNAL_MSG` / `…NOCABLE…`: `OsdDispOsdMessage` (our card, fw/osd/console.c) + `PanelPowerAction(_BACKLIGHT_ON)` (backlight on if it was blanked/off) + timer SEC(3) `SHOW_POWER_SAVING`. In the selector case `AwtoSourceOpen` arms its own sleep rule instead of the 3 s timer (#139 sub).
4. After 3 s: `_OSDEVENT_SHOW_POWER_SAVING_EVENT_MSG`: `OsdDispDisableOsd()` (kills the console/selector), `OsdDispOsdMessage(POWER_SAVING)` card, `_BACKLIGHT_ON`, timer SEC(2) `GO_TO_POWER_SAVING`.
5. After 2 s: `_OSDEVENT_GO_TO_POWER_SAVING_EVENT_MSG`: `OsdDispDisableOsd()`, `SysPowerSetTargetPowerStatus(SAVING)`. (Alternative route: `SysModeHandler` in POWER_SAVING sets the target when `SOURCE_SWITCH_FINISH && UserInterfaceGetIntoPSStatus()`; that is FALSE while any OSD is enabled.)
6. `SysPowerHandler` (NORMAL → SAVING, `UserCommonInterfaceCheckFakeSaving` false) → `SysPowerSwitch(NORMAL_TO_PS)`:
   - `UserInterfacePowerSwitch`: LED breathe, **`PanelPowerAction(_PANEL_OFF)`** (T4 250 + T5 20 blocking; T6 timer armed), **`AwtoNvFlush()`** (flash stall as in T3). LOG: `panel off`, D4 13.
   - `SysModeResetState(RESET_TO_POWER_SAVING)` (OSD reset; `SET_SOURCE_TYPE(NONE)`, judge cleared), `ScalerMemoryPowerControl(OFF)`, `ScalerSyncPowerProc` (RX powered down to PS), `ScalerLDOPowerControl(SAVING)`, optional repeater power off, powerboard low-power.
7. Status SAVING: `SysJudgeHandler` → mode POWER_SAVING. `AwtoSyncPoll`: `AwtoSyncPush(POWER, 3)`, `AwtoPsWakeArm()` (detector baselines and latches, TMDS detectors restarted, cable baseline). LOG: `power saving` (C9 03), `mode POWER SAVING` (01 06).
8. PS main passes: `SysSourceHandler` → `SysSourceDetectPort` → PS predetect of the current search port only (TMDS: counts DDC, no freq wait, SDK sub; DP: AUX toggle counted). Plus `AwtoPsWakePoll` at 14 poll sites, due-checked every 5 ms. Unit 2: one pass is 15.6 ms on IOSC (#144 tmds3; the earlier ~2 s was a measurement error).
- The console and key panels do not redraw in PS (#144 tmds1). Waits in this transition: T4 250 + T5 20 + flash stall + whatever `ScalerSyncPowerProc` costs (not traced).

### T5. Wake from power saving
Common tail after any trigger (SDK PS_TO_NORMAL):
- `SysPowerHandler` target NORMAL, status SAVING → `SysPowerSwitch(PS_TO_NORMAL)`: powerboard on, LDO NORMAL, `ScalerSyncPowerProc` (RX and PHY back), `UserInterfacePowerSwitch` (no NV write), `OsdPowerOnInitial`, memory on, `SysSourceInfoReset`, `SysModeSetFreeRun` (DOM free-run, DCLK typical, DPLL restart, SSC).
- `AwtoSyncPoll` (see below), then SEARCH / display setting as in T6.
- Panel and console on the wake: only when the wake came from OUR poll (`g_ucAwtoPsWakeCon`): `AwtoSyncPoll` calls `AwtoBootConsole` + `AWTO_BOOT_PANEL_ON` (blocking `_BACKLIGHT_ON` from status 0, with a wait for the T6 timer remainder if the wake is within 1.1 s of the panel-off; T3 about 20 ms).
- For an SDK wake the panel comes up at the SDK's DISPLAY_SETTING `_PANEL_ON` / ACTIVE `_BACKLIGHT_ON` (or by a no-signal card event).

Triggers (each entry shows which code decides and what is logged):

| trigger | decider | functions in order | LOG |
|---|---|---|---|
| cable plug (any port) | ours | `AwtoPsWakePoll` (fw/log/sync.c:669; every 5 ms, 14 sites) → `AwtoPsWakeFire(T=cable)` → `SysPowerSetTargetPowerStatus(NORMAL)` (+ the console request) | `Dn cable plugged in: wake` (CB) |
| cable unplug | ours | same, cable edge down. SDK no longer wakes on search-port unplug (`AWTO_PS_CABLE_SDK` sub). | `Dn cable unplugged: wake` (D3) |
| EDID read (HDMI) | ours | `GET_TMDS_RXn_DDC_DETECTED` counted in the cut-down `ScalerTMDSRxnTMDSPSPreDetect`; EDID-IRQ latch (bit0) read by the poll | `Dn EDID read by source: wake` (CC); counted-only SCL toggle: `DDC activity in power saving: no wake` (DD) |
| DP AUX command | ours | AUX toggle counted by the cut-down `ScalerDpRx1PSPreDetect` (`AwtoPsAuxSeen`); the poll reads the AUX registers (B7DC-DD / BADC-DD) | `DP AUX activity…: no wake` (DA); an AUX command alone: DB, no wake (`_AWTO_PS_AUX_WAKE` OFF, #163) |
| DPCD 600h = D0 | ours | the poll reads the INT-backed latch | `DPCD 600h = D0 (source powers the link): wake` (CE) |
| TMDS clock (D2/D3) | ours | `AwtoPsTmdsLive` (freq-detect E6 started/done/stable EF) in the poll; TMDS detectors owned by the poll in PS | `Dn wake by TMDS clock, about x MHz (IOSC reference)` (DC); a short burst: `TMDS clock burst … no wake` (DE) |
| once per sleep | ours | per-trigger latch (`AwtoPsWakeFire` suppress) | `wake suppressed (<trigger>, once per sleep): Dn` (CF 01-06) |
| key press | ours | `AwtoKeyRoute` wake rule (fw/keys/keys.c): front key in SAVING sets the target NORMAL and consumes the press; UP also sets `SHOW_SOURCE` | `mode…`; keys log in `g_stAwtoKey` (not in sync.tsv) |
| SDK source detect | SDK | `SysSourceDetectPort` PS predetect true (current search port: TMDS clock detection or DDC detect, DP AUX toggle) → `SET_TARGET_POWER_STATUS(NORMAL)` | `wake on <port>` (C0 03) + `wake by the SDK source detect, not our poll (poll state …)` (D6) |
| SDK cable reset | SDK | `UserInterfaceGetCableResetStatus` (only when power is NORMAL, gated) | n/a in PS |
| host commands | ours | VCP 0xD6 `set_ap_power_mode`; `AwtoInputSelect` clears `FORCE_POW_SAV` | per T6 |

- `AwtoSyncPoll` on SAVING → NORMAL: counts `g_ucAwtoPsWakes`; if our poll fired: console + panel (above); else `AwtoSyncBegin(WAKE, port)` and the D6 line. LOG: `wake on <port>` (C0 03).
- Known facts [issue #144]: sim wakes 9-30 ms; unit 2 real host test: the poll ran 1-3 times in the whole PS period, so the SDK detect won both times (wd8 1474 ms, tmds1 1539 ms to ACTIVE). Two wake paths coexist.

### T6. Source change (KVM / selector / auto-search / cable / VCP 0x60)
Entry points: `AwtoInputSelect(port, why)` (fw/ddcci/ddcci.c:12) for VCP 0x60, menu input row, test cmds 0x31-0x33 and the selector; SDK auto-search by `SysSourceHandler`; SDK cable reset; front key (SOURCE/UP) → `AwtoSourceKeyOpen`.
A. `AwtoInputSelect`:
1. Returns for ports other than D1-D3, and for "switch to the current ACTIVE port" with why 0x60. **No cable check in this tree** (#84 guard absent).
2. `AwtoSwArm`, `AwtoSwEvent(CMD, why)`, `g_ucAwtoNvSwitch = 1` (NV flush gate: not stable), `AwtoSyncBegin(SWITCH, port)`, `SET_FORCE_POW_SAV_STATUS(FALSE)`, `SysSourceSetScanType(FIXED_PORT)`. LOG: `switch to <port>` (C0 02).
3. `AwtoSwFast(port)` refuses or takes (see T6a). If refused: `SysSourceSwitchInputPort(port)` (HPD toggle suppressed, idle receivers kept, `AwtoSyncBegin` again, probe) then `SysModeSetResetTarget(RESET_TO_SEARCH)`.
B. Full path (refused or SDK-initiated):
1. `SysJudgeHandler` → `SysJudgeModeResetProc` → `SysModeResetState(RESET_TO_SEARCH)`: `UserCommonInterfaceOsdResetProc` (blank sub; OSD reset → `OsdDispDisableOsd` closes console/selector/cards) → `SysSourceInfoReset`, clear flags, **`SysModeSetFreeRun`** (DOM free-run, DCLK typical), cancel judge timers → `ScalerGlobalResetProc` (background ON, WDT off, FRC/OD off, `ScalerSyncResetProc`). LOG: `reset to search` (90 01).
2. Mode: `SysJudgeStateChangeEvent` waits until `GET_MODE_RESET_TARGET == NO_RESET`; ACTIVE → SEARCH. LOG: `mode SEARCH`.
3. `SysSourceHandler`: `SysSourceSwitchPort`, `ScanPortInitial`, `SearchTimeInitial`, `SysSourceDetectPort` (TMDS predetect/scan ~180 ms; DP scan 0.3-0.5 s, DP two-frame waits measured), `SysSourceJudge`. LOG: `TMDS clock … detected` (C1), `DP link … detected` (C2), `scan done: <type>` (C3), `signal lost` (C4) on loss.
4. `SysModeHandler` SEARCH: `ScalerMeasureInputInfo` → timing confirmed. LOG: `timing WxH` (C5), `refresh` (C7), `pixel clock` (C8) via `AwtoSyncTiming`/`AwtoSyncFreq`.
5. `SysJudgeHandler` → DISPLAY_SETTING (`mode DISPLAY SETTING`, 01 02): `SysModeDisplaySetting` (§10.1 steps 4-6) with the FAST_MODE `_PANEL_ON` (no-op when the panel is up) and `AwtoSyncFreq`. LOG: `display setting` (90 0E).
6. `SysJudgeHandler` DISPLAY_SETTING → ACTIVE after `JUDGE_ACTIVE_STATE` timer (HDMI/DP 100 ms) and `ReadyForActive` (panel status READY/ALREADY). `SysModeHandler` ACTIVE first pass: `ScalerGlobalFirstActiveProc`, `UserCommonInterfaceOsdActiveProc` (NVRAM search-port set in RAM only, DDC/CI to the new port, info-card event, **unblank**), `_BACKLIGHT_ON`, `AwtoSwCacheStore`, `SysSourceFirstActiveProc`. LOG: `mode ACTIVE` (01 03), `UNBLANK` (switch log only).
- Timing: unit 2/3 full path about 1 s (HDMI/DP) [issue #60/#83]; KVM fast path 79-96 ms.
C. Fast path T6a (`AwtoSwFast`, awto_fastsw.inc:294): refusal codes as in §5 (LOG: `fast path refused: no cache` / `receiver unstable` / `timing field %`). If taken: `AwtoSwFastGo` (D-domain background ON, search index/type set, scaler snapshot applied, pending), then per pass `AwtoSwFastPoll` (3 frames, clear flags, 1 frame, measure/stable/judge checks) → `ScalerGlobalFirstActiveProc` + `UserCommonInterfaceOsdActiveProc` (unblank). No mode change (mode stays ACTIVE), no panel/link/DOM change, OSD untouched until the active proc. LOG: `fast path taken` (A0 00), or `fast path timeout: full path` (A0 05) → SEARCH reset.
D. Selector choice: `AwtoSourceKey` → `AwtoInputSelect`-like switch; the choice is stored (selector-only NV: `AwtoNvCommitSel`, card "Saving to memory", LOG D4 14 after the flush). KVM/auto-search/UP-DOWN steps are not stored.
E. Cable unplug on the displayed port: signal loss → T8. Cable plug on the idle port: `SysSourceCableDetection` updates `g_stPortCableStatus` every pass; auto search picks it up when the search runs; in a hold it is the `AwtoWakePoll` "another cabled port" rule after 5 s (`hold: auto search, other cable`).
F. Known failure [issue #84, not in this tree]: EXIT/next input or VCP 0x60 to an uncabled port → fixed-port SEARCH → NOSIGNAL (2 s) → power saving (9.8 s) and never back.

### T7. Timing change on the same input (resolution / refresh)
1. `SysJudgeHandler` ACTIVE: `SysJudgeCheckStatus()` (slow-path, every 10 ms) → `ScalerMeasureTimingChange` / interlace / FIFO / M-domain checks fail. LOG: judge-reason lines `judge: timing change` (90 15), `interlace change` (90 16), `source unstable` (90 14), `memory / timing gen` (90 17).
2. If hold conditions hold (`AwtoWakeHold`: cache valid for the port, timing match (!), not within 3 s of a fast wake): L1 hold (T8). Otherwise `SysJudgeModeResetProc` → reset to SEARCH (the full path in T6B, same input).
3. If the cached timing differs (it does for a resolution/refresh change): `AwtoFastScalerMatch` ≠ 0 → `AwtoWakeHold` returns FALSE → SDK reset. LOG: `reset to search`, then T6B steps 1-6. Re-measure → display setting → ACTIVE.
- DOM: steps 2 and 5 of §10.1 (new DCLK / DHtotal / DVtotal). >10 % refresh change → DPLL relock. LNK untouched. OSD lost by `OsdDispDisableOsd` on the reset.
- If the TMDS HPD recovery applies (D2/D3, 3 consecutive "source unstable" judges, at most 2 pulses per episode): `AwtoTmdsStuck` pulses the port's HPD low for 110 ms (blocking `ScalerTimerDelayXms` in the main loop). LOG: `HPD pulse (TMDS recover)` (B0).

### T8. Signal lost / back (ACTIVE)
Lost:
1. `SysJudgeCheckStatus()` fails (`source unstable`, etc.; same lines as T7).
2. With `_AWTO_WAKE_HOLD`: `AwtoWakeHold` → hold L1: D-domain background ON, `ScalerGlobalWatchDog(DISABLE)`, `PCB_BACKLIGHT_POWER_PIN(OFF)` (BL; SDK panel status stays 3), `g_ucAwtoHold = port`. LOG: `hold L1: backlight off` (A8 01). Mode stays ACTIVE; judge is held (`AWTO_FAST_JUDGE_HOLD`, `AWTO_WAKE_HOLD`). The OSD is not reset.
3. `AwtoWakePoll` every 10 ms: `AwtoRxRescan` = `StableDetect` or `NormalPreDetect` + scan. After `usL2Sec` 60 s: **L2** `AwtoL2LinkOff` (stream disable → idle pattern, SSC off, analog PHY off; VDD kept; LNK down; the OSD's link is therefore gone). LOG: `hold L2: eDP link off` (A8 02). After `usL3Sec` 600 s: `AwtoWakeRelease(3)` → `AwtoHoldBacklightSdk` (L2 link back on, pin on, SDK `_BACKLIGHT_OFF`, 300 ms) → target SAVING → T4 steps 6-8. LOG: `hold L3: SDK power saving` (A8 03).
4. Without hold (no cache, hold disabled, rehold guard): SDK path `SysJudgeModeResetProc` → reset to SEARCH → T6B, ending in NOSIGNAL → T4.
Back:
1. `AwtoRxRescan` true → L2: `AwtoL2LinkOn` first (PHY init, `ScalerDisplayDPTxLinkSequence`, stream enable; probes 25/27/28), backlight pin on; then `AwtoSwFastGo` with 1 settle frame, `AwtoSwFastPoll` checks, unblank. LOG: `hold: signal back` (A8 05), `hold: backlight on` (A8 06), `fast path taken` (A0 00). Failure: `hold: fast wake retry` (A8 07), after 4 tries `hold: fast wakes used up` (A8 04) → SDK reset → T6B. `hold: SDK reset` (A8 10) if the SDK reset first.
2. Panel/link state: after L1 only the pin changed. After L2 the link was down and trains again (ours), ~95 ms measured; the SDK panel state never saw it.

### T9. Menu / console / selector open-close (OSD ownership changes)
Opening:
- Console: `AwtoBootConsole` (T1/T2/T5, from the INITIAL mode hook and the wake), `AwtoDiagConsole(AWTO_CON_MAIN/GPIO)` (UP+DOWN via `AwtoKeyRoute`, test cmds 0x20/0x26/0x41/0x43, auto-open `AwtoSyncConPoll` at the settled mode, watchdog-bite auto-open `fw/diag/wdt.c`). Effects: D-domain background ON at boot open, OSD map written (`osd_tc_open`), position/viewport (`osd_tc_place`, `osd_tc_viewport`), enable (`osd_tc_show`). LOG: `console opened (sync log)` (CA).
- Awto menu: `AWTO_REALTEK_MENU_OPEN`/`menu_open` on AUTO (fw/settings/settings_glue.c / `AwtoKeyRoute`), then `AwtoSetLoop` per pass; SDK OSD state stays `_MENU_NONE`, so SDK timers can still close it (`OsdDispDisableOsd` is intercepted by `AwtoMenuForget`).
- Selector: `AwtoSourceKeyOpen`/`AwtoSourceOpen` (SOURCE key, UP, no-signal event). Sets `GET_OSD_STATE() == _MENU_HOTKEY_SOURCE`; sleep rule `AwtoSrcSleepArm`; per-port rows polled every `AWTO_SRC_POLL_MS`.
- Cards: `OsdDispOsdMessage` (our body) for no-signal/no-cable/no-support/power saving/input info (6 s `_AWTO_INFO_POPUP_SEC`), skipped at ACTIVE while the console is open.
Closing / losing:
- Closers: MENU key, POWER (closes first), UP+DOWN toggle, test cmd 0x44, menu_close, `AwtoMenuForget` (from `OsdDispDisableOsd`), selector close/choice (NV flush D4 14 plus "Saving to memory" card).
- Lost by the SDK: every `SysModeResetState` (OSD reset), `_OSDEVENT_SHOW_POWER_SAVING_EVENT_MSG` and `…GO_TO_POWER_SAVING…` (`OsdDispDisableOsd`), `_USER_TIMER_EVENT_OSD_DISABLE` (OSD timeout, 6 s info card), the SDK display setting (OSD registers re-applied; console blank, m4/m5/m6). `AwtoConLost` marks the console released; `AwtoSyncConPoll` can reopen it at the settled mode (the request stays).
- Gating: `AwtoHoldBlocksDisable` (only the #28 debug pop-up holds); `UserInterfaceGetIntoPSStatus` false while the OSD is enabled (blocks the SDK PS entry path in `SysModeHandler`).
- Logging: opening logs CA; key presses log to the key ring; mode/panel lines as above. There is no log line for "console lost" or "OSD disabled by SDK" today; this should be added under the logging rule.

## 10.3 Cross-transition observations (for the redesign)
- Panel: five entry points to a full bring-up (INITIAL boot call, wake `AwtoSyncPoll`, `_PANEL_ON` at display setting, `_BACKLIGHT_ON` at ACTIVE, `_BACKLIGHT_ON` in OSD events), plus raw VDD at boot and L1/L2 pin and link calls. All use inline blocking waits (T1 10, T2 ≤250, T3 20/550, T4 250, T5 20, T6 1100 remainder).
- Mode: logs are polled once per pass (`AwtoSwPoll`), so a blocking pass delays the line.
- OSD: lost by SDK software on resets and PS events; the output hardware does not stop it. A single "OSD owner" that SDK flows ask instead of calling `OsdDispDisableOsd` would remove the console patches.
- DOM: `SysModeSetFreeRun` is called on every `RESET_TO_SEARCH` (also at power-up and PS entry). A design that keeps the output in free-run until the frame-sync step 5 is already how the SDK works; what differs is that our flows blank/disable the OSD and re-bring-up the panel around it.

## Short summary of this addendum (10 lines)
1. File not written (no write tool); append §10 to `tmp/sdk_model_inventory.md`.
2. Nine transition blocks T1-T9 with ordered functions, resources, waits and the exact log texts from `sync.tsv`.
3. Corrected the panel state model: T3 timer sets status 2 READY (not backlight on); with FAST_MODE the SDK runs `_PANEL_ON` at display setting and `_BACKLIGHT_ON` at ACTIVE, and ACTIVE waits for READY/ALREADY.
4. Our INITIAL `_BACKLIGHT_ON` therefore runs the SDK's ACTIVE step early, inline and blocking (T1, T2, T5).
5. OSD question: the eDP link is not touched by any mode-flow step (only `PanelPowerAction` and our L2 call link code); DCLK/timing changes need no retrain by the SDK design; the link CMU ignores DCLK and `ScalerPLLSetDPLLRefPLL` returns early when the PHY is on.
6. Output timing/DCLK is touched at reset (`SysModeSetFreeRun`, free-run at panel typical) and at the frame-sync step (`ScalerMDomainControl`: format, DPLL fine-tune, SSC, DB apply). Over-10 % DCLK change (e.g. 50 Hz) relocks the DPLL.
7. So the panel can stay in free-run with the OSD up through search; the output changes only at the frame-sync step. The SDK already does this; what kills the OSD is `OsdDispDisableOsd` (software) on every reset and PS event.
8. Not explained: the +1609 retrain in #162. Candidates: T6 timer resetting the panel status to 0, or another `_PANEL_ON` with status 0. Needs the boot profile.
9. SDK `UserInterfaceGetIntoPSStatus` is false while the OSD is enabled (an open console blocks the SDK PS entry path).
10. Not traced (marked in the text): `ScalerSyncPowerProc` internals, `SysPowerInitial` waits, whether display setting resets OSD engine registers, FRC build setting.

### Critical Files for Implementation
- /mnt/2tb/git/awto-ddc-ui/tmp/sdcc-port/src/Kernel/User Common Function/Code/UserCommonInterface.c
- /mnt/2tb/git/awto-ddc-ui/tmp/sdcc-port/src/Kernel/System/Code/SysMode.c
- /mnt/2tb/git/awto-ddc-ui/tmp/sdcc-port/src/Kernel/Scaler/ScalerFunction/Code/ScalerMDomain.c
- /mnt/2tb/git/awto-ddc-ui/fw/sdcc/awto_fastsw.inc
- /mnt/2tb/git/awto-ddc-ui/fw/awto/sync.tsv
