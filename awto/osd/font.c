/* font.c: the awto OSD font (tools/gen_font.py -> font_data.inc): 24 x 36 px, 2 bpp, fixed pitch = 4 tiles of 12 x 18 per
 * character, tiles shared between characters. The tile data is VLC compressed and loaded through the hardware decoder
 * (osd-font-download.md). Reading the __code blob happens here (bank-safe), the register work in the integrator (osd_tc_vlc_*). */
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

/* one blob = [8 byte value map][2 byte BE length N][N stream bytes]; tile = first tile id of this blob */
static void font_blob(const uint8_t __code *b, uint16_t tile)
{
    uint16_t n = (uint16_t)b[8] << 8 | b[9], o = 10;
    uint8_t k, m;

    for (k = 0; k < 8; k++)
        fbuf[k] = b[k];
    osd_tc_vlc_begin(fbuf, tile);
    while (n != 0) {
        m = n > sizeof fbuf ? (uint8_t)sizeof fbuf : (uint8_t)n;
        for (k = 0; k < m; k++)
            fbuf[k] = b[o + k];
        osd_tc_vlc_put(fbuf, m);
        o += m;
        n -= m;
    }
    osd_tc_vlc_end();
}

void osd_font_load(void)
{
    FONT_LOAD_CHUNKS
}
