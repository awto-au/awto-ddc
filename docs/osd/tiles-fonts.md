# Tile map, characters, fonts A / B

Text is a grid of glyph cells. One map row = one row command + N char words; a char word picks a glyph bitmap. Windows sit behind / in front: [windows.md](windows.md).

## SRAM layout (one map) [hw: our screens render with it]
| region | start | size | register |
|---|---|---|---|
| row commands | `row_base` (our code: 0) | 1 word per row, then an end word `00 00 00` | `0x3A19` row_base0 (8 bit), `0x3A1A` row_base1 |
| char words | `fs_base` = rows + 1 | 1 word per cell, rows concatenated | `0x3A0C` + `0x3A0D[7:4]` (12 bit) |
| glyph bitmaps | `font_base` = fs + cells | 9 / 18 / 36 words per 1 / 2 / 4-bit glyph | `0x3A0D[3:0]`, `0x3A0E`, `0x3A17[5:3]` (15 bit) |
- Budget: `rows + 1 + cells + 9 x U1 + 18 x U2 + 36 x U4 <= 12288` (U = unique glyphs of that depth). The 2-bit and 4-bit offsets (`0x3A21` / `0x3A22` / `0x3A23`) add to the char id before the glyph address.
- Glyph address = `font_base + words_per_glyph x (offset + id)`.

## Row command (3 bytes) [hw for our values]
- Ours: `80 (h-1) n`: B0 = `0x80` (row present; B0[7] = 0 ends the list), B1 = row height - 1 px, B2 = char count.
- Height: model reads B1[5:0] = 1..64 px [emu]; [sdk-hypothesis] `ScalerOsdRowHeight` 1..64. Taller rows add blank lines, they do not scale glyphs.
- Char count: 8 bit, <= 255 per row [spec]; 160 per row rendered clean [hw] unit 2, 2026-11-11.
- Other row-command bits (per-row double size, vbi, effect): from the RTD2662 open projects, not seen on this chip [?]: no per-row scale in the SDK, only global `0x3A0A`.

## Char word (3 bytes)
| type | B0 | B1 | B2 | evidence |
|---|---|---|---|---|
| 1-bit | `01` [7:6], id bit 8 [5], width px [4:0] | id [7:0] | fg index [7:4], bg index [3:0]; bg 0 = transparent | [hw] `0x4C` = 1-bit, 12 px: renders on units 1..3; id bit 8 ([5]) and width in saver code |
| 2-bit | `10` [7:6]; colour bits (below) | id [7:0] | colour bits | [hw] text renders (Pac-Man, Scope 2); colour packing [sdk-hypothesis] |
| 4-bit | `11` [7:6], bg colour [5:0] | id [7:0] | palette-set flags | [sdk-hypothesis]; bg index 0 is drawn: photo unit 3 (qc-osd-suite) |
| blank | `00` | length px | bg colour (6 bit) | [sdk-hypothesis] OT-7 |
- 2-bit colour packing (4 colours c0..c3, one per pixel value): `B0 = 1 c0[3] c1[3] c3[2:0] c0[2]`, `B2 = c0[1:0] c2[2:0] c1[2:0]`; c2 / c3 are 3 bit. Colour index 0 = transparent. Id is 8 bit (B0[5] is a colour bit), so 256 2-bit ids max [hw: Scope 2 / Pac-Man].
- 1-bit ids: 9 bit = 512 [hw: Asteroids uses ids to 330 of 512; B0[5] set by `AwtoOsdMap1` for cell >= 256].
- The B0 bit layout of the RTD2662 open projects (`visible / blink / fontSize / width`, B0[3:0] width) does not apply: the same bytes read as type / id8 / width here. `0x4C` in that layout = not visible + blink.
- Blank word: one word covers up to 255 px (BLANK_FONT 4..255, ALIGN 0..255) [sdk-hypothesis]; a 1920 px span = 8 words. No glyph-repeat command in the SDK or regdb.

## Glyph bitmaps
- 1-bit tile 12 x 18 = 216 bit = 9 words. Pixel order: row-major; word w = rows 2w (high 12 bit) and 2w + 1 (low 12 bit); stored bytes B2 (px 0..7), B1 (px 8..15), B0 (px 16..23), MSB = leftmost; 1 = foreground [hw: logo, text].
- 2-bit: two planes, each stored like a 1-bit tile (18 words). **First plane (9 words) = LOW bit** [hw] T9, 2026-11-18, unit 3: plane A solid = colour c1.
- 4-bit: four planes (36 words); plane order **[?] OT-1** (MSB-first from Realtek's QC icon data only [sdk-hypothesis]; the QC photo cannot tell: swapping bit order only recolours).
- Narrow glyph: char width < 12 shows a slice of the tile chosen by `disp_zone`: [pipeline.md](pipeline.md).
- 24 x 36 mode `0x3A43[6]`: 36 words per 1-bit glyph; 2- / 4-bit offset bits 8 / 7 must be 0 [spec]. Not modelled: layout unknown (OT-8).
- Pictures: [1-bit](img/text_1bit.png), [widths](img/char_width.png), [2-bit](img/text_2bit.png), [4-bit](img/text_4bit.png), [blank](img/blank_cells.png).

## Our fonts
- 7 fixed fonts (Spleen, Tamzen; cells 8 x 18 .. 5 x 8), each glyph a window inside the 12 x 18 tile, ASCII 0x20..0x7E = 95 tiles: list and menu setting in [../osd.md](../osd.md) section 2.

## Two maps: font A / font B and pop-on
- `0x3A18[3]` fontx2_en: font A rows at `row_base0` / `fs_base0` (`0x3A19`, `0x3A1B[7:4]` + `0x3A1C`), font B at `row_base1` / `fs_base1` (`0x3A1A`, `0x3A1B[3:0]` + `0x3A1D`); B's origin = set 2 + `0x3A27..29` [spec]. Picture: [font_b](img/font_b.png) [spec-model].
- [?] whether B overlaps A (transparent cells show A) or priority A vs B; scale-up over both. Test T-D; use case #195 (console title on B).
- Pop-on `0x3A18[7:6] = 11`: `display_base_sel` (`[0]`) shows base 0 or 1 [spec], fontx2 not needed (SDK QC frame 4: 2-font off, `ScalerOsdPopOn(_OSD_B)`); the sim draws base 1 at font A's place [spec-model], test T-E. Pictures: [base 0](img/pop_on_0.png), [base 1](img/pop_on_1.png) [spec-model].
- Roll-up `0x3A18[7:6] = 10`: rows scroll through the font-select base (`0x3A19`, `0x3A1B/1C`, 12 bit) [hw: console, `osd_tc_scroll`]. Base wraps at 4095: 46 steps at 160 columns corrupt the lower half after step ~25 [hw] unit 2, 2026-11-11. Not modelled.
- Font mask regions `0x3A45..4C`: hide cell rows / columns of A and B [spec] OT-20. Not modelled.
- Highlight: font colours inside windows 4_1..4_8 are replaced: [palette-blend.md](palette-blend.md).
- Row totals `0x3A3E..40`: [pipeline.md](pipeline.md).

## Map size limit
- Display fetch of a map crossing word 8192 corrupts / wraps [hw] unit 2, 2026-11-11 (160 x 48 clean; 160 x 63 wrong from map row 50 = word 8192; 160 x 72 / 90 blank). The explicit-address write / read port reaches 12287 with no hole at 4096 or 8192 [hw] unit 3, 2026-11-16 (#226). Whether the fetch limit is a silicon address width or a register effect is [?] OT-3. Rule used by `console.c`: `cols x rows + rows + 1 < 8192`.
