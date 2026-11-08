/* menu.c: our OSD menu engine (awto/include/menu.h, awto-ddc#67). Walks the generated page tables; one line per
 * entry: label, value. Sub-pages first, then rows. No per-item code. */
#include <stdint.h>
#include "cc.h"
#include "settings.h"
#include "osd.h"
#include "ui.h"
#include "menu.h"

#define MAIN       0xFE           /* virtual top page: every page whose parent is the top */
#define M_LIST     0
#define M_EDIT     1
#define M_RUN      2              /* action: press Menu again to run */
#define LABEL_COL  2
#define VALUE_COL  25
#define VALUE_W    14
#define STRIP_MS   200u           /* status strip refresh: ports change on a seconds scale (cable, link, mode); 5 Hz is live to the eye */

/* UI strings: named arrays (an anonymous literal is a __str_N area, a name the bank layout shares across modules) */
static const char __code mn_s0[] = "AWTO";
static const char __code mn_s1[] = "Settings";
static const char __code mn_s2[] = "> ";
static const char __code mn_s3[] = "AWTO >";
static const char __code mn_s4[] = " > ";
static const char __code mn_s5[] = " >";
static const char __code mn_s6[] = "Keep the new value";
static const char __code mn_s7[] = "Press MENU again to run";
static const char __code mn_s8[] = "Recovery: all settings at defaults";
static const char __code mn_s9[] = "* stored only: no effect yet";
static const char __code mn_s10[] = "read only";
static const char __code mn_s11[] = "takes effect after a restart";
static const char __code mn_s12[] = "reverts after 15 s unless kept";

static uint8_t __xdata active, mode, page, cursor, top, secs, last_left;
static uint16_t __xdata sec_t, strip_t;
static int16_t __xdata edit_v, edit_old;
static struct setting __xdata row;
static char __xdata line[MENU_COLS + 1];
static char __xdata tmp[24];
static uint16_t __xdata redraws;
static uint8_t __xdata last_key = 0xFF;
struct menu_diag __xdata menu_diag;

static void mn_sync(void);

static void mn_row(uint8_t r, const char __xdata *s, uint8_t style, uint8_t sel)
{
    redraws++;
    ui_row(r, s, style, sel);
}

static uint8_t mn_n_entries(void)
{
    uint8_t p, n = 0;

    if (page != MAIN)
        return set_page_n(page);
    for (p = 0; p < SET_PAGES; p++)
        n += set_page_parent(p) == 0xFF;
    return n;
}

static uint8_t mn_entry(uint8_t k)
{
    uint8_t p;

    if (page != MAIN)
        return set_page_entry(page, k);
    for (p = 0; p < SET_PAGES; p++)
        if (set_page_parent(p) == 0xFF && k-- == 0)
            return 0x80 | p;
    return 0x80;
}

static void mn_blank(void)
{
    uint8_t k;

    for (k = 0; k < MENU_COLS; k++)
        line[k] = ' ';
    line[MENU_COLS] = 0;
}

static uint8_t mn_put(uint8_t col, const char __xdata *s, uint8_t max)
{
    uint8_t n = 0;

    while (s[n] != 0 && n < max && col + n < MENU_COLS) {
        line[col + n] = s[n];
        n++;
    }
    return n;
}

static void mn_put_c(uint8_t col, const char __code *s)
{
    while (*s != 0 && col < MENU_COLS)
        line[col++] = *s++;
}

static uint8_t mn_num(char __xdata *d, int16_t v, uint8_t dec)
{
    char __xdata *p = tmp + sizeof tmp - 1;
    uint16_t u = v < 0 ? (uint16_t)-v : (uint16_t)v;
    uint8_t n = 0, k = 0;

    *p = 0;
    do {
        *--p = (char)('0' + u % 10);
        u /= 10;
        if (++k == dec)
            *--p = '.';
    } while (u != 0 || k <= dec);
    if (v < 0)
        *--p = '-';
    while (p[n] != 0) {
        d[n] = p[n];
        n++;
    }
    d[n] = 0;
    return n;
}

/* value text of row (loaded in `row`) into buf */
static void mn_value_text(char __xdata *buf, int16_t v)
{
    uint8_t n;

    buf[0] = 0;
    if (row.type == STY_ACTION) {
        buf[0] = '.'; buf[1] = '.'; buf[2] = '.'; buf[3] = 0;
        return;
    }
    if (row.type == STY_BOOL) {
        buf[0] = 'O';
        buf[1] = v ? 'n' : 'f';
        buf[2] = v ? 0 : 'f';
        buf[3] = 0;
        return;
    }
    if (row.type == STY_ENUM && row.opts != 0xFFFF) {
        set_text(set_opt(row.opts, (uint8_t)(v - row.min)), buf, VALUE_W + 1);
        return;
    }
    if (row.id == SET_ID_INFO_VFREQ) {                   /* measured timing: 3 decimals */
        struct ui_timing __xdata t;

        if (ui_timing(&t) && t.vmhz != 0) {
            ui_fmt_vfreq(buf, t.vmhz);
            return;
        }
    }
    n = mn_num(buf, v, row.unit == SU_DHZ ? 1 : 0);
    switch (row.unit) {
    case SU_PERCENT: buf[n++] = '%'; break;
    case SU_MS: buf[n++] = ' '; buf[n++] = 'm'; buf[n++] = 's'; break;
    case SU_S: buf[n++] = ' '; buf[n++] = 's'; break;
    case SU_HZ: case SU_DHZ: buf[n++] = ' '; buf[n++] = 'H'; buf[n++] = 'z'; break;
    default: break;
    }
    buf[n] = 0;
}

static void mn_draw_title(void)
{
    uint8_t n;

    mn_blank();
    mn_put_c(0, mn_s0);
    if (page == MAIN) {
        mn_put_c(5, mn_s1);
    } else {
        mn_put_c(5, mn_s2);
        set_page_title(page, tmp, sizeof tmp);
        mn_put(7, tmp, 30);
    }
    if (page != MAIN && set_page_parent(page) != 0xFF) {
        n = set_page_title(set_page_parent(page), tmp, sizeof tmp);
        (void)n;
        mn_blank();
        mn_put_c(0, mn_s3);
        n = mn_put(7, tmp, 14);
        mn_put_c(7 + n, mn_s4);
        set_page_title(page, tmp, sizeof tmp);
        mn_put(10 + n, tmp, 28 - n);
    }
    redraws++;
    ui_title(line);
}

static void mn_draw_entry(uint8_t k)
{
    uint8_t e, sel = (k == cursor), style = OS_TEXT, n;
    int16_t v;

    mn_blank();
    if (k < mn_n_entries()) {
        e = mn_entry(k);
        if (e & 0x80) {
            set_page_title(e & 0x7F, tmp, sizeof tmp);
            n = mn_put(LABEL_COL, tmp, 22);
            mn_put_c(LABEL_COL + n, mn_s5);
        } else {
            set_row(e, &row);
            set_text(row.label, tmp, sizeof tmp);
            mn_put(LABEL_COL, tmp, 22);
            v = (sel && mode == M_EDIT) ? edit_v : set_get(row.id);
            mn_value_text(tmp, v);
            n = mn_put(VALUE_COL, tmp, VALUE_W);
            if (sel && mode == M_EDIT) {
                line[VALUE_COL - 1] = '<';
                line[VALUE_COL + n] = '>';
            }
            if (row.flags & SF_INERT)
                line[MENU_COLS - 1] = '*';
        }
    }
    if (k == top && top > 0)
        line[MENU_COLS - 1] = '^';
    if (k == top + MENU_LIST - 1 && k + 1 < mn_n_entries())
        line[MENU_COLS - 1] = 'v';
    if (k < mn_n_entries() && !(mn_entry(k) & 0x80) && (row.flags & SF_INERT))
        style = OS_DIM;
    if (sel && mode == M_EDIT && ui_hl_style == UI_HL_MARK)
        style = OS_RED;
    if (sel)
        ui_highlight(UI_L_LIST + k - top);
    mn_row(UI_L_LIST + k - top, line, style, sel && k < mn_n_entries());
}

static void mn_draw_status(void)
{
    uint8_t e, warn = 0, ctx = UC_PAGE;
    uint16_t left = set_pending_left();
    const char __code *m = 0;

    if (set_pending() != 0) {
        m = mn_s6;
        warn = 1;
        ctx = UC_KEEP;
    } else if (mode == M_RUN) {
        m = mn_s7;
        warn = 1;
        ctx = UC_RUN;
    } else if (set_load_result() == 2) {
        m = mn_s8;
        warn = 1;
    }
    if (mode == M_EDIT)
        ctx = UC_EDIT;
    else if (mn_n_entries() != 0 && page == MAIN)
        ctx = UC_MAIN;
    if (m == 0 && mode == M_LIST && mn_n_entries() != 0 && !((e = mn_entry(cursor)) & 0x80)) {
        set_row(e, &row);
        ctx = row.type == STY_ACTION ? UC_ACTION : (row.flags & SF_RO) ? UC_RO : UC_ROW;
        if (row.flags & SF_INERT)
            m = mn_s9;
        else if (row.flags & SF_RO)
            m = mn_s10;
        else if (row.flags & SF_REBOOT)
            m = mn_s11;
        else if (row.flags & SF_RISKY)
            m = mn_s12;
    }
    mn_blank();
    if (m != 0)
        mn_put_c(0, m);
    if (set_pending() != 0) {
        line[MENU_COLS - 3] = (char)('0' + (left / 1000) / 10);
        line[MENU_COLS - 2] = (char)('0' + (left / 1000) % 10);
        line[MENU_COLS - 1] = 's';
    }
    redraws++;
    ui_message(line, warn ? OS_RED : OS_DIM);
    ui_legend(ctx);
    last_left = (uint8_t)(left / 1000);
}

static void mn_draw_list(void)
{
    uint8_t k;

    for (k = top; k < top + MENU_LIST; k++)
        mn_draw_entry(k);
}

static void mn_draw_all(void)
{
    mn_draw_title();
    ui_strip(1);
    mn_draw_list();
    mn_draw_status();
}

static void mn_scroll(void)
{
    uint8_t old = top;

    if (cursor < top)
        top = cursor;
    if (cursor >= top + MENU_LIST)
        top = cursor - MENU_LIST + 1;
    if (old != top)
        mn_draw_list();
}

static void mn_go(uint8_t p, uint8_t c)
{
    page = p;
    cursor = c;
    top = 0;
    mode = M_LIST;
    mn_scroll();
    mn_draw_all();
}

void menu_relayout(void)
{
    if (active)
        osd_tc_place((uint8_t)set_get(SET_ID_OSD_HPOS), (uint8_t)set_get(SET_ID_OSD_VPOS),
                     (uint8_t)set_get(SET_ID_OSD_SCALE));
}

void menu_open(void)
{
    ui_open();
    active = 1;
    menu_relayout();
    secs = 0;
    sec_t = set_now_ms();
    mn_go(MAIN, 0);
    ui_show(1);
    mn_sync();
}

void menu_close(void)
{
    if (!active)
        return;
    if (mode == M_EDIT)
        set_put(row.id, edit_old, 1);
    active = 0;
    set_save_now();
    ui_close();
    mn_sync();
}

void menu_forget(void)
{
    active = 0;
    mn_sync();
}

uint8_t menu_active(void)
{
    return active;
}

uint8_t menu_state(void)
{
    return (uint8_t)(mode << 6 | (page & 0x3F));
}

uint8_t menu_cursor(void)
{
    return cursor;
}

static void mn_move(int8_t d)
{
    uint8_t n = mn_n_entries(), old = cursor;

    if (n == 0)
        return;
    cursor = d > 0 ? (cursor + 1 >= n ? 0 : cursor + 1) : (cursor == 0 ? n - 1 : cursor - 1);
    mn_scroll();
    ui_highlight(UI_L_LIST + cursor - top);              /* the bar first: the rows below draw onto it */
    if (old >= top && old < top + MENU_LIST)
        mn_draw_entry(old);
    mn_draw_entry(cursor);
    mn_draw_status();
}

static void mn_change(int8_t d)
{
    int16_t v = edit_v + (d > 0 ? row.step : -row.step);

    if (row.type == STY_BOOL)
        v = !edit_v;
    else if (row.type == STY_ENUM && v > row.max)
        v = row.min;                                     /* option lists wrap */
    else if (row.type == STY_ENUM && v < row.min)
        v = row.max;
    if (v < row.min)
        v = row.min;
    if (v > row.max)
        v = row.max;
    edit_v = v;
    if (row.flags & SF_LIVE)
        set_put(row.id, v, 0);
    mn_draw_entry(cursor);
}

static void mn_enter(void)
{
    uint8_t e = mn_entry(cursor);

    if (e & 0x80) {
        mn_go(e & 0x7F, 0);
        return;
    }
    set_row(e, &row);
    if (row.flags & SF_RO)
        return;
    if (row.type == STY_ACTION) {
        mode = M_RUN;
        mn_draw_status();
        return;
    }
    edit_v = edit_old = set_get(row.id);
    mode = M_EDIT;
    mn_draw_entry(cursor);
    mn_draw_status();
}

static void mn_back(void)
{
    uint8_t p = page, up, k, n;

    if (page == MAIN) {
        menu_close();
        return;
    }
    up = set_page_parent(page);
    page = (up == 0xFF) ? MAIN : up;
    n = mn_n_entries();
    for (k = 0; k < n && mn_entry(k) != (0x80 | p); k++)
        ;
    mn_go(page, k < n ? k : 0);
}

/* fill menu_diag from the engine state (after every key, command and service pass that drew) */
static void mn_sync(void)
{
    uint8_t e = 0;
    int16_t v = 0;

    menu_diag.seq++;                             /* odd: update in progress */
    menu_diag.magic = 'M';
    menu_diag.version = 1;
    menu_diag.open = active;
    menu_diag.page = page;
    menu_diag.cursor = cursor;
    menu_diag.item_id = 0;
    menu_diag.item_page = 0xFF;
    menu_diag.n = active ? mn_n_entries() : 0;
    if (active && cursor < menu_diag.n) {
        e = mn_entry(cursor);
        if (e & 0x80) {
            menu_diag.item_page = e & 0x7F;
        } else {
            set_row(e, &row);
            menu_diag.item_id = row.id;
            v = (mode == M_EDIT) ? edit_v : set_get(row.id);
        }
    }
    menu_diag.mode = mode;
    menu_diag.top = top;
    menu_diag.val_lo = (uint8_t)v;
    menu_diag.val_hi = (uint8_t)((uint16_t)v >> 8);
    menu_diag.redraw_lo = (uint8_t)redraws;
    menu_diag.redraw_hi = (uint8_t)(redraws >> 8);
    menu_diag.last_key = last_key;
    menu_diag.pending = set_pending();
    menu_diag.parent = (page == MAIN) ? 0xFF : set_page_parent(page);
    menu_diag.seq++;
}

static void mn_key(uint8_t k);

void menu_key(uint8_t k)
{
    last_key = k;
    mn_key(k);
    mn_sync();
}

uint8_t menu_cmd(uint8_t op, uint16_t arg)
{
    uint8_t k, n, ok = 1;

    secs = 0;                                    /* a host command is activity: the menu timeout restarts */
    sec_t = set_now_ms();
    switch (op) {
    case MO_KEY:
        key_inject((uint8_t)arg);            /* through the firmware key path, like a front key */
        break;
    case MO_HOLD:
        key_hold((uint8_t)(arg & 0x1F), (uint16_t)(arg >> 5) * 50u);
        break;
    case MO_OPEN:
        if ((uint8_t)arg != MAIN && (uint8_t)arg >= SET_PAGES) {
            ok = 0;
            break;
        }
        if (!active)
            menu_open();
        mn_go((uint8_t)arg, 0);
        break;
    case MO_SELECT:
        ok = 0;
        if (!active)
            break;
        n = mn_n_entries();
        for (k = 0; k < n && !ok; k++) {
            uint8_t e = mn_entry(k);
            if (arg & 0x80) {
                ok = (e == (uint8_t)arg);
            } else if (!(e & 0x80)) {
                set_row(e, &row);
                ok = (row.id == (uint8_t)arg);
            }
            if (ok) {
                mode = M_LIST;
                cursor = k;
                mn_scroll();
                mn_draw_list();
                mn_draw_status();
            }
        }
        break;
    case MO_SET:
        ok = 0;
        if (!active || mn_n_entries() == 0 || (mn_entry(cursor) & 0x80))
            break;
        set_row(mn_entry(cursor), &row);
        mode = M_LIST;
        ok = set_put(row.id, (int16_t)arg, 1);
        mn_draw_entry(cursor);
        mn_draw_status();
        break;
    case MO_BACK:
        if (active)
            mn_back();
        break;
    case MO_CLOSE:
        menu_close();
        break;
    case MO_ENTER:
        if (active)
            mn_key(MK_MENU);
        break;
    default:
        ok = 0;
        break;
    }
    if (op != MO_KEY)                            /* a key syncs when menu_key consumes it: seq moving = key handled */
        mn_sync();
    return ok;
}

static void mn_key(uint8_t k)
{
    uint8_t e;

    if (!active)
        return;
    secs = 0;
    sec_t = set_now_ms();
    if (set_pending() != 0 && mode == M_LIST && (k == MK_MENU || k == MK_EXIT)) {
        if (k == MK_MENU)
            set_confirm();
        else
            set_revert();
        mn_draw_list();
        mn_draw_status();
        return;
    }
    if (mode == M_EDIT) {
        switch (k) {
        case MK_RIGHT: mn_change(1); break;
        case MK_LEFT: mn_change(-1); break;
        case MK_MENU:
            mode = M_LIST;
            set_put(row.id, edit_v, 1);
            mn_draw_entry(cursor);
            mn_draw_status();
            break;
        default:
            mode = M_LIST;
            if (set_get(row.id) != edit_old)
                set_put(row.id, edit_old, 1);
            mn_draw_entry(cursor);
            mn_draw_status();
            break;
        }
        return;
    }
    if (mode == M_RUN) {
        mode = M_LIST;
        e = mn_entry(cursor);
        set_row(e, &row);
        mn_draw_status();
        if (k == MK_MENU)
            set_action(row.id);                  /* may close the menu (vendor / factory menu) */
        return;
    }
    switch (k) {
    case MK_RIGHT: mn_move(1); break;
    case MK_LEFT: mn_move(-1); break;
    case MK_MENU: mn_enter(); break;
    default: mn_back(); break;
    }
}

void menu_service(void)
{
    uint16_t now, to;

    if (!active)
        return;
    now = set_now_ms();
    if ((uint16_t)(now - strip_t) >= STRIP_MS) {
        strip_t = now;
        ui_strip(0);                                     /* live inputs; redraws only on a change */
    }
    if ((uint16_t)(now - sec_t) >= 1000u) {
        sec_t += 1000u;
        if (secs < 255)
            secs++;
        to = (uint16_t)set_get(SET_ID_OSD_TIMEOUT);
        if (to != 0 && secs >= to && set_pending() == 0 && mode != M_EDIT) {
            menu_close();
            return;
        }
    }
    if (set_pending() != 0 && (uint8_t)(set_pending_left() / 1000) != last_left) {
        mn_draw_status();                           /* countdown, once a second */
        mn_sync();
    } else if (set_pending() == 0 && last_left != 0) {
        mn_draw_list();                             /* auto-revert happened: show the old value again */
        mn_draw_status();
        mn_sync();
    }
}
