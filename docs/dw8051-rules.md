# DW8051 / SDCC coding rules: repo side

- Rules (flags, memory, banking, ISRs, stack, types, speed, C23 use), each with why + source: awto-dan `docs/embedded/dw8051-rules.md`. Not restated here.
- Rules with no enforcing gate, one proposed gate each: #361. Gate list and tiers: [gates.md](gates.md).
- SDK edit rules (`// awto:` marks, no build-step patches): [keil2sdcc-rules.md](keil2sdcc-rules.md).

## Compiler
- Firmware compiler: `/usr/local`, pinned by `SDCC_COMMIT` in `scripts/fwimage.py` (21ec5e00dd on main 2026-11-28: #182, #185/#195, #186/#196, #191, #192, #202, #204, #206); the build refuses another stamp. Test + numbers: #334.
- `constexpr`: not used in our code (SIGSEGV on `x + N` in a function on f8d34cffc1 and a0e3940b0d, awto-sdcc#198; not re-checked on 21ec5e00dd); use `enum` / `#define`.
- Standard `[[...]]` attributes, `unreachable()` codegen, `_BitInt(24)`: in the pinned compiler since 21ec5e00dd (rules doc, C23 section).

## Sweep report
- `./dev.py rules-report [--image tmp/fw/<stem>] [--profile]` (`scripts/dw8051_sweep.py`): counts per rule class over our files (`magic_lint.our_files`) on the tree's last build: `constexpr`, `__sfr16`, `__critical`, `isr_shared` without `volatile`, `(x & M) == M` single-bit tests (ours + SDK), `_PARM_n` slots of our modules, banked calls reachable from ISRs, call-graph recursion, #360 guard sites.
- `--profile`: per-site calls and no-op fraction from `fw_profile` (idle main passes); rows in `tmp/dw8051/guard_sites.tsv`.
- #360 guard sites (banked function whose first instructions test a global and `ret`): report only. Hoisting the test to the caller needs Dan's decision per site (numbers on #360; [sync-log-design.md](sync-log-design.md) "Line rules").
- Sweep of 2026-11-27 (on main: df5897f3, 7669559c, 94e22f8f, 25f7bffc, f4c43723): results and sizes on #361.

## Simulator cycle model
- `scripts/dw8051_model.py`: MOV A,#data (0x74) is 1 cycle there, databook 2 (#362): every fw_sim count is low by 1 per executed MOV A,#data until fixed; `docs/speed-bench.tsv` gets a re-baseline then.
