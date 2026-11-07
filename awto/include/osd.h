/* osd.h: on-screen display engine (windows, character map, fonts, palette).
 * DRAFT interface (wave A); spec osd (step 4) refines it. Our UI sits on top of this, never on registers. */
#ifndef AWTO_OSD_H
#define AWTO_OSD_H

#include <stdint.h>
#include "cc.h"

struct osd_win {
    uint16_t x0, y0, x1, y1;       /* OSD pixels, inclusive */
    uint8_t  colour;               /* palette index */
    uint8_t  border, shadow;       /* palette indices; 0xFF = none */
    uint8_t  style;                /* gradient / border style bits, per spec osd */
};

void    osd_init(void);
void    osd_show(uint8_t on);
void    osd_place(uint16_t x, uint16_t y);           /* top-left of the OSD on the panel */
void    osd_scale(uint8_t h2, uint8_t v2);           /* 1 = double size in that direction */
uint8_t osd_hdouble(void);                           /* current horizontal double-size state */
void    osd_window(uint8_t n, const struct osd_win *w);
void    osd_window_off(uint8_t n);
void    osd_grid(uint8_t rows, uint8_t cols);        /* character map size */
void    osd_text(uint8_t row, uint8_t col, const uint8_t *glyphs, uint8_t n, uint8_t fg, uint8_t bg);
void    osd_fill(uint8_t row, uint8_t col, uint8_t n, uint8_t glyph, uint8_t fg, uint8_t bg);
void    osd_font(uint16_t first, const uint8_t __code *src, uint16_t len);   /* our font format, spec osd */
void    osd_palette(uint8_t idx, uint8_t r, uint8_t g, uint8_t b);

#endif
