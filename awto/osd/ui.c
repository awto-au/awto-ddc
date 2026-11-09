/* ui.c: the awto OSD components (awto/include/ui.h, awto-ddc#89). Everything on screen goes through ui_text / ui_row / the
 * bars below, on the text layer of osd.h. Strings are named __code arrays (bank layout), composed into xdata line buffers. */
#include <stdint.h>
#include "cc.h"
#include "osd.h"
#include "ui.h"

#define W_FRAME   0              /* decoration windows (osd_tc_bar): frame red, inset black, title bar, separators, highlight */
#define W_INSET   1
#define W_TITLE   2
#define W_SEP1    3
#define W_SEP2    4
#define W_HL      5
#define W_UL      6
#define PX_W      (UI_CHARS * OSD_CHAR_W)
#define PX_H      (UI_LINES * OSD_CHAR_H)
#define SLOT      22             /* timing begins after the input name + state */
#define KSLOT     7              /* legend: 6 physical-key columns */

static const char __code us_d1[] = "DisplayPort";
static const char __code us_d2[] = "HDMI 1";
static const char __code us_d3[] = "HDMI 2";
static const char __code us_nocable[] = "no cable";
static const char __code us_nosignal[] = "no signal";
static const char __code us_ready[] = "ready";
static const char __code us_active[] = "ACTIVE";
static const char __code us_hz[] = " Hz";
static const char __code us_k0[] = "SOURCE";
static const char __code us_k1[] = "MENU";
static const char __code us_k2[] = "DOWN";
static const char __code us_k3[] = "UP";
static const char __code us_k4[] = "AUTO";
static const char __code us_k5[] = "POWER";
static const char __code ua_none[] = "";
static const char __code ua_open[] = "open";
static const char __code ua_edit[] = "edit";
static const char __code ua_set[] = "set";
static const char __code ua_run[] = "run";
static const char __code ua_keep[] = "keep";
static const char __code ua_undo[] = "undo";
static const char __code ua_back[] = "back";
static const char __code ua_close[] = "close";
static const char __code ua_cancel[] = "cancel";
static const char __code ua_prev[] = "prev";
static const char __code ua_next[] = "next";
static const char __code ua_less[] = "less";
static const char __code ua_more[] = "more";
static const char __code ua_off[] = "off";

static const char __code *const __code us_port[3] = { us_d1, us_d2, us_d3 };
static const char __code *const __code us_key[6] = { us_k0, us_k1, us_k2, us_k3, us_k4, us_k5 };
static const char __code *const __code us_state[4] = { us_nocable, us_nosignal, us_ready, us_active };
/* action of each key per context (UC_*): SOURCE MENU DOWN UP AUTO POWER */
static const char __code *const __code ua_ctx[UC_N][6] = {
    { ua_none, ua_back, ua_prev, ua_next, ua_open, ua_off },      /* UC_PAGE: cursor on a sub-page */
    { ua_none, ua_back, ua_prev, ua_next, ua_edit, ua_off },      /* UC_ROW */
    { ua_none, ua_back, ua_prev, ua_next, ua_none, ua_off },      /* UC_RO */
    { ua_none, ua_back, ua_prev, ua_next, ua_run, ua_off },       /* UC_ACTION */
    { ua_none, ua_undo, ua_less, ua_more, ua_set, ua_off },       /* UC_EDIT */
    { ua_none, ua_cancel, ua_none, ua_none, ua_run, ua_off },     /* UC_RUN */
    { ua_none, ua_undo, ua_none, ua_none, ua_keep, ua_off },      /* UC_KEEP */
    { ua_none, ua_close, ua_prev, ua_next, ua_open, ua_off },     /* UC_MAIN */
};

uint8_t __xdata ui_hl_style = UI_HL_BAR;
static uint8_t __xdata top_cells[2 * UI_CHARS], bot_cells[2 * UI_CHARS], quad[4];
static char __xdata buf[UI_CHARS + 1];
static uint8_t __xdata hl_line = 0xFF, last_ctx = 0xFF;
static uint8_t __xdata sig[8];

void ui_text(uint8_t line, uint8_t col, const char __xdata *s, uint8_t n, uint8_t style)
{
    uint8_t k, c = 0;

    if (col >= UI_CHARS)
        return;
    if (col + n > UI_CHARS)
        n = UI_CHARS - col;
    for (k = 0; k < n; k++) {
        osd_font_tiles(s[k], quad);
        top_cells[c] = quad[0];
        top_cells[c + 1] = quad[1];
        bot_cells[c] = quad[2];
        bot_cells[c + 1] = quad[3];
        c += 2;
    }
    osd_tc_cells(2 * line, 2 * col, top_cells, c, style);
    osd_tc_cells(2 * line + 1, 2 * col, bot_cells, c, style);
}

static void fill_blank(uint8_t from)
{
    uint8_t k;

    for (k = from; k < UI_CHARS; k++)
        buf[k] = ' ';
    buf[UI_CHARS] = 0;
}

/* copy a __code string into buf at col, n = its length. A macro, not a function: the string lives in the bank of the function that
 * names it, and a helper called from there may run in another bank (banked 8051: it would read the wrong bytes). */
#define PUT_C(n, col, str) \
    do { \
        (n) = 0; \
        while ((str)[(n)] != 0 && (col) + (n) < UI_CHARS) { \
            buf[(col) + (n)] = (str)[(n)]; \
            (n)++; \
        } \
    } while (0)

static uint8_t put_dec(uint8_t col, uint32_t v, uint8_t decimals)
{
    char d[11];
    uint8_t n = 0, k = 0, m = 0;

    do {
        d[n++] = (char)('0' + v % 10);
        v /= 10;
        if (++k == decimals) {
            d[n++] = '.';
        }
    } while (v != 0 || k <= decimals);
    while (n != 0 && col + m < UI_CHARS)
        buf[col + m++] = d[--n];
    return m;
}

uint8_t ui_fmt_vfreq(char __xdata *dst, uint32_t vmhz)
{
    uint8_t n;

    uint8_t m;

    n = put_dec(0, vmhz, 3);
    PUT_C(m, n, us_hz);
    n += m;
    buf[n] = 0;
    for (vmhz = 0; vmhz <= n; vmhz++)
        dst[vmhz] = buf[vmhz];
    return n;
}

static void bars(void)
{
    osd_tc_bar(W_FRAME, 0, 0, PX_W - 1, PX_H - 1, OB_RED);
    osd_tc_bar(W_INSET, 2, 2, PX_W - 3, PX_H - 3, OB_BLACK);
    osd_tc_bar(W_TITLE, 2, 2, PX_W - 3, OSD_CHAR_H - 1, OB_RED);
    osd_tc_bar(W_SEP1, 2, UI_L_LIST * OSD_CHAR_H - 2, PX_W - 3, UI_L_LIST * OSD_CHAR_H - 1, OB_RED);
    osd_tc_bar(W_SEP2, 2, UI_L_MSG * OSD_CHAR_H + OSD_CHAR_H + 4, PX_W - 3, UI_L_MSG * OSD_CHAR_H + OSD_CHAR_H + 5, OB_RED);
}

void ui_open(void)
{
    osd_tc_open(UI_CHARS, UI_LINES);
    osd_font_load();
    bars();
    hl_line = 0xFF;
    last_ctx = 0xFF;
    sig[0] = 0xFF;
}

void ui_show(uint8_t on)
{
    osd_tc_show(on);
}

void ui_close(void)
{
    osd_tc_close();
}

void ui_title(const char __xdata *s)
{
    uint8_t n = 0;

    fill_blank(0);
    while (s[n] != 0 && n < UI_CHARS - 2) {
        buf[1 + n] = s[n];
        n++;
    }
    ui_text(UI_L_TITLE, 0, buf, UI_CHARS, OS_ONRED);
}

void ui_highlight(uint8_t line)
{
    if (line == hl_line)
        return;
    hl_line = line;
    if (line == 0xFF) {
        osd_tc_bar_off(W_HL);
        osd_tc_bar_off(W_UL);
    } else if (ui_hl_style == UI_HL_BAR) {
        osd_tc_bar(W_HL, 2, (uint16_t)line * OSD_CHAR_H, PX_W - 3, (uint16_t)line * OSD_CHAR_H + OSD_CHAR_H - 1, OB_RED);
        osd_tc_bar_off(W_UL);
    } else {
        osd_tc_bar(W_UL, 2, (uint16_t)line * OSD_CHAR_H + OSD_CHAR_H - 3, PX_W - 3, (uint16_t)line * OSD_CHAR_H + OSD_CHAR_H - 2, OB_RED);
        osd_tc_bar_off(W_HL);
    }
}

void ui_row(uint8_t line, const char __xdata *s, uint8_t style, uint8_t selected)
{
    if (selected && ui_hl_style == UI_HL_BAR)
        style = OS_ONRED;
    ui_text(line, 0, s, UI_CHARS, style);
    if (selected && ui_hl_style == UI_HL_MARK) {
        buf[0] = '>';                                    /* xdata is not initialised at start: build the marker */
        ui_text(line, 0, buf, 1, OS_RED);
    }
}

void ui_message(const char __xdata *s, uint8_t style)
{
    uint8_t n = 0;

    fill_blank(0);
    if (s != 0)
        while (s[n] != 0 && n < UI_CHARS - 2) {
            buf[1 + n] = s[n];
            n++;
        }
    ui_text(UI_L_MSG, 0, buf, UI_CHARS, style);
}

void ui_legend(uint8_t ctx)
{
    uint8_t k, n, col, line;
    const char __code *a;

    if (ctx == last_ctx)
        return;
    last_ctx = ctx;
    for (line = 0; line < 2; line++) {
        fill_blank(0);
        ui_text(UI_L_LEGEND + line, 0, buf, UI_CHARS, OS_TEXT);
    }
    for (k = 0; k < 6; k++) {
        col = k * KSLOT;
        fill_blank(0);
        PUT_C(n, 0, us_key[k]);
        ui_text(UI_L_LEGEND, col, buf, n, OS_RED);
        a = ua_ctx[ctx][k];
        if (a[0] != 0) {
            fill_blank(0);
            PUT_C(n, 0, a);
            ui_text(UI_L_LEGEND + 1, col, buf, n, OS_TEXT);
        }
    }
}

/* strip slot i (0..2): "> D2 HDMI ACTIVE"; marker red, name white, state white when active else dim */
static void strip_port(uint8_t line, uint8_t col, uint8_t i, uint8_t st)
{
    uint8_t n;

    fill_blank(0);
    PUT_C(n, 0, us_port[i]);
    ui_text(line, col + 2, buf, 11, OS_TEXT);
    fill_blank(0);
    PUT_C(n, 0, us_state[st]);
    ui_text(line, col + 13, buf, 9, st == UPS_ACTIVE ? OS_TEXT : OS_DIM);
    if (st == UPS_ACTIVE) {
        buf[0] = '>';
        ui_text(line, col, buf, 1, OS_RED);
    } else {
        buf[0] = ' ';
        ui_text(line, col, buf, 1, OS_TEXT);
    }
    (void)n;
}

void ui_strip(uint8_t force)
{
    struct ui_timing __xdata t;
    uint8_t st[3], k, ok, n, timing_line = UI_L_STRIP + 2, chg = force;

    for (k = 0; k < 3; k++)
        st[k] = ui_port_state(k);
    t.w = 0;
    t.h = 0;
    t.vmhz = 0;
    ok = ui_timing(&t);
    if (!ok)
        t.w = t.h = 0;
    if (sig[0] != st[0] || sig[1] != st[1] || sig[2] != st[2] || sig[3] != (uint8_t)t.w || sig[4] != (uint8_t)(t.w >> 8) ||
        sig[5] != (uint8_t)t.h || sig[6] != (uint8_t)(t.h >> 8) || sig[7] != (uint8_t)(t.vmhz / 10))
        chg = 1;
    if (!chg)
        return;
    sig[0] = st[0];
    sig[1] = st[1];
    sig[2] = st[2];
    sig[3] = (uint8_t)t.w;
    sig[4] = (uint8_t)(t.w >> 8);
    sig[5] = (uint8_t)t.h;
    sig[6] = (uint8_t)(t.h >> 8);
    sig[7] = (uint8_t)(t.vmhz / 10);
    for (k = 0; k < 3; k++) {
        strip_port(UI_L_STRIP + k, 0, k, st[k]);
        fill_blank(0);
        ui_text(UI_L_STRIP + k, SLOT, buf, UI_CHARS - SLOT, OS_TEXT);
        if (st[k] == UPS_ACTIVE)
            timing_line = UI_L_STRIP + k;
    }
    if (ok) {
        fill_blank(0);
        n = put_dec(0, t.w, 0);
        buf[n++] = 'x';
        n += put_dec(n, t.h, 0);
        buf[n++] = '@';
        n += put_dec(n, t.vmhz, 3);
        ui_text(timing_line, SLOT, buf, UI_CHARS - SLOT, OS_TEXT);
    }
}
