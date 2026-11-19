# Why a rebuild rewrote ~190 of 224 flash sectors (fixed: recs 1, 2)

Status: rec 1 + rec 2 implemented (section "Implemented" at the end); the analysis below is the state before.

Analysis only, no hardware (2026-11-19, Dan's question). Tool: `scripts/image_sector_diff.py OLD.bin NEW.bin [--grid]` (reads the `.map` beside each image). Background: `docs/flash-layout.md` (sticky code layout, #12), `docs/flash-registry.md` (manifest diff).

## Answer
- [measured] Code is already sticky: 0 code symbols moved in the clean pairs below; chunk slots in `fw/bank_layout.tsv` hold.
- [measured] The churn is the XDATA layout. Any change in the size of any module's XDATA (a new global, a grown array, a bigger overlay) shifts the address of hundreds of variables; every `MOV DPTR,#addr` (0x90 hh ll) and `ADD A,#lo(addr)` that touches one is a different byte in the image. About 190 sectors contain at least one such operand.
- Cause in the build: `scripts/fw_build.py split_xseg()` assigns module XSEG areas to the 4 XDATA holes first-fit, largest module first; sdld then concatenates the areas in `.rel` order. A size change moves modules between holes (deltas of +4221, -3232 seen) and shifts everything behind it. Nothing pins XDATA the way `bank_layout.tsv` pins code.
- [measured] Second, smaller cause: startup code in common sector 0 embeds XSEG1..4 lengths (`mov r1,#l_XSEG1` clear loops, `crt_xinit.asm`): every XDATA size change rewrites common sector 0 in all 14 banks (14 sectors) even with XDATA otherwise pinned.

## Image structure [measured]
- 0.896 MiB = 224 sectors = 14 banks x 64 KiB x 16 sectors. Per bank: common = first 5 sectors (0x0000-0x4FFF, `#common 0x5000`) copied into every bank, then bank code.
- A change confined to common costs 14 x (sectors touched); common is 5 x 14 = 70 sectors (31 % of the image is the same 20 KiB, 14 times).
- Tag/stamp: the `FW <tag>` string sits in 1 sector (0x85000, bank 8 sector 5). A tag-only rebuild changes that sector only (clk2 -> clk3: 2 sectors = tag + one 3-byte `lcall` insert in 0xAE000).
- No date / git hash in the image; no per-bank CRC; `FF72..FF75` hw CRC is read from the device, not stored. The manifest (`0xFD000`) is outside the image.
- Gamma 0xE0000-0xE2FFF, settings 0xFB000-0xFCFFF, manifest 0xFD000, spare 0xFE000 are outside the 224 image sectors.

## Pairs [measured: image_sector_diff.py, same-tree consecutive builds, serial AWT26110003, `tmp/fw` and agent worktrees `tmp/fw`]
- chg = sectors that differ; floor = still differ after masking address operands that moved with XDATA (all of XDATA frozen); pin = same with one fixed slot per module (only symbols whose offset inside their module run changed still move); data moved = data symbols with a new address.
- Source diffs not recovered (builds carry only a tag); the map names the variable that changed.

| pair | chg | common | data moved | floor | pin | what changed |
|---|---|---|---|---|---|---|
| clk4 -> clk5 | 191 | 70 | 407 | 2 | 6 | module `testcmd` variable +11 B |
| clk8 -> clk9 | 191 | 70 | 409 | 2 | 2 | new variable `g_usAwtoAstFrames` |
| clk9 -> clk10 | 151 | 56 | 163 | 3 | 3 | XDATA growth in one hole |
| clk5 -> clk6 | 191 | 70 | 451 | 19 | 20 | 14 = common sector 0 (l_XSEG), 5 real |
| sl2 -> sl3 | 187 | 70 | 379 | 18 | 21 | same pattern |
| t7 -> t6 | 185 | 70 | 357 | 7 | 7 | |
| clk2 -> clk3 | 2 | 0 | 0 | 2 | 2 | tag + one `lcall` |
| clk3 -> clk4 | 17 | 14 | 0 | 3 | 3 | common sector 4 (x14) + 3; XDATA unchanged so code stayed sticky |
| smb -> smi, pm1 -> m8 | 2 | 0 | 0 | 2 | 2 | XDATA unchanged |

- All 62 pairs scanned (`tmp/logs/pairs3.log`): 41 with >= 150 data symbols moved: mean 187 sectors changed (151-200). 21 with fewer: 0-117, median 3 (the pairs with 24-110 are large code edits).
- Of the 41, 11 are small source edits (floor <= 25): changed 151-192 (mean 188), floor 2-22, pin 2-36 (median 18).
- Pairs with floor ~100 (s1 -> s2, fta -> m9, kc*): real code removal or IRAM changes too (bit / direct addresses `c2 14` -> `c2 13`, `8c 3a` -> `8c 39` from DDOVL overlay moves); not small edits, floor includes IRAM drift (not modelled).
- floor / pin are lower bounds in two ways: the `x` mask (a lone byte whose change equals the low/high byte of a symbol move) can hide a real change; pin is bounded above by the same heuristic. Treat as +-5 sectors.

## Per-sector classes (script) [measured]
- X: only `MOV DPTR,#imm16` operands differ, old and new inside XDATA (variable moved): 33 of 191 in clk4 -> clk5.
- x: address immediates (`ADD A,#lo`, `MOV Rn,#hi`): 156.
- C: LJMP/LCALL operand = same code symbol moved: 0 in clean pairs (stubs / chunks pinned).
- R: real content change: 2 (the edit itself).
- Free-flash numbers (new image): 11 blank sectors, 187 KiB of 0xFF bytes in 896 KiB (10-14 KiB per bank, bank 13: 28 KiB; includes slot gaps).

## Not the cause [measured / checked]
- Code layout, module order, bank pinning, link order for code: already sticky (`bank_layout.tsv`, 1 sector per code edit, `docs/flash-layout.md`). Padding modules to 256 B / 4 KiB would cost flash and gain nothing: code symbols moved = 0 in the clean pairs.
- Build tag / date / git hash: 1 sector.
- CRC / manifest: not in the image.
- Const tables and strings (`.map` code symbols unchanged): no.

## Recommendations (ranked by gain / risk)
| # | change | gain | risk | needs Dan |
|---|---|---|---|---|
| 1 | Startup clear: clear the fixed XDATA hole bounds (from `fw/rl6449_memory.toml`), not `l_XSEG<k>` sizes in `crt_xinit.asm` / startup | removes the 14-sector common sector 0 rewrite on every XDATA size change (clk5 -> clk6: 19 -> 5) | low: clearing the full hole also clears the DDC RAM between holes if mis-bounded; clear per hole, skip E280/E480/E680 | no (startup cost: clear time, measure) |
| 2 | Pin XDATA like code: one area per module (`XSEG_<mod>`, as `split_xseg` already renames), `-a` per area from a committed `fw/xdata_layout.tsv` (module, hole, offset, slot); growth -> re-home to the free tail, only that module's references change; compaction = deliberate full-churn build | 191 -> 2-20 sectors for the clean pairs (table: pin column), 3-6 s per flash at 100 kHz DP AUX instead of 100 s | medium: free pool is the 700 B XDATA floor; re-homing leaves holes (fragmentation); `sync` module alone is 1042 B | yes (XDATA headroom policy, floor) |
| 3 | Same without a layout file (interim): `split_xseg` keeps each module in its previous hole (no size sort), places new/changed awto modules last in a hole | shifts only modules behind the change in one hole; [estimate, not simulated] about half the sectors | low | no |
| 4 | Uniform per-module slack instead of re-home | not recommended: 161 runs, 6398 B of XDATA; round to 4 B = +282 B, 8 B = +730 B (over the 700 B floor), +25 % = +1538 B | - | - |
| 5 | Keep volatile code out of common | an edit to a common chunk costs 14 x sectors touched; put awto main-loop chunks in a bank unless the call graph forces common | low | no |
| 6 | IRAM / DDOVL base drift (direct + bit operands) | secondary: shows in floor ~100 pairs, not measured separately | medium (overlay tool) | no |
- Not recommended: padding every module's code to 256 B / 4 KiB (code already pinned; costs the 11 blank sectors / 187 KiB free).
- Free flash for padding: in-image 11 blank sectors + 187 KiB 0xFF (inside slot gaps); outside the image 0xE3000-0xFAFFF = 24 sectors, but banks 14 / 15 cannot hold code (gamma at 0xE0000, no common copy there).

## Flash time [Dan, 2026-11-19; not re-measured]
- 100 kHz DP AUX: 190 sectors ~ 100 s+ = ~0.53 s per sector. 1 MHz HDMI DDC: 24 s = ~0.126 s per sector.
- Fixed costs not modelled (read gate, manifest, truth-check CRC over skipped runs: `docs/flash-registry.md` "Truth-check cost (to measure)").

| sectors written | 100 kHz DP AUX | 1 MHz HDMI DDC |
|---|---|---|
| 190 (today) | ~100 s | ~24 s |
| 20 (rec 2, worst clean pair) | ~11 s | ~2.5 s |
| 6 | ~3.2 s | ~0.76 s |
| 2 | ~1.1 s | ~0.25 s |

## Open
- Fragmentation: a module growing past the gaps (74-256 B; sync +100 B) evicts a neighbour or compacts; 76 sectors for sync +100 B. Needs more free XDATA.
- `l_XINIT` (init-data size) is an immediate in common sector 0: changes x14 only when initialised XDATA changes.
- Main's tracked `fw/bank_layout.tsv` is stale against its own code: every fresh build promotes a different layout (not committed from this work).
- Two module names sharing their first 29 characters collide in the map's 32-char area names: the build fails with a message (none today).
- Source diffs of the pairs (tags only): fix with a commit id in the build log per tag if the table is to be reproduced.
- Rec 2 needs `sdld` area per module with `-a`: `bank_layout` already passes thousands of `-a`; check the `s_`/`l_` symbol use of `XSEG1..4` in startup first (rec 1 removes that dependency).

## Implemented [measured 2026-11-19, sim + built images, serial AWT26110003, `scripts/xdata_churn_probe.py`]
- Rec 1: startup clears each XDATA hole at the fixed bounds (`fw_build.py xclear_asm()`, `fw/rl6449_memory.toml`); library `crtxclear` (l_XSEG) replaced by an empty label; XISEG pinned to the tail of hole 0 (`s_XISEG` no longer moves with XSEG). DDC RAM windows E280/E480/E680 are not in any hole, not cleared. Clear runs before the XINIT copy (XISEG lies inside hole 0).
  - Common sector 0 identical in all 14 banks across a +7 B XDATA change (was rewritten x14).
  - Cost: `scripts/startup_clear_cost.py` reset -> `_sdcc_program_startup`: 21578 -> 23968 instr, +73240 CPU clocks = +209 us at 350.8 MHz (hole total 7324 B vs 6527 B of module XSEG before). Startup actually runs on the slower reset clock (before M2PLL); WDT period ~4.7 s.
- Rec 2: `fw/xdata_layout.tsv` (module, hole, offset, slot); `split_xseg()` renames each module's XSEG to `XS_<module>` in its `.rel` and `-a` pins it. Library XSEG (37 B reserve) at hole 0 start, XISEG at its tail.
  - Slot kept while size <= slot; growth/new module -> first fit in the gaps; else evict one smaller module; else compaction (log line, full churn); `--xdata-compact` forces it. Fails only when the bytes do not fit.
  - Free XDATA logged per hole + largest gap (fw_build.log); gate `xlayout` (tracked file == linked map), `tests/test_xdata_layout.py`.
  - Rebuild with no change: 1 sector (tag).
- Probes (after = branch before the origin/main merge, before = origin/main + same settled bank layout; one `volatile __xdata unsigned char g_ucChurnProbe[N]` added as the first line after line 1 of one module, vs the clean build, changed sectors of 224):

| module | +B | before | after |
|---|---|---|---|
| `fw/log/sync.c` (hole 0, 1042 B module) | 100 | 147 | 76 |
| `fw/log/swlog.c` | 30 | 188 | 23 |
| `fw/test/testcmd.c` | 11 | 62 | 3 |
| `fw/power/led.c` | 7 | 102 | 18 |
- Free XDATA after the merged tip build: 559 B of 7324 B; hole E780 202 B (largest gap 186), D700 74 B, E380 27 B, E580 256 B
- Large growth with no gap (sync +100 B: its slot + one evicted neighbour) still touches many sectors because XDATA is ~92 % used and gaps are 74-256 B.

## Rec 5: not done
- Common holds 991 stubs (8 B each) + 53 `fn` chunks; the chunks are ISR / `--pin-common` / call-graph forced (SDK DB-apply, timer / EXINT procs, `_AwtoPutStr`, `_AwtoMs`...), edits to them are rare; moving the few awto ones needs per-function ISR reachability analysis for ~2 sectors x14 gain. Open.
- Another common dependency: `l_XINIT` (init-data size) is an immediate in common sector 0; changes only when initialised XDATA changes.
