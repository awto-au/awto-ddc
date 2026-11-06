# Realtek SDK debug facilities (#37, #46 step 0a)

State = working-base. Sources: `fw/overlay/Project/Header/RL6449_Project.h`, `fw/overlay/Kernel/Common/Debug.h`, `scripts/keil2sdcc.py` WRAPS, `fw/msg_enable.txt`.
Host side: main checkout `./dev.py` (diag, osd, dbg-read, dbg-write); debug slave 0x35 must stay at 100 kHz (#12).

## Facilities

| facility | switch | state | gives | host drive | risk |
|---|---|---|---|---|---|
| ScalerDebug slave 0x35 | `_AWTO_DEBUG_PORT` (forces `GET_OSD_DDCCI_STATUS()` off) | ON | reg/XDATA R/W, flash, EEPROM, IIC pass-through, halt, message channel | `rtd_dbg_read/write.py`, `dev.py dbg-read/dbg-write/dump/poke` | DDC/CI (0x37, ddcutil) is off while ON |
| DebugMessage | `_DEBUG_MESSAGE_<Cat>` in Debug.h + allowlist `fw/msg_enable.txt` (cat/file/id) | flags ON for System Scaler Digital Rx0-3 Measure Memory FrameSync FRC Osd QC Check*; allowlist passes 372 of 8507 sites (System, Check, 36 Measure) | tokenised state/error messages (`{0x01,id_hi,id_lo,0}` -> fw/msgids.tsv) | `rtd_diag.py --messages` (host enables with 0x5A; fw halts per message until host reads) | per category: chunk growth past slot -> chunks move -> more sectors flashed; WARN-GATE rows for dead branches |
| Debug timer cursors | `DEBUG_TIMER_SAMPLE_*` macros live when `_DEBUG_MESSAGE_SUPPORT` | macros ON, no call sites in SDK; getters (`ScalerDebugGetTimerCursor{US,MS}Difference`) unlinked | stopwatches around code we mark | `dbg-read g_pstTimerCursorUS` / `g_ucTimerCursorUsedUS` | needs our own call sites (belongs with #46 trace) |
| Factory mode menu | `_FACTORY_INCLUDE "RTDFactoryInclude.h"` | ON, linked (RTDFactoryMainMenu, MenuFactory in map); `_MODE_STATUS_FACTORY` has no entry action | service OSD (burn-in, white balance, ADC gain, panel timer); reachable as the OSD main-menu item next to Information/Picture | `osd_test.py --cmd menu\|left\|right` (key injection) | none to enable; verify only |
| QC self-test | `_FACTORY_RTD_QC_SUPPORT` (QC_Option.h) | OFF | colour/OD/FRC block tests | none | `QC_Option.h` forces ~25 picture features `_OFF` (OD, gamma, dither, ICM...); 4751 of the 8507 message sites are QC; no RL6449 branch in the QC_Option.h include chain. Not built. |
| `_AUTO_TEST_SUPPORT` | AT_Option.h | OFF | IIC slave 0x3E test channel, SysAutotestHandler | none | `ScalerMcuDdcciSwitchPort` sets slave 0x3E and returns early: takes the DDC channel from 0x35. Incompatible with the debug port. Not built. |
| `_DP_DEBUG_MSG` | RTD2014Project.h / User_Project_Option.h | OFF | DP info strings in input pop-up / power-saving screen | none (panel only) | adds fields to `g_stOsdInfo` (shifts the byte offsets `osd_test.py` writes without `--cmd`), 2 OSD strings, extra pop-up draws; collides with the awto debug pop-up |
| `_DEBUG_IIC_BY_USERINTERFACE` | Debug.h | OFF | `UserInterfaceDebugIIC` hook in 0x44/0x04 IIC pages; only reaches an LED driver (`_DEVICE_LED_DRIVER_TYPE`) | none | no LED driver on this board: nothing gained |

## Size (builds in worktree tmp/, sticky layout copy, vs working-base 4e8337e)
- Digital messages (108 sites): common unchanged (0x462f of 0x5000), +171 B total chunk bytes, 1 chunk moved (`_ScalerSyncHdcpDownLoadBKsv`, bank 3, 340 -> 424 B), 19 of 224 sectors differ.
- Scaler + Digital + Osd + FS: 173 sectors differ, ~12 layout rows moved (ScalerMemory, ScalerIDomain chunks outgrow their slots) + needs a warn_policy row (ScalerMemory.c:570). Not taken.
- Memory / CheckMDomain categories alone also trip WARN-GATE at ScalerMemory.c:570 (dead branch under constant config).
- Others (QC, auto-test, `_DP_DEBUG_MSG`, IIC-by-UI): not built; reasons above.

## Order (one per flash, unit 3 only)
1. DebugMessage `Digital` (done in step 1): smallest growth, inert until the host sends 0x5A, covers RX/DP/HDMI digital input path.
2. DebugMessage `Osd` (14) + `Memory` (8, needs the warn row): small; one flash each.
3. DebugMessage `Scaler` / `FS` / `FRC`: bigger, moves chunks; take one category at a time, accept the sector cost.
4. DebugMessage `Rx0-3` (512/492/207/203 sites): large; per port, only the port in use.
5. Timer cursors: only with our own call sites (#46 trace).
6. Factory menu: already in the image; check by key injection, no flash.
7. `_DP_DEBUG_MSG`: panel-only info, layout side effects; low value.
8. Not worth it: QC (disables the picture pipeline), `_AUTO_TEST_SUPPORT` (kills 0x35), `_DEBUG_IIC_BY_USERINTERFACE` (nothing to reach).
