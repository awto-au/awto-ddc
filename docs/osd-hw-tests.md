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

## Results

(filled per run below)
