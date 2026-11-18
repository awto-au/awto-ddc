# Saver frame rate: what the OSD hardware can do instead of the CPU

Status 2026-11-18 (Dan: "get some agents to sort out how to get to 25 fps"). Scope: hardware features only; per-saver redesign and CPU budgets live in their own docs (`docs/saver-fps-budget.md`, per-saver docs). Nothing flashed, no production firmware change.

- Tags: `[spec]` regdb `re/regdb/RTD2795T-CG.tsv.gz`; `[sdk]` Realtek SDK source in `fw/sdk`; `[hw]` measured on our units; `[emu]` fw_sim / `osd_model.py`; `[guess]`; `[?]` unknown (says what resolves it). Conventions: awto-dan `docs/embedded/reversing/README.md`.
- Register and limit reference (one place per fact): [OSD manual](osd/README.md); this file keeps the ranking and the test plan.
- Numbers script: `python scripts/saver_hw_budget.py` (burst byte time, tile upload cost, run-glyph budget); log `tmp/logs/saver_hw_budget.log`.
- Target: 25 fps = 40 ms per frame, shared with the main loop (DDC/CI, keys).

## Baseline (sim, dw8051 model, image `hwbase` = main 6df194c, 2026-11-18)

| saver | sim today | needed for 25 fps |
|---|---|---|
| Scope 1 | 854 ms / frame (1.17 / s), pass mean 18.1 ms | 21x |
| Scope 2 | 178.8 ms / frame (5.59 / s), 4.47 ms per column | 4.5x |
| Asteroids | pass mean 11.9 ms, 5 frames / s (paced, 8 ticks / s) | 5x |
| Pac-Man | 4.4 ms per sub-step, paced at 31 ms (32 / s) | CPU already fits; motion is design-limited (3 px per sub-step) |

- Scope 1 / 2 are bound by per-pixel compute, not by OSD writes: writes are ~5 % (Scope 1: 384 tiles x 27 B x 4.12 us = 43 ms of 854). Only features that remove pixel work reach 25 fps; write-path features matter once the compute is gone.

## Ranked list (score = ms saved per frame x confidence)

| # | feature | savers | est. saved per frame | confidence | cheap to try |
|---|---|---|---|---|---|
| 1 | Run-glyph trace: 1-bit chars 2..6 px wide, glyph = one vertical run; frame = map writes only | Scope 1, Scope 2 | Scope 2 ~170 of 179 ms, Scope 1 ~800 of 854 ms [guess: est. 0.2-0.7 ms of port writes per frame, `saver_hw_budget.py`] | medium: width field [sdk+hw proportional text], min width + 240-char rows [?] | yes: host-only ISP test T-C |
| 2 | MCU clock x2 (`_MCU_SPEED_UP_SUPPORT`) | all | Scope 2 -64.6 ms (-36 %), Scope 1 -186 ms (-22 %), Asteroids pass -2.5 ms (-21 %) [emu] | medium-high: SDK option for RL6449 [sdk], sim run [emu], no hardware run | build flag + flash unit 3 (T-L) |
| 3 | Window grid lines (WIN2/3/4) for the graticule + chessboard windows for dotted cursors | Scope 1, Scope 2 | Scope 1 ~60-90 ms (graticule dots: `cursor_init` 7 % + part of `cursor_plot`), Scope 2 ~10-25 ms (base copies, cursor-only tiles) [guess] | medium: windows [hw], grid / chessboard [spec+sdk+emu] | yes: host-only T-A, T-B |
| 4 | Burst DMA XRAM -> data port, one burst per column of contiguous glyph slots | all tile savers | Scope 1 ~37 ms, Scope 2 ~15 ms, Asteroids ~60 us per tile [guess from SDK gap formula] | medium-high: in use for SDK pop-up text [sdk+hw], speed [?] | firmware test op T-H |
| 5 | Direct port stores instead of `ScalerOsdDataPort` (4.12 -> 2.39 us / B) | all | Scope 1 ~18 ms, Scope 2 ~8 ms, Asteroids ~46 us per tile | high [hw: T1 / T2 / T5 PASS, `docs/osd-hw-tests.md`] | done 2026-11-18 (data stores; Dan lifted the rule) |
| 6 | Hardware 180 turn on download (decoder raw path) | all, Rotate 180 (unit 3) | Scope 2 ~20 ms (176.0 vs 155.8 ms Rotate 180 vs upright, saver-library step 3) | medium: SDK does exactly this [sdk], VLC + 180 runs on unit 3 [hw]; raw 2-bit planes [?] | firmware test op T-I |
| 7 | SPI dual-output read (`READ_INSTRUCTION` read_mode 10) + cache common page | all | 10-25 % of fetch stalls, more at 2x clock [guess] | low-medium [spec] | runtime poke, reset recovers (T-M) |
| 8 | Palette animation, 1-bit per-cell colour ageing (phosphor), blink | Scope 2, Pac-Man | ~0 CPU today; new effects at ~12 us per palette entry | high [hw: palette port in use] | yes |
| 9 | Font B second map as one hardware sprite | Pac-Man, Asteroids ship | 4 tiles per frame per sprite [guess] | low-medium: overlap with map A [?] | host-only T-D |
| 10 | Single-plane map writes (`bytesel` B1 only): 1 B per changed cell instead of 3 | Pac-Man, Scope 2, #1 | Pac-Man ~0.1 ms per sub-step | high [spec+sdk, hw single-plane reads] | yes |
| 11 | Pop-on page flip (`FRAME_CTRL_18` display_base_sel) | all | 0 CPU; tear-free frames, drawing decoupled from showing | medium [spec+sdk+emu] | host-only T-E |
| 12 | Coarse + fine hardware scroll (roll-up rows [hw]; fs_base +1 columns [guess] + font delay 1 px) | strip-chart scope variant | all but one column per frame | vertical high, horizontal low | host-only T-F |
| 13 | Masked bit writes into font SRAM (`FRAME_CTRL_33` bit_block_en, `FRAME_CTRL_34`) | sparse pixels (shots, cursor dots) | ~15 us per pixel vs 65-130 us per tile re-upload [guess] | medium [spec+sdk on map words] | firmware test op T-J |
| 14 | `SCA_INF_PERIOD` / `SCA_WR_INTRVL` / `CYCLE_GATING` tuning of every register access | all | [?] | low | runtime poke (T-K) |

- Cheapest first steps: #5 (rule change, no test), #2 (one SDK define, sim already done), #1 + #3 checked host-only over ISP in one session (T-A..T-F).
- Pac-Man needs no CPU feature for 25 fps: smoother motion is a generator / data change (more sub-steps); #8 / #9 / #10 make it nicer.

## (a) Motion and layout without rewriting tiles

### Windows as moving rectangles
- 26 windows: WIN0..9, WIN4_1..4_8, WIN5_1..5_8 [spec]. Each: solid colour (64-LUT index), border / shadow / 3D button (1-8 px), rounded corners (WIN0, 4_x, 5_x), gradient (WIN0, 5..9), chessboard (WIN8, 9, 4_x, 5_x), grid lines (WIN2, 3, 4) [spec].
- Registers (window SRAM, `OSD_WRITE_OPTION` sram_sel 00, word `0x100 + 4n` for WIN0..9): `WINn_ADR1` hor_sta / ver_sta, `WINn_ADR2` hor_end / ver_end (12 bit each), `WINn_ADR3` win_color / blend_en / win_en [spec]; field layout confirmed on the boot window [hw, `docs/osd/windows.md`].
- Move = 2 words (6 data bytes + address) ~ 20 us. Position fields are "effective at Vsync rising, cross-byte double buffer" with global double buffer on (`OSD_MISC_PORT` db_enable) [spec]; `win_en` is never double-buffered [spec]. Our screens switch global double buffer off (`AwtoOsdScreenBegin`): window moves then apply immediately (tear risk only).
- Priority vs font: `FRAME_CTRL_07` win3 / win4_higher_font, `FRAME_CTRL_08` win2 / win8 / win9_higher_font, `WIN4_x ADR3` bor_higher_font [spec]. Other windows sit below the font.
- No bitmap in a window: sprites of arbitrary shape need a font map (font B below) or tiles.
- Uses: Asteroids shots (4-6 small squares, removes `osd_pixel` + dirty tiles), HUD bars, Scope cursor lines (chessboard below).
- Delay sets: each window / font picks delay set 1 or 2 (`osd_delay_sel`, `FRAME_CTRL_00..06`) [spec]: one register write moves every member of a set.

### Grid-line windows (graticule in hardware)
- WIN2 / 3 / 4, `WINn_ADR7`: grid_width 1-4 px, grid_color, grid_h_en, grid_v_en, grid_offset (px); `WINn_ADR8`: grid_pitch [14:0] (um), grid_en [spec]. SDK `ScalerOsdDrawGridLine` writes `0x183 + 7 (n - 2)` and `ScalerOsdDrawGridLinePanelPitch` sets `FRAME_CTRL_35..37` panel pitch (um, U9.2) [sdk]. Line spacing = grid pitch / panel pitch [guess].
- `osd_model.py` renders it, assuming panel pitch 993 [emu, guess].
- Saves: the graticule leaves the tiles: trace tiles become pure trace with transparent background (more dedup, no static-base copy per tile: `S2BaseCopy` / `S2Base`, Scope 1 graticule dots `cursor_init`).
- Limits: solid lines only (no dotted minor ticks); 3 grid windows (e.g. major grid, centre cross with 1 line each way via offset + large pitch); inside the scale-up region lines scale with it [guess].
- Test: T-A.

### Chessboard windows (dotted cursors)
- `WINn_ADR4` (4_x, 5_x) / `ADR5` (8, 9): cb_color_en, cb_color1, cb_color2 [spec]; SDK `ScalerOsdWindowChessboard` [sdk]. Square size [?] (T-B).
- A 1-px wide chessboard window = a dotted vertical line moved by 2 words: Scope 2's two cursors leave the per-frame tile set (today cursor-only tiles: up to 9 per column, `scope_saver2.c`).

### Second map: font B (one hardware sprite layer)
- `FRAME_CTRL_18` fontx2_en: font A rows at `row_base0` / `fs_base0`, font B at `row_base1` / `fs_base1` (`FRAME_CTRL_19..1D`) [spec]; font B position `FRAME_CTRL_27..29` font_b_hori / vert_delay (12 bit, Vsync latched) [spec]; SDK `ScalerOsd2FontFunction` [sdk]; `osd_model.py` draws B after A at its own origin [emu].
- Sprite = a small font B map (e.g. 2 x 2 cells), moved per frame by 3 register bytes; glyphs change only when the animation frame does.
- [?] whether B overlaps A (transparent background showing A) or the two areas must not overlap; priority A vs B; scale-up covering both. T-D decides.
- Uses: Pac-Man player (1-px motion, no piece composition), Asteroids ship.
- Font mask regions `FRAME_CTRL_45..4C` (row / column start / end per font) hide cells [spec].

### Scale-up engine: global, not per window
- `OSD_SU_CRTL` (osd_su_en, boundary mode), `OSD_VER_FACTOR` / `OSD_HOR_FACTOR` (6 bit, Xi / Xo x 64), region start / size 12 bit (`OSD_SU_VER_ST_*`, `OSD_SU_HOR_ST_*`, `OSD_SU_*_SIZE_*`) [spec]; region in display coordinates [hw, `docs/osd/scale-up.md`].
- One region, one factor pair: no per-window or per-map scale [spec: no second register set].
- Whole-OSD x2: `FRAME_CTRL_0A` db_width / db_height [spec].
- Row commands: height 1..64 per row (`ScalerOsdRowHeight`) [sdk]; no per-row double width / height on this chip [sdk: only global `_OSD_DOUBLE_*`]; per-row 2x bits are an ORTD2662 feature [oss], not seen here. Taller rows add blank lines, they do not scale glyphs.

### Character width (basis of #1)
- 1-bit char word B0[4:0] = displayed width in px; 2-bit / 4-bit chars have no width field (12 px) [sdk `ScalerOsdCharacterWidth`, `osd_model` layout]. `FRAME_CTRL_02` disp_zone picks which part of the 12-px glyph a narrow char shows (middle / left / right) [spec].
- Proportional widths render on hardware (SDK message-card text) [hw]; widths below 4 px [?]; blank command 4..255 px [sdk].
- Row command char count 8 bit: <= 255 chars per row [spec]; 160 chars per row measured clean [hw, unit 2, `docs/osd/tiles-fonts.md`]; display fetch below map word 8192 [hw].

### Run-glyph trace (#1)
- Glyph set: every vertical run [a, b] inside an 18-row cell, drawn across the full 12 columns: 171 runs + blank = 172 1-bit glyphs = 1548 words [arith]. Char width CW px, fg colour per cell (B2 = fg << 4 | bg, bg 0 = transparent).
- Per frame: per trace point (CW px of x) the cells its run crosses get the run glyph; cells left by the old trace get blank. Only changed cells are written: B1 (glyph id) only, `bytesel` 010; address set only when the next cell is not adjacent.
- Budget (`saver_hw_budget.py`, Scope-2-like pulse moving 8 px / frame):

| raster | CW | chars x rows | map + glyph words | cells changed / frame | port writes / frame |
|---|---|---|---|---|---|
| 480 x 270 (Scope 2 today, 8x scale) | 4 | 120 x 15 | 1816 + 1548 | 53 | ~0.3 ms |
| 480 x 270 | 2 | 240 x 15 | 3616 + 1548 | 72 | ~0.35 ms |
| 960 x 540 (4x scale) | 4 | 240 x 30 | 7231 + 1548 | 101 | ~0.55 ms |

- Graticule then comes from #3 (windows under the font); readouts / labels stay glyph cells in rows the trace does not enter (or font B).
- Phosphor persistence for free: old trace cells get a dimmer fg index (B2 only, 1 byte) instead of blank; a palette ramp makes the decay (#8).
- Risks: min char width; 240-char rows; per-cell fg colour only (one colour per cell); two traces in one cell need a union glyph (not in the set).
- Asteroids: lines at any angle are per-column runs too, but overlapping objects in one cell lose segments: not a fit; Asteroids keeps tiles.

### Scroll
- Vertical roll-up: `FRAME_CTRL_18` osd_special_en, `FRAME_CTRL_19` row_base0, `FRAME_CTRL_1B` / `1C` fs_base0 [spec]; used by the console on hardware (`osd_tc_scroll`) [hw]; 12-bit base wraps at 4095 [hw, `docs/osd/tiles-fonts.md`].
- Horizontal: fs_base + 1 shifts every row one cell left, wrapping each row's first cell onto the previous row [guess]; fine shift by `FRAME_CTRL_24..26` font_a_hori_delay (1 px with `FRAME_CTRL_06` hori_delay_step_sel) [spec]. Mask the wrapped column with the font mask region [spec]. T-F.

### Page flip (pop-on)
- `FRAME_CTRL_18` = osd_special_en | pop_on_en | display_base_sel: shows base 0 or base 1 (row + font-select base pairs above) [spec]; SDK `ScalerOsdPopOn` [sdk]; `osd_model` models it [emu].
- Draw frame N+1 into the hidden map, flip one bit: no half-drawn frames on screen. `FRAME_CTRL_18` is RW, not listed as Vsync latched [spec]: flip at DVS (`ScalerTimerWaitForEvent(_EVENT_DVS)`, used by the text layer).
- SRAM: two maps. Scope 2 map 616 words x 2 fits.

### Blink
- No hardware blink on this chip: SDK `ScalerOsdSetBlinking` is an empty function [sdk]; the 1-bit / 2-bit char words carry no blink bit (B0[7:6] = type) [sdk]. The ORTD2662 blink bit [oss] does not apply. Blink = palette toggle (#8).

## (b) Colour tricks

- Palette: 64 x 24 bit, `OVERLAY_LUT_ADDR` (0x80 | index) + 3 bytes to `COLOR_LUT_PORT` [spec+sdk `ScalerOsdSetColorPalette`] = 5 register writes (~12 us). Effective immediately, no Vsync latch listed [spec] (a mid-frame change can split one frame).
- Uses (no map / glyph writes): Pac-Man power pellet and dot blink, frightened-ghost white / blue flash (all ghost cells share the index), Scope cursor blink, colour cycling of a 4-bit glyph set.
- Phosphor decay: 1-bit cells carry their own fg index (16 per cell, B2[7:4]): age old trace cells by rewriting B2 (#1); 2-bit cells carry 4 indexes (`ScalerOsdChange2BitColor` packing) [sdk].
- Alpha: one global level `OVERLAY_CTRL` / `OVERLAY_CTRL1` alpha_blending_level (8 bit) + type `FRAME_CTRL_0A` alpha_blend_type (window / all / window + char background) + per-window blend_en; specific-colour blending `FRAME_CTRL_08` / `09` (type 2); window 7 blending (type 3, `FRAME_CTRL_21`) [spec+sdk]. No per-window alpha level: not usable for per-frame persistence.
- Highlight windows 4_1..4_8: `FRAME_CTRL_2A..56` fg / bg colour override for the font inside the window [spec+sdk `ScalerOsdWindowHighlightFunction`]: recolour a rectangle of text with 2 writes.
- Gradient windows (WIN0, 5..9) and the display pattern generator (`DISP_PG_*`, page 07: per-pixel / per-line increment or toggle, random mode) [spec] give backgrounds (CRT glow, noise) at no CPU cost; neither draws thin lines.

## (c) OSD SRAM write path

| path | per byte | evidence |
|---|---|---|
| `ScalerOsdDataPort` (banked call per byte) | 4.12 us | [hw] T1 |
| direct `AWTO_XFR` store loop, EA off | 2.39 us | [hw] T2 |
| burst DMA, gap from `hb_osd_gap` at dclk 533 MHz | ~0.46 us + ~16 register accesses setup | [sdk formula + guess: SYS period = MCU clock] |

- Address auto-increments per data access [hw]; `OSD_WRITE_OPTION` bytesel any subset of B0 / B1 / B2 (001..111) [spec]: write only the changed byte of map words (#10).
- Burst DMA: `SCA_INF_CONTROL` reg_burdat_wr + addr_non_inc, target `SCA_INF_ADDR` = 0x92, source `SCA_INF_BWR_ADRH/M/L`, count `SCA_INF_BWR_COUNT_H/L`, `BANK_SWICH_CONTROL` burst_data_source_sel = XRAM, gap `SCA_INF_PERIOD` [spec]; our `hb_burst` (`fw/rtdfw/awto/reg/burst.c`) implements the SDK sequence; SDK pop-up text uses it from XRAM (27 B bursts) [sdk+hw]. MCU halts until done (interrupts release it) [spec].
  - Gap: g = 12109500 / dclk_khz - 2 (x2 with db_width): the port takes one byte per ~276 display clocks [sdk-derived]. Hard ceiling for any write path ~0.4-0.5 us / B [guess]; MCU stores at 1.95 us / B are below it [hw: T2 PASS].
  - Per-tile bursts gain little (setup ~ 38 us vs 27-54 data bytes); gain comes from one burst per column: dynamic glyph slots allocated contiguously, tiles staged contiguously in XRAM (Scope 2 column <= 9 tiles = 486 B).
- VLC hardware decoder (`FRAME_CTRL_0F..17`) [spec+hw (fonts)]: compressed glyph upload; sparse trace tiles shrink ~3x on the wire, but the MCU must VLC-encode them first: no net gain once bursts are cheap [guess].
- Decoder raw path + rotation (#6): `FRAME_CTRL_17` osd_compression_en + decode_nocom_data, `FRAME_CTRL_0B` f_dl_swap 01 (180) + hw_rotate_en: the SDK sends uncompressed glyphs through it to turn them (`ScalerOsdHardwareCompression`, burst source, 2 ms wait after) [sdk]; poll `FRAME_CTRL_0B` buf_empty / buf_valid instead of the 2 ms [spec]. Removes `AwtoOsdTurn` / `AwtoOsdRevByte` per byte. `docs/osd/rotation.md` says f_dl_swap needs the compressed path: the SDK raw mode is that path with decode_nocom_data = 1. Map mirroring stays in software.
- Auto rotation `FRAME_CTRL_41` (auto_rotate_en, dir 10 = 180, rotate_flib engine turns the font library in SRAM, char remap LUT) [spec]: would turn map and glyphs in hardware; behaviour at 180 [?] (T-G).
- Block copy inside SRAM: none in the regdb [spec: no copy / fill engine on page 3A or the 0x90-0x94 port]; no glyph-repeat command [sdk, `docs/osd/tiles-fonts.md`].
- Masked writes (#13): `FRAME_CTRL_33` bit_block_en + bit_block_byte_sel, `FRAME_CTRL_34` per-bit protect mask: unprotected bits of the selected byte change, others keep their value [spec]; SDK uses it on map B0 [sdk]. Set one pixel = bytesel one plane, mask all but its bit, address, write 0xFF.
- Vblank-only writes: not required, writes while shown and scaled read back exact [hw, T2]; window / frame registers marked RW4 latch at Vsync when double buffered [spec]; SRAM words never latch (use pop-on for tear-free maps).

## (d) MCU speed levers

| lever | today | max / option | evidence | effect |
|---|---|---|---|---|
| MCU clock | 87.75 MHz (`MCU_CONTROL` flash_clk_div 4, `MCU_CLOCK_CONTROL` mcu_clk_div 1, M2PLL) [hw, unit 2 2026-11-12 `tmp/regs/*-ps-*.json`] | 175.5 MHz: `_MCU_SPEED_UP_SUPPORT` -> `_FLASH_CLK_DIV` 2, `_FLASH_2_CLK_DIV` 4 (SPI stays 43.9 MHz) [sdk `Scaler_Option.h`]; Timer2 / Timer0/1 counts derive from the dividers [sdk] | gated on local dimming in `Project_Option.h`; `Project_Config_Check.h` warns it "should be ON" with it [sdk]; DW8051 rated > 120 MHz on <= 0.25 um [spec, DW8051 brief] | sim: Scope 2 1.57x, Scope 1 1.28x, Asteroids pass 1.27x |
| SPI read mode | fast read 0x0B, 1 bit (`READ_INSTRUCTION` read_mode 01) [sdk `ScalerMcuInitial`] | 10 = dual output (0x3B), 11 = dual I/O [spec]; MX25L8006E has dual output [guess: datasheet not on disk] | cache line fill data phase halves | [?] |
| cache | on, full size, common page off (`CACHE_OPTION` = 0) [hw] | `CACHE_OPTION` common_page_en + `COMMON_START_ADDRESS_H/L`: the 0x0000-0x4FFF common area cached once, not once per bank [spec]; SDK switches it off explicitly [sdk] | fewer misses after bank switches (trampoline 5-9 % of saver time) | [?] |
| MOVX stretch | `CKCON` MD = 0 (2 cycles) [sdk] | already minimum | - | none |
| register access | `SCA_INF_PERIOD` 3 (left by the last non-OSD burst) [hw], `SCA_WR_INTRVL` 0x80 [hw], `CYCLE_GATING` reset 0x0F [spec] | period "halts the MCU extra time TI in normal access" [spec]: 1 or 2 may shorten every scaler access | [?] T-K |
| dual DPTR | `DPS` SFR 0x86 [spec+sdk Keil MODDP2] | copy loops without DPTR reloads; SDCC does not emit it (hand asm) | ~2 cycles per copied byte; superseded by burst DMA | low |
| MDU | none: DW8051 has no multiply / divide unit [spec, DW8051 brief]; no multiplier in the regdb [spec] | table lookups / shifts instead of `__mulint` / `_divslong` | - | - |
| DMA | only the burst-write engine (scaler registers / OSD port, from flash or XRAM) [spec] | (c) above | - | - |

- Measured on unit 3 (2026-11-18): `docs/clock-sweep.md` (MCU 43.9 .. 350.8 MHz and SPI 21.9 .. 70.2 MHz at run time; Scope 2 5.6 -> 8.3 / s at 175.4, 12.4 / s with SPI 70.2, 17.6 / s at 350.8).
- Sim experiment (2026-11-18, not kept): `Project_Option.h` `_MCU_SPEED_UP_SUPPORT` forced `_ON`, image `hwspd`, same commit as `hwbase`; `scope2_sim.py --frames 6`: 178.8 -> 114.2 ms / frame (5.59 -> 8.76 / s); `saver_loop_cost.py --case scope`: 854 -> 668 ms / frame; `--case asteroids`: pass mean 11.9 -> 9.4 ms. Logs `tmp/logs/hw_s2*.log`, `hw_loop*.log`. Gain < 2x: the sim charges flash-fetch stalls at the unchanged SPI clock (cache model sizes assumed, `docs/sim-cpu-model.md`).
- Risks of x2: our own delay calibrations (`g_ucAwtoCal5`, `docs/delays.md`), DDC debounce (`_TMDS_DDC_DEBOUNCE_NORMAL` doubles in the SDK), WDT counts real time (unchanged), power / heat [?], `hb_osd_gap` assumes the 87.75 MHz system clock (recompute).

## (e) Hardware pattern / line drawing

- No line or shape engine for the OSD [spec: page 3A + window words list none]. What exists: windows (rectangles, borders, rounded corners, gradients, chessboard), grid lines (WIN2-4), font mask / window 7 mask regions [spec].
- Graticule: grid windows (#3) do the major lines; minor ticks on the centre axes stay glyph cells (static) or thin windows (26 windows total).
- Display pattern generator `DISP_PG_*` (page 07) and input pattern generator `I_PG_*` (page 00): per-pixel / per-line increment or toggle with step counts, random mode [spec]: video-path backgrounds (stripes, ramps, noise) behind a transparent OSD; no thin lines, and they replace the picture [guess].
- Overlay / PIP: the OSD blends over the picture by the alpha settings in (b); the video highlight window (`HLW_*`, page 0) switches picture processing per region and draws a coloured RGB border around the region (width, colour, per-side disable; `0x006C[6]` hides it) [spec]; not part of the OSD SRAM ([docs/osd/windows.md](osd/windows.md), OT-18).

## Minimal hardware tests (unit 3; NOT run: agent a5cec59bb6f242e33 owns unit 3)

Host-only over ISP (`scripts/rtd_osd.py 11 --keep ...`: MCU halted, the OSD keeps showing what is written; reboot after). No firmware change, no flash.

| test | writes | proves |
|---|---|---|
| T-A grid | `wr:0x3A35..37` panel pitch; WIN2 words 0x108..0x10B (rect over the panel, win_en) + 0x183 / 0x184 (grid width 1, colour, H + V, pitch = 10x panel pitch, grid_en) | grid lines exist, line spacing = pitch / panel pitch, priority vs font, scaled with scale-up on |
| T-B chessboard | WIN4_1 words 0x200..0x203 (1 x 400 px), 0x164 (cb_en, two colours) | dotted vertical line; checker square size |
| T-C narrow chars | one 1-bit glyph solid; map row of chars with B0 = 0x40 \| w for w = 1, 2, 3, 4, 6; then a row command with 240 chars | minimum displayed width, advance = width, disp_zone effect, 240-char row fetch (#1) |
| T-D font B | `FRAME_CTRL_18` fontx2_en, `FRAME_CTRL_19..1D` bases, font B map 2 x 2 over map A, `FRAME_CTRL_27..29` delay stepped | B overlaps A with transparent bg (sprite) or not; which is on top |
| T-E pop-on | two maps, toggle `FRAME_CTRL_18` = 0xC0 / 0xC1 | page flip works, switch is clean |
| T-F h-scroll | static map, fs_base +1, +2 | coarse horizontal scroll and its wrap |
| T-G auto rotate | `FRAME_CTRL_41` = 0x21 on an upright test map | hardware turns map + glyphs 180 (would delete all software turning) |
| T-M dual read | `dbg-write` `READ_INSTRUCTION` read_mode 10 (keep latch bits) on the running image, then `./dev.py health` loop rate | MCU still runs; loop rate change; recovery = `./dev.py reset` |

Firmware test ops (new ops in the `-D _AWTO_OSD_HWTEST` image, `docs/osd-hw-tests.md`; flash = our own build, `--no-backup`):

| test | does | proves |
|---|---|---|
| T-H burst | `hb_burst` of 54 / 486 B LFSR pattern from XRAM to a glyph range, read back (op 2), fw us per byte; repeat at `SCA_INF_PERIOD` 2 / g / g - 4 | burst correctness, real byte time, how low the gap can go |
| T-I hw turn | raw + 180 download of 1-bit and 2-bit glyphs (`FRAME_CTRL_17` = 0x03, `FRAME_CTRL_0B` f_dl_swap 01 + hw_rotate_en), poll buf_empty, read back vs `AwtoOsdTurn` output | plane order and word order of the hardware turn; wait time instead of 2 ms |
| T-J masked write | set / clear single pixels in a known glyph via bit_block, read back | per-bit writes on glyph words |
| T-K access timing | T2 direct loop at `SCA_INF_PERIOD` 1 / 2 / 3, `CYCLE_GATING` default vs lower | whether register accesses get cheaper |
| T-L MCU x2 | image with `_MCU_SPEED_UP_SUPPORT` on: `./dev.py health` (heartbeat vs Timer2 vs host ms), DDC/CI round trips, `scope2` fps from the sync log | 175 MHz stable on the unit; real gain vs the sim's 1.3-1.6x |

## Not available (checked)

- Per-window scale or palette, per-row glyph scaling, hardware blink, per-window alpha level, SRAM block copy / fill, glyph repeat, MDU [spec / sdk as above].
