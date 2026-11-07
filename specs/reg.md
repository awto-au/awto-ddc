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
| S8 | `HB_GAP` | 0xFF | kind HB_OSD: hb_osd_gap(mode_dclk_khz(), OSD_HDOUBLE set ? 1 : 0); else 3 | always | - |
| S9 | `MCU_MAP` | `MCU_MAP_BURST_FROM_XRAM` | 1 (read-modify-write, set only) | from_xram | - |
| S10 | `HB_CTRL` | 0xFF | HB_CMDS: 0x10; HB_STEP: 0x08; HB_FIXED, HB_OSD: 0x28 (whole-byte write) | always | CPU stalls until done or an interrupt releases it |
| S11 | `HB_CTRL` | go bit of S10 | while the go bit (0x10 for HB_CMDS, 0x08 otherwise) reads 1: set it again (read-modify-write); at most T2 times | busy after release | - |
| S12 | `MCU_MAP` | `MCU_MAP_BURST_FROM_XRAM` | 0 (read-modify-write) | always | - |
- S10 values in bit terms: 0x10 = `HB_CTRL_CMD_GO`; 0x08 = `HB_CTRL_DATA_GO`; 0x28 = `HB_CTRL_DATA_GO` + `HB_CTRL_NOINC`.
  All other bits written 0 (including `HB_CTRL_NO_IRQ_RELEASE`: interrupts may release the stalled CPU).
- S11: an interrupt releases the CPU mid-burst with the go bit still 1; setting it again resumes the burst.
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
D1: `hb_osd_gap(dclk_khz, hdouble)`, computed in 32-bit unsigned then 16-bit unsigned:
1. q = 48,438,000 / (dclk_khz * 4), integer division; dclk_khz = 0 -> q = 0xFFFFFFFF.
2. g = (q - 2) mod 2^16.
3. hdouble = 1 -> g = (2 * g) mod 2^16.
4. g > 0xFF -> 0xFF. Then g < 2 -> 2. Return g.
| constant | value | tag | source |
|---|---|---|---|
| item length in display clocks | 69 (57 + 4 per serial font byte x 3) | vendor-value | reference timing formula |
| M2PLL | 351 MHz (14.318 MHz x 49 / 2, rounded) | derived | board crystal + PLL setting |
| flash clock divider x MCU divider | 4 x 1 | vendor-value | reference clock plan (fast flash, no MCU speed-up) |
| 48,438,000 | 69 x 351 x 1000 x 2 | derived | the rows above |
- Vectors: `specs/vectors/osdgap.tsv`.

## 6. Oracle
- Host test with a recording REG8 mock: for each kind and from_xram value, the access list must equal section 2
  (reads included: S2, S3, S9, S11, S12 read before they write). Simulate busy: mock returns the go bit set for the first
  N busy-checks after S10 (N = 0, 1, 5, 99, 100, 200). The go bit is checked at most 100 times; a check that reads busy
  is followed by a restart only while fewer than 99 restarts were done -> restarts = min(N, 99); return 1 iff N >= 100.
- reg_*16/32/_n: access lists per section 1, including n = 0.
- `hb_osd_gap`: every row of `osdgap.tsv`.
- Measured, reference image: 32-bit writes go a, a+1, a+2, a+3, high byte first
  (trace_ddr_ours_2160p60, 2026-11-07, BE build, 0x00010100 -> 8A04..8A07 = 00 01 01 00).
- Mixed build: `trace_equiv.py` with `specs/reg.equiv` on 1080p60 and 2160p60 (D2 HDMI source).

## 7. Implementer task
- Files: `awto/reg/reg.c` (16/32/n access), `awto/reg/burst.c` (hb_burst, hb_osd_gap), `tests/host/test_reg.c`.
- `hb_burst` calls `mode_dclk_khz()` (declared in `mode.h`; the host test stubs it).
- Budget: reg.c <= 250 B, burst.c <= 350 B code (sdcc --model-large). No lookup tables.

## 8. Q&A
