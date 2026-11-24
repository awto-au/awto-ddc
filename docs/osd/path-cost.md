# OSD write paths: where the time goes

Sim measurements 2026-11-18, image = main b15e45f + this branch (default build: MCU 350.8 MHz, flash 70.2 MHz, Rotate 180, 1080p60 sim input). Tags: `[sim]` cycle model (hardware direct stores are 2.0x the sim: 1.08 vs 0.54 us/B, [clock-sweep.md](../clock-sweep.md)), `[hw]` measured on unit 3.
Rate knobs and the register sweep: [osd-write-sweep.md](../osd-write-sweep.md).

Per-saver frame costs (Scope 1 / Scope 2 / Asteroids / Pac-Man) went with the games: `docs/games.md`; the OSD port stage was <= 2.7 % of a frame in every saver, direct stores are the default in every path.

## Paths enumerated
| path | file | store | writes per redraw | status |
|---|---|---|---|---|
| text layer cells (console, menus, health text) | `text_layer.c` `osd_tc_cells` | was `ScalerOsdDataPort`, now direct (this branch) | 3 stores per cell; a full 40 x 15 console = 1800 B | merged here |
| flash / splash screen | `flash_screen.c` | was `ScalerOsdDataPort`, now direct | map 3 B x cells, glyph bytes | merged here |
| VLC font stream | `text_layer.c` `osd_tc_vlc_put`, `qc_osd.c` | `ScalerOsdDataPort` | font load at boot / screen change | left: the decoder consumes the stream at its own rate [?]; direct pacing is unproven on hardware, test in Phase B (`size` group is not the decoder) |
| QC pattern / probes / HWTEST ops | `qc_osd.c`, `testcmd.c` | `ScalerOsdDataPort` and direct (test code) | test only | left |
| address set | every path | `ScalerOsdAddrSet` = 2 RMW on `0x94` + RMW `0x90` + write `0x91`, each a banked call | 160 per Scope 2 frame (removed saver) | see below |

## Ranked wins
| # | change | est. saving per Scope 2 frame [sim] | risk | status |
|---|---|---|---|---|
| 1 | hardware 180 turn on glyph download (T-I) replaces `AwtoOsdTurn` / `AwtoOsdRevByte` | 2.7 ms (5.8 %) Scope 2, 0.94 ms Asteroids, 7.3 % of Scope 1 | needs hardware plane / word order proof | not done: Phase B test |
| 2 | merge the two `0x94` RMWs and inline `0x90` / `0x91` stores into one macro (`AWTO_OSD_ADDR_SET`) | <= 0.9 ms (160 sets x 5.6 us of banked-call + RMW overhead of the 1.26 ms stage) | low: same final register values; not md5-proven on hardware | not done: needs an address-set A/B on unit 3 first |
| 3 | `text_layer.c` + `flash_screen.c` direct stores | console cell 3.2 us less per cell [sim: 3 x (1.62 - 0.54)]; full 1800 B console redraw ~1.9 ms [sim], ~5 ms [hw 3.79 -> 1.08 us/B] | none beyond the saver precedent (T1 / T2 / T5 / T7 byte-exact) | merged |
| 4 | register values from `osd-sweep` (FFF1 / FFFB / FFBC, burst) | unknown until Phase B | speed-raising register change: Dan decides with measured numbers | Phase B |
| 5 | single-plane map writes (`bytesel` B1) for id-only changes | 2 of 3 stores per changed cell | needs the `base_b1` case (auto-increment of a B1-only write) | Phase B |
| 6 | dirty-tile redraw | Scope 2 already writes 68 glyphs + 92 map words per frame (dirty tiles); console redraws full rows | - | nothing left in the savers |
- Proof for #3: the written values are the same stores (`ScalerOsdDataPort(v)` = `ScalerSetByte(0x0092, v)`, OsdAddress90_91_92.c). The OSD state md5 of console and flash preview (`scripts/osd_screens_md5.py`) differs between base and branch images only in time-dependent digits (console timestamps, flash progress text: 55 / 31 font words, all digit glyph ids; palette, registers, windows equal), so an md5 A/B is not possible there; Scope 1 / 2, Asteroids, Pac-Man paths are unchanged code.
