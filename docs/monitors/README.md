# Monitors with Realtek scaler boards (AliExpress-class 4K)

Tracking issue: https://github.com/awto-au/awto-ddc/issues/1

## Files
- `jxc-4k-edid.bin`: raw EDID read from `card0-DP-1` on 2026-11-04
- Vendor tool: `~/vendors/realtek/` (see its `README.md`)

## JXC "4K MONITOR" (DP-1)
- Scaler: Realtek (VCP 0xC8), caps model `RTK`, part number unknown
- Firmware level (VCP 0xC9): 0.1; MCCS 2.2
- EDID: vendor `JXC`, product 0x2800, serial `demoset-1`, week 51/2020
- No USB device in `lsusb` attributable to the monitor
- `ddcutil getvcp known` on bus 15 returned "No monitor detected" on 2026-11-04 10:xx; earlier `detect` found buses 11, 15, 21

## Flashing options (RTD27xx class)
- Realtek RTDCustomerTool V3.7 back-ends: DP AUX (`Comm_Aux`), GPU I2C (`Comm_GFXI2C`), Realtek USB, Type-C USB, FTDI, CH341A (via third-party DLL)
- Whether the monitor's firmware accepts ISP over DP AUX / DDC is untested
- Static read of `Comm_Aux.dll` / `Comm_GFXI2C.dll` (strings, nothing executed; extracted to `tmp/rtdtool/rtdtool-3.7/`):
  - They reach the monitor through GPU-vendor Windows driver APIs: AMD ADL (`ADL_Display_NativeAUXChannel_Access`, `ADL_Display_DDCBlockAccess_Get`) and NVIDIA `nvapi.dll`; Intel device struct present too
  - Wine cannot map those to Linux DRM/i2c-dev, so the AUX and GPU-I2C back-ends will not work under Wine
  - USB back-ends (RealtekUSB, FTDI, CH341A) need vendor kernel drivers; not worth a Wine attempt
  - Exported comm API is small (`I2CRead/Write`, `IspEnable`, `ReadFlashData`, `SectorErase`, `WriteFlashData`, `SetAuxMode`): a Linux-native tool over `/dev/i2c-N` is the realistic path (see ghent360/RTD-2660-Programmer for the RTD266x protocol)
- Wine is not banned; the limit here is technical (above): no DRM/i2c-dev or kernel-driver access

## Read-only I2C probe (2026-11-04)
- Bus numbers shift on re-enumeration; `ddcutil detect --brief` then showed i2c-10 (`card0-DP-3`, Intel iGPU), i2c-16 (`card1-HDMI-A-3`), i2c-20 (`card1-DP-4`), all reporting the same monitor
- `i2cdetect -y -r 10` found 0x30, 0x37, 0x4a, 0x4b, 0x50
  - 0x30 EDID segment, 0x37 DDC/CI, 0x50 EDID: expected
  - 0x4a and 0x4b: extra devices; negative controls 0x44 and 0x6e NACK, so the ACKs are real
- `i2cget` at 0x4a returned 0x00 on buses 10, 16 and 20 (0x4b only seen on bus 10)
- 0x4a matches the Realtek ISP slave address used by the RTD266x tools (ghent360); unconfirmed for this scaler
- Reads only; no writes sent
- Intel iGPU path (i915 exposes DP AUX as `/dev/i2c-N`) is usable for a Linux-native ISP tool
- ISP entry (reg 0x6F=0x80) read back 0x92 (bit 7 set); SPI flash JEDEC ID `C2 20 14` (Macronix, 1 MiB). Script: `scripts/rtd_isp_probe.py`

## Flash fingerprint (2026-11-04, ISP read-only dumps in `~/vendors/realtek/analysis/dumps/`, tool: `scripts/rtd_dump_info.py`)
- CPU: 8051-compatible MCU core inside the scaler; image starts with an 8051 vector table (LJMP reset to 0x23F4, interrupt slots every 8 B) [fw]
- Flash: Macronix JEDEC `C2 20 14` (1 MiB) on all dumped units; used banks 0-6 (64 KB each, bank 6 partly), 0xFF fill from 0x70000, small blocks near 0xE0000/0xF0000, last used byte 0xFCFFF
- Bus 16 vs bus 20 dumps: code, EDIDs and caps strings identical; only 0xFB001-0xFCFFF differs (settings area) [fw]: same board + firmware build
- EDID: three 256 B-spaced copies at 0x138D8 / 0x139D8 / 0x13AD8 (one per input port); each reads `JXC` / `4K MONITOR` / `demoset-1`
- DDC caps string is plain text in flash, two copies at 0x52D72 and 0x52DD9: `(prot(monitor)type(LCD)model(RTK)cmds(01 02 03 07 0C E3 F3)vcp(02)mswhql(1)asset_eep(40)mccs_ver(2.2))`
  - `vcp(02)` lists only one feature; the firmware answers many more (see DDC/CI section below)
- Bus 10 dump (Intel DP, 256 B reads, ~3.5 min) matches the other two the same way: all three units run the same firmware build; only 0xFB001-0xFCFFF (+ 0xFBFFB-0xFCFFF) differs
- The dumps leave each monitor in ISP mode (scaler MCU halted, DDC/CI silent, `ddcutil` shows "Invalid display")

## ISP exit without power-cycle (2026-11-04)
- `rtd_isp_probe.py <bus> --resume` writes 0x02 to ISP reg 0xEE (from naorunaoru/rtdflash [oss]); the write times out (errno 110) as the scaler resets, and DDC/CI answers again within seconds [fw+measured]
- Worked on all three units (buses 10, 16, 20)
- ISP reg 0x23 reads 0x6E on the units tested (buses 16, 20): rtdflash uses reg 0x23 to detect the ISP address family

## DDC/CI actually works despite the caps string (2026-11-04, bus 20, read-only unless stated)
- Caps string lists only `vcp(02)`, but the firmware answers: 0x10 brightness (max 100), 0x12 contrast (max 100), 0x14 colour preset (7500 K), 0x16/0x18/0x1A RGB gain (max 100), 0x6C/0x6E/0x70 black levels, 0x87 sharpness (max 4), 0x62 volume, 0xCC OSD language, 0xD6 power mode (DPM On), 0xAC/0xAE sync freqs, 0xC8/0xC9/0xDF identity
- 0x60 input source reads `VGA-2 (sl=0x02)` on the DP-connected unit, and "Invalid value" in one `getvcp known` pass: do not rely on it yet
- 0xCA `sh=0x00` is the power-button field, not 0xD6 (see issue #1 for the research)
- Write test: `setvcp 0x10 80` read back 80; restored to 100. Brightness on buses 10 and 16 was 80 before this session's tests
- Power (bus 20, `ddcutil --noverify setvcp 0xd6 N`, each value sent alone, 2026-11-04):
  - `4` -> reads back `DPM: Off, DPMS: Standby (sl=0x02)`; user confirmed the monitor went to standby; DDC/CI keeps answering (brightness read OK)
  - `2` -> no change (still On)
  - `1` -> back to On, reads `sl=0x01`
  - Without `--noverify`, ddcutil reports `DDCRC_VERIFY` because the read-back value differs from the value sent (4 reads back as 2)
- Not tested: 0x60 set (input select), `0xD6` values 3 and 5

## I2C read throughput (2026-11-04, `scripts/i2c_bench.py`, 3 s per cell, read-only)

| Bus | Path | 16 B | 64 B | 255 B |
|---|---|---|---|---|
| 10 | `card0-DP-3`, Intel iGPU DP AUX | 0.37 KB/s | 1.44 KB/s | 5.0 KB/s |
| 16 | `card1-HDMI-A-3`, discrete GPU HDMI DDC | 7.9 KB/s | 9.7 KB/s | 10.2 KB/s |
| 20 | `card1-DP-4`, discrete GPU DP AUX | 8.6 KB/s | 18.6 KB/s | 26.1 KB/s |

- Bus 10 costs ~43 ms per transaction regardless of size (16 B and 64 B both ~45 ms): fixed overhead, so bigger reads are the lever
- Bus 20 ~1.8 ms/transaction, ~15x faster per call than bus 10
- EDID (0x50) and ISP (0x4A reg 0x70) targets give the same rates: the limit is the transport, not the scaler
- Rated max for I2C-over-AUX / DDC is 100 kHz (~11 KB/s theoretical); bus 20 at 26 KB/s exceeds that, cause not investigated
- 1 MiB flash dump estimates: bus 10 @256 B ~3.5 min; bus 20 @255 B ~40 s; bus 16 ~100 s
- Hardware programmer (AliExpress): listing below

## Programmer listings (AliExpress, checked 2026-11-04)
- https://www.aliexpress.com/item/1005005418648450.html: "RTD2556 programmer ... RTD2795 RTD2660", USB ISP board, ETAxopowo Store, AU$36.79 + AU$9.85 shipping, 15 sold
- https://www.aliexpress.com/item/1005007188788600.html: upgraded RTD programmer, 2x HDMI + 2x VGA + DVI outputs (not opened)
- Maker's usage notes: https://lcddisplay.co/en/realtek-rtd-writer/ (lists RTD2556, RTD2660, RTD2785, RTD2795, RTD2995; USB-A/micro/Type-C in; red LED = SDA, green = SCL)
- Cheap alternative: CH341A programmer + wbcbz7 DLL

## Next
- [ ] Open monitor, read scaler part number and SPI flash chip
- [ ] Try DDC/AUX ISP read with the vendor tool (Windows, outside this box)
- [ ] Dump flash before any write

## Philips 288E2 (the PC's other monitor, `card2-DP-2`, checked 2026-11-05)
- Not Realtek: DDC/CI VCP 0xC8 (display controller type) reports MStar, controller 0x16, firmware 1.0; its capabilities string has no `RTK` model [measured, ddcutil].
- Debug port: not determinable from the PC side. On DP the I2C runs over AUX, which acknowledged every address (same reply for 0x4A, 0x35 and a nonsense address), so probing says nothing [measured]. The Realtek ISP/debug protocol would not apply to an MStar chip anyway.
- Identity: Philips 288E2, serial UK52307000611, week 7/2023, 4K60 native. EDID saved at `tmp/philips/edid.bin` (not tracked).
- Never touch it with our tools: it is Dan's own display. Excluded from all flash/DDC test scripts by EDID serial.
