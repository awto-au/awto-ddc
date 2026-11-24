# Extra apps (extra source root + app hooks)

Extension points for code that lives outside this repo (awto-games-dw8051 builds its arcade image with them; awto-ddc#345).
- Default image: byte-identical without `--extra-fw` (everything below is compiled out; only the tag string differs).

## Build
- `./dev.py build --extra-fw DIR [--tag T]` (or `$AWTO_EXTRA_FW`); DIR may be outside the repo.
  - `DIR/**/*.c` compile like `fw/<subsystem>/*.c`; every folder with a `.c .h .inc .asm` is on the include path; `*.asm` are assembled and linked.
  - Adds `-D _AWTO_EXTRA_APPS=_ON`: compiles `fw/apps/apps.c` (+ hooks in keys.c, testcmd.c, vcp.c) and `fw/apps/AwtoApps.h`.
  - Variant build: the tracked `fw/bank_map.tsv` / `fw/xdata_layout.tsv` stay untouched; maps go to `tmp/fw/<stem>.{bank_layout,xdata_layout}.tsv`, like hwtest.
  - `tmp/fw/<stem>.build.json` records `extra_fw`; `fw_gates.py` sets `$AWTO_EXTRA_FW` from it, so the static gates (magic, pokes, ...) read the same sources.
  - `tmp/fw/<stem>.apps.tsv` = index, name, source of each app.
- Module name = file stem: a stem used twice (also against fw/ or the SDK) fails the compile with both paths.
- Extra code follows the repo rules: no magic numbers, no warnings outside `fw/warn_policy.tsv`, bounded loops.
- Example: `fw/apps/example/hello_app.c`; `./dev.py build --extra-fw fw/apps/example --tag apps-ex`; sim: `scripts/apps_sim.py BIN MAP`.

## Registration (no runtime registration)
- `AWTO_APP(name, init, step, key, stop);` at file scope in any extra `.c`; a hook is a non-static function or `AWTO_APP_NONE`.
- `scripts/gen_awto_apps.py` scans the root (comments and the `#define` are skipped; malformed / duplicate / more than 15 = build error) and writes `tmp/sdcc-port/apps_gen.inc`: `AWTO_APP_COUNT` and `switch` dispatchers with direct calls.
  - Direct calls, not a table of function pointers: the bank tool routes a call to a banked function through its stub; a pointer would not.
  - The firmware carries no names; index order = file path, then position.

## Hooks
| where | what |
|---|---|
| VCP 0xEB (`vcp_set`, `fw/rtdfw/awto/settings/vcp.c`) | `0x20 + index` starts an app, `0` stops it (and the saver path as before); a value >= 0x20 never reaches the registry (it would clamp to a saver value). The DDC/CI handler only records `g_ucAwtoAppReq`. |
| debug byte | write `index + 1` (`0xFF` = stop) to XDATA `g_ucAwtoAppReq` (map symbol) over the debug link / `dev.py xwrite` |
| main loop (`AwtoDiagTestCmd`, after `AwtoSaverPoll`) | `AwtoAppsPoll`: serves the request, calls the running app's `step` once per pass; stops the app when the power status is not NORMAL or the mode changed since the start |
| key router (`AwtoKeyRouteDo`, first) | a running app gets every key but POWER (`key(ucKey, ucEv)`, injected keys look like front keys); POWER stops the app and keeps its normal action; an app without a key hook stops on any press |
| pacing (`AwtoLoopBusy`) | an app counts as work: the loop free-runs while it runs |
| sync log | line E9 arg `0x79` (the saver's): value `0xF0` + index at the start, `0` at the stop |
- Key ids / events: `fw/keys/keys.h` (`AWTO_K_*`, `AWTO_KEV_*`; moved from keys.c, same values).
- Watchdog: `AWTO_WDT_PASS` is fed once per pass by `AwtoDiagMainPass`; `step` must end well inside the bite time (warn 200 ms, reset 586 ms). A bounded loop that can run longer calls `AwtoAppFeed()` (site `AWTO_WDT_S_APP`).

## API (`fw/apps/AwtoApps.h`)
- Control: `AwtoAppStop()`, `g_ucAwtoAppRun` (0 or index + 1), `g_ucAwtoAppReq`.
- Time / random: `AwtoAppMs()` (= `AwtoMs()`, unsigned long ms), `AwtoAppRandom()` (xorshift16, seeded at the start).
- Canvas (the full-screen OSD map of the removed savers, 12 x 18 px cells, `docs/osd/api.md`, `docs/osd/rotation.md`):
  - `AwtoAppScreenBegin()` / `AwtoAppScreenEnd()`: OSD reset, rotation latched (`g_ucAwtoOsdRot`), popup hold so SDK OSD resets cannot wipe the screen; the stop path ends a begun screen.
  - Setup: the existing `AwtoOsdRowCmds`, `AwtoOsdMap1`, `AwtoOsdPlaceScaleUp`, `ScalerOsd*` (see `fw/test/flash_screen.c`, `fw/test/qc_osd.c`).
  - Per frame: `AwtoAppCell(addr, b0, b12)` (one SRAM word), `AwtoAppCellAddr(base, cell, cells)` (mirrored cell when Rotate 180), `AwtoAppCells(addr, ptr, words)` (a run, one address set), `AwtoAppGlyph(addr, ptr, bytes)` (glyph upload, turned in place when Rotate 180), `AwtoAppTurn(ptr, bytes)`.
  - No flip: the OSD reads SRAM live (double buffer off); write changed cells only.
- Sound (player that remains): `AwtoAppSoundTone(sc, ms)`, `AwtoAppSoundAlert()`, `AwtoAppSoundStop()`. The game tracks (waka, intro, Asteroids) are not in the player.

## Limits
- One app at a time; at most 15 (VCP value and the 4-bit sync index).
- Apps share the XDATA / bank space of the build: an image with big apps needs its own layout (separate arcade image, awto-ddc#345).
- An app that draws must end via stop (or `AwtoAppStop`): the screen is closed on that path only.

## Checks
- `tests/test_extra_apps.py` (generator, scan, build flag, source lists; `--slow`: builds the example, runs `fw_gates.py` and `scripts/apps_sim.py` on it).
- `scripts/apps_sim.py`: start / stop by VCP and by the debug byte, step per pass, key forward, quit key, out-of-range VCP dropped.
