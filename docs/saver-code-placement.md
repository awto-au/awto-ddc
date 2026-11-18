# Saver fast loops: flash cache, bank switching, XDATA, code placement

Status 2026-11-18, base main 3a40c9e. Sim only (nothing flashed; unit 3 not touched).

- Tags: `[databook]` DW8051 databook v3.2a (`/vendors/realtek/analysis/rl6449-dw8051/DW8051-databook.txt`); `[sim]` fast core, dw8051 model; `[hw]` unit measurement quoted from `docs/saver-fps-budget.md`; `[sdk-hypothesis]` taken from Realtek SDK source / comments (not reliable: unconfirmed until measured); `[guess]`.
- Evidence rank: unit / sim-calibrated measurement > databook > regdb > SDK.
- Tool: `scripts/saver_code_profile.py` (counters in `scripts/mcs51_core.c`: cycles per opcode, MOVX split, bank writes, per-line cache fetches / fills, per-address XRAM accesses). Log `tmp/logs/saver_code_profile.log`.
- Models run for every number (the sim cannot tell them apart: both match unit-3 Scope 2 within ~3 %, `saver-fps-budget.md`):
  - A: 2 KB 2-way, common area (< 0x5000) shared across banks (sim default).
  - B: 4 KB 2-way, common area cached per bank (`AWTO_SIM_FETCH_COMMON=0`, 128 sets); matches "common page off" [hw: `CACHE_OPTION` 0, `saver-fps-hw.md`].
  - Scope 2 free-run 176.5 ms (A) vs 181.8 ms (B) on the base image.

## Databook cycle costs (instruction cycle = 4 clk)

| access | instruction | cycles | source |
|---|---|---|---|
| IRAM direct read / write | `MOV A,direct` / `MOV direct,A` | 2 / 2 | [databook] Table 2-4, p. 2-20 |
| IRAM direct to direct | `MOV direct,direct` | 3 | Table 2-4 |
| IRAM indirect | `MOV A,@Ri` / `MOV @Ri,A` | 1 / 1 | Table 2-4 |
| register | `MOV A,Rn` | 1 | Table 2-4 |
| XDATA pointer load | `MOV DPTR,#data16` | 3 | Table 2-4 |
| XDATA access | `MOVX A,@DPTR` / `MOVX @DPTR,A` | 2 + CKCON[2:0] (2 at stretch 0) | Table 2-4 p. 2-21, Table 2-5 p. 2-26 |
| XDATA variable (SDCC large model) | `MOV DPTR,#v` + `MOVX` | 5 cycles, 4 code bytes | derived |
| IRAM variable | `MOV A,direct` | 2 cycles, 2 code bytes | derived |
| code table read | `MOVC A,@A+DPTR` | 3 | Table 2-4 |
| `LCALL` / `RET` / `LJMP` | | 4 / 4 / 4 | Table 2-4 |
| `INC DPTR` | | 3 | Table 2-4 |
| 2nd data pointer | DPS SFR 0x86 | no reload cost | databook p. 2-26 |

- Code fetch is not in the table: each instruction byte is one memory access (databook p. 2-23), stalls come from the flash line fill: 40 + 16 x 8 = 168 flash clk = 3.74 us per miss at 87.7 MHz [sim, `sim-cpu-model.md`; geometry ASSUMED].
- XDATA vs IRAM: +3 cycles and +2 code bytes per variable access [databook, derived]. MOVX stretch: CKCON reset value 1 (3 cycles) [databook p. 2-25]; firmware value 0 [sdk-hypothesis]; unit micro-bench 2.00 cycles [hw, `saver-fps-budget.md`].
- Free direct IRAM in the map is 6 B (holes 0x1d and 0x7d); the 128 B above 0x80 are the stack (margin 11 B). The usable direct space is the DATA overlay `DDOVL0` (70 B, sized by the deepest call chain of main): the saver chains reach offset ~34, so function locals declared `__data` there cost no extra IRAM [sim: build IRAM report unchanged].

## Where the time goes (base image cp0, 87.7 MHz, model A, 8 s windows)

| saver | ms / frame | flash stall | compute (4 clk x cycles) | line fills / frame | fetched B / fill | bank writes / frame | XRAM MOVX (rd+wr) | register MOVX |
|---|---|---|---|---|---|---|---|---|
| Scope 1 | 168.9 | 81.1 (48 %) | 87.7 | 21.7 k | 75 | 12.4 k | 39.6 k | 43.9 k |
| Scope 2 | 177.8 | 91.9 (52 %) | 86.0 | 24.6 k | 62 | 12.5 k | 56.9 k | 19.4 k |
| Asteroids | 51.3 | 29.5 (58 %) | 21.8 | 7.9 k | 49 | 2.4 k | 21.2 k | 4.1 k |
| Pac-Man (paced 31 ms) | 31.4 | 23.9 (76 %) | 7.5 | 6.4 k | 20 | 1.3 k | 4.6 k | 3.0 k |

- Scope 2 detail [sim]:
  - Flash stall 52 %; cycles by class: IRAM direct 27 %, branch / call / ret 23 %, reg / acc / immediate ALU 29 %, `MOV DPTR` 11 %, MOVX 8 %.
  - XDATA variable access (MOV DPTR + MOVX on XRAM, ~57 k per frame x 5 cycles) ~13 ms = 7 %; of that 3 cycles per access (~7.8 ms = 4 %) is the IRAM saving.
  - Bank trampolines (`_bs_keil`, `_bs_ret`, `_bs_call_sw`, stubs): ~22 ms = 12 % incl. their own cache misses; 6185 cross-bank calls per frame, ~56 cycles each [databook Table 2-4 sum of the `__bs_call` / ret path].
  - Main loop outside the saver slot 60 ms of 178 (14.5 passes, ~4 ms each, ~60 % of that is refilling the cache).
- Hot-line footprint, Scope 2: 50 % of fetches in 31 lines (0.5 KB), 80 % in 103 lines (1.6 KB), 90 % in 196 lines (3.1 KB; cache 128 lines), 99 % in 721 lines. LRU loops larger than the cache miss on every pass.
- Set conflict seen: `S2ColBegin`, `S2Pulse`, `_bs_S2Y` stub on one set -> 488 x 3 fills per frame (~5.5 ms); removed by calling `S2Y` in its own bank.
- ISR `SysTimerIntProc2` (1 kHz) costs 1.4 k fills per frame and evicts saver lines; `AwtoMs`, `memset`, `abs` also show up in the top fills.
- Cache size sensitivity (base image, A geometry changed, `--sets`): Scope 2 240 / 177 / 136 / 111 / 82 ms at 1 / 2 / 4 / 8 / 32 KB; Asteroids 91 / 57 / 44 / 41 / 40 ms. The older note "64 -> 1024 sets: +-5 ms" holds for the cold-boot first pass only; saver loops move by 2x. Real geometry is the largest unknown.
- Common sharing: per-bank common (B vs A) at 2 KB: Scope 2 222 vs 177 ms, Asteroids 128 vs 57 ms.
- 175.5 MHz (`_MCU_SPEED_UP_SUPPORT` forced `_ON`, throw-away image; speed-up path [sdk-hypothesis]): Scope 1 110.0, Scope 2 114.3, Asteroids 40.6 ms; flash stall 62 / 65 / 75 % of time (SPI clock unchanged): the flash is the limit.

## Experiments (sim, ms / frame; A = 2 KB shared common, B = 4 KB per-bank common)

Frames IDENTICAL (`saver_frames_md5.py`, 6-12 frames) to the base for every step that was checked (listed per row).

| image | change | Scope 1 A / B | Scope 2 A / B | Asteroids A / B | verdict |
|---|---|---|---|---|---|
| cp0 | base | 168.9 / 237.1 | 177.8 / 181.8 | 51.3 / 70.2 | |
| p1 | Scope 2 draw path in one bank: `S2Y`, `S2Pulse`, `S2CellId`, `S2BaseCopy` + their 3 tables `bank(11)` -> `bank(12)` (data + readers move together; the hand-written pragmas on the readers alone read the wrong bank) | - | 163.3 / 163.3 | - | md5 IDENTICAL; -8 % A, -10 % B |
| c1 | + `ScalerOsdDataPort`, `ScalerOsdAddrSet`, `ScalerOsdAddrLsb` into common (6185 -> ~1.3 k cross-bank calls) | 131.4 / 144.1 | 148.2 / 133.3 | 48.2 / 47.1 | md5 IDENTICAL, NOT kept (port rate, below) |
| c2 | + `AwtoPsPollSite`, `ScalerSyncDpHpdIrqAssertTimer2EventProc_EXINT` into common (called every pass / every 1 ms ISR through the trampoline) | 130.8 / 140.8 | 145.5 / 127.0 | 47.6 / 45.5 | kept the two non-port pins only |
| f1 | + `--opt-code-speed` on `scope_saver2.c`, `scope_saver.c`, `asteroids.c`, `osd_screen.c` (replacing `--opt-code-size`) | - | 145.5 / 127.0 | 48.8 / 45.2 | 2 of 2480 chunks change (56 -> 48 B); gain 0: not kept |
| a1 | + hot locals `__data` (S2ColRows, S2Trace, S2ColBegin, ScRun, ScRuns, ScTile, AstShape, AstLine, AstCull) | 117.8 / 128.7 | 137.9 / 117.7 | 43.7 / 42.8 | md5 IDENTICAL (Scope 1, 2), IRAM report unchanged |
| k1 = kept | p1 + a1 + the two non-port pins | 137.8 / 215.9 | 153.9 / 151.0 | 46.8 / 56.3 | gates ALL PASS |

- Kept (k1) vs base, model A: Scope 1 -18 %, Scope 2 -13 %, Asteroids -9 % (noise ~5 % on Asteroids: frames are tick-paced); at 175.5 MHz (image `k1s`): Scope 1 110.0 -> 80.8, Scope 2 114.3 -> 101.3, Asteroids 40.6 -> 39.8 (no change within noise).
- Model B shows a smaller gain for the kept set (Scope 2 181.8 -> 151.0, Scope 1 237 -> 216): under per-bank common the cross-bank port calls (not kept) dominate.
- Not kept, c1 port pins: per byte `ScalerOsdDataPort` costs ~4 us [sim, same as unit T1 4.12 us] through the trampoline and ~2 us in common [sim]; the unit runs port loops 1.6-1.9x the sim [hw]; direct stores are the default since 2026-11-18 (`docs/osd/glyph-load.md`).
- `__data` locals: Scope 2 -7.6 ms (A), Scope 1 -13 ms, Asteroids -3.9 ms on top of c2: larger than the 3-cycles-per-access estimate (~3.7 ms Scope 1) because 2 code bytes per access also leave the flash fetch. Per-variable table: `saver_code_profile.py --xdata`.
- Static `__data` variables (6 B free) not tried: top candidates `s_sOy`, `s_tNew`, `s_tOld` (~0.2 ms each); the 6 B holes are the only permanent IRAM left.

## Method notes / pitfalls

- A `bank(n)` pragma on a reader without its `__code` table in the same bank reads the wrong bank (md5 differs): move table + readers together (`scripts/gen_scope2.py` emits the table pragmas).
- A function can be moved into common only by also editing its row in `fw/bank_layout.tsv` (sticky layout keeps the old bank otherwise) plus `--pin-common` (default list in `scripts/fw_build.py`).
- `dev.py build` ignores `FILE_FLAGS` edits without `--force`; sizes in the map prove whether a flag took effect.
- Compile flags `--opt-code-size` and `--opt-code-speed` both on the command line: size wins; the experiment removed the size flag per file.

## To test on unit 3 (not run here)

- Cache geometry: read the miss / reference counters (`FDB3..FDC4`, regdb) over the debug link during a Scope 2 run; sim predicts 24.6 k fills per frame on the base image (A) vs 36.2 k (2 KB per-bank) / ~15 k (4 KB shared). Separates A from B and fixes every number above.
- Kept image (k1): Scope 2 / Scope 1 / Asteroids frame rate from the sync log vs sim (153.9 / 137.8 / 46.8 ms A).
- c1 (port helpers in common) only with a port-rate check (T1 / T2 style, `osd-hw-tests.md`) and a photo of the tiles.
- 175.5 MHz image: stability, then rates (sim: Scope 2 101 ms with k1).
- Common page mode (`FDA1[1]`) on: sim A vs B difference is the prize (Scope 2 up to 20 %, Asteroids up to 2x).

## Open levers seen (not done)

- Saver slice length vs main loop passes (budget doc lever 1): main loop is 35 % of a Scope 2 frame at 87.7 MHz.
- `_mulint` / `_divuint_keil` in `S2Y` / `S2ColBegin` / `ScRun`: ~12 ms per Scope 2 frame incl. stalls (budget doc lever 5).
- Contiguous hot code: the 90 % footprint (3.1 KB Scope 2, 7 KB Asteroids) exceeds 2 KB; placement can only help the part that fits, shrinking the loop (budget doc 5 / 7) matters more.
