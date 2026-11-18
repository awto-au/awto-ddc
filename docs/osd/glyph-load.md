# OSD SRAM access: data port, direct stores, burst, VLC download

## Ports (page 0) [spec]
| reg | name | fields |
|---|---|---|
| `0x90` | OSD_ADR_PORT_MSB | [6:0] word address MSB |
| `0x91` | OSD_ADR_PORT_LSB | [7:0] word address LSB |
| `0x92` | OSD_DATA_PORT | data byte |
| `0x93` | OSD_MISC_PORT | [7] db_enable (global double buffer), [5] sram_read_select (0 = M1, 1 = M2) |
| `0x94` | OSD_WRITE_OPTION | [7:5] bytesel (001 B0, 010 B1, 100 B2, 011 / 101 / 110 pairs, 111 all), [3:2] sram_sel (00 window registers, 10 font select + font map SRAM) |
- A word = 3 bytes B0 B1 B2 (regdb: LSB / MSB / HSB). Write: `0x94 = bytesel << 5 | sram_sel << 2`, `0x90 / 0x91` = word address, then data-port writes; address auto-increments per data access [hw: write + read-back of window word 0x120 exact, +1 per single-plane read, 2026-11-04].
- Font and map SRAM are two memories M1 / M2; writes (`sram_sel` 10) go to both at once, reads pick one with `0x93[5]` [spec]; both hold identical words [hw] 2026-11-16.
- Single-byte writes (`bytesel` B1 only) change one byte of a word: a glyph-id change costs 1 byte instead of 3 [spec]; [?] timing gain OT-24.

## Write paths (unit 3, 2026-11-18, `docs/osd-hw-tests.md` T1 / T2 / T5, 4K60 input)
| path | per byte | result |
|---|---|---|
| `ScalerOsdDataPort` (banked call per byte) | 4.12 us | 0 bad bytes in 30 KB, M1 and M2 |
| direct `AWTO_XFR(AWTO_R_OSD_DATA_PORT)` store loop, EA on / off | 2.60 / 2.39 us | 0 bad bytes |
| direct unrolled triples (map shape), EA on / off | 2.75 / 2.46 us (map range 3.25) | 0 bad bytes |
| direct, OSD shown and scaled (Scope 2), EA on / off | 2.69 / 2.36 us | 0 bad bytes |
| direct unrolled, shown, EA off | 1.95 us | 0 bad bytes |
- Direct stores are the default write path; no minimum gap needed at the fastest MCU store rate [hw]. The earlier rule "every byte via `ScalerOsdDataPort`" was lifted by Dan, 2026-11-18, and is gone: direct stores are fine, perf-affecting rules are asked first.
- Writes while the OSD scans can disturb the picture: T10, [timing.md](timing.md).

## Burst DMA XRAM -> data port
- `SCA_INF_CONTROL` reg_burdat_wr + addr_non_inc, target `SCA_INF_ADDR` = 0x92, source `SCA_INF_BWR_ADRH/M/L`, count `SCA_INF_BWR_COUNT_H/L`, source select XRAM, gap `SCA_INF_PERIOD` [spec]; our `hb_burst` (`fw/rtdfw/awto/reg/burst.c`) follows the SDK sequence; pop-up text uses it with 27-byte bursts [hw].
- Gap formula `g = 12109500 / dclk_khz - 2` (x2 with `db_width`): ~0.46 us per byte [sdk-hypothesis]; real byte time [?] T-H.
- Per-tile bursts gain little (setup ~38 us vs 27..54 data bytes); gain only from one burst per column of contiguous glyph slots [sdk-hypothesis].

## Write protection (masked writes)
- `0x3A33[0]` bit_block_en, `[2:1]` bit_block_byte_sel (B0 / B1 / B2), `0x3A34` per-bit protect mask: protected bits keep their value while the OSD is on [spec]. No scan interlock. Use: change single pixels in a glyph [?] T-J.

## VLC download (hardware decoder)
| step | register | meaning | evidence |
|---|---|---|---|
| 1 | `0x94` = `0xE8` | all bytes, font SRAM | [hw] |
| 2 | `0x3A0F..16` | 16 nibbles = the blob's 8-byte map (vlc_0..vlc_f) | [spec] [hw] decoded blobs of the Dahua firmware |
| 3 | `0x3A17[0]` | osd_compression_en: 4-bit symbols, code `1111_1111` ends the data | [spec] |
| 3b | `0x3A17[1]` | decode_nocom_data: 1 = decode non-compressed data (pass-through, used with rotation) | [spec] |
| 3c | `0x3A17[2]` | rotate_3byte (acceleration; compression + rotation on) | [spec] |
| 4 | `0x90/0x91` then `0x92` stream bytes | decoder writes 3 bytes (1 word) per 6 nibbles, address auto-increments | [spec] [hw] |
| 5 | `0x3A17 &= 0xFC` | clear after the download | [hw] Dahua firmware |
- Code table (first-bit-first): `0`, `100`, `1010`, `1011`, `1100`, `11010`, `11011`, `11100`, `111010`, `111011`, `111100`, `111101`, `1111100`, `1111101`, `1111110`, `11111110` -> vlc_0..vlc_f; END `11111111` [spec].
- Stream: bits LSB-first per byte; nibble pairs high-first; END then padding; blob = 8-byte map + 2-byte BE length + stream [hw: all 4 Dahua-firmware blobs decode to whole tiles, 53 / 98 / 189 / 586]. Encoder: sort nibbles by frequency, shortest code for the most frequent.
- Reset map is all 0: any glyph needs its map loaded.
- Our tools: `scripts/osd_vlc.py` (encode / decode), `scripts/glyph_decode.py`, `osd_tc_vlc_*` in firmware ([api.md](api.md)).
- Hardware turn while loading: [rotation.md](rotation.md).
- The Dahua firmware blob RE (addresses, contents) stays in `docs/reversing/realtek-rtd/osd-font-download.md`.

## SRAM extent
- 12288 words, both memories: marker written to `0x0000, 0x0800, 0x0FFF, 0x1000, 0x1FFF, 0x2000, 0x2FFF` reads back from M1 and M2; `0x3000` does not; `0x3FFF..0x7FFF` read changing junk [hw] unit 3, 2026-11-16 (`AwtoOsdSramProbe`, #226). Needs `0x3A02[0]` on at the time (see below).
- Display fetch across word 8192: [tiles-fonts.md](tiles-fonts.md).
