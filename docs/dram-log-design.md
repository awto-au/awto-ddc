# DRAM log: the sync / diag log ring in the DDR

Issue: awto-ddc (design issue, see its number in the commit). Related: #284, #291, #139, #144. Build switch `_AWTO_DRAM_LOG` (header default `_ON`; `-D _AWTO_DRAM_LOG=_OFF` = the 718 B XDATA ring).
Code: `fw/log/hostnote.c` (DDR access, flush, `AwtoSyncAt`), `fw/log/sync.c` (tail, collapse, T2 re-base), `fw/osd/console.c` (reads through `AwtoSyncAt`).
Host: `scripts/dram_log.py`, `sync_log.py` (`read_ring` version 4, `--dram`), `unit_log.py` (`ingest_dram`). Gate: `scripts/dram_log_sim.py`.

## Why
- XDATA free was 56 B; the ring cost 718 B (88 x 8 B + 14 B) and every new line needs ring room; a boot episode is ~87 lines.
- DDR = 2 x 32 MiB chips; the log is on chip A (MCU_DC port A, path proved by the note store, docs/note-store.md). Map: docs/ddr-map.md.

## Region (chip A, 8 B units, 2^22 units)
- Header burst: units 0x3EBFFE. Ring: units 0x3EC000.. = 32768 slots x 16 B = 512 KiB (31.375 MB .. 31.875 MB), ends at the note store (0x3FC000, 31.98 MB).
- Clear of everything: 4K capture writes one 12,441,600 B block per chip (E/O mode); 1- and 2-buffer modes stay below unit 0x3B5380 (docs/ddr-map.md, #348); panel is 3840 x 2160 only.
- 32768 entries = ~375 boots at 87 lines.

## Entry (16 B = one burst)
- id, arg, ms32 BE, value32 BE, absolute index (24 bit BE), generation, boot, check = xor of bytes 0..14 ^ 0x5A.
- 32 bit stamp: no 16 bit wrap logic in the DDR path. The XDATA 8 B view keeps the low 16 bits (console and host decoders unchanged).
- Valid = check ok, index equals the slot's expected index, generation equals the header's. A slot of the previous lap fails the index test.
- The 12 bit stamp fields inside `sdone` values are durations, not entry stamps: unchanged.

## Header burst
- `D L` version generation boot hint(32) note-sequence(16) check. Hint = index of an entry written at the last header write; rewritten every 64 entries, at boot and at each host note.
- Warm start: XDATA tail valid -> write index from it; XDATA lost (new image) -> scan forward from the hint (<= 2 x 64 + 2 reads).
- Cold power-up (`AwtoBootReason() == COLD`) or invalid header: generation + 1, index 0, boot 0. Old entries never validate.
- Note numbering lives in the header (was: a scan of the ring for the newest NOTE line, 88 DDR reads).

## XDATA
- Header 14 B (unchanged offsets, version 4) + generation, boot, pending, lost, head, write index (32), old = 24 B, + tail 32 x 10 B (8 B entry + ms bits 31..16) = 344 B, at `AWTO_SYNC_ADDR` 0xF53F (no-init, kept over warm reset). Was 718 B at 0xF3C9.
- Tail = collapse look-back (<= 3 lines), the console cache for the newest 32 lines, lines waiting for the DDR (`ucPend`).
- `AwtoSyncAt(seq)`: tail for <= 32 lines back, else one DDR burst into a 2-entry cache (88 lines back = ring depth shown by the console, as before).
- Collapse of repeats (`AWTO_SYNC_SAME`, REPEAT line, counts) is unchanged: it runs on the tail before a line is queued.

## Write path
- Callers of `AwtoSyncPush` / `AwtoSyncPushQuiet`: main loop only. ISRs count (`isr_*` bytes) and the main loop writes the line (`AwtoDelayLongPoll` fw/timer/delay.c:131, DP training counter, HPD counters). The sanitizer run (below) shows no ISR access to the tail.
- MCU_DC port A is shared by the log, the note store and ddr_draw, and a 16 B burst load costs ~68 us (16 register writes, docs/ddr-draw.md): the main loop drains <= 4 lines per pass (`AWTO_DLOG_DRAIN`, SysMainPass after `AwtoSwPoll`, counted in stage "sw poll").
- Tail nearly full (>= 28 pending) in a shallow caller: that caller writes the oldest 4 lines at once. 4 entries stay free for `AwtoWaitLog`, which runs on the deepest DATA overlay path and cannot call the DDR code.
- Tail full in such a path: the line is dropped and counted (`ucLost`); the next shallow push writes `log overflow: N lines lost (DDR busy)` (sync.tsv 0x98, error class). Never silent.
  - Tail still full at that push: the count is kept, not reset (was: reset to 2 per push while the port stayed busy, #392).
- Before Timer2 runs, lines carry WDT time and are re-based at the Timer2 start (`AwtoSyncT2Start`, now 32 bit): no flush until then (forced only when the tail is full).
- Reset: lines pending at a warm reset stay in the kept XDATA tail and are written at the next boot (`AwtoDlBoot`). Crash record logic (AwtoWdtBite) stays in XDATA, untouched.

## DDR not usable during boot init
- Measured on unit 3 (2026-11-22, first image): writes made during the boot init (header at `AwtoSyncInit`, forced flushes) were accepted by the port and lost; from the first main-loop pass on they stick.
- So the DDR work (header check, cold clear, write index, flushes) starts at the first drain (`AwtoDlFlush` without FORCE, main loop). Before it, lines wait in the tail (a cold boot makes ~20 lines before the first pass: tail 32).
- Lines the previous boot left pending (`ucOld`) are written first, with the previous boot's number, not re-based.

## Memory powered off (#358)
- Measured on unit 3 (800e5789, 2026-11-27T17:31): DDC/CI sleep, wake poll 316 ms later. Lines written while `ScalerMemoryPowerControl(_OFF)` held the memory off were accepted by the port and lost: abs 5457..5464, the wake BEGIN among them. Older lines and the note store survived.
- `g_ucAwtoDdrOff` (set at OFF after this boot's first ON, cleared at the end of ON): `AwtoDlBurstW / R` and the note port wait return 0, so lines stay pending in the tail and drain after the ON. The boot-time OFF (`SysPowerInitial`) is not guarded: it comes before any ON, and the first-drain rule above covers it.
- Paths: power saving / power off (SysPower.c), the #353 re-init (`SysMachineMemReinit`: OFF then ON in one call).
- Re-init burst: lines pushed between OFF and ON are slow-wait lines of the ON path (14 delay / poll sites in docs/delay-audit.tsv: MPLL / DDR2 PLL set, DC PHY init), plus the re-init line and up to `AWTO_DLOG_DRAIN_MAX` 4 pending = at most 19, under the tail flush mark of 28 (32 - `AWTO_SYNC_RESERVE` 4). `mem_reinit_sim` checks no line is dropped.
- A power saving that logs more than 32 lines: the lines past a full tail are dropped and counted (`log overflow: N lines lost`), never silently.

## Stall bound (MCU_DC port A)
- Waits for: CMD idle before a command, READ_FLAG after a read. Expected: idle within the 255-poll spin (a few tens of us; `CMD slow polls 0` in docs/ddr-draw.md).
- The log only spins (`AWTO_DDRN_SPIN`), no ms wait: a busy port leaves a write pending (retried next pass) or a read unread (zero line, skipped by the console). Each expiry is counted in `g_ucAwtoDlBusy` (255 max).
- Notes keep the 50 ms wait (note store, main loop, once per note).
- Wedged port (#392, unit 3, main 6d27891d and ddr-keep 7f34698a): `MCU_DC_CMD_A` held the reserved opcode 011 (0x60), `LEN_A` 0x0A, `ADDR` not ours, after minutes of host DDR reads over the debug link. A reserved opcode never gets its qack: every op failed until a DC re-init (wake / POWER on) or a NOP write.
  - Every busy expiry (log spin, note 50 ms) checks the opcode: not write / read -> NOP, logged once as `MCU_DC port A: reserved command cleared` (sync 98 01).
  - Every command writes `LEN_A` (16 B burst) first; a late answer to an expired read is cleared (one `DATABUF_R` read) before the next command.
  - Note write expiry is logged (sync 98 02, ms waited + limit).
  - Writer of the bad values: not found (no firmware code writes `LEN_A`); open in #392.
- Why not a ms wait: the static masked-section analysis (docs/irq-masks.md) sees the loop under `AwtoSyncPush` in boot sections, and a ms-long wait in a pass stage breaks the 1 ms stage budget.

## Console
- Backfill: console open `AWTO_LOG_FILL_N` (54 lines), map-full redraw `AWTO_LOG_REDRAW_N` (27), under an episode start row `AWTO_LOG_VIEW_N` (`fw/osd/console.c`); `AwtoSyncAt` -> DDR for lines older than the XDATA tail; one burst read each, one row per pass.
- Console open after a warm reset: the current episode from its start row (#358, [sync-log-design.md](sync-log-design.md)); older boots: `synclog --dram`.

## Host
- `./dev.py synclog` (episode / `--whole`): version 4 image -> virtual version 3 ring (`sync_log.read_ring`), the DDR is read only for the lines asked for.
- `./dev.py synclog --dram [--last K | --boot B | --since ABS [--count K] | --all]`: DDR history, per boot, ms since reset, 32 bit; `--since A --count K` = one page (GUI log view); a progress line every 100 entries; ~77.7 entries/s over the debug link (unit 3, 2026-11-27, #358).
- `./dev.py synclog --follow --save`: `unit_log.py` polls with `--since <saved index + 1>`; dedupe by absolute index; gap marker when entries between two polls are missing.
- Sim: `fw_sim.DdrPort` (MCU_DC port A model, in every sim bus) keeps the DDR over the chip reset; `sync_log.DDR_UNIT` / `inject_lines`.

## Switch
- `_AWTO_DRAM_LOG` in `RL6449_Project.h`; `fw/rl6449_memory.toml` `pool_end_dram_log` (pool end 0xF53F vs 0xF3C9, picked by `scripts/fw_build.py` from `-D` or the header default).
- OFF (`-D _AWTO_DRAM_LOG=_OFF`) = the 718 B XDATA ring, behaviour of origin/main (builds and passes the normal tier).

## Results
See the issue comments (numbers with date, image, conditions).
