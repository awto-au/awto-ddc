/* SPDX-License-Identifier: MIT */
#include "osd_lines.h"
#include <stddef.h>
#include <string.h>

typedef struct {
    int16_t col;
    int16_t row;
    uint8_t x;
    uint8_t y;
} tile_cursor;

static void cursor_init(tile_cursor *p, int16_t x, int16_t y)
{
    int16_t rem;
    p->col = x / OSD_TILE_W;
    rem = x % OSD_TILE_W;
    if (rem < 0) { rem += OSD_TILE_W; --p->col; }
    p->x = (uint8_t)rem;
    p->row = y / OSD_TILE_H;
    rem = y % OSD_TILE_H;
    if (rem < 0) { rem += OSD_TILE_H; --p->row; }
    p->y = (uint8_t)rem;
}

static void cursor_x(tile_cursor *p, int8_t step)
{
    if (step > 0) {
        if (++p->x == OSD_TILE_W) { p->x = 0; ++p->col; }
    } else if (p->x == 0) {
        p->x = OSD_TILE_W - 1;
        --p->col;
    } else { --p->x; }
}

static void cursor_y(tile_cursor *p, int8_t step)
{
    if (step > 0) {
        if (++p->y == OSD_TILE_H) { p->y = 0; ++p->row; }
    } else if (p->y == 0) {
        p->y = OSD_TILE_H - 1;
        --p->row;
    } else { --p->y; }
}

static void cursor_plot(osd_canvas *c, const tile_cursor *p, uint8_t ink)
{
    uint16_t tile, bit, offset;
    uint8_t mask, old, value;
    if (p->col < 0 || p->row < 0 || p->col >= c->cols || p->row >= c->rows)
        return;
    tile = (uint16_t)p->row * c->cols + (uint16_t)p->col;
    bit = (uint16_t)p->y * OSD_TILE_W + p->x;
    offset = tile * OSD_TILE_BYTES + (bit >> 3);
    mask = (uint8_t)(0x80u >> (bit & 7u));
    old = c->pixels[offset];
    value = ink ? (uint8_t)(old | mask) : (uint8_t)(old & (uint8_t)~mask);
    if (old != value) {
        c->pixels[offset] = value;
        c->dirty[tile >> 3] |= (uint8_t)(1u << (tile & 7u));
    }
}

void osd_mark_all_dirty(osd_canvas *c)
{
    uint16_t count = (c->tile_count + 7u) / 8u;
    memset(c->dirty, 0xff, count);
    if (c->tile_count & 7u)
        c->dirty[count - 1] = (uint8_t)((1u << (c->tile_count & 7u)) - 1u);
}

uint8_t osd_canvas_init(osd_canvas *c, uint8_t cols, uint8_t rows,
                        uint8_t *pixels, uint16_t pixel_bytes,
                        uint8_t *dirty, uint16_t dirty_bytes)
{
    uint32_t count = (uint32_t)cols * rows;
    if (c == NULL || pixels == NULL || dirty == NULL || count == 0 ||
        count * OSD_TILE_BYTES > pixel_bytes || (count + 7u) / 8u > dirty_bytes)
        return 0;
    c->pixels = pixels;
    c->dirty = dirty;
    c->cols = cols;
    c->rows = rows;
    c->tile_count = (uint16_t)count;
    memset(pixels, 0, (size_t)(count * OSD_TILE_BYTES));
    osd_mark_all_dirty(c);
    return 1;
}

void osd_clear(osd_canvas *c)
{
    uint16_t tile, offset = 0;
    uint16_t b;
    uint8_t changed;
    for (tile = 0; tile < c->tile_count; ++tile) {
        changed = 0;
        for (b = 0; b < OSD_TILE_BYTES; ++b, ++offset) {
            changed |= c->pixels[offset];
            c->pixels[offset] = 0;
        }
        if (changed)
            c->dirty[tile >> 3] |= (uint8_t)(1u << (tile & 7u));
    }
}

void osd_pixel(osd_canvas *c, int16_t x, int16_t y, uint8_t ink)
{
    tile_cursor p;
    cursor_init(&p, x, y);
    cursor_plot(c, &p, ink);
}

void osd_line(osd_canvas *c, int16_t x0, int16_t y0,
              int16_t x1, int16_t y1, uint8_t ink)
{
    tile_cursor p;
    uint16_t dx, dy, error, remaining;
    int8_t sx, sy;
    /* Unsigned subtraction represents full-range signed endpoint distances.
     * All raster-loop arithmetic is 16-bit, including 65535-pixel spans.
     */
    sx = x1 >= x0 ? 1 : -1;
    sy = y1 >= y0 ? 1 : -1;
    dx = x1 >= x0 ? (uint16_t)((uint16_t)x1 - (uint16_t)x0)
                  : (uint16_t)((uint16_t)x0 - (uint16_t)x1);
    dy = y1 >= y0 ? (uint16_t)((uint16_t)y1 - (uint16_t)y0)
                  : (uint16_t)((uint16_t)y0 - (uint16_t)y1);
    /* Fast rejection also bounds obviously invisible long lines. */
    if ((x0 < 0 && x1 < 0) || (y0 < 0 && y1 < 0) ||
        (x0 >= (int16_t)((uint16_t)c->cols * OSD_TILE_W) &&
         x1 >= (int16_t)((uint16_t)c->cols * OSD_TILE_W)) ||
        (y0 >= (int16_t)((uint16_t)c->rows * OSD_TILE_H) &&
         y1 >= (int16_t)((uint16_t)c->rows * OSD_TILE_H)))
        return;
    cursor_init(&p, x0, y0);
    if (dx >= dy) {
        error = dx / 2u;
        remaining = dx;
        for (;;) {
            cursor_plot(c, &p, ink);
            if (remaining == 0) break;
            --remaining;
            cursor_x(&p, sx);
            /* Avoid error + dy or 2*error overflowing a 16-bit target. */
            if (error < dy) {
                error += dx - dy;
                cursor_y(&p, sy);
            } else { error -= dy; }
        }
    } else {
        error = dy / 2u;
        remaining = dy;
        for (;;) {
            cursor_plot(c, &p, ink);
            if (remaining == 0) break;
            --remaining;
            cursor_y(&p, sy);
            if (error < dx) {
                error += dy - dx;
                cursor_x(&p, sx);
            } else { error -= dx; }
        }
    }
}

uint16_t osd_flush(osd_canvas *c, osd_upload_fn upload, void *user)
{
    uint16_t tile, done = 0;
    uint8_t mask;
    if (upload == NULL) return 0;
    for (tile = 0; tile < c->tile_count; ++tile) {
        mask = (uint8_t)(1u << (tile & 7u));
        if (!(c->dirty[tile >> 3] & mask)) continue;
        if (!upload(tile, &c->pixels[tile * OSD_TILE_BYTES], OSD_TILE_BYTES, user))
            break;
        c->dirty[tile >> 3] &= (uint8_t)~mask;
        ++done;
    }
    return done;
}
