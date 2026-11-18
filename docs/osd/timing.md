# Vsync, double buffer, write timing, read-back

## Double buffer [spec]
- Global enable `0x93[7]` db_enable (reset 1). Fields marked RW4 (delays, font delays, highlight colours, rotation, `osd_en`, 24x36) latch at Vsync rising; reads show the pending value immediately.
- Window position / size words latch at Vsync with the global double buffer on; the `win_en` byte (`ADR3` HSB) is never double buffered.
- SRAM words (map, glyphs) never latch: a write is visible at once; use pop-on ([tiles-fonts.md](tiles-fonts.md)) for tear-free maps.
- Our screens: `AwtoOsdScreenBegin()` switches the global double buffer off, so window moves apply immediately (tearing possible, no waiting).
- Our screen helpers address with `ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, addr, _OSD_WITHOUT_DB)`.

## Write timing
- [hw] T7 / T8 (unit 3, 2026-11-18): what the firmware stores (map + glyphs, both memories) equals the sim's byte for byte at frame ends and mid-frame (0 of 5224 words differ; 0 of 600 cells show a tile of neither frame).
- [?] T10 cycle (unit 3, 2026-11-18; ladder of 256 red glyphs rewritten with identical content, 8 s per variant): whether the display glitches while the MCU writes during the scan. The look is Dan's; no result is recorded yet. Reading the screen: digits 2 / 3 / 4 glitch and 1 / 5 clean = write-during-scan disturbance (fix: write in vertical blanking or into off-screen slots); all clean = the photo's garbling was the old code.
  - Status (docs/osd-hw-tests.md, 2026-11-18): the Scope 2 tile garble on unit 3 is display-side and unresolved; a scale-up-off test is planned.
  - Rates measured [hw]: glyph rewrite 3166 / s (`ScalerOsdDataPort`) / 4308 / s (direct); all-map rewrite 45 / s; one glyph per frame 60 / s.
- The SDK writes map / font SRAM while shown with no vblank wait; `_EVENT_DVS` waits only before window / position register changes and in its read path [sdk-hypothesis].
- Register-width timing: `SCA_INF_PERIOD`, `SCA_WR_INTRVL`, `CYCLE_GATING` change every register access time [spec]: T-K; sweep tool, OSD clock knobs and the DDR plan: [osd-write-sweep.md](../osd-write-sweep.md); per-path cost: [path-cost.md](path-cost.md).

## Read-back
Conditions that decide whether a read returns the stored word:
| condition | result | evidence |
|---|---|---|
| recipe: circuit off (`0x3A02[0] = 0`), wait one DVS, `0x3A33[4]` sram_read_en = 1, set address all-bytes, read 3 bytes twice, keep the 2nd set | exact, 30 KB of LFSR data | [hw] T1 2026-11-18 |
| scale-up engine on (`0x3AC0` non-zero) | junk (rows read `01 10 00`, glyphs read a map word) | [hw] 2026-11-18 |
| overlay on (`0x006C[0]`, an SDK pop-up) | junk | [hw] 2026-11-18 |
| per-byte bytesel reads with the circuit on | junk, every word `48 11 30` | [hw] 2026-11-18 |
| probe: circuit on, scale-up off, overlay off, M1 / M2 selected by `0x93[5]`, 2nd read | marker words correct to `0x2FFF` | [hw] 2026-11-16 (#226) |
| circuit off for a font write | write ignored | [hw] 2026-11-16 |
- The two circuit-on rows (works on 11-16, junk on 11-18) disagree: what differs is the byte select (probe vs per-byte reads) or leftover scale-up / overlay state. [?] OT-4: repeat T1's read with circuit on, scale-up off, overlay off, all-bytes address.
- Window SRAM reads back with no special condition [hw] 2026-11-04.
- One 1-byte read glitch per ~60 KB read; handled by reading each chunk until two reads agree [hw] 2026-11-18, cause [?].
- Host tools: `scripts/osd_hw_test.py` (`./dev.py osd-hw-test`), firmware `-D _AWTO_OSD_HWTEST`, `scripts/osd_sram_probe.py`.
- The earlier all-zero font reads over ISP (2026-11-04) were the circuit being off, not a chip limit.
