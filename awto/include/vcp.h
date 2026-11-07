/* vcp.h: DDC/CI VCP get/set on the settings registry (MCCS codes from the rows, plus our manufacturer pair).
 * 0xE0 = row id select (read: selected id, max 255), 0xE1 = value of the selected row (read: current + max),
 * 0xE2 = settings schema (read only), 0xE3 = write 1 confirm a pending risky value, 2 save now, 3 defaults,
 * 0xE4 / 0xE5 = menu command and state (below). */
#ifndef AWTO_VCP_H
#define AWTO_VCP_H

#include <stdint.h>
#include "cc.h"

#define VCP_SEL     0xE0
#define VCP_VAL     0xE1
#define VCP_SCHEMA  0xE2
#define VCP_CMD     0xE3
#define VCP_MENU    0xE4         /* write: menu command op << 8 | arg (menu.h); read: page << 8 | open */
#define VCP_ITEM    0xE5         /* read: mode << 8 | registry id under the cursor */
#define VCP_RESET   0x04         /* MCCS restore factory defaults */
#define VCP_NEWCTL  0x02         /* MCCS new control value: always 1 (no host-pending changes reported) */
#define VCP_CTRL    0xC8         /* MCCS display controller type: 0x09 = Realtek in the MCCS 2.2 table (public standard) */
#define VCP_FWLVL   0xC9         /* MCCS display firmware level, SH.SL */
#define VCP_VERSION 0xDF         /* MCCS VCP version: 2.2 */
#define VCP_FW_LEVEL 0x0100u     /* our firmware level 1.0 (derived: first registry firmware, awto-ddc#67) */

/* 1 = code handled; cur / max filled for a get, type 0 = set parameter, 1 = momentary */
uint8_t vcp_get(uint8_t code, uint16_t __xdata *cur, uint16_t __xdata *max, uint8_t __xdata *type);
uint8_t vcp_set(uint8_t code, uint16_t v);
void    vcp_box_service(void);   /* main loop: host mailbox _vcp_box (debug link), same get/set as DDC/CI */

#endif
