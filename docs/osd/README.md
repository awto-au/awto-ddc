# OSD manual (RL6449 / RTD2795T)

Reference for the on-chip OSD: how it works, every register group, how our code uses it, what is proven.
Pictures come from the simulator (`python scripts/osd_manual.py`, check: `--check`, pytest `tests/test_osd_manual.py`); they show what the model draws, not a photo.

## Evidence tags (order: hw > databook > spec > emu > sdk-hypothesis)
| tag | meaning |
|---|---|
| `[hw]` | measured on our units (test id / issue / date given) |
| `[databook]` | Synopsys DW8051 v3.2a, MX25L8006E |
| `[spec]` | regdb `re/regdb/RTD2795T-CG.tsv.gz` text (register names, bits, descriptions) |
| `[spec-model]` | the sim draws it from a `[spec]` reading; not seen on hardware; the settling test is named |
| `[emu]` | our sim model only (`scripts/osd_model.py`) |
| `[sdk-hypothesis]` | Realtek SDK source / comments (Dan, 2026-11-18: the SDK is not reliable; a lead to test, never a fact) |
| `[?]` | unknown; the test that settles it is named ([open-items.md](open-items.md)) |

Conventions: awto-dan `docs/embedded/reversing/README.md`. Names: say Dahua firmware (factory image of the units), Realtek SDK menu, awto menu; never bare "vendor".

## The hardware on one page
- **Draws on the display side** from on-chip OSD SRAM while each pixel goes to the panel; no DDR, no input clock: [pipeline.md](pipeline.md).
- **OSD SRAM** = 12288 words x 24 bit (`0x0000..0x2FFF`), two memories M1 / M2 written together [hw, 2026-11-16, #226]. Holds, in this order by our convention:
  1. row commands (1 word per text row) + end word, 2. char words (1 word per cell), 3. glyph bitmaps (9 words per 1-bit 12 x 18 tile, 18 per 2-bit, 36 per 4-bit): [tiles-fonts.md](tiles-fonts.md).
- **Window control SRAM** (`sram_sel` 00) is a separate address space: 26 windows x 4..11 words: [windows.md](windows.md).
- **Palette** = 64-entry x 24 bit LUT (`0x6E` / `0x6F`); everything references 6-bit indices (1-bit chars only 4 bit): [palette-blend.md](palette-blend.md).
- **Access** = 5 scaler registers `0x90..0x94` (address MSB / LSB, data, misc, write option); every OSD word is 3 bytes B0 B1 B2; address auto-increments per data access [hw]: [glyph-load.md](glyph-load.md).
- **Frame registers** `0x3A00..0x3A8F` (position, bases, fonts A / B, special modes, blend type, rotation, mask, highlight, round tables) and **scale-up** `0x3AC0..0x3ACB`: [pipeline.md](pipeline.md), [scale-up.md](scale-up.md).
- **Compose order** (back to front) [spec-model]: video, windows below the font, font map(s), windows set "higher than font", then alpha blend by `0x3A0A[3:2]` and the global level; scale-up and mask windows act on the result.
- No framebuffer, no line / shape engine, no sprite engine: everything is glyph cells + windows + a second map [spec].

## Feature index
Status = best evidence for the behaviour shown. Gaps are visible here: a row without a picture says why in its chapter.

| feature | registers | picture | status |
|---|---|---|---|
| display pipeline, clocking | `0x01DC[3]`, `0x002B`, `0x3A02[0]` | - | [hw] OSD independent of input timing; mechanism [?] |
| position, delay sets, step | `0x3A00..06`, `0x3A24..29`, `0x3A2C/2F`, `0x3A32` | [position](img/position.png) | [hw] set 1; set 2 / fine tune [?] OT-6 |
| display zone (narrow chars) | `0x3A02[2:1]` | [mid](img/zone_0.png) [left](img/zone_1.png) [right](img/zone_2.png) | [spec-model] T-C |
| 1-bit chars | char B0 `01xxxxxx` | [text_1bit](img/text_1bit.png) | [hw] |
| char width / proportional | char B0[4:0] | [char_width](img/char_width.png) | [hw] 12..6 px; < 4 px [?] T-C |
| 2-bit chars | char B0 `10`, `0x3A21[1]`, `0x3A22` | [text_2bit](img/text_2bit.png) | [hw] plane order T9; colour packing [sdk-hypothesis] |
| 4-bit chars | char B0 `11`, `0x3A21[0]`, `0x3A23`, `0x3A07[2]` | [text_4bit](img/text_4bit.png) | [sdk-hypothesis] plane order [?] OT-1 |
| blank cells | char B0 `00` | [blank_cells](img/blank_cells.png) | [sdk-hypothesis] OT-7 |
| 24 x 36 tile mode | `0x3A43[6]` | not modelled: pixel layout unknown | [?] OT-8 |
| blink / attributes | none | - | none on this chip [spec]; blink = palette toggle |
| palette, colour indices | `0x6E`, `0x6F` | [palette](img/palette.png) | [hw] writes; auto-increment [?] OT-5 |
| window matrix (26 windows) | window SRAM `0x100 + 4n`, `0x200 + 4n` | table in [windows.md](windows.md) | [spec] |
| window solid colour | `WINn_ADR1..3` | [win_solid](img/win_solid.png) | [hw] |
| shadow (4 types) | `ADR0/3` eff_opt 0..3 | [win_shadow](img/win_shadow.png) | [spec-model] OT-9 |
| 3D button | eff_opt 4, 5 | [win_3d](img/win_3d.png) | [spec-model] OT-9 |
| border | eff_opt 7 | [win_border](img/win_border.png) | [spec-model] OT-9 |
| rounded corners 8 / 16 / 32 px | `ADR10`, `0x3A60..0x3A8B` | not modelled: model radius differs from the regdb size codes | [spec] OT-10 |
| gradient, level, step | `ADR0/3/4/6/8/9` | [win_gradient](img/win_gradient.png) | [hw] photo of QC frame 2 / 3 (qc-osd-suite) |
| gray level | `ADR9[1]` | [win_gray](img/win_gray.png) | [spec-model] OT-11 |
| chessboard | `ADR5` (8, 9), `ADR4` (4_x, 5_x), `ADR9` step | [win_chess](img/win_chess.png) (WIN8) | [spec-model] T-B |
| grid lines (WIN2 / 3 / 4) | `ADR7/8`, `0x3A35..37` | [win_grid](img/win_grid.png) | [hw] QC frames 2 / 3 match; pitch unit [?] T-A |
| special colour mask | `ADR9[3:2]` | [win_mask_colour](img/win_mask_colour.png) | [spec-model] OT-12 |
| window rotate | `ADR9[0]` | not modelled | [?] OT-13 |
| zero-width window | window words | not modelled | [hw] photo 2026-11-15 (#215): runs to the edge; rest [?] OT-14 |
| window vs font priority | `0x3A07[1:0]`, `0x3A08[7:5]`, `ADR3[1]` | [win_priority](img/win_priority.png) | [spec-model] OT-15 |
| window 7 mask region | `0x3A09[6:5]`, `0x3A07[3]` | [win7_mask](img/win7_mask.png) | [spec-model] OT-16 |
| window 6 / 7 blend functions | `0x3A21[6:2]`, `0x3A09[6:5]` | modelled, no picture yet | [spec-model] OT-16 |
| highlight windows 4_1..4_8 | `0x3A2A..0x3A56` | [highlight](img/highlight.png) | [spec-model] OT-17 |
| video highlight window + border | `0x0060/0x0061`, `0x006C[6]` | not modelled | [spec]; draws an RGB border: OT-18 |
| alpha: windows only | `0x3A0A[3:2]=01`, `0x006C[4:2]`, `0x008F[7:3]` | [blend_01](img/blend_01.png) | [hw] 01 showed nothing under char cells |
| alpha: all | `=10` | [blend_10](img/blend_10.png) | [spec-model] |
| alpha: window + char bg | `=11` | [blend_11](img/blend_11.png) | [hw] unit 1 2026-11-13 (#176) |
| specific colour blending | `0x3A08`, `0x3A09[7,3:0]` | [blend_colour](img/blend_colour.png) | [spec-model] OT-19 |
| font mask regions A / B | `0x3A45..4C` | not modelled | [spec] OT-20 |
| second map (font B), delay set 2 | `0x3A18[3:1]`, `0x3A19..1D`, `0x3A27..29`, `0x3A03..05` | [font_b](img/font_b.png) | [spec-model] T-D (#195) |
| pop-on page flip | `0x3A18[7:6,0]` | [pop-on 0](img/pop_on_0.png) [pop-on 1](img/pop_on_1.png) | [spec-model] T-E |
| roll-up scroll | `0x3A18[7:6]`, `0x3A19`, `0x3A1B/1C` | not modelled | [hw] console scroll (`osd_tc_scroll`) |
| vertical boundary | `0x3A18[5:4]`, `0x3A1E..20` | not modelled: units unknown | [?] OT-21 |
| double size (x2) | `0x3A0A[1:0]` | [double_size](img/double_size.png) | [hw] console |
| scale-up x2 / x8 (integer) | `0x3AC0..CB` | [scale_up_2](img/scale_up_2.png) | [hw] x8 savers; polarity bit7 = 1 on |
| scale-up non-integer | `0x3AC2/3` | [scale_up_1p5](img/scale_up_1p5.png) | [spec-model] OT-22 |
| scale-up edge modes / filter | `0x3AC0[1:0]`, `0x3AC1` | not modelled | [?] OT-22 |
| software Rotate 180 | `fw/osd/osd_rot.c` | [rot180](img/rot180_software.png) | [hw] unit 3 |
| VLC-decoder turn (text layer) | `0x3A0B`, `0x3A17` | not modelled (turn applied while loading) | [hw] menu / console on unit 3 |
| hardware auto rotation | `0x3A41`, `0x3A42` | not modelled | [?] T-G; excludes double size [hw] |
| write timing, double buffer | `0x0093[7]`, RW4 fields | - | [hw] T7 / T8 stored data exact; T10 glitch look pending |
| read-back | `0x3A33[4]`, `0x0093[5]` | - | [hw] recipe in [timing.md](timing.md) |
| display pattern generator | `DISP_PG_*` `0x07F0..FE` | not modelled | [hw] test cmd 0xB2 runs it (#228) |

## Chapters
- [pipeline.md](pipeline.md): clocking, enable, position, delay sets, zone, boundary.
- [tiles-fonts.md](tiles-fonts.md): map, row / char words, 1 / 2 / 4-bit, widths, blank, fonts A / B, pop-on, roll-up, masks.
- [glyph-load.md](glyph-load.md): SRAM, data port, direct stores, burst, bytesel, write protect, VLC download.
- [palette-blend.md](palette-blend.md): palette, alpha types, specific colour, highlight.
- [windows.md](windows.md): 26 windows, effects, priority, HLW.
- [scale-up.md](scale-up.md): scale-up engine, double size, positioning.
- [rotation.md](rotation.md): software turn, VLC turn, hardware options.
- [timing.md](timing.md): vsync, double buffer, write timing, read-back.
- [limits.md](limits.md): one table.
- [api.md](api.md): our functions.
- [open-items.md](open-items.md): every `[?]` with its test; new host-only tests.
