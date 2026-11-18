# Tiled OSD line drawing

Portable C99 monochrome line renderer, defaulting to 12 x 18 pixel tiles.
No heap, floating point, recursion, operating system or hardware SDK dependency.
See `example_scope.c` for a 384 x 216 waveform display.

## Use

Compile `osd_lines.c` into your firmware and include `osd_lines.h`.
Allocate caller-owned pixel/dirty buffers, then call `osd_canvas_init()` once.

```c
osd_line(&canvas, 0, 100, 383, 40, 1); /* draw, both endpoints included */
osd_line(&canvas, 0, 100, 383, 40, 0); /* erase the same line */
osd_flush(&canvas, upload_tile, user);
```

Coordinates start at the top left and increase right/down. All slopes and both
directions work, including single pixels. Pixels outside the canvas are ignored.
Erasing must repeat the same endpoints in the same order: reversing a line can
choose a different pixel at exact half-pixel ties. Ink is monochrome, not a
palette index. Configure the trace colour in the OSD attributes/palette.

## Tile layout and hardware adapter

Tiles are stored in row-major order. Every screen cell needs its own writable
font/tile ID; tile `row * cols + col` corresponds to that cell. The caller sets
up the hardware OSD map, font base, palette and display position separately.

Within each tile, pixels form a continuous row-major bitstream, MSB first:

```
bit = local_y * OSD_TILE_W + local_x
byte = tile_id * OSD_TILE_BYTES + (bit >> 3)
mask = 0x80 >> (bit & 7)
```

Rows are not individually byte-aligned. For 12 x 18, two 12-bit rows occupy
three bytes, and one tile occupies 27 bytes. For tile areas not divisible by
eight, the final byte has unused low bits, initialized to zero.

This is the renderer's explicit canonical format. The upload callback must
confirm/adapt the Realtek font-port byte order, bit swapping and hardware address
mapping against the SDK. No Realtek register writes are invented here. The
callback receives relative tile ID, bytes, byte count and a caller user pointer.
Return nonzero only when all bytes are successfully copied/uploaded. Failure
retains the dirty flag and stops the flush so a later flush can retry.

## Memory and timing

| Canvas | Tiles | Pixel bytes | Dirty bytes |
| --- | ---: | ---: | ---: |
| 384 x 216 | 32 x 12 = 384 | 10,368 | 48 |
| 384 x 288 | 32 x 16 = 512 | 13,824 | 64 |

These are software storage figures. Hardware also needs the OSD map/commands,
and the 512-tile layout leaves no unique tile IDs for other content in that
same ID range. The renderer does not validate the scaler's hardware limits.

The line loop uses 16-bit integer Bresenham arithmetic. It calculates the
starting tile using division once per axis, then updates the tile cursor using
increments and boundary checks; there is no division/modulo in the pixel loop.
Only changed bytes mark a tile dirty. There is no measured FPS claim.

Clipping preserves the raster of the original line: the walk starts at the
first Bresenham step inside the canvas (closed form, 32-bit once per line) and
stops at the first pixel past the far edge, so only visible pixels are walked.
Entirely rejected bounding boxes return immediately. `tests/test_osd_lines_clip.py`
(awto-ddc) checks pixels and dirty flags against the original prototype.
`OSD_MEM` is the canvas address space (`__xdata` on SDCC mcs51, else empty). Coordinates and tile dimensions fit signed 16-bit cursor
arithmetic; initialization rejects buffers requiring more than 65,535 bytes.

On SDCC/8051, place the large buffers in `__xdata` as shown in the example.
The core uses portable pointers; address-space specialization can be added after
profiling. SDCC target compilation and hardware timing have not been verified.
Calls on one canvas must be serialized; the callback must not draw recursively.
Flush does not synchronize to vertical blank, so hardware tearing/atomic updates
must be handled by the adapter if necessary.

`osd_clear()` followed by drawing a new trace is the simplest animation path.
It conservatively marks tiles touched by either frame. Erasing only the old trace
and drawing the new one can reduce CPU work. Shared grid/trace pixels need
recomposition or separate hardware layers to avoid erasing the grid.

## Host verification

Run `python3 test_lines.py`. It compiles with strict C99 warnings and checks
2,550 line cases across five tile sizes against an independent closed-form
reference, plus full int16 spans, bounds guards, packing, erase and upload retry.

The included example is an integration template, not monitor firmware.
