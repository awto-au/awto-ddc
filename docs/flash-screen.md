# Flash warning screen, alert tone, 1 MHz ISP (#232, #229)

Status 2026-11-18. Seen on unit 3 (Dan: "looked great").

## What `dev.py flash` shows and plays

- 1 s alert tone first, so the host never starts while the generator is on: `scripts/alert.py --wait`, DDC/CI VCP 0xEB = 6.
  - Rising beep, beep, long beep (880 / 1175 / 1568 Hz, 150 + 50 + 150 + 50 + 600 ms), monitor speaker at the monitor's own volume (VCP 0x62).
  - Same call for "an agent needs Dan": `./dev.py alert --unit 3`.
- Red full-panel screen with a 72 x 72 px Pac-Man (mouth open / shut) and text rows, from the running firmware (VCP 0xEB = 5), then updated over ISP:
  - title: FLASHING - DO NOT POWER OFF
  - row 1: phase + bank (BANKED / BANK0 / COMMON / BOOT, `boot_last` order), row 2: address, sector n/N, %
  - row 3: interface (bus kind, ISP kHz, write mode), row 4: burst failures + ISP recoveries, row 5: elapsed + ETA
- OSD off before the exit reset, so the new firmware starts empty.
- Best effort: a screen / tone failure is logged (`tmp/logs/flash_screen.log`, `alert.log`) and never fails the flash. Firmware that does not know VCP 0xEB = 5 / 6 (max < value) is skipped; `AWTO_FLASH_SCREEN_OFF=1` disables the screen (use it when the running image has a different screen layout).

## How it works

- Firmware: `fw/test/flash_screen.c` draws the screen (window 0 red, 30 x 11 tiles scaled 64 / 6 = 10.67, 1-bit glyphs); `fw/test/saver.c` serves VCP 0xEB in the main loop; sound: `fw/test/pacman_sound.c` track `alert`.
- The OSD circuit keeps drawing while the MCU is held in ISP. The flasher (`scripts/rtd_flash_image.py`) calls `flash_screen.tick(isp, k, info)` per sector: it rewrites only changed char commands over the ISP F4 / F5 window (`rtd_osd.Osd`), the mouth every 2 sectors.
- Layout source `scripts/gen_flash_screen.py` (-> `fw/test/flash_screen_data.inc`); host `scripts/flash_screen.py`; `tests/test_flash_screen.py` keeps them equal.
- Rotate 180: the firmware turns map and glyphs, the host writes the mirrored cell (`docs/osd-rotation.md`); the marker file `tmp/flash_screen.shown` carries the rotate flag from `show` to the flasher process.
- Dry run of the screen without a flash: `python scripts/flash_screen.py test --bus 11`.

## 1 MHz ISP

- `dev.py flash` loads `tools/gmbus_rate` (i915 GMBUS 1 MHz) around the ISP session, 100 kHz otherwise.
- A kernel update left the module built for the old kernel; the load failed and every flash ran at 100 kHz without saying so. `scripts/gmbus_rate.py` now rebuilds when the module is missing or its vermagic differs from `uname -r` (needs `/usr/src/kernels/<release>`).
- Measured 2026-11-18 on unit 3, full image 896 KiB, burst, 224 sectors: 109 s at 100 kHz, 26 s at 1 MHz, 0 burst failures, 0 ISP recoveries, final CRC OK (2 runs).

## Boot splash (Dan's idea: big Pac-Man at power-on)

Status 2026-11-18, sim only (no hardware run).

- Registry `boot_splash` (id 122, bool, group osd, default On, no VCP code; menu OSD page / DDC paged pair 0xE0 / 0xE1). Off = no splash.
- Drawing: the flash screen's (red window, 72 x 72 px Pac-Man mouth open, rotate 180 turned) with the title row "AWTO" (second row of `g_aucFsTitle`, `gen_flash_screen.py` `TITLE_SPLASH`); `AwtoFlashDraw(ucSplash, ucStep)` draws one step (set-up, 3 cell steps, 3 glyph steps, show); `AwtoFlashScreen(1 | 2)` runs all steps at once (flash / preview).
- Preview: DDC/CI VCP 0xEB = 7 ("Boot splash", screensaver_now option); stays until VCP 0xEB = 0.
- Start: first main-loop pass (`AwtoSaverPoll`, `fw/test/saver.c`), run SPLASH / why BOOT, then one draw step per main pass.
- Draw steps never run in mode SEARCH or DISPLAY SETTING (the picture's path).
- Ends (no redraw, nothing closed when someone else owns the OSD):
  - console / menu opened (their hold flag): OSD left to them
  - first front key (`AwtoSaverKey`); DDC/CI commands do not end it (the host talks at power-on)
  - mode ACTIVE: the picture takes over
  - hard maximum `AWTO_SPLASH_MAX_MS` 3 s from the start: 4x power-on -> ACTIVE in the sim (~0.75 s), equal to the console hold `AWTO_CON_HOLD_MS`; expiry closes the OSD
  - an SDK OSD reset (`OsdDispDisableOsd` -> `AwtoSaverTaken`) wipes the drawing: the splash starts drawing again from step 0 while the run lasts; a mode reset never leaves a half drawing shown
- Check: `scripts/splash_sim.py BIN MAP --base BIN0 MAP0` (boot times against an image without the splash, key end, setting off, upright / Rotate 180 frames in `tmp/splash_sim/`).

### Where it can show (measured in the sim, `boot_sim.py`, unit-3 image, 1080p60, 2026-11-18)

- Ring times: first main-loop pass 166 ms; next pass ~584 ms (the first pass holds INITIAL: panel T1, HPD, link training, video 542 ms); SEARCH 587; DISPLAY SETTING 602; the SDK resets the OSD ~650 ms; ACTIVE 747; console 777.
- Pass 1 is the only draw point before the picture's path; the draw does not finish there, so a boot with a signal shows no splash.
- Draw all steps in pass 1: ACTIVE +54 ms (801 vs 747), rejected. Draw 22 small steps in DISPLAY SETTING passes: ACTIVE +7 ms, lost to the OSD reset at ~650 ms, rejected.
- As shipped: ACTIVE 747 ms, console 777 ms, first OSD 786 ms with / 785 ms without the splash (+1 ms, one pass of the saver poll).
- A splash visible at power-on needs the panel path to give passes (or the draw to move into the first pass at a cost of ~54 ms to ACTIVE).

## Open

- Self-flashing from firmware: #232 part 2.
- The screen shows 26 s at 1 MHz; hold the last state longer only if asked.
