# Asteroids screensaver

Status 2026-11-18. Stage 1 = host decoder, stage 2 = firmware (sim only, nothing flashed). Fifth saver after Pac-Man / Scope / Scope 2 (`docs/screensaver.md`).

## Licence boundary (Dan, 2026-11-18)

- The ROM set is Atari's: it stays in `/vendors/atari/asteroids-mame/` (manifest there). Never in this repo.
- Shapes are generated from the local ROM at build time (`scripts/gen_asteroids.py` via `asteroids_dvg.py`) into `fw/test/asteroids_data.inc`: gitignored, never committed. An image built with the ROM carries Atari-derived geometry; images are not committed either.
- No ROM: the same script writes our own outlines (4 rocks, saucer, ship + flame at 16 angles) into the same include, same shape ids. Log line `asteroids shapes: rom|fallback`; the saver pushes sync E9 0x90 with value 1 (ROM) / 0 (own).
- Digits are always our own strokes (`DIGITS` in the script).
- `fw_build.py` runs the generator first. Tests: `tests/test_asteroids_gen.py`, `tests/test_asteroids_dvg.py` (fails if a ROM-derived file is tracked).
- The decoder is clean-room: DVG semantics from public hardware documentation and MAME's `avgdvg.cpp` (read to confirm the model, not copied).

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

## Firmware (`fw/test/asteroids.c`)

### Game (runs on the chip)

- Pool of 24 objects (rock L / M / S, saucer L / S, ship shot, saucer shot, explosion), ship separate. Units 1/8 px, playfield 360 x 198 (`AWTO_AST_COLS` 30 x `AWTO_AST_ROWS` 11 tiles; `AWTO_AST_W` / `_H` derive from them), wrap-around (saucers leave the screen).
- One frame = 2 game ticks (finer motion and hit tests; frames are slow). Tick: move, autopilot, collisions, waves / saucer timer / respawn, score.
- Rocks split L -> 2 M -> 2 S; scores 20 / 50 / 100, saucer 200 / 1000. Wave n: 4 + n rocks (max 7). Saucer every 150..350 ticks while rocks exist; small saucer (25 %) aims.
- Autopilot: nearest rock / saucer, lead by relative velocity, turn 1 or 2 heading steps (64 headings), fire when within ~4 deg and 90 px (max 4 shots, cooldown 3), wander thrust bursts, flee when a rock is close behind. 3 lives, respawn when the centre is clear, game over -> new game after 60 ticks. No text (no GAME OVER).
- Shot hit test also halfway back along the step (no tunnelling).

### Rendering

- OSD 30 x 11 tiles (360 x 198), 1-bit glyph per cell (330 of 512 ids, identity map), band canvas `g_aucScPix` / `g_scCv` shared with Scope 1 (1 tile column x 6 rows); 2 bands per column of 6 + 5 rows (11 is prime; `s_ucBandRows` / `s_sBandH` per pass), the saver pump `AstPoll` runs between drawing steps as before.
- Scale-up: factor = 64 x `AWTO_AST_W` / `_PANEL_DH_WIDTH` = 6 (ratio 10.67), position from the panel constants as Scope 2; compile error unless the width fills the panel exactly and the height fits with equal bars. Gameplay constants stay in raster px (objects 17 % larger on screen than at 384 x 216).
- Per pass: cull objects against the 12 x 108 window (wrap-aware), skip lines wholly outside it (`osd_line` walks every pixel of a clipped line), draw, upload only tiles that hold ink or held ink at their last upload (per-pass occupancy byte). Empty passes cost ~1 ms: a main-loop pass runs on through empty columns until one drew something.
- Score / spare ships (top left) redraw only when they change or an object touches those passes (occupancy bit 6).
- Rotate 180: `AwtoOsdRotCell` + `AwtoScTile` (turns the tile, direct port stores) as the scopes (`docs/osd/rotation.md`); scale-up window start = OSD position (`AwtoOsdPlaceScaleUp`).
- Ship: 16 stored angles x quarter turns (generator bakes the flame at the hull's end point); size = vertex >> shift (rock 1 / 2 / 3, saucer 2 / 3, ship 3).
- Frames follow at once (no pause); one column per main pass, watchdog kicked per pass.

### Sound

- `snd.c` tracks 10..16 (`scripts/pacman_sound.py`): thrust (loop, background state 5), saucer (loop, state 6), fire, explosion small / medium / large, ship explosion. `AwtoPmSound` cmds 9..13, `AwtoPmSoundBg` 5 / 6.
- Priorities as Pac-Man (one generator, higher wins, lower dropped, looping background resumes): ship explosion 6, large 5, medium / small 4, fire 3, thrust 2, saucer 1.
- Only when the user mute is off (`GET_OSD_VOLUME_MUTE`); level = the user's volume (DVC gain). Without `-D _AWTO_AUDIO_TEST`: one sync E9 86 "sound unavailable" at draw, then silent.
- Sync rows: the logged-row table is full (254), so the saver's own E9 0x90..0x93 and the cmd line 0x8C have no rows (printed raw); row 86 text now names both savers.

### Integration

- `saver.c`: run id `AWTO_SAVER_ASTEROIDS` 7; setting 119 value 5 (`SAVER_MODE_RUN` maps it, 5 is also the flash run id). Alternate: Pac-Man -> Scope -> Scope 2 -> Asteroids.
- DDC/CI VCP 0xEB = 8 starts it (7 = Boot splash, 6 alert, 5 flash). Registry rows 119 (`Asteroids`, value 5) and 121 (`Asteroids=8`); schema CRC changed with the row 119 range (records are id-tagged: values kept).
- Test only on unit 3; nothing flashed yet.

## Numbers (our side, sim, 2026-11-18)

- XDATA free 1541 B -> 1173 B (default image): -368 B for state, 24 objects, per-pass occupancy (64 B) and function locals; audio image 1158 B.
- Code: bank 8 +5.8 KB, bank 11 +4.0 KB (incl. sound data), bank 1 +0.9 KB; the data and its readers are pinned to bank 8 (bank 13 has only ~3 KB left: message-table reserve). Shapes: 612 B (ROM) / 584 B (own) + 94 B offsets.
- Time (`scripts/asteroids_speed.py`): column pass mean 9.5 ms, p95 20, max 31; pass with the game step max 41 ms; 7.94 ticks/s (paced). Largest costs: `osd_line` / `cursor_plot` (~1/3), main-loop base (~15 %).
- Checks: `scripts/asteroids_sim.py` (frames + mp4 + wav), `scripts/saver_sim.py` (VCP 0xEB = 8 start / stop, Rotate 180 at the same game tick: mean difference 0.4 turned vs 3.1 unturned), `python scripts/fw_gates.py` ALL PASS.

## Colour and info overlay (Dan, 2026-11-19)
- All drawing is the diagnostic console's phosphor green: palette `AWTO_PAL_DIAG_TEXT` (index 1) = `AWTO_RGB_PHOSPHOR_GREEN` (0, 255, 65); background `AWTO_PAL_DIAG_BG` (index 3) = near black (2, 2, 6). Same indices the console uses (it sets its own when it opens); none other needed.
- Info overlay lower left (3 lines: input resolution + refresh, draw grid + scale-up, fps): `docs/saver-mode.md` "Info overlay". Glyphs: digits + x . F P S, 4 x 6 px (`gen_asteroids.py` shapes >> 1), drawn after the objects. Sim: `scripts/saver_sim.py` `asteroids_info_check` (green only, text in the lower-left box); picture `tmp/saver_sim/asteroids_run.png`.

## Open

- Hardware: nothing seen on a panel; sound not heard (generator pitch range 189..2000 Hz).
- Pace (D-SL5, 2026-11-18): game ticks run on a fixed-rate schedule, `AWTO_AST_TICK_MS` 126 ms = 7.94 ticks/s (the first version's measured 7.96 ticks/s; there was no named constant). Schedule `s_usTickAt += period` (never restarted from now), at most `AWTO_AST_MAX_CATCHUP` 4 ticks per frame, resync when still behind; a frame starts only when a tick is due (an unchanged frame is not redrawn); the first frame runs `AWTO_AST_TICKS` ticks. Frame rate = as fast as drawing allows (5.0 frames/s in the sim, 1 or 2 ticks per frame).
- Measured (`saver_loop_cost.py --case asteroids --window 62`, sim, fw time): 7.94 game ticks/s, 5.03 frames/s; before the pacing 10.23 ticks/s, 5.11 frames/s. `asteroids_speed.py` counts column-0 passes as frames: idle waits inflate it (7.94 steps/s over 30 s).
- Frames 0..2 of `saver_frames_md5.py` are md5-identical to the unpaced build (same game state at the same tick); later frames differ only by which ticks they land on.
- Game-over / attract text: none drawn.

## Panel fill (Dan 2026-11-18, option A approved): built

- Raster 360 x 198 px = 30 x 11 tiles at 64 / 6 = 10.67x: 3840 x 2112 of the 3840 x 2160 panel = 100 % x 97.8 % (24 px bars top and bottom, symmetric: Rotate 180 keeps the picture in place). Was 384 x 216 at 9.14x = 91.4 % x 91.4 %.
- Check: `saver_sim.py` "asteroids fills the panel" >= 97 % in each direction; sim 1080p60 render box 1920 x 1056 of 1920 x 1080 (100.0 % x 97.8 %), Rotate 180 box 1920 x 1056. 2160p60 input scales to the same panel (not rendered separately).
- Measured 2026-11-18 (sim, same pacing code, before -> after): column pass mean 8.5 -> 8.6 ms, p95 18 -> 20, max 28 -> 39 (`asteroids_speed.py`, 30 s); frames/s 5.36 -> 5.51 over 180 s (`saver_loop_cost.py --case asteroids`; 5.03 -> 4.76 over 62 s: game-state noise); ticks/s 7.94 / 7.93 unchanged; frame = 30 columns instead of 32. XDATA free 996 -> 997 B (default), audio 983 B.
- Other options (480 x 270 slot ring, 240 x 135) were not built: Option A fits the 512 glyph ids and the 8-10 ms pass budget.
