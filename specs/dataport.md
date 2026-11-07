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

## 5. Data
- None.

## 6. Oracle
- Host test, recording REG8 mock: each row of section 2 for idx in {0x00, 0x7F, 0xFF} (wrap: 0xFF + 1 = 0x00), n in {0, 1, 2, 5},
  both step modes; mock data register returns a counter so values are checked too.
- Mixed build: `trace_equiv.py` (no extra rules: ports are compared as ordered index/value bursts by default),
  1080p60 and 2160p60.

## 7. Implementer task
- Files: `awto/dataport/dataport.c`, `tests/host/test_dataport.c`.
- Budget: <= 500 B code total (sdcc --model-large).

## 8. Q&A
