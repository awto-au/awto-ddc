# Realtek RTD display scalers (RTD2xxx)

Reversing conventions (confidence tags, one address one name): awto-dan `docs/embedded/reversing/README.md`. Device notes: [`docs/monitors/`](../../monitors/README.md).
Vendor-tool analysis (Ghidra projects, decompile dumps) lives in `~/vendors/realtek/analysis/`, not here.

## ISP access over DDC (I2C slave 0x4A)

| Item | Value | Tag |
|---|---|---|
| ISP I2C slave | 0x4A | [oss] ghent360/RTD-2660-Programmer; ACK seen on target monitor via `/dev/i2c-10` (i2cget, 2026-11-04) |
| Enter ISP | write 0x80 to reg 0x6F; read back bit 7 set | [oss] |
| SPI engine ctl / opcode | reg 0x60 (`type<<5 \| nw<<3 \| nr<<1`, bit0 = go/busy), reg 0x61 = SPI opcode | [oss] |
| SPI addr / write data | regs 0x64-0x66 | [oss] |
| SPI read data | regs 0x67-0x69 | [oss] |
| JEDEC ID | opcode 0x9F, 3 reads | [oss] |
| Bulk read | regs 0x60=0x46, 0x61=0x03, addr 0x64-66, 0x60=0x47, data from reg 0x70 (64 B chunks) | [oss] |
| Page program | reg 0x71 = len-1, addr 0x64-66, data to reg 0x70, reg 0x6F = 0xA0 | [oss] |
| CRC | start 0x64-66, end 0x72-74, reg 0x6F = 0x84, wait bit1, result reg 0x75 | [oss] |

- All rows from RTD2660/2662 prior art; RTD27xx-generation match is [guess] until confirmed.
- `[fw]` confirmation from the vendor tool: see `~/vendors/realtek/analysis/`.

## Public prior art
- https://github.com/ghent360/RTD-2660-Programmer (protocol above)
- https://github.com/KunYi/RTD266x, https://github.com/floppes/RTD266xFlash, https://github.com/KerJoe/RTDMultiProg
- https://github.com/Dizi0/RTD-Firmwares (RTD2556 firmware builder)
