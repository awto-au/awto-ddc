# Per-build size log

Every `./dev.py build` (and the variant builds that go through it: gates, test_image, gate_matrix) appends one row and prints a short report. Code: `scripts/size_log.py` (internal), called from `scripts/fwimage.py`.

## Files

- `<main checkout>/tmp/size/size-history.tsv`: one row per image; shared by all worktrees (`$AWTO_DDC_REPO`, else the git common dir's parent). Untracked.
- `tmp/size/funcs/<image_crc>.tsv.gz`: function sizes of that image, for the top-5 grew / shrank lists.
- `tmp/fw/<stem>.build.json` `size`: the same numbers as the row.
- `./dev.py size-graph`: `tmp/size/size-graph.png` + `size-graph.html` (inline SVG + row table). Open: `code-insiders <abs-path>`.

## Columns

| Column | Source |
|---|---|
| time | build end, ISO 8601 local offset |
| tree, branch, commit (12 hex) | build tree git |
| dirty, diff_hash | `git diff HEAD` (tracked files) non-empty; 8 hex of its SHA-256, so two dirty builds of one commit differ; `?` = backfilled dirty image |
| serial, tag, variant, layout | variant = sorted `-D` defines joined by `+`, `default` without |
| compiler | build.json stamp, 10 hex |
| src | `build` or `backfill` |
| common_b | CODE areas below common_end (map) |
| banked_b, bank_used, bank_free | CODE areas per bank; free = bank - common_end - used - a reserved block (message table) in that bank |
| min_bank_free | smallest bank free (`bank:bytes`) |
| direct_used / direct_free, iram_src | `link` = sdcc_link holes (build.json); `map` (backfill) = DSEG + OSEG + DDOVLn map sizes (DSEG's map size is synthetic: 2 B less free than the link at 29a3f8ac, equal at b3); the report gives no delta across sources |
| idata, stack | ISEG size; stack space (0x100 - stack start) |
| stack_static | `fw_stack.py` main + nested ISRs, worst of both IP states (as `./dev.py stats`); build rows only |
| bseg_bits | map `l_BSEG` |
| xdata_used, xdata_free | XDATA areas (map); free from build.json (blank for old images without it) |
| image_crc | CRC-32 of the .bin |

## Report

- This build vs the previous row of the same serial + variant + layout, and vs the newest clean build of origin/main's newest built first-parent commit: every number, delta in B and %.
- Bank free changes per bank; the 3 smallest bank free values (no limit).
- Top 5 functions grown / shrunk (map `CH_` chunk areas; maps before chunking: spacing of global symbols, statics fold into the preceding global).
- Added build time: ~0.6 s (fw_stack 0.5 s, rest < 0.1 s), on a ~100 s build.

## Graph

- `./dev.py size-graph [--backfill] [--serial S] [--variant V | --all] [--branch B] [--dirty N] [--out DIR]`
- Default rows: one per origin/main first-parent commit (newest clean default-variant build), oldest first, then the 5 newest dirty builds; x label = commit, `*` = dirty.
- Panels: flash common, banked total, free per bank, direct IRAM free, XDATA free, BSEG bits; the 3 largest steps per metric labelled.
- `--backfill`: rows from archived images (`build-debris/images`, `tmp/flashed/images/*`, `tmp/fw` of the main checkout and every worktree) whose commit is a main first-parent commit, or a merged branch tip with the merge's tree; no rebuild. Coverage at 2026-11-27: 57 main commits back to 1dbdbaa3 (2026-11-05); main has 1038 first-parent commits, most built only on branch commits.
