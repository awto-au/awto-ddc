# Known unknowns and their tests

Every `[?]` in the manual. Tests only on unit 3 (bus 11); nothing here has been run for this manual.
- `T1..T10`: `docs/osd-hw-tests.md` (done unless noted). `T-A..T-M`: `docs/saver-fps-hw.md` (not run).
- `OT-n`: new, host-only over ISP (`python scripts/rtd_osd.py 11 --keep wr:REG=VAL osdw:win:ADDR=B0,B1,B2 ...`: the MCU halts, the OSD keeps showing what is written, reboot after). The verdict is a photo compared with the sim picture of the same feature (`docs/osd/img/`), unless a PASS says otherwise. One session can batch OT-9 / 11 / 12 / 15 / 17 / 19 (26 windows, one frame each).

| id | question | method | PASS |
|---|---|---|---|
| OT-1 | 4-bit glyph plane order | ladder like T9: 4-bit ids 0..15, plane k solid, one palette index per plane value | colour shown per plane tells which bit it is |
| OT-2 | OSD independent of the input clock (mechanism) | no test short of a databook; the no-signal and garbled-picture observations stand | low priority |
| OT-3 | map fetch past word 8192: address-width limit or register effect | 90 x 90 map at `fs_base` 4000 with chars crossing 8192 vs the same map below; vary `row_base`, `font_base` | which variable moves the break |
| OT-4 | read-back with circuit on | T1 read, circuit on, scale-up off, overlay off, all-bytes address, 2 reads | 0 bad bytes (then the circuit-off recipe is optional) |
| OT-5 | palette write pointer auto-increment | `0x6E = 0x80 + 10`, 9 bytes to `0x6F`, window colours 10 / 11 / 12 | three distinct colours as written = auto-increment |
| OT-6 | delay set 2, fine tune `0x3A1E` | window with `osd_delay_sel` 1, set 2 moved | window moves by the set-2 amount only |
| OT-7 | blank word | map row: char, blank 40 px bg colour 2, char | blank width 40 px, colour 2 |
| OT-8 | 24 x 36 layout | `0x3A43[6]`, 36-word glyph with marked rows | pixel order read from the photo |
| OT-9 | shadow types 1..4, 3D 1 / 2, border placement | window with `eff_opt` 0..5, 7, 6 px | edge placement equals the sim picture |
| OT-10 | rounded corners | `ADR10` size 00 / 01 / 10, tables `0x3A60..8B` loaded | radius 8 / 16 / 32 px, shape from tables |
| OT-11 | gray level | `ADR9[1]` on a colour window | grey value vs luma formula |
| OT-12 | colour mask | `ADR9[3:2]` over a bars picture | AND / OR of picture and colour |
| OT-13 | window rotate `ADR9[0]` | set on WIN0 with auto rotation on / off | what changes |
| OT-14 | zero-width / inverted windows, end inclusive | x end = start, y end = start, both, end < start | #215 steps 1..6 |
| OT-15 | window vs font priority | win 1 / 3 over text, `0x3A07[0]`, `0x3A08[7:5]` | order as the picture |
| OT-16 | window 7 mask region, window 6 / 7 blend functions | `0x3A09[6:5]`, `0x3A21` | appears only inside / hidden inside; blend per type |
| OT-17 | highlight recolours font | `0x3A2A / 2B` on WIN4_1 over text | fg / bg replaced inside only |
| OT-18 | video highlight window border | `0x0060 / 0x0061`: rectangle, width 3, red, `0x006C[6]` 0 / 1 | red border drawn / hidden; does it draw over the OSD |
| OT-19 | specific colour blending | `0x3A09[7]` + index, level 128 | only that colour blends; which elements |
| OT-20 | font mask regions | `0x3A45..4C` rows / cols | cells hidden as set |
| OT-21 | vertical boundary units | `0x3A18[5]`, upper / lower values | line positions in panel lines |
| OT-22 | scale-up: non-integer factors, edge modes, filter phase, over x2 | `0x3AC0[1:0]`, `0x3AC1`, factors 43 / 51, `0x3A0A` = 3 | picture vs sim |
| OT-23 | `osd_len / wid 1 / 2`, row totals needed? | clear them with a working screen | no change = not needed |
| OT-24 | single-byte (bytesel) write cost | T2 direct loop with `bytesel` B1 only | us per byte |
| OT-25 | alpha direction | level 64 / 192, type 11, bright picture | which share is video |
| OT-26 | scale-up position units | position ladder with scale-up x8 | measured px per unit (H and V) |
| OT-27 | row count limit | 255 rows x 1 col | rows shown |
| T-A | grid lines: pitch unit, panel pitch, priority, scale | `docs/saver-fps-hw.md` | per that doc |
| T-B | chessboard square size | same | |
| T-C | narrow chars: minimum width, zone effect, 240-char row | same | |
| T-D | font B overlap / priority | same | |
| T-E | pop-on flip | same | |
| T-F | horizontal scroll via `fs_base + 1` | same | |
| T-G | hardware auto rotation (and with double size / scale-up) | same | |
| T-H | burst byte time, gap | same (firmware op) | |
| T-I | decoder raw-path 180 turn | same (firmware op) | |
| T-J | masked bit writes | same (firmware op) | |
| T-K | register access timing | same | |
| T-L | MCU x2 clock | same | |
| T10 | write during scan glitch; Scope 2 garble display-side | `./dev.py osd-hw-test --unit 3 cycle`, Dan's look; scale-up-off test planned | pending |

## Model gaps (for the model owner; the manual shows "not modelled" for these)
- Window `sha` / `bor` colour bit 4 (`ADR0` B0 [7:6]) is decoded as bit 5; bit 5 (`ADR3` B0 [7:6]) is not read: indices >= 16 decode wrong.
- Round corners: size code mapping 4 / 8 / 16 / 32 px vs regdb 8 / 16 / 32; the table shape is not used.
- Chessboard colours on WIN4_x / 5_x live in `ADR4`; the model reads `ADR5` only.
- Pop-on needs `fontx2_en` in the model; whether the hardware does is T-E.
- Not modelled: 24 x 36 layout, font mask regions, roll-up, vertical boundary units, window rotate, HLW border, DISP_PG, scale-up filter / edge modes, VLC-turn, shadow type 1..4 differences.
