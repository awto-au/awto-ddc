🤖 Power LED (P3.5 / P3.6): one owner, the system machine (wb-p14ui-led `0dbfe87`, tools-led `1a25605`, image wb-p14ui-led2)

**Root cause (our code)**
- `fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h:553-563` (wb-p14ui 294056f, from 11f56fc): the SDK LED macros mapped wrong:
  - `PCB_LED_IDLE()` (SDK `_LED_POWER_SEARCH`, RTD2014Osd.c:114) = `AWTO_LED_OFF`: LED dark in SEARCH, and NO SIGNAL / NO SUPPORT-search inherit it.
  - `PCB_LED_OFF()` = `AWTO_LED_BREATHE`: POWER OFF breathed.
  - `PCB_LED_AC_ON_INITIAL()` = `AWTO_LED_OFF`: dark at AC on.
- ACTIVE depended on one SDK OSD-flow call (`RTD2014Osd.c:130`, OSD mode-change flag + power NORMAL) after SEARCH had switched it off; the sim reaches it on every path it runs, so the dark ACTIVE Dan saw is a path the sims do not run (not identified).
- Sim of the pre-fix image (hdcpoff-2, `sysm_sim --report`): SEARCH / NO SIGNAL (0, 0), OFF breathing, ACTIVE (1, 0).
- Two writers (SDK power switch + SDK OSD flow), none tied to the system machine (#162 step 3).

**Fix**
- `SysJudge.c` `SysMachineLed` (table `tSysLed`): called by `SysMachineGo` on every transition; sets the pins only on a colour change; POWER DOWN shows its target at once (Dahua: LED before the panel-down). AC on: `PCB_LED_AC_ON_INITIAL()` -> `SysMachineLedBoot()` at GPIO init (Dahua 5:d311).
- Rule (Dan 2026-11-12 + re-dahua-1 §2a/2b: Dahua keys off power status): on colour (1, 0) in AC ON, INITIAL, SEARCH, DISPLAY SETTING, ACTIVE, FAST SWITCH, HOLD L1, NO SUPPORT, NO SIGNAL, WAKE SEARCH; standby colour breathing in POWER SAVING (incl. fake PS); (0, 0) in OFF.
- SDK `UserInterfaceKeyPadLedControl` and its 9 calls deleted; `PCB_LED_*` gone from the board header.
- Log: one line per change, `LED: on colour (ACTIVE)` (sync.tsv 1C, fmt `sname`).
- `g_ucAwtoLedPins` = P3 pin levels (MCU_FFE3, bus value) per main-loop pass: readable over the debug slave (FFE3 itself reads 0 there).

**Gate** (tools-led `led_check.py` in sysm_sim + panel_sim): P3 SFR write hook; colour after every transition line; pins + `g_ucAwtoLedMode` per phase; lint: one writer. Image wb-p14ui-led2: 25 gates PASS.

**Integrated + unit 2** (2026-11-12, image `tmp/fw/AWT26110002-wb-p14ui-int1-be.bin` = `wb-p14ui-int` b38e1e6: wb-p14ui 094c69a + portcfg + led; tools `tools-int` 2a17774; 26 gates PASS incl. sysm / panel LED checks)
- LED line ids: sync.tsv 1C 00..02 (no clash; E0 = selector, E1 = port lines).
- `led_unit.py wb-p14ui-int1 --host-off`: 5/5 PASS. Pins = (P3.5, P3.6) over 6 reads 0.25 s apart, `g_ucAwtoLedMode` as read:

| state | how | g_ucAwtoLedMode | P3.5 | P3.6 | expected on the bezel |
|---|---|---|---|---|---|
| ACTIVE (after cold boot) | `hass_power.py cycle` | on colour | 1 | 0 | on colour steady (P3.5 LED) |
| POWER SAVING | VCP D6 = 4, host outputs off | standby breathing | 0 | 0 / 1 (PWM) | standby colour breathing (P3.6 LED), ~8.2 s cycle |
| ACTIVE (wake) | VCP D6 = 1 | on colour | 1 | 0 | on colour steady |
| OFF | test cmd 0x3E | off | 0 | 0 | dark |
| ACTIVE (power on) | test cmd 0x3E | on colour | 1 | 0 | on colour steady |

- **ACTIVE pins read (1, 0)** in all three ACTIVE samples.
- Ring: `LED: on colour (AC ON)` at +121 ms of a cold boot; `LED: standby colour breathing (POWER DOWN)` at the D6 = 4 request; `LED: off (POWER DOWN)` at POWER off; `LED: on colour (INITIAL)` at power on; `LED: on colour (WAKE SEARCH)` on a wake.
- Without `--host-off` (first run) POWER SAVING failed: the host's live HDMI TMDS clock woke the unit 375 ms after it entered power saving (`D2 wake by TMDS clock`, #144 design), so the sample saw WAKE SEARCH (on colour). LED followed the state correctly; the tool now blanks the host for that sample (`host_dpms.py`, 15 s guard).
- Not yet checked by eye: the two physical colours. Dan: on colour steady while a picture / search / no signal is up, standby colour breathing in power saving, dark when POWER off.
