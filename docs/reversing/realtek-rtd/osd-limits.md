# RL6449 / RTD2795T OSD: size limits and the sim renderer (#63, #46)

Tags: `[sdk]` Kingdomwhisky RTD-Scaler-TEST Kernel/User sources; `[regdb]` re/regdb RTD2795T-CG; `[sim]` scripts/osd_render.py; `[guess]`.
Builds on `osd.md` (ports, windows) and `osd-font-download.md` (VLC, char words).

## Limits
- OSD SRAM = 12288 words of 24 bit [sdk: `_OSD_SRAM_SIZE`, Kernel/Common/RL6449_OSD_Gen_Option.h]. Read-back on hardware: not yet measured.
- Layout [sdk OsdFuncApplyMap]: row commands at 0..H-1 (`80, height-1, width`), end word at H, char commands from `fs = H+1` (W*H words), glyphs from `font_base = fs + W*H` (9 words per 1-bit 12x18 glyph).
  - Budget: `H + 1 + W*H + 9*U <= 12288` (U = unique tiles).
- 1-bit glyph id: B1 (8 bit) + B0 bit5 (+256) = 512 ids [sdk ScalerOsdChange1BitColorFont256_511 writes B0 = 0x60 | width]. `OsdFontPut1Bit` hard-codes B0 = 0x4C (ids 0..255).
- Char command B0: [7:6] type (01 = 1-bit, 10 = 2-bit, 11 = 4-bit), [5] id bit 8, [4:0] width px. B2 = fg<<4 | bg; bg index 0 = transparent, fg index 0 = opaque black (palette 0 is black).
- Register widths [regdb]: fs_base 12 bit, font_base 15 bit, row_base 8 bit, row command char count 8 bit, window / position fields 12 bit, font A delay 12 bit.
- Scale: `0x3A0A[1:0]` = x2 width/height of the whole OSD (windows too). SDK default `b1OsdDoubleSize` = _OFF (RTD2014NVRamOsd.c), sim agrees (0x3A0A = 0 when the logo is drawn). The issue's "2x" is unverified on hardware.
- Scale-up engine `0x3AC0..CB` [regdb, sdk RL6449_Series_OsdScaleUp.c]: factor 6 bit = `Xi/Xo * 64` (V `0x3AC2`, H `0x3AC3`), region start/size 12 bit, boundary mode 00/01/10. SDK QC tests 1.5x, 2x, 2.5x, 3x (`RL6449_Series_QC_OSD.c`). Comment in `OsdScaleUpOnOff.c`: only valid in even-odd mode. Behaviour on top of the x2 double is untested [guess]. Not used by the logo build.
- Font mode 24x36 `0x3A43[6]`: 36 words per 1-bit glyph, 2-/4-bit offsets must be 0.
- Position: delay x step (4 px; 1 px when `0x3A06[4]`) x scale [sdk OsdDispSetPosition; sim: centred logo at 1x = delay 375*4 = 1500, 990 = (3840-840)/2, (2160-180)/2].
- Burst-DMA font download [sdk ScalerBurstWrite]: FFF3 bit3 = data burst (bit5 = no host-address increment), count FFF9/A, source bank FFF6 + addr FFF7/8, host reg = page(0x9F):FFF4. Map bytes go to 0x3A0F.., stream bytes to 0x92; decoded at destination `font_base + 9*offset`.

## Hardware read-back of the SRAM size (for the firmware agent)
- Not run by this agent. Unit must be halted in an ISP session (OSD SRAM persists). `rtd_osd.Osd.read_word` reads one byte plane; `0x3A33[4]` (sram_read_en) must be 1 and the first read is discarded ("send 2 times, the 2nd is right" [regdb]).
- Command (bus = the unit's I2C bus; the OSD is halted by the ISP session, the monitor reboots afterwards unless `--keep`; ops run left to right):
  `python3 scripts/rtd_osd.py BUS --keep wr:0x3A33=0x10 osdw:font:0x0000=A1,A2,A3 osdw:font:0x2FFF=B1,B2,B3 osdw:font:0x3000=C1,C2,C3 osdw:font:0x3001=D1,D2,D3 osdw:font:0x3FFF=E1,E2,E3 osdr:font:0x0000 osdr:font:0x2FFF osdr:font:0x3000 osdr:font:0x3001 osdr:font:0x3FFF osdr:font:0x0000`
  - `wr:0x3A33=0x10` = sram_read_en; the first read after an address set is discarded, so each `osdr` is read twice by the firmware agent if the first value looks stale.
  - SRAM end = first marker address that does not read back its own marker. 0x2FFF = last word if the size is 12288. Aliasing (a high address reading A1,A2,A3 or the last marker overwriting word 0) means the SRAM is smaller than the address range.
  - If every font read returns 0 (as on 2026-11-04), repeat with window SRAM (`osdw:win`) only to check the read path itself; then the size stays the SDK constant 12288.

## Renderer (scripts/osd_render.py, scripts/osd_model.py)
- Runs an image in fw_sim, taps OSD port / palette / burst DMA, renders 3840x2160 PNG over grey. Tests: tests/test_osd_model.py.
- Validated: boot logo shape and colour of image wb-port3 = what Dan sees on unit 3 (2026-11-07, "looks correct"). Scale and position not compared yet.
- Pop-up text: prop-font glyph bursts (27 B from XRAM, FFFC bit5) read all zeros in the sim (source buffer 0xEA37 empty), so info/debug pop-up text rows render blank; icon, windows and menu are fine. Cause not found yet.
- Not modelled: window border/shadow/gradient, 2-/4-bit fonts, font B, rotation, alpha direction (255 assumed opaque), FB-shift, pipeline position offsets.

## Blank command and glyph repeat [sdk] (#226 audit, 2026-11-16)
- Blank = one 3-byte char-map word: B0 = type (`_OSD_BLANK_FONT` / `_OSD_BLANK_ALIGN`, `enum & 3`), B1 = pixel length (BLANK_FONT 4..255, ALIGN 0..255), B2 = background colour (6 bit) [sdk `ScalerOsdBlankFont`, `SRAM/OsdBlankFont.c`]. A 1920 px empty span = 8 words (24 B), not 160 glyph entries.
- No glyph-repeat command in the SDK API (no function or field for "this glyph N times"): a fill is N map words. Not found in regdb either.

## Font SRAM read-back on unit 3 [measured 2026-11-16, not conclusive]
- Font and map SRAM are TWO memories, M1 and M2: writes with `0x94[3:2]` = 10 go to both ("M1 and M2 SRAM must be written at the same time"); `0x0093[5]` `sram_read_select` picks the one that is read (0 = M1, 1 = M2) [regdb]. `rtd_osd.py` osdr never sets it.
- Test 1 (read-back with `0x0093[5]` left at 0, OSD on and off, markers `<addr hi>,<addr lo>,A5` at 0x0000, 0x0FFF, 0x1000, 0x1FFF, 0x2000, 0x2FFF, 0x3000, 0x3FFF, 0x4000, 0x7FFF): every read 00 00 00. This did NOT show that font read-back is impossible.
- Test 2 (`wr:0x0093` = 0x80 / 0xA0, then with the global double buffer off `0x0093` = 0x00 / 0x20): M1 and M2 return non-zero words, none of them our markers; M2 reads at 0x0000 and 0x4000 are nearly identical (b1, b2 equal, b0 differs by a bit), so the read address may wrap at 14 bit. The values look like the firmware's own map / font data (the SRAM persists across the ISP session); our writes did not read back at any of the ten addresses.
- Window SRAM (`osdw:win:0x0100/0x0101`) writes and reads back correctly.
- Open: why font writes do not read back (write needs both M1 and M2 written the same way? double buffer, `osd_en`, MCU halt?), and whether the read address really wraps at 14 bit. Until that is explained the SRAM extent is the SDK constant 12288 words, and the 8192 question needs the display-fetch test (glyphs / map markers at high addresses on screen).
