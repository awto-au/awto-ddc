# JXC 4K monitor: boot-logo hunt (static analysis)

Status: logo NOT located. This file records what is established, what is ruled out, and the next steps.
Tags: [fw] read from our dump/disassembly, [spec] regdb RTD2795T-CG, [guess], [?] unknown.
Dump: `~/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin` (1 MiB). Nothing was written to the monitor or flash.
Tools: `scripts/dis51.py` (linear 8051 disassembler), `scripts/logo_decode.py` (tile sheet renderer), `scripts/vlc_probe.py` (OSD VLC stream probe).
Renders (not in git): `~/vendors/realtek/analysis/logo/` (`contig_20.png` = whole bank 0 font, `font4bpp.png`).

## Flash occupancy (premise "banks 0-6 only" is incomplete)
| range | content | tag |
|---|---|---|
| 0x00000-0x028C5 | common code, identical in all banks; banked-call thunks, Keil startup, IRQ vectors | [fw] |
| 0x0N28C6-0x0NFFFF, N=0..6 | per-bank overlay (data tables first, then code) | [fw] |
| 0xE0000-0xE2863 | bank 14: VLC-compressed OSD font data + 1025-entry offset table (same shape as bank 3 tables) | [fw] shape / [guess] purpose |
| 0xE00B4-0xE00D3, 0xE01B4-0xE01C1, 0xE01FC-0xE020A | small tables | [fw] |
| 0xFB000-0xFCFFF | differs between the 3 dumps (3618 bytes differ) = settings / EEPROM emulation | [fw] |
| everything else >= 0x70000 | 0xFF | [fw] |
- Bank 6 (0x60000-0x66964, then 0xFF) is code, not bitmap: OSD register driver, key scan, SPI-flash command engine (FFF3-FFFC) [fw]. Its "97% used" is code density.

## Banking [fw]
- Each bank file is a full 64 KB overlay; bank-local helpers differ per bank (e.g. 0x5ED9 is a different function in bank 1 and bank 6).
- Cross-bank call: `MOV DPTR,#target ; LJMP thunk`, thunks spaced 0x12 from 0x0429 (bank 0); bank 6 thunk = 0x0495. 112 bank-6 thunks (e.g. 0x1077 -> 0x504D, 0x10D1 -> 0x661D) sit in common code.
- SFR 0x49 = current bank, 0xFFFF = bank register (stubs at 0x32000-style `MOV 49h,A ; MOVX @DPTR,A`).

## How the OSD is driven [fw]
- Scaler regs are memory-mapped at XDATA 0x0000-0x3FFF (not via FFF4/FFF5, which are SPI-flash controller regs). OSD ports 0x0090-0x0094 and 3A0C/0D/0E (font_base/fs_base) are touched ONLY by bank 6 code.
- Bank 6 OSD primitives (named in `re/jxc-4k/ghidra_names_bank6.tsv`): `osd_enable_set` 0x5E35, `osd_port_write_byte` 0x6029, `osd_port_read_byte` 0x64D9, `osd_set_font_bases` 0x504D, `osd_lut_write` 0x65B7, `osd_fill_words` 0x5ED9.
- No OSD font-SRAM bulk-load loop found in banks 0-6 (writes to 0x92 are single-byte/word helpers). Font download path unresolved [?].
- regdb has no splash/blit/bitmap-DMA register; only OSD windows/font/LUT and the OSD scaler (OSD_SU, page 3A 0xC0-0xCB) [spec]. A splash therefore has to be an OSD composition (font tiles + window) [guess, strong].

## Font tile format (bank 0) [fw]
- Tile set at 0x028C6, 27 bytes per tile (period 27 measured; digits legible), index = char code: tile 0 blank, 0x01-0x0A = '0'-'9', 0x0B = 'A'.. (strings at 0x077xx use this: `0c 1c 13 11 12 1e 18 0f 1d 1d` = BRIGHTNESS).
- Pixel format most consistent with the render: 4 bpp, 6x9 px per tile, MSB-nibble first [guess]; 2 tiles = one 12-px CJK glyph (string bytes 0x40+ come in pairs/triples).
- ~712 tiles to 0x077xx; four solid-white tiles (progress bar) repeat; no logo-like region in the sheet [fw].
- Menu text = 0xFF-terminated tile-id strings from 0x07700. No run of >= 10 consecutive ids anywhere in banks 0-6, so no tile-map row of a large logo [fw].

## Other data regions checked, none is a logo [fw]
- bank 3 0x328C6-0x3A000: 12+ copies of a 1025-entry 16-bit offset table (0..0x3FF0) + VLC data = large font (CJK) [guess].
- bank 2 0x228C6-0x26900: VLC data (`24 49 92` repeats), no own index table found [guess: font/icons].
- bank 6 0x628C6-0x62FB2: 9 distinct 197-byte high-entropy blobs, addressed through the 15-entry pointer table at 0x62FB3 (`ff hi lo`, spacing 0xC5) via `ptr_table_lookup` 0x661D; only caller found = bank 5 0xFAAE [fw]. Format unknown (not a plain RGB palette) [?].
- bank 1: string pools + EDID (`4K MONITOR`, `demoset-1`) at 0x13A00; bank 5: timing tables [fw].
- Firmware contains no "Dahua"/"JXC"/"logo" string [fw]. EDID name `demoset-1` suggests a Realtek demo-derived image [guess].

## VLC compressed fonts [spec]
- OSD compression: 4 bit/symbol prefix code `0,100,1010,1011,1100,11010,11011,11100,111010,111011,111100,111101,1111100,1111101,1111110,11111110`, END = `11111111`; symbol values programmable in 0x3A0F-0x3A16; enabled by 0x3A17[0] (+hw rotate 0x3A0B).
- Firmware writes to 0x3A0F-0x3A16 not found by a literal `MOV DPTR,#3A0x` scan, so the value map is unknown; the identity-map decode of bank 14 (`vlc_probe.py`) gave noise [fw]. Tile boundaries and map are unresolved [?].

## Answers to the brief
1. Logo data: not found. Best remaining candidates, in order: bank 14 0xE0500-0xE2863 (unreferenced by any bank 0-6 code found so far), bank 2 0x23000-0x26900, bank 6 197-byte blobs. [?]
2. Drawing code: OSD-path (no blitter exists in regdb) [spec]; driver in bank 6 [fw]; caller that composes the splash not found.
3. Constraints: unknown until the data is found. Checksum: no 16-bit sum over the image found; image has no header (0x15 = 0xFF, vectors at 0x00-0x2F) [fw]; a sum loop search in boot code was not completed [?].
4. Patch plan: blocked. Generic safe procedure once the sector is known: fresh dump, diff against `jxc-4k-flash-bus20.bin`, patch only the 4 KB sector(s) (0x1000 aligned) holding the data, keep original sector bytes to revert, read back, re-diff.

## Next steps
- [ ] Find who reads flash >= 0x70000: search all banks for `MOV DPTR,#0xE0xx`-style or SPI-flash-engine reads (FFF3/FFF6-FFFA, bank 6 0x4445) with addresses in 0xE0000; the SPI engine routine at bank 6 0x4445 is the only flash reader seen.
- [ ] Locate the VLC value-map writes (0x3A0F-0x3A16, may use `INC DPTR` chains) to decode fonts.
- [ ] Hardware route (read-only): power-on with OSD font SRAM/window dump via `rtd_osd.py` read-back right after boot to capture the splash window setup (WIN0 measured 0,4 -> 156,80; font_base 0x3F1, fs_base 0x019 in `osd.md`).
- [ ] Confirm with Dan that the splash is the firmware's (it may come from another chip on the board).

## Splash confirmed by Dan (2026-11-04)
- The boot splash IS a two-colour BLACK Dahua logo on a WHITE background [user].
- Two colours => drawable by the OSD engine (low-colour tile/font path), NOT a separate colour boot image.
  So it IS produced by this scaler firmware, consistent with the agent finding no colour bitmap.
- Prime suspect for the logo data: bank 14 (0xE0000-0xE2863), which is VLC-font/data shaped and undecoded,
  drawn via the OSD VLC value-map (regs 0x3A0F-0x3A16, writes not yet located). Bank 0 tile font is only the
  small menu glyphs (no logo).
- Next RE: decode the VLC value-map + bank14; find the splash composer (who enables the window + loads these
  tiles at boot); then the logo is a tile/bitmap patch in that region + possibly the font SRAM.
- A full power-cycle (not just ISP reset) is the reliable way to see the splash.
