# Rotation

Display Rotate 180 (setting row 32 `disp_rotate`, unit 3 stored) turns the picture in the frame buffer. The OSD circuit is not turned: an upright map shows upside down [hw] unit 3, 2026-11-18 (Pac-Man photo). There is no OSD mirror in hardware: Mirror modes leave the OSD upright.

## Three mechanisms
| mechanism | used by | evidence |
|---|---|---|
| decoder turn while downloading glyphs (`0x3A0B[7:6]` f_dl_swap 01 = 180, `hw_rotate_en`, buffer poll `0x3A0B[5:4]`) + map written in reverse | menu, console (`text_layer.c`, `AwtoOsdOrient`) | [hw] unit 3, works with the VLC / compressed download path |
| software turn: map cell mirrored, glyph words reversed + bit-reversed while streaming (`fw/osd/osd_rot.c`) | savers, QC pattern (glyphs go raw, not through the decoder) | [hw] unit 3; sim check `scripts/saver_sim.py` |
| chip auto rotation `0x3A41` (auto_rotate_en, dir 00 CCW / 01 CW / 10 180, `rotate_flib`, char remap, `0x3A42` font B LUT start) | not used (`AwtoOsdTestReset` clears it) | [?] T-G: would turn map and glyphs in hardware |
- The decoder's raw path (`0x3A17[1]` decode_nocom_data with `f_dl_swap`) is the SDK's route for raw glyphs [sdk-hypothesis]; not in our savers yet: T-I.
- Auto rotation + `disp_zone` 00 not allowed [spec]; with double size it showed boxes without text [hw] unit 3.
- `0x3A0B[0]` rotation: fetch / display considering rotated font-map data [spec].
- Window rotate `ADR9[0]` per window [spec] [?] OT-13.

## Software rule (`fw/osd/osd_rot.c`)
- Turned = `AwtoOsdRot180()`: 1 when `GET_OSD_DISP_ROTATE() == _DISP_ROTATE_180` (and `_DISPLAY_ROTATION_SUPPORT`); read once when the screen is drawn.
- Map: cell c -> cells - 1 - c (row r col x -> row H-1-r col W-1-x), for the initial map and every later cell write.
- Glyph: word order reversed + every word bit-reversed (24 bit): output byte i = `AwtoOsdRevByte(source byte AwtoOsdRotSrc(i, words))`. Only the used rows are turned (Pac-Man: 12 of 18 rows = 6 words). 2-bit glyphs: each plane is turned like a 1-bit glyph.
- Position: the OSD box is not mirrored; centred screens need nothing, off-centre ones mirror their own position.
- Scope savers upload tiles from the `osd_lines` canvas turned the same way; Scope 2 uses a second generated table (`AwtoOsdTurn` replaced the older `s_tS2BaseRot`).
- Picture: [rot180_software](img/rot180_software.png): the map and glyphs as the OSD circuit receives them when the display is turned (upside down by design: the panel turns it back).
