# Our API

Code is the reference; this lists what exists and who owns what. Hardware facts are in the other chapters.

## Screen helpers: `fw/osd/osd_screen.c` (savers, QC pattern; full-screen maps of 12 x 18 tiles)
| function | does |
|---|---|
| `AwtoOsdScreenBegin()` | close the text layer, latch Rotate 180, `AwtoOsdTestReset` (clears blend / mask / pop-on / scale-up), global double buffer off, circuit on, DVS source |
| `AwtoOsdScreenOff()` | close + scale-up off |
| `AwtoOsdWord(addr, b0, b12)` | one 3-byte word |
| `AwtoOsdRowCmds(rows, rowH, cols)` | row commands + end marker (`80, h-1, cols`) |
| `AwtoOsdGlyph(addr, ptr, words)` | glyph words, turned when latched ([rotation.md](rotation.md)) |
| `AwtoOsdMap1(cols, rows, attr)` | 1-bit map, glyph id = cell; sets bases |
| `AwtoOsdTile(cell, bytes)` | canvas tile into the glyph of its cell (mirrored when turned) |
| `AwtoOsdPlaceScaleUp(posH, posV, cols, rows, factor)` | position, scale-up window = OSD position, factor, boundary neighbourhood, on |
- At most 3 parameters where possible: the 4th and later go to XDATA (floor 700 B).
- Users: scope savers, Asteroids, Pac-Man, QC pattern, flash screen (adopting). Library of the savers: `docs/saver-library.md`; their budgets and frame rates: `docs/saver-fps-*.md`.

## Rotation helpers: `fw/osd/osd_rot.c`
`AwtoOsdRot180()`, `AwtoOsdRotCell(cell, cells)`, `AwtoOsdRevByte(b)`, `AwtoOsdRotSrc(out, words)`, `AwtoOsdTurn(ptr, n)`.

## Text layer: `fw/osd/text_layer.c` (header `fw/rtdfw/awto/include/osd.h`)
- One text path for menu, cards, console. Grid: one map row per text row; cell size from the loaded font.
- `osd_tc_open(chars, lines, font)`, `osd_tc_rowh`, `osd_tc_cells(maprow, cell, tiles, n, style)`, `osd_tc_bar` / `osd_tc_bar_off` (windows as bars; widths < 2 px widened), `osd_tc_place` (own placement, cell size from the font, clamped at 0), `osd_tc_place_corner`, `osd_tc_viewport`, `osd_tc_scroll` (roll-up, stops before the 12-bit base wraps), `osd_tc_show`, `osd_tc_close`, `osd_tc_vlc_begin / put / end` (VLC glyph download, turned when Rotate 180).
- `AwtoOsdBlend()`: blend type 11 + level from `osd_transparency`. `AwtoOsdRoll(on)`: roll-up mode.
- Menu bars in `ui.c` assume 8 x 18 cells.

## Console and screens
- Diagnostic console `fw/osd/console.c` (`AwtoDiagConsole`, pages MAIN / GPIO, `AwtoBootConsole`, `AwtoConScroll`): layout and modes in `docs/osd.md`.
- Registry menu, key test panel, cards: `docs/osd.md`, `docs/settings.md`.

## Host side
| tool | does |
|---|---|
| `scripts/osd_model.py` | OSD model: SRAM + registers -> image |
| `scripts/osd_render.py` | runs an image in `fw_sim`, renders OSD frames |
| `scripts/osd_manual.py` | the manual's pictures; `--check` |
| `scripts/osd_catalog.py` | every layout, contact sheet |
| `scripts/qc_frames_shot.py`, `scripts/qc_suite_unit.py` | Realtek QC frames in the sim / on unit 3 |
| `scripts/rtd_osd.py` | PC-driven OSD over ISP (raw SRAM words, palette, windows) |
| `scripts/osd_hw_test.py` | `./dev.py osd-hw-test`: SRAM write / read tests on a unit |
| `scripts/osd_vlc.py`, `scripts/glyph_decode.py` | VLC encode / decode |
| `scripts/osd_test.py` | raise OSD events / keys in the running firmware |
