# Analog audio output (awto-ddc#93)

Tags (#91): [fw] = seen in the Dahua firmware (decompile `~/vendors/realtek/analysis/jxc-4k/bank3`, or its sim trace `tmp/logs/trace_vendor_{2160p60,1080p60}.tsv.gz` = ordered register writes with values); [spec] = Realtek SDK source / register DB (`regdb/RTD2785TM-CG.tsv`); [hw] = measured on a unit; [guess]; [?] unknown.
Status: speaker output only since 2026-11-13 (headphone out dropped, Dan: "it definitely does not work"); DAC + amp pins run, HDMI D2 audio plays through the DVC (register readback below); audible result: Dan's ears (#94), ear test `./dev.py sound-test` (below).

## Summary
- Our firmware compiled the Realtek SDK audio out (`_AUDIO_SUPPORT _OFF`, "no audio jacks", 2026-11-04). The Dahua firmware runs the SDK audio path into the embedded DAC. [fw]
- Now: `_AUDIO_SUPPORT _ON`, `_EMBEDDED_DAC_SUPPORT _ON`, `_DAC_SPEAKER_OUTPUT_SWAP _ON` (RL6449_Project.h). The SDK `SysAudio` state machine + `UserInterface*Audio*` hooks do the sequencing; we supply volume, mute and the hold.
- Source = digital (HDMI D2/D3, DP D1) -> audio PLL -> DVC (digital volume) -> DAC -> pins. Not a line-in monitor: see "audio_source".
- Volume = DVC gain (P8_A5/A6), exactly like the Dahua firmware. DAC gain `DA_GAIN_L/R` stays 0 dB (0x57). [fw]

## Pins, jack
- Output: speaker only = aout 116/117 AUDIO_SOUTL/R (feeds the speaker amp); `UserInterfaceGetAudioDACOutput` returns SPEAKER, `_DAC_HP_OUTPUT_SUPPORT _OFF` (hpout 109/110 AUDIO_HOUTL/R unpowered; Dan 2026-11-13: no sound from it). `AWTO_AUDIO_OUT` (speaker / headphone / both) removed. 115 AUDIO_REF. Chip pins: RL6449 LQFP216, `docs/monitors/pinshare-live-AWT26110003.tsv`; all in audio mode (0x03). [hw]
- Dahua firmware picks the output from P4.5 (pin 113, jack input, `1:f69b`): low -> SPEAKER, high -> HEADPHONE; unit 2 reads P4.5 = 1 with no jack (2026-11-13) [hw], so its sim trace (06C0 = DF, HP only) is the no-jack-detected path; polarity [?].
- Speakers: confirmed present by Dan (2026-11-13; earlier 'no speakers', #3/#22, was wrong).
- Amp pins (one owner `fw/sdcc/awto_audio.inc`, as Dahua `5:d2a0` / `1:ea99`, `docs/reversing/dahua-fw/gpio-ir.md` s4): AC on P7.4 (pin 161) = 0; P7.3 (pin 160) = 0 `AWTO_AUDIO_AUX_MS` = 200 ms later (first main-loop poll + 200 ms); P7.4 = !mute (`PCB_AMP_MUTE` from `SysAudioMuteProc`, Dahua speaker path). Ring lines `E5` (sync.tsv): amp on / off / aux low. [fw]
- The SDK demo board uses P3.5 (pin 91) as AMP_MUTE; our pin 91 is DPTX_AUX_P (P3D5 output, live 0x01). Not the same function. [hw]

## Option set (SDK `RL6449_Project.h` names) and what the Dahua firmware uses
| Option | Dahua firmware | Ours | Evidence |
|---|---|---|---|
| `_AUDIO_SUPPORT` | on | on | audio code present [fw] |
| `_EMBEDDED_DAC_SUPPORT` | on | on | `ScalerAudioDACInitial` 3:f39f [fw] |
| `_DAC_SPEAKER_OUTPUT_SUPPORT` / `_DAC_HP_OUTPUT_SUPPORT` | on / on | on / **off** | REG_DAC_POWER0 ends 0xFF = bits 5,4 set [fw]; ours: hpout dropped (#94) |
| `_DAC_SPEAKER_OUTPUT_SWAP` | on | on | REG_MUX_ANA_OUT = 0x50 (aout L/R crossed, hpout straight) [fw] |
| `UserInterfaceGetAudioDACOutput()` | P4.5: speaker or headphone | SPEAKER | Dahua trace 06C0 = DF = headphone (P4.5 high in the sim) [fw]; ours was 06C0 = FB (both, unit 2) [hw] |
| `_DAC_DITHER_FUNCTION_LEVEL` | off | default off | DA_CTRL = 0x40 [fw] |
| `_DIGITAL_DAC_AOUT/HPOUT_GAIN_DB`, `_LINE_IN_DAC_*_GAIN_DB` | 0 dB | default 0 dB | REG_OUT_GAIN = 0x00 twice [fw] |
| `_LINE_IN_SUPPORT` | on (ADC init runs at boot) | **off** | ADC init writes P6_B0..B7 in the trace [fw]; line-in pins are GPIO on this board [hw] |
| `_SLEEP_AUDIO_SUPPORT` | ? | off | no stand-alone audio; L1-L3 must be silent |
| `_DVC_ADJUST_TYPE` | dB gain mode | default `_DB_GAIN` | P8_A0 = 0x8F, VA 0x0001 [fw] |
- `PCB_AMP_MUTE`, `_DAC_*_SWAP` live in `fw/sdk`; the rest are SDK defaults.

## Register sequence (Dahua firmware, 2160p60 sim, boot to ACTIVE) [fw]
All values are the trace of `trace_vendor_2160p60.tsv.gz`; function names are Dahua-firmware Ghidra names (= SDK names).

### 1. Boot: `ScalerAudioADCInitial` then `ScalerAudioDACInitial` (t = 55 ms)
| Addr | Name | Value(s) | Tag |
|---|---|---|---|
| 06B4 | AD_CTRL | 48 | [fw] ADC path, not used by us |
| 06B0 | REG_ADC_POWER | D0, then D1 | [fw] ADC (line-in) only |
| 06C0 | REG_DAC_POWER0 | 07 | [fw] ADC init: input buffer, mbias, vcm |
| 06C0 | REG_DAC_POWER0 | CF, EF, FF | [fw] DACInitial: dac, dacvref, df2se, mbias, vcm; + aout(5); + hpout(4) |
| 06D4 | DA_CLK_CTRL | 12 | [fw] depop clock on, div 2 (55.75 kHz, 100 ms transition [spec]) |
| 06C1 | REG_DAC_POWER1 | F1 | [fw] depop circuit on, VCM select 01 |
| 06D0 | DA_CTRL | 40 | [fw] HPF on, dither off |
| 06D1 | DA_MUTE | 01 | [fw] **DAC digital mute off** (reset value C1 = muted); never written again |
| 06D2 / 06D3 | DA_GAIN_L / R | 57 / 57 | [fw] 0 dB (0.75 dB steps, 0x00 = -65.25 dB [spec]) |
| 06D2 | DA_GAIN_L | D7 | [fw] bit 7 = double-buffer latch |
| 06E0 | REG_MUX_ANA_OUT | 50 | [fw] speaker out swapped |

### 2. Source / port select (`ScalerAudioSourceInputSwitch`, `ScalerAudioInputPortSwitch`, t = 122 ms)
| Addr | Name | Value | Tag |
|---|---|---|---|
| 08A0 | DVC_EN | 8F | [fw] DVC on, dB mode, up/down step 1/8 dB |
| 08A3 / 08A4 | DVC_ZC_WIN_CTRL_0/1 | 00 / 30 | [fw] ZCD window 0x30 samples (48 kHz default) |
| 08A1 / 08A2 | DVC_VA_MSB/LSB | 00 / 01 | [fw] |
| 08A5 / 08A6 | DVC_GAIN_MSB/LSB | 00 / 00 | [fw] gain 0 = silent until unmute |
| 06D1 | DA_MUTE | 01 | [fw] digital source: DAC input from GDI (bit 3 = 0) |
| 6F01 | MUX_DA_DVC_IN | 02 | [fw] DVC input = digital port |
| 6F00 | MUX_DIG_OUT | 20, then 22 | [fw] |
| 08A0 | DVC_EN | CF, 8F | [fw] counter enable pulse |
| 06C8 | REG_OUT_GAIN | 00, 00 | [fw] `ScalerAudioDACSetOutputGain` aout, hpout = 0 dB |
| 06C5 | REG_ANA_CTRL | 01 | [fw] Vcm ready |
- HDMI port: `ScalerAudioD2/D3HDMIAudioInitial` + `D2/D3SetAudioPLL` (data port P71/P72_C9, regs HDMI_MCAPR, CMCR, DPCR0-3, AFCR, WDCR0-2, ... ) [fw names, values = SDK source: `RL6449_Series_Audio.c` 634-860]. In the trace only D1 (DP) was initialised at boot (PB9_xx, t = 105-110 ms). [fw]
- DP port D1: `ScalerAudioD1SetAudioPLL` (PB9_D1 DIVM 1A, DIVN 00, PLL_WD 16, RESERVE C2, INSEL B0, PLL_PWR 80 -> 00 -> 04 -> 0C -> 1C, ~2 ms apart), `ScalerAudioD1DPAudioInitial` (PB9_74 FSM_CTRL_0 54, PB9_50 FREQ_DET 06, thresholds 00 00 28 4C 5C 70, MN_RS_DEC 8F, DP_AUD_CTRL A0, DVC_CTRL 8F, DP_I2S_CTRL 0F, SPDIF_TX_0 CF, ...). [fw]
- N/CTS: no software N/CTS value is written. HDMI audio PLL runs from the incoming clock-regeneration packets in hardware; the code sets M/K/O codes and I/P tracking constants only. [spec]

### 3. DAC state machine (`SysAudioAnalogAudioHandler`; times from the decompiled timer arguments)
| State | Action | Registers | Tag |
|---|---|---|---|
| INITIAL | wait 100 ms (timer 0x1F) | - | [fw] |
| CHARGE | `ScalerAudioDACOutputSwitch` (headphone only); Vcm ready on; wait 500 ms (timer 0x20) | 06C0 = DF, 06C5 = 01 | [fw] |
| DEPOP | `DACOutputEnable`: Vcm ready off, enable the selected output (hpout only: 06C6 untouched), Vcm ready on; wait 100 ms (timer 0x21) | 06C5 = 00, 06C7 = 00 (mute bits 7:6 cleared), 06C5 = 01 | [fw] |
| READY | `DACDepopToNormal`: depop -> normal | 06C6 = C8 (aout stays muted), 06C7 = 08, 06C5 = 00 | [fw] |
- Order matters for pop-free start: outputs stay muted (06C6/06C7 bits 7:6 = 1 from `NormalToDepop`) until Vcm has charged. Sim: boot t = 55 ms -> DEPOP at 1092 ms -> READY at 1200 ms. [fw]
- Power off / power saving (`SysAudioPowerProc` -> `ScalerAudioDisable`): mute (DVC ramp) -> watchdog off -> cancel timers 0x1F-0x21 -> `NormalToDepop` (06C5 = 00, 06C6/06C7 bit 3 = 0, bits 7:6 = 1, 06C5 = 01) -> 06D4 &= ~10 -> 06C1 &= 0F -> 06C0 = 00 -> DVC_EN bit 6 = 1 -> audio PLL off. [fw] [spec]

### 4. Mute and volume
- Mute = `SysAudioMuteProc(bMute)` -> `ScalerAudioDVCVolumeMute`: DVC gain ramps to 0 (ZCD) and waits until `DVC_GAIN_DONE` bit 7 or 400 ms (`_DVC_VOLUME_MUTE_TIMER`), then sets the DVC mute status. Unmute writes the user gain. [spec] The Dahua firmware's `SysAudioMuteProc` (3:f8e5) is this function; `DA_MUTE` is not used for mute. [fw]
- Gain at ACTIVE in the Dahua sim: DVC_GAIN = 0x098C (P8_A5/A6) = 0.149 = -16.5 dB. [fw] Its volume mapping constants (user bank) are not identified. [?]
- Samples-per-ramp is derived from the detected sampling rate (`ScalerAudioDVCSetMuteZCDTimeout`); rate detect writes `DA_CLK_CTRL` 92 (no audio) / 12 / 52 depending on rate. [fw]

## Our volume mapping (`AwtoAudioGain`, fw/sdcc/glue.inc)
- Registry `volume` 0..100 % -> DVC_GAIN (14 bit, linear, 0x3FFF = 0 dB, 1/16384 steps [spec]).
- Dahua-like (Dan 2026-11-13): 50 % = `AWTO_AUDIO_GAIN_DAHUA_50` 0x098C (-16.5 dB, the Dahua default) [fw]; 100 % = `AWTO_AUDIO_GAIN_MAX`, now -6 dB (0x1FFF): cap until the ear test (steps 4-6) shows a cleaner maximum.
- Points per 10 %, even in dB: 0 % = silence, 10 % = -40 dB, 10..50 % 5.9 dB / step, 50..100 % 2.1 dB / step; linear in gain between points. Table `tAwtoVolGain`. [guess: shape; Dahua mapping constants not identified]
- Why not the SDK mapping: `UserCommonAdjustPercentToRealValue` is linear in gain: 50 % would be -6 dB and 10 % -20 dB (steep, hard to set low).
- `DA_GAIN_L/R` (DAC, 0.75 dB steps) are not used for volume; the SDK/Dahua path ramps through the DVC (click-free).

## Ear test (`./dev.py sound-test`, scripts/audio_test.py `steps`)
- `./dev.py sound-test [--unit N] [--only 1,2,..] [--freqs 200,1000,4000] [--secs S]`: opens the diagnostics console (test cmd 0x26, held), then per step: VCP 0x63 = 0x10 + n (console `audio test n/6: ...`), per tone VCP 0x63 = 0x8000 | Hz (console `audio test n: <Hz> Hz`) + the host tone (both channels, ALSA pcm of the unit's connector), VCP 0x63 = 0x30 + n (`... done`). VCP 0x62 volume read before / after, set back if it moved. Times: `tmp/logs/audio_test.log`.
- Steps (firmware `tAwtoAudioTestAmp` / `tAwtoAudioTestGain`, awto_audio.inc; held until done, the SDK unmute / volume mapping keep them):

| n | amp P7.4 | DVC gain |
|---|---|---|
| 1 | on | user volume |
| 2 | off | user volume |
| 3 | on | -16.5 dB (0x098C, Dahua default) |
| 4 | on | -6 dB (0x1FFF, volume 100 % now) |
| 5 | on | -3 dB (0x2D4E) |
| 6 | on | 0 dB (0x3FFF) |
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
