# Flash registry: what each unit's flash holds, kept on the host

Status 2026-11-18, offline tests only (`tests/test_flash_registry.py`); no hardware run yet.

## What it is

- The registry = the per-unit manifest `tmp/fw/<serial>-flash-state.json`, extended (`scripts/flash_state.py`, VERSION 2). One typed file per serial; dev.py deploy / recover / `_log_unit_state` already maintain it, so no second file.
- A v1 manifest is ignored (derived artifact, no migration): the next flash writes every image sector, or run `./dev.py flash --registry-rebuild` once.
- Incremental flash diffs the NEW image against the registry; unchanged sectors are never read from the device.

## Schema

| field | meaning |
|---|---|
| `version`, `serial`, `sector_size`, 256 sectors | geometry guard; another serial / geometry = file ignored |
| `sectors[i]` | SHA-256 of what the device holds in sector i; `null` = unknown |
| `how[i]` | `w` written + verified by us, `r` read back from the device, `null` unknown |
| `image`, `image_size`, `image_sha256`, `git_commit`, `time` | last image flashed / read |
| `source` | `write`, `readback`, `+per-monitor-edid` suffix (deploy); `write-in-progress` / `write-failed` = a session ended part-way |
| `verified_time`, `verified_how` | when + how the DEVICE last confirmed the registry (final CRC over the image runs, hw CRC runs, rebuild read) |

## Volatile sectors (never trusted, read from the device every flash)

- `flash_state.VOLATILE_RANGES`: gamma `0xE0000-0xE2FFF`; NVRAM settings + retired registry `0xFB000-0xFEFFF` (`docs/nvram-settings.md`: gate writes at runtime; `FFF4` backup lives there).
- Per-unit EDID sector of the image (`build_fw_edid_sector.edid_offsets`, written per unit by `dev.py deploy`).
- Only matters inside the image length. Today's image = 224 sectors (`0x00000-0xDFFFF`), so the settings / gamma ranges are outside it and never touched; the EDID sector is inside and is the live case.
- A volatile sector is read, hashed into the registry (`r`), compared to the image; written only when it differs. Same result as before for the EDID sector (it differs from the shared image after deploy, so it is rewritten).
- `--no-registry` drops this rule.

## Invalidation rules

- Session start (first erase): every sector to be written goes `null` and `source = write-in-progress`, saved before the erase. A kill / crash / abort leaves them unknown.
- Failure or exception: `source = write-failed`; registry untrusted as a whole (`FlashState.trusted` false) until a clean session ends.
- Final CRC mismatch: the mismatching run's sectors go `null`.
- `trusted` also needs: not `--no-registry`, not `--full`, no MIXED image from an earlier session.
- Untrusted registry = every run of unchanged sectors is hw-CRC checked (old behaviour) and `null` sectors are read.
- Other writers (RTDTool, manual ISP session, another host, a lost / copied `tmp/`): invisible to the registry. Caught by the drift guard (sampled runs) or the final CRC; if in doubt `--registry-rebuild`.
- dev.py deploy edid: records the patched sector hash (`mark(..., w)`), source gets `+per-monitor-edid`.

## Drift guard: what it proves

- Hardware CRC8 (`docs/flash-crc.md`, calibrated == crc8 of a readback each run) over a run of unchanged sectors vs crc8 of the image bytes. Reads no data. Miss chance 1/256 per corrupted run.
- Trusted registry: first + last + random middle runs, `DRIFT_SAMPLE_RUNS = 3` (all runs when fewer). `--verify-all` / `--no-registry` / untrusted registry: every run.
- A pass proves the sampled runs equal the registry; it says nothing about unsampled runs. Those are covered by the final CRC after writing (whole image, always every non-blank run).
- Any mismatch: registry distrusted, automatic full readback diff of the image region (authoritative, hashes recorded as `r`), logged `!!! DRIFT ... registry untrusted -> full readback diff`.
- CRC engine failed calibration: guard falls back to the 4-sector readback sample (readback verify for writes).
- Read gate (2 reads of sector 0 must match, #71) and CRC calibration stay before any erase.

## Flags (`./dev.py flash`)

- default: registry diff, volatile rule, sampled drift guard.
- `--verify-all`: drift guard over every run.
- `--no-registry`: previous behaviour (every run checked, no volatile rule).
- `--registry-rebuild`: read the whole 1 MiB once, verify each 64 KiB chunk by hw CRC (second read when the CRC engine is off), rebuild the registry (`r`), then flash only the difference. Nothing is erased before the read verifies; no drift guard afterwards (the read is the truth). Use after a lost `tmp/`, a foreign tool, or a MIXED history.

## Summary line (log, `DONE:` keeps its old prefix)

```
SUMMARY: sectors: image 224, erased 2, programmed 2 (32 pages), skipped 222 (already match, no need to flash); erase operations 2
SUMMARY: bytes: erased 8 KiB, programmed 8 KiB, skipped 888 KiB; ISP time 1.1 s writing, 4.0 s total
SUMMARY: device reads: 2 of 224 image sectors read, 222 avoided (~88.8 s at the measured 400 ms per 4 KiB); hw CRC runs 3 of 11
DONE: 5.3 s total, 2/224 sectors changed, 0.008 MB at 0.0074 MB/s; erased 2 programmed 2 skipped 222 of 224, bus 1000 kHz
```

- erased = sectors erased (= changed); programmed = erased sectors with non-blank new content (a data -> blank sector is erase-only); skipped = image - erased; erase operations also count redos.
- On the warning screen row 1: `BANKED BANK 14/15 SKIP 212/224` (skipped / image sectors; erased = the `SEC n/N` of row 2).
- The ms-per-read figure is measured per run from the read gate; the example number above is illustrative.

## Measured (fake bus, 224-sector image, 2 sectors changed, 11 unchanged runs, 2026-11-18)

| path | sectors read | hw CRC runs (drift guard) |
|---|---|---|
| full readback diff (what the registry replaces) | 224 | 0 |
| registry, trusted (default) | 2 (read gate) | 3 of 11 |
| `--verify-all` / `--no-registry` | 2 | 11 of 11 |
| `--registry-rebuild` | 258 (256 + gate) | 0 |

- The pre-registry incremental path already read no unchanged sector while the CRC engine worked; the registry's saving is against a read-based diff (222 reads, ~0.4 s each at 100 kHz per the code comment in `rtd_flash_image._write_sector`, not re-measured) and 8 of 11 CRC runs.
- Real-bus time saved is reported by the run itself; hardware figures are for Dan's approved unit-3 test.

## Failure modes

- Registry says match, device differs, run unsampled: drift found only by the final CRC after the writes -> RuntimeError, sectors `null`, unit left per MIXED rules (not reset), rerun repairs. Use `--verify-all` to catch it before any erase.
- Wholesale swap by another tool: first / last runs are always sampled, so it is caught.
- Registry copied between hosts: valid if nobody flashed in between; the drift guard samples it.
- Volatile ranges incomplete: a runtime-written sector outside the list is trusted; the drift guard catches it only when its run is sampled.
- v1 / corrupt / other-serial file: ignored, full path.

## Decision: manifest ON the device? (Dan 2026-11-18: "or maybe the NVRAM holds the CRC32 for every sector?")

Candidate: image tag + CRC32 per image sector (224 x 4 B = 896 B + header) in one sector, valid marker written last by the flasher; the firmware could self-check at boot.

| | host registry (built) | on-device manifest | hw CRC over runs (drift guard) |
|---|---|---|---|
| truth about the flash | what we intended / read | what we intended to write | the flash itself |
| goes stale on runtime writes, other tools | yes (volatile rule, guard) | yes, same | no |
| survives lost `tmp/` / other PC | no (`--registry-rebuild`: 1 MiB read) | yes | n/a (needs a reference) |
| data read per flash | 0 | ~1 KiB (~1/4 of a sector read) | 0 |
| cost per flash | 0 | +1 sector erase + 4 page programs + verify (~1 sector = ~0.12 s at 1 MHz, 26 s / 224) + 1 erase cycle of wear | ~10 ms/sector-equivalent, hardware |
| firmware / layout impact | none | a sector the firmware must not touch, outside the CRC list; sticky layout must not use it | none |
| aborted flash | `write-failed` + `null` entries | marker not rewritten: old manifest invalid or absent = unknown (correct) | n/a |
| per-sector hash strength | SHA-256 | CRC32 (hw CRC8 is the only on-chip engine; host computes CRC32) | CRC8, 1/256 miss per run |

- Where it would sit: retired registry `0xFD000-0xFEFFF` (never written; first-boot read of the #151 layout may still parse it, check before use). Conflicts: `docs/self-flash.md` T1 uses those two sectors as test spares (#235).
- Recommendation: host registry primary + hw CRC drift guard as the truth (built here). The device manifest gives only portability (another PC / lost `tmp/`), which `--registry-rebuild` already covers for one 1 MiB read (hw-CRC-verified). It costs a sector write + wear per flash and a protected sector, and is as stale-able as the host file.
- Fits later: self-flash (`docs/self-flash.md` section 4: per-page CRC + whole-image CRC + valid marker written last, session record) needs an on-device record anyway; build it there, and let the host flasher read it as a second source.
- DECISION FOR DAN (not implemented): write an on-device manifest at the end of a clean host flash?
  - Proposed layout if yes: sector `0xFD000` (one 4 KiB sector; `0xFE000` spare for A/B alternation to avoid a window with no valid manifest); header 16 B (magic, version, image tag hash, count 224, flags) + 224 x CRC32 LE + header CRC32; erase, program, verify, THEN the valid word (first 4 bytes, programmed last; erased 0xFFFFFFFF = invalid).
  - Writer: flasher only, after the final CRC. Readers: host flasher (second source: compare against the registry; mismatch = distrust), firmware boot self-check (future).
  - Excluded from the final-CRC runs and from the image diff (volatile); the self-flash T1 spare-sector plan moves to `0xFE000` / another sector.

## Open

- Real-bus numbers (read ms, CRC ms per run) from the unit-3 test below.
