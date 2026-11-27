## Question
Can IP/TCP run over the monitor's DDC I2C channel?

## Answer: yes, as a point-to-point serial link (SLIP/PPP over a mailbox). Host and firmware are both ours.

## Transport already in the repo
- Debug slave 0x35 on the DDC wire: read/write of firmware XDATA in the running firmware (`rtd_dbg_read.py`, `rtd_dbg_write.py`; SDK `ScalerDebug`: 0x3A read, 0x3B write).
- Firmware is built from the RL6449 SDK + our layers, so we can add a mailbox ourselves.
- EXINT1 services the DDC slave in the ISR; main loop is free to poll a mailbox.

## Measured link limits (docs/monitors/README.md, 2026-11-04, read-only)
| Bus | 255 B reads |
|---|---|
| 20 (dGPU DP AUX) | 26 KB/s |
| 16 (dGPU HDMI DDC) | 10 KB/s |
| 10 (iGPU DP AUX) | 5 KB/s (~43 ms fixed per transaction) |
- Rated max 100 kHz (~11 KB/s); 0x35 NAKs intermittently at 1 MHz (#12), so 100 kHz.
- Half-duplex, master-driven: the monitor cannot send unprompted.

## Design sketch
- XDATA mailbox: TX ring + RX ring + head/tail + magic/version, same style as the diag block (`docs/diag-block.md`).
- Host: poll TX-ring head (one block read), pull new bytes, push RX bytes with 0x3B writes. Frame as SLIP.
- Host exposes it as a pty (`pppd`/`slattach`) or TAP; monitor runs a tiny stack (lwIP-class or UDP-only).
- Expect ~1-5 KB/s usable, latency = poll period + ~2-45 ms per transaction.

## Limits
- 8051 RAM is the constraint: XDATA map is already tight (`fw_ram_report.py`); a TCP stack is heavy, UDP + SLIP is realistic.
- Vendor firmware has no mailbox: needs our build.
- Writes are one byte per 0x3B command: TX path from host is slow (check burst-write support in the SDK).
- Standard DDC/CI (0x37) is 16 B RX buffer (`_DDCCI_RXBUF_LENGTH`): not usable for bulk, hence 0x35.
- The 0x35 debug port replaces DDC/CI on the active port (RL6449_Project.h:142).

## Next
- [ ] Measure 0x3B write throughput (bytes/s) on bus 20.
- [ ] Check XDATA headroom for rings.
- [ ] Prototype: loopback mailbox (host writes, fw echoes) before any SLIP.
