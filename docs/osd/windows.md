# Windows (26), effects, priority, highlight

Rectangles in the window control SRAM (`sram_sel` 00), drawn behind the font (or in front, per window). No bitmap inside a window.

## Addressing [spec]
- Word index (`port_idx`): WIN0..9 at `0x100 + 4n` (WIN0 `0x100` ... WIN9 `0x124`); WIN4_1..4_8 from `0x200` step 4; WIN5_1..5_8 from `0x220` step 4 [hw: boot window written / read at `0x100..0x103`]. Higher ADR words follow the regdb `port_idx` (`osd_model.win_adr`).
- Colour indices are 6 bit into the 64-entry LUT ([palette-blend.md](palette-blend.md)); the high bits sit in `ADR3` B0.

## Words (bytes B0 = LSB, B1 = MSB, B2 = HSB) [spec]
| word | B0 | B1 | B2 |
|---|---|---|---|
| ADR0 | [7] sha_color[4], [6] bor_color[4], [5:3] eff_width - 1, [2:0] eff_height - 1 | [7:4] sha_color[3:0], [3:0] bor_color[3:0] | gradient (WIN0, 5..9): [7:5] polarity R G B, [4:3] step - 1, [2:0] enable R G B |
| ADR1 | [7:4] hor_sta[11:8], [3:0] ver_sta[11:8] | hor_sta[7:0] | ver_sta[7:0] |
| ADR2 | [7:4] hor_end[11:8], [3:0] ver_end[11:8] | hor_end[7:0] | ver_end[7:0] |
| ADR3 | [7] sha[5], [6] bor[5], [5] win_color[5], [4] gra_sat_en, [3] gra_rev_en, [2] osd_delay_sel, [0] gra_level_ext (WIN4_x / 5_x: [1] bor_higher_font) | [7:5] gra_level, [4:0] win_color[4:0] | [7] blend_en, [6] gra_en, [5] gra_dir, [4] eff_en, [3:1] eff_opt, [0] win_en |
- Boot window of the Dahua firmware, read over ISP: ADR1 `00 00 04`, ADR2 `00 9C 50`, ADR3 `00 04 81` = (0,4)-(156,80), colour 4, enabled + blend [hw] 2026-11-04.
- Positions are in OSD px (before x2 / scale-up). End is inclusive in the sim; [?] the hardware (OT-14).

## Which window supports which type [spec]
| windows | words | effects | gradient | chessboard | round | grid | colour mask / gray | pixel step |
|---|---|---|---|---|---|---|---|---|
| WIN0, WIN5 | ADR0..4, 6, 8, 9, 10 | yes | yes (+ saturated ADR4) | no | ADR10 | no | yes | ADR9 |
| WIN1 | ADR0..3, 9 | yes | no | no | no | no | no | no |
| WIN2, 3, 4 | ADR0..3, 7, 8, 9 | yes | no | no | no | ADR7 / 8 | no | no |
| WIN6, 7 | ADR0..4, 6, 8, 9 | yes | yes | no | no | no | yes | ADR9 |
| WIN8, 9 | ADR0..6, 8, 9 | yes | yes | ADR5 | no | no | yes | ADR9 |
| WIN4_1..4_8, WIN5_1..5_8 | ADR0..4, 9, 10 | yes | no | ADR4 | ADR10 | no | no | no |
- Every window: `ADR9[0]` win_rotate_en (the regdb lists it on all 26; effect [?] OT-13).
- Priority bits: win2 `0x3A08[7]`, win3 `0x3A07[0]`, win4 `0x3A07[1]`, win8 `0x3A08[5]`, win9 `0x3A08[6]` (1 = above the font); WIN4_x / 5_x `ADR3[1]` bor_higher_font (border only). Other windows sit below the font [spec].

## Effects (pictures: sim, `[spec-model]` = register-text reading, not seen on the panel)
- Solid: [win_solid](img/win_solid.png) [hw].
- Shadow / border / 3D button: `eff_en` + `eff_opt` 000..011 shadow types 1..4, 100 / 101 3D button, 111 border; thickness `eff_width` px x `eff_height` lines (1..8; equal for 3D); sha / bor colours (3D: left-top / right-bottom). Pictures: [shadow](img/win_shadow.png) [3D](img/win_3d.png) [border](img/win_border.png) [spec-model]; the sim draws the 4 shadow types the same, and its exact edge placement is a reading: OT-9.
- Rounded corners: `ADR10[0]` enable, `[2:1]` size 00 = 8 x 8, 01 = 16 x 16, 10 = 32 x 32 px, `[6:3]` corners (UL, LL, UR, LR); the shape comes from tables `0x3A60..63` (8 x 8, 3 bit per line), `0x3A64..6B` (16 x 16, 4 bit), `0x3A6C..8B` (32 x 32, 5 bit) [spec]. Not pictured: the sim's radius mapping (4 / 8 / 16 / 32 px for codes 0..3) disagrees with the regdb sizes and ignores the tables. OT-10.
- Gradient: `gra_en`, direction `gra_dir` (0 H, 1 V), per-channel enable / polarity (`ADR0` B2), `gra_step` 1..4 px per level (extension `ADR9[4]` + `ADR8` 8 bit), `gra_level` 1..7 per gradient or per-channel 256 levels (`gra_level_ext`, `ADR6`), saturated end colour (`ADR3[4]`, `ADR4`), reversed (`ADR3[3]`) [spec]. Picture: [win_gradient](img/win_gradient.png). [hw] QC frames with gradients match the sim (unit 3 photo, qc-osd-suite); level / saturate semantics beyond that are readings.
- Gray level: `ADR9[1]`: window shown as gray [spec]; formula (luma) is the sim's [?] OT-11. Picture: [win_gray](img/win_gray.png).
- Chessboard: colours 1 / 2 (`ADR5` WIN8 / 9, `ADR4` 4_x / 5_x, bit 7 enable), square = `ADR9` pixel step (WIN8 / 9), 1 px chessboard = dotted line [spec]. Picture: [win_chess](img/win_chess.png) (WIN8). The sim reads `ADR5` only, so 4_x / 5_x chessboards are not drawn. Square size on hardware [?] T-B.
- Grid lines (WIN2 / 3 / 4): `ADR7` width 1..4 px `[7:6]`, colour `[5:0]` (B0); H enable `[7]`, V enable `[6]`, offset `[5:0]` (B1); pitch `[14:0]` in um (`ADR7` B2 + `ADR8` `[7:1]`), `grid_en` `ADR8[0]`; spacing in px = pitch / panel pitch, panel pitch `0x3A35..37` (U9.2 um, per axis) [spec]. Picture: [win_grid](img/win_grid.png) (panel pitch 993 um assumed, from the QC set). [hw] QC frames 2 / 3 match the sim; our panel's real pitch is [?] T-A.
- Special colour mask: `ADR9[2]` enable, `[3]` AND / OR of the window colour with the **picture** (no OSD pixel) [spec]. Picture: [win_mask_colour](img/win_mask_colour.png) OT-12.
- Window 7 mask region: `0x3A09[6:5]` = 10: OSD appears only inside window 7; 11: transparent inside; `0x3A07[3]` = mask all windows and fonts (0) or only transparent fonts (1) [spec]. Picture: [win7_mask](img/win7_mask.png) OT-16.
- Window 6 / 7 blend functions (`0x3A21[6]`, `[5:4]` / `[3:2]` per-window foreground / background blend), `0x3A09[6:5]` = 01 window 7 blending [spec]: modelled, no picture yet (OT-16).

## Priority vs font
- Picture: [win_priority](img/win_priority.png): window 3 above the text, window 1 below [spec-model] OT-15.
- Border above the font for 4_x / 5_x: `ADR3[1]`.

## Zero-width window
- Window 5 with x end = x start drew a line from x0 to the right screen edge, past the OSD box (photo unit 3, rotation 180, 2026-11-15, #215). `osd_tc_bar` widens windows below 2 px (`AWTO_OSD_WIN_MIN_PX`) to avoid it. Remaining cases (y, both, end < start, blend / priority) [?] OT-14. Not modelled.

## Highlight windows
- 4_1..4_8: for the font inside window 4_n, foreground colour = `fg_color_hl n`, background = `bg_color_hl n` (6 bit each; enable bit 6 of the first register) in `0x3A2A / 2B`, `0x3A2D / 2E`, `0x3A30 / 31`, `0x3A4D..56` [spec]. Picture: [highlight](img/highlight.png) [spec-model] OT-17.
- Video highlight window (HLW, page 0): `0x0060` HLW_ADDR_PORT + `0x0061` HLW_DATA_PORT: a rectangle (start / end 13 bit), which picture-processing blocks (contrast, gamma, DCC, sharpness, sRGB, ...) apply inside / outside, **and a border**: width 5 bit, colour R / G / B (8 bit each), per-side disable (`HLW_BORDER_EN` [7:4] L R T B), `window_en` [0] [spec]; `0x006C[6]` hides the border. The border is drawn in the video path, independent of the OSD SRAM. Sim: border inside [start, end) (SDK end = start + size), under the OSD [spec-model]; picture [hlw_border](img/hlw_border.png); OT-18.

## Limits
- 26 windows; 8 highlight sets; 1 grid window per WIN2 / 3 / 4; all windows share the OSD scale / position / alpha level (no per-window alpha level, only `blend_en`).
- Uses in our code: bars and rules (`osd_tc_bar`), QC / OSD demo (`fw/test/osd_demo.c`, test cmds 0xA0..0xA5), Scope graticule candidates (saver-fps-hw #3).
