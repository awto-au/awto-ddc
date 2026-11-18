# Saver / game library: shared graphics + sound (Dan's request 2026-11-18)

Status 2026-11-18: inventory + design; steps 1 (draw core) and 2 (screen) done, "Migration log" below. Savers: `docs/screensaver.md`, `docs/saver-mode.md`.

- Numbers: sim (fast core, dw8051 timing), default image of main b7fa3a8 unless a row says otherwise (`AWT26110003-slbase-be`, audio build `-slbaseav-be`).
- Sizes: `python scripts/saver_lib_sizes.py MAP` (CH_ area per function / const, ST_ stub, bank; XDATA per module from `sdcc_mem_report.py`).
- Speed: `saver_loop_cost.py --case scope|asteroids|scope2|pacman --pcprof`, `asteroids_speed.py`, `pacman_speed.py`, `scope2_sim.py`.
- Proof of no change: `scripts/saver_frames_md5.py` (md5 of OSD state + render at every "frame complete" sync line, `--compare A B`).

## Conclusions

- Sound is already one module (`pacman_sound.c`: Pac-Man, Asteroids, alert, key click, calibration). Sharing it = rename + table-driven cmd -> track; saves ~150 B, no speed effect.
- Line drawing is already shared (`tools/osd_lines`, compiled once into `scope_saver.c`, called by Scope 1 + Asteroids). It is the hot spot: `cursor_plot` + generic-pointer helpers + `__mulint` = 40-50 % of Scope 1 and ~30 % of Asteroids time. Biggest cheap win = an 8051-aware, clip-aware version of the same library, pixel-identical.
- Real duplication is in the screen setup (5 copies of begin / row commands / map / placement), the tile upload with rotation (4 copies), the frame-done pattern (3 copies), the generators (3 glyph packers, 3 copies of a 5 x 7 font).
- Pac-Man has no sprite engine on the chip: sub-tile pieces are made by the generator and replayed as 27 KB of cell deltas. An on-chip sprite layer is new capability (and the largest possible const saving, ~20 KB), not deduplication.
- XDATA: savers never run together, yet each keeps its own statics (Asteroids 366 B, Scope 2 204 B, Scope 1 232 B incl. the shared 173 B canvas). One overlay struct would free ~270 B.
- Expected total: code -1.5 to -2.5 KB, const -2.3 KB (Scope 2 turned copy) now, -20 KB more with an on-chip Pac-Man; XDATA +270 B free; Scope 1 / Asteroids draw time -30 to -50 %.

## (a) Inventory: graphics primitives per saver

Bytes = CH_ area (code incl. its local consts); B = bank. `-` = not used.

| primitive | Pac-Man `pacman_classic.c` | Scope 1 `scope_saver.c` | Scope 2 `scope_saver2.c` | Asteroids `asteroids.c` | Flash / splash `flash_screen.c` | QC `qc_osd.c` |
|---|---|---|---|---|---|---|
| screen begin (close, rot latch, reset, double buffer off, circuit, DVS) | inline in `AwtoPacmanClassic` (dup) | `AwtoOsdScreenBegin` | same | same | inline in `AwtoFlashDraw` (dup) | `AwtoOsdScreenBegin` |
| palette | table `g_pcPal` 36 B + `PcPal` loop | 3 calls | 4 calls | 3 calls | 4 calls | table 192 B |
| row commands | `PcWord` 48 B loop, row h 12 (dup) | `AwtoOsdRowCmds` | same | same | `FsWord` 48 B loop (dup) | in VLC blob |
| char map | `PcMaze` 183 B from `g_pcCell` 3024 B (3 B / cell), rot on read | identity loop in `AwtoScopeSaver` (dup) | `S2MapWord` 56 B per cell, 2-bit attrs, rot | identity loop in `AwtoAsteroids` (dup) | `FsCellId` 98 B computed, rot | VLC blob |
| cell write later (rot) | `PcCellSet` 43 B (step deltas) | - | `S2MapWord` | - | host over ISP | - |
| glyph upload | `__code` stream turned per byte (`PcGlyph` + `AwtoOsdRotSrc` + `AwtoOsdRevByte`) | `ScUpload` 147 B -> `AwtoOsdGlyph` 344 B (turns xdata) | `S2Glyph` 62 B (pre-turned table `s_tS2BaseRot` 2322 B) | `AstUpload` 147 B (= `ScUpload`) | `__code` stream turned per byte (dup of Pac-Man's) | VLC hardware decode |
| placement + scale-up | inline (WORD position > 255) (dup) | `AwtoOsdPlaceScaleUp` 199 B | same | same | inline, position 0 (dup) | own (2 maps) |
| canvas | - | `osd_lines` band 1 x 6 tiles, `g_aucScPix` 162 B + dirty 1 B + `g_scCv` 10 B | `g_aucScPix` as one 2-plane tile buffer (54 B) | `osd_lines` band (shared with Scope 1) + occupancy `s_aucOcc` 64 B | - | - |
| pixel | - | `osd_pixel` 75 B (graticule dots: `cursor_init` divides per dot) | `S2Run` 259 B vertical run, rot-aware | `osd_pixel` (shots) | - | - |
| line | - | `osd_line` 916 B + `cursor_*` 1311 B, one call per trace px | trace = vertical runs per column (`S2Trace` 240 B) | `osd_line` via `AstShape` 620 B polylines | - | - |
| clipping | `osd_line` bbox reject only, walks every px | bbox per band | clamp in `S2Trace`, `S2Char` | skip lines wholly outside the band (`AstShape`), cull objects (`AstCull` 266 B, wrap-aware) | - | - |
| circle / arc / curve | generator only (`circle`, Pac-Man disc) | sine table `s_tSine` 64 B, `ScY` 142 B | pulse table + linear interpolation `S2Pulse` 178 B | boom dashes on 8 headings (`AstDrawBoom` 450 B), cos table 17 B (`AstDir` 114 B) | generator (`pac_pixels`) | - |
| text / digits | pre-rendered glyphs (generator) | - | `S2Char` 739 B + `S2Text` 83 B, 5 x 7 font 78 B, scaled runs; `S2Uint` 102 B | digits as stroke shapes (`AstShape`, `AstDigits` 157 B) | pre-rendered glyphs + title table 60 B | in blob |
| sprites | generator: 12 x 12 pieces, dedup by content (106 1-bit, 73 2-bit), replay `PcStep` 457 B over 24.7 KB deltas | - | - | vector objects, culled per band | Pac-Man 6 x 4 tiles, 2 frames | - |
| dirty / reuse | delta records | every tile, every pass | per column mask `s_aMask` 80 B, slot ring, cursor cache 16 B | per-pass occupancy, HUD dirty bit | host rewrites changed cells | - |
| per-pass budget | timer: 31 ms sub-step (saver.c) | one column (2 bands) per pass | 8 ms + one tile (`AWTO_S2_PASS_MS`) | one column; runs on through empty ones | 3 + 3 steps (cells 110, glyphs 30) | one shot |
| frame done + sync | E9 0x74 per step | hidden first frame, then show + E9 0x76 / 0x77 | same, 0x7B / 0x7C | same, 0x90 / 0x91 | - | E9 0x50 |
| watchdog kick | every 128 port bytes | per column | per call, per 64 cells | per pass | every port byte | - |

- Shared today: `fw/osd/osd_screen.c` (720 B: begin / off, word, row commands, glyph, placement), `fw/osd/osd_rot.c` (123 B), `tools/osd_lines` (3328 B), the band canvas (173 B XDATA).
- Generators: `gen_pacman_classic.pack` (1 / 2-bit), `gen_scope2.pack` (+ turned), `gen_flash_screen` (uses Pac-Man's `pack`), `osd_lines_view.py` (decode); 5 x 7 fonts in `gen_pacman_classic.FONT` (25 chars), `gen_flash_screen.F5` (41), `gen_scope2.FONT` (22, column bytes): glyphs differ ('5', '6', '9', 'C', 'G'); Asteroids digits = own strokes.

## (a) Inventory: sound + game helpers

| primitive | where | bytes (audio build) | users |
|---|---|---|---|
| tone source (generator on / off, amp) | `PsStart` 89, `PsStop` 19, `PsBase` 16 | 124 | all |
| note write + amp gate (4 ms) | `PsNote` 142, gate in `AwtoPmSoundPoll` | 142 | all |
| sequencer (10 ms ticks, loop, no drift) | `AwtoPmSoundPoll` 346, `PsByte` 14 | 360 | all |
| priority + resume (waka / background wanted) | `PsRequest` 44, `PsResume` 33, `AwtoPmSoundBg` 77, generated `PsPrio` 105 / `PsLoops` 104 / `PsOff` 139 | 502 | Pac-Man, Asteroids |
| cmd -> track + sync rows | `AwtoPmSound` 296 (if chain) | 296 | Pac-Man, Asteroids, saver (alert) |
| one held tone | `AwtoPmSoundTone` 52 | 52 | key click, calibration |
| track data | `g_aucPsData` 604 | 604 | 17 tracks |
| XDATA | 13 B | | |
| per-game cmd ids | `AWTO_PC_SND_*`, `AWTO_AST_SND_*`, `AWTO_SAVER_SND_ALERT`, mute check `AstSnd` / `AstBg` | | duplicated constants |

| game helper | where | bytes |
|---|---|---|
| rng (xorshift16) | `AstRnd` | 106 |
| object pool | `AstAlloc` 39 + `AstAdd` 133 + `AstCount` 48 | 220 |
| heading table (64) | `AstDir` 114 + `s_tCos` 17 | 131 |
| toroidal distance / hit | `AstDiff` 91 + `AstNear` 294 | 385 |
| fixed-rate tick | Pac-Man in `saver.c` (`s_usTick = now`, drifts; D5); Asteroids none (frame = 2 ticks) | - |

## Sizes per file (default image)

| file | code | const | stubs | XDATA | banks |
|---|---|---|---|---|---|
| `scope_saver.c` | 2246 | 64 | 16 | 232 (module, incl. canvas + osd_lines) | 11, 13 |
| `tools/osd_lines/osd_lines.c` | 3328 | 0 | 16 | in `scope_saver` | 13 |
| `scope_saver2.c` | 4761 | 5386 | 96 | 204 | 8, 11, 12 |
| `asteroids.c` | 10221 | 723 | 208 | 366 | 8, 13 |
| `pacman_classic.c` | 1714 | 36924 | 80 | 10 | 11, 12, 13 |
| `pacman_sound.c` (audio build) | 1128 | 604 + 348 generated | 80 | 13 | 8, 10, 11, 13 |
| `flash_screen.c` | 1220 | 2490 | 24 | 2 | 11, 13 |
| `qc_osd.c` | 965 | 6918 | 16 | 39 | 11, 12 |
| `saver.c` | 1519 | 0 | 80 | 22 | 8, 13 |
| `osd_screen.c` + `osd_rot.c` | 843 | 0 | 72 | 4 | 13 |

## Speed today (sim, default image, 2026-11-18)

| saver | pass | frame | top PC shares |
|---|---|---|---|
| Scope 1 | 26.7 ms mean (saver 22.7 = 85 %), worst 58 | 1127 ms (0.89 / s) | `cursor_plot` 27 %, `__gptrget` 9, `osd_clear` 8, `osd_line` 7, `__mulint` 6, `ScPass` 6, bank trampoline 5, `cursor_init` 5, `AwtoOsdGlyph` 5 |
| Asteroids | 13.6 ms mean, worst 30 (`asteroids_speed`: column 9.6 ms, p95 20) | 256 ms (3.9 / s, 7.96 ticks / s) | `cursor_plot` 17 %, `osd_line` 9, trampoline 7, `AstPass` 7, `AstShape` 7, `AstTileInk` 6, `__mulint` 4, `__gptrget` 4 |
| Scope 2 | <= 8 ms + one tile per call | 152 ms (6.6 / s) | `docs/screensaver.md` |
| Pac-Man | 4.4 ms per sub-step | 31 ms timer (32 / s) | `docs/pacman.md` |

## (b) What is duplicated, and the shared layers

| layer | today | shared form | users |
|---|---|---|---|
| screen | `osd_screen.c` used by scopes / Asteroids / QC; Pac-Man and flash inline copies | + `AwtoOsdMap1` (identity 1-bit map + bases), `AwtoOsdPlaceScaleUp` with WORD position, row height parameter already there | all 6 |
| canvas | band canvas in `osd_lines`, uploads in `ScUpload` / `AstUpload` / `S2Glyph`, occupancy in Asteroids only | band canvas + `AwtoOsdTile` (rot cell + glyph slot) + occupancy bits (skip blank-to-blank uploads) for every band user; per-call ms budget (`AWTO_S2_PASS_MS` model) | Scope 1, Asteroids, Scope 2 tile buffer |
| draw | `osd_line` (no clip), `osd_pixel` (div per dot), `S2Run`, `S2Char` | `osd_line` clipped to the canvas (same pixels), `osd_hrun` / `osd_vrun`, `osd_polyline` (int8 vertex lists, shift, quarter turn: `AstShape`'s core), `osd_circle` / `osd_arc` (midpoint, int16), `osd_bezier2` (quadratic, forward differences, n segments of `osd_line`), `osd_text5x7` (one font table, scale, clip: `S2Char`'s core) | Scope 1 / 2, Asteroids, future games |
| sprite | generator-made pieces (Pac-Man), vector objects (Asteroids) | on-chip: sprite = (glyph set, px, py); per tile compose pieces over the static tile (priority = draw order, later wins, as the generator's `overlay`), dedup by content in a small slot ring (Scope 2's ring + cache model), only changed tiles uploaded (occupancy) | Pac-Man on chip (new), Asteroids HUD ships |
| sound | `pacman_sound.c` | `snd.c`: same player; per game a generated table {cmd -> track, prio, loops, offset}; no per-game if chain; game ids in the generated header | Pac-Man, Asteroids, alert, key click |
| game | Asteroids only | `game.c`: rng, pool (fixed array, type byte 0 = free), 64-step sin / cos, toroidal diff, fixed-rate tick (`at += period`, no drift: D5) | Asteroids, Pac-Man on chip |
| generator | per script | `scripts/osd_gfx.py`: `pack(g, bits, turned)`, one 5 x 7 font + `text_px`, `arr()` / bank pragma emit, `say` / repo root; `gen_*` import it | all `gen_*`, `flash_screen.py`, `osd_lines_view.py` |

## (c) Design

### Module API (C, SDCC mcs51 large, banked)

```c
// fw/osd/osd_screen.c (screen)
void AwtoOsdScreenBegin(void);                                    // exists
void AwtoOsdRowCmds(BYTE ucRows, BYTE ucRowH, BYTE ucCols);       // exists
void AwtoOsdMap1(BYTE ucCols, BYTE ucRows, BYTE ucAttr);           // identity map, glyph id = cell; + col max + SRAM bases
void AwtoOsdPlaceScaleUp(WORD usPosH, BYTE ucPosV, BYTE ucCols, BYTE ucRows, BYTE ucFactor);   // WORD for Pac-Man
void AwtoOsdTile(WORD usCell, const BYTE __xdata *pucB);            // geometry latched by AwtoOsdMap1: rot cell, font base, glyph words
// tools/osd_lines (canvas + draw); OSD_MEM = __xdata on SDCC mcs51
void osd_line(osd_canvas OSD_MEM *c, int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint8_t ink);   // clipped walk, same pixels
void osd_polyline(osd_canvas OSD_MEM *c, const int8_t __code *v, int16_t cx, int16_t cy, uint8_t shift, uint8_t quarter);
void osd_circle(osd_canvas OSD_MEM *c, int16_t cx, int16_t cy, uint8_t r, uint8_t octants);         // arc = octant mask
void osd_bezier2(osd_canvas OSD_MEM *c, const int16_t *p, uint8_t segs);
void osd_text(osd_canvas OSD_MEM *c, const char *s, int16_t x, int16_t y, uint8_t scale);           // 5 x 7
// fw/test/snd.c (sound)
void AwtoSnd(BYTE ucCmd); void AwtoSndBg(BYTE ucState); void AwtoSndPoll(void); BYTE AwtoSndTone(BYTE ucSc, WORD usMs);
// fw/test/game.c (game)
BYTE AwtoRnd(void); void AwtoDir(BYTE ucAng);  // -> g_cAwtoDx / g_cAwtoDy
```

- At most 3 parameters where possible: the 4th and later go to XDATA `_PARM_` bytes (floor 700 B) and cost a store per call.
- Generic (library): pixel / run / line / polyline / circle / curve / text into a canvas; tile upload with rotation; screen set-up; sound player; rng / pool / tables.
- Per game: shapes, palettes, maps, tracks, priorities, game rules, layout constants: generated headers and the game file.

### Bank placement rules

- A `__code` table and every function that reads it share a bank: `#pragma place bank(N)` before each (it pins only the next definition). movc reads the running bank.
- Library code reading a game's table: pass the bytes, never a `__code` pointer across banks; or a leaf reader per game in the data's bank (`PcGlyph`, `FsByte` pattern).
- `gptr_const_xbank` link gate: a const in a bank must not cover the XDATA address of a generic pointer target (seen: Pac-Man cells moved to bank 13, delta B capped at 7200 B in bank 11). New consts go to banks with room and are checked with `fw_gates.py` link.
- Library code: bank 13 today with `osd_screen.c` (only ~3 KB left there for code: message-table reserve, `docs/asteroids.md`); new library code to bank 8 / 10 (most CH_ room: 10.7 / 12.3 KB).

### Generator side (Python)

- `scripts/osd_gfx.py`: `pack(tile, bits=1|2, turned=False)` (data-port byte order), `FONT5X7` (one table, union of the three), `text_px(plane, s, x, y, scale)`, `tiles(plane) -> (unique glyphs, cell ids)` (dedup), `arr(name, data, bank)` / `define(name, value)`, `say()` / `repo_root()`.
- `gen_pacman_classic`, `gen_scope2`, `gen_flash_screen`, `gen_asteroids` import it; `tests/` checks the generated `.inc` files byte-identical before / after the move.
- ROM-derived data (Asteroids shapes) stays generated into a gitignored include from `/vendors/atari/...`; the shared module holds only our own code and fonts. Same rule for any future ROM-derived game (Pac-Man maze / sprites from a ROM would follow it).

### Savings (estimates; measured rows in the migration log)

| module | code | const | XDATA |
|---|---|---|---|
| screen: Pac-Man + flash adopt begin / row cmds / placement; `AwtoOsdMap1` for Scope 1 + Asteroids; one tile upload | -0.8 to -1.0 KB | 0 | 0 |
| draw: `S2Char` -> `osd_text`, `AstShape` -> `osd_polyline`; osd_lines specialised (xdata pointers) | -0.3 to +0.2 KB | 0 | 0 |
| rotation: 256 B bit-reverse table in `AwtoOsdRevByte`; Scope 2 drops `s_tS2BaseRot` (turns on upload) | +0.25 KB | -2.3 KB | 0 |
| sound: generated cmd table instead of the if chain | -0.15 KB | +0.03 KB | 0 |
| state overlay: one union for the running saver's statics | ~0 | 0 | +270 B free |
| sprite + game: Pac-Man on chip (pieces composed per tile, game logic) instead of 27 KB of deltas | +6 to +9 KB | -20 KB | -150 B |
| generators | -150 lines Python | | |

### Speed

- Draw specialisation (no generic pointers, byte bit index, clipped walk): Scope 1 column -30 to -50 %, Asteroids pass -20 to -30 % (estimate from the PC shares above; measured in the log).
- Bit-reverse table: `AwtoOsdRevByte` 8-step loop -> one movc: every turned glyph upload faster (Scope 1 / Asteroids / Pac-Man load / flash with Rotate 180, the unit 3 setting).
- Banked trampoline (`__bs_call`, 5-8 %): keep the per-pixel path inside one bank (canvas + draw in the same bank as their callers' hot loops).
- Measure every step: `saver_loop_cost.py --pcprof`, `asteroids_speed.py`, `pacman_speed.py`, `scope2_sim.py`; sim cycles per pass before / after.

### Risks

- Bank layout: moving code changes CH_ placement; the link gate (`gptr_const_xbank`) has failed on such moves before. One module per step, gate each.
- XDATA floor: new `_PARM_` bytes and locals; check `fw_gates.py` / free bytes per step.
- Speed regressions from extra banked calls on per-pixel paths.
- Behaviour drift: every step must keep frames md5-identical (`saver_frames_md5.py`, upright and Rotate 180) until a step is meant to change pixels.
- Parallel edits: `saver.c` is being changed by other work; migrations stay out of it.
- Sprite engine: new code, Pac-Man stops being a recording; needs its own design and Dan's yes (D-SL3).

### Migration order (smallest / safest first, each gated)

1. Draw core: `osd_lines` pixel-identical speed-up (xdata pointers, clipped walk). Host equivalence test + frames md5 Scope 1 / Asteroids. Done.
2. Screen: `AwtoOsdMap1` + shared tile upload for Scope 1 / Asteroids. Frames md5. Done.
3. Rotation table (256 B) in `AwtoOsdRevByte`; then Scope 2 drops its turned copy. Frames md5 with Rotate 180.
4. Pac-Man and flash adopt `AwtoOsdScreenBegin` / `AwtoOsdRowCmds` / `AwtoOsdPlaceScaleUp` (WORD position). Frames md5; `splash_sim.py` for the splash timing.
5. Generators: `scripts/osd_gfx.py`; generated `.inc` byte-identical.
6. Draw API: `osd_polyline` (from `AstShape`), `osd_text` (from `S2Char`, needs a 2-plane canvas flag), `osd_circle`, `osd_bezier2`.
7. Sound: `snd.c` rename + generated cmd table (after the `saver.c` work lands).
8. State overlay (one union); then game helpers into `game.c`.
9. Sprite layer + Pac-Man on chip (design first).

## Decisions for Dan

- D-SL1: rename the sound player to a generic `snd` module (touches Pac-Man, Asteroids, `saver.c`, key click) once the `saver.c` work is merged?
- D-SL2: Scope 2 turned copy (2.3 KB const) traded for a 256 B bit-reverse table and per-byte turning at upload (slower Rotate 180 uploads, measured before deciding)?
- D-SL3: Pac-Man on chip (sprite layer + game logic, ~20 KB const saved, no longer a fixed recording) or keep the recording?
- D-SL4: one XDATA overlay for saver state (+270 B free) at the cost of a mechanical rename in every saver file?
- D-SL5: Asteroids game speed now follows the faster draw (9.46 ticks / s vs 7.96): pace the game by time (fixed tick) instead of per frame, or keep "as fast as it draws"?

## Migration log

Proof per step: `saver_frames_md5.py --saver S --frames N [--rotate]` on main (`slbase`) and the step image, then `--compare`: all frames IDENTICAL. Gates `fw_gates.py` ALL PASS (health `delay cal` known), `saver_sim.py` (audio build) all PASS, `pytest` 323 passed, `magic_lint` 0.

| step | what | frames md5 | code / XDATA | speed (sim) |
|---|---|---|---|---|
| 1 draw core (b24b690) | `osd_line` walks only the visible part (closed-form first step: `skip_steps` / `minor_steps`, stop at the first pixel past the far edge); `OSD_MEM` = `__xdata` on SDCC (no `__gptrget`); cursor keeps tile / byte base / bit index incrementally (no `__mulint` per pixel); byte divide in `cursor_init` for 0..255; `AwtoOsdGlyph` writes the data port directly (was a banked `ScalerOsdDataPort` call per byte) | Scope 1, Scope 2, Asteroids, Pac-Man: 12 frames upright + 8 Rotate 180 each; Scope 1 / Asteroids also 40 frames: IDENTICAL | CH_ +395 B, stubs +48 B, XDATA -9 B (1015 -> 1006 free) | below |
| 2 screen (284834d) | `AwtoOsdMap1(cols, rows, attr)` + `AwtoOsdTile(cell, bytes)` in `osd_screen.c`; Scope 1 / Asteroids drop `ScUpload` / `AstUpload` and their map loops | Scope 1, Asteroids upright + Rotate 180: IDENTICAL | CH_ -77 B, stubs +8 B, XDATA 0 | same |

- Host proof of step 1: `tests/test_osd_lines_clip.py` compiles the original prototype (`docs/osd-prototypes/osd-lines-12x18.zip`) and the new library, > 100 000 random pixel / line / clear calls per tile size (12 x 18, 8 x 8, 5 x 7, 16 x 16, 32 x 32, 1 x 1, 32 x 3), endpoints up to full int16: pixels + dirty flags equal after every call.
- Rejected inside step 1: cursor steps / plot as macros (no call per pixel): -3 % instructions, no change in us per pass, +1.7 KB code.
- Rejected inside step 2: `AwtoOsdTile(canvas, cell0, tile)` (computes cell + pointer itself): +244 B, net worse than the call-site form.

| measure (sim, dw8051) | main `slbase` | after steps 1 + 2 (`sl5`) |
|---|---|---|
| Scope 1 frame | 1127 ms (0.89 / s) | 768 ms (1.30 / s) |
| Scope 1 pass mean / worst | 26.7 / 58.0 ms | 14.7 / 40.3 ms |
| Scope 1 instructions per pass | 147 657 | 75 578 |
| Asteroids column pass mean / p95 / max (`asteroids_speed.py`) | 9.6 / 20 / 29 ms | 8.0 / 16 / 25 ms |
| Asteroids game ticks / s | 7.96 (3.98 frames / s) | 9.46 (4.73 frames / s) |
| Asteroids pass mean / worst (`saver_loop_cost.py`) | 13.6 / 30.4 ms | 11.4 / 33.3 ms |
| Scope 2, Pac-Man | 152 ms / frame, 33 ms / step | unchanged (do not use `osd_lines`) |

- After the merge with main f34ce75 (saver D1 / D4 / D5, input scan rates D7): frames still IDENTICAL to `slbase` for all four savers; XDATA free 997 B (default), 982 B (audio build).
- Hot spots left: Scope 1 `cursor_plot` 25 %, `osd_clear` 10 %, `ScPass` 9 %, `cursor_init` 7 % (one per graticule dot: draw the dotted graticule as runs next); Asteroids `AstPass` / `AstShape` / `AstTileInk` 8-9 % each, trampoline 9 %.
