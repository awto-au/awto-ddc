/* reg.c: multi-byte register access, big-endian in register space. Spec: reg section 1. */
#include <stdint.h>
#include "reg.h"

/* write hook: host tests redefine REG8_WR to record writes (see tests/host/test_reg.c) */
#ifndef REG8_WR
#define REG8_WR(a, v) (REG8(a) = (uint8_t)(v))
#endif

uint16_t reg_rd16(uint16_t a)
{
    uint8_t hi = reg_rd(a);
    return ((uint16_t)hi << 8) | reg_rd(a + 1);
}

void reg_wr16(uint16_t a, uint16_t v)
{
    REG8_WR(a, v >> 8);
    REG8_WR(a + 1, v);
}

uint32_t reg_rd32(uint16_t a)
{
    uint8_t b0 = reg_rd(a);
    uint8_t b1 = reg_rd(a + 1);
    uint8_t b2 = reg_rd(a + 2);
    uint8_t b3 = reg_rd(a + 3);
    return ((uint32_t)b0 << 24) | ((uint32_t)b1 << 16) | ((uint32_t)b2 << 8) | b3;
}

void reg_wr32(uint16_t a, uint32_t v)
{
    REG8_WR(a, v >> 24);
    REG8_WR(a + 1, v >> 16);
    REG8_WR(a + 2, v >> 8);
    REG8_WR(a + 3, v);
}

void reg_rmw32(uint16_t a, uint32_t keep, uint32_t set)
{
    reg_wr32(a, (reg_rd32(a) & keep) | (set & ~keep));
}

/* step 0 adds nothing to a: every byte goes to the same address */
void reg_wr_n(uint16_t a, const uint8_t *src, uint16_t n, uint8_t step)
{
    while (n--) {
        REG8_WR(a, *src++);
        a += step;
    }
}

void reg_rd_n(uint16_t a, uint8_t *dst, uint16_t n, uint8_t step)
{
    while (n--) {
        *dst++ = reg_rd(a);
        a += step;
    }
}
