Found while driving playwrong for awto-ddc#30 (2026-11-06):

- `~/.local/bin/playwrong` is a dangling symlink to `/mnt/2tb/git/awto-playwrong/playwrong` (repo now `awto-play`); `playwrong` not on PATH usable.
- `js` op has a hard 60 s cap; a long async loop wedges with "engine ... wedged" text. Workaround used: start the promise in page, store in `window`, poll in short calls. A documented pattern (or a longer per-call `timeout` param) would help.
- `download` of large files from `org.downloadcenter.samsung.com`: plain HTTP times out, in-browser fallback fails with `TypeError: Failed to fetch` (cross-origin) for ~1.6-3 GB files on first attempt; succeeded on retry. Fallback could stream via CDP instead of page fetch().
- `newtab` refused with `MemoryHighWater` (7.1 of 8.2 GB held by other agents' tabs) until own tab was closed.
