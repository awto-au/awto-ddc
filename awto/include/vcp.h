/* vcp.h: DDC/CI VCP get/set on the settings registry (MCCS codes from the rows, plus our manufacturer pair).
 * 0xE0 = row id select (read: selected id, max 255), 0xE1 = value of the selected row (read: current + max),
 * 0xE2 = settings schema (read only), 0xE3 = write 1 confirm a pending risky value, 2 save now, 3 defaults. */
#ifndef AWTO_VCP_H
#define AWTO_VCP_H

#include <stdint.h>
#include "cc.h"

#define VCP_SEL     0xE0
#define VCP_VAL     0xE1
#define VCP_SCHEMA  0xE2
#define VCP_CMD     0xE3
#define VCP_RESET   0x04         /* MCCS restore factory defaults */

/* 1 = code handled; cur / max filled for a get, type 0 = set parameter, 1 = momentary */
uint8_t vcp_get(uint8_t code, uint16_t __xdata *cur, uint16_t __xdata *max, uint8_t __xdata *type);
uint8_t vcp_set(uint8_t code, uint16_t v);
void    vcp_box_service(void);   /* main loop: host mailbox _vcp_box (debug link), same get/set as DDC/CI */

#endif
