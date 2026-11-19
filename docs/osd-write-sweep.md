# OSD write-rate sweep and OSD clock knobs

Status 2026-11-19: Phase A (firmware op, host tool, sim proof, regdb search), Phase B (unit 3 sweeps, results below) and Phase C (DDR PLL steps to +5 %, outcome below) done.
Tags: `[hw]` measured on unit 3, `[regdb]` `re/regdb/RTD2795T-CG.tsv.gz`, `[sdk-hypothesis]` SDK claim, `[sim]` fw_sim, `[?]` unknown.
Related: [timing.md](osd/timing.md), [saver-fps-hw.md](saver-fps-hw.md) (levers T-H / T-K / T-M), [clock-sweep.md](clock-sweep.md), [path-cost.md](osd/path-cost.md).

## Baseline and result [hw]
- Direct triples were 1.08 us/B at MCU 350.8 MHz with flash 70.2 MHz (docs/clock-sweep.md), 2.16 at 175.4, 3.79 at stock 87.7.
- Default image since 2026-11-19 (MCU 350.8 / flash 116.9 MHz): direct triples 0.385 us/B, direct loop 0.348, `ScalerOsdDataPort` 1.391, B1-only 0.215 per byte-equivalent (one store per word), `bit_block` on 0.385, address set 4.5 us each; unit 3, 1848 B x 73 passes, read-back clean.
- Closed: the 2x gap between the sim (0.54 us/B, cycle model) and the old hardware figure (1.08) was flash-fetch bound. Raising the flash clock from 70.2 to 116.9 MHz took hardware to 0.385 us/B, under the sim. None of `FFF1`, `FFFB`, `FFBC` was involved.
- Register sweep (direct triples, us/B; 0 bad bytes M1 and M2 in every row; no FIFO / STATUS0 flag):
  - `FFF1` sel 0 0.385, 1..5 0.378, 6..8 0.385, 9..11 0.393, 12..13 0.400, 14 0.408, 15 0.415; `burwr_func_int_sel` 1 0.378. Higher sel only slows. Default sel 12 and no port nops: `docs/osd-port-loss.md`.
  - `FFFB` 0, 1, 2, 3, 4, 6, 8, 16, 32, 64, 128, 255: 0.378 to 0.385 (stock 0x28 = 40): no effect.
  - `FFBC` 31, 24, 16, 15, 8, 4, 2, 1, 0: 0.378 to 0.385: no effect on a timed write.
  - State flags (EA off, scale-up off, overlay off, `0x93[7]` on): 0.378 to 0.385. N 1848 / 3696 / 8184: 0.378 / 0.376 / 0.374.
  - Combinations of the best single values: 0.378 (no gain). No register combination beats stock.
- Burst XRAM -> port (SDK sequence, one 54 B glyph per burst, setup included), by `FFFB` gap: 40 -> 0.341, 32 -> 0.294, 24 -> 0.247, 16 -> 0.200, 14 -> pass, 12 -> 0.180 (3 of 3 clean), 11 -> 0.167 (3 of 3), 10 -> 0.167 (1 of 3), 9 -> 0.160 (fails 1 to 2 bytes), 8 -> 0.154 (26 bad), 3 -> 0.127 (253 bad). Smallest reliable gap 11 to 12; the SDK formula gives about 18 at 4K60 [sdk-hypothesis]. Best passing: 0.180 us/B at gap 12 = 2.1x direct triples; with EA off at gap 3 it still fails.
- Held with the savers running (heartbeat vs host clock +-0.3 %, 100 link reads, Scope 2): best values and `FFBC` 14 / 12 healthy, Scope 2 31.1 frames/s unchanged.
- HAZARD `FFBC`: held at 10 or lower the debug link stops answering (10, 8 no answer; 6, 5 link lost); the firmware restored the register at its hold limit and the unit came back 12/12. Reset value 0x0F: do not lower it. (regmap row FFBC.)
- Reads of PHY-page registers (0x88xx, 0xC8xx) and the FIFO status pages: a read at a new address returns the previous read's data; the second read of the same address is right (MCU and debug slave). The firmware sweep reads them twice (`AwtoRegRd2`); the FIFO flags of the first OSD sweep run (before 2026-11-19 06:17) were single reads and are not evidence.
- Nothing adopted into the default build.

## Tool
- Firmware: `g_stAwtoOsw`, `AwtoOswRun` / `AwtoOswPoll` in `fw/test/testcmd.c`, `-D _AWTO_OSD_HWTEST` only (build: `./dev.py build --unit 3 --tag T -D _AWTO_OSD_HWTEST`).
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

## Phase C: DDR PLL clock steps (Dan 2026-11-18: DDR only, relative steps; run 2026-11-19 on unit 3)
- Scope: DDR PLL only. Not touched: display PLL (DPLL block `0x00F5..0x00FF`), panel timing, dclk.
- Model, high confidence for the ratio: `F_pll = F_xtal / (pdiv + 1) x (N + 2 + F / 8192)`.
  - Sources: regdb text of `reg_n_code_` (0x882B), worked example 13.5 MHz x (116 + 2 + 4247 / 8192) = 1.6 GHz [regdb]; SDK `ScalerPLLSetDDR2PLLFreq` computes N and F the same way [sdk-hypothesis]; live registers, both channels: N 81, F 6639, `reg_pdiv` code 0 (Div1) -> 14.318 x (81 + 2 + 6639 / 8192) = 1200.00 MHz = the project's `_DDR2_MEMORY_CLK_1200M_SUPPORT` option [hw + build option, independent of the formula's source].
  - One code unit = 1.748 kHz = 0.000146 %; 0.5 % = 3432 units. Whether 1200 MHz is the data rate or the clock does not matter for relative steps.
  - Would falsify: a PHY or frame-path observable that does not follow the code (see result), or a different pdiv / reference than assumed.
- Tool: firmware `g_stAwtoDdr` (HWTEST), host `scripts/ddr_clk_sweep.py` (`read`, `run`; log `tmp/logs/ddr_clk_sweep.log` / `.tsv`).
  - Op sets a signed delta from the stock code on both channels (F first, then N; transient within one N unit = 1.2 %); envelope +-5 %, `AWTO_DDR_F_OVERRIDE` / `--ddr-override` doubles it; refuses when the stock N of A and B differ by more than one; restores by itself 30 s after the last set (host re-arms each rung); sim proof: apply, refuse above the envelope, override, revert, auto-revert at a 400 ms hold.
  - Per rung: settle 0.5 s, DDR read-path flags (`ddr_sweep.py` `Phy.measure`, VALID_WIN_DET + INT_STATUS1, A and B, worst of 3 clears), FIFO / STATUS0 flags, heartbeat, link reads, `./dev.py health` (12/12). Failing rung: revert, one retry from stock; stop after 3 reproducible failures or at the first lost link / health failure.
- Result 2026-11-19: stock, -0.5 % (control), +0.5 % to +5.0 % in 0.5 % rungs all PASS; flags at every rung equal to stock (VALID_WIN_DET 1 of 8 on both channels, INT_STATUS1 0 of 8, `cal` bytes `00 05 05 05`); health 12/12 at every rung; heartbeat 0.9997 to 1.0007. Registers read back as written (e.g. +5 %: N 86, F 7 on both channels = 1260.0 MHz modelled). Reverted to stock N 81 / F 6639 at the end.
- Not validated: no PHY or controller state followed the code. A full `ddr_sweep.py state` diff (74 lines, stock vs +2.5 % vs +5 % held) shows no difference. The PLL may only re-lock through the SDK's reset sequence (`0x8837` `rst_n`, SDK de-asserts reset after writing N / F), or the change is below what the read-path flags and calibration show. There is no clock counter (the DDR PHY speed sensor needs the PHY clock; `docs/clock-sweep.md`) and no frame-buffer capture, so "the DDR clock moved" is not demonstrated; only "the code was accepted and nothing broke".
- To close it: a PLL reset-sequence step (stop and restart the DDR clock = risk to frame-buffer contents; needs its own go) or a counter on the DDR clock. Not done.
