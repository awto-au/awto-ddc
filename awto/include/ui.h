/* ui.h: the awto OSD components (awto-ddc#89). The menu uses the same normal Realtek letterforms as the small user-facing
 * cards, in fixed 12 x 18 cells, with the shared blue-on-white AWTO colour scheme. */
#ifndef AWTO_UI_H
#define AWTO_UI_H

#include <stdint.h>
#include "cc.h"
#include "osd.h"

/* screen geometry in characters (480 x 378 px; default hardware 2x presents 960 x 756) */
#define UI_CHARS    40
#define UI_LINES    21
#define UI_L_TITLE  0
#define UI_L_STRIP  1            /* status strip: 3 lines, one per input */
#define UI_L_LIST   4
#define UI_LIST     14           /* list lines 4..17 */
#define UI_L_MSG    18
#define UI_L_LEGEND 19           /* names in physical order, actions below */

/* selected-row look (Dan picks, #87): bar = blue bar behind white text; mark = blue '>' marker + blue underline, text unchanged */
enum ui_hl { UI_HL_BAR = 0, UI_HL_MARK = 1 };
extern uint8_t __xdata ui_hl_style;

void ui_open(void);                                   /* frame, bars, palette, font; the screen stays hidden */
void ui_show(uint8_t on);
void ui_close(void);
void ui_text(uint8_t line, uint8_t col, const char __xdata *s, uint8_t n, uint8_t style);
void ui_title(const char __xdata *s);                 /* white on the red title bar */
void ui_row(uint8_t line, const char __xdata *s, uint8_t style, uint8_t selected);   /* one UI_CHARS wide list line */
void ui_highlight(uint8_t line);                      /* moves the highlight; 0xFF = none */

/* key legend: all six columns in physical left-to-right order: SOURCE MENU DOWN UP AUTO POWER (awto-ddc#85) */
enum ui_ctx { UC_PAGE = 0, UC_ROW, UC_RO, UC_ACTION, UC_EDIT, UC_RUN, UC_KEEP, UC_MAIN, UC_N };
void ui_legend(uint8_t ctx);
void ui_message(const char __xdata *s, uint8_t style);   /* the line above the legend; NULL / "" clears it */

/* status strip: D1 D2 D3 state, active input marked, measured timing; redraws only when something changed */
enum ui_port_state { UPS_NOCABLE = 0, UPS_NOSIGNAL = 1, UPS_READY = 2, UPS_ACTIVE = 3 };
struct ui_timing { uint16_t w, h; uint32_t vmhz; };   /* vmhz = vertical frequency in millihertz */
uint8_t ui_port_state(uint8_t i);                     /* integrator: i = 0..2 = D1..D3 */
uint8_t ui_timing(struct ui_timing __xdata *t);       /* integrator: 1 = the active input's measured timing is valid */
void ui_strip(uint8_t force);
uint8_t ui_fmt_vfreq(char __xdata *dst, uint32_t vmhz);   /* "59.994 Hz" (3 decimals, from the measured timing) */

/* menu copy of the normal SDK font (awto/osd/font.c, generated data) */
void osd_font_load(void);
uint8_t osd_font_glyph(char c);

#endif
