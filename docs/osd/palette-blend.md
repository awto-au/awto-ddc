# Palette, colours, transparency, blending

## Palette [spec]
- 64 entries x 24 bit. Write: `0x6E = 0x80 | index` (lut_acc_en + 6-bit address), then the colour bytes to `0x6F` (COLOR_LUT_PORT, write-only); our SDK call re-writes `0x6E` per entry and clears it after (5 register writes per entry) [hw: used by every screen].
- Byte order R G B per entry [hw: colours of our screens are right]. Whether the write pointer auto-increments over entries: the sim assumes it (`tests/test_osd_model.py`), the hardware is [?] OT-5.
- Effective at once, no Vsync latch listed [spec]: a mid-frame change can split one frame.
- Index 0 = black in the SDK palette; as a char background index 0 is transparent, as a foreground index 0 is opaque black [sdk-hypothesis, hw: our screens show windows through bg 0]. 1-bit chars carry only 4-bit fg / bg indices (palette 0..15); windows, 2-bit colours (3 bit for c2 / c3), blank and 4-bit bg use more bits ([tiles-fonts.md](tiles-fonts.md)).
- Picture: [palette](img/palette.png): 64 blank cells, one per index (index 0 transparent). Demo colours are ours; real values are set by the screen.
- Palette animation (blink, phosphor decay, ramps) needs no map / glyph writes: ~12 us per entry [hw: palette port in use]; effect on a scan mid-frame [?] T-K.
- No hardware blink: the char words carry no blink bit and the regdb has none [spec]; the RTD2662 blink bit does not apply.

## Alpha blending [spec]
- Level: 8 bit = `0x006C[4:2]` (bits 7:5) + `0x008F[7:3]` (bits 4:0); regdb text "000 disable, 001..111 = 1/8..7/8". The sim treats the level as the **video share** (level / 256); the direction is [?] OT-25 (the SDK menu item "Transparency" suggests it; not measured on a panel).
- Type `0x3A0A[3:2]`: 00 off, 01 windows only, 10 all (windows, char foreground, char background), 11 windows + char background.
  - [hw] unit 1, 2026-11-13 (#176): type 01 level 51: menu not see-through; type 11 see-through. Our code uses 11 (`AwtoOsdBlend`: foreground stays opaque; 01 showed nothing because our backgrounds are char cells).
  - A window pixel under a char cell with background index 0 counts as character background: at type 01 it stays opaque (same measurement).
- Per window: `ADR3 blend_en`. One global level; no per-window level.
- Pictures (checker picture behind, level 128): [01](img/blend_01.png), [10](img/blend_10.png), [11](img/blend_11.png).

## Specific colour blending (type 2) [spec-model]
- `0x3A09[7]` enable, colour index `0x3A08[3:2]` (bits 5:4) + `0x3A09[3:0]`; `0x3A08[4]` match 4 or 6 bits: every OSD pixel of that colour blends [spec]. Picture: [blend_colour](img/blend_colour.png). [?] whether it applies to all elements (windows, fg, bg) OT-19.

## Window 6 / 7 blend functions and highlight
- `0x3A21[6]` window 6 special blend, `[3:2]` / `[5:4]` types (none / foreground only / background only / both) for windows 6 / 7 [spec]; window 7 blending type 3 `0x3A09[6:5]` = 01: [windows.md](windows.md).
- Highlight windows recolour font fg / bg inside 4_1..4_8: [windows.md](windows.md).

## 4-bit background reference
- `0x3A07[2]` f4b_color_sel: 4-bit font background from B2[1:0] (0) or B0[3:0] (1) [spec]; our decode uses B0[5:0] [sdk-hypothesis; bg drawn incl. index 0: photo unit 3].
