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

/* Every bounded wait that expires (tmr_poll, tmr_wait_edge) reports once through this hook before it returns 0:
 * op = TO_POLL (arg = register address) or TO_EDGE (arg = enum tmr_edge), the limit and the elapsed time in ms.
 * The integrator implements it (diag message); host tests record the call. Callers never log timeouts themselves. */
enum tmr_op { TO_POLL = 0, TO_EDGE = 1 };
void tmr_expiry_hook(uint8_t op, uint16_t arg, uint16_t limit_ms, uint16_t elapsed_ms);

/* wait for a video timing edge (spec timer lists them: input vsync, display vsync, enable edges) */
enum tmr_edge { TE_IN_VSYNC = 0, TE_IN_VEND = 1, TE_OUT_VSYNC = 2, TE_OUT_VEND = 3 };
uint8_t  tmr_wait_edge(uint8_t edge);      /* 1 = seen, 0 = timeout (bound in spec) */

#endif
