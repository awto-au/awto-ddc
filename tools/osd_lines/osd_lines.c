/* SPDX-License-Identifier: MIT */
#include "osd_lines.h"
#include <stddef.h>
#include <string.h>

#if OSD_TILE_W * OSD_TILE_H <= 256
typedef uint8_t osd_bit_t;              /* bit index inside a tile: one byte for 12 x 18 */
#else
typedef uint16_t osd_bit_t;
#endif

/* The one cursor: calls on a canvas are serialised (README). tile / base / bitpos follow col, row, x, y
 * incrementally (no multiply per pixel); they are used only while the cursor is inside the canvas. */
typedef struct {
    int16_t col;
    int16_t row;
    uint8_t x;
    uint8_t y;
    osd_bit_t bitpos;                    /* y * OSD_TILE_W + x */
    uint16_t tile;                      /* row * cols + col */
    uint16_t base;                      /* tile * OSD_TILE_BYTES */
} tile_cursor;

static OSD_MEM tile_cursor s_p;
static OSD_MEM uint16_t s_cols;
static OSD_MEM uint16_t s_row_bytes;    /* cols * OSD_TILE_BYTES */

static void cursor_init(osd_canvas OSD_MEM *c, int16_t x, int16_t y)
{
    int16_t rem;
    if ((uint16_t)x <= 0xFFu) {         /* 0..255: byte divide (8051 div ab, no library call) */
        s_p.col = (uint8_t)x / (uint8_t)OSD_TILE_W;
        s_p.x = (uint8_t)x % (uint8_t)OSD_TILE_W;
    } else {
        s_p.col = x / OSD_TILE_W;
        rem = x % OSD_TILE_W;
        if (rem < 0) { rem += OSD_TILE_W; --s_p.col; }
        s_p.x = (uint8_t)rem;
    }
    if ((uint16_t)y <= 0xFFu) {
        s_p.row = (uint8_t)y / (uint8_t)OSD_TILE_H;
        s_p.y = (uint8_t)y % (uint8_t)OSD_TILE_H;
    } else {
        s_p.row = y / OSD_TILE_H;
        rem = y % OSD_TILE_H;
        if (rem < 0) { rem += OSD_TILE_H; --s_p.row; }
        s_p.y = (uint8_t)rem;
    }
    s_p.bitpos = (osd_bit_t)((osd_bit_t)s_p.y * OSD_TILE_W + s_p.x);
    if (s_cols != c->cols) {
        s_cols = c->cols;
        s_row_bytes = s_cols * OSD_TILE_BYTES;
    }
    s_p.tile = (uint16_t)((uint16_t)s_p.row * s_cols + (uint16_t)s_p.col);
    s_p.base = s_p.tile * OSD_TILE_BYTES;
}

static void cursor_x(int8_t step)
{
    if (step > 0) {
        ++s_p.bitpos;
        if (++s_p.x == OSD_TILE_W) {
            s_p.x = 0; s_p.bitpos -= OSD_TILE_W;
            ++s_p.col; ++s_p.tile; s_p.base += OSD_TILE_BYTES;
        }
    } else if (s_p.x == 0) {
        s_p.x = OSD_TILE_W - 1; s_p.bitpos += OSD_TILE_W - 1;
        --s_p.col; --s_p.tile; s_p.base -= OSD_TILE_BYTES;
    } else { --s_p.x; --s_p.bitpos; }
}

static void cursor_y(int8_t step)
{
    if (step > 0) {
        s_p.bitpos += OSD_TILE_W;
        if (++s_p.y == OSD_TILE_H) {
            s_p.y = 0; s_p.bitpos -= (osd_bit_t)(OSD_TILE_W * OSD_TILE_H);
            ++s_p.row; s_p.tile += s_cols; s_p.base += s_row_bytes;
        }
    } else if (s_p.y == 0) {
        s_p.y = OSD_TILE_H - 1; s_p.bitpos += (osd_bit_t)(OSD_TILE_W * (OSD_TILE_H - 1));
        --s_p.row; s_p.tile -= s_cols; s_p.base -= s_row_bytes;
    } else { --s_p.y; s_p.bitpos -= OSD_TILE_W; }
}

/* Returns 0 when the cursor is outside the canvas (nothing written). */
static uint8_t cursor_plot(osd_canvas OSD_MEM *c, uint8_t ink)
{
    uint16_t offset;
    uint8_t mask, old, value;
    if (s_p.col < 0 || s_p.row < 0 || s_p.col >= c->cols || s_p.row >= c->rows)
        return 0;
    offset = s_p.base + (s_p.bitpos >> 3);
    mask = (uint8_t)(0x80u >> (s_p.bitpos & 7u));
    old = c->pixels[offset];
    value = ink ? (uint8_t)(old | mask) : (uint8_t)(old & (uint8_t)~mask);
    if (old != value) {
        c->pixels[offset] = value;
        c->dirty[s_p.tile >> 3] |= (uint8_t)(1u << (s_p.tile & 7u));
    }
    return 1;
}

void osd_mark_all_dirty(osd_canvas OSD_MEM *c)
{
    uint16_t count = (c->tile_count + 7u) / 8u;
    memset(c->dirty, 0xff, count);
    if (c->tile_count & 7u)
        c->dirty[count - 1] = (uint8_t)((1u << (c->tile_count & 7u)) - 1u);
}

uint8_t osd_canvas_init(osd_canvas OSD_MEM *c, uint8_t cols, uint8_t rows,
                        uint8_t OSD_MEM *pixels, uint16_t pixel_bytes,
                        uint8_t OSD_MEM *dirty, uint16_t dirty_bytes)
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

void osd_clear(osd_canvas OSD_MEM *c)
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

void osd_pixel(osd_canvas OSD_MEM *c, int16_t x, int16_t y, uint8_t ink)
{
    cursor_init(c, x, y);
    cursor_plot(c, ink);
}

/* Bresenham with error e0 = major / 2: after i steps the minor axis has moved k(i) = ceil((i * minor - e0) / major)
 * (0 while i * minor <= e0) and the error is e0 - i * minor + k(i) * major. */
static uint16_t minor_steps(uint16_t i, uint16_t major, uint16_t minor, uint16_t e0)
{
    uint32_t n = (uint32_t)i * minor;
    return n <= e0 ? 0 : (uint16_t)((n - e0 + major - 1u) / major);
}

/* First step i with k(i) >= m (m >= 1, minor > 0). */
static uint32_t step_for_minor(uint16_t m, uint16_t major, uint16_t minor, uint16_t e0)
{
    uint32_t n = (uint32_t)(m - 1u) * major + e0 + 1u;
    return (n + minor - 1u) / minor;
}

/* Steps along the major axis before the line can be inside the canvas (both axes past their near edge);
 * 0xFFFF when it never is. */
static uint16_t skip_steps(int16_t a0, int8_t sa, int16_t amax, int16_t b0, int8_t sb, int16_t bmax,
                           uint16_t major, uint16_t minor, uint16_t e0)
{
    uint32_t skip = 0, need;
    uint16_t m = 0;
    if (sa > 0 && a0 < 0) skip = (uint16_t)(0u - (uint16_t)a0);
    else if (sa < 0 && a0 > amax) skip = (uint16_t)((uint16_t)a0 - (uint16_t)amax);
    if (sb > 0 && b0 < 0) m = (uint16_t)(0u - (uint16_t)b0);
    else if (sb < 0 && b0 > bmax) m = (uint16_t)((uint16_t)b0 - (uint16_t)bmax);
    if (m != 0) {
        if (m > minor) return 0xFFFFu;
        need = step_for_minor(m, major, minor, e0);
        if (need > skip) skip = need;
    }
    return skip > major ? 0xFFFFu : (uint16_t)skip;
}

void osd_line(osd_canvas OSD_MEM *c, int16_t x0, int16_t y0,
              int16_t x1, int16_t y1, uint8_t ink)
{
    uint16_t dx, dy, error, remaining, skip, k;
    int16_t w, h;
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
    w = (int16_t)((uint16_t)c->cols * OSD_TILE_W);
    h = (int16_t)((uint16_t)c->rows * OSD_TILE_H);
    /* Fast rejection also bounds obviously invisible long lines. */
    if ((x0 < 0 && x1 < 0) || (y0 < 0 && y1 < 0) ||
        (x0 >= w && x1 >= w) || (y0 >= h && y1 >= h))
        return;
    /* Start at the first step that can be inside, stop at the first pixel outside after it:
     * both axes move monotonically, so the pixels skipped are exactly the ones outside. */
    if (dx >= dy) {
        error = dx / 2u;
        skip = skip_steps(x0, sx, w - 1, y0, sy, h - 1, dx, dy, error);
        if (skip == 0xFFFFu) return;
        if (skip != 0) {
            k = minor_steps(skip, dx, dy, error);
            error = (uint16_t)((uint32_t)error + (uint32_t)k * dx - (uint32_t)skip * dy);
            x0 = (int16_t)(sx > 0 ? (uint16_t)x0 + skip : (uint16_t)x0 - skip);
            y0 = (int16_t)(sy > 0 ? (uint16_t)y0 + k : (uint16_t)y0 - k);
        }
        remaining = dx - skip;
        cursor_init(c, x0, y0);
        for (;;) {
            if (!cursor_plot(c, ink) || remaining == 0) break;
            --remaining;
            cursor_x(sx);
            /* Avoid error + dy or 2*error overflowing a 16-bit target. */
            if (error < dy) {
                error += dx - dy;
                cursor_y(sy);
            } else { error -= dy; }
        }
    } else {
        error = dy / 2u;
        skip = skip_steps(y0, sy, h - 1, x0, sx, w - 1, dy, dx, error);
        if (skip == 0xFFFFu) return;
        if (skip != 0) {
            k = minor_steps(skip, dy, dx, error);
            error = (uint16_t)((uint32_t)error + (uint32_t)k * dy - (uint32_t)skip * dx);
            y0 = (int16_t)(sy > 0 ? (uint16_t)y0 + skip : (uint16_t)y0 - skip);
            x0 = (int16_t)(sx > 0 ? (uint16_t)x0 + k : (uint16_t)x0 - k);
        }
        remaining = dy - skip;
        cursor_init(c, x0, y0);
        for (;;) {
            if (!cursor_plot(c, ink) || remaining == 0) break;
            --remaining;
            cursor_y(sy);
            if (error < dx) {
                error += dy - dx;
                cursor_x(sx);
            } else { error -= dx; }
        }
    }
}

#ifndef OSD_NO_FLUSH                    /* SDCC mcs51: a call through a 4-argument function pointer needs reentrant; such callers upload tiles themselves */
uint16_t osd_flush(osd_canvas OSD_MEM *c, osd_upload_fn upload, void *user)
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
#endif
