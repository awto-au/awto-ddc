/* arith.h: 32-bit scaled arithmetic used by timing/clock maths. Exact results are defined in spec arith;
 * callers depend on them bit for bit (register values are computed from them). */
#ifndef AWTO_ARITH_H
#define AWTO_ARITH_H

#include <stdint.h>

/* a * b / c with a 64-bit intermediate; rounding per spec arith (two regimes) */
uint32_t ar_muldiv(uint32_t a, uint32_t b, uint32_t c);
/* a * 2^k / c, rounded half up; k = 0..32 */
uint32_t ar_shldiv(uint32_t a, uint8_t k, uint32_t c);

#endif
