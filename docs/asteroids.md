# Asteroids screensaver (stage 1: host tool + design)

Status 2026-11-18. Stage 1 = host side only. No firmware written, nothing flashed. Third DDC-triggered saver after Pac-Man / Scope (`docs/screensaver.md`).

## Licence boundary (decision needed, see Open)

- The Asteroids ROM set is Atari's; it stays in `/vendors/atari/asteroids-mame/` (manifest there). Never in this repo.
- ROM-derived data (shape tables, PNGs, `shapes.json`) lives only in `tmp/asteroids/`. `.gitignore` blocks ROM files, `asteroids/` dirs and `asteroids_shapes*`; `tests/test_asteroids_dvg.py` fails if any such file is tracked.
- The tool is clean-room: DVG semantics from the public hardware documentation and MAME's `avgdvg.cpp` (read to confirm the model, not copied).
- Firmware shapes must not be generated from the ROM into committed files. Plan: our own outlines, using the ROM decode only as a size / proportion reference.

## Host tool `scripts/asteroids_dvg.py`

- Run: `python scripts/asteroids_dvg.py [--zip PATH] [--out DIR]`; log `tmp/logs/asteroids_dvg.log`; output `tmp/asteroids/` (per-shape PNG, `shapes.json`, `frame_sample.png`).
- Reads `035127-02.np3` only (vector ROM, 1024 words, DVG word address base 0x800 = 6502 0x5000). The 6502 code is not run: the saver is our own game, attract-mode frames are not needed.
- Interpreter: VCTR (op 0..9: 10-bit |dy|, |dx|, sign bit 10, brightness in word 1, scale = global + op), SVEC (1 word, 2-bit magnitudes << 8, scale = global + 2 + bit 11 + 2 x bit 3), CUR (12-bit position, global scale), HALT, JSR / RTS / JMP (12-bit word address). Scale >= 10 draws nothing. Displacement = magnitude x 2^scale / 512 (scale 9 = x1).
- Catalog: 37-entry character table (blank, 0-9, A-Z), 4 rock outlines, saucer, 17 ship hull + 17 thrust-flame angle shapes, 4 explosion-debris patterns. Everything else in the ROM is swept and decoded into per-subroutine PNGs.

### Verification

- Every vector op in the ROM (2196 deltas) checked against an independent rate-multiplier model of the DVG (12-bit counters, as in MAME): worst error 0.5 px (integer pulse count).
- All 4 rock outlines return to their start point exactly and span exactly 64 x 64 units at global scale 0; characters are 8 x 12 units; hull / thrust shapes repeat a constant ~56-unit tip radius over 17 angle steps.
- Rendered shapes inspected visually: all 37 characters, rocks, saucer and ship read correctly.
- Not verified: the ship's step 15 vs 16 pairing (both point up; 15 is the mirrored variant), where the thrust flame is anchored (assumed: end point of the closed hull), the in-game global scale per object (needs the 6502 display-list code).

## Firmware design (stage 2)

### Rendering

- Same path as Scope 1 / 2: OSD tile map 32 x 12 tiles (384 x 216), 1-bit glyphs, one glyph per cell, `tools/osd_lines` `osd_line` into a one-tile-column band canvas shared with the scope savers (`g_aucScPix`, `g_scCv`; never two savers at once), band redrawn per column and per band, scale-up as `scope_saver.c`.
- Per pass: cull whole objects by bounding box first (about 10 objects x 128 passes), then draw only intersecting lines. Playfield = full 384 x 216, wrap-around.
- Upload only tiles touched this frame or last frame (object boxes at t and t-1 are recomputable, no stored previous frame): about 60 tiles x 27 B = 1.6 KB per frame instead of 10.4 KB for all 384 tiles.
- Rotate 180: flip x / y at draw time (`docs/osd-rotation.md`).

### Scale and rotation

- Shapes stored as int8 vertex pairs in 64-unit boxes; sprite size by arithmetic shift, no multiply: large rock /2 (32 px), medium /4 (16 px), small /8 (8 px). Ship /8 (~12 px, ratio to a large rock about 1 : 2.7 as in the original).
- Ship: 17 stored angles over 90 degrees (5.6 degree steps) plus x / y mirroring = 64 steps around the circle; step per frame chosen by the script. Thrust flame only on thrust frames.
- Characters: digits and the few letters used (score, GAME OVER), about 8 x 12 units, drawn /1 or /2.

### State without XDATA

- XDATA floor is 700 B: no new XDATA. Game state is not kept; like Pac-Man the host plays the game once and the firmware replays it.
- Host generator `scripts/gen_asteroids.py` (stage 2): Python game with an autopilot (rock motion, ship turn / thrust / shots, saucer, splits, score), emits a timeline of objects: shape, size, start t, end t, x0, y0, vx, vy (fixed point), plus ship angle / thrust keyframes. Position = closed-form function of t, so no per-object runtime state.
- t derives from the run-start time the saver already keeps (`s_ulSwap`) and `AwtoMs()`: zero new variables, frame skips are harmless.
- Loop: about 60 s of play, then restart.

### Budget (estimates, to be measured)

| item | bytes (banked code space) |
|---|---|
| shape data, our own outlines (about 400 vertices x 2 B + per-polyline headers + index) | ~1.2 K |
| timeline (about 60 objects x 8 B + ship keyframes) | ~1.5 K |
| renderer glue, object culling, mirror / shift transforms, timeline walker | ~2 K |
| saver hook + strings | ~0.2 K |
| total | ~5 K of the 20-30 K free in banks 11-13 |

- Data and its reader in the same bank (`#pragma place bank(N)`), as `scope_saver2.c`.
- XDATA: +0 B target. Any byte added must be paid for from the 700 B floor and recorded.
- Frame cost: 128 band passes (32 columns x 4 bands of 3 tile rows) per frame; measure sim cycles per pass and unit-3 frame rate before / after (`scripts/saver_sim.py`). Watchdog: kick per band pass.

### Saver integration

- `fw/test/saver.c`: new `AWTO_SAVER_ASTEROIDS` run id, `AwtoAsteroids(cmd)` with the same (1 draw, 2 next, 0 off) contract as the scopes; Alternate cycles all four savers.
- DDC/CI VCP 0xEB: next free value 7 = Asteroids (0 stop, 1 selected, 2 Pac-Man, 3 Scope, 4 Scope 2, 5 Flash, 6 alert tone). `docs/osd-editor-spec.md` and `docs/settings.md` row 121 list gets "Asteroids".
- Settings row 119 `screensaver`: add choice Asteroids (registry `fw/rtdfw/settings/registry.tsv`, `scripts/settings_gen.py`).
- Test only on unit 3; `saver_sim.py` extended for 0xEB = 7.

## Open

- Shape source: own outlines (planned) or generate from the ROM into an ignored include (then the firmware build needs the ROM and the image carries Atari-derived geometry).
- Sound: none planned (Pac-Man only has it).
- Game-over / attract text: wording for the loop end.
