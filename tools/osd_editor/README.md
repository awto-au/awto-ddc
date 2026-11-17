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
- monitor (#217): unit picker (`scripts/devices.json`; only the `test` unit is writable, others greyed)
  - Quick group: screensaver start / stop (`dev.py ddc set 0xEB v`: Stop, Selected, Pac-Man, Scope, Scope 2, Flash warning), volume (0x62), mute (0x8D), rotate (`disp_rotate`); "Read quick values"
  - settings: one widget per `settings_table.py` row, grouped by registry page + group; slider int, combo enum / bool with option labels; `ro` rows disabled; Get all / Set / Save
  - live refresh (15 s, only when idle): a touched or dragged row keeps its widget value until Set
  - input select (`scripts/kvm.py`), host time now, health verdict
  - boot / sync log (`dev.py synclog [--whole]`): +ms column per line, red above 100 ms, summary line (lines, episode length, slowest step); `sync_log.py --delta` not used, the +ms is computed from the `<ms>:` field
  - backend = subprocesses off the UI thread, one at a time (`dev.py settings|ddc|synclog|health --unit N`: bus, map, debug link on/off, EDID guard inside dev.py); no I2C in the GUI
  - every call has a limit (3x the slowest measured, `monitor.py LIMIT_S`, docs/osd-editor-spec.md section 7); expiry or a unit that does not answer shows a red banner and a log line
  - every action: one ISO 8601 line in the app and `tmp/logs/osd_editor.log`
- screens: the catalogue renders come from `osd_model.py`, which draws 1 / 2 / 4 bpp chars (smoke test shows a 2 bpp glyph)

## Not done
- palette editing / .pal files, char-map (screen layout) editing, OsdEdit .txt export (byte format differs, see docs/osd-editor-spec.md)
- 2 / 4 bpp tile packing in the glyph editor is row-major; `osd_model.py` draws bit planes (#227): exports are not hardware-verified
- monitor page not checked in a real window; screensaver value 5 (Flash warning) is not in the registry options or the capabilities string (unit 3 reports max 5 for VCP 0xEB)
