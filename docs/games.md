# Games (removed)

- Pac-Man, Scope 2 and Asteroids screensavers (and the Pac-Man OSD demo, game sound tracks, no-signal / idle saver logic) were removed from awto-ddc on 2026-11-25 (Dan).
- They live in awto-au/awto-games-dw8051 at commit 7dbd518 (history rewritten 2026-11-25; the Doom-derived renders are not in it) (`fw/games`, `scripts`, `tests`, `docs/games`, `tools/pacman_osd`).
- Left here: the flash warning screen, boot splash and alert tone (VCP 0xEB = 5 / 7 / 6, `fw/awto/savers.tsv`), the alert / calibration / key-click sound player (`docs/audio.md`).
- Saver research docs and scripts (`docs/screensaver.md`, `docs/saver-*.md`, `scripts/saver_*.py` measuring game frames except `saver_hw_budget.py`, `scripts/snd_timing.py`; `docs/saver-fps-hw.md` stays: the regmap gate reads its test ids T-A..T-M) were deleted too and are not in awto-doom; last in this repo at commit 3d271b99 (`git show 3d271b99:docs/saver-fps-hw.md`).
- Settings rows 119 `screensaver` and 120 `screensaver_s` are retired (ids not reused); 121 `screensaver_now` keeps VCP 0xEB for the flash screen, alert and splash; 80 `pwr_l3_s` is inert.
