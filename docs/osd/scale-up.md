# Scale-up, double size, positioning

## Double size (x2) [spec] [hw]
- `0x3A0A[1]` db_width, `[0]` db_height: every OSD element (windows and chars) doubled. Picture: [double_size](img/double_size.png).
- [hw] the Dahua firmware ran x2 at boot (`0x3A0A = 0x0B`: x2 both + alpha type 10, ISP read 2026-11-04); our console runs x2 on unit 3 (136 columns x 50 rows = 2176 x 1836 px of 3840 x 2160). Our default image: off until a screen asks (`osd_tc_place(..., big)`).
- Position units multiply with it: origin = delay x step x 2.
- Excludes the chip's auto rotation: with x2 on, auto rotation showed boxes without text [hw] unit 3 (`text_layer.c`).

## Scale-up engine (`0x3AC0..0x3ACB`) [spec]
| reg | field | meaning |
|---|---|---|
| `0x3AC0[7]` | osd_su_en | enable. The regdb text says "0: Enable / 1: Disable"; **hardware: 1 = on** (scaled Scope 2 shows with the bit set; `0x3AC0 = 0` makes reads exact: [hw] 2026-11-18, [timing.md](timing.md)). Our code writes 1 to enable. |
| `0x3AC0[1:0]` | osd_su_bd_cond | boundary: 00 neighbourhood (default), 01 thin, 10 fat |
| `0x3AC1` | osd_vsu_ini / osd_hsu_ini | filter coefficient initial phase (4 bit each) |
| `0x3AC2` | osd_vsu_factor | vertical, 6 bit = `Yi / Yo x 64` |
| `0x3AC3` | osd_hsu_factor | horizontal, 6 bit = `Xi / Xo x 64` |
| `0x3AC4/5`, `0x3AC6/7` | ipt_ver_start, ipt_hor_start | region start (12 bit), display coordinates |
| `0x3AC8/9`, `0x3ACA/B` | ipt_ver_size, ipt_hor_size | region size (12 bit) |
- One region, one factor pair for the whole OSD: no per-window or per-map scale [spec].
- Factor n scales by 64 / n: n = 32 is x2, n = 13 is x4.9, n = 8 is x8 [hw: Scope 2 factor 8 fills 3840 x 2160 from 480 x 270; Pac-Man factor 13]; non-integer, e.g. n = 43 is x1.5 [spec-model] OT-22. Picture: [x2](img/scale_up_2.png), [x1.5](img/scale_up_1p5.png) (the sim scales from the OSD origin by nearest neighbour; the filter, initial phase and boundary modes are not modelled, OT-22).
- Region start is in display coordinates, not relative to the OSD: with start 0 a centred OSD scaled only vertically; start = OSD position fixed it [hw] unit 3, 2026-11-18 (poked `0x3AC6/7` live). `AwtoOsdPlaceScaleUp` does that: H = `posH x 4` px, V = `posV` lines.
- **Position with scale-up on** [hw] only for position 0 (all full-screen savers). A non-zero position (T9: asked 384 / 504 = centred) appeared right of centre and low: the unit is not what `AwtoOsdPlaceScaleUp` assumes. Settle: OT-26 (ladder at known positions, measure on the photo).
- Comment in the SDK: only valid in even-odd mode [sdk-hypothesis]. Scale-up over x2 double size: [?] OT-22.
- Auto-rotation excludes scale-up [sdk-hypothesis]; text_layer.c's measured fact is only the double-size exclusion above. T-G tests both.
- Read-back and scale-up: reads return junk with it on: [timing.md](timing.md).
- Our savers: raster 480 x 270 px (40 x 15 tiles) scaled x8 to 3840 x 2160 (Scope 2); factor and position derive from `_PANEL_DH_WIDTH` / `_PANEL_DV_HEIGHT`.
