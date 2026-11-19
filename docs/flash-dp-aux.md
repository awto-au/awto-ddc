# Flashing over DP AUX (#254)

Measured 2026-11-19 on unit 2 (AWT26110002), Intel iGPU `card1-DP-1`, i2c bus 15 (`AUX USBC2/DDI TC2/PHY C`), 100 kHz-class i2c-dev over AUX; tool `scripts/dp_isp_bench.py` (ISP session, no erase, dry 0xFF page only) and two full flashes (224 sectors, 202 non-blank, 2917 pages, 808 KiB programmed).

## What limits it
- ISP slave 0x4A/0x4B is inside the scaler: no I2C wire, so the I2C speed (DPCD 0x00C / 0x109, regdb `DPCD_I2C_SPEED_CTRL` "register is 00 if the receiver has no physical I2C bus") does not apply. Not configurable.
- Cost is AUX transactions: i915 splits every i2c message into 16 B AUX requests.
  - 16 B data transaction ~0.62 ms (255 B read = 9.8 ms, 26 KB/s); bare / 1-byte transaction ~0.4 ms; most of it is turn-around + driver, not payload bits.
  - Small register write = 1.16 ms, register read (index + read) = 1.7 ms, a write inside a multi-message ioctl = 0.8 ms (each message still restarts).
- Page (256 B) cost before: 22.3 ms = 256 B data 9.9 ms + address writes 2.4 + 5 polling reads 8.4 + start write 1.2.
- Not limits: host CPU, Python, ioctl count, flash tPP (done within the first poll, 1.00 polls/page).

## Phase table, full flash of 224 sectors
| phase (s) | before (`--aux-fast off`) | after |
|---|---|---|
| erase (224 x tSE + engine ops) | 16.5 | 15.6 |
| program (2917 pages) | 67.4 | 38.9 |
| verify (CRC per sector) | 2.7 | 1.6 |
| final CRC + manifest | 0.6 | 0.4 |
| flash screen (OSD redraw; before: the unsplit "other" bucket, 40.3 incl. ~0.7 ISP enter/reset) | ~39.6 | 4.5 |
| ISP enter / JEDEC / protect / reset | ~0.7 | 0.7 |
| total | 127.5 | 61.8 |
- Rate: 6.4 KiB/s -> 13.2 KiB/s. Unit 3 HDMI at 1 MHz: ~24 s for the same image class.
- Incremental deploy of a different image (202 of 224 sectors changed): 60.6 s.

## What changed
- ISP slave 0x4B = same registers as 0x4A with address auto-increment (probed per session, `Rtd.enable_aux_fast`): 0x64..0x66 and 0x72..0x74 are one message (erase, CRC).
- Page = two transfers: `[0x4B: 64 hi mid][0x4A: 70 + 256 B]`, then `[0x6F <- v|start]`, then polls until 6F.5 clear and 6F.4 set. 22.3 -> 13.3 ms/page.
- Flash-screen redraw capped at 10 % of the run on DP AUX (`flash_screen.DUTY_MAX`); other buses redraw every sector as before.
- Failure: any bus error flushes the page, redoes that sector on the 0x4A burst path (not byte mode), counts as a burst failure.
- `dev.py flash --aux-fast auto|off` (auto = on for `AUX` adapters only; i915 gmbus, NVIDIA unchanged).

## Measured dead ends (do not retry)
- Start write in the same transfer as the data: 6F.4 stays low (buffer never ready again) and the in-transfer read returns 0xFF. Start must be its own transfer; reading 6F inside the data transfer is useless.
- Batching several small writes into one ioctl: ~0.8 ms/message instead of 1.16, no more.
- 0x4A data to 0x70 with auto-increment: not applicable (0x70 is a port).

## Floor and remaining options
- Floor on this link: data 2917 x 9.9 ms = 29 s + erase 15.6 s = ~45 s; now 61.8 s.
- Left over: 13.3 ms/page of which ~3.4 ms is address + start + poll; erase is tSE (~70 ms/sector).
- Not built: firmware-resident copy (DPCD mailbox / frame-buffer staging, row 26 of `docs/data-channels.md`) removes the AUX floor but needs a running firmware, no ISP recovery path.
