# Read-behind: internet + SDK + local research (2026-11-19, read-only, no hardware)

- Problem: 22 pages (88 8A 8B 8E 8F 90 A0 A3 A4 A6 A7 A8 AB AC AE AF C8 CA CB CE CF D0): first read of a new aligned dword returns the previous dword's same-lane byte; later lanes right; no time dependence 0..1000 ms (`re/regmap/README.md` "Read-behind", `re/regmap/read_behind.tsv`).
- Tags: [regdb] [databook] [sdk] [sdk-mirror] [hw] [web] [gpl-code] [guess]. Confidence: H / M / L.
- No hardware used. No GitHub writes. Vendor files read in place (`/vendors/realtek/analysis`), nothing copied.

## 1. Headline findings

| # | finding | source | tag / conf | implies | test |
|---|---|---|---|---|---|
| 1 | `0x3780` DC_PHY_CLK_SET_A[5] `rbus_a_rd_no_async` / `0x37C0[5]` B: "RBUS read signal sync by eclk_scalar_rw or not? 0: sync by MCU RW clock; 1: no sync (default & suggestion, this option can avoid to read the previous data)". Same bit on RTD2776B / 2797UPM (`rbus_rd_no_async`). | `re/regdb/RTD2795T-CG.tsv.gz`, `RTD2776B`, `RTD2797UPM` | [regdb] H | Realtek names our exact symptom ("read the previous data") on the DC_PHY RBUS read path and ships a fix bit. Live value 3780 = 0x31, 37C0 = 0x31 (bit 5 = 1): the fix is already on and the artifact persists. So the bit is necessary but not sufficient, or does not cover the page set. | T5 (control), T4 |
| 2 | `0x3790[6:5]` M_DOMAIN_MCLK_SET_A `clk_sys_a_div_sel` (B: `0x37D0`): "dc_phy register R/W clock: 00 bypass, 01 /2, 10 /4, others /2". Live 3790 = 0xB7, 37D0 = 0x37: both = 01 (/2). | regdb (above); `re/regmap/regs.tsv` obs `B7` / `37` | [regdb][hw] H (value) / M (relevance) | The DC_PHY / DC_SYS register bus runs at half clock. Bypass (00) halves its latency; a slow register clock would explain a fetch that completes after the MCU's capped wait. Never written by the SDK. | T4 |
| 3 | `FFBC[4:0]` `mcurd_max_cycle` text: "Limit the maximum cycles of clock gating when execute reading **Mout**". "Mout" is not defined anywhere in the regdb. All 22 pages are the memory (M) domain (DC_SYS / DC_PHY, DDR controller and PHY); pages in the same range that read clean (89 8D 91 A1 A2 A5 A9 AA AD) were not checked against the regdb page names (guess: not DC data-path pages). | regdb FFBC; `read_behind.tsv` | [regdb] H (text) / [guess] L (Mout = M-domain output) | Reading is stalled by clock gating for at most N MCU cycles, then the MCU takes whatever is on the bus. If M-domain RBUS reads need more than 15 cycles, the MCU takes the old latch: matches "first read of a new dword stale, repeat right". Also matches the hazard: <= 10 starves even fast-page reads (docs/osd-write-sweep.md), so 15 has little headroom. | T3 |
| 4 | FFBC is counted in MCU cycles; MCU went 87.7 -> 350.8 MHz as the default on 2026-11-19 (4x); read-behind was found the same day. The probe MCU clock is not recorded in `read_behind.tsv`. The 350.8 MHz default also surfaced an AUX FIFO "longer / stale reply" (docs/clock-sweep.md). | `docs/clock-sweep.md`, `re/regmap/read_behind.tsv` (no clock column) | [hw] M | If the artifact is absent or rarer at 87.7 MHz, the cap is a cycle-count problem (FFBC / FFFB / stretch are the right knobs) and the SDK never saw it. If identical, the latch is read-triggered by design and only a helper (or a different path) fixes it. | T2 (first) |
| 5 | The live reads are MCU MOVX reads in the EXINT1 ISR: `fw/diag/dbgisr.c` `*(volatile __xdata BYTE*)(hi<<8 | lo)`. So the MCU-side knobs (FFBC, FFFB, CKCON stretch, FFEE) apply to the live path; the ISP path (MCU halted, hardware reads) is outside them, and it shows the artifact at a lower rate and not on A* pages. | `fw/diag/dbgisr.c`; `re/regmap/README.md` | [sdk][hw] H | FFBC cannot explain the ISP-path artifact; the ISP result points at a hardware wait that is fixed (A* clean, 88..90 / C8..D0 not) and at 3780 / 3790 style clocks or the dcu bus. Two mechanisms may be stacked. | T4, T7 |
| 6 | The SDK's own debugger reads through the indirect port, not MOVX: `ScalerDebug` case 0x41: `FFF3 |= 0x20; FFF4 = addr; r = FFF5`. Page select through `P0_9F` (`ScalerSetByte(P0_9F_PAGE_SEL, HIBYTE(...))` in burst write). This is the 2005-era "scaler interface" (`CScalerRead`: `FFF3`, `FFF4`, `FFF5`, no dummy read). | `fw/sdk/.../ScalerCommonDebug.c:523-530`, `ScalerCommonBurstWrite.c`; [gpl-code]/proprietary old RTD2660 `RTDAccess.c` (below) | [sdk] H | A second, hardware-handshaked read path exists (FFF5 read halts the MCU for the interface time + FFFB period). Never tried on these pages. | T6 |
| 7 | `FFFB` `sca_inf_period`: "interval between two commands TI = SYS_PERIOD x 2 x value; it will halt MCU extra time TI in normal access". Reset 0x02. Live values 0x14 / 0x28 / 0x03 across scans: the SDK burst-write helper sets 0x03 (or an OSD-computed value) and never restores it. | regdb; `ScalerCommonBurstWrite.c:84-100`; `re/regmap/regs.tsv` FFFB row obs | [regdb][sdk][hw] H | The read-time FFFB is state-dependent (depends on whether a burst ran before). The OSD write sweep tested FFFB on writes only; the read artifact was never correlated with FFFB at the time of the read. | T6b |
| 8 | CKCON stretch (MD2..0, SFR 8Eh): databook default 1 (3-cycle MOVX), "for full-speed data memory access set 0"; strobe width 2 clk (stretch 0) .. 28 clk (stretch 7), "gives the peripheral more time to respond". SDK sets stretch 0 (`_CKCON_MOVX_DEFAULT_CYCLE = _CKCON_MOVX_2_CYCLE`). | `/vendors/realtek/analysis/rl6449-dw8051/DW8051-databook.txt` 2273-2330; `ScalerMcu.c:142`; `ScalerCommonMcuCommonInclude.h:32` | [databook][sdk] H | The SDK runs MOVX at the fastest strobe, so the read strobe is as short as the core allows. Whole-firmware stretch 7 was tried for the 350.8 MHz AUX problem (no effect there), never for read-behind. | T8 |
| 9 | `FFF0[7]` `extmcu_regrw_div`: "In external MCU mode: eclk_scalar_rw = eclk_ng or eclk_ng / 4". `FFEE[6]` `mcu_peri_non_stop`. Both 0 live. | regdb | [regdb] M | ISP is the external-MCU mode; eclk_scalar_rw is the clock named in finding 1. Only relevant to the ISP-path artifact. | T7 |
| 10 | The SDK never writes FFBC, 3780, 3790, 37C0, 37D0 (declared only). No SDK file reads a PHY page twice; `ScalerGetByte` / `ScalerGetDWord` are plain MOVX (`*((volatile DWORD xdata *)(usAddr))`). The parked DDR3 code reads PHY status once (`ScalerGetDWord(PAC_04_WL_CTRL_11)` in the write-level check) with `DELAY_5US()` only around DMA commands. | grep `fw/sdk`, `fw/sdk-parked`; public mirror below | [sdk] H | Either Realtek's firmware never hit it (87.7 MHz MCU, different timing) or never read these pages in a way that shows it. Neither is evidence the artifact is intended. | T2 |
| 11 | Dahua firmware (jxc-4k, Ghidra constant-address export): writes `FFEE` (flash clock group, `|= 0x40`), reads/writes `FFF4` (timer ISR) and `FFFB` 0x02 / 0x03 (`spi_flash_read_engine`); no static write to `FFBC`, `0x3780 / 3790 / 37C0 / 37D0`; no constant-address access to any of the 22 pages in `regreads.tsv`. | `/vendors/realtek/analysis/jxc-4k/bank*/regwrites.tsv`, `regreads.tsv` | [hw-RE] M (static, constant addresses only) | The shipped firmware keeps the reset values and probably never touches the PHY pages after boot (DDR set up by the boot path / a table); no double-read idiom to copy. | none |
| 12 | `FFF3[0]` `page_addr_map`: "1: XFR can only be accessed by SCA_INF_ADDR / SCA_INF_DATA". Live FFF3 = 0xA0 / 0x60 (bit 7 reg_read_en; bit 5 addr_non_inc left set by the burst helper), bit 0 = 0. Old-SDK `SysTimer` ISRs save / restore FFF4 ("Backup for Burst Write Bug"); our own measurement: direct reads leave FFF4 unchanged (regmap FFF4 row). | regdb; `SysTimer.c:365-525`; regmap | [regdb][sdk][hw] H | `page_addr_map` is a global switch of the read path; with it on, only the FFF4/FFF5 interface works (kills the MOVX debug link: risky). T6 uses the interface with the map left off. | T6 |

## 2. Internet (A)

- Method: `gh search code|repos|issues`, playwrong search + fetch (DuckDuckGo). gh code search hit the 10/min limit after one burst of 28 calls (my error): later gh queries were reduced. Not done: GitLab, Codeberg, sr.ht, Bitbucket, SourceForge, grep.app (no usable search endpoint reached; absence is not shown there).
- Result: no public statement of this artifact. A failed search is not proof of absence.

| query / place | result | tag |
|---|---|---|
| gh code `mcurd_max_cycle` | only `awto-au/awto-ddc` (this repo) | [web] |
| gh code `MCU_FFBC_CYCLE_GATING` | `Kingdomwhisky/RTD-Scaler-TEST` (RL6449 / RL6369 / RL6432 / RL6463 / RL6492 / RL6410 SDK headers + `*_Mcu.c`): same Realtek SDK as `fw/sdk`; declaration only, no write to FFBC in any file | [web][sdk-mirror] |
| gh code `rbus_rd_no_async`, `rbus_a_rd_no_async`, `clk_sys_a_div_sel`, `DC_PHY_CLK_SET` | no hit (the regdb TSVs are not public) | [web] |
| gh code `CScalerRead dummy`, `ScalerGetByte read twice` | no hit | [web] |
| gh repos `RTD2660/2662/266x/2556/2795/2785/RL6449` | RTD2660/2662 hobby stack: `KerJoe/ORTD2662` (custom firmware, GPL-style), `danyaPostfactum/RTD2660`, `avtehnik/RTD2662`, `gamelaster/RTD2662`, `ergoz/RTD2660_PCB800099` (leaked Realtek 2005 sources), `adafruit/Adafruit_RTD266x_Firmware`, flashers (`ghent360`, `static-void`, `floppes`, `KerJoe/RTDMultiProg`), RTD2556 dumps; `naorunaoru/rtdflash`. No RTD2795 / RL6449 firmware project besides the SDK mirror | [web] |
| `danyaPostfactum/RTD2660 Core/code/mcu/RTDAccess.c` (fetched) | `CScalerRead` = `FFF3 = 0x20/0; FFF4 = addr; loop { *p++ = FFF5 }`: no dummy read, no wait, in the 2005 RTD2660 family. Realtek copyright, no open licence: read, not copied | [web][guess licence: proprietary leak] |
| `KerJoe/ORTD2662 peripherals/xsfr.h` (fetched) | XFR window `0xFF00 | reg`, F3/F4/F5 scaler interface, `SCALER_PERIOD` 0xFA named "scaler access delay" (our FFFB): no read-twice remark. The RTD266x has no DDR PHY pages | [web][gpl-code] |
| bitbuilt.net worklog ORTD2662 (fetched) | no register-read quirk mentioned | [web] |
| DuckDuckGo: "RTD2662 ... read twice / dummy read", "RTD2795 / 2785 / 2796 firmware RE", "DC_PHY_CLK_SET / rbus_rd_no_async / mcurd_max_cycle", "ISP read first read old data" | no exact-phrase hit; relaxed results unrelated (datasheet portals, CSDN reference-design posts, Linux RTD1625 clk patches) | [web] |
| DW8051 databook / Keil data sheet (search) | stretch values: same content as the local `DW8051-databook.txt` | [web][databook] |

- Implication: nothing public to copy; the Realtek regdb (finding 1-3) is the only first-party hint and it is local.
- Unchecked leads: leaked RL6449 / RTD2795 SDK trees beyond the one mirror (no PHY-page helper seen in the mirror's headers); Chinese reference-design posts (CSDN / elecfans) list the chip but no register notes; grep.app / SearchCode for `rbus_rd_no_async`.

## 3. Local sweep (B): what was missed before

- Never written anywhere (SDK, firmware, Dahua static): `FFBC`, `0x3780`, `0x3790`, `0x37C0`, `0x37D0`. The first four of those five were not on the candidate list in `issue-readbehind-cause.md`; `FFBC` was (H1).
- The regdb text for `rbus_a_rd_no_async` was not read against the symptom: it states the symptom and the fix, and the fix is already on (0x31).
- CKCON stretch was ruled out for the AUX bug only; it was never run through `reg_behind_probe.py`.
- Probe MCU clock not recorded per row: the 87.7 vs 350.8 comparison does not exist yet.
- FFFB / FFF3 state at read time not recorded in probe rows (FFFB changes with the last burst: 0x03 vs 0x28 vs 0x14; FFF3 0xA0 vs 0x60).
- The SDK debug read (FFF3[5] / FFF4 / FFF5, page via `P0_9F`) was never tried on the 22 pages.
- `/mnt/2tb/git/awto-ddc-prestrip` (tag pre-strip-209) does not exist on this machine: no stripped-code check possible. In the current tree no helper other than `AwtoRegRd2` / `dbg_xdata.BEHIND_PAGES` handles it.
- `fw/rtdfw/facts/regs/p37.h`, `pff.h`: names only.
- Regdb fields containing "read" on the 22 pages: DDR PHY debug / BIST flags and `wrlvl_rddata` (DQ readback, values depend on a prior wrlvl enable, so some `other`-class values may be real state, not latch). No description mentions a read latency, dummy read or latch on those pages.

## 4. Ranked tests for the FFBC-family experiment (all test unit only, one change at a time, restore after, link / heartbeat checked, read-only otherwise)

Success = `scripts/reg_behind_cause.py --pages A0,8E` first-read ok 0 -> 12 of 12 (and `reg_behind_probe.py` wrong rate), on the byte path and the block path.

| rank | id | change | prediction if it is the cause | cost / risk |
|---|---|---|---|---|
| 1 | T2 | None: run the probe on the clk87 build (MCU 87.7 MHz) and on 350.8; record the clock in the row | rate falls at 87.7 -> cycle-count cap (T3 / T6b / T8 are the right knobs); identical -> read-triggered latch by design, go to T6 / helper | no register write; image exists (clk87) |
| 2 | T4 | `3790[6:5]` = 00 (bypass), then `37D0[6:5]` = 00; `3790` = 0xB7 -> 0x97 | stale rate falls on the pages of that DCU only (also maps A / B: 88.. / A0..A7 vs C8.. / A8..AF); 10 (/4) raises it | DC_PHY register clock; reset restores; do while DDR idle |
| 3 | T3 | `FFBC` = 0x10, 0x14, 0x1F (reset 0x0F); restore 0x0F | ok rate rises with N; the knee N gives the PHY read time in MCU cycles (x clock) | documented field; <= 10 is a hazard, upward unmeasured |
| 4 | T6 | Read the 22 pages through `FFF3 |= 0x20; FFF4 = lo; FFF5` with `P0_9F` = page (SDK debug path), page_addr_map left 0; save / restore FFF3, FFF4, 9F around the ISR read | hardware-handshaked read: no artifact | firmware change in `dbgisr.c`; must not break burst writes (FFF4 is the burst target) |
| 5 | T6b | Set `FFFB` = 0x03 / 0x28 / 0x80 / 0xFF before the read pass; record FFFB per probe row | stale rate follows FFFB (extra MCU halt per access) | register restored after; earlier sweep: no write effect |
| 6 | T8 | `CKCON[2:0]` stretch 0 -> 3 -> 7 for the probe pass only | wider strobe lets the RBUS answer | slows every MOVX in that window |
| 7 | T5 | `3780[5]` = 0 (control, then restore 1) | stale rate rises (also later lanes): confirms the path; no fix | one bit; restore by write |
| 8 | T7 | ISP path: `FFF0[7]` = 1 (eclk_scalar_rw /4) in an ISP session | ISP stale rate rises: names the ISP mechanism | ISP session halts + resets the unit |
| 9 | T9 | `FFEE[5:2]` mcu_clk_div up (same as T2, per divider step) | same as T2, finer | clock sweep tooling exists |
| - | W | Fallback: central read helper (discard first read of a dword on the 22 pages; priming read for blocks) | works regardless | already in `dbg_xdata` / `AwtoRegRd2`; Dan: one place, not per site |

- Combine only after singles: T4 + T3, then T2 as the shipping-clock check.
- Record in the issue: MCU clock, FFBC, FFFB, FFF3, 3780, 3790, 37C0, 37D0, CKCON at each probe row (so the regmap store can attribute).

## 5. Open points that these findings do not settle

- Page 88 on unit 1: X -> Y right, X -> W -> Y stale: unexplained; a per-page one-dword cache with a read-triggered refill and an `other` class (88C0.. unmapped offsets) fits `rbus` handshake loss better than a pure timing cap [guess].
- A* clean on the ISP path but stale on the live path: points at the MCU-side stall (FFBC / FFFB / stretch) for A*, and a hardware or clock-domain mechanism (3780 / 3790 / dcu rbus clock) for 88..90 / C8..D0 [guess].
- "Mout" meaning: T3 answers it; if FFBC moves the rate, the M-domain reading is right.
