# awto OSD editor (awto-ddc#89)
PySide6 viewer/editor on top of `scripts/` (VLC codec: `scripts/osd_vlc.py` via `vlc_adapter.py`).

- Launch: `python3 tools/osd_editor/run.py` (first run builds `.venv`, Python 3.13 via uv; default python3 has no PySide6 wheels)
- Test: `QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_smoke.py` (screenshots -> `tmp/osdedit/shots/`); monitor page: `test_monitor_gui.py` (screenshot -> `tmp/scratch/qt/`)

## Features (top-right toolbar)
- glyphs: tile list, pixel editor (left = colour, right = colour 0, ctrl+z undo), 1x / 2x preview; 1 / 2 / 4 bpp, 12x18 or 24x36 (2x2 cells, cell borders drawn)
- import: TTF (ASCII 0x20..0x7E), PNG / SVG sheet sliced into tiles; open: our `.inc` export or an OsdEdit "HardWare VLC 2523V" `.txt`
- export C: `BYTE __code NAME_VLC0[]` blobs (our encoder), header line carries bpp / geometry / tile count for re-import
- defaults (#89): 24x36 at 2 bpp, palette = black-to-white ramp (text); red is reserved for decorations (frame, title, highlight, icons)
- budget (top): font SRAM words / 12288, flash raw vs VLC bytes, red above 100 %
- screens: pages through `tmp/osd_catalog/*/catalog.tsv` renders, fit or zoom; "render BIN..." runs `scripts/osd_catalog.py`
- monitor (#217, docs/monitor-gui.md): unit strip (hotkeys 1..9, status dots, auto-detect via sysfs EDID), page tree with search, Quick strip, per-unit job queues
  - settings: one widget per `settings_table.py` row, grouped by registry page; `ro` rows disabled; risky and action rows ask first; Get all / Set / Save
  - only `test` units are writable; live refresh (15 s, idle only); input select (`scripts/kvm.py`), host time, health, boot / sync log (`dev.py synclog`)
  - backend = `dev.py` subprocesses, one worker per unit (units in parallel); no I2C in the GUI; every call has a limit (`LIMIT_S`); one ISO 8601 log line per action in `tmp/logs/osd_editor.log`
- screens: the catalogue renders come from `osd_model.py`, which draws 1 / 2 / 4 bpp chars (smoke test shows a 2 bpp glyph)

## Not done
- palette editing / .pal files, char-map (screen layout) editing, OsdEdit .txt export (byte format differs, see docs/osd-editor-spec.md)
- 2 / 4 bpp tile packing in the glyph editor is row-major; `osd_model.py` draws bit planes (#227): exports are not hardware-verified
- monitor page not checked in a real window; screensaver value 5 (Flash warning) is not in the registry options or the capabilities string (unit 3 reports max 5 for VCP 0xEB)
