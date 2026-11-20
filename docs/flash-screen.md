# Flash warning screen, alert tone, 1 MHz ISP (#232, #229)

Status 2026-11-18. Seen on unit 3 (Dan: "looked great").

## What `dev.py flash` shows and plays

- 1 s alert tone first, so the host never starts while the generator is on: `scripts/alert.py --wait`, DDC/CI VCP 0xEB = 6.
  - Rising beep, beep, long beep (880 / 1175 / 1568 Hz, 150 + 50 + 150 + 50 + 600 ms), monitor speaker at the monitor's own volume (VCP 0x62).
  - Same call for "an agent needs Dan": `./dev.py alert --unit 3`.
- Red full-panel screen with a static 36 x 36 px Pac-Man (3 x 2 tiles, mouth open, drawn once, never redrawn) and text rows, from the running firmware (VCP 0xEB = 5), then updated over ISP:
  - title: FLASHING - DO NOT POWER OFF
  - row 1: phase + bank (BANKED / BANK0 / COMMON / BOOT, `boot_last` order) + `SKIP n/N` (image sectors already matching, no need to flash / image sectors; erased = the `SEC n/N` of row 2; totals + on-device manifest: `docs/flash-registry.md`), row 2: address, sector n/N, %
  - row 3: interface (bus kind, ISP kHz, write mode), row 4: burst failures + ISP recoveries, row 5: elapsed + ETA
- OSD off before the exit reset, so the new firmware starts empty.
- Best effort: a screen / tone failure is logged (`tmp/logs/flash_screen.log`, `alert.log`) and never fails the flash. Firmware that does not know VCP 0xEB = 5 / 6 (max < value) is skipped; `AWTO_FLASH_SCREEN_OFF=1` disables the screen (use it when the running image has a different screen layout).

## How it works

- Firmware: `fw/test/flash_screen.c` draws the screen (window 0 red, 30 x 11 tiles scaled 64 / 6 = 10.67, 1-bit glyphs); `fw/test/saver.c` serves VCP 0xEB in the main loop; sound: `fw/test/snd.c` track `alert`.
- The OSD circuit keeps drawing while the MCU is held in ISP. The flasher (`scripts/rtd_flash_image.py`) calls `flash_screen.tick(isp, k, info)` per sector: it rewrites only changed char commands over the ISP F4 / F5 window (`rtd_osd.Osd`): text rows only, at most once per second (`THROTTLE_S`, monotonic deadline, all buses); a change of the burst-failure / recovery counts and the last sector draw at once.
- Layout source `scripts/gen_flash_screen.py` (-> `fw/test/flash_screen_data.inc`); host `scripts/flash_screen.py`; `tests/test_flash_screen.py` keeps them equal.
- Rotate 180: the firmware turns map and glyphs, the host writes the mirrored cell (`docs/osd/rotation.md`); the marker file `tmp/flash_screen.<bus>.shown` (per bus: flashes of several units run in parallel) carries the rotate flag from `show` to the flasher process.
- Picture of old vs new, upright and Rotate 180, in the sim: `python scripts/flash_screen_pic.py OLD.bin NEW.bin` (`tmp/flash_screen_pic.png`). Rotate 180: text and Pac-Man turned, mouth to the left, as the panel is mounted.
- Dry run of the screen without a flash: `python scripts/flash_screen.py test --bus 11`.

## Screen cost (2026-11-20, `dev.py flash --full`, 224 sectors, gated images, main 505a3fd)

- Old = origin/main (72 x 72 px Pac-Man, mouth every 2 sectors, text per sector, DP duty cap 10 %), new = static 36 x 36 px Pac-Man + text at most 1 x / s, off = new image with `AWTO_FLASH_SCREEN_OFF=1`.
- Seconds of `rtd_flash_image` total (`DONE:` line); in brackets the `screen` bucket of its time split. One run per variant, units flashed in parallel; repeats where listed.

| bus | old | new | off | new vs off | old vs off |
|---|---|---|---|---|---|
| HDMI, NVIDIA, 100 kHz (unit 1) | 125.0 (4.4) | 124.8 (4.6), 121.9 (4.3) | 117.2, 116.8 | +6.3 s mean (+5 %) | +7.9 s (+7 %) |
| DP AUX (unit 2) | 68.5 (1.9) | 69.7 (7.1) | 60.8, 60.6 | +9.0 s (+15 %) | +7.8 s (+13 %) |
| HDMI, Intel DDC, 1 MHz (unit 3, Rotate 180) | 27.6 (3.8) | 24.1 (0.4) | 23.7 | +0.4 s (+2 %) | +3.9 s (+16 %) |

- DP AUX: a second `new` run did not show the screen (firmware not yet answering VCP 0xEB after the previous flash), so it is not counted; its 60.1 s equals the off runs.
- The bucket under-reports on DP AUX: old was +7.8 s over off with 1.9 s in the bucket (OSD writes slow the ISP traffic around them as well).
- Rotate 180 (unit 3): disp_rotate stayed 180 after every flash.

## 1 MHz ISP

- `dev.py flash` loads `tools/gmbus_rate` (i915 GMBUS 1 MHz) around the ISP session, 100 kHz otherwise.
- A kernel update left the module built for the old kernel; the load failed and every flash ran at 100 kHz without saying so. `scripts/gmbus_rate.py` now rebuilds when the module is missing or its vermagic differs from `uname -r` (needs `/usr/src/kernels/<release>`).
- Measured 2026-11-18 on unit 3, full image 896 KiB, burst, 224 sectors: 109 s at 100 kHz, 26 s at 1 MHz, 0 burst failures, 0 ISP recoveries, final CRC OK (2 runs).

## Boot splash (Dan's idea: big Pac-Man at power-on)

Status 2026-11-18, sim only (no hardware run).

- Cold power-up only (Dan, 2026-11-18): `AwtoBootReason() == AWTO_BOOT_COLD`. Warm resets (host ISP 0xEE, watchdog bite, probe / hardware watchdog reset, any warm start) show nothing.
- Registry `boot_splash` (id 122, bool, group osd, default On, no VCP code; menu OSD page / DDC paged pair 0xE0 / 0xE1). Off = no splash.
- Drawing: the flash screen's (red window, 36 x 36 px Pac-Man mouth open, rotate 180 turned) with the title row "AWTO" (second row of `g_aucFsTitle`, `gen_flash_screen.py` `TITLE_SPLASH`). `AwtoFlashDraw(ucSplash, ucStep)` = one step; `AwtoFlashScreen(1 | 2)` runs all steps (flash / preview).
- Preview: DDC/CI VCP 0xEB = 7 ("Boot splash"); stays until VCP 0xEB = 0.
- Start: first main pass (`AwtoSaverPoll`, `fw/test/saver.c`) arms it (run SPLASH / why BOOT, sync line E9 79); all draw steps run in the first pass in mode INITIAL.
  - Earlier passes are mode POWER_OFF: the SDK's INITIAL OSD init wipes anything drawn there (white fill seen in the sim).
  - A hold (`AWTO_HOLD_POPUP`) is set after the draw so SDK OSD resets cannot wipe it; Stop / the console release it.
- Ends:
  - mode ACTIVE: `AwtoSaverStop` closes it (the console auto-open waits for the hold)
  - first front key (`AwtoSaverKey`); DDC/CI commands do not end it (the host talks at power-on)
  - console / test command taking the OSD (`OsdDispDisableOsd` past the hold -> `AwtoSaverTaken`): ends, nothing closed
  - hard maximum `AWTO_SPLASH_MAX_MS` 3 s from the arming pass: ~4x power-on -> ACTIVE in the sim (0.75 s), = console hold `AWTO_CON_HOLD_MS`; expiry closes the OSD
- Check: `scripts/splash_sim.py BIN MAP` (cold boot vs the same image at boot_splash = 0, key end, warm reset + watchdog bite show none, setting off, preview frames upright / Rotate 180 in `tmp/splash_sim/`).

### Cold boot timeline (sim, `splash_sim.py`, unit-3 image, 1080p60, 2026-11-18, fw ms)

- Main pass 1 at 162 (mode POWER_OFF); pass 2 at ~585 in mode INITIAL (pass 1 holds INITIAL: panel T1, HPD, link training, video 542).
- 585: splash drawn (OSD on), visible until the display-setting panel cycle blanks the OSD (~750).
- 780: ACTIVE; 816: console opens, splash released (823).
- Cost against the same image at boot_splash = 0: ACTIVE +45 ms (780 vs 735), console +51 ms (accepted by Dan: the draw is ~45 ms of main-loop work in pass 2).
- Black between the OSD blank (~750) and the console (~816).

## Open

- Self-flashing from firmware: #232 part 2.
- The screen shows 26 s at 1 MHz; hold the last state longer only if asked.
