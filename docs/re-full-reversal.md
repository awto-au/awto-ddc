# Full reversal of the vendor firmware (multi-agent)

Target: JXC 4K monitor, Realtek RTD2795T / RL6449, Keil C51, 7 x 64 KiB banks, Ghidra `8051:BE:16:default`, one program per bank.
Tracking: awto-ddc#1 (umbrella) and the "Full reversal" issue (see bottom). Confidence tags: awto-dan `docs/embedded/reversing/README.md`.

## Phases
- Phase 1 (done, this doc): SDK types + typed globals imported into Ghidra, counts, bank-agent instructions.
- Phase 2: 7 bank agents (no Ghidra) name functions from the exports + SDK source.
- Phase 3 (done, section below): export fix, bit-field order, merge + verification, globals, stats.

## Pipeline (scripts / data)
| step | file |
|---|---|
| import/regen (labels, names, types, exports) | `scripts/ghidra_re.py import\|regen <bank\|all>` |
| register labels (9209) | `scripts/regdb_ghidra_labels.py` |
| `[lib]` names (exact OMF signature) | `scripts/ghidra_merge_lib_names.py` |
| `[auto-sdk]` names (register fingerprint) | `scripts/ghidra_match_sdk.py` |
| SDK types -> `re/jxc-4k/sdk_types.tsv` | `scripts/ghidra_sdk_types.py` |
| SDK globals -> `re/jxc-4k/ghidra_globals.tsv` (+ `ghidra_globals_hand.tsv`) | `scripts/ghidra_globals_map.py` |
| apply types + typed labels | `re/ghidra/ApplySdkTypes.java` (run by `ghidra_re.py` after ApplyNames) |
| progress table | `scripts/ghidra_re_stats.py` |
| merge (newest row wins, common area, thunks) | `scripts/ghidra_names_merge.py` -> `tmp/names_merged_bank<N>.tsv` |
| verification | `scripts/ghidra_verify_names.py` -> `re/jxc-4k/phase2_verification.tsv` (+ `phase2_verification_manual.tsv`) |
- Exports per bank: `~/vendors/realtek/analysis/jxc-4k/bank<N>/{decompiled_named.c,disassembly.asm,regwrites.tsv,regreads.tsv}`.
- Names per bank: `re/jxc-4k/ghidra_names_bank<N>.tsv` (source of truth).

## Types (task 1)
- Source: `sdcc -E` of all 232 C files of `STD_FW_1P.Uv2` (target `RL6449_Project`, same flags as the port build), headers under `tmp/sdcc-port/src`, unioned by name.
- Result: 464 types under `/SDK` (368 enums, 96 struct/union; every `Struct*` typedef of the build). All 7 programs get them.
- Layout model = Keil C51 data layout: awto-sdcc `docs/keil-c51.md` ("Data layout").
- Bit fields are NOT split: consecutive bit fields pack into one `u8`/`u16` member `bf_<first field>`, comment lists the fields.
  - Bit order: Keil C51 packs first-declared fields from bit 0 (LSB-first), confirmed by the phase-3 vendor checks and later Keil probes. `StructPowerInfoType` therefore has `b4PowerAction[3:0]` and `b4PowerStatus[7:4]`; see `scripts/ghidra_sdk_types.py` and `re/jxc-4k/sdk_types.tsv`.
- Caveat: struct bodies follow OUR port config (`#if` of the RL6449 project defaults); the vendor build can have extra/missing fields. Sizes are only checked where the anchored address map agrees.
- Enums are datatypes only; no equates applied to constants yet.
- Applying a type to a variable: a `var:<TypeName>` row (column 3) in a names TSV, or a row in `ghidra_globals_hand.tsv` (`type` column: `u8 s8 u16 s16 u32 s32 ptr3 f32`, a type name from `sdk_types.tsv`, `[n]` suffix for arrays).
- ApplySdkTypes creates an uninitialised block `XRAM_SDK` at `EXTMEM:d700-f6ff` (data units need memory behind them); scaler registers live below it.

## Globals (task 2)
- Inventory: `_name::` in XSEG/DSEG/BSEG of `tmp/sdcc-port/asm` -> 196 XDATA + 10 DATA + 30 BIT globals, sizes from `.ds`.
- Anchors: vendor functions with an SDK identity:
  - names `[lib]` (exact signature), `[auto-sdk]` (register fingerprint), weight 1.0;
  - `[weak]`: `tmp/match_bank<N>.tsv` candidates score >= 0.30, margin >= 0.05, weight 0.5;
  - `[cmatch]`: constants + register fingerprint (weighted Jaccard of 8/16-bit immediates and register addresses, score >= 0.30, margin >= 0.10, weight 0.7); top-1 correct on 77/81 (95%) of functions that already had an `[lib]`/`[auto-sdk]` name.
- Pair evidence: SDK `mov dptr,#_g (+off)` vs vendor `MOV DPTR,#imm` (imm in 0xD700-0xF6FF). Candidate base = imm - off with all offsets of g present; vote = weight / #candidates.
- Accept: score >= 1.0, >= 2x runner-up, >= 2 supporting functions (or one `[lib]` pair with a single candidate); overlaps resolved by score; up to 8 rounds with explain-away (accepted globals consume their immediates).
- Only 117 anchor pairs (of ~250 named/matched functions) touch XDATA globals at all -> yield is low.
- Not done on purpose: layout extrapolation inside a module. Keil's `?XD?<module>` order is NOT declaration order.
  - Evidence: Keil map `RL6432_Beacon_Project.m51` (SDK mirror `Output/`): `ScalerMDomain` segment `E1BB..E1F4`: `g_uDclkSpreadRange E1BB, g_uDclkSpreadSpeed E1BC, g_ulDClkFreq E1BD, g_stMDomainFRCFIFOData E1C1, g_usDVFreq E1C7, g_stMDomainInfo E1C9, g_stMDomainInputData E1CC, g_stMDomainOutputData E1E1`; source order differs.
  - Segments are placed largest-first, gap-filling around absolute blocks (E000-E0FF, E280-E37F ...); the vendor module sizes (custom OSD/User modules) are unknown.
- Applied (12, all banks): see `re/jxc-4k/ghidra_globals.tsv`. Examples: `g_stColorInfo` e231 (10 functions), `g_stPowerInfo` e23a (4), `g_stTMDSRx2CtrlInfo` e187 / `Rx3` e1a1 (9 each), `g_stInputTimingData` e07c (5), `g_stPortCableStatus` dbf3 (4).
- NOT found: `g_stMDomainInputData`, `g_stOsdInfo`, `g_stSystemData`, `g_stModeInfo`, `g_usTimerCounter` (DATA space, not mapped: direct-address operands are not voted), `g_stMDomainOutputData`. Votes for them are split between candidates; one-function pairs disagree (bank2 `0xbfc4` vs bank5 `0x3787` both `ScalerMemoryUpdateIVS2DVSLineDelay` give different bases).
- To raise yield (phase 2/3): bank agents that identify a function by SDK name add `var:<Type>` rows for the globals it touches (`ghidra_globals_hand.tsv` is the shared home); the voting then gets more `[re-agent]` anchors if the map script is extended to read `[re-agent]` names (not done).
- Vendor build = JXC custom User/OSD modules (RTD2014* layout differs from the SDK `Beacon`/`RTD2014` source we compile), so User-module globals (`g_stOsdInfo`, `g_stOSDUserData`, `g_stSystemData` ...) have no anchors beyond name-equivalent hand rows.

## Spot-check (task 3)
- `scripts/ghidra_re.py regen all`: exit 0 on all 7 banks (log `tmp/logs/re_regen_bank<N>.log`); 464 types + 12 typed labels each.
- `backlight_group_on` (bank1): unchanged, it only touches port pins and register labels (nothing typed):
  ```
  void backlight_group_on(void) { PORT97_PIN_REG = 1; PORTA0_PIN_REG = 1; PORT85_PIN_REG = 1; PORT84_PIN_REG = 1;
    func_0x0b5b(); func_0x0b61(); FUN_CODE_2040(); return; }
  ```
- `ScalerDisplayDPTx1VideoStreamOutput` (bank1 0x565c): only a declaration changed (`undefined1 *` -> `undefined *`). Its XDATA hits (0xdbbc-0xdbc1, 0xdbe7, 0xdbeb) are Keil overlay locals, not globals; `g_stDisplayDPTx1*` (0xe0fb..) not anchored.
- OSD function `osd_compose_glyph_grid_map` (bank1 0xb0f4): unchanged (register/OSD-port code).
- Where the types do show (typed globals used): before -> after
  ```
  - if ((DAT_EXTMEM_e23a >> 4 == 3) || (DAT_EXTMEM_e23a >> 4 == 1)) {
  + if ((g_stPowerInfo.bf_b4PowerAction >> 4 == 3) || (g_stPowerInfo.bf_b4PowerAction >> 4 == 1)) {
  - DAT_EXTMEM_e231 = DAT_EXTMEM_e231 & 0xf8;               (bank1 0x700c)
  + g_stColorInfo.bf_b3ColorSpace = g_stColorInfo.bf_b3ColorSpace & 0xf8;
  + g_stPortCableStatus.bf_b1D5CableDetect = 0;
  - undefined1 FUN_CODE_6e03(void) { return uEXTMEMdbf3; }
  + byte FUN_CODE_6e03(void) { return g_stPortCableStatus.bf_b1A0CableDetect; }
  ```
- Summary: readability gain is confined to the 12 anchored globals; the three named spot-check functions do not use any.

## Counts (`scripts/ghidra_re_stats.py`, 2026-11-06)
- Total = function headers in `decompiled_named.c` (thunks and `FUN_` included; banks 0-6 each carry the common area 0x0000-0x28C5, identical bytes, so it is counted 7x).
| bank | total | named | [fw] hand | [guess] | [lib] | [auto-sdk] | typed globals |
|---|---|---|---|---|---|---|---|
| 0 | 633 | 13 | 6 | 6 | 1 | 0 | 12 |
| 1 | 1158 | 36 | 11 | 0 | 7 | 18 | 12 |
| 2 | 936 | 25 | 3 | 0 | 6 | 16 | 12 |
| 3 | 1115 | 3 | 0 | 0 | 3 | 0 | 12 |
| 4 | 1243 | 22 | 0 | 0 | 3 | 19 | 12 |
| 5 | 1025 | 43 | 3 | 1 | 10 | 29 | 12 |
| 6 | 388 | 101 | 19 | 7 | 69 | 5 | 12 |
| all | 6498 | 243 | 42 | 14 | 99 | 87 | 12 (same XDATA map in every bank) |
- 1 extra `[?]` row in bank 6. Not all rows of the TSVs are functions (vars/labels excluded above).

## PHASE 2 instructions for the 7 bank agents
Hard rules
- Do NOT run Ghidra/analyzeHeadless. Read-only on: exports, `tmp/sdcc-port/src` (+ `tmp/sdcc-port/asm`), the raw SDK `/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST`, `re/jxc-4k/sdk_types.tsv`, `ghidra_globals.tsv`.
- Write ONLY `re/jxc-4k/ghidra_names_bank<N>.tsv` (your bank). Append rows; never edit/delete existing rows of any status.
- No fw/, dev.py, tmp/sdcc-port, tmp/fw. No monitor/I2C access. Logs `./tmp/logs/`, scratch `./tmp/`. No `sleep`/`timeout`.
- Common area (code < 0x28C6, identical in all banks): only the bank 0 agent names it; other agents skip addresses < 0x28C6.
- One name per address and one address per name within a bank. Names: SDK function name when the SDK has it (`ScalerXxx`), else `snake_case` role name; never reuse a `[lib]`/`[auto-sdk]` name.
Row format (tab separated, 6 columns; columns 1-5 as the existing files)
```
CODE:<addr hex>\t<name>\tfunc\t<one-line comment: what, evidence (regs/consts/callees/SDK file)>\t[re-agent]\t<confidence>
```
- `confidence` = `high` (SDK function identified by constants + registers + callees, or exact behaviour), `med` (role clear, name guessed), `low` (hint only).
- Globals/labels: `EXTMEM:<addr>\t<name>\tvar:<TypeName or u8/u16/...>\t<comment>\t[re-agent]\t<confidence>`; use `g_` SDK names when the SDK declares the variable.
Method per function
1. Pick unnamed functions in `decompiled_named.c` (`FUN_CODE_xxxx`) from the leaves up (called by many, calling nothing unnamed).
2. Evidence in this order: register labels (`regwrites.tsv`/`regreads.tsv`: reg names, masks, constants), string/table constants, callees already named, call-site arguments, XDATA addresses against `ghidra_globals.tsv`.
3. Search the SDK for the same register/constant pattern: `grep -rn "<REG_NAME>\|<const>" tmp/sdcc-port/src`; compare the SDCC asm in `tmp/sdcc-port/asm` for control flow. Same family reference images are reference only.
4. Name only when the SDK match or behaviour is clear; otherwise skip (an unnamed function is better than a wrong name).
5. Keep comments terse (point form, max 3 lines, no measurements).
Deliverable per agent: appended rows + a line count in the bank section of the final report (rows added by confidence).
Phase 3 (caller): merge, `scripts/ghidra_re.py regen all`, `scripts/ghidra_re_stats.py`, optionally extend `ghidra_globals_map.py` to treat `[re-agent]` `high` names as anchors.

## PHASE 3 (merge, verification, 2026-11-06)
Export fix
- Ghidra flagged Keil helpers (13ed LMUL, 1478 ULDIV, 15ce LSTXDATA, 133e, thunks) non-returning and put `CALL_RETURN` overrides on the calls; decompile/disassembly stopped at the first LCALL.
- `re/ghidra/FixKeilReturns.java` (run by `ghidra_re.py import|fixret`): clears the flags/overrides on CALLs (JMP overrides from Shared Return Calls stay), disassembles fall-throughs, rebuilds bodies, disables the analyzer that re-flags them. Kept non-returning: CCASE/ICASE (inline tables).
- `ExportRegAccess.java`: `func_addr` = function whose intra-procedural flow reaches the insn (calls skipped), not the preceding entry.
- `re/ghidra/EnsureFunctions.java`: every `func` row becomes a real function entry (ApplyNames renamed the containing function otherwise), stale names of superseded rows are reset.
Merge rules (`ghidra_names_merge.py`)
- Newest row per address wins; `#` lines skipped; name `-` retracts (reset to default); `ghidra_names_phase3.tsv` applied last.
- CODE rows: own bank + bank-0 common area (< 0x28C6) in every bank. EXTMEM rows of all banks apply to every program (one XDATA map).
- `bcall_*` thunk names regenerated from the final target names.
Verification (`phase2_verification.tsv`)
- CONFIRMED = exact lib signature, SDK call graph both ways, register set, or hand-checked constants/sequence. PLAUSIBLE = agent reading or one weak signal: not a basis for firmware changes. REFUTED = contradicted.
- Firmware-relevant verdicts: bit-field order CONFIRMED; DDR2 PHY values = SDK 1200M branch 12/12 CONFIRMED; DDR2 power-up order, M-domain call order, M-domain globals (Keil map shift 0x1AD) CONFIRMED; AC-on `d2a0` head CONFIRMED, tail delays are vendor PCB macros; backlight pin-group "backlight" label PLAUSIBLE only (renamed `pcb_pin_group_*`), proven backlight enable = P9.2 FE2A active low.
Globals
- `ghidra_globals_map.py`: anchors = merged names, [re-agent]/[auto-sdk] weight 1.0 only when CONFIRMED (else 0.3); high-confidence [re-agent] `g_` rows named like an SDK XDATA global are fixed seeds (accepted first, consume immediates).
Counts: `scripts/ghidra_re_stats.py` (bank 3 excludes 0x28C6-0xA7FF; common area counted once per bank program).
