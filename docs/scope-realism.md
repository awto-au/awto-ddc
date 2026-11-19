# Scope screensavers vs real scopes without a trigger (2026-11-19)

Tags: `[web]` cited source (list at the end), `[code]` read in `fw/test/` / `scripts/` on this branch, `[hw]` unit 3 measurement (`docs/saver-fps-hw.md`), `[guess]` not checked.
Scope 1 was retired 2026-11-19 (`docs/saver-mode.md` Scope 1 retired: smoothness, pacing); Scope 1 rows below are history. Code read: `fw/test/scope_saver.c` (Scope 1, deleted), `fw/test/scope_saver2.c` + `scripts/gen_scope2.py` + `scripts/scope2_sim.py` (Scope 2).
Not in this worktree: `docs/scope-corruption.md` (branch `worktree-agent-ae2a966dd9a939cf6`).

## 1. Real scope without a trigger

### Analog CRT
- Recurrent sweep: a free-running sawtooth oscillator, uncalibrated, on cheap/old scopes; set slightly below a submultiple of the signal to show >= 2 cycles [web Wikipedia Oscilloscope, "Recurrent sweeps"].
- Auto sweep: a timer forces pseudo-triggers when no real trigger arrives so the trace stays visible; it stops once real triggers come [web same, "Automatic sweep mode"].
- Untriggered periodic signal: sweep and signal are not locked, so the trace drifts across the screen and shows several copies at different phases (ghosts). Locking is what stops it [web: lock by trigger, "Triggered sweep"; the drift/ghost look itself is [guess] from that].
- Retrace: the beam is blanked at the right edge while the sweep resets; holdoff ignores triggers during that time [web "Triggered sweep", "Holdoff"].
- Phosphor persistence: the trace fades with the phosphor decay time; slow sweeps need less intensity, fast ones more [web Wikipedia, "Intensity control"].
- Dual-trace: chopped (async) or alternate (per sweep) channel switching [web "Dual and multiple-trace"].

### Digital storage scope (DSO)
- Acquisition record: an ADC buffer is filled, then drawn; pre-trigger and post-trigger portions around the trigger point [web Test&Measurement Tips, Tek roll-mode article, "pre-trigger portion"].
- Trigger mode AUTO: the timeout forces a trigger so the display always updates. TiePie: "approximately 20 ms" on conventional desktop scopes (vendor statement) [web TiePie "Trigger time-out"].
- Trigger mode NORMAL: an acquisition completes only after a real trigger; with no trigger the last record stays on screen. Keysight: NORMAL for low-rate signals [web Keysight BenchVue "Trigger Settings"; "last record stays" is [guess] from that].
- SINGLE: arm once, one record, then stop until re-armed [web Wikipedia "Single sweeps"].
- Roll mode: no trigger, auto trigger only, slow timebase only. Trace enters at the right edge and moves right to left; the time base is static; a single-shot resets it to the right side [web Test&Measurement Tips, Tek MDO3000]. Threshold given as <= 40 ms/div (Tek) and "greater than approximately 100 ms/div" (Liquid Instruments). Vendors disagree, so treat the number as per-model [web both].
- Scan mode (some scopes): same as roll, but the trace enters at the left [web Tek roll-mode article].
- Equivalent-time sampling: builds the picture over many repetitions of a repetitive signal; not usable for single-shot [web Pico Technology KB "Equivalent time sampling"]. Real-time: one record per event.
- Persistence / intensity grading: the screen cell hit count sets its brightness, so frequently hit areas glow [web electronics-notes "Digital Phosphor Oscilloscope"; Keysight "Intensity Grading, Persistence and Histograms" is a video, title only].
- Update: each acquisition redraws the screen; the rate is the waveform update rate of the scope [web Pico KB title only; the "redraw per record" rule is [guess]].
- Graticule: 10 major divisions across the screen (Wikipedia: "One expects to see ten major divisions across"). Vertical count varies by model [web Wikipedia "Graticule"]; 8 vertical is the common 10 x 8 [guess].
- Readouts: frequency = reciprocal of the measured period; digital scopes compute the measurements and print them [web Wikipedia "Graticule"; Keysight "Trigger Settings" for the controls].

## 2. Ours

### Scope 1 (`fw/test/scope_saver.c`) [code]
- 384 x 216 px, 32 x 12 tiles of 12 x 18, 1-bit cells, scale-up 64/7 (AWTO_SC_SU_FACTOR).
- Trace = two sine terms: y = mid - A1 sin(x + ph) - A2 sin(2x + 2 ph) (64-entry tables). Fundamental period 64 px, so 6 cycles on screen, all the time.
- Per frame: `s_ucPhase += 3`. The waveform translates right to left at constant speed. No trigger, no start point, no edge.
- Per column: draws the runs of the new phase and clears the runs of the previous phase (`ScRuns(ucCol, ph - 3)`), so no persistence.
- Frame schedule: 40 ms target (25 fps) with resync when behind (`AWTO_SC_FRAME_MS`).
- Between frames: the last complete frame stays up while columns are rewritten in place (see 2b).
- Graticule: dots every 4 px, 8 x 4 divisions (AWTO_SC_GRID_STEP_X 48, _Y 54).
- No readouts, no labels.

### Scope 2 (`fw/test/scope_saver2.c`, `gen_scope2.py`) [code]
- Raster 480 x 270 px = 40 x 15 tiles, scaled 8x to the panel; 2-bit cells: green plane = trace and readouts, red = graticule and level marks.
- Static tiles (graticule, labels) uploaded once; per frame only tiles the trace, cursors or delta t touch are drawn, into a slot ring above the static ids.
- One rising pulse per frame at x0. x0 drifts +2 px per frame over a 129 px range, then wraps (`AWTO_S2_X0_STEP`, `_RANGE`). So one pulse moves right, then jumps back.
- Edge speed: table step (spread) 4..9 px, +1 at every wrap. The rise time therefore changes about every 65 frames.
- Cursors: dotted, on the 10 % and 90 % points of the edge. Delta t readout = cursor distance x 1 ns/div (`AWTO_S2_PS_PER_DIV` 1000, `DIV_X` 60). Because spread changes, the readout jumps at each wrap, while the scale label stays fixed.
- Labels at the bottom (V/div, s/div), delta t at the top. No frequency readout.
- Per-column passes, 8 ms budget (`AWTO_S2_PASS_MS`) plus one tile, so the main loop (DDC/CI, keys) runs between calls.
- Frame rate: 6.6 frames/s in the sim (scope2_sim, 2026-11-18); 5.63 frames/s stock on unit 3 [hw, `docs/saver-fps-hw.md`, 2026-11-19].

### 2b. What the screen shows between frames [code, visibility guess]
- Scope 1 and 2: global double buffer is off (`AwtoOsdScreenBegin`; `docs/saver-fps-hw.md` "Windows", tear-risk note), so each frame is written in place while it is shown.
- At any moment the panel shows the new frame left of the write position and the old frame right of it [code]. The boundary moves left to right each frame [guess: not photographed].
- Old trace cells are reset to the static tile in the same column pass, so there is no decay between frames [code].
- First frame is drawn hidden, then the OSD is shown (both savers) [code].
- Scope 2 SRAM corruption at default clocks (direct stores, no spacing) is fixed only on `worktree-agent-ae2a966dd9a939cf6` (24 nops per store, not merged) [code, other branch].

## 3. Gap table

| real scope behaviour | what ours does | gap | cheap way to match (OSD hardware, `docs/saver-fps-hw.md`) | cost |
|---|---|---|---|---|
| Auto/untriggered: event drifts, wraps [web] | Scope 2 pulse drifts +2 px/frame and wraps; Scope 1 waveform scrolls at constant speed | Scope 2 drift looks like auto-trigger; the wrap jump and the readout jump do not happen on a real scope | none needed; keep drift, remove the readout jump (fix spread steps) | none / CPU less |
| Trigger lock: fixed trigger point, stable edge [web] | no trigger point anywhere | nothing stays still in Scope 2 | pin x0 (no drift) + 0-1 px jitter | none |
| Phosphor persistence: trace fades over frames [web] | none; cells cleared in the same column pass | no trail | palette ageing: rewrite the colour bits of aged cells (map byte, bytesel B2) + palette entries (~12 us each) [saver-fps-hw #8, (b)] | low (1 byte per aged cell) |
| Intensity grading: hit count sets brightness [web] | none | no density | per-cell hit counter in XDATA (Scope 2: 600 cells; Scope 1: 384) + palette ramp | medium |
| Roll mode: new data at right, scrolls right to left, no trigger [web] | Scope 1 scrolls the whole periodic waveform at constant speed; Scope 2 does not scroll | Scope 1 redraws every column each frame; real roll only adds the newest column | coarse horizontal scroll fs_base +1 per step (wraps per row) + 1 px font delay; test T-F [saver-fps-hw "Scroll", guess] | medium; T-F needed |
| Retrace blanking [web] | in-place column write, visible boundary | visible mixed frame | pop-on page flip, FRAME_CTRL_18 display_base_sel, two maps (Scope 2: 616 words x 2 fits) [saver-fps-hw #11, T-E] | low CPU, SRAM x2 |
| Single / Normal / hold last record [web] | always running | no "stopped" state | freeze the frame, print "SINGLE" / "STOP" text cells (static tiles) | near zero |
| Graticule 10 x 8 major divisions [web] | Scope 1 8 x 4, Scope 2 8 across | 8 vs 10 across | window grid lines WIN2-4 for the solid graticule [saver-fps-hw T-A]; keep dotted minor ticks as cells | medium; T-A |
| Readouts: frequency, delta t, V/div, s/div [web] | Scope 2: delta t + labels; Scope 1: none | no Hz, labels fixed | static text cells; Hz from fixed period, not measured | low |
| Equivalent-time / real-time sampling [web] | none | not modelled | no OSD feature; skip | - |
| Update per acquisition [web] | 25 fps schedule target (Scope 1); Scope 2 5.6 fps on unit 3 stock [hw] | rate not comparable | clock x2 (#2 in saver-fps-hw) or fewer changed tiles (run-glyph #1) | see saver-fps-hw |

## 4. Modes that look like a real scope, ranked by effort

1. **Single-shot capture with readouts** (lowest). One pulse, frame held, "SINGLE" text, delta t and V/div / s/div readouts. Near-zero CPU while held. Needs: a state flag and text cells.
2. **Triggered repeating capture with persistence.** Pulse pinned at a fixed x (trigger point), 0-1 px jitter, 2-4 old captures aged by palette. Needs: remove drift; palette ageing. Low-medium.
3. **Auto-trigger free-run with phosphor decay.** Drifting pulse (as now) plus ageing of old trace cells, pop-on to stop the in-place tear. Medium. Scope 2 is closest to this, minus the ageing and the tear fix.
4. **Roll mode, right to left.** Map scrolls one cell per step (fs_base +1), only the rightmost column of tiles is drawn; no trigger. Medium-high; depends on T-F (wrap behaviour on the unit).
5. **Intensity-graded persistence** (DPO-like). Per-cell hit count drives palette index per cell, decays each frame. Highest: counters, a colour write per changed cell, XDATA 384-600 B.

Which one our Scope 2 resembles: mode 3 without ageing and without the tear fix. Its drifting pulse reads as an auto trigger with no lock [guess, visual only]. Its delta t readout jumps at each wrap, which a real scope would not do [code].
Scope 1 resembles an untriggered periodic signal that never drifts, i.e. a constant-speed scroll. A real untriggered scope would drift or show ghosts instead [web + guess].

## 5. Next steps (decisions for Dan)
- D-R1: pick the target mode (one of 1-5) for the Scope 2 default.
- D-R2: test T-F (horizontal fs_base wrap) and T-E (pop-on) on unit 3 before choosing mode 4 or the tear fix.
- D-R3: the readout jump at each drift wrap: fix (constant spread) or keep as "auto" behaviour?

## Sources [web]
- Wikipedia, Oscilloscope (triggered sweep, auto sweep, recurrent, single, holdoff, graticule, intensity): https://en.wikipedia.org/wiki/Oscilloscope
- TiePie, Trigger time-out: https://www.tiepie.com/en/fut/trigger-time-out
- Test & Measurement Tips, Basics of oscilloscope roll mode (Tek MDO3000): https://www.testandmeasurementtips.com/basics-oscilloscope-roll-mode-act-event-trigger-menu/
- Liquid Instruments KB, "roll" timebase: https://knowledge.liquidinstruments.com/oscilloscope/what-is-timebase-setting-%22roll%22
- Keysight BenchVue help, Trigger Settings (Auto / Normal): https://helpfiles.keysight.com/BenchVueSoftware_HDML5HelpFiles/USBModular/ScopeApp/English/Content/GUI/Instrument%20Settings/Trigger%20Settings.htm
- Keysight, Intensity grading / persistence (video page, title only): https://www.keysight.com/ca/en/assets/6123-1230/lessons/0018HighSpeedOscilloscopeBasics008WaveformVisualization.html
- Electronics Notes, Digital Phosphor Oscilloscope: https://www.electronics-notes.com/articles/test-methods/oscilloscope/digital-phosphor-oscilloscope-dpo.php
- Pico Technology KB, Equivalent time sampling: https://www.picotech.com/library/knowledge-bases/oscilloscopes/equivalent-time-sampling (page cut off in capture; the claim used is the first section)
