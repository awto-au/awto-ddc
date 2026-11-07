# Spec: reg  (step 2 helpers, #65)
Status: draft. Writer: Opus (process owner), 2026-11-07.
Covers `awto/include/reg.h`: multi-byte register access, n-byte transfers, the host-bus burst engine, the OSD burst gap.
Single-byte macros (`reg_rd`, `reg_wr`, `reg_rmw`, `reg_test`) are defined in the header: not part of this task.

## 1. Interface
- Register space: XDATA address = (page << 8) | offset. Every access is one CPU read or write of one byte.
- `reg_rd16(a)`: reads a, then a+1; returns (byte(a) << 8) | byte(a+1).
- `reg_wr16(a, v)`: writes a = v >> 8, then a+1 = v & 0xFF.
- `reg_rd32(a)`: reads a, a+1, a+2, a+3 in that order; byte(a) is bits 31:24.
- `reg_wr32(a, v)`: writes a = bits 31:24, a+1 = 23:16, a+2 = 15:8, a+3 = 7:0, in that order.
- `reg_rmw32(a, keep, set)`: new = (old & keep) | (set & ~keep); old read as reg_rd32, new written as reg_wr32.
- `reg_wr_n(a, src, n, step)` / `reg_rd_n(a, dst, n, step)`: n = 0 -> no access. step 1: byte i to/from address a + i,
  i ascending. step 0: every byte to/from address a, i ascending.
- `hb_burst(src24, len, target, kind, from_xram)`: section 2. Returns 0 when the engine reports done, 1 when it is still
  busy after the restart limit (T2).
- `hb_osd_gap(dclk_khz, hdouble)`: pure; section 5 table D1.
- Context: main loop only. Not reentrant (hb_burst uses shared engine registers).

## 2. Register sequences: hb_burst
| # | reg | mask | value | condition | wait |
|---|---|---|---|---|---|
| S1 | `REG_PAGE` | 0xFF | target >> 8 | always | - |
| S2 | `HB_CTRL` | `HB_CTRL_CMD_GO` + `HB_CTRL_DATA_GO` | 0 (read-modify-write, other bits kept) | always | - |
| S3 | `HB_CTRL` | `HB_CTRL_NOINC` | 1 (read-modify-write) | always | - |
| S4 | `HB_TARGET` | 0xFF | target & 0xFF | kind != HB_CMDS | - |
| S5 | `HB_SRC_BANK` | 0xFF | src24 >> 16 | always | - |
| S6 | `HB_SRC_HI` / `HB_SRC_LO` | 0xFF | src24 bits 15:8 / 7:0 | always | - |
| S7 | `HB_LEN_HI` / `HB_LEN_LO` | 0xFF | len bits 15:8 / 7:0 | always | - |
| S8r | `OSD_FRAME_0A` | `OSD_HDOUBLE` | read only (one read, test the bit) | kind HB_OSD | - |
| S8 | `HB_GAP` | 0xFF | kind HB_OSD: hb_osd_gap(mode_dclk_khz(), OSD_HDOUBLE set ? 1 : 0); else 3 | always | - |
| S9 | `MCU_MAP` | `MCU_MAP_BURST_FROM_XRAM` | 1 (read-modify-write, set only) | from_xram | - |
| S10 | `HB_CTRL` | 0xFF | HB_CMDS: 0x10; HB_STEP: 0x08; HB_FIXED, HB_OSD: 0x28 (whole-byte write) | always | CPU stalls until done or an interrupt releases it |
| S11 | `HB_CTRL` | go bit of S10 | check = one read of `HB_CTRL`; while the go bit (0x10 for HB_CMDS, 0x08 otherwise) reads 1: restart = one read-modify-write setting the go bit (a second read, then one write); at most T2 checks | after S10 | - |
| S12 | `MCU_MAP` | `MCU_MAP_BURST_FROM_XRAM` | 0 (read-modify-write) | always | - |
- S10 values in bit terms: 0x10 = `HB_CTRL_CMD_GO`; 0x08 = `HB_CTRL_DATA_GO`; 0x28 = `HB_CTRL_DATA_GO` + `HB_CTRL_NOINC`.
  All other bits written 0 (including `HB_CTRL_NO_IRQ_RELEASE`: interrupts may release the stalled CPU).
- S11: an interrupt releases the CPU mid-burst with the go bit still 1; setting it again resumes the burst.
- S11 access list (measured on the reference image 2026-11-07, source of truth for the sequence): per busy check 1 read; per
  restart 1 more read and 1 write (written value = that read | go bit); the final non-busy check is 1 read, no restart.
  Total for N busy checks (N < 100): N+1 check reads, N restart reads, N restart writes. N >= 100: 100 check reads,
  99 restart reads, 99 restart writes, return 1. A single read serving as both check and restart read is NOT allowed.
- S8r: read once, after S7 and before the S8 write; only for HB_OSD. The page it lives on is addressed directly (no page select).
- S9: the reference also does the read-modify-write when from_xram is 0 (value unchanged); skipping it is allowed (no register effect).
- S9 happens only when from_xram is 1 (never clears the bit); S12 always clears it.
- S4 is not written for HB_CMDS (command items carry their own targets).

## 3. Barriers and commutative groups
- S1 first. Group G1 = {S2, S3} in that order. Group G2 = {S4..S9}: any order, after G1.
- Barrier: S10 after all of S1..S9. S11 after S10. S12 last.
- `.equiv`: `specs/reg.equiv` (HB_CTRL as action register: its write sequence is compared).

## 4. Timing
| what | value | source | tag |
|---|---|---|---|
| T2 restart limit | at most 100 busy checks / 99 restarts after S10 (still busy at check 100 -> return 1) | reference behaviour | vendor-value |
| burst duration | hardware; CPU stalled | - | - |

## 5. Data
D1: `hb_osd_gap(dclk_khz, hdouble)`, computed in 32-bit unsigned then 16-bit unsigned.
Domain: dclk_khz < 2^30 (1.07 THz; real clocks are < 1 GHz). Outside it: any result, but the call returns.
1. q = 12,109,500 / dclk_khz, integer division; dclk_khz = 0 -> q = 0xFFFFFFFF.
   (= 48,438,000 / (dclk_khz * 4) for every dclk_khz < 2^30: 48,438,000 is divisible by 4. The reference multiplies by 4 in
   32 bits and wraps at 2^30; that is real but unreachable, so the spec does not require it. Form 1 needs no 32-bit multiply.)
2. g = (q - 2) mod 2^16.
3. hdouble = 1 -> g = (2 * g) mod 2^16.
4. g > 0xFF -> 0xFF. Then g < 2 -> 2. Return g.
| constant | value | tag | source |
|---|---|---|---|
| item length in display clocks | 69 (57 + 4 per serial font byte x 3) | vendor-value | reference timing formula |
| M2PLL | 351 MHz (14.318 MHz x 49 / 2, rounded) | derived | board crystal + PLL setting |
| flash clock divider x MCU divider | 4 x 1 | vendor-value | reference clock plan (fast flash, no MCU speed-up) |
| 12,109,500 | 69 x 351 x 1000 x 2 / 4 | derived | the rows above (the /4 is the flash divider) |
- Vectors: `specs/vectors/osdgap.tsv`.

## 6. Oracle
- Host test with a recording mock that tells reads from writes (hooks `REG8_RD` / `REG8_WR`, section 7): for each kind and
  from_xram value, the access list must equal section 2 (reads included: S2, S3, S9, S12 read before they write; S8r for
  HB_OSD; S11 per its access list). Simulate busy: the mock returns the go bit set for the first N check reads after S10 (the
  restart read returns what the preceding check read returned) (N = 0, 1, 5, 99, 100, 200). The go bit is checked at most
  100 times; restarts = min(N, 99); return 1 iff N >= 100; S12 runs in every case.
- reg_*16/32/_n: access lists per section 1, including n = 0.
- `hb_osd_gap`: every row of `osdgap.tsv`.
- Measured, reference image: 32-bit writes go a, a+1, a+2, a+3, high byte first
  (trace_ddr_ours_2160p60, 2026-11-07, BE build, 0x00010100 -> 8A04..8A07 = 00 01 01 00).
- Mixed build: `trace_equiv.py` with `specs/reg.equiv` on 1080p60 and 2160p60 (D2 HDMI source).

## 7. Implementer task
- Files: `awto/reg/reg.c` (16/32/n access), `awto/reg/burst.c` (hb_burst, hb_osd_gap), `tests/host/test_reg.c`.
- `hb_burst` calls `mode_dclk_khz()` (declared in `mode.h`; the host test stubs it).
- Hooks: `awto/include/reg.h` defines `REG8_RD(a)` and `REG8_WR(a, v)` once (defaults: plain volatile XDATA read / write);
  `reg_rd`, `reg_wr`, `reg_rmw`, `reg_test` and every .c file use only these. Host tests predefine them to record reads and
  writes separately. No per-file hook definitions. (Header change: process owner.)
- Budget (hard limit, sdcc --model-large, CSEG bytes of the object file; no lookup tables):
  - `reg.c` <= 760 B: n-byte read/write 2 x ~190 B reference (measured 380 B in the image map AWT26110003-wb-port8-be,
    2026-11-07) + the five 16/32-bit helpers (no reference routine: inlined at call sites; measured 674-749 B total for the
    first implementation).
  - `burst.c` <= 450 B (reference burst routine 291 B + gap routine 158 B, same map). First implementation: 607-683 B.
- Size notes (measured, SDCC 4.6.4 mcs51 large): each 32-bit operation on XDATA values costs 30-60 B, so keep 32-bit work to
  the minimum: use form 1 of D1 (167 B vs 190 B), keep byte values in 8-bit variables, avoid helper layers that add a call
  and parameter copy per register write. Report per-function sizes if over budget.

## 8. Q&A
- 2026-11-07, Q1 (REG8 mock cannot tell read from write): the header carries `REG8_RD` / `REG8_WR` once (section 7). Remove the
  per-file `REG8_WR` fallbacks.
- 2026-11-07, Q2 (OSD frame read missing): added as S8r, read after S7 and before S8, HB_OSD only.
- 2026-11-07, Q3 (S11 one read or two): two reads per restart (check, then the RMW's own read). See the S11 access list.
- 2026-11-07, Q4 (dclk_khz * 4 wraps at 2^30): real in the reference, unreachable; D1 now defines the domain (< 2^30) and
  the equivalent form 1 (12,109,500 / dclk_khz). Vectors unchanged (max 7,000,000).
- 2026-11-07, Q5 (size): budgets re-based in section 7.
