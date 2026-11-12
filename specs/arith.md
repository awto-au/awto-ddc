# Spec: arith  (step 2 helpers, #65)
Status: draft. Writer: Opus (process owner), 2026-11-07.
Covers `awto/include/arith.h`. Results feed register values: they must match bit for bit, rounding quirks included.

## 1. Interface
- All values unsigned 32-bit; results mod 2^32.
- Domain: 1 <= c <= 2^31. Outside it (c = 0, c > 2^31): any result, but the call must return.
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
| regime rule, rounding rule | measured | reference arithmetic run on host against `specs/vectors/arith.tsv`, 2026-11-07: 1600/1600 equal |

## 4. Oracle
- `specs/vectors/arith.tsv`: `fn a b_or_k c expected`, hex (generator: `scripts/spec_vectors.py`, fixed seed).
- Host test (gcc): all rows. Target check: the same rows through the SDCC build in the verifier's simulator.
- Speed: report cycles per call for (0x12345678, 0x9ABCDEF0, 594000) on the target build; budget below.

## 5. Implementer task
- Files: `awto/arith/arith.c`, `tests/host/test_arith.c` (reads the vectors file given on the command line).
- Budget: <= 1480 B code (sdcc --model-large, CSEG bytes of the object file; the 32-bit divide / modulo / multiply routines
  the compiler calls are runtime library routines already in the image and are not counted); slow regime <= 20,000 cycles
  per call on the 8051 target. Basis: the replaced reference routines measure 940 + 539 = 1479 B in the image map
  AWT26110003-wb-port8-be (2026-11-07). First implementation: 1906-2361 B (a 64-bit-by-32-bit restoring divider written
  out in 32-bit C, instantiated for both routines).
- Free to use any method as long as every vector matches. SDCC mcs51 has no 64-bit integer type: do not emulate one.
- Size hints (the maths is ours, `derived`):
  - Because c <= 2^31, a remainder r < c always satisfies 2r < 2^32. So R(x, k, c) needs no 64-bit division: start with
    q = x / c and r = x mod c (one 32-bit divide and modulo, library), then k times: r = 2r, q = 2q (mod 2^32), and when
    r >= c subtract c from r and add 1 to q. Result q + (1 if 2r >= c). k = 0 is the plain rounded division.
  - The slow regime is then R(H, 32, c) + R(L, 0, c): two calls of the same function; there is no separate divider.
  - Product halves H, L from four 16 x 16 partial products with carry; no wider type needed.
  - A prototype of this shape measured 1211 B and passed all 1600 rows (SDCC 4.6.4, 2026-11-07); static `__data`
    working variables measured 336 B for the shldiv function alone (vs 443 B), at the price of internal RAM and
    non-reentrancy (allowed, section 1): use only if the budget needs it.

## 6. Q&A
- 2026-11-07, Q5 (size, ldiv32 ~443 B): the 600 B budget had no basis; re-based to the replaced code (1480 B). The excess
  came from the hand-written 64/32 divider in 32-bit C (SDCC does 32-bit shifts/compares through XDATA, 30-60 B each) and
  its duplication; see the size hints. SDCC has no 64-bit division to use.
