# RTD OSD font download + VLC glyph format (RTD2795T)

Date: 2026-11-04T14:30+10:00. Static/offline only; nothing written to hardware.
Tags: `[spec]` = Realtek regdb `~/vendors/realtek/analysis/regdb/RTD2795T-CG.tsv` (siblings 2775TM/2785TM/2776B/2797UPM/2537T/2525AR carry identical text for every field below); `[oss]` = understood from open projects, re-derived in own words, no code copied; `[fw-measured]` = decoded from our dump `~/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin`; `[guess]`.
OSS read: KerJoe/ORTD2662 (`osd/osd.c`, `osd.h`, `osd_registers.h`, `scripts/vlc_encode_decode.py`, `scripts/unifonthex2vlc.py`), floppes/RTD266xFlash (`FontCoder.cs`, `FirmwareModifier.cs`). KunYi/RTD266x: no font code. Kingdomwhisky SDK: not opened (not needed).
Builds on `osd.md` (ports, window words) and `boot-logo.md` (firmware RE). Supersedes the "value map = hardware reset = all zero" conclusion in boot-logo.md.

## Headline
- [fw-measured] 4 VLC glyph blobs sit back-to-back in flash at `0x228C6`, `0x22BED`, `0x231AB`, `0x23B41` (bank 2, offset 0x28C6...). Format = 8-byte code map + 2-byte BE length + VLC stream. No offset table.
- The VLC value map is NOT the hardware reset map. It is the first 8 bytes of each blob, loaded into the decoder (0x3A0F-0x3A16) before the stream.
- Why the firmware scan found no `MOV DPTR,#0x3A0F`: [oss] map is loaded as data-port bytes (OSD word 5-7 in the ORTD2662 model), not as a scaler-register write [guess for 2795: word N byte b = `0x3A00 + 3N + b`, consistent with 0x3A0C-0E = word 4 = fs/font base].

## 1. Register sequence of a hardware font download [spec unless noted]
| step | reg | field | meaning |
|---|---|---|---|
| 1 | `0x94` | bytesel=111, sram_sel=10 | all 3 bytes, font select + font map SRAM (`0xE8`); M1/M2 written together |
| 2 | `0x3A0F-0x3A16` | vlc_0..vlc_f | 4-bit value for each VLC code (below); reset 0x00 each |
| 3 | `0x3A17[0]` | osd_compression_en | 1 = decode 4 bit/symbol VLC, code `1111_1111` = end of data; "only for SRAM" |
| 3b | `0x3A17[1]` | decode_nocom_data | 0 = decode compressed data, 1 = decode non-compressed data (pass-through, used with rotation) |
| 3c | `0x3A17[2]` | rotate_3byte | write 3 decoded bytes to SRAM per access (accel); active only when compression + hw rotation both on |
| 4 | `0x3A0B[2]` | hw_rotate_en | font download rotation; requires compression enabled; not needed when auto-rotate+remap is used (desc says "1: Enable (Default)" but reset = 0x00) |
| 4b | `0x3A0B[7:6]` | f_dl_swap | 00 none, 01 180, 10 CCW, 11 CW |
| 4c | `0x3A0B[3]` | buf_rst | write 1 then 0 to reset rotation buffer |
| 4d | `0x3A0B[5:4]` | buf_empty (R, 1=not empty), buf_valid (R, 1=buffer still writing to SDRAM) | poll for download done when rotating |
| 5 | `0x90`/`0x91` | osd_addr_msb[6:0]/lsb | destination word address in font SRAM (15-bit word address) |
| 6 | `0x92` | data port | write stream bytes one at a time; decoder emits 3 bytes (1 word) per 6 nibbles into SRAM, address auto-increments [oss + osd.md measured +1/access] |
| 7 | `0x3A17[0]` -> 0 | | firmware clears with `&= 0xFC` (also clears decode_nocom_data) [fw] |
| 8 | `0x3A0C`, `0x3A0D`, `0x3A0E`, `0x3A17[5:3]` | fs_base[11:0], font_base[14:0] | where the hardware fetches text map / glyphs at display time |
| 9 | `0x3A0B[0]` | rotation | display-time: 1 if the stored font map data is rotated (latch 24 bit per 24 bit when 0) |
| 10 | `0x3A02[0]` | osd_en | enable; first write `0x94=0x00` before disabling |

- `0x3A0C` fs_base[7:0]; `0x3A0D` = fs_base[11:8]<<4 | font_base[3:0]; `0x3A0E` font_base[11:4]; `0x3A17[5:3]` font_base[14:12]. Units = 24-bit words.
- Other fields: `0x3A33[0]` bit_block_en (write-protect font SRAM while OSD on; keep 0 during download), `0x3A41[3]` rotate_flib (font map library rotation, auto-clears), `0x3A41[0]` auto_rotate_en, `0x3A41[5:4]` auto_rotate_dir, `0x3A41[2:1]` font A/B remap, `0x3A18[3]` fontx2_en (two-font mode: font B row/select via word 8/9, bases `0x3A19-0x3A1D`).
- Display-side scale: `0x3A0A[1]` db_width, `[0]` db_height (2x whole OSD); scale-up block `0x3AC0+` (osd_su_bd_cond 00 neighbourhood / 01 thin / 10 fat).

## 2. VLC symbol map [spec for codes, fw-measured for values]
Prefix code, 16 symbols + END. Codes are read first-bit-first.
| field (reg, nibble) | code | bits |
|---|---|---|
| vlc_0 `3A0F[7:4]` | `0` | 1 |
| vlc_1 `3A0F[3:0]` | `100` | 3 |
| vlc_2 `3A10[7:4]` | `1010` | 4 |
| vlc_3 `3A10[3:0]` | `1011` | 4 |
| vlc_4 `3A11[7:4]` | `1100` | 4 |
| vlc_5 `3A11[3:0]` | `11010` | 5 |
| vlc_6 `3A12[7:4]` | `11011` | 5 |
| vlc_7 `3A12[3:0]` | `11100` | 5 |
| vlc_8 `3A13[7:4]` | `111010` | 6 |
| vlc_9 `3A13[3:0]` | `111011` | 6 |
| vlc_a `3A14[7:4]` | `111100` | 6 |
| vlc_b `3A14[3:0]` | `111101` | 6 |
| vlc_c `3A15[7:4]` | `1111100` | 7 |
| vlc_d `3A15[3:0]` | `1111101` | 7 |
| vlc_e `3A16[7:4]` | `1111110` | 7 |
| vlc_f `3A16[3:0]` | `11111110` | 8 |
| END | `11111111` | 8 |
- Each symbol = one 4-bit value; 8 map bytes = 16 nibbles, high nibble = lower-numbered code.
- Reset/default value of every field = `0x00` (all 8 bytes `00`) [spec, all 7 chips]. Degenerate; any real glyph needs the map loaded.
- Encoder convention [oss, both projects agree]: sort nibble values by frequency, most frequent gets the shortest code. Hence the map is data-dependent per blob.
- Measured maps [fw-measured, header bytes of each blob]:
  - `0x228C6`: `0f 1c 82 e4 73 a6 95 db`
  - `0x22BED`: `0f 81 3e c7 69 b2 4d a5`
  - `0x231AB`: `0f 18 c3 7e 62 49 db a5`
  - `0x23B41`: `0f c1 38 e7 46 25 a9 db`
  - Every map is a permutation of nibbles 0-F; symbol `0` (shortest code) is nibble `0` = blank, `f` second = solid.
- There is no single "default" map to apply to all blobs. Decode with each blob's own header.

## 3. Stream bit/nibble packing [oss, verified [fw-measured] on all 4 blobs]
- Bits consumed LSB-first within each byte; bytes in stored order.
- Decoded nibbles pair up high-nibble-first into bytes: nibbles (n0,n1) -> byte `n0<<4|n1`.
- Stream ends with END `11111111`; remaining bits of the last byte are padding (0).
- Length field counts stream bytes after the 10-byte header, including the END byte.
- Verified [fw-measured]: for all 4 blobs END lands exactly in the last byte named by the length; decoded byte count is an exact multiple of 27 (= 9 words = one 12x18 1bpp glyph): 53, 98, 189, 586 glyphs.

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

## 5. Glyph cell geometry
- 1 bpp cell = 12 x 18 px = 216 bits = 9 words x 24 bit = 27 bytes [oss + fw-measured].
- Pixel order within a glyph: row-major, 12 px per row, 2 rows per word (24 bits). Within a word, the 3 stored bytes (B0,B1,B2) are read B2 first (px 0-7), then B1 (px 8-15), then B0 (px 16-23). Within a byte MSB = leftmost. Pixel 1 = foreground [oss floppes: black=1; ORTD2662 same]. Decoded byte order in stream: B0,B1,B2 (each triplet).
- Equivalent nibble picture [oss ORTD2662 comment]: row 2i = B2.hi, B2.lo, B1.hi; row 2i+1 = B1.lo, B0.hi, B0.lo.
- Bits per pixel [spec + oss]: 1 bpp = fg/bg index (4 bit each) into the 64-entry LUT; 2 bpp and 4 bpp fonts exist, selected per character (char word fontSize: 0 = 1 bit, 1 = 4 bit, 3 = 2 bit [oss]); 2/4 bpp char index offsets at `0x3A21[1:0]`/`0x3A22` (2-bit offset[8:0]) and `0x3A21[0]`/`0x3A23` (4-bit offset[8:0]); `0x3A07[2]` f4b_color_sel (4-bit font background from byte2[1:0] or byte0[3:0]).
- 2 bpp / 4 bpp glyph size in words: 18 / 36 [derived from 216 px x bpp / 24; guess, not measured]. Bit packing inside those words unknown.
- 24x36 mode: `0x3A43[6]` font_24x36_en [spec]; 24x36 1 bpp = 864 bits = 36 words [derived]. In that mode `0x3A21`/`0x3A23` offset bit8/bit7 must be 0 [spec].
- 2x scale: `0x3A0A[1:0]` doubles all OSD (windows + chars) [spec]; firmware boot runs 2x.
- Glyph address = `font_base + words_per_glyph * index` [oss, 9 words at 1 bpp]. Firmware boot value `font_base=0x3F1`, `fs_base=0x019` [osd.md measured].

## 6. Text-map (font select SRAM) layout [oss ORTD2662; not in regdb]
Region 0 = row commands at word 0.., then character words from `fs_base` (rows' chars concatenated, `length` chars per row), glyph bitmaps from `font_base`. A row-command byte0 bit7 = 0 ends the list.
- Row command word (3 bytes) [oss]:
  - B0: bit7 notStop (0 = end of rows), bit6 vbi function, bits4:2 char effect (border/shadow), bit1 width2x, bit0 height2x.
  - B1: bits7:3 height (5 bit), bits2:0 width (3 bit). Value encoding is not pinned: ORTD2662 UI sets height=16 and width=8 (truncated to 0 in a 3-bit field), so width 0 works for 8-12 px cells [guess]. Our `osd.md` "(18,12,N)" does not fit 3 bits.
  - B2: number of characters in this row.
- Character word, visible glyph [oss]:
  - B0: bit7 isVisible=1, bit6 blink, bits5:4 fontSize (0=1bpp, 1=4bpp, 3=2bpp), bits3:0 char width (px, 4 bit).
  - B1: glyph index (relative to font_base; text demo stores ASCII-0x20).
  - B2: fg colour [7:4], bg colour [3:0] (4-bit palette indices; bg 0 = transparent).
- Blank (non-glyph) word [oss]: B0 bit7 = 0 (bit6 blink), B1 = blank width, B2 = colour.
- Correction to `osd.md`: char word is flags/width | glyph index | colours (B0|B1|B2), not `(bg<<4)|fg | glyph | 0`.
- Frame-control words in the same SRAM numbering: word 4 = fs_base/font_base (0x3A0C-0E), words 5-7 = VLC map + compression enable (0x3A0F-0x3A17) [oss ORTD2662 map; matches 2795 register addresses byte-for-byte].
- Window words: `0x100 + 4n` (osd.md).

## 7. Splash path summary (what the firmware does, spec-aligned)
1. Read blob header from flash (SPI engine `bank6:0x4445`), load 8 map bytes into vlc_0..vlc_f.
2. `0x3A17 |= 1`; stream N bytes from flash to `0x92` with destination = font SRAM word (font_base + glyph base).
3. `0x3A17 &= 0xFC`.
4. Fill row/char words (`bank1:0xb0f4` grid composer), set `0x3A0C-0E`, windows, `0x3A0A`, `0x3A02[0]`.
- Re-encode our logo = build one blob per glyph set: encode 27 bytes/glyph, choose map by nibble frequency, write header+stream+END, length = stream bytes. Replace in place only if it fits before the next blob (blobs are contiguous: no slack; same-size or shorter, pad the stream tail is not valid since END terminates, remaining bytes unused).

## 8. Open / unknown
- [?] Which blob and which grid dims form the power-on splash (blob D `0x23B41` is the likely logo; map word contents decide ordering).
- [?] How the firmware passes the 8 map bytes (data port words 5-7 vs registers): decide with a live capture of `0x90-0x92` writes, or static search for data-port writes near `bank6:0x4272`.
- [?] 2 bpp / 4 bpp bit packing; row-command width encoding; first ~100 glyphs of blob D (different cell format?).
- [guess] hw rotation (`0x3A0B`) changes decoded glyph orientation; the firmware writes `0x3A0B` via `osd_fontdl_orient_enable bank1:0x97a5`, so the blob data may be stored pre-rotated. Check cell orientation before concluding the grid is wrong.
- Fix needed in `scripts/glyph_decode.py`: use each blob's own 8-byte header map and a 10-byte header skip (earlier run used zero/identity/rank maps and started at the header, giving noise).
- Scratch (not committed): `awto-ddc/tmp/sigscan.py` (header signature scan: 16 nibbles all distinct + plausible BE length), `vlcdec.py` (decoder + sheet renderer).
