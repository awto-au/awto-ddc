/* font.c: the awto OSD font (tools/gen_font.py -> font_data.inc): 24 x 36 px, 2 bpp, fixed pitch = 4 tiles of 12 x 18 per
 * character, tiles shared between characters. Glyphs are uploaded raw: the RTD2795 VLC decoder corrupts this 2-bit font
 * on real hardware even when fed as short streams. Reading __code happens here (bank-safe); the integrator writes SRAM. */
#include <stdint.h>
#include "cc.h"
#include "osd.h"
#include "ui.h"
#include "font_data.inc"

static uint8_t __xdata fbuf[32];

void osd_font_tiles(char c, uint8_t __xdata *q4)
{
    uint8_t i, k = (uint8_t)c;
    uint16_t o;                                          /* 95 characters x 4 ids = 380: not a byte */

    if (k < OSD_FONT_FIRST || k > OSD_FONT_LAST)
        k = OSD_FONT_FIRST;
    o = (uint16_t)(k - OSD_FONT_FIRST) * 4;
    for (i = 0; i < 4; i++)
        q4[i] = font_ids[o + i];
}

static void font_raw_data(const uint8_t __code *b, uint16_t tiles)
{
    uint16_t n = tiles * OSD_FONT_TILE_BYTES, o = 0;
    uint8_t k, m;

    osd_tc_raw_begin(0);
    while (n != 0) {
        m = n > sizeof fbuf ? (uint8_t)sizeof fbuf : (uint8_t)n;
        for (k = 0; k < m; k++)
            fbuf[k] = b[o + k];
        osd_tc_raw_put(fbuf, m);
        o += m;
        n -= m;
    }
    osd_tc_raw_end();
}

void osd_font_load(void)
{
    FONT_LOAD_CHUNKS
}
