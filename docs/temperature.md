# Temperature sensor investigation (RTD2795T / RL6449)

- Question: does this die have a readable temperature sensor? Needed for flash-overclock and 350.8 MHz margin (`docs/clock-sweep.md`: no temperature logged in any run).
- Verdict on #206 ("none": LSADC A2 + external NTC): **unknown, not none** (Dan believes an undocumented sensor exists). No dedicated sensor found yet; no test has proven absence.
- Tags: [hw] unit 3 unless stated, [spec] regdb, [source-code] public repo (other SoC), [sdk-hypothesis], [fw] Dahua firmware static, [guess].
- Register facts: `re/regmap/regs.tsv` (keys below); this file keeps the investigation and the plan.

## Checked
| where | result |
|---|---|
| regdb of other chips | RTD2525AR (RL6463, LC-tank): test signal `0x008E` test_signal_sel code 0x0A = tsensor, `0x410C` reg_mux_nf_tsensor (N.F code from thermal sensor); its SDK has a page 5F thermal block (TSENSOR_00..17, TEMP_OFFSET `0x5F53/54`, TW_READ `0x5F6E/6F`) [spec][sdk-hypothesis]. Not present in any 2795T-family regdb |
| our regdb | incomplete: 1919 SDK registers missing; the 2525AR regdb lacks its own page 5F: absence in a regdb is weak evidence |
| SDK | `GET_TEMP_SENSOR_PWM` = I2C command 0x71, dead end (below); `ScalerADCThermalCompensationSetting` writes `0x01FF` bit5 (reg_thermo[5:0]), `ScalerIOSCTrimming` writes reg_emb_bgres (`0x06A6[1:0]` = 11, "thermal compensation factor"): write-only compensation, no readout [sdk-hypothesis] |
| Dahua firmware (static) | no handler for 0x71, no GET_* factory replies, no temperature strings; ADC use A0 / A1 only (`docs/reversing/dahua-fw/register-audit.md`) [fw] |
| ISP dumps (31 with pages) | no thermal / voltage sensor and no monotonic counter found (`docs/register-audit.md`) [hw] |
| live (ISP / debug slave) | ADC block reads `FF08` = B0, `FF09..FF0C` = F8 (saturated high), `FF0D` = 04, seen via slave 0x4B with the MCU halted (ADC is off after halt + reset otherwise) [hw] |

## Candidates
1. **DSS ring-oscillator speed sensors** (PVT proxy: process, voltage, temperature; Realtek's `Speed-Monitor.c` block comment says so [source-code, other SoC]). In our regdb: `0xA750..0xA757` and `0xAF50..0xAF57` (probably the two DDR PHY channels); keys `A750..A757`, `AF50..AF57`.
   - Layout (regdb): `A750-52` data_in (20-bit threshold); `A753` CTRL_3 {speed_en[6], data_in_ready[5], wire_sel[4] (0 long, 1 short), ro_sel[3:1] (001 HVT 12T NAND, 010 multi NAND, 011 NOR, 100 multi NOR, 101 mixed, others all disabled), dss_rst_n[0], reset 1}; `A755-57` count_out 20-bit (delay = count / (dss_clk x 16384) for 51 elements); `A757[1]` wsort_go, `[0]` ready.
   - Dumps: all zeros except `A753` = 0x01.
   - Attempt 1 (unit 3, 2026-11-19 00:26): final value written in ONE write (0x43 etc., ro 1..3, long / short, data_in_ready): sensor never became ready within 1 s on either channel; `A753` restored to 0x01 OK. Failed, cause open.
   - Attempt 2 (queued): Realtek's sequence is three writes (rst_n = 0 + ro / wire set; rst_n = 1; speed_en = 1; poll ready), then speed_en = 0 / rst_n = 0. Whether dss_clk needs its own enable: unknown.
   - Output is a delay, not degrees: needs calibration.
2. **IOSC trim counter** `06A4` + `06A5[7:4]` (target 1956 per regdb text; 12-bit) as a drift proxy. Documented on all 7 regdbs; ISP dumps A8 / C8 / CB / CF / D0: unit 1 1992, unit 3 1995 / 1999 / 2000; live 1998..2000. Constant 1999 over a 30-minute soak at 350.8 MHz and 10 minutes stock: no visible drift at this resolution; weak candidate.
3. **ADC** `FF08` ADC_ACONTROL (results `FF09..FF0C`, 5 bit [7:3], thresholds `FF0F..FF16`, `FF0D` ADC_CLK_DIV, `FF17` wait): no internal channel in the regdb; Dahua firmware reads A0 / A1 (front-key bands, pins 94 / 95, `key_scan_adc` 6:3944), never A2 / A3. An external NTC on A2 would need board knowledge (#206).

## Other families' sensors (hints only, not this die)
- Realtek TV SoCs: thermal sensor reading val / 1024 degC; a successive-approximation one (sdata * 165 / 128 - 40 - 7). Sources: `Speed-Monitor.c` in BPI-SINOVOIP/BPI-1296-Android6 (github.com/BPI-SINOVOIP/BPI-1296-Android6); `rtk_thermal_sensor.c` in TCLOpenSource/rtk2841 (github.com/TCLOpenSource/rtk2841) [source-code].

## GET_TEMP_SENSOR_PWM (0x71): dead end
- SDK: command 0x71 (`BeaconFactoryInclude.h:666`); handler `ScalerCommonMcu.c:536`, whole body `#if 0`. Reply would be 7 bytes: temperature (hardcoded 0), backlight light sensor (`Value2561`, TSL2561-class) 2 B, target 2 B, PWM duty 2 B, checksum. Live code only `SET_SEND_SENSOR_DATA()` (sets `ucIICControl3` bit 7, never read) [sdk-hypothesis].
- Dahua firmware has no 0x71 handler [fw]. Nothing to read there.

## Next (host-only, no flash)
- T-TS1: DSS three-step sequence on `A753`, both channels, poll `A757[0]`; restore `A753` = 0x01. Read only the sensor window; unit 3 only.
- T-TS2: if ready: sample count_out cold vs after load at 350.8 MHz; log with host time; look for monotonic drift.
- T-TS3: IOSC trim count logged each minute during a soak (higher resolution than 1999 constant is unlikely: use as a negative control).
- T-TS4: ISP-dump the pages the regdb lacks that other families put the sensor on (page 5F, `0x410C` neighbourhood): read-only scan, units 1 / 2 allowed (Dan 2026-11-19); see `docs/register-audit.md`.
- Calibration idea: delta against a host thermometer or the on-board NTC (if A2 is wired) with the unit warmed 20 C, fit count vs degC per unit; the sensor then gives drift, not absolute temperature.
- T-TS1..4 are proposed names (not yet in `re/regmap/tests.tsv`); open items: `docs/open-decisions.md`.
