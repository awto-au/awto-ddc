/* nvram.h: settings records in SPI flash, plus raw flash access.
 * DRAFT interface (wave A); spec nvram (step 6) refines it. Record layout and wear policy are ours. */
#ifndef AWTO_NVRAM_H
#define AWTO_NVRAM_H

#include <stdint.h>

/* The settings record (layout GENERATED from the settings registry, settings.h): header {set_schema, length, check},
 * then each SF_NV row at its nv_slot. Schema or check mismatch -> nv_load returns 0 and set_load applies defaults. */
#define NV_REC_SETTINGS 0

/* records: small fixed-size structs, each with our version byte and check value */
uint8_t nv_load(uint8_t rec, void *dst, uint8_t len);     /* 1 = valid copy found; 0 = caller applies defaults */
void    nv_store(uint8_t rec, const void *src, uint8_t len);   /* queued; written by nv_service */
void    nv_service(void);                                 /* main loop: writes queued records */
void    nv_wipe(void);                                    /* factory reset: all records invalid */

/* raw flash (24-bit addresses). Erase unit and timings per spec nvram. 1 = ok */
uint8_t fl_read(uint32_t a, uint8_t *dst, uint16_t n);
uint8_t fl_write(uint32_t a, const uint8_t *src, uint16_t n);  /* within one page */
uint8_t fl_erase(uint32_t sector_a);

#endif
