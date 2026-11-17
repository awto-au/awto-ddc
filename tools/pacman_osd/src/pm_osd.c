#include "pm_osd.h"
#include "pm_assets.h"

typedef struct { uint8_t x, y, fg, visible, frame, phase; uint16_t glyph; } Actor;
static PM_XDATA Actor actors[PM_ACTORS];
#ifndef PM_MINIMAL
static PM_XDATA uint8_t background[PM_CELLS];
#else
#define PM_EAT_SEG 200U
/* 4800 map bits = 600 bytes.  Three arrays fit the real linker's separate
 * XDATA holes; one contiguous 600-byte allocation does not. */
static PM_XDATA uint8_t eaten0[PM_EAT_SEG], eaten1[PM_EAT_SEG], eaten2[PM_EAT_SEG];

static uint8_t pellet_eaten(uint16_t pos)
{
    uint16_t n = pos >> 3;
    uint8_t mask = 1U << (pos & 7U);
    if (n < PM_EAT_SEG) return eaten0[n] & mask;
    if (n < PM_EAT_SEG * 2U) return eaten1[n - PM_EAT_SEG] & mask;
    return eaten2[n - PM_EAT_SEG * 2U] & mask;
}

static void pellet_mark(uint16_t pos)
{
    uint16_t n = pos >> 3;
    uint8_t mask = 1U << (pos & 7U);
    if (n < PM_EAT_SEG) eaten0[n] |= mask;
    else if (n < PM_EAT_SEG * 2U) eaten1[n - PM_EAT_SEG] |= mask;
    else eaten2[n - PM_EAT_SEG * 2U] |= mask;
}
#endif
static PM_XDATA uint8_t dirty_x[PM_DIRTY_CAP], dirty_y[PM_DIRTY_CAP];
static PM_XDATA uint8_t dirty_count, redraw_all;

static uint16_t fragment(uint8_t slot, uint8_t dx, uint8_t dy)
{
    uint16_t off;
    if (actors[slot].frame == 255) return (dx == 0 && dy == 0) ? actors[slot].glyph : 0;
    off = (uint16_t)actors[slot].frame * (PM_PHASES * 4U) + (uint16_t)actors[slot].phase * 4U + (uint16_t)dy * 2U + dx;
    return pm_phase_glyph[off];
}

static void dirty(uint8_t x, uint8_t y)
{
    uint8_t i;
    if (redraw_all) return;
    for (i = 0; i < dirty_count; ++i)
        if (dirty_x[i] == x && dirty_y[i] == y) return;
    if (dirty_count == PM_DIRTY_CAP) { redraw_all = 1; dirty_count = 0; return; }
    dirty_x[dirty_count] = x; dirty_y[dirty_count] = y; ++dirty_count;
}

static void draw(uint8_t x, uint8_t y)
{
    uint8_t i, fg;
    uint16_t pos, glyph, g;
    pos = (uint16_t)y * PM_COLS + x;
#ifdef PM_MINIMAL
    glyph = pm_initial_map[pos];
    if ((glyph == PM_G_DOT || glyph == PM_G_POWER) && pellet_eaten(pos)) glyph = PM_G_BLANK;
#else
    glyph = background[pos];
#endif
    fg = pm_asset_fg[glyph];
    for (i = 0; i < PM_ACTORS; ++i)
        if (actors[i].visible && x >= actors[i].x && y >= actors[i].y &&
            x - actors[i].x < 2 && y - actors[i].y < 2) {
            g = fragment(i, x - actors[i].x, y - actors[i].y);
            if (g) { glyph = g; fg = actors[i].fg; }
        }
    /* Bit 5 is the ninth glyph-id bit, NOT a different pixel format. */
    pm_hw_word(PM_FS_BASE + pos, (uint8_t)(PM_CHAR_B0 | ((glyph >> 8) << 5)),
               (uint8_t)glyph, (uint8_t)(fg << 4 | 1));
}

static void dirty_actor(uint8_t slot)
{
    uint8_t dx, dy, x, y;
    if (!actors[slot].visible) return;
    for (dy = 0; dy < 2; ++dy) for (dx = 0; dx < 2; ++dx) {
        x = actors[slot].x + dx; y = actors[slot].y + dy;
        if (x < PM_COLS && y < PM_ROWS && fragment(slot, dx, dy)) dirty(x,y);
    }
}

void pm_redraw(void)
{
    uint8_t x, y;
    for (y = 0; y < PM_ROWS; ++y)
        for (x = 0; x < PM_COLS; ++x) draw(x, y);
    dirty_count = 0; redraw_all = 0;
}

void pm_load(void)
{
    uint16_t n, off;
    uint8_t i;
    for (i = 0; i < PM_ACTORS; ++i) actors[i].visible = 0;
    dirty_count = 0; redraw_all = 0;
#ifndef PM_MINIMAL
    for (n = 0; n < PM_CELLS; ++n) background[n] = pm_initial_map[n];
#else
    for (n = 0; n < PM_EAT_SEG; ++n) eaten0[n] = eaten1[n] = eaten2[n] = 0;
#endif
    for (n = 0; n < PM_ROWS; ++n) pm_hw_word(n, 0x80, PM_CELL_H - 1, PM_COLS);
    pm_hw_word(PM_ROWS, 0, 0, 0);
    /* Complete expanded glyphs are uploaded ONCE; no pixel loop in pm_flush. */
    for (n = 0; n < PM_GLYPHS * PM_FONT_WORDS; ++n) {
        off = n * 3U;
        pm_hw_word(PM_FONT_BASE + n, pm_glyph_bytes[off],
                   pm_glyph_bytes[off + 1], pm_glyph_bytes[off + 2]);
    }
    pm_redraw();
}

uint8_t pm_actor(uint8_t slot, uint8_t x, uint8_t y, uint16_t glyph, uint8_t fg, uint8_t visible)
{
    if (slot >= PM_ACTORS || x >= PM_COLS || y >= PM_ROWS || glyph >= PM_GLYPHS || fg > 15 || visible > 1) return 0;
    if (actors[slot].visible && actors[slot].x == x && actors[slot].y == y &&
        actors[slot].glyph == glyph && actors[slot].fg == fg && actors[slot].frame == 255 && visible) return 1;
    dirty_actor(slot);
    actors[slot].x = x; actors[slot].y = y; actors[slot].glyph = glyph;
    actors[slot].fg = fg; actors[slot].visible = visible; actors[slot].frame = 255;
    dirty_actor(slot);
    return 1;
}

uint8_t pm_actor_smooth(uint8_t slot, uint16_t x, uint16_t y, uint8_t frame, uint8_t fg, uint8_t visible)
{
    uint8_t cx, cy, phase;
    if (slot >= PM_ACTORS || x > (PM_COLS-1)*PM_CELL_W || y > (PM_ROWS-1)*PM_CELL_H ||
        x % 3U || y % 3U || frame >= PM_PHASE_FRAMES || fg > 15 || visible > 1) return 0;
    cx = (uint8_t)(x / PM_CELL_W); cy = (uint8_t)(y / PM_CELL_H);
    phase = (uint8_t)((y % PM_CELL_H) / 3U * 4U + (x % PM_CELL_W) / 3U);
    if (actors[slot].visible && visible && actors[slot].x == cx && actors[slot].y == cy &&
        actors[slot].phase == phase && actors[slot].frame == frame && actors[slot].fg == fg) return 1;
    dirty_actor(slot);
    actors[slot].x = cx; actors[slot].y = cy; actors[slot].frame = frame;
    actors[slot].phase = phase; actors[slot].fg = fg; actors[slot].visible = visible;
    dirty_actor(slot);
    return 1;
}

uint8_t pm_background_at(uint8_t x, uint8_t y)
{
    if (x >= PM_COLS || y >= PM_ROWS) return PM_G_BLANK;
#ifdef PM_MINIMAL
    {
        uint16_t pos = (uint16_t)y * PM_COLS + x;
        uint8_t g = pm_initial_map[pos];
        return ((g == PM_G_DOT || g == PM_G_POWER) && pellet_eaten(pos)) ? PM_G_BLANK : g;
    }
#else
    return background[(uint16_t)y * PM_COLS + x];
#endif
}

uint8_t pm_background(uint8_t x, uint8_t y, uint8_t glyph)
{
#ifdef PM_MINIMAL
    if (x >= PM_COLS || y >= PM_ROWS || glyph >= PM_BASE_GLYPHS) return 0;
    /* The diagnostic build keeps the maze immutable in code memory. */
    return pm_background_at(x, y) == glyph;
#else
    uint16_t pos;
    if (x >= PM_COLS || y >= PM_ROWS || glyph >= PM_BASE_GLYPHS) return 0;
    pos = (uint16_t)y * PM_COLS + x;
    if (background[pos] != glyph) { background[pos] = glyph; dirty(x, y); }
    return 1;
#endif
}

uint8_t pm_eat(uint8_t x, uint8_t y)
{
#ifdef PM_MINIMAL
    uint16_t pos;
    uint8_t g;
    if (x >= PM_COLS || y >= PM_ROWS) return 0;
    pos = (uint16_t)y * PM_COLS + x;
    g = pm_initial_map[pos];
    if ((g != PM_G_DOT && g != PM_G_POWER) || pellet_eaten(pos)) return 0;
    pellet_mark(pos);
    dirty(x, y);
    return 1;
#else
    uint8_t g;
    if (x >= PM_COLS || y >= PM_ROWS) return 0;
    g = pm_background_at(x, y);
    if (g != PM_G_DOT && g != PM_G_POWER) return 0;
    return pm_background(x, y, PM_G_BLANK);
#endif
}

void pm_flush(void)
{
    uint8_t i;
    if (redraw_all) { pm_redraw(); return; }
    for (i = 0; i < dirty_count; ++i) draw(dirty_x[i], dirty_y[i]);
    dirty_count = 0;
}
