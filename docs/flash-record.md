# Flash record = which image each unit runs (host side)

Not the on-device manifest (`docs/flash-registry.md`). Code: `scripts/flash_registry.py`, `scripts/fw_probe.py`.

## Layout (main checkout, shared by every worktree)

- Root = `unit_lock.lock_root()` (git common dir's parent), same rule as the unit locks.
- `tmp/flashed/<serial>.json`: tag, sha256, built (bin mtime), `commit` (the image's build commit from `<stem>.build.json`, `+dirty` if the tree was; `unknown` for an older image), `flasher_commit` + `worktree` (the checkout that ran the flash; a warning prints when they differ), flashed (ISO), `images_dir`.
- `tmp/flashed/images/<sha12>/<tag>.{bin,map,sync.tsv,settings_table.py,build.json,ids.tsv}`: content-addressed copies. Deleting a worktree loses nothing; no symlinks.
- Same tag with different bytes -> different `<sha12>` dir, never overwritten.
- `build-debris/images/` (`fw_archive.py`) unchanged; used as a second place to look up a tag.
- Old `tmp/fw/<serial>-flashed.json`: no reader left, no fallback; old files are ignored.

## Writers / readers

- Writer: `dev.py flash` (and so `recover`, `deploy`; incremental and `--full`): record invalidated before the first write (tag `""`, `attempted_image` kept for `recover`), `record()` after rc 0, restored when nothing was erased (rc 5).
- Readers go through `flash_registry.current(serial)` / `map_for(serial, given)`: `dev._flashed` / `dev._fwmap` (every `--map` default), `msg_table.load_ids`, `cold_boot.py`, `selector_switch_unit.py`, `disk_guard.prune_fw` (pins), GUI via dev.py.
- `map_for` unknown: exit listing the known images; never a guess.

## Verification against the unit (reads only)

- `dev.py health` / `settings` (no `--map`) run `fw_probe.py` first: diag magic `AD` at `_isr_g_stAwtoDiag`, mailbox magic `V` at `_vcp_box`, addresses from the record's map.
- Layout check only: the firmware does not report its tag over the debug slave, so two images of one layout both pass.
- Stale: `registry stale: unit does not answer at the map of <tag>; maps that answer: ...`, exit; fix with `adopt`.
- Firmware change that would make the check exact: expose tag / image sha in the diag block.

## Commands

- `dev.py flash-record --unit N show | list | scan [--max N] | adopt IMAGE.bin` (`--force` on working screens).
- `scan`: probes known maps (images/, build-debris) newest first, prints PASS / fail per tag.
- `adopt`: records an image (+ companions beside it) without flashing.
