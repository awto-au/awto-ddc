# Handover — 2026-11-05T14:40+11:00

Open work lives in GitHub issues (tracking #1, firmware #7). This file points to it and records state.

## Units (serial → bus, resolve with `ddcutil detect --brief` before any write; numbers change on reboot)
| Serial | Input | Bus now | Firmware |
|---|---|---|---|
| AWT26110001 | DP | i2c-15 | original (reference for register/GPIO reads) |
| AWT26110002 | DP | i2c-21 | original |
| AWT26110003 | HDMI | i2c-11 | ours; new image being flashed at handover (see "In flight") |

## Flashed at 2026-11-05T14:41+11:00
- **New image is on AWT26110003** (`scripts/rtd_flash_image.py 11 tmp/fw/AWT26110003/fw.bin --serial AWT26110003 --write`): 184/184 sectors verified, reprotected (SR 0x9c), WP# re-asserted, scaler reset. Log: `tmp/logs/rtd_flash_image.log`.
  - Backups of the previous flash (identical reads): `~/vendors/realtek/analysis/dumps/jxc-4k-flash-AWT26110003-20261105-142704.bin` and `...-143339.bin`. Revert = rerun with either as the image.
  - Not yet checked by eye: does the panel light (backlight, picture)? DDC/CI is off in this build; debug slave 0x35 is on.
  - If dark: vary one thing at a time (backlight PWM polarity, P7.2 vs rail, backlight delay T3) and reflash.
- Not pushed: all local commits.

## What changed this session
- **Panel identity (#3)**
  - Panel's own EDID read over eDP AUX (`scripts/rtd_panel_aux.py`): mfr `MST`, name `AGERA`, week 51/2018, 597 x 336 mm, DTD 533.25 MHz, 4000 x 2222. `Agera` is a template string (also in an unrelated MediaTek EDID); no maker is named. DPCD: rev 1.4, HBR2, 4 lanes, sink OUI zero. Doc: `docs/monitors/panel-edid.md`.
  - Best candidate: **BOE MV270QUM-N20** (colours R/B/W match to EDID resolution, 2017-18 spec history, same size/timing). Others ruled in/out in the doc. Not confirmed by label.
  - Service menu says Innolux M280DCA-E3B (28", 620.9 x 341.3 mm): does not match the panel's 597 x 336 mm.
  - Datasheets in `~/vendors/boe/` (N10, N20, N50) and `~/vendors/innolux/` (M280DCA-E3B). Innolux M270DCA-E5B datasheet (panelook) not fetched.
- **GPIO roles (#7)**, `docs/monitors/gpio-roles.md`, script `scripts/rtd_gpio_live.py` (live pin levels, monitor on vs DPMS standby) + 3 read-only code-reversing agents:
  - P7.2 panel power (rail) high-on; P8.5 backlight enable high-on; P8.4 power LED (LED1); P9.2 standby LED (probable); P9.1 = PWM4 backlight pin.
  - Unknown: P3.5/P3.6, P4.2, P8.6 (maybe WP#/CS), P7.3/P7.4; P8.1 (VCCK_OFF) never written by old firmware.
- **Firmware board header** (`fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h`): panel power and backlight enable now defined (SDK defaults were no-ops, the likely cause of the earlier blank unit); backlight PWM = PWM4, polarity untested (`_BACKLIGHT_PWM_INVERSE _OFF`); MHL/VCCK/DDR macros are no-ops. Panel header T3 = 550 ms (datasheets ask >= 500 ms backlight delay). Debug-message categories on via `fw/sdk/Kernel/Common/Debug.h`. FreeSync VSDB removed from the EDID generator.
- **Flasher**: second read now limited to the image region.
- **Removed / deferred on purpose**: FreeSync + MHL (#21), audio (#22).

## Open work (issues)
| issue | what | next step |
|---|---|---|
| #7 | Own firmware on RL6449 SDK | Verify the flash lights the panel; if dark, vary one thing at a time (PWM polarity, P7.2 vs rail, backlight delay) and reflash |
| #3 | OEM / panel identity | Rear label photo or Innolux E5B / BOE N20 power sequence; update `_PANEL_*` names once settled |
| #11 `needs-dan` | Toolchain: Keil PK51 (~A$284/month via MDK) vs SDCC | Dan decides; SDCC image is 12 banks, common 0x3f27/0x5000 |
| #6 `needs-dan` | Windows flasher: which GPU / I2C path | Dan picks NVIDIA / AMD / Intel / CH341A |
| #15, #16, #19, #20 | SDCC port bugs (word views, CONST banking, ISR helpers, port risks) | open |
| #2, #5 | Tech OSD, persistent boot splash | not started |
| #21, #22 | FreeSync/MHL re-add; audio hardware check | deferred |
| #9, #10, #13 | USB port, emulator tests, CLI for RTDCustomerTool | open |

## Gotchas
- Entering ISP (`0x6F=0x80`) halts the MCU; exiting via `0xEE=0x02` reboots the monitor. Every register/GPIO read script ends with that reboot.
- DRM connector and i2c bus numbers change after a reboot; identify units by the serial in the EDID.
- Pin-level reads in standby are unreliable for inputs (always-off domain reads 0); use output pins the firmware writes.
- Flash rules: dump twice and compare first; never write without a backup in `~/vendors/realtek/analysis/dumps/`; unit 3 is the test unit.
- Repo stays PRIVATE (Realtek SDK code, `re/regdb/`).

## SDK source (awto-ddc#162)
- `fw/sdk/` = the Realtek SDK files the RL6449 build compiles or includes (`fw/sdk_files.txt`), in SDCC form; it is our code. Edit it directly; our changes carry `// awto: <what> (#issue)`.
- Build: `msg_tokenise.py port` (DebugMessage ids, build tag) -> `fw_compile.py` (compile) -> link. No build step patches the SDK; gate `rules` enforces it.
- History: first commit = mechanical import of the mirror (`scripts/sdk_import.py`, run by hand to compare a new SDK drop), then the overlay merge, then the behaviour edits. What each removed rule did: `docs/keil2sdcc-rules.md`.
- Bank layout: the tracked `fw/bank_layout.tsv` only (`fw_build.py` refuses a layout under `tmp/`).
