# OSD SRAM hardware tests (Scope 2 garbling on unit 3)

Started 2026-11-18. Unit 3 (AWT26110003, bus 11, Rotate 180 stored). Trigger: Dan's photo of Scope 2 on unit 3 (garbled tile runs, red / green swapped vs the sim) with image `f2` (c50dc38, direct back-to-back `0x0092` stores in `S2Glyph` / `S2MapWord`).

Status 2026-11-18: direct data port stores are the default in every saver (Dan lifted the rule; T1 / T2 / T5 / T7 byte-exact). Open: Scope 2 tile garble on unit 3 is display-side, unresolved (T10 cycle verdict pending, scale-up-off test planned).

## Tools

- Firmware: `-D _AWTO_OSD_HWTEST` (`fw/test/testcmd.c`, `g_stAwtoOsdHw`). Host writes params + `ucGo` = op over debug slave 0x35; the main loop runs the op, clears `ucGo`. No test cmd number.
  - ops: 1 pattern write, 2 verify (read back + compare), 3 read 18 words, 4 CRC, 5 write buffer, 6 plane screen, 7 Scope 2 frames (saver poll held), 8 registers, 9 saver request (= VCP 0xEB).
  - write modes: 0 `ScalerOsdDataPort` per byte, 1 direct `AWTO_XFR(AWTO_R_OSD_DATA_PORT)` loop over a 54-byte chunk, 2 direct + delay loop, 3 direct unrolled triples (the map-write shape).
  - flags: EA off while writing, read M2, overlay off while writing, hold the saver poll.
  - pattern: 16-bit Galois LFSR 0xB400, 8 steps per byte (no shifted copy between neighbours), host twin `osd_hw_test.pattern()`.
  - read-back: `0x3A33[4]` sram_read_en, overlay `0x006C[0]` off for the read (regdb: "SRAM read function when OSD off"), OSD circuit `0x3A02[0]` on, 2nd read of each byte kept.
- Host: `scripts/osd_hw_test.py` (`./dev.py osd-hw-test`), log `tmp/logs/osd_hw_test.log`, dumps `tmp/osd_hw/`.
- Same ops run in the simulator (`osd_hw_test.Sim`): T7 compares the unit's SRAM with the sim's at the same Scope 2 frame.

## Test cases and PASS / FAIL criteria (stated before the runs)

| test | what | PASS |
|---|---|---|
| T1 | pattern via `ScalerOsdDataPort`, OSD hidden: Scope 2 glyph range (words 616 + 4608), Asteroids 1-bit range (397 + 3456), map range (0 + 616) | 0 bad bytes in M1 and M2 |
| T2 | same via direct loop / unrolled triples, EA on / off; then with Scope 2 shown (scaled, fetching) into the unused top (0x2000 + 4096) | 0 bad bytes; on FAIL: count, first offset, window shift (dropped / doubled byte) |
| T3 | direct + gap sweep 0..32 delay passes (only if T2 fails) | smallest gap with 0 bad bytes |
| T5 | map-shaped writes (unrolled triples) = T2 `s2map` rows | as T2 |
| T6 | plane screen: SOLID = plane A only (first 9 words), BOXES = plane B only, PLUSES = both; c1 red, c2 green, c3 blue | human: colour of each shape; stored words read back as written |
| T7 | Scope 2 SRAM (words 0..5223) at the end of frame F: unit vs sim (same image, Rotate 180) | 0 differing words |
| T4 | T7 started on top of Asteroids (no stop) | 0 differing words |
| T8 | Scope 2 held mid-frame (running, shown): every cell's tile = its tile at the end of frame F-1 or F (sim) | 0 cells otherwise |
| T9 | ladder: 2-bit ids 0..255, 16 x 16, plane A solid (Scope 2's font base) | human: all cells one solid colour; which colour |
| T10 | cycle: the ladder with digit 1..6 = write variants (same content rewritten), then Scope 2 running; 8 s each | human: which digits / the scope show glitches; machine: glyphs unchanged after a round |

## Results 2026-11-18 (unit 3, images `ohw3`..`ohw6` = main 2a290fb + `-D _AWTO_OSD_HWTEST`, 4K60 DP input, Rotate 180)

Commands: `./dev.py osd-hw-test --unit 3 [--cal] t1 t2 t4 t7 t8 rd freeze`; logs `tmp/logs/ohw_run_*.log`.

### Read-back method (decided first)
- Per-byte `bytesel` reads with the circuit on: junk (every word reads the same `48 11 30`). Dropped.
- `ScalerOsdSramGetData` method (circuit `0x3A02[0]` off, one DVS, `sram_read_en`, address set with `_OSD_BYTEALL`, 3 port reads twice, 2nd set kept): correct with the OSD hidden (T1 PASS on 30 KB of LFSR data).
- With the scale-up engine on (`0x3AC0` = Scope 2 shown) the same reads return junk: rows 0..14 read `01 10 00` / `00 00 00`, glyph words read a map word `86 0f 5a`. With `0x3AC0` = 0 for the read: `80 11 28` x 15 as written. All later reads switch scale-up off for the read (`F_RD_SU`, host default).
- Overlay on (`0x006C[0]`, SDK info pop-up) during a read: also junk; reads switch the overlay off.

### T1 / T2 / T5: write paths (all PASS, 0 bad bytes in M1 and M2)
| case | words | fw time per byte (port only, `F_REPEAT`) |
|---|---|---|
| `ScalerOsdDataPort`, hidden, Scope 2 glyphs / Asteroids / map range | 616+4608, 397+3456, 0+616 | 4.12 us |
| direct loop, hidden, EA on / off | same | 2.60 / 2.39 us |
| direct unrolled triples (map shape), hidden, EA on / off | same | 2.75 / 2.46 us (map range 3.25) |
| `ScalerOsdDataPort`, Scope 2 shown + scaled (poll held), EA on / off | 0x2000+4096 | 4.15 / 3.66 us |
| direct loop, shown, EA on / off | 0x2000+4096 | 2.69 / 2.36 us |
| direct triples, shown, EA on / off | 0x2000+4096 | 2.77 / 1.95 us |
- With the pattern refill (no `F_REPEAT`): 42..46 us/B, all PASS too.
- **Killed: back-to-back direct `0x0092` stores drop / shift bytes.** Fastest tested stream 1.95 us/B: 0 errors. **Minimum safe gap: none needed** at the fastest store rate the MCU can produce; T3 (gap sweep) not run.
- Killed: interrupts (EA) during the stream matter.

### T7 / T4 / T8: Scope 2 SRAM vs the simulator (all PASS)
- T7 held from the start, frame 3: 5224 words (rows, map, 256 glyphs), 0 differ. T7 free-running 6 s then held, frame 33: 0 differ.
- T4 Asteroids 4 s then Scope 2 (no stop), frame 3: 0 differ. **Killed: stale SRAM from a previous saver.**
- T8 held mid-frame while running (frames 31, 37): 0 of 600 cells show a tile of neither frame end. **Killed: ring slot reuse while a cell still points at it** (sim mid-frame checks at 5 instants: 0 too).
- So: what the firmware stores (map + glyphs, both memories) is byte-exact the simulator's, at frame ends and mid-frame. **Killed: glyph-id / map / SRAM-region overlaps in the stored data.**

### What was left after T1..T8 (display side)
- Colour swap: decided by T9 (below). Garbled runs: the 4096-wrap candidate killed by T9; write-during-scan disturbance is T10 (below).
- `freeze`: Scope 2 held at a frame end on the unit (SRAM checked == sim) + the sim render of that frame (`tmp/osd_hw/freeze_sim_f<N>_viewer.png`) for a photo comparison.

### T9 ladder: RESULT (Dan's photo, 2026-11-18): one uniform red rectangle, all 16 x 16 cells
- **2-bit plane order: the first 9 words (plane A) are the LOW bit** (c1 red shown; the sim had it as the high bit -> green).
- **No address wrap**: ids 193..255 (glyph words past 4096) show the same solid red. The 4096-wrap hypothesis is killed.
- Screen: 16 x 16 cells, glyph id = row x 16 + col as the viewer reads it, every glyph plane A solid, Scope 2's font base 616; c0 grey, c1 red, c2 green, c3 blue. Stored words read back as written.
- Position: asked for posH 384 (x 4 px) / posV 504 = centred; the photo shows it right of centre and low (panel position roughly (324, 250) px from the photo, turned 180). Position units with the scale-up on are not what `AwtoOsdPlaceScaleUp` assumes for a non-zero position; all full-screen savers use position 0 and are not affected. Not measured further.

### Colour fix (from T9)
- Sim: `scripts/osd_model.py` `_planes(..., lsb_first=True)` for 2-bit glyphs (4-bit order unmeasured, left MSB first); `tests/test_osd_model.py` follows.
- Scope 2: `S2MapWord` colour fields swapped: c1 = green (plane A: trace, readouts), c2 = red (plane B: graticule), c3 = green. Glyph data unchanged.
- Pac-Man: `gen_pacman_classic.py` packs the low bit plane first (ghost body = 1, white = 2 as designed); `pacman_classic_data.inc` regenerated.
- Proof in the sim (`saver_frames_md5.py --rotate --frames 6`, before = main 2a290fb model + code, after = both fixed): render md5 of frames 0..5 identical for Scope 2 and Pac-Man; state md5 differs (map colour fields / plane order), as intended. Scope 1, Asteroids, the flash screen: 1-bit only, unaffected. Realtek QC pattern (2-bit icons, Realtek's own data): its sim render now follows the hardware order.
- Unit: Scope 2 SRAM == sim (T7, frames 3 and 33) on image `ohw10` (colour fix + test code).

### Stack canary: the main-loop stalls of the test runs
- The "main loop stops, WDT kicked" stalls were the stack canary (`g_ucAwtoPokeLast` = 15 = `AWTO_WDT_S_STACK`, read while stalled): test ops that started / drew Scope 2 one or two calls deeper than the saver poll (`OP_SAVER` calling `AwtoSaverPoll`, `S2FRAMES` in a helper).
- Fixed in the test code: Scope 2 calls only at the saver poll's depth (inline in `AwtoOsdHwPoll`), the saver request served by the normal poll (host waits for `ucSaverRun`). Stack high water after T7 + T10: 0xE5 (guard 0xF0), same in repeated runs.
- Production saver poll path not changed; its own depth margin: 11 bytes at 0xE5 (includes the test ops' depth).

### T10 write-disturbance cycle (screen for Dan, left running on unit 3)
- Question: does the display show glitches while the MCU writes OSD SRAM during the scan (the photo's garbled runs, with SRAM content proven right)?
- `./dev.py osd-hw-test --unit 3 cycle` (stop: `cyclestop`, which also checks the 256 glyphs in SRAM). The ladder (solid red, 16 x 16) with a blue digit, 8 s per variant, looping; every write rewrites the SAME content, so any visible glitch is the write itself:
  | digit | variant | measured rate (unit 3, 50 s round) |
  |---|---|---|
  | 1 | static, no writes | 0 |
  | 2 | glyphs rewritten via `ScalerOsdDataPort`, 8 ms bands per main pass (Scope 2's band) | 3166 glyphs/s (171 KB/s) |
  | 3 | glyphs rewritten with direct stores | 4308 glyphs/s (233 KB/s) |
  | 4 | all 256 map words rewritten | 45 maps/s (11.5 k words/s) |
  | 5 | one glyph per frame, right after DVS (vertical blanking) | 60 glyphs/s (one per frame) |
  | 6 | address sets only, no data | 21653 /s |
  | (no digit) | Scope 2 itself, running | ~5 frames/s |
- Scope 2's own write load: ~70 glyphs + ~600 map words per frame at ~5 frames/s, well below variants 2..4.
- Machine side: after full rounds the 256 ladder glyphs read back unchanged (`cyclestop` PASS, 2 runs; one earlier run had 1 differing byte that read back correct on re-read = a read glitch; dumps now read each chunk until two reads agree and count disagreements).
- SDK (b): the SDK writes map / font SRAM while the OSD is shown with no vblank wait or circuit-off (`OsdFontPut*`, `ScalerOsdDataPort`); `_EVENT_DVS` waits only before window / position register changes (`RTD2014OsdWindow.c`, `RTD2014OsdFunc.c`) and in the read path (`ScalerOsdSramGetData`, circuit off). Write protection `0x3A33[0]`/`0x3A34` is bit masking, not a scan interlock. No double-buffer switch for SRAM areas found.
- Decision by Dan's look: digits 2/3/4 glitch and 1/5 clean = write-during-scan disturbance confirmed -> fix = Scope 2 writes in vertical blanking (variant 5 shape) or into off-screen slots; all digits clean and the scope clean = the photo's garbling is gone with the current code (image `f2` differed: rotated static tiles from the separate `s_tS2BaseRot` table, replaced since by `AwtoOsdTurn`).

### Unresolved
- Read-back: one 1-byte glitch in ~60 k bytes read (cycle run 2026-11-18); handled by double reads, cause not known.
