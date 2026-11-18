# Display pipeline, OSD clocking, enable, position

## Where the OSD sits
- Input side runs on the PC's clock (receiver, measure, line buffer or DDR frame buffer). Display side runs on the scaler's own display clock and drives the panel at its native timing (3840 x 2160 @ 60) whatever the source sends.
- The OSD is drawn by the display side from on-chip SRAM as each pixel goes to the panel.
  - [hw] OSD shows on the no-signal screen with no input; OSD stayed correct while the picture was garbled (2026-11-06 / 07).
  - [?] mechanism (no DDR / input clock use) is inferred from those two observations, not read from a databook. Test: OT-2.
- Consequence: a persistent overlay (debug lines, key test) can stay up at any input mode; it costs only OSD SRAM words ([limits.md](limits.md)).
- Faults on the picture crossing (4K60 line-buffer underflow, 4K30 / 1080p50 FRC bad data, #26, #36) do not affect the OSD [hw].

## Enables
| reg | field | meaning | evidence |
|---|---|---|---|
| `0x3A02[0]` | osd_en | OSD circuit active; effective at Vsync rising, cross-byte double buffered | [spec] |
| `0x006C[0]` | overlay_port_en | overlay port; 0 = nothing drawn, SRAM keeps content (the sim treats it so) | [spec] [emu] |
| `0x01DC[3]` | osd_clken | OSD clock enable; reads 1 in the running Dahua firmware | [hw] 2026-11-04 |
| `0x002B` | osd_av_sta | reference DEN position for the OSD; must not be 0 when page 12 `CRA0[7:6]` = 11 | [spec] |
| `0x3A09[4]` | ven_sel | OSD Vsync source: 0 = DVS, 1 = ENA | [spec]; our code selects DVS |
- Before clearing `osd_en` write `0x94 = 0x00` (SRAM chip select otherwise stuck high) [hw] 2026-11-04.
- With `osd_en` off, SRAM writes to font / map are ignored and reads return stale words; window SRAM does not need it [hw] 2026-11-16 (#226). The working read-back recipe needs it off: [timing.md](timing.md).

## Position and delay sets
- Origin of the OSD box = delay x step x scale (panel px). Horizontal step 4 px, or 1 px with `0x3A06[4]` (hori_delay_step_sel); vertical step 1 line [spec]; ours: `AWTO_OSD_PX_PER_HD` = 4 px per unit.
- Delay set 1: `vert_delay1[10:3]` `0x3A00`, `hori_delay1[9:2]` `0x3A01`, low bits in `0x3A02[7:3]`, bits 11:10 in `0x3A06[3:2]`. Set 2: `0x3A03`, `0x3A04`, `0x3A05`, `0x3A06[1:0]` [spec]. Latched at Vsync rising when double buffered [spec].
- Each window picks its set with `ADR3 osd_delay_sel`; font A with `0x3A18[2]`, font B with `0x3A18[1]` [spec]. One register write moves every member of a set.
- Per-font origin on top of the set: font A `0x3A24..26`, font B `0x3A27..29` (12 bit each) [spec]. Global compatibility offsets `0x3A2C` (V), `0x3A2F` (H); window offsets `0x3A32` (4 bit each) [spec].
- Fine tune: `0x3A1E[7]` / `[3]` shift 1 px when global double size is on [spec].
- Picture: [position](img/position.png) = hd 8 (x4 = 32 px), vd 16 lines [emu]; the hardware boot window sat at (0,4)-(156,80) with delay `0x3A00 = 0x02`, `0x3A01 = 0x6C` [hw] Dahua firmware, bus 20, 2026-11-04.
- Position units with scale-up on differ: [scale-up.md](scale-up.md).

## Display zone
- `0x3A02[2:1]` disp_zone: which part of the 12 px glyph a narrower char shows: 00 middle, 01 left, 10 right (not with auto rotate + remap) [spec]. Pictures: [mid](img/zone_0.png), [left](img/zone_1.png), [right](img/zone_2.png) [spec-model].
- [?] whether the shift applies per char or per row; test T-C ([open-items.md](open-items.md)).

## Vertical boundary
- `0x3A18[5]` ver_boundary_en, `0x3A18[4]` fnt_win_v_bd_align, upper / lower `0x3A1E[6:4]` + `0x3A1F`, `0x3A1E[2:0]` + `0x3A20` (11 bit): clips the OSD to a band [spec]. Units and origin [?] OT-21. Not modelled for the manual (the sim guesses panel lines).
- Our `AwtoOsdPlaceScaleUp` sets the alignment on.

## Other frame-control fields (no behaviour known beyond the regdb)
- `0x3A38..3D` osd_len / osd_wid 1 / 2 (12 bit), `0x3A3E..40` row totals (all / font A / font B): [?] whether the hardware needs them; our screens leave them to the SDK calls. OT-23.
- `0x3A33[6]` font_align_disable (align mark debug), `[5]` blank_color_en [spec].
- `0x3A8F` dummy; `0x3A90..93`, `0x3ACE/CF` BIST: unused.
