# OSD write paths: where the time goes

Sim measurements 2026-11-18, image = main b15e45f + this branch (default build: MCU 350.8 MHz, flash 70.2 MHz, Rotate 180, 1080p60 sim input), `scripts/saver_frame_cost.py --rotate` (10 s window; Scope 1 25 s), logs `tmp/logs/pc_*.out`. Tags: `[sim]` cycle model (hardware direct stores are 2.0x the sim: 1.08 vs 0.54 us/B, [clock-sweep.md](../clock-sweep.md)), `[hw]` measured on unit 3.
Rate knobs and the register sweep: [osd-write-sweep.md](../osd-write-sweep.md).

## Per-frame cost of the saver paths [sim, default clock]
| saver | frames/s [sim] (hw) | frame | upload (glyph / map / turn) | OSD port stage (address sets, SDK call + store) | port bytes / frame | other big stages |
|---|---|---|---|---|---|---|
| Scope 2 | 21.5 (17.55) | 46.5 ms | 6.99 ms = 15.0 %: `S2Glyph` 3.42, `AwtoOsdTurn` 2.70, `S2MapWord` 0.84 | 1.26 ms = 2.7 %: 160 `ScalerOsdAddrSet` (0.74 + 0.38 + ...) | 3951 (glyph 3676 in 68 uploads, map 275) | draw 11.65 ms, frame logic 10.05, helpers (mul / div) 4.05, trampolines 1.2 |
| Asteroids | 25.0 (paced 40 ms) | 40 ms | 0.97 ms = 2.4 %: `AwtoOsdTurn` 0.94 | 0.11 ms = 0.3 % | 588 (22 address sets) | main loop 29 ms of the 40 ms frame is idle slot |
| Pac-Man | paced | 31 ms | 0.11 ms = 0.3 % | 0.05 ms | 29 (map) | saver slot 1.6 ms |
| Scope 1 | (8.16 hw) | ~120 ms | 7.5 % of run time | 1.0 % | glyph only | draw 3.0 %; the tool's frame counter reads 0 here (the ScPass hook does not fire): shares only |
- Writes are not the bound in any saver at the default clock: the OSD port stage is <= 2.7 % of a frame; the glyph turn (`AwtoOsdTurn`, software 180 rotation) is 2x the whole port stage in Scope 2 and Scope 1 (5.8 % / 7.3 %).
- Direct stores are already the default in every saver (`AWTO_OSD_PORT`: osd_screen.c 6, pacman_classic.c 5, scope_saver2.c 4, scope_saver.c 3 sites).

## Paths enumerated
| path | file | store | writes per redraw | status |
|---|---|---|---|---|
| saver map words / glyphs | `scope_saver*.c`, `pacman_classic.c`, `asteroids` via `osd_screen.c` `AwtoOsdWord` | direct | per saver table above | already direct |
| text layer cells (console, menus, health text) | `text_layer.c` `osd_tc_cells` | was `ScalerOsdDataPort`, now direct (this branch) | 3 stores per cell; a full 40 x 15 console = 1800 B | merged here |
| flash / splash screen | `flash_screen.c` | was `ScalerOsdDataPort`, now direct | map 3 B x cells, glyph bytes | merged here |
| VLC font stream | `text_layer.c` `osd_tc_vlc_put`, `qc_osd.c` | `ScalerOsdDataPort` | font load at boot / screen change | left: the decoder consumes the stream at its own rate [?]; direct pacing is unproven on hardware, test in Phase B (`size` group is not the decoder) |
| QC pattern / probes / HWTEST ops | `qc_osd.c`, `testcmd.c` | `ScalerOsdDataPort` and direct (test code) | test only | left |
| address set | every path | `ScalerOsdAddrSet` = 2 RMW on `0x94` + RMW `0x90` + write `0x91`, each a banked call | 160 per Scope 2 frame | see below |

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
