# DDR draw ops in the monitor (#267)

- Test-only commands that draw into the frame buffer through `MCU_DC` port A from the firmware. Source `fw/test/ddr_draw.c`; compiled to nothing unless `-D _AWTO_FREEZE=_ON` (`./dev.py build --freeze`).
- Host: `./dev.py ddr-draw [--unit N] OP:key=val,...` (`scripts/ddr_draw.py`); one command from the host, the monitor draws; each op is timed by the firmware (`AwtoMs`, 1 ms tick) and by the host.
- Interface: params into `g_stAwtoDraw` (map symbol; big-endian), `ucGo = op` last; the main pass runs the op to the end (WDT fed per line) and clears `ucGo`. No test cmd number.
- Frame prep (host side, as #255): `0x0C` frame mode, black host window, freeze (register poke or `0xFE`), ops, release (`0xFF` / unfreeze), `0x0D`. Ops do not freeze by themselves; `ucFrozen` records the state at op start.

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

## Cost
- Hot loop (`DrwFull`): per burst 1 `CMD` read, `ADDR_L`, `ADDR`, `CMD` write; the write buffer is loaded once per burst phase (3 phases, bursts p, p + 3, ...) per line, `WMASK` and the upper address bytes only on edges / carries.
- Static cycle count, XDATA and code delta: see the issue comment (#267); throughput on hardware: not measured yet.
- Host check: `tests/test_ddr_draw_host.py` builds the firmware file on the host against a port-A model (CMD busy / write-while-busy hazards, swap, mask) and compares every op with a per-pixel spec. The sim has no MCU DDR port model.
