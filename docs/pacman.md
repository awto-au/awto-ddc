# Pac-Man on the scaler (OSD demo + sound)

Status 2026-11-18. Runs on unit 3 as a screensaver (`docs/screensaver.md`) and from test cmds. Tags: [hw] seen on unit 3, [sim] firmware simulator only, [spec] SDK source / regdb, [guess].

## What it is

- A recorded Pac-Man demo played on the OSD of the Realtek RL6449: 260 steps, drawn from font glyphs and a 28 x 36 tile map, scaled up to the panel by the OSD scale-up engine.
- No game logic in the firmware: the host script plays the game once, the firmware replays cell changes.
- Sound: the chip's HDMI audio test generator as tone source, pitch by audio PLL divider; events come from the same recording.

## Files

| file | role |
|---|---|
| `scripts/gen_pacman_classic.py` | game model + glyph / cell / delta generator -> `fw/test/pacman_classic_data.inc` |
| `fw/test/pacman_classic.c` | loader + step player (`AwtoPacmanClassic`) |
| `scripts/pacman_sound.py` | note tables -> `fw/test/snd_data.inc`, WAVs for listening |
| `fw/test/snd.c` | non-blocking note player (`AwtoPmSound`, `AwtoPmSoundPoll`) |
| `fw/test/saver.c` | screensaver manager (starts / stops Pac-Man, scopes) |
| `scripts/pacman_unit.py` | host stepper for a unit (test cmds over the debug link) |
| `scripts/pacman_sim.py`, `audio_sim.py` | sim video with sound, audio tap (`docs/pacman-sound.md`, `docs/sim.md`) |
| `tools/pacman_osd/` | the earlier host prototype (MIT emulator, not in the firmware) |

## Screen

- Map: 28 x 36 tiles, 12 x 18 glyphs, row height 12 (6 px of each glyph cut), maze = the classic 31 rows from tile row 3 (3 score rows above, 2 spare below).
- Glyphs (`gen_pacman_classic.py`): 1-bit walls (autotiled, double-line rule), dots, power pellet, text, Pac-Man frames and death frames 0..10; 2-bit ghosts (body, eye white, pupil), frightened, eyes, cherry.
- One char command per cell: 1-bit = `0x4C | id bit 8 << 5`, id, `fg << 4 | bg`; 2-bit = type `0x80` + four colours packed over B0 / B2 (see `osd_model.py` `decode_char`). Palette 12 entries.
- SRAM: row commands from 0, end word, char commands from `AWTO_PC_FS_BASE`, glyph words from `AWTO_PC_FONT_BASE`; 2-bit glyphs at 18 words x (2-bit offset + id), MSB plane first.
- Scale-up: ratio 64 / `AWTO_PC_SU_FACTOR` (13 -> 4.9): 432 lines -> 2126 of 2160; the scale-up window start = the OSD position (`docs/osd-rotation.md`). Position `g_usAwtoPcPosH` (WORD, hd units of 4 panel px) / `g_usAwtoPcPosV`.
- Rotation: display Rotate 180 does not turn the OSD; the loader turns map and glyphs itself (`docs/osd-rotation.md`).

## How a frame is made

- Draw (test cmd 0xB7 / saver start): `AwtoOsdTestReset`, palette, row commands, maze cells (`PcMaze`), glyph stream (`PcGlyph`), map base, scale-up, `osd_tc_show(1)`.
- Step (0xB8, one per 31 ms in the saver = 4 sub-steps per 125 ms game step): `PcStep(n)` applies the cell deltas of sub-step n: `g_pcIdx` gives start / end offsets, `g_pcDeltaA` / `g_pcDeltaB` hold 3-byte records (`delta_rec` in the generator: cell index 10 bits, 1-bit / 2-bit kind, glyph id 9 bits, colour or style index; 2-bit styles from `g_pcStyle`). After sub-step 1040 the maze is redrawn from the start.
- Off (0xB9): close the OSD, scale-up off, stop the sound.
- The game (`Demo` in the generator): READY!, play, power pellets (frightened ghosts, eaten ghosts), fruit at 70 / 170 pellets eaten, death animation + lives, GAME OVER.
- Not done: smooth sub-tile motion, bigger sprites, score popups, steering.

## Sub-tile motion (2026-11-18)

- The OSD has tiles, no sprites: Pac-Man, the 4 ghosts, the lives icons and the fruit are cut into 12 x 12 glyph pieces. A sprite at pixel position (px, py) overlaps up to 4 tiles; each tile shows the piece of the sprite inside it (`overlay`).
- Each game step = `SUB` 4 sub-steps; a sprite moves 3 px per sub-step (`STEP_PX`), so a tile move takes 4 sub-steps. Teleports (ghost reset, eyes into the pen) are not interpolated.
- Pieces are deduplicated by content as the game plays: 106 1-bit glyphs (max 512), 73 2-bit glyphs (max 256). Piece colour = per-cell colour: pieces carry no dot / wall of the tile under them (a sprite covers its tiles).
- Mouth cycles per sub-step (`MOUTH`), ghost feet every 2 sub-steps. Where two sprites share a tile, the later one (ghost over Pac-Man) wins the whole tile.
- Sound events: one per game step, fired at its first sub-step (`g_pcEvt` is per game step, index `step >> AWTO_PC_SUB_SHIFT`); the background state is applied every sub-step.
- Data (2026-11-18): glyphs 6804 B, delta records 24702 B (8234 records), index 2082 B, cells 3024 B; before: 3348 + 14395 + 522 + 3024. Delta split: bank 11 7200 B (its old slot; a larger const in bank 11 covers the scope S2 strings' addresses and fails the `link` gate), rest in bank 12.
- Check render: `python scripts/gen_pacman_classic.py --strip OUT.png --frame N --count 8` (same window, consecutive sub-frames); `--png OUT.png --frame N` for a whole screen.
- Speed (sim, `python scripts/pacman_speed.py BIN`, 2026-11-18, dw8051 model): firmware time from the end of the cmd write to the step counter change, 1 ms resolution: before 4.7 ms mean (8 ms max) per game step, after 4.4 ms mean (7 ms max) per sub-step (min 2 ms = main loop pickup). Sub-steps are as cheap as the old whole steps: mean 7.9, max 19 records per sub-step (3 data port bytes each). The saver pace is 31 ms per sub-step (32 / s); the sim measures ~230 steps / s incl. the pickup pass (this tracks the sim loop pass, not hardware: a hardware figure is not measured).
- Not smooth: the dots and power pellets blink / vanish per game step; ghost-eaten and death animations run at game-step speed (frames repeat for 4 sub-steps); the pen exit teleports.

## Firmware constraints that shaped it

- Data and its reader share a code bank: `#pragma place bank(N)` pins only the next definition; arrays sit in banks 11 / 12 (~24 KB) with leaf reader functions (`PcCell`, `PcGlyph`, ...). Bank 13 is nearly full.
- Watchdog bites after 586 ms: long loops kick `CLR_WDT` (`PC_KICK`, every 128 data port bytes).
- No magic numbers (`scripts/magic_lint.py`): colours, timings, ids are named.
- XDATA floor 700 B: the player keeps a handful of bytes (`s_usStep`); free 701 B before, 703 B after the sub-tile change.
- Sync log lines: E9 0x73 drawn, 0x74 step (value = step), 0x75 off.

## Audio

### Signal path

- Tone source: the HDMI audio block's test generator (`AFCR.audio_test_enable`, a sine "to IIS / SPDIF") [spec]. It needs no incoming audio stream.
- The generator has no frequency register: the tone is the sample rate divided by the sine's sample count (32 or 64, `AFCR.tst_i2s_sw`) [spec]. Pitch is set by the audio PLL divider.
- Chain: generator -> audio PLL -> DVC (digital volume, VCP 0x62) -> DAC -> analogue out -> speaker amp [spec, `docs/audio.md`].
- Amp pins: P7.4 `bAMP_EN` (1 = on), P7.3 `bAMP_MUTE` (1 = muted), owned by `fw/audio/amp.c` (`AwtoAudioAmp`).
- The SDK handler (`SysAudioHandler`) returns early while the generator is on, so no re-mute and no sample-rate detect. That is why the build needs `-D _AWTO_AUDIO_TEST` (also defines `_INTERNAL_AUDIO_TEST_SUPPORT`). Making it permanent: #229.
- The generator runs on the current input's HDMI block: D2 (page 71) or D3 (page 72); D1 (DP) has none. Unit 3 on HDMI-A-2 = D2.

### Pitch

- `SCAPR` (idx 18) = `0x80 | sc` (S1 divide by 2, as the SDK 48 kHz code 0xA0); latch with `CMCR.dbdcb` (idx 16, bit 4).
- Model: f = K / sc (octave flag clear: K / 2 / sc), K = 48000 Hz by default [guess]; sc 32 = 48 kHz sample rate = 1500 Hz tone.
- sc range 24..127 keeps the DAC clock divider at its 48 kHz setting (fs <= 64 kHz) [spec]. Tones 378..2000 Hz, 189..1000 Hz with the octave flag.
- Calibration: test cmd 0xBD plays sc 32 (expect 1500 Hz); measure with a tuner, regenerate with `pacman_sound.py --k-hz <measured x 32>`. Not done yet.

### Data and player

- `pacman_sound.py` encodes note names to pairs `{sc | 0x80 octave flag, ticks}`; tick = 10 ms, sc 0 = rest, 0 ticks = end of track. Ten tracks (list: `TRACKS`; ids in `snd.c` follow its order); one rest tick between notes of a melody.
- `AwtoPmSoundPoll` runs each main-loop pass: on the note schedule (`s_usPsAt += s_usPsDur`, no drift) it calls `PsNote` for the next pair.
- `PsNote`: rest = mute the amp pin; note = gate the amp, write AFCR (octave flag), SCAPR, CMCR latch, schedule the amp to open 4 ms later (`AWTO_PS_GAP_MS`, by ear: the pitch change clicked with the amp open, Dan 2026-11-18). The poll opens it.
- `PsStart`: generator on (`SysAudioInternalGenTestProc(_ON)`), `SysAudioMuteProc(_OFF)`, then `AwtoAudioAmp(_OFF)` directly (the SDK call is a no-op once the generator has cleared the DVC mute flag, so P7.4 would stay 0).
- `PsStop`: generator off, gate cleared.
- Order: the Pac-Man draw calls `OsdFuncDisableOsd`, which switches the generator off, so a sound started before a draw is lost: the demo draws first, then sound events.

### Game events

- `g_pcEvt[step]`: low nibble = one sound event (`EV_INTRO`, `EV_WAKA_ON`, `EV_WAKA_OFF`, `EV_DEATH`, `EV_STOP`, `EV_GHOST`, `EV_FRUIT`), high nibble = background state of that step (0 none, 1..3 siren speed, 4 frightened).
- Siren speed from pellets left: > 2/3 speed 1, <= 2/3 speed 2, <= 1/3 speed 3. Frightened while any ghost is blue. Background 0 in ready / dying / game over.
- `AwtoPacmanClassic(2)` dispatches after the cell update: event -> `AwtoPmSound` (intro 0, waka 1, death 2, stop 4, ghost 6, fruit 7, waka off 8), background -> `AwtoPmSoundBg` (acts on a change).
- Test cmds: 0xBA intro, 0xBB waka, 0xBC death, 0xBD calibration tone, 0xBE stop. Sync E9 0x80..0x8B.

### Sounds and priorities

- One tone generator: sounds cannot overlap. A new sound plays only if its priority >= the playing one's; else it is dropped. Table: `pacman_sound.py` `PRIORITY` (emitted as `PsPrio`).

| sound | priority | pitch plan (K = 48000, [guess]) | loops |
|---|---|---|---|
| intro, alert, calibration | 7 | jingle / bip-bip-beep / 1500 Hz | no |
| ghost eaten | 6 | rising sweep 300 -> 1800 Hz, 16 steps x 18 ms | no |
| death | 5 | falling glissando 1000 -> 380 Hz | no |
| fruit eaten | 4 | falling sweep 1600 -> 580 Hz, rest, blip 660 / 880 / 1320 Hz | no |
| waka | 3 | 392..784 Hz up / down, 28 ms steps | while eating |
| frightened | 2 | rising saw 400 -> 1000 Hz, 6 x 20 ms | yes |
| siren 1 / 2 / 3 | 1 | wail 520 -> 780 -> 520 Hz, 8 steps each way, 40 / 30 / 20 ms per step (640 / 480 / 320 ms cycle) | yes |

- Resume: waka and the background state are "wanted" state in `s_ucPsFlags` (one byte: boot, amp gate, waka, background in bits 7:4). When a sound ends (or waka off) `PsResume` starts waka if eating, else the background sound, else silence.
- Any non-waka sound clears the waka flag (the generator re-sends `EV_WAKA_ON` at the next pellet). Stop clears everything.
- A background change replaces the playing sound only if that is silence or a background sound; a higher sound picks the new state up at its end.
- Not done: extra-life jingle (arcade: at 10000 points; the demo score never gets there), the arcade's 5 siren speeds (3 used), eyes-returning sound (ghost eyes running home).
- Sim 2026-11-18 (`pacman_sim.py --game --steps 260`): ghost at step 63, fruit at 122, siren 1 -> 2 at step 158, frightened 57..82; the demo Pac-Man now chases frightened ghosts and the fruit (`CHASE_DIST`, fruit stays 40 steps) so these events happen in the recording.

### Hardware status

- [hw] Dan heard the sound on unit 3 on 2026-11-18: good, clicky at the change of sounds (before the 4 ms amp gate; gate not yet re-listened).
- [guess] K = 48000, period 32 vs 64 samples, PLL relock time, sine level through the amp (known low-frequency distortion, `docs/audio.md`).
- Volume = the user volume (VCP 0x62, 10 % on unit 3 at the last check).
- The sim models no audio hardware; `audio_sim.py` records the register writes and synthesises a WAV from a guessed model (`docs/pacman-sound.md`).

## Run

- Build: `./dev.py build --tree . --serial AWT26110003 --tag pc -D _AWTO_AUDIO_TEST`, gates `python scripts/fw_gates.py tmp/fw/AWT26110003-pc-be`.
- Unit 3: `./dev.py flash --unit 3 tmp/fw/AWT26110003-pc-be.bin`; start `ddcutil --bus 11 setvcp EB 2`, stop `setvcp EB 0` (`docs/screensaver.md`); or test cmds 0xB7 / 0xB8 / 0xB9 (`scripts/pacman_unit.py`).
- Sim: `python scripts/pacman_sim.py --game --steps 1040 --fps 32` -> `tmp/pacman_sim/pacman.mp4`; `python scripts/saver_sim.py` for the DDC start / stop check.

## Open

- [hw] Photo 2026-11-18: maze scaled to full height but not across the width, and upside down. Cause: scale-up window start 0 (the window is in display coordinates) and the OSD not turned with the display. Fixed in code, unit check pending.
- Audio: permanent build + key-click tone (#229); K calibration; amp gate length by ear.
- Panel boot constants named (diag stages, boot probe ids): not done.
