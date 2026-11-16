/* Portable monochrome tiled line renderer. SPDX-License-Identifier: MIT */
#ifndef OSD_LINES_H
#define OSD_LINES_H

#include <stdint.h>

/* Override consistently for every translation unit. Default: Realtek 12x18. */
#ifndef OSD_TILE_W
#define OSD_TILE_W 12
#endif
#ifndef OSD_TILE_H
#define OSD_TILE_H 18
#endif
#if OSD_TILE_W < 1 || OSD_TILE_W > 32 || OSD_TILE_H < 1 || OSD_TILE_H > 32
#error Tile dimensions must be in the range 1..32
#endif
#define OSD_TILE_BYTES ((OSD_TILE_W * OSD_TILE_H + 7) / 8)
#define OSD_TILE_COUNT(cols, rows) ((uint16_t)(cols) * (uint16_t)(rows))
#define OSD_BITMAP_BYTES(cols, rows) (OSD_TILE_COUNT(cols, rows) * OSD_TILE_BYTES)
#define OSD_DIRTY_BYTES(cols, rows) ((OSD_TILE_COUNT(cols, rows) + 7u) / 8u)

typedef struct {
    uint8_t *pixels; /* Caller-owned, preferably __xdata on SDCC/8051. */
    uint8_t *dirty;
    uint8_t cols;
    uint8_t rows;
    uint16_t tile_count;
} osd_canvas;

/* Return nonzero only after a successful synchronous upload.
 * tile_id is relative to this canvas, not an absolute hardware font address.
 * Packing is described in README.md; adapt to the hardware at this boundary.
 */
typedef uint8_t (*osd_upload_fn)(uint16_t tile_id, const uint8_t *bytes,
                               uint16_t count, void *user);

/* Return 0 on invalid dimensions/buffer sizes; 1 on success.
 * Initializes a blank canvas and marks every tile dirty.
 * Storage and dirty arrays must be separate, non-overlapping buffers.
 */
uint8_t osd_canvas_init(osd_canvas *c, uint8_t cols, uint8_t rows,
                        uint8_t *pixels, uint16_t pixel_bytes,
                        uint8_t *dirty, uint16_t dirty_bytes);
void osd_clear(osd_canvas *c);
void osd_mark_all_dirty(osd_canvas *c);

/* Coordinates are signed pixels, origin at top left; y increases downwards.
 * Ink 0 erases; any nonzero ink sets pixels. Out-of-bounds pixels are ignored.
 * osd_line includes both endpoints and handles every slope and direction.
 */
void osd_pixel(osd_canvas *c, int16_t x, int16_t y, uint8_t ink);
void osd_line(osd_canvas *c, int16_t x0, int16_t y0,
              int16_t x1, int16_t y1, uint8_t ink);

/* Upload dirty tiles in row-major order, clear flags only after success.
 * Stop at the first failed upload. Returns the number uploaded this call.
 * Uploads are synchronous. Do not draw/flush concurrently or from an ISR.
 */
uint16_t osd_flush(osd_canvas *c, osd_upload_fn upload, void *user);

#endif
