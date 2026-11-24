# Power levels, sleep requests, wake and EDID log (awto-ddc#78, #216)

Status 2026-11-16. Code: `fw/sdk/Kernel/System/Code/SysJudge.c` (system machine), `fw/input/fastsw.c` (hold), `fw/settings/settings_glue.c`, `fw/log/sync.c`.

## Settings (registry power group)

| row | name | firmware function |
|---|---|---|
| 75 | `pwr_l1_en` | signal lost in ACTIVE -> hold with backlight off (`g_stAwtoPower.ucL1`) |
| 76 | `pwr_l1_ms` | inert (L1 delay) |
| 77 | `pwr_l2_en` | hold ends after `pwr_l2_s` and goes to the SDK no-signal path (`ucL2`) |
| 78 | `pwr_l2_s` | seconds in the hold before L2 (`usL2Sec`); default 60 (`AWTO_L2_SEC`) |
| 79 | `pwr_l3_en` | **off = every power saving request is ignored, the monitor stays on** (`g_ucAwtoSleepOk`) |
| 80 | `pwr_l3_s` | inert (stored only): it timed the no-signal screensaver, removed with the games (`docs/games.md`); not the hold's L3 (`AWTO_L3_SEC`) |
| 81-83 | `wake_d1..d3` | inert |

- Registry source: `fw/rtdfw/settings/registry.tsv` -> generated `fw/rtdfw/awto/settings/set_table.c` (`scripts/settings_gen.py`).

## Sleep requests: one gate

- Every power saving request ends in `SysMachineRequest(_POWER_STATUS_SAVING, who)`. With `pwr_l3_en` = 0 the outcome is `AWTO_SYS_IGNORED` (sync.tsv `18 06`): target not set, state unchanged.
- Sources (who codes): DDC/CI VCP 0xD6 standby/suspend/off (`BY_VCP`; the force-saving flag is not set), OSD no-signal power-saving card (`BY_OSD_PS`; the card is not shown, the NO SIGNAL card stays), SDK wake that found no source (`BY_WAKE_EMPTY`).
- No other fallback: no timer. If L3 is off the monitor stays lit.
- Log line: `power saving by <who> (IGNORED:power saving is off in the settings (L3 deep sleep), the monitor stays on)`.
- Tested: VCP 0xD6 = 4 on unit 3 (2026-11-16). Not tested: host DPMS / no-signal timer, wake-empty.

## What power saving does (SDK `SysPowerSwitch(_POWER_ACTION_NORMAL_TO_PS)`, `SysPower.c` 300-360)

- Frame buffer memory power off (`ScalerMemoryPowerControl`), mode state reset, interface power saving, MCU PWM + pin-share to saving, system clock to crystal / IOSC (`_SYS_PS_CLOCK_SOURCE`), power isolation, `ScalerLDOPowerControl(SAVING)` (empty in this build).
- `ScalerPowerIsolation` (`RL6449_Series_Power.c`): groups A, B, ADI, D0-D3 isolated; ADI, D0-D3 and A power-cut. Wake (`PS_TO_NORMAL`): `ScalerPowerAllGroupPowerCutReset` then the cuts are released.
- `ScalerGlobalWholeChipReset` runs only at MCU boot (`SysPowerInitial`), never on a sleep wake. It clears OSD SRAM and registers on a warm boot (watchdog / host ISP reset).
- Open: whether OSD registers / SRAM of the isolated, not cut groups (B, C, E) survive a sleep (a 2026-11-15 page-00 dump compare was inconclusive; the dump tool skips the OSD ports).

## Log lines

- Wake triggers in power saving (sync.tsv `CB` cable, `CC` EDID read, `CD` AUX, `CE` DPCD 600h, `D3` unplug, `DC` TMDS clock) and their suppressed repeats (`CF`) are unchanged.
- `E7` (new): `<port> EDID read` - an EDID read by the source in any state but power saving. `AwtoEdidPoll` (per main-loop pass, `swlog.c`): logs on the 0 -> 1 edge of the DDCn_EDID_IRQ bit 0 flag and clears it (W1C).
- `E5` audio: text is "audio on / off"; a mute / unmute that changes nothing logs `E5 05 / 06` "already on / already off" (never dropped).
- Request outcomes `18`: 00 accepted, 01 already, 02 replaces, 03 refused, 04 kept, 05 dropped, 06 **ignored**.

## Reading the log on a unit

- Sync log: `dbg_link.py on <bus>`, then `sync_log.py <bus> --map M --serial S --tsv T [--delta] [--whole]`, then `dbg_link.py off <bus>`. Without the link on, `sync_log.py` prints "read over 0x35 failed" (`wait_log.py` turns the link on itself).
- Blocking waits: `wait_log.py <bus> --serial S --map M` (waits under 2 ms are only counted).

## Drop one host output (video loss on one unit)

- `scripts/host_output_drop.py <unit> [--hold-s 5]`: removes that unit's logical monitor with a temporary `gdctl set`, restores the exact layout read before. All outputs: `host_dpms.py` (blanks every screen).
- Result 2026-11-16, unit 3 (HDMI D2) 5 s drop: fast wake times out after 147 ms in FAST SWITCH, "fast wakes used up", full search, ACTIVE at 1159 ms. Host DPMS (all outputs) instead: fast wake, picture up at 67 ms. Details #78.

## DPMS fast wake gives up (#313, 2026-11-22, image b607180d, host DPMS off 15 s then on)

- Ring lines (`sync.tsv` 99): `fast wake hold start, tries N` (counter the last hold left; the counter is reset at every hold start, no carry-over) and `fast wake failed, reason+try 0xRRTT` per timed-out try (RR = A1 reason bits: 1 measure busy, 2 watchdog, 4 M-domain memory check; TT = try number).
- Unit 3 (HDMI D2), n = 10 before: 7 fell back to the full path, each with 4 timeouts of ~137 ms, all reason 4 (memory check); 3 took the fast path (picture ~50 ms). No retry after a first failure succeeded (0 of 21).
- Change: a memory check timeout counts 2 tries (`AWTO_HOLD_TRIES_MEM`) instead of 4; other reasons keep 4. n = 10 after: 10 fell back, 2 timeouts each (the fast path did not succeed in this batch: the first-try result varies between batches); saving per fallback 2 x 137 ms.
- Unit 1 (HDMI D2, NVIDIA), n = 10 (also the pre-change image, n = 3): the fast wake shows the picture at ~55 ms, 121 ms later `judge:memory / timing gen` sends the mode to SEARCH, ACTIVE at ~855 ms. Cause open.
