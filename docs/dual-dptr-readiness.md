# Dual-DPTR safety work - 13 November 2026

**Draft; keep `--dual-dptr` disabled for production. No firmware was flashed.**

Related: [awto-ddc #188](https://github.com/awto-au/awto-ddc/issues/188),
[#160](https://github.com/awto-au/awto-ddc/issues/160), and
[awto-sdcc #88](https://github.com/awto-au/awto-sdcc/issues/88).

## Source availability

The remotely available firmware `main` is `ec4b8a18fdc22ea79cf491e9d59986a389cc420b`.
GitHub returns "No commit found" for the issue's firmware revision `60af7ba`.
The available branches contain neither `awto_wdt.inc`, `AWTO_WDT_FRAME`, the
`crash`/`wdt` gates, nor the fast DW8051 model (`mcs51_core.c`, `fastmachine.py`,
`dw8051_model.json`). These files must be supplied from Selwyn before the
watchdog changes can be applied and verified. The missing implementation has
not been reconstructed from the issue description.

The compiler inputs were inspected at baseline `3f45e82ead` and current
`awto/next` `2751f2ef2197c933d74d192143011d8b3b439681`. The option macro is absent
in both. Current `awto/main` predates the dual-DPTR integration, so the compiler
change targets `awto/next`.

## Implemented

- Compiler: predefine `__SDCC_MCS51_DUAL_DPTR=1` only with `--dual-dptr`, from
  MCS51 option finalisation before preprocessing. Document the ISR stack growth.
- Firmware build: use the existing `wb_build.py --flags` / `K2S_SDCC_EXTRA`
  route. Propagate `--dual-dptr` to the common flags used by CRT overrides and
  ISR helper clones as well as SDK compilation. No default is changed.
- Before SDK processing, preprocess an assertion of the compiler macro; reject
  the older option-enabled compiler without that macro.
- Before linking, audit the `.asm` companion of **each direct `.rel` input**,
  including generated assembly and hand-written modules. Reject binary-only
  objects, missing vector targets, missing or late saves/selector reset, wrong
  restore order, paths skipping restoration, incompatible stack joins, and
  unverified control flow. Diagnostics name the module and handler.
- The only automatic exception is a single bare `RETI`, which neither uses
  DPTR nor makes calls. Noncanonical assembly fails closed and needs review.

The checker does not inspect archive members pulled in by the linker. A vector
target without companion assembly fails. The current SDK compile command uses
`--norestartseqatomics`; a handler tail-jumping to the external atomic rollback
helper is conservatively rejected, rather than assuming that helper is safe.
This check establishes the save/restore envelope, not arbitrary inline-assembly
semantics, a safe total stack budget, or runtime correctness.

The three committed hand-written `.asm` files were inspected: `bank.asm`,
`crt_xinit.asm`, `crt_rtd_startup.asm`. None contains an ISR/`RETI`. This is **not**
an audit of the unavailable `60af7ba` link: generated SDK handlers and newer
hand-written handlers remain unverified until that tree is built.

## Regression results in the cloud

| Check | Result |
| --- | --- |
| New compiler frame test | 6 execution cases passed: off/on, LE, BE/sc3, no-peep |
| Interrupted PC | `0x1234` recovered from actual hardware interrupt stack in ucsim `DW8051` |
| Frame size including PC | 16 B off; 19 B on; asserted against emitted pushes and captured SP |
| Wrong frame negative controls | On with 16/20 B and off with 19 B all rejected |
| Broken DPL1 save | Rejected by pointer-preservation assertion |
| Missing option macro | Older compiler rejected by both fixture preprocessing and build preflight |
| Code generation comparison | Assembly unchanged by macro-only change in both off/on modes |
| Existing `dual_dptr_test.py`, LE | 17 cases passed, including nested interrupts and register banks; 2 broken-code controls detected |
| Existing `dual_dptr_test.py`, BE/sc3 | 17 cases passed; 2 broken-code controls detected |
| Firmware audit tests | 16 tests passed, including absent saves, branch bypasses and missing link-input assembly |

The focused compiler/simulator builds use recovered upstream sources plus
hash-verified GitHub compiler build inputs. The existing copy test uses only
the required `_dualdptrcopy` and atomic helper fixture archives built here,
not a complete installed firmware toolchain. These are focused execution tests,
not a fresh run of the entire SDCC regression suite or firmware gates.

## Comparison with the documented A/B

Baseline: compiler `3f45e82ead`, firmware `60af7ba`, as reported in #188.

| Metric | Baseline off | Baseline on | New full-firmware measurement |
| --- | ---: | ---: | --- |
| Flash banks | 378654 B | 378502 B (-152 B) | Blocked: firmware tree/SDK absent |
| Common area | 13954 B | 14135 B (+181 B) | Blocked |
| XRAM | 7050 B | 7054 B (+4 B) | Blocked |
| Complete stack depth/headroom | Not supplied in issue | Not supplied in issue | `fw_stack.py` must be rerun |
| WDT entry frame including PC | 16 B | 19 B required | Confirmed only in representative compiler fixture |
| `crash` / `wdt` | On introduces failures | Failing in issue | Not rerun; implementations unavailable |

The macro change does not alter generated code for sources that do not use the
macro. The real watchdog header change can alter firmware bytes; no new memory
totals or full stack margin are claimed. Each nested compiled ISR adds three
stack bytes, so one ISR's +3 B is not a bound on total nesting overhead.

## Required work on the current Selwyn tree

1. Supply/push `60af7ba` or its current successor, including the watchdog
   recorder, simulator/clock model, build/gate scripts and assembly outputs.
2. In the actual watchdog header, select `AWTO_WDT_FRAME` as 16 or 19 with
   `#ifdef __SDCC_MCS51_DUAL_DPTR`. Keep this tied to the generated handler's
   real push count, rather than treating 19 as a universal ISR size.
3. Migrate the real `wdt` gate from 8052 to the fast core's DW8051 mode. Verify
   Timer2/watchdog timing and deadlines against its clock model; merely changing
   a CPU name is insufficient evidence of a correct watchdog test.
4. Rebuild both modes with identical source/options and a newly stamped compiler.
   Check the complete link's ISR audit and `fw_stack.py`, including nested
   priorities; reject insufficient IRAM headroom.
5. Run full firmware gates in both modes, especially `crash` (the recorded PC
   resolves to `AwtoWdtHang`) and `wdt` (boot/ACTIVE and watchdog timing).
   Mutate the actual frame constant to the wrong value in each mode and require
   the real crash gate to fail. Archive A/B memory, stack and gate reports.
6. After separate approval to flash unit 2, verify watchdog capture/reset and
   interrupt preemption of XDATA copies on physical hardware. Simulator success
   does not establish reset state, silicon timing, or production readiness.

Neither merging nor flashing is authorized by this draft.

## Reproduce focused tests

In awto-sdcc, with a built compiler and matching tools:

```sh
python3 scripts/dual_dptr_frame_test.py --sdcc /path/to/new/bin/sdcc \
  --tools /path/to/new/bin --baseline /path/to/pre-macro/bin/sdcc
python3 scripts/dual_dptr_test.py --sdcc /path/to/new/bin/sdcc --tools /path/to/new/bin
python3 scripts/dual_dptr_test.py --sdcc /path/to/new/bin/sdcc --tools /path/to/new/bin \
  --big-endian --sdcccall 3
```

In awto-ddc:

```sh
python3 -m unittest discover -s tests -p test_fw_dual_dptr.py -v
python3 scripts/fw_dual_dptr_check.py /path/to/linked/modules/*.asm
```
