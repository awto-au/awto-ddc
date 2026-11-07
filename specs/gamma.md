# Spec: gamma  (step 8 data, #65): output gamma LUTs generated from maths
Status: draft. Writer: Sonnet (spec side), 2026-11-07. Replaces the 4 vendor LUTs (1.8 / 2.0 / 2.2 / 2.4, 6156 B each).
Covers a new `awto/include/gamma.h` (section 1). Provenance: format `derived` from the load path + `measured` on the reference tables; values `derived` (maths).

## 1. Interface (implementer creates `awto/include/gamma.h`)
- `void gamma_load(uint8_t kind)`: kind 0..3 = gamma 1.8 / 2.0 / 2.2 / 2.4 (x10: 18, 20, 22, 24). Loads the curve into all three channel tables. Main loop only.
- `void gamma_enable(uint8_t on)`: 1 = gamma stage on, 0 = off (bypass). Main loop only.
- Both are called by the OSD settings code; `gamma_load` while the stage is on follows the sequence in section 2.

## 2. Register sequences
Names: `GM_PORT` = `P00_66` (table data port: bytes written to it fill the selected table sequentially), `GM_CTRL` = `P00_67`.
`GM_CTRL` bits (our names, positional facts `P00_67_B*`): `GM_ON` = B6 (gamma stage enabled), `GM_ACCESS` = B7 (table access enabled),
`GM_CH` = B5:4 (channel select 0 = R, 1 = G, 2 = B), `GM_PTR` = B3 (offset load mode), `GM_LOC` = B2 (0 = table SRAM).
| # | reg | mask | value | condition | wait |
|---|---|---|---|---|---|
| L1 | `GM_CTRL` | `GM_ON` | read: 1 = stage was on | start | - |
| L2 | wait for the display-enable stop edge (`tmr_wait_edge(TE_OUT_VEND)`) | | | stage was on | until the edge; on timeout: return, no write at all (stage stays on, old table) |
| L3 | `GM_CTRL` | `GM_ON` | 0 (read-modify-write) | stage was on | - |
| C(ch) | channel select, one per channel in the order R, G, B: | | | always | - |
| C1 | `GM_CTRL` | `GM_ACCESS`,`GM_CH`,`GM_LOC` | `GM_ACCESS` = 0, `GM_CH` = ch, `GM_LOC` = 0 (RMW; B3 kept) | | - |
| C2 | `GM_CTRL` | `GM_PTR` | 1 (RMW) | | - |
| C3 | `GM_PORT` | 0xFF | 0x00 then 0x00 (table offset 0, high byte first) | | - |
| C4 | `GM_CTRL` | `GM_ACCESS`,`GM_PTR` | `GM_ACCESS` = 1, `GM_PTR` = 0 (RMW) | | - |
| T(ch) | table bytes: 2052 bytes written to `GM_PORT` (fixed target, all bytes to one register), section 5 for the contents | | | after C4 | burst or CPU writes |
| L4 | `GM_CTRL` | `GM_ACCESS` | 0 (RMW) | after the third T | - |
| L5 | wait for the display-enable stop edge | | | stage was on | until the edge; on timeout: continue with L6 anyway (stage back on, new table; a stage left off is the worse failure) |
| L6 | `GM_CTRL` | `GM_ON` | 1 (RMW) | stage was on | - |
- Timeouts: the log (operation, limit, elapsed) is owned by `tmr_wait_edge` / `tmr_poll` (timer.h `tmr_expiry_hook`), not by gamma.
  Gamma only decides what to do after a 0 return (L2 / L5 rows).
- `kind` > 3: `gamma_load` returns without any register access (invalid values come from the settings registry range check, so this is a programming error; the current table stays).
- `gamma_enable(on)`: `GM_CTRL` `GM_ON` = on (RMW), nothing else.
- Order: L1, [L2, L3], C(R), T(R), C(G), T(G), C(B), T(B), L4, [L5, L6]. Brackets: only when the stage was on at L1.
- The table bytes T go through `hb_burst` (HB_FIXED, target `GM_PORT`) or `reg_wr_n(GM_PORT, buf, 2052, 0)`; either is valid, the trace compares the final state and the port data per channel.

## 3. Barriers and commutative groups
- Strict order as listed in section 2. L3 is the barrier before the first C; L4 the barrier before L5.

## 4. Timing
| what | value | source | tag |
|---|---|---|---|
| waits at L2 / L5 | one display-enable stop edge each; bound = `tmr_wait_edge` timeout | timer spec | derived |
| table write | 3 x 2052 B | section 5 | derived |

## 5. Data (table format and formula)
- One channel = 2052 bytes = 1026 entries of 16 bit, big-endian (high byte first). Channel order in memory R, G, B. Tag `measured`: decoded from the 4 reference tables, 2026-11-07 (all four: 1026 entries per channel, 0 <= e <= 0x3FF0, entries 0..1023 non-decreasing).
- Entry value: 14-bit with 4 fraction bits (0x3FF0 = full scale 1023.0 in 10-bit units). `derived`.
- Entries i = 0..1023 (input code i of 1023): `e(i) = round_half_up(16368 * (i / 1023) ^ (g / gn))`, with g the target gamma (kind), gn = panel native gamma.
  - `gn = 2.2` (default constant `GM_NATIVE_X10 = 22`). `measured` basis: the reference tables have log-log slope g / 2.2 between index 100 and 800 (1.8: 0.82-0.85, 2.0: 0.91-0.92, 2.2: 1.01-1.03, 2.4: 1.10-1.13). Replace by a `measured` panel value when the panel is characterised.
  - Entry 1024 = 0x3FF0, entry 1025 = 0x0000 (as in the reference tables; `measured`; purpose of the last two entries unknown, keep them).
- Known difference to the reference tables, accepted by design: below index ~50 the reference curves fall much faster than the power law (e.g. gamma 2.2: e(3) = 3 in the reference, 48 here) and R, G, B differ by up to ~5 % near white (panel white balance). Our three channels are identical (white balance is a separate colour feature). Judge by eye on unit 3 (gamma pattern photo) before accepting.
- Tolerance of the implementation against the formula: +-1 LSB (rounding of the power function); vectors below.
- Storage: R = G = B, so one 2052-byte curve per kind may be stored and sent three times. Computing entries at run time instead of storing them is allowed (no floating point library in the image: use fixed-point or a build-time generated table; the generator script lives in `tools/` of awto-rtdfw). Code-space constants are read by the loader: placement in a code bank other than the reader's is an integration issue (`gptr_const_xbank` in the link check); the integrator pins gamma chunks together, the implementer keeps the loader and its tables in one source file and reads the table by direct indexing (`gm_tab[kind][i]`), never through a pointer variable or pointer table: the banker keeps any const whose address escapes in the small common area (#16, 8,468 B do not fit there) and the layout fails.

## 6. Oracle
- Vectors: `specs/vectors/gamma.tsv` (`gamma_x10 index expected_u16`, hex, accept +-1), built from the formula above (`scripts/spec_vectors.py`).
- Host test: the generator or table for each kind against the vectors; byte order and length (2052) of one channel; entries 1024 / 1025.
- Bus sequence: the table in section 2 with a recording `REG8` mock (order of control writes, three channel selections, 3 x 2052 data bytes to `GM_PORT`).
- Trace: `specs/gamma.equiv` (control sequence compared; table data on `GM_PORT` ignored: values differ by design).
- Visual: unit 3 gamma pattern, kinds 0..3 (process owner / Dan).

## 7. Implementer task
- Files: `awto/gamma/gamma.c` (+ `awto/include/gamma.h`), `tools/gen_gamma.py` (if a build-time table is used), `tests/host/test_gamma.c`.
- Budget: <= 9,000 B code + const in total for all four kinds (reference: 4 x 6,156 B). Cycles: none critical (settings change).
- Uses: `reg.h` (`reg_rmw`, `reg_wr`, `hb_burst` / `reg_wr_n`), `timer.h` (`tmr_wait_edge`).

## 8. Q&A
- (open) Which curves does the product expose? Four kinds assumed (reference menu).
