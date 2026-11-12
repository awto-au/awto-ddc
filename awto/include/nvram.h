/* nvram.h: settings records in SPI flash, plus raw flash access.
 * DRAFT interface (wave A); spec nvram (step 6) refines it. Record layout and wear policy are ours (awto-ddc#67). */
#ifndef AWTO_NVRAM_H
#define AWTO_NVRAM_H

#include <stdint.h>
#include "cc.h"

/* The settings record (settings.c): {schema u16, n, n x (id, value lo, value hi)}. Id-tagged, so a firmware update
 * keeps every value whose row still exists and is in range; a schema change alone loses nothing. */
#define NV_REC_SETTINGS 0
#define NV_PAYLOAD_MAX  500u     /* bytes per record (slot 512 B less the 12 B header) */

/* records: nvram.c keeps a log of slots in two flash sectors; the newest valid slot wins. 1 = ok */
uint16_t nv_load(uint8_t rec, uint8_t __xdata *dst, uint16_t max);   /* payload length, 0 = no valid copy */
uint16_t nv_find(uint8_t rec);                             /* same check, no buffer: payload length; then nv_read_at */
uint8_t  nv_read_at(uint16_t off, uint8_t __xdata *dst, uint16_t n);   /* payload bytes of the slot nv_find chose */
uint8_t  nv_store(uint8_t rec, const uint8_t __xdata *src, uint16_t len);   /* writes now (callers debounce) */
void     nv_wipe(void);                                    /* factory reset: all records invalid */
uint16_t nv_seq(void);                                     /* sequence number of the newest slot (diag) */

/* raw flash (24-bit addresses), integrator. Erase unit 4 KiB. 1 = ok */
uint8_t fl_read(uint32_t a, uint8_t __xdata *dst, uint16_t n);
uint8_t fl_write(uint32_t a, const uint8_t __xdata *src, uint16_t n);  /* within one 256 B page */
uint8_t fl_erase(uint32_t sector_a);

#endif
