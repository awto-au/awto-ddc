/* arith.c: 32-bit scaled multiply/divide with round-half-up. Spec: arith section 2.
 * Domain 1 <= c <= 2^31; outside it results are arbitrary but the calls return. */
#include <stdint.h>
#include "arith.h"

/* (r:n) / c, 32 restoring steps; requires r < c so the quotient fits 32 bits */
static uint32_t ldiv32(uint32_t r, uint32_t n, uint32_t c, uint32_t *rem)
{
    uint32_t q = 0;
    uint8_t i;
    for (i = 0; i < 32; i++) {
        uint8_t top = (uint8_t)(n >> 31);
        n <<= 1;
        r = (r << 1) | top;
        q <<= 1;
        if (r >= c) {
            r -= c;
            q |= 1;
        }
    }
    *rem = r;
    return q;
}

/* round half up of (hi:lo) / c mod 2^32: the high word's quotient is 2^32 multiples, dropped */
static uint32_t rdiv64(uint32_t hi, uint32_t lo, uint32_t c)
{
    uint32_t rem;
    uint32_t q = ldiv32(hi % c, lo, c, &rem);
    return q + ((2 * rem >= c) ? 1 : 0);
}

static void mul64(uint32_t a, uint32_t b, uint32_t *hi, uint32_t *lo)
{
    uint32_t p00 = (uint32_t)(uint16_t)a * (uint16_t)b;
    uint32_t p01 = (uint32_t)(uint16_t)a * (uint16_t)(b >> 16);
    uint32_t p10 = (uint32_t)(uint16_t)(a >> 16) * (uint16_t)b;
    uint32_t p11 = (uint32_t)(uint16_t)(a >> 16) * (uint16_t)(b >> 16);
    uint32_t mid = (p00 >> 16) + (p01 & 0xFFFF) + (p10 & 0xFFFF);

    *lo = (p00 & 0xFFFF) | (mid << 16);
    *hi = p11 + (p01 >> 16) + (p10 >> 16) + (mid >> 16);
}

uint32_t ar_shldiv(uint32_t a, uint8_t k, uint32_t c)
{
    if (c == 0)
        return 0;
    if (k == 0)
        return rdiv64(0, a, c);
    if (k < 32)
        return rdiv64(a >> (32 - k), a << k, c);
    return rdiv64(a, 0, c);
}

uint32_t ar_muldiv(uint32_t a, uint32_t b, uint32_t c)
{
    uint32_t hi, lo;

    if (c == 0)
        return 0;
    /* fast regime: a * b fits in 32 bits (boundary a = floor((2^32-1)/b) is slow) */
    if (a == 0 || b == 0 || a < 0xFFFFFFFFUL / b)
        return (a * b) / c;
    mul64(a, b, &hi, &lo);
    return rdiv64(hi, 0, c) + rdiv64(0, lo, c);
}
