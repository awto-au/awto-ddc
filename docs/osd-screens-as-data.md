# OSD screens as data (design for #89 step 2-3)

## Layers
- **Screen data** (`fw/screens.toml`, beside the settings registry): per screen: id, cols, lines, title bar flag, rows.
  - Row = line, then fields: `{col, style, kind, src}`; kind = `str | num(n) | hex2 | volt | milli | enum(table)`.
  - No drawing calls, no font or colour choice.
- **Presentation module** (firmware, one place): `open(screen)`, `field(screen,row,field)`, `redraw_dirty(screen)`, `close()`.
  - Owns grid, Spleen/Tamzen font, bars, palette, placement, icons.
  - Seed: `AwtoTextOpen/Line/Show` in `fw/sdcc/awto_dbgpop.inc` over `osd_tc_*` / `ui_text`.
- **Logic**: GPIO, key and debug code set values and dirty bits only.

## Generator
- `scripts/screens_gen.py`: screens file to C tables (`const` arrays, one row descriptor per field) plus the dirty-bit map.
- Build checks: every string's characters exist in the font; screen fits the window; column overlap per row.
- `scripts/osd_catalog.py` / `gpio_shot.py` render from the same tables in fw_sim.

## Order
1. GPIO, key test, debug screens (currently hand-written rows in `awto_gpiopop.inc`, `awto_keypop.inc`, `awto_dbgpop.inc`).
2. SDK cards (No Signal, No Cable, No Support, Auto Adjust, Auto Colour, Power Saving, Uniformity, source selector); logo card to the awto mark.
3. Info pop-up.
4. Realtek menu action and SDK icon tables: decide removal (user decision).

## Open
- Spleen glyphs D, O, N, M, K clip in sim (menu too): flash `AWT26110002-wb-p14ui-txt2-be` to unit 2 to separate emulator from tile packing.
- `fw/warn_policy.tsv` is keyed on file:line of inserted code; moving screens to data removes most of the churn.
