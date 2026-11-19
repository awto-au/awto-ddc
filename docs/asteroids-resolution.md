# Asteroids canvas resolution: how far could it go

Question (Dan, 2026-11-19): can Asteroids run at a higher resolution than 360 x 198 (30 x 11 tiles of 12 x 18, x10.67)?
Tags: `[hw]` measured on a unit, `[spec]` regdb, `[sim]` fw_sim 2026-11-19 (base 521678a + the `#ifndef` knobs below), `[calc]` arithmetic from cited numbers, `[?]` unknown.
Nothing flashed. Default build unchanged: 12 frame md5s identical to the unmodified image (`saver_frames_md5.py --compare`).

## Answer
- Yes. Hardware allows far more; our firmware (XDATA at the 700 B floor) is the limit, not speed.
- Hardware ceiling: one tile map of <= 8191 words and <= 255 cells per row [hw: 160 x 48 clean] = about 1920 x 900 canvas px.
- Glyph ids are the practical wall for today's design (id = cell): 512 1-bit ids = <= 512 cells. Today 330.
  - Identity map (no new code): 35 x 13 = 420 x 234 (455 ids, factor 7, 1.17x finer). 40 x 15 = 600 ids does not fit.
  - 2x finer at the same screen size (720 x 396 = 60 x 22 = 1320 cells) needs shared ids (slot ring) or 24 x 36 mode.
- Time is not the limit: 2x finer costs +1.3 ms per frame of 40 (sim); 25 frames/s held in every variant.
- Needs Dan: XDATA (+210 B at 720 x 396) and whether to pursue 24 x 36 mode (hardware test OT-8). Default untouched.

## 1. OSD hardware limits
| item | limit | source |
|---|---|---|
| OSD SRAM | 12288 words x 24 bit, ONE pool: row commands + char words (map) + glyphs; no separate map / glyph SRAM | `docs/osd/limits.md` [hw] 2026-11-16 |
| Scope 2's 5224 words | a user of the same pool (Scope 2 uses 616 map + glyphs), not a reserved region; Asteroids reuses the pool (3312 words today = 27 %) | `docs/osd/limits.md` |
| budget | `rows + 1 + cells + 9 U1 + 18 U2 + 36 U4 <= 12288` | `docs/osd/tiles-fonts.md` |
| map fetch | `cells + rows + 1 < 8192`; glyphs may sit above 8192 (console glyphs cross it) | [hw] unit 2, 2026-11-11; cause OT-3 |
| row | <= 255 char words [spec], 160 clean [hw]; row height 1..64 px; row commands 8 bit | limits.md |
| 1-bit ids | 9 bit = 512 (B0[5] = id bit 8) | [hw] Asteroids 330 |
| 2-bit ids | 8 bit = 256; 18 words per glyph (4-bit: 36 words) | [hw] Scope 2 |
| cell | 12 x 18 (9 words 1-bit). Narrower char width shows a slice, not more pixels. 24 x 36 mode `0x3A43[6]`: 36 words per 1-bit glyph, layout unknown | OT-8 |
| windows | 26 rectangles, no bitmap, share one scale / alpha: they cannot enlarge a canvas | `docs/osd/windows.md` |
| scale-up | one region, one H and one V factor (6 bit each, ratio 64 / n, fractional steps allowed), no per-window scale; region 12 bit | `docs/osd/scale-up.md` [hw] factors 6, 7, 8, 13 |
| scale-up filter | not known whether edges are filtered (sim = nearest) | OT-22 [?] |
| write port | direct stores + 24 nops ~0.67 us/B today; `FFF1` sel 12 ~0.41 us/B; address set 4.5 us | `docs/scope-corruption.md`, `docs/osd-write-sweep.md` |

- Canvas px for a map = cols x 12 by rows x 18. Panel fit needs factor = 64 x W / 3840 integer: W a multiple of 60 (360, 420, 480, 540, 600, 720, 960).
- With id = cell (today): cells <= 512, and `9 x cells + cells + rows + 1 <= 12288` (<= ~1220 cells even if ids allowed).
- 24 x 36 mode with id = cell: 330 cells x 36 words = 11880 + 342 = 12222 <= 12288 [calc] = 720 x 396 with today's 330 ids, 99.5 % of the SRAM. Layout unproven.

## 2. Memory on our side (XDATA free 700 B floor, info overlay on)
- XDATA free, sim builds without the floor, info overlay off [sim]: today 715 B; 40 x 15: 625 (-90); 60 x 22: 505 (-210); 80 x 30: 345 (-370); 2x objects add nothing more.
  - What scales: `s_aucDirty` = cols x bands bytes (60 -> 120 / 240 / 400) and the object y (`AstSeen.ucY`) widens BYTE -> WORD past 360 x 198 (+26 B).
  - Does not scale: band canvas `g_aucScPix` (1 column x 6 rows = 162 B, shared with Scope 1), object pool, state.
- Info overlay (15 B) is written for 2 bands: variants build with `AWTO_SAVER_INFO=_OFF` (`#error` otherwise).
- Code: `AstMark` 341 -> 595 B, `AstPass` 738 -> 839 B (word maths, generic bands) = +0.35 KB in bank 8 [sim]; bank 8 headroom not checked.
- Slot ring (shared ids) would add a slot per cell: 1 B per cell (ids <= 255 + blank) = 600 / 1320 / 2400 B. Not affordable at the floor; the saver-statics overlay frees ~270 B (`docs/saver-library.md`).
- IRAM: nothing scales (6 B direct free).

## 3. Time per frame (sim, 350.8 MHz, 12 s fw window, game state differs per run: +-30 % noise on port bytes)
| variant | canvas | scale | frames/s | saver slot ms (of 40) | instr / frame | OSD bytes / frame (tiles) | ink tiles (one frame) |
|---|---|---|---|---|---|---|---|
| c30x11 (today) | 360 x 198 | 10.67 | 25.00 | 6.0 | 582k | 616 (22.8) | 54 of 330 |
| c40x15 | 480 x 270 | 8 | 25.00 | 6.4 | 597k | 635 (23.5) | 54 of 600 |
| c60x22 | 720 x 396 | 5.33 | 25.00 | 4.9 | 567k | 455 (16.9) | 54 of 1320 |
| c80x30 | 960 x 540 | 4 | 25.00 | 5.1 | 576k | 459 (17.0) | 53 of 2400 |
| r2x40x15 (objects 2x px) | 480 x 270 | 8 | 24.92 | 9.8 | 684k | 1610 (59.6) | 84 of 600 |
| r2x60x22 (objects 2x px) | 720 x 396 | 5.33 | 25.00 | 7.3 | 629k | 1292 (47.9) | 99 of 1320 |
- `cNxM` = same object size in px, bigger playfield (objects shrink on screen). `r2x` = objects, shape shifts and radii x2: same on-screen size, 2x finer (game speeds not rescaled: sim cost only).
- Larger playfield alone costs nothing per frame: ink tiles are the same; clean passes cost a byte test each (80 cols x 5 bands = 400).
- 2x finer: ink px x1.9, ink tiles x1.8, tiles uploaded per frame x2.1..2.8, saver slot +1.3 ms (60 x 22) .. +3.4 ms (40 x 15, objects span more of the canvas).
- Per extra redrawn tile: +77 us all-in (sim: +2.4 ms for +31 tiles/frame), of which the port is 27 B x 0.67 + 4.5 = 22.6 us (15.6 us at `FFF1` 12) [calc].
- Port per frame at 0.67 us/B: today 0.5 ms; r2x60x22 1.1 ms (0.75 ms at 0.41) [calc]. Not a bound (`docs/osd/path-cost.md`: port <= 2.7 % of a frame).
- Knee [calc]: a frame is saver work S plus one idle main pass (2.9 ms, `docs/saver-mode.md`) per 8 ms slice (`AWTO_AST_PASS_MS`): S + (S / 8 + 1) x 2.9 = 40 -> S ~ 27 ms. Today 6.0; 2x finer 7.3..9.8; 4x finer extrapolated ~15 ms (not built: shape shifts can't go negative).
- Line rasterisation: Bresenham walks every px (`AstLine`), cost per px constant, px per object x2 at 2x finer; cost grows linearly in line length, tiles x2.

## 4. What looks better
- Picture: `docs/asteroids-resolution.png` (sim, panel crop 720 px of 3840 x 2160, nearest-neighbour scale-up). Left today x10.67; middle 720 x 396 same px objects (half size on screen); right 720 x 396 objects 2x (same screen size, 2x finer line).
- Finer pixels (right) keep the rock the same size with 1-px steps of 5.3 panel px instead of 10.7: edges read as straight lines; the facets of the rock outline are resolved.
- More area at the same pixel size (middle) = smaller objects and more room; for a screensaver on a 4K panel the objects get small. Not recommended unless the game is rescaled too.
- Scale-up filtering on hardware unknown (OT-22); if it filters, x10.67 looks softer than the sim shows and the gain from finer pixels is smaller.

## 5. Options (ranked; any cost in speed or XDATA is Dan's decision)
| # | option | gain | cost | needs |
|---|---|---|---|---|
| 0 | keep 360 x 198 | - | - | - |
| 1 | identity map 35 x 13 = 420 x 234, factor 7 (as Scope 1) | 1.17x finer, 455 of 512 ids | XDATA about -70 B [calc]: 3 bands -> `s_aucDirty` 105 (+45), word y (+26); constants unchanged | Dan: floor |
| 2 | 24 x 36 mode, 30 x 11 cells = 720 x 396, factor 12, 2x objects | 2x finer, same 330 ids and map | SRAM 99.5 %; canvas 3 rows x 108 B; XDATA > +210 B; layout OT-8 unproven | hardware test OT-8 first |
| 3 | slot ring, 60 x 22 = 720 x 396, 2x objects | 2x finer, 99 ink tiles of 512 ids | XDATA +210 B (dirty, width) + 1320 B slots [calc]; +1.3 ms/frame, port bytes x2.1 | XDATA overlay (~270 B) not enough |
| 4 | slot ring, 40 x 15 = 480 x 270, factor 8 (Scope 2's hardware-proven factor) | 1.33x finer | XDATA +90 B + 600 B slots [calc] | as 3 |
| - | 80 x 30 and larger | not worth it: objects shrink, same ink | XDATA +370 B | - |
- Needed for 2-4 in code beyond the knobs: rescale gameplay constants x2 (speeds, ranges, `AWTO_AST_EDGE_PX`), HUD / info glyph shifts (negative shifts), 16-bit tile maths in `AstMark` (done under `AWTO_AST_WIDE`).
- Recommendation: option 2 is the only one with no XDATA growth for ids; settle OT-8 (one ISP test: 24 x 36 glyph, photo) before spending XDATA.

## Tools
- `scripts/asteroids_res.py build|cost|render|compare` (log `tmp/logs/asteroids_res.log`, TSV `tmp/logs/asteroids_res.tsv`).
- Firmware knobs (default values unchanged): `-D AWTO_AST_COLS=`, `-D AWTO_AST_ROWS=`, `-D AWTO_AST_RES=0|1` in `fw/test/asteroids.c`; bands = ceil(rows / 6); variant builds need `-D AWTO_SAVER_INFO=_OFF --fw-args="--xdata-floor 0"`.
- Variants beyond 512 cells write tile glyphs the hardware could not address; they measure cost only (render reads the uploads, not the OSD model).

## Addendum (2026-11-19): Asteroids-only image
- Question (Dan): with Pac-Man / Scope 2 dropped (`./dev.py build --savers asteroids`, `docs/saver-mode.md` "Selecting savers"), how much finer does Asteroids fit? Sim builds, info overlay off (variants need it), `--xdata-floor 0` to read the number, floor 700.
- XDATA free, Asteroids-only: 917 B at 360 x 198 (all-on: 720). Spare over the floor: 217 B (203 with the overlay on).
| variant | canvas | XDATA free | fits floor 700 | frames/s | saver ms | note |
|---|---|---|---|---|---|---|
| c30x11 today | 360 x 198 | 917 | yes | 25.00 | 5.8 | control |
| c35x13 identity map | 420 x 234 | 842 | yes, 142 spare | 25.00 | 6.2 | 455 of 512 ids, real build; bars 21 + 20 px: `-D AWTO_AST_ODD_BAR_OK=1` |
| c40x15 | 480 x 270 | 827 | geometry yes | 25.00 | 6.3 | 600 cells > 512 ids: cost only |
| c60x22 | 720 x 396 | 707 | geometry yes, 7 spare | 25.00 | 4.8 | 1320 cells > 512 ids: cost only |
| r2x40x15 objects 2x | 480 x 270 | 827 | geometry yes | 24.92 | 9.7 | cost only |
| r2x60x22 objects 2x | 720 x 396 | 707 | geometry yes | 25.00 | 7.3 | cost only |
- 35 x 13 (1.17x finer) fits with 142 B spare. In an all-on image it did not: 720 - 75 = 645 < 700.
- Shared ids (slot ring) do not fit, [calc] from the table: 720 x 396 needs 1320 B of slots on top of 707 free; 480 x 270 needs 600 B on top of 827 (227 left < 700). A sparse cell -> slot list (about 100 live tiles x 3 B = 300 B) is more than the 217 B spare.
- 24 x 36 mode (OT-8, layout unproven, not built): ids stay, canvas 3 rows x 108 B (+162 B) + word y (+26 B) = about +190 B [calc] <= 217 B: the only 720 x 396 route that fits the XDATA; needs the hardware test first.
- Frames: `asteroids_res.py render` of c35x13 uploads 455 of 455 tiles; picture `tmp/asteroids_res/compare.png` (c30x11 | c35x13 | r2x60x22, panel crop).
- Tools: `scripts/asteroids_res.py build` now builds Asteroids-only images (`--savers asteroids`).
