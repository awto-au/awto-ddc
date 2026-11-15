/* font.c: fixed-cell loader for native Spleen 8x16 and Tamzen 8x15 bitmap glyphs.
 * tools/gen_font.py packs them losslessly into the RTD's 12x18 font tiles. */
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
AWTO_PLACE(group=font)  /* reads the blobs via movc: same bank (awto-ddc#149) */
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

uint8_t __xdata osd_cw = 8, osd_rh = 18;       /* cell width / row height of the loaded font */

uint8_t osd_font_cw(uint8_t font)             /* cell width of a font before it is loaded (the map's blanks match it) */
{
    return font_cw[(font < OSD_FONT_N) ? font : 0];
}

void osd_font_load(uint8_t font)
{
    if (font >= OSD_FONT_N)
        font = 0;
    osd_cw = font_cw[font];
    osd_rh = font_rh[font];
    switch (font) {
    case 1: FONT_LOAD_TAMZEN break;
    case 2: FONT_LOAD_SPLEEN6 break;
    case 3: FONT_LOAD_SPLEEN5 break;
    case 4: FONT_LOAD_TAMZEN5 break;
    case 5: FONT_LOAD_TAMZEN6 break;
    case 6: FONT_LOAD_TAMZEN7 break;
    default: FONT_LOAD_SPLEEN break;
    }
    osd_tc_rowh(osd_rh);
}
