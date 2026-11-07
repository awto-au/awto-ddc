/* arith.c: 32-bit scaled multiply/divide with round-half-up. Spec: arith section 2.
 * Domain 1 <= c <= 2^31; outside it results are arbitrary but the calls return. */
#include <stdint.h>
#include "cc.h"
#include "arith.h"

/* working set in internal RAM: XDATA 32-bit ops cost 30-60 B each (spec arith section 5). Not reentrant. */
static __data uint32_t w_n, w_q, w_r, w_c, w_a, w_b, w_hi, w_lo;

/* R(x, k, c): long division of x * 2^k (32 + k bits, MSB first) by c.
 * Quotient kept mod 2^32; remainder r < c <= 2^31 keeps 2r + 1 < 2^32. */
static uint32_t rnd_shl(uint32_t x, uint8_t k, uint32_t c)
{
    uint16_t j;

    w_n = x;
    w_c = c;
    w_q = 0;
    w_r = 0;
    for (j = 0; j < 32 + (uint16_t)k; j++) {
        uint8_t bit = (uint8_t)(w_n >> 31);   /* zeros after the 32 bits of x */
        w_n <<= 1;
        w_r = (w_r << 1) | bit;
        w_q <<= 1;
        if (w_r >= w_c) {
            w_r -= w_c;
            w_q += 1;
        }
    }
    return w_q + ((2 * w_r >= w_c) ? 1 : 0);
}

/* 16 x 16 partial products with carry: w_hi:w_lo = w_a * w_b */
static void mul64(void)
{
    uint16_t a0 = (uint16_t)w_a, a1 = (uint16_t)(w_a >> 16);
    uint16_t b0 = (uint16_t)w_b, b1 = (uint16_t)(w_b >> 16);
    uint32_t p00 = (uint32_t)a0 * b0;
    uint32_t p01 = (uint32_t)a0 * b1;
    uint32_t p10 = (uint32_t)a1 * b0;
    uint32_t p11 = (uint32_t)a1 * b1;
    uint32_t mid = (p00 >> 16) + (p01 & 0xFFFF) + (p10 & 0xFFFF);

    w_lo = (p00 & 0xFFFF) | (mid << 16);
    w_hi = p11 + (p01 >> 16) + (p10 >> 16) + (mid >> 16);
}

uint32_t ar_shldiv(uint32_t a, uint8_t k, uint32_t c)
{
    if (c == 0)
        return 0;
    return rnd_shl(a, k, c);
}

uint32_t ar_muldiv(uint32_t a, uint32_t b, uint32_t c)
{
    uint32_t hi;

    if (c == 0)
        return 0;
    /* fast regime: a * b fits in 32 bits (boundary a = floor((2^32-1)/b) is slow) */
    if (a == 0 || b == 0 || a < 0xFFFFFFFFUL / b)
        return (a * b) / c;
    w_a = a;
    w_b = b;
    mul64();
    hi = rnd_shl(w_hi, 32, c);
    return hi + rnd_shl(w_lo, 0, c);
}
