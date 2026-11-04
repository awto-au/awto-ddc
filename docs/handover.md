# Handover — 2026-11-04T14:20+11:00

State after the 2026-11-04 session (host rebooted mid-work, so no agents are running). The open work lives in issues. This file only points to it.

## Done
- **EDID**: all 3 units flashed with the awto IPS/sRGB EDID, verified, reprotected (SR 0x9C), factory backups kept (`docs/edid-fix.md`).
  - Units are i2c-20 / i2c-10 / i2c-16 with serials AWT26110001 / 0002 / 0003. The bus → serial map is in `docs/edid-fix.md`.
  - Bus numbers can change: re-resolve with `ddcutil detect` before any write.
- **Flasher**: `scripts/rtd_flash_sector.py`
  - Writes a 4 KB sector with backup, `--expect-current`, verify and reprotect.
  - `--read-id` is read-only and prints JEDEC + RDUID + ESN.
  - The MX25L8006E has no factory UID.
- **Per-unit EDID**: `scripts/make_edid.py --serial`, `scripts/build_edid_sector.py`.
- **SDK**: the Realtek RL64xx SDK in git_mirror covers our chip (RL6449 = RTD2795T). Use it as reference only (`docs/reversing/realtek-rtd/sdk-rl64xx-reference.md`).
- **Splash glyph format**: confirmed and decoded (`scripts/glyph_decode.py`). Dahua logo atlas = blob D `0x23B41` (`docs/boot-logo.md`).
- **Panel**: Samsung LTM270FL01, PLS, 60 Hz ceiling (`docs/monitors/panel-samsung-ltm270fl01.md`).

## Open work
| issue | what | next step |
|---|---|---|
| #5 | Persistent awto boot splash | Read OSD font-select SRAM back while the splash is up to get the char-map. Link the `0x1382F` header to blob D. |
| #2 | Tech-info OSD (volatile) | `rtd_tech_osd.py 20 draw` on hardware. It has never completed a draw. `tech-osd.md` is not written. |
| #6 `needs-dan` | Windows flasher | Dan picks NVIDIA, AMD, Intel or a CH341A dongle. |
| #3 | OEM / panel identity | Get the Samsung spec PDF (LCDPanels email, Panelook CAPTCHA). Decode the firmware panel-config table. |
| #4 | EDID mode list | Add 4K30 / 1440p60 / 1080p60 if wanted. Nothing above 60 Hz. |
| #1 | Firmware status umbrella | — |

## Gotchas
- Entering ISP (`0x6F=0x80`) halts the MCU. Exiting via `0xEE=0x02` reboots the monitor.
- i2c-20's kernel `/sys` EDID showed the old VA primaries until that unit re-enumerated. Flash content is correct.
- `docs/boot-logo.md` was pruned of superseded conclusions on 2026-11-04 (all-zero VLC map, bank6 `0x628C6` candidate).
  - `git log -p docs/boot-logo.md` has them if needed.
