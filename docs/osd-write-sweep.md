# OSD write-rate sweep and OSD clock knobs

Status 2026-11-18: Phase A (firmware op, host tool, sim proof, regdb search) done; Phase B (unit 3 measurements) and Phase C (DDR clock) not run.
Tags: `[hw]` measured on unit 3, `[regdb]` `re/regdb/RTD2795T-CG.tsv.gz`, `[sdk-hypothesis]` SDK claim, `[sim]` fw_sim, `[?]` unknown.
Related: [timing.md](osd/timing.md), [saver-fps-hw.md](saver-fps-hw.md) (levers T-H / T-K / T-M), [clock-sweep.md](clock-sweep.md), [path-cost.md](osd/path-cost.md).

## Baseline [hw] (docs/clock-sweep.md, `tmp/logs/clk_sweep.log`)
- Direct triples: 1.08 us/B at MCU 350.8 MHz, 2.16 at 175.4, 3.79 at stock 87.7; `ScalerOsdDataPort` 3.79 us/B at 175.4.
- Sim (this image, cycle model, no register effects): direct triples 0.54 us/B at 350.8 MHz, `ScalerOsdDataPort` 1.62 us/B.
  - Hardware is 2.0x the CPU-cycle model for direct stores: ~0.54 us/B of bus wait is not in the model [?]; Phase B tells which register owns it.

## Tool
- Firmware: `g_stAwtoOsw`, `AwtoOswRun` / `AwtoOswPoll` in `fw/test/testcmd.c`, `-D _AWTO_OSD_HWTEST` only (build: `./dev.py build --unit 3 --tag T -D _AWTO_OSD_HWTEST "--fw-args=--xdata-floor 0"`; XDATA free 430 B, below the 700 B floor, so the floor is off for this image).
- Host: `./dev.py osd-sweep --unit 3 [--sim] [--continue-on-fail] GROUP...` -> `scripts/osd_sweep.py`; log `tmp/logs/osd_sweep.log`, TSV `tmp/logs/osd_sweep.tsv` (`--sim`: `osd_sweep_sim.tsv`). Tests `tests/test_osd_sweep.py`.
- One case = one fw op: apply FFF1 / FFFB / FFBC, time `ucReps` passes of N bytes with one write path (AwtoMs, target 150 ms), restore the three registers, return. The host then reads M1 and M2 back (recipe: circuit off, scale-up off, overlay off, `0x3A33[4]`, two reads) at the restored values and compares with the pattern (54 B LFSR chunk repeated, `F_REPEAT` shape).
- Pass = 0 bad bytes M1 and M2, registers read back as requested, registers restored (checked by a no-apply op after every case), no new FIFO / sync flag, op inside its limit.
- Targets: unused top of the OSD SRAM only (words 0x2000..0x2FFF), N <= 8192 B per pass.

## Safe by construction
| rule | value | reason |
|---|---|---|
| registers touched | FFF1 bit 7 + [3:0], FFFB, FFBC[4:0] | the candidates [regdb]; reserved bits kept |
| restore | in the same op, before it returns | no state survives an op |
| HOLD op (setting held while savers run) | fw restores at `usHoldMs` (host: 25 s, fw cap 30 s) | host crash cannot leave a setting on; `autorevert` group proves it with a silent host |
| stalled main loop | WDT reset (586 ms) = reset values | measured on the clock sweep |
| timed section | fw stops after the pass that exceeds 1000 ms, state TIMEOUT | host plans 150 ms; limit 1.25 x (1000 ms + one worst pass 45 ms) + 250 ms fixed |
| refusals | fw and host both: FFF1 > 0x8F, FFBC > 31, N > 8192 or not x3, address outside the top, burst chunk not 54 / 162 or not a divisor of N | |
| burst | XRAM source 162 B (3 glyphs), <= 100 restarts per burst, WDT kicked per chunk | SDK sequence [sdk-hypothesis], behaviour judged by read-back |
| FIFO flags | read before and after, never cleared | clearing is outside the register envelope |
- `FFBC` = 0 (meaning undocumented) is the last case of its sweep.
- Sim proof (`--sim`, image osw1): all groups, 85 cases, 0 failed; registers applied and restored; `autorevert` restores 300 ms hold with the host silent; burst XRAM -> port verified through the OSD model. The sim does not model the registers' effect, so its us/B is the same for every value.

## Groups
| group | cases | question |
|---|---|---|
| base | SDK, direct, triples, B1 only, bit_block on, address set only, burst 54 / 162 | cost per path at the default clock |
| fff1 | `mcu_wr_sca_intrvl_sel` 0..15, `burwr_func_int_sel` 1 | minimum cycles between continued scaler writes = 4 + 4 x sel |
| fffb | `sca_inf_period` 0, 1, 2, 3, 4, 6, 8, 16, 32, 64, 128, 255 | per-access halt TI = SYS_PERIOD x 2 x value |
| ffbc | `mcurd_max_cycle` 15 (reset), 16, 24, 31, 8, 4, 2, 1, 0 | clock-gating limit on reads |
| burst | chunk 54 / 162 x FFFB gap 1..40 | smallest gap with 0 bad bytes (T-H) |
| state | EA off, scale-up off, overlay off, `0x93[7]` double buffer on, SDK + EA off, burst + EA off | OSD circuit states vs write cost |
| size | N 1848 / 3696 / 8184 triples, 1848 / 8184 SDK, burst 1782 / 8100, address sets 100 / 1000 | per-byte vs fixed cost |
| combo | pairs and all three best single values (read from the TSV), plus burst 162 with them | best passing combination |
| hold | best values held 25 s: heartbeat vs host clock (+-1.5 %), 100 link reads, Scope 2 frames/s | main loop / DDC / link healthy |
- Not swept as registers: CKCON MOVX stretch (already 2 cycles, the minimum), `bytesel` modes beyond B1 (B1 case covers the plane saving), address auto-increment off (`FFF3[5]` is used by the burst).
- Phase B order: base, fff1, fffb, ffbc (one at a time) -> burst -> state -> size -> combo -> hold -> autorevert. Stop on the first failed case; one retry of a failed case before it counts.

## Disturbance detection (Scope 2 tile garble)
- Automatic: SRAM read-back errors (data corruption), FIFO flags (disp / cap M1 / M2 underflow, overflow; STATUS0 ivs / ihs error), sync-log frame counters, `hold` heartbeat.
- Not automatic: a transient scan glitch while the MCU writes (T10 in [timing.md](osd/timing.md)). The OSD read side runs on the dclk-gated OSD clock and the write side on the scaler register bus; the SRAM is dual-ported, so a write collision shows only as a one-pixel-row glitch, which no register reports [?].
- Phase B visual items (no waiting for Dan): after the numeric sweep, for each candidate that passed (best single values and the best combination) run `osd-hw-test cycle` (T10 ladder, 8 s per variant) with the setting held (`hold` window), log the exact setting and wall time, and leave the last ladder on screen. List in the final report: setting, log time, what a glitch looks like (digits 2 / 3 / 4 glitch, 1 / 5 clean = write-during-scan).

## OSD clock knobs (regdb search, read-only so far)
| knob | register | range | verdict |
|---|---|---|---|
| OSD clock gate | `0x01DC[3]` osd_clken (DCLK_GATED_CTRL2) | 0 / 1 | on / off only; the OSD clock comes from the display clock domain; no divider or select exists [regdb] |
| OSD SRAM write side | scaler register bus, set by MCU clock + FFF1 / FFFB / FFBC | this sweep | the only rate knobs on the write path |
| M-domain FIFO clock | `0x0022[1:0]` fifo_clk_sel (MPLL / ICLK / DCLK / M2PLL), `0x37A0[3]` m2pllck_gated | 4 values | feeds the DDR frame-buffer FIFOs, not the OSD [regdb]; not a write-path knob |
| OSD BIST clocks | `0x3A90`, `0x3A92`, `0x3ACE` bist_clk_en | 0 / 1 | test logic, no rate |
| window / font / scale-up engines | none found | - | no clock field in `0x3Axx`, `0x3Axx` window words or `OSD_SU_*` |
| display PLL (DPLL block 0x00F5..0x00FF) | not touched | - | dclk: out of scope by instruction |
- Conclusion: the OSD cannot be overclocked; it has a gate and no divider. Its pixel side follows dclk (display clock), which is off limits. The tunable part is the MCU-to-SRAM write path (this sweep) and the MCU clock (docs/clock-sweep.md).
- Implication for T10: reads (scan) at dclk, writes at the MCU / scaler bus clock; two different clock domains on one SRAM. Whether the SRAM is dual-port or arbitrated is not in the regdb [?]; T10 plus the sweep's `state` group (scale-up off, overlay off) are the tests.

## Phase C: DDR clock sweep (instruction 2026-11-18; run only after Phase B, needs a separate go to touch the unit)
- Scope: DDR clock only. No display PLL (DPLL block `0x00F5..0x00FF`), no panel timing, no dclk. Why: scaler memory bandwidth may limit the picture / scale-up path at 4K.
- Knobs [regdb, `0x88xx` DDR PHY PLL page; channel B mirror at `0xC8xx`]: `PLL_SSC1` `reg_f_code` (`0x8826/27`) and `PLL_SSC2` `reg_n_code` (`0x882B`) set the fractional PLL ratio; `PLL_CTRL3_2` `reg_pdiv`; `0x3780` / `0x37C0` `clken_ddrphi`. The project already builds `_DDR2_MEMORY_CLK_1200M_SUPPORT = _ON` (DDR PLL 1200000 kHz from the code table, `docs/delays.md` "DDR2 freq 2 x 150 us") [sdk-hypothesis].
- First step (read-only): `scripts/ddr_sweep.py state` + `base` to log the live PLL registers and flags; derive the stock ratio and the step size per `f_code` LSB from the registers, not from the SDK.
- Sweep: stock +1, +2, +3 % in small steps (hard envelope +3 % absolute unless the named flag `--ddr-override` is given), each step: write the ratio in the SDK's order [sdk-hypothesis] with the two 150 us waits, settle 200 ms (`ddr_sweep.py` SETTLE_S), read VALID_WIN_DET and INT_STATUS1 per channel (A pages 8E / 8F / A0, B CE / CF / A8), FIFO flags, sync-log frame counters, `./dev.py health`; leave a labelled pattern for the later look; revert at the hold limit; WDT backstop.
- Stop rules: revert at once on any flag change or lost link; retry a failing step once; stop after 3 reproducible failures.
- No frame-buffer capture path exists (no HDMI capture on the host side of unit 3): integrity = flags + counters + health; the visual check is left for Dan.
- Firmware op and host tool for this phase are not written yet: they follow Phase B and its go.
