# Limits (one table)

Format: rated by the chip | what we use | why the gap. A gap with no reason is a bug.

| item | rated | we use | why / evidence |
|---|---|---|---|
| OSD SRAM | 12288 words x 24 bit, M1 + M2 | up to the whole (Scope 2 uses 616 + glyphs; console map 136 x 58 + glyphs) | extent [hw] 2026-11-16 (#226); no hole at 4096 / 8192 on the explicit port |
| budget | `rows + 1 + cells + 9 U1 + 18 U2 + 36 U4 <= 12288` | same | arithmetic [spec] |
| 1-bit glyph ids | 9 bit = 512 (B0[5] = id bit 8) | Asteroids 330, text layer 95 | [hw] ids > 255 rendered by Asteroids |
| 2-bit glyph ids | 8 bit = 256 (B0[5] is a colour bit) | Scope 2: 67 static + 161 dynamic ids at 960 x 540 = exactly full | ids bind before SRAM [emu: `gen_scope2.py (removed, docs/games.md) --raster 960`] |
| char words per row | 255 (8 bit) | 160 tested clean, console 118 columns shown | [hw] unit 2, 2026-11-11 |
| rows | row command count 8 bit (`0x3A3E` row total) | console 58 map rows | [?] hardware row limit OT-27 |
| row height | 1..64 px (B1[5:0] in the sim) | font cell heights 5..18 | [sdk-hypothesis] |
| display fetch of the map | crosses word 8192 wrong | `cols x rows + rows + 1 < 8192` | [hw] unit 2, 2026-11-11; cause [?] OT-3 |
| explicit port address | 15 bit (`0x90[6:0]` + `0x91`); storage ends at 12287 | same | [hw] 2026-11-16 |
| `fs_base` | 12 bit (4095) | below 4096 + map | [spec] |
| `font_base` | 15 bit | glyphs after the map | [spec] |
| `row_base` | 8 bit | 0 | [spec] |
| roll-up base | 12 bit, wraps at 4095 | `osd_tc_scroll` stops before the wrap | [hw] unit 2, 2026-11-11: 46 steps at 160 columns corrupt after ~25 |
| char width | 5 bit (1-bit chars) | 12 .. 6 px | < 4 px [?] T-C |
| windows | 26 | <= 12 (QC demo uses more) | [spec] |
| window coordinates | 12 bit start / end | panel px | [spec] |
| palette | 64 x 24 bit | up to 12 + ramps | [spec] |
| 1-bit colours | 4 bit fg / bg (indices 0..15) | 0..15 | [spec] |
| alpha | 8-bit level (regdb text 1/8 .. 7/8 in 3 bit) | `osd_transparency` as 0..255, type 11 | [hw] unit 1, #176 |
| scale-up factor | 6 bit, n = 64 / scale | 8 (savers), 13 (Pac-Man) | [hw] |
| scale-up region | 12 bit start / size | start = OSD position | [hw] 2026-11-18 |
| position delay | 12 bit horizontal (4 px or 1 px step), 11 bit vertical | 0 with scale-up; centred for menus | non-zero with scale-up [?] OT-26 |
| double size | x2 whole OSD | console | [hw] |
| tile | 12 x 18 (24 x 36 mode: `0x3A43[6]`) | 12 x 18 | 24 x 36 layout unknown OT-8 |
| data port rate | ~0.46 us / B (burst, [sdk-hypothesis]) | direct stores 1.95 .. 2.75 us / B; `ScalerOsdDataPort` 4.12 us / B | [hw] T1 / T2: direct stores need no gap; burst not yet measured (T-H) |
| MCU clock | 175.5 MHz mode (`_MCU_SPEED_UP_SUPPORT`) [sdk-hypothesis] | 87.75 MHz | not tested on the unit: T-L (saver-fps-hw) |
| write during scan | no interlock | savers write while shown | disturbance question open: [timing.md](timing.md), T10 |
| read-back | circuit off, scale-up off, overlay off, 2 reads | host tools only | [hw] [timing.md](timing.md) |
