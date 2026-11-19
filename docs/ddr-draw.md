# DDR draw ops in the monitor (#267)

- Test-only commands that draw into the frame buffer through `MCU_DC` port A from the firmware. Source `fw/test/ddr_draw.c`; compiled to nothing unless `-D _AWTO_FREEZE=_ON` (`./dev.py build --freeze`).
- Host: `./dev.py ddr-draw [--unit N] OP:key=val,...` (`scripts/ddr_draw.py`); one command from the host, the monitor draws; each op is timed by the firmware (`AwtoMs`, 1 ms tick) and by the host.
- Interface: params into `g_stAwtoDraw` (map symbol; big-endian), `ucGo = op` last; the main pass runs the op to the end (WDT fed per line) and clears `ucGo`. No test cmd number.
- Frame prep (host side): host window, `0x0C` frame mode (after the window: a mode change resets it), freeze with `0xFE` (`--sdk-freeze`; the P5_27 / P45_27 poke did NOT hold the frame on the freeze image, unit 1 2026-11-19), ops, `0xFF`, `0x0D`. The host screen must be awake (a locked / power-saved host shows no picture and the unit goes to power saving). Ops do not freeze by themselves; `ucFrozen` records the state at op start.

## Layout (one place: the `AWTO_DRW_*` constants in `ddr_draw.c`; measured 2026-11-19, #255, `docs/data-channels.md`)
- 8 B per address unit, 3 B per pixel in memory order B, G, R, burst = 16 B at an even unit = 5.33 px; line pitch exactly 1440 units = 720 bursts; frame base 0.
- The two 8 B halves of the write buffer are swapped: the driver stages `mem[8..15] + mem[0..7]`.
- Block 1 (A < 1 555 200 units = 1080 lines) is shown line-doubled: screen row = 2 x memory line. Ops take SCREEN x, y, w, h; an odd start / height rounds outward to whole memory lines (2 screen rows). Only block 1 is drawn (screen y < 2160).
- `WMASK` bit = 1: byte NOT written. Bit order vs the swapped halves is ASSUMED (`AWTO_DRW_MASK_LANE_BUFFER`: bit n = buffer byte n); op `masktest` checks it on hardware.
- Reads by address are unreliable (#255): there is no firmware read-back or checksum. Check a drawing with the DCR count (`--count`, lit pixels) or a photo.

## Ops (`ucGo`)
| op | `ddr_draw.py` name | params |
|---|---|---|
| 1 | `fill` | x y w h rgb: clipped to the screen |
| 2 | `hline` | x y w rgb: 1 screen row = 1 memory line (2 rows shown) |
| 3 | `vline` | x y h rgb |
| 4 | `grid` | x y w(side) n: n x n cells; n + 1 vertical and n + 1 horizontal lines, palette of 10 |
| 5 | `circle` | x y w(diameter) rgb: 1 px ring in screen geometry, folded onto memory lines |
| 6 | `figure` | x y: grid100 (100 px, 10 x 10, palette) + white circle in ONE command (`scripts/ddr_grid100.py` figure) |
| 7 | `bars` | x y w h: 8 bars white yellow cyan green magenta red blue black |
| 8 | `frame` | rgb: whole block 1 |
| 9 | `gradh` | grey ramp across the frame, 240 bands of 16 px |
| 10 | `gradv` | grey ramp down the frame, one level per memory line |
| 11 | `masktest` | x y: 16 bursts, burst j writes only memory byte j (0xFF) |

States: 2 ok, 3 refused (unknown op, empty / off-screen rectangle, bad grid), 4 stall (`CMD` busy > 50 ms = 3 frames, op aborted).

## Cost (static, from the compiled asm of `DrwFull`, 87.7 MHz = 11.4 ns per cycle; not measured on hardware)
- Hot loop (`DrwFull`): per burst 1 `CMD` read, `ADDR_L`, `ADDR`, `CMD` write = 4 MOVX, 44 cycles = 0.50 us = ~32 MB/s MCU-side ceiling, if the DCU takes a write every 0.5 us (DDR completion time not known: `CMD` busy at the next burst shows up as extra polls).
- Per line: the write buffer is loaded once per burst phase (3 x ~110 cycles; none for grey), `WMASK` and the upper address bytes only on edges / carries: ~1.5 k cycles on top of 720 x 44 = 32 k.
- Estimates: fill 2000 x 1000 px = 500 lines x 375 bursts = 187 500 bursts = 3.0 MB: ~95 ms; `frame` (1080 lines, 12.4 MB): ~0.40 s; the host-driven path was ~6 ms per burst (#255). The issue's 1.7 us / 25 MOVX estimate assumed re-writing the buffer every burst.
- Image delta: default image 0 B (byte-identical but the commit string); freeze image +5027 B banked code, +58 B XDATA (free XDATA 551 B default, 495 B freeze).
- Host check: `tests/test_ddr_draw_host.py` builds the firmware file on the host against a port-A model (CMD busy and write-while-busy hazards, swap, mask) and compares every op with a per-pixel spec. The sim has no MCU DDR port model.

## Measured (unit 1, freeze image 9578a24, 4K60, MCU 87.7 MHz, 2026-11-19, #267)
- Mask lane order: `masktest` counts R/G/B = 5/5/6 (DCR sel 1..3 = R, G, B, checked with a red fill); model for the assumed order (bit n = buffer byte n) is B6 G5 R5, the shifted order would give R6: the assumption holds.
- DCR counts memory-line pixels (before the vertical doubling): fill 2000 x 1000 screen px = 1 000 000, `frame` = 4 147 200 (3840 x 1080), both exact.
- `fill` 2000 x 1000 white: 188 000 bursts, 279 / 285 / 288 ms = 1.5 us per burst = 10.4-10.8 MB/s (estimate 95 ms, 0.50 us); green: 353 ms (3 buffer loads per line instead of 1). `CMD` slow polls 0: the write completes within the fast spin.
- `frame` white: 777 600 bursts, 926 ms = 13.4 MB/s; `gradv`: 983 ms = 12.7 MB/s.
- `figure`: 1068 bursts, 71 ms (every edge burst reloads the 16 B buffer); `gradh`: 21.3 s (259 200 spans, 82 us each).
- A `DATABUF_W` load of 16 B costs about 68 us (green vs white fill, `figure`, `gradh` all agree): ~4 us per register write, vs ~0.3 us per register access in the burst loop. Data that changes every burst runs at ~0.25 MB/s; solid colours at 10-13 MB/s.
