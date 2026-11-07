# EDID rewrite: JXC 28in 4K, "awto" identity

Status: flashed to units 1-3 (2026-11-04, table below). `make_edid.py` now emits a 594 MHz VIC 97 DTD1 (ab8c4c9, not flashed); decided to go back to the vendor DTD1 3840x2160@59.982, 533.12 MHz and drop VIC 97 (#26, 2026-11-07).

## Files
- Builder: `scripts/make_edid.py` (stdlib; runs `edid-decode -c` on its output)
- EDIDs: `~/vendors/realtek/analysis/edid/awto-dp.bin`, `awto-hdmi.bin` (256 B each)
- Sectors: `.../edid/orig_sector_13000.bin` (from `dumps/jxc-4k-flash-bus20.bin`), `patched_sector_13000.bin`, `sector_13000.diff.txt` (all 372 changed offsets)
- Writer: `scripts/rtd_flash_sector.py` (dry-run default; `--write` required to modify)

## Where the EDIDs live and how the firmware loads them
- Flash `0x138D8`, `0x139D8`, `0x13AD8`, 256 B each, inside 4 KiB sector `0x13000-0x13FFF` (bank 1 offset `0x38D8/39D8/3AD8`) [measured: dump].
- Loader: bank1 `FUN_CODE_d2a3` (`~/vendors/realtek/analysis/jxc-4k/bank1/disassembly.asm`, ~line 16251) [fw]:
  - input index R7 = 4 -> flash `0x38D8` -> XDATA `0xE280`; R7 = 5 -> `0x39D8` -> `0xE480`; R7 = 6 -> `0x3AD8` -> `0xE680`
  - memset 256 B (`0x181a`), then 256 B memcpy code->xdata (`0x11b3`). No checksum or compare in the path.
- Slot 0 holds the DP EDID (1.4, DP interface bit); slots 1 and 2 held byte-identical HDMI EDIDs (1.3, HDMI VSDB). Slot-to-physical-connector mapping beyond "slot 0 = DP" is inferred from content, not probed [?].

## Per-port decision: DIFFERENT EDIDs (DP vs HDMI), the two HDMI slots identical
| | DP slot (0x138D8) | HDMI slots (0x139D8, 0x13AD8) |
|---|---|---|
| EDID version | 1.4 (DP spec requires >= 1.4) | 1.3 |
| Video input byte | `0xB5`: digital, 10 bpc, DisplayPort | `0x81`: digital, DFP 1.x |
| Feature byte | `0x3F` (sRGB-default SET, preferred, continuous freq, RGB+YCC444/422) | `0x27` (sRGB-default SET, preferred, GTF) |
| Range limits type | `0x01` range-limits-only (GTF deprecated in 1.4) | `0x00` default GTF |
| CTA ext | no VSDBs | + HDMI VSDB, HF-VSDB, AMD VSDB |
- HDMI copy is 1.3 because edid-decode 1.32 FAILS an HDMI VSDB inside an EDID 1.4 base ("HDMI Specification requires EDID 1.3"). This is why the original HDMI copies were 1.3.
- DP copy carries no HDMI/HF VSDB (meaningless on DP); everything else (identity, DTD, VICs, audio, VCDB) is shared.
- Both HDMI slots share physical address 1.0.0.0 as before; a source-side CEC address is not meaningful on this panel.

## Identity
- PnP vendor `AWT`: `((A-64)<<10)|((W-64)<<5)|(T-64)` = `0x06F4`, bytes `06 F4`. Not a registered PnP ID (3-letter limit); edid-decode did not warn.
- Product code `0x0001`; 32-bit serial field 0 (edid-decode warns if both it and the text serial are set).
- 0xFC name `awto-mon`; 0xFF serial text `AWT26110001` (newline then space padding, no stray bytes).
- Made week 44 of 2026 (`0x2C`, `0x24`).

## Annotated layout (base block, same for both ports except bytes 0x12-0x14, 0x18, 0x6E-0x71 region)
| Offset | Bytes | Meaning |
|---|---|---|
| 0x00 | `00 ff*6 00` | header |
| 0x08 | `06 f4` | vendor AWT |
| 0x0A | `01 00` | product 1 |
| 0x0C | `00 00 00 00` | serial32 = 0 |
| 0x10 | `2c 24` | week 44, year 2026 |
| 0x12 | `01 04` / `01 03` | EDID 1.4 (DP) / 1.3 (HDMI) |
| 0x14 | `b5` / `81` | video input (see table) |
| 0x15 | `3e 23` | 62 x 35 cm |
| 0x17 | `78` | gamma 2.20 |
| 0x18 | `3f` / `27` | features (sRGB-default bit 0x04 SET: chromaticities are exactly sRGB, so legitimate) |
| 0x19 | `ee 91 a3 54 4c 99 26 0f 50 54` | chromaticity: standard sRGB/BT.709 R 0.640,0.330 G 0.300,0.600 B 0.150,0.060 W 0.3127,0.3290 (D65) |
| 0x23 | `21 08 00` | est. timings 640x480, 800x600, 1024x768 |
| 0x26 | `d1c0 9500 9040 8180 8140 81c0 0101 0101` | std: 1080p, 1440x900, 1400x1050, 1280x1024, 1280x960, 1280x720, 2 unused (`0101`) |
| 0x36 | DTD1 | 3840x2160 533.12 MHz, 620x350 mm, htotal 4000 vtotal 2222, +H -V |
| 0x48 | `fc` | name `awto-mon` |
| 0x5A | `ff` | serial `AWT26110001` |
| 0x6C | `fd 00 18 3c 0f 87 3c {01\|00} 0a ...` | V 24-60 Hz, H 15-135 kHz, <= 600 MHz |
| 0x7E | `01`, checksum | 1 extension |

CTA-861 rev 3 extension:
- header flags `0xB1`: underscan, YCC444+422, 1 native DTD (base DTD1). **Basic-audio bit CLEARED** (was `0xF1`) — see audio note.
- VDB (18 VICs): 97 96 95 94 93 (4K 60/50/30/25/24), 16 31 32 33 34 (1080p), 4 19 60 61 62 (720p), 1 2 3 (SD). Deduped: removed second VIC 16 and VIC 76. No native flag (VIC 97 cannot carry one; native = base DTD1).
- **NO Audio / Speaker-Allocation block** — units have no speakers (Dan 2026-11-04). Removed the LPCM-2ch ADB and FL/FR SADB; header basic-audio bit cleared so the OS doesn't route sound to a dead endpoint.
- Colorimetry Data Block (ext tag `0x05`, bytes `E3 05 06 20`): xvYCC709 + sYCC601 + sRGB colorimetry bit (CTA-861-H). No BT.2020 (panel is ~99% sRGB IPS/PLS, not wide-gamut). sRGB bit set on edid-decode's recommendation (clears the "set the sRGB bit" interop warning).
- HDR Static Metadata Data Block (ext tag `0x06`, bytes `E3 06 01 01`): EOTF = Traditional-gamma SDR only; Static Metadata Type 1. **NO PQ/HLG** — ~300 cd/m2 SDR panel, not real HDR10; advertising HDR10 would be a false claim.
- VCDB `0xCA`: YCC + RGB quantization selectable; IT/CE always underscanned (matches header underscan bit).
- HDMI slots only:
  - HDMI VSDB: PA 1.0.0.0, DC_30bit + DC_Y444, legacy max TMDS 340 MHz (`0x44`).
  - HF-VSDB: v1, max TMDS char rate 600 MHz (`0x78`), SCDC present, scrambling for <= 340 Mcsc. 4K60 4:4:4 8 bpc (594 MHz) fits the field, but 594 MHz is not pursued (#26); 10-bit 4K60 is not claimed (needs 742 MHz). Dropped the old `DC_30bit_420` bit (no Y420 map declared).
  - AMD VSDB carried over unchanged (48-60 Hz FreeSync range) [fw: original bytes].
- DTD2 1920x1080 148.5 MHz: now exactly VIC 16 timing (88/44/148, 4/5/36). DTD3 2560x1440 241.7 MHz (CVT-RB) unchanged. Both image size 620x350 mm.

## Conformance (`edid-decode -c`, edid-decode 1.32.0)
Before (live HDMI copy; DP copy equivalent, `FAIL`):
- serial "Non-space after newline"; image size 527x296 vs 620x350 (DTD2, DTD3); missing VCDB; native progressive timings mix of several resolutions
- also (HDMI copy): duplicate VIC 16, HF-VSDB / legacy max TMDS 600 > 340 inconsistency; timings out of Monitor Range (24 Hz modes vs 48-60 Hz); base 1.4 vs 1.3 mismatch between ports

After (both `awto-dp.bin` and `awto-hdmi.bin`): `EDID conformity: PASS`, zero failures.
- Remaining warning (flashed EDID): "VIC 97 and the first DTD are not identical"; goes away when VIC 97 is dropped (#26).

## Colour + colorimetry revision (2026-11-04, flashed)
- Panel is **IPS/PLS**, not VA — Dan visual confirm 2026-11-04 (stable off-axis, corner/edge glow). Earlier VA assumption was wrong.
- Chromaticity: **standard sRGB / BT.709** primaries — the choice for a ~99%-sRGB IPS panel with no measured panel primaries: R 0.640,0.330 G 0.300,0.600 B 0.150,0.060 W 0.3127,0.3290 (D65). Bytes `ee91a3544c99260f5054` (edid-decode's exact sRGB reference encoding). Gamma 2.20 (`0x17=0x78`), 10bpc kept (DP). Replaces the prior Samsung-VA guess (`cd01a6554c9c260e5054`, R 0.651/0.332 G 0.300/0.610 B 0.148/0.055).
- sRGB-default feature bit RE-SET (`0x18`: `0x3f` DP / `0x27` HDMI): chromaticities now equal the sRGB standard, so "default colour space = sRGB" is legitimate. edid-decode does NOT emit the "sRGB signalled but chromaticities don't match" warning (it only fires when the bit is set but primaries differ).
- Kept CTA Colorimetry DB (sRGB + xvYCC709 + sYCC601; no BT.2020) and HDR Static Metadata DB (SDR EOTF only, no PQ/HLG). Audio still REMOVED (no speakers): no Audio/Speaker-Allocation block, basic-audio header bit cleared.
- Identity/size/timings unchanged: AWT / awto-mon / AWT26110001, 597x336 mm, native DTD 3840x2160@60 533.12 MHz, deduped mode list.
- Both variants `edid-decode -c` PASS (zero failures; only the benign "VIC 97 and first DTD not identical" warning).
- Re-flashed to card1-DP-4 (`/dev/i2c-20`) 2026-11-04T13:13+1100: live sector (prior VA EDID) vs new patched = 24 bytes differ (all in-slot: feature byte + changed chroma bytes + base checksum, x3 slots), `--expect-current` matched (0 differ). SR started `0x9c`, WP# released, unprotect -> SR `0x00`, erase + 16 pages programmed, VERIFY OK (0 mismatches), re-protected to `0x9c` with WP# re-asserted. Live `/sys/class/drm/card1-DP-4/edid` decodes with sRGB primaries (Red 0.6396/0.3300), sRGB-default bit set, Colorimetry+HDR blocks, no audio, conformity PASS.
- Backups: `~/vendors/realtek/analysis/edid/live_sector_13000_before_colourfix.bin` (pre-VA-write live sector) + timestamped copies in `tmp/flash-backups/` (pre-sRGB-write: `sector_013000_20261104-131310.bin`).

## Checksum finding: NO image or EDID-region checksum validated
- EDID load path (above) is a plain 256 B copy; nothing sums or compares it [fw]. Only the per-block EDID checksums matter to sources; both blocks of each new EDID sum to 0.
- Searched bank0/bank1 disassembly (common area `0x0000-0x28C6` shared by both): no MOVC loop that accumulates over code space (only switch-table/compare helpers), no `0x55AA`/`0xAA55` compare in code. Whole-image sum over banks 0-12 = `0xFCDC` (not zero) and the only `55 AA` / `AA 55` byte pairs in the dump are at `0xE076C`, `0xE0831`, `0x3978` (none near the boot path).
- The ISP `0x55AA` boot flag at `0x7000` is a write the vendor tool does, not a validated flash checksum.
- RTDTool's "Total CheckSum / File CRC" fields are host-side display values, not image content.
- Confidence: not exhaustive (banks 2-6 and the 0xE0000/0xF0000 blocks not traced); if the monitor misbehaves after the write, revert (below) and trace further. No checksum is included in the patch.

## The patch (current, after the 2026-11-04 colour revision)
- Sector `0x13000-0x13FFF` (4096 B). Only EDID bytes differ, all inside the 3 EDID slots `0x138D8/0x139D8/0x13AD8`. vs the factory-demo sector: 394 bytes differ, all in-slot; non-slot bytes byte-identical. vs the prior VA-colour flash: 24 bytes differ (feature byte + changed chroma + base checksum, x3 slots).
- sha256 orig (factory demo) sector `70cb3052910dc2ae388c6829df3cfd99a51ffab2af4574d7848b09a3667eee52`
- sha256 patched sector (sRGB/IPS revision) `feeff814de5ea113d7fc6ba97963bef3bb32653dc064f2e114e09149013c383d`
- Flash chip: Macronix `C2 20 14` (1 MiB); 4 KiB sector erase op `0x20`. Sector `0x13000` also holds non-EDID data (before `0x138D8` and after `0x13BD8`); it is rewritten byte-identical.

## Flash procedure
Pre: the DDC bus number changes across reboots; resolve it from `ddcutil detect --brief`. Do all of this on the same bus the dumps used (bus 20 last time). Use dir `/mnt/2tb/git/awto-ddc`.
1. Confirm bus and a healthy read: `python3 scripts/rtd_isp_probe.py <bus>` (read-only).
2. Dry run (enters ISP, reads, backs up, compares, resets; no erase/program):
   `python3 scripts/rtd_flash_sector.py <bus> 0x13000 ~/vendors/realtek/analysis/edid/patched_sector_13000.bin --expect-current ~/vendors/realtek/analysis/edid/orig_sector_13000.bin`
   - Expect: `JEDEC c22014`, `current vs new file: 394 bytes differ` (vs factory demo), `current vs --expect-current: 0 bytes differ`, a backup file in `tmp/flash-backups/`.
   - If the second number is non-zero the sector differs from the 2026-11-04 dump: stop and inspect.
3. Keep the backup (`tmp/flash-backups/sector_013000_<timestamp>.bin`) and `orig_sector_13000.bin` (identical content expected). Copy the backup somewhere durable before step 4.
4. Write (main session gate): same command plus `--write`.
   - Sequence: backup -> unprotect status reg if BP bits set (restored afterwards) -> erase 4 KiB -> blank check -> 16 x 256 B page programs -> read back -> compare -> scaler reset.
   - Expect `VERIFY OK: readback == new data`. Any other result: do not power-cycle yet; go to Revert.
5. Power-cycle the monitor (ISP stops the scaler MCU; the `0xEE` reset normally restarts it).
6. Verify on the host: re-read EDID via `/sys/class/drm/*/edid` per connector (`edid-decode`), expect `AWT` / `awto-mon` / `AWT26110001`, PASS. Replug or reboot if the kernel cached the old EDID. Check each input (DP and both HDMI).
7. Also confirm DDC/CI still works (`ddcutil detect`, capabilities) and the picture comes up at 3840x2160@60.

## Revert
- Same writer, backup as the data file, new data as the expected-current:
  `python3 scripts/rtd_flash_sector.py <bus> 0x13000 <backup.bin> --expect-current ~/vendors/realtek/analysis/edid/patched_sector_13000.bin --write`
- If the monitor does not respond on DDC (EDID corrupt but ISP port is independent of the EDID): ISP is still reachable on I2C 0x4A; use the same command. If `--expect-current` aborts because the sector is partially written, drop that flag (backup is the known-good source).
- Last resort: full 1 MiB re-flash from `dumps/jxc-4k-flash-bus20.bin` with RTDTool / `rtd-2660` flow.

## Size measurement + which unit is flashed (2026-11-04)
- Active-area height measured on the glass = 336 mm, ±2-3 mm (actual lit pixels). 333-339 all = 27.0" real 16:9
  (not 28.0"=350, not 23.8"=296). EDID size field is cm-granular (59x33 cm) so ±3mm doesn't change it. 597x336 stands.
  Closest catalogued panel by size: Samsung LTM270FL01 596.16x335.34 mm (PLS/eDP) — within tolerance, and now consistent with the IPS/PLS visual confirm.
- All three units flashed to AWT:awto-mon (IPS/sRGB build), each a distinct serial. Bus numbers shift on
  re-enumeration — map by DRM connector, not bus. Mapping at 2026-11-04T13:18+1100:

  | DRM connector    | serial (0xFF) | when flashed            |
  |------------------|---------------|-------------------------|
  | card1-DP-4       | AWT26110001   | 2026-11-04T13:01 (IPS)  |
  | card0-DP-3       | AWT26110002   | 2026-11-04T13:18        |
  | card1-HDMI-A-3   | AWT26110003   | 2026-11-04T13:18        |

- Serials are a fixed per-unit sequence AWT2611000N, NOT a hardware fingerprint: MX25L8006E (JEDEC c22014)
  has no readable factory unique ID — RDUID 0x4B returns 0xFFFFFF (opcode absent) and the 128-bit secured-OTP
  ESN reads all-0xFF (unprogrammed) on both factory units. Confirmed via `rtd_flash_sector.py <bus> --read-id`.
- Flash ceremony: a standalone no-op dry-run is pointless. `--write` already does backup -> blank-check ->
  program -> read-back verify -> abort-on-mismatch -> re-protect. One --write is the safe path; skip the separate dry-run.
