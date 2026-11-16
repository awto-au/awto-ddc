/* event.h: one-shot timed events serviced from the main loop.
 * DRAFT interface (wave A). Ids are owned by the system layer (one enum per user, ranges in spec event). */
#ifndef AWTO_EVENT_H
#define AWTO_EVENT_H

#include <stdint.h>

typedef uint8_t evt_t;

void    evt_init(void);
void    evt_arm(evt_t id, uint16_t ms);    /* (re)arm: a pending id is replaced, not duplicated */
void    evt_drop(evt_t id);                /* no-op when not pending */
uint8_t evt_armed(evt_t id);
void    evt_service(void);                 /* main loop: calls evt_fire() once per expired id, oldest first */

/* provided by the system layer */
extern void evt_fire(evt_t id);

#endif
