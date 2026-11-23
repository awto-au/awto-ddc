# Sticky flash layout (#12)

Goal: a small source edit rewrites few 4 KiB flash sectors (I2C flashing ~1.7-2.5 s per sector).

## Why a normal rebuild rewrites ~all sectors
- Legacy packing = first fit in call-graph order; any size change shifts every later chunk in the bank.
- Stubs (`__bs_<fn>`: fn address + bank) sit in common and embed target addresses; common is copied into every bank.
- sdld lays out areas back to back in rel order: one grown function moves everything after it.

## Design (`--layout fw/bank_layout.tsv`, default off)
- One linker area per chunk (`CH<fn|const>`) and per stub (`ST<fn>`), each pinned with `-a<area>=<addr>` to a slot.
- `fw/bank_layout.tsv`: `kind name region offset slot` (kind fn|const|stub; region C = common, n = bank n). Committed.
- Slot = size + 4 + size/32, rounded to 4 B. Gaps stay 0xFF in the image (ihx writes no bytes there).
- Next build, per chunk:
  - fits its slot: same address, bytes only change if the code changed
  - grown: extends into free space after its slot; else best-fit hole in its bank; else another bank (re-home,
    logged "pass A"); a fragmented bank is compacted (only that bank)
  - new: bank where its module already lives; stub: next free 8 B in common
  - gone: slot becomes a hole
- Order within a region at creation: consts, then module, then name (not size).
- Creation (no/empty file): legacy packing with a per-bank fill limit (start 0.80, +0.01 until it fits), then slots.
- Hot helpers and const placement rules are decided once at creation (rows C / bank) and reused; const rules
  (single user bank, escaping address -> common) still run every build.
- Residual areas (vectors, HOME/GSINIT, library, crt, XINIT) stay contiguous after 0x53; `#resid_end` is
  reserved for them, chunk slots in common start there. fw_build fails if they outgrow it.
- fw_build checks every pinned area against the map (names are cut to 32 chars there: compared per prefix).

## Use
- Create/refresh: `AWTO_SDCC_BE=1 AWTO_SDCC_BIN=... fw_build.py --serial S --layout fw/bank_layout.tsv`
- Delete the file (or `--layout` a fresh path) to re-pack from scratch; commit the new file with the code change.
- The layout file changes with the build: commit it together with the source that caused the rows to move.
- Measure: `scripts/flash_layout_measure.py` (old vs new sectors per edit type).

## Limits
- Consts are only reachable from their own bank (movc without bank switch), so data cannot move to a separate
  data bank; stability comes from fixed slots.
- XDATA/IRAM layout is still linker order: an edit that adds/removes a global variable shifts later variables and
  rewrites every code sector that addresses them (not covered here).
- Common holds ~1100 stubs x 8 B (`STUB_SIZE`: mov r0,#bank 2 + mov dptr,#fn 3 + ljmp 3); common edits cost one sector write per bank.
- Bank 14 (0xE0000) is the 15th code bank (`fw/rl6449_memory.toml` code_banks 15): its own 0x5000 common copy + 44 KiB banked; image 240 sectors once it holds code.

## Measured (2026-11-06, base 9be09d6 + this change, unit-3 build, BE compiler)
Image sectors (4 KiB) changed by one small edit vs its own unedited build (`flash_layout_measure.py`; legacy image
12 banks = 192 sectors, sticky image 14 banks = 224 sectors):

| edit | legacy | sticky |
|---|---|---|
| constant in panel header (`_PANEL_DH_START` 48 -> 50) | 1 | 1 |
| one extra call in an OSD fn (`OsdFuncEnableOsd`) | 32 (24 common) | 1 |
| one extra call in a Kernel scaler fn (`ScalerGlobalCrystalClkSel`) | 167 (60 common) | 1 |
| one extra call in `main` (common chunk) | 154 (60 common) | 14 (1 common sector x 14 banks) |

- Unchanged rebuild with the committed layout: 0 sectors; layout file unchanged (idempotent).
- Common high-water: legacy 0x4b0b of 0x5000; sticky 0x431b (slots 14107/17408 B + residual 0xb4e of 0xc00).
- Creation fill: 0.89 per bank for banks 0-9; banks 10-13 hold the rest (4-30 KiB free each).
- fw_stack total: 100 B sticky vs 104 B legacy (limit 128). Warning gate passes.
- ucsim smoke (`fw_sim.py`): sticky and legacy images stall at the same place (boot stage 4).

## Common region (metric, numbers only; `./dev.py stats`, `tmp/fw/<stem>.gates.json` "common", `scripts/common_metrics.py`)
- Common = [0, 0x5000) = 20480 B, copied into every bank image. Code lives there because it is always mapped: ISRs, timer / wait primitives, anything called from many banks, and the 8-byte cross-bank stubs.
- Measured 2026-11-23, main 97417f31, unit-3 image, linker map + `fw/bank_layout.tsv`:

| item | bytes | count |
|---|---|---|
| areas used / free (plain sum of the linked areas) | 17585 / 2895 | |
| slots used / free (what fails the link) | 20420 / 60 | |
| stubs (area sum; slots identical, 8 B each) | 8856 | 1107 |
| function + const chunks (area sum) | 6598 | 127 |
| chunk slots (size + 4 + size/32) | 8208 | 127 |
| residual areas (area sum) | 2131 | |
| residual reserved (`#resid_end`) | 3356 | |
| of which CSEG at 0x135 | 1786 | |

- Free reconciliation: 2895 = chunk slot padding 1610 + residual reserve not linked 1225 + slot free 60.
- CSEG = runtime library, not our code: `__gptrget/put` (+ `_isr` clones), `awto_bank` trampoline (`__bs_call`, `__bs_ret`, return table), `___sdcc_external_startup`, `__div/mod/mul` (int, long), `memcpy`, `memset`, `abs`. Rest of residual: GSINIT* 170, XINIT 96, HOME 56, vectors 20, SSEG 128 (IRAM, not code).
- Top chunks: ScalerMDomainDHVtotalFinetune 645, ScalerMDomainDHtotalFinetune 520, AwtoDbgIsrCmd_EXINT1 471, AwtoWaitLog 361, ScalerTimerWaitForEvent 323, UserCommonNVRamGetSystemData 308, ScalerTimerPollingFlagProc 281, SysTimerIntProc2 233, AwtoWdtPoke 229, ScalerTimerDelayXms 213.
- Residual hole: CSEG ends 0x82F, XINIT is pinned at 0xCBC-0xD1C (`resid_end` 0xd1c): 1165 B free in every common copy. A lower `resid_end` (fw/rl6449_memory.toml) is accepted by the layout and moves no slot.
- Stub = one per banked function called from another bank / common or address-taken (not per call site): moving a function between banks changes the stub count of its callers.
