/* menu.h: our OSD menu (awto-ddc#67). Pages and items come from the settings registry (settings.h); no per-item code.
 * menu_key (MK_*): MK_MENU enter / edit / confirm (front AUTO), MK_RIGHT / MK_LEFT move or change (UP / DOWN),
 * MK_EXIT back / revert (front MENU). Front SOURCE: the integrator calls menu_close (awto-ddc#132). */
#ifndef AWTO_MENU_H
#define AWTO_MENU_H

#include <stdint.h>

enum menu_key { MK_MENU = 0, MK_RIGHT = 1, MK_LEFT = 2, MK_EXIT = 3 };

#define MENU_COLS 40             /* grid: 40 x 20 characters of 16 x 36 presented px (640 x 720 at 2x), see ui.h */
#define MENU_ROWS 20
#define MENU_LIST 14             /* item lines per screen (lines 3..16), the rest scrolls */

void    menu_open(void);
void    menu_close(void);
uint8_t menu_active(void);
void    menu_key(uint8_t k);     /* one key press (auto-repeat calls it again) */
void    menu_service(void);      /* main loop: timeout, risky countdown redraw */
void    menu_relayout(void);   /* position / size settings changed: place the open menu again */
void    menu_forget(void);       /* the vendor OSD took the screen: drop our state without drawing */
uint8_t menu_state(void);        /* diag: bits 7..6 mode (0 list, 1 edit, 2 confirm), 5..0 page */
uint8_t menu_cursor(void);       /* diag: entry index on the page */

/* Host instrumentation (awto-ddc#67): state struct at map symbol _menu_diag, fixed byte offsets, little-endian words.
 * Pages are settings/pages.tsv indices (MENU_MAIN = the top list), items are registry ids. */
#define MENU_MAIN 0xFE
struct menu_diag {
    uint8_t magic;               /* 0  'M' */
    uint8_t version;             /* 1  1 */
    uint8_t open;                /* 2  1 = our menu on screen */
    uint8_t page;                /* 3  page index, MENU_MAIN = top list */
    uint8_t cursor;              /* 4  entry index on the page */
    uint8_t item_id;             /* 5  registry id of the row under the cursor, 0 = a sub-page entry */
    uint8_t item_page;           /* 6  page index of the sub-page entry under the cursor, 0xFF = a row */
    uint8_t mode;                /* 7  0 list, 1 edit, 2 action armed */
    uint8_t top;                 /* 8  first entry on screen (scroll) */
    uint8_t val_lo, val_hi;      /* 9  value shown on the cursor row (the edited value in edit mode) */
    uint8_t redraw_lo, redraw_hi;/* 11 +1 per drawn line (any redraw) */
    uint8_t last_key;            /* 13 last menu key, 0xFF = none */
    uint8_t pending;             /* 14 risky row id waiting for a confirm, 0 = none */
    uint8_t n;                   /* 15 entries on the page */
    uint8_t parent;              /* 16 parent page, 0xFF = top */
    uint8_t seq;                 /* 17 +1 before and after each update: odd = being written, re-read (host reads are async) */
};
extern struct menu_diag __xdata menu_diag;

/* direct commands (host mailbox / VCP 0xE4). 1 = done */
#define MO_SELECT_PAGE 0x100u   /* MO_SELECT arg: bit 8 = a page entry (0x100 | 0x80 | page); else a row id 0..255 */
enum menu_op { MO_KEY = 1, MO_OPEN = 2, MO_SELECT = 3, MO_SET = 4, MO_BACK = 5, MO_CLOSE = 6, MO_ENTER = 7, MO_HOLD = 8 };
/* KEY k (MK_*); OPEN page (MENU_MAIN = top); SELECT registry id, or MO_SELECT_PAGE | 0x80 | page for a sub-page entry; SET value of
 * the cursor row (applied, risky rows pending as from the keys); BACK; CLOSE; ENTER (= Menu on the cursor);
 * HOLD: arg = (ms / 50) << 5 | key mask (firmware key bits: 0x01 power, 0x02 menu, 0x04 right, 0x08 left, 0x10 exit) */
uint8_t menu_cmd(uint8_t op, uint16_t arg);

/* integrator: front-key injection through the firmware's own key path */
void key_inject(uint8_t k);                  /* one key message (menu_key numbering) */
void key_hold(uint8_t mask, uint16_t ms);    /* raw key mask held for ms (long press, combinations) */

#endif
