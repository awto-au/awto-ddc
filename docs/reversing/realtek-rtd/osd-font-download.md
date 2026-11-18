# Dahua firmware OSD font blobs (RE notes)

Date: 2026-11-04T14:30+10:00 (reviewed 2026-11-18). Static / offline only; nothing written to hardware.
Tags: `[spec]` = Realtek regdb (`re/regdb/RTD2795T-CG.tsv.gz`); `[oss]` = understood from open projects, re-derived in own words (KerJoe/ORTD2662, floppes/RTD266xFlash), no code copied; `[fw-measured]` = decoded from our Dahua firmware dump `~/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin`; `[guess]`.
Hardware reference moved to the OSD manual: download sequence, VLC code table, stream packing: [docs/osd/glyph-load.md](../../osd/glyph-load.md); tile geometry, row / char words: [docs/osd/tiles-fonts.md](../../osd/tiles-fonts.md).
The row / char word bit layout of the RTD2662 open projects (visible / blink / fontSize / width in B0) is a different chip's layout and does not match the RTD2795T words: the manual states ours.

## Headline
- [fw-measured] 4 VLC glyph blobs sit back-to-back in flash at `0x228C6`, `0x22BED`, `0x231AB`, `0x23B41` (bank 2, offset 0x28C6...). Format = 8-byte code map + 2-byte BE length + VLC stream. No offset table.
- The VLC value map is NOT the hardware reset map (all 0). It is the first 8 bytes of each blob, loaded into the decoder (0x3A0F-0x3A16) before the stream.
- Why the firmware scan found no `MOV DPTR,#0x3A0F`: [oss] map is loaded as data-port bytes (OSD word 5-7 in the ORTD2662 model), not as a scaler-register write [guess for 2795: word N byte b = `0x3A00 + 3N + b`, consistent with 0x3A0C-0E = word 4 = fs/font base].


## VLC maps of the four blobs
- Measured maps [fw-measured, header bytes of each blob]:
  - `0x228C6`: `0f 1c 82 e4 73 a6 95 db`
  - `0x22BED`: `0f 81 3e c7 69 b2 4d a5`
  - `0x231AB`: `0f 18 c3 7e 62 49 db a5`
  - `0x23B41`: `0f c1 38 e7 46 25 a9 db`
  - Every map is a permutation of nibbles 0-F; symbol `0` (shortest code) is nibble `0` = blank, `f` second = solid.
- There is no single "default" map to apply to all blobs. Decode with each blob's own header.


## 4. Blob header + flash layout [oss: floppes FontCoder; fw-measured]
```
+0   8 bytes  VLC map (16 nibbles, vlc_0 = high nibble of byte 0)
+8   2 bytes  stream length N, big-endian
+10  N bytes  VLC stream, ends with END
```
- floppes (RTD266x boot logo): the whole logo = ONE blob; glyph cells row-major, glyph k = k-th 27 bytes of decoded data. No offset/index table; the blob sits at a fixed firmware offset (per-firmware constant `LogoOffset`, `MaxLogoLength` = room before next data).
- Ours [fw-measured]: 4 blobs contiguous: `0x228C6` (+0x327) -> `0x22BED` (+0x5BE) -> `0x231AB` (+0x996) -> `0x23B41` (+0x2695) -> ends `0x261D6`. `0x228C6` preceded by `FF` fill. Next data after `0x261D6` is not a blob header (not a nibble permutation).
- No offset table found for them: the earlier "offset-table font" at `0x328C6` was gamma LUT (refuted in boot-logo.md). Blob index, if any, lives in code/descriptor, not in the blob.
- Code refs [fw-measured]: `90 28 C6` (MOV DPTR,#0x28C6) at flash `0x15E6D` (bank1), `0x4B02B`, `0x4B09F`, `0x4CB10`, `0x4F185`, `0x4FD43` (bank4). Blobs B/C/D have no absolute `MOV DPTR` hit: addressed through a computed pointer/table [?] (matches boot-logo.md "runtime-computed banked pointer").
- Contents [fw-measured 2026-11-04T16:00+10:00, clean tile atlas `~/vendors/realtek/analysis/logo/glyphdec/atlas_<X>_clean.png`; `scripts/glyph_decode.py`]:
  - `0x228C6` 53 glyphs: menu icons — render as **crisp recognisable glyphs**: "F", home, power ⏻, diamond, "E", gamepad, "ECO", PIP/frame, 2nd power. Confirms tile format exactly.
  - `0x231AB` 189 glyphs: "FPS"/"RTS" text labels + crosshair/aim-reticle + circle glyphs (game-mode OSD). Clean.
  - `0x23B41` 586 glyphs: the **Dahua logo** set. Every individual tile is a clean stroke/curve/letter fragment; swoosh + "TECHNOLOGY" wordmark clearly present when read in reference order. It is a de-dup atlas (566/586 unique, no blank/solid tile) — NOT a raster, so no rectangular reshape de-shears it (see §4a).
  - `0x22BED` 98 glyphs: not catalogued in detail (same clean format).

### 4a. The blob is a de-dup atlas; placement needs a runtime char-map [fw-measured, decisive]
- Rendering blob D as a gap-less W×H grid shears diagonally at EVERY width 48-72 (per-row best-shift non-constant, mismatch 0.35-0.42). A true raster would de-shear at exactly one width; it never does ⇒ tiles are NOT in image-raster order.
- Objective edge-continuity picks cols=56 at every skip (a self-similarity artefact, not the grid); column-major is worse. Within-tile order (B2,B1,B0 MSB, word w→rows 2w,2w+1) is confirmed optimal; the shear is in tile ORDER, not cell packing.
- Matches the SDK model (`sdk-rl64xx-reference.md` §2-3): the font tool emits UNIQUE tiles in reference-scan order; the per-cell glyph-index grid (the placement) lives in a separate char-map array, applied at run time by `osd_compose_glyph_grid_map bank1:0xb0f4`. Blobs A/C confirm this directly — their "FPS"/"RTS"/icon runs are locally continuous because those cells are referenced consecutively.
- Char-map NOT found as a plain flash index array: no run of u16 in [0,586) of map length; the SDK 0x4C/0x4E char-word triples (with 0xFE/0xFF/0xFC/0xFD controls) do not appear as a dense run in our dump → our firmware uses a different (likely more compact / descriptor-driven) encoding. Descriptor region after the splash header (`0x13877+`) holds a `ff 12 0e 17 13 NN`-type record list (glyph-set descriptors, incrementing index), not the per-cell logo map.
- Consequence for re-encoding our own logo: we must also author the char-map/grid, not just the glyph atlas. Its exact source is still open (runtime-built by `bank1:0xb0f4`; pin via a live capture of the OSD data-port 0x92 word stream during splash, or finish the Ghidra trace of `0xb0f4`).


## 7. Splash path summary (what the firmware does, spec-aligned)
1. Read blob header from flash (SPI engine `bank6:0x4445`), load 8 map bytes into vlc_0..vlc_f.
2. `0x3A17 |= 1`; stream N bytes from flash to `0x92` with destination = font SRAM word (font_base + glyph base).
3. `0x3A17 &= 0xFC`.
4. Fill row/char words (`bank1:0xb0f4` grid composer), set `0x3A0C-0E`, windows, `0x3A0A`, `0x3A02[0]`.
- Re-encode our logo = build one blob per glyph set: encode 27 bytes/glyph, choose map by nibble frequency, write header+stream+END, length = stream bytes. Replace in place only if it fits before the next blob (blobs are contiguous: no slack; same-size or shorter, pad the stream tail is not valid since END terminates, remaining bytes unused).


## Open
- [?] Which blob and grid dims form the Dahua power-on splash (blob D `0x23B41` is the likely logo; the char map decides ordering).
- [?] How the Dahua firmware passes the 8 map bytes (data-port words 5-7 vs registers): decide with a live capture of `0x90-0x92` writes, or static search for data-port writes near `bank6:0x4272`.
- [guess] hw rotation (`0x3A0B`) changes decoded glyph orientation; the firmware writes `0x3A0B` via `osd_fontdl_orient_enable bank1:0x97a5`, so blob data may be stored pre-rotated: check cell orientation before concluding the grid is wrong.
- Fix needed in `scripts/glyph_decode.py`: use each blob's own 8-byte header map and a 10-byte header skip.

## Realtek QC icons rendered (2026-11-16, awto-ddc#227)
- `img/qc-osd-patterns.png` (from `scripts/qc_osd_patterns.py`): the QC test's glyph data decoded: `tQCFONT_GLOBAL` (blank + digits 0..9, 1 bpp), `tQCFONT_2BITBROOK` (48 glyphs, 8 x 6 icon), `tQCFONT_4BITLUFFY` (77 glyphs, 11 x 7 icon, palette indexes 0..15 of `tPALETTE_QC` [guess]). 2 / 4 bpp glyphs are decoded as bit planes; the 2-bit plane order on hardware is LOW bit first ([hw] T9, [docs/osd/tiles-fonts.md](../../osd/tiles-fonts.md)); the 4-bit order is [?] (OT-1).
- `img/osd-lines-scope-model.png` (from `scripts/osd_lines_view.py`): the OSD line renderer's 384 x 216 scope trace as the OSD model paints it from the uploaded tiles; model output, not a hardware capture.
