🤖 NVRAM flush line now says what was written (Dan, 2026-11-13: "make the NVRAM flush log line report if anything actually is written").

## Branches / image
- awto-ddc `wb-p14ui-nvlog` a6c57d3 (from wb-p14ui 87ab7c7); tools `tools-nvlog` 175a4d0 (from main 2a17774). awto-rtdfw unchanged. Not merged.
- Image `tmp/fw/AWT26110002-wb-p14ui-nvlog2-be.bin`: gates 27/27 PASS (new gate `nvlog`); flashed on unit 2.

## Lines (unit 2, 2026-11-13)
Before (osdt1 image):
```
+36343 ms NVRAM flush: menu / selector close (since the last poke 16 ms)
+40758 ms NVRAM flush: gate open (since the last poke 1 ms)
```
(a menu close without a change: no line at all)

After (nvlog2):
```
NVRAM flush (menu / selector close): wrote 16 B (OSD data) in 1 program, 0 erases, 8 ms
NVRAM flush (menu / selector close): nothing changed, no flash write (0 ms)
NVRAM flush (power off / saving entry): wrote 16 B (system data) in 1 program, 0 erases, 5 ms
NVRAM flush (power off / saving entry): wrote 32 B (system data, OSD data) in 2 programs, 0 erases, 8 ms
```

## Design
- One line per flush, pushed after it (D4 11..17 = why 1..7; D4 06..0B retired). Erase / page-move lines (D4 03..05) come before it.
- Value (32 bit, saturating, "+" when at max): groups << 27 | erases << 25 | programs << 19 | bytes << 9 | ms.
  - groups (5 bit): system data, OSD data, colour (BriCon / ColorProc / SixColor), panel time, awto settings (aux block); a group counts when the SDK compare let an item program through.
  - erases 0..3, programs 0..63, bytes 0..1023, ms 0..511.
- All settings are in the one SDK store now (aux block = items 0x40..), so "which record" = the group list.
- Counters: `g_stAwtoNv.usErase`, `usBytes` (UserCommonFlashWrite lengths) added; programs = ops - erases.
- ms = AwtoMs (Timer2 tick) across the flush. Timer2 likely stops during a flash halt (sim doc: FFEE[6] mcu_peri_non_stop = 0), so the halt part is probably not in it: CPU time of the flush.
- "nothing changed": a menu close / MCCS save with nothing dirty is logged by the next settings service (was silent); a flush whose items all compare equal says the same with its compare time.
- MCCS 0x0C / VCP 0xE3 = 2 save: own why "DDC/CI save settings" (was labelled "menu / selector close").
- Second BriCon / ColorProc item written at once (AwtoNvDefer snap): own line D4 16 (the old row 0B was never pushed).
- Decoder: firmware `fw/sdcc/awto_nvpop.inc` (included last in RTD2014OsdDisplay.c, so no string renumbering in the bank layout); host `scripts/sync_log.py nv_flush`. Width: worst case 188 cells, 2 console rows (gen_awto_sync.py).

## Tests
- Sim (gate `nvlog` = `nv_test.py --sim --cases flushlog`): change + close -> "wrote", values = counter deltas; close without change -> "nothing changed"; POWER off -> power-off line. PASS.
- Sim note: every item programs twice (96 B in 6 programs for 3 items): the sim flash does not keep writes, the SDK read-back check retries. Unit: 1 program per item.
- Unit 2 (`nv_test.py --unit 2 --cases flushlog,menu,power`): 3/3 PASS, lines above. Debug link off after.
- Loop rate: sim idle ACTIVE 365 -> 366 /s (audit1 -> nvlog2); unit 2 314.7 /s (health; delay cal FAIL as before: tick 9.944 ms).
- XDATA free 2187 B.

## Open
- ms excludes flash halts (probable, not measured): a halt-inclusive time needs a clock that runs during the halt.
