# Note store in DDR (log-keep, option F)

- Each host note's text (`./dev.py note`, #273) is also written to the top 128 KiB of the DDR; the console redraw and the host decoder read it back when the 119 B slot holds a newer note. No "text overwritten" for notes whose DDR line is intact.
- Code: `fw/log/hostnote.c` (`AwtoDdrNoteWrite` / `AwtoDdrNoteRead`), `fw/osd/console.c` (`AwtoPutNote`), constants `AWTO_DDRN_*` in `RL6449_Project.h`. Host: `scripts/ddr_note_read.py` (`./dev.py ddr-notes`), `sync_log.py` (`NOTE_DDR`).

## Layout
- DDR = 32 MiB = 2^22 units of 8 B (address wraps there). Store = units 0x3FC000..0x3FFFFF: 1024 lines x 16 units (128 B = 8 bursts of 16 B).
- Line = tag (2 B BE, note sequence) + length + text (119 B) + zero pad. Line index = sequence & 1023; a line is valid only when its tag equals the sequence asked for.
- Port: MCU_DC port A, burst = 16 B, write / read buffer halves swapped (memory byte j = buffer byte (j + 8) mod 16), CMD 0x80 write / 0xA0 read, READ_FLAG bit 0 (as `fw/test/ddr_draw.c`, `docs/ddr-draw.md`).
- Note numbering continues over a warm reset: `AwtoSyncInit` seeds `g_usAwtoNoteN` from the newest NOTE entry of the kept ring (the DDR lines are keyed by it). A cold power-up clears the ring and restarts at 1.

## Why the top region is free
- Frame buffers at 4K: one 24.9 MB buffer from address 0 (3840 x 2160 x 3 B); 3 buffers only at 1080p (18.7 MB). Highest address of any mode for inputs up to 3840 x 2160 is below 32 MB x 0.78. The store starts at 31.98 MB (units 0x3FC000).
- Measured: the live capture does not write above block 1 (12.4 MB) (#267, `docs/ddr-draw.md`).
- Not a guarantee for a mode that fills the whole DDR (the FRC width limit of 5053 px x 2160 lines x 3 B = 32.7 MB is the SDK's own full-memory figure): none exists for a 3840 x 2160 panel.

## Bus cost (off the live-picture path)
- Write: at note time only (one test cmd per note): 8 bursts, ~14 us. Read: only when the console draws a note row whose text left the slot: 8 bursts, ~64 us each = ~0.5 ms, in the main loop, one row per pass.
- Both wait for CMD idle / READ_FLAG with 255 spins then 50 ms (3 frames of DDR arbitration, as `ddr_draw.c`); on expiry the text is dropped ("text overwritten"), nothing else changes.

## Measured on unit 3 (2026-11-21, main-tip image + freeze image for the marker runs; live 4K60, line buffer mode, rotate 180)
- Marker = address-in-data pattern over blocks 16320..16383 (128 KiB, units 0x3FC000..): `./dev.py ddr-keep fill | verify | cmd 0xNN` (`scripts/ddr_keep_probe.py`, freeze image `--freeze --savers pacman`). 8192 bursts verified with single reads after each event:

| event | bad bursts |
|---|---|
| immediately after fill | 0 |
| console close / reopen (test cmd 0x27 / 0x26) | 0 |
| input switch episode (test cmd 0x32, settled) | 0 |
| power saving by VCP D6 = 4 for ~8 s, wake by D6 = 1 | 0 |
| ISP reset (`./dev.py reset`, 0xEE <- 0x02) | 0 |
| watchdog reset (test cmd 0x4C) | 0 |
| fill + verify with the live picture (no freeze, `--no-prep`), 8 cycles | 0, no sync-log anomaly, health 13/13 |

- Firmware store, unit 3: notes 1..5 written, read back from the DDR by the host (`ddr-notes`) intact, still intact after an ISP reset; note 6 after the reset continued the numbering; `./dev.py synclog` prints the old texts from the DDR.
- Not measured: a cold power-up (the DDR content is then undefined by design: the ring restarts too), picture glitches by eye (no camera login on this box).
- OSD SRAM (option E): no working read-back found (reads returned option-register values with the console shown, over ISP and from the MCU); not used.

## DRAM log (docs/dram-log-design.md)
- Ring of 16 B entries directly below the store (units 0x3EC000..0x3FBFFF) + header burst at 0x3EBFFE; the header also holds the note sequence (`g_usAwtoNoteN` continues over a reset without scanning the ring).
- Port helpers shared in `fw/log/hostnote.c`; the log only spins, the notes keep the 50 ms wait.
