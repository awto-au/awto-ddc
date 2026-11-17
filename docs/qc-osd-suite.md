# Realtek QC suites: OSD frames and pattern generator (awto-ddc#227, #228)

Status 2026-11-17. Reference is the monitor (unit 3), not the sim.

## What exists

- Source: Realtek QC code, upstream mirror `Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_QC_*.c` (single import 2024-02-20; no earlier history). Parked copy: `fw/sdk-parked/Kernel/Scaler/RL6449_Series_Scaler/Code/`.
- Designed for Realtek's QA bench: `NoneFactoryQCFlow` per input port, results on 7-segment GPIOs + `DebugMessageQC`, pass/fail by D-domain CRC vs fixed tables. Visuals are not part of the test.
- No Realtek app starts or steps the QC (RTDCustomerTool plugins: ISP, DebugMessage, NewEDID, GPIO, DPCD, CTS, NewCtrlReg, Measure).

## Tools (this repo)

| tool | does |
|---|---|
| `scripts/qc_osd_patterns.py` | renders the QC font tables (1/2/4 bpp) from the source |
| `scripts/gen_qc_osd.py`, `fw/test/qc_osd.c` | our port of the QC test pattern: test cmd 0xB0 on / 0xB1 off |
| `fw/test/osd_demo.c` | window demo (#215, gradients, grid, shadow, 3D, saturated): test cmds 0xA0..0xA5 |
| `fw/test/dpg_test.c` | D-domain pattern generator (P7 F0..FF): test cmds 0xB2 on / 0xB3 off |
| `fw/test/osd_reset.c` | clears blend / mask / pop-on / scale-up state before a test screen |
| `scripts/osd_model.py` | OSD model: SRAM + registers -> image |
| `scripts/qc_frames_shot.py` | boots a QC harness image in fw_sim, renders every QC frame (`--labels` writes a description on each window, `--bg bars` shows blending) |
| `scripts/qc_suite_unit.py` | steps the 24 QC frames on a unit, one every `--hold-s` |
| `scripts/osd_font_scan.py` | reads the unit's font SRAM through the harness dump command |
| `scripts/osd_test.py` | named test cmds (`--cmd qc-osd`, `dpg`, `osd-demo-*`) |

## QC frame harness (not in main)

- Scratch worktree `tmp/scratch/qcsim`: Realtek's `QC_OSD.c` compiled in with prelude macros, CRC / test-proc stubs, bank-12 pins on tables and loaders, and `AwtoQcRun(n)` on test cmd 0xB2 + n (n = 0 pattern, n = k replays frames 0..k-1, leaves frame k-1). Also `AwtoQcDump` (0xCA).
- The harness kicks the watchdog between frames (a frame run exceeds 586 ms; without it the unit reboots into our console).
- Flashing needs `fw_gates.py <stem> --tree tmp/scratch/qcsim` first (the link check needs that tree's layout).

## Findings

- **Pink "5" cells = Realtek's own clear data.** `_CLEAR_DATA` = `4C 06 17` (1-bit, glyph 6, fg 1, bg 7 = pink) in all five series files. Their blank is `4C 00 10`. The harness uses the blank. Unit 3 photo confirmed the pink. Why Realtek chose it: unknown.
- **2/4 bpp glyph storage = bit planes** (MSB plane first, each stored like a 1 bpp glyph); 2-bit glyph at `font_base + 18 * (off2 + id)`, 4-bit at `font_base + 36 * (off4 + id)`. Unit 3 photo of our port (0xB0): clean Brook and Luffy skulls.
- **4-bit char command:** B0 = `0xC0 | background colour`, B2 = palette-set flags; background pixels (value 0) are drawn in that colour, index 0 included. Photo: Luffy sit on a solid box, Brook transparent.
- **P87 pattern-generator "sub" set does not exist on the 2795T:** wrote 0x5A to 0x07F3 and 0x87F3, read back 5A / 00. Names come from the RTD2797UPM regdb; `gen_regnames.py` merges sibling regdbs.
- **Harness icons are garbage on the unit** (noise in the 2-bit and 4-bit areas) while our own loader (0xB0) shows them clean: Realtek's `ScalerOsdHardwareVLC` path in the harness image loads them wrong. Cause not found. Frame renders from the sim are therefore not comparable for icon areas. SRAM scan (M1 vs M2) gave inconsistent results; not trusted.
- Windows, gradients and grid lines on unit 3 match the sim (photo of frames 2 / 3).
- Photos are washed out by room light; colour is judged by shape, not tint.

## Model coverage (register-doc readings, unverified on the unit unless stated)

- Done: windows (flat, gradient + level / step extension, saturated / reversed, grid, shadow, 3D, border, chessboard, rounded, gray level), window 6 / 7 functions, special colour mask, highlight (4-1..4-3), specific colour blending, font B / two maps, blank cells, 24x36 mode (layout guessed), rotation (approximation), double size, scale-up (ratio = 64 / factor), pop-on, vertical boundary (units guessed), border priority.
- Not modelled: roll-up animation, exact rotation anchor, hardware-verified blend direction (alpha level = video share).

## Run

- Sim: `scripts/qc_frames_shot.py <harness bin> <map> --labels [--bg bars]`.
- Unit 3: flash the harness image, `scripts/qc_suite_unit.py 11 --serial AWT26110003 --map <map> --hold-s 8`; then reflash the standard image.
- Test unit only (unit 3); units 1 and 2 are working screens.

## Open

- Why Realtek's loader path fails in the harness (bank / DMA / my pins?).
- What `_CLEAR_DATA` pink is for (needs the Realtek QA bench or someone who ran it).
- Roll-up, rotation anchor, gradient and mask semantics, vertical-boundary units: need unit photos.
- Other QC suites (Color DDomain I-V, IMDomain, BIST, DSPC, OD_FRC): #228.
