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
| `scripts/pacman_sound.py` | note tables -> `fw/test/pacman_sound_data.inc`, WAVs for listening |
| `fw/test/pacman_sound.c` | non-blocking note player (`AwtoPmSound`, `AwtoPmSoundPoll`) |
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
- Step (0xB8, one per 125 ms in the saver): `PcStep(n)` applies the cell deltas of step n: `g_pcIdx` gives start / end offsets, `g_pcDeltaA` / `g_pcDeltaB` hold 5-byte records (cell index lo, hi, B0, B1, B2). After step 260 the maze is redrawn from the start.
- Off (0xB9): close the OSD, scale-up off, stop the sound.
- The game (`Demo` in the generator): READY!, play, power pellets (frightened ghosts, eaten ghosts), fruit at 70 / 170 pellets eaten, death animation + lives, GAME OVER.
- Not done: smooth sub-tile motion, bigger sprites, score popups, siren, steering.

## Firmware constraints that shaped it

- Data and its reader share a code bank: `#pragma place bank(N)` pins only the next definition; arrays sit in banks 11 / 12 (~24 KB) with leaf reader functions (`PcCell`, `PcGlyph`, ...). Bank 13 is nearly full.
- Watchdog bites after 586 ms: long loops kick `CLR_WDT` (`PC_KICK`, every 128 data port bytes).
- No magic numbers (`scripts/magic_lint.py`): colours, timings, ids are named.
- XDATA floor 700 B: the player keeps a handful of bytes (`s_usStep`).
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

- `pacman_sound.py` encodes note names to pairs `{sc | 0x80 octave flag, ticks}`; tick = 10 ms, sc 0 = rest, 0 ticks = end of track. Three tracks: intro (once), waka (loops), death (once); one rest tick between notes of a melody.
- `AwtoPmSoundPoll` runs each main-loop pass: on the note schedule (`s_usPsAt += s_usPsDur`, no drift) it calls `PsNote` for the next pair.
- `PsNote`: rest = mute the amp pin; note = gate the amp, write AFCR (octave flag), SCAPR, CMCR latch, schedule the amp to open 4 ms later (`AWTO_PS_GAP_MS`, by ear: the pitch change clicked with the amp open, Dan 2026-11-18). The poll opens it.
- `PsStart`: generator on (`SysAudioInternalGenTestProc(_ON)`), `SysAudioMuteProc(_OFF)`, then `AwtoAudioAmp(_OFF)` directly (the SDK call is a no-op once the generator has cleared the DVC mute flag, so P7.4 would stay 0).
- `PsStop`: generator off, gate cleared.
- Order: the Pac-Man draw calls `OsdFuncDisableOsd`, which switches the generator off, so a sound started before a draw is lost: the demo draws first, then sound events.

### Game events

- The generator emits one event per step where something happens (`EV_INTRO`, `EV_WAKA_ON`, `EV_WAKA_OFF`, `EV_DEATH`, `EV_STOP`): `g_pcEvt[step]`.
- `AwtoPacmanClassic(2)` dispatches them to `AwtoPmSound` (intro / waka / death / stop) after the cell update.
- Test cmds: 0xBA intro, 0xBB waka, 0xBC death, 0xBD calibration tone, 0xBE stop. Sync E9 0x80..0x86.

### Hardware status

- [hw] Dan heard the sound on unit 3 on 2026-11-18: good, clicky at the change of sounds (before the 4 ms amp gate; gate not yet re-listened).
- [guess] K = 48000, period 32 vs 64 samples, PLL relock time, sine level through the amp (known low-frequency distortion, `docs/audio.md`).
- Volume = the user volume (VCP 0x62, 10 % on unit 3 at the last check).
- The sim models no audio hardware; `audio_sim.py` records the register writes and synthesises a WAV from a guessed model (`docs/pacman-sound.md`).

## Run

- Build: `./dev.py build --tree . --serial AWT26110003 --tag pc -D _AWTO_AUDIO_TEST`, gates `python scripts/fw_gates.py tmp/fw/AWT26110003-pc-be`.
- Unit 3: `./dev.py flash --unit 3 tmp/fw/AWT26110003-pc-be.bin`; start `ddcutil --bus 11 setvcp EB 2`, stop `setvcp EB 0` (`docs/screensaver.md`); or test cmds 0xB7 / 0xB8 / 0xB9 (`scripts/pacman_unit.py`).
- Sim: `python scripts/pacman_sim.py --game --steps 260` -> `tmp/pacman_sim/pacman.mp4`; `python scripts/saver_sim.py` for the DDC start / stop check.

## Open

- [hw] Photo 2026-11-18: maze scaled to full height but not across the width, and upside down. Cause: scale-up window start 0 (the window is in display coordinates) and the OSD not turned with the display. Fixed in code, unit check pending.
- Audio: permanent build + key-click tone (#229); K calibration; amp gate length by ear.
- Panel boot constants named (diag stages, boot probe ids): not done.
