# Register audit of the ISP dumps and the live scan plan (2026-11-19)

- Scope: what our dumps (`tmp/regs/`) cover vs the regdb (`re/regdb/RTD2795T-CG.tsv.gz`) and the SDK. Per-register results live in `re/regmap/regs.tsv` (#236, #237); this file keeps the numbers and the scan plan.
- Dahua firmware's own register use: `docs/reversing/dahua-fw/register-audit.md` (different audit).
- Tags: [hw] dump / live read, [spec] regdb, [sdk-hypothesis].

## Coverage [hw]
- 31 ISP dumps with pages (47 files in `tmp/regs`): 111 of 256 pages read = all 95 regdb pages + 16 non-regdb pages (81..89, A1, A2, A9, AA, B1..B4).
- 145 pages never read: SDK-defined 0A, 18, 19, 2B, 2C, BB, BC, BD; 137 in neither regdb nor SDK.
- 28,416 addresses, 353,284 byte reads.
- Pages 81..89 etc. read all zero except the page-select echo (`9F`).
- Our regdb is incomplete: 1919 SDK registers missing.

## Undocumented (no regdb row or blank row)
- 20,491 addresses; non-zero 351 (excluding the `9F` echo): 331 constant, 20 vary.
- Changing on one unit in one state: 10. `21D8` CURRENT_PC_BANK (PC bank at halt); `7607` MHL_DATA_ALIGN_CTRL bit 1; `A7E0..A7E3` / `AFE0..AFE3` DC_PHY_BIST_DETAIL (noisy); `8F9D / 8F9E / CF9D / CF9E` undocumented DDR-phase FIFO regs; `FF88`.
- Constant tables: `883B..88FF` stride 4 = 0x0D (mirrored `C8xx`); `8E14..8E27`; `8A09..8A1F`, `8A30..3F`, `8AB8..CF`; ECBUS `2700..2710` / `6700..6710` config; `21A2 / A5 / A8 / AB` BPx_ADDR_BANK = FF and `21D0` DBG_ACC_CTRL = 10; `76xx / 77xx` MHL3 / DPF block; `9CF4..F7` = 55 AA 55 AA; `38DF` = 55.
- Two audio-label dumps store the first byte as a string: `0600` / `0800` values untrusted.
- Value differences vs regdb: `01E4` reads 0x73 (regdb reset 0x76), `0022` reads 0x6C (reset 0x68).
- ISP dumps are post-halt / reset states: `FFxx` reads 00 there; live values differ (`FFED` 0x92, `FFEE` 0x44, `FF6C` 0x60).
- No thermal / voltage sensor and no uptime-monotonic counter found (`docs/temperature.md`).

## Live scan plan
- Read-only, debug slave 0x35, 100 kHz, byte path 8..15 min per pass; running on units 1 and 2 (Dan approved read-only scans there 2026-11-19). Unit 3 only for tests.
- Excluded: data / index ports, OSD ports, HDCP ports, `FF22..FF2F` debug engine, `FE60..FE6F`, `FF00`, `FF03..FF07`, `8F / CF` INT_STATUS.
- Results land in `re/regmap/obs/` via `regmap_import.py`; the summary file `docs/live-register-scan.md` (units 1 / 2 scan agent) links here.
