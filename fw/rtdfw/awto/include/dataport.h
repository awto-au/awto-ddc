/* dataport.h: indexed register ports (index register at `port`, data register at `port + 1`).
 * Index constants come from facts (P<pp>_<aa>_I<idx>). Spec: dataport (helpers wave). */
#ifndef AWTO_DATAPORT_H
#define AWTO_DATAPORT_H

#include <stdint.h>

/* index stepping for multi-byte transfers */
#define DP_SW_STEP 1   /* index idx + i written before byte i */
#define DP_HW_STEP 0   /* index idx written before every byte (port advances by itself or is a FIFO) */

void     dp_wr(uint16_t port, uint8_t idx, uint8_t v);
uint8_t  dp_rd(uint16_t port, uint8_t idx);
/* new = (old & keep) | set; the index is written again before the data write */
void     dp_rmw(uint16_t port, uint8_t idx, uint8_t keep, uint8_t set);
uint8_t  dp_test(uint16_t port, uint8_t idx, uint8_t mask);

/* big-endian values over consecutive indices: high byte at idx */
void     dp_wr16(uint16_t port, uint8_t idx, uint16_t v);
uint16_t dp_rd16(uint16_t port, uint8_t idx, uint8_t step);
void     dp_rd_n(uint16_t port, uint8_t idx, uint8_t *dst, uint16_t n, uint8_t step);

#endif
