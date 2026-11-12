# Dahua firmware: SOURCE page (input selector) (static RE)

Original Dahua firmware, not our build. Tags: [fw] read in disassembly; [fw+x] structure matches the SDK; [guess] inference with a "settle by" line; [?] unknown. Tracking: #41, front keys in `keys.md`.
Evidence: bank 0 `dd7c` (page builder), `e7b1` (page handler, state 0x52), `a62d`, `f4c3`, `cf60`; bank 6 `667d` / `62cf`; bank 4 `fea4` / `fdec` / `fee0` / `fee6` / `fb23` and the table at bank 4 `28c6`; bank 3 `cd09` / `dc75`; bank 1 `f60f`. Method: `scripts/dis51.py` on `~/vendors/realtek/analysis/banks/bank*.bin` (2026-11-12). Names: `re/jxc-4k/names_re1.tsv`.

## 1. Open (SOURCE key or IR A7)
- Entry: SOURCE with `usOsdState == 0` -> `f97a` -> `fcfe()` then `dd7c()`; IR code A7 58 does the same (`gpio-ir.md` 6.3). With the OSD open the key is dropped before any handler (`keys.md` 1a). [fw]
- `dd7c`: `usOsdState` (e14e) = 0x52, draws the page, and loops `dbaf` = 0..2 for 3 rows (`dbaf < 3` at 0:de1a). Always 3 rows. [fw]
- Cursor sync on open: `0f5d` = bank 6 `62cf` maps the current port code (from `056d`) to the cursor `e060`: port 4 -> 0, 5 -> 1, 6 -> 2; any other port leaves `e060` unchanged. Then `a62d` stores the cursor to `e13c:e13d` = "row at open". [fw]
- `a636` + `0597` re-arm the OSD timeout: timer id 8, `e053` seconds (default 10) x 1000 ms (`keys.md` 4b). [fw]
- Row list shows no cable state: the row loop calls `a456`, `a20c`, `b44c` only; no read of a cable-detect pin or a port-status variable in `dd7c` itself. Helper bodies not all read (`a22d`, `a45d`, `a456`); a read inside them is not excluded. [fw]; a branch on `a45d() == 3` at 0:de6f (changes two draw parameters) [?].

## 2. Rows and port codes
- Row -> port code (bank 6 `667d`, called as `0f6f`): 0 -> 4, 1 -> 5, 2 -> 6. [fw]
- Port code -> class: byte table at bank 4 `28c6`, index = port, high nibble = port code, low nibble = class: ports 4, 5, 6 = `0x44`, `0x53`, `0x63` (class 4, 3, 3). The DDC/CI capabilities choice by class nibble (3, 5, 6 -> string A, 4 -> string B, `~/vendors/realtek/analysis/NOTES.md`) uses the same nibble. [fw]
- Current port = `056d` (bank 4 `fea4`) = `table28c6[ e0ea + e108 ]` high nibble: `e108` is the current slot (0..2), `e0ea..e0ec` hold three slot -> table-index bytes. `0cbd` (bank 4 `fdec`) sets `e108` = the slot whose entry matches the given port. [fw]
- Which physical connector is port 4, 5, 6: [?]. The firmware has HPD drivers D1 (P4.2), D2 (P1.1), D3 (P1.0) (`gpio-ir.md` 5), so ports 4..6 are plausibly D1..D3 in some order. [guess] Settle: read `e108` / `e0ea..e0ec` over ISP with the cable on a known connector, or `docs/handover.md` input table.

## 3. Keys while the page is open (`e7b1`, state 0x52)
| key (e151) | action |
|---|---|
| UP (1) | cursor -1 (`f4c3`, range 0..2, `bit02` set = wrap: 0 -> 2), redraw highlight (`0f75(0x0A)` = bank 6 `561e`) [fw] |
| DOWN (2) | cursor +1, wrap 2 -> 0, redraw [fw] |
| MENU (0) | commit (section 4) [fw] |
| AUTO (3) | `fcfe()`: close, no change [fw] |
| SOURCE (4), 6 | dropped by the key gate (OSD open); `e7b1` has no case either [fw] |
- So SOURCE does not step the selection and does not select: it only opens the page. The cursor moves only with UP / DOWN; MENU selects. [fw]

## 4. Commit (MENU)
- `e060` == `e13d` (same row as at open): `fcfe()`, nothing else. [fw]
- Otherwise, in this order (`e7b1` 0xE7D8..0xE82B): [fw]
  1. `0f15(1)` -> bank 1 `f60f`: if mode state != INITIAL, `e22f` high nibble = 1 (SDK-shaped "mode reset target = search"; the wake path in `1:995b` writes the same value). [fw+x]
  2. `0f6f` -> port code from `e060` (section 2); `0cbd(port)` -> `e108` = slot of that port; `0cc3(1)` -> bank 4 `fee0`: `e0f9` bits 4:1 = 1.
  3. Compare with the stored values: NVRAM item 1 (`0687(1)` = bank 3 `dc75`) vs `056d()`; if equal, item 2 vs `0d71()` (bank 4 `fee6` = `e0f9` bits 4:1). Both equal: return, no message.
  4. Else write both: `0df5(1, 056d())` and `0df5(2, 0d71())` (bank 3 `cd09`, the NVRAM setter), then `e150` = 0x0B and return. The page is not closed here (no `fcfe`).
- NVRAM items 1 and 2 (`cd09` cases at bank 3 `cd80` / `cd92`): 4-bit fields stored in the `e1de..e1e0` block; item 2 remaps 9 -> 0 and 8 -> 1. [fw] They match the SDK `SYS.b4SearchPort` and `SYS.b4SourceScanType` (`docs/nvram-settings.md`) in shape. [guess] Settle: read the saved bytes `e1de..e1e0` before / after a selection (ISP RAM read on a spare unit), compare with `_SOURCE_SWITCH_*` values (0 FIXED_PORT, 1 AUTO_IN_GROUP in `Global.h:938`). If item 2 is the scan type, a manual selection writes 1 = AUTO_IN_GROUP, not FIXED_PORT.
- Same four-call write and `e150 = 0x0B` exist a second time at 0:cf60..cf7a (in the main-menu "item" region reached from `c3ea`), so the main menu's input entry commits the same way. [fw]
- `e150 = 0x0B` consumer: not found. `e150` has no constant-address reader in banks 0..6 (writers: 0:cf74, e825, eaf1, eb1b, eb22, ebec, eefe, fd3a; 1:cbf0). The input switch itself is taken to happen through the mode reset target (step 1) and the stored port; the message likely closes the OSD. [?] Settle: log `e22e` (mode state), `e108` and `e150` over ISP while selecting a row on unit 1.

## 5. Commit timing: key, not timeout
- The only code that applies a selection is MENU in `e7b1` (and the `cf60` copy). UP / DOWN only move the cursor; nothing is applied until MENU. [fw]
- Timeout: timer id 8 (e053 s) is armed when the page opens. A timeout consumer was not found (same gap as `keys.md` section 3). No code path found applies the highlighted row on timeout; at worst it closes the page. [fw] for "no commit path", [?] for what expiry does. Settle: unit 2, open SOURCE, move the cursor, wait e053 s with `rtd_keywatch.py` and read back `e108`.

## 6. Input without a cable
- No cable gate in the page (section 1), in the commit (section 4), or in the NVRAM write. A row can be chosen whether or not its connector has a cable. [fw]
- What follows: the reset-to-search request (4.1) sends the mode machine to SEARCH, which then finds no signal on that port; the Dahua mode flow shows the no-signal OSD in NOSIGNAL (`gpio-ir.md` 2a) and later enters power saving; whether it jumps to another port in between depends on the scan type (item 2, section 4). [guess] Settle: select the row of an unplugged connector on unit 1 (original firmware) and watch: stays on that port in NOSIGNAL (FIXED_PORT behaviour) or moves to a connected one (AUTO). Log `e22e` and `e108`.

## 7. For our firmware
- SOURCE opens the list (OSD closed only); while open it does nothing. UP / DOWN move a 3-row cursor with wrap; MENU selects; AUTO cancels. Selection applies on MENU, never on timeout or on cursor move.
- No cable test when selecting: rows are shown and selectable always; an unplugged selection ends in NOSIGNAL.
- On open, put the cursor on the row of the active input; if MENU is pressed on the same row, close without a message.
- Open: scan type written on commit [guess, section 4], port search behaviour after selecting an unplugged row [guess, section 6].
