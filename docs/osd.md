# OSD system: overview and entry point

Overview only; each fact lives in the linked doc. Tracking: awto-ddc#1 (index), #67 (menu), #86, #87, #85, #39.

## Naming
Never write bare "vendor": say which one.

| name | what | where it runs |
|---|---|---|
| **Dahua firmware** | the monitor's original factory firmware (Dahua/JXC). Known only by RE of the flash dump: buttons, boot logo, fonts | units as shipped; dump in `~/vendors/realtek/analysis/dumps/` |
| **Realtek SDK menu** | Realtek's RTD2014 demo OSD (9-icon menu, pop-ups) from the SDK source, compiled into our images | our images ("Vendor menu" on the System page until #87) |
| **awto menu** | our registry menu (#67) | our images (MENU key default) |

- Tag `[sdk-ui]` in `awto-rtdfw/settings/registry.tsv` = Realtek SDK menu fact.

## 1. Layers
### Hardware (RL6449 / RTD2795T)
- OSD SRAM (12288 x 24 bit words), row / char command layout, windows, palette, x2 scale: [reversing/realtek-rtd/osd.md](reversing/realtek-rtd/osd.md), [osd-limits.md](reversing/realtek-rtd/osd-limits.md).
- Font download (VLC decode, char words, burst DMA from flash): [osd-font-download.md](reversing/realtek-rtd/osd-font-download.md).
- No framebuffer: everything (logo, menus, pop-ups) is glyph cells + windows.

### Realtek SDK menu (RTD2014 demo OSD, compiled into our image)
- Pop-ups (input info, source hot menu, no-signal / no-cable messages, DDC/CI hot menu) and the 9-icon Realtek SDK menu.
- Code: SDK `RTD2014*Osd*.c` (p14 line, tmp/sdcc-port/src); drawn by `OsdDispOsdMessage` and the OSD state machine; opened by keys / events (`ucOsdEventMsg`, `ucOsdKeyMessage`).
- Walkthrough of every page and key action: [osd-realtek-sdk-menu.md](osd-realtek-sdk-menu.md).

### Our parts
- Boot logo
  - Code: `awto_logo_icons.inc`, `awto_logo_maps.inc` in `/mnt/2tb/git/awto-ddc-keys/fw/sdcc/` (fw lines are per branch; main has only `fw/sdcc/awto_diag.inc`); art in `docs/logo/`.
  - Drawn by the same glyph composer as the menus, glyphs VLC-downloaded; shown at boot, held by test cmd 0x24.
  - Doc: [boot-logo.md](boot-logo.md).
- Debug / info pop-up (#34, closed)
  - Code: `awto_dbgpop.inc` (`/mnt/2tb/git/awto-ddc-keys/fw/sdcc/`, branch wb-p14keys, worktree /mnt/2tb/git/awto-ddc-keys), hooked into `OsdDispOsdMessage` by keil2sdcc.py.
  - Same window / font / colours as the SDK input-info pop-up; opened by test cmd 0x26 (`osd_test.py debug`), cleared by 0x27.
- Registry menu (#67)
  - Code: `/mnt/2tb/git/awto-rtdfw/awto/settings/menu.c`, `set_table.c` (generated), `settings.c`, `vcp.c`; header `awto/include/menu.h`; registry `/mnt/2tb/git/awto-rtdfw/settings/registry.tsv` + `pages.tsv`.
  - Drawn through the text-cell layer (`osd_tc_glyph`, `awto/include/osd.h`) with our font.
  - Opened with the front keys, `menu_cli.py open`, or VCP 0xE4. Key roles use SDK names (Menu / Right / Left / Exit); physical keys after #85: MENU = enter / edit / confirm, UP / DOWN = move, AUTO = back.
  - Doc (generated): [settings.md](settings.md).
- Key test screen (#39, open)
  - Code: `awto_keytest.inc` + `awto_keypop.inc` in `/mnt/2tb/git/awto-ddc-keys/fw/sdcc/` (branch wb-p14keys); hooks `AWTO_KEY_SCAN` / `AWTO_KEY_MSG` in RTD2014Key.c.
  - Shows live ADC key values + decoded key in the Realtek pop-up style; host log reader `rtd_keywatch.py`.

## 2. Fonts in use
- Our cell font: 95 glyphs (ASCII 0x20..0x7E -> ids 0..94), 12x18 1-bit cells, 9 OSD words (27 bytes) per glyph; `tools/gen_font.py` -> `font_tab.inc` -> `font.c` (`osd_font_load`) in awto-rtdfw. Fixed pitch, one glyph id per cell.
- Realtek SDK pop-ups and the boot logo: SDK font tables downloaded from flash, VLC-compressed (`0x3A17[0]`), 1-/2-/4-bit modes; glyph set descriptors per [osd-font-download.md](reversing/realtek-rtd/osd-font-download.md). Proportional widths come from the char command width field (B0 [4:0]).
- Font SRAM budget: `H + 1 + W*H + 9*U <= 12288` words (U = unique tiles, H rows, W cols); 512 1-bit ids max: [osd-limits.md](reversing/realtek-rtd/osd-limits.md). SRAM size on hardware not yet read back.

## 3. Inputs to the OSD
- Front keys: physical order SOURCE, MENU, DOWN, UP, AUTO, POWER (POWER = digital P3.0, others on ADC A0 / A1). Decode, ADC bands and `osd_key_event_idx`: [reversing/realtek-rtd/buttons.md](reversing/realtek-rtd/buttons.md). #85: firmware uses the SDK reference decode, not the JXC ladder; fix open.
- Debug test byte (`g_stAwtoDiag + 0x28`, #33): 1..4 = menu / right / left / exit key injected after the key scan, 0x10+n = OSD event n, 0x24..0x27 = logo / logo-off / debug / clear. Host: `scripts/osd_test.py`.
- Menu mailbox (`_vcp_box`, debug slave 0x35) and DDC/CI VCP 0xE0..0xE5 (0xE4 = menu command / state): [settings.md](settings.md), host `scripts/menu_cli.py`, `./dev.py settings|menu`.
- VCP 0xCA (OSD button control) may inject keys via the vendor path [?, buttons.md].

## 4. Tools
- `scripts/osd_render.py` + `scripts/osd_model.py`: simulator render of OSD frames (key actions, PNGs). Known gap #86: runtime-built text (info / debug pop-up text panel) not drawn.
- `scripts/osd_catalog.py`: renders every layout, writes `sheet.png` + index.html.
- `scripts/menu_cli.py`: drive / read our menu (state, key, hold, open, select, set, get, back, close, walk); `--sim BIN` or `--bus N --serial S`.
- `scripts/osd_test.py`: raise OSD events / keys in the running firmware, hold or clear visuals.
- `scripts/rtd_osd.py`: clean-room PC-driven OSD over ISP (raw SRAM words, palette, windows, text); halts the MCU unless `--keep`.
- `scripts/rtd_keywatch.py`: live key press watch from the ADC regs.
- Other: `scripts/logo_decode.py` (OSD tile sheet), `scripts/vlc_probe.py`, `scripts/glyph_decode.py` (VLC font data).

## 5. Open work
- #86: osd_render draws no runtime text.
- #87: red redesign of the menu: always-on per-input status strip (2 lines), 2-line key legend, nicer font, V freq with 3 decimals.
- #85: key decode to the real SOURCE / MENU / DOWN / UP / AUTO / POWER ladder.
- #39: key test screen (branch wb-p14keys, not on main).
- #67: registry menu; 49 of 101 rows still inert.
