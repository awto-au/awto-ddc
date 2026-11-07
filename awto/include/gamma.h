/* gamma.h: output gamma stage. Curves are generated from the formula in spec gamma section 5.
 * Both calls: main loop only. */
#ifndef AWTO_GAMMA_H
#define AWTO_GAMMA_H

#include <stdint.h>

/* kind 0..3 = gamma 1.8 / 2.0 / 2.2 / 2.4. Loads the curve into all three channel tables.
 * Stage on: sequence per spec gamma section 2 (waits for display-enable stop edges). */
void gamma_load(uint8_t kind);
/* 1 = gamma stage on, 0 = bypass */
void gamma_enable(uint8_t on);

#endif
