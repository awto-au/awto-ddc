# JXC 4K monitor: boot splash — format, draw path, awto replacement (static analysis)

Scaler: RTD2795-class. Splash = two-colour black "Dahua" logo on white, drawn by THIS firmware's OSD
engine (user-confirmed; no logo plugin in RTDCustomerTool, no separate boot-image chip).
No splash bytes written to flash yet (EDID sectors only — `edid-fix.md`). Open work: awto-ddc#5.

Tags: `[fw]` from our dump/decompile, `[spec]` regdb RTD2795T-CG (`re/regdb/`), `[tool]` RTDCustomerTool
data, `[measured]` bus-20 test, `[guess]`, `[?]` unknown.
Dump: `~/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin` (1 MiB).
Code: `scripts/make_logo.py` (awto encoder + pattern-gen), `scripts/rtd_osd.py` (volatile OSD draw),
`scripts/rtd_flash_sector.py` (flash write, EDID flow). Renders: `~/vendors/realtek/analysis/logo/`.

## TL;DR
- Bank 14 (0xE0000) is NOT the logo — it is three 14-bit gamma LUTs + a config blob [fw, this session]. Corrects the earlier "prime candidate" note.
- Whole 1 MiB flash has only 3 used regions: `0x00000-0x67000` (code + bank 0-6 overlays), `0xE0000-0xE3000` (gamma), `0xFB000-0xFD000` (settings). So any logo data is in `0x00000-0x67000` [fw].
- The logo is drawn by the SAME table-driven OSD glyph composer as the menus, and its glyph bitmaps are **VLC-compressed, downloaded from flash at run time via a banked pointer computed at run time** — not a fixed byte-slot [fw]. No raw uncompressed logo bitmap exists in range [fw, forensic sweep].
- Logo glyph atlas located + decoded: blob D `0x23B41` (586 tiles). Placement char-map is built at run time and not yet pinned → persistent patch still gated on it (awto-ddc#5). Reversible routes meanwhile: **volatile OSD RAM** (`rtd_osd.py`) and the **hardware pattern generator**.

## Splash hardware capability [spec from regdb / tool]
What the OSD + display hardware supports for a boot image:

| property | value | source |
|---|---|---|
| Encoding | OSD font glyphs (1/2/4 bpp) laid by a font-select MAP + OSD windows; NO raw-framebuffer splash register | [spec] regdb has only OSD window/font/LUT + OSD scaler, no blit/DMA-image reg |
| Glyph compression | VLC 4-bit/symbol prefix code, `0x3A17[0]` osd_compression_en; END=`1111_1111`; symbol→value map 0x3A0F-0x3A16 | [spec] |
| Glyph cell | 12×18 px typical (9 OSD words of 24 bit) [oss-understood]; font 2× via `0x3A0A` db_width/db_height; OSD scale-up block `0x3AC0+` | [spec] |
| Colour depth | 1-bit font = fg/bg indices (4 bit each) into palette; 2-bit & 4-bit font modes exist (`0x3A21`/`0x3A23`, `0x3A07[2]` f4b_color_sel) | [spec] |
| Palette | 64 entries × 24-bit RGB (`0x6E`=0x80\|idx, bytes to `0x6F`) | [spec] |
| Windows | 10 (WIN0-9); hor/ver start+end each **12-bit** → a window can cover the whole 4K panel and sit at any x,y; per-window colour/blend/border/shadow/gradient | [spec] |
| Max image | bounded by panel (3840×2160) via a full-screen window; logo detail bounded by font-SRAM budget (glyph words) + VLC stream size, not a fixed "image size" field | [spec] |
| Placement | fully positionable: window geometry (WINn ADR1/ADR2) + OSD origin `0x3A00/0x3A01` | [spec] |
| Tool logo feature | NONE — RTDCustomerTool V3.8 has no logo/splash upload (`CSplashScreenEx` = the PC tool's own GUI splash); no FlashSet logo param | [tool] |

- Firmware boot OSD state [measured, osd.md]: WIN0 start (0,4) end (156,80), colour 4, win_en+blend; fs_base=0x019, font_base=0x3F1; db_width+db_height on (2×), alpha type 10. (Small window = a menu/indicator; the full-screen Dahua splash is the glyph grid below, 2× scaled.)

## Bank 14 is gamma, not the logo [fw, this session]
`0xE0000-0xE2864`:
- `0xE0400-0xE0F30` (≈2864 B): high-entropy config/timing blob (`81a2 c058 c004 800f …`, repeating `058c004800f`), not a bitmap.
- `0xE0F30-0xE1732`, `0xE17CA-0xE1FCC`, `0xE2062-0xE2864`: three tables, 1025× u16-BE each, monotonic 0 → ~0x3c00/0x3ff0 (14-bit near-full-scale), smooth decaying slope (diffs 91,91,92,74,75,…58…) = three gamma/degamma curves (R/G/B or three presets). A VLC font would NOT form a smooth decaying ramp. First 7-8 entries = 0 (reserved).
- Small tables at `0xE00B4`, `0xE01B4`, `0xE01FC` [fw shape].

## Draw path (the splash composer) [fw]
From the firmware RE pass (`re/jxc-4k/`); addresses `bank:addr`, bank N = flash N·0x10000. One unified
OSD glyph composer draws menus and splash; invoked from 4 screen-builder sites.

- `bank1:0xb0f4` `osd_compose_glyph_grid_map` — writes a glyph-index grid (e.g. 23×27 cells) into font-select SRAM (3-byte OSD-word writer `bank6:0x65d1` via data port 0x92; row-command `bank6:0x6530`), computes `font_base`, calls `osd_set_font_bases`, sets window words + OSD scale `0x3A0A`.
- `bank1:0x97a5` `osd_fontdl_orient_enable` — download orient/rotation (`0x3A0B`), writes `0x3A18`, enables OSD via `0x3A02[0]` (`osd_enable_set bank6:0x5e35`).
- `bank6:0x4272` `osd_font_download_from_flash` (thunk 0x106b) — streams glyph bitmaps from SPI flash via `bank6:0x4445` `spi_flash_read_engine` (page reg 0x9F + SPI ctrl 0xFFF3). Toggles **VLC decode ON** (`0x3A17 |= 1`) around the stream, then OFF (`&= 0xFC`) → the downloaded glyph font IS VLC-compressed.
- Source address = a **banked far pointer built at run time**: bank byte = SFR `0xFFFF` (PBANK_SWITCH, current bank) via `DBB7→DC3C→SCA_INF_BWR_ADRH`; 16-bit offset = caller far-pointer `R2:R1` → `ADRM:ADRL`. Seeded from glyph-set descriptor table `bank1:0x3837`. NOT from `E1E8:E1E9` (that is OSD-SRAM `font_base`) nor `DBB8:DBB9` (OSD-SRAM dest word) — see STATUS section. Not a hardcoded constant.
- Composer call sites (callers of thunk 0x106b): `bank1:0x4bd0` (VCP menu), `bank1:0x8f33` (**power-on splash**, via `bank0:FUN_CODE_d986` + timed delays), `bank2:0xf070`/`0xf269` (menu/source/no-signal, variant from `E057 & 3`). Dispatch: bank0 thunks `0x0FAB`(→splash) / `0x0FDB`(→menu). See STATUS section.
- VLC value-map `0x3A0F-0x3A16`: burst-written (auto-increment from `0x3A0F`) from each blob's 8-byte header — no `MOV DPTR,#0x3A10..16` exists, which is why a DPTR scan finds nothing [SDK, `sdk-rl64xx-reference.md`].
- Logo glyph data: blob D `0x23B41` (below). Open: how the splash's first read at `0x1382F` (bank1) leads to blob D (bank2) — awto-ddc#5.

### VLC decode — CONFIRMED format, 2026-11-04T16:00+10:00 [static, `scripts/glyph_decode.py`]
Tile/glyph format fully confirmed by rendering: blobs A/C decode to crisp, recognisable icons and
"FPS"/"RTS" text; blob D (the logo) decodes to clean swoosh + "TECHNOLOGY" wordmark fragments.
- Blobs: `0x228C6` (53 glyphs, menu icons), `0x22BED` (98), `0x231AB` (189, FPS/RTS + crosshairs),
  `0x23B41` (586, **Dahua logo set**). Format = `[8-byte VLC value map][2-byte BE len][stream, END=0xFF]`.
- Confirmed params:
  - **Value map = the blob's own 8 header bytes** (16 nibbles vlc_0..vlc_f).
  - **Stream bit order = LSB-first** within each byte; decoded nibbles pair high-nibble-first into bytes.
  - **Cell = 1bpp 12×18 = 9 words×24bit = 27 bytes.** Word w → image rows (2w, 2w+1). The 3 stored
    bytes of a word read **B2, B1, B0** (reverse); within a byte **MSB = leftmost**. Pixel 1 = fg.
  - All four blobs: END lands exactly at the header length; decoded bytes = exact multiple of 27.
- **blob=atlas-needing-grid, NOT a full raster image.** 566/586 tiles unique, zero blank/solid tiles;
  gap-less grid render shears diagonally at every width 48-72 (per-row shift non-constant) ⇒ tiles are
  de-duplicated and stored in font-tool reference-scan order, not raster order. The logo IMAGE =
  the atlas placed by a separate runtime glyph-index char-map (built by `osd_compose_glyph_grid_map
  bank1:0xb0f4`), which is NOT a plain index array in flash (no u16-in-[0,586) run; SDK 0x4C/0x4E
  char-words absent as a dense run → compact/descriptor-driven encoding in our fw). Full analysis:
  `docs/reversing/realtek-rtd/osd-font-download.md` §4-4a. Composer grid params from bank1:0x8EFE
  (R3=0x10/16, R5=0x18/24, R7=0x12/18) are passed to `bank1:0xb0f4` = cell/grid geometry, not tile order.
- Debunked earlier candidates (unchanged): bank3 `0x328C6` = gamma LUT ramp (u16-BE monotonic); bank2
  mixed data+code tail.
- Renders: `~/vendors/realtek/analysis/logo/glyphdec/atlas_<A|B|C|D>_clean.png` (clean tile atlases);
  `atlas_023b41.png`, `grid_023b41_54x9_s100.png` (grid guess). Decoder: `scripts/glyph_decode.py`.
- **Still needed for a legible assembled logo:** the runtime glyph-index char-map. Cheapest: reboot,
  enter ISP while the splash is up (MCU halts, OSD SRAM persists), read font-select SRAM back with
  `rtd_osd.Osd.read_word`. Fallback: finish the Ghidra trace of `bank1:0xb0f4`. Tile format is done.

Font-base note [spec]: `font_base` is **15-bit** (0x3A0D[3:0], 0x3A0E[7:0], 0x3A17[5:3]); earlier "12-bit" was wrong.

## Built-in hardware pattern generator [spec from regdb]
Zero-art proof we control panel output. Volatile (lost on reset), reversible.
- D-domain: page 7 `0x07F0-0x07FF` `DISP_PG_*`. `0x07F0[7]` pg_enable; `[6]` pattern vs random; per-channel toggle/increment per pixel/line (bits [3:0]); `0x07F3/4/5` R/G/B initial; `0x07F6/7` deltas; `0x07F8/9` steps (≠0); `0x07FB` random formula; `0x07FD[7]` 10/12-bit.
- I-domain: page 0 `I_PG_*_M1` (0x0025 group), `pg_mode` idx98[7:6] (10=programmable, 11=random), R/G/B initials idx101/102/103.
- Examples (vertical bars / solid field / disable): `python scripts/make_logo.py patgen`.
- First proof-of-control on hardware: enable the D-domain generator (solid field or bars), confirm the panel changes, disable. No bitmap needed.

## awto splash: design + how to show it
Discreet mono logo on black, drawn the Realtek way (OSD window + 1-bit glyphs + palette).
Encoder: `scripts/make_logo.py` (clean-room; encodes from the OSD glyph format, no SDK code).
- Palette: index 0 = black `000000` (bg), index 1 = white `FFFFFF` (logo ink).
- Logo: `awto` wordmark, 1-bpp, our own 5×7 letterforms, packed into 12×18 glyph cells (2 cells, 24×18 px; 2× scalable by the OSD as the firmware does, or by a larger window).
- Window: WIN0 = whole panel (0,0 → 3840,2160), colour 0 → solid black background; glyph grid places the logo. Position by the map origin + `0x3A00/0x3A01` (centred or corner; discreet = small, corner or centre).
- Outputs (not git):
  - `python scripts/make_logo.py glyphs` → `awto_logo_sanity.png` (verified legible white "awto" on black) + `awto_glyphs.bin` (18 OSD words = 54 B).
  - `python scripts/make_logo.py osd-plan` → `awto_osd_plan.txt` (the `rtd_osd.py` op list).

### Volatile show (reversible — do this FIRST; proves control without flashing)
```
python scripts/rtd_osd.py <bus> --keep <ops from awto_osd_plan.txt>
```
Writes only OSD RAM/regs; a power-cycle reverts it. Use it to confirm geometry, colours and that the
logo appears, before any flash change. Pair with a boot capture to copy the real Dahua window geometry.

## Flash-patch plan — STATUS: atlas known, char-map + bank link open (awto-ddc#5)
Static RE pass 2026-11-04 (Ghidra decomp of `bank6:0x4272`/`0x4445`, regdb reg names, caller traces).

### Flash source address formula [fw, decisive]
`spi_flash_read_engine bank6:0x4445` drives the SPI reader with a 24-bit byte address in SFR
`0xFFF6:0xFFF7:0xFFF8` = `SCA_INF_BWR_ADRH:ADRM:ADRL` [spec regdb]; page reg `0x9F` = `PAGE_SEL`:
- `ADRH ← DC3C`, `ADRM ← R2 (param_2)`, `ADRL ← R1 (param_1)`.
- In `bank6:0x4272`: `DC3C = DBB7`, and **`DBB7 ← SFR 0xFFFF (PBANK_SWITCH, current program bank)`**
  (read at the call site, e.g. `bank1:0x8F18 MOV DPTR,#FFFF; MOVX; → DBB7`). Bank byte = current bank.
- `R2:R1` = far-pointer offset the caller passes (`R3=0xFF seg=current bank, R2:R1=offset`); both bank1
  sites pass `R2:R1 = 0x382F` ⇒ **first read = flash `0x1382F`** (bank1 base 0x10000 + 0x382F).
- So **src = `(PBANK_SWITCH << 16) | caller_offset`** — runtime-computed, but NOT E1E8:E1E9-derived.

### DBB8:DBB9 vs E1E8:E1E9 discrepancy — RESOLVED [fw]
Neither feeds the flash source; both are OSD-SRAM side:
- **`DBB8:DBB9` = OSD font-SRAM DESTINATION word** (set by the caller; `bank6:0x4272` passes it to
  `FUN_CODE_6868→0x66ab`, which programs OSD ports `0x94`/`0x90` — SRAM write setup, not a flash read).
- **`E1E8:E1E9` = `font_base`** (15-bit OSD-SRAM glyph pointer), computed in
  `osd_compose_glyph_grid_map bank1:0xb0f4` as `DBB2(cell_w)*DBB3(rows) + (DBB3+1)`, written at
  `bank1:0xB15E`, loaded via `osd_set_font_bases bank6:0x504d`. Never a flash address.
- The old "offset from E1E8:E1E9" and "DBB8:DBB9 src ptr" notes both mislabelled SRAM-side vars. True
  flash offset = caller far-pointer `R2:R1` → ADRM:ADRL; bank = `PBANK_SWITCH` via DBB7→DC3C→ADRH.

### VLC on the splash path [fw]
- `bank6:0x4272`: `0x3A17 = 0x3A17 & 0xfc | 1` before the stream, `& 0xfc` after ⇒ compression on.
- Value map = per-blob 8-byte header, burst-written (see VLC decode section).

### Which call site is the power-on splash [fw]
4 composer call sites (callers of thunk `0x106b`→`bank6:0x4272`), bank0-dispatched:
- `bank1:0x8f33` (entry `0x8ECC`, container `FUN_CODE_d986`) — **THE SPLASH**. `d986` is the ONLY path
  invoking the bank1 glyph builder (thunk `0x0FAB`), bracketed by timed delays (`0x0e25(100)`,
  `0x0de9(100)`) = hold-logo-then-continue. Far ptr FF:38:2F, descriptor `bank1:0x3837`.
- `bank1:0x4bd0` (`osd_screen_builder_1`) — big VCP **menu** (reads contrast/brightness e010/e034/e03e…,
  23×27 grid). Not the splash.
- `bank2:0xf070`/`0xf269` (entry `0xF049`, thunk `0x0FDB`) — generic **menu/source/no-signal** renderer,
  called from ~8 bank0 states; `0xf269` picks variant from `E057 & 3` (= INPUT SOURCE). Not the splash.

### Concrete target + what is open
- Splash first flash read = **`0x1382F`** (bank1): `0f 12 34 56 78 9a bc de` (8-byte header). Descriptor
  8 B later (`0x13837` = `00 08 00 00 … c0 ff 00 09 11 98 f1 60`). The body address after it is
  data-driven (`FUN_CODE_64bb`: ADRH←`DC35`, a flash-read byte).
- Logo atlas = blob D **`0x23B41`** (bank2, 586 tiles; sector `0x23000`, may span into `0x24000`+).
- Open (awto-ddc#5):
  1. Link `0x1382F` → `0x23B41` (or find which blob the splash really streams).
  2. Char-map: OSD SRAM read-back during splash, or trace `bank1:0xb0f4`.
- Patch = our atlas (blob D header map, ≤ original length) + char-map, in every sector touched. Minimal
  safe step: same-length blank atlas removes the Dahua logo without the char-map.

### Write procedure once the sector(s) are known (same flow as the EDID writer)
`scripts/rtd_flash_sector.py <bus> <sector_addr> <file4k> --write --expect-current <orig4k>`:
- dry run first (no `--write`): dumps + backs up the sector, diffs vs the new file.
- write path: release flash WP# (scaler GPIO sys 0x1036/0xFE26) → WRSR unprotect → erase 4 KB (0x20) →
  blank check → program 16×256 B pages → read-back + verify → restore status reg → reset scaler.
- One 4 KB sector at a time; note whether the glyph data + its offset table are in one sector or span
  several (patch every sector touched, and the offset table too if glyph sizes change).
- Revert: rerun with the saved backup as `<file4k>` and `--expect-current <the-new-data>`.
- Same engine as the EDID writer, already proven on all 3 units (1f5eb2f).

### Risk / recommendation
- Volatile OSD + pattern generator = safe, reversible, enough to prove control and preview the awto
  splash. Do these first.
- Do not flash the logo until open items 1-2 are done and a fresh dump + diff confirms exactly which
  bytes change. Code runs from the same flash: a patch that strays outside the blob can brick the unit.
