# Flash layout: tracked bank map + compact packing (#12, #44)

Status 2026-11-23 (Dan: the sticky-slot design is dropped). Before: fixed slots + `size + 4 + size/32` padding per chunk, so a
small edit rewrote few sectors; cost 48 KB of slot slack (22 KB padding + 26 KB from functions that shrank, never reclaimed).

## Design
- `fw/bank_map.tsv` (tracked): `kind name region` per fn / const (region C = common, n = bank n) + `#stubs N`. It records the bank
  decision (first-fit / hot-helper / const rules) so an edit does not reshuffle banks; it holds no offsets and no sizes.
- Every build packs each region back to back: order stubs / fixed consts, consts, then module, then name; size only, no padding, no holes.
  Output `tmp/sdcc-port/bank_layout.new.tsv` (`kind name region offset size`), frozen as `tmp/fw/<stem>.bank_layout.tsv` beside the
  image; gates, stats and the common-region metric read that file. Not tracked.
- One linker area per chunk (`CH<fn|const>`) and per stub (`ST<fn>`), each pinned with `-a<area>=<addr>` to its packed address.
- New chunk: the bank where most of its module already lives. A non-fixed fn whose bank is full goes to the bank with most room (re-home).
- Residual areas (vectors, HOME/GSINIT, library, crt, XINIT) stay contiguous after 0x53; `#resid_end` is reserved for them, chunk rows in
  common start there. fw_build fails if they outgrow it. fw_build checks every pinned area against the map (names cut to 32 chars).
- `fw_build.py --layout ''` = no map, legacy first-fit packing without pins (not used by the shipped build).
- Creating the map from scratch (no file): first fit at fill limit 0.80 + 1 %, optional `--cluster`; with exact sizes it still fails when
  CONST lands in a bank the code packing filled (`no room for _RTDFactoryOsdDispNumber in bank 12`): the shipped map is carried forward.

## Cost of an edit (replaces the sticky claim; numbers in "Measured")
- An edit that changes the size of a chunk moves every later chunk of its bank: the bank is rewritten from that chunk on.
- A common edit moves the common chunks and stubs, which are copied into every bank: 14 x sectors touched.
- XDATA layout is separate (`fw/xdata_layout.tsv`, `docs/flash-sector-churn.md`) and unchanged by this design.

## Limits
- Consts are only reachable from their own bank (movc without bank switch), so data cannot move to a separate data bank.
- Common holds ~1100 stubs x 8 B (`STUB_SIZE`: mov r0,#bank 2 + mov dptr,#fn 3 + ljmp 3).
- Bank 14 (0xE0000) is the 15th code bank (`fw/rl6449_memory.toml` code_banks 15): its own 0x5000 common copy + 44 KiB banked.

## Measured (2026-11-23, unit-3 build, `scripts/flash_layout_measure.py`)
Image sectors (4 KiB, of 224) changed by one small edit vs the unedited build of the same tree. Sticky = origin/main ea533d43 (slots), compact = this design.

| edit | sticky | compact | compact common sectors (x14 banks) |
|---|---|---|---|
| constant in panel header (`_PANEL_DH_START` 48 -> 50) | 2 | 2 | 0 |
| one extra call in an OSD fn (`OsdFuncEnableOsd`) | 1 | 67 | 56 |
| one extra call in a Kernel scaler fn (`ScalerGlobalCrystalClkSel`) | 3 | 66 | 56 |
| one extra call in `main` (`AwtoDiagInit`, common chunk) | 14 | 155 | 56 |

- Why: a grown chunk shifts every later chunk of its bank, the stubs (common, copied into every bank) hold those addresses: 4 common sectors x 14 banks.
- Flash time at 0.126 s per sector (1 MHz HDMI DDC) / 0.53 s per sector (100 kHz DP AUX, `docs/flash-sector-churn.md`): sticky 0.13-1.8 s / 0.5-7.4 s; compact 0.25-19.5 s / 1.1-82 s; full 224 sectors 28 s / 119 s.
- Free bytes: banked 27,552 B in fragments (sticky slots) -> 90,231 B packed tail space (banks 0-13; bank 14 is unused: 45,056 B more); common 140 -> 1,665 B.

## Common region (metric, numbers only; `./dev.py stats`, `tmp/fw/<stem>.gates.json` "common", `scripts/common_metrics.py`)
- Common = [0, 0x5000) = 20480 B, copied into every bank image. Code lives there because it is always mapped: ISRs, timer / wait primitives, anything called from many banks, and the 8-byte cross-bank stubs.
- Measured 2026-11-23, main d95b5add + compact layout (#44), unit-1 image, linker map + the image's `bank_layout.tsv`:

| item | bytes | count |
|---|---|---|
| areas used / free (plain sum of the linked areas) | 17590 / 2890 | |
| rows used / free (what fails the link) | 18815 / 1665 | |
| stubs (area sum; slots identical, 8 B each) | 8856 | 1107 |
| function + const chunks (area sum = rows) | 6603 | 127 |
| residual areas (area sum) | 2131 | |
| residual reserved (`#resid_end`) | 3356 | |
| of which CSEG at 0x135 | 1786 | |

- Free reconciliation: 2890 = residual reserve not linked 1225 + row free 1665. (Sticky slots before: 17585 / 2895 areas, 20420 / 60 slots, chunk padding 1610 B.)
- CSEG = runtime library, not our code: `__gptrget/put` (+ `_isr` clones), `awto_bank` trampoline (`__bs_call`, `__bs_ret`, return table), `___sdcc_external_startup`, `__div/mod/mul` (int, long), `memcpy`, `memset`, `abs`. Rest of residual: GSINIT* 170, XINIT 96, HOME 56, vectors 20, SSEG 128 (IRAM, not code).
- Top chunks: ScalerMDomainDHVtotalFinetune 645, ScalerMDomainDHtotalFinetune 520, AwtoDbgIsrCmd_EXINT1 471, AwtoWaitLog 361, ScalerTimerWaitForEvent 323, UserCommonNVRamGetSystemData 308, ScalerTimerPollingFlagProc 281, SysTimerIntProc2 233, AwtoWdtPoke 229, ScalerTimerDelayXms 213.
- Residual hole: CSEG ends 0x82F, XINIT is pinned at 0xCBC-0xD1C (`resid_end` 0xd1c): 1165 B free in every common copy. A lower `resid_end` (fw/rl6449_memory.toml) is accepted by the layout and moves no slot.
- Stub = one per banked function called from another bank / common or address-taken (not per call site): moving a function between banks changes the stub count of its callers.

## Common shrink (awto-ddc #333)
- `common_end` 0x2800 (was 0x5000), `resid_end` 0x890; offsets are build output (compact packing), the tracked `fw/bank_map.tsv` keeps the bank decision.
- Stubs of fns called only from banks are emitted per caller bank (`--local-stubs`, default on; area `ST<bank>_<fn>`, symbol `__bs<fn>_b<bank>`); only stubs with a common / ISR caller stay in common. Address-taken fns (pointer table in a CONST of the same bank) qualify, address-taken from code does not.
- CONST handed only to `--ptr-safe` common readers (default `_AwtoPutStr`) or to one banked callee (`--const-to-callee`, default on) lives in the user / callee bank.
- `--inline-consts CUT` (off): emits a CONST after each user fn; fw_link_check reports false findings (227 at cut 64) until it knows each chunk's code size.
- Audit: `scripts/common_audit.py` (common chunk classes, stub callers by bank, const classes, helper duplication).
