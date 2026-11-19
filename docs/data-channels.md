# Host <-> monitor data channels (#250, #251, #80)

Compiled 2026-11-19. One table, sorted by Max KB/s, fastest first (ties: higher Min first; n/a rows last). Speeds in KB/s (1 KB = 1000 B). n/a = no data rate (flag, 1 bit, or not examined).
- Min / Max KB/s: lowest practical (measured or latency-bound) / best measured or wire ceiling.
- Min / Max MHz: clock of the link that carries the channel (I2C SCL, AUX bit rate, pixel / TMDS character clock, DP link symbol clock, audio bit or sample clock, MCU clock). Pixel-clock range 25 = 640x480@60, 594 = 4K60.
- Basis: **measured** = in this repo (source in Notes); **calc** = arithmetic from the stated numbers; **estimate** = calc with assumptions marked in the section below the table; **unverified** = general knowledge or not examined. Nothing tagged calc / estimate / unverified has been run on hardware.
- The two link-capacity rows (DP main link, TMDS) are wire capacity, not a channel: the MCU cannot read at that rate.

| # | Interface | Channel | Dir | Min KB/s | Max KB/s | Min MHz | Max MHz | Basis | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | DP | Main link capacity | host -> monitor | n/a | 2700000 | 162 | 540 | unverified | HBR2 21.6 Gbit/s raw (RBR 162 MHz -> HBR2 540 MHz symbol clock); not the limit |
| 2 | HDMI | TMDS link capacity | host -> monitor | n/a | 2250000 | 25 | 600 | unverified | 18 Gbit/s (HDMI 2.0, 600 MHz character clock); not the limit |
| 3 | HDMI/DP | MCU DDR write | host -> monitor | 700 | 9000 | 87.7 | 87.7 | estimate | `MCU_DC_*` page 37, cmd 100, per-byte `WMASK`, 16 B per burst; 4K RGB888 = 1 555 200 bursts, so partial edits only; see "MCU DDR estimate" |
| 4 | HDMI/DP | MCU DDR read | host -> monitor | 800 | 7000 | 87.7 | 87.7 | estimate | cmd 101, 16 B per burst; see "MCU DDR estimate"; not measured |
| 5 | HDMI/DP | Audio PCM | host -> monitor | 192 | 4600 | 3.07 | 49.2 | calc | stereo 48 kHz 16-bit -> 8 ch 192 kHz 24-bit; I2S bit clock 2x32x48 kHz / 8x32x192 kHz; wire rate; samples are not MCU-readable: 24-bit DAC PCM, DVC and final outputs are on the 40-bit test-out bus (`AUD_TEST_PIN.aud_test_sel` 0x06E8, `MUX_TST_OUT` 0x6F03) and the I2S / S/PDIF out pins; no readback register found; pins on this board not checked (#250) |
| 6 | I2C/DDC | Bus 3.4 MHz | both | n/a | 380 | 3.4 | 3.4 | calc | i915 GMBUS has nothing above 1 MHz; 8051 slave tolerance untested |
| 7 | I2C/DDC | Bus 1 MHz | both | 35 | 110 | 1 | 1 | measured / calc | min = flash burst incl. flash write time (2026-11-18, `docs/flash-screen.md`); max = I2C ceiling |
| 8 | I2C/DDC | Debug slave 0x35 | both | 0.37 | 110 | 0.1 | 1 | calc | our firmware: XDATA read/write, diag block, #80 rings; bus-bound; #80 throughput not checked; 1 MHz NAKs were a firmware fault, fixed (`docs/diag-block.md`) |
| 9 | VGA | DDC | both | 0.37 | 110 | 0.1 | 1 | unverified | same I2C as above |
| 10 | I2C/DDC | External I2C master | both | n/a | 110 | 0.1 | 1 | unverified | USB / Pico on the DDC pins, bypasses the GPU; slave limit untested |
| 11 | DP | AUX native DPCD | both | 0.4 | 70 | 1 | 1 | calc | 16 B/transaction; min = latency-bound (43 ms/transaction, measured on I2C-over-AUX 2026-11-04); max = 1 Mbit/s ceiling (60-70); host path `/dev/drm_dp_aux*` (raw DPCD, not checked); I2C-over-AUX speed select = DPCD 0x109 (`DPCD_I2C_SPEED_SET`, capability `DPCD_I2C_SPEED_CTRL` at 0x00C, resets 0x00 = no speed control advertised), not read on a unit |
| 12 | I2C/DDC | Bus 400 kHz | both | n/a | 44 | 0.4 | 0.4 | calc | i915 GMBUS has no real 400 kHz step (`docs/flash-burst.md`) |
| 13 | I2C/DDC | ISP slave 0x4A | both | 8.4 | 35 | 0.1 | 1 | measured | 896 KiB in 109 s (100 kHz) / 26 s (1 MHz), 2026-11-18, `docs/flash-screen.md` |
| 14 | DP | SDP / InfoFrame | host -> monitor | n/a | 28 | 162 | 540 | calc | `DP_INFO_FM_*`; Max = ceiling at 1000 Hz, 28 B per frame per type, only if the host changes the packet every frame; same host-update limit as HDMI InfoFrames, not measured (#250) |
| 15 | HDMI | InfoFrames | host -> monitor | n/a | 27 | 25 | 594 | calc | 4 RSV slots (`PTRSV0..3`, bytes via `HDMI_PSAP/PSDP`); Max = ceiling at 1000 Hz, 27 B per frame per slot, only if the host changes the packet every frame; a GPU repeats the same packet each frame, so the real rate = host update rate (DRM commits), not measured, no min; Linux userspace exposes only `HDR_OUTPUT_METADATA` (26 B), arbitrary vendor / SPD frames not confirmed (#250) |
| 16 | I2C/DDC | Bus 100 kHz, 255 B | both | 5.0 | 26.1 | 0.1 | 0.1 | measured | 2026-11-04, `docs/monitors/README.md`: bus 10 (iGPU DP AUX) 5.0, bus 16 (HDMI DDC) 10.2, bus 20 (dGPU DP AUX) 26.1; I2C ceiling ~11, bus 20 exceeds it (cause not investigated) |
| 17 | I2C/DDC | EDID slave 0x50 | monitor -> host | 0.37 | 26.1 | 0.1 | 0.1 | measured | read-only, bus rate |
| 18 | HDMI/DP | Dimming stats (DCR) | host -> monitor | 0.36 | 25 | 25 | 594 | calc | `DCR_ADDRESS_PORT` 0x07D8 / `DATA_PORT` 0x07D9 / `DCR_CTRL` 0x07DA; 6 B/frame (two 24-bit above-threshold counts) -> ~25 B/frame, 60 Hz -> 1000 Hz; count exact (box 500000, full frame 8294400) [measured 2026-11-19, unit 1]; HLW window did not gate the count; see "Measured on unit 1" (#255) |
| 19 | HDMI/DP | Audio peak detector | host -> monitor | 0.016 | 24 | 0.048 | 0.192 | estimate | `PEAK_CTRL_*` page 08 0x08C0-0x08CB: per-channel 24-bit threshold, window in sample periods, `peak_ovfl_det_l/r` flags + IRQ; 1 bit per window: default 384 fs = 0.016 KB/s at 48 kHz, window of 1 fs = 6 KB/s (48 kHz) -> 24 KB/s (192 kHz) ceiling; minimum window, flag stickiness and the ~1800 cycles per sample at 48 kHz not checked (#250) |
| 20 | I2C/DDC | Bus 100 kHz, 16 B | both | 0.37 | 8.6 | 0.1 | 0.1 | measured | same source as row 16; bus 10 ~43 ms/transaction, bus 20 8.6 |
| 21 | DP | Audio channel status | host -> monitor | 0.8 | 5 | 0.032 | 0.192 | calc | `DP_AUD_CH_STATUS0..4`, 40 bits per 192-frame block: 32 kHz -> 192 kHz; needs host control of the status bits (ALSA IEC958, driver not checked) |
| 22 | HDMI/DP | Pixel CRC codebook | host -> monitor | 0.06 | 1 | 25 | 594 | calc | `TMDS_CRCOB2`; ~8 bits/frame, 60 Hz -> 1000 Hz; hash only (#251) |
| 23 | I2C/DDC | DDC/CI slave 0x37 | both | 0.05 | 0.16 | 0.1 | 0.1 | measured / calc | 16 B buffer, 0.1-0.3 s per call (`docs/ddc-control.md`); not for bulk |
| 24 | HDMI | CEC | both | 0.035 | 0.04 | 0.0004 | 0.0004 | calc | block present (`_HW_HDMI_CEC_GEN`); host GPUs usually do not wire the pin |
| 25 | HDMI/DP | Dimming histogram (DCC) | host -> monitor | n/a | n/a | 25 | 594 | unverified | `DCC_ADDRESS_PORT` 0x07C9 / `DCC_DATA_PORT` 0x07CA; bin count and readability not checked (#251) |
| 26 | HDMI/DP | Screen freeze + DDR staging | host -> monitor | n/a | n/a | 25 | 594 | unverified | `LS_SCREEN_FREEZE_MODE_CTRL` 0x03EE (`sfm_cap_en`, `sfm_w_done`, `sfm_disp_en`), InfoFrame as marker, read via `MCU_DC_*`; one 4K frame ~25 MB, 896 KiB flash image fits in ~300 k pixels; flash write (3 ms / 256 B page, CPU halted) becomes the limit; marker timing, lossless capture, `_AWTO_FREEZE` build not checked |
| 27 | HDMI | Audio channel status | host -> monitor | n/a | n/a | 0.032 | 0.192 | unverified | no named HDMI register found; only sample-rate detect |
| 28 | DP | Audio MAUD / NAUD | host -> monitor | n/a | n/a | n/a | n/a | unverified | `MSA_MAUD/NAUD` 24-bit values, normally GPU-computed; only a modified driver can use them |
| 29 | I2C/DDC | SCDC slave 0x54 | both | n/a | n/a | 0.1 | 0.1 | unverified | HDMI only; flags / status |
| 30 | HDMI | HPD | monitor -> host | n/a | n/a | n/a | n/a | unverified | 1 bit per event; a pulse can trigger a modeset |
| 31 | DP | IRQ_HPD short pulse | monitor -> host | n/a | n/a | n/a | n/a | unverified | 1 bit per pulse (0.5-1 ms) |
| 32 | HDMI | SCDC read request | monitor -> host | n/a | n/a | n/a | n/a | unverified | 1 flag |
| 33 | HDMI | HEC / ARC / eARC | - | n/a | n/a | n/a | n/a | regdb, SDK | absent on this chip (no registers, no SDK option) |
| 34 | VGA | Analog RGB, H/V sync | host -> monitor | n/a | n/a | n/a | n/a | unverified | not examined; no capture register for a data channel found; whether this monitor has a VGA connector is not confirmed (scaler has `VGATOP_*` registers; a VCP input read once showed "VGA-2", an input name only) |

DP carries rows 3-5, 18, 19, 22, 25 and 26 as well (same scaler path after the receiver).

## MCU DDR estimate (read / write, 16 B burst)
- Assumptions: MCU 87.7 MHz (351 MHz PLL / 4, `docs/diag-block.md`), 1 cycle = 11.4 ns; MOVX 2 cycles, `mov dptr,#` 2 cycles (micro-bench, `docs/diag-block.md`); DDR latency 0.4 us (assumed, not measured); no arbitration stalls.
- Hand-written register access (~25 MOVX per burst: address 4, command 1, flag poll, 16 data bytes): read ~156 cycles + 0.4 us = ~2.2 us per 16 B = ~7000 KB/s; write ~115 cycles + 0.4 us = ~1.7 us per 16 B = ~9000 KB/s. These are the Max KB/s.
- SDK-style access (`ScalerSetByte` / `ScalerGetByte` function calls, ~70 cycles each): ~20 us per burst = ~800 KB/s read, ~700 KB/s write. These are the Min KB/s.
- The MCU has little free XDATA and cannot store this rate: the sink (flash write ~85 KB/s, or processing) is the real limit.
- To replace with a measured value: time 1000 bursts on unit 3 (#251).

## Measured on unit 1 (2026-11-19, #255; debug slave 0x35 over I2C, MCU running, 4K60, default 350.8 / 116.9 MHz FRC image)
- DCR [measured]: above-threshold count exact for a host box (1000x500 white on black: 500000), solid red (8294400 = 3840x2160). `ready_to_read` sets within 1 frame (4-44 ms after clear); the first ready after a settings change can hold the old frame (use the second). `HLW` window (0x0060/61, `win_dcr_sel`) did not change the count (window 100,200,500x250 and outside-window: still 500000).
- Host-side rates [measured]: single register read 2.4 ms, write 1.8 ms; 16 B block read of `DATABUF_R` 3.5 ms (4.6 KB/s); a complete 16 B DDR read burst through `MCU_DC_*` (LEN, 4 ADDR bytes, flush read, CMD, flag poll, buffer read) 20.0 ms = 0.80 KB/s. This is the host I2C rate, not the MCU rate: rows 3-4 stay estimates until the firmware loop is timed.
- DDR [measured]: frame buffer is only live in frame-buffer mode (P5_AC bit2:1 = 0; test cmd 0x0C); at 4K60 the SDK uses the line buffer and the DDR holds stale data. In frame mode `CAP_M1_MEM_ADDR` = 0, frame at address 0..0x2F7A00 (3 110 400 units of 8 B = 3840x2160x3 B), `CAP_M1_LINE_STEP` 0x5A0 units (1440 = 3840 px x 3 B / 8), `BLOCK_STEP` 0x17BB00 (1080 lines). Solid colours read back as 24 bit per pixel, bytes B, G, R in memory order.
- Freeze [measured 2026-11-19, unit 1, FRC image, frame mode forced]: writing `P5_27` and `P45_27` bit2 (`CAP_Mn_DDR_CTRL1`, what `ScalerFRCDisplayFreeze` sets) stops the capture: DDR kept the red frame while the host showed black; clearing the bits resumes it. No freeze build is needed to hold a frame.
- MCU_DC read data [measured, frozen frame]: a burst at a fixed address returns the right neighbourhood but at a varying 8 B beat offset, read to read (solid red: units (a, a+2) then (a+1, a+3); `xbits` pattern: first half unit phase 0, 1 or 2 mod 3 across three reads, second half = first - 1). Reads of one address do not repeat, so byte-exact readback by address needs self-describing data (position code in the pixels) or a consensus of several reads; port A also timed out on ~25 % of bursts, port B less. The host pattern's non-extreme colours carry +-1 temporal dither (NVIDIA): use 0 / 255 channel values for byte-exact checks.
- `MCU_DC_LEN` != 2 on port A (1, 4): flag never set, `CMD` stays 0xA0, later reads on A time out; port B kept working; the display was disturbed (M1 overflow, wrong DCR counts) until the SDK memory choice was restored (test cmd 0x0D).

## Not examined
- Board UART / ISP pins (physical access), any monitor USB port, I2S / S/PDIF output pins on the board, DDR clock frequency.

## Reading it
- Bidirectional at useful speed: I2C/DDC and DP AUX (host-polled); CEC is bidirectional but ~0.04 KB/s.
- Monitor-initiated: HPD, SCDC read request, CEC.
- Packet and CRC rates scale with frame rate, not link speed (tiny high-refresh mode is the lever, #250).
- Link capacity is never the limit. Pixel readback exists (dimming statistics, MCU DDR port); the open question is its measured rate and picture impact (#251).

## Issues and next tests (state lives in the issues)
- #250: channel inventory (InfoFrames, AUX, audio, CEC, overclock options); comments hold the dated findings.
- #251: pixel path (dimming statistics, MCU DDR port, freeze-frame staging, redundancy and CRC).
- #253: link error counters in the diag log + pixel-clock sweep (1080p as the safe reference mode, find where errors start; Dan has seen none).
- #254 Test 1: DP faster than I2C-over-AUX (raw AUX DPCD, DPCD 0x00C / 0x109 speed select, DPCD mailbox). Needs a DP cable decision from Dan (label needs-dan).
- #255 Test 2: read and edit actual frame data (DCR statistics, DDR read / write via `MCU_DC_*`, frozen frame, marker frame).
- #80: IP over DDC (built; supersedes #61, closed 2026-11-11). awto-dan#110: permission rules for agent GitHub writes (installer script drafted, never run: auto mode blocks agents editing their own settings).

## Session record 2026-11-19 (decisions, corrections, open points)
- Dan: #250 stays open even though #80 works at 1 MHz; InfoFrames to be investigated.
- Dan: monitor is a dumb byte mailbox; host does all routing and IP. Bus contention only causes errors (CRC, sequence numbers, retries); exclusive bus access is not required.
- Dan: the 0x35 NAKs at 1 MHz were "another process on the bus". `docs/diag-block.md` records a firmware cause (ISR latched the command, `ScalerDebug()` loaded the reply a main-loop pass later), fixed. Both are noted; which one was the whole story is not settled.
- Corrections made: audio PCM row restored (samples exist on the test-out bus, I2S / S/PDIF pins and the peak detector; no MCU snapshot register found); "no MCU pixel readback" was premature (DCR / DCC statistics, `MCU_DC_*` DDR port); InfoFrame / SDP min dropped (ceiling only, host update rate unmeasured); DDC at 100 kHz on DP is not the binding limit (26.1 KB/s measured on bus 20).
- Not examined: board UART / ISP pins, monitor USB, I2S / S/PDIF pins, DDR clock, VGA connector presence, CEC / SCDC read-request registers.
- Rules of the work: tests on unit 3 only; every number carries a basis tag; measurements replace estimates in this file.
