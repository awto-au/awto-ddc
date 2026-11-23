# Flash registry = the on-device manifest

Status 2026-11-18, offline tests only (`tests/test_flash_manifest.py`, `tests/test_flash_incremental.py`); no hardware run yet.
Decision (Dan, 2026-11-18): the registry lives ON the device; no host-side file is a trust source for the diff.

## Process (`dev.py flash` -> `rtd_flash_image.py`, `--no-backup` path)

1. Read the manifest sector `0xFD000` (one 4 KiB read) after the read gate + CRC calibration (both unchanged).
2. Per-sector CRC32 of the new image (computed at flash time) vs the manifest's -> sectors to write.
3. Truth check, every flash: hardware CRC8 over every run of sectors planned to be skipped (blank image sectors included) vs crc8 of the image bytes. No data transfer.
   - A mismatching run is localised per sector, its sectors join the write set, logged `manifest stale at run sectors A-B ...`.
   - CRC engine failed calibration: the same runs are read back instead.
4. Volatile sectors (below) are read and compared to the image every flash, never skipped on the manifest's word.
5. Erase / program / verify the write set, `boot_last` order, then the final CRC over the image runs (unchanged).
6. Write the manifest LAST; skipped when the device already holds exactly it (a no-op flash writes nothing).

Pre-flash alert tone honours mute (VCP 0x8D) and `AWTO_SOUND=off`: `docs/flash-screen.md`.

- No valid manifest (erased, no valid word, bad CRC, aborted flash, other sector count, `--full`): hardware CRC of every image sector builds the diff (CRC8 per quarter sector, `flash_state.CRC_PARTS`, a changed sector hides with p = 2^-32), or a readback without the CRC engine. Logged `no valid device manifest (...)`. The manifest is written at the end.
- `--no-device-manifest`: no invalidation and no manifest write (a valid manifest is still read and used).
- Local `tmp/fw/<serial>-flash-state.json` is kept for MIXED-image tracking, deploy (EDID sector) and `_log_unit_state`; the diff never reads it.

## Manifest format (`scripts/flash_manifest.py`)

- 4 KiB sector at `0xFD000`; `0xFE000` stays the spare (alternation / self-flash T1).
- `0x000` header, 16 B: magic `AWFM`, version u8 = 1, flags u8 = 0, count u16 (image sectors, 224 today), image_id u32 (first 4 B of the image SHA-256), reserved u32 = 0.
- `0x010` table: CRC32 of image sector 0..count-1, u32 LE each; the word at `0x200` is skipped (stays `FF`). Capacity 249 sectors.
- `0xF00` commit page, programmed LAST: `AWOK` + CRC32 over `[0x000, 0x400)`. Erased or torn = invalid.
- CRC32 = CRC-32/ISO-HDLC (`zlib.crc32`): poly 0x04C11DB7 (reflected 0xEDB88320), init 0xFFFFFFFF, refin + refout, xorout 0xFFFFFFFF, check("123456789") = 0xCBF43926. Firmware: bytewise with a 16-entry table.
- Standalone: `python scripts/flash_manifest.py build image.bin --out sector.bin`; `check <1 MiB dump | sector.bin> [--image image.bin]` (offline; reading the device needs an ISP session, which halts the MCU).
- Write order: erase (unless blank), body pages, commit page, verify the sector (CRC, readback on mismatch). Failure is logged and never fails the flash (image already verified); the next flash rebuilds the diff from the device.
- Invalidation: before the FIRST image erase of a flash (write set non-empty) the manifest sector is erased. An abort, kill or failure leaves "no manifest" = unknown.
- Not part of the image: it is outside the image CRC runs; an image longer than `0xFD000` (253 sectors) is refused for the manifest.

## Is 0xFD000 unused by firmware? (checked 2026-11-18)

- Flash map (`docs/boot-logo.md`): code `0x00000-0x67000` of bank overlays (image 224 sectors, to `0xDFFFF`; 240 to `0xEFFFF` once bank 14 holds code, #44), settings `0xFB000-0xFCFFF`; `0xFD000-0xFEFFF` erased on every unit (measured, `fw/rtdfw/awto/nvram/nvram.c`).
- Live NVRAM store = SDK EEPROM emulation, bank 15 pages 11-12 = `0xFB000-0xFCFFF` (`fw/nvram/nv_gate.c`, `docs/nvram-settings.md`).
- The retired record log (`nvram.c`, `NV_BASE 0xFD000`) is NEVER written by the firmware: `nv_store` / `nv_wipe` have no caller outside its own tests; the only access is `nv_find` in `settings.c` (`set_load_legacy`), a read at the first boot of the #151 layout when the SDK store is invalid.
- That read scans 512 B slots for magic byte `0xA7` (+ format + Fletcher check). The manifest layout keeps `0xFF` at every 512 B slot boundary it could touch (`0x000` is `A`, `0x200` skipped), so no slot can look valid.
- Result: 0xFD000 is usable; 0xFE000 stays free. `docs/self-flash.md` T1 moves to 0xFE000 only.

## Volatile sectors (read and compared every flash)

- `flash_state.VOLATILE_RANGES`: NVRAM store `0xFB000-0xFCFFF`, spare `0xFE000`. The manifest sector has its own rule.
- Per-unit EDID sector of the image (`build_fw_edid_sector.edid_offsets`, written by `dev.py deploy`): the manifest holds the shared image's CRC32 for it, the device holds the patched sector.
- Only matter inside the image length; today's image (224 sectors) contains just the EDID sector. It is read, differs, and is rewritten every flash exactly as before.

## What each check proves

- CRC32 table vs new image: which sectors the LAST flash of this image-state wrote. It records intent, not the flash's truth.
- Truth check (hw CRC8 over all skipped runs): the flash itself equals the image there. Miss chance 1/256 per stale run, and only for sectors the manifest already claims equal.
- Final CRC: whole image after the writes (same engine, unchanged).
- Read gate / calibration: read path and CRC engine sane before any erase (#71).

## Failure modes

- Manifest valid but stale (runtime write, other tool, bit rot): truth check finds it, only those sectors are rewritten.
- Stale AND the CRC8 collides (1/256): sector kept as is; the manifest rewrite then records the image's CRC32 for it. Residual risk, same as the previous drift guard.
- Aborted flash: manifest erased at the start, never rewritten; next flash takes the no-manifest path.
- Manifest write fails or tears: invalid by its commit CRC; the next flash takes the no-manifest path.
- Another host / tool flashes without a manifest write: the truth check detects what it changed; sectors it left identical are skipped correctly.
- EDID deploy changes a sector after the manifest write: volatile, handled by its own rule.

## Summary lines (examples from the fake bus, 24-sector test image with 7 blank sectors, `pytest -s -k summary_lines`)

First flash (no manifest):
```
SUMMARY: sectors: image 24, erased 17, programmed 17 (272 pages), skipped 7 (already match, no need to flash); erase operations 17
SUMMARY: diff from: no valid manifest (no valid word (erased, or a flash that did not finish)); diff from the device
SUMMARY: device manifest written (erase + 2 pages, valid word last)
```
No-op flash:
```
SUMMARY: sectors: image 24, erased 0, programmed 0 (0 pages), skipped 24 (already match, no need to flash); erase operations 0
SUMMARY: diff from: device manifest (image_id cb1fc095)
SUMMARY: device reads: 3 of 24 image sectors read, 21 avoided (...); truth check: 1 CRC run(s) over 24 sectors in 0.00 s
SUMMARY: device manifest unchanged (valid, identical): nothing written
```
One-sector change:
```
SUMMARY: sectors: image 24, erased 1, programmed 1 (16 pages), skipped 23 (already match, no need to flash); erase operations 1
SUMMARY: device reads: 3 of 24 image sectors read, 21 avoided (...); truth check: 2 CRC run(s) over 23 sectors in 0.00 s
SUMMARY: device manifest written (erase + 2 pages, valid word last)
```
Stale manifest (device sector 11 changed behind its back):
```
manifest stale at run sectors 0-23 (0x000000-0x017fff): 1 sector(s) differ [11]
SUMMARY: sectors: image 24, erased 1, programmed 1 (16 pages), skipped 23 (already match, no need to flash); erase operations 1
SUMMARY: diff from: device manifest (image_id b88e4d4a); STALE at 1 sector(s)
```
- Totals: erased + skipped = image sectors; programmed <= erased (data -> blank is erase-only). `DONE:` keeps its prefix and appends `; erased N programmed N skipped N of M`.
- Warning screen row 1: `BANKED BANK 14/15 SKIP 212/224` (`docs/flash-screen.md`); manifest outcome is log-only.
- Device reads in the summary count the read gate (2) + the manifest (1) + volatile sectors; "avoided" is against reading every image sector.

## Truth-check cost (to measure on unit 3)

- Fake bus: 1 hw CRC call per run of skipped sectors (1 run for a 24-sector image, +1 per changed sector splitting a run); the model has no timing.
- Real number needed: seconds per hw CRC call over a 4 KiB / 224 KiB run at 1 MHz and 100 kHz, from the `truth check: N CRC run(s) over M sectors in X s` summary field. Code comments put one sector CRC at ~10 ms (not re-measured).

## Decision table: why the local file was dropped as trust source

| | local `tmp/` file | on-device manifest |
|---|---|---|
| survives lost `tmp/`, another PC, a unit moved | no (needs a 1 MiB read to rebuild) | yes |
| per-flash cost | none | 1 sector read; +1 erase / 2 pages / verify only when it changes |
| stale after runtime writes / other tools | yes | yes, same; the truth check covers both |
| aborted flash | `write-failed` + null entries to interpret | erased at the first erase: no manifest = unknown, no interpretation |
| two sources to reconcile (file vs device) | yes (rebuild, trust, sampling rules) | one |
| firmware can use it later | no | yes (boot self-check, self-flash) |
| wear | none | 1 erase cycle on `0xFD000` per changed flash (flash rated 100k) |

- The truth check is the same hardware CRC either way; dropping the file removed trust levels, sampling (3 runs) and `--registry-rebuild` / `--no-registry` / `--verify-all`.
- Sampling is gone because the all-runs check is one hardware CRC per run with no data transfer.

## Follow-ups (not built)

- Firmware boot self-check of its own sectors against the manifest (CRC-32/ISO-HDLC, 16-entry table); `docs/self-flash.md`.
- Self-flash update writes the manifest the same way (body pages, commit page last).
