# Live register scan (MCU running, debug slave 0x35)

- ISP-dump audit (coverage, undocumented counts, scan plan): `docs/register-audit.md`.

- Tool: `scripts/reg_live_scan.py` (one pass = link on, calibrate, scan, link off); analysis: `scripts/reg_live_diff.py`.
- Data: `tmp/regs/live/<serial>-<label>-<stamp>.json` (untracked); log `tmp/logs/reg_live_scan.log` (one line per read: addr, value, ok/NAK/SLOW, ms; excluded addresses logged as EXCLUDED).
- Tables: `tmp/scratch/live_*.tsv` (all, changing_AB, undoc_nonzero, neverread_nonzero, unit_diff, highlights, pagesummary).
- Conditions (2026-11-19, 00:13-00:47 +11:00): units 1 (HDMI-1, 4K60, brightness 64) and 2 (DisplayPort-1, brightness 32) in normal use, own firmware (diag version 2 = block path), 100 kHz, host state read before/after with ddcutil getvcp 60/10/D6: unchanged.
- Passes: A at t0, B 4+ min later, C 30+ min after A; same input and mode throughout.

## Reads and timing
| unit | pass | path | result | reads | elapsed |
|---|---|---|---|---|---|
| 1 | A / B / C | block (24 B) | ok / ok / ok | 3462 / 3460 / 3463 transactions, 0 failed | 14.3 / 14.5 / 14.6 s |
| 2 | A / B / C | block | ok / ok / ok | 3462 / 3463 / 3463, 0 failed | 12.2 / 12.7 / 12.1 s |
- 65 425 addresses per pass (65 536 minus 111 excluded) = ~4.5 kB/s; one pass on unit 3 expected ~13 s + link on/off ~0.3 s.
- Limits: per-read limit = 1.25 x worst of the 21 calibration transactions on page 00 (unit 1 14.5 ms, unit 2 4.5 ms). Read that returns late is logged SLOW; it counts as failed only above 10 x the limit (a 1.25 x limit aborted a unit 2 pass on pages 99/9A/9B/BE/C1-C5, where reads take 10-18 ms, with 0 NAK).
- Wall bound = 1.25 x measured full scan (first pass: extrapolated from calibration worst; the unit 2 first attempt aborted at 11.0 s, 0xE790, link left off, no NAK). Abort: 3 consecutive failed reads, heartbeat (0x0000 != 0xCF) failed, wall bound. Heartbeat before, every 256 B (64 B on never-read pages), after.
- Aborted runs kept as `Aabort` / `Babort` (unit 2, wall bound and SLOW limit respectively); not used in the tables.

## Writes the tooling made to the units
- Link on (`dbg_link.py`): DDC/CI setvcp E3 = A5 NN to 0x37 (NN = 10 min, firmware falls back by itself).
- Link off: over 0x35 `0x01 F6`, `0x03 3B`, `0x3B F8` (test command 0x3B at 0xF6F8 = back to DDC/CI).
- Scan: only hi-byte staging (`0x01`) and block read commands (`0x3C lo hi len seq`); bus object is `Real(allow_write=False, regread=True)`.
- One `dev.py health --unit 1` (00:11, before the scan existed) also ran its OSD event + OSD test command: a ~140 ms info pop-up on unit 1. `dev.py synclog` (read) ran once per unit afterwards.

## Excluded (never read; table `EXCLUDE` in the script, reason per entry)
- Index/data ports of regdb PORT_ADDR (0024/25 ... BAC1-BAC4), OSD ports 0090-0092 0099 009D, 0069, 006D, 07CA, 07D9, HDCP key ports 71C4 72C4.
- Our debug engine FF22-FF2F, DDC access ports FE60-FE6F, FF00 (IRQ status), FF03-FF07 (triple-byte op), INT_STATUS 8FF0-8FF7 and CFF0-CFF7.
- Total 111 addresses.

## Results (units 1 and 2, passes A/B/C)
- Read: 65 425 addresses; all-00 across passes: 55 530; all-FF: 260.
- regdb status of what was read: 7818 documented, 1280 blank/reserved, 56 327 no row.
- Pages D0-FC (12 252 addresses) are firmware XDATA RAM, not scaler registers; 86 of the changing addresses are there (firmware variables, e.g. F6xx).
- Page select 0x9F reads back the page number on every page (e.g. 0x029F = 02): explains most "non-zero on never-read pages" (one address per page).
- Never-read pages (below D0) with real content: 0A (36 non-zero, SDK names PG_/DPF_/..., no regdb row), 18 and 19 (CEC), 2B and 2C (ECBUS), BB (DP PHY, 86), BC (audio, 58), BD (DP AUX, 29). Same values on both units except BD 60-6F (AUX, 4 addresses changing).
- Non-zero with no regdb row or blank row: 6936 (899 below D0).
- Units differ (any pass): 3107 addresses (451 below D0 on pass A).

### Interesting addresses
| addr | name | unit 1 A/B/C | unit 2 A/B/C | ISP dumps (unit 3, post-halt) |
|---|---|---|---|---|
| 06A4 | OSC_TRIM_CNT | C8 C8 C8 | A8 A8 A8 | C8 CB CF D0 |
| 06A5 | EMB_BGRES | 77 77 77 | 77 77 77 | 77 |
| FF09-FF0C | ADC_A0..A3_CONVERT_RESULT | F8 F8 F8 x4 | F8 F8 F8 x4 | 00 F8 |
| A750-A757, AF50-AF57 | DC_PHY speed sensor ctrl/status | identical, STATUS 00 | identical, STATUS 00 | 00 (A753/AF53 = 01) |
| A7E0-A7E3 | DC_PHY BIST_DETAIL (A) | 5F CD B0 83 const | 63 5B B8 2F const | 56/5E/5F, 14/54/8D ... |
| AFE0-AFE3 | DC_PHY BIST_DETAIL (B) | 87 D3 EE 5F const | 7F E9 2D 06 const | 87/EE ... |
| FFAA / FFAB | WATCHDOG_CNT2 / CNT23_VALUE | 16 43 E9 / 73 55 52 | 67 AA D1 / 60 62 6E | 00 08 / 00 65 (halted) |
| FF79 | ACCESS_FLASH_ADDR_1 | B0 B6 BC (+6 per pass) | C6 CC D2 (+6 per pass) | 00 B0 |
| 0045 | LAST_LINE_L | 85 85 87 | AD B1 AB | 37 5C AE CA CC CD DD |
| 38D8 38D9 | DPTX_CMU8/9 | BF 68 24 / A4 CE 7B | D0 56 29 / BC CD 04 | |
| B996-B998 | AUD_TRND_4..6 | 00 | 3E 4C 4F / 3E 4C 4F / 0F 00 00 | 00 |
- Trim counter: constant over 30+ min on both units; units differ by 0x20 [sdk-hypothesis: per-chip trim, not temperature].
- ADC: all four channels read F8 on both units = no key pressed / pulled high; no channel floats or drifts [sdk-hypothesis: key ladder reads high when idle].
- DSS status all 00 and BIST_DETAIL constant per unit, different between units, within the ISP-dump value sets of the other unit.
- Counters that step +1 per pass (SPI_S0/S1_RX_BUF_READ_ADR 22AC/22BE, MSG_RX_BUF0/1_RDPTR B712/B716/B732/B736, AUX_FIFO_RD_PTR 9DAD/9FAD/BDAD, HDMI_PSAP 72CD, CACHE_CONTENT_ADDRESS_L FDC8, BDDC): follow the number of scan sessions [sdk-hypothesis: advanced by the link-on DDC/CI message / host getvcp traffic, i.e. self-induced].
- WATCHDOG_CNT2/CNT23 values are live free-running counts (different every pass; the halted ISP dumps show 00/08/65); FF79 steps +6 per pass on both units.
- Sensor-like (drifting, small): 0045 LAST_LINE_L (measured line count, mode related), DPTX_CMU8/9 (PLL calibration code), AUD_TRND/SUMC (audio PLL trend), B8BC MN_SCLKG_SDM_SUMC_L: all documented, none monotonic over A/B/C beyond noise. Unit 1 never changes in B901/B922/B996 (audio/DP regs inactive on HDMI).
- Full lists: `live_changing_AB.tsv` (122), `live_undoc_nonzero.tsv`, `live_neverread_nonzero.tsv`, `live_unit_diff.tsv`.

## Not read
- The 111 excluded addresses; ports behind index/data registers (their data registers are excluded, not swept).
- Nothing else failed: no NAK on any of the 6 passes.
