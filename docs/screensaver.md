# Screensavers in the scaler firmware (design, Dan 2026-11-17)

Status: design only; nothing built. Prototypes today are test cmds, not screensavers.

## Decisions (Dan, 2026-11-17)

- Two screensavers, run by the scaler firmware itself (no host):
  - **Pac-Man**: `fw/test/pacman_classic.c` (+ sound `pacman_sound.c`), test cmds 0xB7 / 0xB8 / 0xB9 today.
  - **Scope**: OSD line renderer `tools/osd_lines` (384 x 216, 12 x 18 tiles, `docs/reversing/realtek-rtd/osd-font-download.md`), a waveform screen.
- **Scope 2** (Dan, 2026-11-17, reference photo of a bench scope): red graticule with minor ticks on the centre axes, green pulse trace, two dotted vertical cursors, 100 / 90 / 10 / 0 % marks on the left, readouts on top (frequency, delta t), scale labels at the bottom (volts per div, time per div). Scope 1 (`scope_saver.c`) stays as is.
  - Two colours per tile: 2-bit glyphs (planes: graticule, trace), 256 glyph ids -> 28 x 9 tiles (336 x 162 px); the one-band canvas is reused per plane (XDATA floor).
  - Text from a small pixel font drawn into the canvas; numbers from the waveform shown.
  - Mode enum gets a `Scope 2` entry; Alternate cycles all three.
- Trigger: **both** no signal and idle timeout with a live picture.
- Selection: **both** a settings-menu choice (Off / Pac-Man / Scope) and an Alternate choice (switch every few minutes).

## Hook points (to check, not yet read in detail)

- No signal: mode machine `NOSIGNAL` (`docs/design-162.md`, `docs/power-levels.md`): runs before L1 (backlight off) and L2 / L3; any L1 / L2 / L3 transition or a locking source stops it.
- Idle with picture: key / DDC activity timer (none exists), draws over the live picture, no scaler reconfiguration; any key ends it and restores the OSD state.
- Settings: registry `fw/rtdfw/settings/registry.tsv` (`scripts/settings_gen.py`), menu card `fw/osd/`.
- Pac-Man image needs ~24 KB of data across banks 11 / 12 (bank 13 is full); the scope needs its own tile map + per-frame tile uploads; check cost.

## Asteroids (2026-11-18)

- Fifth saver, game logic on the chip: `docs/asteroids.md`. Setting 119 value 5, VCP 0xEB = 8, joins Alternate (Pac-Man, Scope, Scope 2, Asteroids), sound through the Pac-Man generator.

## Open

- Draw-over-picture cost and OSD state restore (pop-on, scale-up, palette are reset by `AwtoOsdTestReset` today).
- Sound: only Pac-Man has it; amp P7.4 / P7.3 set by `PsStart` (48e3950), unverified on the unit.
- Test only on unit 3.
