# OSD rotation for our own full-screen OSD screens

Status 2026-11-18. Code: `fw/osd/osd_rot.c`. Users: Pac-Man (`fw/test/pacman_classic.c`), scope savers (`scope_saver.c`, `scope_saver2.c`), Asteroids (`asteroids.c`). The menu / console use the same rule in `fw/osd/text_layer.c`.

## Why

- Display Rotate 180 (settings row 32 `disp_rotate`, unit 3) turns the picture in the frame buffer. The OSD circuit is not turned: an upright map shows upside down. Seen on unit 3, 2026-11-18 (Pac-Man photo: READY! and the scores mirrored).
- No OSD mirror in hardware (`text_layer.c`): Mirror modes leave the OSD upright.
- Chip auto rotation (`FRAME_CTRL_41`) is off in our tests (`AwtoOsdTestReset` clears it); the hardware font download swap (`FRAME_CTRL_0B f_dl_swap`) only works through the VLC / compressed download path, which these screens do not use.
- So: draw the map turned in software when the display is turned.

## Rule

- Turned = `AwtoOsdRot180()`: 1 when `GET_OSD_DISP_ROTATE() == _DISP_ROTATE_180` (and `_DISPLAY_ROTATION_SUPPORT`), else 0. Read once when the screen is drawn.
- Map: cell c -> `AwtoOsdRotCell(c, cells)` = cells - 1 - c (row r col x -> row H-1-r col W-1-x). Applies to the initial map and to every later cell write (Pac-Man step deltas).
- Glyph: bitmap turned 180 inside the glyph. A glyph is words of 24 bits = two 12 px rows, row-major, stored low byte first (B0). Turning = word order reversed + every word bit-reversed:
  - output byte i = `AwtoOsdRevByte(source byte AwtoOsdRotSrc(i, words))` of the unturned glyph.
  - Only the used rows are turned: Pac-Man shows 12 of the 18 glyph rows (row height 12), so it turns 6 words and leaves the 3 padding words; the scopes use all 9 words.
  - 2-bit glyphs: each bit plane is a glyph of its own, turned the same way.
- Position: the OSD box is not mirrored. All our screens are centred, so no change; an off-centre screen must mirror its own position.

## Functions (`fw/osd/osd_rot.c`)

| function | does |
|---|---|
| `BYTE AwtoOsdRot180(void)` | 1 = display Rotate 180 |
| `WORD AwtoOsdRotCell(cell, cells)` | mirrored map cell |
| `BYTE AwtoOsdRevByte(b)` | bit-reversed byte |
| `BYTE AwtoOsdRotSrc(out, words)` | source byte index for output byte `out` of a turned glyph of `words` words |

- Scope savers upload tiles from the `osd_lines` canvas (canonical bytes c0 c1 c2, stored B0 B1 B2 = c2 c1 c0): turned, each word is written as `RevByte(c0), RevByte(c1), RevByte(c2)` of the mirrored word, into the glyph slot of the mirrored cell.
- No extra RAM: the rotation reads the source in a different order while streaming.

## Scale-up window (found with the same photo)

- `ScalerOsdScaleUpHorSize/VerSize(start, size)`: start is in display coordinates, not relative to the OSD (the SDK adds the background start). It must equal the OSD position: H = position hd x 4 px, V = position px. With start 0 the enlargement window missed a centred OSD: scaled vertically (OSD at y = 0), not horizontally (OSD at x = 1096). Poked live on unit 3 (registers 0x3AC6 / 0x3AC7), the maze filled the width.
- The sim scales from the OSD origin, so it never showed this.

## Check

- `python scripts/saver_sim.py <image>`: starts each saver by DDC/CI VCP 0xEB, sets Rotate 180 (registry row 32 through VCP 0xE0 / 0xE1), compares the OSD box with the upright render turned 180 (shrunk 8x, mean difference <= 8, at least 1.5x closer than the unturned render).
- Unit 3: Rotate 180 is the stored setting; the screens should look upright to the viewer.

## Shared screen helpers (`fw/osd/osd_screen.c`)

- `AwtoOsdScreenBegin()`: close, latch `g_ucAwtoOsdRot`, `AwtoOsdTestReset`, double buffer off, circuit on, DVS. `AwtoOsdScreenOff()`: close + scale-up off.
- `AwtoOsdWord(addr, b0, b12)`, `AwtoOsdRowCmds(rows, rowH, cols)` (rows + end marker), `AwtoOsdGlyph(addr, xdata ptr, words)` (turns when latched).
- `AwtoOsdPlaceScaleUp(posH, posV, cols, rows, factor)`: map of 12 x 18 tiles placed, scaled, shown.
- At most 3 parameters where it can: the 4th and later go to XDATA (floor 700 B).
- Users: scope savers, QC pattern; Pac-Man and the flash screen adopt them later.
