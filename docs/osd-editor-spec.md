# OSD editor: feature spec (from studying Realtek OsdEdit v2.66)

Own words. Source of facts: running the vendor GUI under Wine (2026-11-08), its form definitions, the three how-to PDFs. No vendor code or resources copied. Tracking: awto-ddc#89 (design system), editor issue linked there. Tool: `tools/osd_editor/`.

## 1. What OsdEdit is
- Windows GUI (Borland C++ Builder), "GMI RTD2523 OSD Edit", for the RTD2523 generation OSD. Works with the RL6449 tile format for 1 bpp (docs/boot-logo flow).
- Files: `.rgl` font library, `.rft` font-file project (list of .rgl + target .h), `.rop` OSD project, `.pal` palette.
- Windows: Font Library, Font Editor, Font File Project, OSD Project (virtual screens), Logo tool, Myson230 converters, code viewer, batch input, hotkeys.

## 2. Features seen
### Font library window
- Library types at creation: 1 bit, 2 bit, 4 bit (also "True Color" in the new-graphic dialog).
- Grid of 16x16 slots = 256 addresses; list shows name, address, size (WxH tiles). Operations: New, Insert, Edit, Delete, Batch Input, Input, Output, Close, Update / Update all, Save as bitmap / all as bitmap, Decode, Encode, Double.
- New graphic: width in tiles (x12 px), height in tiles (x18 px). One graphic = a block of 12x18 tiles. Logo how-to: max 16x16 tiles per graphic.
- Palette: 16 entries, RGB hex per entry, save / load `.pal`.
### Font editor
- Pixel grid per graphic, colour list, click-paint. Buttons: shift up / down / left / right, flip U-D, flip L-R, Clear, Inv (invert), Paste (bitmap from clipboard, must be a mono bitmap for Inv), Update (commit), Close. Grid cell size 3..9 px.
- Text stamp: pick a Windows font, X / Y, text, optional extended LOGFONT fields (height, width, escapement, orientation, weight, quality) and Draw: rasterises text into the grid.
- Ctrl+arrows move, Ctrl+Enter auto-draw.
### Input (import)
- Sources: file or "from chip" (pasted C array). Formats: Realtek font library, Realtek VLC font library, Realtek old font (1 bit, pre-2523), MST font library, HZK12 (Chinese 12x12 bitmap font), Novatek font library.
- Right-click Encode on pasted data asks width / height in tiles and shows the icon (used to view icons from SDK arrays).
### Output (export)
- Formats: Realtek font format (raw), Realtek VLC font 2523, 2523B, **Realtek HardWare VLC font 2523V**, Realtek old format, M / N / G (other vendors), HuaYa 12x18.
- Output is a `.txt`: `Palette Begin ... Palette End` block (16 RGB triples) then comma-separated hex bytes to paste into a C array.
- Font File Project: list of `.rgl`, choice of 2523 / 2523B / 2523V, "Output Info", writes one `.rft` / `.h`, and the reverse (file to RGL).
### OSD Project (`.rop`)
- RTD system tab: languages (add / del / edit), font-select address, font-base address and a Calc button, palette.
- Virtual screens: add / delete / move screens, per screen tabs for Characters (grid of glyph ids, add / up / down / del / reload / bitmap export), Windows (8 windows: left / right / top / bottom 0..1023, colour, shadow size 0..8, border colour, shadow types 1-4, 3D button 1-2, border, RGB gradient with polarity, direction, levels per gradient, step count), Rows (height, column spacing, row count, length, double width / height, character border or shadow mode: none, border, 4 shadow corners), look-up-table bit (byte 1 bit 7).
- Generates page code and selection code (C source), "Get Load Font Info", view, assign pages / languages / windows.
### Logo tool (1 bit only)
- Project name, path, source BMP, create, get palette: builds a font library project from a bitmap.
### Other
- Myson230 `.PAT` / `.BIN` converters (out of scope). Chinese UI strings inside some forms; password dialog.

## 3. Logo flow (how-to PDFs)
- File > New Font library > 1 bit > New: width = pixels / 12, height = pixels / 18 (round down).
- Paste bitmap (must come from an image viewer clipboard), Inv to match the factory colours, Update, Close.
- Output > "Realtek HardWare VLC font - 2523V" > `.txt` > paste the bytes into `_REALTEK_1BIT_LOGO0/1` (used by `OsdFontVLCLoadFont`).
- Firmware side: `OsdFuncApplyMap(WIDTH(w), HEIGHT(h))`, one `OsdFontPut1Bit(y, x, id)` per cell in raster order, window sized to the logo; black-on-white art needs the inverted bitmap.
- Limits: 16x16 tiles per graphic; the SDK logo is 70x10 tiles; an unreduced logo uses one tile per cell (no de-dup in this flow).

## 4. Cross-check against our encoder (2026-11-08)
- Drew one 12x18 1 bpp tile in OsdEdit, exported all four text formats (scratch files, not committed).
- 2523V output = 8 B nibble map + 2 B big-endian length + stream, same 16 prefix codes, LSB-first bits, nibble pairs high first as ours: our decoder reads it, tile pixels recovered.
- **MISMATCH byte for byte** vs `scripts/font_compare.vlc_encode`:
  - no END code (0xFF) in the 2523V stream, zero padding after the last symbol; the SDK blobs and our encoder both end with END;
  - nibble map tie order differs (equal counts are not sorted by value); the map is functionally equivalent;
  - the 2523 and 2523B formats use other streams (2523B: 16 B map, one nibble per byte, no length field).
- Consequence: we do not emit an OsdEdit `.txt`; we import it. Our output matches the SDK array convention (END present), see osd_logo_encode selftest.

## 5. Our coverage
| feature | status |
|---|---|
| 1 bpp 12x18 tile, 27 B, VLC encode / decode | have: `font_compare.py` (main), `osd_logo_encode.py` (branches; byte-identical to SDK blobs), `glyph_decode.py` |
| 2 / 4 bpp, 24x36 | pack layout [derived], `font_compare.Variant`; hardware bit order not measured; `osd_model.py` does not draw them |
| tile editor, paste, shifts, flips, Inv | editor: pixel paint, undo, 1/2/4 bpp, 12x18 and 24x36; shifts / flips / Inv not done |
| text stamp from a font | editor: TTF import of ASCII range; free text stamp not done |
| PNG / SVG import | editor: sheet sliced into tiles; `make_logo.py` / `osd_logo_big.py` do logo art |
| export C arrays | editor: `.inc` with VLC blobs + header; budget numbers per export |
| import SDK / OsdEdit arrays | editor: our `.inc`, OsdEdit 2523V `.txt`; SDK `tiICON_*` parse in `osd_logo_encode.py` |
| palette (16 RGB, .pal) | not done; palette is a red ramp in the editor; hardware LUT is 64 entries (`osd.md`) |
| logo flow with char-map de-dup | have: `make_logo.py`, `osd_logo_encode.py`, `osd_logo_big.py` (branches); one shared module pending (#87) |
| font SRAM budget | have: `H + 1 + W*H + 9*U <= 12288` (osd-limits.md); editor shows tiles x words and flash raw vs VLC |
| screen layout / char-map editing, windows, rows, page code | not done; screens-as-data is #89 order step 1 |
| view rendered screens | have: `osd_render.py`, `osd_catalog.py`; editor pages the catalogue |
| other vendors (MST, Novatek, Myson, HZK12) | out of scope |

## 6. Open points
- Hardware check of 2 / 4 bpp word packing and the 24x36 mode (`0x3A43[6]`) before they ship in an image.
- Decide the END-code convention for blobs the hardware loader reads (SDK has END; 2523V does not).
