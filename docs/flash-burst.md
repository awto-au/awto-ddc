# Burst page program (#12)

`rtd_flash_image.py --write-mode burst` (default `byte`); `dev.py flash --write-mode burst`.

## Protocol facts
- 0x70 `PROGRAM_DATA_PORT` = "write data port to SRAM", 0x71 `PROGRAM_LENGTH` (8 bit, len-1), 0x6F bit4 `prog_buf_wr_en` (SRAM writable), bit5 `prog_en` (start, auto-clear), bit0 `rst_flash_ctrl` [regdb RTD2795T-CG page FF]
- Page SRAM = 256 B (0x71 = 255 is the max). No FIFO-depth field beyond that in the regdb
- 0x70 is a port, not a register file: no per-byte address, the SRAM write pointer advances per byte [oss: all tools]
- Burst sizes in the wild:
  - ghent360/RTD-2660-Programmer, KunYi/RTD266x: 63 B per write (their USB-I2C gizmo's 64 B limit), 5 writes per page, wait only on 0x6F bit6 (RTD2660) [oss]
  - naorunaoru/rtdflash (RTD2795 family, same ISP slave 0x4A): ONE 256 B write to 0x70 per page through an RP2040 (`i2c_write_timeout_us`, 100-550 kHz), gated by 0x6F.4 before, 0x6F.5 after [oss]
  - wbcbz7/RTDTool-Comm-CH341A (Comm shim only), balika011/realtek_display (docs/firmware repo, no programmer code): no extra protocol info
- No RTD27xx-specific burst limit found. The ISP slave takes 256 B in one transaction on RTD2795; unverified on this unit through GMBUS

## Host bus limits (i915, kernel 7.1 `intel_gmbus.c`)
- GMBUS byte count: 9 bit, 511 max on display ver >= 9 (`GEN9_GMBUS_BYTE_COUNT_MAX`), 256 before. Bigger messages are split into separate GMBUS cycles (new START + address) = broken stream, so gen<9 needs `--burst-chunk <=255`. Here: Tiger Lake class (`gmbus tc3`) = ok
- `gmbus_xfer_write_chunk` feeds 4 B per GMBUS3 write and waits HW_RDY per dword
- i2c-dev: `I2C_RDWR` message len <= 8192, <= 42 messages; `write()` <= 8192 (`i2c-dev.c`)
- Resend hazard (#12): `do_gmbus_xfer` restarts the whole transfer on ENXIO when the failing message is index 0 (once). A mid-message NAK on a 257 B write would duplicate the accepted prefix in the FIFO

## Design
- `Rtd.burst_write`: one `I2C_RDWR` of 3 messages: `[0x6F select][read 1][0x70 + data]`. The select+read pair is an index cycle (i = 0); the data write is i = 2, so a mid-data NAK surfaces as ENXIO instead of being resent. The read byte is 0x6F (buffer-writable check for free)
- Burst error: flush the partial page (kick a program of it into the sector that gets erased and redone, so the SRAM pointer restarts at 0), raise `RuntimeError`; the sector redo runs in byte mode; `SECTOR_TRIES` + CRC/readback verify unchanged
- Not validated: whether the engine resets the SRAM pointer on start (the flush assumes it; `rst_flash_ctrl` is the alternative)
- Tests: `tests/test_flash_burst.py` (bus-level fake with i915 first-message resend model)

## Time estimate (bus arithmetic, 100 kHz, 9 clocks/byte = 90 us)
- Byte mode: 4096 msgs x ~340 us (3 bytes on the wire + driver) = 1.4 s/sector (matches the measured ~1.4 s)
- Burst: 16 pages x 258 wire bytes x 90 us = 0.37 s, + per page ~7 small transfers (addr x2, poll, preface read, 6F r/w, done poll) ~4 ms = 0.07 s -> ~0.45 s/sector
- Sector 2.5 s -> ~1.55 s (erase, CRC ops, setup unchanged); 152-sector image ~380 s -> ~235 s. Assumes all 16 pages non-blank, no NAK redo (each redo costs ~1.5 s)
