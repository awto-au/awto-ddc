# awto OSD editor (awto-ddc#89)
PySide6 viewer/editor on top of `scripts/` (VLC codec: `scripts/osd_vlc.py` via `vlc_adapter.py`).

- Launch: `python3 tools/osd_editor/run.py` (first run builds `.venv`, Python 3.13 via uv; default python3 has no PySide6 wheels)
- Test: `QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_smoke.py` (screenshots -> `tmp/osdedit/shots/`)

## Features (top-right toolbar)
- glyphs: tile list, pixel editor (left = colour, right = colour 0, ctrl+z undo), 1x / 2x preview; 1 / 2 / 4 bpp, 12x18 or 24x36 (2x2 cells, cell borders drawn)
- import: TTF (ASCII 0x20..0x7E), PNG / SVG sheet sliced into tiles; open: our `.inc` export or an OsdEdit "HardWare VLC 2523V" `.txt`
- export C: `BYTE __code NAME_VLC0[]` blobs (our encoder), header line carries bpp / geometry / tile count for re-import
- defaults (#89): 24x36 at 2 bpp, palette = black-to-white ramp (text); red is reserved for decorations (frame, title, highlight, icons)
- budget (top): font SRAM words / 12288, flash raw vs VLC bytes, red above 100 %
- screens: pages through `tmp/osd_catalog/*/catalog.tsv` renders, fit or zoom; "render BIN..." runs `scripts/osd_catalog.py`

## Not done
- palette editing / .pal files, char-map (screen layout) editing, OsdEdit .txt export (byte format differs, see docs/osd-editor-spec.md)
- 2 / 4 bpp tiles are not drawn by `osd_model.py` (model gap), so the screens page cannot show them
