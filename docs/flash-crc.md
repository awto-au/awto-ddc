# Flash CRC engine + incremental flashing (#12)

## On-chip CRC (RTD2795T regdb page FF)
- Regs (ISP slave 0x4A uses the same low bytes as FF60..FF7F): start 0x64-66 (`FLASH_PROG_ISP0-2`), end 0x72-74 (`CRC_END_ADDR0-2`), start/done in 0x6F (`PROGRAM_INSTRUCTION` bit2 `crc_start`, bit1 `crc_done`), result 0x75 (`CRC_RESULT`, 8 bit) [regdb]
- Trigger: write 0x6F = 0x84 (isp_en | crc_start); poll bit1 until 1; read 0x75. Trigger only works in ISP mode [regdb, KunYi/RTD266x `SPIComputeCRC`]
- Algorithm: CRC-8 poly 0x07, init 0, no reflection, end address INCLUSIVE (`SPIComputeCRC(0, size-1)`) [oss: KunYi/RTD266x `programmer/crc.c` + `main.c`]. Python: `flash_state.crc8` (check value `"123456789"` = 0xF4, unit-tested)
- Not used by the Realtek SDK source (only declared in `McuCommonInclude.h`); RTDTool "File CRC / Read Code CRC" fields are host-side
- 8 bit: a corrupted sector passes with p = 1/256. Observed corruption mode (shifted/duplicated chunk, #12) is a burst, which CRC8 catches 255/256
- Status: [oss] for RTD2660; RTD2795T behaviour is [guess] until `rtd_flash_image.py` logs `CRC calibration OK` on hardware. The tool self-checks per session (hw CRC vs crc8 of a readback of 0x0+4096 and 0x0+1024) and falls back to readback verify on any mismatch

## Manifest `tmp/fw/<serial>-flash-state.json`
- `sectors[256]`: SHA-256 of what is known to be in each 4 KiB sector, `null` = unknown
- Written after every verified sector (saved each 16), after any full flash read; a sector is `null` from its erase until its verify passes
- Plan: hash image locally; `hash == manifest` skip, `differs` write, `null` readback then write only if different
- Drift guard before skipping: readback+SHA of first, last, 2 random skipped sectors, plus CRC sweep of every other skipped sector; any mismatch -> full readback diff of the image region (authoritative, ~1/5 of a full write) and the manifest is rebuilt from it
- Sectors beyond the image are never touched or hashed (banks 14-15, #8)
- Other flows: `--full` ignores it; no manifest = write all; without `--no-backup` the old dump+readback diff runs and refreshes the manifest

## Bus speed
- i915 GMBUS rate is hard-coded `GMBUS_RATE_100KHZ` (`intel_gmbus.c`, `bus->reg0 = pin | GMBUS_RATE_100KHZ`); no module parameter (`/sys/module/i915/parameters` has none), no sysfs/debugfs knob. Bit-bang fallback uses a fixed `I2C_RISEFALL_TIME` delay
- DP-AUX i2c buses are slower (2.75 KB/s measured, `rtd_isp_probe.py`)
- Faster = a different master (USB-I2C adapter on the DDC pins, as the RTD2660 tools use) or a patched kernel
