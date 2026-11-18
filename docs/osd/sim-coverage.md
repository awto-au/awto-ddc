# OSD simulator coverage

Typed table: [sim-coverage.tsv](sim-coverage.tsv) (feature | registers | modelled | evidence | test | status | settle_test | demo | note). `tests/test_osd_model_robust.py` checks it (tests exist, demos exist, regdb names exist, every `spec-model` row names the test that settles it).

- Status: `modelled` (hw / databook / sdk behaviour), `spec-model` (most literal reading, behind `osd_model.Opt` where it changes pixels, tagged in captions), `unmodelled`, `not-visible`.
- `settle_test`: `OT-n` = [open-items.md](open-items.md); `C-*` = `scripts/osd_conform.py` case (host-only, unit 3, not run by agents): `--sim` render, `--hw` write over ISP, `--conform CASE PHOTO` diff of a capture against the model.
- Demos / register-image builder: `scripts/osd_demo.py` (`Img`, `DEMOS`, `render_png`).

## Opt switches (defaults keep every measured result and the saver frames unchanged)

| switch | default | reading |
|---|---|---|
| `osd_offsets` | off | `3A2C/2F` added to the delay (delay units), `3A32` to windows (px), `3A1E[7,3]` +1 px when doubled |
| `area_clip` | off | first OSD clipped to `3A38..3A` width x length (px) |
| `row_total` | off | map A / B stop after `3A3F` / `3A40` rows |
| `su_region` | off | scale-up source = region `3AC4..CB` (panel px) instead of the OSD bounding box |
| `win_rotate` | off | windows with `ADR9[0]` turn with the font block under auto rotation |
| `plane4_lsb` | off | 4-bit plane order MSB first (QC icons); on = LSB first like 2-bit (OT-1) |
| `round_circle` | on | all-zero round tables: quarter circle of the size |
| `pg_toggle` | `delta` | pattern generator toggle: init / init + delta (else init / inverse) |

## Model fixes (found while building the table)

- `sha` / `bor` window colour: bit 4 of the index is `ADR0` bit 7 / 6, bit 5 is `ADR3` bit 7 / 6 (was bit 4 read as bit 5; wrong for index >= 16).
- Rounded-corner size codes 8 / 16 / 32 px (was 4 / 8 / 16); tables `3A60..8B` read; the QC ramp (line k = k) gives a chamfer.
- Chessboard: colours at `ADR5` of windows 8 / 9 and `ADR4` of 4_x / 5_x (was `ADR5` for all: 4_x / 5_x never drew); `ADR4` of 4_x / 5_x is no saturated colour.
- Gradient bits only on windows 0, 5..9 (reserved elsewhere).
- Scale-up: `3AC0[7]` = on (SDK `ScalerOsdScaleUpOnOff`); regdb text "0: enable" is inverted; `frame_geometry.su_on` had the wrong sign.
- Grid pitch: um / (panel pitch `3A35..37` U(9.2)) instead of a fixed 993.
- Highlight windows 4_4..4_8 (`3A4D..56`) added; font A / B delay select `3A18[2:1]`, window `osd_delay_sel` honoured (font B was always on delay 2).
- Specific colour blend: `3A08[4]` = 0 matches the index bits [3:0] only.
- `blank_color_en` (`3A33[5]`), data port read-back (2 passes, stale first, junk with circuit / scale-up / overlay on), pattern generator, font masks `3A45..4C`.
- Render speed: glyph bitmaps memoised per render, no `kron` at 1x, chessboard vectorised, rows / cells off panel skipped: busy 4K image 2.1 s -> 1.2 s (dev box).

## Not modelled

- Engine download turn (`3A0B`), hardware remap / lib rotation (`3A41[3:1]`, `3A42`), scale-up edge modes / phase, zero-width windows, `3A57..5A` enable mirrors, `3A18[4]`, `3A07[2]` (regdb contradicts SDK + photo), video highlight window `0x60/0x61`, random pattern mode, SRAM size limit.
