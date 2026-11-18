# OSD prototype archives

Original ZIP snapshots from the Pacman/glyph and scope-line experiments recorded in [issue #226](https://github.com/awto-au/awto-ddc/issues/226). The archives are preserved byte-for-byte; their contents are not part of the firmware build.

| Archive | Size | Contents and status |
| --- | ---: | --- |
| [osd-lines-12x18.zip](osd-lines-12x18.zip) | 8,685 bytes | Portable C monochrome tiled line renderer, default 12 x 18 cells; draw/erase, clipping, dirty tiles, upload callback, scope example, host tests and MIT licence. Realtek upload/packing adaptation and target timing remain integration work. |
| [pacman-osd-prototype.zip](pacman-osd-prototype.zip) | 195,256 bytes | Cached sprite-fragment graphics demonstration; C sources, generated glyphs, native/model/emulator validation tools, standalone HTML viewer, PNG/GIF previews and an emulator diagnostic. Includes the emu8051 licence. Not a complete Pacman game or monitor firmware. |

## Use

Extract an archive and read its own README before building or running it. The Pacman viewer is `pacman-osd/preview/pacman-osd-viewer.html` inside its ZIP. The line renderer's usage and tests are in `osd-lines/README.md`.

The Pacman archive includes a standalone diagnostic binary for an 8051 emulator. **It is not a flashable monitor image.**

Prototype README statements and captured validation results describe their original snapshots. Current hardware facts, corrections, limitations and integration work are tracked in [#226](https://github.com/awto-au/awto-ddc/issues/226) the [OSD overview](../osd.md) and the [OSD manual](../osd/README.md). In particular, the map-address limit (display fetch across word 8192) is not settled; archived estimates do not settle it ([limits](../osd/limits.md), OT-3).

Archive integrity/CRC and embedded paths were checked on import. Git blob IDs were checked against the original ZIP bytes. No monitor was accessed or firmware build changed by this archival import.
