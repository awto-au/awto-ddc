# DDR draw ops in the monitor (#267)

- Test-only commands that draw into the frame buffer on chip A (even screen rows) through `MCU_DC` port A from the firmware; chip B / odd rows are not drawn (`ddr-map.md`). Source `fw/test/ddr_draw.c`; compiled to nothing unless `-D _AWTO_FREEZE=_ON` (`./dev.py build --freeze`).
- Host: `./dev.py ddr-draw [--unit N] OP:key=val,...` (`scripts/ddr_draw.py`); one command from the host, the monitor draws; each op is timed by the firmware (`AwtoMs`, 1 ms tick) and by the host.
- Interface: params into `g_stAwtoDraw` (map symbol; big-endian), `ucGo = op` last; the main pass runs the op to the end (WDT fed per line) and clears `ucGo`. No test cmd number.
- Frame prep (host side): host window, `0x0C` frame mode (after the window: a mode change resets it), freeze with `0xFE` (`--sdk-freeze`; the P5_27 / P45_27 poke did NOT hold the frame on the freeze image, unit 1 2026-11-19), ops, `0xFF`, `0x0D`. The host screen must be awake (a locked / power-saved host shows no picture and the unit goes to power saving). Ops do not freeze by themselves; `ucFrozen` records the state at op start.

## Layout (one place: the `AWTO_DRW_*` constants in `ddr_draw.c`; measured 2026-11-19, #255, `docs/data-channels.md`)
- 8 B per address unit, 3 B per pixel in memory order B, G, R, burst = 16 B at an even unit = 5.33 px; line pitch exactly 1440 units = 720 bursts; frame base 0.
- The two 8 B halves of the write buffer are swapped: the driver stages `mem[8..15] + mem[0..7]`.
- Block 1 (A < 1 555 200 units = 1080 lines) is shown at screen row = 2 x memory line; the odd row below comes from chip B (E/O mode [SDK], #348 test 1). Ops take SCREEN x, y, w, h; an odd start / height rounds outward to whole memory lines (2 screen rows). Only block 1 is drawn (screen y < 2160).
- `WMASK` bit = 1: byte NOT written. Bit order vs the swapped halves is ASSUMED (`AWTO_DRW_MASK_LANE_BUFFER`: bit n = buffer byte n); op `masktest` checks it on hardware.
- Read-back by address: ops 12-14 below (`ddr_addr_test.py`); a plain `ddr-draw` drawing is still checked with the DCR count (`--count`, lit pixels) or a photo.

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
- DCR counts memory-line pixels (even rows only, chip A): fill 2000 x 1000 screen px = 1 000 000, `frame` = 4 147 200 (3840 x 1080), both exact.
- `fill` 2000 x 1000 white: 188 000 bursts, 279 / 285 / 288 ms = 1.5 us per burst = 10.4-10.8 MB/s (estimate 95 ms, 0.50 us); green: 353 ms (3 buffer loads per line instead of 1). `CMD` slow polls 0: the write completes within the fast spin.
- `frame` white: 777 600 bursts, 926 ms = 13.4 MB/s; `gradv`: 983 ms = 12.7 MB/s.
- `figure`: 1068 bursts, 71 ms (every edge burst reloads the 16 B buffer); `gradh`: 21.3 s (259 200 spans, 82 us each).
- A `DATABUF_W` load of 16 B costs about 68 us (green vs white fill, `figure`, `gradh` all agree): ~4 us per register write, vs ~0.3 us per register access in the burst loop. Data that changes every burst runs at ~0.25 MB/s; solid colours at 10-13 MB/s.

## Address-in-data fill + read-back (ops 12-14, `./dev.py ddr-addr`, `scripts/ddr_addr_test.py`, `tests/test_ddr_addr.py`)
- Region = block 1: 1 555 200 units = 777 600 bursts = 12 441 600 B (3840 x 1080 x 3 B, pitch 1440 units; chip A = even rows of 3840 x 2160). Linear burst index, pitch ignored.
- Pattern per 8 B unit u (memory order): bytes 0..3 = (u ^ seed) little endian, bytes 4..7 = lane constants 5A A5 3C C3; second pass every byte inverted. Seed = per-run constant (stale frame cannot match).
- Params and results live in `g_stAwtoAddr` (map symbol; field table `FIELDS` in the script, checked against the C struct by the test): blk0, blocks (0 = block 1), seed, stride, inv, swap, retry; results: checked, bad, by address bit (28), neighbour-unit / data-only counts, flag timeouts, first 4 bad bursts (index + bytes read).
- Fill touches only the index bytes that change (2 buffer bytes per burst, mid / high bytes every 128 bursts); read-back is in the firmware (CMD read 101, poll `MCU_DC_READ_FLAG`, 16 `DATABUF_R` bytes, compare). Single reads by default; `--double` = extra reads of a bad burst, reported as a separate result.
- Read lane order: `DATABUF_R` is in memory order with the two 8 B halves swapped (`swap=1`); found by the script on 8 blocks (swap 0: 1022 bad of 1024, swap 1: 0).
- A burst whose read flag never sets within 50 ms is counted as a timeout, not compared; the retry pass recovers it.
- `ucPort` (0 = port A / chip A, 1 = port B / chip B, #348): the addr ops address the selected port's registers (port B = port A + 0x40); `LEN` written 2 on either port (regdb reset 0x02, port B read 0x02 on unit 3). Port B lane order on unit 3 = port A's (halves swapped, read and write; #348 test 1). Host: `./dev.py ddr-keep --port a|b|ab`.
- `--extend`: fill + sampled read-back (256 blocks over the filled region) in doubling steps past block 1; capacity = first aliasing. `--watch`: live (not frozen) marker block read back repeatedly. `--regs`: buffer-mode registers.

## Measured (unit 2, freeze image 333c92f + this change, MCU 350 MHz default, frozen 4K60, 2026-11-20, #267)
- Fill: 777 600 bursts, 1008 ms = 12.3 MB/s (1.3 us per burst). Read-back: 50.1 / 50.5 s single-read (0.25 MB/s, 64 us per burst; includes 401 / 409 reads x 50 ms timeouts = 20 s).
- Single-read result, both passes (normal, inverted), seed 0xF5B4A162: 777 600 bursts each, 0 mismatches (0 by every address bit); 401 / 409 reads timed out (0.05 %) and were not compared. Double-read (2 extra reads): 777 600 bursts, 0 bad, 371 recovered by retry.
- Capacity: fill + sampled read-back past block 1: 3 110 400 units clean; 6 220 800 units: burst 0 (unit 0) reads back unit 4 194 304, burst 1 unit 4 194 306 (address bit 22 only), 10 880 of 33 024 sampled bursts bad (= the share of samples below 2 026 496 units that were overwritten): the address wraps at 2^22 units = 4 194 304 x 8 B = 32 MiB = 256 Mbit = one chip (chip A; chip B is a second 32 MiB behind port B, `ddr-map.md`).
- Live (not frozen): marker written into block 1 is overwritten within one frame (0 bad in the first back-to-back sample for some positions, all bad by the 2nd-3rd); the 3 positions after block 1 stay intact over 8 samples (about 64 ms). Registers: `CAP_M1_DDR_CTRL1` 0x82 (`cap_cap_en` 1, `cap_db_en` 0, `cap_sb_sel` 0), `CAP_M1_DDR_CTRL3` 0x00 (`cap_3buf_en` 0), `DISP_M1_DISP_CTRL1` 0x01 (`disp_db_en` 0, `disp_src_sel` 00), `DISP_M1_DISP_CTRL3` 0x00 (`disp_3buf_en` 0); M2 the same.
