# Duplicated / unshared code (#283)

Search 2026-11-21 on origin/main 30b070a0 (Rx2/Rx3 TMDS already shared, #292). Tracking: #283.

## Method
- `scripts/clone_scan.py` (stdlib only, TSV out, log `tmp/logs/clone_scan.log`):
  - line clones: maximal runs of identical normalised lines across files; `--norm` turns digit runs into `0` so Rx2/Rx3, `_D2_`/`_D3_`, `P71`/`P72` copies match.
  - `--functions`: C functions grouped by name with digits -> `#`; min similarity of the copies to the first (1.00 = identical after digit normalisation); recoverable bytes = linked copies minus the largest, from a linker map (`CH_<name>` areas) or `fw/bank_layout.tsv` slots.
  - `--asm DIR`: compiled functions identical after symbol digits -> `#` (object-level clones).
- Scope: tracked `fw/` (sdk, rtdfw, our dirs), `scripts/`, `tools/`, `tests/`, `dev.py`. Skipped: `fw/sdk-parked`, generated files (`*_gen*`, `set_table.c`, `fw/log/sync.c`, `bank_layout.tsv`, regs), `fw/sdk/Panel`, other-chip `Pcb`/`Project`/`Common` defaults, gamma / HDCP key / font tables.
- HDCP removed Dan 2026-11-23: restore = revert d14689a6, see #44; the DP Rx1 HDCP 1.4 checks are gated out under `_AWTO_HDCP` (proof: `scripts/hdcp_off_equiv.py`).
- Sizes: map of 30b070a0 (unit-3 image, `AWT26110003-30b070a0-be.map`, exact `CH_` sizes). `bank_layout.tsv` slots are sticky (still list pre-#292 Rx3 sizes), not used for sizes here.
- Drift: `git log -L:<fn>:<file>` per copy, `git log` over the per-port file pairs.
- Estimates marked `est` are line-share x function size, not measured.

## Result in numbers
- C line clones (min 10 lines, digit-normalised): 465 classes, 16.7 k redundant lines; dominated by SDK source that is not linked or is a header twin (see "Not worth merging").
- Function families with >= 2 linked copies: 108 (most are 15-19 B Rx2/Rx3 entry stubs left by #292); recoverable flash from the merge candidates below about 17 KB of 517 KB banked (3 %).
- Our own fw (`fw/awto osd input log diag settings timer ddcci keys audio nvram`): 8 classes of 5+ identical lines, 53 redundant lines in total. Already clean (#233 items merged: `osd_screen.c`, `AwtoDdcReply`).
- Host: 568 py files; 194 `say`/`log` definitions; 48 `repo_root` definitions; 71 scripts referenced nowhere, 68 more only from docs.

## Ranked merge candidates
Flash = recoverable bytes (measured copies minus the largest unless `est`). Risk: ISR = runs in an interrupt (EXINT0/1, WDINT), timing = timing-critical path.

| # | candidate | dup lines x copies | flash | drift found | difficulty | ISR / timing | bank | issue |
|---|---|---|---|---|---|---|---|---|
| 1 | `ScalerSyncTMDSRx2/3Hdmi*` (5 functions, `ScalerCommonSync.c`) | 373 x 2 (6 in source) | 1535 B | none since import | low (identical after digit norm) | main loop | 2 | #293 |
| 2 | `ScalerAudioD2/D3` HDMI audio (10 functions, `RL6449_Series_Audio.c` + `ScalerAudio_SeptPhy.c`) | 250 x 2 | 1896 B | none | low-medium (D2 split over two files) | main loop + timer event | 4, 10 | #294 |
| 3 | `RTDFactory*` per-slot / Left-Right handlers | 515 (24 families) + 91 L/R pairs | 2.5-3.0 KB (overlap) | none | low | no | 1, 5, 10 | comment on #121 (factory menu) |
| 4 | `ScalerDisplayDPTx1TP1/TP2Lane0..3Adjust` | 260 x 4 lanes | ~1.6 KB (tool bound 1839) | none | medium (per-lane state bits -> byte fields) | link training, main loop | 9 | #295 |
| 5 | `ScalerFlashWREN` / `WRDis` per-chip blocks | 3270-line function, 48 distinct bodies in 77 `case _FLASH_` labels | est 3-4 KB of 7.5 KB | none | medium (table, exhaustive host proof) | flash write path (CPU halts) | 5 | #296 |
| 6 | `ScalerPowerGroupD0..D3PowerCut/Isolation` | 37 x 4 | 612 B (before table cost) | none | low | power sequencing | 9 | #297 |
| 7 | `ScalerGDIPhyRx2/Rx3 Power/PowerProc/Z0Switch` | 337 x 2 | done: map -186 B (858 -> 672), image -139 B, XDATA +3 B | real: `ABC0` flag-clear differs Rx2 vs Rx3, kept per port (constant, as the Dahua firmware) | medium | impedance at hot plug | 9 | #298, `scripts/gdiphy_equiv.py` |
| 8 | `ScalerDpRx1Tp1/Tp2Check_EXINT0` lane blocks (7 per function, 4 distinct) | 7 x 52 lines per function | est 3.5 KB of 10 KB | none | high | ISR, link training | 7 | #299 |
| 9 | ISR / main twins of DpRx1 (`DFECheck`, `AdjustLaneFLDBand`, ...) | 15 pairs | 1.1 KB (up to 5.0 KB) | none | high (non-reentrant) | ISR, #281 | 2, 7 | #300 |
| 10 | Own fw: get-VCP reply builder x4, T2 snapshot x3, mirrored rect x2 | 4-12 lines x 2-4 | est < 200 B | none | trivial | T2 snapshot is ISR-safe by `EA` | C, 1 | #301 |
| 11 | Script logger `say`/`log` x194 | ~1100 lines | host | 35 without `mkdir`, 24 non-ISO stamps in scripts | low | no | host | #302 |
| 12 | `repo_root` / `ROOT` x367 | ~900 lines | host | 93 ignore `AWTO_DDC_REPO` | low | no | host | #303 |
| 13 | Orphan scripts (71 + 68) | 297 KB | host | n/a | triage | no | host | #304 |
| 14 | Dead per-port source copies (9.8 k lines of unlinked bodies) | 9.8 k lines | 0 | n/a | low | no | n/a | #305 |

Order = flash recovered per unit of risk: 1, 2, 3 first (identical bodies, main loop), then 4-7, then ISR work (8, 9) last.

## Per-port / per-instance pairs (hunk classes)
Normalisation: digits -> `@`; hunks classed cosmetic (name / register page / macro twin) / ifdef / real drift / port state.

- Sync `ScalerSyncTMDSRx2` vs `Rx3` (`ScalerCommonSync.c`), 5 functions: 0 hunks after normalisation = cosmetic only. Linked sizes equal (564 / 301 / 241 / 220 / 209 B). Rx0, Rx1, Rx4, Rx5 copies (4 x 373 lines) are compiled out.
- Audio `D2` vs `D3`: 10 functions, 0 hunks. `D1` is the DP audio path (different registers, 57 diff lines in `DigitalDetectProc`): not a merge partner. `D0`, `D4`, `D5` copies compiled out.
- GDIPhy `Rx2` vs `Rx3`:
  - `Power`, `PowerProc`: page `P7B`/`P7C`, `P2D`/`P2E`, DDC2/DDC3, MHL RX2/RX3 macros = cosmetic.
  - `Z0Switch` real drift at 2 sites: `P71_A9_TMDS_ABC0` writes `~(B7|B6|B5|B2), (B6|B5)` vs `P72_A9_TMDS_ABC0` `~(B7|B6|B5), (B7|B6|B5)`. Vendor original (import db7cee7e), not our edit; which value is right is open.
  - `Rx1` differs (DP-capable, `_D1_DP_Z0_IMPEDANCE_OPTION` branches): not a partner.
- DPTx1 `TP1Lane0..3Adjust`: identical after digit norm (38 lines each); `TP2Lane0..3Adjust` identical (27 lines each); TP1 vs TP2 share the shape only (19 diff lines). Linked sizes differ (317 / 379 / 321 / 371 B) because each lane has its own state bits. `DPTx2` copy of the whole file part (24 functions) is not linked.
- DpRx1 `Tp1Check` / `Tp2Check` lane blocks (`switch(g_ucDpRx1LaneCount)` cases 4 / 2 / 1 lanes): block similarity after digit norm lane3 = lane1 = 1.00, lane2 ~ lane0 0.96, 2-lane blocks equal the 4-lane ones, 1-lane block 0.80-0.93.
- DpRx1 ISR twins (`_EXINT0`, `_WDINT` vs main): `DFECheck` 11 diff lines (link rate / lane count read from DPCD vs cached globals, debug strings), `AdjustLaneFLDBand` 3 diff lines (local), `SetDFEInitial` 40, `RebuildPhy` vs `_WDINT` 323 (different function).
- PowerGroup `D0..D3`: `PowerCut` x4 and `Isolation` x4 equal after digit norm (only register / bit names).
- DDC channels: `fw/ddcci` already array-driven (`tAwtoIicBase[ucE]`, one handler per engine loop); no per-channel copy left.
- HPD / CEC: TMDS HPD shared in #292; one CEC port; DP HPD single. Nothing to merge.
- MHL Rx2/Rx3, DPRx0: parked (`fw/sdk-parked`), no linked pair.
- `tEDID_TABLE_D2/D3` (256 B each) differed by the port tag: D3 is now the D2 table + 3 patch pairs (`awto_edid_hdmi_d3.h`, #317).
- Tcon0..13: 14 files x 86 lines, 0 bytes linked.

## Drift found in git history
- TMDS Rx2/Rx3 before #292: 3 commits touched Rx2 only (`b37825f3`, `be01411d` #216 colour-depth wait; `ce27afe4` #256 2.9 ms unscrambled-source block); 20 of 23 commits touching the pair edited both files. #292 removes this class.
- Sync / audio / DPTx lane / PowerGroup pairs: no one-sided commit since the SDK import (`db7cee7e`); edits since import hit the pair together (#281 volatile / delay-counter passes) or not at all.
- GDIPhy Z0Switch Rx2 vs Rx3: see above, present in the import (vendor).
- Host `say` / `log` copies: 35 lack `LOG.parent.mkdir` (crash when `tmp/logs` is missing), 24 lack `flush=True`; script timestamps: 19 x `%H:%M:%S`, 5 x `%Y-%m-%dT%H:%M:%S%z` (no colon in the offset) against the ISO 8601 rule.
- Host `ROOT`: 93 files use `Path(__file__).resolve().parents[1]` without `AWTO_DDC_REPO` (3-tier rule: `$AWTO_DDC_REPO` -> git -> file).

## Not worth merging (reviewed)
- `RL6449_Series_McuCommonInclude.h` / `McuInterface.h` (345 identical lines), `ScalerCommonSync{Include,Interface}.h`, `ScalerCommonReg{Common,}Include.h`: SDK header twins, zero flash; Realtek's include scheme needs both.
- `ScalerCommonNVRam.c` flash table repeats other than WREN (2.6 k dup lines are the per-chip blocks of #5), `SysSource.c` / `ScalerPLL.c` / `ScalerCommonTimerFunction.c` repeated state-machine blocks inside one function: same-function, state specific.
- `tLUTGAMMA_18/20/22/24` (4 x 6156 B, distinct data) behind `_AWTO_GAMMA_ALL` (Dan: all kept).
- `ScalerTimerCancelTimerEvent` vs `_EXINT0` (43 instr, intentional ISR twin, 70 B).
- Our fw: `testcmd.c` asm shape variants (`AwtoOplWordNop*`, test only), `AwtoOsd*Lines` (prototype + body counted twice by the tool).

## Method for each merge (from #283)
- Prove equivalence: build-time check header like `RL6449_Series_TMDSRxCheck.h` (register / token equality per port), object diff where the source is unchanged, sim + `./dev.py san`, hardware on the `test` unit (unit 3) only.
- Stats table before / after: `./dev.py stats` (flash common / banked, IRAM, XDATA, stack main / nest, cycles per pass, busy %).
- Port with no hardware (D3, DPTx2): literal-branch proof like #292 plus the sim.

## Tool re-run
- `python3 scripts/clone_scan.py --min-lines 10 --norm --lang c fw --tsv tmp/logs/c_norm.tsv`
- `python3 scripts/clone_scan.py --functions --layout <map> fw --tsv tmp/logs/fam.tsv`
- `python3 scripts/clone_scan.py --asm tmp/sdcc-port/asm --tsv tmp/logs/asm.tsv`
- `python3 scripts/clone_scan.py --lang py --min-lines 6 scripts tools tests dev.py`
