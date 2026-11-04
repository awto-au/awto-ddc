# JXC 4K monitor: boot splash — format, draw path, awto replacement (static analysis)

Scaler: RTD2795-class. Splash = two-colour black "Dahua" logo on white, drawn by THIS firmware's OSD
engine (user-confirmed; no logo plugin in RTDCustomerTool, no separate boot-image chip).
Nothing has been written to the monitor or flash.

Tags: `[fw]` from our dump/decompile, `[spec]` regdb RTD2795T-CG (`re/regdb/`), `[tool]` RTDCustomerTool
data, `[measured]` bus-20 test, `[guess]`, `[?]` unknown.
Dump: `~/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin` (1 MiB).
Code: `scripts/make_logo.py` (awto encoder + pattern-gen), `scripts/rtd_osd.py` (volatile OSD draw),
`scripts/rtd_flash_sector.py` (flash write, EDID flow). Renders: `~/vendors/realtek/analysis/logo/`.

## TL;DR
- Bank 14 (0xE0000) is NOT the logo — it is three 14-bit gamma LUTs + a config blob [fw, this session]. Corrects the earlier "prime candidate" note.
- Whole 1 MiB flash has only 3 used regions: `0x00000-0x67000` (code + bank 0-6 overlays), `0xE0000-0xE3000` (gamma), `0xFB000-0xFD000` (settings). So any logo data is in `0x00000-0x67000` [fw].
- The logo is drawn by the SAME table-driven OSD glyph composer as the menus, and its glyph bitmaps are **VLC-compressed, downloaded from flash at run time via a banked pointer computed at run time** — not a fixed byte-slot [fw]. No raw uncompressed logo bitmap exists in range [fw, forensic sweep].
- Consequence: a blind flash byte-patch of the Dahua logo is NOT safely possible yet (no identified slot; brick risk). Controllable, reversible routes that prove display control first: **volatile OSD RAM** (`rtd_osd.py`) and the **hardware pattern generator**.

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
- Source address = a **banked far pointer built at run time** (bank byte = SFR 0xFFFF current bank; 16-bit offset from XDATA `E1E8:E1E9`), seeded from glyph-set descriptor table `bank1:0x3837`. Not a hardcoded constant.
- Composer call sites (callers of thunk 0x106b): `bank1:0x4bd0`, `bank1:0x8f33`, `bank2:0xf070`, `bank2:0xf269`; dispatched via the OSD jump-table (`bank0:0xd271`). Which one is the power-on splash vs a source/no-signal screen is not isolated statically [?].
- VLC value-map `0x3A0F-0x3A16`: **never written by firmware** (exhaustive `MOV DPTR,#0x3A0x` scan = 0 hits) → runs on the hardware reset map (regdb reset of those fields = 0x00) [fw + spec].
- Candidate logo glyph data (VLC): bank 3 `0x328C6+` (big offset-table font, header `0000 0004 000e 001c…`) and bank 2 `0x228C6-0x26900` (VLC data). Not reduced to one offset statically — pointer is data-driven [?].

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

## Flash-patch plan — STATUS: BLOCKED pending source-pointer resolution
A persistent (survives power-cycle) splash means changing the flash the composer reads. NOT ready to
write, for a concrete reason:
- Splash glyph data is VLC-compressed and fetched by a **runtime-computed banked pointer**
  (`bank6:0x4272` ← descriptor `bank1:0x3837` + `E1E8:E1E9`). No single confirmed bank:offset for the
  logo glyphs ⇒ no sector to point at yet [?].
- Re-encoding our logo into the firmware's VLC glyph stream also needs the exact glyph-set layout
  (grid dims, glyph indices, map) the composer expects — not fully resolved statically.

What unblocks it (next RE, read-only):
1. Resolve the glyph-set source to a concrete `bank:offset`: statically evaluate `bank1:0x3837` +
   `bank2:0xf070` pointer loads and the `E1E8:E1E9` init; OR capture on hardware (break at
   `bank6:0x4272`/`0x4445`, read the SPI-flash address reg at power-on).
2. Decode that VLC region with the HARDWARE DEFAULT value-map (not identity — identity gave noise) to
   confirm it is the logo and learn its glyph layout.
3. Then the sector(s) holding that region (4 KB-aligned, `addr & ~0xFFF`) are the patch target.

### Write procedure once the sector(s) are known (same flow as the EDID writer)
`scripts/rtd_flash_sector.py <bus> <sector_addr> <file4k> --write --expect-current <orig4k>`:
- dry run first (no `--write`): dumps + backs up the sector, diffs vs the new file.
- write path: release flash WP# (scaler GPIO sys 0x1036/0xFE26) → WRSR unprotect → erase 4 KB (0x20) →
  blank check → program 16×256 B pages → read-back + verify → restore status reg → reset scaler.
- One 4 KB sector at a time; note whether the glyph data + its offset table are in one sector or span
  several (patch every sector touched, and the offset table too if glyph sizes change).
- Revert: rerun with the saved backup as `<file4k>` and `--expect-current <the-new-data>`.
- Prereq: confirm the EDID writer's program path works on this unit first (same engine).

### Risk / recommendation
- Volatile OSD + pattern generator = safe, reversible, enough to prove control and preview the awto
  splash. Do these first.
- Persistent flash patch of a compressed, pointer-indexed glyph set = brick risk until the source
  offset + glyph layout are pinned. Do not flash the logo until steps 1-2 are done and a fresh dump +
  diff confirms exactly which bytes change.
