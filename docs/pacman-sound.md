# Pac-Man sound (speaker path, no input audio)

Overview of the whole Pac-Man demo and how the audio works: `docs/pacman.md`. Hardware status 2026-11-18: Dan heard the sound on unit 3 (good; clicky at pitch changes, amp gate added).

Tags: [spec] = SDK source / regdb (`re/regdb/RTD2795T-CG.tsv.gz`); [derived] = arithmetic on [spec]; [guess]; [hw] = measured on a unit. The sections below were written before the first unit listening test; see `docs/pacman.md` for current status.

## Sources the chip can produce without an audio stream
| Source | Registers (regdb) | Verdict |
|---|---|---|
| HDMI audio test generator "sine wave to IIS/SPDIF" | `AFCR.audio_test_enable` (`PORT_PAGE71_HDMI_AFCR` bit 4, data port `P71_HDMI_AP` idx 3; D3 = page 72) | USABLE: SDK path `SysAudioInternalGenTestProc` (always compiled, #229; VCP 0x63 sine only with `--audio-test`) [spec] |
| DAC / ADC / I2S loopback | none in regdb (06E7 `AD_I2S_CTRL` is the ADC I2S, line-in off on this board) | no generator [spec] |
| `AUD_TEST_PIN` 06E8 | test pin mux (pcm, dvc, dac nodes) | observation only, no source [spec] |
| DVC / DAC mute regs | 08A0.., 06D1 | gain only |
- Generator has no frequency register: pitch is fixed per sample rate. Sample rate = HDMI audio PLL; test mode freezes tuning (`DPCR2.reg_dpll_stop` = 0) and loads S / D codes from SDK constants (S 0xA0, D 0xD847 for 48 kHz) [spec].
- SDK generator-on writes: `AFCR` = 0x10 (FIFO off, generator on), `SCAPR` S code, `DCAPR0/1` D code, `AUDIO_FREQDET` auto off (bits 7:6), `CMCR.dbdcb` latch (bit 4), then `ScalerAudioDigitalOutputMute(_OFF)` [spec]. Rate reported as 48 kHz while on (DAC clock `DA_CLK_CTRL` untouched).
- The SDK handler returns early while the generator is on (`SysAudioHandler`): no re-mute, no rate detect. `_INTERNAL_AUDIO_TEST_SUPPORT` is always `_ON`, no build flag (#229).
- Generator runs on the current input port's HDMI block: D2 or D3 only (D1 DP: no generator in SDK). Unit 3 on HDMI-A-2 = D2 [spec].
- Output path after the generator: audio PLL -> DVC (gain) -> DAC -> aout 116/117 -> PAM8006A amp. Amp pins: P7.4 `bAMP_EN` (1 = on), P7.3 `bAMP_MUTE` (1 = muted), `fw/audio/audio.c`, `docs/audio.md` [hw: amp matrix, Dan's ears 2026-11-13]. `SysAudioMuteProc(_OFF)` turns both on.

## Pitch control (what we use)
- Tone = fs / N: sine of N samples per period (`AFCR.tst_i2s_sw`: 1 = counter `test_cnt[4:0]` = 32 values, 0 = `test_cnt[5:1]`; which gives which period is [guess]).
- fs = K / S: SDK constants S 0xA0 (48 kHz) and 0xB0 (32 kHz), same D 0xD847: ratio 3 : 2 = 48 : 32 [derived]. `SCAPR` = slc(7) | sc(6:0); write sc, latch with `CMCR.dbdcb` (takes effect after the current audio PLL cycle [spec]).
- Model: f = K_HZ / sc (tst_i2s_sw = 1), K_HZ / 2 / sc (= 0). Default K_HZ = 48000 (sc 32 = 48 kHz, 32 samples/period): [guess].
- sc range 24..127: fs <= 64 kHz keeps `DA_CLK_CTRL[7:6]` at the 48 kHz setting [spec: `ScalerAudioD2SamplingFreqDetect` switches at 64 kHz]. Tones 378..2000 Hz, 189..1000 Hz with the octave flag; melody needs 440..1100 Hz.
- Calibration: test cmd 0xBD plays sc 32 (expect K/32 = 1500 Hz); measure with a phone tuner, regenerate with `pacman_sound.py --k-hz <f*32>`.
- Rests: `bAMP_MUTE` = 1 (instant). Not DVC mute (ramp blocks up to 400 ms).
- Risks [guess]: audio PLL relock per note may click / drop out; D code untouched so a lock loss is possible at the extremes; the generator is a sine, not a square.

## Build / run (scripts, firmware)
- `scripts/pacman_sound.py`: note tables -> `fw/audio/snd_data.inc` (pairs `{sc | 0x80 octave, 10 ms ticks}`, 0 = rest, 0 ticks = end) + `tmp/pacman_sound/{intro,waka,death}.wav` (square by default, `--wave sine` = what the chip plays). Test: `tests/test_pacman_sound.py`.
- `fw/audio/audio.c` (amp pins + ear tests + player, one owner since #229): non-blocking player (`AwtoPmSoundPoll` each main pass, schedule on `AwtoMs`). Test cmds `AWTO_TC_PACMAN_SND` 0xBA intro, 0xBB waka (loops), 0xBC death, 0xBD calibration tone, 0xBE stop. Sync log E9 80..86. Every build. While a host audio stream plays the cmds are skipped (sync E9 86); mute: callers check (Asteroids) / amp stays user-controlled.
- The player half of `audio.c` is the one sound module (Pac-Man, Asteroids, alert, key click, calibration); function names keep `AwtoPmSound*`. `snd_data.inc` holds, after the note data, a track table (offset, priority, loops per track) and a cmd table (track, sync event, event value = cmd per `AwtoPmSound` cmd); both generated from `TRACKS` / `PRIORITY` / `CMDS` in `pacman_sound.py`. A cmd = one table row, no if chain.
- Extra tracks (2026-11-18): ghost-eat sweep, fruit, siren x 3 speeds (loop), frightened (loop); priorities and resume rules in `docs/pacman.md` "Sounds and priorities". Player entry points: `AwtoPmSound(cmd)` (6 ghost, 7 fruit, 8 waka off), `AwtoPmSoundBg(state)`. Sync log E9 88 ghost, 89 fruit, 8A background state (value), 8B waka off. Lookup functions `PsOff` / `PsPrio` / `PsLoops` are generated into the data include.
- Spectrum check without listening: `pacman_sound.py --wave sine`, 40 ms FFT windows of `tmp/pacman_sound/*.wav`: ghost 320 -> 1405 Hz rising, fruit 1510 -> 616 Hz then 657 -> 1332, siren1 522 -> 775 -> 557 Hz, fright 514 / 754 Hz (chip Hz after sc quantisation; not heard on a unit).
- Build: `./dev.py build --tree . --serial AWT26110003 --tag snd1`, gates `python scripts/fw_gates.py tmp/fw/AWT26110003-snd1-be`.
- Simulator (`scripts/fw_sim.py`) models no audio hardware (`docs/audio.md`): the gates prove build, link and boot only.

## Unverified
- Generator works on this unit with D2 live video and no host audio stream.
- Period (32 vs 64 samples), K_HZ, sc-to-pitch scaling, PLL relock behaviour.
- Whether the amp passes the generator level cleanly (known low-frequency distortion, `docs/audio.md`); DVC gain is whatever the user volume sets.

## Simulator video with sound (no hardware)
- Run: `./dev.py build --tree . --serial AWT26110003 --tag simav`, then `python scripts/pacman_sim.py [--steps N] [--out DIR] [--k-hz HZ]` (defaults: 120 steps, `tmp/pacman_sim`). Output: `pacman.mp4` (H.264 yuv420p + AAC, 8 fps, 1920x1080), `pacman.wav`, `frames/`, `events.tsv`. Log `tmp/logs/pacman_sim.log`. Test: `tests/test_audio_sim.py`.
- Sequence: 0xB7 maze, 0xBA intro, 0xBB waka from the end of the intro, one 0xB8 per frame (1/8 s firmware time), 0xBE stop. Video frame k = OSD state at T0 + k / 8; the WAV spans the same clock.
- Order matters: `OsdFuncDisableOsd` (inside the 0xB7 draw) calls `SysAudioInternalGenTestProc(_OFF)`: 0xB7 after 0xBA silences the intro (player keeps writing, generator off) [spec, seen in the sim]. Applies to the unit too.
- Modelled (`scripts/audio_sim.py`, device `AudioTap`): writes to the HDMI audio block data port (D2 `0x71C9` / D3 `0x72C9`: AFCR idx 3, CMCR idx 16, SCAPR idx 18) and the amp pins (P7.4 `0xFE1C`, P7.3 `0xFE1B`), stamped with the firmware Timer2 clock; the index write preloads the data cell (shadow per index, regdb reset values) so the SDK read-modify-writes work. Addresses numeric from `re/regdb/RTD2795T-CG.tsv.gz`.
- Synthesis: generator on (AFCR bit 4) and amp not muted and latched sc > 0: sine at K / sc (AFCR bit 7 = 1) or K / 2 / sc (= 0), phase continuous; else silence. K = `pacman_sound.PS_K_DEFAULT_HZ`, `--k-hz` overrides.
- Guessed (`MODEL` dict in `audio_sim.py`): K, pitch change at the CMCR.dbdcb write (no PLL relock delay, no click), sine level 0.3, no DVC gain / DAC / amp response, SCAPR slc ignored, P7.4 assumed 1.
- P7.4 assumption: the sim has no audio stream, so the SDK never reaches playback and `SysAudioMuteProc(_OFF)` is a no-op (`SysAudioInternalGenTestProc(_ON)` already clears the DVC mute flag): P7.4 stays 0 in the sim. On the unit it is 1 only if normal playback unmuted earlier [unverified].
- Not modelled: the real generator's period / PLL behaviour (see Unverified above); the video shows the OSD model's render, not the panel.

## Other users of the generator

- `AwtoPmSoundTone(sc, ms)`: one held tone (calibration track), refused while a sound plays. Key click: `docs/keys.md` "Key click" (#229).

## Timing (2026-11-18, Asteroids "sounds are broken up" on unit 3)

- Cause 1: `AwtoPmSoundPoll` ran once per main-loop pass. Asteroids passes are 8-41 ms, notes 8-30 ms. The 4 ms amp gate (`AWTO_PS_GAP_MS`) opened only at the next poll: muted 11 ms median, 34 ms worst per note (thrust notes are 30 ms: about 40 % silence). Note starts were up to a pass late.
- Cause 2: `PsStart` cycled the generator off and on (`PsStop`, `SysAudioInternalGenTestProc`, `SysAudioMuteProc`, `AwtoAudioAmp`) for every new sound, including each fire during thrust and each resume.
- Fix: `PsStart` leaves a running generator alone (full set-up only from silence); Asteroids calls `AwtoPmSoundPoll` between drawing steps (per shape vertex, object, tile upload, game tick, collision candidate: `AstPoll`, audio build only). Pac-Man / alert / key click / calibration unchanged.
- Measure: `python scripts/snd_timing.py BIN --saver asteroids|pacman --seconds 60` (audio build, sim audio tap + poll hook; exit 1 = FAIL). Evidence of the pass over 40 s:

| Asteroids (sim) | before | after |
|---|---|---|
| gate latch -> amp open, median / p95 / max | 11 / 21 / 34 ms | 4 / 7 / 8 ms |
| poll gap median / p99 | 12 / 31 ms | 0 / 2 ms |
| latches with an unchanged pitch (generator restarts) | 93 | 11 |
| Pac-Man gate median / max | 5 / 9 ms | 5 / 8 ms (unchanged) |

- Rare long gaps (an NV write, 21 ms) are not polled around.
- By ear on unit 3: audio build, start Asteroids (screensaver now), thrust loop (autopilot) must hum continuously with a steady 4-note wobble, a shot during thrust must not cut it to silence or restart the loop audibly.
