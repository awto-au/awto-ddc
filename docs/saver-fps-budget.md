# Saver frame budget: what 25 fps costs, what limits it (Dan 2026-11-18: "how to get to 25 fps")

Status 2026-11-18. Research + measurement only; no production change. Savers: `docs/screensaver.md`, `docs/saver-library.md`, `docs/saver-mode.md`.

## Conditions

- Sim: fast core, `dw8051` timing, flash code-fetch model on (2 KB 2-way cache, 16 B lines: ASSUMED geometry, `docs/sim-cpu-model.md`), 1080p60 input, **Rotate 180** (unit 3 setting) unless a row says upright.
- Images (all `--audio-test`, worktree HEAD 6df194c):
  - `fpsb` = as main.
  - `fpsfast` = `fpsb` + `_MCU_SPEED_UP_SUPPORT _ON` (`Project_Option.h:349`), throw-away.
  - `fpsband` = `fpsb` + `AWTO_S2_PASS_MS` 38 (was 8), throw-away.
  - `fpsfb` = both.
  - "dual read" = model what-if: flash clk per byte 8 -> 4 (`byte_flash_clk` in a scratch copy of `dw8051_model.json`), same binary.
- Window: 10 s fw after the saver's hidden first frame (2.5 s; Asteroids 8 s).
- Tools: `scripts/saver_frame_cost.py` (per-frame cost by stage: PC every 200 instr weighted by CPU clk incl. fetch stall; split by main-loop slot; OSD port bytes per address-set burst), `scripts/osd_port_cal.py` (unit-3 port write tests replayed in the sim). Logs `tmp/logs/saver_frame_cost.log`, `tmp/logs/osd_port_cal.log`.
- Hardware numbers are from unit 3 runs of others (`docs/osd-hw-tests.md`, `osd_hw_test.log` 2026-11-18, images `ohw3`..`ohw6`); nothing here ran on a unit.

## Hard limits

### MCU

| item | value | source |
|---|---|---|
| clock today | 87.7 MHz = M2PLL 351 / `FLASH_CLK_DIV` 4 / `MCU_CLK_DIV` 1; 4 clk per cycle = 21.9 M cycles/s | `Scaler_Option.h:654`, sim clock model; unit micro-bench `docs/diag-block.md` |
| at its maximum? | **no**: the SDK has a 175.5 MHz mode for this chip (`_MCU_SPEED_UP_SUPPORT`: `FLASH_CLK_DIV` 2, `FLASH_2_CLK_DIV` 4 keeps the SPI clock at 43.9 MHz; Timer2 reload, 5 us delay counts, Timer0/1 step, DDC debounce follow it) | `Scaler_Option.h:643-700, 747-767`, `RL6449_Gen_Option.h:603` |
| why off | `_MCU_SPEED_UP_SUPPORT = (_LOCAL_DIMMING_SUPPORT == _ON)`; config check warns it "should be ON" with local dimming. No recorded reason against it otherwise | `Project_Option.h:349`, `Project_Config_Check.h:302` |
| cycles per 40 ms | 877 k (175.5 MHz: 1.75 M) | arithmetic |
| instr per 40 ms | 215 k at the Scope 2 mix (4.07 cycles/instr incl. fetch stall), 450 k cache-resident (1.96-2.08 cycles/instr, fetch model off) | sim |
| MOVX XRAM | 2 cycles (CKCON MD = 0) | model = unit micro-bench (2.00) |
| MOVX to scaler registers (OSD port 0x0092) | model 2 cycles; unit port-write loops run 1.64-1.94x the sim (+20-28 cycles per store) | `osd_port_cal.py` vs unit T1 / T2 |
| other instructions | `djnz` 3.65 cycles on the unit vs 3 in the model | `docs/diag-block.md` |
| MOVC data reads | 3 cycles; cache misses of table reads not modelled | `docs/sim-cpu-model.md` |
| interrupt load | unit: EA on vs off on the same write loop = +9-13 % time (4K60 DP); sim Timer2 ISR ~2.7 % | T2 rows below; `saver_frame_cost` |
| dual DPTR | DPS at SFR 0x86, SDCC does not emit it; `--dual-dptr` blocked by gates `crash`, `wdt` (#188) | `docs/reversing/realtek-rtd/mcu-8051.md` |

### Code fetch (the largest single term in the sim)

- SPI flash MX25L8006E, fast read 0x0B 1-bit (`FF6C` read_mode 01) at 43.9 MHz; cache line fill = 40 + 16 x 8 = 168 flash clk = 3.8 us per miss.
- Fetch stall per frame (sim): Scope 2 99 of 192 ms, Asteroids 158 of 256, Scope 1 480 of 883, Pac-Man sub-step 24 of 31 ms (mostly main loop).
- Check against the unit: Scope 2 free run on unit 3 vs sim, same image `ohw6`, Rotate 180 (`osd_port_cal.py`): frame in progress after 6.0 s 31 vs 31, after 7.37 s 37 (unit) vs 38 (sim). The whole-saver sim time is within ~3 %; with a 16 KB cache model the sim would be 1.8x faster than the unit.
- Chip facilities not used today:
  - `FF6C[7:6]` = 10 fast dual data read, 11 dual I/O (regdb). Flash support of 0x3B / 0xBB: check the MX25L8006E datasheet (on the NAS: `/vendors/macronix/NAS-MOVED.tsv`).
  - Cache performance meter `FDB3..FDC4`: reference count, miss count, memory restart count; start / stop by `FDB3[0]`. Readable over the debug link without a firmware change.
  - Common page mode `FDA1[1]` + wildcard `FDB2`: SDK clears it (`ScalerMcuCacheInitial`), so common-area code is cached once per bank on the unit; the sim shares it.
  - Two cacheable ranges `FDA2..FDAD`, cache preload `FDCC[0]`.

### OSD SRAM write path (unit 3, 13824 B, `F_REPEAT`)

| path | unit us/B | sim us/B | KB/s (unit) | B per 40 ms | 2-bit glyphs (54 B) | 1-bit glyphs (27 B) |
|---|---|---|---|---|---|---|
| `ScalerOsdDataPort` (banked call per byte), EA on | 4.12 | 2.39 | 243 | 9 700 | 180 | 360 |
| direct C loop, EA on / off | 2.60 / 2.39 | 1.46 | 385 / 418 | 15 400 | 285 | 570 |
| direct unrolled triples, EA off, OSD shown | 1.95 | 1.42 | 513 | 20 500 | 380 | 760 |

- All write paths store correctly (T1 / T2 / T7 PASS); 1.95 us/B is the fastest stream tested, not the port's limit.
- Address set (`ScalerOsdAddrSet`: 3 read-modify-writes + 1 store, banked): sim 12.7 us each. A scattered map word = set + 3 B = ~25 us via the SDK (sim).
- Limits that do not move: 2-bit ids 256, 1-bit ids 512, SRAM 12288 words, map 1 word per cell (`docs/screensaver.md`).

### Main loop

- Per pass inside a saver run (sim): 4.19 ms Scope 2, 4.05 Asteroids, 4.03 Scope 1, 2.80 Pac-Man (generator on: short audio handler). Idle ACTIVE 2.9 ms (sim 345-348 passes/s); unit 3 idle 264.5 passes/s (3.78 ms) on image `f2` (different image: indicative).
- At 25 fps with one pass per frame: 4.2 ms = 10.5 % of 40 ms. Today Scope 2 runs 15.2 passes per frame (8 ms bands), Asteroids 18.5 (one column per pass).

### Budget at 25 fps (unit, 87.7 MHz)

- 40 ms = 4.2 main-loop pass + ~4 interrupts (10 %) + **~32 ms saver work** (~700 k cycles).
- Port inside that: 4 KB costs 16.5 ms through `ScalerOsdDataPort`, 7.8 ms with direct stores.

## Cost of one frame today (sim, `fpsb`, Rotate 180)

| | Scope 1 | Scope 2 | Asteroids | Pac-Man (per sub-step) |
|---|---|---|---|---|
| ms per frame / fps | 883 / 1.13 | 192 / 5.2 (upright 179 / 5.6) | 256 / 3.9 | 31.3 / 32 (timer-paced) |
| instr per frame | 4.39 M | 1.04 M | 1.06 M | 78 k |
| main-loop passes per frame | 50.1 | 15.2 | 18.5 | 10.2 |
| main loop outside the saver | 204 ms | 64 ms | 75 ms | 28.6 ms |
| saver slot | 679 ms | 129 ms | 181 ms | 2.6 ms |
| port bytes per frame | 10 368 (384 tiles x 27, all, every frame) | 3 966 (68 glyphs x 54 + 91 map words), 159 address sets | 1 193 (44 tiles x 27) | 29 (10 map words) |
| port on the unit (SDK path / direct) | 42.7 / 20.2 ms | 16.3 / 7.7 ms | 4.9 / 2.3 ms | 0.1 ms |
| over 40 ms by | 22x | 4.8x | 6.4x | meets it (32 / s) |

Saver-slot stages, ms per frame (exclusive time by function, grouped; banked-call trampoline and compiler helpers shown apart):

| stage | Scope 1 | Scope 2 | Asteroids |
|---|---|---|---|
| draw | 451: `cursor_plot` 154, `osd_line` 76, `cursor_init` 67, `ScPass` 59, `osd_clear` 42, `skip_steps` 19, `ScY` 18 | 35: `S2Run` 15, `S2Trace` 11, `S2BaseCopy` 9.5 | 79: `cursor_plot` 17.5, `AstShape` 17.4, `osd_line` 17.0, `AstTileInk` 7.9, `cursor_init` 6.6, `skip_steps` 4.9, `memset` 2.7 |
| frame logic | 4 | 35: `S2ColBegin` 11.5, `S2ColRows` 11.0, `S2Pulse` 6.2, `AwtoScopeSaver2` 2.0 | 36: `AstPass` 17.5, `AstCull` 7.1, `AstCollide` 2.5 |
| banked-call trampoline | 87 | 19 | 25 |
| compiler helpers (`_mulint`, `_divuint`, ...) | 47 | 12 | 14 |
| upload (glyph / tile / turn) | 45: `AwtoOsdGlyph` 33 | 14: `AwtoOsdTurn` (Rotate 180) 9.2, `S2Glyph` 4.2 | 5.4 |
| OSD port SDK calls | 26 | 9: `ScalerOsdDataPort` 5.8, `ScalerOsdAddrSet` 2.1 | 3.5 |
| interrupts, `AwtoMs`, sound | 16 | 4 | 15: `AwtoPmSoundPoll` 5.6 |

- Scope 2 per frame: 6415 banked calls (3965 of them `ScalerOsdDataPort`), 483 `S2Pulse`, 637 `S2Run`, 68 tiles, 317 `AwtoMs`.
- Asteroids per frame: 60 band passes, 490 `AstCull`, 121 `osd_line`, 549 `cursor_plot`, 44 tile uploads. The per-band structure, not the pixel count, is the cost.

## Theoretical minimum per frame (unit, 87.7 MHz)

- Scope 2: changed tiles only is already the design (68 glyphs + 91 map words). Floor ~16 ms: port 7.7 (direct) + address sets ~0.5 (direct stores) + tile compose ~3 (70 x 54 B base + ~3000 run pixels) + trace y ~1 (480 points from a per-frame table) + one main pass 4.2. ~60 fps ceiling.
- Asteroids: ~550 px, 44 tiles, 1 game tick. Floor ~10-15 ms with one pass over the objects per frame. XDATA (~1 KB free) rules out a full-frame canvas (360 x 198 1-bit = 8.9 KB): a per-tile object list instead of 60 band passes.
- Scope 1: 384 tiles every frame = 42.7 ms of port alone through the SDK: 25 fps needs dirty tiles (Scope 2's model).
- Pac-Man: 2.6 ms per sub-step: done; smoother motion = more sub-steps (data), not CPU.

## Levers, ranked by ms saved per frame x confidence

Measured = sim run of a throw-away image or model what-if; estimate = baseline minus the stage time it removes.

| # | lever | Scope 2 | Asteroids | confidence / evidence | cost, risk |
|---|---|---|---|---|---|
| 1 | Fewer main-loop passes per frame: whole frame in 1-2 calls, DDC/CI pumped between bands | 192 -> 145 ms measured (band 8 -> 38 ms: 15.2 -> 4.1 passes) | -70 ms est. (18.5 passes x 4.05 ms -> 1) | high | DDC/CI reply latency up to a band (D6, `scope2_ddc_latency.py`); watchdog 586 ms not near |
| 2 | MCU 175.5 MHz (`_MCU_SPEED_UP_SUPPORT`) | 192 -> 128 measured | 256 -> 200 measured | medium: SDK path for this chip and M2PLL; sim only. Gains < 2x: stall time is flash-clock bound | gates + unit 3: Timer2 / delays / DDC debounce / flash writes (9-cycle MOVX), panel and audio timing; port store rate at 2x unknown |
| 3 | Direct OSD port stores, DPTR parked on 0x0092; address set as direct stores | sim -20..25 ms (3965 banked calls x ~4.8 us + body); unit port 16.3 -> <= 7.7 ms | -4 ms unit | high: unit T1 / T2 / T7 PASS for direct stores; the photo fault is display-side (`docs/osd-hw-tests.md`) | lifts the 2026-11-18 rule "every byte via `ScalerOsdDataPort`" (`docs/saver-library.md`): Dan's call |
| 4 | Dual data flash read (`FF6C` read_mode 10) | 192 -> 147 what-if | 256 -> 185 what-if | low-medium: needs the unit miss count (perf meter) and flash 0x3B support | read mode is global: boot, ISP, flash writes; test on unit 3 |
| 2+4 | | 89 ms (11.2 fps) | 139 ms (7.2 fps) | | |
| 1+2+4 | | 72 ms (13.9 fps) measured / what-if | ~99 ms est. | | |
| 5 | Trace y from a per-frame table (no divide / multiply per point) | -25 ms est. (`S2ColBegin`, `S2Pulse`, `_mulint`, `_divuint`) | - | high (pure code) | none |
| 6 | Hot saver code + callees in one bank (no trampolines on per-tile / per-pixel paths) | -10..19 ms est. (19 ms saver-slot trampolines; ~2.5 k calls left after 3) | -15..25 ms est. | medium | bank space (bank 13 nearly full); link gate `gptr_const_xbank` |
| 7 | Compose tiles straight into the port stream (no `S2BaseCopy` buffer, runs ORed while streaming) | -10..15 ms est. | - | medium | XDATA unchanged or less |
| 8 | Rotate 180 without per-tile turning (pre-turned base table or turned compose) | -9 ms (`AwtoOsdTurn`); upright vs Rotate 180 measured 179 vs 192 | small | high | +2.3 KB const (D-SL2 traded it away) |
| 9 | Per-frame object pass instead of 60 band passes (cull + transform once, tile list) | - | -40..80 ms est. (`AstPass` + `AstCull` + per-band `AstShape` / clip) | medium | redesign (saver-redesign agent) |
| 10 | 1-bit trace / ink layer instead of 2-bit glyphs | port -47 % (3.7 KB -> 1.85 KB glyph data): -3.8 ms direct, -7.6 SDK | already 1-bit | high for bytes; display feasibility = OSD-features agent | |
| 11 | Dual DPTR (#188) | <= -10 ms (`S2BaseCopy`, `AwtoOsdTurn` copies); asm loops get most of it without DPTR1 | small | low priority | gates `crash`, `wdt` first |
| 12 | Cache common page mode / cacheable range / preload | unknown | unknown | unmeasured: perf meter first | global, boot path |

## Recommendation (order, expected fps, how computed)

1. Unit 3 measurements before platform levers (cheap, owner of unit 3 runs them):
   - Cache perf meter `FDB3..FDC4` during Scope 2 (start / stop over the debug link, read ref / miss counts): confirms or kills the fetch-stall half of every number above and the value of lever 4.
   - A 175.5 MHz image: boot, gates, `./dev.py health`, Scope 2 fps, the T2 write test.
   - Store-only loop to 0x0092 vs to XRAM: the OSD port's own floor per byte.
2. Scope 2: levers 1 + 3 + 5 + 8 (code only). Estimate 192 - 47 - 22 - 25 - 9 = ~90 ms -> ~11 fps at 87.7 MHz (stage times subtracted; the measured 1 is not fully additive with 3). Then 2 (x1.5 measured on this code) -> ~60 ms; 7 + 6 (halved at 2x clock) -> ~47 ms (21 fps); 4 (-30 % measured at 175.5 MHz: 128 -> 89 ms) -> ~35 ms (28 fps).
3. Asteroids: 1 + 9 + 3 (+ 6): 256 - 70 - 60 - 4 - 15 = ~107 ms -> ~9 fps; 2 + 4 measured x1.84 on today's code -> ~58 ms -> ~17 fps. 25 fps needs 9 done as a per-frame tile list (floor ~10-15 ms) plus 2.
4. Pac-Man: nothing (32 sub-steps/s, 8 % of the period).
5. Scope 1: no work unless rebuilt on Scope 2's dirty-tile model ("Scope 1 stays as is", `docs/screensaver.md`); platform levers alone give ~1.4-2 fps.

- fps = 1000 / (ms per frame). Measured rows: `saver_frame_cost.py` on the named image. Estimates: baseline minus the stage ms the lever removes (exclusive time; overlaps with trampolines and stall make them approximate, +-30 %).
- Sim to unit: whole-saver time matches within ~3 % (Scope 2 check above); port-write-heavy code runs ~1.7x the sim on the unit: redesigns that remove compute and keep the port bytes gain less on the unit than in the sim. Use the unit per-byte rates for the port part.
