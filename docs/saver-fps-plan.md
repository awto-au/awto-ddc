# Savers at 25 frames/s: algorithmic plan (Dan 2026-11-18)

Status 2026-11-18: design + sim prototypes (Scope 1, Asteroids). Companion docs (other agents): `docs/saver-fps-budget.md` (CPU / port budgets, hard limits), `docs/saver-fps-hw.md` (OSD hardware features). Savers: `docs/screensaver.md`, `docs/saver-library.md`.

- Numbers: sim (fast core, dw8051 timing), 1080p60 input, upright unless stated. Base = main 6df194c (`AWT26110003-fpsbase-be`).
- Tools: `scripts/saver_fps_probe.py` (frames/s, port bytes / frame, calls / frame, cost per call in a burst), `scripts/saver_fps_model.py` (Scope 1 tile counts), `saver_loop_cost.py --pcprof` (per-pass split + PC shares), `saver_frames_md5.py` (pixel identity).
- Asteroids md5 proof needs `-D _AWTO_AST_FIXED_TICKS` on both images (2 ticks per frame, unpaced): a paced frame lands on time-dependent ticks.

- Update 2026-11-19: default clock is now MCU 350.8 / flash 70.2 MHz and OSD stores are direct; measured fps per clock and the open run-glyph tests (T-A, T-C): `docs/saver-fps-hw.md` "Update 2026-11-19", `docs/clock-sweep.md`. Sim numbers below predate that.

## Frame budget (all savers)

| item | value | source |
|---|---|---|
| frame at 25 frames/s | 40 ms wall | |
| main loop outside the saver, per pass | 4.05..4.19 ms | `saver_loop_cost` scope / scope2 / asteroids: pass - `AwtoSaverPoll` |
| saver slice per call | 8 ms (+ one unit of work) | D6: DDC/CI reply latency = a pass; Scope 2 `AWTO_S2_PASS_MS` model |
| passes per frame at 8 ms slices | 40 / 12.1 = 3.3 | |
| saver CPU per frame | **<= 26 ms (sim)** | 3.3 x 8 ms |
| 1-bit tile upload (27 B, `AwtoOsdTile` incl. its word loop / rotation / banked port calls) | 250 us sim | probe: gap between back-to-back calls, base Scope 1 |
| port byte alone | sim 2.39 us (`ScalerOsdDataPort`), 1.46 (direct); unit 3: 4.12, 2.39..2.60, 1.95 unrolled | `docs/saver-fps-budget.md`, `docs/osd-hw-tests.md` T1 / T2 |

- The unit runs port-write loops ~1.7x slower than the sim (budget doc): port-heavy savers lose more on the unit than compute-heavy ones.
- Fewer, longer slices buy saver time at the cost of DDC/CI latency (D6): 16 ms slices -> 2 passes -> ~32 ms (budget doc lever 1).

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
- Limit: ~168 trace tiles per frame. Prototype: per tile ~0.28 ms compose (sim, C, XDATA locals) + upload; 4.5 KB port / frame = 18.5 ms unit SDK path, ~11 ms direct.
- Verdict: **NO in C at 87.7 MHz** (prototype 6.3 / s, 9.0 / s fast port); **YES-WITH-HW-FEATURE**: run-glyph trace (`docs/saver-fps-hw.md` #1: frame = map writes only), or MCU x2 + direct port + asm compose (est. 15-20 / s, not 25).

### Scope 2 (480 x 270, 40 x 15 tiles, 2-bit)

- 25 frames/s: the pulse drifts `X0_STEP` 2 px per frame = 50 px/s.
- Base work (probe): 65 dynamic 2-bit tiles (`S2Fill` 1.9 ms each in a burst) + 87 map words = 3770 port B / frame; 174 ms / frame (5.7 / s). PC: `S2Run` 12 %, trampoline 9 %, `S2Trace` 9 %, `S2BaseCopy` 8 %, `S2ColBegin` 7 %, port 7 %.
- Port share at unit rates: 3.8 KB = 15.5 ms (`ScalerOsdDataPort`), 9 ms direct.
- Code levers (budget doc 1 + 3 + 5 + 8): ~11 / s at 87.7 MHz; + MCU x2 + dual read: est. ~28 / s. Add here: skip columns whose trace y values did not change (flat baseline / tail).
- Verdict: **YES-WITH-HW-FEATURE** (MCU x2, direct port; or run-glyph trace). Not prototyped: Scope 2 / plane order are another agent's.

### Asteroids (360 x 198, 30 x 11 tiles, 1-bit)

- 25 frames/s with game ticks at 7.94/s (`AWTO_AST_TICK_MS` 126): render at interpolated positions `p + v x (t - t_tick) / 126` per frame; game logic unchanged.
- Motion per frame at 25/s: rocks 0.2..0.6 px, shots 1.9 px, ship <= 0.8 px: most objects keep their pixel position from one frame to the next.
- Base work (probe): 41 tile uploads + 58 `AstPass` (24-object cull each, 204 us when empty) + 84 `osd_line` (~0.9 ms each incl. 32-bit clip set-up) per frame; 205 ms / frame (5.0 / s), saver 67 % of the pass.
- Levers: only tiles under objects whose pixels changed (old box | new box), clean passes skipped without culling, specialised line walk. Result below.
- Verdict: **YES** (prototype 20.0 / s default, 22.2 / s fast port; 632 port B / frame, so the unit's slower port adds ~1 ms). Remaining gap: pre-rendered rock / saucer sprites (remove most of `AstShape` + `AstLine`, ~28 % of samples) or MCU x2.

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
| faster port write (direct / unrolled / asm, ~2x) | all | Scope 1 / 2 port-bound | direct stores are the default since 2026-11-18 (data port only; unit port-rate check pending) |
| 2-bit planes as layers (static plane uploaded once) | Scope 2 | done for the graticule today; trace tiles still carry both planes | HW agent: 1-bit layer over 2-bit |
| hardware glyph decode (VLC) for sparse trace tiles | Scope 1 / 2 | fewer port bytes per tile | HW agent |
| smaller raster / larger scale factor | all | fewer tiles; coarser picture | not proposed (Dan asked for fill + finer) |
| skip unchanged trace columns | Scope 2 | flat baseline / tail columns keep their tiles | design |

## Prototype results (sim, 2026-11-18)

Images: `fpsbase` (main 6df194c), `fps2` / `fpsfinal` (this branch, default), `fps2fast` (`-D _AWTO_OSD_FAST_PORT`, flag since removed: direct port stores for Scope 1 / Asteroids tiles).

| measure | base | prototype default | + fast port |
|---|---|---|---|
| Scope 1 frames/s (ms / frame) | 1.17 (854) | 6.25 (162) | 9.0 (110) |
| Scope 1 tiles / port B per frame | 384 / 12 312 | 168 / 4 532 | 172 / direct |
| Asteroids frames/s | 5.0 (4.35 in `saver_loop_cost`, tick-paced) | 20.0..20.8 | 22.2..22.7 |
| Asteroids tiles / port B per frame | 41 / 1 110 | 23 / 632 | 22 / direct |
| Asteroids game ticks/s | 7.90 | 7.95 | 7.95 |
| Asteroids unpaced 2-tick frame (`_AWTO_AST_FIXED_TICKS`) | 234 ms | 94 ms | |
| XDATA free (default image) | 997 B | 840 B (audio build 826) | |
| code | `scope_saver.c` 2023, `asteroids.c` 10286 | 1774, 11844 | |
| CH_ free bank 8 / 13 | 11166 / 27601 | 8331 / 32298 | |

- Steps (Asteroids, unpaced 2-tick frames): dirty boxes + time slices 234 -> 108 ms; byte line walk 95; clip to changed rows 94. Scope 1: first incremental 6.0 / s; bank pin + shifts 6.25.
- Pixel identity: Scope 1 md5 IDENTICAL to main, 24 upright + 12 Rotate 180, default and fast port. Asteroids with `_AWTO_AST_FIXED_TICKS` on both images (frac 0): IDENTICAL 150 upright + 16 Rotate 180, every step. Scope 2 / Pac-Man: IDENTICAL to a main build (12 upright + 8 Rotate 180 each).
- Gates on `fpsfinal`: `fw_gates.py` ALL PASS (health `delay cal` known), `saver_sim.py` (audio build `fpsav`) all PASS (Scope 2 5.50 / s), `pytest` 349 passed, `magic_lint` 0.
- Interpolation (Asteroids at 25 / s): looked at sim frames (`asteroids_sim.py --fps 25`): no trails, wrap clean. Rocks move 0.2..0.6 raster px per frame: each 1-px step is shown (1 raster px = 10.7 panel px); before, shots jumped 6 px per tick.
- Rejected: Scope 1 tile as 18 16-bit row words (OR runs, pack): 8.0 / s vs 9.0 (SDCC 16-bit XDATA ops cost more than byte bit ops).
- Left in the profiles: Scope 1 `ScRun` 22 %, `ScRuns` 21 %, `ScTile` 16 % (fast port); Asteroids `AstShape` 14 %, `AstLine` 14 %, trampoline 11 % (mostly `ScalerOsdDataPort` per byte), `AstPass` 7 %.
- `tools/osd_lines` line / pixel / cursor code (3.9 KB) is now called by no saver (only `osd_canvas_init`): drop from the image in a follow-up; the host library and its test stay.
- Asteroids saver CPU at 20 / s: 5.25 ms saver per pass x 110 passes/s = 29 ms per frame vs the 26 ms budget.

## Direct port stores as default (sim, 2026-11-18, Rotate 180, ms / frame by `saver_port_ab.py`)

- Change: `AWTO_OSD_PORT(v)` (direct `0x0092` store) in `osd_screen.c`, Scope 1 / 2, Asteroids, Pac-Man; `AwtoOsdGlyph` / `AwtoOsdTile` removed (`AwtoScTile` is the one tile path); `_AWTO_OSD_FAST_PORT` gone. Address set stays `ScalerOsdAddrSet`.
- Sim port model: MOVX write to `0x0092` = 2 + 22 cycles (`dw8051_model.json`); `osd_port_cal.py` direct loops 0.99-1.16x the unit (T2). Base numbers below use the same model.

| clock | saver | base 465cb97 | direct stores |
|---|---|---|---|
| 87.7 MHz | Scope 1 | 152 | 117 |
| 87.7 MHz | Scope 2 | 182 | 158 |
| 87.7 MHz | Asteroids (paced 40 ms; saver CPU per frame 32.2 -> 29.3; unpaced 2-tick frame 97 -> 92) | 42 | 44 |
| 87.7 MHz | Pac-Man (per sub-step) | 31 | 31 |
| 175.5 MHz | Scope 1 | 95 | 71 |
| 175.5 MHz | Scope 2 | 115 | 101 |
| 175.5 MHz | Asteroids (paced) | 41 | 40 |

- Frames md5 IDENTICAL, 40 frames upright + Rotate 180, all four savers (Asteroids on `_AWTO_AST_FIXED_TICKS` images).
- c1 (`ScalerOsdAddrSet` / `ScalerOsdAddrLsb` in common): Scope 2 158 -> 155, Scope 1 117 -> 119, Asteroids 44 -> 44: not kept. `ScalerOsdDataPort` is no longer called by a saver: nothing to pin.

## Recommended order

1. Asteroids prototype as the production path (pixel-identical drawing proven; interpolation changes frames by design). Unit 3: frames/s from the sync log, tearing.
2. Scope 1 incremental (pixel-identical, 5.3x).
3. Direct port stores (budget lever 3, hw #5): done 2026-11-18, default in every saver (Scope 2, Pac-Man included).
4. MCU 175.5 MHz trial on unit 3 (budget lever 2, hw T-L): likely closes Asteroids to 25.
5. Asteroids pre-rendered sprites if 3 + 4 fall short.
6. Scope 2 code levers (budget doc 1 + 3 + 5 + 8) after the plane-order work lands.
7. Scope 1 / 2 run-glyph trace after hw tests T-C (narrow chars) and T-A (grid windows).
8. Remove the unused `osd_lines` draw code from the image.
