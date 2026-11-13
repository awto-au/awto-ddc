# Analog audio output (awto-ddc#93)

Tags (#91): [fw, unverified] = seen in the Dahua firmware (not a reference for audio, see "Rule" below) (decompile `~/vendors/realtek/analysis/jxc-4k/bank3`, or its sim trace `tmp/logs/trace_vendor_{2160p60,1080p60}.tsv.gz` = ordered register writes with values); [spec] = Realtek SDK source / register DB (`regdb/RTD2785TM-CG.tsv`); [hw] = measured on a unit; [guess]; [?] unknown.
Status (2026-11-13): aout 116/117 feeds the speaker amp, P7.3 = AMP_MUTE (high = muted) [hw: unit 3 output matrix, Dan's ears]; hpout unused. DAC + amp pins run, HDMI D2 audio plays through the DVC (register readback below); audible result: Dan's ears (#94), ear test `./dev.py sound-test` (below).

## Summary
- Our firmware compiled the Realtek SDK audio out (`_AUDIO_SUPPORT _OFF`, "no audio jacks", 2026-11-04). The Dahua firmware runs the SDK audio path into the embedded DAC. [fw, unverified]
- Now: `_AUDIO_SUPPORT _ON`, `_EMBEDDED_DAC_SUPPORT _ON`, `_DAC_SPEAKER_OUTPUT_SWAP _ON` (RL6449_Project.h). The SDK `SysAudio` state machine + `UserInterface*Audio*` hooks do the sequencing; we supply volume, mute and the hold.
- Source = digital (HDMI D2/D3, DP D1) -> audio PLL -> DVC (digital volume) -> DAC -> pins. Not a line-in monitor: see "audio_source".
- Volume = DVC gain (P8_A5/A6), exactly like the Dahua firmware. DAC gain `DA_GAIN_L/R` stays 0 dB (0x57). [fw, unverified]

## Pins, jack
- Output: `UserInterfaceGetAudioDACOutput` = `AWTO_AUDIO_OUT_DEFAULT` = SPEAKER = aout 116/117 AUDIO_SOUTL/R, the amp feed [hw: unit 3 matrix; Dahua dumps of units 1 and 3: 06C0 = EF aout only], read once at DAC start (`_AUDIO_DAC_CHARGE`). `_DAC_HP_OUTPUT_SUPPORT _OFF` (hpout 109/110 alone was silent on unit 3). 115 AUDIO_REF.
- Stock SDK: `SysAudioAnalogAudioHandler` compares the 06C0 power bits with `UserInterfaceGetAudioDACOutput()` every pass and on a mismatch mutes, re-charges and switches back; that undid the 06C0 = FB / 06C6 = 08 pokes (back to DB / C8 within seconds). Ours: `_DAC_OUTPUT_SWITCH_SUPPORT _OFF` (no jack switching); the input-port-changed mute stays. Chip pins: RL6449 LQFP216, `docs/monitors/pinshare-live-AWT26110003.tsv`; all in audio mode (0x03). [hw]
- Dahua firmware picks the output from P4.5 (pin 113, jack input, `1:f69b`): low -> SPEAKER, high -> HEADPHONE [fw, unverified]. Its register dumps of units 1 and 3 both show aout only; GPIO dumps read P4.5 = 0 (unit 1) and 1 (unit 3, another capture); the sim trace (06C0 = DF, HP only) is the P4.5-high path. Polarity [?].
- Speakers: confirmed present by Dan (2026-11-13; earlier 'no speakers', #3/#22, was wrong).
- Amp pins (one owner `fw/sdcc/awto_audio.inc`, `docs/reversing/dahua-fw/gpio-ir.md` s4): P7.4 (pin 161) amp enable = !mute (Dahua `1:ea99`) [fw, unverified]; P7.3 (pin 160) `bAMP_MUTE` = mute, high = muted [hw: unit 3 matrix steps 4 / 6 silent]. Both from `PCB_AMP_MUTE` (`SysAudioMuteProc`); AC on: P7.4 = 0, P7.3 = 1. Dahua instead writes P7.3 = 0 once, 200 ms after AC on, and never again [fw, unverified]. Ring lines `E5` (sync.tsv): amp on / off. P7.4 off = silent [hw: unit 3 amp1 step 2, Dan 2026-11-13] -> P7.4 = amp enable, high = on.
- Amp IC: **PAM8006A** (stereo class-D, DC volume control) next to speaker header CN4 [photo, [boards.md](monitors/boards.md)].
- The SDK demo board uses P3.5 (pin 91) as AMP_MUTE; our pin 91 is DPTX_AUX_P (P3D5 output, live 0x01). Not the same function. [hw]

## Option set (SDK `RL6449_Project.h` names) and what the Dahua firmware uses
| Option | Dahua firmware | Ours | Evidence |
|---|---|---|---|
| `_AUDIO_SUPPORT` | on | on | audio code present [fw, unverified] |
| `_EMBEDDED_DAC_SUPPORT` | on | on | `ScalerAudioDACInitial` 3:f39f [fw, unverified] |
| `_DAC_SPEAKER_OUTPUT_SUPPORT` | on | on (SDK default) | REG_DAC_POWER0 bit 5 [fw, unverified] |
| `_DAC_OUTPUT_SWITCH_SUPPORT` (awto, RL6449_Project_Default.h default on) | on (P4.5 jack switching) | **off** | per-pass output compare / switch in SysAudio.c; ours: output fixed at DAC start (#94) |
| `_DAC_HP_OUTPUT_SUPPORT` | on | **off** | hpout alone silent on unit 3; Dahua runs aout only (06C0 = EF) |
| `_DAC_SPEAKER_OUTPUT_SWAP` | on | **off** (SDK default) | `_ON` writes 06E0 = 0x50 = aout_l and aout_r both from DAC_R (regdb 06E0 fields): left channel lost, not a swap (a swap is 0x40). Bug, see below [spec] [hw] |
| `UserInterfaceGetAudioDACOutput()` | P4.5: speaker or headphone | `AWTO_AUDIO_OUT_DEFAULT` = SPEAKER (aout) | Dahua trace 06C0 = DF = headphone (P4.5 high in the sim) [fw, unverified]; ours was 06C0 = FB (both, unit 2) [hw] |
| `_DAC_DITHER_FUNCTION_LEVEL` | off | default off | DA_CTRL = 0x40 [fw, unverified] |
| `_DIGITAL_DAC_AOUT/HPOUT_GAIN_DB`, `_LINE_IN_DAC_*_GAIN_DB` | 0 dB | default 0 dB | REG_OUT_GAIN = 0x00 twice [fw, unverified] |
| `_LINE_IN_SUPPORT` | on (ADC init runs at boot) | **off** | ADC init writes P6_B0..B7 in the trace [fw, unverified]; line-in pins are GPIO on this board [hw] |
| `_SLEEP_AUDIO_SUPPORT` | ? | off | no stand-alone audio; L1-L3 must be silent |
| `_DVC_ADJUST_TYPE` | dB gain mode | default `_DB_GAIN` | P8_A0 = 0x8F, VA 0x0001 [fw, unverified] |
- `PCB_AMP_MUTE` lives in `fw/sdk`; the rest are SDK defaults.

## Rule: SDK defaults first, the Dahua firmware is no audio reference (Dan, 2026-11-13)
- Dan: the Dahua firmware audio "was always broken". Every [fw, unverified] value here is a data point, not a target; options stay at the SDK default unless a unit test [hw] shows a reason.
- Case: `_DAC_SPEAKER_OUTPUT_SWAP _ON` was copied from the Dahua 06E0 = 0x50. The SDK swap branch (`ScalerAudio.c` `ScalerAudioDACInitial`, `_BIT6 | _BIT4`) writes 0x50 = aout_l = DAC_R, aout_r = DAC_R (regdb `reg_mux_aout_l` 7:6 / `reg_mux_aout_r` 5:4: 00 DAC_L, 01 DAC_R): both speakers play the right channel. A real swap is 0x40. The SDK swap branch is wrong as written; we keep `_OFF` (06E0 = 00, straight). Unit 3 runs 06E0 = 00 since a live poke at 14:55:26 and in the amp2 build.

## Register sequence (Dahua firmware, 2160p60 sim, boot to ACTIVE) [fw, unverified]
All values are the trace of `trace_vendor_2160p60.tsv.gz`; function names are Dahua-firmware Ghidra names (= SDK names).

### 1. Boot: `ScalerAudioADCInitial` then `ScalerAudioDACInitial` (t = 55 ms)
| Addr | Name | Value(s) | Tag |
|---|---|---|---|
| 06B4 | AD_CTRL | 48 | [fw, unverified] ADC path, not used by us |
| 06B0 | REG_ADC_POWER | D0, then D1 | [fw, unverified] ADC (line-in) only |
| 06C0 | REG_DAC_POWER0 | 07 | [fw, unverified] ADC init: input buffer, mbias, vcm |
| 06C0 | REG_DAC_POWER0 | CF, EF, FF | [fw, unverified] DACInitial: dac, dacvref, df2se, mbias, vcm; + aout(5); + hpout(4) |
| 06D4 | DA_CLK_CTRL | 12 | [fw, unverified] depop clock on, div 2 (55.75 kHz, 100 ms transition [spec]) |
| 06C1 | REG_DAC_POWER1 | F1 | [fw, unverified] depop circuit on, VCM select 01 |
| 06D0 | DA_CTRL | 40 | [fw, unverified] HPF on, dither off |
| 06D1 | DA_MUTE | 01 | [fw, unverified] **DAC digital mute off** (reset value C1 = muted); never written again |
| 06D2 / 06D3 | DA_GAIN_L / R | 57 / 57 | [fw, unverified] 0 dB (0.75 dB steps, 0x00 = -65.25 dB [spec]) |
| 06D2 | DA_GAIN_L | D7 | [fw, unverified] bit 7 = double-buffer latch |
| 06E0 | REG_MUX_ANA_OUT | 50 | [fw, unverified] speaker out swapped |

### 2. Source / port select (`ScalerAudioSourceInputSwitch`, `ScalerAudioInputPortSwitch`, t = 122 ms)
| Addr | Name | Value | Tag |
|---|---|---|---|
| 08A0 | DVC_EN | 8F | [fw, unverified] DVC on, dB mode, up/down step 1/8 dB |
| 08A3 / 08A4 | DVC_ZC_WIN_CTRL_0/1 | 00 / 30 | [fw, unverified] ZCD window 0x30 samples (48 kHz default) |
| 08A1 / 08A2 | DVC_VA_MSB/LSB | 00 / 01 | [fw, unverified] |
| 08A5 / 08A6 | DVC_GAIN_MSB/LSB | 00 / 00 | [fw, unverified] gain 0 = silent until unmute |
| 06D1 | DA_MUTE | 01 | [fw, unverified] digital source: DAC input from GDI (bit 3 = 0) |
| 6F01 | MUX_DA_DVC_IN | 02 | [fw, unverified] DVC input = digital port |
| 6F00 | MUX_DIG_OUT | 20, then 22 | [fw, unverified] |
| 08A0 | DVC_EN | CF, 8F | [fw, unverified] counter enable pulse |
| 06C8 | REG_OUT_GAIN | 00, 00 | [fw, unverified] `ScalerAudioDACSetOutputGain` aout, hpout = 0 dB |
| 06C5 | REG_ANA_CTRL | 01 | [fw, unverified] Vcm ready |
- HDMI port: `ScalerAudioD2/D3HDMIAudioInitial` + `D2/D3SetAudioPLL` (data port P71/P72_C9, regs HDMI_MCAPR, CMCR, DPCR0-3, AFCR, WDCR0-2, ... ) [fw names, values = SDK source: `RL6449_Series_Audio.c` 634-860]. In the trace only D1 (DP) was initialised at boot (PB9_xx, t = 105-110 ms). [fw, unverified]
- DP port D1: `ScalerAudioD1SetAudioPLL` (PB9_D1 DIVM 1A, DIVN 00, PLL_WD 16, RESERVE C2, INSEL B0, PLL_PWR 80 -> 00 -> 04 -> 0C -> 1C, ~2 ms apart), `ScalerAudioD1DPAudioInitial` (PB9_74 FSM_CTRL_0 54, PB9_50 FREQ_DET 06, thresholds 00 00 28 4C 5C 70, MN_RS_DEC 8F, DP_AUD_CTRL A0, DVC_CTRL 8F, DP_I2S_CTRL 0F, SPDIF_TX_0 CF, ...). [fw, unverified]
- N/CTS: no software N/CTS value is written. HDMI audio PLL runs from the incoming clock-regeneration packets in hardware; the code sets M/K/O codes and I/P tracking constants only. [spec]

### 3. DAC state machine (`SysAudioAnalogAudioHandler`; times from the decompiled timer arguments)
| State | Action | Registers | Tag |
|---|---|---|---|
| INITIAL | wait 100 ms (timer 0x1F) | - | [fw, unverified] |
| CHARGE | `ScalerAudioDACOutputSwitch` (headphone only); Vcm ready on; wait 500 ms (timer 0x20) | 06C0 = DF, 06C5 = 01 | [fw, unverified] |
| DEPOP | `DACOutputEnable`: Vcm ready off, enable the selected output (hpout only: 06C6 untouched), Vcm ready on; wait 100 ms (timer 0x21) | 06C5 = 00, 06C7 = 00 (mute bits 7:6 cleared), 06C5 = 01 | [fw, unverified] |
| READY | `DACDepopToNormal`: depop -> normal | 06C6 = C8 (aout stays muted), 06C7 = 08, 06C5 = 00 | [fw, unverified] |
- Order matters for pop-free start: outputs stay muted (06C6/06C7 bits 7:6 = 1 from `NormalToDepop`) until Vcm has charged. Sim: boot t = 55 ms -> DEPOP at 1092 ms -> READY at 1200 ms. [fw, unverified]
- Power off / power saving (`SysAudioPowerProc` -> `ScalerAudioDisable`): mute (DVC ramp) -> watchdog off -> cancel timers 0x1F-0x21 -> `NormalToDepop` (06C5 = 00, 06C6/06C7 bit 3 = 0, bits 7:6 = 1, 06C5 = 01) -> 06D4 &= ~10 -> 06C1 &= 0F -> 06C0 = 00 -> DVC_EN bit 6 = 1 -> audio PLL off. [fw, unverified] [spec]

### 4. Mute and volume
- Mute = `SysAudioMuteProc(bMute)` -> `ScalerAudioDVCVolumeMute`: DVC gain ramps to 0 (ZCD) and waits until `DVC_GAIN_DONE` bit 7 or 400 ms (`_DVC_VOLUME_MUTE_TIMER`), then sets the DVC mute status. Unmute writes the user gain. [spec] The Dahua firmware's `SysAudioMuteProc` (3:f8e5) is this function; `DA_MUTE` is not used for mute. [fw, unverified]
- Gain at ACTIVE in the Dahua sim: DVC_GAIN = 0x098C (P8_A5/A6) = 0.149 = -16.5 dB. [fw, unverified] Its volume mapping constants (user bank) are not identified. [?]
- Samples-per-ramp is derived from the detected sampling rate (`ScalerAudioDVCSetMuteZCDTimeout`); rate detect writes `DA_CLK_CTRL` 92 (no audio) / 12 / 52 depending on rate. [fw, unverified]

## Our volume mapping (`AwtoAudioGain`, fw/sdcc/glue.inc)
- Registry `volume` 0..100 % -> DVC_GAIN (14 bit, linear, 0x3FFF = 0 dB, 1/16384 steps [spec]).
- Dahua-like (Dan 2026-11-13): 50 % = `AWTO_AUDIO_GAIN_DAHUA_50` 0x098C (-16.5 dB, the Dahua default) [fw, unverified]; 100 % = `AWTO_AUDIO_GAIN_MAX`, now -6 dB (0x1FFF): cap until the ear test (steps 4-6) shows a cleaner maximum.
- Points per 10 %, even in dB: 0 % = silence, 10 % = -40 dB, 10..50 % 5.9 dB / step, 50..100 % 2.1 dB / step; linear in gain between points. Table `tAwtoVolGain`. [guess: shape; Dahua mapping constants not identified]
- Why not the SDK mapping: `UserCommonAdjustPercentToRealValue` is linear in gain: 50 % would be -6 dB and 10 % -20 dB (steep, hard to set low).
- `DA_GAIN_L/R` (DAC, 0.75 dB steps) are not used for volume; the SDK/Dahua path ramps through the DVC (click-free).

## Ear test (`./dev.py sound-test`, scripts/audio_test.py `steps`)
- `./dev.py sound-test [--unit N] [--only 1,2,..] [--freqs 200,1000,4000] [--secs S]`: opens the diagnostics console (test cmd 0x26, held), then per step: VCP 0x63 = 0x10 + n (console `audio test n/6: ...`), per tone VCP 0x63 = 0x8000 | Hz (console `audio test n: <Hz> Hz`) + the host tone (both channels, ALSA pcm of the unit's connector), VCP 0x63 = 0x30 + n (`... done`). VCP 0x62 volume read before / after, set back if it moved. Times: `tmp/logs/audio_test.log`.
- Steps (firmware `tAwtoAudioTestAmp` / `tAwtoAudioTestMute` / `tAwtoAudioTestGain`, awto_audio.inc; aout; held until the step's end, also through SDK unmutes, E5 04 line):

| n | P7.4 | P7.3 | DVC gain |
|---|---|---|---|
| 1 | on | low | -6 dB |
| 2 | **off** | low | -6 dB |
| 3 | on | low | -16.5 dB (Dahua default) |
| 4 | on | low | -3 dB |
| 5 | on | low | 0 dB |
| 6 | on | **high** (mute check) | -6 dB |
- End: back to default (aout, P7.4 on, P7.3 low, user volume).
- DVC gain pokes: 08A5 / 08A6 are double-buffered; `audio_test.py poke` now latches them (08A7 bit 6, as `ScalerAudioDVCAdjustVolume`). Read back = the applied gain, 00 00 while the SDK holds the DVC muted (no stream). The 14:17-14:18 pokes read 00 for that reason (P7.4 = 0 at the time: muted).
- In every image (VCP 0x63 is unused by the registry); the chip sine generator (VCP 0x63 = 0 / 1) stays in `-D _AWTO_AUDIO_TEST` builds.

## Firmware wiring (what is where)
| Item | Where |
|---|---|
| Options | `fw/sdk/Project/Header/RL6449_Project.h` (audio section) |
| `PCB_AMP_MUTE` no-op | `fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h` |
| `set_ap_volume`, `set_ap_mute`, `AwtoAudioGain` | `fw/sdcc/glue.inc` |
| Amp pins, ear-test steps | `fw/sdcc/awto_audio.inc`; VCP 0x63 in `fw/sdcc/awto_ddcci.inc` |
| Mapping + hold substitutions | `fw/awto/settings/rules.py` (SUBS into `UserAdjustAudioVolumeMapping`, `UserInterfaceGetAudioMuteStatus`) |
| Registry rows | awto-rtdfw `settings/registry.tsv` rows 88-91 (branch `audio`; the firmware pins `audio-fw`, `fw/awto/clean_ref.txt`) |
| MCCS | VCP 0x62 volume 0..100; VCP 0x8D mute: 1 = muted, 2 = unmuted (registry enum `Off=2|On=1`) |
| EDID | `scripts/make_edid.py` (below) |

### Mute sequencing (all by the SDK, plus one hold)
- Unmute only in `SysAudioHandler` PREPARING -> PLAYBACK, when `UserInterfaceGetAudioReadyToPlayStatus()` is true: not muted by the user, DAC READY, audio detected on the input port, mode ACTIVE. [spec]
- Mute again (PLAYBACK -> PREPARING) the moment that condition fails: signal loss, audio loss, input switch, DAC output change. [spec]
- Mode change: `UserInterfaceAdjustAudioResetProc` (SDK, called from the mode reset path) mutes and goes to PREPARING. [spec]
- Power: `SysAudioPowerProc`: NORMAL -> PS / OFF mutes, disables the DAC; PS/OFF -> NORMAL re-initialises. [spec]
- Hold added by us: `UserInterfaceGetAudioMuteStatus()` returns mute `||` mode is not ACTIVE and not DISPLAY_SETTING (`AWTO_AUDIO_HOLD`). So SEARCH, NOSIGNAL, NOSUPPORT, POWER_SAVING, POWER_OFF are all muted, independent of the audio detector.
- L1 (backlight off), L2 (panel off) are NOSIGNAL-mode substates, L3 is POWER_SAVING (the `pwr_l*` rows are still inert): all are covered by the hold. Audio needs an active stream, which a source without video does not provide anyway.
- Risk: the DVC mute ramp blocks the main loop up to 400 ms (`ScalerTimerDelayXms` in `ScalerAudioDVCVolumeMute`). Same code as the Dahua firmware. [spec]

## audio_standalone, audio_source
- `audio_source` (SDK `b1AudioSourceStatus`: Analog = line-in via the ADC, Digital = HDMI/DP): `UserInterfaceGetAudioSource` returns `_DIGITAL_AUDIO` when `_LINE_IN_SUPPORT` is off. Line-in needs pins 113/114 in line_in mode; they are GPIO inputs here. Row stays `inert`. [spec] [hw]
- `audio_standalone` (SDK `_SLEEP_AUDIO_SUPPORT`: keep playing line-in / DP audio in power saving). Conflicts with "silent at L1-L3". Row stays `inert`. [spec]
- To enable line-in later: `_LINE_IN_SUPPORT _ON`, pin-share 113/114 = mode 3, Dahua's ADC init (section 1), a jack. [guess]

## EDID
- Before: no Audio Data Block, no Speaker Allocation Block, basic-audio bit clear ("units have no speakers", docs/edid-fix.md 2026-11-04).
- Now: ADB `23 09 07 07` = Linear PCM, 2 ch, 32/44.1/48 kHz, 16/20/24 bit; SADB `83 01 00 00` = FL/FR; CTA header flags `0xB1 -> 0xF1` (basic audio). Same three ports (DP, HDMI D2, HDMI D3), base block byte-identical (serial text unchanged), checksum fixed. `edid-decode -c`: conformity PASS, warnings unchanged. [spec]

## Offline verification (wb-p14audio1)
See issue "Audio output: add DAC path to our firmware" and the commit message. Proven only by register-write traces: the DAC / DVC / audio PLL sequences. The simulator models no audio hardware, no PLL lock, no analog output. Nothing here proves sound.

## Hardware test plan (unit 2; Dan)
Rollback first: reflash `fw/images/AWT26110002-wb-p14swap10-be.bin` (or the tmp/fw copy), `rtd_flash_image.py ... --write --no-backup`.

1. Connect: headphones or a powered speaker (3.5 mm, line level) to the monitor's jack, if one exists. [?] If there is no connector, probe pins 109/110 (HP out L/R), 115 (ref); also 116/117 (line out, off in this build) on the board and say what is wired; nothing else can be concluded.
2. PC sink: HDMI-2 output is Intel. `pactl list short sinks | grep -i hdmi` (names look like `alsa_output.pci-0000_00_02.0.hdmi-stereo-extra2`); `wpctl status` shows the same under Sinks. Select the monitor sink (`pactl set-default-sink NAME`). After the new EDID, the monitor must show up as an audio device; if not, the EDID did not reach the host (check `/sys/class/drm/card*-HDMI-*/edid` with `edid-decode` for "Basic audio").
3. Tone: `speaker-test -t sine -f 1000 -c 2 -D hdmi:CARD=PCH,DEV=1` or `ffmpeg -f lavfi -i "sine=frequency=1000" -t 30 -f pulse -device NAME out`; quick check `paplay` of any wav to the sink.
4. Checks (tick each):
   - [ ] sound on HDMI-2 (D2), HDMI D3, DP (D1): tone on both channels, left/right correct (the headphone mux is straight; if L/R are crossed, set `_DAC_HP_OUTPUT_SWAP _ON`)
   - [ ] no loud pop at power-on, at the first tone, at input switch, at mode change (`xrandr` change 2160p60 -> 1080p60), at wake from DPMS
   - [ ] volume: `ddcutil --bus N setvcp 62 20`, `... 62 50`, `... 62 100`; `getvcp 62` returns max 100; level steps audibly, 0 = silence
   - [ ] mute: `setvcp 8D 1` silences within ~0.5 s, `setvcp 8D 2` restores; `getvcp 8D` reads 1 / 2
   - [ ] silent at L1 / L2 / L3: `xset dpms force off` (or unplug the source) with the tone running: no sound, no hiss/pop at the backlight-off, panel-off, deep-sleep edges
   - [ ] after wake (key press / signal back) sound returns on its own within ~1 s of the picture
   - [ ] check the main loop: DDC/CI and the front keys still respond while muting (400 ms ramp worst case)
5. If silent: read the DAC state with the debug link (`rtd_reg_dump.py`: 06C0 = DF, 06C5, 06C7 = 00 then 08, 06C6 = C8, 06D1 = 01, 06D2 = 57/D7, 08A0 = 8F, 08A5/08A6 = volume gain, 6F01 = 02), and `pactl list sinks` for the monitor (is the stream running).

## Unit 2 run, 2026-11-13 (wb-p14ui-audio2, HDMI D2 = host Intel HDMI-A-2, 4K60)
- Host: no PipeWire HDMI sink (Intel card profile = analog only); tones go straight to ALSA `plughw:CARD=PCH,DEV=3` (ELD `awto-mon`: LPCM 2 ch, 32/44.1/48 kHz, 16/20/24 bit, FL/FR). `IEC958 Playback Switch` index 0 was off: set on. Tool: `scripts/audio_test.py` (tools-audio); log `tmp/logs/audio_test.log`.
- Volume registry row `volume` = 100 % (VCP 0x62), `mute` = Off.
- Readback during the 880 Hz both-channel tone (debug slave, MCU running) [hw]:
  - 06C0 REG_DAC_POWER0 = FB (aout + hpout on), 06C1 = F1, 06C5 = 00, 06C6 REG_AOUT_CTRL = 08, 06C7 REG_HPOUT_CTRL = 08 (both unmuted, normal), 06C8 = 00 (0 dB)
  - 06D0 = 40, 06D1 DA_MUTE = 01, 06D2/3 DA_GAIN = 57/57 (0 dB), 06D4 = 12, 06E0 = 50
  - DVC: 08A0 = 8F, 08A5/A6 = 3F FF (0 dB, 100 %), 08A7 = 3F; 6F00 = 22, 6F01 = 02
  - P7.3 = 0, P7.4 = 1, P4.5 = 1; SDK audio PLAYBACK, DAC READY, D2 audio detected 48 kHz, power NORMAL, mode ACTIVE
  - Ring: + 213 ms amp off (P7.4 = 0), + 462 ms aux low (P7.3 = 0), + 1489 ms ACTIVE, + 1492 ms amp on (P7.4 = 1)
- Same tones on the previous image (wb-p14ui-nvlog2, hpout only, P7.3/P7.4 never driven: both read 1) at 09:22:07-09:22:16.
- `_DAC_SPEAKER_OUTPUT_SWAP _ON` crosses aout L/R as the Dahua firmware does (06E0 = 50); L/R placement unconfirmed until Dan reports which side the 440 Hz left tone came from. [?]

## Unit 3 ear test, 2026-11-13 (wb-p14ui-rotdef1: aout only, superseded by the hpout build; HDMI D2 = host Intel HDMI-A-2 -> ALSA PCH device 3, volume 100 %)
- `./dev.py sound-test --unit 3 --freqs 200,1000,4000` (3 s per tone, 3 s between steps); every step + tone line came on the console; aplay rc 0 x 18.
- Times (+11:00): step 1 13:37:30-13:37:39, step 2 13:37:42-13:37:51, step 3 13:37:54-13:38:03, step 4 13:38:06-13:38:16, step 5 13:38:19-13:38:28, step 6 13:38:31-13:38:40; tones 200 / 1000 / 4000 Hz at +0 / +3 / +6 s of each step.
- Heard per step: Dan's answer pending (#94); it picks `AWTO_AUDIO_GAIN_MAX` (steps 4-6) and whether P7.4 gates the speaker (step 2).

## Unit 3 ear test, 2026-11-13 (wb-p14ui-rotdef3: hpout only -> amp, aout off; Dan's ears, +11:00)
- Full sound-test 13:56:07-13:57:17 and 14:08:38-14:09:49 (steps: amp on / off, -16.5 / -6 / -3 / 0 dB): silent in every step. State: hpout -> amp, P7.4 = 1, P7.3 = 0.
- Live poke P7.3 = 1 (stays), hpout only, amp on; tones 14:10:22 and 14:17:08-14:17:18: silent.
- Pokes 06C0 = FB / 06C6 = 08 (aout + hpout): not valid, the SDK switched back to 06C0 = DB / 06C6 = C8 within seconds, also during PLAYBACK (14:18:15 -> 14:18:23).
- Compare unit 2 (audible, Dan): wb-p14ui-audio2 (06C0 = FB aout + hpout, both unmuted, DVC 0 dB, P7.3 = 0, P7.4 = 1): voice test "Correct sides", then clipping. wb-p14ui-nvlog2 (hpout only, P7.3 / P7.4 never driven, both read 1): audible.

## Unit 3 ear test, 2026-11-13 (wb-p14ui-outmx3: output matrix, `_DAC_OUTPUT_SWITCH_SUPPORT _OFF`; Dan's ears, +11:00)
- Steps: 1 hpout / P7.3 low, 2 hpout / high, 3 aout / low, 4 aout / high, 5 both / low, 6 both / high; P7.4 on, -6 dB. Runs 14:40:28 and 14:41:33.
- Sound ONLY in step 3 (aout, P7.3 low) and step 5 (both, P7.3 low). Steps 1, 2, 4, 6 silent.
- Reading [hw]: aout feeds the speaker amp, hpout alone does not; P7.3 high silences the amp (AMP_MUTE, active high). P7.4 untested (never 0 while playing on unit 3).
- Open: unit 2 nvlog2 (hpout only, P7.3 / P7.4 released, read 1) was reported audible; contradicts this on unit 3 [?].
- Register comparison, Dahua dumps `tmp/regs/AWT26110001-20261105-121355.json` / `AWT26110003-20261105-180523.json` vs unit 3 live outmx3 14:45:03 (pages 06 / 08) [hw]:
  - Same: 06C1 = F1 (df2se LPF Q 0), 06C2 / C3 = AA / AB (currents), 06C8 = 00, 06D0 = 40 (da_hpf_en on, dither 0), 06D1 = 01, 06D2 / D3 = 57 / 57, 06D4 = 12, 06E0 = 50. No EQ / filter registers on this chip: no frequency-response setting we lack.
  - Dahua 06C0 = EF, 06C6 = 08, 06C7 = C8 = aout only (independent confirmation of step 3).
  - Differ, not frequency response: 06E2 S/PDIF CS sampling_freq (ours 02 / Dahua 00), 06E7 AD_I2S_CTRL (00 / 80), 08A0 DVC_EN (9F / 8F, dvc_value_mode), 08A2 (40 / 01), 08A3 / A4 ZC window (03C0 / 0000), gain (1FFF / 098C). Kept as they are: DVC ramp / ZC values change only with Dan's OK.
- Full field table, Dahua vs ours: `docs/audio-registers.md` (generated by `scripts/audio_regs_doc.py`, ours = `tmp/regs/AWT26110003-audio-wb-p14ui-amp1-20261113-145157.json`). amp1 idle: 06C0 = EB (aout on; bit 2 input buffer off vs Dahua EF: ADC / line-in init, `_LINE_IN_SUPPORT _OFF`), 06C6 = 08, 06C7 = C8.

## Unit 3 GPIO near the amp, 2026-11-13 (wb-p14ui-amp1 live `tmp/regs/AWT26110003-gpio-on-amp1-20261113-145214.json` vs Dahua ON dumps) [hw]
- `scripts/rtd_gpio_live.py --diff`; read after the amp1 sound test (unmuted: P7.3 = 0, P7.4 = 1). ISP read halts the MCU and resets the unit.
- vs unit 1 Dahua (140945): P7.0-P7.6 same (P7.3 0, P7.4 1). Differ: P4.5 jack input 0 -> 1, P4.6 0 -> 1, P4.1 / P4.2, PA.2 / PA.4 / PA.5.
- vs unit 3 Dahua (161803): P7.3 1 -> 0 (ours unmuted), P7.0 rc0 0 -> 1, P7.2 panel VDD 0 -> 1, P6.3, P8.4 / P8.5 0 -> 1, P9.2 backlight 1 -> 0 (on), P9.5, P4.1, P5.7. P7.4, P4.5 same.
- Nothing near pins 160 / 161 differs except P7.3 (the mute itself) and P7.2 (panel power).

## Unit 3 ear test, 2026-11-13 (wb-p14ui-amp1: aout, P7.3 = AMP_MUTE; flashed ungated: wdt gate killed by host load 43, menu passed)
- `./dev.py sound-test --unit 3 --freqs 1000`, 3 s tone, +11:00: step 1 14:50:52-14:50:55, step 2 14:50:58-14:51:01, step 3 14:51:05-14:51:08, step 4 14:51:11-14:51:14, step 5 14:51:17-14:51:20, step 6 14:51:23-14:51:26. Console lines confirmed (sync log). Volume 100 % before / after.
- Host step labels in that log were stale (main's audio_test.py, pre-merge); the firmware lines are the amp1 steps above.
- Heard: Dan's answer pending.

## Distortion, unit 3 (06E0 = 00 by poke from 14:55:26, aout, P7.3 low, P7.4 on; Dan's ears, 2026-11-13) [hw]
- Voice still breaks up; a ringtone plays clean. Low frequencies distort (200 Hz tone, voice); 4000 Hz mostly fine.
- No bass cut or EQ in the chip: `da_hpf_en` (06D0 bit 6) is on / off only (DC block), `df2se_lpfq` (06C1) shapes the top end only; DVC is a flat gain. Nothing in the DAC / DVC registers shapes the low end [spec].
- Open: identify the speaker amp part (Dan to photograph it) for its supply / input range and low-frequency limits; then decide on level (`AWTO_AUDIO_GAIN_MAX`) or a firmware-side limit.

