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
void    osd_fill(uint8_t row, uint8_t col, uint8_t n, uint8_t glyph, uint8_t fg, uint8_t bg);
void    osd_palette(uint8_t idx, uint8_t r, uint8_t g, uint8_t b);

/* Text layer (the awto OSD design system, awto-ddc#89): a chars x lines grid of fixed-pitch characters, each 24 x 36 px at 2 bpp =
 * 2 x 2 hardware cells of 12 x 18. One tile id (0..255) per cell; the integrator implements this on the OSD engine. ui.h = the
 * components on top (frame, title, rows, status strip, key legend); screens never touch this layer directly.
 * Colour sets (osd_style): white ramp on black / dim / white on red / red text. Window 0..7 = decoration bars (red / black). */
enum osd_style { OS_TEXT = 0, OS_DIM = 1, OS_ONRED = 2, OS_RED = 3, OS_N = 4 };
enum osd_bar_colour { OB_BLACK = 0, OB_RED = 1 };
#define OSD_CHAR_W 24
#define OSD_CHAR_H 36
void    osd_tc_open(uint8_t chars, uint8_t lines);   /* grid + palette, all windows off; OSD stays off until osd_tc_show */
void    osd_tc_cells(uint8_t maprow, uint8_t cell, const uint8_t __xdata *tiles, uint8_t n, uint8_t style);   /* n cells of one map row */
void    osd_tc_bar(uint8_t win, uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint8_t colour);   /* px, inclusive */
void    osd_tc_bar_off(uint8_t win);
void    osd_tc_place(uint8_t hpos_pct, uint8_t vpos_pct, uint8_t big);   /* position 0..100 %, big = 2x size */
void    osd_tc_show(uint8_t on);
void    osd_tc_close(void);                          /* OSD off; the Realtek SDK menu may draw again */
/* VLC font download (osd-font-download.md): begin(map8 = the blob's 8 value-map bytes, tile = first tile id), put(stream bytes,
 * the blob after its 10 byte header, END included), end. The caller reads the __code blob (bank-safe) and passes xdata copies. */
void    osd_tc_vlc_begin(const uint8_t __xdata *map8, uint16_t tile);
void    osd_tc_vlc_put(const uint8_t __xdata *p, uint8_t n);
void    osd_tc_vlc_end(void);

#endif
