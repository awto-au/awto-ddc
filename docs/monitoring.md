# Health monitor (low-rate values)

Code: `fw/diag/monitor.c` (`AwtoMonSample`, called from `AwtoDiagMainPass`). Registry row `monitor` (id 124, group Debug, default On).
Host: `scripts/mon_decode.py`, `scripts/sync_log.py` (`mon_text`), `scripts/unit_health.py` (`./dev.py health` row "monitor"), tests `scripts/mon_sim_test.py` (gate `monitor`), `tests/test_monitor.py`.
Register facts: `re/regmap` (keys below). Request: Dan 2026-11-19, issue #245.

## What runs

- Every `AWTO_MON_MS` = 10 s: read, store in `g_stAwtoMon` (21 B, XDATA, readable over debug slave 0x35 by map symbol), push sync rows.
  - Why 10 s: the values drift over minutes (IOSC trim constant 30 min at 350.8 MHz, `docs/temperature.md`); a key ladder is a held level, not a pulse (key presses have their own log); a faster period adds rows, not information.
- Sync row = id `EA`, arg = value (fmt `mon`, texts hard-coded in `console.c AwtoPutMon` and `sync_log.py mon_text`; one logged row of the 254-row index):

| arg | row text | row written when |
|---|---|---|
| 1 | `monitor: ADC A0 F8 A1 F8 A2 F8 A3 F8` | a channel moved `AWTO_MON_ADC_STEP` (16 = two codes) since the last ADC row, or heartbeat |
| 2 | `monitor: IOSC trim count 1999` | trim moved `AWTO_MON_TRIM_STEP` (4) counts since the last trim row, or heartbeat |
| 3 | `monitor: main loop 245 passes/s, longest watchdog gap 18ms` | the longest gap (since boot) changed, or heartbeat |
| 4 | `monitor: uptime 3600 s, stack high BC` | the stack high-water moved, or heartbeat |

- Heartbeat = every `AWTO_MON_BEAT_K` = 30 samples (5 min) and at the first sample after boot / after the registry row goes On: all four rows. 5 min x 4 rows keeps the boot episode in the 48-entry ring for hours; the uptime row differs every beat, so the repeat collapse of `AwtoSyncPush` never drops one.
- Never filtered: a changed row is written every sample it changes; an A B A B flicker is collapsed by the existing explicit "the N lines above repeated" row, not dropped.
- Power saving with the console open: values are stored, no row (a row redraws the open console; no OSD drawing in power saving).
- Read-only: no register is written, no NVRAM / flash write, no OSD draw (rows reach the OSD only through the console that is open anyway).

## Cost (sim, 2026-11-19, image built from this commit, default 350.8 MHz clock)

- Per pass: `AwtoDiagMainPass` +24 machine cycles (235 -> 259; `scripts/fw_profile.py`, 12 passes, ucsim) = 0.015 % of 163 k cycles/pass (0.03 % of the 82 k work cycles/pass). One subtract + compare of the SDK ms counter.
- Per sample (once per 10 s): 1.5 k instructions without a row, 5.3 k with the four heartbeat rows (DW8051 core, call watch on `AwtoDiagMainPass`); median pass 6.9 k instructions. 5.3 k per 10 s = 0.011 % of the instructions executed.
- Not a speed-limiting rule: nothing waits, nothing is slowed. Default On.

## Readout

- `./dev.py health`: row `monitor` = decoded `g_stAwtoMon`; FAIL if A0 / A1 read inside a key band (stuck / held key, floating ladder). "no sample yet" passes within 10 s of boot.
- Sync log (`scripts/sync_log.py`, `rtd_diag.py --sync`, console log pane): the `monitor:` rows with host time.
- Diag page: the console log pane shows the rows (no separate page: a page draws, the rows are free).

## Candidates, ranked by value / cost

| # | value | registers / source (regmap key) | read side effects | cost | status |
|---|---|---|---|---|---|
| 1 | longest watchdog poke gap = main-loop health, margin to the 1025 ms warning | `isr_g_stAwtoWdt.ucMaxPoke` + `g_ucAwtoPokeSite` (the `AWTO_WDT_POKE` macro already latches `FFAC` / `FFAD` at every poke) | none (RAM) | 0 | implemented (row 3). `FFAA` / `FFAB` direct reads not used: they need the `FFEB[3]` latch RMW with a W1C flag in the same byte, the poke macro already has the same gap |
| 2 | main-loop passes per second | `isr_g_stAwtoDiag.usLoopRate` | none | 0 | implemented (row 3) |
| 3 | uptime, last reset cause | `AwtoMs`, `AwtoBootReason` (canary based; no hardware reset-cause register: `docs/watchdog.md`) | none | 0 | implemented (row 4, `g_stAwtoMon.ucBoot`); boot lines `D0` already in the ring. `0003` STATUS1 / `000C` WATCH_DOG_CTRL0 are not reset causes (input-timing status, DVS watchdog flags) |
| 4 | stack high-water | `g_ucAwtoStackHigh` | none | 0 | implemented (row 4) |
| 5 | ADC A0..A3 raw | `FF09`..`FF0C` | none (result registers) | 4 reads | implemented (row 1). A0 / A1 = key ladders; A2 = pin 96, `a_adc2` in our `PINSHARE` (unused input); A3 = pin 97 = the DP HPD output (P4.2 push-pull): not an analog input here, always logged as the fourth byte |
| 6 | IOSC trim counter (temperature proxy) | `06A4` + `06A5[7:4]` (12 bit) | none; the SDK reads both in its own trim code | 2 reads | implemented (row 2). Per-unit constants (units 1 / 2 / 3: about 1992 / 1960 / 1995..2000), no drift in 30 min at 350.8 MHz: a proxy until a warm / cold run says otherwise (`C-IOSC`) |
| 7 | cache miss rate (load metric) | `FDB3` control, `FDB9..FDC4` ref / miss / restart counters (32 bit) | counters free-run once `pm_mtr_en` is set; reading is free | 12 reads + a config write at boot | not implemented: needs `FDB3[0]` set (a register write) and a check that the meter costs no speed at 350.8 MHz. Decision D2 |
| 8 | DDR PHY BIST flags | `A7E0..A7E3`, `AFE0..AFE3` (per-unit constants) | unknown (BIST block; `A7E3` noisy on live dumps) | 8 reads once at boot | not implemented: the meaning is not decoded (`C-BIST`, #228) |
| 9 | HDMI RX clock / stability flags | `71EF` / `72EF` (`no_clock[5]`, `freq_stable[6]` W1C, `freq_error_th`) | `freq_stable` is W1C: read with a plain byte read, never write | 1 read per port | not implemented: the input rows already carry cable / TMDS clock (`C6` rows); no character-error counter named in the regdb (`71A5` TMDS_CRCOB2 is a CRC byte, not a count). SCDC error counters `50..5A` are the source's registers (host side), not ours. Decision D3 |
| 10 | DSS speed sensors | `A750..A757`, `AF50..AF57` | write sequence needed | - | left out: never ready in two attempts (`docs/temperature.md`) |
| 11 | Timer2 vs host drift | sync rows `D7` / `D8` / `D9` | none | 0 | already logged (`docs/ddcci.md` host time) |
| 12 | free XDATA | link map | - | - | static: `docs/speed-bench.tsv` `xdata_free`, not a run-time value |
| 13 | panel / backlight PWM duty | our own setting (`brightness`) | - | - | no value beyond the setting; skipped |
| 14 | boot count | `isr_g_stAwtoWdt.ucBites` (watchdog bites since cold power-up, kept over resets) | none | 0 | exists in the crash record (`rtd_crash.py`); a lifetime count needs an NVRAM write: not done (no extra flash writes) |
| 15 | flash read-window health | CRC window check, `docs/flash-crc.md`, #238 | reads flash | - | hook only: `AWTO_MON_FLASH_CHECK(beat)` runs every sample, beat != 0 on a heartbeat (empty today) |
| 16 | CEC status | when the CEC work lands | - | - | add a row (new `AWTO_MON_EV_*` arg, the `EA` row already takes any arg) |

## ADC / key scan facts behind it

- LSADC: `FF08` ADC_ACONTROL = B0 live (start, auto mode, bias); results `FF09..FF0C` 5 bit in [7:3] (multiples of 8; idle = `F8` = pull-up); thresholds `FF0F..FF16` = `0x00FF` never trigger (our code never reads the comparator flags); `FF17` wait = 0.
- Live ADC block, units 1 and 2, 2026-11-19: `FF08` = B0, `FF09..FF0C` = F8 x4, `FF0D` = 09 (IOSC divider), `FF0F..FF16` = 00 / F8 per channel (H / L), `FF17` = 00. Earlier ISP / unit 3 read `FF0D` = 04 (crystal divider).
- ADC clock `FF0D` bit 7 = 0: not on the M2PLL, so the 350.8 MHz default does not touch it. `AwtoClkDivSet(ADC)` (clock sweep) only retunes it when bit 7 is set. SDK sets 0x04 on the crystal and 0x09 on IOSC (power saving), "target 3 MHz" [sdk-hypothesis]; no datasheet limit read.
- Key timing (`AWTO_KEY_*_MS`) runs on `AwtoMs` (Timer2), clock independent; no `DELAY_*` site in the key path, so nothing in `docs/delay-audit.tsv` to add.
- Pin 96 in the Dahua firmware's pin-share is a GPIO (`P4D1i`); in our `RL6449_AWTO_JXC4K_PINSHARE.h` it is `a_adc2`. Only the second one makes A2 readable.

## Decisions needed (Dan)

- D1 Stuck-key guard: a key (or a ladder stuck in a band) held from power-on or longer than `AWTO_KEY_RESET_MS` (10 s) resets every setting to its default, at every boot while it lasts. Proposal: a key already down at the first sample after boot is latched (ignored until released); `unit_health` already flags a ladder in a band. Cost: none. Not implemented (behaviour change).
- D2 Cache meter: enable `FDB3[0]` at boot and log miss rate per second (rows via the same `EA` id)? Needs a 350.8 MHz speed check first.
- D3 HDMI RX error counter: search the regdb for a character-error counter before any row (test not yet written).
- D4 Results comment on #245 (public repo: text needs Dan's approval); this file is the draft.

## Phase B (unit 3, on Dan's go)

- Flash the image, run `./dev.py health` (row monitor), read the `monitor:` rows over 30 min (`C-MON`); key decode by test cmds 0x01..0x05 / `key_inject` only (no key presses, `docs/keys.md`).
