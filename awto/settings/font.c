/* font.c: our OSD font (tools/gen_font.py -> font_tab.inc), loaded glyph by glyph through the text-cell layer. */
#include <stdint.h>
#include "cc.h"
#include "osd.h"
#include "font_tab.inc"

static uint8_t __xdata g[27];

void osd_font_load(void)
{
    uint8_t i, k;
    uint16_t o = 0;

    for (i = 0; i < OSD_FONT_N; i++) {
        for (k = 0; k < 27; k++)
            g[k] = font_tab[o++];
        osd_tc_glyph(i, g);
    }
}
