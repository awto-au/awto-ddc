# Dahua firmware: register / I2C / GPIO audit

Original Dahua firmware of the JXC 27" 4K monitor (RTD2795T / RL6449, DW8051, 7 banks). Tracking: #41.
Tags: [fw] read in decompiled code/disassembly, [spec] register DB / SDK source, [hw] live read of a unit, [guess], [?] unknown (what settles it is stated).
Labels in `ghidra_names_*.tsv` are not facts (#91); function names below are the current Ghidra names.

## Method
- `scripts/dahua_reg_audit.py` merges `~/vendors/realtek/analysis/jxc-4k/bank0..6/{regreads,regwrites}.tsv` by register address; DB = `re/regdb/RTD2795T-CG.tsv.gz` (scaler pages + MCU 0xFFxx); output `re/jxc-4k/reg_audit.tsv`, log `tmp/logs/dahua_reg_audit.log`.
- Extra columns: `ours_w` = writes in our firmware's sim trace (`tmp/logs/trace_wb-p14kc2-2160p60.tsv.gz`), `dahua_sim_w` = writes in the Dahua firmware's sim traces (`trace_vendor_{2160p60,1080p60}`). Both traces are boot to ACTIVE only: a gap is not proof of absence.
- Bank 0 (common area) is copied into every bank: per-bank counts of common functions are repeated 7 times.
- SFR ports (P1, P3) are not in the export; taken from `decompiled_named.c` and cross-checked in the disassembly. Ghidra output for the lower address range of banks 2/3/6 contains data decoded as code ("bad instruction data" warnings): hits there are ignored.

## Totals
| Item | Count |
|---|---|
| export rows (reads + writes) | 12,027 (7,699 with a resolved address: 3,143 reads + 4,556 writes; 4,328 with unresolved `?` address) |
| distinct addresses | 1,896 = 1,820 register + 76 XRAM (0xD700-0xF6FF, variables, not registers) |
| register addresses in DB | 1,800 |
| register addresses NOT in DB | 20 (all explained below) |
| addresses with a write of a 1 into a "Reserved/Dummy" field | 24 (column `rsv1_writes`; not analysed further, SDK writes these too) |
| Dahua-fw sim writes never seen by the static export (indirect writes) | 193 addresses, all in DB |
| written by both fw (sim vs sim) | 880; Dahua-only 770; ours-only 182 (addresses) |
- Result: no register outside the Realtek DB except the 20 below. All custom behaviour is in GPIO usage, the IR block, audio DAC use and board wiring, not in unknown registers. [fw][spec]

## Registers not in the DB (20)
| Address | Users | Verdict |
|---|---|---|
| A140-A143, A154-A157, A940-A943, A954-A957 | `ScalerDDR2DCPHYInitial` (2:687c), dword stores of 0x48 and 0x01 | SDK names `PA1_40_SYS_CMP_FAIL_READ_0_0`, `PA1_54_SYS_STS_1_0` (DDR2.c writes 0x00000048 / 0x00000001); not in the 2795T DB, in other chips. Standard Realtek DDR2 PHY init. [fw][spec] |
| 1EA3, 1FA3, 269D, 8214 | `FUN_CODE_3218`, `719d`, `9e3c` (bank 3), `4190` (bank 2) | Ghidra "bad instruction data" functions: data decoded as code. Not registers. [guess] settles: byte-compare with the SDK function layout, not worth it |
- Accesses with `?` address (4,328 rows, 36%): pointer/indexed access via Keil helpers (`ScalerDebug*`, PHY setup loops, HDCP2 handlers, pin-share bulk fill). Static export cannot name them; the sim trace resolves 193 more addresses (pin-share 0x1004-0x1048, 0x06E7, 0xFF59-FF5B), all in DB. Remaining blind spot: code paths the sim does not reach. [fw]

## I2C
### MCU I2C master engine (`I2CM_*`, 0xFF55-0xFF5F)
- Driver is the SDK one: `ScalerMcuHwIICWrite` 0x0193, `ScalerMcuHwIICRead` 0xD778 (via stub 0x09ED), `ScalerMcuHwIICInitial` 0xF6A4, `ScalerMcuHwIICSetFreqDiv` 0xFA1E, `ScalerMcuHwIICConfigSetting` 0xFD45 (index 0, called from `mcu_init_pwm_uart` e92b; second call site bank1 fd1b). [fw]
- Only callers of Write/Read in all 7 banks: three call sites in `ScalerDebug` (0x1BC9: read at 1c60/1c82, write at 1d76). Slave address, sub-address length, address and length come from the host's DDC/CI debug packet (`g_pucDdcciData`), buffer XDATA 0xE164. [fw]
- Result: the firmware itself never starts an I2C master transaction on its own. No fixed slave address exists in the image: no EEPROM, sensor, touch/key controller, codec, hub, backlight driver or panel-EEPROM access. [fw]
- Consistent with the pins: EESCL/EESDA (pins 210/211) and EEPROM_WP (pin 209) are plain inputs in the live dump (`docs/monitors/pinshare-live-AWT26110003.tsv`, mode 0), and no PORTA6/A7/B0 access (0xFE36-38) exists in the export. [hw][fw]
- Settings storage is flash (`ScalerFlashRead/Write/ErasePage`, WP on P8.6), no EEPROM driver. [fw]

### I2C slave side (DDC/CI, debug, EDID)
| Item | Value | Evidence |
|---|---|---|
| `IIC_SET_SLAVE` (0xFF23) | 0x6A at `ScalerMcuDdcciInitial` (5:ea2e) and `ScalerMcuDdcciSwitchPort`; 0x6E in SwitchPort for the DDC/CI port | SDK RL6492 Mcu.c writes the same 0x6A / 0x6E / 0x3E [fw][spec] |
| `IIC_1_SET_SLAVE` (0xFE87) | 0x3D | SDK Mcu.c:1182 same [fw][spec] |
| DDC channels | DDC0/1/2/3 + ADC_DDC enable, debounce, force-NACK (`ScalerMcuDdcInitial` 5:c6b8) | standard EDID slave RAMs [fw] |
- No bit-banged (software) I2C: no function toggles two GPIO bits with delays between them; the only GPIO toggles are listed in the table below. `_SW_IIC_SUPPORT` is also off in our header. [fw]

## ADC and analog
| Channel | Use | Evidence |
|---|---|---|
| A0 (0xFF09), A1 (0xFF0A) | front-panel key bands, `key_scan_adc` (6:3944) | [fw] |
| A2, A3 results | never read; thresholds ADC0-3 H/L all set to 0x00FF (never triggers) in `mcu_init_pwm_uart` | [fw] |
| supply / voltage monitoring, temperature | none: no other ADC read, no low-speed-ADC read except A0/A1 | [fw] |
- Pins 94/95 `ADC_KEY1/2` are mode 3 (a_adc0/1); no other pin in the live dump is in an ADC mode. [hw]
- P3.0 (RXD pin, pin 71) read as the POWER key in `key_scan_adc`. [fw]

## GPIO usage (accesses through `PORTxx_PIN_REG` 0xFE00-0xFE35 and SFR P1/P3)
Pin numbers from `docs/monitors/gpio-roles.md` / pin-share live dump. "Header" = mentioned in `RL6449_AWTO_JXC4K.h`.

| Pin | Port | Dahua access | Role | Header |
|---|---|---|---|---|
| 1 | P1.0 | set 1 in `ScalerMcuGpioInitial` (5:d2a0); set/clear in 5:f722/f917, bit6 of XDATA E0E8 | D3 HPD (OD) | yes |
| 14 | P1.1 | same, 5:f774/fa36, bit5 of E0E8 | D2 HPD | yes |
| 71 | P3.0 | read in `key_scan_adc` | power key | yes (P3_0) |
| 91, 92 | P3.5 (T1), P3.6 (WR) | cleared/set in `FUN_CODE_d6b2` (1:d6b2) from a state 0..13; init `T1=1, WR=0` | 2-bit state output, consumer unknown | partly: "never driven here" |
| 97 | P4.2 | write 0 at init, set/clear in 1:e1c0, 1:818e, 4:d319, reads in 1:c275, dab8, 4:fbb1 | D1 HPD (PP) | yes |
| 113 | P4.5 | read in 1:f69b, value discarded | LINE_INL pin used as GPIO read; role [?] | no |
| 159 | P7.2 | `panel_power_seq` 1:917c, 1:9294, init | panel power enable | yes |
| 160, 161 | P7.3, P7.4 | write 0 at init (`d2a0`); P7.4 also `FUN_CODE_ea99` (1:ea99) | OD outputs, role [?] | no |
| 184, 185 | P8.4, P8.5 | init, `panel_power_seq`, group function below | LED1 / unknown | yes |
| 190 | P8.6 | `flash_cmd_end_wp_pin_assert` / `flash_wp_pin_release` (3:d402/d43e) | flash WP | yes |
| 196 | P9.2 | `panel_power_seq`, 1:ab18 read | backlight enable, active low | yes |
| 198 | P9.4 | read in `SysSourceCableDetection` (4:a33c), 4:a47a | D3 cable detect | yes |
| 201, 202 | P9.7, PA.0 | written 1/0 together with P8.4, P8.5 by `pcb_pin_group_p97_pa0_p85_p84_on` (1:f188), `..._set` (5:e222), `ScalerPinshareConfig` (6:5d88, arg 2/3) | OD outputs in the same group as LED1, role [?] | declared, "never driven" |
| 204-208 | PA.2-PA.5 | read in `SysSourceCableDetection` (4:a33c), 4:a3cf | HDMI2 detect / DP1 cable pins | yes |
- Not touched by the Dahua firmware (export + sim): P4.1 (fe01, HPD0), P8.1 (VCCK_OFF), P8.2 (5V reg), P8.3 (EDID WP), P9.0, P9.1, P9.6 (DDR power). Our firmware writes P4.1 and P8.3. [fw]
- `gpio-roles.md` states P9.7 and PA.0 are "never written by the firmware": wrong, they are written as a group with P8.4/P8.5. [fw] Needs a correction in that file (not edited here).
- Pin-mux: the Dahua firmware writes 0x1000-0x1048 (63 values dynamic via pointer walk in `ScalerPinshareInitial` 6:4f38, `ScalerBurstWriteTimeoutCal`-labelled helpers); the mode bits agree with the live dump of unit 3 on all 72 pins compared, 0 differences. [fw][hw]

## Other peripherals
| Peripheral | Finding | Evidence |
|---|---|---|
| CEC | no access to 0x18E3 / 0x18B7 or any CEC register; no CEC function names | [fw] confirmed |
| IR receiver | HW IR block used: `ScalerIRHWModeInitial` 6:6315 called from `SysMainSystemInitial` (0:fb4d) (IR_SF2/3 = 0x00B1, IR_CR2 |= 5, IR_SR3 |= 0x7F); clock select `ScalerIRHWModeClockSel` 6:654C; EXINT0 handler `ScalerIRHWModeIntHandler_EXINT0` 6:4FC4 copies IR_RP0-3, RP2_0-3 to XDATA E1EE-E1F5; `ScalerIRHWModeGetData` 6:57F3 is called from `key_alt_source_poll` 6:5154 (previously "role unknown", `buttons.md`). Pin 194 (P9.0, "LED2") is `irda_in` (mode 6) live. | [fw][hw] |
| Audio | analog audio DAC used: `ScalerAudioDACInitial` 3:f39f, `ScalerAudioDisable` 3:f3e9, writes REG_DAC_POWER0/1, REG_ANA_CTRL, REG_AOUT/HPOUT_CTRL, REG_OUT_GAIN, DA_CTRL, DA_MUTE, DA_GAIN_L/R, DA_CLK_CTRL, REG_MUX_ANA_OUT, AD_SPDIF_CS (0x06C0-0x06E3); HDMI/DP audio PLL, I2S/SPDIF TX setup (`ScalerAudioD1DPAudioInitial`, `D2/D3SetAudioPLL`). Pins 109/110/115-117 are in audio modes live. No audio-mute GPIO exists in the access table (no unlisted pin toggles with mute). Our firmware writes none of 0x06C0-0x06E3 | [fw][hw] |
| PWM | PWM4 only (backlight, pin 195): `pwm_set_freq` 0:db28, `pwm_enable_ctrl` 0:fb79 clears all enables then sets PWM_EN bit4 (0x10), duty `PWM4H_DUT` in 1:c051 ramp, 1:fac7, 5:d04a | [fw] |
| Fan / temperature / USB / touch | no register, pin or I2C access | [fw] |
| UART | 8051 UART set up (TMOD=0x21 in `mcu_init_pwm_uart`), SBUF write in bank 0; debug serial, no board feature [?] (pin function not checked) | [fw] |
| Watchdog | `WATCHDOG_TIMER`, `WATCHDOG_CNT*`, `ScalerTimerWDInitial` 5:f557, 11+ writes of 0xFFEA: standard | [fw] |
| eDP/DPTX | `ScalerDisplayDPTx*` family, `VBY1_LCLK_SOURCE_CTRL` write: panel link is DPTX (eDP) or V-by-One; our firmware already drives it | [fw] |
| MHL | `MHL_CTRL_00/12` touched once (5:a52e); no MHL pins (board has none) | [fw] |

## Worth investigating (ranked)
1. IR remote: confirm `irda_in` on pin 194 and the code table read by `key_alt_source_poll` (copies 8 bytes from code 0xFF:3067, bank-0 bytes there are `30 00 CC 00 13 88 00 7E` [?], layout unproven). Settles: log `g_pucIRCode` (XDATA E1EE) while pressing a remote key on unit 1 via ISP read; then add `_IR_SUPPORT` to our build if wanted. Our firmware has no IR init (0x23AA-0x23BB Dahua-only).
2. Audio DAC / line out (0x06C0-0x06E3 incl. DA_MUTE/GAIN): Dahua-only, our firmware leaves audio dead. Settles: check if the monitor has speakers/headphone jack (hardware photo), then port `ScalerAudioDACInitial` values from the Dahua sim trace.
3. P3.5/P3.6 (pins 91/92) 2-bit output from `d6b2`: states 0,1,2,4 -> (1,0); 3,5 -> (0,1); 6,13 -> (0,0), called with `panel_power_seq` (`d3ac`). Live dump shows both 0 when ON. Consumer unknown (bicolour LED? input select?). Settles: read P3.5/P3.6 on unit 1 in each state (power-save, no-signal, active) with `scripts/rtd_gpio_live.py`.
4. P9.7 / PA.0 (pins 201/202, OD) group-driven with P8.4/P8.5: external loads unknown; the SDK names (VBUS_EN_3, MHL_DETECT_2) do not fit. Settles: board photo/trace or measure which rail follows P9.7.
5. P7.3 / P7.4 (pins 160/161, OD, cleared at boot with a 200 ms gap before P7.3) and P4.5 (pin 113, discarded read in `f69b`): unknown loads; P7.4 also written by `FUN_CODE_ea99`. Settles: bench measure and read the `ea99` call context.
6. Unresolved 36% of accesses (`?` rows): names would come from running the Dahua firmware in the sim over more modes (HDMI, DP, power states); the sim trace already resolved 193 addresses.

## Touched by Dahua but not by our firmware (sim traces, > address level)
- Audio DAC block 0x06C0-0x06E3 (14 registers); IR block 0x23AA, 0x23AB, 0x23B2, 0x23BB; PORT73/PORT74 (P7.3/P7.4) and P9.7/PA.0 (fe2f/fe30) writes; I2C master engine registers (0xFF55-0xFF5F) and `EWSR_OP_CODE` (0xFF63); pin-share 0x1003, 0x104A, 0x104C (DDC pin switch). [fw]
- 770 Dahua-only addresses in total (mostly video/DP/HDMI/HDCP pages not exercised by our sim or not yet ported); full list is `ours_w == 0 && (writes > 0 || dahua_sim_w > 0)` in `reg_audit.tsv`.

## Touched by our firmware but not by Dahua
- Pin-share 0x1004-0x1048 as individual statics (Dahua writes the same by pointer walk; 72/72 mode bits equal, so no real difference), P4.1 (HPD0), P8.3 (EDID WP), PWM `PWML` 0xFF46 / `PWM45L_DUT` 0xFF52, `ISP_SLAVE_ADDRESS` 0xFFEC, `SCA_WR_INTRVL` 0xFFF1. [fw]

## Not covered
- Code the sim does not reach (other input modes, power states, factory menu), and the static `?` rows.
- Contents of OSD/menu code paths beyond register names; semantics of register values (this audit is about which registers, not which values).
- GPIO levels at runtime beyond the existing live dumps.
