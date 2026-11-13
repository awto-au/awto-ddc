# OSD system: overview and entry point

Overview only; each fact lives in the linked doc. Tracking: awto-ddc#1 (index), #67 (menu), #85 (keys), #87 / #89 (look), #120 (SDK menu), #128 (console menu), #129 (key dispatcher), #39 (key test panel).

## Naming
Never write bare "vendor": say which one.

| name | what | where it runs |
|---|---|---|
| **Dahua firmware** | the monitor's original factory firmware (Dahua/JXC). Known only by RE of the flash dump: buttons, boot logo, fonts | units as shipped; dump in `~/vendors/realtek/analysis/dumps/` |
| **Realtek SDK menu** | Realtek's RTD2014 demo OSD: 9-icon main menu and its pages | built out of the default image since 2026-11-11 (#120): [osd-realtek-sdk-menu.md](osd-realtek-sdk-menu.md) |
| **awto menu** | our registry menu (#67) | our images (AUTO key default) |

- Tag `[sdk-ui]` in `awto-rtdfw/settings/registry.tsv` = Realtek SDK menu fact.

## 1. Layers
### Hardware (RL6449 / RTD2795T)
- OSD SRAM (12288 x 24 bit words), row / char command layout, windows, palette, x2 scale: [reversing/realtek-rtd/osd.md](reversing/realtek-rtd/osd.md), [osd-limits.md](reversing/realtek-rtd/osd-limits.md).
- Font download (VLC decode, char words, burst DMA from flash): [osd-font-download.md](reversing/realtek-rtd/osd-font-download.md).
- No framebuffer: everything (menus, pop-ups, console) is glyph cells + windows.

### Text layer (`osd_tc_*`): the one text path for our screens
- API: `awto-rtdfw-ui` `awto/include/osd.h` (`osd_tc_open`, `osd_tc_rowh`, `osd_tc_cells`, `osd_tc_bar`, `osd_tc_place`, `osd_tc_show`, `osd_tc_close`, `osd_tc_viewport`, `osd_tc_scroll`, `osd_tc_vlc_*`).
- Implementation: `awto-ddc-ui` `fw/awto/settings/glue.inc`, section "text layer on the OSD engine".
- Grid: one map row per text row; cell width and row height come from the loaded font (`osd_cw` / `osd_rh`).
- Viewport + hardware scroll: `osd_tc_viewport` fixes the shown height; `osd_tc_scroll` rolls the view (0x3A18..0x3A1C). Limits: [Limits](#limits).
- Placement: `osd_tc_place` (own code, not the SDK): cell size from the loaded font, clamped at 0.
- Menu bars in `ui.c` assume 8x18 cells (`OSD_CHAR_W` / `OSD_CHAR_H`, `osd.h`): smaller fonts misplace them (#128).

### Limits
- Measured SDK limit: `OsdDispSetPosition` wraps above the panel height at 2x (60+ rows): #108, row 1 (unit 2, 2026-11-11).
- Roll-up font-select base is 12 bit (0x3A1B / 0x3A1C); `osd_tc_scroll` stops the view where the base would pass 4095. Register width: [osd-limits.md](reversing/realtek-rtd/osd-limits.md).
- Cell map: the OSD reads cells only below map address 8192 (13 bit). Measured 2026-11-11, unit 2, limit probe at 5x8: 160 x 48 lines clean; 160 x 63 lines correct up to map row 50 (address 65 + 50 x 160 = 8065), corrupt and wrapped from address 8192; 160 x 72 / 90 show nothing. Rule: cols x rows + rows + 1 < 8192.
- Roll-up base wrap, measured the same day: 46 scroll steps at 160 columns corrupt the lower half once the 12-bit font-select base passes 4095 (about step 25).
- Font SRAM size (12288 words) is the SDK constant, not read back from hardware; see [osd-limits.md](reversing/realtek-rtd/osd-limits.md).

### Realtek SDK engine (RTD2014 demo OSD, compiled into our image)
- Ours on the text layer (`fw/osd/console.c`): message cards and the input-info card (`OsdDispOsdMessage`, SDK body removed, #124), source selector (`AwtoSourceOpen` / `AwtoSourceKey`, SDK hot-key source menu removed, #134). SDK timers and OSD states still drive them.
- Still SDK-drawn: DDC/CI and DP-version hot-key menus (proportional font, `OsdPropPutString*`, `tFONT1_GLOBAL`, VLC icons).
- DDC/CI and DP-version hot-key menus: no normal entry point left (#122).
- Source: Realtek SDK `RTD2014*Osd*.c`, rewritten by `scripts/keil2sdcc.py` (generated output in `tmp/sdcc-port/src`); drawn by `OsdDispOsdMessage` and the OSD state machine.
- Realtek 9-icon main menu: built out by default (`_AWTO_REALTEK_MENU`, `RL6449_Project.h`, default `_OFF`). Re-enable with `-D _AWTO_REALTEK_MENU=_ON` (works at 6bd79ce; #129 removes the operation-table path it uses).
- Walkthrough of its pages and key actions (historical): [osd-realtek-sdk-menu.md](osd-realtek-sdk-menu.md).

### Our parts
- Diagnostic console (#89, #128; #34 closed)
  - Code: `fw/osd/console.c` (`AwtoDiagConsole`), `awto_keytest.inc`, `awto_gpio.inc` in `awto-ddc-ui/fw/sdcc/`.
  - Opened at power-on (mode INITIAL, `AwtoBootConsole`, #144: replaces the boot logo), by itself after a switch / wake (#139, registry `sync_console`), by UP+DOWN, test cmd 0x20 / 0x26, 0x41 / 0x42: main page. Menu "GPIO inputs" / test cmd 0x43: GPIO page. Closed by UP+DOWN, 0x44. Host: `scripts/osd_test.py`.
  - Look: green on black (palette 1..4 set in `fw/osd/console.c`); font Spleen 8x16 (font 0, 8 x 18 cells) at 2x; 0x60+n picks a font, 0x4A / 0x4B = 1x / 2x.
  - Grid 120 columns x 63 map rows; 50 rows shown (1920 x 1836 px on the 3840 x 2160 panel), UP / DOWN scroll (`AwtoConScroll`).
  - Pages (#157; `AwtoDiagConsole(AWTO_CON_MAIN / AWTO_CON_GPIO)`, a page change redraws the map):
    - Main (power-on, auto-open, UP+DOWN): title row + sync / power event log, cols 1..118, 47 lines, live at each sync push. Host time + its fw ms on one row.
    - GPIO: input table (left) + the input-change list (right, backfilled from the 32-entry change ring). Input changes never go into the event log.
  - Title row on both: `AWTO DIAGNOSTICS  FW <tag>` + PANEL / UP / HOST, 1 s refresh, only changed 2-cell groups written.
  - Below the view on both (UP / DOWN scroll): key test, debug, watchdog panels. Debug rows are written only when their text changed and only while in view.
  - Power-on in the sim: `scripts/boot_sim.py` (PNGs at set times, console survives display setting).
  - Inputs panel: rows from `fw/awto/inputs.tsv` through `scripts/gen_awto_inputs.py` (generated `AWTO_IN_*`); unlogged inputs red with a legend.
  - Owns the OSD only while its map is in place: an SDK pop-up or mode reset releases it (`AwtoConLost`).
- Boot logo: removed (#144); the console shows the power-on log instead. Dahua splash RE notes: [boot-logo.md](boot-logo.md).
- Registry menu (#67)
  - Code: `/mnt/2tb/git/awto-rtdfw/awto/settings/menu.c`, `ui.c`, `set_table.c` (generated), `settings.c`, `vcp.c`; header `awto/include/menu.h`; registry `/mnt/2tb/git/awto-rtdfw/settings/registry.tsv` + `pages.tsv`.
  - Drawn through the text layer with our fonts; blue text on white (`tAwtoPal`).
  - Opened with the front keys, `menu_cli.py open`, or VCP 0xE4. Key roles use SDK names (Menu / Right / Left / Exit); physical keys (Dan, 2026-11-08, keys6): AUTO = open / enter / edit / confirm (Menu role), UP / DOWN = move, MENU = back (Exit role). Footer: `UP/DOWN move  AUTO open  MENU back`.
  - Look target: #89 (white on black, red decorations, decided 2026-11-08); not yet built.
  - Doc (generated): [settings.md](settings.md).
- Key test panel (#39, open)
  - Shown in the console; `AwtoKeyTestSet` (`awto_keytest.inc`).
  - Live ADC key values + decoded key; host log reader `scripts/rtd_keywatch.py`.
  - Key routing: #129.

## 2. Fonts in use
- Our text fonts: 7 fixed fonts generated by `awto-rtdfw-ui` `tools/gen_font.py` from native Spleen and Tamzen bitmaps (`awto/osd/*.hex`) into `awto/osd/font_data.inc`; loader `awto/osd/font.c` (`osd_font_load`).

  | font | cell (w x row h, px) |
  |---|---|
  | Spleen 8x16 (default) | 8 x 18 |
  | Tamzen 8x15 | 8 x 18 |
  | Spleen 6x12 | 6 x 12 |
  | Spleen 5x8 | 5 x 8 |
  | Tamzen 5x9 | 5 x 9 |
  | Tamzen 6x12 | 6 x 12 |
  | Tamzen 7x13 | 7 x 13 |

- Each glyph is a window in the 12x18 1-bit RTD tile, centred horizontally (`x0 = (12 - w + 1) / 2`) and placed at a per-font top row. Odd widths start on the right column (seen on hardware, #108 row 4).
- Full printable ASCII (0x20..0x7E): 95 tiles, id 0 = blank (space), others 1..94; unknown characters use `?`. Fixed pitch, one tile id per cell.
- Tile = 9 OSD words (27 bytes); VLC-downloaded (`osd_tc_vlc_*`).
- Menu font setting `osd_font` (registry id 106): Spleen | Tamzen. Console: font 0 (Spleen 8x16) by default (#144); limit probe: font 3 (Spleen 5x8).
- Blob bank pin: font loader and constants in different ROM banks (#111, build workaround).
- Realtek SDK pop-ups: SDK font tables from flash, VLC-compressed (`0x3A17[0]`), 1-/2-/4-bit modes; glyph set descriptors per [osd-font-download.md](reversing/realtek-rtd/osd-font-download.md). Proportional widths come from the char command width field (B0 [4:0]). Our message cards still use the SDK proportional font (#89).
- Diagnostic tables, register views, pin ledgers, and similar dense data screens use fixed-cell text. The SDK-backed diagnostic renderer may reuse the normal Realtek glyph shapes, but must emit one glyph per OSD cell; normal menus, labels, and message cards remain proportional.
- Font SRAM budget: `H + 1 + W*H + 9*U <= 12288` words (U = unique tiles, H rows, W cols); 512 1-bit ids max: [osd-limits.md](reversing/realtek-rtd/osd-limits.md). SRAM size on hardware not yet read back.

## 3. Inputs to the OSD
- Front keys: physical order SOURCE, MENU, DOWN, UP, AUTO, POWER (POWER = digital P3.0, others on ADC A0 / A1). Decode, ADC bands: [reversing/realtek-rtd/buttons.md](reversing/realtek-rtd/buttons.md). #85: firmware uses the SDK reference decode, not the JXC ladder; fix open. #129: one input poller and one dispatcher (in progress).
- Test command byte (`fw/sdcc/awto_testcmd.inc`, host `scripts/osd_test.py`):
  - 0x01..0x05 = key messages menu (AUTO) / UP / DOWN / exit (MENU) / SOURCE, injected.
  - 0x10+n = OSD event n.
  - 0x20 / 0x26 = debug pop-up (console), 0x27 = clear holds.
  - 0x21 / 0x24 / 0x25: free (were the boot logo, removed in #144).
  - 0x41 / 0x42 key test, 0x43 / 0x44 GPIO panel.
  - 0x28 / 0x29 = debug messages on / off (NVRAM, #74).
  - 0x31..0x33 = input D1..D3 (#60).
  - 0x0C = frame buffer forced at the current timing (memory work mode, display setting re-run; FRC image only, else a "refused" line), 0x0D = back to the SDK choice (#165). RAM only. Sync log E3: one line per request and per memory-select change. Host: `scripts/mem_mode.py` (tools-frc) reads the DDR PHY flags before / after.
- Menu mailbox (`_vcp_box`, debug slave 0x35) and DDC/CI VCP 0xE0..0xE5 (0xE4 = menu command / state): [settings.md](settings.md), host `scripts/menu_cli.py`, `./dev.py settings|menu`.
- VCP 0xCA (OSD button control) may inject keys via the vendor path [?, buttons.md].

## 4. Tools
- `scripts/osd_render.py` + `scripts/osd_model.py`: simulator render of OSD frames (key actions, PNGs).
- `scripts/osd_catalog.py`: renders every layout, writes `sheet.png` + index.html.
- `scripts/asset_sheet.py` (awto-ddc-ui): contact sheets of every screen and font (SDK and awto).
- `scripts/menu_cli.py`: drive / read our menu (state, key, hold, open, select, set, get, back, close, walk); `--sim BIN` or `--bus N --serial S`.
- `scripts/osd_test.py`: raise OSD events / keys in the running firmware, hold or clear visuals.
- `scripts/rtd_osd.py`: clean-room PC-driven OSD over ISP (raw SRAM words, palette, windows, text); halts the MCU unless `--keep`.
- `scripts/rtd_keywatch.py`: live key press watch from the ADC regs.
- Other: `scripts/logo_decode.py` (OSD tile sheet), `scripts/vlc_probe.py`, `scripts/glyph_decode.py` (VLC font data).

## 5. Open work
- #87: menu look: always-on per-input status strip (2 lines), 2-line key legend, V freq with 3 decimals; colours per #89.
- #89: one design system for every screen (style, font, components; screens as data: [osd-screens-as-data.md](osd-screens-as-data.md)).
- #128: menu on the console display (one text layer, any font size, viewport scroll).
- #129: one key dispatcher; remove the SDK OSD state table.
- #85: key decode to the real SOURCE / MENU / DOWN / UP / AUTO / POWER ladder.
- #39: key test panel (open).
- #67: registry menu; inert rows listed in [settings.md](settings.md).
- #117, #122: SDK card bodies and hot-key menus still linked.
- #108: SDK defect list.
- #111: font loader bank pin.
