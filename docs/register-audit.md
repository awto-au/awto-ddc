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
- Read-behind correction (2026-11-19, `re/regmap/README.md` "Read-behind"): the first read of a dword on pages `88 8A 8B 8E 8F 90 A0 A3 A4 A6 A7 A8 AB AC AE AF C8 CA CB CE CF D0` can return the previous dword's byte; dumps and scans from before the fix are wrong on them. Counts below are from the observation store with the old values of those pages dropped (ISP: `88 8A 8B 8E 8F 90 C8 CA CB CE CF D0`; A-pages read clean over ISP): undocumented, nonzero in an ISP dump, `9F` echo excluded: 345 (331 constant, 14 vary) before, 149 (139 constant, 10 vary) after.
- Changing on one unit in one state: `21D8` CURRENT_PC_BANK (PC bank at halt); `7607` MHL_DATA_ALIGN_CTRL bit 1; `A7E0..A7E3` / `AFE0..AFE3` DC_PHY_BIST_DETAIL (state dependent: `00 FF 10 08` = the bytes of `00E0..00E3` in the fixed scans, `5E 14 BE 8D` over ISP after a reset; not noise, not per-unit constants). `8F9D / 8F9E / CF9D / CF9E` survive as changing pattern bytes (92 24 DB B6 6D 49) inside `8F9B..8FBD` / `CF1E..CFCE`, seen in the fixed scans of unit 3 (C1 vs C2). `FF88` is ISP 00 vs live 80 = a state difference, not a change inside one state; `regmap_query.py --undocumented-nonzero --changing` lists 6 now (was 10).
- Constant tables that survive the fixed scans: `883B..88BF` = 0x0D at offset 3 mod 4 (read right after a low address of page 88 it gives other bytes: history dependent, unresolved); `8E11..8E28` (0xFF then 0x22); `8A30..3F`, `8AB4..BF`, `8A05..8A1F` (01 pattern). Artifacts, gone in the fixed scans: the 0x0D stride in `88C0..88FF` / `C8C0..` (those offsets read the same bytes as `00C0..00FF` on pages 88 / 8A / 8B / 8E), the 0x01 at `8A10..8A12`, `8AC0..8ACF` as a table. Other constants: ECBUS `2700..2710` / `6700..6710` config; `21A2 / A5 / A8 / AB` BPx_ADDR_BANK = FF and `21D0` DBG_ACC_CTRL = 10; `76xx / 77xx` MHL3 / DPF block; `9CF4..F7` = 55 AA 55 AA; `38DF` = 55.
- Two audio-label dumps store the first byte as a string: `0600` / `0800` values untrusted.
- Value differences vs regdb: `01E4` reads 0x73 (regdb reset 0x76), `0022` reads 0x6C (reset 0x68).
- ISP dumps are post-halt / reset states: `FFxx` reads 00 there; live values differ (`FFED` 0x92, `FFEE` 0x44, `FF6C` 0x60).
- No thermal / voltage sensor and no uptime-monotonic counter found (`docs/temperature.md`).

## Live scan plan
- Read-only, debug slave 0x35, 100 kHz, byte path 8..15 min per pass; running on units 1 and 2 (Dan approved read-only scans there 2026-11-19). Unit 3 only for tests.
- Excluded: data / index ports, OSD ports, HDCP ports, `FF22..FF2F` debug engine, `FE60..FE6F`, `FF00`, `FF03..FF07`, `8F / CF` INT_STATUS.
- Results land in `re/regmap/obs/` via `regmap_import.py`; the summary file `docs/live-register-scan.md` (units 1 / 2 scan agent) links here.
