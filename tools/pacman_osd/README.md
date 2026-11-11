# Pac-Man OSD graphics prototype

Open `preview/pacman-osd-viewer.html` locally in a browser. It contains the
capture and graphics, needs no server, and makes no external requests. Play,
pause, step, scrub frames, show the cell grid, or inspect the resident glyphs.
`preview/pacman-osd-motion.gif` is the same 96-frame graphics demonstration.

## What runs, and what does not

This is graphics preparation, not a complete Pac-Man port. The maze and artwork
are original demonstration assets; no arcade ROM data is included. Five actors
move around the perimeter and the yellow actor removes pellets.

The portable C renderer has been compiled and tested on the host. An independent
8051 emulator executes a **19,930-byte standalone diagnostic app** which reads
a display list produced by that C renderer and performs real `MOVC`/`MOVX`
instructions. Its OSD register writes are replayed through awto-ddc's existing
OSD model. Every SRAM word in startup and all 96 frames matches the C output.
A negative control replaces the data-port `MOVX` with `NOP`; the check detects
the missing output. The diagnostic is not an SDCC build of the C renderer.

No monitor firmware was patched or flashed. The app does not include monitor
startup, scaler/video/panel setup, banking, key input, game rules, collisions,
sound, or firmware ABI integration. No interrupt/coexistence or actual monitor
timing claim follows from this test. The viewer's fps is playback speed only.

## Cached sub-cell movement

The stored glyph format remains 12x18, 1bpp, 27 bytes / 9 24-bit words. Visible
rows use height 12 (row command height field = 11), leaving the final six glyph
rows zero. This produces square 12x12 visible cells and round actors. The
28x36 map is 336x432 OSD pixels, or 672x864 at whole-OSD 2x scale. The 12-line
row configuration is verified in the model, not on hardware.

Each 12x12 actor has sixteen cached offsets: x and y in {0,3,6,9}. At each offset
it occupies up to four neighbouring cells. The generator splits the sprite,
deduplicates the fragments, and emits `pm_phase_glyph[]`. Frames 0..7 are two
mouth poses for right/down/left/up; frames 8..11 are one ghost pose for those
four directions. All four ghosts share masks and use per-cell foreground colours.

The C renderer tracks old/new actor footprints and writes only affected map
entries. It neither shifts glyph pixels nor uploads glyphs during animation.
Identical updates are skipped. A full redraw is the explicit fallback if
several updates before a flush overflow the dirty queue.

| Allocation | Words | Bytes |
| --- | ---: | ---: |
| 36 row commands + terminator | 37 | 111 |
| 28x36 character map | 1008 | 3024 |
| 343 glyphs, including cached fragments | 3087 | 9261 |
| Total used | 4132 | 12396 |
| SDK-documented SRAM capacity | 12288 | 36864 |

343 of the 512 one-bit glyph IDs are used. Unused SRAM alone cannot eliminate
that addressing limit. Keeping the cache resident is what reduces CPU work;
filling unused SRAM would not speed this demonstration. The C renderer uses
approximately 1.1 KiB of declared state plus compiler alignment/stack overhead.
The measured demo changes at most 10 map words / 30 data bytes per frame,
excluding address/control writes. Its runtime glyph upload count is zero.

**Compositing limitation:** a nonempty sprite fragment replaces the complete
cell using an opaque black background. The background is restored when the
actor leaves. Dots in partially occupied cells can temporarily disappear;
multiple actors sharing a cell use slot priority rather than pixel compositing.
Mixed-colour background/sprite composition is the next graphics step. This
prototype does not claim those cases are implemented.

## Rotation and shifting

The RTD2795T register descriptions document:

- Font A/B position offsets at `0x3A24..0x3A29`, moving a font layer.
- Download rotation at `0x3A0B`: enable bit 2; bits 7:6 select none/180/CCW/CW.
  Compression must be enabled with this path.
- Global OSD auto-rotation/remapping at `0x3A41`.

A per-character rotation selector has not been established. Download rotation
could create multiple resident directions from one source orientation, saving
flash/source copies and software rotation, while still consuming SRAM for the
resident directions. This version generates them offline and does not exercise
hardware rotation or a hardware pixel shifter. See `docs/integration.md`.

## Rebuild and validate

From the repository root, first run `cd tools/pacman_osd`.

Requirements: Python 3 and a C compiler. The HTML viewer needs no dependencies.
The PNG/GIF reference rendering additionally needs Pillow and numpy.

```sh
make generate
make emulator
python3 tools/preview.py --reference ../../scripts
python3 tools/make_viewer.py
node tests/viewer_logic.cjs
```

The independent reference scripts must be from awto-ddc commit
`ca6b4dc25de155506838e5e503afe387f074628e`: `osd_model.py`, `osd_vlc.py`, and
`glyph_decode.py`. The preview runner substitutes only the unused `fw_sim.Dev`
base type; it does not execute or impersonate the repository's ucsim firmware
runner. The included emulator core is Jari Komppa's MIT-licensed emu8051.

Native C tests cover SRAM layout and bytes, ninth glyph-ID bit, background
restoration, all cached phases, hidden actors, invalid arguments, dirty overflow,
and reload. Python independently reconstructs all 192 actor/phase combinations.
Native address/undefined-behaviour sanitizer checks pass with leak detection
disabled because this environment prevents LeakSanitizer's process inspection.

The HTML JS was checked with a DOM/canvas test double and its pixels compared
with the independent OSD model. Full browser interaction/layout testing could
not run in this environment: the local browser cannot create its socket, and
the shared browser disallows file URLs. No browser test pass is claimed.

## Source provenance

- OSD layout: https://github.com/awto-au/awto-ddc/blob/ca6b4dc25de155506838e5e503afe387f074628e/docs/reversing/realtek-rtd/osd-limits.md
- Model: https://github.com/awto-au/awto-ddc/blob/ca6b4dc25de155506838e5e503afe387f074628e/scripts/osd_model.py
- Register database: https://github.com/awto-au/awto-ddc/blob/ca6b4dc25de155506838e5e503afe387f074628e/re/regdb/RTD2795T-CG.tsv.gz
- emu8051: https://github.com/jarikomppa/emu8051 (core files with whitespace-only normalisation and MIT licence under `third_party/emu8051/`).

The current binary is a standalone emulator diagnostic, **not a flash image**.

## Saved validation

`validation/emulator-validation.json` records the SRAM comparison and negative
control; `validation/app-build.json` records the diagnostic image hash and entry
labels. Build outputs and host executables are ignored. The saved HTML/GIF/PNG
are review artefacts and are regenerated by the commands above.
