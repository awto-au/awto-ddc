# Savers at 25 frames/s: algorithmic plan (Dan 2026-11-18)

Status 2026-11-18: design + sim prototypes (Scope 1, Asteroids). Companion docs (other agents): `docs/saver-fps-budget.md` (CPU / port budgets, hard limits), `docs/saver-fps-hw.md` (OSD hardware features). Savers: `docs/screensaver.md`, `docs/saver-library.md`.

- Numbers: sim (fast core, dw8051 timing), 1080p60 input, upright unless stated. Base = main 6df194c (`AWT26110003-fpsbase-be`).
- Tools: `scripts/saver_fps_probe.py` (frames/s, port bytes / frame, calls / frame, cost per call in a burst), `scripts/saver_fps_model.py` (Scope 1 tile counts), `saver_loop_cost.py --pcprof` (per-pass split + PC shares), `saver_frames_md5.py` (pixel identity).
- Asteroids md5 proof needs `-D _AWTO_AST_FIXED_TICKS` on both images (2 ticks per frame, unpaced): a paced frame lands on time-dependent ticks.

## Frame budget (all savers)

| item | value | source |
|---|---|---|
| frame at 25 frames/s | 40 ms wall | |
| main loop outside the saver, per pass | 4.05..4.19 ms | `saver_loop_cost` scope / scope2 / asteroids: pass - `AwtoSaverPoll` |
| saver slice per call | 8 ms (+ one unit of work) | D6: DDC/CI reply latency = a pass; Scope 2 `AWTO_S2_PASS_MS` model |
| passes per frame at 8 ms slices | 40 / 12.1 = 3.3 | |
| saver CPU per frame | **<= 26 ms (sim)** | 3.3 x 8 ms |
| 1-bit tile upload (27 B, `AwtoOsdTile` via `ScalerOsdDataPort`) | 250 us sim = 9.3 us/B | probe: gap between back-to-back calls, base Scope 1 |
| same on unit 3 | `ScalerOsdDataPort` 4.12 us/B, direct stores 2.4..2.6 us/B, unrolled 1.95 | `docs/osd-hw-tests.md` T1 / T2 |

- The sim charges ~2x the hardware per port byte: port-bound sim figures are pessimistic (budget doc reconciles).
- Fixed per frame: whatever is drawn, port bytes x us/B. 26 ms / 9.3 us = **2.8 KB per frame in the sim**, 6.3 KB at hw `ScalerOsdDataPort`, ~10 KB with direct stores.

## Per saver: what 25 frames/s means, work per frame, verdict

### Pac-Man

- 25 frames/s = 25 sub-steps/s; it runs 32 sub-steps/s today (`AWTO_SAVER_PACMAN_MS` 31, D5): 3 px per sub-step at 32/s, already smooth.
- Work: sub-step 4.4 ms (`pacman_speed.py`), 7.9 records = 24 port bytes mean, 19 max; pass mean 3.66 ms with the saver (`saver_loop_cost --case pacman`).
- CPU: 32 x 4.4 = 141 ms/s = 14 %.
- Verdict: **YES (done)**. Visible steps that stay at 8/s are content (dots, death frames at game-step rate), not frame rate.

### Scope 1 (384 x 216, 32 x 12 tiles, 1-bit)

- 25 frames/s: the trace redrawn per frame (phase + 3 table units = 3 px of the slow sine); smoothness = small phase step x 25/s (`AWTO_SC_PH_STEP` 3 = 75 px/s; 1 = 25 px/s).
- Model (`saver_fps_model.py`): trace 2874 px / frame, touches 151 of 384 tiles; incremental (now | last frame) 170 tiles; 18 distinct graticule tiles.
- Base work: all 384 tiles drawn (`osd_line` per px step, `osd_pixel` per graticule dot: 986 + 2324 calls / frame) and uploaded (12312 port B / frame); 854 ms / frame.
- Limit: port bytes. 170 x 27 B = 4.6 KB / frame = 43 ms sim, 19 ms hw (`ScalerOsdDataPort`), 11 ms hw (direct).
- Verdict: **YES-WITH-HW-FEATURE**: a faster port path (direct / burst stores, or hardware glyph decode) is needed; the drawing itself fits.

### Scope 2 (480 x 270, 40 x 15 tiles, 2-bit)

- 25 frames/s: the pulse drifts `X0_STEP` 2 px per frame = 50 px/s.
- Base work (probe): 65 dynamic 2-bit tiles (`S2Fill` 1.9 ms each in a burst) + 87 map words = 3770 port B / frame; 174 ms / frame (5.7 / s). PC: `S2Run` 12 %, trampoline 9 %, `S2Trace` 9 %, `S2BaseCopy` 8 %, `S2ColBegin` 7 %, port 7 %.
- Floor per tile after the levers below: upload 54 B (0.5 ms sim) + base copy + runs (~0.15 ms) = ~0.7 ms -> 65 tiles = 46 ms sim; with unchanged-column skip (flat baseline / tail: est. -30..40 %) ~30 ms. Port share at hw rates: 3.8 KB = 15.5 ms (`ScalerOsdDataPort`), 9 ms direct.
- Verdict: **YES-WITH-HW-FEATURE**: algorithm alone reaches ~13-15 frames/s (sim); 25 needs the faster port, or a 1-bit trace layer over the static 2-bit graticule (halves bytes, drops the base copy). Not touched here (Scope 2 / plane order are being changed by another agent).

### Asteroids (360 x 198, 30 x 11 tiles, 1-bit)

- 25 frames/s with game ticks at 7.94/s (`AWTO_AST_TICK_MS` 126): render at interpolated positions `p + v x (t - t_tick) / 126` per frame; game logic unchanged.
- Motion per frame at 25/s: rocks 0.2..0.6 px, shots 1.9 px, ship <= 0.8 px: most objects keep their pixel position from one frame to the next.
- Base work (probe): 41 tile uploads + 58 `AstPass` (24-object cull each, 204 us when empty) + 84 `osd_line` (~0.9 ms each incl. 32-bit clip set-up) per frame; 205 ms / frame (5.0 / s), saver 67 % of the pass.
- Levers: only tiles under objects whose pixels changed (old box | new box), clean passes skipped without culling, specialised line walk. Result below.
- Verdict: see "Prototype results".

## Levers (cost from the sim, not guesses)

| lever | applies to | cost / gain (sim) | status |
|---|---|---|---|
| incremental redraw: tiles touched now or last frame only | Scope 1 | 384 -> 172 tiles / frame, 12.3 -> 4.7 KB port / frame | prototyped |
| table-driven trace: per px column one vertical run (= `osd_line` pixels for dx = 1), amplitude tables (no `__mulint`) | Scope 1 | `osd_line` + `osd_pixel` (2324 dots) gone; per tile draw ~0.28 ms incl. graticule | prototyped |
| graticule computed per tile (18 distinct tiles: dots + frame edges) | Scope 1 | no canvas clear / no 2324 `osd_pixel` calls | prototyped |
| per-object dirty boxes (last drawn x / y / radius / key per slot) | Asteroids | uploads only where pixels can change; clean passes = 1 byte test | prototyped |
| specialised line walk (same Bresenham, byte divides, tables) instead of `osd_line` | Asteroids | no 32-bit `skip_steps`, no generic canvas cursor | prototyped |
| render interpolation at 25 frames/s | Asteroids | 1 multiply per object axis per frame | prototyped |
| time-sliced passes (8 ms + one column), multiple columns per call | Scope 1, Asteroids | frames no longer bound to one column per main pass (4 ms main loop each) | prototyped |
| hot draw path in one bank (pragma) | Scope 1, Asteroids | trampoline 10-16 % of saver PC samples | partly (Asteroids) |
| pre-rendered sprites (rock / saucer / ship bitmaps, shifted blit) | Asteroids | pixel-identical to the line walk (integer vertices); ~1 KB const rocks / saucer + 1.9 KB ship (64 headings); blit 12-bit window per row | design only: line walk first |
| faster port write (direct / unrolled / asm, ~2x) | all | Scope 1 / 2 port-bound | needs the garble diagnosis (`docs/osd-hw-tests.md`); switchable only |
| 2-bit planes as layers (static plane uploaded once) | Scope 2 | done for the graticule today; trace tiles still carry both planes | HW agent: 1-bit layer over 2-bit |
| hardware glyph decode (VLC) for sparse trace tiles | Scope 1 / 2 | fewer port bytes per tile | HW agent |
| smaller raster / larger scale factor | all | fewer tiles; coarser picture | not proposed (Dan asked for fill + finer) |
| skip unchanged trace columns | Scope 2 | flat baseline / tail columns keep their tiles | design |

## Prototype results

(filled below)
