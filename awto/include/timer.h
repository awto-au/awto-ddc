/* timer.h: millisecond time base, delays and bounded register polls.
 * DRAFT interface (wave A): the timer spec owner may refine it; changes go through the process owner. */
#ifndef AWTO_TIMER_H
#define AWTO_TIMER_H

#include <stdint.h>

void     tmr_init(void);
uint16_t tmr_now(void);                    /* free-running ms count, wraps at 2^16 */
void     tmr_wait_ms(uint16_t ms);         /* returns after >= ms (spec gives the resolution) */
void     tmr_wait_us(uint16_t us);         /* calibrated busy wait, >= us */

/* poll until (reg & mask) == want, or limit_ms passes. 1 = condition met, 0 = expired (caller logs) */
uint8_t  tmr_poll(uint16_t reg, uint8_t mask, uint8_t want, uint16_t limit_ms);

/* wait for a video timing edge (spec timer lists them: input vsync, display vsync, enable edges) */
enum tmr_edge { TE_IN_VSYNC = 0, TE_IN_VEND = 1, TE_OUT_VSYNC = 2, TE_OUT_VEND = 3 };
uint8_t  tmr_wait_edge(uint8_t edge);      /* 1 = seen, 0 = timeout (bound in spec) */

#endif
