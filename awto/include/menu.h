/* menu.h: our OSD menu (awto-ddc#67). Pages and items come from the settings registry (settings.h); no per-item code.
 * Keys (front panel): Menu = enter / edit / confirm, Right / Left = move or change, Exit = back / revert. */
#ifndef AWTO_MENU_H
#define AWTO_MENU_H

#include <stdint.h>

enum menu_key { MK_MENU = 0, MK_RIGHT = 1, MK_LEFT = 2, MK_EXIT = 3 };

#define MENU_COLS 40             /* grid: 40 x 18 cells of 12 x 18 px (480 x 324 px, 2x = 960 x 648) */
#define MENU_ROWS 18
#define MENU_LIST 14             /* item lines per screen (rows 2..15), the rest scrolls */

void    menu_open(void);
void    menu_close(void);
uint8_t menu_active(void);
void    menu_key(uint8_t k);     /* one key press (auto-repeat calls it again) */
void    menu_service(void);      /* main loop: timeout, risky countdown redraw */
void    menu_relayout(void);   /* position / size settings changed: place the open menu again */
void    menu_forget(void);       /* the vendor OSD took the screen: drop our state without drawing */
uint8_t menu_state(void);        /* diag: bits 7..6 mode (0 list, 1 edit, 2 confirm), 5..0 page */
uint8_t menu_cursor(void);       /* diag: entry index on the page */

#endif
