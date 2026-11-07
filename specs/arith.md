# Spec: arith  (step 2 helpers, #65)
Status: draft. Writer: Opus (process owner), 2026-11-07.
Covers `awto/include/arith.h`. Results feed register values: they must match bit for bit, rounding quirks included.

## 1. Interface
- All values unsigned 32-bit; results mod 2^32.
- Domain: 1 <= c <= 2^31. `ar_muldiv` with c = 0 returns 0xFFFFFFFF in both regimes (the display-link timing code calls it with c = 0 before the link rate is known; `measured`: reference image, 1080p60 and 2160p60 traces, 2026-11-07).
- c > 2^31, and `ar_shldiv` with c = 0: any result, but the call must return.
- Pure functions; reentrancy not required.

## 2. Definitions
- R(x, k, c) = round half up of x * 2^k / c = floor(x * 2^k / c) + (1 if 2 * ((x * 2^k) mod c) >= c else 0), mod 2^32.
- `ar_shldiv(a, k, c)` = R(a, k, c), k = 0..32.
- `ar_muldiv(a, b, c)`, two regimes, chosen exactly as follows:
  - fast: a = 0, or b = 0, or a < floor((2^32 - 1) / b)  ->  floor(a * b / c)   (truncating; a * b < 2^32 here)
  - slow: otherwise. P = a * b exact (64 bit), H = P >> 32, L = P mod 2^32  ->  (R(H, 32, c) + R(L, 0, c)) mod 2^32
- The slow regime is not the exact quotient: each half is rounded separately. Keep it (register values depend on it).
- Boundary: a = floor((2^32 - 1) / b) takes the slow regime even when a * b fits in 32 bits.

## 3. Data
| item | tag | source |
|---|---|---|
| c = 0 result 0xFFFFFFFF (`ar_muldiv`) | measured | reference image, 3 captured calls (c = 0, fast regime) return 0xFFFFFFFF; slow regime with c = 0 is our choice (same value) | 
| regime rule, rounding rule | measured | reference arithmetic run on host against `specs/vectors/arith.tsv`, 2026-11-07: 1600/1600 equal |

## 4. Oracle
- `specs/vectors/arith.tsv`: `fn a b_or_k c expected`, hex (generator: `scripts/spec_vectors.py`, fixed seed).
- Host test (gcc): all rows. Target check: the same rows through the SDCC build in the verifier's simulator.
- Speed: report cycles per call for (0x12345678, 0x9ABCDEF0, 594000) on the target build; budget below.

## 5. Implementer task
- Files: `awto/arith/arith.c`, `tests/host/test_arith.c` (reads the vectors file given on the command line).
- Budget: <= 600 B code; slow regime <= 20,000 cycles per call on the 8051 target.
- Free to use any method (long division, 64-bit emulation) as long as every vector matches.

## 6. Q&A
