/* font.c: fixed-cell loader for the monitor's normal Realtek UI letterforms.
 * tools/gen_font.py extracts those glyphs from the SDK and emits the VLC data below. */
#include <stdint.h>
#include "cc.h"
#include "osd.h"
#include "ui.h"
#include "font_data.inc"

static uint8_t __xdata fbuf[32];

uint8_t osd_font_glyph(char c)
{
    uint8_t k = (uint8_t)c;

    if (k < OSD_FONT_FIRST || k > OSD_FONT_LAST)
        k = '?';
    return font_ids[k - OSD_FONT_FIRST];
}

/* one blob = [8-byte value map][2-byte BE length N][N stream bytes] */
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
