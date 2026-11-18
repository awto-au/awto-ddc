# OSD SRAM hardware tests (Scope 2 garbling on unit 3)

Started 2026-11-18. Unit 3 (AWT26110003, bus 11, Rotate 180 stored). Trigger: Dan's photo of Scope 2 on unit 3 (garbled tile runs, red / green swapped vs the sim) with image `f2` (c50dc38, direct back-to-back `0x0092` stores in `S2Glyph` / `S2MapWord`).

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

### What is left (needs the screen)
- The photo's faults are therefore in how the display engine shows correct SRAM:
  - colour: sim plane A (first 9 words) = MSB -> c2/c3 (green), plane B -> c1 (red). Photo: trace (plane A) red, graticule (plane B) green = the hardware takes plane A as the LSB (or c1 / c2 swapped; the same picture). T6 screen decides it in one look.
  - garbled runs: photo shows extra cursor dots / axis-tick tiles in wrong columns, dark / grey / striped cells. Candidates, not decided: (a) display fetch disturbed while the MCU writes the SRAM (the scale-up engine shares the read path: reads return the word the display fetched) = transient, gone on a frozen frame; (b) display addressing of 2-bit glyphs differs from the sim (e.g. a 4096-word wrap: ids >= 193 end past word 4096) = also on a frozen frame.
  - `freeze`: Scope 2 held at a frame end on the unit (SRAM checked == sim) + the sim render of that frame as the viewer sees it (`tmp/osd_hw/freeze_sim_f<N>_viewer.png`). Same picture (colours aside) = (a); garbled = (b).

### T9 ladder (screen for Dan, left on unit 3 at the end of the run)
- `./dev.py osd-hw-test --unit 3 ladder`: 16 x 16 cells, 2-bit glyph id = row x 16 + col as the viewer reads it (map turned for Rotate 180), every glyph plane A solid, plane B 0, Scope 2's font base 616 (same glyph word addresses). c0 grey, c1 red, c2 green, c3 blue. Stored words read back as written (unit, 2026-11-18).
- Expected as the sim models it: all 256 cells solid GREEN (`tmp/osd_hw/ladder_sim_viewer.png`; the sim draws it off-centre, its known scale-up offset).
- Plane order: all cells RED = the hardware takes plane A as the LSB (colour swap of the photo).
- Address wrap: the cells from some id on striped / other colours. At a 4096-word wrap the first broken id is 193 (row 12, col 1): `ladder_sim_viewer_if_wrap4096.png`.
- Support for the wrap from the photo: Scope 2 frame 33 rendered with a 4096 wrap (`freeze_sim_f33_viewer_if_wrap4096.png`) shows the same kinds of fault as the photo: striped blocks (map words fetched as pixels), stray axis-tick / cursor-dot / text fragments in other cells, and a broken "1ns" label read as "1r" at the bottom centre as in the photo. At frame 31 the ring uses ids 54..122 only and the wrap render is clean: the faults come and go with the ring position.

### Unresolved
- Twice the main loop stopped (heartbeat 0/s, WDT kicked, unit alive on the debug ISR) right after `S2FRAMES` + the next op (once Scope 2 not started: test bug, fixed by guard `AWTO_OHW_ST_NO_S2`; once a READ with the scale-up engine on, before `F_RD_SU`). Not reproduced in 6 later runs. Recovery: `./dev.py reset --unit 3`.
