# Native DW8051 delay batching, 24 November 2026

Review base: `3d271b994882eafe190cd9521b3a5b7c38d5cf22`.
Related: [awto-ddc#342](https://github.com/awto-au/awto-ddc/issues/342).
No monitor access, firmware flash, deployment, merge or issue closure.

## Implementation and exactness boundary

`counted_ffwd()` runs inside `core_run_`, after an ordinary instruction and
its interrupt poll. It recognises `DJNZ Rn,$` and `DJNZ direct,$` with a
counter in lower IRAM. This matches the current `push ar7; mov r7,direct;
djnz r7,$; pop ar7; ret` routine, the inner loop of AwtoDelayXus, and
AwtoDelayCnt. Everything outside the self loop remains interpreted, including
the Xus timer check and its long-delay logger. No firmware symbols, addresses
or whole-routine timing estimates are needed in the accelerator.

Batch size is bounded by the remaining count, the C run instruction budget,
and the first timer deadline. The final iteration is interpreted. An initial
zero means 256 iterations. Timer deadlines are approached strictly from below;
the ordinary instruction that reaches/passes the deadline performs the usual
timer update and interrupt arbitration. Timer0/1, Timer2, interrupt priorities,
RETI/enable-write inhibition, ISR stack pushes and instruction accounting
therefore retain the interpreter's boundaries. Register-bank selection uses
PSW, rather than assuming bank zero.

Fetches must be cached hits for all instruction bytes. A cold first iteration
is interpreted. The ordinary fetch establishes the LRU order; repeating the
same byte sequence cannot change that final order while all its lines remain
resident. Every skipped byte hit is added to the physical-line counters,
including instructions crossing cache lines. Cache misses/stalls, opcode
counts and opcode cycle totals remain exact. Timer counter/edge/level cases,
SFR counters, enabled race instrumentation and PC breakpoints use the normal
interpreter. A nonempty loop body, especially MOVX polling, never qualifies.

There are no added host stops. FastMachine sees the same run budgets and
clock-register events, so its ticker/deadline and wall-time accounting stays
in its existing run wrapper. `install_delay_ffwd()` now only enables the C
path and installs no Python hooks. Core's Python wrapper enables batching by
default; `AWTO_SIM_COUNTED_FFWD=0` or `core.set_counted_ffwd(False)` selects the
reference interpreter. The switch survives snapshot restore as host
configuration, like hooks. The existing `core_ffwd_room`/`core_ffwd` primitives
are reused; fetch modelling disabled entirely also permits exact batching.

## Offline validation and remaining full-image check

`tests/delay_program.py` assembles the actual naked functions in
`fw/timer/delay.c`, including AwtoDelayEnd and AwtoDelayLong. Unknown assembly
is an error. Direct-variable addresses are relocated into a test allocation;
no vendor SDK or compiler output is substituted for the current routines.

The C differential oracle runs **57,536 cases**:

- Counts 0..255 for Loops, Xus outer count, Xus base count and Cnt.
- All prescaler residues for both /4 and /12 timer clocks, at CPU rates
  87.69775, 175.3955 and 350.791 MHz, with the corresponding SPI dividers.
- Timer0/1 mode-1 overflows and Timer2 reload interrupts inside waits; the
  Timer2 ISR has higher priority and uses R7. Its interrupted return PC and
  stack bytes are part of the comparison.
- Every R0..R7 DJNZ encoding, all four register banks and every initial count.
- Instruction budgets 1, 2, 7, 127, 255, 256, 257 and 1000, including stops
  during a loop or ISR.

Every byte of the private core state is compared, apart from allocation
pointers and the enable flag. This includes timer residues/deadlines, fetch
cache tags, registers, stack, IRAM, SFR, XDATA, IRQ state, last opcode and all
instruction/cycle/access counters. Both complete physical-line hit/miss arrays
are compared separately. Additional Python tests cover cold/uncached and
cross-line fetches, five flash ratios and changes between run chunks, timer
fallbacks, pending/inhibited IRQs, SFR counters, breakpoints, loop bodies,
classic 8052 fallback, and the exact 256-iteration zero case. A separately
compiled sanitizer test verifies all 200 instruction commits and 400 IRAM
accesses remain visible with batching enabled.

The focused suite passed **75 tests**. Three full-image tests were skipped:
the boot-plus-three-second check and two SimBus snapshot checks. This fresh
checkout has no built firmware image or awto-sdcc installation. The initial
build attempt also stopped at the 12 GiB available-memory guard (8963 MiB
available). No build guard was bypassed.

The passing portable per-count test's xfail was removed. The full-image boot
test's xfail is deliberately retained, now strict, until an actual run passes.
Its comparison is tightened to exact state/counters/wall time because native
batching adds no Python stop-granularity noise. A passing run will be XPASS
(strict), signalling that its last xfail can be removed. This PR remains draft
pending that check. No full-boot timing improvement is claimed here.

## Actual host execution time

[delay-host-times.json](delay-host-times.json) retains all samples, wall and
process CPU times, hashes and environment/compiler metadata. Each sample runs
30,000,000 instructions after a 10,000-instruction warmup; nine samples per
mode, with mode order rotated on each round. Compilation, restore and hashing
are outside timing. The original core is compiled from the review base;
`off` is the new core with batching disabled. All three modes must produce the
same architectural/counter/fetch-statistics digest. These are isolated hot
loop workloads, without firmware boot or a hardware model workload.

| Workload | Original wall s | Native wall s | Speedup vs original |
| --- | ---: | ---: | ---: |
| Loops count 1 | 0.291695 | 0.296939 | 0.98x |
| Loops count 4 | 0.308150 | 0.296131 | 1.04x |
| Loops count 29 | 0.308463 | 0.096005 | 3.21x |
| Loops count 109 | 0.265955 | 0.031673 | 8.40x |
| Loops count 255 | 0.295923 | 0.014444 | 20.49x |
| Loops count 0 (256) | 0.272732 | 0.013643 | 19.99x |
| Xus base 29, outer 64 | 0.312070 | 0.056483 | 5.53x |
| Cnt count 29 | 0.365398 | 0.088443 | 4.13x |
| MOVX/ALU loop, no eligible delay | 0.265307 | 0.268856 | 0.99x |

The small-count/control differences are small on this shared virtual host;
raw samples should be inspected before claiming a general throughput effect.
The useful result is a measured reduction in host work for substantial delay
counts, with equal simulated work. These numbers do not predict full-boot
speed or Doom FPS and do not replace the pending full-image check.

Reproduce:

```sh
git show 3d271b994882eafe190cd9521b3a5b7c38d5cf22:scripts/mcs51_core.c > /tmp/original-core.c
python scripts/bench_counted_ffwd.py --reference-source /tmp/original-core.c --instructions 30000000 --repeat 9 --out tmp/ffwd-review/bench.json
AWTO_TEST_NO_BUILD=1 python -m pytest tests/test_delay_ffwd.py tests/test_counted_ffwd.py tests/test_sim_snapshot.py tests/test_sim_idle_irq.py --slow -q
# With the real full firmware available:
AWTO_TEST_IMAGE=/absolute/path/to/image-stem python -m pytest tests/test_delay_ffwd.py --slow -q
```

## Doom: timing preserved, no speed benefit in this checkpoint

Examined the latest `doom-ddr-dw8051.zip` checkpoint, version 14, SHA-256
`8ea95f1a929650ed30f117fd5422df5f09606d08f8e05a50281c6844565706bb`.
It contains changed source based on `505a3fd65de77f1ea2a50f7debed5909fe206e40`.
Its DDR/MPAGE core differs from main; it was restored separately and is not
folded into this change. [doom-integration.patch](doom-integration.patch)
ports the same native path to that source, without replacing its DDR model.
The C delay oracle also passes against that adapted core.

[doom-host-times.json](doom-host-times.json): seven paired runs of 12 real
native frames, using the checkpoint's switch scene, a use command on frame
one and **64 CPU clocks of DDR latency**. The supplied compiled two-bank
firmware was used unchanged. Original shareware Doom 1.9 assets were loaded
before CPU boot. Every paired run matches all result data, instruction and
cycle counts, architectural state, full 32 MiB DDR hash, DDR statistics,
physical fetch counters and frame timings. Total: 37,066,083 instructions,
410,530,148 CPU clocks. Median simulation host wall time: **0.543500 s off,
0.545236 s native (0.997x)**. Benchmark instrumentation counted **zero skipped
iterations**. No Doom speedup is claimed.

The renderer's copies, pixel loops, arithmetic and DDR waits do work on every
iteration. In particular `read_wait` and `idle_wait` read MOVX status each
pass; skipping those reads would change polling, event and timeout timing.
They are excluded. A real DJNZ self-delay added to Doom would use the tested
path, but accelerating its useful counted loops needs a separate operation-
specific implementation preserving each memory access and DDR completion.

The benchmark instruments only a temporary C build to count skipped
iterations. It compares complete results before saving the compact report;
state hashes and all host samples remain in that report. Inputs, generated
images, IWAD bytes and decoded assets are not committed.

Reproduce after restoring the checkpoint's source at its documented base:

```sh
git -C /path/to/doom-checkpoint apply --unidiff-zero /path/to/this-checkout/docs/benchmarks/native-delay-2026-11-24/doom-integration.patch
python scripts/bench_doom_counted_ffwd.py --doom-root /path/to/doom-checkpoint --image-dir /path/to/checkpoint/current --wad /path/to/doom1.wad --frames 12 --repeat 7 --result tmp/ffwd-review/doom-bench.json
```
