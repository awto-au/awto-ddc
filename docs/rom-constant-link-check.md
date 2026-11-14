# ROM constant link validation (#149, #205)

Inspected against `main` at `c7c5de5df541dfe30f65a8cac3ed1ca406d9202d`.

## Why the font placement escaped

Issue #205 records `_font_blob` reading a `const __code *` through `MOVC`
while running in another bank than the font blobs. The address is only 16 bits;
`MOVC A,@A+DPTR` reads the active ROM bank, not the symbol's bank in the map.
A trampoline changes the active bank for the callee, but does not make this
pointer carry a bank number.

The previous protections do not establish this invariant:

- `sdcc_bank.Chunk.gptr` and `gptr_callee` recognise `__gptrget` calls, not
  direct MOVC readers. Their CONST re-homing rules and escaping-address rules
  therefore do not impose a direct-reader/caller co-location constraint. A
  sticky layout assigns explicit slots again in pass B; matching those slots
  only proves that the linker followed the layout.
- `asm_const_ptr` likewise requires a callee containing a `__gptrget` call and
  searches only 30 source lines after a pointer immediate.
- The binary `gptr_const_xbank` heuristic recognises DPTR and Keil R1/R2
  setups near a stub call. A spilled or otherwise split direct code pointer
  can escape that window. The reader itself has no constant immediate to
  check because it receives the pointer as a parameter.
- `const_other_bank` guesses from numeric offsets. An unrelated object at
  the same 16-bit offset in the reader's bank can hide the intended symbol.
- Static symbols need not appear in the map. The linked CH area name must
  supply their names, including full names lost to map truncation.

The committed `fw/bank_layout.tsv` places `_font_blob` and all seven
`_font_blob_*` constants in bank 10. This change preserves that file byte for
byte. No placement algorithm, compiler flags, firmware source or runtime bank
switching is changed.

## Added check

`code_const_reads` combines linked `.rst` symbol identities and signatures
with MOVC instructions and resolved call/stub edges from the image/map.
It checks direct references, follows symbolic ROM pointer-table entries, and
walks callers of pointer-taking readers through wrappers to a fixed point.
There is no instruction-distance or caller-depth cutoff. Banked readers use
their own bank; common readers inherit their callers' contexts. Explicitly
RAM-qualified pointer parameters do not propagate ROM references.

An incompatible reference emits `code_const_xbank`, naming the reader,
supplier, constant, and bank context. Common ROM, compatible co-location,
common readers/wrappers, and DMA-only consumers remain supported. Existing
generic-pointer and DMA proofs still run.

The firmware `link` gate supplies `--require-rst`. Missing listings emit
`code_const_source` and fail; existing `kind_stale` failures reject listings
whose CH areas disagree with the map. Standalone legacy layout-only checking
remains available without that option. Firmware gates still require zero
findings and record a link failure, with no baseline suppression.

This is a conservative placement check, not full pointer alias analysis.
Every symbolic ROM reference in a pointer supplier is considered a possible
input. Functions using unrelated ROM objects for different consumers may
need to be split or their data placed in common. Runtime numeric pointers,
global pointer stores, indirect function calls, and aggregate library CSEG
pointer provenance are not newly proved. The existing generic-pointer checks
continue to cover their recognised patterns. MOVC @A+PC switch tables do not
consume a passed pointer and are excluded.

## Offline validation

`tests/test_fw_link_code_const.py` builds synthetic `.bin`, `.map`, and linked
`.rst` fixtures. They deliberately separate the font reader and data, spill
split address halves, delay the call beyond the old windows, and overlap
unrelated bank offsets. The negative fixtures assert that the old checks
accept the image and the new check rejects it. Additional fixtures cover
tail calls, common wrappers, omitted static map symbols, symbolic pointer
tables, stale/missing listings, RAM pointers, and supported cross-bank uses.
The gate integration test executes the link subprocess and `fw_gates.main`,
then verifies the complete record contains `link: FAIL`.

Passed:

```
python -m pytest -q tests/test_fw_link_code_const.py tests/test_sdcc_layout.py
# 31 passed
python scripts/fw_link_check_test.py
python scripts/sdcc_link_test.py
python scripts/sdcc_bank_stackargs_test.py
git diff --check
```

The additional `tests/test_sdcc_link.py` run has four pre-existing failures:
`with_libs`, `check_lk`, and `banked_rom_ok` are absent from the inspected
`sdcc_link.py`, and `_sdld` does not reject the warning used by that test.
No changes to that module are part of this patch.

The production image/map/listings are untracked build artifacts and were
not present in this environment. The external clean firmware source and
pinned awto-sdcc installation were also unavailable. Accordingly, the exact
historical font-loader instruction stream and a full production 30-gate run
have not been reproduced. Before merge, rebuild on the firmware host and run
the gates with that image's linked `asm_bank` directory, checking for any
conservative placement findings. No monitor traffic or flashing was done.
