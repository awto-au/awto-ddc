# Scope 2 corrupted on the default image (unit 3)

Trigger: Dan's photos 2026-11-19 (Scope 2 via VCP 0xEB, default image: MCU 350.8 MHz, flash 116.9 MHz, direct OSD port stores). Default clocks stay (Dan, 2026-11-19); the fix is at 350.8 / 116.9.
Measured 2026-11-19 on unit 3 (AWT26110003, bus 11, Rotate 180, 4K DP input), base 244384a + `-D _AWTO_OSD_HWTEST`, `./dev.py osd-hw-test --unit 3 --cal t2 t7` (method: `docs/osd-hw-tests.md`; T7 = OSD SRAM map + glyphs at a Scope 2 frame end vs the sim render of the same frame).
Draft issue text: `tmp/scratch/issue-scope-corrupt.md` (not posted; public repo).

## Cause
- Direct `AWTO_OSD_PORT` stores (`AWTO_XFR(0x0092)`, `RL6449_Project.h`) arrive too close together for the OSD SRAM port while the OSD is shown. The wrong bytes are in SRAM itself (T7 reads them back), so it is a write-side loss, not a scan-side glitch.
- Failing shape: map words (`S2MapWord`, `AwtoOsdWord`): `ScalerOsdAddrSet` then 3 back-to-back stores. Unit words have a byte lost / duplicated (e.g. unit `265653`, sim `862653`; unit `254553`, sim `862553`); the third byte (colour) stays right.
- Glyph writes (a loop, about 12+ cycles between stores) are clean; T2 "direct triples shown" (12 KB at 0.49 us/B) fails with 475..516 bad bytes in M1 and M2 at 350.8 MHz.
- Why not seen at 87 MHz (T7 PASS 2026-11-18): spacing scales with the MCU clock.
- Not the cause: flash clock (350/70 control below), flash reads of font / code, saver write ordering (held frame fails too).

## Results (T7, Scope 2 SRAM 5224 words; differing words)
| image | MCU / flash MHz | port write | T7 held (frame 3) | T7 free-run |
|---|---|---|---|---|
| sc-hw350 | 350.8 / 116.9 | direct, no gap (default today) | 83 map | 299 map + 3 glyph (frame 190) |
| sc-hw175 | 175.4 / 70.2 | direct, no gap | 49 map | 130 map (frame 62) |
| sc-hw350sdk | 350.8 / 116.9 | `ScalerOsdDataPort` (SDK call) | 0 | 0 (frame 169) |
| sc-nop2 | 350.8 / 116.9 | direct + 2 nops after each store | 38 map | 249 map |
| sc-nop8 | 350.8 / 116.9 | + 8 nops | 22 map | 59 map |
| sc-nop12 | 350.8 / 116.9 | + 12 nops | 6 map | 39 map |
| sc-nop16 | 350.8 / 116.9 | + 16 nops | 0 | 0 (frame 182) |
| sc-nop24 | 350.8 / 116.9 | + 24 nops (fix) | 0 | 0 (frame 179), repeated once: 0 |
- Control clean: SDK port call at 350.8 / 116.9 (so the flash clock and the clock are not the cause: the same image clocks fine with spacing). 175.4 / 70.2 is not clean with direct stores (fixed nop count = twice the time at 175, still 0 gap fails).
- Flash control: see "350 / 70" below.
- Smallest passing spacing 16 nops (about 16 machine cycles = 0.18 us at 350.8 MHz); 12 fails. Fix uses 24 (1.5x).

## Fix (in this branch, not merged)
- Superseded: `AWTO_OSD_PORT(v)` is a single store; spacing = `FFF1` sel 12 set at MCU init (`docs/osd-port-loss.md`). Every saver goes through the macro.

## Not covered
- Scope 1, Asteroids, Pac-Man: no SRAM-vs-sim check exists for them (T4 only checks Scope 2 after Asteroids); they share the macro and word-write shape, so the same loss is expected before the fix; fixed by the same macro.
- Nobody looked at the screen: whether the photographed bars are fully explained by the lost bytes is not proven (SRAM is clean after the fix; the display itself has no capture).
