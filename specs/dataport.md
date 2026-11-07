# Spec: dataport  (step 2 helpers, #65)
Status: draft. Writer: Opus (process owner), 2026-11-07.
Covers `awto/include/dataport.h`. A data port = index register at `port`, data register at `port + 1`.
Some ports advance their index by themselves after a data access, some are FIFOs: the caller picks the step mode.

## 1. Interface
- `port`: full register address of the index register (facts: the address one below the `_I<idx>` data port).
- `idx`: 8-bit index. Index arithmetic is 8-bit: idx + i wraps at 0x100.
- Context: main loop only. No locking (callers in ISRs must not share a port with main code).

## 2. Access sequences (W = write, R = read; in this order, nothing else)
| fn | sequence | returns |
|---|---|---|
| `dp_wr(p, i, v)` | W p = i; W p+1 = v | - |
| `dp_rd(p, i)` | W p = i; R p+1 | the byte read |
| `dp_test(p, i, m)` | W p = i; R p+1 | byte & m |
| `dp_rmw(p, i, keep, set)` | W p = i; R p+1 -> old; W p = i; W p+1 = (old & keep) \| set | - |
| `dp_wr16(p, i, v)` | W p = i; W p+1 = v >> 8; W p = i+1; W p+1 = v & 0xFF | - |
| `dp_rd_n(p, i, d, n, DP_SW_STEP)` | for k = 0..n-1: W p = i+k; R p+1 -> d[k] | - |
| `dp_rd_n(p, i, d, n, DP_HW_STEP)` | for k = 0..n-1: W p = i; R p+1 -> d[k] | - |
| `dp_rd16(p, i, step)` | as dp_rd_n with n = 2 | (d[0] << 8) \| d[1] |
- n = 0: no access at all.
- dp_rmw writes the index twice on purpose: the read may have advanced it.

## 3. Barriers and commutative groups
- None inside a call: every sequence above is strictly ordered (the index write selects what the data access hits).

## 4. Timing
- No waits. Each access is one CPU XDATA access.
- Performance requirement (hot path: these run many times per main-loop pass on the unit; 2026-11-07 the module cost ~4 % loop rate):
  - `dp_wr`, `dp_rd`, `dp_rmw`, `dp_test`, `dp_wr16`, `dp_rd16`: NO calls to other functions (no `dp_rd` inside `dp_test`/`dp_rmw`, no `dp_wr` inside `dp_wr16`). The port access is written inline in each function, with exactly the register sequence of section 2.
  - Keep arguments and temporaries out of XDATA where the compiler allows (no extra copies of arguments into locals; use the parameters directly; narrow types; `__data` is not available to the integrator build, so minimise live temporaries instead).
  - Budgets per call, measured as below (machine cycles from entry to return, `movx` instructions executed); the clean function must be <= the reference on BOTH:
| function | reference cycles | reference movx | what is measured |
|---|---|---|---|
| `dp_wr` | 112 | 13 | write byte, port 0x0031, idx 0x20 |
| `dp_test` | 116 | 13 | test bit |
| `dp_rmw` | 200 | 20 | read-modify-write |
| `dp_wr16` | 324 | 36 | write 16-bit value |
  - Current implementation (first merge), same method: `dp_wr` 56 / 9, `dp_test` 110 / 15, `dp_rmw` 142 / 18, `dp_wr16` 212 / 28. Only `dp_test` exceeds a budget (15 > 13 movx; 63 vs 66 instructions). Target for all: strictly fewer instructions than the reference.
  - `dp_rd_n` / `dp_rd16`: no reference budget measured (the reference takes a bit argument); same rule: no internal calls, loop body inline.

## 5. Data
| item | tag | source |
|---|---|---|
| reference cycles / movx in section 4 | measured | ucsim, reference image wb-port13 (SDK routines), image with the first clean merge, 2026-11-07, args: port 0x0031 idx 0x20 |

## 6. Oracle
- Host test, recording REG8 mock: each row of section 2 for idx in {0x00, 0x7F, 0xFF} (wrap: 0xFF + 1 = 0x00), n in {0, 1, 2, 5},
  both step modes; mock data register returns a counter so values are checked too.
- Mixed build: `trace_equiv.py` (no extra rules: ports are compared as ordered index/value bursts by default),
  1080p60 and 2160p60.

## 7. Implementer task
- Files: `awto/dataport/dataport.c`, `tests/host/test_dataport.c`.
- Budget: <= 500 B code total (sdcc --model-large). Performance: section 4 (no internal calls; per-call budgets).
- Report the measured numbers: ucsim, entry to return, cycles and movx per function (the verifier repeats the measurement).

## 8. Q&A
